"""Delete RAG query logs older than the retention window (privacy)."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from rag import conf
from rag.models import RAGQueryLog


class Command(BaseCommand):
    help = "Purge RAGQueryLog rows older than RAG_QUERY_LOG_RETENTION_DAYS (or --days)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=None)

    def handle(self, *args, **opts):
        days = opts["days"] if opts["days"] is not None else conf.query_log_retention_days()
        if days <= 0:
            self.stdout.write("Retention disabled (days <= 0); nothing purged.")
            return
        deleted, _ = RAGQueryLog.objects.filter(created_at__lt=timezone.now() - timedelta(days=days)).delete()
        self.stdout.write(f"Purged {deleted} query log row(s) older than {days} days.")
