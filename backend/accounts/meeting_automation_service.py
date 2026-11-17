"""
Automated Custom Browser Engine (CBE) + Webhook meeting-processing orchestration.

Connects Market Intel DB across all active users (Google Calendar, Microsoft/Outlook
Calendar, CRM Meeting records, and user emails) with the unmodified Custom Browser
Engine (`cbe_meet_service`) automation service via HMAC-SHA256 webhooks:

1. Dynamically discovers scheduled meetings across all active users.
2. Resolves the meeting URL from calendar conference metadata or matching emails
   when the scheduled start time arrives.
3. Sends the meeting link & metadata to the configured trigger webhook.
4. Trigger webhook invokes CBE `POST /v1/meetings` (`transcription_enabled=True`)
   using canonical `X-CBE-*` HMAC-SHA256 signing.
5. CBE executes browser join, audio capture, speaker diarization, and transcription.
6. CBE completion webhook (`meeting.completed`) verifies HMAC signature and stores
   the transcript, aligned utterances, speaker diarization segments, participants,
   and recording status back into `Meeting`, `CalendarEventRecording`, and
   `MeetingAutomationJob`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)
User = get_user_model()

MEETING_LINK_RE = re.compile(
    r"https?://(?:"
    r"meet\.google\.com/[a-zA-Z0-9\-_]+"
    r"|(?:[a-zA-Z0-9-]+\.)?zoom\.us/(?:j|wc/join|my)/[A-Za-z0-9?=&_\-]+"
    r"|teams\.microsoft\.com/l/meetup-join/[^\s\"'<>]+"
    r"|teams\.live\.com/meet/[^\s\"'<>]+"
    r")",
    re.IGNORECASE,
)


def _get_env(name: str, default: str = "") -> str:
    val = getattr(settings, name, None)
    if val is None or val == "":
        val = os.environ.get(name, default)
    return str(val or default).strip()


def extract_meeting_url_from_text(*texts: Optional[str]) -> str:
    for text in texts:
        if not text:
            continue
        match = MEETING_LINK_RE.search(str(text))
        if match:
            return match.group(0).rstrip(".,;)")
    return ""


def detect_meeting_platform(url: str) -> str:
    lower = (url or "").lower()
    if "meet.google.com" in lower:
        return "GOOGLE_MEET"
    if "zoom.us" in lower:
        return "ZOOM"
    if "teams.microsoft.com" in lower or "teams.live.com" in lower:
        return "MS_TEAMS"
    return "MANUAL"


def _parse_iso_datetime(value: Any) -> Optional[dt.datetime]:
    if not value:
        return None
    if isinstance(value, dt.datetime):
        return timezone.make_aware(value, dt.timezone.utc) if timezone.is_naive(value) else value
    raw = str(value).strip()
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        if "T" not in raw and len(raw) == 10:
            parsed_date = dt.date.fromisoformat(raw)
            return timezone.make_aware(
                dt.datetime(parsed_date.year, parsed_date.month, parsed_date.day, 0, 0, 0),
                dt.timezone.utc,
            )
        parsed = dt.datetime.fromisoformat(raw)
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, dt.timezone.utc)
        return parsed
    except Exception:
        return None


def compute_job_idempotency_key(user_id: int, event_key: str, scheduled_start: dt.datetime) -> str:
    utc_dt = scheduled_start.astimezone(dt.timezone.utc) if scheduled_start else timezone.now()
    seed = f"{user_id}|{event_key}|{utc_dt.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# CBE Canonical HMAC-SHA256 Signing & Verification (matches cbe/hmac_auth.cpp)
# ---------------------------------------------------------------------------

def compute_cbe_canonical_string(
    method: str,
    path_with_query: str,
    timestamp: str,
    nonce: str,
    body_sha256_hex: str,
) -> str:
    return "\n".join([
        str(method or "POST").upper(),
        str(path_with_query or "/"),
        str(timestamp),
        str(nonce),
        str(body_sha256_hex).lower(),
    ])


def sign_cbe_headers(
    *,
    method: str,
    path_with_query: str,
    body_bytes: bytes,
    service_id: str,
    key_id: str,
    secret: str,
    timestamp: Optional[str] = None,
    nonce: Optional[str] = None,
) -> dict[str, str]:
    ts_str = timestamp or str(int(time.time()))
    nonce_str = nonce or secrets.token_hex(16)
    body_sha = hashlib.sha256(body_bytes).hexdigest().lower()
    canonical = compute_cbe_canonical_string(method, path_with_query, ts_str, nonce_str, body_sha)
    sig_hex = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest().lower()
    return {
        "X-CBE-Service-Id": service_id,
        "X-CBE-Key-Id": key_id,
        "X-CBE-Timestamp": ts_str,
        "X-CBE-Nonce": nonce_str,
        "X-CBE-Body-SHA256": body_sha,
        "X-CBE-Signature": f"v1={sig_hex}",
    }


def verify_cbe_hmac_headers(
    *,
    method: str,
    path_with_query: str,
    headers: dict[str, Any],
    raw_body: bytes,
    secret: str,
    max_skew_seconds: int = 300,
) -> tuple[bool, str]:
    """
    Verify incoming CBE canonical HMAC-SHA256 webhook headers.
    Returns (is_valid, reason).
    """
    lower_hdrs = {str(k).lower(): str(v) for k, v in (headers or {}).items()}
    ts_str = lower_hdrs.get("x-cbe-timestamp", "").strip()
    nonce = lower_hdrs.get("x-cbe-nonce", "").strip()
    body_sha_hdr = lower_hdrs.get("x-cbe-body-sha256", "").strip().lower()
    sig_hdr = lower_hdrs.get("x-cbe-signature", "").strip()

    if not secret:
        return False, "CBE webhook secret is not configured."
    if not ts_str or not nonce or len(nonce) < 8 or not sig_hdr:
        return False, "Missing required X-CBE HMAC authentication headers."

    try:
        ts_val = int(ts_str)
    except ValueError:
        return False, "Invalid X-CBE-Timestamp."
    ts_ms = ts_val if ts_val >= 100_000_000_000 else ts_val * 1000
    now_ms = int(time.time() * 1000)
    if abs(now_ms - ts_ms) > max_skew_seconds * 1000:
        return False, "X-CBE-Timestamp outside allowed clock skew window."

    actual_body_sha = hashlib.sha256(raw_body).hexdigest().lower()
    if body_sha_hdr and not hmac.compare_digest(body_sha_hdr, actual_body_sha):
        return False, "X-CBE-Body-SHA256 mismatch."

    canonical = compute_cbe_canonical_string(method, path_with_query, ts_str, nonce, actual_body_sha)
    expected_hex = hmac.new(secret.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest().lower()
    provided_hex = sig_hdr[3:].lower() if sig_hdr.lower().startswith("v1=") else sig_hdr.lower()
    if not hmac.compare_digest(provided_hex, expected_hex):
        return False, "X-CBE-Signature verification failed."
    return True, "ok"


# ---------------------------------------------------------------------------
# Step 1 & 2: Multi-User Calendar Discovery & Email/Calendar Link Resolution
# ---------------------------------------------------------------------------

def resolve_meeting_link_from_emails(
    user,
    *,
    title: str = "",
    attendees: Optional[list] = None,
    scheduled_start: Optional[dt.datetime] = None,
) -> str:
    """
    Search the user's relevant synced/sent emails (EmailThreadMessage and OutreachEmail)
    for a scheduled meeting link when the calendar event or Meeting lacks one.
    """
    from prospects.models import EmailThreadMessage, OutreachEmail

    attendee_emails = set()
    for a in (attendees or []):
        if isinstance(a, dict) and a.get("email"):
            attendee_emails.add(str(a["email"]).strip().lower())
        elif isinstance(a, str) and "@" in a:
            attendee_emails.add(a.strip().lower())

    msg_qs = EmailThreadMessage.objects.select_related("thread").filter(owner=user).order_by("-sent_at", "-created_at")
    if scheduled_start:
        window_start = scheduled_start - dt.timedelta(days=14)
        msg_qs = msg_qs.filter(Q(sent_at__gte=window_start) | Q(sent_at__isnull=True, created_at__gte=window_start))

    title_lower = (title or "").strip().lower()
    candidates = list(msg_qs[:60])

    # Pass 1: messages matching attendee email or event title
    for msg in candidates:
        sender_l = (msg.sender_email or "").lower()
        corresp_l = (getattr(msg.thread, "correspondent_email", "") or "").lower()
        subj_l = (msg.subject or "").lower()
        to_l = {str(x).lower() for x in (msg.to_emails or [])}
        matches_attendee = bool(attendee_emails and (sender_l in attendee_emails or corresp_l in attendee_emails or (to_l & attendee_emails)))
        matches_title = bool(title_lower and len(title_lower) >= 4 and (title_lower in subj_l or subj_l in title_lower))
        if matches_attendee or matches_title:
            url = extract_meeting_url_from_text(msg.body_text, msg.body_html, msg.snippet)
            if url:
                return url

    # Pass 2: fallback to OutreachEmail for attendee/title match
    outreach_qs = OutreachEmail.objects.filter(created_by=user).order_by("-created_at")[:40]
    for oe in outreach_qs:
        subj_l = (oe.subject or "").lower()
        matches_title = bool(title_lower and len(title_lower) >= 4 and title_lower in subj_l)
        if matches_title or not attendee_emails:
            url = extract_meeting_url_from_text(oe.body)
            if url:
                return url

    return ""


def _upsert_automation_job(
    *,
    user,
    source_type: str,
    external_event_id: str,
    scheduled_start: dt.datetime,
    scheduled_end: Optional[dt.datetime],
    title: str,
    meeting_link: str,
    organizer_email: str = "",
    attendees: Optional[list] = None,
    meeting_obj=None,
):
    from .models import CalendarEventRecording, MeetingAutomationJob

    event_key = external_event_id or (f"meeting:{meeting_obj.pk}" if meeting_obj else title or "untitled")
    idem_key = compute_job_idempotency_key(user.id, event_key, scheduled_start)

    if not meeting_link:
        meeting_link = resolve_meeting_link_from_emails(
            user,
            title=title,
            attendees=attendees,
            scheduled_start=scheduled_start,
        )

    platform = detect_meeting_platform(meeting_link) if meeting_link else ""
    cal_rec = None
    if external_event_id and not meeting_obj:
        cal_rec = CalendarEventRecording.objects.filter(user=user, event_id=external_event_id).first()

    job = MeetingAutomationJob.objects.filter(idempotency_key=idem_key).first()
    if job:
        updates = []
        if meeting_link and not job.meeting_link:
            job.meeting_link = meeting_link
            job.platform = platform
            updates.extend(["meeting_link", "platform"])
        if meeting_obj and not job.meeting_id:
            job.meeting = meeting_obj
            updates.append("meeting")
        if cal_rec and not job.calendar_recording_id:
            job.calendar_recording = cal_rec
            updates.append("calendar_recording")
        if title and not job.title:
            job.title = title[:500]
            updates.append("title")
        if scheduled_end and job.scheduled_end != scheduled_end:
            job.scheduled_end = scheduled_end
            updates.append("scheduled_end")
        if updates:
            updates.append("updated_at")
            job.save(update_fields=updates)
        return job, False

    job = MeetingAutomationJob.objects.create(
        user=user,
        meeting=meeting_obj,
        calendar_recording=cal_rec,
        source_type=source_type,
        external_event_id=external_event_id[:255],
        idempotency_key=idem_key,
        title=(title or "Scheduled Meeting")[:500],
        meeting_link=(meeting_link or "")[:512],
        platform=platform,
        organizer_email=(organizer_email or user.email or "")[:254],
        attendees=attendees or [],
        scheduled_start=scheduled_start,
        scheduled_end=scheduled_end,
        status=MeetingAutomationJob.Status.PENDING,
    )
    return job, True


def _fetch_microsoft_calendar_events(creds, time_min: dt.datetime, time_max: dt.datetime) -> list[dict]:
    from .microsoft_services import ms_api_request

    params = {
        "startDateTime": time_min.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "endDateTime": time_max.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "$top": 50,
    }
    data = ms_api_request(creds, "GET", "/me/calendarView", params=params)
    items = data.get("value", []) if isinstance(data, dict) else []
    events = []
    for item in items:
        if item.get("isCancelled"):
            continue
        start_obj = item.get("start") or {}
        end_obj = item.get("end") or {}
        online = item.get("onlineMeeting") or {}
        join_url = online.get("joinUrl") or item.get("onlineMeetingUrl") or extract_meeting_url_from_text(
            (item.get("location") or {}).get("displayName", ""),
            (item.get("body") or {}).get("content", ""),
            item.get("bodyPreview", ""),
        )
        events.append({
            "id": item.get("id") or "",
            "summary": item.get("subject") or "(No Title)",
            "description": item.get("bodyPreview") or "",
            "start": start_obj.get("dateTime"),
            "end": end_obj.get("dateTime"),
            "meet_url": join_url or "",
            "attendees": [
                {
                    "email": ((a.get("emailAddress") or {}).get("address") or ""),
                    "name": ((a.get("emailAddress") or {}).get("name") or ""),
                }
                for a in (item.get("attendees") or []) if isinstance(a, dict)
            ],
        })
    return events


def collect_scheduled_meetings_for_all_users(
    *,
    time_min: Optional[dt.datetime] = None,
    time_max: Optional[dt.datetime] = None,
) -> dict[str, Any]:
    """
    Step 1: Dynamically iterate over ALL active users, fetch their scheduled
    CRM Meeting records, Google Calendar events, and Microsoft Calendar events,
    and ensure idempotent MeetingAutomationJob entries exist.
    """
    from .calendar_services import list_events
    from .models import GoogleCalendarCredentials, MeetingAutomationJob, MicrosoftCalendarCredentials
    from prospects.models import Meeting

    now = timezone.now()
    window_min = time_min or (now - dt.timedelta(minutes=30))
    window_max = time_max or (now + dt.timedelta(days=1))

    discovered = 0
    created_jobs = 0
    errors = []

    # 1A. All CRM Meeting records across all active users
    meetings_qs = (
        Meeting.objects
        .select_related("prospect", "prospect_contact", "created_by", "google_calendar_owner")
        .filter(
            scheduled_datetime__gte=window_min,
            scheduled_datetime__lte=window_max,
            is_completed=False,
        )
        .exclude(status__in=["CANCELLED", "COMPLETED"])
    )
    for m in meetings_qs:
        owner = m.google_calendar_owner or m.created_by
        if not owner or not owner.is_active:
            continue
        discovered += 1
        attendees = []
        if m.prospect_contact and m.prospect_contact.official_email:
            attendees.append({"email": m.prospect_contact.official_email, "name": m.prospect_contact.contact_name})
        ext_id = m.google_event_id or m.calendar_event_id or f"meeting_{m.pk}"
        title = f"{m.prospect.company_name}: {m.agenda}" if m.agenda else f"Meeting with {m.prospect.company_name}"
        end_dt = m.scheduled_datetime + dt.timedelta(minutes=30)
        _job, is_new = _upsert_automation_job(
            user=owner,
            source_type=MeetingAutomationJob.SourceType.MEETING_RECORD,
            external_event_id=ext_id,
            scheduled_start=m.scheduled_datetime,
            scheduled_end=end_dt,
            title=title,
            meeting_link=(m.meeting_link or "").strip(),
            organizer_email=owner.email or "",
            attendees=attendees,
            meeting_obj=m,
        )
        if is_new:
            created_jobs += 1

    # 1B. All users with connected Google Calendar credentials
    for creds in GoogleCalendarCredentials.objects.select_related("user").filter(is_active=True, user__is_active=True):
        try:
            events = list_events(creds, time_min=window_min, time_max=window_max)
            for ev in events:
                start_dt = _parse_iso_datetime(ev.get("start"))
                if not start_dt:
                    continue
                end_dt = _parse_iso_datetime(ev.get("end")) or (start_dt + dt.timedelta(minutes=30))
                ev_id = str(ev.get("id") or "")
                link = ev.get("meet_url") or extract_meeting_url_from_text(ev.get("location"), ev.get("description"))
                linked_meeting = Meeting.objects.filter(
                    Q(google_event_id=ev_id) | Q(calendar_event_id=ev_id)
                ).first() if ev_id else None
                discovered += 1
                _job, is_new = _upsert_automation_job(
                    user=creds.user,
                    source_type=MeetingAutomationJob.SourceType.GOOGLE_CALENDAR,
                    external_event_id=ev_id,
                    scheduled_start=start_dt,
                    scheduled_end=end_dt,
                    title=ev.get("summary") or "Google Calendar Meeting",
                    meeting_link=link,
                    organizer_email=creds.email or creds.user.email or "",
                    attendees=ev.get("attendees") or [],
                    meeting_obj=linked_meeting,
                )
                if is_new:
                    created_jobs += 1
        except Exception as exc:
            logger.warning("Calendar discovery skipped for user %s: %s", creds.user_id, exc)
            errors.append(f"google_calendar user={creds.user_id}: {exc}")

    # 1C. All users with connected Microsoft Calendar credentials
    for ms_creds in MicrosoftCalendarCredentials.objects.select_related("user").filter(is_active=True, user__is_active=True):
        try:
            ms_events = _fetch_microsoft_calendar_events(ms_creds, window_min, window_max)
            for ev in ms_events:
                start_dt = _parse_iso_datetime(ev.get("start"))
                if not start_dt:
                    continue
                end_dt = _parse_iso_datetime(ev.get("end")) or (start_dt + dt.timedelta(minutes=30))
                ev_id = str(ev.get("id") or "")
                discovered += 1
                _job, is_new = _upsert_automation_job(
                    user=ms_creds.user,
                    source_type=MeetingAutomationJob.SourceType.MICROSOFT_CALENDAR,
                    external_event_id=ev_id,
                    scheduled_start=start_dt,
                    scheduled_end=end_dt,
                    title=ev.get("summary") or "Outlook Meeting",
                    meeting_link=ev.get("meet_url") or "",
                    organizer_email=ms_creds.email or ms_creds.user.email or "",
                    attendees=ev.get("attendees") or [],
                )
                if is_new:
                    created_jobs += 1
        except Exception as exc:
            logger.debug("Microsoft calendar discovery skipped for user %s: %s", ms_creds.user_id, exc)
            errors.append(f"microsoft_calendar user={ms_creds.user_id}: {exc}")

    return {"discovered": discovered, "created_jobs": created_jobs, "errors": errors}


# ---------------------------------------------------------------------------
# Step 3, 4 & 5: Trigger Webhook -> Custom Browser Engine (/v1/meetings)
# ---------------------------------------------------------------------------

def trigger_cbe_meeting_processing(payload: dict[str, Any]) -> dict[str, Any]:
    """
    Invoke unmodified Custom Browser Engine (`cbe_meet_service`) POST /v1/meetings
    with canonical HMAC-SHA256 authentication and `transcription_enabled=True` so
    CBE executes headless join, audio capture, speaker diarization, and transcription.
    """
    from .models import CalendarEventRecording, MeetingAutomationJob

    cbe_base_url = _get_env("CBE_SERVICE_URL", "http://127.0.0.1:8443").rstrip("/")
    service_id = _get_env("CBE_SERVICE_ID", "market-intel-db")
    key_id = _get_env("CBE_KEY_ID", "")
    secret = _get_env("CBE_HMAC_SECRET", "")
    profile_id = _get_env("CBE_DEFAULT_PROFILE_ID", "")
    timeout = int(_get_env("CBE_HTTP_TIMEOUT_SECONDS", "15") or 15)

    meet_url = str(payload.get("meeting_link") or payload.get("meet_url") or "").strip()
    if not meet_url:
        raise ValueError("meeting_link is required to trigger CBE meeting processing.")

    start_epoch_ms = int(payload.get("scheduled_start_epoch_ms") or 0)
    end_epoch_ms = int(payload.get("scheduled_end_epoch_ms") or 0)
    cbe_body = {
        "title": str(payload.get("title") or "Market Intel Scheduled Meeting")[:240],
        "meet_url": meet_url,
        "auto_assign_profile": True,
        "transcription_enabled": True,
        "scheduled_start_epoch_ms": start_epoch_ms,
        "scheduled_end_epoch_ms": end_epoch_ms,
    }
    if profile_id:
        cbe_body["profile_id"] = profile_id

    raw_bytes = json.dumps(cbe_body).encode("utf-8")
    path = "/v1/meetings"
    headers = {"Content-Type": "application/json"}
    if key_id and secret:
        headers.update(
            sign_cbe_headers(
                method="POST",
                path_with_query=path,
                body_bytes=raw_bytes,
                service_id=service_id,
                key_id=key_id,
                secret=secret,
            )
        )

    req = urllib.request.Request(
        f"{cbe_base_url}{path}",
        data=raw_bytes,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_json = json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        err_text = exc.read().decode("utf-8", errors="ignore")[:500]
        raise RuntimeError(f"CBE /v1/meetings HTTP {exc.code}: {err_text or exc.reason}") from exc

    job_id = payload.get("automation_job_id")
    cbe_job_id = str(resp_json.get("job_id") or "")
    cbe_meeting_id = str(resp_json.get("meeting_id") or "")

    if job_id:
        job = MeetingAutomationJob.objects.filter(pk=job_id).first()
        if job:
            job.status = MeetingAutomationJob.Status.PROCESSING
            job.cbe_job_id = cbe_job_id or job.cbe_job_id
            job.cbe_meeting_id = cbe_meeting_id or job.cbe_meeting_id
            job.dispatch_response = resp_json
            job.last_error = ""
            job.dispatched_at = job.dispatched_at or timezone.now()
            job.save(update_fields=[
                "status", "cbe_job_id", "cbe_meeting_id",
                "dispatch_response", "last_error", "dispatched_at", "updated_at",
            ])
            if job.meeting:
                job.meeting.transcription_status = "PROCESSING"
                job.meeting.cbe_meeting_id = cbe_meeting_id or job.meeting.cbe_meeting_id
                job.meeting.save(update_fields=["transcription_status", "cbe_meeting_id", "updated_at"])
            if job.calendar_recording:
                job.calendar_recording.transcription_status = "PROCESSING"
                job.calendar_recording.cbe_meeting_id = cbe_meeting_id or job.calendar_recording.cbe_meeting_id
                job.calendar_recording.save(update_fields=["transcription_status", "cbe_meeting_id", "updated_at"])

    return {"ok": True, "cbe_response": resp_json, "cbe_job_id": cbe_job_id}


def send_meeting_to_trigger_webhook(job) -> dict[str, Any]:
    """
    Step 3: Send meeting_link and required meeting details for a due MeetingAutomationJob
    to the configured trigger webhook (`MEETING_TRIGGER_WEBHOOK_URL`), or invoke the local
    trigger webhook workflow when no external URL override is set.
    """
    from .models import MeetingAutomationJob

    if not job.meeting_link:
        job.meeting_link = resolve_meeting_link_from_emails(
            job.user,
            title=job.title,
            attendees=job.attendees,
            scheduled_start=job.scheduled_start,
        )
        if job.meeting_link:
            job.platform = detect_meeting_platform(job.meeting_link)

    if not job.meeting_link:
        job.status = MeetingAutomationJob.Status.SKIPPED
        job.last_error = "No meeting link found in calendar event, Meeting record, or emails."
        job.save(update_fields=["status", "last_error", "updated_at"])
        return {"dispatched": False, "reason": "no_meeting_link"}

    payload = {
        "event_type": "meeting.scheduled_due",
        "automation_job_id": str(job.id),
        "idempotency_key": job.idempotency_key,
        "user_id": job.user_id,
        "username": job.user.username,
        "user_email": job.user.email,
        "meeting_id": job.meeting_id,
        "calendar_event_id": job.external_event_id,
        "source_type": job.source_type,
        "title": job.title,
        "meeting_link": job.meeting_link,
        "platform": job.platform or detect_meeting_platform(job.meeting_link),
        "organizer_email": job.organizer_email,
        "attendees": job.attendees or [],
        "scheduled_start": job.scheduled_start.isoformat() if job.scheduled_start else None,
        "scheduled_end": job.scheduled_end.isoformat() if job.scheduled_end else None,
        "scheduled_start_epoch_ms": int(job.scheduled_start.timestamp() * 1000) if job.scheduled_start else 0,
        "scheduled_end_epoch_ms": int(job.scheduled_end.timestamp() * 1000) if job.scheduled_end else 0,
        "transcription_enabled": True,
    }

    webhook_url = _get_env("MEETING_TRIGGER_WEBHOOK_URL", "")
    secret = _get_env("CBE_TRIGGER_WEBHOOK_SECRET", "") or _get_env("CBE_HMAC_SECRET", "")
    service_id = _get_env("CBE_SERVICE_ID", "market-intel-db")
    key_id = _get_env("CBE_KEY_ID", "trigger-key")

    if webhook_url:
        parsed = urllib.parse.urlparse(webhook_url)
        path_with_query = parsed.path or "/"
        if parsed.query:
            path_with_query = f"{path_with_query}?{parsed.query}"
        raw_bytes = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Idempotency-Key": job.idempotency_key,
        }
        if secret:
            headers.update(
                sign_cbe_headers(
                    method="POST",
                    path_with_query=path_with_query,
                    body_bytes=raw_bytes,
                    service_id=service_id,
                    key_id=key_id,
                    secret=secret,
                )
            )
        req = urllib.request.Request(webhook_url, data=raw_bytes, headers=headers, method="POST")
        timeout = int(_get_env("CBE_HTTP_TIMEOUT_SECONDS", "15") or 15)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp_body = json.loads(resp.read().decode("utf-8") or "{}")
        job.webhook_url_used = webhook_url
        job.dispatched_at = timezone.now()
        if job.status == MeetingAutomationJob.Status.PENDING:
            job.status = MeetingAutomationJob.Status.DISPATCHED
        job.dispatch_response = resp_body
        job.save(update_fields=["meeting_link", "platform", "webhook_url_used", "dispatched_at", "status", "dispatch_response", "updated_at"])
        return {"dispatched": True, "webhook_url": webhook_url, "response": resp_body}

    # Internal default trigger path when no external trigger URL is overridden
    res = trigger_cbe_meeting_processing(payload)
    return {"dispatched": True, "webhook_url": "internal:/api/auth/webhooks/meeting-trigger/", "response": res}


def process_due_scheduled_meetings(
    *,
    now: Optional[dt.datetime] = None,
    lead_seconds: Optional[int] = None,
    grace_seconds: Optional[int] = None,
) -> dict[str, Any]:
    """
    Discover scheduled meetings across all users and dispatch due meetings
    whose scheduled start time has arrived.
    """
    from .models import MeetingAutomationJob

    current = now or timezone.now()
    lead = int(lead_seconds if lead_seconds is not None else (_get_env("CBE_JOIN_LEAD_SECONDS", "60") or 60))
    grace = int(grace_seconds if grace_seconds is not None else (_get_env("CBE_LATE_JOIN_GRACE_SECONDS", "900") or 900))

    discovery = collect_scheduled_meetings_for_all_users(
        time_min=current - dt.timedelta(seconds=grace),
        time_max=current + dt.timedelta(hours=24),
    )

    due_cutoff = current + dt.timedelta(seconds=lead)
    pending_jobs = list(
        MeetingAutomationJob.objects
        .select_related("user", "meeting", "calendar_recording")
        .filter(
            status=MeetingAutomationJob.Status.PENDING,
            scheduled_start__lte=due_cutoff,
        )
        .order_by("scheduled_start")
    )

    dispatched_count = 0
    skipped_count = 0
    failed_count = 0
    for job in pending_jobs:
        end_limit = (job.scheduled_end or (job.scheduled_start + dt.timedelta(seconds=grace)))
        if current > end_limit + dt.timedelta(seconds=grace):
            job.status = MeetingAutomationJob.Status.SKIPPED
            job.last_error = "Meeting window already ended before dispatch."
            job.save(update_fields=["status", "last_error", "updated_at"])
            skipped_count += 1
            continue
        try:
            res = send_meeting_to_trigger_webhook(job)
            if res.get("dispatched"):
                dispatched_count += 1
            else:
                skipped_count += 1
        except Exception as exc:
            logger.error("Failed dispatching MeetingAutomationJob %s: %s", job.id, exc)
            job.status = MeetingAutomationJob.Status.FAILED
            job.last_error = str(exc)[:1000]
            job.save(update_fields=["status", "last_error", "updated_at"])
            failed_count += 1

    return {
        **discovery,
        "dispatched": dispatched_count,
        "skipped": skipped_count,
        "failed": failed_count,
    }


# ---------------------------------------------------------------------------
# Step 6: Ingest CBE Completion Webhook & Store Results in Market Intel DB
# ---------------------------------------------------------------------------

def _format_ms_hms(ms: Any) -> str:
    try:
        total_ms = max(0, int(ms))
    except (TypeError, ValueError):
        return "00:00:00"
    secs = total_ms // 1000
    hrs = secs // 3600
    mins = (secs % 3600) // 60
    rem = secs % 60
    return f"{hrs:02d}:{mins:02d}:{rem:02d}"


def format_transcript_text_from_cbe(payload: dict[str, Any]) -> str:
    tr = payload.get("transcription") or {}
    segments = tr.get("segments") or []
    lines = []
    if isinstance(segments, list) and segments:
        for seg in segments:
            if not isinstance(seg, dict):
                continue
            text = str(seg.get("text") or seg.get("english_text") or "").strip()
            if not text:
                continue
            speaker = str(seg.get("speaker_name") or seg.get("display_name") or seg.get("speaker") or "Speaker").strip()
            ts = _format_ms_hms(seg.get("start_ms") or seg.get("start_offset_ms") or 0)
            lines.append(f"[{ts}] {speaker}: {text}")

    if not lines:
        for seg in (payload.get("speaker_segments") or []):
            if not isinstance(seg, dict):
                continue
            text = str(seg.get("text") or "").strip()
            if not text:
                continue
            speaker = str(seg.get("speaker_name") or seg.get("display_name") or "Speaker").strip()
            ts = _format_ms_hms(seg.get("start_ms") or 0)
            lines.append(f"[{ts}] {speaker}: {text}")
    return "\n".join(lines)


def _match_target_records(payload: dict[str, Any], idempotency_key: str, delivery_id: str):
    from accounts.google_meet_service import extract_meeting_code
    from prospects.models import Meeting
    from .models import CalendarEventRecording, MeetingAutomationJob

    meeting_info = payload.get("meeting") or {}
    cbe_meeting_id = str(meeting_info.get("meeting_id") or "")
    cal_event_id = str(meeting_info.get("calendar_event_id") or "")
    meeting_url = str(meeting_info.get("meeting_url") or "")
    meet_code = extract_meeting_code(meeting_url) if meeting_url else ""

    job = None
    if delivery_id:
        job = MeetingAutomationJob.objects.select_related("meeting", "calendar_recording", "user").filter(cbe_delivery_id=delivery_id).first()
    if not job and cbe_meeting_id:
        job = MeetingAutomationJob.objects.select_related("meeting", "calendar_recording", "user").filter(cbe_meeting_id=cbe_meeting_id).first()
    if not job and idempotency_key:
        job = MeetingAutomationJob.objects.select_related("meeting", "calendar_recording", "user").filter(idempotency_key=idempotency_key).first()
    if not job and cal_event_id:
        job = MeetingAutomationJob.objects.select_related("meeting", "calendar_recording", "user").filter(external_event_id=cal_event_id).order_by("-scheduled_start").first()
    if not job and meeting_url:
        job = MeetingAutomationJob.objects.select_related("meeting", "calendar_recording", "user").filter(meeting_link__iexact=meeting_url).order_by("-scheduled_start").first()
    if not job and meet_code:
        job = MeetingAutomationJob.objects.select_related("meeting", "calendar_recording", "user").filter(meeting_link__icontains=meet_code).order_by("-scheduled_start").first()

    meeting_obj = job.meeting if (job and job.meeting) else None
    if not meeting_obj and cal_event_id:
        meeting_obj = Meeting.objects.filter(Q(google_event_id=cal_event_id) | Q(calendar_event_id=cal_event_id)).first()
    if not meeting_obj and meeting_url:
        meeting_obj = Meeting.objects.filter(meeting_link__iexact=meeting_url).first()
    if not meeting_obj and meet_code:
        meeting_obj = Meeting.objects.filter(meeting_link__icontains=meet_code).first()

    cal_rec = job.calendar_recording if (job and job.calendar_recording) else None
    if not cal_rec and cal_event_id:
        qs = CalendarEventRecording.objects.filter(event_id=cal_event_id)
        if job:
            qs = qs.filter(user=job.user)
        cal_rec = qs.first()
    if not cal_rec and job and cal_event_id and not meeting_obj:
        cal_rec, _ = CalendarEventRecording.objects.get_or_create(
            user=job.user,
            event_id=cal_event_id,
            defaults={"meeting_link": meeting_url[:512]},
        )

    return job, meeting_obj, cal_rec


def ingest_cbe_completed_webhook(
    payload: dict[str, Any],
    *,
    delivery_id: str = "",
    idempotency_key: str = "",
) -> dict[str, Any]:
    """
    Step 6: Verify & store completed CBE recording, speaker diarization segments,
    participants, and audio transcription into MeetingAutomationJob, Meeting, and
    CalendarEventRecording records inside Market Intel DB.
    """
    from .models import CalendarEventRecording, MeetingAutomationJob

    del_id = str(delivery_id or payload.get("delivery_id") or "")[:255]
    idem = str(idempotency_key or payload.get("idempotency_key") or "")[:128]
    meeting_info = payload.get("meeting") or {}
    rec_info = payload.get("recording") or {}
    tr_info = payload.get("transcription") or {}
    participants = payload.get("participants") or []
    speaker_segments = payload.get("speaker_segments") or []
    tr_segments = tr_info.get("segments") or []

    transcript_text = format_transcript_text_from_cbe(payload)
    tr_status_raw = str(tr_info.get("status") or "completed").upper()
    tr_status = "COMPLETED" if tr_status_raw == "COMPLETED" else tr_status_raw
    backend_used = str(tr_info.get("backend_used") or "")[:64]
    cbe_meeting_id = str(meeting_info.get("meeting_id") or "")[:255]
    cbe_session_id = str(meeting_info.get("session_id") or "")[:255]
    cbe_recording_id = str(rec_info.get("recording_id") or "")[:255]
    now = timezone.now()

    with transaction.atomic():
        job, meeting_obj, cal_rec = _match_target_records(payload, idem, del_id)

        if job and job.cbe_delivery_id and del_id and job.cbe_delivery_id == del_id and job.status == MeetingAutomationJob.Status.COMPLETED:
            return {
                "duplicate": True,
                "job_id": str(job.id),
                "meeting_id": meeting_obj.id if meeting_obj else None,
                "calendar_recording_id": cal_rec.id if cal_rec else None,
            }

        if job:
            job.status = MeetingAutomationJob.Status.COMPLETED
            job.cbe_meeting_id = cbe_meeting_id or job.cbe_meeting_id
            job.cbe_session_id = cbe_session_id or job.cbe_session_id
            job.cbe_recording_id = cbe_recording_id or job.cbe_recording_id
            job.cbe_delivery_id = del_id or job.cbe_delivery_id
            job.transcript_text = transcript_text
            job.transcript_segments = tr_segments if isinstance(tr_segments, list) else []
            job.speaker_segments = speaker_segments if isinstance(speaker_segments, list) else []
            job.participants = participants if isinstance(participants, list) else []
            job.recording_metadata = rec_info if isinstance(rec_info, dict) else {}
            job.webhook_payload = payload
            job.last_error = ""
            job.completed_at = now
            if meeting_obj and not job.meeting_id:
                job.meeting = meeting_obj
            if cal_rec and not job.calendar_recording_id:
                job.calendar_recording = cal_rec
            job.save()

        common_fields = {
            "transcript_text": transcript_text,
            "transcript_segments": tr_segments if isinstance(tr_segments, list) else [],
            "speaker_segments": speaker_segments if isinstance(speaker_segments, list) else [],
            "diarization_participants": participants if isinstance(participants, list) else [],
            "transcription_status": tr_status,
            "transcription_backend": backend_used,
            "transcription_completed_at": now,
            "cbe_meeting_id": cbe_meeting_id,
            "cbe_session_id": cbe_session_id,
            "cbe_recording_id": cbe_recording_id,
            "cbe_delivery_id": del_id,
            "recording_status": "COMPLETED" if rec_info.get("recording_id") else None,
            "recording_downloaded_at": now if rec_info.get("recording_id") else None,
        }

        if meeting_obj:
            for attr, val in common_fields.items():
                if val is not None:
                    setattr(meeting_obj, attr, val)
            meeting_obj.is_completed = True
            meeting_obj.status = "COMPLETED"
            meeting_obj.save()

        if cal_rec:
            for attr, val in common_fields.items():
                if val is not None:
                    setattr(cal_rec, attr, val)
            cal_rec.save()

    return {
        "duplicate": False,
        "job_id": str(job.id) if job else None,
        "meeting_id": meeting_obj.id if meeting_obj else None,
        "calendar_recording_id": cal_rec.id if cal_rec else None,
        "transcription_status": tr_status,
        "utterance_count": len(tr_segments) if isinstance(tr_segments, list) else 0,
        "speaker_segment_count": len(speaker_segments) if isinstance(speaker_segments, list) else 0,
    }
