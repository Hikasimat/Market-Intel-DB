"""Upload flow: authorise (done by caller) -> validate -> checksum -> dedupe/version -> store -> record -> enqueue."""
from __future__ import annotations

import logging

from django.db import transaction

from .. import constants as C
from .. import tasks
from ..exceptions import AuthorizationError, DocumentValidationError, DuplicateDocumentError
from ..models import KnowledgeBase, KnowledgeDocument
from . import knowledge_base_service as kbs, storage_service
from .document_validation_service import validate_upload

logger = logging.getLogger("rag.upload")


def upload_document(kb: KnowledgeBase, user, uploaded_file) -> KnowledgeDocument:
    if not kbs.can_ingest_documents(user):
        raise AuthorizationError("Only a Super Admin has permission to ingest documents.")
    from .. import conf

    limit = conf.max_document_bytes()
    declared = getattr(uploaded_file, "size", None)
    if declared is not None and declared > limit:
        raise DocumentValidationError(f"The file exceeds the {limit // (1024 * 1024)} MB limit.", code="file_too_large")
    data = uploaded_file.read(limit + 1)
    validated = validate_upload(getattr(uploaded_file, "name", ""), data, getattr(uploaded_file, "content_type", ""))

    with transaction.atomic():
        # Serialise concurrent uploads into the same KB (version numbering / duplicate check).
        KnowledgeBase.objects.select_for_update().get(pk=kb.pk)

        live = kb.documents.exclude(status=C.STATUS_DELETING)
        dup = live.filter(checksum_sha256=validated.checksum).first()
        if dup is not None:
            if dup.status == C.STATUS_FAILED:
                raise DuplicateDocumentError(
                    "An identical document already exists but failed processing. Use 'Retry' on it instead."
                )
            raise DuplicateDocumentError()

        previous = live.filter(original_filename=validated.filename).order_by("-version").first()
        version = (previous.version + 1) if previous else 1
        doc = KnowledgeDocument(
            knowledge_base=kb,
            original_filename=validated.filename,
            file_type=validated.file_type,
            file_size=validated.size,
            mime_type=validated.mime_type,
            checksum_sha256=validated.checksum,
            status=C.STATUS_UPLOADED,
            version=version,
            replaces=previous if (previous and previous.is_active) else None,
            created_by=user,
        )
        doc.storage_key = storage_service.build_storage_key(kb.tenant_key, kb.pk, doc.pk, validated.filename)
        storage_service.save(doc.storage_key, validated.data, validated.mime_type)
        try:
            doc.save()
        except Exception:
            storage_service.delete(doc.storage_key)
            raise
        transaction.on_commit(lambda: _safe_enqueue(doc))
    logger.info("Document %s uploaded to KB %s (type=%s, size=%d, v%d)", doc.pk, kb.pk, doc.file_type, doc.file_size, version)
    return doc


def _safe_enqueue(doc: KnowledgeDocument) -> None:
    try:
        tasks.enqueue_ingestion(doc)
    except Exception as exc:
        logger.error("Could not enqueue document %s: %s", doc.pk, type(exc).__name__)
        KnowledgeDocument.objects.filter(pk=doc.pk).update(
            status=C.STATUS_FAILED, processing_error="Could not queue the document for processing. Use Retry."
        )


def retry_document(doc: KnowledgeDocument, *, user=None) -> KnowledgeDocument:
    """Safe retry: only Super Admin may retry FAILED (or never-queued UPLOADED) documents."""
    if user is not None and not kbs.can_ingest_documents(user):
        raise AuthorizationError("Only a Super Admin has permission to retry document ingestion.")
    with transaction.atomic():
        doc = KnowledgeDocument.objects.select_for_update().get(pk=doc.pk)
        if doc.status not in (C.STATUS_FAILED, C.STATUS_UPLOADED):
            raise DocumentValidationError("Only failed documents can be retried.", code="not_retryable")
        doc.status = C.STATUS_UPLOADED
        doc.processing_error = ""
        doc.save(update_fields=["status", "processing_error", "updated_at"])
        transaction.on_commit(lambda: _safe_enqueue(doc))
    return doc
