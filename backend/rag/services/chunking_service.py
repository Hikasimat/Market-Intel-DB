"""
Structure-aware chunking.

* Target size / overlap / hard max come from `rag.conf` (env-tunable).
* Boundaries: headings, paragraphs and tables. Tables are never split mid-row;
  an oversized table is split row-wise and the header line is repeated in every part
  so a value can never be separated from the column that describes it.
* Overlap applies to prose only (never across a table).
* Every chunk carries page / sheet / section metadata.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from .. import conf
from .text_extraction_service import Block, estimate_tokens

_SENT_SPLIT = re.compile(r"(?<=[.!?।])\s+|\n")


@dataclass
class ChunkDraft:
    text: str
    page: int | None = None
    sheet: str = ""
    heading: str = ""
    token_count: int = 0
    metadata: dict = field(default_factory=dict)

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def _split_long_text(text: str, limit: int) -> list[str]:
    """Split an over-long paragraph on sentence boundaries, hard-splitting only as a last resort."""
    pieces, cur, cur_t = [], [], 0
    for sent in _SENT_SPLIT.split(text):
        sent = sent.strip()
        if not sent:
            continue
        t = estimate_tokens(sent)
        if t > limit:  # single huge sentence: hard split by characters
            if cur:
                pieces.append(" ".join(cur))
                cur, cur_t = [], 0
            step = max(200, int(limit * 3))
            pieces.extend(sent[i : i + step] for i in range(0, len(sent), step))
            continue
        if cur_t + t > limit and cur:
            pieces.append(" ".join(cur))
            cur, cur_t = [], 0
        cur.append(sent)
        cur_t += t
    if cur:
        pieces.append(" ".join(cur))
    return pieces


def chunk_blocks(blocks: list[Block], *, size: int | None = None, overlap: int | None = None, max_tokens: int | None = None) -> list[ChunkDraft]:
    size = size or conf.chunk_size_tokens()
    overlap = conf.chunk_overlap_tokens() if overlap is None else overlap
    max_tokens = max_tokens or conf.chunk_max_tokens()

    chunks: list[ChunkDraft] = []
    units: list[tuple[str, int]] = []  # (text, tokens) of current prose chunk
    state = {"page": None, "sheet": "", "heading": "", "pages": set()}

    def reset_meta():
        state.update(page=None, sheet="", heading="", pages=set())

    def emit(text: str, tokens: int, extra: dict | None = None):
        meta = {"pages": sorted(state["pages"])} if state["pages"] else {}
        meta.update(extra or {})
        chunks.append(
            ChunkDraft(text=text, page=state["page"], sheet=state["sheet"], heading=state["heading"], token_count=tokens, metadata=meta)
        )

    def flush_prose(carry_overlap: bool = True):
        nonlocal units
        if not units:
            return
        text = "\n".join(u[0] for u in units).strip()
        if text:
            emit(text, sum(u[1] for u in units))
        tail: list[tuple[str, int]] = []
        if carry_overlap and overlap > 0:
            acc = 0
            for u in reversed(units):
                if acc + u[1] > overlap and tail:
                    break
                if u[1] > overlap:  # never carry a unit bigger than the overlap budget
                    break
                tail.insert(0, u)
                acc += u[1]
        units = tail
        if not tail:
            reset_meta_keep_heading()

    def reset_meta_keep_heading():
        state.update(page=None, sheet="", pages=set())

    def touch(block: Block):
        if state["page"] is None and block.page is not None:
            state["page"] = block.page
        if block.page is not None:
            state["pages"].add(block.page)
        if not state["sheet"] and block.sheet:
            state["sheet"] = block.sheet
        if block.heading and not state["heading"]:
            state["heading"] = block.heading

    for block in blocks:
        if block.kind == "table":
            flush_prose(carry_overlap=False)
            units = []
            reset_meta()
            _emit_table(block, size, max_tokens, chunks)
            continue

        text = block.full_text().strip()
        if not text:
            continue

        if block.kind == "heading":
            cur_tokens = sum(u[1] for u in units)
            if units and cur_tokens >= size * 0.3:
                flush_prose(carry_overlap=False)
                units = []
                reset_meta()
            state["heading"] = state["heading"] or block.heading or text
            if not units:
                state["heading"] = block.heading or text
            touch(block)
            units.append((text, estimate_tokens(text)))
            continue

        pieces = [text] if estimate_tokens(text) <= max_tokens else _split_long_text(text, size)
        for piece in pieces:
            t = estimate_tokens(piece)
            cur = sum(u[1] for u in units)
            if units and cur + t > size:
                flush_prose()
            if not units:
                state["heading"] = block.heading or state["heading"]
            touch(block)
            units.append((piece, t))

    flush_prose(carry_overlap=False)
    return chunks


def _emit_table(block: Block, size: int, max_tokens: int, out: list[ChunkDraft]) -> None:
    ctx = " > ".join(x for x in (block.sheet, block.heading if block.heading != block.sheet else "") if x)
    header = block.header_line
    prefix = ((f"Table: {ctx}\n" if ctx else "Table:\n") + (header + "\n" if header else "")).rstrip("\n") + "\n"
    prefix_t = estimate_tokens(prefix)
    total = prefix_t + sum(estimate_tokens(r) for r in block.rows)

    def make(rows: list[str], part: int, parts: int):
        text = prefix + "\n".join(rows)
        meta = {"table": True, "row_count": len(rows)}
        if parts > 1:
            meta.update(part=part, parts=parts)
        out.append(
            ChunkDraft(text=text.strip(), page=block.page, sheet=block.sheet, heading=block.heading,
                       token_count=estimate_tokens(text), metadata=meta)
        )

    if total <= max_tokens:
        make(block.rows, 1, 1)
        return
    groups, cur, cur_t = [], [], prefix_t
    for row in block.rows:
        rt = estimate_tokens(row)
        if cur and cur_t + rt > size:
            groups.append(cur)
            cur, cur_t = [], prefix_t
        cur.append(row)
        cur_t += rt
    if cur:
        groups.append(cur)
    for i, g in enumerate(groups, start=1):
        make(g, i, len(groups))


def embedding_input_for_chunk(filename: str, chunk_text: str, *, sheet: str = "", heading: str = "", page: int | None = None) -> str:
    """Text actually embedded: the chunk prefixed with its source context (improves retrieval)."""
    ctx = [f"Document: {filename}"]
    if sheet:
        ctx.append(f"Sheet: {sheet}")
    if heading and heading != sheet:
        ctx.append(f"Section: {heading}")
    if page:
        ctx.append(f"Page: {page}")
    return " | ".join(ctx) + "\n" + chunk_text
