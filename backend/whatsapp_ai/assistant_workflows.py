from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone as dj_timezone

from accounts import calendar_services as cal
from accounts import microsoft_services as ms
from accounts import zoom_services as zoom
from accounts.timezone_utils import extract_timezone_from_text, normalize_timezone
from prospects.models import Meeting, Prospect, ProspectContact
from prospects.task_service import (
    create_whatsapp_escalation_pre_task,
    resolve_prospect_and_contact_for_phone,
)
from rag.constants import REASON_INJECTION_QUESTION
from .models import WhatsAppAssistantState, WhatsAppMeetingRequest

logger = logging.getLogger(__name__)


ESCALATION_OFFER_MESSAGE = (
    "Our executive will contact you once they are available. "
    "I can forward your request to the concerned executive for further assistance. "
    "Would you like me to share your query and contact details with them? "
    "Or ask another business question if I can help, I will."
)


@dataclass
class AssistantWorkflowOutcome:
    handled: bool = False
    reply_text: str = ""
    model_used: str = ""
    skip_reason: str = ""
    meeting_request_id: Optional[str] = None


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def is_meeting_scheduling_intent(text: str) -> bool:
    t = _clean_text(text).lower()
    if not t:
        return False
    strong_patterns = [
        r"\bschedule\b.*\b(meeting|call|demo|session|appointment|zoom|meet)\b",
        r"\b(book|arrange|set up|setup|fix|organize|plan)\b.*\b(meeting|call|demo|appointment)\b",
        r"\bwant to (meet|schedule|book)\b",
        r"\bcan we (meet|schedule|have a call|have a meeting|hop on a call)\b",
        r"\bmeeting\b.*\b(schedule|book|tomorrow|today|next week|zoom|google meet|slot|time)\b",
        r"\blet'?s\b.*\b(meet|schedule a call|schedule a meeting|book a call)\b",
        r"\binterested in scheduling\b",
        r"\bi'?d like to schedule\b",
    ]
    return any(re.search(pat, t) for pat in strong_patterns)


def is_affirmative_reply(text: str) -> bool:
    t = _clean_text(text).lower().strip("!.,? ")
    if not t:
        return False
    # Exact or leading confirmation words
    if re.match(
        r"^(yes|yep|yeah|yup|sure|ok|okay|confirm|confirmed|please do|go ahead|"
        r"proceed|sounds good|do it|please share|share it|forward it|book it|"
        r"schedule it|correct|right|definitely|absolutely|yes please)\b",
        t,
    ):
        # Guard against "yes, actually no" or question forms
        if re.search(r"\b(no|don't|do not|cancel|stop)\b", t):
            return False
        return True
    if any(
        phrase in t
        for phrase in (
            "please forward",
            "share my query",
            "share my details",
            "forward my request",
            "confirm the meeting",
            "confirm meeting",
            "book the meeting",
            "go ahead and book",
        )
    ):
        return True
    return False


def is_negative_or_cancel_reply(text: str) -> bool:
    t = _clean_text(text).lower().strip("!.,? ")
    if not t:
        return False
    return bool(
        re.match(r"^(no|nope|nah|cancel|stop|nevermind|never mind|don't|do not|skip this|not now)\b", t)
        or "cancel meeting" in t
        or "cancel scheduling" in t
    )


def _normalize_timezone(raw_tz: str) -> Optional[str]:
    return normalize_timezone(raw_tz)


def _parse_date_deterministic(text: str, today: date) -> Optional[str]:
    lower = text.lower()
    # Explicit ISO YYYY-MM-DD
    m_iso = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", text)
    if m_iso:
        try:
            d = date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
            return d.isoformat()
        except ValueError:
            pass

    # Slash or dash DD/MM/YYYY or MM/DD/YYYY (prefer YYYY at end)
    m_dmy = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](20\d{2})\b", text)
    if m_dmy:
        a, b, y = int(m_dmy.group(1)), int(m_dmy.group(2)), int(m_dmy.group(3))
        # Disambiguate DD/MM vs MM/DD: if a > 12 => DD/MM; elif b > 12 => MM/DD; else default DD/MM
        candidates = [(b, a)] if a > 12 else ([(a, b)] if b > 12 else [(b, a), (a, b)])
        for month, day in candidates:
            try:
                return date(y, month, day).isoformat()
            except ValueError:
                continue

    # Named month ("20 Nov 2026", "Nov 20", "November 20, 2026")
    months = {
        "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
        "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
        "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
    }
    m_named1 = re.search(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?:\s*,?\s*(20\d{2}))?\b",
        lower,
    )
    if m_named1:
        day = int(m_named1.group(1))
        month = months[m_named1.group(2)]
        year = int(m_named1.group(3)) if m_named1.group(3) else today.year
        try:
            d = date(year, month, day)
            if not m_named1.group(3) and d < today:
                d = date(year + 1, month, day)
            return d.isoformat()
        except ValueError:
            pass

    m_named2 = re.search(
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?(?:\s*,?\s*(20\d{2}))?\b",
        lower,
    )
    if m_named2:
        month = months[m_named2.group(1)]
        day = int(m_named2.group(2))
        year = int(m_named2.group(3)) if m_named2.group(3) else today.year
        try:
            d = date(year, month, day)
            if not m_named2.group(3) and d < today:
                d = date(year + 1, month, day)
            return d.isoformat()
        except ValueError:
            pass

    if "day after tomorrow" in lower:
        return (today + timedelta(days=2)).isoformat()
    if re.search(r"\btomorrow\b", lower):
        return (today + timedelta(days=1)).isoformat()
    if re.search(r"\btoday\b", lower):
        return today.isoformat()

    weekdays = {
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6,
    }
    for name, idx in weekdays.items():
        if re.search(rf"\b(this|next|on)?\s*{name}\b", lower):
            days_ahead = (idx - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            if f"next {name}" in lower and days_ahead < 7:
                days_ahead += 7
            return (today + timedelta(days=days_ahead)).isoformat()

    return None


def _parse_time_deterministic(text: str) -> Optional[str]:
    lower = text.lower()
    # 12-hour with optional minutes ("3 pm", "3:30pm", "10:15 a.m.")
    m_12 = re.search(r"\b(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*(a\.?m\.?|p\.?m\.?)\b", lower)
    if m_12:
        hour = int(m_12.group(1))
        minute = int(m_12.group(2) or 0)
        ampm = m_12.group(3).replace(".", "")
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        return f"{hour:02d}:{minute:02d}"

    # 24-hour HH:MM
    m_24 = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", lower)
    if m_24:
        return f"{int(m_24.group(1)):02d}:{int(m_24.group(2)):02d}"

    return None


def _parse_platform_deterministic(text: str) -> Optional[str]:
    lower = text.lower()
    has_zoom = bool(re.search(r"\bzoom\b", lower))
    has_gmeet = bool(re.search(r"\b(google\s*meet|gmeet|g-meet|meet\.google)\b", lower))
    has_teams = bool(re.search(r"\b(ms\s*teams|microsoft\s*teams|teams|outlook)\b", lower))
    matches = [p for flag, p in ((has_zoom, "ZOOM"), (has_gmeet, "GOOGLE_MEET"), (has_teams, "MS_TEAMS")) if flag]
    if len(matches) == 1:
        return matches[0]
    return None


def _parse_duration_deterministic(text: str) -> Optional[int]:
    lower = (text or "").lower()
    if re.search(r"\bhalf\s*(?:an?\s*)?hour\b", lower):
        return 30
    m_hr = re.search(r"\b(\d+(?:\.\d+)?)\s*(?:hr|hrs|hour|hours)\b", lower)
    if m_hr:
        try:
            mins = int(round(float(m_hr.group(1)) * 60))
            if 15 <= mins <= 480:
                return mins
        except ValueError:
            pass
    m_min = re.search(r"\b(\d{2,3})\s*(?:m|min|mins|minute|minutes)\b", lower)
    if m_min:
        try:
            mins = int(m_min.group(1))
            if 15 <= mins <= 480:
                return mins
        except ValueError:
            pass
    return None


def _parse_alternative_choice_index(text: str, max_options: int) -> Optional[int]:
    t = _clean_text(text).lower()
    if not t or max_options <= 0:
        return None
    m = re.match(r"^(?:option\s*|slot\s*|choice\s*|#)?(\d+)(?:\b|[.)])?$", t)
    if m:
        idx = int(m.group(1))
        if 1 <= idx <= max_options:
            return idx
    ordinals = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4}
    for word, idx in ordinals.items():
        if re.search(rf"\b(?:the\s+)?{word}(?:\s+(?:one|slot|option))?\b", t) and idx <= max_options:
            return idx
    return None


def _parse_timezone_deterministic(text: str, *, expecting_timezone: bool = False) -> Optional[str]:
    return extract_timezone_from_text(text, expecting_timezone=expecting_timezone)


