"""
Views for the `email_ai` Django app:
1. Personalized Email AI Generation (`POST /api/email-ai/generate/`) for:
   - Outreach Workspace (`OUTREACH`)
   - Email Inbox Compose (`INBOX`)
   - Bulk Email Campaign (`CAMPAIGN`)
2. Manager Email Activity & Daily Email Activity AI Reports (moved from `prospects.manager_views`):
   - `manager_email_activity_list`
   - `manager_email_activity_detail`
   - `manager_email_summary_refresh`
   - `manager_daily_email_report`
   - `manager_daily_email_report_refresh`
"""

from datetime import date as date_type

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.permissions import IsManagerOrSuperuser
from prospects.models import EmailThread, OutreachEmail
from prospects.serializers import EmailThreadDetailSerializer, EmailThreadListSerializer
from .services import generate_personalized_email

User = get_user_model()


# ────────────────────────────────────────────────────────────────────────────
# 1. Personalized Email Generation View (Outreach, Inbox, Campaign)
# ────────────────────────────────────────────────────────────────────────────

@api_view(["POST"])
@permission_classes([IsAuthenticated])
def generate_personalized_email_view(request):
    """
    POST /api/email-ai/generate/
    Body:
      - prompt: str (required) — user instructions for the email
      - source_context: 'OUTREACH' | 'INBOX' | 'CAMPAIGN' (optional, default 'OUTREACH')
      - tone: str (optional, default 'professional')
      - prospect_id: str/uuid (optional)
      - recipient_emails: list[str] or comma-separated str (optional)
      - company_name: str (optional)
      - recipient_name: str (optional)
      - industry: str (optional)
      - country: str (optional)
      - campaign_name: str (optional)
      - current_subject: str (optional)
      - current_body: str (optional)
    """
    data = request.data or {}
    user_prompt = str(data.get("prompt") or "").strip()
    if not user_prompt:
        return Response(
            {"detail": "Please enter a prompt describing the email you want to generate."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    raw_recipients = data.get("recipient_emails") or data.get("to_emails") or []
    if isinstance(raw_recipients, str):
        recipient_emails = [
            e.strip() for e in raw_recipients.replace(";", ",").split(",") if e.strip()
        ]
    elif isinstance(raw_recipients, (list, tuple)):
        recipient_emails = [str(e).strip() for e in raw_recipients if str(e).strip()]
    else:
        recipient_emails = []

    result = generate_personalized_email(
        user=request.user,
        user_prompt=user_prompt,
        source_context=str(data.get("source_context") or "OUTREACH"),
        tone=str(data.get("tone") or "professional"),
        prospect_id=str(data.get("prospect_id") or "").strip() or None,
        recipient_emails=recipient_emails,
        company_name=str(data.get("company_name") or "").strip(),
        recipient_name=str(data.get("recipient_name") or "").strip(),
        industry=str(data.get("industry") or "").strip(),
        country=str(data.get("country") or "").strip(),
        campaign_name=str(data.get("campaign_name") or "").strip(),
        current_subject=str(data.get("current_subject") or "").strip(),
        current_body=str(data.get("current_body") or "").strip(),
    )
    return Response(result, status=status.HTTP_200_OK)


# ────────────────────────────────────────────────────────────────────────────
# 2. Manager Email Activity & AI Conversation Summaries (moved from prospects)
# ────────────────────────────────────────────────────────────────────────────

def _get_report_tz():
    import zoneinfo

    tz_name = getattr(settings, "MANAGER_REPORT_TIMEZONE", settings.TIME_ZONE)
    try:
        return zoneinfo.ZoneInfo(tz_name)
    except Exception:
        return timezone.utc


def _day_bounds(reporting_date):
    """Return (day_start, day_end) as aware datetimes in the reporting timezone."""
    import datetime

    tz = _get_report_tz()
    day_start = timezone.datetime(
        reporting_date.year,
        reporting_date.month,
        reporting_date.day,
        0,
        0,
        0,
        tzinfo=tz,
    )
    day_end = day_start + datetime.timedelta(days=1)
    return day_start, day_end


def _get_authorized_pre_users_for_manager(request_user):
    """
    Dynamically return active PRE/LQ users within the manager's authorized company scope.
    Superusers can view all companies.
    Managers with company assigned see only PRE/LQ users in that same company.
    Managers without a company see PRE/LQ users without a company (backward compatibility).
    """
    qs = (
        User.objects.filter(
            is_active=True,
            is_superuser=False,
            profile__role__in=["PRE", "LQ"],
        )
        .select_related("profile")
        .order_by("id")
    )

    if request_user.is_superuser:
        return qs

    mgr_company_id = getattr(getattr(request_user, "profile", None), "company_id", None)
    if mgr_company_id is not None:
        return qs.filter(profile__company_id=mgr_company_id)
    return qs.filter(profile__company__isnull=True)


def _parse_date_range_bounds(request):
    """Parse optional ?date=YYYY-MM-DD or ?date_from=...&date_to=... into UTC aware datetimes."""
    import datetime

    single_date = (request.query_params.get("date") or "").strip()
    date_from = (request.query_params.get("date_from") or "").strip()
    date_to = (request.query_params.get("date_to") or "").strip()

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


@api_view(["GET"])
@permission_classes([IsManagerOrSuperuser])
def manager_email_activity_list(request):
    """
    GET /api/manager-dashboard/email-activity/
    Returns paginated email conversation threads + AI summaries across all
    authorized PRE/LQ users with filters (pre_user_id, date, date_from, date_to,
    search, status, direction, match_status).
    """
    import sys
    from prospects.email_thread_service import (
        backfill_outreach_emails_to_threads,
        sync_authorized_mailboxes,
    )
    from .services import schedule_thread_summary

    authorized_users = list(_get_authorized_pre_users_for_manager(request.user))
    authorized_ids = [u.id for u in authorized_users]

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
        .select_related("owner", "owner__profile", "prospect", "prospect_contact")
        .filter(owner_id__in=authorized_ids)
    )

    pre_user_id = (request.query_params.get("pre_user_id") or "").strip()
    filter_uid = None
    if pre_user_id and pre_user_id.lower() != "all":
        try:
            uid_int = int(pre_user_id)
        except ValueError:
            return Response({"detail": "Invalid pre_user_id."}, status=status.HTTP_400_BAD_REQUEST)
        if uid_int not in authorized_ids:
            if User.objects.filter(pk=uid_int).exists():
                return Response(
                    {"detail": "You are not authorized to access this PRE user."},
                    status=status.HTTP_403_FORBIDDEN,
                )
            base_qs = base_qs.none()
        else:
            filter_uid = uid_int
            base_qs = base_qs.filter(owner_id=uid_int)

    sync_param = (request.query_params.get("sync") or "").strip().lower()
    force_sync = sync_param in ("1", "true", "yes")
    running_tests = "test" in sys.argv
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

    status_filter = (request.query_params.get("status") or "").strip().upper()
    if status_filter and status_filter != "ALL":
        base_qs = base_qs.filter(status=status_filter)

    direction_filter = (request.query_params.get("direction") or "").strip().upper()
    if direction_filter and direction_filter != "ALL":
        base_qs = base_qs.filter(last_direction=direction_filter)

    match_filter = (request.query_params.get("match_status") or "").strip().upper()
    if match_filter and match_filter != "ALL":
        base_qs = base_qs.filter(match_status=match_filter)

    search_q = (request.query_params.get("search") or "").strip()
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

    agg = base_qs.aggregate(
        total=Count("id"),
        waiting=Count("id", filter=Q(status=EmailThread.Status.WAITING_REPLY)),
        replied=Count("id", filter=Q(status=EmailThread.Status.REPLIED)),
        failed=Count("id", filter=Q(status=EmailThread.Status.FAILED)),
        unmatched=Count("id", filter=Q(match_status=EmailThread.MatchStatus.UNMATCHED)),
    )

    per_user_counts = dict(
        EmailThread.objects.filter(owner_id__in=authorized_ids)
        .values("owner_id")
        .annotate(c=Count("id"))
        .values_list("owner_id", "c")
    )
    pre_users_meta = [
        {
            "id": u.id,
            "name": u.get_full_name() or u.username,
            "username": u.username,
            "email": u.email,
            "role": getattr(getattr(u, "profile", None), "role", "PRE"),
            "thread_count": per_user_counts.get(u.id, 0),
        }
        for u in authorized_users
    ]

    try:
        page = max(1, int(request.query_params.get("page") or 1))
    except ValueError:
        page = 1
    try:
        page_size = min(100, max(1, int(request.query_params.get("page_size") or 20)))
    except ValueError:
        page_size = 20

    total_count = agg["total"] or 0
    total_pages = max(1, (total_count + page_size - 1) // page_size)
    offset = (page - 1) * page_size

    page_threads = list(base_qs.order_by("-last_message_at", "-updated_at")[offset : offset + page_size])

    for th in page_threads:
        if th.summary_status == EmailThread.SummaryStatus.PENDING and th.message_count > 0:
            schedule_thread_summary(th.id)

    serializer = EmailThreadListSerializer(page_threads, many=True)
    return Response({
        "count": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "pre_users": pre_users_meta,
        "stats": {
            "total_threads": total_count,
            "waiting_reply": agg["waiting"] or 0,
            "replied": agg["replied"] or 0,
            "failed": agg["failed"] or 0,
            "unmatched": agg["unmatched"] or 0,
        },
        "results": serializer.data,
    })


@api_view(["GET"])
@permission_classes([IsManagerOrSuperuser])
def manager_email_activity_detail(request, thread_id):
    """
    GET /api/manager-dashboard/email-activity/<uuid:thread_id>/
    Returns chronological full email thread messages & safe metadata for the manager.
    """
    authorized_ids = list(
        _get_authorized_pre_users_for_manager(request.user).values_list("id", flat=True)
    )
    thread = (
        EmailThread.objects
        .select_related("owner", "owner__profile", "prospect", "prospect_contact")
        .prefetch_related("messages")
        .filter(pk=thread_id)
        .first()
    )
    if not thread:
        return Response({"detail": "Email thread not found."}, status=status.HTTP_404_NOT_FOUND)
    if thread.owner_id not in authorized_ids and not request.user.is_superuser:
        return Response({"detail": "You are not authorized to view this email thread."}, status=status.HTTP_403_FORBIDDEN)

    if thread.summary_status == EmailThread.SummaryStatus.PENDING and thread.message_count > 0:
        from .services import schedule_thread_summary

        schedule_thread_summary(thread.id)

    serializer = EmailThreadDetailSerializer(thread)
    return Response(serializer.data)


@api_view(["POST"])
@permission_classes([IsManagerOrSuperuser])
def manager_email_summary_refresh(request, thread_id):
    """
    POST /api/manager-dashboard/email-activity/<uuid:thread_id>/refresh-summary/
    Forces regeneration of the AI conversation summary for the given thread.
    """
    from .services import summarize_email_thread

    authorized_ids = list(
        _get_authorized_pre_users_for_manager(request.user).values_list("id", flat=True)
    )
    thread = EmailThread.objects.filter(pk=thread_id).first()
    if not thread:
        return Response({"detail": "Email thread not found."}, status=status.HTTP_404_NOT_FOUND)
    if thread.owner_id not in authorized_ids and not request.user.is_superuser:
        return Response({"detail": "You are not authorized to refresh this thread summary."}, status=status.HTTP_403_FORBIDDEN)

    result = summarize_email_thread(thread.id, force=True)
    thread.refresh_from_db()
    data = EmailThreadListSerializer(thread).data
    data["refresh_result"] = result
    return Response(data, status=status.HTTP_200_OK)


def _get_authorized_all_users_for_manager(request_user):
    """
    Dynamically return all active non-superuser users within the manager's company scope
    (all roles) so the daily email activity report covers every existing user.
    """
    qs = (
        User.objects.filter(
            is_active=True,
            is_superuser=False,
        )
        .select_related("profile")
        .order_by("id")
    )

    if request_user.is_superuser:
        return qs

    mgr_company_id = getattr(getattr(request_user, "profile", None), "company_id", None)
    if mgr_company_id is not None:
        return qs.filter(profile__company_id=mgr_company_id)
    return qs.filter(profile__company__isnull=True)


def _serialize_daily_user_report(user, report):
    return {
        "user_id": user.id,
        "username": user.username,
        "name": user.get_full_name() or user.username,
        "email": user.email,
        "role": getattr(getattr(user, "profile", None), "role", "PRE"),
        "report_date": report.report_date.isoformat(),
        "emails_received": report.emails_received,
        "emails_sent": report.emails_sent,
        "sent_received_responses": report.sent_received_responses,
        "pending_responses": report.pending_responses,
        "overall_summary": report.overall_summary,
        "recommended_actions": report.recommended_actions,
        "summary_status": report.summary_status,
        "summary_provider": report.summary_provider,
        "summary_model": report.summary_model,
        "summary_error": report.summary_error,
        "generated_at": report.generated_at.isoformat() if report.generated_at else None,
    }


@api_view(["GET"])
@permission_classes([IsManagerOrSuperuser])
def manager_daily_email_report(request):
    """
    GET /api/manager-dashboard/daily-email-report/?date=YYYY-MM-DD
    Returns a user-wise daily email activity report with Gemini AI analysis and
    exact counts (received, sent, sent_received_responses, pending_responses)
    for every existing active user in the manager's authorized scope.
    """
    import sys
    from prospects.email_thread_service import backfill_outreach_emails_to_threads, sync_authorized_mailboxes
    from .services import generate_daily_user_email_report

    date_param = (request.query_params.get("date") or "").strip()
    tz = _get_report_tz()
    if date_param:
        try:
            report_date = date_type.fromisoformat(date_param)
        except ValueError:
            return Response({"detail": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
    else:
        report_date = timezone.now().astimezone(tz).date()

    day_start, day_end = _day_bounds(report_date)

    authorized_users = list(_get_authorized_all_users_for_manager(request.user))
    target_user_id_raw = (request.query_params.get("user_id") or "").strip()
    if target_user_id_raw and target_user_id_raw.lower() != "all":
        try:
            target_uid = int(target_user_id_raw)
        except ValueError:
            return Response({"detail": "Invalid user_id."}, status=status.HTTP_400_BAD_REQUEST)
        auth_ids = {u.id for u in authorized_users}
        if target_uid not in auth_ids:
            if User.objects.filter(pk=target_uid).exists():
                return Response({"detail": "You are not authorized to access this user."}, status=status.HTTP_403_FORBIDDEN)
            return Response({
                "date": report_date.isoformat(),
                "users": [],
                "totals": {
                    "total_users": 0,
                    "emails_received": 0,
                    "emails_sent": 0,
                    "sent_received_responses": 0,
                    "pending_responses": 0,
                },
            })
        authorized_users = [u for u in authorized_users if u.id == target_uid]

    user_ids = [u.id for u in authorized_users]
    if user_ids and OutreachEmail.objects.filter(created_by_id__in=user_ids, thread_message__isnull=True).exists():
        try:
            backfill_outreach_emails_to_threads(user_ids)
        except Exception:
            pass

    sync_param = (request.query_params.get("sync") or "").strip().lower()
    force_sync = sync_param in ("1", "true", "yes")
    force_regen = (request.query_params.get("force") or "").strip().lower() in ("1", "true", "yes")
    running_tests = "test" in sys.argv
    if user_ids and force_sync:
        try:
            sync_authorized_mailboxes(user_ids, force=force_sync, limit=25)
        except Exception:
            pass

    user_reports = []
    totals = {
        "total_users": len(authorized_users),
        "emails_received": 0,
        "emails_sent": 0,
        "sent_received_responses": 0,
        "pending_responses": 0,
    }

    if not running_tests and len(authorized_users) > 1:
        from concurrent.futures import ThreadPoolExecutor
        from django.db import close_old_connections

        def _build_report_for_user(u):
            close_old_connections()
            try:
                rep = generate_daily_user_email_report(
                    u,
                    report_date,
                    day_start,
                    day_end,
                    force=force_regen,
                    timeout_override=8,
                    max_retries_override=1,
                )
                return u, rep
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=min(4, len(authorized_users))) as pool:
            computed = list(pool.map(_build_report_for_user, authorized_users))
    else:
        computed = [
            (
                u,
                generate_daily_user_email_report(
                    u, report_date, day_start, day_end, force=force_regen
                ),
            )
            for u in authorized_users
        ]

    for u, report in computed:
        serialized = _serialize_daily_user_report(u, report)
        user_reports.append(serialized)
        totals["emails_received"] += report.emails_received
        totals["emails_sent"] += report.emails_sent
        totals["sent_received_responses"] += report.sent_received_responses
        totals["pending_responses"] += report.pending_responses

    return Response(
        {
            "date": report_date.isoformat(),
            "totals": totals,
            "users": user_reports,
        },
        status=status.HTTP_200_OK,
    )


@api_view(["POST"])
@permission_classes([IsManagerOrSuperuser])
def manager_daily_email_report_refresh(request, user_id):
    """
    POST /api/manager-dashboard/daily-email-report/<int:user_id>/refresh/
    Forces Gemini AI regeneration of a single user's daily email activity summary.
    """
    from .services import generate_daily_user_email_report

    authorized_users = list(_get_authorized_all_users_for_manager(request.user))
    target_user = next((u for u in authorized_users if u.id == user_id), None)
    if not target_user:
        if User.objects.filter(pk=user_id).exists():
            return Response({"detail": "You are not authorized to refresh this user report."}, status=status.HTTP_403_FORBIDDEN)
        return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)

    date_param = (request.data.get("date") or request.query_params.get("date") or "").strip()
    tz = _get_report_tz()
    if date_param:
        try:
            report_date = date_type.fromisoformat(date_param)
        except ValueError:
            return Response({"detail": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
    else:
        report_date = timezone.now().astimezone(tz).date()

    day_start, day_end = _day_bounds(report_date)
    report = generate_daily_user_email_report(target_user, report_date, day_start, day_end, force=True)
    return Response(_serialize_daily_user_report(target_user, report), status=status.HTTP_200_OK)


# ────────────────────────────────────────────────────────────────────────────
# 3. Per-User Real-Time Dashboard Listener Feed (Strictly Owner-Scoped)
# ────────────────────────────────────────────────────────────────────────────

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def user_dashboard_live_feed(request):
    """
    GET /api/email-ai/dashboard-feed/?sync=1&force=0
    Returns the authenticated user's own connected email, incoming mail,
    outreach activity, pending tasks/meetings, and AI recommendations.
    Never exposes another user's data or accepts arbitrary user_id overrides.
    """
    from .services import build_user_dashboard_live_feed

    sync = str(request.query_params.get("sync") or "").strip().lower() in ("1", "true", "yes")
    force_ai = str(request.query_params.get("force") or "").strip().lower() in ("1", "true", "yes")
    payload = build_user_dashboard_live_feed(request.user, sync=sync, force_ai=force_ai)
    return Response(payload, status=status.HTTP_200_OK)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def user_dashboard_live_feed_refresh(request):
    """POST /api/email-ai/dashboard-feed/refresh/ — force live sync + AI recommendation refresh for request.user."""
    from .services import build_user_dashboard_live_feed

    payload = build_user_dashboard_live_feed(request.user, sync=True, force_ai=True)
    return Response(payload, status=status.HTTP_200_OK)

