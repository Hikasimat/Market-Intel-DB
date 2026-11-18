"""Deterministic reranking. Only reorders; it never admits chunks that failed relevance gating."""
from __future__ import annotations

import re

from .vector_store_service import RetrievedChunk

_TOKEN = re.compile(r"[A-Za-z0-9\u0B80-\u0BFF]{3,}")
_LEXICAL_WEIGHT = 0.15


def tokens(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN.findall(text or "")}


def lexical_overlap(query: str, text: str) -> float:
    q = tokens(query)
    if not q:
        return 0.0
    t_low = (text or "").lower()
    hits = sum(1 for tok in q if tok in t_low)
    return hits / len(q)


def rerank(query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    for c in chunks:
        c.score = c.similarity + _LEXICAL_WEIGHT * lexical_overlap(query, c.text)
    return sorted(chunks, key=lambda c: c.score, reverse=True)