def _extract_email_deterministic(text: str) -> Optional[str]:
    m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")
    return m.group(0) if m else None


def _extract_with_gemini_fallback(text: str, current_state: dict, model_name: str = "") -> dict:
    """
    Optional structured slot extraction via Gemini when API key is configured.
    Never throws; returns {} if unavailable or on error.
    """
    api_key = getattr(settings, "GEMINI_API_KEY", "") or ""
    if not api_key:
        return {}
    try:
        from google import genai
        from google.genai import types
    except Exception:
        return {}

    today_str = dj_timezone.localdate().isoformat()
    prompt = (
        f"Today's date is {today_str}.\n"
        f"Current collected meeting state JSON: {json.dumps(current_state)}\n"
        f"User WhatsApp message: {text!r}\n\n"
        "Extract any meeting scheduling details explicitly mentioned in the user's message "
        "and return ONLY valid JSON with keys (use null if not mentioned in this message): "
        '{"date": "YYYY-MM-DD or null", "time": "HH:MM (24-hour) or null", '
        '"timezone": "IANA timezone name like Asia/Kolkata or America/New_York or null", '
        '"duration_minutes": "integer minutes or null", '
        '"platform": "ZOOM or GOOGLE_MEET or MS_TEAMS or null", "email": "email or null", '
        '"topic": "short agenda/topic or null", "company_name": "company name or null"}.'
    )
    try:
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=model_name or getattr(settings, "GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=256),
        )
        raw = (resp.text or "").strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE | re.DOTALL).strip()
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception as exc:
        logger.debug("Gemini meeting slot extraction fallback failed cleanly: %s", exc)
        return {}


def _extract_meeting_slots(text: str, existing: dict, model_name: str = "") -> dict:
    """
    Merge deterministic extraction with optional Gemini extraction so both natural
    language and strict structured inputs work reliably.
    """
    updated = dict(existing or {})
    today = dj_timezone.localdate()

    expecting_tz = bool(updated.get("date") and updated.get("time") and not updated.get("timezone"))
    parsed_date = _parse_date_deterministic(text, today)
    parsed_time = _parse_time_deterministic(text)
    parsed_tz = _parse_timezone_deterministic(text, expecting_timezone=expecting_tz)
    parsed_platform = _parse_platform_deterministic(text)
    parsed_duration = _parse_duration_deterministic(text)
    parsed_email = _extract_email_deterministic(text)

    # Call Gemini only when key slots remain ambiguous in freeform text
    need_llm = (
        (not parsed_date and not updated.get("date"))
        or (not parsed_time and not updated.get("time"))
        or (not parsed_tz and not updated.get("timezone"))
    )
    llm_slots: dict = {}
    if need_llm and len(text.split()) >= 2:
        llm_slots = _extract_with_gemini_fallback(text, updated, model_name=model_name)

    if not parsed_date and llm_slots.get("date"):
        try:
            date.fromisoformat(str(llm_slots["date"]).strip())
            parsed_date = str(llm_slots["date"]).strip()
        except ValueError:
            pass

    if not parsed_time and llm_slots.get("time"):
        if re.match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", str(llm_slots["time"]).strip()):
            parsed_time = str(llm_slots["time"]).strip()

    if not parsed_tz and llm_slots.get("timezone"):
        parsed_tz = _normalize_timezone(str(llm_slots["timezone"]))

    if not parsed_platform and llm_slots.get("platform") in ("ZOOM", "GOOGLE_MEET", "MS_TEAMS"):
        parsed_platform = llm_slots["platform"]

    if not parsed_duration and llm_slots.get("duration_minutes"):
        try:
            d_mins = int(llm_slots["duration_minutes"])
            if 15 <= d_mins <= 480:
                parsed_duration = d_mins
        except (TypeError, ValueError):
            pass

    if not parsed_email and llm_slots.get("email"):
        parsed_email = _extract_email_deterministic(str(llm_slots["email"]))

    # Extract explicit topic if user answered agenda/topic prompt or used natural phrasing
    topic = None
    m_topic = re.search(
        r"(?:(?:topic|agenda)\s*[:\-]\s*|(?:about|regarding|to discuss)\s+)([^?.!,\n]{2,150})",
        text,
        re.IGNORECASE,
    )
    if m_topic:
        topic = m_topic.group(1).strip(" .?!,-")[:200]
    elif re.search(r"\bfor\s+([A-Za-z][^?.!,\n]{2,120})", text, re.IGNORECASE):
        m_for = re.search(r"\bfor\s+([A-Za-z][^?.!,\n]{2,120})", text, re.IGNORECASE)
        cand_topic = m_for.group(1).strip(" .?!,-")
        if cand_topic.lower() not in ("zoom", "google meet", "gmeet", "ms teams", "microsoft teams", "teams", "me", "us", "you"):
            topic = cand_topic[:200]
    elif llm_slots.get("topic"):
        topic = str(llm_slots["topic"]).strip()[:200]
    elif (
        updated.get("awaiting_details")
        and not parsed_date
        and not parsed_time
        and not parsed_platform
        and not parsed_tz
    ):
        # User answered our details prompt cleanly (maybe "product demo, skip email" or "demo at @email")
        cleaned = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "", text).strip(" ,.-")
        if cleaned and cleaned.lower() not in ("skip", "none", "na", "n/a", "no"):
            topic = cleaned[:200]

    company_mention = None
    m_comp = re.search(r"\b(?:from|with|at|company)\s+([A-Z][A-Za-z0-9&.\- ]{1,60}?)(?:\s+(?:to|and|on|at|for|tomorrow|today|,)|$)", text)
    if m_comp:
        cand = m_comp.group(1).strip()
        if cand.lower() not in ("zoom", "google meet", "meet"):
            company_mention = cand
    elif llm_slots.get("company_name"):
        company_mention = str(llm_slots["company_name"]).strip()[:100]

    changed = False
    if parsed_date and parsed_date != updated.get("date"):
        updated["date"] = parsed_date
        changed = True
    if parsed_time and parsed_time != updated.get("time"):
        updated["time"] = parsed_time
        changed = True
    if parsed_tz and parsed_tz != updated.get("timezone"):
        updated["timezone"] = parsed_tz
        changed = True
    if parsed_platform and parsed_platform != updated.get("platform"):
        updated["platform"] = parsed_platform
        changed = True
    if parsed_duration and parsed_duration != updated.get("duration_minutes"):
        updated["duration_minutes"] = parsed_duration
        changed = True
    elif not updated.get("duration_minutes"):
        updated["duration_minutes"] = int(getattr(settings, "MEETING_DEFAULT_DURATION_MINUTES", 30) or 30)
    if parsed_email and parsed_email != updated.get("email"):
        updated["email"] = parsed_email
        changed = True
    if topic and topic != updated.get("topic"):
        updated["topic"] = topic
        changed = True
    if company_mention and not updated.get("company_name"):
        updated["company_name"] = company_mention
        changed = True

    if (
        re.search(r"\b(?:skip\s*(?:email|details?)|no\s*email)\b", text, re.IGNORECASE)
        or (
            updated.get("awaiting_details")
            and (topic or parsed_email or re.search(r"\b(skip|none|no agenda|na|n/a)\b", text, re.IGNORECASE))
        )
    ):
        updated["details_collected"] = True
        updated["awaiting_details"] = False

    if changed and updated.get("awaiting_confirmation") and not is_affirmative_reply(text):
        # User modified a slot instead of simply confirming -> re-present updated summary
        updated["awaiting_confirmation"] = False

    return updated


def _resolve_session_owner(session):
    """
    Strictly resolve the authenticated owner of this WhatsAppSession.
    Never substitute another user or pick an arbitrary global fallback user.
    """
    owner = getattr(session, "owner", None) if session is not None else None
    if owner and getattr(owner, "is_active", False):
        return owner
    return None


def _platform_label(platform: str) -> str:
    return {
        "ZOOM": "Zoom",
        "GOOGLE_MEET": "Google Meet",
        "MS_TEAMS": "Microsoft Teams",
    }.get(platform or "", "Google Meet")


def _is_valid_meeting_link(url: str) -> bool:
    import urllib.parse

    if not url or not isinstance(url, str):
        return False
    parsed = urllib.parse.urlparse(url.strip())
    return parsed.scheme == "https" and bool(parsed.netloc)


def _resolve_owner_platforms(owner) -> Dict[str, Any]:
    """Return active connected meeting/calendar credentials strictly for `owner`."""
    if not owner:
        return {"google": None, "microsoft": None, "zoom": None}
    return {
        "google": cal.get_calendar_credentials(owner),
        "microsoft": ms.get_microsoft_credentials(owner),
        "zoom": zoom.get_zoom_credentials(owner),
    }


