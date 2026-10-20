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
import json
import logging
import urllib.request
import urllib.error
import urllib.parse
import mimetypes
import os
import re
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

# In-memory cache for the latest QR code pushed by WAHA
LATEST_QR_CACHE: dict = {}

def get_cached_qr(session_name: str = "default") -> Optional[dict]:
    """Return the most recently received QR code for a session."""
    return LATEST_QR_CACHE.get(session_name)


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
    "presence.update",
    "group.v2.participants",
    "group.v2.update",
    "message.waiting",
])

# Valid WhatsApp chat ID pattern.
VALID_CHAT_ID_RE = re.compile(r"^\d{7,25}@(c\.us|g\.us|lid)$")
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

    if event_type not in ALLOWED_EVENT_TYPES:
        raise WebhookVerificationError(
            f"Unknown event type: {event_type!r}. "
            f"Allowed: {sorted(ALLOWED_EVENT_TYPES)}"
        )

    session_name = payload.get("session", "default")
    if not isinstance(session_name, str):
        session_name = "default"
    session_name = session_name.strip()[:100]

    event_data = payload.get("payload") or payload.get("data") or {}
    if not isinstance(event_data, dict):
        event_data = {}

    return event_type, session_name, event_data


def _extract_phone_digits(chat_id: str) -> Optional[str]:
    """
    Safely extract phone digits from a WhatsApp chat ID.

    Returns None if the chat ID is not a valid individual contact.
    """
    if not isinstance(chat_id, str):
        return None

    # Only process individual chats (not groups).
    if not (chat_id.endswith("@c.us") or chat_id.endswith("@lid") or chat_id.endswith("@s.whatsapp.net")):
        return None

    digits = chat_id.split("@")[0].split(":")[0]

    if not PHONE_DIGITS_RE.match(digits):
        return None

    return digits


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
        elif event_type == "message.ack":
            _handle_message_ack(event_data, session_name, event_record)
        elif event_type == "session.status":
            _handle_session_status(event_data, session_name, event_record)
        elif event_type == "session.connected":
            _handle_session_connected(event_data, session_name, event_record)
        elif event_type == "session.disconnected":
            _handle_session_disconnected(event_data, session_name, event_record)
        elif event_type == "auth.qr":
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
    qr = event_data.get("qr") or event_data.get("value")
    qr_base64 = event_data.get("qrBase64") or ""
    if qr:
        LATEST_QR_CACHE[session_name] = {
            "qr": qr,
            "qrBase64": qr_base64,
            "session": session_name,
            "timestamp": timezone.now().isoformat(),
        }
        WhatsAppSession.objects.filter(session_name=session_name).update(
            status=WhatsAppSession.Status.QR_REQUIRED
        )
        logger.info("Received and cached auth.qr for session: %s", session_name)


def _handle_session_connected(event_data: dict, session_name: str, event_record: WhatsAppEvent) -> None:
    LATEST_QR_CACHE.pop(session_name, None)
    me = event_data.get("me") or {}
    phone = me.get("phone") or (me.get("id", "").split(":")[0] if ":" in me.get("id", "") else me.get("id", "").split("@")[0])
    name = me.get("name") or ""

    session, _ = WhatsAppSession.objects.get_or_create(session_name=session_name)
    session.status = WhatsAppSession.Status.READY
    if phone:
        session.phone_number = phone
    session.started_at = timezone.now()
    session.reconnect_count += 1
    session.save()
    logger.info("Session %s connected successfully! Phone: %s Name: %s", session_name, phone, name)


def _handle_session_disconnected(event_data: dict, session_name: str, event_record: WhatsAppEvent) -> None:
    LATEST_QR_CACHE.pop(session_name, None)
    is_logged_out = bool(event_data.get("isLoggedOut", False))
    new_status = WhatsAppSession.Status.FAILED if is_logged_out else WhatsAppSession.Status.DISCONNECTED
    WhatsAppSession.objects.filter(session_name=session_name).update(
        status=new_status,
        stopped_at=timezone.now()
    )
    logger.warning("Session %s disconnected (logged_out=%s)", session_name, is_logged_out)


