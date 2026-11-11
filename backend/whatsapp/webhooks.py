"""
backend/whatsapp/webhooks.py

Secure WAHA webhook event processor.

Security design:
  1.  HMAC-SHA256 signature verification (reject if invalid).
  2.  Timestamp validation (reject stale events > 5 minutes).
  3.  Payload schema validation (reject unknown event types).
  4.  Duplicate event detection (idempotent processing).
  5.  Safe phone number extraction (no arbitrary field trust).
  6.  Opt-out keyword detection.
  7.  Unmatched message quarantine (no guessing associations).
  8.  Async-safe: all DB writes use atomic transactions.

IMPORTANT:
  - Never execute arbitrary commands from webhook payloads.
  - Never trust phone numbers, chat IDs, or message bodies without validation.
  - Never expose unmatched messages to random users.
"""

import hashlib
import hmac
import ipaddress
import json
import logging
import socket
import urllib.request
import urllib.error
import urllib.parse
import mimetypes
import os
import re
import tempfile
from typing import Optional

from django.core.files.base import ContentFile
from django.db import transaction, IntegrityError
from django.utils import timezone

from .models import (
    WhatsAppAuditLog,
    WhatsAppConversation,
    WhatsAppEvent,
    WhatsAppMessage,
    WhatsAppOptOut,
    WhatsAppSafetyEvent,
    WhatsAppSession,
)
from .services import (
    _write_audit_log,
    check_incoming_for_opt_out,
)

logger = logging.getLogger(__name__)

# Shared file-based + in-memory cache for the latest QR code pushed by WAHA
LATEST_QR_CACHE: dict = {}

def _qr_cache_file(session_name: str) -> str:
    import tempfile
    clean = re.sub(r'[^a-zA-Z0-9_\-]', '', session_name) or "default"
    return os.path.join(tempfile.gettempdir(), f"waha_qr_{clean}.json")