def _available_platform_choices_text(owner) -> str:
    creds = _resolve_owner_platforms(owner)
    labels = []
    if creds["zoom"]:
        labels.append("*Zoom*")
    if creds["google"]:
        labels.append("*Google Meet*")
    if creds["microsoft"]:
        labels.append("*Microsoft Teams*")
    if not labels:
        return "*Zoom*, *Google Meet*, or *Microsoft Teams*"
    if len(labels) == 1:
        return labels[0]
    if len(labels) == 2:
        return f"{labels[0]} or {labels[1]}"
    return f"{', '.join(labels[:-1])}, or {labels[-1]}"


def _msg_text(msg) -> str:
    return (getattr(msg, "full_body", "") or getattr(msg, "body_preview", "") or "").strip()


def _resolve_conv_crm(conversation, sender_phone: str = "", email: str = "", sender_name: str = "", owner=None):
    prospect = getattr(conversation, "prospect", None)
    contact = getattr(conversation, "prospect_contact", None)
    if prospect and contact:
        return prospect, contact
    p2, c2 = resolve_prospect_and_contact_for_phone(
        phone=sender_phone or getattr(conversation, "phone_number", "") or getattr(conversation, "chat_id", ""),
        email=email,
        sender_name=sender_name or getattr(conversation, "whatsapp_name", ""),
    )
    resolved_p = prospect or p2
    resolved_c = contact or c2
    if not prospect and resolved_p and owner and resolved_p.created_by and resolved_p.created_by != owner.username:
        return None, None
    return resolved_p, resolved_c


def _collect_owner_local_busy_intervals(owner, window_start_utc, window_end_utc, exclude_request_id=None):
    """Collect busy intervals from CRM Meeting records and active WhatsAppMeetingRequest locks owned by `owner`."""
    from datetime import timezone as _dt_tz

    busy = []
    if not owner:
        return busy

    default_dur = int(getattr(settings, "MEETING_DEFAULT_DURATION_MINUTES", 30) or 30)
    meetings = (
        Meeting.objects
        .filter(
            Q(created_by=owner) | Q(google_calendar_owner=owner),
            scheduled_datetime__gte=window_start_utc - timedelta(hours=8),
            scheduled_datetime__lte=window_end_utc,
        )
        .exclude(status__in=["CANCELLED"])
        .prefetch_related("whatsapp_requests")
    )
    for m in meetings:
        m_start = m.scheduled_datetime
        if m_start.tzinfo is None:
            m_start = m_start.replace(tzinfo=_dt_tz.utc)
        m_start = m_start.astimezone(_dt_tz.utc)
        req_dur = default_dur
        try:
            linked_req = m.whatsapp_requests.first()
            if linked_req and linked_req.duration_minutes:
                req_dur = int(linked_req.duration_minutes)
        except Exception:
            pass
        m_end = m_start + timedelta(minutes=req_dur)
        busy.append((m_start, m_end, m.agenda or f"CRM Meeting ({m.meeting_provider})"))

    active_reqs = WhatsAppMeetingRequest.objects.filter(
        user=owner,
        state__in=[
            WhatsAppMeetingRequest.State.REVALIDATING_SLOT,
            WhatsAppMeetingRequest.State.CREATING_MEETING,
            WhatsAppMeetingRequest.State.SCHEDULED,
        ],
        selected_slot_start__lt=window_end_utc,
        selected_slot_end__gt=window_start_utc,
    )
    if exclude_request_id:
        active_reqs = active_reqs.exclude(pk=exclude_request_id)
    for r in active_reqs:
        if r.selected_slot_start and r.selected_slot_end:
            busy.append((
                r.selected_slot_start.astimezone(_dt_tz.utc),
                r.selected_slot_end.astimezone(_dt_tz.utc),
                r.purpose or "Scheduled WhatsApp Meeting",
            ))
    return busy


def _suggest_alternative_slots(
    *,
    busy_intervals: list,
    requested_local_dt: datetime,
    duration_minutes: int,
    tz_name: str,
    count: int = 4,
) -> List[Dict[str, Any]]:
    """Find up to `count` future non-overlapping slots of length `duration_minutes`."""
    from datetime import timezone as _dt_tz

    tz = ZoneInfo(tz_name or "UTC")
    now_utc = dj_timezone.now().astimezone(_dt_tz.utc)
    suggestions: List[Dict[str, Any]] = []
    seen_starts = set()

    req_utc = requested_local_dt.astimezone(_dt_tz.utc)
    base_date = requested_local_dt.date()

    candidate_local_starts: List[datetime] = []
    for hour in range(9, 19):
        for minute in (0, 30):
            cand = datetime.combine(base_date, time(hour, minute), tzinfo=tz)
            if cand != requested_local_dt and cand.hour * 60 + cand.minute >= requested_local_dt.hour * 60 + requested_local_dt.minute:
                candidate_local_starts.append(cand)
    for hour in range(9, 19):
        for minute in (0, 30):
            cand = datetime.combine(base_date, time(hour, minute), tzinfo=tz)
            if cand != requested_local_dt and cand not in candidate_local_starts:
                candidate_local_starts.append(cand)
    for day_offset in range(1, 4):
        d = base_date + timedelta(days=day_offset)
        for hour in range(9, 18):
            for minute in (0, 30):
                candidate_local_starts.append(datetime.combine(d, time(hour, minute), tzinfo=tz))

    for cand_local in candidate_local_starts:
        cand_start_utc = cand_local.astimezone(_dt_tz.utc)
        cand_end_utc = cand_start_utc + timedelta(minutes=duration_minutes)
        if cand_start_utc <= now_utc + timedelta(minutes=5):
            continue
        if cand_start_utc == req_utc or cand_start_utc in seen_starts:
            continue
        has_conflict = any(
            cal.intervals_overlap(cand_start_utc, cand_end_utc, b[0], b[1])
            for b in busy_intervals
        )
        if not has_conflict:
            seen_starts.add(cand_start_utc)
            end_local = cand_local + timedelta(minutes=duration_minutes)
            suggestions.append({
                "index": len(suggestions) + 1,
                "date": cand_local.date().isoformat(),
                "time": cand_local.strftime("%H:%M"),
                "end_time": end_local.strftime("%H:%M"),
                "timezone": tz_name,
                "label": f"{cand_local.date().isoformat()} at {cand_local.strftime('%H:%M')} - {end_local.strftime('%H:%M')} ({tz_name})",
                "start_utc": cand_start_utc.isoformat(),
                "end_utc": cand_end_utc.isoformat(),
            })
            if len(suggestions) >= count:
                break
    return suggestions


