import logging
import signal
import sys
import time
from django.core.management.base import BaseCommand
from prospects.campaign_service import process_campaign_queue

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Processes persistent bulk email campaign queues with strict interval pacing.'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.running = True

    def _handle_exit(self, signum, frame):
        self.stdout.write(self.style.WARNING(f"\nReceived signal {signum}. Shutting down campaign worker gracefully..."))
        self.running = False

    def add_arguments(self, parser):
        parser.add_argument(
            '--run-once',
            action='store_true',
            help='Run a single processing cycle and exit immediately.',
        )
        parser.add_argument(
            '--poll-interval',
            type=int,
            default=5,
            help='Interval in seconds between database polling cycles (default: 5).',
        )
        parser.add_argument(
            '--max-jobs',
            type=int,
            default=None,
            help='Maximum number of recipients to process before stopping.',
        )

    def handle(self, *args, **options):
        run_once = options['run_once']
        poll_interval = options['poll_interval']
        max_jobs = options['max_jobs']

        # Register signal handlers for graceful termination
        try:
            signal.signal(signal.SIGINT, self._handle_exit)
            signal.signal(signal.SIGTERM, self._handle_exit)
        except Exception:
            pass

        self.stdout.write(self.style.SUCCESS("Starting MarketIntel Campaign Processing Worker..."))
        self.stdout.write(f"Settings: run_once={run_once}, poll_interval={poll_interval}s, max_jobs={max_jobs}")

        total_processed = 0

        while self.running:
            try:
                limit = (max_jobs - total_processed) if max_jobs is not None else None
                count = process_campaign_queue(max_jobs=limit)
                if count > 0:
                    total_processed += count
                    self.stdout.write(self.style.SUCCESS(f"Dispatched {count} campaign recipient(s). Total processed: {total_processed}"))

                if max_jobs is not None and total_processed >= max_jobs:
                    self.stdout.write(self.style.SUCCESS(f"Reached max jobs limit ({max_jobs}). Exiting worker."))
                    break

            except Exception as e:
                logger.exception("Error in campaign processing loop: %s", e)
                self.stdout.write(self.style.ERROR(f"Error in campaign processing loop: {e}"))

            if run_once:
                break

            # Sleep in 1-second chunks to respond quickly to termination signals
            for _ in range(poll_interval):
                if not self.running:
                    break
                time.sleep(1)

        self.stdout.write(self.style.SUCCESS(f"Campaign worker finished. Processed {total_processed} total recipient(s)."))
