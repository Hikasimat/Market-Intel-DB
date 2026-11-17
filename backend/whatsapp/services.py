"""
backend/whatsapp/services.py

Business logic layer for WhatsApp integration.

This is where all safety checks, authorization, and business rules live.
The Django views call this layer. This layer calls the WAHA client.

Safety Guard order for outbound sends:
  1.  WHATSAPP_ENABLED check
  2.  outbound_enabled (global kill switch)
  3.  safety_stop_active (auto-triggered by consecutive failures)
  4.  User send permission
  5.  Company/prospect/key-person authorization
  6.  Opt-out check
  7.  Recipient cooldown check
  8.  Idempotency check (duplicate send protection)
  9.  Rate limit check (per-user + global)
 10.  Message content validation
 11.  WAHA send
 12.  Post-send: record result, update Safety Guard counters

On any WhatsApp-side error:
  - Log the error.
  - Increment consecutive_failed_sends.
  - If threshold reached: trigger safety_stop_active.
  - Alert (log at ERROR level + create WhatsAppSafetyEvent).
  - Do NOT retry automatically.
"""

import hashlib
import logging
import os
import re
from datetime import timedelta
from typing import Optional

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from .client import WAHAServiceError, get_waha_client
from .models import (
    WhatsAppAuditLog,
    WhatsAppConfiguration,
    WhatsAppConversation,
    WhatsAppMessage,
    WhatsAppOptOut,
    WhatsAppSafetyEvent,
    WhatsAppSession,
)

logger = logging.getLogger(__name__)
User = get_user_model()

# Regex for valid WhatsApp chat IDs.
VALID_CHAT_ID_RE = re.compile(r"^[0-9a-zA-Z_\-\.]+@(c\.us|g\.us|lid|s\.whatsapp\.net)$")

# Opt-out keywords (case-insensitive).
OPT_OUT_KEYWORDS = frozenset([
    "stop",
    "unsubscribe",
    "do not contact",
    "remove me",
    "dont contact",
    "optout",
    "opt out",
    "no more",
])


class WhatsAppError(Exception):
    """Base exception for WhatsApp service errors."""
    def __init__(self, message: str, code: str = "WA_ERROR"):
        super().__init__(message)
        self.code = code


class WhatsAppBlockedError(WhatsAppError):
    """Raised when a send is blocked by a safety control."""
    def __init__(self, message: str, code: str = "WA_BLOCKED"):
        super().__init__(message, code)


class WhatsAppAuthorizationError(WhatsAppError):
    """Raised when authorization fails."""
    def __init__(self, message: str):
        super().__init__(message, "WA_UNAUTHORIZED")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _phone_digits(value: str) -> str:
    """Strip all non-digit characters from a phone number."""
    return re.sub(r"\D+", "", value or "")


def _is_lid_identifier(value: str) -> bool:
    if not value:
        return False
    raw = str(value).strip()
    if raw.endswith("@lid"):
        return True
    digits = re.sub(r"\D+", "", raw.split("@")[0].split(":")[0])
    return len(digits) > 13 or digits.startswith(("7658", "2262", "2167"))


def normalize_phone_digits(value: str) -> str:
    """
    Extract normalized phone digits (7-15 digits) from a raw phone or WhatsApp JID.
    Returns '' for @lid identifiers or invalid lengths.
    """
    if not value:
        return ""
    raw = str(value).strip()
    if "@g.us" in raw or _is_lid_identifier(raw):
        return ""
    if "@" in raw:
        raw = raw.split("@")[0].split(":")[0]
    digits = re.sub(r"\D+", "", raw)
    if 7 <= len(digits) <= 15:
        return digits
    return ""


def normalize_phone_number(value: str) -> Optional[str]:
    """Normalize a phone number or JID to canonical '+<digits>' format."""
    digits = normalize_phone_digits(value)
    return f"+{digits}" if digits else None


def generate_user_session_name(user) -> str:
    """
    Generate a deterministic, unique, non-guessable WAHA session name
    tied securely to the authenticated Market Intel user.
    """
    import hmac as _hmac
    from django.conf import settings as _settings
    secret = (getattr(_settings, "SECRET_KEY", None) or "market-intel-wa-session").encode("utf-8")
    msg = f"wa_user_session:{user.id}".encode("utf-8")
    digest = _hmac.new(secret, msg, hashlib.sha256).hexdigest()[:12]
    return f"wa_u{user.id}_{digest}"


def verify_deterministic_session_name(session_name: str, user_id: int) -> bool:
    """Verify whether `session_name` matches the HMAC-derived session ID for `user_id`."""
    import hmac as _hmac
    from django.conf import settings as _settings
    if not session_name or not user_id:
        return False
    secret = (getattr(_settings, "SECRET_KEY", None) or "market-intel-wa-session").encode("utf-8")
    msg = f"wa_user_session:{user_id}".encode("utf-8")
    expected = f"wa_u{user_id}_{_hmac.new(secret, msg, hashlib.sha256).hexdigest()[:12]}"
    return _hmac.compare_digest(session_name, expected)


def _chat_id_from_phone(phone: str) -> str:
    """Convert a phone number to a WhatsApp chat ID."""
    digits = _phone_digits(phone)
    return f"{digits}@c.us"


def _get_config() -> WhatsAppConfiguration:
    """Return the WhatsApp configuration, creating defaults if needed."""
    config, _created = WhatsAppConfiguration.objects.get_or_create(
        pk=1,
        defaults={"outbound_enabled": True}
    )
    if not config.outbound_enabled:
        config.outbound_enabled = True
        config.save(update_fields=["outbound_enabled"])
    return config