def _evaluate_owner_slot_availability(
    owner,
    *,
    platform: str,
    local_start_dt: datetime,
    duration_minutes: int,
    tz_name: str,
    exclude_request_id=None,
) -> Dict[str, Any]:
    """
    Strictly check `owner`'s connected provider + calendars + CRM meetings for `[start, start+duration)`.
    Never falls back to any other user's credentials.
    """
    from datetime import timezone as _dt_tz

    if not owner:
        return {
            "status": "MISSING_CREDENTIALS",
            "message": "This WhatsApp session has no authenticated owner account configured for scheduling.",
            "alternatives": [],
            "busy_intervals": [],
        }

    utc_start = local_start_dt.astimezone(_dt_tz.utc)
    utc_end = utc_start + timedelta(minutes=duration_minutes)
    if utc_start <= dj_timezone.now().astimezone(_dt_tz.utc) - timedelta(minutes=2):
        return {
            "status": "PAST_SLOT",
            "message": (
                f"The requested time ({local_start_dt.date().isoformat()} at {local_start_dt.strftime('%H:%M')} {tz_name}) "
                "is in the past. Please share a future date and time."
            ),
            "alternatives": [],
            "busy_intervals": [],
        }

    owner_creds = _resolve_owner_platforms(owner)
    g_creds = owner_creds["google"]
    ms_creds = owner_creds["microsoft"]
    z_creds = owner_creds["zoom"]

    def _other_connected_hint(excluded_platform: str) -> str:
        alts = []
        if excluded_platform != "ZOOM" and z_creds:
            alts.append("*Zoom*")
        if excluded_platform != "GOOGLE_MEET" and g_creds:
            alts.append("*Google Meet*")
        if excluded_platform != "MS_TEAMS" and ms_creds:
            alts.append("*Microsoft Teams*")
        if alts:
            return f" Would you like me to check availability on {' or '.join(alts)} instead?"
        return ""

    if platform == "GOOGLE_MEET" and not g_creds:
        return {
            "status": "MISSING_CREDENTIALS",
            "message": (
                f"{owner.get_full_name() or owner.username}'s Google Calendar account is not connected, "
                "so I cannot check availability or generate a Google Meet link right now."
                + _other_connected_hint("GOOGLE_MEET")
            ),
            "alternatives": [],
            "busy_intervals": [],
        }
    if platform == "MS_TEAMS" and not ms_creds:
        return {
            "status": "MISSING_CREDENTIALS",
            "message": (
                f"{owner.get_full_name() or owner.username}'s Microsoft Outlook / Teams account is not connected, "
                "so I cannot check availability or generate a Teams meeting link right now."
                + _other_connected_hint("MS_TEAMS")
            ),
            "alternatives": [],
            "busy_intervals": [],
        }
    if platform == "ZOOM" and not z_creds:
        return {
            "status": "MISSING_CREDENTIALS",
            "message": (
                f"{owner.get_full_name() or owner.username}'s Zoom account is not connected, "
                "so I cannot generate a Zoom meeting link right now."
                + _other_connected_hint("ZOOM")
            ),
            "alternatives": [],
            "busy_intervals": [],
        }

    win_min = utc_start - timedelta(hours=14)
    win_max = utc_start + timedelta(days=4)
    all_busy = _collect_owner_local_busy_intervals(
        owner,
        win_min,
        win_max,
        exclude_request_id=exclude_request_id,
    )

    try:
        if platform == "GOOGLE_MEET":
            g_res = cal.check_availability(g_creds, utc_start, utc_end, tz_name=tz_name)
            all_busy.extend(g_res["busy_intervals"])
        elif platform == "MS_TEAMS":
            m_res = ms.check_ms_availability(ms_creds, utc_start, utc_end, tz_name=tz_name)
            all_busy.extend(m_res["busy_intervals"])
        elif platform == "ZOOM":
            z_res = zoom.check_zoom_availability(z_creds, utc_start, utc_end)
            all_busy.extend(z_res["busy_intervals"])
            if g_creds:
                g_res = cal.check_availability(g_creds, utc_start, utc_end, tz_name=tz_name)
                all_busy.extend(g_res["busy_intervals"])
            elif ms_creds:
                m_res = ms.check_ms_availability(ms_creds, utc_start, utc_end, tz_name=tz_name)
                all_busy.extend(m_res["busy_intervals"])
    except (cal.CalendarAuthError, ms.MicrosoftAuthError, zoom.ZoomAuthError) as auth_exc:
        return {
            "status": "AUTH_REVOKED",
            "message": (
                f"{_platform_label(platform)} authorization for {owner.get_full_name() or owner.username} "
                f"has expired or been revoked ({auth_exc}). Please ask the executive to reconnect their calendar/meeting account."
            ),
            "alternatives": [],
            "busy_intervals": [],
        }
    except (cal.CalendarAPIError, ms.MicrosoftAPIError, zoom.ZoomAPIError, Exception) as api_exc:
        logger.warning("Availability check provider failure for owner %s (%s): %s", owner.pk, platform, api_exc)
        return {
            "status": "PROVIDER_ERROR",
            "message": (
                f"I'm temporarily unable to verify calendar availability on {_platform_label(platform)} right now. "
                "Could you please try again in a moment, or reply with another preferred time?"
            ),
            "alternatives": [],
            "busy_intervals": [],
        }

    conflicts = [b for b in all_busy if cal.intervals_overlap(utc_start, utc_end, b[0], b[1])]
    if conflicts:
        alternatives = _suggest_alternative_slots(
            busy_intervals=all_busy,
            requested_local_dt=local_start_dt,
            duration_minutes=duration_minutes,
            tz_name=tz_name,
            count=4,
        )
        return {
            "status": "UNAVAILABLE",
            "message": "Requested time overlaps with an existing calendar commitment.",
            "alternatives": alternatives,
            "busy_intervals": all_busy,
        }

    return {
        "status": "AVAILABLE",
        "message": "",
        "alternatives": [],
        "busy_intervals": all_busy,
    }


def _get_or_create_meeting_request(
    *,
    owner,
    session,
    conversation,
    incoming,
    state_data: dict,
) -> Optional[WhatsAppMeetingRequest]:
    if not owner:
        return None
    req_id = state_data.get("meeting_request_id")
    req = None
    if req_id:
        req = WhatsAppMeetingRequest.objects.filter(pk=req_id, conversation=conversation, user=owner).first()
    if req is None:
        idemp_key = f"wamr:{conversation.id.hex[:20]}:{incoming.id.hex[:20]}"
        req, _ = WhatsAppMeetingRequest.objects.get_or_create(
            idempotency_key=idemp_key,
            defaults={
                "user": owner,
                "session": session,
                "conversation": conversation,
                "source_message": incoming,
                "state": WhatsAppMeetingRequest.State.COLLECTING_DETAILS,
                "expires_at": dj_timezone.now() + timedelta(days=2),
            },
        )
        state_data["meeting_request_id"] = str(req.id)
    return req


def _sync_meeting_request_fields(
    req: Optional[WhatsAppMeetingRequest],
    state_data: dict,
    *,
    req_state: str,
    calendar_provider: str = "",
    failure_reason: str = "",
):
    if not req:
        return
    d_val = None
    t_val = None
    start_utc = None
    end_utc = None
    dur = int(state_data.get("duration_minutes") or getattr(settings, "MEETING_DEFAULT_DURATION_MINUTES", 30) or 30)
    tz_name = state_data.get("timezone") or "UTC"
    if state_data.get("date"):
        try:
            d_val = date.fromisoformat(state_data["date"])
        except ValueError:
            d_val = None
    if state_data.get("time"):
        try:
            parts = [int(p) for p in state_data["time"].split(":")]
            t_val = time(parts[0], parts[1])
        except Exception:
            t_val = None
    if d_val and t_val:
        try:
            tz_obj = ZoneInfo(tz_name)
        except Exception:
            tz_obj = ZoneInfo("UTC")
        local_dt = datetime.combine(d_val, t_val, tzinfo=tz_obj)
        start_utc = local_dt.astimezone(ZoneInfo("UTC"))
        end_utc = start_utc + timedelta(minutes=dur)

    req.requested_date = d_val
    req.requested_time = t_val
    req.duration_minutes = dur
    req.timezone = tz_name
    req.purpose = (state_data.get("topic") or "")[:255]
    req.platform = state_data.get("platform") or ""
    if calendar_provider:
        req.calendar_provider = calendar_provider
    req.attendee_email = (state_data.get("email") or "")[:254]
    req.selected_slot_start = start_utc
    req.selected_slot_end = end_utc
    req.suggested_slots = state_data.get("suggested_slots") or []
    req.state = req_state
    if failure_reason:
        req.failure_reason = failure_reason[:1000]
    req.save()


