import uuid
from django.conf import settings
from django.db import models
from django.utils import timezone


class WhatsAppAIAutoReplyConfig(models.Model):
    """
    Per-session Gemini AI auto-reply settings.
    Defaults to enabled=False (OFF) for newly connected accounts until explicitly
    enabled by the owning user.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField(
        "whatsapp.WhatsAppSession",
        on_delete=models.CASCADE,
        related_name="ai_auto_reply_config",
    )
    enabled = models.BooleanField(default=False)
    reply_to_groups = models.BooleanField(default=False)
    max_history_messages = models.PositiveIntegerField(default=20)
    model_name = models.CharField(max_length=128, blank=True, default="gemini-3.8-flash")
    system_instructions = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "WhatsApp AI Auto-Reply Config"
        verbose_name_plural = "WhatsApp AI Auto-Reply Configs"

    def __str__(self):
        return f"WhatsAppAIConfig({self.session.session_name}, enabled={self.enabled})"


class WhatsAppAIReplyLog(models.Model):
    """
    Idempotent audit record for Gemini AI-generated WhatsApp automatic replies.
    Ensures each incoming WhatsAppMessage receives at most one automatic reply
    and preserves traceability even when the session owner is logged out.
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        QUEUED = "QUEUED", "Queued"
        PROCESSING = "PROCESSING", "Processing"
        SENT = "SENT", "Sent"
        SKIPPED = "SKIPPED", "Skipped"
        FAILED = "FAILED", "Failed"
        SEND_UNKNOWN = "SEND_UNKNOWN", "Send Status Unknown"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        "whatsapp.WhatsAppSession",
        on_delete=models.CASCADE,
        related_name="ai_reply_logs",
    )
    conversation = models.ForeignKey(
        "whatsapp.WhatsAppConversation",
        on_delete=models.CASCADE,
        related_name="ai_reply_logs",
    )
    incoming_message = models.OneToOneField(
        "whatsapp.WhatsAppMessage",
        on_delete=models.CASCADE,
        related_name="ai_reply_log",
    )
    reply_message = models.ForeignKey(
        "whatsapp.WhatsAppMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_from_ai_logs",
    )
    sender_identifier = models.CharField(max_length=160, blank=True, default="")
    history_message_count = models.PositiveIntegerField(default=0)
    reply_text = models.TextField(blank=True, default="")
    model_used = models.CharField(max_length=128, blank=True, default="")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    error_message = models.TextField(blank=True, default="")
    replied_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["session", "-created_at"]),
            models.Index(fields=["status", "-created_at"]),
        ]

    def __str__(self):
        return f"AIReply({self.sender_identifier}, {self.status})"


class WhatsAppAssistantState(models.Model):
    """
    Tracks multi-turn workflow state per WhatsApp conversation so the AI assistant can
    guide meeting scheduling (date/time, timezone, Zoom vs Google Meet, confirmation)
    or await sender confirmation before escalating unanswered Vector DB queries to PRE.
    """

    class Mode(models.TextChoices):
        IDLE = "IDLE", "Idle"
        MEETING_SCHEDULING = "MEETING_SCHEDULING", "Meeting Scheduling"
        ESCALATION_CONFIRMATION = "ESCALATION_CONFIRMATION", "Escalation Confirmation"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    conversation = models.OneToOneField(
        "whatsapp.WhatsAppConversation",
        on_delete=models.CASCADE,
        related_name="assistant_state",
    )
    session = models.ForeignKey(
        "whatsapp.WhatsAppSession",
        on_delete=models.CASCADE,
        related_name="assistant_states",
    )
    mode = models.CharField(max_length=40, choices=Mode.choices, default=Mode.IDLE, db_index=True)
    pending_query = models.TextField(blank=True, default="")
    state_data = models.JSONField(default=dict, blank=True)
    last_incoming_message_id = models.CharField(max_length=128, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["session", "mode"]),
        ]

    def reset(self, save: bool = True):
        self.mode = self.Mode.IDLE
        self.pending_query = ""
        self.state_data = {}
        if save:
            self.save(update_fields=["mode", "pending_query", "state_data", "updated_at"])

    def __str__(self):
        return f"WhatsAppAssistantState({self.conversation_id}, mode={self.mode})"


class WhatsAppMeetingRequest(models.Model):
    """
    Persistent state machine and idempotency record for WhatsApp AI meeting scheduling.
    Strictly scoped to the authenticated session owner (user) and originating conversation.
    """

    class State(models.TextChoices):
        RECEIVED = "RECEIVED", "Received"
        COLLECTING_DETAILS = "COLLECTING_DETAILS", "Collecting Details"
        READY_FOR_AVAILABILITY_CHECK = "READY_FOR_AVAILABILITY_CHECK", "Ready For Availability Check"
        CHECKING_AVAILABILITY = "CHECKING_AVAILABILITY", "Checking Availability"
        AWAITING_ALTERNATIVE_SELECTION = "AWAITING_ALTERNATIVE_SELECTION", "Awaiting Alternative Selection"
        AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION", "Awaiting Confirmation"
        REVALIDATING_SLOT = "REVALIDATING_SLOT", "Revalidating Slot"
        CREATING_MEETING = "CREATING_MEETING", "Creating Meeting"
        SCHEDULED = "SCHEDULED", "Scheduled"
        FAILED = "FAILED", "Failed"
        CANCELLED = "CANCELLED", "Cancelled"
        EXPIRED = "EXPIRED", "Expired"
        REQUIRES_RECONNECTION = "REQUIRES_RECONNECTION", "Requires Reconnection"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="whatsapp_meeting_requests",
    )
    session = models.ForeignKey(
        "whatsapp.WhatsAppSession",
        on_delete=models.CASCADE,
        related_name="meeting_requests",
    )
    conversation = models.ForeignKey(
        "whatsapp.WhatsAppConversation",
        on_delete=models.CASCADE,
        related_name="meeting_requests",
    )
    source_message = models.ForeignKey(
        "whatsapp.WhatsAppMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="meeting_requests",
    )
    idempotency_key = models.CharField(max_length=160, unique=True)
    requested_date = models.DateField(null=True, blank=True)
    requested_time = models.TimeField(null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(default=30)
    timezone = models.CharField(max_length=64, default="UTC")
    purpose = models.CharField(max_length=255, blank=True, default="")
    platform = models.CharField(max_length=32, blank=True, default="")
    calendar_provider = models.CharField(max_length=32, blank=True, default="")
    attendee_email = models.EmailField(blank=True, default="")
    selected_slot_start = models.DateTimeField(null=True, blank=True)
    selected_slot_end = models.DateTimeField(null=True, blank=True)
    suggested_slots = models.JSONField(default=list, blank=True)
    state = models.CharField(max_length=40, choices=State.choices, default=State.RECEIVED, db_index=True)
    external_event_id = models.CharField(max_length=255, blank=True, default="")
    meeting_link = models.URLField(max_length=500, blank=True, default="")
    meeting = models.ForeignKey(
        "prospects.Meeting",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="whatsapp_requests",
    )
    failure_reason = models.TextField(blank=True, default="")
    notification_sent = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "selected_slot_start", "state"]),
            models.Index(fields=["conversation", "-created_at"]),
            models.Index(fields=["session", "-created_at"]),
        ]

    def __str__(self):
        return f"WhatsAppMeetingRequest({self.user_id}, {self.state}, {self.requested_date} {self.requested_time})"


