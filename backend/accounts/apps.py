from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = 'accounts'

    def ready(self):
        from .meeting_automation_service import (
            should_autostart_meeting_scheduler,
            start_meeting_scheduler,
        )
        if should_autostart_meeting_scheduler():
            start_meeting_scheduler()

