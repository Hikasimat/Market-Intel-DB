"""
backend/whatsapp/urls.py

URL patterns for the WhatsApp integration module.

Register in config/urls.py with:
    path('api/whatsapp/', include('whatsapp.urls')),

All endpoints require authentication EXCEPT:
  - /webhook/  (HMAC-authenticated)
  - /health/   (monitoring, no auth)
"""

from django.urls import path

from .views import (
    WhatsAppAuditLogView,
    WhatsAppConfigView,
    WhatsAppContactInfoView,
    WhatsAppCRMContactsView,
    WhatsAppConversationAvatarView,
    WhatsAppConversationDeleteView,
    WhatsAppConversationLinkCRMView,
    WhatsAppConversationMessagesView,
    WhatsAppConversationSyncView,
    WhatsAppConversationsView,
    WhatsAppHealthView,
    WhatsAppMarkReadView,
    WhatsAppMediaProxyView,
    WhatsAppMessageDeleteView,
    WhatsAppOptOutsView,
    WhatsAppPairingCodeView,
    WhatsAppProfilePicView,
    WhatsAppQRView,
    WhatsAppResetSafetyStopView,
    WhatsAppSafetyEventsView,
    WhatsAppSendMediaView,
    WhatsAppSendMessageView,
    WhatsAppSessionListView,
    WhatsAppSessionLogoutView,
    WhatsAppSessionRegisterView,
    WhatsAppSessionStartView,
    WhatsAppSessionStopView,
    WhatsAppSetOutboundView,
    WhatsAppStatusView,
    WhatsAppWebhookView,
)

urlpatterns = [
    # -- Health (no auth) --------------------------------------------------
    path("health/", WhatsAppHealthView.as_view(), name="whatsapp-health"),

    # -- Media proxy (authenticated, ownership-verified) -------------------
    path("media-proxy/", WhatsAppMediaProxyView.as_view(), name="whatsapp-media-proxy"),

    # -- Profile / contact info (authenticated, session-resolved) ----------
    path("profile-pic/<str:chat_id>/", WhatsAppProfilePicView.as_view(), name="whatsapp-profile-pic"),
    path("contact-info/<str:chat_id>/", WhatsAppContactInfoView.as_view(), name="whatsapp-contact-info"),

    # -- Webhook (HMAC auth, no JWT) ----------------------------------------
    path("webhook/", WhatsAppWebhookView.as_view(), name="whatsapp-webhook"),

    # -- Session registration and listing (LQ / Super Admin) ---------------
    path("session/register/", WhatsAppSessionRegisterView.as_view(), name="whatsapp-session-register"),
    path("session/list/", WhatsAppSessionListView.as_view(), name="whatsapp-session-list"),

    # -- Session management (own sessions / Super Admin) --------------------
    path("status/", WhatsAppStatusView.as_view(), name="whatsapp-status"),
    path("qr/", WhatsAppQRView.as_view(), name="whatsapp-qr"),
    path("pair-code/", WhatsAppPairingCodeView.as_view(), name="whatsapp-pair-code"),
    path("session/start/", WhatsAppSessionStartView.as_view(), name="whatsapp-session-start"),
    path("session/stop/", WhatsAppSessionStopView.as_view(), name="whatsapp-session-stop"),
    path("session/logout/", WhatsAppSessionLogoutView.as_view(), name="whatsapp-session-logout"),

    # -- Messaging (LQ / Super Admin) ----------------------------------------
    path("send/", WhatsAppSendMessageView.as_view(), name="whatsapp-send"),
    path("send-media/", WhatsAppSendMediaView.as_view(), name="whatsapp-send-media"),

    # -- Conversations (LQ / Manager) ----------------------------------------
    path("conversations/", WhatsAppConversationsView.as_view(), name="whatsapp-conversations"),
    path(
        "conversations/<uuid:conversation_id>/messages/",
        WhatsAppConversationMessagesView.as_view(),
        name="whatsapp-conversation-messages",
    ),
    path(
        "conversations/<uuid:conversation_id>/sync/",
        WhatsAppConversationSyncView.as_view(),
        name="whatsapp-conversation-sync",
    ),
    path(
        "conversations/<uuid:conversation_id>/read/",
        WhatsAppMarkReadView.as_view(),
        name="whatsapp-conversation-read",
    ),
    path(
        "conversations/<uuid:conversation_id>/link-crm/",
        WhatsAppConversationLinkCRMView.as_view(),
        name="whatsapp-conversation-link-crm",
    ),
    path(
        "conversations/<uuid:conversation_id>/avatar/",
        WhatsAppConversationAvatarView.as_view(),
        name="whatsapp-conversation-avatar",
    ),
    path(
        "crm-contacts/",
        WhatsAppCRMContactsView.as_view(),
        name="whatsapp-crm-contacts",
    ),
    path(
        "conversations/<uuid:conversation_id>/",
        WhatsAppConversationDeleteView.as_view(),
        name="whatsapp-conversation-delete",
    ),

    # -- Message management ------------------------------------------------
    path(
        "messages/<uuid:message_id>/",
        WhatsAppMessageDeleteView.as_view(),
        name="whatsapp-message-delete",
    ),

    # -- Configuration (Manager / Super Admin) --------------------------------
    path("config/", WhatsAppConfigView.as_view(), name="whatsapp-config"),
    path("config/outbound/", WhatsAppSetOutboundView.as_view(), name="whatsapp-outbound"),
    path(
        "config/safety-reset/",
        WhatsAppResetSafetyStopView.as_view(),
        name="whatsapp-safety-reset",
    ),

    # -- Monitoring / Audit (Manager / Super Admin) ---------------------------
    path("safety-events/", WhatsAppSafetyEventsView.as_view(), name="whatsapp-safety-events"),
    path("audit-log/", WhatsAppAuditLogView.as_view(), name="whatsapp-audit-log"),
    path("opt-outs/", WhatsAppOptOutsView.as_view(), name="whatsapp-opt-outs"),
]
