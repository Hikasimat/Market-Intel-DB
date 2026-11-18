from django.apps import AppConfig


class ProspectsConfig(AppConfig):
    name = 'prospects'

    def ready(self):
        from .outreach_ai_listener import (
            register_outreach_ai_signals,
            should_autostart_outreach_listener,
            start_outreach_ai_listener,
        )

        register_outreach_ai_signals()
        if should_autostart_outreach_listener():
            start_outreach_ai_listener()