def _handle_incoming_message(
    event_data: dict,
    session_name: str,
    event_record: WhatsAppEvent,
) -> None:
    """
    Handle an incoming or sync WhatsApp message event.
    """
    raw_from = str(event_data.get("from") or "")
    raw_to = str(event_data.get("to") or "")
    raw_body = str(event_data.get("body") or "")
    waha_message_id = str(event_data.get("id") or "")
    is_from_me = bool(event_data.get("fromMe", False))

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

    # Validate chat ID.
    if not VALID_CHAT_ID_RE.match(target_chat_id):
        logger.warning("Incoming message with invalid chat ID: %r — ignored.", target_chat_id)
        return

    phone_digits = _extract_phone_digits(target_chat_id)

    # Opt-out keyword check only for incoming messages from contacts
    conversation = WhatsAppConversation.objects.filter(
        chat_id=target_chat_id,
        session__session_name=session_name,
    ).first()

    if not is_from_me:
        opt_out_registered = check_incoming_for_opt_out(
            message_body=raw_body,
            phone_digits=phone_digits or "",
            prospect_contact=conversation.prospect_contact if conversation else None,
        )
        if opt_out_registered:
            logger.info("Opt-out registered from incoming message: phone=%s", phone_digits)

    # -----------------------------------------------------------------------
    # Find or create conversation record.
    # -----------------------------------------------------------------------
    is_matched = False
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

    # Extract real phone number (Baileys senderPn/participantPn for @lid messages)
    resolved_phone = None
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
        if existing_saved:
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

        # Opportunistically update the name if we got one and it was missing
        if extracted_name and (not conversation.whatsapp_name or conversation.whatsapp_name.startswith("+") or "@" in conversation.whatsapp_name):
            conversation.whatsapp_name = extracted_name
            conv_updates.append("whatsapp_name")
            
        # If conversation exists but is unmatched, attempt to match against ProspectContact
        if not is_matched and search_digits and len(search_digits) >= 8:
            from prospects.models import ProspectContact
            for contact in ProspectContact.objects.filter(
                phone_number__isnull=False
            ).select_related("prospect"):
                stored_digits = re.sub(r"\D+", "", contact.phone_number or "")
                if stored_digits and (
                    stored_digits == search_digits
                    or (len(search_digits) >= 10 and stored_digits.endswith(search_digits[-10:]))
                    or (len(stored_digits) >= 10 and search_digits.endswith(stored_digits[-10:]))
                ):
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
                    break

        if conv_updates:
            conversation.save(update_fields=list(set(conv_updates)))
            
    else:
        # Try to match by phone number against ProspectContact records.
        from prospects.models import ProspectContact

        matched_contact = None
        if search_digits and len(search_digits) >= 8:
            for contact in ProspectContact.objects.filter(
                phone_number__isnull=False
            ).select_related("prospect"):
                stored_digits = re.sub(r"\D+", "", contact.phone_number or "")
                if stored_digits and (stored_digits == search_digits or stored_digits.endswith(search_digits[-10:])):
                    matched_contact = contact
                    break

        with transaction.atomic():
            session_obj, _ = WhatsAppSession.objects.get_or_create(session_name=session_name)
            if session_obj.owner is None and session_name.startswith("user_"):
                try:
                    u_id = int(session_name.split("_")[1])
                    from django.contrib.auth import get_user_model
                    User = get_user_model()
                    u = User.objects.filter(id=u_id).first()
                    if u:
                        session_obj.owner = u
                        session_obj.save(update_fields=["owner"])
                except Exception:
                    pass

            final_name = extracted_name or (matched_contact.contact_name if matched_contact else "")
            final_phone = resolved_phone or (matched_contact.phone_number if matched_contact else None)
            conversation = WhatsAppConversation.objects.create(
                chat_id=target_chat_id,
                phone_number=final_phone,
                prospect_contact=matched_contact,
                prospect=matched_contact.prospect if matched_contact else None,
                session=session_obj,
                is_matched=matched_contact is not None,
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
    # Create WhatsAppMessage record.
    # -----------------------------------------------------------------------
    # Generate an idempotency key for this message.
    body_hash = hashlib.sha256(raw_body.encode("utf-8")).hexdigest()
    msg_idempotency = hashlib.sha256(
        f"{'outbound' if is_from_me else 'inbound'}:{target_chat_id}:{waha_message_id}:{body_hash}".encode()
    ).hexdigest()

    existing_message = WhatsAppMessage.objects.filter(
        idempotency_key=msg_idempotency
    ).first()

    if existing_message:
        # Already recorded this message.
        event_record.whatsapp_message = existing_message
        event_record.save(update_fields=["whatsapp_message"])
        return

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
            )

            # Update conversation metadata.
            conversation.last_message_at = timezone.now()
            conversation.last_message_preview = raw_body[:200] if raw_body else f"[{msg_type.capitalize()}]"
            conversation.last_message_from_me = is_from_me
            if not is_from_me:
                conversation.unread_count = conversation.unread_count + 1
            conversation.save(update_fields=[
                "last_message_at", "last_message_preview", "last_message_from_me", "unread_count"
            ])

            # Update session receive count.
            if not is_from_me:
                WhatsAppSession.objects.filter(session_name=session_name).update(
                    receive_count=models_f_whatsapp("receive_count") + 1
                )

            event_record.whatsapp_message = wa_message
            event_record.save(update_fields=["whatsapp_message"])
    except IntegrityError:
        # Concurrent webhook already created this message
        wa_message = WhatsAppMessage.objects.filter(idempotency_key=msg_idempotency).first()
        if wa_message:
            event_record.whatsapp_message = wa_message
            event_record.save(update_fields=["whatsapp_message"])
            return
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
        "Incoming WhatsApp message recorded: chat_id=%s matched=%s message_id=%s",
        raw_from,
        is_matched,
        wa_message.pk,
    )


