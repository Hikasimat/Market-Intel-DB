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
from rest_framework.permissions import IsAuthenticated, IsAdminUser
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


def _get_owned_session(request, session_id=None, session_name=None):
    """
    Retrieve a WhatsAppSession that is owned by request.user.

    Returns WhatsAppSession or None.
    Superusers can access any session.
    """
    qs = WhatsAppSession.objects.all()
    if not request.user.is_superuser:
        qs = qs.filter(assigned_profiles__user=request.user)

    if session_id:
        return qs.filter(pk=session_id).first()
    if session_name:
        return qs.filter(session_name=session_name).first()
    return None


def _get_owned_conversation(request, conversation_id):
    """
    Retrieve a WhatsAppConversation owned by request.user.

    For normal users: conversation.session.owner == request.user
    For superusers: any conversation.
    Returns (conversation, error_response).
    """
    try:
        if request.user.is_superuser:
            conv = WhatsAppConversation.objects.select_related(
                "session", "session__owner", "prospect_contact", "prospect"
            ).get(pk=conversation_id)
        else:
            conv = WhatsAppConversation.objects.select_related(
                "session", "session__owner", "prospect_contact", "prospect"
            ).get(pk=conversation_id)
            
            is_assigned = conv.session.assigned_profiles.filter(user=request.user).exists()
            if not is_assigned and conv.session.phone_number:
                has_phone_access = WhatsAppSession.objects.filter(
                    phone_number=conv.session.phone_number,
                    assigned_profiles__user=request.user
                ).exists()
                if not has_phone_access:
                    raise WhatsAppConversation.DoesNotExist
            elif not is_assigned:
                raise WhatsAppConversation.DoesNotExist
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
    List WhatsApp sessions owned by the current user.
    Returns only sessions the current user owns.
    Super Admin can optionally list all sessions.
    """
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def get(self, request):
        try:
            from .client import get_waha_client
            client = get_waha_client()
            waha_sessions = client.get_all_sessions()
            waha_session_names = {s.get("name") for s in waha_sessions if s.get("name")}
            waha_status_map = {s.get("name"): s.get("status") for s in waha_sessions if s.get("name")}
            
            # Sync existing local sessions
            all_local_sessions = WhatsAppSession.objects.all()
            for s in all_local_sessions:
                waha_session_data = next((ws for ws in waha_sessions if ws.get("name") == s.session_name), None)
                
                if not waha_session_data:
                    new_status = "DISCONNECTED"
                else:
                    w_status = waha_session_data.get("status")
                    new_status = "READY" if w_status == "WORKING" else "STOPPED"
                    
                    # Also update the phone number if it connected
                    if w_status == "WORKING" and not s.phone_number:
                        me_info = waha_session_data.get("me")
                        if me_info and me_info.get("id"):
                            s.phone_number = me_info.get("id").split("@")[0]
                
                update_fields = []
                if s.status != new_status:
                    s.status = new_status
                    update_fields.append('status')
                
                # If we just assigned a phone number, we need to save it too
                if waha_session_data and waha_session_data.get("status") == "WORKING":
                    me_info = waha_session_data.get("me")
                    if me_info and me_info.get("id"):
                        new_phone = me_info.get("id").split("@")[0]
                        if s.phone_number != new_phone:
                            s.phone_number = new_phone
                            update_fields.append('phone_number')
                            
                if update_fields:
                    s.save(update_fields=update_fields)
                    
            # Auto-import missing sessions from WAHA
            existing_local_names = set(WhatsAppSession.objects.values_list("session_name", flat=True))
            for waha_session in waha_sessions:
                name = waha_session.get("name")
                if name and name not in existing_local_names:
                    status_val = "READY" if waha_session.get("status") == "WORKING" else "STOPPED"
                    phone_number = None
                    me_info = waha_session.get("me")
                    if me_info and me_info.get("id"):
                        phone_number = me_info.get("id").split("@")[0]
                        
                    new_s = WhatsAppSession.objects.create(
                        session_name=name,
                        status=status_val,
                        phone_number=phone_number,
                    )
                    if hasattr(request.user, "profile"):
                        new_s.assigned_profiles.add(request.user.profile)
                        
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Failed to sync sessions from WAHA: {e}")

        if request.user.is_superuser and request.query_params.get("all") == "true":
            sessions = WhatsAppSession.objects.all().order_by("-last_used_at", "-created_at")
        else:
            sessions = WhatsAppSession.objects.filter(
                assigned_profiles__user=request.user, is_active=True
            ).order_by("-last_used_at", "-created_at")
        return Response(WhatsAppSessionListSerializer(sessions, many=True).data)


# ---------------------------------------------------------------------------
# Session management
# ---------------------------------------------------------------------------

class WhatsAppStatusView(APIView):
    """Get WhatsApp session status for the current user's sessions."""
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def get(self, request):
        session_id = request.query_params.get("session_id")
        session_name = request.query_params.get("session")

        if session_id or session_name:
            session_obj = _get_owned_session(request, session_id=session_id, session_name=session_name)
            if not session_obj:
                return Response({"detail": "Session not found."}, status=status.HTTP_404_NOT_FOUND)
            try:
                status_data = get_session_status(session_name=session_obj.session_name)
            except WAHAServiceError as exc:
                return Response(
                    {"detail": "WhatsApp service is unavailable.", "session_status": "UNKNOWN"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            return Response({
                "session": WhatsAppSessionListSerializer(session_obj).data,
                "waha_status": status_data.get("waha_status", {}),
                "config": {
                    "outbound_enabled": _get_config().outbound_enabled,
                    "safety_stop_active": _get_config().safety_stop_active,
                },
            })

        # List all user's sessions with status.
        sessions = WhatsAppSession.objects.filter(assigned_profiles__user=request.user, is_active=True)
        return Response({
            "sessions": WhatsAppSessionListSerializer(sessions, many=True).data,
            "config": {
                "outbound_enabled": _get_config().outbound_enabled,
                "safety_stop_active": _get_config().safety_stop_active,
            },
        })


class WhatsAppQRView(APIView):
    """Get QR code for WhatsApp authentication for an owned session."""
    permission_classes = [IsAuthenticated, CanManageOwnWhatsAppSession]

    def get(self, request):
        session_name = request.query_params.get("session", "").strip()
        is_valid, err = _validate_session_name(session_name) if session_name else (False, "session parameter required")
        if not is_valid:
            return Response({"detail": err}, status=status.HTTP_400_BAD_REQUEST)

        # Verify ownership.
        session_obj = _get_owned_session(request, session_name=session_name)
        if not session_obj:
            return Response({"detail": "Session not found or not owned by you."}, status=status.HTTP_404_NOT_FOUND)

        try:
            result = get_qr(session_name=session_obj.session_name, performed_by=request.user)
            return Response(result)
        except WhatsAppError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except WAHAServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


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
    Super Admin only — this is a deliberate WAHA-level operation, NOT
    a MarketIntel application logout.
    """
    permission_classes = [IsAuthenticated, CanManageWhatsAppSession]

    def post(self, request):
        session_name = (request.data.get("session_name") or "").strip()
        is_valid, err = _validate_session_name(session_name)
        if not is_valid:
            return Response({"detail": err}, status=status.HTTP_400_BAD_REQUEST)

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
            # Fallback for unmatched chats (chat_id provided, no contact_id)
            # The conversation must be owned by the current user.
            from .client import get_waha_client
            import hashlib as _hashlib
            try:
                # Ownership-enforced conversation lookup.
                if request.user.is_superuser:
                    conv = WhatsAppConversation.objects.filter(chat_id=raw_chat_id).first()
                else:
                    conv = WhatsAppConversation.objects.filter(chat_id=raw_chat_id).first()
                    if conv:
                        is_assigned = conv.session.assigned_profiles.filter(user=request.user).exists()
                        if not is_assigned and conv.session.phone_number:
                            has_phone_access = WhatsAppSession.objects.filter(
                                phone_number=conv.session.phone_number,
                                assigned_profiles__user=request.user
                            ).exists()
                            if not has_phone_access:
                                return Response({"detail": "Conversation not found."}, status=status.HTTP_404_NOT_FOUND)
                        elif not is_assigned:
                            return Response({"detail": "Conversation not found."}, status=status.HTTP_404_NOT_FOUND)

                if not conv:
                    return Response({"detail": "Conversation not found."}, status=status.HTTP_404_NOT_FOUND)

                if conv.is_deleted:
                    conv.is_deleted = False
                    conv.save(update_fields=['is_deleted'])

                # Resolve the actual WAHA session from the conversation's session record.
                if not conv.session or not conv.session.session_name:
                    return Response({"detail": "No active session for this conversation."}, status=status.HTTP_400_BAD_REQUEST)
                
                actual_session_name = conv.session.session_name
                target_conv = conv
                
                # If current session isn't READY OR isn't assigned to the user, find an active one with the same phone number.
                is_assigned_to_user = request.user.is_superuser or conv.session.assigned_profiles.filter(user=request.user).exists()
                if (conv.session.status != "READY" or not is_assigned_to_user) and conv.session.phone_number:
                    active_session = WhatsAppSession.objects.filter(
                        phone_number=conv.session.phone_number,
                        status="READY",
                        assigned_profiles__user=request.user
                    ).first()
                    if not active_session and request.user.is_superuser:
                        active_session = WhatsAppSession.objects.filter(
                            phone_number=conv.session.phone_number,
                            status="READY"
                        ).first()
                    if active_session:
                        actual_session_name = active_session.session_name
                        target_conv, _ = WhatsAppConversation.objects.get_or_create(
                            session=active_session,
                            chat_id=raw_chat_id,
                            defaults={
                                "prospect_contact": conv.prospect_contact,
                                "prospect": conv.prospect,
                                "is_matched": conv.is_matched,
                                "whatsapp_name": conv.whatsapp_name,
                            }
                        )
                        if target_conv.is_deleted:
                            target_conv.is_deleted = False
                            target_conv.save(update_fields=['is_deleted'])
                    else:
                        return Response(
                            {"detail": "You do not have any active, assigned WhatsApp session for this contact's phone number. Please start a session and assign it to your profile first."},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                reply_to_id = None
                if raw_chat_id.endswith("@lid"):
                    # For Business accounts (@lid), WAHA often rejects direct sends (HTTP 400).
                    # We must reply to the last inbound message instead.
                    last_inbound = WhatsAppMessage.objects.filter(
                        conversation=conv, direction="INBOUND"
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
        Resolve the best WAHA session name for this user and contact.

        Priority:
          1. Existing conversation for this contact under a user-owned session.
          2. Any READY user-owned session.
          3. Any user-owned session.
          4. Empty string (service will handle the error).
        """
        phone = re.sub(r"\D+", "", contact.phone_number or "")
        if phone:
            chat_id = f"{phone}@c.us"
            conv = WhatsAppConversation.objects.filter(
                chat_id=chat_id,
                session__assigned_profiles__user=user,
                is_deleted=False,
            ).select_related("session").first()
            if conv and conv.session:
                return conv.session.session_name

        # Fall back to any ready session owned by user.
        ready_session = WhatsAppSession.objects.filter(
            assigned_profiles__user=user, status=WhatsAppSession.Status.READY, is_active=True
        ).first()
        if ready_session:
            return ready_session.session_name

        # Fall back to any session owned by user.
        any_session = WhatsAppSession.objects.filter(assigned_profiles__user=user, is_active=True).first()
        if any_session:
            return any_session.session_name

        return ""


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------

class WhatsAppConversationsView(APIView):
    """
    List WhatsApp conversations visible to the current user.

    Strictly scoped to conversations in sessions owned by request.user.
    Managers and Super Admins see only their own sessions' conversations
    through the normal endpoint — administrative access uses a separate path.
    """
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def get(self, request):
        session_id = request.query_params.get("session_id")

        if request.user.is_superuser:
            qs = WhatsAppConversation.objects.select_related(
                "prospect_contact", "prospect", "session"
            ).filter(is_deleted=False)
        else:
            qs = WhatsAppConversation.objects.select_related(
                "prospect_contact", "prospect", "session"
            ).filter(
                session__assigned_profiles__user=request.user,
                is_deleted=False,
            )

        if session_id:
            if request.user.is_superuser:
                session_obj = WhatsAppSession.objects.filter(id=session_id).first()
            else:
                session_obj = WhatsAppSession.objects.filter(id=session_id, assigned_profiles__user=request.user).first()

            if session_obj:
                # If phone_number is missing, try to fetch it dynamically from WAHA
                if not session_obj.phone_number:
                    import urllib.request
                    import json
                    import os
                    waha_url = os.environ.get("WHATSAPP_SERVICE_URL", "http://localhost:3000")
                    api_key = os.environ.get("WHATSAPP_SERVICE_API_KEY", "")
                    req = urllib.request.Request(f"{waha_url}/api/sessions/")
                    if api_key:
                        req.add_header("X-Api-Key", api_key)
                    try:
                        with urllib.request.urlopen(req, timeout=5) as resp:
                            waha_sessions = json.loads(resp.read().decode("utf-8"))
                            for ws in waha_sessions:
                                if ws.get("name") == session_obj.session_name:
                                    me_info = ws.get("me")
                                    if me_info and me_info.get("id"):
                                        session_obj.phone_number = me_info.get("id").split("@")[0]
                                        session_obj.save(update_fields=["phone_number"])
                                    break
                    except Exception as e:
                        print("Failed to dynamically fetch session phone_number:", e)
                
                if session_obj.phone_number:
                    # Filter the existing authorized qs to this phone number
                    qs = qs.filter(session__phone_number=session_obj.phone_number)
                else:
                    qs = qs.filter(session_id=session_id)
            else:
                # Session not found or not authorized for this user
                qs = qs.none()

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


class WhatsAppMessageDeleteView(APIView):
    """
    Soft-delete a WhatsApp message.

    Only the message sender (performed_by) or the session owner may delete it.
    Audit metadata is preserved; body/media are hidden from the UI.
    """
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def delete(self, request, message_id):
        try:
            if request.user.is_superuser:
                msg = WhatsAppMessage.objects.select_related(
                    "conversation", "conversation__session"
                ).get(pk=message_id)
            else:
                msg = WhatsAppMessage.objects.select_related(
                    "conversation", "conversation__session"
                ).get(pk=message_id, conversation__session__assigned_profiles__user=request.user)
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

    Security:
      - HMAC-SHA256 verification on raw request body.
      - Reject all events with invalid signatures.
      - Reject duplicate events.
      - Reject unknown event types.
      - All processing happens within a DB transaction.
      - Returns 200 immediately after verification.
    """
    authentication_classes = []  # No JWT on webhook.
    permission_classes = []      # Auth is via HMAC.

    def post(self, request):
        # Read raw body for HMAC verification.
        raw_body = request.body
        
        # Log headers to see what WAHA actually sends.
        logger.error("WEBHOOK HEADERS: %s", dict(request.headers))
        
        # Try multiple common signature headers in case WAHA uses a different one.
        signature = (
            request.headers.get("X-Webhook-Hmac") or
            request.headers.get("X-Hub-Signature-256") or
            request.headers.get("X-Hub-Signature") or
            request.headers.get("X-Whatsapp-Signature") or
            request.headers.get("X-Waha-Signature") or
            ""
        )
        # WAHA specifies the HMAC algorithm in a header (defaulting to sha256)
        algorithm = request.headers.get("X-Webhook-Hmac-Algorithm", "sha256")
        
        remote_addr = _get_client_ip(request)

        # DEBUG: Log raw payload (remove in production if desired).
        try:
            import json as _json
            _payload = _json.loads(raw_body.decode("utf-8"))
            _event_type = _payload.get("event") or _payload.get("type", "unknown")
            _event_data = _payload.get("payload") or _payload.get("data") or {}
            logger.debug(
                "WEBHOOK_DEBUG event=%s has_media=%s msg_type=%s from=%s",
                _event_type,
                _event_data.get("hasMedia"),
                _event_data.get("type"),
                _event_data.get("from", ""),
            )
        except Exception:
            pass

        try:
            event_record = process_webhook_event(
                raw_body=raw_body,
                signature_header=signature,
                algorithm=algorithm,
                remote_addr=remote_addr,
            )

            return Response(
                {"status": "received", "event_id": str(event_record.pk)},
                status=status.HTTP_200_OK,
            )

        except WebhookVerificationError as exc:
            logger.warning(
                "Webhook verification failed from %s: %s",
                remote_addr,
                str(exc),
            )
            return Response(
                {"detail": "Unauthorized."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        except WebhookDuplicateError:
            return Response({"status": "duplicate"}, status=status.HTTP_200_OK)

        except Exception as exc:
            logger.error(
                "Webhook processing unexpected error from %s: %s",
                remote_addr,
                str(exc),
                exc_info=True,
            )
            return Response({"status": "processing_error"}, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Authenticated media proxy
# ---------------------------------------------------------------------------

class WhatsAppMediaProxyView(APIView):
    """
    Proxies media files from WAHA through authenticated Django request.

    Requires authentication and verifies the requesting user owns the message
    that references this media URL.

    GET /api/whatsapp/media-proxy/?url=<waha_url>&message_id=<uuid>
    """
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def get(self, request):
        import urllib.request
        import urllib.error
        import urllib.parse
        from django.http import FileResponse

        message_id = request.query_params.get("message_id", "")
        if not message_id:
            return Response({"detail": "Missing message_id parameter."}, status=status.HTTP_400_BAD_REQUEST)

        # Ownership verification: require message_id and verify ownership.
        try:
            if request.user.is_superuser:
                msg = WhatsAppMessage.objects.select_related("conversation__session").get(pk=message_id)
            else:
                msg = WhatsAppMessage.objects.select_related("conversation__session").get(
                    pk=message_id,
                    conversation__session__assigned_profiles__user=request.user,
                )
        except WhatsAppMessage.DoesNotExist:
            return Response({"detail": "Media not found or unauthorized."}, status=status.HTTP_404_NOT_FOUND)

        if not msg.media_url and not msg.media_file:
             return Response({"detail": "No media associated with this message."}, status=status.HTTP_404_NOT_FOUND)

        # Serve from local storage if available
        if msg.media_file:
            try:
                return FileResponse(msg.media_file.open("rb"))
            except Exception:
                pass # fallback to WAHA proxy if file open fails but URL exists

        if not msg.media_url:
             return Response({"detail": "Media not available."}, status=status.HTTP_404_NOT_FOUND)
        
        waha_base_url = os.environ.get("WHATSAPP_SERVICE_URL", "http://localhost:3000").rstrip("/")
        api_key = os.environ.get("WHATSAPP_SERVICE_API_KEY", "")

        # Only allow deriving local WAHA URLs, preventing DNS rebinding/SSRF
        if not msg.media_url.startswith(waha_base_url) and not msg.media_url.startswith("http://localhost:3000") and not msg.media_url.startswith("http://host.docker.internal:3000"):
            return Response({"detail": "Invalid media location."}, status=status.HTTP_400_BAD_REQUEST)

        # Construct the WAHA URL securely based on waha_message_id and session
        session_name = msg.conversation.session.session_name
        dl_url = (
            f"{waha_base_url}/api/messages/"
            f"{urllib.parse.quote(msg.waha_message_id)}/download"
            f"?session={urllib.parse.quote(session_name)}"
        )

        req = urllib.request.Request(dl_url)
        if api_key:
            req.add_header("X-Api-Key", api_key)
            
        content = None
        content_type = "application/octet-stream"
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                content = resp.read()
                content_type = resp.headers.get("Content-Type", "application/octet-stream")
        except urllib.error.HTTPError as e:
            if content is None:
                return Response({"detail": "Media no longer available."}, status=status.HTTP_404_NOT_FOUND)
        except Exception:
            return Response({"detail": "Media unavailable."}, status=status.HTTP_404_NOT_FOUND)

        from django.http import HttpResponse
        response = HttpResponse(content, content_type=content_type)
        response["Cache-Control"] = "private, max-age=3600"
        return response



def models_Q(**kwargs):
    """Helper to import Q for complex queries."""
    from django.db.models import Q
    return Q(**kwargs)


# ---------------------------------------------------------------------------
# Authenticated send media
# ---------------------------------------------------------------------------

class WhatsAppSendMediaView(APIView):
    """
    Send a media file (image, document, audio, video) via WhatsApp.
    Accepts multipart/form-data with the file and optional caption.

    Session is always resolved from the conversation's owned session —
    never trusted from the frontend.
    """
    permission_classes = [IsAuthenticated, CanSendWhatsApp]

    def post(self, request):
        import base64
        import urllib.request
        import json as _json
        import hashlib as _hashlib

        chat_id = request.data.get("chat_id")
        caption = request.data.get("caption", "")
        uploaded_file = request.FILES.get("file")

        if not chat_id or not uploaded_file:
            return Response({"detail": "chat_id and file are required."}, status=status.HTTP_400_BAD_REQUEST)

        # Ownership-enforced conversation lookup.
        if request.user.is_superuser:
            conversation = WhatsAppConversation.objects.filter(chat_id=chat_id, is_deleted=False).first()
        else:
            conversation = WhatsAppConversation.objects.filter(
                chat_id=chat_id,
                session__assigned_profiles__user=request.user,
                is_deleted=False,
            ).first()

        if not conversation:
            return Response({"detail": "Conversation not found."}, status=status.HTTP_404_NOT_FOUND)

        # Resolve session from the conversation's owned session.
        if not conversation.session or not conversation.session.session_name:
            return Response({"detail": "No active session for this conversation."}, status=status.HTTP_400_BAD_REQUEST)

        session_name = conversation.session.session_name

        file_bytes = uploaded_file.read()
        mime = uploaded_file.content_type or "application/octet-stream"
        b64 = base64.b64encode(file_bytes).decode("utf-8")
        data_uri = f"data:{mime};base64,{b64}"

        # Determine message_type for DB and WAHA endpoint.
        if mime.startswith("image/"):
            endpoint = "sendImage"
            db_message_type = "image"
        elif mime.startswith("video/"):
            endpoint = "sendVideo"
            db_message_type = "video"
        elif mime.startswith("audio/"):
            endpoint = "sendVoice" if "ogg" in mime or "opus" in mime else "sendFile"
            db_message_type = "audio"
        else:
            endpoint = "sendFile"
            db_message_type = "document"

        waha_url = os.environ.get("WHATSAPP_SERVICE_URL", "http://localhost:3000")
        api_key = os.environ.get("WHATSAPP_SERVICE_API_KEY", "")

        payload = _json.dumps({
            "session": session_name,
            "chatId": chat_id,
            "file": {
                "mimetype": mime,
                "data": data_uri,
                "filename": uploaded_file.name,
            },
            "caption": caption,
        }).encode("utf-8")

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

        # Save the outbound media message to the database.
        try:
            body_hash = _hashlib.sha256((caption or '').encode()).hexdigest()
            waha_id = (waha_data.get("key") or {}).get("id") or waha_data.get("id", "")
            idem_key = _hashlib.sha256(
                f'outbound-media:{chat_id}:{waha_id}:{body_hash}'.encode()
            ).hexdigest()

            # Reset file pointer to save to DB.
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

            # Update conversation metadata.
            conversation.last_message_at = timezone.now()
            conversation.last_message_preview = caption or f'[Media: {uploaded_file.name}]'
            conversation.last_message_from_me = True
            conversation.save(update_fields=['last_message_at', 'last_message_preview', 'last_message_from_me'])

            # Update session last_used_at.
            WhatsAppSession.objects.filter(pk=conversation.session_id).update(last_used_at=timezone.now())

        except Exception as e:
            logger.error("Failed to save media message to DB: %s", e)
            return Response({"detail": "Media sent but failed to save record.", "waha_response": waha_data}, status=status.HTTP_200_OK)

        return Response(WhatsAppMessageSerializer(wa_msg).data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Authenticated profile picture and contact info
# ---------------------------------------------------------------------------

class WhatsAppProfilePicView(APIView):
    """
    Proxies profile picture fetching from WAHA.
    GET /api/whatsapp/profile-pic/<chat_id>/

    Requires authentication. Resolves session from the user's owned conversation.
    """
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def get(self, request, chat_id):
        import urllib.request
        import urllib.error
        import urllib.parse
        import json as _json

        waha_url = os.environ.get("WHATSAPP_SERVICE_URL", "http://localhost:3000")
        api_key = os.environ.get("WHATSAPP_SERVICE_API_KEY", "")

        # Resolve session from the user's owned conversation.
        session_name = self._resolve_session_for_chat(request.user, chat_id)
        if not session_name:
            return Response({"detail": "No session found for this chat."}, status=status.HTTP_404_NOT_FOUND)

        url = f"{waha_url}/api/contacts/profile-picture?session={urllib.parse.quote(session_name)}&contactId={urllib.parse.quote(chat_id)}"
        req = urllib.request.Request(url)
        if api_key:
            req.add_header("X-Api-Key", api_key)

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
                pic_url = data.get("profilePictureURL")
                if pic_url:
                    from django.http import HttpResponseRedirect
                    return HttpResponseRedirect(pic_url)
                else:
                    return Response({"detail": "No profile picture"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)

    def _resolve_session_for_chat(self, user, chat_id: str) -> str:
        """Resolve the WAHA session name for a chat_id owned by this user."""
        if user.is_superuser:
            conv = WhatsAppConversation.objects.filter(chat_id=chat_id).select_related("session").first()
        else:
            conv = WhatsAppConversation.objects.filter(
                chat_id=chat_id,
                session__assigned_profiles__user=user,
            ).select_related("session").first()

        if conv and conv.session:
            return conv.session.session_name

        # Fallback: use any ready session owned by user.
        session = WhatsAppSession.objects.filter(
            assigned_profiles__user=user, status=WhatsAppSession.Status.READY
        ).first()
        if session:
            return session.session_name

        return ""


class WhatsAppContactInfoView(APIView):
    """
    Proxies contact info fetching from WAHA.
    GET /api/whatsapp/contact-info/<chat_id>/

    Requires authentication. Resolves session from the user's owned conversation.
    """
    permission_classes = [IsAuthenticated, CanViewWhatsApp]

    def get(self, request, chat_id):
        import urllib.request
        import urllib.error
        import urllib.parse as _parse
        import json as _json

        waha_url = os.environ.get("WHATSAPP_SERVICE_URL", "http://localhost:3000")
        api_key = os.environ.get("WHATSAPP_SERVICE_API_KEY", "")

        # Resolve session from the user's owned conversation.
        session_name = self._resolve_session_for_chat(request.user, chat_id)
        if not session_name:
            return Response({"detail": "No session found for this chat."}, status=status.HTTP_404_NOT_FOUND)

        url = f"{waha_url}/api/contacts?session={_parse.quote(session_name)}&contactId={_parse.quote(chat_id)}"
        req = urllib.request.Request(url)
        if api_key:
            req.add_header("X-Api-Key", api_key)

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_404_NOT_FOUND)

        # Enrich with CRM company info from LQ pipeline (business logic preserved).
        phone_number = data.get("phoneNumber", "")
        if phone_number:
            import re as _re
            waha_digits = _re.sub(r"\D+", "", phone_number)
            waha_core_10 = waha_digits[-10:] if len(waha_digits) >= 10 else waha_digits

            try:
                from prospects.models import ProspectContact
                for contact in ProspectContact.objects.select_related("prospect").filter(
                    phone_number__isnull=False
                ):
                    stored_digits = _re.sub(r"\D+", "", contact.phone_number or "")
                    stored_core_10 = stored_digits[-10:] if len(stored_digits) >= 10 else stored_digits

                    if (stored_digits == waha_digits or
                        (len(waha_core_10) == 10 and stored_digits.startswith(waha_core_10)) or
                        (len(waha_core_10) == 10 and stored_core_10 == waha_core_10) or
                        (len(waha_core_10) >= 8 and waha_core_10 in stored_digits)
                       ):
                        if contact.prospect:
                            data["company"] = contact.prospect.company_name
                            data["contact_name"] = contact.contact_name
                        break
            except Exception:
                pass

        return Response(data)

    def _resolve_session_for_chat(self, user, chat_id: str) -> str:
        """Resolve the WAHA session name for a chat_id owned by this user."""
        if user.is_superuser:
            conv = WhatsAppConversation.objects.filter(chat_id=chat_id).select_related("session").first()
        else:
            conv = WhatsAppConversation.objects.filter(
                chat_id=chat_id,
                session__assigned_profiles__user=user,
            ).select_related("session").first()

        if conv and conv.session:
            return conv.session.session_name

        session = WhatsAppSession.objects.filter(
            assigned_profiles__user=user, status=WhatsAppSession.Status.READY
        ).first()
        if session:
            return session.session_name

        return ""

class WhatsAppSessionAssignView(APIView):
    """
    Super Admin only: reassign a WhatsApp session to a different user.
    """
    permission_classes = [IsAuthenticated, CanManageWhatsAppSession]

    def post(self, request):
        session_id = request.data.get("session_id")
        user_id = request.data.get("user_id")
        
        if not session_id or not user_id:
            return Response({"detail": "session_id and user_id are required."}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            from django.contrib.auth import get_user_model
            User = get_user_model()
            session = WhatsAppSession.objects.get(pk=session_id)
            user = User.objects.get(pk=user_id)
            
            session.owner = user
            session.save()
            return Response({"detail": f"Session '{session.session_name}' assigned to {user.username}."})
        except WhatsAppSession.DoesNotExist:
            return Response({"detail": "Session not found."}, status=status.HTTP_404_NOT_FOUND)
        except User.DoesNotExist:
            return Response({"detail": "User not found."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
