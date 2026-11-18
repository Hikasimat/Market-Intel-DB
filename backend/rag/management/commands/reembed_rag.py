"""Re-embed documents whose vectors were produced by a different model/dimension than the current config."""
from django.core.management.base import BaseCommand

from rag.models import KnowledgeBase
from rag.workers import embedding_worker


class Command(BaseCommand):
    help = "Controlled re-embedding after RAG_EMBEDDING model/dimension changes (documents are swapped atomically)."

    def add_arguments(self, parser):
        parser.add_argument("--knowledge-base", help="Limit to one knowledge base UUID.")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **opts):
        kb = KnowledgeBase.objects.get(pk=opts["knowledge_base"]) if opts.get("knowledge_base") else None
        if opts["dry_run"]:
            docs = list(embedding_worker.stale_documents(kb))
            self.stdout.write(f"{len(docs)} document(s) need re-embedding.")
            return
        self.stdout.write(str(embedding_worker.reembed_knowledge_base(kb)))
