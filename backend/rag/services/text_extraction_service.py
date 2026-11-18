"""Shared text utilities and the intermediate `Block` representation produced by parsers."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTI_SPACE = re.compile(r"[ \t\u00a0]+")
_MULTI_NL = re.compile(r"\n{3,}")


@dataclass
class Block:
    """A unit of extracted content that the chunker never splits mid-way (except oversized tables, by row)."""

    kind: str  # "paragraph" | "heading" | "table"
    text: str = ""
    page: Optional[int] = None
    sheet: str = ""
    heading: str = ""  # nearest preceding heading (section)
    # table-only
    header_line: str = ""
    rows: list[str] = field(default_factory=list)

    def full_text(self) -> str:
        if self.kind == "table":
            parts = ([self.header_line] if self.header_line else []) + self.rows
            return "\n".join(parts)
        return self.text


def normalize_text(text: str) -> str:
    """NFC-normalise (important for Tamil), strip control chars, collapse whitespace."""
    text = unicodedata.normalize("NFC", text or "")
    text = _CONTROL.sub("", text).replace("\r\n", "\n").replace("\r", "\n")
    text = _MULTI_SPACE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return _MULTI_NL.sub("\n\n", text).strip()


def estimate_tokens(text: str) -> int:
    """
    Tokenizer-free, deliberately conservative estimate: ~4 chars/token for Latin,
    ~1.5 chars/token for non-ASCII scripts (Tamil etc.). Used only for sizing.
    """
    if not text:
        return 0
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    other = len(text) - ascii_chars
    return max(1, int(ascii_chars / 4 + other / 1.5) + 1)


def cell_to_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return normalize_text(str(value)).replace("\n", " ")


def row_to_line(headers: list[str], cells: list[str]) -> str:
    """'Header: value | Header: value' so a price can never be separated from its product/units."""
    parts = []
    for idx, cell in enumerate(cells):
        if cell == "":
            continue
        h = headers[idx] if idx < len(headers) and headers[idx] else f"Column {idx + 1}"
        parts.append(f"{h}: {cell}")
    return " | ".join(parts)