def _get_or_create_session(session_name: str = "default", owner=None) -> WhatsAppSession:
    """
    Return the WhatsApp session record, creating it ONLY when an explicit owner
    or an already-registered session exists. Never assigns ownership casually.
    """
    session = WhatsAppSession.objects.filter(session_name=session_name).first()
    if session:
        return session
    if owner is None and session_name == "default":
        raise WhatsAppAuthorizationError("Shared 'default' WhatsApp session cannot be used without an owner.")
    session, _created = WhatsAppSession.objects.get_or_create(
        session_name=session_name,
        defaults={"owner": owner, "status": WhatsAppSession.Status.DISCONNECTED, "is_active": True},
    )
    return session


def get_or_create_user_session(user, create: bool = True) -> Optional[WhatsAppSession]:
    """
    Resolve the isolated active WhatsAppSession belonging to `user`.
    Creates a deterministic, secure per-user session if none exists and `create=True`.
    """
    import uuid as _uuid
    if not user or not user.is_authenticated:
        return None

    active = (
        WhatsAppSession.objects.filter(owner=user, is_active=True)
        .order_by("-last_used_at", "-updated_at", "-id")
        .first()
    )
    if active:
        return active

    if not create:
        return None

    # If user has no active session, check if there is an un-switched disconnected session
    # (only reactivate if there's one without a phone number or if none is archived)
    det_name = generate_user_session_name(user)
    conflict = WhatsAppSession.objects.filter(session_name=det_name).first()
    if conflict:
        if conflict.owner_id == user.id:
            conflict.is_active = True
            conflict.save(update_fields=["is_active"])
            return conflict
        if conflict.owner_id is None:
            conflict.owner = user
            conflict.is_active = True
            conflict.save(update_fields=["owner", "is_active"])
            return conflict
        det_name = f"wa_u{user.id}_{_uuid.uuid4().hex[:12]}"

    session = WhatsAppSession.objects.create(
        session_name=det_name,
        owner=user,
        status=WhatsAppSession.Status.DISCONNECTED,
        is_active=True,
    )
    return session


def reconcile_connected_session(
    session_obj: WhatsAppSession,
    raw_phone: str,
    source: str = "webhook",
) -> tuple[WhatsAppSession, bool, Optional[str]]:
    """
    Reconcile a WAHA connection event against the database WhatsAppSession.

    Handles:
      - First-time connection: normalizes & saves phone_number, marks READY.
      - Scenario B (same number reconnect): keeps existing session identity and
        all persisted conversations/messages intact, marks READY.
      - Scenario C (different number connected): preserves the old account's
        session & conversation history untouched (archived with is_active=False),
        and activates/creates a separate session for the new phone number.

    Returns (active_session, account_switched, previous_phone).
    """
    import uuid as _uuid

    norm_phone = normalize_phone_number(raw_phone)
    new_digits = normalize_phone_digits(raw_phone)

    with transaction.atomic():
        locked = WhatsAppSession.objects.select_for_update().get(pk=session_obj.pk)
        old_phone = locked.phone_number
        old_digits = normalize_phone_digits(old_phone or "")
        was_ready = locked.status == WhatsAppSession.Status.READY

        # Deactivate any stale unowned session still claiming this same phone number
        if new_digits:
            for stale in WhatsAppSession.objects.filter(owner__isnull=True, is_active=True).exclude(pk=locked.pk):
                if normalize_phone_digits(stale.phone_number or "") == new_digits:
                    stale.is_active = False
                    stale.status = WhatsAppSession.Status.DISCONNECTED
                    stale.stopped_at = stale.stopped_at or timezone.now()
                    stale.save(update_fields=["is_active", "status", "stopped_at", "updated_at"])

        # Same number or first-time phone binding
        if not new_digits or not old_digits or old_digits == new_digits:
            update_fields = []
            if locked.status != WhatsAppSession.Status.READY:
                locked.status = WhatsAppSession.Status.READY
                update_fields.append("status")
            if not locked.is_active:
                locked.is_active = True
                update_fields.append("is_active")
            if norm_phone and locked.phone_number != norm_phone:
                locked.phone_number = norm_phone
                update_fields.append("phone_number")
            if not was_ready:
                locked.started_at = timezone.now()
                locked.reconnect_count = (locked.reconnect_count or 0) + 1
                update_fields.extend(["started_at", "reconnect_count"])
            if update_fields:
                locked.save(update_fields=list(set(update_fields)))
            return locked, False, None

        # Scenario C: Different WhatsApp number authenticated on this user's WAHA slot.
        # Preserve the old session & its entire conversation/message history untouched!
        live_session_name = locked.session_name
        owner = locked.owner

        logger.warning(
            "WhatsApp account switch detected on session %s (owner=%s): %s -> %s (%s). "
            "Archiving previous account history without deletion.",
            live_session_name,
            getattr(owner, "username", owner),
            old_phone,
            norm_phone,
            source,
        )

        # Look for an existing historical session owned by the same user for `new_digits`
        existing_target = None
        if owner is not None:
            for cand in WhatsAppSession.objects.filter(owner=owner).exclude(pk=locked.pk).order_by("-updated_at"):
                if normalize_phone_digits(cand.phone_number or "") == new_digits:
                    existing_target = cand
                    break

        # Archive the old account session (preserving its conversations & messages!)
        archive_suffix = _uuid.uuid4().hex[:6]
        locked.is_active = False
        locked.status = WhatsAppSession.Status.DISCONNECTED
        locked.stopped_at = timezone.now()
        locked.session_name = f"hist_u{owner.id if owner else 0}_{old_digits}_{archive_suffix}"[:100]
        locked.save(update_fields=["is_active", "status", "stopped_at", "session_name", "updated_at"])

        if existing_target:
            existing_target.session_name = live_session_name
            existing_target.phone_number = norm_phone
            existing_target.status = WhatsAppSession.Status.READY
            existing_target.is_active = True
            existing_target.started_at = timezone.now()
            existing_target.reconnect_count = (existing_target.reconnect_count or 0) + 1
            existing_target.save(update_fields=[
                "session_name", "phone_number", "status", "is_active",
                "started_at", "reconnect_count", "updated_at",
            ])
            new_session = existing_target
        else:
            new_session = WhatsAppSession.objects.create(
                owner=owner,
                session_name=live_session_name,
                phone_number=norm_phone,
                status=WhatsAppSession.Status.READY,
                is_active=True,
                started_at=timezone.now(),
                reconnect_count=1,
            )

        _write_audit_log(
            action=WhatsAppAuditLog.Action.SESSION_CONNECTED,
            performed_by=owner,
            session_name=live_session_name,
            success=True,
            result_code="ACCOUNT_SWITCHED",
            result_detail=f"Switched active WhatsApp number from {old_phone} to {norm_phone}; previous history preserved.",
        )

        return new_session, True, old_phone


