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
    OutreachEmail, EmailThread, EmailThreadMessage,
)
from .serializers import (
    ProspectSerializer, EmailThreadListSerializer, EmailThreadDetailSerializer,
)

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


# ────────────────────────────────────────────────────────────────────────────
# Manager Email Activity & AI Conversation Summaries (Part B)
# ────────────────────────────────────────────────────────────────────────────

def _get_authorized_pre_users_for_manager(request_user):
    """
    Dynamically return active PRE/LQ users within the manager's authorized company scope.
    Superusers can view all companies.
    Managers with company assigned see only PRE/LQ users in that same company.
    Managers without a company see PRE/LQ users without a company (backward compatibility).
    Never uses hardcoded user IDs or fixed user counts.
    """
    qs = User.objects.filter(
        is_active=True,
        is_superuser=False,
        profile__role__in=['PRE', 'LQ'],
    ).select_related('profile').order_by('id')

    if request_user.is_superuser:
        return qs

    mgr_company_id = getattr(getattr(request_user, 'profile', None), 'company_id', None)
    if mgr_company_id is not None:
        return qs.filter(profile__company_id=mgr_company_id)
    return qs.filter(profile__company__isnull=True)


def _parse_date_range_bounds(request):
    """Parse optional ?date=YYYY-MM-DD or ?date_from=...&date_to=... into UTC aware datetimes."""
    import datetime
    single_date = (request.query_params.get('date') or '').strip()
    date_from = (request.query_params.get('date_from') or '').strip()
    date_to = (request.query_params.get('date_to') or '').strip()

    tz = _get_report_tz()
    start_dt = None
    end_dt = None

    if single_date:
        try:
            d = date_type.fromisoformat(single_date)
            return _day_bounds(d)
        except ValueError:
            pass

    if date_from:
        try:
            df = date_type.fromisoformat(date_from)
            start_dt = timezone.datetime(df.year, df.month, df.day, 0, 0, 0, tzinfo=tz)
        except ValueError:
            pass

    if date_to:
        try:
            dt = date_type.fromisoformat(date_to)
            end_dt = timezone.datetime(dt.year, dt.month, dt.day, 0, 0, 0, tzinfo=tz) + datetime.timedelta(days=1)
        except ValueError:
            pass

    return start_dt, end_dt


@api_view(['GET'])
@permission_classes([IsManagerOrSuperuser])
def manager_email_activity_list(request):
    """
    GET /api/manager-dashboard/email-activity/
    Returns paginated email conversation threads + AI summaries across all
    authorized PRE/LQ users with filters (pre_user_id, date, date_from, date_to,
    search, status, direction, match_status).
    """
    import sys
    from .email_thread_service import (
        backfill_outreach_emails_to_threads,
        sync_authorized_mailboxes,
    )
    from .email_summarizer import schedule_thread_summary, _resolve_provider_and_key

    authorized_users = list(_get_authorized_pre_users_for_manager(request.user))
    authorized_ids = [u.id for u in authorized_users]

    # Opportunistic idempotent backfill for legacy OutreachEmail records without threads
    if authorized_ids and OutreachEmail.objects.filter(
        created_by_id__in=authorized_ids,
        thread_message__isnull=True,
    ).exists():
        try:
            backfill_outreach_emails_to_threads(authorized_ids)
        except Exception:
            pass

    base_qs = (
        EmailThread.objects
        .select_related('owner', 'owner__profile', 'prospect', 'prospect_contact')
        .filter(owner_id__in=authorized_ids)
    )

    # Filter by specific PRE user (strictly within authorized scope)
    pre_user_id = (request.query_params.get('pre_user_id') or '').strip()
    filter_uid = None
    if pre_user_id and pre_user_id.lower() != 'all':
        try:
            uid_int = int(pre_user_id)
        except ValueError:
            return Response({'detail': 'Invalid pre_user_id.'}, status=status.HTTP_400_BAD_REQUEST)
        if uid_int not in authorized_ids:
            # Distinguish out-of-tenant unauthorized user from nonexistent user cleanly
            if User.objects.filter(pk=uid_int).exists():
                return Response(
                    {'detail': 'You are not authorized to access this PRE user.'},
                    status=status.HTTP_403_FORBIDDEN,
                )
            base_qs = base_qs.none()
        else:
            filter_uid = uid_int
            base_qs = base_qs.filter(owner_id=uid_int)

    # Sync incoming replies from authorized PRE Gmail mailboxes automatically
    # (cooldown-throttled every 30s unless ?sync=true; skipped inside unit test runs unless ?sync=true)
    sync_param = (request.query_params.get('sync') or '').strip().lower()
    force_sync = sync_param in ('1', 'true', 'yes')
    running_tests = ('test' in sys.argv)
    if authorized_ids and (force_sync or not running_tests):
        try:
            sync_authorized_mailboxes(
                authorized_ids,
                pre_user_id=filter_uid,
                force=force_sync,
                limit=25,
            )
        except Exception:
            pass

    # Date range filter
    start_dt, end_dt = _parse_date_range_bounds(request)
    if start_dt is not None:
        base_qs = base_qs.filter(
            Q(last_message_at__gte=start_dt)
            | Q(last_message_at__isnull=True, created_at__gte=start_dt)
        )
    if end_dt is not None:
        base_qs = base_qs.filter(
            Q(last_message_at__lt=end_dt)
            | Q(last_message_at__isnull=True, created_at__lt=end_dt)
        )

    # Status / Direction / Match Status filters
    status_filter = (request.query_params.get('status') or '').strip().upper()
    if status_filter and status_filter != 'ALL':
        base_qs = base_qs.filter(status=status_filter)

    direction_filter = (request.query_params.get('direction') or '').strip().upper()
    if direction_filter and direction_filter != 'ALL':
        base_qs = base_qs.filter(last_direction=direction_filter)

    match_filter = (request.query_params.get('match_status') or '').strip().upper()
    if match_filter and match_filter != 'ALL':
        base_qs = base_qs.filter(match_status=match_filter)

    # Search filter (subject, correspondent, prospect, snippet, summary)
    search_q = (request.query_params.get('search') or '').strip()
    if search_q:
        base_qs = base_qs.filter(
            Q(subject__icontains=search_q)
            | Q(correspondent_email__icontains=search_q)
            | Q(correspondent_name__icontains=search_q)
            | Q(mailbox_email__icontains=search_q)
            | Q(prospect__company_name__icontains=search_q)
            | Q(last_snippet__icontains=search_q)
            | Q(summary_text__icontains=search_q)
            | Q(owner__username__icontains=search_q)
            | Q(owner__first_name__icontains=search_q)
            | Q(owner__last_name__icontains=search_q)
        )

    # Aggregate counts before pagination
    agg = base_qs.aggregate(
        total=Count('id'),
        waiting=Count('id', filter=Q(status=EmailThread.Status.WAITING_REPLY)),
        replied=Count('id', filter=Q(status=EmailThread.Status.REPLIED)),
        failed=Count('id', filter=Q(status=EmailThread.Status.FAILED)),
        unmatched=Count('id', filter=Q(match_status=EmailThread.MatchStatus.UNMATCHED)),
    )

    # Dynamic list of authorized PRE users + per-user thread counts
    per_user_counts = dict(
        EmailThread.objects.filter(owner_id__in=authorized_ids)
        .values('owner_id')
        .annotate(c=Count('id'))
        .values_list('owner_id', 'c')
    )
    pre_users_meta = [
        {
            'id': u.id,
            'name': u.get_full_name() or u.username,
            'username': u.username,
            'email': u.email,
            'role': getattr(getattr(u, 'profile', None), 'role', 'PRE'),
            'thread_count': per_user_counts.get(u.id, 0),
        }
        for u in authorized_users
    ]

    # Pagination
    try:
        page = max(1, int(request.query_params.get('page') or 1))
    except ValueError:
        page = 1
    try:
        page_size = min(100, max(1, int(request.query_params.get('page_size') or 20)))
    except ValueError:
        page_size = 20

    total_count = agg['total'] or 0
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    offset = (page - 1) * page_size

    page_threads = list(base_qs.order_by('-last_message_at', '-updated_at')[offset:offset + page_size])

    # Trigger non-blocking summary for any page thread still PENDING
    for th in page_threads:
        if th.summary_status == EmailThread.SummaryStatus.PENDING and th.message_count > 0:
            schedule_thread_summary(th.id)

    serializer = EmailThreadListSerializer(page_threads, many=True)
    return Response({
        'count': total_count,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
        'pre_users': pre_users_meta,
        'stats': {
            'total_threads': total_count,
            'waiting_reply': agg['waiting'] or 0,
            'replied': agg['replied'] or 0,
            'failed': agg['failed'] or 0,
            'unmatched': agg['unmatched'] or 0,
        },
        'results': serializer.data,
    })