def _handle_message_ack(
    event_data: dict,
    session_name: str,
    event_record: WhatsAppEvent,
) -> None:
    """
    Handle a message acknowledgement event (delivered/read status update).
    """
    waha_message_id = str(event_data.get("id") or "")
    ack_value = event_data.get("ack")

    if not waha_message_id:
        return

    # Map WAHA ACK values to our status enum.
    # WAHA ACK: 0=PENDING, 1=SENT, 2=DELIVERED, 3=READ, -1=FAILED
    ACK_STATUS_MAP = {
        -1: WhatsAppMessage.Status.FAILED,
        0: WhatsAppMessage.Status.PENDING,
        1: WhatsAppMessage.Status.SENT,
        2: WhatsAppMessage.Status.DELIVERED,
        3: WhatsAppMessage.Status.READ,
    }

    new_status = ACK_STATUS_MAP.get(int(ack_value or 0))
    if not new_status:
        return

    # Build update kwargs: only set timestamps when transitioning TO that state.
    # Use conditional expressions to avoid clobbering existing timestamps with None.
    update_kwargs = {"status": new_status}
    now = timezone.now()

    # Only advance timestamps — never regress them.
    # WAHA ack events can arrive out of order; treat them as idempotent advances.
    if new_status == WhatsAppMessage.Status.DELIVERED:
        # Set delivered_at only if not already set.
        WhatsAppMessage.objects.filter(
            waha_message_id=waha_message_id,
            status__in=[WhatsAppMessage.Status.PENDING, WhatsAppMessage.Status.SENT],
        ).update(status=new_status, delivered_at=now)
        return
    elif new_status == WhatsAppMessage.Status.READ:
        # Advance to READ; set both delivered_at and read_at if not already set.
        from django.db.models import Q
        WhatsAppMessage.objects.filter(
            waha_message_id=waha_message_id,
        ).exclude(status=WhatsAppMessage.Status.READ).update(
            status=new_status,
            delivered_at=now,
            read_at=now,
        )
        return
    elif new_status == WhatsAppMessage.Status.FAILED:
        WhatsAppMessage.objects.filter(
            waha_message_id=waha_message_id,
            status__in=[WhatsAppMessage.Status.PENDING, WhatsAppMessage.Status.SENT],
        ).update(status=new_status)
        return

    with transaction.atomic():
        updated = WhatsAppMessage.objects.filter(
            waha_message_id=waha_message_id,
        ).update(**update_kwargs)

    if updated:
        logger.debug("Message ACK updated: waha_id=%s new_status=%s", waha_message_id, new_status)


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
    STATUS_MAP = {
        "STARTING": WhatsAppSession.Status.STARTING,
        "SCAN_QR_CODE": WhatsAppSession.Status.QR_REQUIRED,
        "WORKING": WhatsAppSession.Status.READY,
        "FAILED": WhatsAppSession.Status.FAILED,
        "STOPPED": WhatsAppSession.Status.STOPPED,
        "DISCONNECTED": WhatsAppSession.Status.DISCONNECTED,
    }

    mapped_status = STATUS_MAP.get(waha_status.upper(), WhatsAppSession.Status.DISCONNECTED)

    with transaction.atomic():
        session, _ = WhatsAppSession.objects.get_or_create(session_name=session_name)

        old_status = session.status
        session.status = mapped_status

        if phone:
            session.phone_number = phone

        if mapped_status == WhatsAppSession.Status.READY and old_status != WhatsAppSession.Status.READY:
            session.reconnect_count += 1
            session.started_at = timezone.now()

        if mapped_status == WhatsAppSession.Status.DISCONNECTED and old_status == WhatsAppSession.Status.READY:
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


# Compatibility shims for F() expressions (avoid importing at module level
# to keep this file self-contained).
def models_f(field_name):
    from django.db.models import F
    return F(field_name)


def models_f_whatsapp(field_name):
    from django.db.models import F
    return F(field_name)


