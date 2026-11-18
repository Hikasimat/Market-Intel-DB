"""
Tenant-authorised retrieval: embed query -> SQL-filtered vector search (+ optional hybrid)
-> dedupe -> relevance gating -> rerank.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from .. import conf
from ..exceptions import AuthorizationError
from ..models import KnowledgeBase, KnowledgeBaseSessionAssignment
from . import embedding_service, knowledge_base_service, reranking_service, vector_store_service
from .vector_store_service import RetrievedChunk

logger = logging.getLogger("rag.retrieval")

RRF_K = 60


@dataclass
class RetrievalResult:
    status: str  # "ok" | "no_results" | "low_relevance"
    chunks: list[RetrievedChunk] = field(default_factory=list)  # gated + reranked, <= top_k
    candidates: list[RetrievedChunk] = field(default_factory=list)  # everything considered (for diagnostics/eval)
    best_similarity: float = 0.0
    threshold: float = 0.0


def authorize(kb_or_kbs, *, session=None, user=None) -> list[KnowledgeBase]:
    """Explicit authorisation before EVERY retrieval. Raises AuthorizationError."""
    kbs = vector_store_service._normalize_kb_list(kb_or_kbs)
    if not kbs:
        raise AuthorizationError("No knowledge base provided for retrieval.")
    for kb in kbs:
        if session is not None:
            ok = knowledge_base_service.tenant_compatible(session.owner, kb) and kb.is_active
        elif user is not None:
            ok = knowledge_base_service.accessible_knowledge_bases(user).filter(pk=kb.pk).exists()
        else:
            ok = False
        if not ok:
            raise AuthorizationError("Not authorised to retrieve from this knowledge base.")
    return kbs


_norm_ws = re.compile(r"\s+")


def _dedupe(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    seen, out = set(), []
    for c in chunks:
        key = c.content_checksum or _norm_ws.sub(" ", c.text.strip().lower())
        text_key = _norm_ws.sub(" ", c.text.strip().lower())
        if key in seen or text_key in seen:
            continue
        seen.add(key)
        seen.add(text_key)
        out.append(c)
    return out


def _rrf_merge(vector_hits: list[RetrievedChunk], keyword_hits: list[RetrievedChunk]) -> list[RetrievedChunk]:
    merged: dict[str, RetrievedChunk] = {}
    scores: dict[str, float] = {}
    for hits in (vector_hits, keyword_hits):
        for rank, c in enumerate(hits):
            merged.setdefault(c.chunk_id, c)
            scores[c.chunk_id] = scores.get(c.chunk_id, 0.0) + 1.0 / (RRF_K + rank + 1)
    ordered = sorted(merged.values(), key=lambda c: scores[c.chunk_id], reverse=True)
    for c in ordered:
        c.score = scores[c.chunk_id]
    return ordered


def retrieve(
    kb: KnowledgeBase,
    *,
    query_text: str,
    session=None,
    user=None,
    top_k: int | None = None,
    threshold: float | None = None,
    hybrid: bool | None = None,
    document_ids=None,
    metadata_filters=None,
    query_embedding: list[float] | None = None,
) -> RetrievalResult:
    authorize(kb, session=session, user=user)
    top_k = top_k or conf.default_top_k()
    threshold = conf.min_relevance_threshold() if threshold is None else threshold
    hybrid = conf.hybrid_enabled() if hybrid is None else hybrid

    qvec = query_embedding if query_embedding is not None else embedding_service.embed_query(query_text)
    limit = max(top_k * 3, 15)
    vector_hits = vector_store_service.vector_search(
        kb, qvec, limit, document_ids=document_ids, metadata_filters=metadata_filters
    )
    candidates = vector_hits
    if hybrid:
        keyword_hits = vector_store_service.keyword_search(
            kb, query_text, qvec, limit, document_ids=document_ids, metadata_filters=metadata_filters
        )
        candidates = _rrf_merge(vector_hits, keyword_hits)
    candidates = _dedupe(candidates)
    if not candidates:
        return RetrievalResult("no_results", threshold=threshold)

    best = max(c.similarity for c in candidates)
    gated = []
    for c in candidates:
        if c.similarity >= threshold:
            gated.append(c)
        elif hybrid and c.similarity >= threshold * 0.7 and reranking_service.lexical_overlap(query_text, c.text) >= 0.6:
            gated.append(c)  # strong exact-term evidence (e.g. SKU/model number) backing a borderline vector score
    if not gated:
        return RetrievalResult("low_relevance", candidates=candidates, best_similarity=best, threshold=threshold)

    ranked = reranking_service.rerank(query_text, gated)[:top_k]
    return RetrievalResult("ok", chunks=ranked, candidates=candidates, best_similarity=best, threshold=threshold)
