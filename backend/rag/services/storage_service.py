"""
Private document storage: local filesystem (dev) or private S3 bucket (prod).

* Keys are tenant-prefixed and unguessable; they are NEVER returned by the API.
* S3 uses the default boto3 credential chain (EC2 instance role in production).
  No access keys are read or logged here. Objects are written with SSE and are
  never public; presigned URLs are short-lived and only generated on demand.
"""
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from .. import conf
from ..exceptions import StorageError

logger = logging.getLogger("rag.storage")


def build_storage_key(tenant_key: str, kb_id, doc_id, filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()[:10]
    return f"{conf.s3_prefix()}/{tenant_key}/{kb_id}/{doc_id}/{uuid.uuid4().hex}{ext}"


def _s3_client():
    import boto3

    kwargs = {"region_name": conf.aws_region()}
    profile = conf.aws_profile()
    session = boto3.Session(profile_name=profile) if profile else boto3.Session()
    return session.client("s3", **kwargs)


def _local_path(key: str) -> Path:
    root = Path(conf.local_storage_dir()).resolve()
    path = (root / key).resolve()
    if root not in path.parents:  # path traversal guard
        raise StorageError("Invalid storage key.")
    return path


def save(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    try:
        if conf.storage_backend() == "s3":
            bucket = conf.s3_bucket()
            if not bucket:
                raise StorageError("RAG_S3_BUCKET_NAME (or AWS_STORAGE_BUCKET_NAME) is not configured.")
            _s3_client().put_object(
                Bucket=bucket, Key=key, Body=data, ContentType=content_type, ServerSideEncryption="AES256"
            )
        else:
            path = _local_path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    except StorageError:
        raise
    except Exception as exc:
        logger.error("RAG storage save failed (%s)", type(exc).__name__)
        raise StorageError("Could not store the document.") from exc


def read(key: str) -> bytes:
    try:
        if conf.storage_backend() == "s3":
            obj = _s3_client().get_object(Bucket=conf.s3_bucket(), Key=key)
            return obj["Body"].read()
        return _local_path(key).read_bytes()
    except StorageError:
        raise
    except Exception as exc:
        logger.error("RAG storage read failed (%s)", type(exc).__name__)
        raise StorageError("Could not read the stored document.") from exc


def delete(key: str) -> None:
    """Idempotent: deleting a missing object succeeds."""
    if not key:
        return
    try:
        if conf.storage_backend() == "s3":
            _s3_client().delete_object(Bucket=conf.s3_bucket(), Key=key)
        else:
            path = _local_path(key)
            if path.exists():
                path.unlink()
                # prune now-empty directories inside the storage root
                root = Path(conf.local_storage_dir()).resolve()
                parent = path.parent
                while parent != root and parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
                    parent = parent.parent
    except StorageError:
        raise
    except Exception as exc:
        logger.error("RAG storage delete failed (%s)", type(exc).__name__)
        raise StorageError("Could not delete the stored document.") from exc


def presigned_url(key: str, expires_seconds: int = 300) -> str:
    """Short-lived download URL (S3 only). Not exposed by any default API."""
    if conf.storage_backend() != "s3":
        raise StorageError("Presigned URLs are only available with the S3 backend.")
    return _s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": conf.s3_bucket(), "Key": key},
        ExpiresIn=max(30, min(int(expires_seconds), 900)),
    )