def _write_audit_log(
    action: str,
    performed_by=None,
    prospect_contact=None,
    session_name: str = "",
    chat_id: str = "",
    message_id=None,
    success: Optional[bool] = None,
    result_code: str = "",
    result_detail: str = "",
    request_id: str = "",
    ip_address: str = "",
) -> WhatsAppAuditLog:
    """Write an immutable audit log entry."""
    profile = getattr(performed_by, "profile", None)

    entry = WhatsAppAuditLog(
        action=action,
        performed_by=performed_by,
        performed_by_role=profile.role if profile else None,
        session_name=session_name or "",
        chat_id=chat_id,
        success=success,
        result_code=result_code,
        result_detail=result_detail[:500] if result_detail else None,
        request_id=request_id,
        ip_address=ip_address or None,
        message_id=message_id,
    )

    if prospect_contact is not None:
        entry.prospect_contact_id = prospect_contact.pk
        entry.prospect_contact_name = prospect_contact.contact_name
        try:
            entry.prospect_id = prospect_contact.prospect_id
            entry.prospect_name = prospect_contact.prospect.company_name
        except Exception:
            pass

    entry.save()
    return entry


def _trigger_safety_stop(reason: str, session: WhatsAppSession, user=None):
    """
    Trigger the Safety Guard: disable all outbound messaging and alert.

    This is a non-reversible automated action. Only a Super Admin can reset it.
    """
    config = _get_config()

    if config.safety_stop_active:
        # Already stopped — just log.
        logger.warning("Safety stop already active. Reason: %s", reason)
        return

    with transaction.atomic():
        config.safety_stop_active = True
        config.safety_stop_reason = reason
        config.safety_stop_at = timezone.now()
        config.save(update_fields=["safety_stop_active", "safety_stop_reason", "safety_stop_at"])

        WhatsAppSafetyEvent.objects.create(
            event_type=WhatsAppSafetyEvent.EventType.SAFETY_STOP_TRIGGERED,
            triggered_by=user,
            details=reason,
            consecutive_failures_at_event=session.consecutive_failed_sends,
        )

    # Log at ERROR level so monitoring systems can alert.
    logger.error(
        "WHATSAPP SAFETY STOP TRIGGERED: %s | consecutive_failures=%d | "
        "OUTBOUND MESSAGING IS NOW DISABLED. Manual Super Admin review required.",
        reason,
        session.consecutive_failed_sends,
    )


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

def start_session(performed_by=None, session_name: str = "") -> dict:
    """Start the WAHA WhatsApp session."""
    if not session_name:
        user_sess = get_or_create_user_session(performed_by, create=True) if performed_by else None
        if not user_sess:
            raise WhatsAppAuthorizationError("Cannot start WhatsApp session without an authenticated user or session name.")
        session_name = user_sess.session_name

    client = get_waha_client()

    _write_audit_log(
        action=WhatsAppAuditLog.Action.SESSION_STARTED,
        performed_by=performed_by,
        session_name=session_name,
    )

    try:
        result = client.start_session(session_name)
        session = _get_or_create_session(session_name, owner=performed_by)
        session.started_at = timezone.now()
        if session.status != WhatsAppSession.Status.READY:
            session.status = WhatsAppSession.Status.STARTING
        session.save(update_fields=["started_at", "status"])
        return result
    except WAHAServiceError as exc:
        logger.error("Failed to start WAHA session: %s", str(exc))
        raise WhatsAppError(str(exc), "WA_START_FAILED") from exc


def stop_session(performed_by=None, session_name: str = "") -> dict:
    """Stop the WAHA session without logging out WhatsApp."""
    if not session_name:
        user_sess = get_or_create_user_session(performed_by, create=False) if performed_by else None
        if not user_sess:
            raise WhatsAppAuthorizationError("Cannot stop WhatsApp session without an owned session.")
        session_name = user_sess.session_name

    client = get_waha_client()

    _write_audit_log(
        action=WhatsAppAuditLog.Action.SESSION_STOPPED,
        performed_by=performed_by,
        session_name=session_name,
    )

    try:
        result = client.stop_session(session_name)
        session = _get_or_create_session(session_name, owner=performed_by)
        session.status = WhatsAppSession.Status.STOPPED
        session.stopped_at = timezone.now()
        session.save(update_fields=["status", "stopped_at"])
        return result
    except WAHAServiceError as exc:
        logger.error("Failed to stop WAHA session: %s", str(exc))
        raise WhatsAppError(str(exc), "WA_STOP_FAILED") from exc


