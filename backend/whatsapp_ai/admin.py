from django.contrib import admin
from .models import WhatsAppAIAutoReplyConfig, WhatsAppAIReplyLog, WhatsAppMeetingRequest


@admin.register(WhatsAppAIAutoReplyConfig)
class WhatsAppAIAutoReplyConfigAdmin(admin.ModelAdmin):
    list_display = ("session", "enabled", "reply_to_groups", "model_name", "max_history_messages", "updated_at")
    list_filter = ("enabled", "reply_to_groups")
    search_fields = ("session__session_name", "session__phone_number")


@admin.register(WhatsAppAIReplyLog)
class WhatsAppAIReplyLogAdmin(admin.ModelAdmin):
    list_display = ("sender_identifier", "session", "status", "model_used", "history_message_count", "replied_at", "created_at")
    list_filter = ("status", "model_used")
    search_fields = ("sender_identifier", "reply_text", "session__session_name")
    readonly_fields = ("incoming_message", "reply_message", "created_at", "updated_at")


@admin.register(WhatsAppMeetingRequest)
class WhatsAppMeetingRequestAdmin(admin.ModelAdmin):
    list_display = ("user", "session", "state", "platform", "requested_date", "requested_time", "duration_minutes", "updated_at")
    list_filter = ("state", "platform", "calendar_provider")
    search_fields = ("purpose", "attendee_email", "meeting_link", "idempotency_key")
