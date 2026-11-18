"""
pgvector storage + tenant-filtered similarity search on the EXISTING PostgreSQL connection.

Isolation guarantee: every query is filtered IN SQL by knowledge base, tenant
(company / owner), active KB, READY + active document and the current embedding
model/dimension. Nothing is fetched globally and filtered afterwards.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

from django.db import connection, transaction
from django.db.models import F, Q

from .. import conf
from ..constants import STATUS_READY
from ..exceptions import RAGError
from ..models import KnowledgeBase, KnowledgeDocument, KnowledgeDocumentChunk

logger = logging.getLogger("rag.vector_store")

_ALLOWED_META_FILTERS = {"page_number", "sheet_name", "section_heading"}


@dataclass
class RetrievedChunk:
    chunk_id: str
    document_id: str
    document_name: str
    chunk_index: int
    text: str
    page_number: Optional[int]
    sheet_name: str
    section_heading: str
    similarity: float  # cosine similarity in [-1, 1]
    score: float = 0.0  # ranking score (may include hybrid/rerank adjustments)
    metadata: dict = field(default_factory=dict)
    content_checksum: str = ""


def tenant_q(kb: KnowledgeBase) -> Q:
    if kb.company_id:
        return Q(knowledge_base__company_id=kb.company_id)
    return Q(knowledge_base__owner_id=kb.owner_id, knowledge_base__company__isnull=True)


def _normalize_kb_list(kb_or_kbs) -> list[KnowledgeBase]:
    if isinstance(kb_or_kbs, (list, tuple, set)):
        return [k for k in kb_or_kbs if k is not None]
    return [kb_or_kbs] if kb_or_kbs is not None else []


def base_queryset(kb_or_kbs):
    """The ONLY entry point for reading retrievable chunks (supports single KB or dynamic list of KBs)."""
    from . import embedding_service

    kbs = _normalize_kb_list(kb_or_kbs)
    if not kbs:
        return KnowledgeDocumentChunk.objects.none()

    model, dim = embedding_service.current_model()
    kb_ids = [k.id for k in kbs]
    combined_tenant_q = Q()
    for k in kbs:
        combined_tenant_q |= (tenant_q(k) & Q(knowledge_base_id=k.id) & Q(document__knowledge_base_id=k.id))

    return KnowledgeDocumentChunk.objects.filter(
        combined_tenant_q,
        knowledge_base_id__in=kb_ids,
        knowledge_base__is_active=True,
        document__status=STATUS_READY,
        document__is_active=True,
        embedding_model=model,
        embedding_dimension=dim,
    )


# ── writes ───────────────────────────────────────────────────────────────────
def replace_document_chunks(document: KnowledgeDocument, drafts, embeddings, model: str, dim: int) -> int:
    """Idempotent: removes any existing chunks of the document then inserts the new set atomically."""
    if len(drafts) != len(embeddings):
        raise RAGError("Chunk/embedding count mismatch.")
    rows = [
        KnowledgeDocumentChunk(
            document=document,
            knowledge_base_id=document.knowledge_base_id,
            chunk_index=i,
            text=d.text,
            embedding=emb,
            embedding_model=model,
            embedding_dimension=dim,
            page_number=d.page,
            sheet_name=d.sheet or "",
            section_heading=(d.heading or "")[:500],
            metadata=d.metadata or {},
            token_count=d.token_count,
            content_checksum=d.checksum,
        )
        for i, (d, emb) in enumerate(zip(drafts, embeddings))
    ]
    with transaction.atomic():
        KnowledgeDocumentChunk.objects.filter(document=document).delete()
        KnowledgeDocumentChunk.objects.bulk_create(rows, batch_size=200)
        stored = KnowledgeDocumentChunk.objects.filter(
            document=document, embedding_model=model, embedding_dimension=dim
        ).count()
        if stored != len(rows):
            raise RAGError(f"Chunk verification failed: expected {len(rows)}, stored {stored}.")
    return stored


def delete_document_chunks(document: KnowledgeDocument) -> int:
    deleted, _ = KnowledgeDocumentChunk.objects.filter(document=document).delete()
    return deleted


# ── reads ────────────────────────────────────────────────────────────────────
def _apply_filters(qs, document_ids, metadata_filters):
    if document_ids:
        qs = qs.filter(document_id__in=list(document_ids))
    for key, value in (metadata_filters or {}).items():
        if key not in _ALLOWED_META_FILTERS:
            raise RAGError(f"Unsupported metadata filter '{key}'.")
        qs = qs.filter(**{key: value})
    return qs


def _to_retrieved(chunk, similarity: float, score: Optional[float] = None) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=str(chunk.id),
        document_id=str(chunk.document_id),
        document_name=chunk.document.original_filename,
        chunk_index=chunk.chunk_index,
        text=chunk.text,
        page_number=chunk.page_number,
        sheet_name=chunk.sheet_name,
        section_heading=chunk.section_heading,
        similarity=float(similarity),
        score=float(similarity if score is None else score),
        metadata=chunk.metadata or {},
        content_checksum=chunk.content_checksum,
    )


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def _set_hnsw_options():
    """Let HNSW keep scanning when the tenant filter discards candidates (pgvector >= 0.8). Safe no-op otherwise."""
    for stmt in ("SET LOCAL hnsw.iterative_scan = relaxed_order", "SET LOCAL hnsw.ef_search = 100"):
        try:
            with transaction.atomic():  # savepoint: an unknown GUC must not abort the outer transaction
                with connection.cursor() as cur:
                    cur.execute(stmt)
        except Exception:
            logger.debug("pgvector option not supported: %s", stmt)


def vector_search(kb: KnowledgeBase, query_embedding: list[float], limit: int, *, document_ids=None, metadata_filters=None) -> list[RetrievedChunk]:
    qs = _apply_filters(base_queryset(kb), document_ids, metadata_filters).select_related("document")
    if connection.vendor == "postgresql":
        from pgvector.django import CosineDistance

        with transaction.atomic():
            _set_hnsw_options()
            rows = list(
                qs.annotate(distance=CosineDistance("embedding", query_embedding))
                .defer("embedding")
                .order_by("distance")[:limit]
            )
        return [_to_retrieved(c, 1.0 - float(c.distance)) for c in rows]
    # Non-PostgreSQL (unit-test DB only): same SQL-level filters, exact cosine in Python.
    scored = [(c, _cosine(c.embedding, query_embedding)) for c in qs]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [_to_retrieved(c, s) for c, s in scored[:limit]]


def keyword_search(kb: KnowledgeBase, query_text: str, query_embedding: list[float], limit: int, *, document_ids=None, metadata_filters=None) -> list[RetrievedChunk]:
    """Optional lexical leg for hybrid retrieval. Results still carry their cosine similarity."""
    qs = _apply_filters(base_queryset(kb), document_ids, metadata_filters).select_related("document")
    if connection.vendor == "postgresql":
        from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
        from pgvector.django import CosineDistance

        query = SearchQuery(query_text, config="simple", search_type="websearch")
        rows = list(
            qs.annotate(rank=SearchRank(SearchVector("text", config="simple"), query))
            .filter(rank__gt=0)
            .annotate(distance=CosineDistance("embedding", query_embedding))
            .defer("embedding")
            .order_by("-rank")[:limit]
        )
        return [_to_retrieved(c, 1.0 - float(c.distance)) for c in rows]
    terms = {t for t in query_text.lower().split() if len(t) > 2}
    scored = []
    for c in qs:
        hits = sum(1 for t in terms if t in c.text.lower())
        if hits:
            scored.append((hits, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [_to_retrieved(c, _cosine(c.embedding, query_embedding)) for _, c in scored[:limit]]