def logout_session(performed_by=None, session_name: str = "") -> dict:
    """
    Logout from WhatsApp (disconnects the WAHA runtime session).

    Scenario A lifecycle invariant:
      - Updates existing session status to DISCONNECTED and sets stopped_at.
      - Preserves session owner.
      - Preserves connected phone_number as historical identity information.
      - Preserves ALL conversations, messages, and media references in PostgreSQL.
      - Never deletes database records or reassigns conversations.
    """
    if not session_name:
        user_sess = get_or_create_user_session(performed_by, create=False) if performed_by else None
        if not user_sess:
            raise WhatsAppAuthorizationError("No active WhatsApp session found to disconnect.")
        session_name = user_sess.session_name

    client = get_waha_client()

    logger.info(
        "WhatsApp logout requested by %s for session %s",
        getattr(performed_by, "username", "system"),
        session_name,
    )

    _write_audit_log(
        action=WhatsAppAuditLog.Action.SESSION_STOPPED,
        performed_by=performed_by,
        session_name=session_name,
        result_detail="logout_preserving_history",
    )

    try:
        try:
            result = client.logout_session(session_name)
        except WAHAServiceError as exc:
            # If WAHA already lost/stopped the runtime session (404), still update local DB cleanly.
            if getattr(exc, "status_code", None) == 404:
                result = {"status": "DISCONNECTED", "detail": "WAHA session not active"}
            else:
                raise

        session = _get_or_create_session(session_name, owner=performed_by)
        session.status = WhatsAppSession.Status.DISCONNECTED
        session.stopped_at = timezone.now()
        # Preserve session.owner, session.phone_number, and all conversations/messages/media!
        session.save(update_fields=["status", "stopped_at"])

        return result
    except WAHAServiceError as exc:
        raise WhatsAppError(str(exc), "WA_LOGOUT_FAILED") from exc


def get_session_status(session_name: str = "") -> dict:
    """Get WAHA session status (from WAHA, plus local tracking data)."""
    if not session_name:
        return {
            "session_name": "",
            "waha_status": {},
            "local_status": WhatsAppSession.Status.DISCONNECTED,
        }
    client = get_waha_client()

    try:
        waha_status = client.get_session_status(session_name)
        local_session = WhatsAppSession.objects.filter(session_name=session_name).first()
        if not local_session:
            return {
                "session_name": session_name,
                "waha_status": waha_status,
                "local_status": WhatsAppSession.Status.DISCONNECTED,
            }

        return {
            "session_name": session_name,
            "waha_status": waha_status,
            "local_status": local_session.status,
            "phone_number": local_session.phone_number,
            "send_count": local_session.send_count,
            "failed_send_count": local_session.failed_send_count,
            "consecutive_failed_sends": local_session.consecutive_failed_sends,
            "last_successful_message_at": local_session.last_successful_message_at,
        }
    except WAHAServiceError as exc:
        local_session = WhatsAppSession.objects.filter(session_name=session_name).first()
        return {
            "session_name": session_name,
            "waha_status": {"error": str(exc)},
            "local_status": local_session.status if local_session else WhatsAppSession.Status.DISCONNECTED,
            "phone_number": local_session.phone_number if local_session else None,
        }


def get_qr(session_name: str = "default", performed_by=None) -> dict:
    """Get the QR code for WhatsApp authentication."""
    client = get_waha_client()

    _write_audit_log(
        action=WhatsAppAuditLog.Action.QR_REQUESTED,
        performed_by=performed_by,
        session_name=session_name,
    )

    try:
        return client.get_qr(session_name)
    except WAHAServiceError as exc:
        raise WhatsAppError(str(exc), "WA_QR_FAILED") from exc


# ---------------------------------------------------------------------------
# Outbound messaging — with full Safety Guard pipeline
# ---------------------------------------------------------------------------

