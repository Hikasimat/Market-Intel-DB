from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
import json
import logging
import re
import uuid
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone as dj_timezone

from accounts import calendar_services as cal
from accounts import zoom_services as zoom
from accounts.models import GoogleCalendarCredentials, ZoomCredentials
from accounts.timezone_utils import extract_timezone_from_text, normalize_timezone
from prospects.models import Meeting, Prospect, ProspectContact
from prospects.task_service import (
    create_whatsapp_escalation_pre_task,
    resolve_pre_user,
    resolve_prospect_and_contact_for_phone,
)
from rag.constants import REASON_INJECTION_QUESTION
from .models import WhatsAppAssistantState

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
    if has_zoom and not has_gmeet:
        return "ZOOM"
    if has_gmeet and not has_zoom:
        return "GOOGLE_MEET"
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
        '"platform": "ZOOM or GOOGLE_MEET or null", "email": "email or null", '
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

    if not parsed_platform and llm_slots.get("platform") in ("ZOOM", "GOOGLE_MEET"):
        parsed_platform = llm_slots["platform"]

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
    if parsed_email and parsed_email != updated.get("email"):
        updated["email"] = parsed_email
        changed = True
    if topic and topic != updated.get("topic"):
        updated["topic"] = topic
        changed = True
    if company_mention and not updated.get("company_name"):
        updated["company_name"] = company_mention
        changed = True

    if updated.get("awaiting_details") and (
        topic or parsed_email or re.search(r"\b(skip|none|no agenda|na|n/a)\b", text, re.IGNORECASE)
    ):
        updated["details_collected"] = True
        updated["awaiting_details"] = False

    if changed and updated.get("awaiting_confirmation") and not is_affirmative_reply(text):
        # User modified a slot instead of simply confirming -> re-present updated summary
        updated["awaiting_confirmation"] = False

    return updated


def _pick_google_calendar_creds(preferred_user):
    if preferred_user:
        creds = cal.get_calendar_credentials(preferred_user)
        if creds:
            return creds, preferred_user
    for candidate in GoogleCalendarCredentials.objects.select_related("user").filter(is_active=True).order_by("-updated_at"):
        creds = cal.get_calendar_credentials(candidate.user)
        if creds:
            return creds, candidate.user
    return None, preferred_user


def _pick_zoom_creds(preferred_user):
    if preferred_user:
        creds = zoom.get_zoom_credentials(preferred_user)
        if creds:
            return creds, preferred_user
    active = ZoomCredentials.objects.select_related("user").filter(is_active=True).order_by("-updated_at").first()
    if active:
        return active, active.user
    return None, preferred_user


def _msg_text(msg) -> str:
    return (getattr(msg, "full_body", "") or getattr(msg, "body_preview", "") or "").strip()


def _resolve_conv_crm(conversation, sender_phone: str = "", email: str = "", sender_name: str = ""):
    prospect = getattr(conversation, "prospect", None)
    contact = getattr(conversation, "prospect_contact", None)
    if prospect and contact:
        return prospect, contact
    p2, c2 = resolve_prospect_and_contact_for_phone(
        phone=sender_phone or getattr(conversation, "phone_number", "") or getattr(conversation, "chat_id", ""),
        email=email,
        sender_name=sender_name or getattr(conversation, "whatsapp_name", ""),
    )
    return prospect or p2, contact or c2


