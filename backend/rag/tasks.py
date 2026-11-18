"""Queue abstraction: inline (tests) | local DB queue (dev) | Amazon SQS (production)."""
from __future__ import annotations

import json
import logging
import sys
import threading

from django.db import connection

from . import conf
from .exceptions import RAGError
from .models import IngestionJob, KnowledgeDocument

logger = logging.getLogger("rag.tasks")


def _sqs_client():
    import boto3

    profile = conf.aws_profile()
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    return session.client("sqs", region_name=conf.aws_region())


def _spawn_local_background_drain():
    """
    In local development (`RAG_QUEUE_BACKEND=local`), also drain the queued job on a
    background daemon thread so uploads/retries complete immediately even if the
    developer hasn't started a separate `manage.py run_rag_worker` terminal.
    Because `run_one_local_job` uses `select_for_update(skip_locked=True)`, it is
    100% safe when `run_rag_worker` is also running.
    """
    if "test" in sys.argv:
        return

    def _runner():
        from .workers.ingestion_worker import run_one_local_job

        try:
            while run_one_local_job():
                pass
        except Exception:
            logger.exception("Local background ingestion thread error")
        finally:
            try:
                connection.close()
            except Exception:
                pass

    t = threading.Thread(target=_runner, name="rag-local-ingestion", daemon=True)
    t.start()


def enqueue_ingestion(document: KnowledgeDocument) -> None:
    """Never blocks on parsing/embedding. Queue failures leave the document UPLOADED (retry endpoint can requeue)."""
    backend = conf.queue_backend()
    if backend == "inline":
        from .workers.ingestion_worker import process_document

        process_document(document.pk)
    elif backend == "sqs":
        url = conf.ingestion_queue_url()
        if not url:
            raise RAGError("RAG_INGESTION_QUEUE_URL is not configured.")
        _sqs_client().send_message(QueueUrl=url, MessageBody=json.dumps({"document_id": str(document.pk)}))
    else:
        IngestionJob.objects.create(document=document)
        _spawn_local_background_drain()
    logger.info("Queued ingestion for document %s via %s", document.pk, backend)
