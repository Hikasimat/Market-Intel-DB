"""
Run the standalone real-time WhatsApp Gemini AI listener loop.

Useful in deployments that run a dedicated worker process alongside Gunicorn/Daphne.
Note: Django's web server already auto-starts an in-process listener thread when
WHATSAPP_AI_REALTIME_POLLING is enabled (default).
"""

import time

from django.core.management.base import BaseCommand
from django.db import connection

from whatsapp_ai.realtime_listener import _get_poll_interval_seconds, run_realtime_sync_cycle


class Command(BaseCommand):
    help = "Poll connected WhatsApp sessions in real time and send Gemini AI auto-replies."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run a single real-time sync and auto-reply cycle, then exit.",
        )

    def handle(self, *args, **options):
        if options.get("once"):
            result = run_realtime_sync_cycle(force_chat_poll=True)
            self.stdout.write(self.style.SUCCESS(f"WhatsApp AI sync cycle: {result}"))
            return

        interval = _get_poll_interval_seconds()
        self.stdout.write(
            self.style.SUCCESS(f"WhatsApp AI real-time listener started (interval={interval:.1f}s). Press Ctrl+C to stop.")
        )
        try:
            while True:
                try:
                    run_realtime_sync_cycle()
                except Exception as exc:
                    self.stderr.write(f"WhatsApp AI sync error: {exc}")
                finally:
                    connection.close()
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write("WhatsApp AI listener stopped.")
