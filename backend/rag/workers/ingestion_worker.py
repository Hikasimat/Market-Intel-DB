"""
Document ingestion (idempotent + retry-safe) and queue consumers.

Invariants
* A document becomes READY only inside the same DB transaction that stores ALL of its
  chunks + embeddings and after the stored count was verified.
* Chunks are written via delete-then-insert in one transaction, so retries never duplicate.
* A new version replaces the old one only after it is fully READY (old chunks are then retired).
"""
from __future__ import annotations

import json
import logging
import signal
import time
from dataclasses import dataclass
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .. import conf
from .. import constants as C
from ..exceptions import (
    DocumentParseError,
    DocumentValidationError,
    EmbeddingError,
    OCRRequiredError,
    StorageError,
)
from ..models import IngestionJob, KnowledgeDocument
from ..services import (
    chunking_service,
    document_parser_service,
    document_validation_service,
    embedding_service,
    storage_service,
    vector_store_service,
)

logger = logging.getLogger("rag.ingestion")


@dataclass
class IngestionResult:
    status: str  # ready | failed | skipped
    retryable: bool = False
    message: str = ""


def _set_status(doc_id, status, **extra):
    KnowledgeDocument.objects.filter(pk=doc_id).update(status=status, updated_at=timezone.now(), **extra)


def _claim(document_id) -> tuple[KnowledgeDocument | None, str]:
    stale = timezone.now() - timedelta(seconds=conf.stale_processing_seconds())
    with transaction.atomic():
        doc = KnowledgeDocument.objects.select_for_update().filter(pk=document_id).first()
        if doc is None:
            return None, "missing"
        if doc.status == C.STATUS_DELETING:
            return None, "deleting"
        if doc.status == C.STATUS_READY:
            return None, "already_ready"
        if doc.status in C.IN_FLIGHT_STATUSES and doc.processing_started_at and doc.processing_started_at > stale:
            return None, "in_progress"  # another worker owns it (duplicate delivery)
        doc.status = C.STATUS_VALIDATING
        doc.processing_attempts += 1
        doc.processing_started_at = timezone.now()
        doc.processing_error = ""
        doc.save(update_fields=["status", "processing_attempts", "processing_started_at", "processing_error", "updated_at"])
        return doc, "claimed"


def process_document(document_id) -> IngestionResult:
    doc, state = _claim(document_id)
    if doc is None:
        logger.info("Ingestion skipped for %s (%s)", document_id, state)
        return IngestionResult("skipped", message=state)
    doc_id = doc.pk
    try:
        data = storage_service.read(doc.storage_key)
        if document_validation_service.sha256_hex(data) != doc.checksum_sha256:
            raise DocumentValidationError("Stored file checksum mismatch.", code="checksum_mismatch")
        document_validation_service._check_signature(doc.file_type, data)

        _set_status(doc_id, C.STATUS_PROCESSING)
        blocks, total_pages = document_parser_service.parse_document(doc.file_type, data, storage_key=doc.storage_key)

        _set_status(doc_id, C.STATUS_CHUNKING, total_pages=total_pages)
        drafts = chunking_service.chunk_blocks(blocks)
        if not drafts:
            raise DocumentParseError("No indexable text was found in the document.")

        _set_status(doc_id, C.STATUS_EMBEDDING)
        texts = [
            chunking_service.embedding_input_for_chunk(
                doc.original_filename, d.text, sheet=d.sheet, heading=d.heading, page=d.page
            )
            for d in drafts
        ]
        model, dim = embedding_service.validate_configuration()
        embeddings = embedding_service.embed_texts(texts)

        _finalize(doc, drafts, embeddings, model, dim, total_pages)
        logger.info("Document %s READY (%d chunks)", doc_id, len(drafts))
        return IngestionResult("ready")
    except OCRRequiredError as exc:
        return _fail(doc_id, f"PDF_NEEDS_OCR: {exc}", retryable=False)
    except (DocumentValidationError, DocumentParseError) as exc:
        return _fail(doc_id, str(exc), retryable=False)
    except (EmbeddingError, StorageError) as exc:
        return _fail(doc_id, f"{type(exc).__name__}: {exc}", retryable=True)
    except Exception as exc:  # unexpected - keep worker alive, preserve useful info
        logger.exception("Unexpected ingestion error for %s", doc_id)
        return _fail(doc_id, f"Unexpected error ({type(exc).__name__}).", retryable=True)


