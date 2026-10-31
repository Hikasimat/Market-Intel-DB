"""
Manager dashboard analytics endpoint.

GET /api/manager-dashboard/?date=YYYY-MM-DD

Returns aggregated PRE/LQ performance metrics for the given reporting date.
All calculations use MANAGER_REPORT_TIMEZONE from settings (defaults to TIME_ZONE).
"""
import hashlib
from datetime import date as date_type

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from rest_framework import status

from accounts.permissions import IsManagerOrSuperuser
from .models import (
    Prospect, LeadQualification, CallActivity, CommunicationActivity,
    OutreachEmail,
)
from .serializers import ProspectSerializer

User = get_user_model()

# ────────────────────────────────────────────────────────────────────────────
# Timezone helpers
# ────────────────────────────────────────────────────────────────────────────

def _get_report_tz():
    import zoneinfo
    tz_name = getattr(settings, 'MANAGER_REPORT_TIMEZONE', settings.TIME_ZONE)
    try:
        return zoneinfo.ZoneInfo(tz_name)
    except Exception:
        return timezone.utc


def _day_bounds(reporting_date):
    """Return (day_start, day_end) as aware datetimes in the reporting timezone."""
    import datetime
    tz = _get_report_tz()
    day_start = timezone.datetime(
        reporting_date.year, reporting_date.month, reporting_date.day,
        0, 0, 0, tzinfo=tz
    )
    day_end = day_start + datetime.timedelta(days=1)
    return day_start, day_end


# ────────────────────────────────────────────────────────────────────────────
# ────────────────────────────────────────────────────────────────────────────
# LQ distribution helper: prospects mapped directly to their creator PRE user
# ────────────────────────────────────────────────────────────────────────────

def _get_all_lq_users():
    """Return ordered list of PRE users handling LQ pipeline (non-superuser, by id)."""
    return list(
        User.objects.filter(profile__role__in=['PRE', 'LQ'], is_superuser=False)
        .order_by('id')
        .values_list('id', flat=True)
    )


def _get_lq_assignment_map():
    """
    Returns a dict: {user_id: [prospect_id, ...]} for ALL prospects,
    mapping prospects directly to the creator PRE user (or assigned_lq).
    Removes the 5-record split and round-robin formula entirely.
    """
    users = list(
        User.objects.filter(profile__role__in=['PRE', 'LQ'], is_superuser=False)
        .order_by('id')
    )
    user_by_username = {u.username: u.id for u in users}
    user_ids_set = {u.id for u in users}
    assignment = {u.id: [] for u in users}

    all_prospects = list(
        Prospect.objects.order_by('created_at', 'id').values(
            'id', 'created_by', 'lead_qualification__assigned_lq'
        )
    )

    for p in all_prospects:
        pid = p['id']
        assigned_lq_id = p.get('lead_qualification__assigned_lq')
        creator_username = p.get('created_by')

        target_uid = None
        if creator_username and creator_username in user_by_username:
            target_uid = user_by_username[creator_username]
        elif assigned_lq_id and assigned_lq_id in user_ids_set:
            target_uid = assigned_lq_id

        if target_uid and target_uid in assignment:
            assignment[target_uid].append(pid)

    return assignment


def _get_lq_received_on_date(lq_user_id, day_start, day_end, assignment_map):
    """
    Return list of prospect IDs assigned to lq_user_id that were created on the given day.
    Uses the pre-computed global assignment map so we honour the full ordering.
    """
    assigned_ids = assignment_map.get(lq_user_id, [])
    if not assigned_ids:
        return []
    # Filter to those created on the selected date
    return list(
        Prospect.objects.filter(
            id__in=assigned_ids,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).values_list('id', flat=True)
    )


# ────────────────────────────────────────────────────────────────────────────
# Deterministic audit sample
# ────────────────────────────────────────────────────────────────────────────

def _stable_sample(prospect_ids, reporting_date, lq_user_id, n=10):
    """
    Returns the first n records created/assigned on this day for the user.
    Sorting by id guarantees chronological order, so the list never shifts
    even if new records are added later in the day.
    """
    return sorted(prospect_ids)[:n]


