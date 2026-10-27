"""
backend/whatsapp/views.py

Django REST Framework views for the WhatsApp integration.

Security design:
  - Every view requires authentication (IsAuthenticated).
  - Ownership chain enforced: request.user → WhatsAppSession.owner →
    WhatsAppConversation.session → WhatsAppMessage.conversation
  - No API key, session secret, or credential is ever returned.
  - The webhook endpoint bypasses JWT auth (uses HMAC instead).
  - Webhook processing is stateless and reject-first.
  - Media proxy is authenticated and ownership-verified.

Endpoints:
  GET    /api/whatsapp/status/                         Session status (own sessions)
  GET    /api/whatsapp/qr/                             QR code (own session)
  POST   /api/whatsapp/session/register/               Register a new session name (LQ/Super Admin)
  GET    /api/whatsapp/session/list/                   List own sessions
  POST   /api/whatsapp/session/start/                  Start session (own session / Super Admin)
  POST   /api/whatsapp/session/stop/                   Stop session (own session / Super Admin)
  POST   /api/whatsapp/session/logout/                 Logout session (Super Admin only)
  POST   /api/whatsapp/send/                           Send message (LQ only)
  POST   /api/whatsapp/send-media/                     Send media (LQ only)
  GET    /api/whatsapp/conversations/                  List own conversations (LQ/Manager)
  GET    /api/whatsapp/conversations/<id>/messages/    Messages in own conversation
  POST   /api/whatsapp/conversations/<id>/sync/        Sync history for own conversation
  DELETE /api/whatsapp/conversations/<id>/             Soft-delete own conversation
  DELETE /api/whatsapp/messages/<id>/                  Soft-delete own message
  GET    /api/whatsapp/profile-pic/<chat_id>/          Profile pic (authenticated, own session)
  GET    /api/whatsapp/contact-info/<chat_id>/         Contact info (authenticated, own session)
  GET    /api/whatsapp/media-proxy/                    Media proxy (authenticated, ownership verified)
  GET    /api/whatsapp/config/                         Get config (Manager/Admin)
  PATCH  /api/whatsapp/config/                         Update config (Manager/Admin)
  POST   /api/whatsapp/config/safety-reset/            Reset safety stop (Super Admin)
  POST   /api/whatsapp/config/outbound/                Enable/disable outbound (Manager/Admin)
  GET    /api/whatsapp/audit-log/                      Audit log (Manager/Admin)
  GET    /api/whatsapp/safety-events/                  Safety events (Manager/Admin)
  GET    /api/whatsapp/opt-outs/                       Opt-out list (Manager/Admin)
  POST   /api/whatsapp/webhook/                        WAHA webhook (HMAC auth, no JWT)
  GET    /api/whatsapp/health/                         Internal health (no auth)
"""

import logging
import os
import re
import urllib.parse
import uuid

from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from prospects.models import ProspectContact

from .client import WAHAServiceError
from .models import (
    WhatsAppAuditLog,
    WhatsAppConversation,
    WhatsAppMessage,
    WhatsAppOptOut,
    WhatsAppSafetyEvent,
    WhatsAppSession,
)
from .permissions import (
    CanManageWhatsAppConfig,
    CanManageWhatsAppSession,
    CanManageOwnWhatsAppSession,
    CanResetSafetyStop,
    CanSendWhatsApp,
    CanViewAuditLog,
    CanViewWhatsApp,
)
from .serializers import (
    ResetSafetyStopSerializer,
    SendMessageSerializer,
    SetOutboundEnabledSerializer,
    WhatsAppAuditLogSerializer,
    WhatsAppConfigurationSerializer,
    WhatsAppConversationSerializer,
    WhatsAppMessageSerializer,
    WhatsAppOptOutSerializer,
    WhatsAppSafetyEventSerializer,
    WhatsAppSessionSerializer,
    WhatsAppSessionListSerializer,
)
from .services import (
    WhatsAppAuthorizationError,
    WhatsAppBlockedError,
    WhatsAppError,
    admin_reset_safety_stop,
    admin_set_outbound_enabled,
    get_qr,
    get_session_status,
    logout_session,
    send_whatsapp_message,
    start_session,
    stop_session,
    _get_config,
    _write_audit_log,
)
from .webhooks import (
    WebhookDuplicateError,
    WebhookVerificationError,
    process_webhook_event,
)

logger = logging.getLogger(__name__)

# Valid WAHA session name: letters, digits, hyphens, underscores only.
# Must be 1-80 chars, no path traversal, no shell metacharacters.
SESSION_NAME_RE = re.compile(r'^[A-Za-z0-9_\-]{1,80}$')


from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, AuthenticationFailed


