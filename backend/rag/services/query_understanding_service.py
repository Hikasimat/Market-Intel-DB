"""Question normalisation, language detection and (lightweight) follow-up resolution."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_TAMIL = re.compile(r"[\u0B80-\u0BFF]")
_LATIN = re.compile(r"[A-Za-z]")
MAX_QUESTION_CHARS = 1000


@dataclass
class QueryPlan:
    original: str
    normalized: str
    retrieval_query: str
    language: str  # "ta" | "en" | "mixed" | "other"
    is_followup: bool


def normalize_question(text: str) -> str:
    text = unicodedata.normalize("NFC", text or "")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:MAX_QUESTION_CHARS]


def detect_language(text: str) -> str:
    ta = len(_TAMIL.findall(text))
    la = len(_LATIN.findall(text))
    if ta and la:
        return "mixed" if min(ta, la) / max(ta, la) > 0.15 else ("ta" if ta > la else "en")
    if ta:
        return "ta"
    if la:
        return "en"
    return "other"


_FOLLOWUP_STARTS = (
    "and ", "also ", "what about", "how about", "how much", "is it", "does it", "do they", "what is the", "that ", "those ",
    "அதன்", "அது", "அப்படி", "மேலும்", "அதற்கு",
)


def understand(question: str, previous_customer_messages: list[str] | None = None) -> QueryPlan:
    normalized = normalize_question(question)
    prev = [normalize_question(m) for m in (previous_customer_messages or []) if m and m.strip()]
    words = normalized.split()
    low = normalized.lower()
    short = len(words) <= 4
    followup = bool(prev) and (short or low.startswith(_FOLLOWUP_STARTS))
    retrieval_query = normalized
    if followup:
        # Resolve references by retrieving with the previous customer turn as context.
        retrieval_query = f"{prev[-1]} {normalized}"[: MAX_QUESTION_CHARS * 2]
    return QueryPlan(
        original=question or "",
        normalized=normalized,
        retrieval_query=retrieval_query,
        language=detect_language(normalized),
        is_followup=followup,
    )
