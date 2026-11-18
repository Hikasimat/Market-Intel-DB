"""
Embedding generation service:
* Production / AWS configured: Amazon Bedrock Titan Text Embeddings V2 (`amazon.titan-embed-text-v2:0`, 1024 dims)
  using boto3's default credential chain (EC2 IAM instance role in production, or AWS env/profile locally).
* Local development (`DEBUG=True`) when no AWS credentials are configured on the machine:
  automatically uses the configured `GEMINI_API_KEY` (`gemini-embedding-001` with `outputDimensionality=1024`,
  L2-normalized) for BOTH document ingestion and query embeddings so local testing works out of the box without
  mixing vectors from different models.
"""
from __future__ import annotations

import json
import logging
import math
import os
import random
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from django.conf import settings

from .. import conf
from ..exceptions import EmbeddingConfigError, EmbeddingError

logger = logging.getLogger("rag.embedding")

GEMINI_LOCAL_EMBEDDING_MODEL = "gemini-embedding-001"

_RETRYABLE_CODES = {
    "ThrottlingException",
    "TooManyRequestsException",
    "ModelTimeoutException",
    "ServiceUnavailableException",
    "InternalServerException",
    "ModelNotReadyException",
    "RequestTimeout",
    "RequestTimeoutException",
}

# Test seam: replace with a callable returning an object exposing invoke_model().
_client_factory: Optional[Callable[[], object]] = None
_cached_client = None
_aws_creds_checked: Optional[bool] = None


def _has_aws_credentials() -> bool:
    global _aws_creds_checked
    if _client_factory is not None:
        return True
    if os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"):
        return True
    if _aws_creds_checked is not None:
        return _aws_creds_checked
    try:
        import boto3

        profile = conf.aws_profile()
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        creds = session.get_credentials()
        _aws_creds_checked = bool(creds and creds.access_key)
    except Exception:
        _aws_creds_checked = False
    return bool(_aws_creds_checked)


def _use_gemini_local_embeddings() -> bool:
    """
    Use Gemini 1024-dim embeddings in local dev (DEBUG=True) when no AWS credentials are
    present on the developer workstation and GEMINI_API_KEY is configured.
    Never used when _client_factory is set (unit tests) or when AWS credentials exist.
    """
    if _client_factory is not None:
        return False
    configured = conf.embedding_model_id()
    if configured.startswith("gemini-embedding"):
        return True
    if not getattr(settings, "DEBUG", False):
        return False
    if _has_aws_credentials():
        return False
    gemini_key = (os.environ.get("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    return bool(gemini_key)


def _get_client():
    global _cached_client
    if _client_factory is not None:
        return _client_factory()
    if _cached_client is None:
        import boto3

        profile = conf.aws_profile()
        session = boto3.Session(profile_name=profile) if profile else boto3.Session()
        _cached_client = session.client("bedrock-runtime", region_name=conf.aws_region())
    return _cached_client


def reset_client_cache() -> None:
    global _cached_client, _aws_creds_checked
    _cached_client = None
    _aws_creds_checked = None


def current_model() -> tuple[str, int]:
    dim = conf.embedding_dimensions()
    if _use_gemini_local_embeddings():
        return GEMINI_LOCAL_EMBEDDING_MODEL, dim
    return conf.embedding_model_id(), dim


def validate_configuration() -> tuple[str, int]:
    # Always validate env consistency first
    conf_model = conf.embedding_model_id()
    dim = conf.embedding_dimensions()
    if "titan-embed-text-v2" in conf_model and dim not in conf.TITAN_V2_DIMENSIONS:
        raise EmbeddingConfigError(f"Titan V2 supports dimensions {conf.TITAN_V2_DIMENSIONS}, got {dim}.")
    from ..models import KnowledgeDocumentChunk

    column_dim = KnowledgeDocumentChunk._meta.get_field("embedding").dimensions
    if column_dim != dim:
        raise EmbeddingConfigError(
            f"RAG_EMBEDDING_DIMENSIONS={dim} does not match the database vector column ({column_dim}). "
            "Changing dimensions requires a schema migration plus a full re-embed."
        )
    return current_model()


def _validate_input(text: str) -> str:
    if not isinstance(text, str) or not text.strip():
        raise EmbeddingError("Cannot embed empty text.")
    limit = conf.embedding_max_chars()
    return text if len(text) <= limit else text[:limit]


def _error_code(exc: Exception) -> str:
    resp = getattr(exc, "response", None)
    if isinstance(resp, dict):
        return str((resp.get("Error") or {}).get("Code") or "")
    return type(exc).__name__


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in vec))
    if not norm:
        return vec
    return [x / norm for x in vec]