def _finalize(doc, drafts, embeddings, model, dim, total_pages) -> None:
    to_cleanup: list[str] = []
    with transaction.atomic():
        locked = KnowledgeDocument.objects.select_for_update().get(pk=doc.pk)
        if locked.status == C.STATUS_DELETING:
            raise DocumentValidationError("Document was deleted during processing.", code="deleted")
        stored = vector_store_service.replace_document_chunks(locked, drafts, embeddings, model, dim)
        if stored != len(drafts):
            raise DocumentParseError("Chunk verification failed.")
        # Retire every other version of the same file: new version goes live only now.
        for old in KnowledgeDocument.objects.select_for_update().filter(
            knowledge_base_id=locked.knowledge_base_id, original_filename=locked.original_filename
        ).exclude(pk=locked.pk).exclude(status=C.STATUS_DELETING):
            if old.version < locked.version and old.status in (C.STATUS_READY, C.STATUS_FAILED):
                vector_store_service.delete_document_chunks(old)
                if old.storage_key:
                    to_cleanup.append(old.storage_key)
                old.delete()
        locked.total_chunks = stored
        locked.total_pages = total_pages
        locked.is_active = True
        locked.ready_at = timezone.now()
        locked.processing_error = ""
        locked.status = C.STATUS_READY  # LAST: only after everything above succeeded
        locked.save()
    for key in to_cleanup:
        try:
            storage_service.delete(key)
        except StorageError:
            logger.warning("Could not remove retired storage object (will remain orphaned)")


def _fail(doc_id, message: str, *, retryable: bool) -> IngestionResult:
    msg = message[:1000]
    KnowledgeDocument.objects.filter(pk=doc_id).exclude(status=C.STATUS_DELETING).update(
        status=C.STATUS_FAILED, processing_error=msg, is_active=False, updated_at=timezone.now()
    )
    logger.warning("Document %s FAILED (retryable=%s): %s", doc_id, retryable, msg[:200])
    return IngestionResult("failed", retryable=retryable, message=msg)


# ── Local (DB) queue consumer ────────────────────────────────────────────────
class GracefulStop:
    def __init__(self):
        self.stop = False

    def install(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self._handler)
            except (ValueError, OSError):  # not main thread / unsupported
                pass

    def _handler(self, signum, frame):
        logger.info("Shutdown signal received; finishing current job...")
        self.stop = True


def _claim_local_job() -> IngestionJob | None:
    now = timezone.now()
    stale = now - timedelta(seconds=conf.stale_processing_seconds())
    with transaction.atomic():
        qs = IngestionJob.objects.select_for_update(skip_locked=True).filter(
            Q(status=IngestionJob.Status.QUEUED, available_at__lte=now)
            | Q(status=IngestionJob.Status.RUNNING, locked_at__lt=stale)
        )
        job = qs.order_by("created_at").first()
        if job is None:
            return None
        job.status = IngestionJob.Status.RUNNING
        job.locked_at = now
        job.attempts += 1
        job.save(update_fields=["status", "locked_at", "attempts", "updated_at"])
        return job


def run_one_local_job() -> bool:
    job = _claim_local_job()
    if job is None:
        return False
    result = process_document(job.document_id)
    if result.status == "failed" and result.retryable and job.attempts < conf.max_ingestion_attempts():
        job.status = IngestionJob.Status.QUEUED
        job.available_at = timezone.now() + timedelta(seconds=30 * (2 ** (job.attempts - 1)))
    elif result.status == "failed":
        job.status = IngestionJob.Status.FAILED
    else:
        job.status = IngestionJob.Status.DONE
    job.last_error = result.message[:1000]
    job.save(update_fields=["status", "available_at", "last_error", "updated_at"])
    return True


def run_local_worker(poll_interval: float = 3.0, once: bool = False) -> int:
    stopper = GracefulStop()
    stopper.install()
    processed = 0
    while not stopper.stop:
        if run_one_local_job():
            processed += 1
            continue
        if once:
            break
        time.sleep(poll_interval)
    return processed


# ── SQS consumer (production) ────────────────────────────────────────────────
def run_sqs_worker(once: bool = False) -> int:
    from ..tasks import _sqs_client

    url = conf.ingestion_queue_url()
    if not url:
        raise RuntimeError("RAG_INGESTION_QUEUE_URL is not configured.")
    client = _sqs_client()
    stopper = GracefulStop()
    stopper.install()
    processed = 0
    while not stopper.stop:
        resp = client.receive_message(
            QueueUrl=url, MaxNumberOfMessages=1, WaitTimeSeconds=20, VisibilityTimeout=900
        )
        messages = resp.get("Messages", [])
        if not messages:
            if once:
                break
            continue
        msg = messages[0]
        try:
            document_id = json.loads(msg["Body"])["document_id"]
        except Exception:
            logger.error("Discarding malformed ingestion message")
            client.delete_message(QueueUrl=url, ReceiptHandle=msg["ReceiptHandle"])
            continue
        result = process_document(document_id)
        if result.status == "failed" and result.retryable:
            # Leave the message: it reappears after the visibility timeout and, after the queue's
            # maxReceiveCount, SQS moves it to the dead-letter queue (redrive policy).
            logger.warning("Ingestion for %s will be retried by SQS", document_id)
        else:
            client.delete_message(QueueUrl=url, ReceiptHandle=msg["ReceiptHandle"])
        processed += 1
        if once:
            break
    return processed