def _book_confirmed_meeting(
    *,
    session,
    conversation,
    state_data: dict,
    sender_name: str,
    sender_phone: str,
    meeting_request: Optional[WhatsAppMeetingRequest] = None,
) -> Tuple[Optional[Meeting], Optional[str], Optional[Dict[str, Any]]]:
    """
    Revalidate availability under a concurrency lock, create the meeting strictly using
    `session.owner`'s credentials (Google Meet, MS Teams, or Zoom), verify the returned link,
    and persist the CRM Meeting + WhatsAppMeetingRequest idempotently.
    Returns (Meeting, error_reply_message_if_failed, conflict_payload_if_slot_taken).
    """
    owner = _resolve_session_owner(session)
    if not owner:
        return (
            None,
            "This WhatsApp account does not have an active authenticated owner configured to schedule meetings.",
            None,
        )

    date_str = state_data.get("date")
    time_str = state_data.get("time")
    tz_name = state_data.get("timezone") or "UTC"
    platform = state_data.get("platform") or "GOOGLE_MEET"
    duration = int(state_data.get("duration_minutes") or getattr(settings, "MEETING_DEFAULT_DURATION_MINUTES", 30) or 30)
    sender_email = (state_data.get("email") or "").strip()
    topic = (state_data.get("topic") or "").strip()
    mentioned_company = (state_data.get("company_name") or "").strip()

    prospect, contact = _resolve_conv_crm(
        conversation,
        sender_phone=sender_phone,
        email=sender_email,
        sender_name=sender_name,
        owner=owner,
    )
    if prospect is None and mentioned_company:
        prospect = Prospect.objects.filter(
            company_name__iexact=mentioned_company,
            created_by=owner.username,
        ).first()

    if not sender_email and contact and contact.official_email:
        sender_email = contact.official_email.strip()
    elif not sender_email and prospect and prospect.official_email_address:
        sender_email = prospect.official_email_address.strip()

    company_display = prospect.company_name if prospect else (mentioned_company or sender_name or sender_phone or "WhatsApp Contact")

    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz_name = "UTC"
        tz = ZoneInfo("UTC")

    d_val = date.fromisoformat(date_str)
    t_parts = [int(p) for p in time_str.split(":")]
    t_val = time(t_parts[0], t_parts[1])
    local_dt = datetime.combine(d_val, t_val, tzinfo=tz)
    utc_dt = local_dt.astimezone(ZoneInfo("UTC"))
    utc_end = utc_dt + timedelta(minutes=duration)

    with transaction.atomic():
        if meeting_request:
            meeting_request = WhatsAppMeetingRequest.objects.select_for_update().get(pk=meeting_request.pk)
            if (
                meeting_request.state == WhatsAppMeetingRequest.State.SCHEDULED
                and meeting_request.meeting_id
                and _is_valid_meeting_link(meeting_request.meeting_link)
            ):
                return meeting_request.meeting, None, None

        overlapping_lock = WhatsAppMeetingRequest.objects.select_for_update().filter(
            user=owner,
            state__in=[
                WhatsAppMeetingRequest.State.REVALIDATING_SLOT,
                WhatsAppMeetingRequest.State.CREATING_MEETING,
                WhatsAppMeetingRequest.State.SCHEDULED,
            ],
            selected_slot_start__lt=utc_end,
            selected_slot_end__gt=utc_dt,
        )
        if meeting_request:
            overlapping_lock = overlapping_lock.exclude(pk=meeting_request.pk)
        if overlapping_lock.exists():
            avail = _evaluate_owner_slot_availability(
                owner,
                platform=platform,
                local_start_dt=local_dt,
                duration_minutes=duration,
                tz_name=tz_name,
                exclude_request_id=meeting_request.pk if meeting_request else None,
            )
            return None, None, avail

        if meeting_request:
            meeting_request.state = WhatsAppMeetingRequest.State.REVALIDATING_SLOT
            meeting_request.selected_slot_start = utc_dt
            meeting_request.selected_slot_end = utc_end
            meeting_request.save(update_fields=["state", "selected_slot_start", "selected_slot_end", "updated_at"])

    avail = _evaluate_owner_slot_availability(
        owner,
        platform=platform,
        local_start_dt=local_dt,
        duration_minutes=duration,
        tz_name=tz_name,
        exclude_request_id=meeting_request.pk if meeting_request else None,
    )
    if avail["status"] in ("MISSING_CREDENTIALS", "AUTH_REVOKED"):
        if meeting_request:
            _sync_meeting_request_fields(
                meeting_request,
                state_data,
                req_state=WhatsAppMeetingRequest.State.REQUIRES_RECONNECTION,
                failure_reason=avail["message"],
            )
        return None, avail["message"], None
    if avail["status"] in ("UNAVAILABLE", "PAST_SLOT"):
        return None, avail["message"], avail
    if avail["status"] == "PROVIDER_ERROR":
        if meeting_request:
            _sync_meeting_request_fields(
                meeting_request,
                state_data,
                req_state=WhatsAppMeetingRequest.State.FAILED,
                failure_reason=avail["message"],
            )
        return None, avail["message"], None

    if meeting_request:
        meeting_request.state = WhatsAppMeetingRequest.State.CREATING_MEETING
        meeting_request.save(update_fields=["state", "updated_at"])

    req_hex = meeting_request.id.hex[:16] if meeting_request else conversation.id.hex[:16]
    client_request_id = f"wa_{conversation.id.hex[:16]}_{req_hex}"

    existing_meeting = Meeting.objects.filter(client_request_id=client_request_id).first()
    if existing_meeting and _is_valid_meeting_link(existing_meeting.meeting_link):
        if meeting_request:
            meeting_request.meeting = existing_meeting
            meeting_request.meeting_link = existing_meeting.meeting_link
            meeting_request.state = WhatsAppMeetingRequest.State.SCHEDULED
            meeting_request.save(update_fields=["meeting", "meeting_link", "state", "updated_at"])
        return existing_meeting, None, None

    summary = f"Meeting with {company_display}" + (f" ({sender_name})" if sender_name and sender_name != company_display else "")
    agenda_lines = [
        topic or "Scheduled via WhatsApp AI Assistant",
        f"Duration: {duration} minutes",
        f"Sender: {sender_name or 'WhatsApp Contact'} ({sender_phone or 'N/A'})",
    ]
    if sender_email:
        agenda_lines.append(f"Email: {sender_email}")
    if company_display:
        agenda_lines.append(f"Company: {company_display}")
    description = "\n".join(agenda_lines)
    attendees = [sender_email] if sender_email else []

    owner_creds = _resolve_owner_platforms(owner)
    g_creds = owner_creds["google"]
    ms_creds = owner_creds["microsoft"]
    z_creds = owner_creds["zoom"]

    if platform == "ZOOM":
        if not z_creds:
            return (
                None,
                f"{owner.get_full_name() or owner.username}'s Zoom account is not connected. "
                f"Please pick another option: {_available_platform_choices_text(owner)}.",
                None,
            )
        try:
            z_res = zoom.create_zoom_meeting(
                z_creds,
                summary=summary,
                description=description,
                start_dt=utc_dt,
                tz_name=tz_name,
                duration_minutes=duration,
            )
        except Exception as exc:
            logger.exception("WhatsApp Zoom meeting creation failed: %s", exc)
            if meeting_request:
                _sync_meeting_request_fields(
                    meeting_request,
                    state_data,
                    req_state=WhatsAppMeetingRequest.State.FAILED,
                    failure_reason=str(exc),
                )
            return (
                None,
                f"I ran into an issue generating the Zoom link ({exc}). Would you like to try another platform ({_available_platform_choices_text(owner)})?",
                None,
            )

        join_url = (z_res.get("join_url") or "").strip()
        if not _is_valid_meeting_link(join_url):
            if z_res.get("meeting_id"):
                zoom.delete_zoom_meeting(z_creds, str(z_res["meeting_id"]))
            if meeting_request:
                _sync_meeting_request_fields(
                    meeting_request,
                    state_data,
                    req_state=WhatsAppMeetingRequest.State.FAILED,
                    failure_reason="Zoom returned an empty or invalid join URL.",
                )
            return None, "Zoom did not return a valid meeting link. Please try again shortly.", None

        cal_event_id = ""
        cal_type = ""
        if g_creds:
            try:
                cal_event_id = cal.deterministic_event_id(owner.id, client_request_id)
                end_local = local_dt + timedelta(minutes=duration)
                cal_body = {
                    "id": cal_event_id,
                    "summary": f"{summary} (Zoom)",
                    "description": f"{description}\n\nZoom Link: {join_url}",
                    "location": join_url,
                    "start": {"dateTime": local_dt.isoformat(), "timeZone": tz_name},
                    "end": {"dateTime": end_local.isoformat(), "timeZone": tz_name},
                }
                if attendees:
                    cal_body["attendees"] = [{"email": a} for a in attendees]
                cal._api_request(
                    g_creds,
                    "POST",
                    "/calendars/primary/events",
                    body=cal_body,
                    params={"sendUpdates": "all" if attendees else "none"},
                )
                cal_type = "GOOGLE_CALENDAR"
            except Exception as exc:
                logger.warning("Failed syncing WhatsApp Zoom meeting to Google Calendar: %s", exc)
                cal_event_id = ""
        elif ms_creds:
            try:
                cal_event_id = ms.create_outlook_event_for_zoom(
                    ms_creds,
                    summary=summary,
                    description=description,
                    start_dt=utc_dt,
                    tz_name=tz_name,
                    attendees=attendees,
                    zoom_join_url=join_url,
                    duration_minutes=duration,
                ) or ""
                if cal_event_id:
                    cal_type = "OUTLOOK_CALENDAR"
            except Exception as exc:
                logger.warning("Failed syncing WhatsApp Zoom meeting to Outlook Calendar: %s", exc)
                cal_event_id = ""

        meeting = Meeting.objects.create(
            prospect=prospect,
            prospect_contact=contact,
            scheduled_datetime=utc_dt,
            meeting_date=local_dt.date(),
            meeting_time=local_dt.time(),
            timezone=tz_name,
            meeting_link=join_url,
            agenda=description,
            meeting_provider="ZOOM",
            provider_meeting_id=str(z_res.get("meeting_id") or ""),
            google_event_id=cal_event_id if cal_type == "GOOGLE_CALENDAR" else "",
            calendar_event_id=cal_event_id or str(z_res.get("meeting_id") or ""),
            calendar_type=cal_type,
            google_calendar_owner=owner if cal_type == "GOOGLE_CALENDAR" else None,
            created_by=owner,
            status="SCHEDULED",
            conference_status="READY",
            client_request_id=client_request_id,
        )
        if meeting_request:
            meeting_request.meeting = meeting
            meeting_request.meeting_link = join_url
            meeting_request.external_event_id = cal_event_id or str(z_res.get("meeting_id") or "")
            meeting_request.calendar_provider = cal_type or "ZOOM"
            meeting_request.state = WhatsAppMeetingRequest.State.SCHEDULED
            meeting_request.failure_reason = ""
            meeting_request.save()
        return meeting, None, None

    if platform == "MS_TEAMS":
        if not ms_creds:
            return (
                None,
                f"{owner.get_full_name() or owner.username}'s Microsoft Outlook / Teams account is not connected.",
                None,
            )
        try:
            m_res = ms.create_teams_meeting_and_event(
                ms_creds,
                summary=summary,
                description=description,
                start_dt=utc_dt,
                tz_name=tz_name,
                attendees=attendees,
                duration_minutes=duration,
            )
        except Exception as exc:
            logger.exception("WhatsApp MS Teams meeting creation failed: %s", exc)
            if meeting_request:
                _sync_meeting_request_fields(
                    meeting_request,
                    state_data,
                    req_state=WhatsAppMeetingRequest.State.FAILED,
                    failure_reason=str(exc),
                )
            return (
                None,
                f"I ran into an issue generating the Microsoft Teams link ({exc}). Would you like to try another platform ({_available_platform_choices_text(owner)})?",
                None,
            )

        join_url = (m_res.get("join_url") or "").strip()
        if not _is_valid_meeting_link(join_url):
            if m_res.get("event_id"):
                ms.delete_outlook_event(ms_creds, m_res["event_id"])
            if meeting_request:
                _sync_meeting_request_fields(
                    meeting_request,
                    state_data,
                    req_state=WhatsAppMeetingRequest.State.FAILED,
                    failure_reason="Microsoft Teams did not return a valid join URL.",
                )
            return None, "Microsoft Teams did not return a valid meeting link. Please try again.", None

        meeting = Meeting.objects.create(
            prospect=prospect,
            prospect_contact=contact,
            scheduled_datetime=utc_dt,
            meeting_date=local_dt.date(),
            meeting_time=local_dt.time(),
            timezone=tz_name,
            meeting_link=join_url,
            agenda=description,
            meeting_provider="MS_TEAMS",
            provider_meeting_id=str(m_res.get("meeting_id") or ""),
            calendar_event_id=m_res.get("event_id") or "",
            calendar_type="OUTLOOK_CALENDAR",
            created_by=owner,
            status="SCHEDULED",
            conference_status="READY",
            client_request_id=client_request_id,
        )
        if meeting_request:
            meeting_request.meeting = meeting
            meeting_request.meeting_link = join_url
            meeting_request.external_event_id = m_res.get("event_id") or ""
            meeting_request.calendar_provider = "OUTLOOK_CALENDAR"
            meeting_request.state = WhatsAppMeetingRequest.State.SCHEDULED
            meeting_request.failure_reason = ""
            meeting_request.save()
        return meeting, None, None

    # Default / GOOGLE_MEET (strictly using session.owner's Google Calendar credentials)
    if not g_creds:
        return (
            None,
            f"{owner.get_full_name() or owner.username}'s Google Calendar is not connected, "
            "so I couldn't generate a Google Meet link right now. Please contact our executive team directly for assistance.",
            None,
        )

    try:
        g_res = cal.create_meet_event(
            g_creds,
            summary=summary,
            description=description,
            start_dt=utc_dt,
            tz_name=tz_name,
            attendees=attendees,
            client_request_id=client_request_id,
            duration_minutes=duration,
        )
    except Exception as exc:
        logger.exception("WhatsApp Google Meet creation failed: %s", exc)
        if meeting_request:
            _sync_meeting_request_fields(
                meeting_request,
                state_data,
                req_state=WhatsAppMeetingRequest.State.FAILED,
                failure_reason=str(exc),
            )
        return (
            None,
            f"I ran into an issue generating the Google Meet link ({exc}). Would you like me to try again or switch to another platform ({_available_platform_choices_text(owner)})?",
            None,
        )

    meet_url = (g_res.get("meet_url") or "").strip()
    if not _is_valid_meeting_link(meet_url):
        if g_res.get("event_id"):
            cal.delete_event(g_creds, g_res["event_id"])
        if meeting_request:
            _sync_meeting_request_fields(
                meeting_request,
                state_data,
                req_state=WhatsAppMeetingRequest.State.FAILED,
                failure_reason="Google Calendar did not return a valid Google Meet link.",
            )
        return None, "Google Calendar did not return a valid Google Meet link yet. Please try again in a moment.", None

    meeting = Meeting.objects.create(
        prospect=prospect,
        prospect_contact=contact,
        scheduled_datetime=utc_dt,
        meeting_date=local_dt.date(),
        meeting_time=local_dt.time(),
        timezone=tz_name,
        meeting_link=meet_url,
        agenda=description,
        meeting_provider="GOOGLE_MEET",
        google_event_id=g_res.get("event_id") or "",
        calendar_event_id=g_res.get("event_id") or "",
        calendar_type="GOOGLE_CALENDAR",
        google_calendar_owner=owner,
        created_by=owner,
        status="SCHEDULED" if g_res.get("status") == "READY" else "PENDING",
        conference_status=g_res.get("status") or "READY",
        client_request_id=client_request_id,
    )
    if meeting_request:
        meeting_request.meeting = meeting
        meeting_request.meeting_link = meet_url
        meeting_request.external_event_id = g_res.get("event_id") or ""
        meeting_request.calendar_provider = "GOOGLE_CALENDAR"
        meeting_request.state = WhatsAppMeetingRequest.State.SCHEDULED
        meeting_request.failure_reason = ""
        meeting_request.save()
    return meeting, None, None