def _embed_one_gemini(text: str, model: str, dim: int) -> list[float]:
    api_key = (os.environ.get("GEMINI_API_KEY") or getattr(settings, "GEMINI_API_KEY", "") or "").strip()
    if not api_key:
        raise EmbeddingError("GEMINI_API_KEY is not configured.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent?key={api_key}"
    payload = json.dumps({
        "model": f"models/{model}",
        "content": {"parts": [{"text": text}]},
        "outputDimensionality": dim,
    }).encode("utf-8")
    attempts = conf.embedding_max_retries() + 1
    last: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            values = (data.get("embedding") or {}).get("values")
            return _l2_normalize(_validate_vector(values, dim))
        except EmbeddingError:
            raise
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                break
            delay = min(20.0, (2 ** attempt) * 0.5) * (0.5 + random.random() / 2)
            time.sleep(delay)
        except Exception as exc:
            last = exc
            if attempt == attempts - 1:
                break
            time.sleep(0.5 * (attempt + 1))
    raise EmbeddingError(f"Embedding generation failed ({type(last).__name__ if last else 'unknown'}).") from last


def _embed_one(text: str, model: str, dim: int) -> list[float]:
    if model == GEMINI_LOCAL_EMBEDDING_MODEL:
        return _embed_one_gemini(text, model, dim)
    body = json.dumps({"inputText": text, "dimensions": dim, "normalize": True})
    attempts = conf.embedding_max_retries() + 1
    last: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            resp = _get_client().invoke_model(
                modelId=model, body=body, contentType="application/json", accept="application/json"
            )
            raw = resp["body"].read() if hasattr(resp["body"], "read") else resp["body"]
            vector = json.loads(raw)["embedding"]
            return _validate_vector(vector, dim)
        except EmbeddingError:
            raise
        except Exception as exc:
            code = _error_code(exc)
            retryable = code in _RETRYABLE_CODES or type(exc).__name__ in (
                "ReadTimeoutError",
                "ConnectTimeoutError",
                "EndpointConnectionError",
            )
            last = exc
            if not retryable or attempt == attempts - 1:
                logger.error("Bedrock embedding failed (code=%s, attempt=%d/%d)", code, attempt + 1, attempts)
                break
            delay = min(30.0, (2 ** attempt) * 0.5) * (0.5 + random.random() / 2)
            logger.warning("Bedrock embedding throttled/transient (code=%s); retry in %.1fs", code, delay)
            time.sleep(delay)
    raise EmbeddingError(f"Embedding generation failed ({_error_code(last) if last else 'unknown'}).") from last


def _validate_vector(vector, dim: int) -> list[float]:
    if not isinstance(vector, list) or len(vector) != dim:
        raise EmbeddingError(
            f"Embedding dimension mismatch: expected {dim}, got {len(vector) if isinstance(vector, list) else 'n/a'}."
        )
    out = [float(x) for x in vector]
    if not all(math.isfinite(x) for x in out):
        raise EmbeddingError("Embedding contains non-finite values.")
    return out


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Batch embedding."""
    model, dim = validate_configuration()
    prepared = [_validate_input(t) for t in texts]
    started = time.monotonic()
    results: list[list[float]] = []
    batch = conf.embedding_batch_size()
    workers = min(4, batch)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i in range(0, len(prepared), batch):
            results.extend(pool.map(lambda t: _embed_one(t, model, dim), prepared[i : i + batch]))
    logger.info("Embedded %d texts with %s (dim=%d) in %.2fs", len(prepared), model, dim, time.monotonic() - started)
    if len(results) != len(texts):
        raise EmbeddingError("Embedding count mismatch.")
    return results


def embed_query(text: str) -> list[float]:
    model, dim = validate_configuration()
    return _embed_one(_validate_input(text), model, dim)
