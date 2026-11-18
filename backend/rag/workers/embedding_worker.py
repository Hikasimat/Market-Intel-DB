"""
Controlled re-embedding after an embedding-model change.

Retrieval only reads chunks whose (embedding_model, embedding_dimension) equal the
CURRENT configuration, so vectors from different models are never mixed. While a
document is being re-embedded its old vectors are simply not retrievable; each
document is swapped atomically (all chunks or none).
"""
from __future__ import annotations

import logging

from django.db import transaction

from .. import constants as C
from ..models import KnowledgeBase, KnowledgeDocument, KnowledgeDocumentChunk
from ..services import chunking_service, embedding_service

logger = logging.getLogger("rag.reembed")


def stale_documents(kb: KnowledgeBase | None = None):
    model, dim = embedding_service.current_model()
    qs = KnowledgeDocument.objects.filter(status=C.STATUS_READY)
    if kb is not None:
        qs = qs.filter(knowledge_base=kb)
    stale_chunks = KnowledgeDocumentChunk.objects.exclude(embedding_model=model, embedding_dimension=dim)
    return qs.filter(pk__in=stale_chunks.values("document_id"))


def reembed_document(doc: KnowledgeDocument) -> int:
    model, dim = embedding_service.validate_configuration()
    chunks = list(doc.chunks.order_by("chunk_index"))
    if not chunks:
        return 0
    texts = [
        chunking_service.embedding_input_for_chunk(
            doc.original_filename, c.text, sheet=c.sheet_name, heading=c.section_heading, page=c.page_number
        )
        for c in chunks
    ]
    vectors = embedding_service.embed_texts(texts)  # raises -> nothing written for this document
    with transaction.atomic():
        for c, v in zip(chunks, vectors):
            c.embedding, c.embedding_model, c.embedding_dimension = v, model, dim
        KnowledgeDocumentChunk.objects.bulk_update(chunks, ["embedding", "embedding_model", "embedding_dimension"], batch_size=100)
    return len(chunks)


def reembed_knowledge_base(kb: KnowledgeBase | None = None) -> dict:
    done = failed = 0
    seen = set()
    for doc in stale_documents(kb):
        if doc.pk in seen:
            continue
        seen.add(doc.pk)
        try:
            reembed_document(doc)
            done += 1
        except Exception as exc:
            failed += 1
            logger.error("Re-embedding failed for %s (%s)", doc.pk, type(exc).__name__)
    return {"documents_reembedded": done, "documents_failed": failed}
