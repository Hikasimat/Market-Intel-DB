"""
Manager dashboard & audit analytics endpoints.

GET /api/manager-dashboard/?date=YYYY-MM-DD[&include_audit=1]
GET /api/manager-dashboard/audit/?date=YYYY-MM-DD

Designed for the unified PRE architecture (where PRE owns the entire prospect,
outreach, email, WhatsApp, calendar, meeting, and qualification lifecycle).
All metrics query real database models and are strictly scoped to authorized
users in the manager's company (or global for superusers).
"""
from datetime import date as date_type, timedelta

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from accounts.models import (
    GoogleCalendarCredentials,
    GoogleMailCredentials,
    MicrosoftCalendarCredentials,
    ZoomCredentials,
)
from accounts.permissions import IsManagerOrSuperuser
from email_ai.views import (  # noqa: F401
    _day_bounds,
    _get_authorized_all_users_for_manager,
    _get_authorized_pre_users_for_manager,
    _get_report_tz,
    _parse_date_range_bounds,
    _serialize_daily_user_report,
    manager_daily_email_report,
    manager_daily_email_report_refresh,
    manager_email_activity_detail,
    manager_email_activity_list,
    manager_email_summary_refresh,
)
from whatsapp.models import (
    WhatsAppConfiguration,
    WhatsAppMessage,
    WhatsAppSession,
)
from whatsapp_ai.models import (
    WhatsAppAIAutoReplyConfig,
    WhatsAppAIReplyLog,
    WhatsAppMeetingRequest,
)
from .models import (
    AuditReverificationRequest,
    CallActivity,
    CommunicationActivity,
    EmailCampaign,
    EmailThread,
    EmailThreadMessage,
    LeadQualification,
    Meeting,
    OutreachEmail,
    PreTask,
    Prospect,
)
from .serializers import ProspectSerializer

User = get_user_model()


def _parse_reporting_date(request):
    """Parse optional ?date=YYYY-MM-DD or return today in MANAGER_REPORT_TIMEZONE."""
    tz = _get_report_tz()
    date_str = (request.query_params.get('date') or '').strip()
    if date_str:
        reporting_date = date_type.fromisoformat(date_str)
    else:
        reporting_date = timezone.now().astimezone(tz).date()
    return reporting_date, tz


def _stable_sample(prospect_ids, n=10):
    """Return a deterministic slice of up to `n` prospect IDs."""
    return sorted(prospect_ids, key=lambda pid: str(pid))[:n]


def _resolve_actor_uid(primary_id, fallback_id, creator_username, username_to_uid):
    if primary_id is not None:
        return primary_id
    if fallback_id is not None:
        return fallback_id
    if creator_username:
        return username_to_uid.get(creator_username)
    return None


def _build_pre_audit_samples(authorized_users, authorized_usernames, day_start, day_end):
    """
    Sample up to 10 prospects entered per active PRE user on the reporting date,
    enriched with unified qualification metadata and daily activities.
    """
    if not authorized_users:
        return []

    entered_rows = list(
        Prospect.objects.filter(
            created_by__in=authorized_usernames,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).order_by('id').values_list('id', 'created_by')
    )
    entered_by_username = {}
    for pid, uname in entered_rows:
        entered_by_username.setdefault(uname, []).append(pid)

    sampled_by_uid = {}
    all_sample_ids = []
    for pre_user in authorized_users:
        user_pids = entered_by_username.get(pre_user.username, [])
        sample_pids = _stable_sample(user_pids, n=10)
        sampled_by_uid[pre_user.id] = (len(user_pids), sample_pids)
        all_sample_ids.extend(sample_pids)

    prospects_by_id = {}
    activities_by_pid = {}
    if all_sample_ids:
        prospects_qs = (
            Prospect.objects.filter(id__in=all_sample_ids)
            .select_related('lead_qualification')
            .prefetch_related(
                'email_verifications',
                'market_event_participations__market_event',
                'offerings',
                'key_contacts',
                'parent_companies',
                'child_companies',
                'reverification_requests',
            )
            .annotate(
                emails_sent_annotated=Count(
                    'communication_timeline',
                    filter=Q(communication_timeline__activity_type='EMAIL_SENT'),
                    distinct=True,
                ),
                calls_logged_annotated=Count(
                    'communication_timeline',
                    filter=Q(communication_timeline__activity_type='CALL'),
                    distinct=True,
                ),
            )
        )
        prospects_by_id = {p.id: p for p in prospects_qs}

        comm_rows = (
            CommunicationActivity.objects.filter(
                prospect_id__in=all_sample_ids,
                created_at__gte=day_start,
                created_at__lt=day_end,
            )
            .select_related('performed_by')
            .order_by('created_at')
        )
        for ca in comm_rows:
            actor = (
                (ca.performed_by.get_full_name() or ca.performed_by.username)
                if ca.performed_by
                else 'System'
            )
            activities_by_pid.setdefault(ca.prospect_id, []).append(
                f"{ca.get_activity_type_display()} ({ca.status or 'Completed'}) by {actor}"
            )

        meeting_rows = (
            Meeting.objects.filter(
                prospect_id__in=all_sample_ids,
                created_at__gte=day_start,
                created_at__lt=day_end,
            )
            .exclude(status='CANCELLED')
            .order_by('created_at')
        )
        for mtg in meeting_rows:
            activities_by_pid.setdefault(mtg.prospect_id, []).append(
                f"Meeting scheduled ({mtg.get_meeting_provider_display()})"
            )

    samples = []
    for pre_user in authorized_users:
        entered_total, sample_pids = sampled_by_uid[pre_user.id]
        sample_prospects = []
        for pid in sample_pids:
            p = prospects_by_id.get(pid)
            if not p:
                continue
            lq_obj = getattr(p, 'lead_qualification', None)
            item_data = ProspectSerializer(p).data
            item_activities = list(activities_by_pid.get(p.id, []))
            if lq_obj and lq_obj.decision_at and day_start <= lq_obj.decision_at < day_end:
                item_activities.append(f"Qualification decision: {lq_obj.qualification_status}")
            item_data.update({
                'verification_status': lq_obj.verification_status if lq_obj else None,
                'qualification_status': lq_obj.qualification_status if lq_obj else None,
                'email_status': lq_obj.email_status if lq_obj else 'Not Sent',
                'attended_meeting': lq_obj.attended_meeting if lq_obj else False,
                'attended_at': lq_obj.attended_at.isoformat() if lq_obj and lq_obj.attended_at else None,
                'decision_at': lq_obj.decision_at.isoformat() if lq_obj and lq_obj.decision_at else None,
                'daily_activities': item_activities,
            })
            sample_prospects.append(item_data)

        samples.append({
            'pre_user_id': pre_user.id,
            'pre_name': pre_user.get_full_name() or pre_user.username,
            'pre_username': pre_user.username,
            'entered_total': entered_total,
            'sample_count': len(sample_prospects),
            'sample': sample_prospects,
        })
    return samples


