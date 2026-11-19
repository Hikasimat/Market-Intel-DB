"""
backend/whatsapp/serializers.py

DRF serializers for the WhatsApp module.

Security principles:
  - Read serializers expose only safe metadata fields.
  - No API keys, session secrets, or credentials are ever serialized.
  - Write serializers validate all inputs strictly.
  - Company isolation is enforced at the view layer (not serializer).
"""

from rest_framework import serializers
import re

from .models import (
    WhatsAppAuditLog,
    WhatsAppConfiguration,
    WhatsAppConversation,
    WhatsAppMessage,
    WhatsAppOptOut,
    WhatsAppSafetyEvent,
    WhatsAppSession,
    WhatsAppCallRecording,
)


class WhatsAppConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = WhatsAppConfiguration
        fields = [
            "outbound_enabled",
            "safety_stop_active",
            "safety_stop_reason",
            "safety_stop_at",
            "recipient_cooldown_minutes",
            "global_hourly_limit",
            "per_user_hourly_limit",
            "consecutive_failure_threshold",
            "updated_at",
        ]
        read_only_fields = [
            "safety_stop_active",
            "safety_stop_reason",
            "safety_stop_at",
            "updated_at",
        ]

    def validate_recipient_cooldown_minutes(self, value):
        if value < 1 or value > 10080:  # max 7 days
            raise serializers.ValidationError(
                "Cooldown must be between 1 and 10080 minutes (7 days)."
            )
        return value

    def validate_global_hourly_limit(self, value):
        if value < 1 or value > 500:
            raise serializers.ValidationError("Global hourly limit must be between 1 and 500.")
        return value

    def validate_per_user_hourly_limit(self, value):
        if value < 1 or value > 100:
            raise serializers.ValidationError("Per-user hourly limit must be between 1 and 100.")
        return value


