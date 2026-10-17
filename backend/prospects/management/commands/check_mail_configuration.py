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

        # ── EMAIL OPEN TRACKING & DELIVERABILITY CONFIGURATION ─────────────────
        self.stdout.write(f"\n{'-' * 60}")
        self.stdout.write("EMAIL TRACKING & DELIVERABILITY CONFIGURATION")
        from django.conf import settings
        from prospects.tracking_utils import (
            global_open_tracking_enabled,
            validate_tracking_configuration,
        )

        tracking_enabled = global_open_tracking_enabled()
        self._result("open_tracking_globally_enabled", tracking_enabled)

        base_url = getattr(settings, 'EMAIL_TRACKING_BASE_URL', '')
        self.stdout.write(f"  effective_tracking_base_url = {base_url or '(not configured)'}")

        valid_syntax, syntax_err = validate_tracking_configuration(base_url)
        self._result("tracking_url_syntax_valid", valid_syntax, syntax_err)

        # Operational check (safe, operator-initiated only)
        if base_url and valid_syntax:
            import urllib.parse
            import socket
            import urllib.request
            import ssl
            parsed = urllib.parse.urlsplit(base_url)
            host = parsed.hostname
            # 1. DNS check
            dns_ok = False
            try:
                socket.gethostbyname(host)
                dns_ok = True
                self._result("tracking_host_dns_resolved", True)
            except Exception as exc:
                self._result("tracking_host_dns_resolved", False, f"DNS error: {exc}")

            # 2. TLS check if HTTPS
            if dns_ok and parsed.scheme == 'https':
                tls_ok = False
                try:
                    ctx = ssl.create_default_context()
                    with socket.create_connection((host, parsed.port or 443), timeout=5) as sock:
                        with ctx.wrap_socket(sock, server_hostname=host) as ssock:
                            tls_ok = True
                    self._result("tracking_host_tls_valid", True)
                except Exception as exc:
                    self._result("tracking_host_tls_valid", False, f"TLS error: {exc}")

            # 3. HTTP GET check on tracking pixel endpoint with dummy UUID
            if dns_ok:
                try:
                    dummy_pixel_url = f"{base_url.rstrip('/')}/api/email-tracking/00000000-0000-0000-0000-000000000000/"
                    req = urllib.request.Request(
                        dummy_pixel_url,
                        headers={'User-Agent': 'MarketIntel-Diagnostic/1.0'}
                    )
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        content_type = resp.headers.get('Content-Type', '')
                        status_code = resp.status
                        gif_ok = (status_code == 200 and 'image/gif' in content_type)
                        self._result("public_tracking_pixel_accessible", gif_ok, f"Status: {status_code}, Content-Type: {content_type}")
                except Exception as exc:
                    self._result("public_tracking_pixel_accessible", False, f"Request error: {exc}")