def _build_reverification_list(request_user, authorized_ids, authorized_usernames, limit=100):
    """Return company-scoped AuditReverificationRequest items for the audit tracker."""
    qs = AuditReverificationRequest.objects.select_related('prospect', 'pre_user', 'manager')
    if not request_user.is_superuser:
        qs = qs.filter(
            Q(pre_user_id__in=authorized_ids)
            | Q(pre_user__isnull=True, prospect__created_by__in=authorized_usernames)
        )
    items = []
    for req in qs.order_by('-created_at')[:limit]:
        items.append({
            'id': req.id,
            'prospect_id': str(req.prospect_id),
            'prospect_company_name': req.prospect.company_name if req.prospect else '',
            'pre_user_id': req.pre_user_id,
            'pre_user_name': (
                (req.pre_user.get_full_name() or req.pre_user.username)
                if req.pre_user
                else (req.prospect.created_by if req.prospect else '')
            ),
            'manager_name': (req.manager.get_full_name() or req.manager.username) if req.manager else '',
            'highlighted_fields': req.highlighted_fields or [],
            'manager_notes': req.manager_notes or '',
            'status': req.status,
            'created_at': req.created_at.isoformat() if req.created_at else None,
            'resolved_at': req.resolved_at.isoformat() if req.resolved_at else None,
        })
    return items


