from django.apps import AppConfig


class RagConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "rag"
    verbose_name = "RAG Knowledge Base"

    # NOTE: no workers/threads are started here. Ingestion runs in dedicated
    # processes (`manage.py run_rag_worker`).