def _format_alternatives_reply(
    *,
    requested_date: str,
    requested_time: str,
    tz_name: str,
    duration_minutes: int,
    alternatives: List[Dict[str, Any]],
) -> str:
    if not alternatives:
        return (
            f"The requested slot (*{requested_date} at {requested_time} {tz_name}*, {duration_minutes} mins) "
            "is unavailable due to an existing calendar conflict, and no open slots were found in the next few days. "
            "Could you please suggest another date or time?"
        )
    lines = [
        f"That time slot (*{requested_date} at {requested_time} {tz_name}*, {duration_minutes} mins) is currently unavailable on the calendar.",
        "Here are the next available time slots:",
        "",
    ]
    for alt in alternatives:
        lines.append(f"{alt['index']}. {alt['label']}")
    lines.append("")
    lines.append("Please reply with an option number (e.g., *1* or *2*) or suggest another preferred date/time.")
    return "\n".join(lines)


def _next_scheduling_prompt(
    state_data: dict,
    *,
    owner=None,
    meeting_request: Optional[WhatsAppMeetingRequest] = None,
    company_hint: str = "",
    email_hint: str = "",
) -> Tuple[str, str]:
    """
    Determine the next question, run availability checks when slot & platform are ready,
    or present the final confirmation summary.
    Returns (reply_text, req_state).
    """
    d_str = state_data.get("date")
    t_str = state_data.get("time")
    tz_str = state_data.get("timezone")
    plat = state_data.get("platform")
    dur = int(state_data.get("duration_minutes") or getattr(settings, "MEETING_DEFAULT_DURATION_MINUTES", 30) or 30)

    if not d_str or not t_str:
        if d_str and not t_str:
            return (
                f"Got your preferred date ({d_str}). What *time* (and *time zone*, e.g. IST, EST, UTC, Asia/Kolkata) works best for you?",
                WhatsAppMeetingRequest.State.COLLECTING_DETAILS,
            )
        if t_str and not d_str:
            return (
                f"Got your preferred time ({t_str}). Which *date* (and *time zone*, e.g. IST, EST, UTC, Asia/Kolkata) would you like?",
                WhatsAppMeetingRequest.State.COLLECTING_DETAILS,
            )
        return (
            "I would be happy to schedule a meeting for you! "
            "Could you please share your preferred *date* and *time* "
            "(for example, tomorrow at 3:00 PM or 2026-11-25 at 10:30 AM)?",
            WhatsAppMeetingRequest.State.COLLECTING_DETAILS,
        )

    if not tz_str:
        return (
            f"Thanks! I have *{d_str} at {t_str}*. "
            "Which *time zone* are you in (e.g., IST / Asia/Kolkata, EST / America/New_York, UTC, GMT+4)?",
            WhatsAppMeetingRequest.State.COLLECTING_DETAILS,
        )

    effective_email = state_data.get("email") or email_hint

    # If user already gave date, time, timezone, AND platform, verify slot availability
    # BEFORE asking optional agenda/email details so we never ask details for a busy/unconnected slot.
    if plat:
        try:
            tz = ZoneInfo(tz_str)
        except Exception:
            tz_str = "UTC"
            tz = ZoneInfo("UTC")
        d_val = date.fromisoformat(d_str)
        t_parts = [int(p) for p in t_str.split(":")]
        local_dt = datetime.combine(d_val, time(t_parts[0], t_parts[1]), tzinfo=tz)

        avail = _evaluate_owner_slot_availability(
            owner,
            platform=plat,
            local_start_dt=local_dt,
            duration_minutes=dur,
            tz_name=tz_str,
            exclude_request_id=meeting_request.pk if meeting_request else None,
        )

        if avail["status"] in ("MISSING_CREDENTIALS", "AUTH_REVOKED"):
            state_data["platform"] = None
            state_data["awaiting_confirmation"] = False
            return avail["message"], WhatsAppMeetingRequest.State.REQUIRES_RECONNECTION

        if avail["status"] == "PAST_SLOT":
            state_data["date"] = None
            state_data["time"] = None
            state_data["awaiting_confirmation"] = False
            return avail["message"], WhatsAppMeetingRequest.State.COLLECTING_DETAILS

        if avail["status"] == "PROVIDER_ERROR":
            state_data["awaiting_confirmation"] = False
            return avail["message"], WhatsAppMeetingRequest.State.FAILED

        if avail["status"] == "UNAVAILABLE":
            state_data["awaiting_confirmation"] = False
            state_data["awaiting_alternative_selection"] = True
            state_data["suggested_slots"] = avail["alternatives"]
            return (
                _format_alternatives_reply(
                    requested_date=d_str,
                    requested_time=t_str,
                    tz_name=tz_str,
                    duration_minutes=dur,
                    alternatives=avail["alternatives"],
                ),
                WhatsAppMeetingRequest.State.AWAITING_ALTERNATIVE_SELECTION,
            )

    if not state_data.get("details_collected") and (not state_data.get("topic") or not effective_email):
        state_data["awaiting_details"] = True
        missing_parts = []
        if not effective_email:
            missing_parts.append("your *email address* for the invite")
        if not state_data.get("topic"):
            missing_parts.append("the *meeting topic / agenda*")
        if not company_hint and not state_data.get("company_name"):
            missing_parts.append("your *company name*")
        joined = " and ".join(missing_parts) if len(missing_parts) <= 2 else ", ".join(missing_parts[:-1]) + ", and " + missing_parts[-1]
        return (
            f"Noted: *{d_str} at {t_str} ({tz_str})*. "
            f"Could you also share {joined}? (You can reply _skip_ if you prefer.)",
            WhatsAppMeetingRequest.State.COLLECTING_DETAILS,
        )

    if not plat:
        choices_text = _available_platform_choices_text(owner)
        return (
            f"Which meeting platform do you prefer — {choices_text}?",
            WhatsAppMeetingRequest.State.COLLECTING_DETAILS,
        )

    # Slot is AVAILABLE and details are collected! Ready for final confirmation.
    state_data["awaiting_alternative_selection"] = False
    state_data["suggested_slots"] = []
    state_data["awaiting_confirmation"] = True
    end_local = local_dt + timedelta(minutes=dur)
    platform_label = _platform_label(plat)
    topic_label = state_data.get("topic") or "Business Discussion"
    lines = [
        "Please confirm your meeting details (this slot is available):",
        f"- Date: {d_str}",
        f"- Time: {t_str} - {end_local.strftime('%H:%M')} ({tz_str}, {dur} mins)",
        f"- Platform: {platform_label}",
        f"- Topic: {topic_label}",
    ]
    if effective_email:
        lines.append(f"- Email: {effective_email}")
    lines.append("")
    lines.append("Reply *Yes* or *Confirm* to schedule the meeting and generate your meeting link.")
    return "\n".join(lines), WhatsAppMeetingRequest.State.AWAITING_CONFIRMATION


