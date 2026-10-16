"""
Management command: check_mail_configuration

Diagnoses database and Google Mail (Gmail OAuth) connectivity without sending email
or exposing credentials.

Usage:
    python manage.py check_mail_configuration
"""

from django.core.management.base import BaseCommand
from django.db import connection as db_connection
from django.utils import timezone


class Command(BaseCommand):
    help = "Diagnose database and Google Mail OAuth connectivity. Never prints secrets."

    def _result(self, label, passed, detail=""):
        icon = "PASS" if passed else "FAIL"
        line = f"  {label} = {icon}"
        if detail and not passed:
            line += f"  [{detail}]"
        self.stdout.write(line)
        return passed

    def handle(self, *args, **options):
        # ── DATABASE ────────────────────────────────────────────────────────────
        self.stdout.write("\nDATABASE")
        try:
            with db_connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            self._result("connection", True)
        except Exception as exc:
            self._result("connection", False, type(exc).__name__)

        # ── GOOGLE MAIL CREDENTIALS ─────────────────────────────────────────────
        try:
            from accounts.models import GoogleMailCredentials
        except ImportError as exc:
            self.stdout.write(f"\nFATAL: could not import GoogleMailCredentials: {exc}")
            return

        creds = GoogleMailCredentials.objects.filter(is_active=True)
        if not creds.exists():
            self.stdout.write("\nNo active GoogleMailCredentials found in database.")
            return

        for cred in creds:
            self.stdout.write(
                f"\n{'-' * 60}\n"
                f"GoogleMailCredentials user={cred.user.username} email={cred.email}"
            )
            has_token = bool(cred.access_token_encrypted)
            has_refresh = bool(cred.refresh_token_encrypted)
            is_expired = cred.token_expiry and cred.token_expiry < timezone.now()

            self._result("has_access_token", has_token)
            self._result("has_refresh_token", has_refresh)
            self._result("token_valid_or_refreshable", has_refresh or not is_expired)