class WhatsAppSessionSerializer(serializers.ModelSerializer):
    ai_enabled = serializers.SerializerMethodField()

    class Meta:
        model = WhatsAppSession
        fields = [
            "id",
            "session_name",
            "status",
            "phone_number",
            "ai_enabled",
            "last_health_check_at",
            "last_health_status",
            "send_count",
            "receive_count",
            "failed_send_count",
            "consecutive_failed_sends",
            "disconnect_count",
            "reconnect_count",
            "outbound_block_count",
            "cooldown_block_count",
            "opt_out_count",
            "last_successful_message_at",
            "last_failed_message_at",
            # Do NOT expose last_failed_message_error (may contain sensitive WAHA details).
            "started_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_ai_enabled(self, obj):
        from whatsapp_ai.gemini_service import is_session_ai_enabled
        return is_session_ai_enabled(obj)


class WhatsAppSessionListSerializer(serializers.ModelSerializer):
    """
    Session serializer for the UI session selector.
    Returns id, session_name, status, phone_number, and owner username.
    Owner details are read-only and non-sensitive.
    """
    owner_username = serializers.SerializerMethodField()
    ai_enabled = serializers.SerializerMethodField()

    class Meta:
        model = WhatsAppSession
        fields = [
            "id",
            "session_name",
            "status",
            "phone_number",
            "is_active",
            "ai_enabled",
            "last_used_at",
            "last_synced_at",
            "stopped_at",
            "owner_username",
            "started_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_owner_username(self, obj):
        if obj.owner:
            return obj.owner.username
        return None

    def get_ai_enabled(self, obj):
        from whatsapp_ai.gemini_service import is_session_ai_enabled
        return is_session_ai_enabled(obj)


class WhatsAppConversationSerializer(serializers.ModelSerializer):
    contact_name = serializers.SerializerMethodField()
    prospect_name = serializers.SerializerMethodField()
    prospect_phone = serializers.SerializerMethodField()
    phone_number = serializers.SerializerMethodField()
    contact_designation = serializers.SerializerMethodField()
    contact_email = serializers.SerializerMethodField()
    prospect_id = serializers.SerializerMethodField()
    is_group = serializers.SerializerMethodField()

    class Meta:
        model = WhatsAppConversation
        fields = [
            "id",
            "chat_id",
            "is_group",
            "phone_number",
            "is_matched",
            "whatsapp_name",
            "custom_avatar_url",
            "contact_name",
            "contact_designation",
            "contact_email",
            "prospect_name",
            "prospect_id",
            "prospect_phone",
            "account_phone",
            "prospect_contact",
            "unread_count",
            "last_message_at",
            "last_message_preview",
            "last_message_from_me",
            "updated_at",
        ]
        read_only_fields = fields

    def get_is_group(self, obj):
        return bool(obj.chat_id and obj.chat_id.endswith("@g.us"))

    def _is_lid(self, val):
        if not val:
            return False
        s = str(val).strip()
        if s.endswith("@lid"):
            return True
        digits = re.sub(r"\D+", "", s)
        return len(digits) > 13 or digits.startswith(("7658", "2262", "2167"))

    def _extract_verified_conversation_digits(self, obj) -> str:
        if obj.chat_id:
            cid = str(obj.chat_id).strip()
            if "@c.us" in cid.lower() or "@s.whatsapp.net" in cid.lower():
                raw = cid.split("@")[0].split(":")[0]
                digits = re.sub(r"\D+", "", raw)
                if digits and not self._is_lid(digits) and 7 <= len(digits) <= 15:
                    return digits
        if obj.phone_number:
            raw = str(obj.phone_number).strip()
            if not self._is_lid(raw):
                digits = re.sub(r"\D+", "", raw)
                if digits and not self._is_lid(digits) and 7 <= len(digits) <= 15:
                    return digits
        return ""

    def _has_verified_crm_contact(self, obj) -> bool:
        contact = getattr(obj, "prospect_contact", None)
        if not contact:
            return False
        conv_digits = self._extract_verified_conversation_digits(obj)
        if not conv_digits:
            return False
        contact_digits = re.sub(
            r"\D+",
            "",
            str(getattr(contact, "phone_number", None) or getattr(contact, "phone_digits", None) or ""),
        )
        if not contact_digits or contact_digits != conv_digits:
            return False
        session = getattr(obj, "session", None)
        owner = getattr(session, "owner", None) if session else None
        prospect = getattr(contact, "prospect", None)
        if owner and prospect and getattr(prospect, "created_by", None):
            if prospect.created_by != owner.username:
                return False
        return True

    def get_contact_name(self, obj):
        if obj.chat_id and obj.chat_id.endswith("@g.us"):
            return getattr(obj, "whatsapp_name", None) or "WhatsApp Group"

        # Priority 1: Actual sender's WhatsApp pushName / verified profile name
        w_name = (getattr(obj, "whatsapp_name", None) or "").strip()
        if (
            w_name
            and w_name.lower() != "whatsapp contact"
            and not self._is_lid(w_name)
            and "@" not in w_name
            and not w_name.startswith("+")
            and not re.fullmatch(r"[\d\s\-\+\(\)]+", w_name)
        ):
            return w_name

        # Priority 2: Verified CRM contact name (exact phone + owner scope verified)
        if self._has_verified_crm_contact(obj) and obj.prospect_contact.contact_name:
            return obj.prospect_contact.contact_name.strip()

        # Priority 3: Sender's verified phone number or safe unresolved WhatsApp identifier
        phone = self.get_phone_number(obj)
        if phone:
            return phone
        if obj.chat_id:
            return str(obj.chat_id)
        return "WhatsApp Contact"

    def get_prospect_name(self, obj):
        if self._has_verified_crm_contact(obj):
            if obj.prospect_contact.prospect and obj.prospect_contact.prospect.company_name:
                return obj.prospect_contact.prospect.company_name
            if obj.prospect and obj.prospect.company_name:
                return obj.prospect.company_name
        return None

    def get_phone_number(self, obj):
        digits = self._extract_verified_conversation_digits(obj)
        if digits:
            return f"+{digits}"
        if self._has_verified_crm_contact(obj):
            val = getattr(obj.prospect_contact, "phone_number", None) or getattr(obj.prospect_contact, "phone", None)
            if val:
                c_digits = re.sub(r"\D+", "", str(val))
                if c_digits and not self._is_lid(c_digits):
                    return f"+{c_digits}"
        return None

    def get_prospect_phone(self, obj):
        return self.get_phone_number(obj)

    def get_contact_designation(self, obj):
        if self._has_verified_crm_contact(obj):
            return getattr(obj.prospect_contact, "designation", None)
        return None

    def get_contact_email(self, obj):
        if self._has_verified_crm_contact(obj):
            return getattr(obj.prospect_contact, "official_email", None)
        return None

    def get_prospect_id(self, obj):
        if self._has_verified_crm_contact(obj):
            if obj.prospect_contact.prospect_id:
                return str(obj.prospect_contact.prospect_id)
            if obj.prospect_id:
                return str(obj.prospect_id)
        return None


class WhatsAppMessageSerializer(serializers.ModelSerializer):
    performed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = WhatsAppMessage
        fields = [
            "id",
            "waha_message_id",
            "direction",
            "status",
            "body_preview",
            "message_type",
            "performed_by_name",
            "waha_timestamp",
            "sent_at",
            "delivered_at",
            "read_at",
            "created_at",
            "full_body",
            "has_media",
            "media_file",
            "media_mime_type",
            "media_url",
            "is_edited",
            "reply_context",
        ]
        read_only_fields = fields

    def get_performed_by_name(self, obj):
        if obj.performed_by:
            return obj.performed_by.get_full_name() or obj.performed_by.username
        if obj.error_code and obj.direction == "INBOUND":
            return obj.error_code
        return None


class SendMessageSerializer(serializers.Serializer):
    """
    Input serializer for outbound WhatsApp message sends.

    Requires explicit prospect_contact_id — no generic "to" + "message" endpoint.
    The backend resolves and validates the recipient from the Market Intel record.
    """
    prospect_contact_id = serializers.UUIDField(
        help_text="UUID of the ProspectContact (Key Person) to message.",
        required=False,
        allow_null=True
    )
    chat_id = serializers.CharField(
        help_text="Raw WhatsApp chat ID for unmatched conversations.",
        required=False,
        allow_null=True
    )
    message_body = serializers.CharField(
        max_length=4096,
        min_length=1,
        trim_whitespace=True,
        help_text="Plain-text message body.",
    )
    session_name = serializers.CharField(
        default="",
        max_length=100,
        required=False,
        allow_blank=True,
    )
    reply_to = serializers.CharField(
        max_length=255,
        required=False,
        allow_null=True,
        allow_blank=True,
    )
    mentions = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_null=True,
    )

    def validate_message_body(self, value):
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("Message body cannot be empty or whitespace only.")
        # Reject suspiciously long messages.
        if len(stripped) > 4096:
            raise serializers.ValidationError("Message exceeds 4096 character limit.")
        return stripped
        
    def validate(self, data):
        if not data.get("prospect_contact_id") and not data.get("chat_id"):
            raise serializers.ValidationError("Must provide either prospect_contact_id or chat_id.")
        return data


class WhatsAppOptOutSerializer(serializers.ModelSerializer):
    contact_name = serializers.SerializerMethodField()

    class Meta:
        model = WhatsAppOptOut
        fields = [
            "id",
            "phone_digits",
            "reason",
            "is_active",
            "contact_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_contact_name(self, obj):
        if obj.prospect_contact:
            return obj.prospect_contact.contact_name
        return None


class WhatsAppSafetyEventSerializer(serializers.ModelSerializer):
    triggered_by_name = serializers.SerializerMethodField()
    contact_name = serializers.SerializerMethodField()

    class Meta:
        model = WhatsAppSafetyEvent
        fields = [
            "id",
            "event_type",
            "triggered_by_name",
            "contact_name",
            "details",
            "consecutive_failures_at_event",
            "created_at",
        ]
        read_only_fields = fields

    def get_triggered_by_name(self, obj):
        if obj.triggered_by:
            return obj.triggered_by.get_full_name() or obj.triggered_by.username
        return "System"

    def get_contact_name(self, obj):
        if obj.prospect_contact:
            return obj.prospect_contact.contact_name
        return None


class WhatsAppAuditLogSerializer(serializers.ModelSerializer):
    performed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = WhatsAppAuditLog
        fields = [
            "id",
            "action",
            "performed_by_name",
            "performed_by_role",
            "prospect_name",
            "prospect_contact_name",
            "session_name",
            "chat_id",
            "success",
            "result_code",
            "result_detail",
            "created_at",
        ]
        read_only_fields = fields

    def get_performed_by_name(self, obj):
        if obj.performed_by:
            return obj.performed_by.get_full_name() or obj.performed_by.username
        return "System"


class ResetSafetyStopSerializer(serializers.Serializer):
    """Input for Super Admin safety stop reset."""
    reason = serializers.CharField(
        max_length=1000,
        required=True,
        help_text="Required: explanation of why the safety stop is being reset.",
    )

    def validate_reason(self, value):
        stripped = value.strip()
        if len(stripped) < 10:
            raise serializers.ValidationError(
                "Please provide a meaningful reason (at least 10 characters)."
            )
        return stripped


class SetOutboundEnabledSerializer(serializers.Serializer):
    """Input for enabling/disabling the global outbound kill switch."""
    enabled = serializers.BooleanField()
    reason = serializers.CharField(max_length=500, required=False, default="")


class WhatsAppCallRecordingSerializer(serializers.ModelSerializer):
    """
    Serializer for WhatsApp VoIP call recordings.
    Exposes safe metadata and authorized streaming/download endpoints.
    """
    stream_url = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()
    owner_username = serializers.CharField(source="user.username", read_only=True)

    class Meta:
        model = WhatsAppCallRecording
        fields = [
            "id",
            "call_id",
            "participant_phone",
            "participant_name",
            "direction",
            "duration_seconds",
            "file_format",
            "file_size_bytes",
            "status",
            "consent_confirmed",
            "consent_confirmed_at",
            "started_at",
            "ended_at",
            "created_at",
            "stream_url",
            "download_url",
            "owner_username",
        ]
        read_only_fields = fields

    def get_stream_url(self, obj):
        return f"/api/whatsapp/calls/recordings/{obj.id}/stream/"

    def get_download_url(self, obj):
        return f"/api/whatsapp/calls/recordings/{obj.id}/download/"