def _get_client_ip(request) -> str:
    """Extract client IP from request headers."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def _get_request_id(request) -> str:
    """Extract or generate a request ID for tracing."""
    return (
        request.META.get("HTTP_X_REQUEST_ID") or
        request.META.get("HTTP_X_TRACE_ID") or
        str(uuid.uuid4())
    )


def _validate_session_name(name: str) -> tuple[bool, str]:
    """
    Validate a user-supplied WAHA session name.

    Returns (is_valid, error_message).
    """
    if not name:
        return False, "Session name cannot be blank."
    name = name.strip()
    if not name:
        return False, "Session name cannot be blank."
    if len(name) > 80:
        return False, "Session name must be 80 characters or fewer."
    if not SESSION_NAME_RE.match(name):
        return False, (
            "Session name may only contain letters, digits, hyphens, and underscores. "
            "No spaces or special characters allowed."
        )
    return True, ""


def _get_user_session(user, create=True) -> WhatsAppSession:
    """
    Resolve the active WhatsApp session belonging to the given user.
    Enforces per-user isolated sessions:
    - User 15 (LQ) retains session 'default'.
    - Other users get deterministic session 'user_{user.id}'.
    """
    if not user or not user.is_authenticated:
        return None

    # 1. Existing active session owned by this user
    session = WhatsAppSession.objects.filter(owner=user, is_active=True).first()
    if session:
        return session

    # 2. If user is User 15 (LQ) or session 'default' belongs to this user / unowned
    default_sess = WhatsAppSession.objects.filter(session_name="default", is_active=True).first()
    if default_sess and (default_sess.owner == user or (default_sess.owner is None and user.id == 15)):
        if default_sess.owner != user:
            default_sess.owner = user
            default_sess.save(update_fields=["owner"])
        return default_sess

    if not create:
        return None

    # 3. Create isolated per-user session
    session_name = f"user_{user.id}"
    session, _ = WhatsAppSession.objects.get_or_create(
        session_name=session_name,
        defaults={
            "owner": user,
            "status": WhatsAppSession.Status.DISCONNECTED,
            "is_active": True,
        }
    )
    if session.owner != user:
        session.owner = user
        session.save(update_fields=["owner"])
    return session


def _get_owned_session(request, session_id=None, session_name=None):
    """
    Retrieve an active WhatsAppSession for the requesting user.
    Superusers may access any session; normal users access only their own.
    """
    qs = WhatsAppSession.objects.filter(is_active=True)
    if not request.user.is_superuser:
        qs = qs.filter(owner=request.user)

    if session_id:
        return qs.filter(pk=session_id).first()
    if session_name:
        return qs.filter(session_name=session_name).first()

    return _get_user_session(request.user, create=True)


def _get_owned_conversation(request, conversation_id):
    """
    Retrieve a WhatsAppConversation.
    Returns (conversation, error_response).
    """
    try:
        conv = WhatsAppConversation.objects.select_related(
            "session", "session__owner", "prospect_contact", "prospect"
        ).get(pk=conversation_id)
    except WhatsAppConversation.DoesNotExist:
        return None, Response(
            {"detail": "Conversation not found."},
            status=status.HTTP_404_NOT_FOUND,
        )
    return conv, None


# ---------------------------------------------------------------------------
# Health (no authentication required — used by monitoring)
# ---------------------------------------------------------------------------

class WhatsAppHealthView(APIView):
    """Public health check endpoint for monitoring systems."""
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        try:
            config = _get_config()
            # Health is based on global config state, not a specific session.
            health_status = "HEALTHY"
            if config.safety_stop_active:
                health_status = "SAFETY_STOP"
            elif not config.outbound_enabled:
                health_status = "OUTBOUND_BLOCKED"

            return Response({
                "status": health_status,
                "outbound_enabled": config.outbound_enabled,
                "safety_stop_active": config.safety_stop_active,
            })
        except Exception:
            return Response({"status": "DEGRADED"})


# ---------------------------------------------------------------------------
# Session registration and listing
# ---------------------------------------------------------------------------

class WhatsAppSessionRegisterView(APIView):
    """
    Register a new WAHA session name for the current user.
    Creates a WhatsAppSession owned by request.user and starts it in WAHA.
    """
    permission_classes = [IsAuthenticated, IsAdminUser]

    def post(self, request):
        session_name = (request.data.get("session_name") or "").strip()
        is_valid, err = _validate_session_name(session_name)
        if not is_valid:
            return Response({"detail": err}, status=status.HTTP_400_BAD_REQUEST)

        # Prevent reuse of a session_name that already exists (global uniqueness for WAHA).
        if WhatsAppSession.objects.filter(session_name=session_name).exists():
            return Response(
                {"detail": "This session name is already registered. Please choose a different name."},
                status=status.HTTP_409_CONFLICT,
            )

        # Create the owned session record.
        session_obj = WhatsAppSession.objects.create(
            session_name=session_name,
            owner=request.user,
            status=WhatsAppSession.Status.DISCONNECTED,
        )

        # Attempt to start it in WAHA.
        try:
            start_session(performed_by=request.user, session_name=session_name)
            session_obj.status = WhatsAppSession.Status.STARTING
            session_obj.started_at = timezone.now()
            session_obj.save(update_fields=["status", "started_at"])
        except (WhatsAppError, WAHAServiceError) as exc:
            logger.warning("WAHA start failed for new session %s: %s", session_name, exc)
            # Still return the created session; user can retry start manually.

        _write_audit_log(
            action=WhatsAppAuditLog.Action.SESSION_REGISTERED,
            performed_by=request.user,
            session_name=session_name,
            success=True,
            result_detail="Session registered and start attempted.",
        )

        return Response(WhatsAppSessionListSerializer(session_obj).data, status=status.HTTP_201_CREATED)


class WhatsAppSessionListView(APIView):
    """
    List active WhatsApp sessions for the current user.
    Auto-syncs session states with WAHA.
    """
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def get(self, request):
        user_session = _get_user_session(request.user, create=True)
        try:
            from .client import get_waha_client
            client = get_waha_client()
            waha_sessions = client.get_all_sessions()

            sessions_to_sync = (
                list(WhatsAppSession.objects.filter(is_active=True))
                if request.user.is_superuser
                else [user_session]
            )
            for s in sessions_to_sync:
                waha_session_data = next((ws for ws in waha_sessions if ws.get("name") == s.session_name), None)
                if not waha_session_data:
                    new_status = "DISCONNECTED"
                else:
                    w_status = waha_session_data.get("status")
                    if w_status == "WORKING":
                        new_status = "READY"
                    elif w_status == "SCAN_QR_CODE":
                        new_status = "QR_REQUIRED"
                    elif w_status == "STARTING":
                        new_status = "STARTING"
                    else:
                        new_status = "STOPPED"

                    if w_status == "WORKING":
                        me_info = waha_session_data.get("me") or {}
                        phone = me_info.get("phone") or (me_info.get("id") or "").split("@")[0].split(":")[0]
                        if phone and s.phone_number != phone:
                            s.phone_number = phone

                update_fields = []
                if s.status != new_status:
                    s.status = new_status
                    update_fields.append('status')
                if s.phone_number and 'phone_number' not in update_fields:
                    update_fields.append('phone_number')

                if update_fields:
                    s.save(update_fields=update_fields)

        except Exception as e:
            logger.error(f"Failed to sync sessions from WAHA: {e}")

        # Non-superusers see strictly their own session
        if request.user.is_superuser and request.query_params.get("all") == "true":
            sessions = WhatsAppSession.objects.filter(is_active=True).order_by("-last_used_at", "-created_at")
        else:
            sessions = [user_session] if user_session else []

        return Response(WhatsAppSessionListSerializer(sessions, many=True).data)


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

class WhatsAppStatusView(APIView):
    """Get WhatsApp session status for the current user."""
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def get(self, request):
        user_session = _get_user_session(request.user, create=True)
        session_id = request.query_params.get("session_id")
        session_name = request.query_params.get("session")

        target_session = user_session
        if request.user.is_superuser and (session_id or session_name):
            target_session = _get_owned_session(request, session_id=session_id, session_name=session_name)
            if not target_session:
                return Response({"detail": "Session not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            status_data = get_session_status(session_name=target_session.session_name)
        except Exception:
            status_data = {"status": target_session.status}

        return Response({
            "session": WhatsAppSessionListSerializer(target_session).data,
            "sessions": WhatsAppSessionListSerializer([target_session], many=True).data,
            "waha_status": status_data.get("waha_status", {}),
            "status": status_data.get("status") or target_session.status,
            "phone_number": target_session.phone_number,
            "config": {
                "outbound_enabled": _get_config().outbound_enabled,
                "safety_stop_active": _get_config().safety_stop_active,
            },
        })


class WhatsAppQRView(APIView):
    """
    Get live QR code or connection status for WhatsApp authentication.
    Strictly isolated per user:
    - User 15 (LQ 1) manages their session (e.g. 'default').
    - User 19 (LQ 2) manages their own session (e.g. 'user_19').
    - Auto-starts WAHA session and streams live QR code.
    """
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def get(self, request):
        session_obj = _get_user_session(request.user, create=True)
        session_name = session_obj.session_name

        from .client import get_waha_client, WAHAServiceError
        from .webhooks import get_cached_qr
        import time
        client = get_waha_client()

        # Check live WAHA session status first
        waha_status = "UNKNOWN"
        me_info = {}
        try:
            waha_info = client.get_session_status(session_name)
            waha_status = waha_info.get("status")
            me_info = waha_info.get("me") or {}
        except Exception as e:
            logger.warning("Could not query WAHA session status for %s: %s", session_name, e)

        # 1. If session is already authenticated and WORKING
        if waha_status == "WORKING":
            phone = me_info.get("phone") or (me_info.get("id") or "").split("@")[0].split(":")[0]
            if session_obj.status != "READY" or (phone and session_obj.phone_number != phone):
                session_obj.status = WhatsAppSession.Status.READY
                if phone:
                    session_obj.phone_number = phone
                session_obj.save(update_fields=["status", "phone_number"])

            return Response({
                "status": "WORKING",
                "connected": True,
                "session_name": session_name,
                "phone_number": session_obj.phone_number,
                "me": me_info,
                "message": "WhatsApp is connected and ready.",
            })

        # 2. If session is FAILED or UNKNOWN or not in WAHA, auto-start it
        if waha_status in ("FAILED", "UNKNOWN") or not waha_status:
            try:
                client.delete_session(session_name)
            except Exception:
                pass
            try:
                client.start_session(session_name)
                waha_status = "STARTING"
            except Exception as start_err:
                logger.warning("Auto-start WAHA session %s: %s", session_name, start_err)
        elif waha_status == "STOPPED":
            try:
                client.start_session(session_name)
                waha_status = "STARTING"
            except Exception as start_err:
                logger.warning("Start WAHA session %s: %s", session_name, start_err)

        # 3. If STARTING, poll WAHA briefly (up to 3 seconds) for SCAN_QR_CODE or WORKING
        if waha_status == "STARTING":
            for _ in range(6):
                time.sleep(0.5)
                try:
                    waha_info = client.get_session_status(session_name)
                    waha_status = waha_info.get("status")
                    if waha_status in ("SCAN_QR_CODE", "WORKING"):
                        me_info = waha_info.get("me") or {}
                        break
                except Exception:
                    pass

        if waha_status == "WORKING":
            phone = me_info.get("phone") or (me_info.get("id") or "").split("@")[0].split(":")[0]
            session_obj.status = WhatsAppSession.Status.READY
            if phone:
                session_obj.phone_number = phone
            session_obj.save(update_fields=["status", "phone_number"])
            return Response({
                "status": "WORKING",
                "connected": True,
                "session_name": session_name,
                "phone_number": session_obj.phone_number,
                "me": me_info,
                "message": "WhatsApp is connected and ready.",
            })

        # 4. Check for cached QR event from webhook first
        cached_qr = get_cached_qr(session_name)
        if cached_qr and (cached_qr.get("qr") or cached_qr.get("qrBase64")):
            qr_base64 = cached_qr.get("qrBase64") or ""
            if qr_base64 and not qr_base64.startswith("data:image/"):
                qr_base64 = f"data:image/png;base64,{qr_base64}"
            return Response({
                "status": "SCAN_QR_CODE",
                "connected": False,
                "session_name": session_name,
                "qr": cached_qr.get("qr") or cached_qr.get("value"),
                "qrBase64": qr_base64,
                "value": cached_qr.get("value") or cached_qr.get("qr"),
            })

        # 5. Fetch live QR from WAHA
        try:
            qr_data = client.get_qr(session_name)
            qr_base64 = qr_data.get("qrBase64") or ""
            if qr_base64 and not qr_base64.startswith("data:image/"):
                qr_base64 = f"data:image/png;base64,{qr_base64}"
            qr_data["qrBase64"] = qr_base64
            qr_data["status"] = "SCAN_QR_CODE"
            qr_data["connected"] = False
            qr_data["session_name"] = session_name
            return Response(qr_data)
        except WAHAServiceError as exc:
            return Response({
                "status": waha_status if waha_status in ("STARTING", "SCAN_QR_CODE") else "STARTING",
                "connected": False,
                "session_name": session_name,
                "detail": str(exc),
            }, status=status.HTTP_200_OK)


class WhatsAppPairingCodeView(APIView):
    """
    Request an 8-character pairing code to link WhatsApp by phone number instead of QR scanning.
    POST /api/whatsapp/pair-code/
    Body: {"session_name": "default", "phone_number": "919003619221"}
    """
    permission_classes = [IsAuthenticated, CanManageOwnWhatsAppSession]

    def post(self, request):
        session_name = (request.data.get("session_name") or "default").strip()
        phone_number = (request.data.get("phone_number") or "").strip()
        if not phone_number:
            return Response({"detail": "Phone number is required."}, status=status.HTTP_400_BAD_REQUEST)

        clean_phone = re.sub(r"\D+", "", phone_number)
        if not clean_phone:
            return Response({"detail": "Valid phone number required."}, status=status.HTTP_400_BAD_REQUEST)

        from .client import get_waha_client
        client = get_waha_client()
        try:
            res = client.request_code(session_name, clean_phone)
            return Response(res, status=status.HTTP_200_OK)
        except Exception as exc:
            logger.error("Failed to request pairing code for %s: %s", session_name, exc)
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)



class WhatsAppSessionStartView(APIView):
    """Start a WAHA session. User can start own sessions; Super Admin can start any."""
    permission_classes = [IsAuthenticated, CanManageOwnWhatsAppSession]

    def post(self, request):
        session_name = (request.data.get("session_name") or "").strip()
        is_valid, err = _validate_session_name(session_name)
        if not is_valid:
            return Response({"detail": err}, status=status.HTTP_400_BAD_REQUEST)

        session_obj = _get_owned_session(request, session_name=session_name)
        if not session_obj:
            return Response({"detail": "Session not found or not owned by you."}, status=status.HTTP_404_NOT_FOUND)

        try:
            result = start_session(performed_by=request.user, session_name=session_obj.session_name)
            return Response(result)
        except WhatsAppError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except WAHAServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class WhatsAppSessionStopView(APIView):
    """Stop a WAHA session. User can stop own sessions; Super Admin can stop any."""
    permission_classes = [IsAuthenticated, CanManageOwnWhatsAppSession]

    def post(self, request):
        session_name = (request.data.get("session_name") or "").strip()
        is_valid, err = _validate_session_name(session_name)
        if not is_valid:
            return Response({"detail": err}, status=status.HTTP_400_BAD_REQUEST)

        session_obj = _get_owned_session(request, session_name=session_name)
        if not session_obj:
            return Response({"detail": "Session not found or not owned by you."}, status=status.HTTP_404_NOT_FOUND)

        try:
            result = stop_session(performed_by=request.user, session_name=session_obj.session_name)
            return Response(result)
        except WhatsAppError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class WhatsAppSessionLogoutView(APIView):
    """
    Logout from WhatsApp WAHA session (clears WhatsApp authentication).
    Session owners can log out their own session; Super Admin can log out any session.
    """
    permission_classes = [IsAuthenticated, CanManageOwnWhatsAppSession]

    def post(self, request):
        session_name = (request.data.get("session_name") or "").strip()
        if not session_name:
            user_session = _get_user_session(request.user, create=False)
            session_name = user_session.session_name if user_session else "default"

        is_valid, err = _validate_session_name(session_name)
        if not is_valid:
            return Response({"detail": err}, status=status.HTTP_400_BAD_REQUEST)

        session_obj = _get_owned_session(request, session_name=session_name)
        if not session_obj:
            return Response({"detail": "Session not found or not owned by you."}, status=status.HTTP_404_NOT_FOUND)

        if not request.user.is_superuser and session_obj.owner != request.user:
            return Response({"detail": "You can only disconnect your own WhatsApp session."}, status=status.HTTP_403_FORBIDDEN)

        try:
            result = logout_session(performed_by=request.user, session_name=session_name)
            return Response(result)
        except WhatsAppError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


# ---------------------------------------------------------------------------
# Messaging
# ---------------------------------------------------------------------------

class WhatsAppSendMessageView(APIView):
    """
    Send a WhatsApp message to an authorized ProspectContact (Key Person).
    LQ and Super Admin only.

    The backend resolves the WAHA session from the conversation's owned session —
    it never trusts session_name from the frontend for authorization.
    """
    permission_classes = [IsAuthenticated, CanSendWhatsApp]

    def post(self, request):
        serializer = SendMessageSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        contact_id = data.get("prospect_contact_id")
        raw_chat_id = data.get("chat_id")
        message_body = data["message_body"]

        if contact_id:
            # Resolve the ProspectContact and enforce authorization.
            try:
                contact = ProspectContact.objects.select_related("prospect").get(pk=contact_id)
            except ProspectContact.DoesNotExist:
                return Response({"detail": "Key person not found."}, status=status.HTTP_404_NOT_FOUND)

            # For the service call, resolve the session from the user's owned session
            # for this contact's conversation (if one exists), otherwise use any active session.
            session_name = self._resolve_session_name_for_user(request.user, contact)

            try:
                wa_message = send_whatsapp_message(
                    performed_by=request.user,
                    prospect_contact=contact,
                    message_body=message_body,
                    session_name=session_name,
                    intent_tag="manual",
                    request_id=_get_request_id(request),
                    ip_address=_get_client_ip(request),
                )
                return Response(
                    WhatsAppMessageSerializer(wa_message).data,
                    status=status.HTTP_201_CREATED,
                )
            except WhatsAppBlockedError as exc:
                return Response(
                    {"detail": str(exc), "code": getattr(exc, "code", "WA_BLOCKED")},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            except WhatsAppAuthorizationError as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
            except WhatsAppError as exc:
                return Response(
                    {"detail": str(exc), "code": getattr(exc, "code", "WA_ERROR")},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            # Direct chat send with chat_id (e.g. from "+ New Chat" or direct recipient)
            from .client import get_waha_client
            import hashlib as _hashlib
            try:
                user_session = _get_user_session(request.user, create=True)
                actual_session_name = user_session.session_name if user_session else "default"

                target_conv = WhatsAppConversation.objects.filter(
                    session=user_session,
                    chat_id=raw_chat_id
                ).first()

                if not target_conv:
                    existing_any = WhatsAppConversation.objects.filter(chat_id=raw_chat_id).first()
                    import re
                    digits = re.sub(r"\D+", "", raw_chat_id.split("@")[0].split(":")[0])
                    matched_contact = existing_any.prospect_contact if existing_any else None
                    if not matched_contact and digits and len(digits) >= 8:
                        from prospects.models import ProspectContact
                        suffix = digits[-10:] if len(digits) >= 10 else digits[-8:]
                        matched_contact = (
                            ProspectContact.objects.filter(phone_digits__endswith=suffix)
                            .select_related("prospect")
                            .first()
                        )
                        if not matched_contact:
                            for c in ProspectContact.objects.filter(phone_number__icontains=suffix).select_related("prospect"):
                                s_digits = re.sub(r"\D+", "", c.phone_number or "")
                                if s_digits and (s_digits == digits or s_digits.endswith(digits[-10:]) or digits.endswith(s_digits[-10:])):
                                    matched_contact = c
                                    break

                    phone_formatted = f"+{digits}" if digits else None
                    target_conv = WhatsAppConversation.objects.create(
                        session=user_session,
                        chat_id=raw_chat_id,
                        phone_number=phone_formatted,
                        prospect_contact=matched_contact,
                        prospect=matched_contact.prospect if matched_contact else (existing_any.prospect if existing_any else None),
                        is_matched=matched_contact is not None or (existing_any.is_matched if existing_any else False),
                        whatsapp_name=matched_contact.contact_name if matched_contact else (existing_any.whatsapp_name if existing_any else ""),
                    )

                if target_conv.is_deleted:
                    target_conv.is_deleted = False
                    target_conv.save(update_fields=['is_deleted'])

                reply_to_id = None
                if raw_chat_id.endswith("@lid"):
                    # For Business accounts (@lid), WAHA often rejects direct sends (HTTP 400).
                    # We must reply to the last inbound message instead.
                    last_inbound = WhatsAppMessage.objects.filter(
                        conversation=target_conv, direction="INBOUND"
                    ).order_by("-sent_at").first()
                    if last_inbound and last_inbound.waha_message_id:
                        reply_to_id = last_inbound.waha_message_id

                client = get_waha_client()
                waha_res = client.send_text(actual_session_name, raw_chat_id, message_body, reply_to=reply_to_id)

                body_hash = _hashlib.sha256(message_body.encode("utf-8")).hexdigest()

                msg = WhatsAppMessage.objects.create(
                    conversation=target_conv,
                    idempotency_key=str(uuid.uuid4()),
                    waha_message_id=waha_res.get("id") or (waha_res.get("key") or {}).get("id", ""),
                    direction="OUTBOUND",
                    body_preview=message_body[:200],
                    full_body=message_body,
                    body_hash=body_hash,
                    status="SENT",
                    sent_at=timezone.now(),
                    performed_by=request.user,
                )

                # Update conversation last-message metadata.
                target_conv.last_message_at = timezone.now()
                target_conv.last_message_preview = message_body[:200]
                target_conv.last_message_from_me = True
                target_conv.save(update_fields=["last_message_at", "last_message_preview", "last_message_from_me"])

                # Update session last_used_at.
                if target_conv.session_id:
                    WhatsAppSession.objects.filter(pk=target_conv.session_id).update(last_used_at=timezone.now())

                return Response(
                    WhatsAppMessageSerializer(msg).data,
                    status=status.HTTP_201_CREATED,
                )
            except Exception as exc:
                logger.error("WhatsApp send (unmatched chat) failed: %s", exc, exc_info=True)
                return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    def _resolve_session_name_for_user(self, user, contact) -> str:
        """
        Resolve the WAHA session name belonging to this specific user.
        """
        user_session = _get_user_session(user, create=True)
        if user_session:
            return user_session.session_name

        phone = re.sub(r"\D+", "", contact.phone_number or "")
        if phone:
            chat_id = f"{phone}@c.us"
            conv = WhatsAppConversation.objects.filter(
                chat_id=chat_id,
                is_deleted=False,
            ).select_related("session").first()
            if conv and conv.session:
                return conv.session.session_name

        return "default"


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

class WhatsAppConversationsView(APIView):
    """
    List WhatsApp conversations visible to the current user.
    Strictly isolated per user session.
    """
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def get(self, request):
        user = request.user
        session_id = request.query_params.get("session_id")
        user_session = _get_user_session(user, create=True)

        qs = WhatsAppConversation.objects.select_related(
            "prospect_contact", "prospect", "session"
        ).filter(is_deleted=False)

        if user.is_superuser and session_id:
            qs = qs.filter(session_id=session_id)
        else:
            # Strictly scoped to current user's session!
            qs = qs.filter(session=user_session)

        # Deduplicate by chat_id in Python and sort by last_message_at
        conversations = list(qs)
        unique_convs = {}
        for c in conversations:
            if c.chat_id not in unique_convs:
                unique_convs[c.chat_id] = c
            else:
                existing = unique_convs[c.chat_id]
                if c.last_message_at and existing.last_message_at:
                    if c.last_message_at > existing.last_message_at:
                        unique_convs[c.chat_id] = c
                elif c.last_message_at:
                    unique_convs[c.chat_id] = c

        final_list = list(unique_convs.values())

        # Opportunistic auto-matching for unmatched conversations
        import re
        from prospects.models import ProspectContact

        for c in final_list:
            if not c.is_matched or not c.prospect_contact:
                c_phone = c.chat_id.split("@")[0].split(":")[0]
                c_digits = re.sub(r"\D+", "", c_phone)

                if len(c_digits) >= 8:
                    suffix = c_digits[-10:] if len(c_digits) >= 10 else c_digits[-8:]
                    matched_c = (
                        ProspectContact.objects.filter(phone_digits__endswith=suffix)
                        .select_related("prospect")
                        .first()
                    )
                    if not matched_c:
                        for contact in ProspectContact.objects.filter(phone_number__icontains=suffix).select_related("prospect"):
                            stored_digits = re.sub(r"\D+", "", contact.phone_number or "")
                            if stored_digits and (
                                stored_digits == c_digits
                                or (len(c_digits) >= 10 and stored_digits.endswith(c_digits[-10:]))
                                or (len(stored_digits) >= 10 and c_digits.endswith(stored_digits[-10:]))
                            ):
                                matched_c = contact
                                break
                    if matched_c:
                        c.prospect_contact = matched_c
                        c.prospect = matched_c.prospect
                        c.is_matched = True
                        if not c.whatsapp_name or c.whatsapp_name.startswith("+"):
                            c.whatsapp_name = matched_c.contact_name
                        c.save(update_fields=["prospect_contact", "prospect", "is_matched", "whatsapp_name"])

        final_list.sort(key=lambda x: x.last_message_at or x.created_at, reverse=True)

        serializer = WhatsAppConversationSerializer(final_list[:100], many=True)
        return Response(serializer.data)


class WhatsAppConversationMessagesView(APIView):
    """Get messages for a specific owned conversation."""
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def get(self, request, conversation_id):
        conv, err = _get_owned_conversation(request, conversation_id)
        if err:
            return err

        if conv.is_deleted:
            return Response({"detail": "Conversation not found."}, status=status.HTTP_404_NOT_FOUND)

        limit = min(int(request.query_params.get("limit", 2000)), 5000)
        
        if conv.session and conv.session.phone_number:
            messages = WhatsAppMessage.objects.filter(
                conversation__chat_id=conv.chat_id,
                conversation__session__phone_number=conv.session.phone_number,
                is_deleted=False,
            ).order_by("-created_at")[:limit]
        else:
            messages = WhatsAppMessage.objects.filter(
                conversation=conv,
                is_deleted=False,
            ).order_by("-created_at")[:limit]

        serializer = WhatsAppMessageSerializer(messages, many=True)
        return Response({
            "conversation": WhatsAppConversationSerializer(conv).data,
            "messages": serializer.data,
        })


class WhatsAppConversationSyncView(APIView):
    """Sync old messages from WAHA into the database (ownership enforced)."""
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def post(self, request, conversation_id):
        conv, err = _get_owned_conversation(request, conversation_id)
        if err:
            return err

        if conv.is_deleted:
            return Response({"detail": "Conversation not found."}, status=status.HTTP_404_NOT_FOUND)

        from .client import get_waha_client
        import hashlib
        from datetime import datetime, timezone as dt_timezone

        client = get_waha_client()
        if not conv.session or not conv.session.session_name:
            return Response({"detail": "No session associated with this conversation."}, status=status.HTTP_400_BAD_REQUEST)

        session_name = conv.session.session_name

        try:
            imported_count = 0
            offset = 0
            limit = 5000

            while True:
                _, res = client._request(
                    "GET", "/api/messages",
                    query={"session": session_name, "chatId": conv.chat_id, "limit": limit, "offset": offset, "downloadMedia": "false"}
                )

                if not res:
                    break

                new_in_chunk = 0
                for msg_data in res:
                    waha_id = msg_data.get("id")
                    if not waha_id or WhatsAppMessage.objects.filter(waha_message_id=waha_id).exists():
                        continue

                    direction = WhatsAppMessage.Direction.OUTBOUND if msg_data.get("fromMe") else WhatsAppMessage.Direction.INBOUND

                    body = msg_data.get("body")
                    if not body and msg_data.get("hasMedia"):
                        body = "(Media)"
                    elif not body:
                        body = ""

                    body_preview = body[:200]
                    body_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

                    ts = msg_data.get("timestamp")
                    if ts:
                        created_at = datetime.fromtimestamp(ts, tz=dt_timezone.utc)
                    else:
                        created_at = datetime.now(dt_timezone.utc)

                    WhatsAppMessage.objects.create(
                        conversation=conv,
                        idempotency_key=str(uuid.uuid4()),
                        waha_message_id=waha_id,
                        direction=direction,
                        body_preview=body_preview,
                        full_body=body,
                        body_hash=body_hash,
                        status=WhatsAppMessage.Status.DELIVERED,
                        created_at=created_at,
                    )
                    new_in_chunk += 1
                    imported_count += 1

                if len(res) < limit:
                    break

                offset += limit

            return Response({"detail": f"Synced {imported_count} new messages."})
        except Exception as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class WhatsAppConversationDeleteView(APIView):
    """
    Soft-delete a WhatsApp conversation.

    Only the conversation's session owner may delete it.
    CRM (Prospect/ProspectContact) data is never affected.
    """
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def delete(self, request, conversation_id):
        conv, err = _get_owned_conversation(request, conversation_id)
        if err:
            return err

        if conv.is_deleted:
            return Response({"detail": "Conversation already deleted."}, status=status.HTTP_404_NOT_FOUND)

        conv.is_deleted = True
        conv.deleted_at = timezone.now()
        conv.deleted_by = request.user
        conv.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

        _write_audit_log(
            action=WhatsAppAuditLog.Action.CONVERSATION_DELETED,
            performed_by=request.user,
            prospect_contact=conv.prospect_contact,
            session_name=conv.session.session_name if conv.session else "",
            chat_id=conv.chat_id,
            success=True,
            result_detail="Soft-deleted by owner.",
        )

        return Response({"detail": "Conversation deleted."}, status=status.HTTP_200_OK)

    def patch(self, request, conversation_id):
        """Update/rename contact or set phone for this conversation."""
        conv, err = _get_owned_conversation(request, conversation_id)
        if err:
            return err

        name = request.data.get("name") or request.data.get("whatsapp_name")
        phone = request.data.get("phone") or request.data.get("phone_number")

        update_fields = []
        if name is not None:
            conv.whatsapp_name = name.strip()
            update_fields.append("whatsapp_name")
        if phone is not None:
            clean_phone = phone.strip()
            conv.phone_number = clean_phone
            update_fields.append("phone_number")
            # Attempt to auto-match with CRM ProspectContact
            import re
            digits = re.sub(r"\D+", "", clean_phone)
            if digits and len(digits) >= 8:
                from prospects.models import ProspectContact
                suffix = digits[-10:] if len(digits) >= 10 else digits[-8:]
                matched_c = (
                    ProspectContact.objects.filter(phone_digits__endswith=suffix)
                    .select_related("prospect")
                    .first()
                )
                if not matched_c:
                    for c in ProspectContact.objects.filter(phone_number__icontains=suffix).select_related("prospect"):
                        stored = re.sub(r"\D+", "", c.phone_number or "")
                        if stored and (stored == digits or stored.endswith(digits[-10:]) or digits.endswith(stored[-10:])):
                            matched_c = c
                            break
                if matched_c:
                    conv.prospect_contact = matched_c
                    conv.prospect = matched_c.prospect
                    conv.is_matched = True
                    if not conv.whatsapp_name:
                        conv.whatsapp_name = matched_c.contact_name
                        if "whatsapp_name" not in update_fields:
                            update_fields.append("whatsapp_name")
                    update_fields.extend(["prospect_contact", "prospect", "is_matched"])

        if update_fields:
            conv.save(update_fields=list(set(update_fields)))

        return Response(WhatsAppConversationSerializer(conv).data, status=status.HTTP_200_OK)


class WhatsAppMessageDeleteView(APIView):
    """
    Soft-delete a WhatsApp message.

    Only the message sender (performed_by) or the session owner may delete it.
    Audit metadata is preserved; body/media are hidden from the UI.
    """
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def delete(self, request, message_id):
        try:
            msg = WhatsAppMessage.objects.select_related(
                "conversation", "conversation__session"
            ).get(pk=message_id)
        except WhatsAppMessage.DoesNotExist:
            return Response({"detail": "Message not found."}, status=status.HTTP_404_NOT_FOUND)

        if msg.is_deleted:
            return Response({"detail": "Message already deleted."}, status=status.HTTP_404_NOT_FOUND)

        msg.is_deleted = True
        msg.deleted_at = timezone.now()
        msg.deleted_by = request.user
        msg.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

        _write_audit_log(
            action=WhatsAppAuditLog.Action.MESSAGE_DELETED,
            performed_by=request.user,
            session_name=msg.conversation.session.session_name if msg.conversation.session else "",
            chat_id=msg.conversation.chat_id,
            message_id=msg.pk,
            success=True,
            result_detail="Soft-deleted by owner.",
        )

        return Response({"detail": "Message deleted."}, status=status.HTTP_200_OK)


class WhatsAppMarkReadView(APIView):
    """Mark all messages in a conversation as read."""
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def post(self, request, conversation_id):
        conv, err = _get_owned_conversation(request, conversation_id)
        if err:
            return err

        # Update backend unread count.
        conv.unread_count = 0
        conv.save(update_fields=["unread_count"])

        # Mark inbound messages as READ in DB.
        WhatsAppMessage.objects.filter(
            conversation=conv,
            direction=WhatsAppMessage.Direction.INBOUND,
            status__in=[WhatsAppMessage.Status.DELIVERED, WhatsAppMessage.Status.SENT, WhatsAppMessage.Status.PENDING],
        ).update(status=WhatsAppMessage.Status.READ, read_at=timezone.now())

        # Attempt to mark as read in WAHA if session is available.
        if conv.session and conv.session.session_name:
            try:
                from .client import get_waha_client
                client = get_waha_client()
                client._request("POST", "/api/sendSeen", payload={
                    "session": conv.session.session_name,
                    "chatId": conv.chat_id,
                })
            except Exception as exc:
                logger.warning("Failed to mark conversation as seen in WAHA: %s", exc)

        return Response({"detail": "Marked as read."})


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class WhatsAppConfigView(APIView):
    """Get or update WhatsApp configuration."""
    permission_classes = [IsAuthenticated, CanManageWhatsAppConfig]

    def get(self, request):
        config = _get_config()
        return Response(WhatsAppConfigurationSerializer(config).data)

    def patch(self, request):
        config = _get_config()
        serializer = WhatsAppConfigurationSerializer(
            config, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data)


class WhatsAppSetOutboundView(APIView):
    """Enable or disable the global outbound kill switch."""
    permission_classes = [IsAuthenticated, CanManageWhatsAppConfig]

    def post(self, request):
        serializer = SetOutboundEnabledSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            admin_set_outbound_enabled(
                performed_by=request.user,
                enabled=serializer.validated_data["enabled"],
                reason=serializer.validated_data.get("reason", ""),
            )
            return Response({"detail": "Outbound setting updated.", "enabled": serializer.validated_data["enabled"]})
        except WhatsAppAuthorizationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)


class WhatsAppResetSafetyStopView(APIView):
    """Reset the Safety Guard stop. Super Admin only."""
    permission_classes = [IsAuthenticated, CanResetSafetyStop]

    def post(self, request):
        serializer = ResetSafetyStopSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            admin_reset_safety_stop(
                performed_by=request.user,
                reason=serializer.validated_data["reason"],
            )
            return Response({"detail": "Safety stop reset. Outbound messaging may resume."})
        except WhatsAppAuthorizationError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)


# ---------------------------------------------------------------------------
# Monitoring / Audit
# ---------------------------------------------------------------------------

class WhatsAppSafetyEventsView(APIView):
    """List recent Safety Guard events."""
    permission_classes = [IsAuthenticated, CanViewAuditLog]

    def get(self, request):
        qs = WhatsAppSafetyEvent.objects.select_related(
            "triggered_by", "prospect_contact"
        ).order_by("-created_at")[:100]
        return Response(WhatsAppSafetyEventSerializer(qs, many=True).data)


class WhatsAppAuditLogView(APIView):
    """List WhatsApp audit log entries."""
    permission_classes = [IsAuthenticated, CanViewAuditLog]

    def get(self, request):
        qs = WhatsAppAuditLog.objects.select_related(
            "performed_by"
        ).order_by("-created_at")[:200]
        return Response(WhatsAppAuditLogSerializer(qs, many=True).data)


class WhatsAppOptOutsView(APIView):
    """List opt-out records."""
    permission_classes = [IsAuthenticated, CanViewAuditLog]

    def get(self, request):
        qs = WhatsAppOptOut.objects.select_related("prospect_contact").order_by("-created_at")
        return Response(WhatsAppOptOutSerializer(qs, many=True).data)


# ---------------------------------------------------------------------------
# Webhook endpoint
# ---------------------------------------------------------------------------

class WhatsAppWebhookView(APIView):
    """
    WAHA webhook receiver.
    This endpoint does NOT use JWT authentication.
    Instead, it verifies the HMAC signature from WAHA.
    """
    authentication_classes = []  # No JWT on webhook.
    permission_classes = []      # Auth is via HMAC.

    def post(self, request):
        raw_body = request.body
        
        signature = (
            request.headers.get("X-Webhook-Hmac") or
            request.headers.get("X-Hub-Signature-256") or
            request.headers.get("X-Hub-Signature") or
            request.headers.get("X-Whatsapp-Signature") or
            request.headers.get("X-Waha-Signature") or
            ""
        )
        algorithm = request.headers.get("X-Webhook-Hmac-Algorithm", "sha256")
        timestamp = (
            request.headers.get("X-Webhook-Timestamp") or
            request.headers.get("X-Timestamp") or
            ""
        )
        remote_addr = _get_client_ip(request)

        try:
            event_record = process_webhook_event(
                raw_body=raw_body,
                signature_header=signature,
                algorithm=algorithm,
                remote_addr=remote_addr,
                timestamp=timestamp,
            )

            event_id = str(event_record.pk) if event_record else "bypassed"
            return Response(
                {"status": "received", "event_id": event_id},
                status=status.HTTP_200_OK,
            )

        except WebhookVerificationError as exc:
            logger.warning("Webhook verification failed from %s: %s", remote_addr, str(exc))
            return Response({"detail": "Unauthorized."}, status=status.HTTP_401_UNAUTHORIZED)

        except WebhookDuplicateError:
            return Response({"status": "duplicate"}, status=status.HTTP_200_OK)

        except Exception as exc:
            logger.error("Webhook processing unexpected error from %s: %s", remote_addr, str(exc), exc_info=True)
            return Response({"status": "processing_error"}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Authenticated media proxy
# ---------------------------------------------------------------------------

class WhatsAppMediaProxyView(APIView):
    """
    Proxies media files from WAHA or local storage through authenticated Django request.
    Requires authentication and verifies the requesting user owns/has access to the message.
    GET /api/whatsapp/media-proxy/?url=<waha_url>&message_id=<uuid>
    """
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def get(self, request):
        import urllib.request
        import urllib.error
        import urllib.parse
        from django.http import FileResponse, HttpResponse

        message_id = request.query_params.get("message_id", "")
        if not message_id:
            return Response({"detail": "Missing message_id parameter."}, status=status.HTTP_400_BAD_REQUEST)

        # Ownership verification
        try:
            msg = WhatsAppMessage.objects.select_related("conversation__session").get(pk=message_id)
        except WhatsAppMessage.DoesNotExist:
            return Response({"detail": "Media not found or unauthorized."}, status=status.HTTP_404_NOT_FOUND)

        if not msg.media_url and not msg.media_file:
            return Response({"detail": "No media associated with this message."}, status=status.HTTP_404_NOT_FOUND)

        # 1. Serve from local storage if file is present on disk
        if msg.media_file:
            try:
                mime_type = msg.media_mime_type or "application/octet-stream"
                response = FileResponse(msg.media_file.open("rb"), content_type=mime_type)
                response["Cache-Control"] = "private, max-age=86400"
                return response
            except Exception as e:
                logger.warning("Local media file open failed: %s, falling back to media_url", e)

        if not msg.media_url:
            return Response({"detail": "Media not available."}, status=status.HTTP_404_NOT_FOUND)

        waha_base_url = os.environ.get("WHATSAPP_SERVICE_URL", "http://localhost:3000").rstrip("/")
        api_key = os.environ.get("WHATSAPP_SERVICE_API_KEY", "")

        raw_url = msg.media_url.strip()
        if raw_url.startswith("http://") or raw_url.startswith("https://"):
            parsed = urllib.parse.urlparse(raw_url)
            target_url = f"{waha_base_url}{parsed.path}"
            if parsed.query:
                target_url += f"?{parsed.query}"
        elif raw_url.startswith("/"):
            target_url = f"{waha_base_url}{raw_url}"
        else:
            session_name = msg.conversation.session.session_name if (msg.conversation and msg.conversation.session) else "default"
            target_url = f"{waha_base_url}/api/files/{session_name}/{raw_url}"

        req = urllib.request.Request(target_url)
        if api_key:
            req.add_header("X-Api-Key", api_key)

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                content = resp.read()
                content_type = resp.headers.get("Content-Type") or msg.media_mime_type or "application/octet-stream"
                response = HttpResponse(content, content_type=content_type)
                response["Cache-Control"] = "private, max-age=86400"
                return response
        except Exception as exc:
            logger.error("Media proxy error fetching %s: %s", target_url, exc)
            return Response({"detail": "Media unavailable."}, status=status.HTTP_404_NOT_FOUND)


# ---------------------------------------------------------------------------
# Authenticated send media
# ---------------------------------------------------------------------------

class WhatsAppSendMediaView(APIView):
    """
    Send a media file (image, document, audio, video) via WhatsApp.
    Accepts multipart/form-data with file, chat_id, and optional caption.
    """
    permission_classes = [IsAuthenticated, CanSendWhatsApp]

    def post(self, request):
        import base64
        import urllib.request
        import json as _json
        import hashlib as _hashlib
        from django.db.models import Q

        chat_id = request.data.get("chat_id")
        caption = request.data.get("caption", "")
        uploaded_file = request.FILES.get("file")

        if not chat_id or not uploaded_file:
            return Response({"detail": "chat_id and file are required."}, status=status.HTTP_400_BAD_REQUEST)

        existing_conv = WhatsAppConversation.objects.filter(chat_id=chat_id, is_deleted=False).first()
        user_session = _get_user_session(request.user, create=True)
        session_name = user_session.session_name if user_session else (existing_conv.session.session_name if existing_conv and existing_conv.session else "default")

        target_conv, _ = WhatsAppConversation.objects.get_or_create(
            session=user_session,
            chat_id=chat_id,
            defaults={
                "prospect_contact": existing_conv.prospect_contact if existing_conv else None,
                "prospect": existing_conv.prospect if existing_conv else None,
                "is_matched": existing_conv.is_matched if existing_conv else False,
                "whatsapp_name": existing_conv.whatsapp_name if existing_conv else "",
            }
        )
        if target_conv.is_deleted:
            target_conv.is_deleted = False
            target_conv.save(update_fields=['is_deleted'])

        conversation = target_conv

        file_bytes = uploaded_file.read()
        mime = uploaded_file.content_type or "application/octet-stream"
        b64 = base64.b64encode(file_bytes).decode("utf-8")

        # Determine endpoint and DB message_type
        if mime.startswith("image/"):
            endpoint = "sendImage"
            db_message_type = "image"
        elif mime.startswith("video/"):
            endpoint = "sendFile"  # WAHA noweb-light handles videos through sendFile
            db_message_type = "video"
        elif mime.startswith("audio/"):
            endpoint = "sendVoice" if ("ogg" in mime or "opus" in mime or "webm" in mime) else "sendFile"
            db_message_type = "audio"
        else:
            endpoint = "sendFile"
            db_message_type = "document"

        waha_url = os.environ.get("WHATSAPP_SERVICE_URL", "http://localhost:3000").rstrip("/")
        api_key = os.environ.get("WHATSAPP_SERVICE_API_KEY", "")

        file_payload = {
            "mimetype": mime,
            "data": b64,
            "filename": uploaded_file.name or f"file.{mime.split('/')[-1]}",
        }

        request_body = {
            "session": session_name,
            "chatId": chat_id,
            "file": file_payload,
        }
        if caption:
            request_body["caption"] = caption

        payload = _json.dumps(request_body).encode("utf-8")

        req = urllib.request.Request(
            f"{waha_url}/api/{endpoint}",
            data=payload,
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        if api_key:
            req.add_header("X-Api-Key", api_key)

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                waha_data = _json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            logger.error("Failed to send media via WAHA: %s", e)
            return Response({"detail": f"Failed to send media: {e}"}, status=status.HTTP_502_BAD_GATEWAY)

        # Save the outbound media message to the database
        try:
            body_hash = _hashlib.sha256((caption or '').encode()).hexdigest()
            waha_id = (waha_data.get("key") or {}).get("id") or waha_data.get("id", "")
            idem_key = _hashlib.sha256(
                f'outbound-media:{chat_id}:{waha_id}:{body_hash}'.encode()
            ).hexdigest()

            uploaded_file.seek(0)

            wa_msg = WhatsAppMessage.objects.create(
                idempotency_key=idem_key,
                conversation=conversation,
                performed_by=request.user,
                waha_message_id=waha_id,
                direction=WhatsAppMessage.Direction.OUTBOUND,
                status=WhatsAppMessage.Status.SENT,
                body_preview=caption[:200] if caption else f'[{mime}]',
                full_body=caption or '',
                body_hash=body_hash,
                message_type=db_message_type,
                has_media=True,
                media_mime_type=mime,
                media_file=uploaded_file,
                sent_at=timezone.now(),
            )

            conversation.last_message_at = timezone.now()
            conversation.last_message_preview = caption or f'[Media: {uploaded_file.name}]'
            conversation.last_message_from_me = True
            conversation.save(update_fields=['last_message_at', 'last_message_preview', 'last_message_from_me'])

            WhatsAppSession.objects.filter(pk=conversation.session_id).update(last_used_at=timezone.now())

        except Exception as e:
            logger.error("Failed to save media message to DB: %s", e)
            return Response({"detail": "Media sent but failed to save record.", "waha_response": waha_data}, status=status.HTTP_200_OK)

        return Response(WhatsAppMessageSerializer(wa_msg).data, status=status.HTTP_200_OK)



# ---------------------------------------------------------------------------
# Authenticated profile picture, contact info & CRM linking
# ---------------------------------------------------------------------------

def generate_avatar_svg(name: str, chat_id: str) -> str:
    """Generate a clean, high-resolution SVG avatar for contacts."""
    import hashlib
    import html

    PALETTE = [
        "#00a884", "#0284c7", "#2563eb", "#7c3aed",
        "#c026d3", "#e11d48", "#ea580c", "#d97706",
        "#059669", "#475569", "#0891b2", "#4f46e5"
    ]

    seed = (name or chat_id or "wa").strip()
    color_index = int(hashlib.md5(seed.encode("utf-8")).hexdigest()[:6], 16) % len(PALETTE)
    bg_color = PALETTE[color_index]

    clean_name = (name or "").strip()
    words = [w for w in clean_name.split() if w and any(c.isalpha() for c in w)]

    if words:
        if len(words) == 1:
            initials = words[0][:2].upper()
        else:
            initials = (words[0][0] + words[-1][0]).upper()
        initials = html.escape(initials)

        return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">
  <circle cx="50" cy="50" r="50" fill="{bg_color}" />
  <text x="50" y="58" font-family="-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif" font-size="38" font-weight="600" fill="#ffffff" text-anchor="middle" dominant-baseline="middle">{initials}</text>
</svg>'''
    else:
        # Crisp white silhouette on contact's unique palette background
        return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100" height="100">
  <circle cx="50" cy="50" r="50" fill="{bg_color}" />
  <g fill="#ffffff" opacity="0.95">
    <circle cx="50" cy="38" r="18" />
    <path d="M 22 84 C 22 66 35 60 50 60 C 65 60 78 66 78 84 Z" />
  </g>
</svg>'''


class WhatsAppProfilePicView(APIView):
    """
    Returns profile picture for a WhatsApp contact.
    GET /api/whatsapp/profile-pic/<chat_id>/

    Publicly accessible so standard HTML <img> tags render without auth header issues.
    """
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, chat_id):
        import base64
        import urllib.request
        import urllib.error
        import urllib.parse
        import json as _json
        from django.http import HttpResponse, HttpResponseRedirect

        chat_id = urllib.parse.unquote(chat_id).strip()

        # Check conversation record
        conv = WhatsAppConversation.objects.filter(chat_id=chat_id).select_related(
            "prospect_contact", "prospect"
        ).first()
        if not conv and "@" not in chat_id:
            conv = WhatsAppConversation.objects.filter(chat_id__startswith=chat_id).select_related(
                "prospect_contact", "prospect"
            ).first()

        # 1. Custom avatar on conversation
        if conv and conv.custom_avatar_url:
            raw_url = conv.custom_avatar_url.strip()
            if raw_url.startswith("data:image"):
                try:
                    header, encoded = raw_url.split(",", 1)
                    mime = header.split(";")[0].split(":")[1]
                    decoded = base64.b64decode(encoded)
                    response = HttpResponse(decoded, content_type=mime)
                    response["Cache-Control"] = "public, max-age=86400"
                    return response
                except Exception:
                    pass
            elif raw_url.startswith("http://") or raw_url.startswith("https://") or raw_url.startswith("/media/"):
                return HttpResponseRedirect(raw_url)

        # 2. Try WAHA with a fast timeout (in case endpoint exists on custom engine)
        waha_url = os.environ.get("WHATSAPP_SERVICE_URL", "http://localhost:3000")
        api_key = os.environ.get("WHATSAPP_SERVICE_API_KEY", "")
        session_name = self._resolve_session_for_chat(request.user, chat_id)
        if session_name:
            try:
                url = f"{waha_url}/api/contacts/profile-picture?session={urllib.parse.quote(session_name)}&contactId={urllib.parse.quote(chat_id)}"
                req = urllib.request.Request(url)
                if api_key:
                    req.add_header("X-Api-Key", api_key)
                with urllib.request.urlopen(req, timeout=2) as resp:
                    data = _json.loads(resp.read().decode("utf-8"))
                    pic_url = data.get("url") or data.get("profilePictureURL") or data.get("picture")
                    if pic_url and isinstance(pic_url, str) and pic_url.startswith("http"):
                        if conv and not conv.custom_avatar_url:
                            conv.custom_avatar_url = pic_url
                            conv.save(update_fields=["custom_avatar_url"])
                        return HttpResponseRedirect(pic_url)
            except Exception:
                pass

        # 3. Dynamic crisp SVG avatar (always returns 200 OK)
        name = ""
        if conv:
            name = (
                conv.whatsapp_name
                or (conv.prospect_contact.contact_name if conv.prospect_contact else "")
            )
        svg_content = generate_avatar_svg(name, chat_id)
        response = HttpResponse(svg_content.encode("utf-8"), content_type="image/svg+xml")
        response["Cache-Control"] = "public, max-age=86400"
        return response

    def _resolve_session_for_chat(self, user, chat_id: str) -> str:
        """Resolve the WAHA session name for a chat_id."""
        conv = WhatsAppConversation.objects.filter(chat_id=chat_id).select_related("session").first()
        if conv and conv.session:
            return conv.session.session_name

        session = WhatsAppSession.objects.filter(status=WhatsAppSession.Status.READY, is_active=True).first()
        if session:
            return session.session_name

        default_session = WhatsAppSession.objects.filter(session_name="default", is_active=True).first()
        return default_session.session_name if default_session else "default"


class WhatsAppContactInfoView(APIView):
    """
    Get contact details & CRM linking information for a WhatsApp chat.
    GET /api/whatsapp/contact-info/<chat_id>/
    """
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def get(self, request, chat_id):
        conv = WhatsAppConversation.objects.filter(chat_id=chat_id).select_related(
            "prospect_contact", "prospect"
        ).first()

        clean_phone = chat_id.split("@")[0].split(":")[0]

        if conv:
            contact = conv.prospect_contact
            prospect = conv.prospect or (contact.prospect if contact else None)

            data = {
                "chatId": conv.chat_id,
                "phoneNumber": clean_phone,
                "name": conv.whatsapp_name or (contact.contact_name if contact else ""),
                "company": prospect.company_name if prospect else "",
                "contact_name": contact.contact_name if contact else "",
                "designation": getattr(contact, "designation", "") if contact else "",
                "official_email": getattr(contact, "official_email", "") if contact else "",
                "is_matched": conv.is_matched,
                "prospect_id": str(prospect.id) if prospect else None,
                "prospect_contact_id": str(contact.id) if contact else None,
                "custom_avatar_url": conv.custom_avatar_url or "",
            }
            return Response(data)

        # Fallback: search ProspectContact by indexed phone digits
        from prospects.models import ProspectContact
        import re
        digits = re.sub(r"\D+", "", clean_phone)
        matched = None
        if len(digits) >= 8:
            suffix = digits[-10:] if len(digits) >= 10 else digits[-8:]
            matched = (
                ProspectContact.objects.filter(phone_digits__endswith=suffix)
                .select_related("prospect")
                .first()
            )
            if not matched:
                for pc in ProspectContact.objects.filter(phone_number__icontains=suffix).select_related("prospect"):
                    stored = re.sub(r"\D+", "", pc.phone_number or "")
                    if stored and (stored == digits or (len(digits) >= 10 and stored.endswith(digits[-10:]))):
                        matched = pc
                        break

        if matched:
            return Response({
                "chatId": chat_id,
                "phoneNumber": clean_phone,
                "name": matched.contact_name,
                "company": matched.prospect.company_name if matched.prospect else "",
                "contact_name": matched.contact_name,
                "designation": matched.designation or "",
                "official_email": matched.official_email or "",
                "is_matched": True,
                "prospect_id": str(matched.prospect_id) if matched.prospect_id else None,
                "prospect_contact_id": str(matched.id),
                "custom_avatar_url": "",
            })

        return Response({
            "chatId": chat_id,
            "phoneNumber": clean_phone,
            "name": "",
            "company": "",
            "contact_name": "",
            "designation": "",
            "official_email": "",
            "is_matched": False,
            "prospect_id": None,
            "prospect_contact_id": None,
            "custom_avatar_url": "",
        })


class WhatsAppCRMContactsView(APIView):
    """
    Search and list CRM Key Persons (ProspectContact) for linking with WhatsApp chats.
    GET /api/whatsapp/crm-contacts/?search=...
    """
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def get(self, request):
        from prospects.models import ProspectContact
        from django.db.models import Q

        search = request.query_params.get("search", "").strip()
        qs = ProspectContact.objects.select_related("prospect").all()

        if search:
            qs = qs.filter(
                Q(contact_name__icontains=search)
                | Q(designation__icontains=search)
                | Q(phone_number__icontains=search)
                | Q(official_email__icontains=search)
                | Q(prospect__company_name__icontains=search)
            )

        contacts = qs.order_by("-created_at")[:100]

        results = []
        for c in contacts:
            results.append({
                "id": str(c.id),
                "contact_name": c.contact_name,
                "designation": c.designation or "",
                "phone_number": c.phone_number or "",
                "official_email": c.official_email or "",
                "company_name": c.prospect.company_name if c.prospect else "",
                "prospect_id": str(c.prospect_id) if c.prospect_id else None,
            })

        return Response(results)


class WhatsAppConversationLinkCRMView(APIView):
    """
    Link or unlink a WhatsApp conversation to/from a CRM ProspectContact.
    POST /api/whatsapp/conversations/<conversation_id>/link-crm/
    Body:
        { "prospect_contact_id": "<uuid>" }  # to link
        { "prospect_contact_id": null }      # to unlink
    """
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def post(self, request, conversation_id):
        conv, err = _get_owned_conversation(request, conversation_id)
        if err:
            return err

        contact_id = request.data.get("prospect_contact_id")

        if contact_id:
            from prospects.models import ProspectContact
            try:
                contact = ProspectContact.objects.select_related("prospect").get(id=contact_id)
            except ProspectContact.DoesNotExist:
                return Response({"detail": "CRM contact not found."}, status=status.HTTP_404_NOT_FOUND)

            conv.prospect_contact = contact
            conv.prospect = contact.prospect
            conv.is_matched = True

            # If current whatsapp_name is blank or just digits/LID, adopt contact name
            if not conv.whatsapp_name or conv.whatsapp_name.startswith("+") or "@lid" in conv.whatsapp_name:
                conv.whatsapp_name = contact.contact_name

            conv.save(update_fields=["prospect_contact", "prospect", "is_matched", "whatsapp_name"])
            try:
                _write_audit_log(
                    action="CRM_LINKED",
                    performed_by=request.user,
                    chat_id=conv.chat_id,
                    session_name=conv.session.session_name if conv.session else "",
                    prospect_contact=contact,
                    result_detail=f"Linked chat {conv.chat_id} to CRM contact {contact.contact_name}",
                )
            except Exception:
                pass
        else:
            # Unlink
            prev_contact = conv.prospect_contact.contact_name if conv.prospect_contact else "none"
            conv.prospect_contact = None
            conv.prospect = None
            conv.is_matched = False
            conv.save(update_fields=["prospect_contact", "prospect", "is_matched"])
            try:
                _write_audit_log(
                    action="CRM_UNLINKED",
                    performed_by=request.user,
                    chat_id=conv.chat_id,
                    session_name=conv.session.session_name if conv.session else "",
                    result_detail=f"Unlinked chat {conv.chat_id} from CRM contact {prev_contact}",
                )
            except Exception:
                pass

        serializer = WhatsAppConversationSerializer(conv)
        return Response(serializer.data, status=status.HTTP_200_OK)


class WhatsAppConversationAvatarView(APIView):
    """
    Set or upload a custom avatar for a WhatsApp conversation.
    POST /api/whatsapp/conversations/<conversation_id>/avatar/
    DELETE /api/whatsapp/conversations/<conversation_id>/avatar/
    """
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def post(self, request, conversation_id):
        conv, err = _get_owned_conversation(request, conversation_id)
        if err:
            return err

        uploaded_file = request.FILES.get("file")
        avatar_data = request.data.get("avatar_data")  # base64 data URL
        avatar_url = request.data.get("avatar_url")    # direct URL

        if uploaded_file:
            import os
            import time
            from django.conf import settings
            from django.core.files.storage import default_storage

            ext = os.path.splitext(uploaded_file.name)[1].lower() or ".jpg"
            if ext not in [".jpg", ".jpeg", ".png", ".webp", ".gif"]:
                ext = ".jpg"
            filename = f"avatar_{conv.id}_{int(time.time())}{ext}"
            saved_path = default_storage.save(f"whatsapp_avatars/{filename}", uploaded_file)

            rel_url = f"{settings.MEDIA_URL.rstrip('/')}/{saved_path.lstrip('/')}"
            conv.custom_avatar_url = rel_url
            conv.save(update_fields=["custom_avatar_url"])
            return Response({"custom_avatar_url": conv.custom_avatar_url}, status=status.HTTP_200_OK)

        elif avatar_data and avatar_data.startswith("data:image"):
            conv.custom_avatar_url = avatar_data
            conv.save(update_fields=["custom_avatar_url"])
            return Response({"custom_avatar_url": conv.custom_avatar_url}, status=status.HTTP_200_OK)

        elif avatar_url:
            conv.custom_avatar_url = avatar_url
            conv.save(update_fields=["custom_avatar_url"])
            return Response({"custom_avatar_url": conv.custom_avatar_url}, status=status.HTTP_200_OK)

        return Response({"detail": "No image file or avatar data provided."}, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, conversation_id):
        conv, err = _get_owned_conversation(request, conversation_id)
        if err:
            return err

        conv.custom_avatar_url = None
        conv.save(update_fields=["custom_avatar_url"])
        return Response({"detail": "Custom avatar removed."}, status=status.HTTP_200_OK)