# ────────────────────────────────────────────────────────────────────────────
# Main analytics view
# ────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsManagerOrSuperuser])
def manager_dashboard(request):
    """
    GET /api/manager-dashboard/?date=YYYY-MM-DD

    Returns structured analytics for the Manager dashboard.
    """
    # --- Resolve reporting date ---
    date_str = request.query_params.get('date')
    if date_str:
        try:
            reporting_date = date_type.fromisoformat(date_str)
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
    else:
        tz = _get_report_tz()
        reporting_date = timezone.now().astimezone(tz).date()

    day_start, day_end = _day_bounds(reporting_date)

    # --- Fetch all LQ users and assignment map once ---
    lq_user_ids = _get_all_lq_users()
    lq_users_qs = User.objects.filter(id__in=lq_user_ids).select_related('profile')
    lq_users = list(lq_users_qs)

    assignment_map = _get_lq_assignment_map()

    # --- PRE users ---
    pre_users = list(
        User.objects.filter(profile__role='PRE', is_superuser=False)
        .select_related('profile')
        .order_by('id')
    )

    # ── PRE DAILY PRODUCTION ──────────────────────────────────────────────
    pre_users_data = []
    total_pre_entered = 0
    for pre_user in pre_users:
        count = Prospect.objects.filter(
            created_by=pre_user.username,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).count()
        pre_users_data.append({
            'user_id': pre_user.id,
            'name': pre_user.get_full_name() or pre_user.username,
            'username': pre_user.username,
            'prospects_entered': count,
        })
        total_pre_entered += count

    # ── LQ DAILY METRICS ─────────────────────────────────────────────────
    lq_users_data = []
    total_lq_received = 0
    total_attended = 0
    total_lead_qualified = 0
    total_not_lead_qualified = 0
    total_activities = 0

    for lq_user in lq_users:
        received_ids = _get_lq_received_on_date(lq_user.id, day_start, day_end, assignment_map)
        received_count = len(received_ids)
        total_lq_received += received_count

        # Attended: attended_at on the selected date
        attended_count = LeadQualification.objects.filter(
            attended_at__gte=day_start,
            attended_at__lt=day_end,
            decision_by=lq_user,
        ).count()
        # Fallback: if decision_by not set, use qualified_by
        attended_count_fallback = LeadQualification.objects.filter(
            attended_at__gte=day_start,
            attended_at__lt=day_end,
            qualified_by=lq_user,
            decision_by__isnull=True,
        ).count()
        attended_count = attended_count + attended_count_fallback
        total_attended += attended_count

        # Lead Qualified decisions on this date
        lq_count = LeadQualification.objects.filter(
            decision_at__gte=day_start,
            decision_at__lt=day_end,
            decision_by=lq_user,
            qualification_status='Lead Qualified',
        ).count()
        total_lead_qualified += lq_count

        # Not Lead Qualified decisions on this date (decided but not LQ)
        not_lq_count = LeadQualification.objects.filter(
            decision_at__gte=day_start,
            decision_at__lt=day_end,
            decision_by=lq_user,
        ).exclude(qualification_status='Lead Qualified').exclude(
            qualification_status='Unqualified'
        ).count()
        # Also count explicitly disqualified etc on this day
        not_lq_count_2 = LeadQualification.objects.filter(
            decision_at__gte=day_start,
            decision_at__lt=day_end,
            decision_by=lq_user,
            qualification_status__in=['Disqualified', 'Lead Freeze', 'Nurture'],
        ).count()
        not_lq_count = max(not_lq_count, not_lq_count_2)
        total_not_lead_qualified += not_lq_count

        # Activities: calls + emails + comm activity on this date by this user
        calls_count = CallActivity.objects.filter(
            created_by=lq_user,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).count()
        emails_count = OutreachEmail.objects.filter(
            created_by=lq_user,
            sent_at__gte=day_start,
            sent_at__lt=day_end,
        ).count()
        total_activities += calls_count + emails_count

        # PRE → LQ source breakdown for received records on this date
        pre_source = {}
        if received_ids:
            qs = Prospect.objects.filter(
                id__in=received_ids,
                created_at__gte=day_start,
                created_at__lt=day_end,
            ).values('created_by').annotate(count=Count('id'))
            for row in qs:
                pre_source[row['created_by'] or 'Unknown'] = row['count']

        lq_users_data.append({
            'user_id': lq_user.id,
            'name': lq_user.get_full_name() or lq_user.username,
            'username': lq_user.username,
            'received': received_count,
            'attended': attended_count,
            'lead_qualified': lq_count,
            'not_lead_qualified': not_lq_count,
            'calls': calls_count,
            'emails_sent': emails_count,
            'pre_source': pre_source,
        })

    # ── PRE AUDIT SAMPLES ─────────────────────────────────────────────────
    pre_audit_samples = []
    for pre_user in pre_users:
        entered_ids = list(Prospect.objects.filter(
            created_by=pre_user.username,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).values_list('id', flat=True))
        
        sample_ids = _stable_sample(entered_ids, reporting_date, pre_user.id, n=10)
        sample_prospects = []
        if sample_ids:
            prospects_qs = Prospect.objects.filter(id__in=sample_ids).select_related(
                'lead_qualification'
            ).prefetch_related(
                'email_verifications',
                'market_event_participations__market_event',
                'offerings',
                'key_contacts',
                'parent_companies',
                'child_companies',
                'reverification_requests'
            ).annotate(
                emails_sent_annotated=Count(
                    'communication_timeline',
                    filter=Q(communication_timeline__activity_type='EMAIL_SENT'),
                    distinct=True
                ),
                calls_logged_annotated=Count(
                    'communication_timeline',
                    filter=Q(communication_timeline__activity_type='CALL'),
                    distinct=True
                )
            )
            p_dict = {str(p.id): p for p in prospects_qs}
            for pid in sample_ids:
                p = p_dict.get(str(pid))
                if p:
                    sample_prospects.append(ProspectSerializer(p).data)
        pre_audit_samples.append({
            'pre_user_id': pre_user.id,
            'pre_name': pre_user.get_full_name() or pre_user.username,
            'entered_total': len(entered_ids),
            'sample_count': len(sample_prospects),
            'sample': sample_prospects,
        })

    # ── LQ AUDIT SAMPLES ──────────────────────────────────────────────────
    audit_samples = []
    for lq_user in lq_users:
        received_ids = _get_lq_received_on_date(lq_user.id, day_start, day_end, assignment_map)
        sample_ids = _stable_sample(received_ids, reporting_date, lq_user.id, n=10)

        sample_prospects = []
        if sample_ids:
            prospects_qs = Prospect.objects.filter(id__in=sample_ids).select_related(
                'lead_qualification'
            ).prefetch_related(
                'email_verifications',
                'market_event_participations__market_event',
                'offerings',
                'key_contacts',
                'parent_companies',
                'child_companies',
                'reverification_requests'
            ).annotate(
                emails_sent_annotated=Count(
                    'communication_timeline',
                    filter=Q(communication_timeline__activity_type='EMAIL_SENT'),
                    distinct=True
                ),
                calls_logged_annotated=Count(
                    'communication_timeline',
                    filter=Q(communication_timeline__activity_type='CALL'),
                    distinct=True
                )
            )
            # Build dict to preserve stable order
            p_dict = {str(p.id): p for p in prospects_qs}
            for pid in sample_ids:
                p = p_dict.get(str(pid))
                if not p:
                    continue
                lq_obj = getattr(p, 'lead_qualification', None)
                item_data = ProspectSerializer(p).data
                item_data.update({
                    'verification_status': lq_obj.verification_status if lq_obj else None,
                    'qualification_status': lq_obj.qualification_status if lq_obj else None,
                    'attended_meeting': lq_obj.attended_meeting if lq_obj else False,
                    'attended_at': lq_obj.attended_at.isoformat() if lq_obj and lq_obj.attended_at else None,
                    'decision_at': lq_obj.decision_at.isoformat() if lq_obj and lq_obj.decision_at else None,
                })
                
                # Retrieve LQ activities performed today on this prospect
                activities = []
                comm_acts = CommunicationActivity.objects.filter(
                    prospect=p,
                    performed_by=lq_user,
                    created_at__gte=day_start,
                    created_at__lt=day_end,
                ).order_by('created_at')
                for ca in comm_acts:
                    activities.append(f"{ca.get_activity_type_display()} - {ca.status or 'Completed'}")
                    
                if lq_obj and lq_obj.decision_at and day_start <= lq_obj.decision_at < day_end:
                    activities.append(f"Record decision: {lq_obj.qualification_status}")
                    
                item_data['lq_activities'] = activities
                sample_prospects.append(item_data)

        audit_samples.append({
            'lq_user_id': lq_user.id,
            'lq_name': lq_user.get_full_name() or lq_user.username,
            'received_total': len(received_ids),
            'sample_count': len(sample_prospects),
            'sample': sample_prospects,
        })

    # ── PRE → LQ DISTRIBUTION SUMMARY ───────────────────────────────────
    lq_pre_distribution = []
    for entry in lq_users_data:
        lq_pre_distribution.append({
            'lq_user_id': entry['user_id'],
            'lq_name': entry['name'],
            'received': entry['received'],
            'pre_source': entry['pre_source'],
        })

    # ── USER ACTIVITY (date-wise) ─────────────────────────────────────────
    user_activity = []

    # PRE activity (including unified LQ tasks)
    for pre_user in pre_users:
        entered = Prospect.objects.filter(
            created_by=pre_user.username,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).count()
        email_verifications = CommunicationActivity.objects.filter(
            performed_by=pre_user,
            created_at__gte=day_start,
            created_at__lt=day_end,
            activity_type='EMAIL_SENT',
        ).count()
        calls = CallActivity.objects.filter(
            created_by=pre_user,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).count()
        emails = OutreachEmail.objects.filter(
            created_by=pre_user,
            sent_at__gte=day_start,
            sent_at__lt=day_end,
        ).count()
        decisions = LeadQualification.objects.filter(
            decision_by=pre_user,
            decision_at__gte=day_start,
            decision_at__lt=day_end,
        ).count()
        attended = LeadQualification.objects.filter(
            attended_at__gte=day_start,
            attended_at__lt=day_end,
            decision_by=pre_user,
        ).count()
        lq_decisions = LeadQualification.objects.filter(
            decision_by=pre_user,
            decision_at__gte=day_start,
            decision_at__lt=day_end,
            qualification_status='Lead Qualified',
        ).count()
        not_lq_decisions = LeadQualification.objects.filter(
            decision_by=pre_user,
            decision_at__gte=day_start,
            decision_at__lt=day_end,
        ).exclude(qualification_status__in=['Lead Qualified', 'Unqualified']).count()

        if any([entered, email_verifications, calls, emails, decisions, attended]):
            user_activity.append({
                'user_id': pre_user.id,
                'name': pre_user.get_full_name() or pre_user.username,
                'role': 'PRE',
                'prospects_entered': entered,
                'email_verifications': email_verifications,
                'calls': calls,
                'emails_sent': emails,
                'qualification_decisions': decisions,
                'attended': attended,
                'lead_qualified': lq_decisions,
                'not_lead_qualified': not_lq_decisions,
            })

    # Legacy LQ users if any distinct from pre_users
    pre_user_ids = {u.id for u in pre_users}
    for lq_user in lq_users:
        if lq_user.id in pre_user_ids:
            continue
        calls = CallActivity.objects.filter(
            created_by=lq_user,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).count()
        emails = OutreachEmail.objects.filter(
            created_by=lq_user,
            sent_at__gte=day_start,
            sent_at__lt=day_end,
        ).count()
        decisions = LeadQualification.objects.filter(
            decision_by=lq_user,
            decision_at__gte=day_start,
            decision_at__lt=day_end,
        ).count()
        attended = LeadQualification.objects.filter(
            attended_at__gte=day_start,
            attended_at__lt=day_end,
            decision_by=lq_user,
        ).count()
        lq_decisions = LeadQualification.objects.filter(
            decision_by=lq_user,
            decision_at__gte=day_start,
            decision_at__lt=day_end,
            qualification_status='Lead Qualified',
        ).count()
        not_lq_decisions = LeadQualification.objects.filter(
            decision_by=lq_user,
            decision_at__gte=day_start,
            decision_at__lt=day_end,
        ).exclude(qualification_status__in=['Lead Qualified', 'Unqualified']).count()

        if any([calls, emails, decisions]):
            user_activity.append({
                'user_id': lq_user.id,
                'name': lq_user.get_full_name() or lq_user.username,
                'role': 'LQ',
                'prospects_entered': 0,
                'email_verifications': 0,
                'calls': calls,
                'emails_sent': emails,
                'qualification_decisions': decisions,
                'attended': attended,
                'lead_qualified': lq_decisions,
                'not_lead_qualified': not_lq_decisions,
            })

    # ── SUMMARY ──────────────────────────────────────────────────────────
    summary = {
        'pre_entered': total_pre_entered,
        'lq_received': total_lq_received,
        'attended': total_attended,
        'lead_qualified': total_lead_qualified,
        'not_lead_qualified': total_not_lead_qualified,
        'activities': total_activities,
        'pre_users_active': len([u for u in pre_users_data if u['prospects_entered'] > 0]),
        'lq_users_active': len([u for u in lq_users_data if u['received'] > 0]),
    }

    return Response({
        'date': reporting_date.isoformat(),
        'summary': summary,
        'pre_users': pre_users_data,
        'lq_users': lq_users_data,
        'lq_pre_distribution': lq_pre_distribution,
        'pre_audit_samples': pre_audit_samples,
        'audit_samples': audit_samples,
        'user_activity': user_activity,
    })
