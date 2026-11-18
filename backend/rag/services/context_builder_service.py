"""Builds the bounded, sanitised evidence block sent to Gemini."""
from __future__ import annotations

from dataclasses import dataclass

from .. import conf
from . import guardrails_service
from .text_extraction_service import estimate_tokens
from .vector_store_service import RetrievedChunk


@dataclass
class BuiltContext:
    text: str
    included: list[RetrievedChunk]

    @property
    def ids(self) -> set[str]:
        return {c.chunk_id for c in self.included}


def source_label(c: RetrievedChunk) -> str:
    parts = [c.document_name]
    if c.page_number:
        parts.append(f"page {c.page_number}")
    if c.sheet_name:
        parts.append(f"sheet {c.sheet_name}")
    if c.section_heading and c.section_heading != c.sheet_name:
        parts.append(f"section {c.section_heading[:80]}")
    return ", ".join(parts)


def build_context(chunks: list[RetrievedChunk], max_tokens: int | None = None) -> BuiltContext:
    budget = max_tokens or conf.max_context_tokens()
    used, included, blocks = 0, [], []
    for c in chunks:
        body = guardrails_service.sanitize_evidence(c.text)
        t = estimate_tokens(body)
        if included and used + t > budget:
            break
        if not included and t > budget:  # always keep the best chunk, truncated
            body = body[: budget * 3]
            t = budget
        used += t
        included.append(c)
        blocks.append(
            f'<evidence id="{c.chunk_id}" source="{guardrails_service.sanitize_evidence(source_label(c))}">\n{body}\n</evidence>'
        )
    return BuiltContext(text="\n\n".join(blocks), included=included)