def send_whatsapp_message(
    *,
    performed_by,
    prospect_contact,
    message_body: str,
    session_name: str = "default",
    intent_tag: str = "manual",
    request_id: str = "",
    ip_address: str = "",
    chat_id_override: Optional[str] = None,
) -> WhatsAppMessage:
    """
    Send a WhatsApp text message through the full Safety Guard pipeline.

    Args:
        performed_by:     The authenticated Django User initiating the send.
        prospect_contact: The ProspectContact (Key Person) to message.
        message_body:     The plaintext message.
        session_name:     WAHA session name (default: "default").
        intent_tag:       A label for the send intent (for idempotency key).
        request_id:       Optional request/trace ID for logging.
        ip_address:       Request IP for audit log.
        chat_id_override: Optional explicit WhatsApp JID (e.g. @lid or @c.us).

    Returns:
        WhatsAppMessage record.

    Raises:
        WhatsAppBlockedError: If any safety control blocks the send.
        WhatsAppAuthorizationError: If authorization fails.
        WhatsAppError: On unexpected WAHA errors.
    """
    from prospects.models import ProspectContact

    # ------------------------------------------------------------------
    # GUARD 1: WHATSAPP_ENABLED
    # ------------------------------------------------------------------
    if os.environ.get("WHATSAPP_ENABLED", "false").lower() != "true":
        raise WhatsAppBlockedError(
            "WhatsApp integration is disabled.",
            code="WA_DISABLED",
        )

    # ------------------------------------------------------------------
    # GUARD 2: Global kill switch
    # ------------------------------------------------------------------
    config = _get_config()

    if not config.outbound_enabled:
        WhatsAppSafetyEvent.objects.create(
            event_type=WhatsAppSafetyEvent.EventType.OUTBOUND_DISABLED,
            triggered_by=performed_by,
            prospect_contact=prospect_contact,
        )
        raise WhatsAppBlockedError(
            "Outbound WhatsApp messaging is disabled. Contact your administrator.",
            code="WA_OUTBOUND_DISABLED",
        )

    # ------------------------------------------------------------------
    # GUARD 3: Safety stop (auto-recover if tripped by transient WAHA state)
    # ------------------------------------------------------------------
    if config.safety_stop_active:
        reason_lower = (config.safety_stop_reason or "").lower()
        if intent_tag == "manual" or any(k in reason_lower for k in ("waha", "working state", "unreachable", "timed out", "automatic safety stop")):
            config.safety_stop_active = False
            config.safety_stop_reason = None
            config.safety_stop_at = None
            config.save(update_fields=["safety_stop_active", "safety_stop_reason", "safety_stop_at"])
        else:
            WhatsAppSafetyEvent.objects.create(
                event_type=WhatsAppSafetyEvent.EventType.SAFETY_STOP_TRIGGERED,
                triggered_by=performed_by,
                prospect_contact=prospect_contact,
                details="Send blocked due to active safety stop.",
            )
            raise WhatsAppBlockedError(
                "WhatsApp sending has been temporarily stopped due to unusual activity. "
                "Contact your administrator. Reason: "
                + (config.safety_stop_reason or "Unknown."),
                code="WA_SAFETY_STOP",
            )

    # ------------------------------------------------------------------
    # GUARD 4: User send permission
    # ------------------------------------------------------------------
    profile = getattr(performed_by, "profile", None)
    user_role = profile.role if profile else None

    # Only PRE, LQ and SuperAdmin can send WhatsApp messages.
    allowed_sender_roles = {"PRE", "LQ"}
    is_superuser = performed_by.is_superuser

    if not is_superuser and user_role not in allowed_sender_roles:
        raise WhatsAppAuthorizationError(
            f"Role '{user_role}' is not permitted to send WhatsApp messages. "
            "Only PRE users and administrators can send WhatsApp messages."
        )

    # ------------------------------------------------------------------
    # GUARD 5: Contact/prospect validation
    # ------------------------------------------------------------------
    if not isinstance(prospect_contact, ProspectContact):
        raise WhatsAppAuthorizationError("Invalid prospect contact.")

    phone = _phone_digits(prospect_contact.phone_number)
    if chat_id_override and VALID_CHAT_ID_RE.match(chat_id_override.strip()):
        chat_id = chat_id_override.strip()
        if not phone:
            phone = _phone_digits(chat_id.split("@")[0].split(":")[0])
    else:
        if not prospect_contact.phone_number:
            raise WhatsAppBlockedError(
                "This key person does not have a phone number.",
                code="WA_NO_PHONE",
            )
        if len(phone) < 7 or len(phone) > 15:
            raise WhatsAppBlockedError(
                "Phone number must be in international format (7-15 digits, e.g., 919876543210).",
                code="WA_INVALID_PHONE",
            )
        chat_id = f"{phone}@c.us"

    # Validate chat ID format.
    if not VALID_CHAT_ID_RE.match(chat_id):
        raise WhatsAppBlockedError(
            f"Invalid WhatsApp chat ID format: {chat_id!r}",
            code="WA_INVALID_CHAT_ID",
        )

    # Resolve user's owned session early so safety counters & cooldowns are scoped properly
    if not session_name or session_name == "default":
        session = get_or_create_user_session(performed_by, create=True)
        session_name = session.session_name
    else:
        session = WhatsAppSession.objects.filter(session_name=session_name).first()
        if not session:
            session = get_or_create_user_session(performed_by, create=True)
            session_name = session.session_name
        elif not is_superuser and session.owner_id != performed_by.id:
            raise WhatsAppAuthorizationError("You are not authorized to send via this WhatsApp session.")

    # ------------------------------------------------------------------
    # GUARD 6: Opt-out check
    # ------------------------------------------------------------------
    opt_out = WhatsAppOptOut.objects.filter(phone_digits=phone, is_active=True).first()
    if opt_out:
        if intent_tag in ("manual", "direct") and opt_out.reason == WhatsAppOptOut.Reason.INCOMING_KEYWORD:
            # Auto-reverse false positive keyword opt-out for manual agent conversation
            opt_out.is_active = False
            opt_out.reversed_by = performed_by
            opt_out.reversed_at = timezone.now()
            opt_out.reversal_reason = "Manual agent outreach override"
            opt_out.save(update_fields=["is_active", "reversed_by", "reversed_at", "reversal_reason"])
            opt_out = None
        else:
            session.opt_out_count = (session.opt_out_count or 0) + 1
            session.save(update_fields=["opt_out_count"])

            WhatsAppSafetyEvent.objects.create(
                event_type=WhatsAppSafetyEvent.EventType.OPT_OUT_BLOCKED,
                triggered_by=performed_by,
                prospect_contact=prospect_contact,
                details=f"Recipient {phone} has opted out.",
            )

            _write_audit_log(
                action=WhatsAppAuditLog.Action.SEND_BLOCKED,
                performed_by=performed_by,
                prospect_contact=prospect_contact,
                session_name=session_name,
                chat_id=chat_id,
                success=False,
                result_code="WA_OPT_OUT",
                result_detail="Recipient has opted out.",
                request_id=request_id,
                ip_address=ip_address,
            )

            raise WhatsAppBlockedError(
                "This recipient has opted out of WhatsApp messages.",
                code="WA_OPT_OUT",
            )

    # ------------------------------------------------------------------
    # GUARD 7: Recipient cooldown (only for automated/bulk sends, not manual 1-on-1 chat)
    # ------------------------------------------------------------------
    cooldown_minutes = config.recipient_cooldown_minutes
    if intent_tag != "manual" and cooldown_minutes > 0:
        cooldown_cutoff = timezone.now() - timedelta(minutes=cooldown_minutes)

        recent_to_recipient = WhatsAppMessage.objects.filter(
            conversation__session=session,
            conversation__chat_id=chat_id,
            direction=WhatsAppMessage.Direction.OUTBOUND,
            status__in=[WhatsAppMessage.Status.SENT, WhatsAppMessage.Status.DELIVERED, WhatsAppMessage.Status.READ],
            created_at__gte=cooldown_cutoff,
        ).exists()

        if recent_to_recipient:
            session.cooldown_block_count += 1
            session.save(update_fields=["cooldown_block_count"])

            WhatsAppSafetyEvent.objects.create(
                event_type=WhatsAppSafetyEvent.EventType.COOLDOWN_BLOCKED,
                triggered_by=performed_by,
                prospect_contact=prospect_contact,
                details=f"Cooldown: {cooldown_minutes} minutes not elapsed since last message to {phone}.",
            )

            _write_audit_log(
                action=WhatsAppAuditLog.Action.SEND_BLOCKED,
                performed_by=performed_by,
                prospect_contact=prospect_contact,
                session_name=session_name,
                chat_id=chat_id,
                success=False,
                result_code="WA_COOLDOWN",
                result_detail=f"Cooldown: {cooldown_minutes} minutes not elapsed.",
                request_id=request_id,
                ip_address=ip_address,
            )

            raise WhatsAppBlockedError(
                f"A message was recently sent to this recipient. "
                f"Please wait {cooldown_minutes} minutes before sending again.",
                code="WA_COOLDOWN",
            )

    # ------------------------------------------------------------------
    # GUARD 8: Idempotency (duplicate send protection)
    # ------------------------------------------------------------------
    if intent_tag == "manual":
        import time as _time
        bucket = int(_time.time() // 2)
        idempotency_key = hashlib.sha256(
            f"{performed_by.pk}:{prospect_contact.pk}:{message_body.strip()}:manual:{bucket}".encode("utf-8")
        ).hexdigest()
    else:
        idempotency_key = WhatsAppMessage.compute_idempotency_key(
            user_id=performed_by.pk,
            prospect_contact_id=str(prospect_contact.pk),
            message_body=message_body,
            intent_tag=intent_tag,
        )

    existing = WhatsAppMessage.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        WhatsAppSafetyEvent.objects.create(
            event_type=WhatsAppSafetyEvent.EventType.DUPLICATE_BLOCKED,
            triggered_by=performed_by,
            prospect_contact=prospect_contact,
            details="Duplicate send attempt detected by idempotency key.",
        )
        logger.info(
            "Duplicate WhatsApp send blocked: idempotency_key=%s message_id=%s",
            idempotency_key,
            existing.pk,
        )
        # Return the existing message record instead of sending again.
        return existing

    # ------------------------------------------------------------------
    # GUARD 9: Rate limits
    # ------------------------------------------------------------------
    one_hour_ago = timezone.now() - timedelta(hours=1)

    # Per-user rate limit.
    user_sends_last_hour = WhatsAppMessage.objects.filter(
        performed_by=performed_by,
        direction=WhatsAppMessage.Direction.OUTBOUND,
        created_at__gte=one_hour_ago,
    ).count()

    if user_sends_last_hour >= config.per_user_hourly_limit:
        WhatsAppSafetyEvent.objects.create(
            event_type=WhatsAppSafetyEvent.EventType.RATE_LIMIT_BLOCKED,
            triggered_by=performed_by,
            prospect_contact=prospect_contact,
            details=f"Per-user hourly limit reached: {user_sends_last_hour}/{config.per_user_hourly_limit}",
        )
        raise WhatsAppBlockedError(
            f"You have reached your hourly WhatsApp message limit ({config.per_user_hourly_limit}/hour). "
            "Please wait before sending more messages.",
            code="WA_RATE_LIMIT_USER",
        )

    # Global rate limit.
    global_sends_last_hour = WhatsAppMessage.objects.filter(
        direction=WhatsAppMessage.Direction.OUTBOUND,
        created_at__gte=one_hour_ago,
    ).count()

    if global_sends_last_hour >= config.global_hourly_limit:
        WhatsAppSafetyEvent.objects.create(
            event_type=WhatsAppSafetyEvent.EventType.RATE_LIMIT_BLOCKED,
            triggered_by=performed_by,
            prospect_contact=prospect_contact,
            details=f"Global hourly limit reached: {global_sends_last_hour}/{config.global_hourly_limit}",
        )
        raise WhatsAppBlockedError(
            "The global WhatsApp message limit for this hour has been reached. "
            "Please try again later.",
            code="WA_RATE_LIMIT_GLOBAL",
        )

    # ------------------------------------------------------------------
    # GUARD 10: Message content validation
    # ------------------------------------------------------------------
    body = message_body.strip() if isinstance(message_body, str) else ""

    if not body:
        raise WhatsAppBlockedError("Message body cannot be empty.", code="WA_EMPTY_BODY")

    if len(body) > 4096:
        raise WhatsAppBlockedError(
            "Message body exceeds 4096 characters.", code="WA_BODY_TOO_LONG"
        )

    # ------------------------------------------------------------------
    # STEP 11: Get/create conversation record
    # ------------------------------------------------------------------
    # Resolve the session object before creating the conversation.
    # The session MUST be owned by performed_by for the ownership chain.
    if not session_name or session_name == "default":
        session = get_or_create_user_session(performed_by, create=True)
        session_name = session.session_name
    else:
        session = WhatsAppSession.objects.filter(session_name=session_name).first()
        if not session:
            session = get_or_create_user_session(performed_by, create=True)
            session_name = session.session_name
        elif not is_superuser and session.owner_id != performed_by.id:
            raise WhatsAppAuthorizationError("You are not authorized to send via this WhatsApp session.")

    alt_chat_id = None
    if chat_id.endswith("@s.whatsapp.net"):
        alt_chat_id = chat_id.replace("@s.whatsapp.net", "@c.us")
    elif chat_id.endswith("@c.us"):
        alt_chat_id = chat_id.replace("@c.us", "@s.whatsapp.net")

    candidate_ids = [chat_id]
    if alt_chat_id:
        candidate_ids.append(alt_chat_id)

    from django.db.models import Q
    conversation = WhatsAppConversation.objects.filter(
        session=session,
        chat_id__in=candidate_ids,
        is_deleted=False,
    ).first()

    if not conversation and phone and len(phone) >= 8:
        suffix = phone[-10:] if len(phone) >= 10 else phone[-8:]
        conversation = WhatsAppConversation.objects.filter(
            session=session,
            is_deleted=False,
        ).filter(
            Q(phone_number__icontains=suffix) | Q(chat_id__icontains=suffix) | Q(prospect_contact=prospect_contact)
        ).first()

    if not conversation:
        conversation, _ = WhatsAppConversation.objects.get_or_create(
            chat_id=chat_id,
            session=session,
            defaults={
                "prospect_contact": prospect_contact,
                "prospect": prospect_contact.prospect,
                "phone_number": f"+{phone}" if phone else None,
                "whatsapp_name": prospect_contact.contact_name or "",
                "is_matched": True,
            },
        )

    # Ensure conversation is matched to this contact and phone/name are populated.
    conv_updates = []
    if not conversation.is_matched or not conversation.prospect_contact:
        conversation.prospect_contact = prospect_contact
        conversation.prospect = prospect_contact.prospect
        conversation.is_matched = True
        conv_updates.extend(["prospect_contact", "prospect", "is_matched"])
    if not conversation.phone_number and phone:
        conversation.phone_number = f"+{phone}"
        conv_updates.append("phone_number")
    if not conversation.whatsapp_name and prospect_contact.contact_name:
        conversation.whatsapp_name = prospect_contact.contact_name
        conv_updates.append("whatsapp_name")
    if conv_updates:
        conversation.save(update_fields=list(set(conv_updates)))

    # ------------------------------------------------------------------
    # STEP 12: Create message record (PENDING) before sending.
    # This ensures we have a record even if WAHA times out.
    # ------------------------------------------------------------------
    body_hash = WhatsAppMessage.compute_body_hash(body)

    with transaction.atomic():
        wa_message = WhatsAppMessage.objects.create(
            idempotency_key=idempotency_key,
            conversation=conversation,
            performed_by=performed_by,
            direction=WhatsAppMessage.Direction.OUTBOUND,
            status=WhatsAppMessage.Status.PENDING,
            body_preview=body[:500],
            full_body=body,
            body_hash=body_hash,
            message_type="chat",
        )

    # ------------------------------------------------------------------
    # STEP 13: Call WAHA
    # ------------------------------------------------------------------
    # session was already resolved in STEP 11 above.
    client = get_waha_client()

    reply_to_id = None
    if chat_id.endswith("@lid"):
        last_inbound = WhatsAppMessage.objects.filter(
            conversation=conversation, direction=WhatsAppMessage.Direction.INBOUND
        ).order_by("-sent_at").first()
        if last_inbound and last_inbound.waha_message_id:
            reply_to_id = last_inbound.waha_message_id

    try:
        waha_response = client.send_text(
            session_name=session_name,
            chat_id=chat_id,
            text=body,
            reply_to=reply_to_id,
        )

        # Success path.
        with transaction.atomic():
            wa_message.status = WhatsAppMessage.Status.SENT
            wa_message.waha_message_id = (
                waha_response.get("id") or
                waha_response.get("key", {}).get("id")
            )
            wa_message.sent_at = timezone.now()
            wa_message.save(update_fields=["status", "waha_message_id", "sent_at"])

            session.send_count += 1
            session.consecutive_failed_sends = 0  # Reset on success.
            session.last_successful_message_at = timezone.now()
            session.last_used_at = timezone.now()
            session.save(update_fields=[
                "send_count", "consecutive_failed_sends", "last_successful_message_at", "last_used_at"
            ])

            conversation.last_message_at = timezone.now()
            conversation.last_message_preview = body[:200]
            conversation.last_message_from_me = True
            conversation.save(update_fields=[
                "last_message_at", "last_message_preview", "last_message_from_me"
            ])

        _write_audit_log(
            action=WhatsAppAuditLog.Action.MESSAGE_SENT,
            performed_by=performed_by,
            prospect_contact=prospect_contact,
            session_name=session_name,
            chat_id=chat_id,
            message_id=wa_message.pk,
            success=True,
            result_code="SENT",
            request_id=request_id,
            ip_address=ip_address,
        )

        logger.info(
            "WhatsApp message sent: user=%s prospect_contact=%s chat_id=%s message_id=%s",
            performed_by.username,
            prospect_contact.pk,
            chat_id,
            wa_message.pk,
        )

        return wa_message

    except WAHAServiceError as exc:
        # Failure path — update message record and Safety Guard counters.
        error_msg = str(exc)
        error_code = getattr(exc, "status_code", 500)

        with transaction.atomic():
            wa_message.status = WhatsAppMessage.Status.FAILED
            wa_message.error_message = error_msg
            wa_message.error_code = str(error_code)
            wa_message.save(update_fields=["status", "error_message", "error_code", "updated_at"])

            session.failed_send_count += 1
            session.consecutive_failed_sends += 1
            session.last_failed_message_at = timezone.now()
            session.last_failed_message_error = error_msg[:500]
            session.save(update_fields=[
                "failed_send_count",
                "consecutive_failed_sends",
                "last_failed_message_at",
                "last_failed_message_error",
            ])

        _write_audit_log(
            action=WhatsAppAuditLog.Action.MESSAGE_FAILED,
            performed_by=performed_by,
            prospect_contact=prospect_contact,
            session_name=session_name,
            chat_id=chat_id,
            message_id=wa_message.pk,
            success=False,
            result_code=str(error_code),
            result_detail=error_msg,
            request_id=request_id,
            ip_address=ip_address,
        )

        logger.error(
            "WhatsApp send failed: user=%s chat_id=%s error=%s consecutive_failures=%d",
            performed_by.username,
            chat_id,
            error_msg,
            session.consecutive_failed_sends,
        )

        # Check if Safety Guard should trigger (ignore session disconnect/state errors).
        is_session_state_err = any(
            k in error_msg.lower() for k in ("not in working state", "does not exist", "not connected", "unreachable", "timed out")
        )
        if not is_session_state_err and session.consecutive_failed_sends >= config.consecutive_failure_threshold:
            _trigger_safety_stop(
                reason=(
                    f"Automatic safety stop: {session.consecutive_failed_sends} consecutive "
                    f"send failures. Last error: {error_msg}"
                ),
                session=session,
                user=performed_by,
            )

        raise WhatsAppError(
            f"WhatsApp message delivery failed: {error_msg}",
            code="WA_SEND_FAILED",
        ) from exc


# ---------------------------------------------------------------------------
# Admin controls
# ---------------------------------------------------------------------------

def admin_reset_safety_stop(performed_by, reason: str = "") -> None:
    """
    Reset the Safety Guard stop. Only callable by Super Admin.

    This resumes outbound messaging. The admin must have reviewed the
    incident before calling this.
    """
    if not performed_by.is_superuser:
        raise WhatsAppAuthorizationError(
            "Only Super Admin can reset the WhatsApp safety stop."
        )

    config = _get_config()

    if not config.safety_stop_active:
        return  # Already not in safety stop.

    with transaction.atomic():
        config.safety_stop_active = False
        config.safety_stop_reason = None
        config.safety_stop_at = None
        config.save(update_fields=["safety_stop_active", "safety_stop_reason", "safety_stop_at"])

        WhatsAppSession.objects.filter(is_active=True).update(consecutive_failed_sends=0)

        WhatsAppSafetyEvent.objects.create(
            event_type=WhatsAppSafetyEvent.EventType.SAFETY_STOP_RESET,
            triggered_by=performed_by,
            details=reason or "Manual reset by Super Admin.",
        )

    _write_audit_log(
        action=WhatsAppAuditLog.Action.ADMIN_RESUMED,
        performed_by=performed_by,
        result_detail=reason or "Safety stop manually reset.",
        success=True,
    )

    logger.warning(
        "WhatsApp safety stop RESET by %s. Reason: %s. Outbound messaging resumed.",
        performed_by.username,
        reason or "No reason provided.",
    )


def admin_set_outbound_enabled(performed_by, enabled: bool, reason: str = "") -> None:
    """
    Enable or disable the global outbound kill switch.
    Only callable by Super Admin or Manager.
    """
    profile = getattr(performed_by, "profile", None)
    role = profile.role if profile else None

    if not performed_by.is_superuser and role not in ("MANAGER",):
        raise WhatsAppAuthorizationError(
            "Only Super Admin or Manager can change the outbound enabled setting."
        )

    config = _get_config()
    config.outbound_enabled = enabled
    config.save(update_fields=["outbound_enabled"])

    event_type = (
        WhatsAppSafetyEvent.EventType.OUTBOUND_ENABLED
        if enabled
        else WhatsAppSafetyEvent.EventType.OUTBOUND_DISABLED
    )

    WhatsAppSafetyEvent.objects.create(
        event_type=event_type,
        triggered_by=performed_by,
        details=reason or f"Outbound messaging {'enabled' if enabled else 'disabled'}.",
    )

    _write_audit_log(
        action=WhatsAppAuditLog.Action.CONFIG_CHANGED,
        performed_by=performed_by,
        result_detail=f"outbound_enabled set to {enabled}. Reason: {reason}",
        success=True,
    )

    logger.warning(
        "WhatsApp outbound_enabled set to %s by %s. Reason: %s",
        enabled,
        performed_by.username,
        reason or "No reason provided.",
    )


def register_opt_out(
    phone_digits: str,
    reason: str,
    prospect_contact=None,
    registered_by=None,
    trigger_message: str = "",
    session=None,
) -> WhatsAppOptOut:
    """
    Register a recipient opt-out.

    Blocks all future outbound messages to this phone number.
    """
    opt_out, created = WhatsAppOptOut.objects.get_or_create(
        phone_digits=phone_digits,
        defaults={
            "reason": reason,
            "prospect_contact": prospect_contact,
            "registered_by": registered_by,
            "trigger_message": trigger_message,
            "is_active": True,
        },
    )

    if not created and not opt_out.is_active:
        # Reactivate an existing opt-out.
        opt_out.is_active = True
        opt_out.reason = reason
        opt_out.registered_by = registered_by
        opt_out.trigger_message = trigger_message
        opt_out.reversed_by = None
        opt_out.reversed_at = None
        opt_out.reversal_reason = None
        opt_out.save()

    if created or not opt_out.is_active:
        _write_audit_log(
            action=WhatsAppAuditLog.Action.OPT_OUT_REGISTERED,
            performed_by=registered_by,
            prospect_contact=prospect_contact,
            session_name=session.session_name if session else "",
            result_detail=f"Opt-out registered for {phone_digits}. Reason: {reason}",
            success=True,
        )

        target_sess = session or (get_or_create_user_session(registered_by, create=False) if registered_by else None)
        if target_sess:
            target_sess.opt_out_count += 1
            target_sess.save(update_fields=["opt_out_count"])

    return opt_out


OPT_OUT_STANDALONE_PATTERN = re.compile(
    r"^\s*(stop|unsubscribe|cancel|quit|remove\s+me|dont\s+contact|do\s+not\s+contact|optout|opt\s+out|no\s+more)\s*[\.!\?]*\s*$",
    re.IGNORECASE,
)


def check_incoming_for_opt_out(message_body: str, phone_digits: str, prospect_contact=None) -> bool:
    """
    Check if an incoming message contains an opt-out command.
    Strictly matches standalone commands only (e.g. 'stop', 'unsubscribe') so normal
    conversational text containing words like 'stop' is never falsely marked as opted out.
    """
    if not message_body or not phone_digits:
        return False
    if len(phone_digits) < 7:
        return False

    body_trimmed = message_body.strip()
    if OPT_OUT_STANDALONE_PATTERN.match(body_trimmed):
        register_opt_out(
            phone_digits=phone_digits,
            reason=WhatsAppOptOut.Reason.INCOMING_KEYWORD,
            prospect_contact=prospect_contact,
            trigger_message=message_body[:500],
        )
        logger.info(
            "Opt-out keyword detected from %s. Keyword match: %r",
            phone_digits,
            body_trimmed,
        )
        return True

    return False
