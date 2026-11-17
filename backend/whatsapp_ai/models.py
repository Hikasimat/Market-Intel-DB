import uuid
from django.db import models
from django.utils import timezone


class WhatsAppAIAutoReplyConfig(models.Model):
    """
    Per-session Gemini AI auto-reply settings.
    Auto-created with enabled=True when a connected session receives a message
    unless disabled by an admin.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField(
        "whatsapp.WhatsAppSession",
        on_delete=models.CASCADE,
        related_name="ai_auto_reply_config",
    )
    enabled = models.BooleanField(default=True)
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
