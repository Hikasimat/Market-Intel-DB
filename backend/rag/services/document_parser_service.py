"""Type-specific parsers. Output: (list[Block], total_pages_or_sheets). Document content is treated as data only."""
from __future__ import annotations

import csv
import io
import logging
import re
import time

from .. import conf
from ..exceptions import DocumentParseError, OCRRequiredError
from .text_extraction_service import Block, cell_to_str, normalize_text, row_to_line

logger = logging.getLogger("rag.parser")

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_MAX_SHEET_ROWS = 200_000


def parse_document(file_type: str, data: bytes, *, storage_key: str = "") -> tuple[list[Block], int]:
    try:
        if file_type == "pdf":
            return _parse_pdf(data, storage_key)
        if file_type == "docx":
            return _parse_docx(data)
        if file_type == "xlsx":
            return _parse_xlsx(data)
        if file_type == "csv":
            return _parse_csv(data)
        if file_type in ("txt", "md"):
            return _parse_text(data, markdown=(file_type == "md"))
    except DocumentParseError:
        raise
    except Exception as exc:  # malformed content must fail the document, not the worker
        raise DocumentParseError(f"Could not parse {file_type.upper()} document ({type(exc).__name__}).") from exc
    raise DocumentParseError(f"Unsupported file type: {file_type}")


# ── helpers ───────────────────────────────────────────────────────────────────
def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16"):
        try:
            return data.decode(enc)
        except UnicodeError:
            continue
    return data.decode("cp1252", errors="replace")


def _paragraph_blocks(text: str, *, page=None, sheet="", heading="") -> list[Block]:
    out = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if para:
            out.append(Block(kind="paragraph", text=para, page=page, sheet=sheet, heading=heading))
    return out


# ── TXT / Markdown ───────────────────────────────────────────────────────────
def _parse_text(data: bytes, markdown: bool) -> tuple[list[Block], int]:
    text = normalize_text(_decode(data))
    if not text:
        raise DocumentParseError("The document contains no extractable text.")
    if not markdown:
        return _paragraph_blocks(text), 1
    blocks: list[Block] = []
    heading = ""
    buf: list[str] = []

    def flush():
        if buf:
            blocks.extend(_paragraph_blocks("\n".join(buf), heading=heading))
            buf.clear()

    for line in text.split("\n"):
        m = _MD_HEADING.match(line)
        if m:
            flush()
            heading = m.group(2).strip()
            blocks.append(Block(kind="heading", text=heading, heading=heading))
        else:
            buf.append(line)
    flush()
    return blocks, 1


# ── CSV ──────────────────────────────────────────────────────────────────────
def _parse_csv(data: bytes) -> tuple[list[Block], int]:
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [[cell_to_str(c) for c in row] for row in csv.reader(io.StringIO(text), dialect)]
    rows = [r for r in rows if any(r)]
    if not rows:
        raise DocumentParseError("The CSV contains no data.")
    return [_table_block(rows, sheet="", page=None)], 1


def _table_block(rows: list[list[str]], *, sheet: str, page, heading: str = "") -> Block:
    headers = rows[0]
    body = rows[1:] if len(rows) > 1 else []
    header_line = "Columns: " + " | ".join(h or f"Column {i + 1}" for i, h in enumerate(headers))
    lines = [row_to_line(headers, r) for r in body]
    lines = [ln for ln in lines if ln]
    if not lines:  # header-only / single-row table: keep the row text itself
        lines = [" | ".join(c for c in headers if c)]
        header_line = ""
    return Block(kind="table", sheet=sheet, page=page, heading=heading, header_line=header_line, rows=lines)


# ── XLSX ─────────────────────────────────────────────────────────────────────
def _parse_xlsx(data: bytes) -> tuple[list[Block], int]:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    blocks: list[Block] = []
    sheets = 0
    try:
        for ws in wb.worksheets:
            rows: list[list[str]] = []
            for idx, row in enumerate(ws.iter_rows(values_only=True)):
                if idx >= _MAX_SHEET_ROWS:
                    raise DocumentParseError(f"Sheet '{ws.title}' exceeds the supported row limit.")
                cells = [cell_to_str(c) for c in row]
                if any(cells):
                    rows.append(cells)
            if not rows:
                continue
            sheets += 1
            blocks.append(_table_block(rows, sheet=ws.title, page=None, heading=ws.title))
    finally:
        wb.close()
    if not blocks:
        raise DocumentParseError("The workbook contains no data.")
    return blocks, sheets


