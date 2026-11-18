"""Upload validation. Never trusts the extension alone: extension + declared MIME + magic bytes."""
from __future__ import annotations

import hashlib
import io
import mimetypes
import os
import re
import zipfile
from dataclasses import dataclass

from .. import conf
from ..constants import ALLOWED_MIME_TYPES, SUPPORTED_EXTENSIONS
from ..exceptions import DocumentValidationError

_UNSAFE_NAME = re.compile(r"[^\w\-. ()\u0080-\uffff]")


@dataclass
class ValidatedUpload:
    filename: str
    file_type: str
    mime_type: str
    size: int
    checksum: str
    data: bytes


def sanitize_filename(name: str) -> str:
    name = os.path.basename((name or "").replace("\\", "/")).strip()
    name = _UNSAFE_NAME.sub("_", name).lstrip(".")
    if not name:
        raise DocumentValidationError("A valid file name is required.", code="invalid_filename")
    return name[:200]


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _check_zip_container(data: bytes, required_member_prefix: str):
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise DocumentValidationError("The file is corrupted or not a valid Office document.", code="malformed") from exc
    infos = zf.infolist()
    total = sum(i.file_size for i in infos)
    if total > conf.max_uncompressed_bytes() or len(infos) > 5000:
        raise DocumentValidationError("The document expands to an unsafe size.", code="unsafe_archive")
    for i in infos:
        if i.filename.startswith("/") or ".." in i.filename.split("/"):
            raise DocumentValidationError("The document contains unsafe paths.", code="unsafe_archive")
    if not any(i.filename.startswith(required_member_prefix) for i in infos):
        raise DocumentValidationError("The file extension does not match the file content.", code="signature_mismatch")


def _check_signature(file_type: str, data: bytes):
    head = data[:2048]
    if file_type == "pdf":
        if b"%PDF-" not in head[:1024]:
            raise DocumentValidationError("The file is not a valid PDF.", code="signature_mismatch")
    elif file_type == "docx":
        if not data.startswith(b"PK"):
            raise DocumentValidationError("The file is not a valid DOCX.", code="signature_mismatch")
        _check_zip_container(data, "word/")
    elif file_type == "xlsx":
        if not data.startswith(b"PK"):
            raise DocumentValidationError("The file is not a valid XLSX.", code="signature_mismatch")
        _check_zip_container(data, "xl/")
    else:  # text based: csv / txt / md
        if b"\x00" in data[:8192] or data.startswith(b"%PDF") or data.startswith(b"PK\x03\x04"):
            raise DocumentValidationError("The file does not look like a text document.", code="signature_mismatch")


def validate_upload(filename: str, data: bytes, declared_mime: str = "") -> ValidatedUpload:
    safe_name = sanitize_filename(filename)
    ext = os.path.splitext(safe_name)[1].lower()
    file_type = SUPPORTED_EXTENSIONS.get(ext)
    if not file_type:
        raise DocumentValidationError(
            f"Unsupported file type '{ext or 'unknown'}'. Supported: PDF, DOCX, XLSX, CSV, TXT, Markdown.",
            code="unsupported_type",
        )
    size = len(data)
    if size == 0:
        raise DocumentValidationError("The file is empty.", code="empty_file")
    if size > conf.max_document_bytes():
        raise DocumentValidationError(
            f"The file exceeds the {conf.max_document_bytes() // (1024 * 1024)} MB limit.", code="file_too_large"
        )

    mime = (declared_mime or "").split(";")[0].strip().lower()
    if not mime:
        mime = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    if mime not in ALLOWED_MIME_TYPES[file_type]:
        raise DocumentValidationError(
            f"MIME type '{mime}' is not allowed for .{ext.lstrip('.')} files.", code="mime_mismatch"
        )
    _check_signature(file_type, data)
    return ValidatedUpload(
        filename=safe_name, file_type=file_type, mime_type=mime, size=size, checksum=sha256_hex(data), data=data
    )
