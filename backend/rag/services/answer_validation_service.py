"""
Answer validation - independent of the model's own confidence.

Checks (all must pass for an answer to be sent):
  1. strict schema,
  2. can_answer / source ids: every id must belong to the chunks actually placed in the prompt, >= 1 id,
  3. no prompt/mechanism leakage,
  4. numbers, e-mails and URLs in the answer must literally occur in the CITED evidence,
  5. lexical support: content words of the answer must be present in the cited evidence (same-script answers),
  6. optional LLM fact-check pass (RAG_LLM_GROUNDING_CHECK).
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field

from .. import conf
from . import guardrails_service
from .context_builder_service import BuiltContext

logger = logging.getLogger("rag.validation")

MIN_MODEL_CONFIDENCE = 0.4
MIN_LEXICAL_SUPPORT = 0.5

_TAMIL_DIGITS = str.maketrans("௦௧௨௩௪௫௬௭௮௯", "0123456789")
_NUM = re.compile(r"\d+(?:[.,]\d+)*")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_URL = re.compile(r"https?://[^\s)>\]]+|www\.[^\s)>\]]+", re.IGNORECASE)
_WORD = re.compile(r"[A-Za-z\u0B80-\u0BFF]{4,}")
_TAMIL = re.compile(r"[\u0B80-\u0BFF]")
_STOP = {
    "this", "that", "with", "from", "have", "will", "your", "for", "and", "the", "are", "you", "our", "can", "please",
    "thank", "thanks", "available", "information", "details", "also", "which", "their", "there", "about", "would",
    "could", "should", "been", "here", "them", "than", "then", "were", "what", "when", "where", "while", "does",
    "document", "documents", "provided", "conflicting", "according", "currently", "following", "mentioned", "stated",
}


@dataclass
class ValidationResult:
    ok: bool
    can_answer: bool = False
    answer: str = ""
    source_ids: list[str] = field(default_factory=list)
    confidence: float = 0.0
    reason: str = ""  # model refusal reason or validation failure code


def _norm_numbers(text: str) -> list[str]:
    text = text.translate(_TAMIL_DIGITS)
    return [n.replace(",", "") for n in _NUM.findall(text)]


def _canon_number(n: str) -> str:
    return n.rstrip("0").rstrip(".") if "." in n else n  # 10.50 == 10.5, but 100 != 1


def _evidence_number_blob(text: str) -> str:
    text = unicodedata.normalize("NFC", text).translate(_TAMIL_DIGITS)
    return re.sub(r"(?<=\d),(?=\d)", "", text)


def _script(text: str) -> str:
    return "ta" if len(_TAMIL.findall(text)) > len(text) * 0.3 else "latin"


def _content_words(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(unicodedata.normalize("NFC", text)) if w.lower() not in _STOP}


def lexical_support(answer: str, evidence: str) -> float:
    words = _content_words(answer)
    if not words:
        return 1.0
    ev = unicodedata.normalize("NFC", evidence).lower()
    hits = sum(1 for w in words if w in ev or (len(w) >= 6 and w[: max(4, len(w) - 3)] in ev))
    return hits / len(words)


def validate(parsed: dict, context: BuiltContext, *, model: str = "") -> ValidationResult:
    # 1. schema
    if not isinstance(parsed, dict) or not parsed:
        return ValidationResult(False, reason="schema_invalid")
    can_answer = parsed.get("can_answer")
    answer = parsed.get("answer")
    ids = parsed.get("source_chunk_ids")
    conf_val = parsed.get("confidence")
    reason = parsed.get("refusal_reason", "")
    if not isinstance(can_answer, bool) or not isinstance(answer, str) or not isinstance(ids, list):
        return ValidationResult(False, reason="schema_invalid")
    if not all(isinstance(i, str) for i in ids) or not isinstance(reason, (str, type(None))):
        return ValidationResult(False, reason="schema_invalid")
    if isinstance(conf_val, bool) or not isinstance(conf_val, (int, float)) or not (0 <= float(conf_val) <= 1):
        return ValidationResult(False, reason="schema_invalid")
    confidence = float(conf_val)

    if not can_answer:
        return ValidationResult(True, can_answer=False, confidence=confidence, reason=(reason or "model_cannot_answer")[:200])

    answer = answer.strip()
    if not answer or len(answer) > 2000:
        return ValidationResult(False, reason="answer_empty_or_too_long")

    # 2. citations must be real, retrieved, and in the prompt
    if not ids:
        return ValidationResult(False, reason="no_sources")
    allowed = context.ids
    if any(i not in allowed for i in ids):
        return ValidationResult(False, reason="unknown_source_id")
    ids = list(dict.fromkeys(ids))
    if confidence < MIN_MODEL_CONFIDENCE:
        return ValidationResult(False, reason="low_model_confidence")

    # 3. leakage
    if guardrails_service.answer_leaks_internals(answer):
        return ValidationResult(False, reason="internal_leak")

    cited = [c for c in context.included if c.chunk_id in set(ids)]
    evidence = "\n".join(c.text for c in cited)

    # 4. literal grounding of risky tokens
    ev_blob = _evidence_number_blob(evidence)
    ev_numbers = {_canon_number(n) for n in _norm_numbers(ev_blob)}
    for num in _norm_numbers(answer):
        if _canon_number(num) not in ev_numbers:
            return ValidationResult(False, reason="ungrounded_number")
    ev_low = evidence.lower()
    for token in _EMAIL.findall(answer) + _URL.findall(answer):
        if token.lower().rstrip(".,") not in ev_low:
            return ValidationResult(False, reason="ungrounded_contact_or_url")

    # 5. lexical support (only when answer and evidence use the same script)
    if _script(answer) == _script(evidence) and lexical_support(answer, evidence) < MIN_LEXICAL_SUPPORT:
        return ValidationResult(False, reason="low_lexical_support")

    # 6. optional LLM fact-check
    if conf.llm_grounding_check_enabled():
        from . import answer_generation_service

        supported, claims, _ = answer_generation_service.judge_grounding(answer, context, ids, model=model)
        if not supported:
            logger.info("LLM grounding check rejected the answer (%d unsupported claims)", len(claims))
            return ValidationResult(False, reason="llm_grounding_failed")

    return ValidationResult(True, can_answer=True, answer=answer, source_ids=ids, confidence=confidence)
