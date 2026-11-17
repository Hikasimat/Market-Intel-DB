from django.apps import AppConfig


class WhatsAppAiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "whatsapp_ai"
    verbose_name = "WhatsApp Gemini AI Auto-Reply"

    def ready(self):
        from whatsapp.signals import whatsapp_message_persisted
        from .gemini_service import handle_persisted_whatsapp_message
        from .realtime_listener import should_autostart_listener, start_realtime_listener

        whatsapp_message_persisted.connect(
            handle_persisted_whatsapp_message,
            dispatch_uid="whatsapp_ai.handle_persisted_whatsapp_message",
        )
        if should_autostart_listener():
            start_realtime_listener()
