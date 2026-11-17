import uuid
from django.conf import settings
from django.db import models


class EmailAIGenerationLog(models.Model):
    """
    Audit log of Gemini AI personalized email generation across Outreach Workspace,
    Inbox Compose, and Bulk Email Campaign.
    """

    class SourceContext(models.TextChoices):
        OUTREACH = "OUTREACH", "Outreach Workspace"
        INBOX = "INBOX", "Email Inbox Compose"
        CAMPAIGN = "CAMPAIGN", "Bulk Email Campaign"

    class Status(models.TextChoices):
        SUCCESS = "SUCCESS", "Success"
        FALLBACK = "FALLBACK", "Fallback Used"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="email_ai_generation_logs",
    )
    prospect = models.ForeignKey(
        "prospects.Prospect",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="email_ai_generation_logs",
    )
    source_context = models.CharField(
        max_length=20,
        choices=SourceContext.choices,
        default=SourceContext.OUTREACH,
    )
    user_prompt = models.TextField()
    tone = models.CharField(max_length=40, blank=True, default="professional")
    generated_subject = models.CharField(max_length=500, blank=True, default="")
    generated_body = models.TextField(blank=True, default="")
    provider = models.CharField(max_length=40, blank=True, default="gemini")
    model_used = models.CharField(max_length=128, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.SUCCESS,
    )
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
            models.Index(fields=["source_context", "-created_at"]),
        ]

    def __str__(self):
        return f"EmailAIGen({self.user_id}, {self.source_context}, {self.status})"