@api_view(['GET'])
@permission_classes([IsManagerOrSuperuser])
def manager_dashboard(request):
    """
    GET /api/manager-dashboard/?date=YYYY-MM-DD

    Returns real-time operational metrics, pipeline funnel, unified PRE team
    performance & connected channel health, WhatsApp & AI automation monitor,
    upcoming meetings, PRE action tasks, bulk email campaigns, and a chronological
    activity stream for the Manager's authorized team.
    """
    try:
        reporting_date, tz = _parse_reporting_date(request)
    except ValueError:
        return Response(
            {'error': 'Invalid date format. Use YYYY-MM-DD.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    now = timezone.now()
    today_in_tz = now.astimezone(tz).date()
    day_start, day_end = _day_bounds(reporting_date)

    authorized_users = list(
        _get_authorized_pre_users_for_manager(request.user)
        .select_related('profile', 'profile__mail_account')
    )
    authorized_ids = [u.id for u in authorized_users]
    authorized_ids_set = set(authorized_ids)
    authorized_usernames = [u.username for u in authorized_users]
    username_to_uid = {u.username: u.id for u in authorized_users}
    uid_to_name = {u.id: (u.get_full_name() or u.username) for u in authorized_users}

    def _empty_counter():
        return {uid: 0 for uid in authorized_ids}

    prospects_today_by_uid = _empty_counter()
    total_prospects_by_uid = _empty_counter()
    lq_today_by_uid = _empty_counter()
    not_lq_today_by_uid = _empty_counter()
    qualified_decisions_today = 0
    attended_today_by_uid = _empty_counter()
    calls_today_by_uid = _empty_counter()
    emails_sent_today_by_uid = _empty_counter()
    emails_received_today_by_uid = _empty_counter()
    emails_opened_today_by_uid = _empty_counter()
    wa_out_today_by_uid = _empty_counter()
    wa_in_today_by_uid = _empty_counter()
    wa_ai_today_by_uid = _empty_counter()
    meetings_today_by_uid = _empty_counter()
    meetings_created_today_by_uid = _empty_counter()
    upcoming_meetings_by_uid = _empty_counter()
    tasks_completed_today_by_uid = _empty_counter()
    pending_tasks_by_uid = _empty_counter()
    waiting_threads_by_uid = _empty_counter()
    replied_threads_total = 0
    waiting_threads_total = 0

    funnel_counts = {
        'total': 0,
        'lead_qualified': 0,
        'received_response': 0,
        'waiting_for_response': 0,
        'call_follow_up': 0,
        'ready_for_outreach': 0,
        'lead_freeze': 0,
    }
    total_lq_by_uid = _empty_counter()

    tasks_created_today = 0
    email_reply_pending = 0
    whatsapp_escalation_pending = 0
    pending_tasks_total = 0
    pending_audit_reverifications = 0
    wa_ai_failed_today = 0
    wa_ai_skipped_today = 0
    wa_ai_meetings_scheduled_today = 0
    wa_ai_meetings_in_progress = 0

    if authorized_ids:
        # 1. Prospects entered (selected date + all-time per PRE)
        for row in (
            Prospect.objects.filter(
                created_by__in=authorized_usernames,
                created_at__gte=day_start,
                created_at__lt=day_end,
            )
            .values('created_by')
            .annotate(c=Count('id'))
        ):
            uid = username_to_uid.get(row['created_by'])
            if uid is not None:
                prospects_today_by_uid[uid] += row['c']

        for row in (
            Prospect.objects.filter(created_by__in=authorized_usernames)
            .values('created_by')
            .annotate(c=Count('id'))
        ):
            uid = username_to_uid.get(row['created_by'])
            if uid is not None:
                total_prospects_by_uid[uid] += row['c']

        # 2. Live Outreach & Pipeline Funnel + per-PRE total lead qualified
        # Matches real Outreach statuses in LqPipelinePage / LqWorkspaceModal
        prospect_ids_with_calls = set(
            CallActivity.objects.filter(prospect__created_by__in=authorized_usernames)
            .values_list('prospect_id', flat=True)
            .distinct()
        )
        for row in (
            LeadQualification.objects.filter(prospect__created_by__in=authorized_usernames)
            .values('prospect_id', 'qualification_status', 'email_status', 'prospect__created_by')
        ):
            q_status = row['qualification_status']
            e_status = (row['email_status'] or '').strip().lower()
            funnel_counts['total'] += 1

            if q_status == LeadQualification.QualificationStatus.LEAD_QUALIFIED:
                funnel_counts['lead_qualified'] += 1
                uid = username_to_uid.get(row['prospect__created_by'])
                if uid is not None:
                    total_lq_by_uid[uid] += 1
            elif q_status == LeadQualification.QualificationStatus.LEAD_FREEZE:
                funnel_counts['lead_freeze'] += 1
            elif e_status == 'received response':
                funnel_counts['received_response'] += 1
            elif e_status in ('waiting for response', 'sent'):
                funnel_counts['waiting_for_response'] += 1
            elif row['prospect_id'] in prospect_ids_with_calls:
                funnel_counts['call_follow_up'] += 1
            else:
                funnel_counts['ready_for_outreach'] += 1

        # 3. Qualification decisions on reporting date
        seen_decision_ids = set()
        for row in (
            LeadQualification.objects.filter(
                decision_at__gte=day_start,
                decision_at__lt=day_end,
            )
            .filter(
                Q(decision_by_id__in=authorized_ids)
                | Q(decision_by__isnull=True, qualified_by_id__in=authorized_ids)
                | Q(
                    decision_by__isnull=True,
                    qualified_by__isnull=True,
                    prospect__created_by__in=authorized_usernames,
                )
            )
            .values('id', 'decision_by_id', 'qualified_by_id', 'prospect__created_by', 'qualification_status')
        ):
            if row['id'] in seen_decision_ids:
                continue
            seen_decision_ids.add(row['id'])
            uid = _resolve_actor_uid(
                row['decision_by_id'], row['qualified_by_id'], row['prospect__created_by'], username_to_uid
            )
            if uid not in authorized_ids_set:
                continue
            q_status = row['qualification_status']
            if q_status != LeadQualification.QualificationStatus.UNQUALIFIED:
                qualified_decisions_today += 1
            if q_status == LeadQualification.QualificationStatus.LEAD_QUALIFIED:
                lq_today_by_uid[uid] += 1
            elif q_status in (
                LeadQualification.QualificationStatus.DISQUALIFIED,
                LeadQualification.QualificationStatus.LEAD_FREEZE,
                LeadQualification.QualificationStatus.NURTURE,
            ):
                not_lq_today_by_uid[uid] += 1

        # 4. Attended meetings flagged on reporting date
        seen_attended_ids = set()
        for row in (
            LeadQualification.objects.filter(
                attended_at__gte=day_start,
                attended_at__lt=day_end,
            )
            .filter(
                Q(decision_by_id__in=authorized_ids)
                | Q(decision_by__isnull=True, qualified_by_id__in=authorized_ids)
                | Q(
                    decision_by__isnull=True,
                    qualified_by__isnull=True,
                    prospect__created_by__in=authorized_usernames,
                )
            )
            .values('id', 'decision_by_id', 'qualified_by_id', 'prospect__created_by')
        ):
            if row['id'] in seen_attended_ids:
                continue
            seen_attended_ids.add(row['id'])
            uid = _resolve_actor_uid(
                row['decision_by_id'], row['qualified_by_id'], row['prospect__created_by'], username_to_uid
            )
            if uid in authorized_ids_set:
                attended_today_by_uid[uid] += 1

        # 5. Calls logged on reporting date
        for row in (
            CallActivity.objects.filter(
                created_by_id__in=authorized_ids,
                created_at__gte=day_start,
                created_at__lt=day_end,
            )
            .values('created_by_id')
            .annotate(c=Count('id'))
        ):
            calls_today_by_uid[row['created_by_id']] += row['c']

        # 6. Emails sent / received / opened (outreach + inbox + campaigns without double-counting)
        day_msg_q = Q(sent_at__gte=day_start, sent_at__lt=day_end) | Q(
            sent_at__isnull=True, created_at__gte=day_start, created_at__lt=day_end
        )
        for row in (
            EmailThreadMessage.objects.filter(owner_id__in=authorized_ids)
            .filter(day_msg_q)
            .values('owner_id', 'direction', 'status')
            .annotate(c=Count('id'))
        ):
            uid = row['owner_id']
            if uid not in authorized_ids_set:
                continue
            if row['direction'] == EmailThreadMessage.Direction.OUTBOUND and row['status'] in (
                EmailThreadMessage.Status.SENT,
                EmailThreadMessage.Status.SENDING,
            ):
                emails_sent_today_by_uid[uid] += row['c']
            elif row['direction'] == EmailThreadMessage.Direction.INBOUND:
                emails_received_today_by_uid[uid] += row['c']

        # Legacy or standalone OutreachEmail rows not linked to EmailThreadMessage
        for row in (
            OutreachEmail.objects.filter(
                created_by_id__in=authorized_ids,
                thread_message__isnull=True,
                sent_at__gte=day_start,
                sent_at__lt=day_end,
            )
            .exclude(status__in=['NOT SENT', 'FAILED'])
            .values('created_by_id')
            .annotate(c=Count('id'))
        ):
            emails_sent_today_by_uid[row['created_by_id']] += row['c']

        for row in (
            OutreachEmail.objects.filter(
                created_by_id__in=authorized_ids,
                sent_at__gte=day_start,
                sent_at__lt=day_end,
                is_opened=True,
            )
            .values('created_by_id')
            .annotate(c=Count('id'))
        ):
            emails_opened_today_by_uid[row['created_by_id']] += row['c']

        # Live EmailThread health totals
        for row in (
            EmailThread.objects.filter(owner_id__in=authorized_ids)
            .values('owner_id', 'status')
            .annotate(c=Count('id'))
        ):
            if row['status'] == EmailThread.Status.WAITING_REPLY:
                waiting_threads_by_uid[row['owner_id']] += row['c']
                waiting_threads_total += row['c']
            elif row['status'] == EmailThread.Status.REPLIED:
                replied_threads_total += row['c']

        # 7. WhatsApp messages & AI auto-reply metrics
        for row in (
            WhatsAppMessage.objects.filter(
                is_deleted=False,
                conversation__session__owner_id__in=authorized_ids,
                created_at__gte=day_start,
                created_at__lt=day_end,
            )
            .values('conversation__session__owner_id', 'direction')
            .annotate(c=Count('id'))
        ):
            uid = row['conversation__session__owner_id']
            if uid not in authorized_ids_set:
                continue
            if row['direction'] == WhatsAppMessage.Direction.OUTBOUND:
                wa_out_today_by_uid[uid] += row['c']
            elif row['direction'] == WhatsAppMessage.Direction.INBOUND:
                wa_in_today_by_uid[uid] += row['c']

        for row in (
            WhatsAppAIReplyLog.objects.filter(
                session__owner_id__in=authorized_ids,
                created_at__gte=day_start,
                created_at__lt=day_end,
            )
            .values('session__owner_id', 'status')
            .annotate(c=Count('id'))
        ):
            uid = row['session__owner_id']
            st = row['status']
            cnt = row['c']
            if st == WhatsAppAIReplyLog.Status.SENT and uid in authorized_ids_set:
                wa_ai_today_by_uid[uid] += cnt
            elif st in (WhatsAppAIReplyLog.Status.FAILED, WhatsAppAIReplyLog.Status.SEND_UNKNOWN):
                wa_ai_failed_today += cnt
            elif st == WhatsAppAIReplyLog.Status.SKIPPED:
                wa_ai_skipped_today += cnt

        wa_ai_meetings_scheduled_today = WhatsAppMeetingRequest.objects.filter(
            user_id__in=authorized_ids,
            state=WhatsAppMeetingRequest.State.SCHEDULED,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).count()
        wa_ai_meetings_in_progress = WhatsAppMeetingRequest.objects.filter(
            user_id__in=authorized_ids,
            state__in=[
                WhatsAppMeetingRequest.State.COLLECTING_DETAILS,
                WhatsAppMeetingRequest.State.READY_FOR_AVAILABILITY_CHECK,
                WhatsAppMeetingRequest.State.CHECKING_AVAILABILITY,
                WhatsAppMeetingRequest.State.AWAITING_ALTERNATIVE_SELECTION,
                WhatsAppMeetingRequest.State.AWAITING_CONFIRMATION,
                WhatsAppMeetingRequest.State.REVALIDATING_SLOT,
                WhatsAppMeetingRequest.State.CREATING_MEETING,
            ],
        ).count()

        # 8. Meetings (scheduled on reporting date, created on reporting date, upcoming 7d)
        upcoming_window_start = now - timedelta(minutes=30)
        upcoming_7d_end = now + timedelta(days=7)
        for row in (
            Meeting.objects.filter(
                Q(created_by_id__in=authorized_ids) | Q(google_calendar_owner_id__in=authorized_ids)
            )
            .filter(
                Q(scheduled_datetime__gte=day_start, scheduled_datetime__lt=day_end)
                | Q(created_at__gte=day_start, created_at__lt=day_end)
                | Q(scheduled_datetime__gte=upcoming_window_start, scheduled_datetime__lt=upcoming_7d_end)
            )
            .exclude(status='CANCELLED')
            .values('id', 'created_by_id', 'google_calendar_owner_id', 'scheduled_datetime', 'created_at')
        ):
            host_uid = row['created_by_id'] if row['created_by_id'] in authorized_ids_set else row['google_calendar_owner_id']
            if host_uid not in authorized_ids_set:
                continue
            sdt = row['scheduled_datetime']
            cdt = row['created_at']
            if sdt and day_start <= sdt < day_end:
                meetings_today_by_uid[host_uid] += 1
            if cdt and day_start <= cdt < day_end:
                meetings_created_today_by_uid[host_uid] += 1
            if sdt and upcoming_window_start <= sdt < upcoming_7d_end:
                upcoming_meetings_by_uid[host_uid] += 1

        # 9. PRE Tasks & Audit Reverification queue
        tasks_created_today = PreTask.objects.filter(
            assigned_pre_id__in=authorized_ids,
            created_at__gte=day_start,
            created_at__lt=day_end,
        ).count()
        for row in (
            PreTask.objects.filter(
                assigned_pre_id__in=authorized_ids,
                completed_at__gte=day_start,
                completed_at__lt=day_end,
            )
            .values('assigned_pre_id')
            .annotate(c=Count('id'))
        ):
            tasks_completed_today_by_uid[row['assigned_pre_id']] += row['c']

        for row in (
            PreTask.objects.filter(
                assigned_pre_id__in=authorized_ids,
                status=PreTask.Status.PENDING,
            )
            .values('assigned_pre_id', 'task_type')
            .annotate(c=Count('id'))
        ):
            cnt = row['c']
            pending_tasks_total += cnt
            pending_tasks_by_uid[row['assigned_pre_id']] += cnt
            if row['task_type'] == PreTask.TaskType.EMAIL_REPLY:
                email_reply_pending += cnt
            elif row['task_type'] == PreTask.TaskType.WHATSAPP_ESCALATION:
                whatsapp_escalation_pending += cnt

        pending_audit_reverifications = AuditReverificationRequest.objects.filter(
            status=AuditReverificationRequest.Status.PENDING,
        ).filter(
            Q(pre_user_id__in=authorized_ids)
            | Q(pre_user__isnull=True, prospect__created_by__in=authorized_usernames)
        ).count()

    # Connected integrations per PRE user (metadata only, zero secrets/tokens)
    gmail_map = {}
    gcal_set = set()
    ms_set = set()
    zoom_set = set()
    sessions_by_uid = {}

    if authorized_ids:
        for row in GoogleMailCredentials.objects.filter(user_id__in=authorized_ids, is_active=True).values('user_id', 'email'):
            gmail_map[row['user_id']] = row['email'] or ''
        gcal_set = set(
            GoogleCalendarCredentials.objects.filter(user_id__in=authorized_ids, is_active=True).values_list('user_id', flat=True)
        )
        ms_set = set(
            MicrosoftCalendarCredentials.objects.filter(user_id__in=authorized_ids, is_active=True).values_list('user_id', flat=True)
        )
        zoom_set = set(
            ZoomCredentials.objects.filter(user_id__in=authorized_ids, is_active=True).values_list('user_id', flat=True)
        )

        sessions_qs = (
            WhatsAppSession.objects.filter(owner_id__in=authorized_ids, is_active=True)
            .exclude(session_name__startswith='hist_')
            .select_related('owner', 'ai_auto_reply_config')
            .order_by('-last_used_at', '-created_at')
        )
        for sess in sessions_qs:
            sessions_by_uid.setdefault(sess.owner_id, []).append(sess)

    # Per-session WhatsApp daily counters
    session_msg_today = {}
    session_ai_today = {}
    if authorized_ids:
        for row in (
            WhatsAppMessage.objects.filter(
                is_deleted=False,
                conversation__session__owner_id__in=authorized_ids,
                created_at__gte=day_start,
                created_at__lt=day_end,
            )
            .values('conversation__session_id', 'direction')
            .annotate(c=Count('id'))
        ):
            sid = row['conversation__session_id']
            d_counts = session_msg_today.setdefault(sid, {'OUTBOUND': 0, 'INBOUND': 0})
            if row['direction'] in d_counts:
                d_counts[row['direction']] += row['c']

        for row in (
            WhatsAppAIReplyLog.objects.filter(
                session__owner_id__in=authorized_ids,
                created_at__gte=day_start,
                created_at__lt=day_end,
            )
            .values('session_id', 'status')
            .annotate(c=Count('id'))
        ):
            sid = row['session_id']
            a_counts = session_ai_today.setdefault(sid, {'sent': 0, 'failed': 0})
            if row['status'] == WhatsAppAIReplyLog.Status.SENT:
                a_counts['sent'] += row['c']
            elif row['status'] in (WhatsAppAIReplyLog.Status.FAILED, WhatsAppAIReplyLog.Status.SEND_UNKNOWN):
                a_counts['failed'] += row['c']

    # Build unified team_performance list + whatsapp_sessions list
    team_performance = []
    whatsapp_sessions_payload = []
    active_pre_users = 0
    whatsapp_sessions_ready = 0
    whatsapp_ai_enabled_sessions = 0

    for u in authorized_users:
        uid = u.id
        profile = getattr(u, 'profile', None)
        mail_acc = getattr(profile, 'mail_account', None) if profile else None
        gmail_email = gmail_map.get(uid) or (
            mail_acc.email_address if (mail_acc and mail_acc.is_active) else ''
        )
        user_sessions = sessions_by_uid.get(uid, [])
        primary_sess = user_sessions[0] if user_sessions else None

        primary_ai_cfg = None
        if primary_sess:
            try:
                primary_ai_cfg = primary_sess.ai_auto_reply_config
            except WhatsAppAIAutoReplyConfig.DoesNotExist:
                primary_ai_cfg = None

        for s in user_sessions:
            try:
                ai_cfg = s.ai_auto_reply_config
            except WhatsAppAIAutoReplyConfig.DoesNotExist:
                ai_cfg = None
            ai_on = bool(ai_cfg and ai_cfg.enabled)
            if s.status == WhatsAppSession.Status.READY:
                whatsapp_sessions_ready += 1
            if ai_on:
                whatsapp_ai_enabled_sessions += 1
            m_counts = session_msg_today.get(s.id, {})
            ai_counts = session_ai_today.get(s.id, {})
            whatsapp_sessions_payload.append({
                'session_id': s.id,
                'session_name': s.session_name,
                'user_id': uid,
                'user_name': uid_to_name[uid],
                'phone_number': s.phone_number or '',
                'status': s.status,
                'ai_enabled': ai_on,
                'ai_model': (ai_cfg.model_name if ai_cfg else '') or '',
                'reply_to_groups': bool(ai_cfg and ai_cfg.reply_to_groups),
                'sent_today': m_counts.get('OUTBOUND', 0),
                'received_today': m_counts.get('INBOUND', 0),
                'ai_replies_today': ai_counts.get('sent', 0),
                'failed_today': ai_counts.get('failed', 0),
                'last_used_at': s.last_used_at.isoformat() if s.last_used_at else None,
            })

        total_act = (
            calls_today_by_uid[uid]
            + emails_sent_today_by_uid[uid]
            + wa_out_today_by_uid[uid]
        )
        has_activity = any([
            prospects_today_by_uid[uid],
            lq_today_by_uid[uid],
            not_lq_today_by_uid[uid],
            attended_today_by_uid[uid],
            calls_today_by_uid[uid],
            emails_sent_today_by_uid[uid],
            wa_out_today_by_uid[uid],
            meetings_created_today_by_uid[uid],
            tasks_completed_today_by_uid[uid],
        ])
        if has_activity:
            active_pre_users += 1

        team_performance.append({
            'user_id': uid,
            'name': uid_to_name[uid],
            'username': u.username,
            'email': u.email,
            'last_login': u.last_login.isoformat() if u.last_login else None,
            'prospects_entered': prospects_today_by_uid[uid],
            'lead_qualified': lq_today_by_uid[uid],
            'not_lead_qualified': not_lq_today_by_uid[uid],
            'attended': attended_today_by_uid[uid],
            'calls': calls_today_by_uid[uid],
            'emails_sent': emails_sent_today_by_uid[uid],
            'emails_received': emails_received_today_by_uid[uid],
            'emails_opened': emails_opened_today_by_uid[uid],
            'whatsapp_outbound': wa_out_today_by_uid[uid],
            'whatsapp_inbound': wa_in_today_by_uid[uid],
            'whatsapp_ai_replies': wa_ai_today_by_uid[uid],
            'meetings_today': meetings_today_by_uid[uid],
            'meetings_created_today': meetings_created_today_by_uid[uid],
            'tasks_completed_today': tasks_completed_today_by_uid[uid],
            'total_activities': total_act,
            'total_prospects': total_prospects_by_uid[uid],
            'total_lead_qualified': total_lq_by_uid[uid],
            'pending_tasks': pending_tasks_by_uid[uid],
            'upcoming_meetings': upcoming_meetings_by_uid[uid],
            'waiting_email_threads': waiting_threads_by_uid[uid],
            'integrations': {
                'gmail_connected': bool(gmail_email),
                'gmail_email': gmail_email,
                'google_calendar_connected': uid in gcal_set,
                'microsoft_connected': uid in ms_set,
                'zoom_connected': uid in zoom_set,
                'whatsapp_status': primary_sess.status if primary_sess else 'NOT_LINKED',
                'whatsapp_phone': (primary_sess.phone_number or '') if primary_sess else '',
                'whatsapp_ai_enabled': bool(primary_ai_cfg and primary_ai_cfg.enabled),
            },
        })

    # WhatsApp global safety configuration
    wa_cfg = WhatsAppConfiguration.objects.first()
    whatsapp_config_payload = {
        'outbound_enabled': bool(wa_cfg.outbound_enabled) if wa_cfg else True,
        'safety_stop_active': bool(wa_cfg.safety_stop_active) if wa_cfg else False,
        'safety_stop_reason': (wa_cfg.safety_stop_reason or '') if wa_cfg else '',
        'global_hourly_limit': wa_cfg.global_hourly_limit if wa_cfg else 50,
        'per_user_hourly_limit': wa_cfg.per_user_hourly_limit if wa_cfg else 20,
    }

    # Upcoming meetings & provider breakdown
    provider_breakdown = {'GOOGLE_MEET': 0, 'ZOOM': 0, 'MS_TEAMS': 0, 'MANUAL': 0}
    recordings_completed = 0
    transcriptions_completed = 0
    upcoming_meetings_payload = []
    if authorized_ids:
        mtg_scope_qs = (
            Meeting.objects.filter(
                Q(created_by_id__in=authorized_ids) | Q(google_calendar_owner_id__in=authorized_ids)
            )
            .exclude(status='CANCELLED')
            .select_related('prospect', 'prospect_contact', 'created_by', 'google_calendar_owner')
        )
        for row in (
            mtg_scope_qs.filter(
                scheduled_datetime__gte=now - timedelta(minutes=30),
                scheduled_datetime__lt=now + timedelta(days=30),
            )
            .values('meeting_provider')
            .annotate(c=Count('id'))
        ):
            prov = row['meeting_provider']
            if prov in provider_breakdown:
                provider_breakdown[prov] += row['c']

        recordings_completed = mtg_scope_qs.filter(recording_status='COMPLETED').count()
        transcriptions_completed = mtg_scope_qs.filter(transcription_status='COMPLETED').count()

        for m in mtg_scope_qs.filter(
            scheduled_datetime__gte=now - timedelta(minutes=30)
        ).order_by('scheduled_datetime')[:12]:
            host = m.created_by if (m.created_by_id in authorized_ids_set) else m.google_calendar_owner
            upcoming_meetings_payload.append({
                'id': m.id,
                'company_name': m.prospect.company_name if m.prospect else 'WhatsApp / Direct Contact',
                'prospect_id': str(m.prospect_id) if m.prospect_id else None,
                'contact_name': m.prospect_contact.contact_name if m.prospect_contact else '',
                'host_id': host.id if host else None,
                'host_name': (host.get_full_name() or host.username) if host else '',
                'meeting_provider': m.meeting_provider,
                'scheduled_datetime': m.scheduled_datetime.isoformat() if m.scheduled_datetime else None,
                'timezone': m.timezone or 'UTC',
                'meeting_link': m.meeting_link or '',
                'status': m.status or 'SCHEDULED',
                'recording_status': m.recording_status or 'NONE',
                'transcription_status': m.transcription_status or 'NONE',
            })

    # Recent pending PRE tasks
    recent_pending_tasks = []
    if authorized_ids:
        for t in (
            PreTask.objects.filter(assigned_pre_id__in=authorized_ids, status=PreTask.Status.PENDING)
            .select_related('assigned_pre', 'prospect')
            .order_by('-created_at')[:10]
        ):
            recent_pending_tasks.append({
                'id': str(t.id),
                'task_type': t.task_type,
                'title': t.title,
                'company_name': (t.prospect.company_name if t.prospect else '') or t.company_name or '',
                'sender_name': t.sender_name or '',
                'assigned_pre_id': t.assigned_pre_id,
                'assigned_pre_name': (
                    (t.assigned_pre.get_full_name() or t.assigned_pre.username)
                    if t.assigned_pre
                    else t.assigned_pre_username
                ),
                'created_at': t.created_at.isoformat() if t.created_at else None,
            })

    # Bulk email campaigns overview
    total_campaigns = 0
    active_campaigns = 0
    completed_campaigns_today = 0
    recent_campaigns_payload = []
    if authorized_ids:
        camp_base = EmailCampaign.objects.filter(created_by_id__in=authorized_ids)
        total_campaigns = camp_base.count()
        active_campaigns = camp_base.filter(
            status__in=[
                EmailCampaign.Status.QUEUED,
                EmailCampaign.Status.RUNNING,
                EmailCampaign.Status.PAUSED,
            ]
        ).count()
        completed_campaigns_today = camp_base.filter(
            status__in=[EmailCampaign.Status.COMPLETED, EmailCampaign.Status.COMPLETED_WITH_ERRORS],
            completed_at__gte=day_start,
            completed_at__lt=day_end,
        ).count()

        for c in (
            camp_base.select_related('created_by')
            .annotate(
                total_cnt=Count('recipients', distinct=True),
                sent_cnt=Count('recipients', filter=Q(recipients__status='SENT'), distinct=True),
                failed_cnt=Count('recipients', filter=Q(recipients__status='FAILED'), distinct=True),
                pending_cnt=Count(
                    'recipients',
                    filter=Q(recipients__status__in=['PENDING', 'SENDING', 'RETRY_PENDING']),
                    distinct=True,
                ),
            )
            .order_by('-created_at')[:6]
        ):
            recent_campaigns_payload.append({
                'id': str(c.id),
                'name': c.name,
                'sender_email': c.sender_email,
                'status': c.status,
                'total_count': c.total_cnt,
                'sent_count': c.sent_cnt,
                'failed_count': c.failed_cnt,
                'pending_count': c.pending_cnt,
                'created_by_name': (c.created_by.get_full_name() or c.created_by.username) if c.created_by else '',
                'created_at': c.created_at.isoformat() if c.created_at else None,
            })

    # Real-time chronological activity stream (top 25 across authorized team)
    live_feed = []
    if authorized_ids:
        for p in (
            Prospect.objects.filter(created_by__in=authorized_usernames)
            .order_by('-created_at')[:8]
        ):
            actor_uid = username_to_uid.get(p.created_by)
            live_feed.append({
                'id': f'prospect-{p.id}',
                'type': 'PROSPECT_CREATED',
                'category': 'prospects',
                'actor_id': actor_uid,
                'actor_name': uid_to_name.get(actor_uid, p.created_by or 'PRE'),
                'title': f'Added prospect {p.company_name}',
                'subtitle': f'{p.country_head_office} · {p.primary_industries}',
                'badge': p.company_structure,
                'timestamp': p.created_at.isoformat() if p.created_at else None,
                'route': f'/prospects/{p.id}',
            })

        for lq in (
            LeadQualification.objects.filter(
                decision_at__isnull=False,
            )
            .filter(Q(decision_by_id__in=authorized_ids) | Q(prospect__created_by__in=authorized_usernames))
            .select_related('prospect', 'decision_by')
            .order_by('-decision_at')[:8]
        ):
            actor_uid = _resolve_actor_uid(lq.decision_by_id, lq.qualified_by_id, lq.prospect.created_by, username_to_uid)
            live_feed.append({
                'id': f'qual-{lq.id}',
                'type': 'QUALIFICATION',
                'category': 'prospects',
                'actor_id': actor_uid,
                'actor_name': uid_to_name.get(actor_uid, 'PRE'),
                'title': f'{lq.prospect.company_name} marked {lq.qualification_status}',
                'subtitle': f'Verification: {lq.verification_status}',
                'badge': lq.qualification_status,
                'timestamp': lq.decision_at.isoformat() if lq.decision_at else None,
                'route': f'/prospects/{lq.prospect_id}',
            })

        for ca in (
            CallActivity.objects.filter(created_by_id__in=authorized_ids)
            .select_related('prospect', 'prospect_contact', 'created_by')
            .order_by('-created_at')[:8]
        ):
            live_feed.append({
                'id': f'call-{ca.id}',
                'type': 'CALL',
                'category': 'calls',
                'actor_id': ca.created_by_id,
                'actor_name': uid_to_name.get(ca.created_by_id, 'PRE'),
                'title': f'Call to {ca.prospect.company_name if ca.prospect else "Prospect"}',
                'subtitle': f'{ca.call_status}' + (f' · {ca.communication_outcome}' if ca.communication_outcome else ''),
                'badge': ca.communication_outcome or ca.call_status,
                'timestamp': ca.created_at.isoformat() if ca.created_at else None,
                'route': f'/outreach-activity/{ca.prospect_id}' if ca.prospect_id else '/prospects?tab=outreach',
            })

        for em in (
            EmailThreadMessage.objects.filter(owner_id__in=authorized_ids)
            .select_related('thread', 'thread__prospect')
            .order_by('-sent_at', '-created_at')[:10]
        ):
            ts = em.sent_at or em.created_at
            is_in = em.direction == EmailThreadMessage.Direction.INBOUND
            company = em.thread.prospect.company_name if (em.thread and em.thread.prospect) else ''
            live_feed.append({
                'id': f'email-{em.id}',
                'type': 'EMAIL_INBOUND' if is_in else 'EMAIL_OUTBOUND',
                'category': 'email',
                'actor_id': em.owner_id,
                'actor_name': uid_to_name.get(em.owner_id, 'PRE'),
                'title': f'{"Reply from" if is_in else "Sent to"} {company or (em.sender_email if is_in else (", ".join(em.to_emails[:1]) or "Recipient"))}',
                'subtitle': em.subject or '(No Subject)',
                'badge': 'INBOUND' if is_in else em.status,
                'timestamp': ts.isoformat() if ts else None,
                'route': '/manager-dashboard?tab=email',
            })

        for m in (
            Meeting.objects.filter(
                Q(created_by_id__in=authorized_ids) | Q(google_calendar_owner_id__in=authorized_ids)
            )
            .exclude(status='CANCELLED')
            .select_related('prospect')
            .order_by('-created_at')[:6]
        ):
            actor_uid = m.created_by_id if m.created_by_id in authorized_ids_set else m.google_calendar_owner_id
            live_feed.append({
                'id': f'meeting-{m.id}',
                'type': 'MEETING',
                'category': 'meetings',
                'actor_id': actor_uid,
                'actor_name': uid_to_name.get(actor_uid, 'PRE'),
                'title': f'Meeting scheduled: {m.prospect.company_name if m.prospect else "Direct Contact"}',
                'subtitle': f'{m.meeting_provider} · {m.scheduled_datetime.strftime("%Y-%m-%d %H:%M UTC") if m.scheduled_datetime else ""}',
                'badge': m.meeting_provider,
                'timestamp': m.created_at.isoformat() if m.created_at else None,
                'route': '/calendar',
            })

        for al in (
            WhatsAppAIReplyLog.objects.filter(
                session__owner_id__in=authorized_ids,
                status__in=[WhatsAppAIReplyLog.Status.SENT, WhatsAppAIReplyLog.Status.FAILED],
            )
            .select_related('session', 'conversation', 'conversation__prospect')
            .order_by('-created_at')[:8]
        ):
            actor_uid = al.session.owner_id if al.session else None
            contact_lbl = (
                (al.conversation.prospect.company_name if al.conversation and al.conversation.prospect else '')
                or (al.conversation.whatsapp_name if al.conversation else '')
                or al.sender_identifier
                or 'WhatsApp Contact'
            )
            live_feed.append({
                'id': f'wa-ai-{al.id}',
                'type': 'WHATSAPP_AI',
                'category': 'whatsapp',
                'actor_id': actor_uid,
                'actor_name': uid_to_name.get(actor_uid, 'PRE'),
                'title': f'WhatsApp AI reply to {contact_lbl}',
                'subtitle': (al.reply_text or al.error_message or '')[:100],
                'badge': f'AI {al.status}',
                'timestamp': (al.replied_at or al.created_at).isoformat() if (al.replied_at or al.created_at) else None,
                'route': '/manager-dashboard?tab=operations',
            })

        for wm in (
            WhatsAppMessage.objects.filter(
                is_deleted=False,
                conversation__session__owner_id__in=authorized_ids,
            )
            .select_related('conversation', 'conversation__session', 'conversation__prospect')
            .order_by('-created_at')[:8]
        ):
            actor_uid = wm.conversation.session.owner_id if (wm.conversation and wm.conversation.session) else None
            contact_lbl = (
                (wm.conversation.prospect.company_name if wm.conversation and wm.conversation.prospect else '')
                or (wm.conversation.whatsapp_name if wm.conversation else '')
                or 'Contact'
            )
            preview = (wm.body_preview or '').strip()[:100] or (f'[{wm.message_type}]' if wm.has_media else '')
            live_feed.append({
                'id': f'wa-msg-{wm.id}',
                'type': f'WHATSAPP_{wm.direction}',
                'category': 'whatsapp',
                'actor_id': actor_uid,
                'actor_name': uid_to_name.get(actor_uid, 'PRE'),
                'title': f'WhatsApp {"from" if wm.direction == "INBOUND" else "to"} {contact_lbl}',
                'subtitle': preview,
                'badge': wm.direction,
                'timestamp': wm.created_at.isoformat() if wm.created_at else None,
                'route': '/manager-dashboard?tab=operations',
            })

        for pt in (
            PreTask.objects.filter(assigned_pre_id__in=authorized_ids)
            .select_related('prospect')
            .order_by('-updated_at')[:6]
        ):
            ts = pt.completed_at or pt.created_at
            live_feed.append({
                'id': f'task-{pt.id}',
                'type': 'TASK',
                'category': 'tasks',
                'actor_id': pt.assigned_pre_id,
                'actor_name': uid_to_name.get(pt.assigned_pre_id, pt.assigned_pre_username or 'PRE'),
                'title': pt.title,
                'subtitle': (pt.prospect.company_name if pt.prospect else '') or pt.company_name or pt.task_type,
                'badge': pt.status,
                'timestamp': ts.isoformat() if ts else None,
                'route': '/pre-tasks',
            })

        for ar in (
            AuditReverificationRequest.objects.filter(
                Q(pre_user_id__in=authorized_ids)
                | Q(pre_user__isnull=True, prospect__created_by__in=authorized_usernames)
            )
            .select_related('prospect')
            .order_by('-updated_at')[:5]
        ):
            ts = ar.resolved_at or ar.created_at
            live_feed.append({
                'id': f'audit-{ar.id}',
                'type': 'AUDIT_REVERIFY',
                'category': 'tasks',
                'actor_id': ar.pre_user_id,
                'actor_name': uid_to_name.get(ar.pre_user_id, ar.prospect.created_by if ar.prospect else 'PRE'),
                'title': f'Audit {ar.status}: {ar.prospect.company_name if ar.prospect else "Prospect"}',
                'subtitle': ', '.join(ar.highlighted_fields or []),
                'badge': f'AUDIT {ar.status.upper()}',
                'timestamp': ts.isoformat() if ts else None,
                'route': '/manager-audit',
            })

    live_feed.sort(key=lambda item: item.get('timestamp') or '', reverse=True)
    live_feed = live_feed[:25]

    total_calls = sum(calls_today_by_uid.values())
    total_emails_sent = sum(emails_sent_today_by_uid.values())
    total_emails_received = sum(emails_received_today_by_uid.values())
    total_emails_opened = sum(emails_opened_today_by_uid.values())
    total_wa_out = sum(wa_out_today_by_uid.values())
    total_wa_in = sum(wa_in_today_by_uid.values())
    total_wa_ai = sum(wa_ai_today_by_uid.values())
    total_meetings_today = sum(meetings_today_by_uid.values())
    total_meetings_created_today = sum(meetings_created_today_by_uid.values())
    total_tasks_completed_today = sum(tasks_completed_today_by_uid.values())
    total_prospects_portfolio = sum(total_prospects_by_uid.values())
    total_lq_portfolio = sum(total_lq_by_uid.values())
    total_upcoming_7d = sum(upcoming_meetings_by_uid.values())

    funnel_total = funnel_counts['total']
    funnel_counts['conversion_rate'] = (
        round((funnel_counts['lead_qualified'] / funnel_total) * 100, 1) if funnel_total else 0.0
    )

    payload = {
        'date': reporting_date.isoformat(),
        'meta': {
            'date': reporting_date.isoformat(),
            'timezone': str(tz),
            'generated_at': now.isoformat(),
            'is_today': reporting_date == today_in_tz,
            'team_size': len(authorized_users),
        },
        'summary': {
            'prospects_entered': sum(prospects_today_by_uid.values()),
            'active_pre_users': active_pre_users,
            'lead_qualified': sum(lq_today_by_uid.values()),
            'qualified_decisions': qualified_decisions_today,
            'not_lead_qualified': sum(not_lq_today_by_uid.values()),
            'meetings_attended': sum(attended_today_by_uid.values()),
            'calls_logged': total_calls,
            'emails_sent': total_emails_sent,
            'emails_received': total_emails_received,
            'emails_opened': total_emails_opened,
            'whatsapp_outbound': total_wa_out,
            'whatsapp_inbound': total_wa_in,
            'whatsapp_ai_replies': total_wa_ai,
            'meetings_scheduled_today': total_meetings_today,
            'meetings_created_today': total_meetings_created_today,
            'tasks_created_today': tasks_created_today,
            'tasks_completed_today': total_tasks_completed_today,
            'total_activities': total_calls + total_emails_sent + total_wa_out,
            'total_prospects': total_prospects_portfolio,
            'total_lead_qualified': total_lq_portfolio,
            'pending_tasks_total': pending_tasks_total,
            'email_reply_pending': email_reply_pending,
            'whatsapp_escalation_pending': whatsapp_escalation_pending,
            'pending_audit_reverifications': pending_audit_reverifications,
            'upcoming_meetings_7d': total_upcoming_7d,
            'active_campaigns': active_campaigns,
            'whatsapp_sessions_ready': whatsapp_sessions_ready,
            'whatsapp_ai_enabled_sessions': whatsapp_ai_enabled_sessions,
            'waiting_email_replies': waiting_threads_total,
            'replied_email_threads': replied_threads_total,
        },
        'pipeline_funnel': funnel_counts,
        'team_performance': team_performance,
        'whatsapp_overview': {
            'config': whatsapp_config_payload,
            'sessions': whatsapp_sessions_payload,
            'ai_metrics': {
                'replies_sent_today': total_wa_ai,
                'replies_failed_today': wa_ai_failed_today,
                'replies_skipped_today': wa_ai_skipped_today,
                'active_escalations_pending': whatsapp_escalation_pending,
                'ai_meetings_scheduled_today': wa_ai_meetings_scheduled_today,
                'ai_meetings_in_progress': wa_ai_meetings_in_progress,
            },
        },
        'meetings_overview': {
            'provider_breakdown': provider_breakdown,
            'recordings_completed': recordings_completed,
            'transcriptions_completed': transcriptions_completed,
            'upcoming': upcoming_meetings_payload,
        },
        'tasks_overview': {
            'pending_total': pending_tasks_total,
            'email_reply_pending': email_reply_pending,
            'whatsapp_escalation_pending': whatsapp_escalation_pending,
            'completed_today': total_tasks_completed_today,
            'pending_audit_reverifications': pending_audit_reverifications,
            'recent_pending': recent_pending_tasks,
        },
        'campaigns_overview': {
            'total_campaigns': total_campaigns,
            'active_campaigns': active_campaigns,
            'completed_today': completed_campaigns_today,
            'recent_campaigns': recent_campaigns_payload,
        },
        'live_feed': live_feed,
    }

    include_audit = str(request.query_params.get('include_audit') or '').strip().lower() in ('1', 'true', 'yes')
    if include_audit:
        payload['audit_samples'] = _build_pre_audit_samples(
            authorized_users, authorized_usernames, day_start, day_end
        )

    return Response(payload, status=status.HTTP_200_OK)


@api_view(['GET'])
@permission_classes([IsManagerOrSuperuser])
def manager_audit(request):
    """
    GET /api/manager-dashboard/audit/?date=YYYY-MM-DD

    Returns unified PRE daily audit record samples (combining prospect master data,
    qualification state, and daily activities) alongside the re-verification request tracker.
    """
    try:
        reporting_date, tz = _parse_reporting_date(request)
    except ValueError:
        return Response(
            {'error': 'Invalid date format. Use YYYY-MM-DD.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    day_start, day_end = _day_bounds(reporting_date)
    authorized_users = list(_get_authorized_pre_users_for_manager(request.user))
    authorized_ids = [u.id for u in authorized_users]
    authorized_usernames = [u.username for u in authorized_users]

    pre_audit_samples = _build_pre_audit_samples(
        authorized_users, authorized_usernames, day_start, day_end
    )
    reverification_requests = _build_reverification_list(
        request.user, authorized_ids, authorized_usernames
    )

    active_pre_users = sum(1 for g in pre_audit_samples if g['entered_total'] > 0)
    total_entered = sum(g['entered_total'] for g in pre_audit_samples)
    total_sampled = sum(g['sample_count'] for g in pre_audit_samples)
    pending_reverify = sum(1 for r in reverification_requests if r['status'] == AuditReverificationRequest.Status.PENDING)
    corrected_reverify = sum(1 for r in reverification_requests if r['status'] == AuditReverificationRequest.Status.CORRECTED)

    return Response({
        'date': reporting_date.isoformat(),
        'timezone': str(tz),
        'generated_at': timezone.now().isoformat(),
        'summary': {
            'total_pre_users': len(authorized_users),
            'active_pre_users': active_pre_users,
            'total_entered': total_entered,
            'total_sampled': total_sampled,
            'pending_reverifications': pending_reverify,
            'corrected_reverifications': corrected_reverify,
        },
        'pre_audit_samples': pre_audit_samples,
        'reverification_requests': reverification_requests,
    }, status=status.HTTP_200_OK)