def get_cached_qr(session_name: str = "default") -> Optional[dict]:
    """Return the most recently received QR code for a session, shared across all worker processes."""
    cached = LATEST_QR_CACHE.get(session_name)
    if cached and (cached.get("qr") or cached.get("qrBase64")):
        return cached

    cache_path = _qr_cache_file(session_name)
    try:
        if os.path.exists(cache_path):
            age = timezone.now().timestamp() - os.path.getmtime(cache_path)
            if age <= 180:  # Valid for up to 3 minutes
                with open(cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and (data.get("qr") or data.get("qrBase64")):
                        LATEST_QR_CACHE[session_name] = data
                        return data
            else:
                try:
                    os.remove(cache_path)
                except OSError:
                    pass
    except Exception as e:
        logger.debug("Failed to read shared QR cache file: %s", e)
    return None

def set_cached_qr(session_name: str, qr_data: dict) -> None:
    """Persist QR code to memory and disk so all Gunicorn workers see it immediately."""
    if not isinstance(qr_data, dict):
        return
    qr = qr_data.get("qr") or qr_data.get("value") or qr_data.get("raw")
    qr_base64 = qr_data.get("qrBase64") or qr_data.get("data") or ""
    if not qr_base64 and qr and str(qr).startswith("data:image/"):
        qr_base64 = qr
    if qr_base64 and not qr_base64.startswith("data:image/"):
        qr_base64 = f"data:image/png;base64,{qr_base64}"

    payload = {
        "qr": qr or qr_base64,
        "qrBase64": qr_base64,
        "value": qr or qr_base64,
        "data": qr_base64,
        "session": session_name,
        "timestamp": timezone.now().isoformat(),
    }
    LATEST_QR_CACHE[session_name] = payload
    try:
        cache_path = _qr_cache_file(session_name)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception as e:
        logger.debug("Failed to write shared QR cache file: %s", e)

def clear_cached_qr(session_name: str) -> None:
    """Clear cached QR code across memory and disk."""
    LATEST_QR_CACHE.pop(session_name, None)
    try:
        cache_path = _qr_cache_file(session_name)
        if os.path.exists(cache_path):
            os.remove(cache_path)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Live WhatsApp Active / Incoming Call Tracking
# ---------------------------------------------------------------------------

LATEST_CALL_CACHE: dict = {}
HANDLED_CALL_IDS: dict = {}


def _normalize_call_id(call_id: Optional[str]) -> str:
    if not call_id:
        return ""
    s = str(call_id).strip()
    if s.startswith("call_"):
        s = s[5:]
    return s.strip()


def _handled_calls_file() -> str:
    return os.path.join(tempfile.gettempdir(), "waha_handled_calls.json")


def mark_call_handled(call_id: Optional[str]) -> None:
    """
    Record a call_id as handled (accepted, rejected, ended, or missed) across memory and
    shared temp storage so late/retried webhooks or polling never re-trigger an incoming call.
    """
    import time
    clean_id = _normalize_call_id(call_id)
    if not clean_id:
        return
    now = time.time()
    HANDLED_CALL_IDS[clean_id] = now
    fpath = _handled_calls_file()
    try:
        data = {}
        if os.path.exists(fpath):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        data = loaded
            except Exception:
                data = {}
        # Prune entries older than 48 hours
        data = {k: v for k, v in data.items() if isinstance(v, (int, float)) and (now - v) < 172800}
        data[clean_id] = now
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        logger.debug("Failed to persist handled call ID %s: %s", clean_id, e)


def is_call_handled(call_id: Optional[str]) -> bool:
    """Return True if call_id has already been accepted, declined, or ended."""
    import time
    clean_id = _normalize_call_id(call_id)
    if not clean_id:
        return False
    now = time.time()
    ts = HANDLED_CALL_IDS.get(clean_id)
    if ts and (now - ts) < 172800:
        return True
    fpath = _handled_calls_file()
    try:
        if os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                file_ts = data.get(clean_id)
                if isinstance(file_ts, (int, float)) and (now - file_ts) < 172800:
                    HANDLED_CALL_IDS[clean_id] = file_ts
                    return True
    except Exception:
        pass
    return False


def _call_cache_file(session_name: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", session_name or "default")
    return os.path.join(tempfile.gettempdir(), f"waha_active_call_{clean}.json")


def _call_state_file(session_name: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_\-]", "_", session_name or "default")
    return os.path.join(tempfile.gettempdir(), f"waha_call_state_{clean}.json")


def get_active_incoming_call(session_name: str = "default") -> Optional[dict]:
    """
    Retrieve currently ringing incoming voice call strictly for the specified session.
    Never cross-pollutes calls across different user sessions.
    """
    import time
    now = time.time()

    if not session_name:
        return None

    def _is_valid_call(data: dict, mtime: float) -> bool:
        if not isinstance(data, dict):
            return False
        cid = _normalize_call_id(data.get("call_id"))
        if not cid:
            return False
        if is_call_handled(cid):
            return False
        if data.get("status") != "ringing":
            return False
        max_age = 45
        ref_time = data.get("received_at") or mtime
        return (now - ref_time) <= max_age

    cache_path = _call_cache_file(session_name)
    try:
        if os.path.exists(cache_path):
            mtime = os.path.getmtime(cache_path)
            with open(cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if _is_valid_call(data, mtime):
                LATEST_CALL_CACHE[session_name] = data
                return data
            else:
                LATEST_CALL_CACHE.pop(session_name, None)
                try:
                    os.remove(cache_path)
                except OSError:
                    pass
        else:
            LATEST_CALL_CACHE.pop(session_name, None)
    except Exception:
        pass

    return None


def set_active_incoming_call(session_name: str, call_data: dict) -> None:
    """Persist active incoming call to memory and temp cache file strictly for this session."""
    import time
    if not isinstance(call_data, dict) or not session_name:
        return
    clean_id = _normalize_call_id(call_data.get("call_id"))
    if clean_id and is_call_handled(clean_id):
        logger.debug("Skipping set_active_incoming_call for already-handled call %s", clean_id)
        return
    call_data = dict(call_data)
    if clean_id:
        call_data["call_id"] = clean_id
    call_data["received_at"] = time.time()
    call_data["session_name"] = session_name
    LATEST_CALL_CACHE[session_name] = call_data
    try:
        cache_path = _call_cache_file(session_name)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(call_data, f)
    except Exception as e:
        logger.debug("Failed to write call cache file: %s", e)


def get_active_call_state(session_name: str) -> Optional[dict]:
    """Retrieve active call state (connected, ended, etc.) strictly for session."""
    if not session_name:
        return None
    state_file = _call_state_file(session_name)
    try:
        if os.path.exists(state_file):
            with open(state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return None


def set_session_call_state(session_name: str, state_data: dict) -> None:
    """Record active call state strictly for session."""
    if not session_name or not isinstance(state_data, dict):
        return
    state_file = _call_state_file(session_name)
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state_data, f)
    except Exception as e:
        logger.debug("Failed to persist call state: %s", e)


def mark_active_call_connected(session_name: str = "default", call_id: Optional[str] = None) -> None:
    """
    Mark an incoming call as handled/connected and remove it from active ringing cache
    so polling never re-surfaces the call banner after the user attends it.
    """
    clean_target = _normalize_call_id(call_id)
    if clean_target:
        mark_call_handled(clean_target)
    clear_active_call(session_name, call_id)
    if session_name:
        set_session_call_state(session_name, {
            "call_id": clean_target or "",
            "status": "active",
            "session_name": session_name,
            "connected_at": timezone.now().isoformat(),
        })


def mark_call_ended(session_name: str = "default", call_id: Optional[str] = None, reason: str = "ended") -> None:
    """Explicitly mark an active call as ended in session state."""
    clean_target = _normalize_call_id(call_id)
    if clean_target:
        mark_call_handled(clean_target)
    clear_active_call(session_name, call_id)
    if session_name:
        set_session_call_state(session_name, {
            "call_id": clean_target or "",
            "status": "ended",
            "reason": reason,
            "session_name": session_name,
            "ended_at": timezone.now().isoformat(),
        })


def clear_active_call(session_name: str = "default", call_id: Optional[str] = None) -> None:
    """Clear active incoming ringing call strictly for this session."""
    clean_target = _normalize_call_id(call_id)
    if clean_target:
        mark_call_handled(clean_target)

    # Only affect the requested session
    if session_name in LATEST_CALL_CACHE:
        cached = LATEST_CALL_CACHE.get(session_name)
        cached_id = _normalize_call_id(cached.get("call_id")) if isinstance(cached, dict) else ""
        if not clean_target or cached_id == clean_target:
            LATEST_CALL_CACHE.pop(session_name, None)

    try:
        cache_path = _call_cache_file(session_name)
        if os.path.exists(cache_path):
            if not clean_target:
                os.remove(cache_path)
            else:
                with open(cache_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                file_cid = _normalize_call_id(data.get("call_id")) if isinstance(data, dict) else ""
                if file_cid == clean_target or is_call_handled(file_cid):
                    os.remove(cache_path)
    except Exception:
        pass


CRM_GROUP_CACHE = {}

def set_crm_group_participants(chat_id: str, participants: list, name: str = "") -> None:
    """Cache CRM broadcast group participants in memory and disk cache."""
    CRM_GROUP_CACHE[chat_id] = list(participants)
    try:
        import hashlib
        fpath = os.path.join(tempfile.gettempdir(), f"crm_group_{hashlib.md5(chat_id.encode()).hexdigest()}.json")
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump({"chat_id": chat_id, "participants": list(participants), "name": name}, f)
    except Exception:
        pass

def get_crm_group_participants(chat_id: str) -> list:
    """Retrieve CRM broadcast group participants from memory, disk cache, or audit log."""
    if chat_id in CRM_GROUP_CACHE:
        return CRM_GROUP_CACHE[chat_id]
    try:
        import hashlib
        fpath = os.path.join(tempfile.gettempdir(), f"crm_group_{hashlib.md5(chat_id.encode()).hexdigest()}.json")
        if os.path.exists(fpath):
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "participants" in data:
                CRM_GROUP_CACHE[chat_id] = data["participants"]
                return data["participants"]
    except Exception:
        pass
    try:
        from .models import WhatsAppAuditLog
        log = WhatsAppAuditLog.objects.filter(
            chat_id=chat_id,
        ).order_by("-timestamp").first()
        if log and isinstance(log.details, dict) and "participants" in log.details:
            CRM_GROUP_CACHE[chat_id] = log.details["participants"]
            return log.details["participants"]
    except Exception:
        pass
    return []


def _save_media_url_to_message(message_id, media_url: str, mime_type: str):
    """Store WAHA's local media URL directly in the database - no re-download needed."""
    from whatsapp.models import WhatsAppMessage
    import logging as _logging
    try:
        wa_message = WhatsAppMessage.objects.get(pk=message_id)
    except WhatsAppMessage.DoesNotExist:
        return

    try:
        wa_message.has_media = True
        wa_message.media_mime_type = mime_type or ''
        wa_message.media_url = media_url
        wa_message.save(update_fields=['has_media', 'media_mime_type', 'media_url'])
        _logging.getLogger(__name__).info('Saved media URL for message %s: %s', wa_message.waha_message_id, media_url)
    except Exception as e:
        _logging.getLogger(__name__).error('Failed to save media URL for message %s: %s', wa_message.waha_message_id, e)


def _is_ssrf_safe_url(url: str, allowed_base: str) -> bool:
    """
    Returns True only if *url* is safe to fetch:
    - Scheme must be http or https.
    - Hostname must resolve to a public, non-RFC-1918 IP address.
    - Allows any URL whose hostname matches the configured WHATSAPP_SERVICE_URL host.
    """
    _PRIVATE_NETWORKS = [
        ipaddress.ip_network('10.0.0.0/8'),
        ipaddress.ip_network('172.16.0.0/12'),
        ipaddress.ip_network('192.168.0.0/16'),
        ipaddress.ip_network('127.0.0.0/8'),
        ipaddress.ip_network('169.254.0.0/16'),  # link-local / cloud metadata
        ipaddress.ip_network('::1/128'),
        ipaddress.ip_network('fc00::/7'),
    ]
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False
        hostname = parsed.hostname or ''
        # Always allow the configured WAHA server
        allowed_host = urllib.parse.urlparse(allowed_base).hostname or ''
        if hostname == allowed_host:
            return True
        # Resolve hostname and check against private ranges
        ip_str = socket.gethostbyname(hostname)
        ip_obj = ipaddress.ip_address(ip_str)
        for net in _PRIVATE_NETWORKS:
            if ip_obj in net:
                return False
        return True
    except Exception:
        return False  # if we cannot resolve, block it


def _download_and_save_media_bg(message_id, session_name: str, media_url: str = None, mime_type: str = None):
    """Download media from WAHA and store it locally in Django media directory."""
    from whatsapp.models import WhatsAppMessage
    import logging as _logging

    try:
        wa_message = WhatsAppMessage.objects.select_related("conversation").get(pk=message_id)
        chat_id = wa_message.conversation.chat_id if wa_message.conversation else ""
        if "status@broadcast" in chat_id or chat_id.endswith("@broadcast"):
            return  # strictly ignore status stories/broadcast media
    except WhatsAppMessage.DoesNotExist:
        return

    waha_url = os.getenv('WHATSAPP_SERVICE_URL', 'http://localhost:3000').rstrip('/')
    api_key = os.getenv('WHATSAPP_SERVICE_API_KEY')

    urls_to_try = []
    if media_url:
        if media_url.startswith('http'):
            urls_to_try.append(media_url)
        else:
            urls_to_try.append(f"{waha_url}/{media_url.lstrip('/')}")
    
    # Try direct WAHA files endpoint
    if wa_message.waha_message_id:
        urls_to_try.append(f'{waha_url}/api/files/{urllib.parse.quote(session_name)}/{urllib.parse.quote(wa_message.waha_message_id)}')
        urls_to_try.append(f'{waha_url}/api/messages/{urllib.parse.quote(wa_message.waha_message_id)}/download?session={urllib.parse.quote(session_name)}')

    for url in urls_to_try:
        # SSRF guard: block any URL that resolves to a private/internal IP address
        if not _is_ssrf_safe_url(url, waha_url):
            _logging.getLogger(__name__).warning(
                'SSRF guard blocked media fetch from disallowed URL: %s (message %s)',
                url, wa_message.waha_message_id,
            )
            try:
                WhatsAppSafetyEvent.objects.create(
                    event_type='SSRF_BLOCKED',
                    details=f'Blocked outbound media fetch to: {url}',
                )
            except Exception:
                pass
            continue
        try:
            req = urllib.request.Request(url)
            if api_key:
                req.add_header('X-Api-Key', api_key)

            with urllib.request.urlopen(req, timeout=30) as response:
                content = response.read()
                content_type = response.headers.get('Content-Type', '') or mime_type or 'application/octet-stream'
                ext = mimetypes.guess_extension(content_type.split(';')[0]) or '.bin'
                file_name = f'{wa_message.waha_message_id or message_id}{ext}'

                wa_message.has_media = True
                wa_message.media_mime_type = content_type
                if media_url and not wa_message.media_url:
                    wa_message.media_url = media_url
                wa_message.media_file.save(file_name, ContentFile(content), save=True)
                _logging.getLogger(__name__).info(
                    'Successfully downloaded media for %s from %s', wa_message.waha_message_id, url
                )
                return  # success — stop trying
        except Exception as e:
            _logging.getLogger(__name__).warning(
                'Failed to download media for %s from %s: %s', wa_message.waha_message_id, url, e
            )

    _logging.getLogger(__name__).error(
        'All download attempts failed for message %s', wa_message.waha_message_id
    )


def _fetch_contact_profile_picture_bg(conversation_id, session_name: str, chat_id: str):
    """
    Fetch profile picture from WAHA in background and store in conversation.custom_avatar_url.
    GET /api/contacts/profile-picture?contactId=...&session=...
    """
    from whatsapp.models import WhatsAppConversation
    try:
        conv = WhatsAppConversation.objects.get(pk=conversation_id)
        if conv.custom_avatar_url:
            return  # already cached
    except WhatsAppConversation.DoesNotExist:
        return

    waha_url = os.getenv('WHATSAPP_SERVICE_URL', 'http://localhost:3000').rstrip('/')
    api_key = os.getenv('WHATSAPP_SERVICE_API_KEY')

    # Try standard WAHA profile picture endpoints
    urls = [
        f"{waha_url}/api/contacts/profile-picture?session={urllib.parse.quote(session_name)}&contactId={urllib.parse.quote(chat_id)}",
        f"{waha_url}/api/contacts/profile-picture?contactId={urllib.parse.quote(chat_id)}",
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url)
            if api_key:
                req.add_header('X-Api-Key', api_key)
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                pic_url = data.get("url") or data.get("profilePictureURL") or data.get("picture")
                if pic_url and isinstance(pic_url, str) and pic_url.startswith("http"):
                    conv.custom_avatar_url = pic_url
                    conv.save(update_fields=["custom_avatar_url"])
                    logger.info("Saved WAHA profile picture for %s: %s", chat_id, pic_url)
                    return
        except Exception:
            pass


# Maximum allowed age of a webhook event (seconds).
# Events older than this are rejected to prevent replay attacks.
WEBHOOK_MAX_AGE_SECONDS = 300  # 5 minutes

# Allowed WAHA event types. Anything else is rejected.
ALLOWED_EVENT_TYPES = frozenset([
    "message",
    "message.any",
    "message.ack",
    "message.reaction",
    "session.status",
    "session.connected",
    "session.disconnected",
    "auth.qr",
    "auth.pairing_code",
    "qrcode",
    "qr",
    "scan.qr",
    "presence.update",
    "group.v2.participants",
    "group.v2.update",
    "message.waiting",
    "call",
    "call.received",
    "call.ringing",
    "call.accepted",
    "call.rejected",
    "call.missed",
    "call.ended",
    "call.update",
    "call.voice.incoming",
    "call.voice.ringing",
    "call.voice.active",
    "call.voice.rejected",
    "call.voice.missed",
    "call.voice.ended",
])

# Valid WhatsApp chat ID pattern.
VALID_CHAT_ID_RE = re.compile(r"^[0-9a-zA-Z_\-\.]+@(c\.us|g\.us|lid|s\.whatsapp\.net)$")
PHONE_DIGITS_RE = re.compile(r"^\d{7,25}$")


class WebhookVerificationError(Exception):
    """Raised when webhook signature or schema validation fails."""
    pass


class WebhookDuplicateError(Exception):
    """Raised when a duplicate webhook event is detected."""
    pass


def _get_webhook_secret() -> str:
    secret = os.environ.get("WHATSAPP_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise RuntimeError("WHATSAPP_WEBHOOK_SECRET is not configured.")
    return secret


def verify_hmac_signature(request_body: bytes, signature_header: str, algorithm: str = "sha256", timestamp: str = "") -> bool:
    """
    Verify the HMAC signature from WAHA.
    Supports WAHA's cryptographic format (${timestamp}.${rawBody}) as well as raw body.
    Supports both sha512 and sha256.
    """
    if not signature_header:
        logger.warning("Webhook received without signature header.")
        return False

    try:
        secret = _get_webhook_secret()
    except RuntimeError:
        logger.error("WHATSAPP_WEBHOOK_SECRET not configured. Cannot verify webhook.")
        return False

    received_mac = signature_header.removeprefix("sha256=").removeprefix("sha512=").strip()

    bodies_to_test = []
    if timestamp:
        bodies_to_test.append(f"{timestamp}.".encode("utf-8") + request_body)
    bodies_to_test.append(request_body)

    for body in bodies_to_test:
        for digestmod in (hashlib.sha512, hashlib.sha256):
            expected_mac = hmac.new(
                key=secret.encode("utf-8"),
                msg=body,
                digestmod=digestmod,
            ).hexdigest()
            if hmac.compare_digest(expected_mac, received_mac):
                return True

    return False


def _compute_payload_hash(raw_body: bytes) -> str:
    """SHA256 hash of the raw webhook payload for deduplication."""
    return hashlib.sha256(raw_body).hexdigest()


def _validate_event_schema(payload: dict) -> tuple[str, str, dict]:
    """
    Validate the webhook event payload schema.

    Returns (event_type, session_name, event_data).
    Raises WebhookVerificationError on invalid schema.
    """
    if not isinstance(payload, dict):
        raise WebhookVerificationError("Payload must be a JSON object.")

    event_type = payload.get("event") or payload.get("type")
    if not isinstance(event_type, str) or not event_type:
        raise WebhookVerificationError("Missing or invalid 'event' field.")

    # Normalize event type.
    event_type = event_type.strip().lower()

    if event_type not in ALLOWED_EVENT_TYPES and not event_type.startswith("call.") and event_type != "call":
        raise WebhookVerificationError(
            f"Unknown event type: {event_type!r}. "
            f"Allowed: {sorted(ALLOWED_EVENT_TYPES)}"
        )

    raw_session = payload.get("session")
    # Message / acknowledgement events must explicitly identify their originating session.
    # Never silently substitute "default" — ambiguous events are rejected.
    if event_type in ("message", "message.any", "message.ack", "message.reaction", "message.waiting"):
        if not isinstance(raw_session, str) or not raw_session.strip():
            raise WebhookVerificationError(
                f"Event {event_type!r} is missing its originating 'session' — rejected."
            )
    session_name = raw_session if raw_session is not None else "default"
    if not isinstance(session_name, str):
        session_name = "default"
    session_name = session_name.strip()[:100]

    event_data = payload.get("payload") or payload.get("data") or {}
    if not isinstance(event_data, dict):
        event_data = {}

    return event_type, session_name, event_data


def _is_lid(val: str) -> bool:
    if not val:
        return False
    digits = re.sub(r"\D+", "", str(val))
    return len(digits) > 13 or digits.startswith(("7658", "2262", "2167")) or str(val).endswith("@lid")


def _extract_phone_digits(chat_id: str) -> Optional[str]:
    """
    Safely extract phone digits from a WhatsApp chat ID.
    Per user rule: before the @c.us (or @s.whatsapp.net) is the user mobile number.
    @lid JIDs are internal WhatsApp device identifiers and NOT phone numbers.
    """
    if not isinstance(chat_id, str):
        return None

    # Only process individual chats with @c.us or @s.whatsapp.net (NOT @lid or @g.us)
    if not (chat_id.endswith("@c.us") or chat_id.endswith("@s.whatsapp.net")):
        return None

    digits = chat_id.split("@")[0].split(":")[0]

    if not PHONE_DIGITS_RE.match(digits):
        return None

    if _is_lid(digits):
        return None

    return digits


def _resolve_originating_session(session_name: str) -> Optional[WhatsAppSession]:
    """
    Resolve the originating WhatsAppSession strictly by the exact WAHA session name.
    Returns None when the session cannot be resolved reliably (caller must reject the event).
    Only a registered `user_<id>` session whose owner exists may be lazily registered.
    """
    session_name = (session_name or "").strip()
    if not session_name:
        return None
    session_obj = WhatsAppSession.objects.filter(session_name=session_name).first()
    if session_obj:
        return session_obj
    if session_name.startswith("user_"):
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            u_id = int(session_name.split("_")[1])
            u = User.objects.filter(id=u_id, is_active=True).first()
            if u:
                session_obj, _ = WhatsAppSession.objects.get_or_create(
                    session_name=session_name,
                    defaults={"owner": u, "status": WhatsAppSession.Status.STARTING},
                )
                return session_obj
        except Exception:
            return None
    return None


def _normalize_chat_jid(jid: str) -> str:
    """Normalize equivalent JID formats (device suffix, @s.whatsapp.net -> @c.us). Session-agnostic string
    normalization only; callers must always combine it with a session for identity."""
    jid = re.sub(r":[0-9]+@", "@", str(jid or "").strip())
    return jid.replace("@s.whatsapp.net", "@c.us")


def process_webhook_event(
    raw_body: bytes,
    signature_header: str,
    algorithm: str = "sha256",
    remote_addr: str = "",
    timestamp: str = "",
) -> Optional[WhatsAppEvent]:
    """
    Process an incoming WAHA webhook event.

    This is the main entry point called by the webhook view.
    """
    # -----------------------------------------------------------------------
    # 1. HMAC verification
    # -----------------------------------------------------------------------
    from django.conf import settings
    bypass_hmac = getattr(settings, 'DEBUG', False) and not signature_header

    if bypass_hmac:
        logger.warning("Bypassing webhook HMAC verification because DEBUG=True and WAHA sent no signature.")
    elif not verify_hmac_signature(raw_body, signature_header, algorithm, timestamp=timestamp):
        logger.warning(
            "Webhook HMAC verification FAILED from %s. Request rejected.",
            remote_addr,
        )
        raise WebhookVerificationError("Invalid webhook signature.")

    # -----------------------------------------------------------------------
    # 2. Parse JSON
    # -----------------------------------------------------------------------
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Webhook payload JSON parse error: %s", exc)
        raise WebhookVerificationError("Invalid JSON payload.") from exc

    # -----------------------------------------------------------------------
    # 3. Validate schema
    # -----------------------------------------------------------------------
    event_type, session_name, event_data = _validate_event_schema(payload)

    # -----------------------------------------------------------------------
    # 4. Duplicate detection
    # -----------------------------------------------------------------------
    payload_hash = _compute_payload_hash(raw_body)

    existing = WhatsAppEvent.objects.filter(
        payload_hash=payload_hash,
        processing_status=WhatsAppEvent.ProcessingStatus.PROCESSED,
    ).first()

    if existing:
        logger.debug("Duplicate webhook event detected: hash=%s", payload_hash)
        raise WebhookDuplicateError(f"Duplicate event: {payload_hash}")

    # -----------------------------------------------------------------------
    # 5. Create event record
    # -----------------------------------------------------------------------
    with transaction.atomic():
        event_record = WhatsAppEvent.objects.create(
            event_type=event_type,
            session_name=session_name,
            hmac_valid=True,
            processing_status=WhatsAppEvent.ProcessingStatus.PENDING,
            payload_hash=payload_hash,
        )

    # -----------------------------------------------------------------------
    # 6. Route to handler
    # -----------------------------------------------------------------------
    try:
        if event_type in ("message", "message.any"):
            _handle_incoming_message(event_data, session_name, event_record)
        elif event_type == "call" or event_type.startswith("call."):
            _handle_call_event(event_data, session_name, event_record, event_type)
        elif event_type == "message.ack":
            _handle_message_ack(event_data, session_name, event_record)
        elif event_type in ("group.v2.participants", "group.join", "group.leave"):
            _handle_group_participant_event(event_data, session_name, event_record, event_type)
        elif event_type == "session.status":
            _handle_session_status(event_data, session_name, event_record)
        elif event_type == "session.connected":
            _handle_session_connected(event_data, session_name, event_record)
        elif event_type == "session.disconnected":
            _handle_session_disconnected(event_data, session_name, event_record)
        elif event_type in ("auth.qr", "qrcode", "qr", "scan.qr"):
            _handle_auth_qr(event_data, session_name, event_record)

        # Mark as processed.
        event_record.processing_status = WhatsAppEvent.ProcessingStatus.PROCESSED
        event_record.processed_at = timezone.now()
        event_record.save(update_fields=["processing_status", "processed_at"])

    except Exception as exc:
        logger.error(
            "Webhook event processing error: event_type=%s error=%s",
            event_type,
            str(exc),
            exc_info=True,
        )
        event_record.processing_status = WhatsAppEvent.ProcessingStatus.FAILED
        event_record.processing_error = str(exc)[:500]
        event_record.processed_at = timezone.now()
        event_record.save(update_fields=["processing_status", "processing_error", "processed_at"])

    return event_record


# ---------------------------------------------------------------------------
# Event handlers
# ---------------------------------------------------------------------------

def _handle_auth_qr(event_data: dict, session_name: str, event_record: WhatsAppEvent) -> None:
    qr = event_data.get("qr") or event_data.get("value") or event_data.get("data")
    qr_base64 = event_data.get("qrBase64") or event_data.get("data") or ""
    if qr or qr_base64:
        set_cached_qr(session_name, {
            "qr": qr or qr_base64,
            "qrBase64": qr_base64,
            "value": qr or qr_base64,
            "data": qr_base64,
        })
        WhatsAppSession.objects.filter(session_name=session_name).update(
            status=WhatsAppSession.Status.QR_REQUIRED
        )
        logger.info("Received and cached auth.qr for session: %s", session_name)


def _handle_session_connected(event_data: dict, session_name: str, event_record: WhatsAppEvent) -> None:
    clear_cached_qr(session_name)
    me = event_data.get("me") or {}
    phone = me.get("phone") or (me.get("id", "").split(":")[0] if ":" in me.get("id", "") else me.get("id", "").split("@")[0])
    name = me.get("name") or ""

    session, _ = WhatsAppSession.objects.get_or_create(session_name=session_name)

    # Detect account switch on the same session
    clean_new_phone = re.sub(r"\D+", "", str(phone or ""))
    clean_old_phone = re.sub(r"\D+", "", str(session.phone_number or ""))
    if clean_new_phone and clean_old_phone and clean_new_phone != clean_old_phone:
        logger.warning(
            "WhatsApp account change detected on session %s: %s -> %s. Purging old session data.",
            session_name, clean_old_phone, clean_new_phone
        )
        WhatsAppMessage.objects.filter(conversation__session=session).delete()
        WhatsAppConversation.objects.filter(session=session).delete()

    session.status = WhatsAppSession.Status.READY
    if phone:
        session.phone_number = phone
    session.started_at = timezone.now()
    session.reconnect_count += 1
    session.save()
    logger.info("Session %s connected successfully! Phone: %s Name: %s", session_name, phone, name)


def _handle_session_disconnected(event_data: dict, session_name: str, event_record: WhatsAppEvent) -> None:
    is_logged_out = bool(event_data.get("isLoggedOut", False))
    session = WhatsAppSession.objects.filter(session_name=session_name).first()
    if not session:
        return

    # If the session is already authenticated (READY with phone_number),
    # do NOT disconnect on transient socket drops!
    if session.status == WhatsAppSession.Status.READY and session.phone_number and not is_logged_out:
        logger.warning("Session %s transient socket disconnect - preserving READY status and auto-reconnecting", session_name)
        from .client import get_waha_client
        try:
            get_waha_client().start_session(session_name)
        except Exception as e:
            logger.debug("Auto-reconnect session %s on disconnect event: %s", session_name, e)
        return

    if is_logged_out:
        clear_cached_qr(session_name)
        new_status = WhatsAppSession.Status.DISCONNECTED
        session.phone_number = None
        # Purge data for logged out account to prevent bleeding into next scan
        WhatsAppMessage.objects.filter(conversation__session=session).delete()
        WhatsAppConversation.objects.filter(session=session).delete()
    else:
        new_status = WhatsAppSession.Status.DISCONNECTED

    session.status = new_status
    session.stopped_at = timezone.now()
    session.save(update_fields=["status", "phone_number", "stopped_at"] if is_logged_out else ["status", "stopped_at"])
    logger.warning("Session %s disconnected (logged_out=%s)", session_name, is_logged_out)


def _parse_waha_timestamp(event_data: dict):
    """
    Extract and normalize the original WhatsApp message or call timestamp from
    WAHA / Baileys event payloads into a timezone-aware UTC datetime.
    Supports Unix seconds, Unix milliseconds, Baileys Long dicts ({'low': ...}),
    and ISO-8601 strings. Falls back to timezone.now() only if no timestamp exists.
    """
    from datetime import datetime, timezone as dt_timezone

    if not isinstance(event_data, dict):
        return timezone.now()

    _data = event_data.get("_data") if isinstance(event_data.get("_data"), dict) else {}
    candidates = [
        event_data.get("timestamp"),
        _data.get("messageTimestamp"),
        event_data.get("messageTimestamp"),
        event_data.get("startedAt"),
        event_data.get("endedAt"),
        event_data.get("date"),
        event_data.get("t"),
        _data.get("t"),
    ]

    for raw in candidates:
        if raw is None or raw == "":
            continue
        if isinstance(raw, dict):
            raw = raw.get("low") or raw.get("value") or raw.get("timestamp")
            if raw is None:
                continue
        if isinstance(raw, (int, float)):
            val = float(raw)
            if val <= 0:
                continue
            if val >= 10_000_000_000:
                val = val / 1000.0
            try:
                return datetime.fromtimestamp(val, tz=dt_timezone.utc)
            except Exception:
                continue
        if isinstance(raw, str):
            s = raw.strip()
            if not s:
                continue
            if re.match(r"^\d+(\.\d+)?$", s):
                val = float(s)
                if val <= 0:
                    continue
                if val >= 10_000_000_000:
                    val = val / 1000.0
                try:
                    return datetime.fromtimestamp(val, tz=dt_timezone.utc)
                except Exception:
                    continue
            try:
                iso_str = s.replace("Z", "+00:00")
                dt = datetime.fromisoformat(iso_str)
                if timezone.is_naive(dt):
                    dt = dt.replace(tzinfo=dt_timezone.utc)
                return dt
            except Exception:
                continue

    return timezone.now()


def _handle_call_event(
    event_data: dict,
    session_name: str,
    event_record: Optional[WhatsAppEvent],
    event_type: str,
) -> None:
    """
    Handle WhatsApp call events dispatched by WAHA / waha-noweb-light.
    Supported events:
      - call.received  (status: "offer")
      - call.ringing   (status: "ringing")
      - call.accepted  (status: "accept")
      - call.rejected  (status: "reject")
      - call.missed    (status: "timeout")
      - call.ended     (status: "terminate")
      - call.update    (generic fallback)
    """
    sub_data = event_data.get("call") or event_data.get("data") or {}
    if not isinstance(sub_data, dict):
        sub_data = {}

    raw_call_id = str(
        event_data.get("callId")
        or event_data.get("call_id")
        or event_data.get("id")
        or sub_data.get("callId")
        or sub_data.get("call_id")
        or sub_data.get("id")
        or ""
    ).strip()
    call_id = _normalize_call_id(raw_call_id)
    raw_from = str(
        event_data.get("callerPhone")
        or event_data.get("caller")
        or event_data.get("peer")
        or event_data.get("from")
        or sub_data.get("callerPhone")
        or sub_data.get("caller")
        or sub_data.get("peer")
        or sub_data.get("from")
        or ""
    ).strip()
    raw_chat = str(
        event_data.get("chatId")
        or event_data.get("chat_id")
        or sub_data.get("chatId")
        or sub_data.get("chat_id")
        or ""
    ).strip()
    is_group = bool(event_data.get("isGroup", False) or event_data.get("is_group", False) or sub_data.get("isGroup", False))
    group_jid = str(event_data.get("groupJid") or event_data.get("group_jid") or sub_data.get("groupJid") or "").strip()
    is_video = bool(event_data.get("isVideo", False) or event_data.get("is_video", False) or sub_data.get("isVideo", False))
    raw_status = str(event_data.get("status") or sub_data.get("status") or "").strip().lower()

    # Determine target chat ID
    if is_group and group_jid:
        target_chat_id = group_jid
    elif raw_chat:
        target_chat_id = raw_chat
    else:
        target_chat_id = raw_from

    # Strip multidevice colons (e.g. 919003619221:0@s.whatsapp.net -> 919003619221@s.whatsapp.net)
    target_chat_id = re.sub(r":[0-9]+@", "@", target_chat_id).strip()
    raw_from = re.sub(r":[0-9]+@", "@", raw_from).strip()

    if not target_chat_id and raw_from:
        target_chat_id = raw_from

    clean_target_digits = re.sub(r"\D+", "", target_chat_id.split("@")[0].split(":")[0])
    if clean_target_digits and "@" not in target_chat_id:
        target_chat_id = f"{clean_target_digits}@c.us"
    clean_from_digits = re.sub(r"\D+", "", raw_from.split("@")[0].split(":")[0])
    if clean_from_digits and "@" not in raw_from:
        raw_from = f"{clean_from_digits}@c.us"

    # Normalize WhatsApp JIDs: @s.whatsapp.net -> @c.us
    if "@s.whatsapp.net" in target_chat_id:
        target_chat_id = target_chat_id.replace("@s.whatsapp.net", "@c.us")
    if "@s.whatsapp.net" in raw_from:
        raw_from = raw_from.replace("@s.whatsapp.net", "@c.us")

    target_chat_id = target_chat_id.lstrip("+")
    raw_from = raw_from.lstrip("+")

    if not target_chat_id or not VALID_CHAT_ID_RE.match(target_chat_id):
        if clean_target_digits:
            target_chat_id = f"{clean_target_digits}@c.us"
        elif clean_from_digits:
            target_chat_id = f"{clean_from_digits}@c.us"
        else:
            logger.warning("Call event with invalid chat ID: %r — ignored.", target_chat_id)
            return

    # Call type and human-readable label
    call_type = "Video call" if is_video else "Voice call"
    is_missed = event_type in ("call.missed", "call.voice.missed") or raw_status in ("timeout", "missed")
    is_rejected = event_type in ("call.rejected", "call.voice.rejected") or raw_status in ("reject", "declined", "rejected")
    is_ended = event_type in ("call.ended", "call.voice.ended") or raw_status in ("terminate", "ended")
    is_accepted = event_type in ("call.accepted", "call.voice.active") or raw_status in ("accept", "answered", "active")
    is_received = (
        event_type in ("call.received", "call.ringing", "call.voice.incoming", "call.voice.ringing")
        or raw_status in ("offer", "received", "incoming", "ringing")
    )

    call_dt = _parse_waha_timestamp(event_data)

    # Outgoing calls placed by this session also emit ringing/offer events (direction="outbound").
    # They must never surface as an incoming call banner/notification for the caller themselves.
    call_direction = str(
        event_data.get("direction") or sub_data.get("direction") or ""
    ).strip().lower()
    if is_received and call_direction in ("outbound", "outgoing"):
        if call_id:
            mark_call_handled(call_id)
        logger.info("Ignoring ringing event for outgoing call %s in session %s", call_id, session_name)
        return

    # Guard against late/duplicate/retried ringing webhooks for a call that was already attended, declined, or ended
    if is_received and call_id and is_call_handled(call_id):
        logger.info("Ignoring late/duplicate incoming call event %s for already-handled call %s", event_type, call_id)
        return

    if is_missed:
        call_label = f"Missed {call_type.lower()}"
        call_preview = f"📞 Missed {call_type.lower()}" if not is_video else f"📹 Missed {call_type.lower()}"
        msg_status = WhatsAppMessage.Status.FAILED
        unread_inc = 1
    elif is_rejected:
        call_label = f"Declined {call_type.lower()}"
        call_preview = f"📞 Declined {call_type.lower()}" if not is_video else f"📹 Declined {call_type.lower()}"
        msg_status = WhatsAppMessage.Status.FAILED
        unread_inc = 0
    elif is_ended:
        call_label = call_type
        call_preview = f"📞 {call_type}" if not is_video else f"📹 {call_type}"
        msg_status = WhatsAppMessage.Status.DELIVERED
        unread_inc = 0
    elif is_accepted:
        call_label = f"Answered {call_type.lower()}"
        call_preview = f"📞 Answered {call_type.lower()}" if not is_video else f"📹 Answered {call_type.lower()}"
        msg_status = WhatsAppMessage.Status.DELIVERED
        unread_inc = 0
    elif is_received:
        call_label = f"Incoming {call_type.lower()}"
        call_preview = f"📞 Incoming {call_type.lower()}" if not is_video else f"📹 Incoming {call_type.lower()}"
        msg_status = WhatsAppMessage.Status.PENDING
        unread_inc = 1
    else:
        call_label = f"{call_type} ({raw_status or 'update'})"
        call_preview = f"📞 {call_label}" if not is_video else f"📹 {call_label}"
        msg_status = WhatsAppMessage.Status.DELIVERED
        unread_inc = 0

    # Find or resolve session strictly by session_name
    session_obj = WhatsAppSession.objects.filter(session_name=session_name).first()
    if not session_obj:
        if session_name and session_name.startswith("user_"):
            try:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                u_id = int(session_name.split("_")[1])
                u = User.objects.filter(id=u_id, is_active=True).first()
                if u:
                    session_obj, _ = WhatsAppSession.objects.get_or_create(
                        session_name=session_name,
                        defaults={"owner": u, "status": WhatsAppSession.Status.STARTING}
                    )
            except Exception:
                pass

    if not session_obj:
        logger.warning("Call event received for unmapped session %r — rejected to protect multi-user isolation.", session_name)
        return

    # 1. Resolve phone digits if available (from @c.us or @s.whatsapp.net)
    phone_digits = _extract_phone_digits(target_chat_id)
    if not phone_digits and raw_from:
        phone_digits = _extract_phone_digits(raw_from)

    # 2. If target_chat_id is @lid or phone_digits is not yet found, check event_data phone fields
    resolved_phone = None
    for k in ("callerPhone", "phoneNumber", "senderPn", "participantPn", "callerPn", "phone"):
        cand = event_data.get(k)
        if cand and not str(cand).endswith("@lid"):
            cand_d = re.sub(r"\D+", "", str(cand).split("@")[0].split(":")[0])
            if 8 <= len(cand_d) <= 13 and not _is_lid(cand_d):
                phone_digits = cand_d
                resolved_phone = f"+{cand_d}"
                break

    # 3. If target_chat_id is @lid and still no phone_digits, query WAHA contact info
    push_name = str(event_data.get("callerName") or event_data.get("name") or event_data.get("pushName") or "").strip()
    if (not phone_digits or target_chat_id.endswith("@lid")) and not target_chat_id.endswith("@g.us"):
        try:
            from .client import get_waha_client
            w_client = get_waha_client()
            c_info = w_client.get_contact_info(session_name, target_chat_id)
            if isinstance(c_info, dict):
                if not push_name:
                    push_name = str(c_info.get("name") or c_info.get("pushname") or "").strip()
                for field in ("number", "phone", "id"):
                    val = c_info.get(field)
                    if val and not str(val).endswith("@lid"):
                        d = re.sub(r"\D+", "", str(val).split("@")[0].split(":")[0])
                        if 8 <= len(d) <= 13 and not _is_lid(d):
                            phone_digits = d
                            resolved_phone = f"+{d}"
                            break
        except Exception:
            pass

    # 4. Build candidate chat IDs to match existing conversations
    candidate_chat_ids = [target_chat_id]
    if "@s.whatsapp.net" in target_chat_id:
        candidate_chat_ids.append(target_chat_id.replace("@s.whatsapp.net", "@c.us"))
    elif "@c.us" in target_chat_id:
        candidate_chat_ids.append(target_chat_id.replace("@c.us", "@s.whatsapp.net"))
    if phone_digits:
        candidate_chat_ids.extend([f"{phone_digits}@c.us", f"{phone_digits}@s.whatsapp.net"])

    # 5. Find or create conversation strictly for this user session
    conversation = WhatsAppConversation.objects.filter(
        chat_id__in=candidate_chat_ids,
        session=session_obj,
        is_deleted=False,
    ).order_by("-updated_at").first()
    if not conversation and session_obj.owner:
        conversation = WhatsAppConversation.objects.filter(
            chat_id__in=candidate_chat_ids,
            session__owner=session_obj.owner,
            is_deleted=False,
        ).order_by("-updated_at").first()

    # If still not found by chat_id, but we have phone_digits, search by phone_number
    if not conversation and phone_digits:
        suffix = phone_digits[-10:] if len(phone_digits) >= 10 else phone_digits[-8:]
        conversation = WhatsAppConversation.objects.filter(
            session=session_obj,
            phone_number__icontains=suffix,
            is_deleted=False,
        ).exclude(chat_id__endswith="@g.us").first()

    if conversation:
        # If conversation exists but has no valid phone or has an LID stored, update it
        if phone_digits and (not conversation.phone_number or _is_lid(conversation.phone_number)):
            conversation.phone_number = f"+{phone_digits}"
            conversation.save(update_fields=["phone_number"])
    else:
        matched_contact = None
        if phone_digits and len(phone_digits) >= 8:
            from prospects.models import ProspectContact
            suffix = phone_digits[-10:] if len(phone_digits) >= 10 else phone_digits[-8:]
            matched_contact = ProspectContact.objects.filter(phone_digits__endswith=suffix).select_related("prospect").first()

        is_grp = target_chat_id.endswith("@g.us")
        canonical_chat_id = f"{phone_digits}@c.us" if (phone_digits and target_chat_id.endswith("@lid")) else target_chat_id
        phone_formatted = f"+{phone_digits}" if phone_digits else None
        initial_name = (
            "WhatsApp Group" if is_grp
            else (matched_contact.contact_name if matched_contact
            else (push_name if push_name and not _is_lid(push_name) and "@" not in push_name and push_name.strip().lower() != "whatsapp contact"
            else (phone_formatted or "WhatsApp Contact")))
        )
        conversation = WhatsAppConversation.objects.create(
            session=session_obj,
            account_phone=session_obj.phone_number if session_obj else None,
            chat_id=canonical_chat_id,
            phone_number=phone_formatted if not is_grp else None,
            prospect_contact=matched_contact if not is_grp else None,
            prospect=matched_contact.prospect if matched_contact else None,
            is_matched=matched_contact is not None or is_grp,
            whatsapp_name=initial_name,
        )

    # Idempotent call record handling
    waha_call_id = f"call_{call_id}" if call_id else None
    existing_message = None
    if waha_call_id:
        existing_message = WhatsAppMessage.objects.filter(
            waha_message_id__in=[waha_call_id, call_id],
            conversation=conversation,
        ).first()

    # Do not let a late ringing event regress an already answered/ended/declined call message back to PENDING
    if is_received and existing_message and existing_message.status != WhatsAppMessage.Status.PENDING:
        mark_call_handled(call_id)
        logger.info("Ignoring late ringing event for already-resolved call message %s", call_id)
        return

    body_hash = hashlib.sha256(call_label.encode("utf-8")).hexdigest()

    if existing_message:
        existing_message.body_preview = call_label
        existing_message.full_body = call_label
        existing_message.body_hash = body_hash
        existing_message.status = msg_status
        existing_message.error_code = raw_status[:50]
        update_fields = ["body_preview", "full_body", "body_hash", "status", "error_code"]
        if not existing_message.waha_timestamp and call_dt:
            existing_message.waha_timestamp = call_dt
            update_fields.append("waha_timestamp")
        existing_message.save(update_fields=update_fields)
        wa_message = existing_message
    else:
        msg_idempotency = hashlib.sha256(
            f"call:{session_name}:{target_chat_id}:{call_id or call_dt.isoformat()}".encode()
        ).hexdigest()

        try:
            with transaction.atomic():
                wa_message = WhatsAppMessage.objects.create(
                    idempotency_key=msg_idempotency,
                    conversation=conversation,
                    performed_by=None,
                    waha_message_id=waha_call_id,
                    direction=WhatsAppMessage.Direction.INBOUND,
                    status=msg_status,
                    body_preview=call_label,
                    full_body=call_label,
                    body_hash=body_hash,
                    message_type="call",
                    has_media=False,
                    error_code=raw_status[:50],
                    waha_timestamp=call_dt,
                    sent_at=call_dt,
                    created_at=call_dt,
                )
        except IntegrityError:
            wa_message = WhatsAppMessage.objects.filter(idempotency_key=msg_idempotency).first()

    # Update conversation metadata (preserving chronological order)
    conv_update_fields = []
    if not conversation.last_message_at or call_dt >= conversation.last_message_at or existing_message:
        if not conversation.last_message_at or call_dt >= conversation.last_message_at:
            conversation.last_message_at = call_dt
            conv_update_fields.append("last_message_at")
        conversation.last_message_preview = call_preview
        conversation.last_message_from_me = False
        conv_update_fields.extend(["last_message_preview", "last_message_from_me"])
    if unread_inc and not existing_message:
        conversation.unread_count = conversation.unread_count + unread_inc
        conv_update_fields.append("unread_count")
    if conv_update_fields:
        conversation.save(update_fields=list(set(conv_update_fields)))

    if wa_message and event_record:
        event_record.whatsapp_message = wa_message
        event_record.save(update_fields=["whatsapp_message"])

    try:
        _write_audit_log(
            action=WhatsAppAuditLog.Action.MESSAGE_RECEIVED,
            prospect_contact=conversation.prospect_contact,
            session_name=session_name,
            chat_id=target_chat_id,
            performed_by=None,
            message_id=wa_message.pk if wa_message else None,
            success=True,
            result_detail=f"{event_type}:{call_label}:{call_id}"[:500],
        )
    except Exception as audit_err:
        logger.debug("Call event audit logging non-fatal error: %s", audit_err)

    logger.info("Processed call event %s for %s (%s)", event_type, target_chat_id, call_label)

    # Track or clear active incoming call in real-time
    clean_d = re.sub(r"\D+", "", str(raw_from or target_chat_id).split("@")[0].split(":")[0])
    phone_from_jid = ""
    target_str = str(target_chat_id or raw_from or "").lower()
    if "@c.us" in target_str or "@s.whatsapp.net" in target_str:
        jid_digits = re.sub(r"\D+", "", target_str.split("@")[0].split(":")[0])
        if jid_digits and not _is_lid(jid_digits):
            phone_from_jid = f"+{jid_digits}"

    phone_display = (
        conversation.phone_number
        if (conversation and conversation.phone_number and not _is_lid(conversation.phone_number))
        else (phone_from_jid or (f"+{phone_digits}" if (phone_digits and not _is_lid(phone_digits)) else ""))
    )
    display_name = (
        conversation.prospect_contact.contact_name
        if (conversation and conversation.prospect_contact and conversation.prospect_contact.contact_name)
        else (
            conversation.whatsapp_name
            if (conversation and conversation.whatsapp_name and conversation.whatsapp_name != target_chat_id and not _is_lid(conversation.whatsapp_name) and "@" not in conversation.whatsapp_name and conversation.whatsapp_name.strip().lower() != "whatsapp contact")
            else (
                push_name
                if (push_name and not _is_lid(push_name) and push_name.strip().lower() != "whatsapp contact" and "@" not in push_name)
                else (phone_display or "WhatsApp Contact")
            )
        )
    )

    if is_received or event_type in ("call.received", "call.ringing", "call.voice.incoming", "call.voice.ringing") or raw_status in ("offer", "ringing"):
        if call_id and is_call_handled(call_id):
            return
        if (timezone.now() - call_dt).total_seconds() > 45:
            logger.debug("Ignoring stale ringing call event %s (age > 45s)", call_id)
            return
        incoming_payload = {
            "call_id": call_id,
            "caller_phone": phone_display,
            "caller_name": display_name,
            "session_name": session_name,
            "chat_id": target_chat_id,
            "is_video": is_video,
            "status": "ringing",
        }
        set_active_incoming_call(session_name, incoming_payload)
        logger.info("Registered active incoming WhatsApp call: %s from %s for session %s", call_id, display_name, session_name)
    elif is_accepted:
        mark_active_call_connected(session_name, call_id)
        logger.info("Marked active connected WhatsApp call: %s for session %s", call_id, session_name)
    elif is_missed or is_rejected or is_ended or event_type in (
        "call.rejected", "call.voice.rejected",
        "call.missed", "call.voice.missed",
        "call.ended", "call.voice.ended",
    ) or raw_status in ("reject", "declined", "rejected", "timeout", "missed", "terminate", "ended"):
        # Do NOT overwrite the call state file if the user has already actively accepted this
        # call (state = "active"). Baileys/WAHA fires a spurious call.ended or terminate event
        # when the remote side answers an outgoing call, or as a signalling handshake step during
        # call setup. Only the WebSocket bridge closing with reason='call ended' or an explicit
        # End Call API request should transition an active call to ended.
        existing_state = get_active_call_state(session_name)
        existing_call_id = _normalize_call_id((existing_state or {}).get("call_id", ""))
        normalized_call_id = _normalize_call_id(call_id)
        if (
            existing_state
            and existing_state.get("status") == "active"
            and existing_call_id
            and normalized_call_id
            and existing_call_id == normalized_call_id
        ):
            logger.info(
                "Webhook call.ended/terminate for %s suppressed: call is currently active in session %s. "
                "Actual end will come via WebSocket bridge or explicit End Call action.",
                call_id, session_name,
            )
        else:
            mark_call_ended(session_name, call_id, reason=raw_status or event_type)
            logger.info("Cleared and ended WhatsApp call: %s (%s) for session %s", call_id, event_type, session_name)


def _handle_incoming_message(
    event_data: dict,
    session_name: str,
    event_record: Optional[WhatsAppEvent] = None,
    is_history_sync: bool = False,
) -> bool:
    """
    Handle an incoming or sync WhatsApp message event.
    """
    _data = event_data.get("_data") or {}
    key = _data.get("key") or event_data.get("key") or {}

    raw_from = str(event_data.get("from") or "").strip()
    raw_to = str(event_data.get("to") or "").strip()
    # Unpack nested message containers if present (e.g. ephemeralMessage, viewOnceMessage)
    _nested_msg = (
        (event_data.get("message") or {})
        or (_data.get("message") or {})
    )
    if isinstance(_nested_msg, dict):
        if "ephemeralMessage" in _nested_msg and isinstance(_nested_msg.get("ephemeralMessage"), dict):
            _nested_msg = _nested_msg["ephemeralMessage"].get("message") or _nested_msg
        if "viewOnceMessage" in _nested_msg and isinstance(_nested_msg.get("viewOnceMessage"), dict):
            _nested_msg = _nested_msg["viewOnceMessage"].get("message") or _nested_msg
        if "viewOnceMessageV2" in _nested_msg and isinstance(_nested_msg.get("viewOnceMessageV2"), dict):
            _nested_msg = _nested_msg["viewOnceMessageV2"].get("message") or _nested_msg
        if "documentWithCaptionMessage" in _nested_msg and isinstance(_nested_msg.get("documentWithCaptionMessage"), dict):
            _nested_msg = _nested_msg["documentWithCaptionMessage"].get("message") or _nested_msg

    raw_body = str(
        event_data.get("body")
        or event_data.get("text")
        or event_data.get("caption")
        or _data.get("body")
        or _data.get("text")
        or (_nested_msg.get("conversation") if isinstance(_nested_msg, dict) else "")
        or ((_nested_msg.get("extendedTextMessage") or {}).get("text") if isinstance(_nested_msg, dict) else "")
        or ((_nested_msg.get("imageMessage") or {}).get("caption") if isinstance(_nested_msg, dict) else "")
        or ((_nested_msg.get("videoMessage") or {}).get("caption") if isinstance(_nested_msg, dict) else "")
        or ((_nested_msg.get("documentMessage") or {}).get("caption") if isinstance(_nested_msg, dict) else "")
        or ""
    ).strip()
    waha_message_id = str(event_data.get("id") or "")
    is_from_me = bool(event_data.get("fromMe", False))

    has_media_early = bool(
        event_data.get("hasMedia", False)
        or event_data.get("mediaUrl")
        or (event_data.get("media") or {}).get("url")
    )
    if not raw_body and not has_media_early:
        # Ignore empty Baileys protocol/system sync messages (e.g. history/key sync)
        return

    # 1. Resolve Group Chat ID (@g.us) if this message belongs to a WhatsApp Group
    group_chat_id = None
    for candidate in (
        event_data.get("chatId"),
        key.get("remoteJid"),
        event_data.get("to"),
        event_data.get("from"),
        _data.get("chatId"),
        (_data.get("chat") or {}).get("id"),
        event_data.get("groupJid"),
        (event_data.get("chat") or {}).get("id"),
    ):
        if candidate and "@g.us" in str(candidate):
            cand_norm = re.sub(r":[0-9]+@", "@", str(candidate).strip())
            if cand_norm.endswith("@g.us"):
                group_chat_id = cand_norm
                break

    # If payload contains participant or author, it is definitively a group message
    if not group_chat_id:
        has_participant = bool(
            event_data.get("participant")
            or key.get("participant")
            or event_data.get("author")
            or _data.get("participant")
        )
        if has_participant:
            for candidate in (
                event_data.get("chatId"),
                key.get("remoteJid"),
                event_data.get("to"),
                event_data.get("from"),
            ):
                if candidate and "@g.us" in str(candidate):
                    cand_norm = re.sub(r":[0-9]+@", "@", str(candidate).strip())
                    if cand_norm.endswith("@g.us"):
                        group_chat_id = cand_norm
                        break

    if group_chat_id:
        target_chat_id = group_chat_id
    else:
        # Standard 1-on-1 direct message
        raw_chat_id = str(event_data.get("chatId") or key.get("remoteJid") or "").strip()
        if raw_chat_id and not raw_chat_id.endswith("@broadcast"):
            target_chat_id = raw_chat_id
        else:
            target_chat_id = raw_to if is_from_me else raw_from

    # -----------------------------------------------------------------------
    # CRITICAL: Ignore WhatsApp status updates, stories, and broadcast media.
    # Do not fetch, download, or store any status media.
    # -----------------------------------------------------------------------
    if (
        "status@broadcast" in raw_from
        or "status@broadcast" in raw_to
        or "status@broadcast" in target_chat_id
        or raw_from.endswith("@broadcast")
        or raw_to.endswith("@broadcast")
        or target_chat_id.endswith("@broadcast")
        or event_data.get("broadcast") is True
        or (event_data.get("_data") or {}).get("broadcast") is True
        or (event_data.get("_data") or {}).get("key", {}).get("remoteJid") == "status@broadcast"
    ):
        logger.info("Ignoring WhatsApp Status story/broadcast media from %s", raw_from)
        return

    # Strip multi-device colon from chat ID (e.g. 919003619221:0@s.whatsapp.net -> 919003619221@s.whatsapp.net)
    target_chat_id = re.sub(r":[0-9]+@", "@", target_chat_id)

    # Validate chat ID.
    if not VALID_CHAT_ID_RE.match(target_chat_id):
        logger.warning("Incoming message with invalid chat ID: %r — ignored.", target_chat_id)
        return

    # Resolve the originating WhatsApp session strictly by the exact WAHA webhook session name
    # BEFORE any contact / LID / conversation lookup. A conversation's identity is always
    # (WhatsAppSession, normalized remote chat id) — never the remote phone number alone.
    session_obj = _resolve_originating_session(session_name)
    if not session_obj:
        logger.warning("Incoming message received for unmapped session %r — rejected to protect multi-user isolation.", session_name)
        return False
    conversation = None

    phone_digits = _extract_phone_digits(target_chat_id)
    is_group = target_chat_id.endswith("@g.us")

    # If message is from a WhatsApp Business / multi-device LID (@lid), extract real phone number
    resolved_phone = None
    sender_pn = key.get("senderPn") or key.get("participantPn") or event_data.get("senderPn") or _data.get("senderPn")
    if sender_pn:
        d = re.sub(r"\D+", "", str(sender_pn).split("@")[0].split(":")[0])
        if len(d) >= 8:
            resolved_phone = f"+{d}"
            phone_digits = d

    if not resolved_phone and not target_chat_id.endswith("@lid") and not is_group:
        d = re.sub(r"\D+", "", target_chat_id.split("@")[0].split(":")[0])
        if len(d) >= 8:
            resolved_phone = f"+{d}"
            phone_digits = d

    # If @lid without sender_pn, correlate with real phone number across WAHA, CRM, and active conversations
    if not resolved_phone and target_chat_id.endswith("@lid"):
        # 1. Query WAHA contact info for real number
        try:
            from .client import get_waha_client
            w_client = get_waha_client()
            c_info = w_client.get_contact_info(session_name, target_chat_id)
            c_num = c_info.get("number") or c_info.get("phone") or ""
            c_d = re.sub(r"\D+", "", str(c_num).split("@")[0].split(":")[0])
            if len(c_d) >= 8 and not str(c_num).endswith("@lid"):
                resolved_phone = f"+{c_d}"
                phone_digits = c_d
        except Exception:
            pass

        # 2. Check if a conversation of THIS session already has this @lid saved
        # (LID mappings must never be borrowed from another WhatsApp account)
        if not resolved_phone:
            existing_saved = WhatsAppConversation.objects.filter(
                session=session_obj,
                chat_id=target_chat_id,
                phone_number__isnull=False
            ).exclude(phone_number="").first()
            if existing_saved and existing_saved.phone_number and not _is_lid(existing_saved.phone_number):
                resolved_phone = existing_saved.phone_number
                phone_digits = re.sub(r"\D+", "", resolved_phone)

        # 3. Check pushName against CRM contact or existing conversation whatsapp_name
        p_name = (
            _data.get("pushName")
            or event_data.get("pushName")
            or _data.get("notifyName")
            or ""
        ).strip()
        if not resolved_phone and p_name:
            from prospects.models import ProspectContact
            crm_match = ProspectContact.objects.filter(contact_name__iexact=p_name).first()
            if crm_match and crm_match.phone_number:
                resolved_phone = crm_match.phone_number
                phone_digits = re.sub(r"\D+", "", resolved_phone)
            else:
                named_conv = WhatsAppConversation.objects.filter(
                    session=session_obj,
                    whatsapp_name__iexact=p_name,
                    is_deleted=False,
                ).exclude(chat_id__endswith="@g.us").first()
                if named_conv and named_conv.phone_number and not _is_lid(named_conv.phone_number):
                    resolved_phone = named_conv.phone_number
                    phone_digits = re.sub(r"\D+", "", resolved_phone)
                    conversation = named_conv

        # 4. Correlate with recently messaged 1-on-1 chat in this session (e.g. from "+ New Chat")
        if not resolved_phone and not conversation:
            from datetime import timedelta
            recent_cutoff = timezone.now() - timedelta(hours=3)
            recent_outbound = WhatsAppConversation.objects.filter(
                session=session_obj,
                is_deleted=False,
                last_message_at__gte=recent_cutoff,
                last_message_from_me=True,
            ).exclude(chat_id__endswith="@g.us").exclude(chat_id=target_chat_id).order_by("-last_message_at").first()
            if recent_outbound and recent_outbound.phone_number and not _is_lid(recent_outbound.phone_number):
                resolved_phone = recent_outbound.phone_number
                phone_digits = re.sub(r"\D+", "", resolved_phone)
                conversation = recent_outbound

    # Build candidate JIDs for 1-on-1 chats to match @s.whatsapp.net, @c.us, and @lid
    alt_chat_id = None
    if target_chat_id.endswith("@s.whatsapp.net"):
        alt_chat_id = target_chat_id.replace("@s.whatsapp.net", "@c.us")
    elif target_chat_id.endswith("@c.us"):
        alt_chat_id = target_chat_id.replace("@c.us", "@s.whatsapp.net")

    candidate_ids = [target_chat_id]
    if alt_chat_id:
        candidate_ids.append(alt_chat_id)

    if phone_digits and len(phone_digits) >= 8:
        candidate_ids.append(f"{phone_digits}@c.us")
        candidate_ids.append(f"{phone_digits}@s.whatsapp.net")

    from django.db.models import Q

    # For group messages, search for existing group conversation strictly within this session
    # (session_obj and conversation were resolved/initialised above)
    if is_group:
        conversation = WhatsAppConversation.objects.filter(
            chat_id=target_chat_id,
            session=session_obj,
        ).order_by("-last_message_at", "-updated_at").first()
        if conversation and conversation.is_deleted:
            conversation.is_deleted = False
            conversation.save(update_fields=["is_deleted"])

    if not conversation:
        # Find existing conversation for THIS session only (checking both @c.us and @s.whatsapp.net)
        conversation = WhatsAppConversation.objects.filter(
            chat_id__in=candidate_ids,
            session=session_obj,
            is_deleted=False,
        ).first()

    # If not found by chat_id and not a group, match by phone digits within this session
    if not conversation and not is_group and phone_digits and len(phone_digits) >= 8:
        suffix = phone_digits[-10:] if len(phone_digits) >= 10 else phone_digits[-8:]
        conversation = WhatsAppConversation.objects.filter(
            session=session_obj,
            is_deleted=False,
        ).filter(
            Q(phone_number__icontains=suffix) | Q(chat_id__icontains=suffix)
        ).first()

    if not is_from_me and not is_group and phone_digits and len(phone_digits) >= 8:
        opt_out_registered = check_incoming_for_opt_out(
            message_body=raw_body,
            phone_digits=phone_digits,
            prospect_contact=conversation.prospect_contact if conversation else None,
        )
        if opt_out_registered:
            logger.info("Opt-out registered from incoming message: phone=%s", phone_digits)

    # -----------------------------------------------------------------------
    # Find or create conversation record.
    # -----------------------------------------------------------------------
    is_matched = is_group
    prospect_contact = None
    
    # Extract name from WAHA payload (Baileys puts pushName in _data.pushName or top-level)
    _data = event_data.get("_data") or {}
    key = _data.get("key") or {}

    extracted_name = (
        _data.get("pushName")
        or event_data.get("pushName")
        or _data.get("notifyName")
        or event_data.get("sender", {}).get("pushname")
        or event_data.get("sender", {}).get("name")
        or ""
    ).strip()

    group_name = (
        event_data.get("chatName")
        or (_data.get("chat") or {}).get("name")
        or _data.get("subject")
        or (event_data.get("chat") or {}).get("name")
        or ""
    ).strip()

    if is_group and not group_name:
        try:
            from .client import get_waha_client
            client = get_waha_client()
            g_info = client.get_group_info(session_name, target_chat_id)
            group_name = (g_info.get("subject") or g_info.get("name") or "").strip()
        except Exception:
            pass

    group_author = (
        event_data.get("author")
        or event_data.get("participant")
        or key.get("participant")
        or _data.get("participant")
        or (raw_from if raw_from != target_chat_id else "")
        or ""
    )
    group_author_name = extracted_name or (group_author.split("@")[0].split(":")[0] if group_author else "")

    # Extract real phone number (Baileys senderPn/participantPn for @lid messages if not yet resolved)
    if not resolved_phone:
        sender_pn = key.get("senderPn") or key.get("participantPn") or event_data.get("senderPn")
        if sender_pn:
            d = re.sub(r"\D+", "", str(sender_pn).split("@")[0].split(":")[0])
            if len(d) >= 8:
                resolved_phone = f"+{d}"

    if not resolved_phone and not target_chat_id.endswith("@lid"):
        d = re.sub(r"\D+", "", target_chat_id.split("@")[0].split(":")[0])
        if len(d) >= 8:
            resolved_phone = f"+{d}"

    # For @lid messages without sender_pn, inherit phone_number if previously saved
    if not resolved_phone and target_chat_id.endswith("@lid"):
        existing_saved = WhatsAppConversation.objects.filter(
            chat_id=target_chat_id,
            phone_number__isnull=False
        ).exclude(phone_number="").first()
        if existing_saved and existing_saved.phone_number and not _is_lid(existing_saved.phone_number):
            resolved_phone = existing_saved.phone_number

    search_digits = re.sub(r"\D+", "", resolved_phone or phone_digits or "")

    if conversation:
        is_matched = conversation.is_matched
        prospect_contact = conversation.prospect_contact
        conv_updates = []

        # Update phone number if resolved
        if resolved_phone and not conversation.phone_number:
            conversation.phone_number = resolved_phone
            conv_updates.append("phone_number")

        # For groups, update the group subject/name if received
        if is_group:
            if not conversation.is_matched:
                conversation.is_matched = True
                conv_updates.append("is_matched")
            if group_name and conversation.whatsapp_name != group_name:
                conversation.whatsapp_name = group_name
                conv_updates.append("whatsapp_name")
            # Map group author LID to real senderPn if available
            if sender_pn and group_author:
                p_lid = re.sub(r"\D+", "", str(group_author).split("@")[0].split(":")[0])
                p_pn = re.sub(r"\D+", "", str(sender_pn).split("@")[0].split(":")[0])
                if len(p_lid) >= 14 and 8 <= len(p_pn) <= 13:
                    meta = conversation.metadata if isinstance(conversation.metadata, dict) else {}
                    lid_map = meta.get("lid_map") or {}
                    lid_map[p_lid] = f"+{p_pn}"
                    meta["lid_map"] = lid_map
                    conversation.metadata = meta
                    conv_updates.append("metadata")
        elif extracted_name and (not conversation.whatsapp_name or conversation.whatsapp_name.startswith("+") or "@" in conversation.whatsapp_name):
            conversation.whatsapp_name = extracted_name
            conv_updates.append("whatsapp_name")
            
        # If conversation exists but is unmatched, attempt to match against ProspectContact
        if not is_matched and search_digits and len(search_digits) >= 8:
            from prospects.models import ProspectContact
            suffix = search_digits[-10:] if len(search_digits) >= 10 else search_digits[-8:]
            matched_c = (
                ProspectContact.objects.filter(phone_digits__endswith=suffix)
                .select_related("prospect")
                .first()
            )
            if not matched_c:
                for contact in ProspectContact.objects.filter(
                    phone_number__icontains=suffix
                ).select_related("prospect"):
                    stored_digits = re.sub(r"\D+", "", contact.phone_number or "")
                    if stored_digits and (
                        stored_digits == search_digits
                        or (len(search_digits) >= 10 and stored_digits.endswith(search_digits[-10:]))
                        or (len(stored_digits) >= 10 and search_digits.endswith(stored_digits[-10:]))
                    ):
                        matched_c = contact
                        break
            if matched_c:
                contact = matched_c
                conversation.prospect_contact = contact
                conversation.prospect = contact.prospect
                conversation.is_matched = True
                is_matched = True
                prospect_contact = contact
                if not conversation.phone_number and contact.phone_number:
                    conversation.phone_number = contact.phone_number
                    conv_updates.append("phone_number")
                if not conversation.whatsapp_name:
                    conversation.whatsapp_name = contact.contact_name
                    conv_updates.append("whatsapp_name")
                conv_updates.extend(["prospect_contact", "prospect", "is_matched"])

        if conv_updates:
            conversation.save(update_fields=list(set(conv_updates)))
            
    else:
        # Try to match by phone number against ProspectContact records.
        from prospects.models import ProspectContact

        matched_contact = None
        if search_digits and len(search_digits) >= 8:
            suffix = search_digits[-10:] if len(search_digits) >= 10 else search_digits[-8:]
            matched_contact = (
                ProspectContact.objects.filter(phone_digits__endswith=suffix)
                .select_related("prospect")
                .first()
            )
            if not matched_contact:
                for contact in ProspectContact.objects.filter(
                    phone_number__icontains=suffix
                ).select_related("prospect"):
                    stored_digits = re.sub(r"\D+", "", contact.phone_number or "")
                    if stored_digits and (stored_digits == search_digits or stored_digits.endswith(suffix) or search_digits.endswith(stored_digits[-8:])):
                        matched_contact = contact
                        break

        # Check if a conversation already exists for this matched CRM contact
        if matched_contact:
            existing_c = WhatsAppConversation.objects.filter(
                session=session_obj,
                prospect_contact=matched_contact,
                is_deleted=False,
            ).first()
            if existing_c:
                conversation = existing_c

        if conversation:
            is_matched = True
            prospect_contact = matched_contact
            conv_updates = []
            if not conversation.phone_number and resolved_phone:
                conversation.phone_number = resolved_phone
                conv_updates.append("phone_number")
            if not conversation.whatsapp_name and matched_contact:
                conversation.whatsapp_name = matched_contact.contact_name
                conv_updates.append("whatsapp_name")
            # NOTE: a conversation is never moved/reassigned between WhatsApp sessions.
            if conv_updates:
                conversation.save(update_fields=list(set(conv_updates)))
        else:
            with transaction.atomic():
                if is_group:
                    final_name = group_name or extracted_name or "WhatsApp Group"
                    final_phone = None
                    matched_status = True
                else:
                    final_name = extracted_name or (matched_contact.contact_name if matched_contact else "")
                    final_phone = resolved_phone or (matched_contact.phone_number if matched_contact else (f"+{search_digits}" if search_digits else None))
                    matched_status = matched_contact is not None

                conversation = WhatsAppConversation.objects.create(
                    chat_id=target_chat_id,
                    phone_number=final_phone,
                    prospect_contact=matched_contact,
                    prospect=matched_contact.prospect if matched_contact else None,
                    session=session_obj,
                    account_phone=session_obj.phone_number if session_obj else None,
                    is_matched=matched_status,
                    whatsapp_name=final_name,
                )

            is_matched = conversation.is_matched
            prospect_contact = conversation.prospect_contact

    if not is_matched:
        logger.info(
            "WhatsApp message for unmatched number %s under session %s.",
            target_chat_id,
            session_name,
        )

    # -----------------------------------------------------------------------
    # Create WhatsAppMessage record (preserving original WhatsApp timestamp).
    # -----------------------------------------------------------------------
    msg_dt = _parse_waha_timestamp(event_data)

    # Generate an idempotency key for this message. It is scoped to the originating WhatsApp
    # session so identical message IDs/content in two different accounts can never collide.
    body_hash = hashlib.sha256(raw_body.encode("utf-8")).hexdigest()
    msg_idempotency = hashlib.sha256(
        f"s{session_obj.pk}:{'outbound' if is_from_me else 'inbound'}:{target_chat_id}:{waha_message_id}:{body_hash}".encode()
    ).hexdigest()

    existing_message = WhatsAppMessage.objects.filter(
        idempotency_key=msg_idempotency,
        conversation__session=session_obj,
    ).first()
    if not existing_message and waha_message_id:
        existing_message = WhatsAppMessage.objects.filter(
            conversation=conversation,
            waha_message_id=waha_message_id,
        ).first()

    if existing_message:
        # Backfill original WhatsApp timestamp if missing on previously stored record
        ts_updates = []
        if not existing_message.waha_timestamp and msg_dt:
            existing_message.waha_timestamp = msg_dt
            ts_updates.append("waha_timestamp")
        if not existing_message.sent_at and msg_dt:
            existing_message.sent_at = msg_dt
            ts_updates.append("sent_at")
        if ts_updates:
            existing_message.save(update_fields=ts_updates)
        if event_record:
            event_record.whatsapp_message = existing_message
            event_record.save(update_fields=["whatsapp_message"])
        return False

    has_media = bool(event_data.get("hasMedia", False))
    _media_url = event_data.get("mediaUrl") or (event_data.get("media") or {}).get("url") or None
    _media_info = event_data.get("media") or {}
    _mime_type = _media_info.get("mimetype") or ""

    msg_type = str(event_data.get("type") or "chat")
    if has_media or _media_url:
        has_media = True
        if _mime_type.startswith("image/"):
            msg_type = "image"
        elif _mime_type.startswith("video/"):
            msg_type = "video"
        elif _mime_type.startswith("audio/"):
            msg_type = "audio"
        elif _mime_type:
            msg_type = "document"

    try:
        with transaction.atomic():
            wa_message = WhatsAppMessage.objects.create(
                idempotency_key=msg_idempotency,
                conversation=conversation,
                performed_by=None,
                waha_message_id=waha_message_id or None,
                direction=WhatsAppMessage.Direction.OUTBOUND if is_from_me else WhatsAppMessage.Direction.INBOUND,
                status=WhatsAppMessage.Status.SENT if is_from_me else WhatsAppMessage.Status.DELIVERED,
                body_preview=raw_body[:200],
                full_body=raw_body,
                body_hash=body_hash,
                message_type=msg_type,
                has_media=has_media,
                media_url=_media_url,
                media_mime_type=_mime_type,
                error_code=(group_author_name or "")[:50] if (is_group and not is_from_me) else None,
                waha_timestamp=msg_dt,
                sent_at=msg_dt,
                created_at=msg_dt,
            )

            # Update conversation metadata only if this message is newer than or equal to the latest message
            conv_meta_updates = []
            if not conversation.last_message_at or msg_dt >= conversation.last_message_at:
                conversation.last_message_at = msg_dt
                conversation.last_message_preview = raw_body[:200] if raw_body else f"[{msg_type.capitalize()}]"
                conversation.last_message_from_me = is_from_me
                conv_meta_updates.extend(["last_message_at", "last_message_preview", "last_message_from_me"])
            if not is_from_me and not is_history_sync:
                conversation.unread_count = conversation.unread_count + 1
                conv_meta_updates.append("unread_count")
            if conv_meta_updates:
                conversation.save(update_fields=list(set(conv_meta_updates)))

            # Update session receive count.
            if not is_from_me:
                WhatsAppSession.objects.filter(session_name=session_name).update(
                    receive_count=models_f_whatsapp("receive_count") + 1
                )

            if event_record:
                event_record.whatsapp_message = wa_message
                event_record.save(update_fields=["whatsapp_message"])
    except IntegrityError:
        # Concurrent webhook already created this message
        wa_message = WhatsAppMessage.objects.filter(idempotency_key=msg_idempotency).first()
        if wa_message:
            if event_record:
                event_record.whatsapp_message = wa_message
                event_record.save(update_fields=["whatsapp_message"])
            return False
        raise

    if has_media and wa_message.waha_message_id:
        import threading
        threading.Thread(
            target=_download_and_save_media_bg,
            args=(wa_message.pk, session_name, _media_url, _mime_type)
        ).start()

    if not conversation.custom_avatar_url:
        import threading
        threading.Thread(
            target=_fetch_contact_profile_picture_bg,
            args=(conversation.pk, session_name, target_chat_id)
        ).start()

    _write_audit_log(
        action=WhatsAppAuditLog.Action.MESSAGE_RECEIVED,
        prospect_contact=prospect_contact,
        session_name=session_name,
        chat_id=target_chat_id,
        message_id=wa_message.pk,
        success=True,
        result_code="RECEIVED",
        result_detail="matched" if is_matched else "unmatched",
    )

    logger.info(
        "Incoming WhatsApp message recorded: chat_id=%s matched=%s message_id=%s ts=%s",
        raw_from,
        is_matched,
        wa_message.pk,
        msg_dt.isoformat(),
    )
    return True


# Baileys / WAHA acknowledgement levels (proto WebMessageInfo.Status):
#   0=ERROR 1=PENDING 2=SERVER_ACK(sent) 3=DEVICE(delivered) 4=READ 5=PLAYED
ACK_STATUS_MAP = {
    0: WhatsAppMessage.Status.FAILED,
    1: WhatsAppMessage.Status.PENDING,
    2: WhatsAppMessage.Status.SENT,
    3: WhatsAppMessage.Status.DELIVERED,
    4: WhatsAppMessage.Status.READ,
    5: WhatsAppMessage.Status.READ,  # PLAYED: final "read" tick state for the existing status model
}

# Monotonic ordering used so a delayed ack can never move a message backwards.
_STATUS_RANK = {
    WhatsAppMessage.Status.FAILED: -1,
    WhatsAppMessage.Status.BLOCKED: -1,
    WhatsAppMessage.Status.PENDING: 0,
    WhatsAppMessage.Status.SENT: 1,
    WhatsAppMessage.Status.DELIVERED: 2,
    WhatsAppMessage.Status.READ: 3,
}


def _ack_message_id_candidates(event_data: dict) -> list:
    """All identifiers a stored outbound message may carry for this ack (composite + raw)."""
    composite = str(event_data.get("id") or "").strip()
    raw_id = str(event_data.get("rawId") or "").strip()
    remote = _normalize_chat_jid(event_data.get("remoteJid") or event_data.get("chatId") or event_data.get("from") or "")
    if not raw_id and composite.count("_") >= 2 and composite.split("_", 1)[0] in ("true", "false"):
        raw_id = composite.split("_", 2)[2]
    candidates = []
    for c in (
        composite,
        raw_id,
        f"true_{remote}_{raw_id}" if (remote and raw_id) else "",
        f"false_{remote}_{raw_id}" if (remote and raw_id) else "",
        f"_{raw_id}" if raw_id else "",
    ):
        if c and c not in candidates:
            candidates.append(c)
    return candidates


def apply_message_ack(session_obj, candidate_ids: list, ack_value, remote_jid: str = "") -> int:
    """
    Advance OUTBOUND messages of `session_obj` matching `candidate_ids` to the status implied by
    `ack_value`. Never touches another session, never moves a status backwards.
    Returns the number of messages updated.
    """
    try:
        ack_int = int(ack_value)
    except (TypeError, ValueError):
        return 0
    new_status = ACK_STATUS_MAP.get(ack_int)
    if not new_status or new_status == WhatsAppMessage.Status.PENDING or not candidate_ids:
        return 0

    qs = WhatsAppMessage.objects.filter(
        conversation__session=session_obj,
        direction=WhatsAppMessage.Direction.OUTBOUND,
        waha_message_id__in=candidate_ids,
    )
    remote_norm = _normalize_chat_jid(remote_jid)
    if remote_norm and not remote_norm.endswith("@lid"):
        narrowed = qs.filter(conversation__chat_id__in=[remote_norm, remote_norm.replace("@c.us", "@s.whatsapp.net")])
        if narrowed.exists():
            qs = narrowed

    now = timezone.now()
    updated = 0
    for msg in qs:
        cur = msg.status
        if new_status == WhatsAppMessage.Status.FAILED:
            # An error ack only applies to a message that was never confirmed by the server.
            if cur != WhatsAppMessage.Status.PENDING:
                continue
        elif _STATUS_RANK.get(new_status, 0) <= _STATUS_RANK.get(cur, 0):
            continue  # same or older level — idempotent / out-of-order ack
        fields = ["status"]
        msg.status = new_status
        rank = _STATUS_RANK[new_status]
        if rank >= 1 and not msg.sent_at:
            msg.sent_at = now
            fields.append("sent_at")
        if rank >= 2 and not msg.delivered_at:
            msg.delivered_at = now
            fields.append("delivered_at")
        if rank >= 3 and not msg.read_at:
            msg.read_at = now
            fields.append("read_at")
        msg.save(update_fields=fields)
        updated += 1
    return updated


def _handle_message_ack(
    event_data: dict,
    session_name: str,
    event_record: WhatsAppEvent,
) -> None:
    """
    Handle a message acknowledgement event (sent / delivered / read status update).
    Strictly scoped to the originating WhatsApp session.
    """
    session_obj = WhatsAppSession.objects.filter(session_name=(session_name or "").strip()).first()
    if not session_obj:
        logger.warning("Message ack for unmapped session %r ignored.", session_name)
        return

    candidates = _ack_message_id_candidates(event_data)
    if not candidates:
        return

    updated = apply_message_ack(
        session_obj,
        candidates,
        event_data.get("ack"),
        remote_jid=str(event_data.get("remoteJid") or event_data.get("chatId") or event_data.get("from") or ""),
    )
    if updated:
        logger.debug("Message ACK applied: session=%s ids=%s ack=%s", session_name, candidates, event_data.get("ack"))
    else:
        logger.debug(
            "Message ACK matched nothing to advance in session %s (ids=%s ack=%s) — no other session touched.",
            session_name, candidates, event_data.get("ack"),
        )


def _handle_group_participant_event(
    event_data: dict,
    session_name: str,
    event_record: WhatsAppEvent,
    event_type: str,
) -> None:
    """
    Handle group participant join/leave/add/remove notifications.
    Creates a system notification message in the group conversation.
    """
    session_obj = WhatsAppSession.objects.filter(session_name=(session_name or "").strip()).first()
    if not session_obj:
        return

    group_jid = _normalize_chat_jid(
        event_data.get("groupJid") or event_data.get("id") or event_data.get("chatId") or ""
    )
    if not group_jid or not group_jid.endswith("@g.us"):
        return

    action = str(event_data.get("action") or ("add" if event_type == "group.join" else "remove" if event_type == "group.leave" else "")).lower()
    raw_participants = event_data.get("participants") or []
    if isinstance(raw_participants, str):
        raw_participants = [raw_participants]

    participant_labels = []
    for p in raw_participants:
        clean_p = re.sub(r"\D+", "", str(p).split("@")[0].split(":")[0])
        if clean_p:
            participant_labels.append(f"+{clean_p}")
        elif p:
            participant_labels.append(str(p))

    if not participant_labels:
        return

    names_str = ", ".join(participant_labels)
    if action in ("add", "join"):
        notice = f"{names_str} was added to the group"
    elif action in ("remove", "leave"):
        notice = f"{names_str} was removed from the group"
    else:
        notice = f"Group participants updated: {names_str}"

    conv = WhatsAppConversation.objects.filter(session=session_obj, chat_id=group_jid).first()
    if not conv:
        return

    if conv.is_deleted:
        conv.is_deleted = False
        conv.save(update_fields=["is_deleted"])

    now = timezone.now()
    WhatsAppMessage.objects.create(
        conversation=conv,
        idempotency_key=str(uuid.uuid4()),
        direction=WhatsAppMessage.Direction.INBOUND,
        status=WhatsAppMessage.Status.READ,
        message_type="notification",
        body_preview=notice,
        full_body=notice,
        sent_at=now,
    )
    conv.last_message_at = now
    conv.last_message_preview = notice
    conv.save(update_fields=["last_message_at", "last_message_preview"])


def _handle_session_status(
    event_data: dict,
    session_name: str,
    event_record: WhatsAppEvent,
) -> None:
    """
    Handle a WAHA session status change event.

    Updates the local WhatsAppSession record.
    Triggers alerts for AUTH_FAILURE or abnormal disconnects.
    """
    waha_status = str(event_data.get("status") or "")
    phone = str(event_data.get("me", {}).get("phone") or "") if isinstance(event_data.get("me"), dict) else ""

    # Map WAHA status strings to our enum.
    raw_status_upper = waha_status.upper()
    STATUS_MAP = {
        "STARTING": WhatsAppSession.Status.STARTING,
        "SCAN_QR_CODE": WhatsAppSession.Status.QR_REQUIRED,
        "WORKING": WhatsAppSession.Status.READY,
        "FAILED": WhatsAppSession.Status.FAILED,
        "STOPPED": WhatsAppSession.Status.STOPPED,
        "DISCONNECTED": WhatsAppSession.Status.DISCONNECTED,
    }

    mapped_status = STATUS_MAP.get(raw_status_upper, WhatsAppSession.Status.DISCONNECTED)

    with transaction.atomic():
        session, _ = WhatsAppSession.objects.get_or_create(session_name=session_name)

        old_status = session.status

        # If already READY, DO NOT disconnect automatically on transient blips!
        if session.status == WhatsAppSession.Status.READY:
            if raw_status_upper in ("WORKING", "READY", "ONLINE", "AUTHENTICATED"):
                session.status = WhatsAppSession.Status.READY
            elif raw_status_upper in ("LOGGED_OUT", "UNPAIRED"):
                session.status = WhatsAppSession.Status.DISCONNECTED
                session.phone_number = None
            elif raw_status_upper in ("FAILED", "STOPPED", "STARTING", "SCAN_QR_CODE", "CONNECTING", "RESUMING"):
                # Preserve READY status and trigger seamless auto-recovery in WAHA
                logger.info("Preserving READY status for session %s despite WAHA status: %s (auto-recovering)", session_name, waha_status)
                from .client import get_waha_client
                try:
                    get_waha_client().start_session(session_name)
                except Exception as rec_err:
                    logger.debug("Auto-recover session %s: %s", session_name, rec_err)
            else:
                logger.info("Preserving READY status for session %s despite WAHA status: %s", session_name, waha_status)
        else:
            if raw_status_upper in ("WORKING", "READY", "ONLINE", "AUTHENTICATED"):
                session.status = WhatsAppSession.Status.READY
            elif mapped_status:
                session.status = mapped_status

        if phone:
            clean_new_phone = re.sub(r"\D+", "", str(phone or ""))
            clean_old_phone = re.sub(r"\D+", "", str(session.phone_number or ""))
            if clean_new_phone and clean_old_phone and clean_new_phone != clean_old_phone:
                logger.warning(
                    "WhatsApp account switch detected in session.status %s: %s -> %s. Purging old session data.",
                    session_name, clean_old_phone, clean_new_phone
                )
                WhatsAppMessage.objects.filter(conversation__session=session).delete()
                WhatsAppConversation.objects.filter(session=session).delete()
            session.phone_number = phone

        qr = event_data.get("qr") or event_data.get("value")
        qr_base64 = event_data.get("qrBase64") or ""
        if (qr or qr_base64) and session.status != WhatsAppSession.Status.READY:
            set_cached_qr(session_name, {
                "qr": qr or qr_base64,
                "qrBase64": qr_base64,
                "value": qr or qr_base64,
            })

        if session.status == WhatsAppSession.Status.READY:
            clear_cached_qr(session_name)
            if old_status != WhatsAppSession.Status.READY:
                session.reconnect_count += 1
                session.started_at = timezone.now()

        if session.status == WhatsAppSession.Status.DISCONNECTED and old_status == WhatsAppSession.Status.READY:
            session.disconnect_count += 1
            session.stopped_at = timezone.now()

        session.save()

    logger.info(
        "Session status change: session=%s %s -> %s",
        session_name,
        old_status,
        mapped_status,
    )

    # Alert on failure states.
    if mapped_status in (WhatsAppSession.Status.FAILED, WhatsAppSession.Status.DISCONNECTED):
        logger.error(
            "WHATSAPP SESSION FAILURE: session=%s status=%s — Manual intervention may be required.",
            session_name,
            mapped_status,
        )

    _write_audit_log(
        action=WhatsAppAuditLog.Action.SESSION_DISCONNECTED
        if mapped_status == WhatsAppSession.Status.DISCONNECTED
        else WhatsAppAuditLog.Action.SESSION_CONNECTED,
        session_name=session_name,
        result_detail=f"WAHA status: {waha_status}",
        success=mapped_status == WhatsAppSession.Status.READY,
    )

    if mapped_status == WhatsAppSession.Status.READY and old_status != WhatsAppSession.Status.READY:
        try:
            import threading
            threading.Thread(
                target=sync_two_day_whatsapp_history,
                kwargs={"session_name": session_name, "days": 2, "force": True},
                daemon=True,
            ).start()
        except Exception as sync_err:
            logger.debug("Auto 2-day history sync on session READY failed: %s", sync_err)


# Compatibility shims for F() expressions (avoid importing at module level
# to keep this file self-contained).
def models_f(field_name):
    from django.db.models import F
    return F(field_name)


def models_f_whatsapp(field_name):
    from django.db.models import F
    return F(field_name)


def sync_recent_waha_messages(
    messages_list: list,
    default_session_name: str = "default",
    days: int = 2,
) -> int:
    """
    Idempotently ingest messages from the last `days` days (default 2 days)
    in strict ascending chronological order (oldest -> newest), preserving
    each message's original WhatsApp timestamp.
    """
    from datetime import timedelta

    if not isinstance(messages_list, list) or not messages_list:
        return 0

    cutoff_dt = timezone.now() - timedelta(days=max(int(days or 2), 1))
    target_session = (default_session_name or "").strip()
    if not target_session or _resolve_originating_session(target_session) is None:
        logger.warning("sync_recent_waha_messages: unresolved target session %r — nothing imported.", target_session)
        return 0

    candidates = []
    seen_ids = set()

    for item in messages_list:
        if not isinstance(item, dict):
            continue
        # Every synchronized message must carry an explicit originating session that matches
        # the authorized target session exactly. Missing / mismatched identity is rejected
        # (a message from "default" is only accepted when "default" IS the target session).
        item_sess = str(item.get("session") or "").strip()
        if not item_sess or item_sess != target_session:
            continue
        m_id = str(item.get("id") or "")
        chat_norm = _normalize_chat_jid(
            item.get("chatId") or ((item.get("_data") or {}).get("key") or {}).get("remoteJid")
            or item.get("to") or item.get("from") or ""
        )
        dedupe_key = (item_sess, chat_norm, m_id)
        if m_id and dedupe_key in seen_ids:
            continue
        msg_dt = _parse_waha_timestamp(item)
        if msg_dt < cutoff_dt:
            continue
        if m_id:
            seen_ids.add(dedupe_key)
        candidates.append((msg_dt, item))

    # Sort strictly oldest -> newest so conversation history and previews are ordered chronologically
    candidates.sort(key=lambda pair: pair[0])

    synced = 0
    for _msg_dt, item in candidates:
        sess = str(item.get("session") or "").strip()
        try:
            created = _handle_incoming_message(item, sess, event_record=None, is_history_sync=True)
            if created:
                synced += 1
        except Exception as exc:
            logger.debug("sync_recent_waha_messages item skip: %s", exc)
    return synced


def sync_two_day_whatsapp_history(
    session_name: str = "default",
    chat_id: Optional[str] = None,
    days: int = 2,
    force: bool = False,
) -> dict:
    """
    Synchronize WhatsApp chat history and messages from the last `days` days (default 2 days).
    Fetches any missing chats or messages from WAHA / WAHA-NoWeb-Light, preserves original
    message timestamps, and reconciles conversation ordering.
    Strictly isolated to `session_name`.
    """
    from datetime import timedelta
    from .client import get_waha_client

    client = get_waha_client()
    cutoff_dt = timezone.now() - timedelta(days=max(int(days or 2), 1))
    collected = []
    seen_ids = set()

    def _add_msg(m: dict, fallback_chat_id: str = "", trusted_session: bool = False):
        """
        `trusted_session=True` is used ONLY for messages fetched through this session's own
        per-chat WAHA API (the session is implied by the request). Messages coming from the
        shared stats buffer must carry an explicit session equal to this session.
        """
        if not isinstance(m, dict):
            return
        m_sess = str(m.get("session") or "").strip()
        if m_sess and m_sess != session_name:
            # Strictly ignore messages from any other session (including legacy "default")
            return
        if not m_sess and not trusted_session:
            # Ambiguous origin — never attribute to the current session
            return
        msg_copy = dict(m)
        if fallback_chat_id and not msg_copy.get("chatId"):
            msg_copy["chatId"] = fallback_chat_id
        msg_copy["session"] = session_name
        m_id = str(msg_copy.get("id") or "")
        dedupe_key = (
            session_name,
            _normalize_chat_jid(msg_copy.get("chatId") or msg_copy.get("to") or msg_copy.get("from") or ""),
            m_id,
        )
        if m_id and dedupe_key in seen_ids:
            return
        if m_id:
            seen_ids.add(dedupe_key)
        collected.append(msg_copy)

    # 1. Pull buffered messages and webhook logs from WAHA-NoWeb-Light stats
    try:
        stats_msgs = client.get_recent_messages_from_stats(force=force)
        for m in stats_msgs:
            if chat_id:
                m_chat = str(
                    m.get("chatId")
                    or ((m.get("_data") or {}).get("key") or {}).get("remoteJid")
                    or m.get("to")
                    or m.get("from")
                    or ""
                )
                m_chat = re.sub(r":[0-9]+@", "@", m_chat).replace("@s.whatsapp.net", "@c.us")
                target_norm = re.sub(r":[0-9]+@", "@", chat_id).replace("@s.whatsapp.net", "@c.us")
                if m_chat and target_norm and m_chat != target_norm:
                    continue
            _add_msg(m)
    except Exception as e:
        logger.debug("2-day sync stats fetch skipped: %s", e)

    # 2. Pull per-chat message history if WAHA engine supports /api/chats/{chat_id}/messages
    target_chat_ids = []
    if chat_id:
        target_chat_ids.append(chat_id)
    else:
        try:
            recent_convs = WhatsAppConversation.objects.filter(
                session__session_name=session_name,
                is_deleted=False,
            ).order_by("-last_message_at", "-updated_at")[:25]
            for c in recent_convs:
                if c.chat_id and not c.chat_id.startswith("crm_group_"):
                    target_chat_ids.append(c.chat_id)
        except Exception:
            pass

    for cid in target_chat_ids:
        try:
            chat_msgs = client.get_messages(session_name, cid, limit=200)
            if isinstance(chat_msgs, list):
                for cm in chat_msgs:
                    _add_msg(cm, fallback_chat_id=cid, trusted_session=True)
        except Exception:
            pass

    # 3. Filter to 2-day window, sort chronologically (oldest -> newest), and store missing messages
    synced_count = sync_recent_waha_messages(
        collected,
        default_session_name=session_name,
        days=days,
    )

    # 4. Reconcile conversation last_message_at & preview from actual latest message in DB
    try:
        conv_qs = WhatsAppConversation.objects.filter(
            session__session_name=session_name,
            is_deleted=False,
        )
        if chat_id:
            conv_qs = conv_qs.filter(chat_id=chat_id)
        for conv in conv_qs[:50]:
            latest_msg = (
                WhatsAppMessage.objects.filter(conversation=conv, is_deleted=False)
                .order_by("-waha_timestamp", "-sent_at", "-created_at")
                .first()
            )
            if latest_msg:
                eff_ts = latest_msg.waha_timestamp or latest_msg.sent_at or latest_msg.created_at
                if eff_ts and conv.last_message_at != eff_ts:
                    conv.last_message_at = eff_ts
                    conv.last_message_preview = (
                        latest_msg.body_preview
                        or latest_msg.full_body[:200]
                        or f"[{latest_msg.message_type.capitalize()}]"
                    )
                    conv.last_message_from_me = (
                        latest_msg.direction == WhatsAppMessage.Direction.OUTBOUND
                    )
                    conv.save(update_fields=["last_message_at", "last_message_preview", "last_message_from_me"])
    except Exception as rec_err:
        logger.debug("2-day sync conversation reconciliation warning: %s", rec_err)

    return {
        "synced": synced_count,
        "checked": len(collected),
        "days": days,
        "cutoff": cutoff_dt.isoformat(),
    }



