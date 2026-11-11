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
    WhatsAppCallAcceptView,
    WhatsAppCallPairView,
    WhatsAppCallEndView,
    WhatsAppCallRejectView,
    WhatsAppCallStartView,
    WhatsAppCallStatusView,
    WhatsAppCallWebRTCView,
    WhatsAppCallRecordingUploadView,
    WhatsAppCallRecordingListView,
    WhatsAppCallRecordingStreamView,
    WhatsAppCallRecordingDownloadView,
    WhatsAppCallRecordingDeleteView,
    WhatsAppConfigView,
    WhatsAppContactInfoView,
    WhatsAppCRMContactsView,
    WhatsAppConversationAvatarView,
    WhatsAppConversationDeleteView,
    WhatsAppConversationLinkCRMView,
    WhatsAppConversationMessagesView,
    WhatsAppConversationSyncView,
    WhatsAppConversationsView,
    WhatsAppGroupCreateView,
    WhatsAppGroupAddParticipantView,
    WhatsAppGroupRemoveParticipantView,
    WhatsAppGroupInviteLinkView,
    WhatsAppHealthView,
    WhatsAppMarkReadView,
    WhatsAppMediaProxyView,
    WhatsAppMessageDeleteView,
    WhatsAppMessageEditView,
    WhatsAppClearOptOutView,
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
    WhatsAppTwoDaySyncView,
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
    path("sync-history/", WhatsAppTwoDaySyncView.as_view(), name="whatsapp-sync-history"),
    path("groups/create/", WhatsAppGroupCreateView.as_view(), name="whatsapp-group-create"),
    path("groups/<str:chat_id>/participants/add/", WhatsAppGroupAddParticipantView.as_view(), name="whatsapp-group-add-participant"),
    path("groups/<str:chat_id>/participants/remove/", WhatsAppGroupRemoveParticipantView.as_view(), name="whatsapp-group-remove-participant"),
    path("groups/<str:chat_id>/invite-link/", WhatsAppGroupInviteLinkView.as_view(), name="whatsapp-group-invite-link"),
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
        "messages/<uuid:message_id>/edit/",
        WhatsAppMessageEditView.as_view(),
        name="whatsapp-message-edit",
    ),
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
    path("opt-outs/clear/", WhatsAppClearOptOutView.as_view(), name="whatsapp-opt-outs-clear"),
    path("opt-outs/", WhatsAppOptOutsView.as_view(), name="whatsapp-opt-outs"),

    # -- Voice Calling (WAHA / WaCalls WebRTC VoIP) ---------------------------
    path("calls/status/", WhatsAppCallStatusView.as_view(), name="whatsapp-call-status"),
    path("calls/pair/", WhatsAppCallPairView.as_view(), name="whatsapp-call-pair"),
    path("calls/start/", WhatsAppCallStartView.as_view(), name="whatsapp-call-start"),
    path("calls/<str:call_id>/accept/", WhatsAppCallAcceptView.as_view(), name="whatsapp-call-accept"),
    path("calls/<str:call_id>/reject/", WhatsAppCallRejectView.as_view(), name="whatsapp-call-reject"),
    path("calls/<str:call_id>/end/", WhatsAppCallEndView.as_view(), name="whatsapp-call-end"),
    path("calls/<str:call_id>/webrtc/", WhatsAppCallWebRTCView.as_view(), name="whatsapp-call-webrtc"),

    # -- Call Recordings ----------------------------------------------------
    path("calls/recordings/upload/", WhatsAppCallRecordingUploadView.as_view(), name="whatsapp-call-recording-upload"),
    path("calls/recordings/", WhatsAppCallRecordingListView.as_view(), name="whatsapp-call-recordings-list"),
    path("calls/recordings/<uuid:recording_id>/stream/", WhatsAppCallRecordingStreamView.as_view(), name="whatsapp-call-recording-stream"),
    path("calls/recordings/<uuid:recording_id>/download/", WhatsAppCallRecordingDownloadView.as_view(), name="whatsapp-call-recording-download"),
    path("calls/recordings/<uuid:recording_id>/", WhatsAppCallRecordingDeleteView.as_view(), name="whatsapp-call-recording-delete"),
    path("calls/recordings/<uuid:recording_id>/delete/", WhatsAppCallRecordingDeleteView.as_view(), name="whatsapp-call-recording-delete-alias"),
]
