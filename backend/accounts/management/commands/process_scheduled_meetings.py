"""
Management command to continuously or once poll all users' scheduled calendar
events & CRM meetings, resolve meeting links (calendar or email), and dispatch due
meetings to the Custom Browser Engine webhook workflow.

Usage:
    py manage.py process_scheduled_meetings --once
    py manage.py process_scheduled_meetings --loop --interval 30
"""

import time

from django.core.management.base import BaseCommand

from accounts.meeting_automation_service import process_due_scheduled_meetings


class Command(BaseCommand):
    help = "Discover scheduled meetings across all users and dispatch due ones to CBE webhook workflow."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Run one discovery/dispatch cycle and exit (default behavior if --loop is not specified).",
        )
        parser.add_argument(
            "--loop",
            action="store_true",
            help="Continuously poll on an interval until interrupted.",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=30,
            help="Polling interval in seconds when --loop is used (default: 30).",
        )

    def handle(self, *args, **options):
        run_loop = bool(options.get("loop")) and not bool(options.get("once"))
        interval = max(5, int(options.get("interval") or 30))

        while True:
            result = process_due_scheduled_meetings()
            self.stdout.write(
                f"CBE scheduler tick: discovered={result['discovered']} "
                f"created={result['created_jobs']} dispatched={result['dispatched']} "
                f"skipped={result['skipped']} failed={result['failed']}"
            )
            if not run_loop:
                break
            time.sleep(interval)
