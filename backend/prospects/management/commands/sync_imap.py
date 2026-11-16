import sys
from django.core.management.base import BaseCommand
from prospects.models import OutreachEmail, CommunicationActivity, ProspectContact
from django.utils import timezone
import json

class Command(BaseCommand):
    help = 'Synchronize Gmail via Google OAuth to detect email responses, persist normalized threads, and update Outreach threads.'

    def add_arguments(self, parser):
        parser.add_argument('--user-id', type=int, default=None, help='Sync only a specific user ID')
        parser.add_argument('--limit', type=int, default=30, help='Maximum messages to fetch per mailbox')

    def handle(self, *args, **options):
        user_id = options.get('user_id')
        limit = options.get('limit') or 30
        try:
            from accounts.models import GoogleMailCredentials
            google_creds = GoogleMailCredentials.objects.filter(is_active=True)
            if user_id:
                google_creds = google_creds.filter(user_id=user_id)
            for cred in google_creds:
                try:
                    self.sync_google_account(cred, limit=limit)
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Failed to sync Gmail {cred.email}: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Gmail sync error: {e}"))

    def sync_google_account(self, cred, limit=30):
        from prospects.email_thread_service import sync_mailbox_messages
        self.stdout.write(f"Syncing Gmail {cred.email}..."); sys.stdout.flush()
        result = sync_mailbox_messages(cred, limit=limit)
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully synced Gmail {cred.email} "
                f"(synced={result.get('synced', 0)}, skipped={result.get('skipped', 0)})"
            )
        )
