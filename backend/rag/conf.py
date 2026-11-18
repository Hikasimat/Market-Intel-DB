"""
Central RAG configuration.

Every value is resolved at call time from (1) Django settings, (2) environment
variables, (3) the default below, so values can be tuned without code changes.
Nothing here enables customer-facing Strict RAG: strict mode is a per-session
opt-in stored in the database (`SessionRAGConfig.strict_rag_enabled`).
"""
from __future__ import annotations

import os

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

DEFAULT_EMBEDDING_MODEL = "amazon.titan-embed-text-v2:0"
TITAN_V2_DIMENSIONS = (256, 512, 1024)


def _raw(name: str, default: str = "") -> str:
    val = getattr(settings, name, None)
    if val is None or val == "":
        val = os.environ.get(name, "")
    if val is None or str(val).strip() == "":
        return default
    return str(val).strip()


def get_str(name: str, default: str = "") -> str:
    return _raw(name, default)


def get_int(name: str, default: int) -> int:
    try:
        return int(_raw(name, str(default)))
    except (TypeError, ValueError):
        return default


def get_float(name: str, default: float) -> float:
    try:
        return float(_raw(name, str(default)))
    except (TypeError, ValueError):
        return default


def get_bool(name: str, default: bool) -> bool:
    val = _raw(name, "")
    if val == "":
        return default
    return val.lower() in ("1", "true", "yes", "on")


# ── Feature flags ────────────────────────────────────────────────────────────
def rag_enabled() -> bool:
    return get_bool("RAG_ENABLED", True)


def strict_mode_default() -> bool:
    # Informational only: new sessions are NEVER auto-enabled for strict mode.
    return get_bool("RAG_STRICT_MODE_DEFAULT", False)


# ── Embeddings ───────────────────────────────────────────────────────────────
def embedding_model_id() -> str:
    primary = _raw("BEDROCK_EMBEDDING_MODEL_ID", "")
    alias = _raw("RAG_EMBEDDING_MODEL", "")
    if primary and alias and primary != alias:
        raise ImproperlyConfigured(
            "BEDROCK_EMBEDDING_MODEL_ID and RAG_EMBEDDING_MODEL disagree "
            f"({primary!r} vs {alias!r}). Set only one, or make them identical."
        )
    return primary or alias or DEFAULT_EMBEDDING_MODEL


def embedding_dimensions() -> int:
    return get_int("RAG_EMBEDDING_DIMENSIONS", 1024)


def aws_region() -> str:
    return (
        _raw("RAG_AWS_REGION")
        or _raw("AWS_REGION")
        or _raw("AWS_DEFAULT_REGION")
        or _raw("AWS_S3_REGION_NAME")
        or "ap-south-1"
    )


def aws_profile() -> str:
    """Optional named profile for local development only."""
    return _raw("RAG_AWS_PROFILE")


def embedding_batch_size() -> int:
    return max(1, get_int("RAG_EMBEDDING_BATCH_SIZE", 16))


def embedding_max_retries() -> int:
    return max(0, get_int("RAG_EMBEDDING_MAX_RETRIES", 5))


def embedding_max_chars() -> int:
    # Titan V2 accepts up to 8192 tokens (~50k chars). Stay well below.
    return get_int("RAG_EMBEDDING_MAX_CHARS", 30000)


# ── Chunking ─────────────────────────────────────────────────────────────────
def chunk_size_tokens() -> int:
    return max(100, get_int("RAG_CHUNK_SIZE", 700))


def chunk_overlap_tokens() -> int:
    return max(0, min(get_int("RAG_CHUNK_OVERLAP", 100), chunk_size_tokens() // 2))


def chunk_max_tokens() -> int:
    return max(chunk_size_tokens(), get_int("RAG_CHUNK_MAX_TOKENS", 900))


# ── Retrieval ────────────────────────────────────────────────────────────────
def default_top_k() -> int:
    return max(1, min(get_int("RAG_DEFAULT_TOP_K", 5), 50))


def min_relevance_threshold() -> float:
    # Starting point only; calibrate with `manage.py evaluate_rag --sweep`.
    return get_float("RAG_MIN_RELEVANCE_THRESHOLD", 0.30)


def max_context_tokens() -> int:
    return max(500, get_int("RAG_MAX_CONTEXT_TOKENS", 3000))


def hybrid_enabled() -> bool:
    return get_bool("RAG_HYBRID_ENABLED", False)


def llm_grounding_check_enabled() -> bool:
    return get_bool("RAG_LLM_GROUNDING_CHECK", True)


def refusal_message() -> str:
    from .constants import DEFAULT_REFUSAL_MESSAGE

    return _raw("RAG_REFUSAL_MESSAGE", DEFAULT_REFUSAL_MESSAGE)


def conversation_context_messages() -> int:
    return max(0, min(get_int("RAG_CONVERSATION_CONTEXT_MESSAGES", 4), 10))


def query_log_retention_days() -> int:
    return get_int("RAG_QUERY_LOG_RETENTION_DAYS", 90)


def gemini_model() -> str:
    return _raw("RAG_GEMINI_MODEL") or _raw("WHATSAPP_AI_MODEL") or "gemini-flash-lite-latest"


def gemini_timeout() -> int:
    return get_int("RAG_GEMINI_TIMEOUT", 25)


# ── Documents / storage ──────────────────────────────────────────────────────
def max_document_bytes() -> int:
    return get_int("RAG_MAX_DOCUMENT_SIZE_MB", 20) * 1024 * 1024


def max_uncompressed_bytes() -> int:
    """Zip-bomb guard for DOCX/XLSX."""
    return get_int("RAG_MAX_UNCOMPRESSED_MB", 200) * 1024 * 1024


def storage_backend() -> str:
    val = _raw("RAG_STORAGE_BACKEND", "local").lower()
    if val not in ("local", "s3"):
        raise ImproperlyConfigured("RAG_STORAGE_BACKEND must be 'local' or 's3'.")
    return val


def s3_bucket() -> str:
    # Reuse the existing bucket configuration unless a dedicated one is given.
    return _raw("RAG_S3_BUCKET_NAME") or _raw("AWS_STORAGE_BUCKET_NAME")


def s3_prefix() -> str:
    return _raw("RAG_S3_PREFIX", "rag-documents").strip("/")


def local_storage_dir() -> str:
    default = os.path.join(str(settings.MEDIA_ROOT), "rag_private")
    return _raw("RAG_LOCAL_STORAGE_DIR", default)


def ocr_backend() -> str:
    return _raw("RAG_OCR_BACKEND", "none").lower()  # none | textract


# ── Queue ────────────────────────────────────────────────────────────────────
def queue_backend() -> str:
    val = _raw("RAG_QUEUE_BACKEND", "local").lower()
    if val not in ("local", "sqs", "inline"):
        raise ImproperlyConfigured("RAG_QUEUE_BACKEND must be 'local', 'sqs' or 'inline'.")
    return val


def ingestion_queue_url() -> str:
    return _raw("RAG_INGESTION_QUEUE_URL")


def ingestion_dlq_url() -> str:
    return _raw("RAG_INGESTION_DLQ_URL")


def stale_processing_seconds() -> int:
    return get_int("RAG_STALE_PROCESSING_SECONDS", 1800)


def max_ingestion_attempts() -> int:
    return max(1, get_int("RAG_MAX_INGESTION_ATTEMPTS", 3))