# ── DOCX ─────────────────────────────────────────────────────────────────────
def _parse_docx(data: bytes) -> tuple[list[Block], int]:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = docx.Document(io.BytesIO(data))
    blocks: list[Block] = []
    heading = ""
    pending: list[str] = []

    def flush():
        if pending:
            blocks.extend(_paragraph_blocks("\n\n".join(pending), heading=heading))
            pending.clear()

    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            para = Paragraph(child, document)
            text = normalize_text(para.text)
            if not text:
                continue
            style = (para.style.name or "") if para.style is not None else ""
            if style.lower().startswith(("heading", "title")):
                flush()
                heading = text
                blocks.append(Block(kind="heading", text=text, heading=heading))
            else:
                pending.append(text)
        elif tag == "tbl":
            flush()
            table = Table(child, document)
            rows = [[cell_to_str(c.text) for c in r.cells] for r in table.rows]
            rows = [r for r in rows if any(r)]
            if rows:
                blk = _table_block(rows, sheet="", page=None, heading=heading)
                blocks.append(blk)
    flush()
    if not any(b.full_text().strip() for b in blocks):
        raise DocumentParseError("The document contains no extractable text.")
    return blocks, 1


# ── PDF ──────────────────────────────────────────────────────────────────────
_PDF_MIN_CHARS_PER_PAGE = 25


def _looks_like_heading(line: str) -> bool:
    line = line.strip()
    if not (3 <= len(line) <= 90) or line.endswith((".", ",", ";")):
        return False
    words = line.split()
    return len(words) <= 10 and (line.isupper() or re.match(r"^(\d+(\.\d+)*[.)]?\s+)\S", line) is not None)


def _parse_pdf(data: bytes, storage_key: str) -> tuple[list[Block], int]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentParseError("Encrypted PDFs are not supported.")
        page_texts = [normalize_text(p.extract_text() or "") for p in reader.pages]
    except PdfReadError as exc:
        raise DocumentParseError("The PDF is malformed or unreadable.") from exc

    total_pages = len(page_texts)
    if total_pages == 0:
        raise DocumentParseError("The PDF has no pages.")
    chars = sum(len(t) for t in page_texts)
    if chars < _PDF_MIN_CHARS_PER_PAGE * total_pages:
        # Scanned / image-only PDF.
        if conf.ocr_backend() == "textract" and storage_key and conf.storage_backend() == "s3":
            page_texts = _textract_pages(storage_key, total_pages)
            if sum(len(t) for t in page_texts) < _PDF_MIN_CHARS_PER_PAGE:
                raise OCRRequiredError("OCR produced no text for this PDF.")
        else:
            raise OCRRequiredError(
                "This PDF appears to be scanned (no extractable text). OCR is required: "
                "set RAG_OCR_BACKEND=textract with the S3 storage backend, or upload a text-based PDF."
            )

    blocks: list[Block] = []
    heading = ""
    for page_no, text in enumerate(page_texts, start=1):
        if not text:
            continue
        for para in re.split(r"\n\s*\n", text):
            para = para.strip()
            if not para:
                continue
            first = para.split("\n", 1)[0]
            if _looks_like_heading(first):
                heading = first.strip()
                rest = para.split("\n", 1)[1].strip() if "\n" in para else ""
                blocks.append(Block(kind="heading", text=heading, page=page_no, heading=heading))
                if rest:
                    blocks.append(Block(kind="paragraph", text=rest, page=page_no, heading=heading))
            else:
                blocks.append(Block(kind="paragraph", text=para, page=page_no, heading=heading))
    return blocks, total_pages


def _textract_pages(storage_key: str, total_pages: int) -> list[str]:  # pragma: no cover - needs AWS
    """Async Textract OCR for S3-stored PDFs (production). Requires textract:Start/GetDocumentTextDetection."""
    import boto3

    profile = conf.aws_profile()
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    client = session.client("textract", region_name=conf.aws_region())
    job = client.start_document_text_detection(
        DocumentLocation={"S3Object": {"Bucket": conf.s3_bucket(), "Name": storage_key}}
    )
    job_id = job["JobId"]
    deadline = time.time() + 600
    while time.time() < deadline:
        res = client.get_document_text_detection(JobId=job_id)
        if res["JobStatus"] == "SUCCEEDED":
            break
        if res["JobStatus"] == "FAILED":
            raise DocumentParseError("Textract OCR failed.")
        time.sleep(3)
    else:
        raise DocumentParseError("Textract OCR timed out.")
    pages: dict[int, list[str]] = {}
    token = None
    while True:
        res = client.get_document_text_detection(JobId=job_id, **({"NextToken": token} if token else {}))
        for blk in res.get("Blocks", []):
            if blk.get("BlockType") == "LINE":
                pages.setdefault(int(blk.get("Page", 1)), []).append(blk.get("Text", ""))
        token = res.get("NextToken")
        if not token:
            break
    return [normalize_text("\n".join(pages.get(i, []))) for i in range(1, total_pages + 1)]