def _book_confirmed_meeting(
    *,
    session,
    conversation,
    state_data: dict,
    sender_name: str,
    sender_phone: str,
) -> Tuple[Optional[Meeting], Optional[str]]:
    """
    Create the meeting link via the selected platform (Zoom or Google Meet),
    sync to calendar, and persist the CRM Meeting associated with sender & company.
    Returns (Meeting, error_reply_message_if_failed).
    """
    date_str = state_data.get("date")
    time_str = state_data.get("time")
    tz_name = state_data.get("timezone") or "UTC"
    platform = state_data.get("platform") or "GOOGLE_MEET"
    sender_email = (state_data.get("email") or "").strip()
    topic = (state_data.get("topic") or "").strip()
    mentioned_company = (state_data.get("company_name") or "").strip()

    prospect, contact = _resolve_conv_crm(
        conversation,
        sender_phone=sender_phone,
        email=sender_email,
        sender_name=sender_name,
    )
    if prospect is None and mentioned_company:
        prospect = Prospect.objects.filter(company_name__iexact=mentioned_company).first()

    if not sender_email and contact and contact.official_email:
        sender_email = contact.official_email.strip()
    elif not sender_email and prospect and prospect.official_email_address:
        sender_email = prospect.official_email_address.strip()

    owner = resolve_pre_user(prospect=prospect, whatsapp_session=session)
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

    client_request_id = f"wa_{conversation.id.hex[:20]}_{uuid.uuid4().hex[:12]}"
    summary = f"Meeting with {company_display}" + (f" ({sender_name})" if sender_name and sender_name != company_display else "")
    agenda_lines = [
        topic or "Scheduled via WhatsApp AI Assistant",
        f"Sender: {sender_name or 'WhatsApp Contact'} ({sender_phone or 'N/A'})",
    ]
    if sender_email:
        agenda_lines.append(f"Email: {sender_email}")
    if company_display:
        agenda_lines.append(f"Company: {company_display}")
    description = "\n".join(agenda_lines)
    attendees = [sender_email] if sender_email else []

    if platform == "ZOOM":
        z_creds, z_owner = _pick_zoom_creds(owner)
        if not z_creds:
            return (
                None,
                "Zoom is not currently connected on our server, so I couldn't generate a Zoom link right now. "
                "Would you like me to schedule this meeting using *Google Meet* instead?",
            )
        try:
            z_res = zoom.create_zoom_meeting(
                z_creds,
                summary=summary,
                description=description,
                start_dt=utc_dt,
                tz_name=tz_name,
                duration_minutes=30,
            )
        except Exception as exc:
            logger.exception("WhatsApp Zoom meeting creation failed: %s", exc)
            return (
                None,
                f"I ran into an issue generating the Zoom link ({exc}). "
                "Would you like me to try *Google Meet* instead?",
            )

        cal_event_id = ""
        cal_type = ""
        g_creds, g_owner = _pick_google_calendar_creds(owner)
        if g_creds:
            try:
                cal_event_id = cal.deterministic_event_id(g_owner.id if g_owner else 0, client_request_id)
                end_local = local_dt + timedelta(minutes=30)
                cal_body = {
                    "id": cal_event_id,
                    "summary": f"{summary} (Zoom)",
                    "description": f"{description}\n\nZoom Link: {z_res.get('join_url') or ''}",
                    "location": z_res.get("join_url") or "",
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

        meeting = Meeting.objects.create(
            prospect=prospect,
            prospect_contact=contact,
            scheduled_datetime=utc_dt,
            meeting_date=local_dt.date(),
            meeting_time=local_dt.time(),
            timezone=tz_name,
            meeting_link=z_res.get("join_url") or "",
            agenda=description,
            meeting_provider="ZOOM",
            provider_meeting_id=str(z_res.get("meeting_id") or ""),
            google_event_id=cal_event_id,
            calendar_event_id=cal_event_id or str(z_res.get("meeting_id") or ""),
            calendar_type=cal_type,
            google_calendar_owner=g_owner if cal_event_id else None,
            created_by=owner,
            status="SCHEDULED",
            conference_status="READY",
            client_request_id=client_request_id,
        )
        return meeting, None

    # Default / GOOGLE_MEET
    g_creds, g_owner = _pick_google_calendar_creds(owner)
    if not g_creds:
        return (
            None,
            "Google Calendar is not currently connected on our server, so I couldn't generate a Google Meet link right now. "
            "Please contact our executive team directly for assistance.",
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
            duration_minutes=30,
        )
    except Exception as exc:
        logger.exception("WhatsApp Google Meet creation failed: %s", exc)
        return (
            None,
            f"I ran into an issue generating the Google Meet link ({exc}). "
            "Would you like me to try again or switch to *Zoom*?",
        )

    meeting = Meeting.objects.create(
        prospect=prospect,
        prospect_contact=contact,
        scheduled_datetime=utc_dt,
        meeting_date=local_dt.date(),
        meeting_time=local_dt.time(),
        timezone=tz_name,
        meeting_link=g_res.get("meet_url") or "",
        agenda=description,
        meeting_provider="GOOGLE_MEET",
        google_event_id=g_res.get("event_id") or "",
        calendar_event_id=g_res.get("event_id") or "",
        calendar_type="GOOGLE_CALENDAR",
        google_calendar_owner=g_owner,
        created_by=owner,
        status="SCHEDULED" if g_res.get("status") == "READY" else "PENDING",
        conference_status=g_res.get("status") or "READY",
        client_request_id=client_request_id,
    )
    return meeting, None


def _next_scheduling_prompt(state_data: dict, *, company_hint: str = "", email_hint: str = "") -> str:
    d_str = state_data.get("date")
    t_str = state_data.get("time")
    tz_str = state_data.get("timezone")
    plat = state_data.get("platform")

    if not d_str or not t_str:
        if d_str and not t_str:
            return (
                f"Got your preferred date ({d_str}). What *time* (and *time zone*, e.g. IST, EST, UTC, Asia/Kolkata) works best for you?"
            )
        if t_str and not d_str:
            return (
                f"Got your preferred time ({t_str}). Which *date* (and *time zone*, e.g. IST, EST, UTC, Asia/Kolkata) would you like?"
            )
        return (
            "I would be happy to schedule a meeting for you! "
            "Could you please share your preferred *date* and *time* "
            "(for example, tomorrow at 3:00 PM or 2026-11-25 at 10:30 AM)?"
        )

    if not tz_str:
        return (
            f"Thanks! I have *{d_str} at {t_str}*. "
            "Which *time zone* are you in (e.g., IST / Asia/Kolkata, EST / America/New_York, UTC, GMT+4)?"
        )

    effective_email = state_data.get("email") or email_hint
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
            f"Could you also share {joined}? (You can reply _skip_ if you prefer.)"
        )

    if not plat:
        return "Which meeting platform do you prefer — *Zoom* or *Google Meet*?"

    # Ready for confirmation!
    state_data["awaiting_confirmation"] = True
    platform_label = "Zoom" if plat == "ZOOM" else "Google Meet"
    topic_label = state_data.get("topic") or "Business Discussion"
    lines = [
        "Please confirm your meeting details:",
        f"- Date: {d_str}",
        f"- Time: {t_str} ({tz_str})",
        f"- Platform: {platform_label}",
        f"- Topic: {topic_label}",
    ]
    if effective_email:
        lines.append(f"- Email: {effective_email}")
    lines.append("")
    lines.append("Reply *Yes* or *Confirm* to schedule the meeting and generate your meeting link.")
    return "\n".join(lines)


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
            prospect, contact = _resolve_conv_crm(
                conversation,
                sender_phone=sender_phone,
                email=extracted_email,
                sender_name=sender_name,
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

        if in_meeting_flow and is_negative_or_cancel_reply(text):
            state.reset()
            return AssistantWorkflowOutcome(
                handled=True,
                reply_text="No problem — I have cancelled the meeting scheduling request. Let me know if you need anything else!",
                model_used="assistant:meeting_cancelled",
            )

        sdata = dict(state.state_data or {})
        prospect, contact = _resolve_conv_crm(
            conversation,
            sender_phone=sender_phone,
            email=sdata.get("email"),
            sender_name=sender_name,
        )
        known_email = (
            sdata.get("email")
            or (contact.official_email if contact and contact.official_email else "")
            or (prospect.official_email_address if prospect and prospect.official_email_address else "")
        )
        known_company = prospect.company_name if prospect else ""

        # If awaiting confirmation & sender confirms -> generate link and save Meeting!
        if (
            sdata.get("awaiting_confirmation")
            and sdata.get("date")
            and sdata.get("time")
            and sdata.get("timezone")
            and sdata.get("platform")
            and is_affirmative_reply(text)
        ):
            meeting, err_msg = _book_confirmed_meeting(
                session=session,
                conversation=conversation,
                state_data=sdata,
                sender_name=sender_name,
                sender_phone=sender_phone,
            )
            if err_msg:
                # Allow switching platform if one provider isn't connected
                sdata["platform"] = None
                sdata["awaiting_confirmation"] = False
                state.state_data = sdata
                state.last_incoming_message_id = str(incoming.id)
                state.save(update_fields=["mode", "state_data", "last_incoming_message_id", "updated_at"])
                return AssistantWorkflowOutcome(
                    handled=True,
                    reply_text=err_msg,
                    model_used="assistant:meeting_provider_retry",
                )

            platform_label = "Zoom" if meeting.meeting_provider == "ZOOM" else "Google Meet"
            company_label = meeting.prospect.company_name if meeting.prospect else (sdata.get("company_name") or sender_name or "Your Team")
            local_date_str = meeting.meeting_date.isoformat() if meeting.meeting_date else sdata.get("date")
            local_time_str = meeting.meeting_time.strftime("%H:%M") if meeting.meeting_time else sdata.get("time")
            reply = (
                f"Your {platform_label} meeting is confirmed and added to the calendar!\n\n"
                f"- Company / Contact: {company_label}\n"
                f"- Date: {local_date_str}\n"
                f"- Time: {local_time_str} ({meeting.timezone})\n"
                f"- Platform: {platform_label}\n"
                f"- Meeting Link: {meeting.meeting_link or 'Link generated in calendar'}\n\n"
                "We look forward to speaking with you!"
            )
            state.reset()
            return AssistantWorkflowOutcome(
                handled=True,
                reply_text=reply,
                model_used=f"assistant:meeting_booked:{meeting.meeting_provider.lower()}",
            )

        # Extract any new slots from message and advance the conversation
        sdata = _extract_meeting_slots(text, sdata, model_name=model_name)
        reply = _next_scheduling_prompt(sdata, company_hint=known_company, email_hint=known_email)
        state.mode = WhatsAppAssistantState.Mode.MEETING_SCHEDULING
        state.state_data = sdata
        state.last_incoming_message_id = str(incoming.id)
        state.save(update_fields=["mode", "state_data", "last_incoming_message_id", "updated_at"])
        return AssistantWorkflowOutcome(
            handled=True,
            reply_text=reply,
            model_used="assistant:meeting_scheduler",
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
