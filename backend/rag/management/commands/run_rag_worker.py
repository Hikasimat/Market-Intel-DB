"""Dedicated ingestion worker process (never started from AppConfig.ready())."""
from django.core.management.base import BaseCommand, CommandError

from rag import conf
from rag.workers import ingestion_worker


class Command(BaseCommand):
    help = "Run the RAG document ingestion worker (local DB queue or Amazon SQS, per RAG_QUEUE_BACKEND)."

    def add_arguments(self, parser):
        parser.add_argument("--poll-interval", type=float, default=3.0)
        parser.add_argument("--once", action="store_true", help="Process available work then exit.")

    def handle(self, *args, **opts):
        backend = conf.queue_backend()
        self.stdout.write(f"RAG ingestion worker started (queue backend: {backend}). Ctrl+C / SIGTERM to stop gracefully.")
        if backend == "sqs":
            n = ingestion_worker.run_sqs_worker(once=opts["once"])
        elif backend == "local":
            n = ingestion_worker.run_local_worker(poll_interval=opts["poll_interval"], once=opts["once"])
        else:
            raise CommandError("RAG_QUEUE_BACKEND=inline processes documents inside the web request; no worker is needed.")
        self.stdout.write(f"Worker stopped after processing {n} job(s).")