def handle_pre_rag_assistant_workflow(
    *,
    session,
    conversation,
    incoming,
    sender_name: str = "",
    sender_phone: str = "",
    model_name: str = "",
) -> AssistantWorkflowOutcome:
    """
    Intercepts multi-turn AI Assistant workflows BEFORE Vector DB RAG / Gemini:
      1. Confirmed WhatsApp escalations awaiting user Yes/No
      2. Active WhatsApp meeting scheduling conversations OR newly detected scheduling intent
    """
    text = _msg_text(incoming)
    if not text:
        return AssistantWorkflowOutcome(handled=False)

    state = WhatsAppAssistantState.objects.filter(conversation=conversation).first()

    # 1. Pending escalation confirmation from an earlier Vector DB refusal
    if state and state.mode == WhatsAppAssistantState.Mode.ESCALATION_CONFIRMATION:
        if is_affirmative_reply(text):
            extracted_email = _extract_email_deterministic(text) or ""
            owner = _resolve_session_owner(session)
            prospect, contact = _resolve_conv_crm(
                conversation,
                sender_phone=sender_phone,
                email=extracted_email,
                sender_name=sender_name,
                owner=owner,
            )
            orig_msg_id = (state.state_data or {}).get("incoming_message_id") or str(incoming.id)
            source_key = f"wa_escalation:{conversation.id}:{orig_msg_id}"
            pre_task = create_whatsapp_escalation_pre_task(
                session=session,
                conversation=conversation,
                original_query=state.pending_query or text,
                sender_name=sender_name,
                sender_phone=sender_phone,
                sender_email=extracted_email,
                prospect=prospect,
                prospect_contact=contact,
                source_key=source_key,
                extra_metadata={
                    "confirmed_at_message_id": str(incoming.id),
                    "confirmation_text": text,
                },
            )
            state.reset()
            exec_label = (
                pre_task.assigned_pre.username
                if pre_task.assigned_pre
                else "our concerned executive"
            )
            return AssistantWorkflowOutcome(
                handled=True,
                reply_text=(
                    f"Thank you! I have forwarded your query and contact details to {exec_label}. "
                    "Our executive will review your details and reach out to you shortly."
                ),
                model_used="assistant:escalation_confirmed",
            )

        if is_negative_or_cancel_reply(text):
            state.reset()
            return AssistantWorkflowOutcome(
                handled=True,
                reply_text=(
                    "Understood — I have not forwarded your details. "
                    "Feel free to ask any other business question if I can help!"
                ),
                model_used="assistant:escalation_declined",
            )

        # Sender pivoted cleanly to a new question or meeting request
        state.reset()

    # 2. Meeting scheduling workflow (active OR new scheduling intent)
    in_meeting_flow = bool(state and state.mode == WhatsAppAssistantState.Mode.MEETING_SCHEDULING)
    if in_meeting_flow or is_meeting_scheduling_intent(text):
        owner = _resolve_session_owner(session)
        if not owner:
            if state:
                state.reset()
            return AssistantWorkflowOutcome(
                handled=True,
                reply_text=(
                    "I cannot schedule a meeting automatically because this WhatsApp account does not have "
                    "an active authenticated owner configured. Please contact our team directly."
                ),
                model_used="assistant:meeting_no_owner",
            )

        if state is None:
            state = WhatsAppAssistantState.objects.create(
                conversation=conversation,
                session=session,
                mode=WhatsAppAssistantState.Mode.MEETING_SCHEDULING,
                state_data={},
            )
        elif state.mode != WhatsAppAssistantState.Mode.MEETING_SCHEDULING:
            state.mode = WhatsAppAssistantState.Mode.MEETING_SCHEDULING
            state.pending_query = ""
            state.state_data = {}

        sdata = dict(state.state_data or {})
        meeting_req = _get_or_create_meeting_request(
            owner=owner,
            session=session,
            conversation=conversation,
            incoming=incoming,
            state_data=sdata,
        )

        if in_meeting_flow and is_negative_or_cancel_reply(text):
            _sync_meeting_request_fields(
                meeting_req,
                sdata,
                req_state=WhatsAppMeetingRequest.State.CANCELLED,
            )
            state.reset()
            return AssistantWorkflowOutcome(
                handled=True,
                reply_text="No problem — I have cancelled the meeting scheduling request. Let me know if you need anything else!",
                model_used="assistant:meeting_cancelled",
            )

        prospect, contact = _resolve_conv_crm(
            conversation,
            sender_phone=sender_phone,
            email=sdata.get("email"),
            sender_name=sender_name,
            owner=owner,
        )
        known_email = (
            sdata.get("email")
            or (contact.official_email if contact and contact.official_email else "")
            or (prospect.official_email_address if prospect and prospect.official_email_address else "")
        )
        known_company = prospect.company_name if prospect else ""

        # If awaiting alternative selection from earlier conflict
        if sdata.get("awaiting_alternative_selection"):
            alts = list(sdata.get("suggested_slots") or [])
            chosen_idx = _parse_alternative_choice_index(text, len(alts))
            if chosen_idx is not None:
                chosen = alts[chosen_idx - 1]
                sdata["date"] = chosen["date"]
                sdata["time"] = chosen["time"]
                sdata["timezone"] = chosen.get("timezone") or sdata.get("timezone")
                sdata["awaiting_alternative_selection"] = False
                sdata["suggested_slots"] = []
                reply, req_state = _next_scheduling_prompt(
                    sdata,
                    owner=owner,
                    meeting_request=meeting_req,
                    company_hint=known_company,
                    email_hint=known_email,
                )
                _sync_meeting_request_fields(meeting_req, sdata, req_state=req_state)
                state.mode = WhatsAppAssistantState.Mode.MEETING_SCHEDULING
                state.state_data = sdata
                state.last_incoming_message_id = str(incoming.id)
                state.save(update_fields=["mode", "state_data", "last_incoming_message_id", "updated_at"])
                return AssistantWorkflowOutcome(
                    handled=True,
                    reply_text=reply,
                    model_used="assistant:meeting_alternative_selected",
                    meeting_request_id=str(meeting_req.id) if meeting_req else None,
                )

            # Check if user suggested a fresh date/time directly
            prev_date, prev_time = sdata.get("date"), sdata.get("time")
            updated_try = _extract_meeting_slots(text, sdata, model_name=model_name)
            if updated_try.get("date") != prev_date or updated_try.get("time") != prev_time:
                sdata = updated_try
                sdata["awaiting_alternative_selection"] = False
                sdata["suggested_slots"] = []
                reply, req_state = _next_scheduling_prompt(
                    sdata,
                    owner=owner,
                    meeting_request=meeting_req,
                    company_hint=known_company,
                    email_hint=known_email,
                )
                _sync_meeting_request_fields(meeting_req, sdata, req_state=req_state)
                state.mode = WhatsAppAssistantState.Mode.MEETING_SCHEDULING
                state.state_data = sdata
                state.last_incoming_message_id = str(incoming.id)
                state.save(update_fields=["mode", "state_data", "last_incoming_message_id", "updated_at"])
                return AssistantWorkflowOutcome(
                    handled=True,
                    reply_text=reply,
                    model_used="assistant:meeting_scheduler",
                    meeting_request_id=str(meeting_req.id) if meeting_req else None,
                )

            return AssistantWorkflowOutcome(
                handled=True,
                reply_text="Please reply with one of the numbered time slots above (e.g., *1* or *2*), or share another preferred date and time.",
                model_used="assistant:meeting_alternative_prompt",
                meeting_request_id=str(meeting_req.id) if meeting_req else None,
            )

        # If awaiting confirmation & sender confirms -> revalidate availability, book & verify link!
        if (
            sdata.get("awaiting_confirmation")
            and sdata.get("date")
            and sdata.get("time")
            and sdata.get("timezone")
            and sdata.get("platform")
            and is_affirmative_reply(text)
        ):
            meeting, err_msg, conflict_payload = _book_confirmed_meeting(
                session=session,
                conversation=conversation,
                state_data=sdata,
                sender_name=sender_name,
                sender_phone=sender_phone,
                meeting_request=meeting_req,
            )
            if conflict_payload is not None:
                dur = int(sdata.get("duration_minutes") or getattr(settings, "MEETING_DEFAULT_DURATION_MINUTES", 30) or 30)
                if conflict_payload.get("status") == "PAST_SLOT":
                    sdata["date"] = None
                    sdata["time"] = None
                    sdata["awaiting_confirmation"] = False
                    _sync_meeting_request_fields(meeting_req, sdata, req_state=WhatsAppMeetingRequest.State.COLLECTING_DETAILS)
                    reply = conflict_payload["message"]
                else:
                    alts = conflict_payload.get("alternatives") or []
                    sdata["awaiting_confirmation"] = False
                    sdata["awaiting_alternative_selection"] = True
                    sdata["suggested_slots"] = alts
                    _sync_meeting_request_fields(
                        meeting_req,
                        sdata,
                        req_state=WhatsAppMeetingRequest.State.AWAITING_ALTERNATIVE_SELECTION,
                    )
                    reply = _format_alternatives_reply(
                        requested_date=sdata["date"],
                        requested_time=sdata["time"],
                        tz_name=sdata["timezone"],
                        duration_minutes=dur,
                        alternatives=alts,
                    )
                state.state_data = sdata
                state.last_incoming_message_id = str(incoming.id)
                state.save(update_fields=["mode", "state_data", "last_incoming_message_id", "updated_at"])
                return AssistantWorkflowOutcome(
                    handled=True,
                    reply_text=reply,
                    model_used="assistant:meeting_slot_revalidation_conflict",
                    meeting_request_id=str(meeting_req.id) if meeting_req else None,
                )

            if err_msg:
                sdata["platform"] = None
                sdata["awaiting_confirmation"] = False
                state.state_data = sdata
                state.last_incoming_message_id = str(incoming.id)
                state.save(update_fields=["mode", "state_data", "last_incoming_message_id", "updated_at"])
                return AssistantWorkflowOutcome(
                    handled=True,
                    reply_text=err_msg,
                    model_used="assistant:meeting_provider_retry",
                    meeting_request_id=str(meeting_req.id) if meeting_req else None,
                )

            dur = int(sdata.get("duration_minutes") or getattr(settings, "MEETING_DEFAULT_DURATION_MINUTES", 30) or 30)
            platform_label = _platform_label(meeting.meeting_provider)
            company_label = meeting.prospect.company_name if meeting.prospect else (sdata.get("company_name") or sender_name or "Your Team")
            topic_label = sdata.get("topic") or "Business Discussion"
            local_date_str = meeting.meeting_date.isoformat() if meeting.meeting_date else sdata.get("date")
            local_time_str = meeting.meeting_time.strftime("%H:%M") if meeting.meeting_time else sdata.get("time")
            try:
                tz_obj = ZoneInfo(meeting.timezone or sdata.get("timezone") or "UTC")
                end_str = (meeting.scheduled_datetime.astimezone(tz_obj) + timedelta(minutes=dur)).strftime("%H:%M")
            except Exception:
                end_str = ""
            time_window = f"{local_time_str} - {end_str}" if end_str else local_time_str
            reply = (
                f"Your {platform_label} meeting is confirmed and added to the calendar!\n\n"
                f"- Company / Contact: {company_label}\n"
                f"- Purpose: {topic_label}\n"
                f"- Date: {local_date_str}\n"
                f"- Time: {time_window} ({meeting.timezone}, {dur} mins)\n"
                f"- Platform: {platform_label}\n"
                f"- Meeting Link: {meeting.meeting_link}\n\n"
                "We look forward to speaking with you!"
            )
            state.reset()
            return AssistantWorkflowOutcome(
                handled=True,
                reply_text=reply,
                model_used=f"assistant:meeting_booked:{meeting.meeting_provider.lower()}",
                meeting_request_id=str(meeting_req.id) if meeting_req else None,
            )

        # Extract any new slots from message and advance the conversation
        sdata = _extract_meeting_slots(text, sdata, model_name=model_name)
        reply, req_state = _next_scheduling_prompt(
            sdata,
            owner=owner,
            meeting_request=meeting_req,
            company_hint=known_company,
            email_hint=known_email,
        )
        _sync_meeting_request_fields(meeting_req, sdata, req_state=req_state)
        state.mode = WhatsAppAssistantState.Mode.MEETING_SCHEDULING
        state.state_data = sdata
        state.last_incoming_message_id = str(incoming.id)
        state.save(update_fields=["mode", "state_data", "last_incoming_message_id", "updated_at"])
        return AssistantWorkflowOutcome(
            handled=True,
            reply_text=reply,
            model_used="assistant:meeting_scheduler",
            meeting_request_id=str(meeting_req.id) if meeting_req else None,
        )

    return AssistantWorkflowOutcome(handled=False)