@api_view(['GET'])
@permission_classes([IsManagerOrSuperuser])
def manager_email_activity_detail(request, thread_id):
    """
    GET /api/manager-dashboard/email-activity/<uuid:thread_id>/
    Returns chronological full email thread messages & safe metadata for the manager.
    """
    authorized_ids = list(
        _get_authorized_pre_users_for_manager(request.user).values_list('id', flat=True)
    )
    thread = (
        EmailThread.objects
        .select_related('owner', 'owner__profile', 'prospect', 'prospect_contact')
        .prefetch_related('messages')
        .filter(pk=thread_id)
        .first()
    )
    if not thread:
        return Response({'detail': 'Email thread not found.'}, status=status.HTTP_404_NOT_FOUND)
    if thread.owner_id not in authorized_ids and not request.user.is_superuser:
        return Response({'detail': 'You are not authorized to view this email thread.'}, status=status.HTTP_403_FORBIDDEN)

    if thread.summary_status == EmailThread.SummaryStatus.PENDING and thread.message_count > 0:
        from .email_summarizer import schedule_thread_summary
        schedule_thread_summary(thread.id)

    serializer = EmailThreadDetailSerializer(thread)
    return Response(serializer.data)


@api_view(['POST'])
@permission_classes([IsManagerOrSuperuser])
def manager_email_summary_refresh(request, thread_id):
    """
    POST /api/manager-dashboard/email-activity/<uuid:thread_id>/refresh-summary/
    Forces regeneration of the AI conversation summary for the given thread.
    """
    from .email_summarizer import summarize_email_thread

    authorized_ids = list(
        _get_authorized_pre_users_for_manager(request.user).values_list('id', flat=True)
    )
    thread = EmailThread.objects.filter(pk=thread_id).first()
    if not thread:
        return Response({'detail': 'Email thread not found.'}, status=status.HTTP_404_NOT_FOUND)
    if thread.owner_id not in authorized_ids and not request.user.is_superuser:
        return Response({'detail': 'You are not authorized to refresh this thread summary.'}, status=status.HTTP_403_FORBIDDEN)

    result = summarize_email_thread(thread.id, force=True)
    thread.refresh_from_db()
    data = EmailThreadListSerializer(thread).data
    data['refresh_result'] = result
    return Response(data, status=status.HTTP_200_OK)
