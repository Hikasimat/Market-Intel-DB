"""Strict-RAG guardrails: injection heuristics, evidence sanitising, output leak checks."""
from __future__ import annotations

import re

_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier|your)\s+(instructions?|rules?|prompts?|guidelines?)",
    r"disregard\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier|your)\s+(instructions?|rules?)",
    r"(reveal|show|print|repeat|tell me)\s+(me\s+)?(your|the)\s+(system\s+)?(prompt|instructions?|rules)",
    r"\bsystem\s+prompt\b",
    r"you\s+are\s+now\s+(a|an|in)\b",
    r"\b(developer|jailbreak|dan)\s+mode\b",
    r"forget\s+(everything|all|your)\s+(you|instructions?|rules)",
    r"act\s+as\s+(if\s+you\s+(are|were)\s+)?(a|an)\s+(?!customer)",
    r"pretend\s+(to\s+be|you)",
    r"override\s+(your|the|all)\s+(rules|instructions|restrictions)",
]
_INJECTION_RE = re.compile("|".join(f"(?:{p})" for p in _INJECTION_PATTERNS), re.IGNORECASE)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Fragments that must never appear in an outgoing answer (prompt / mechanism leakage).
_LEAK_RE = re.compile(
    r"(strict rag|system instruction|<\s*/?\s*evidence|source_chunk_ids|can_answer|chunk id=|as an ai language model)",
    re.IGNORECASE,
)


def question_injection_suspected(question: str) -> bool:
    return bool(_INJECTION_RE.search(question or ""))


def chunk_has_injection(text: str) -> bool:
    """Diagnostic only: such text is still passed as DATA, never obeyed."""
    return bool(_INJECTION_RE.search(text or ""))


def sanitize_evidence(text: str) -> str:
    """Neutralise anything that could close/forge our evidence delimiters."""
    text = _CONTROL.sub("", text or "")
    return text.replace("<", "\u2039").replace(">", "\u203a")


def sanitize_customer_text(text: str, limit: int = 600) -> str:
    return sanitize_evidence(text)[:limit]


def answer_leaks_internals(answer: str) -> bool:
    return bool(_LEAK_RE.search(answer or ""))