def handle_post_rag_refusal(
    *,
    session,
    conversation,
    incoming,
    refusal_reason: str = "",
    sender_name: str = "",
    sender_phone: str = "",
) -> Optional[AssistantWorkflowOutcome]:
    """
    When Vector DB / Strict RAG cannot answer a business query (non-injection refusal),
    never fabricate an answer. Enter ESCALATION_CONFIRMATION state and ask the sender
    to confirm forwarding their query + contact details to the concerned executive.
    """
    if refusal_reason == REASON_INJECTION_QUESTION:
        return None

    state, _ = WhatsAppAssistantState.objects.get_or_create(
        conversation=conversation,
        defaults={"session": session},
    )
    state.session = session
    state.mode = WhatsAppAssistantState.Mode.ESCALATION_CONFIRMATION
    state.pending_query = _msg_text(incoming)
    state.state_data = {
        "refusal_reason": refusal_reason or "",
        "incoming_message_id": str(incoming.id),
        "sender_name": sender_name or "",
        "sender_phone": sender_phone or "",
    }
    state.last_incoming_message_id = str(incoming.id)
    state.save(
        update_fields=[
            "session",
            "mode",
            "pending_query",
            "state_data",
            "last_incoming_message_id",
            "updated_at",
        ]
    )
    return AssistantWorkflowOutcome(
        handled=True,
        reply_text=ESCALATION_OFFER_MESSAGE,
        model_used="rag:escalation_prompt",
    )
