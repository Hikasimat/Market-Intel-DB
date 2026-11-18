"""Static constants for the RAG app. Tunable values live in `rag.conf`."""

DEFAULT_REFUSAL_MESSAGE = (
    "Sorry, I can only assist with questions related to the information available in "
    "this company's knowledge base. Please ask something related to our products, "
    "services or company information."
)

# Document processing statuses
STATUS_UPLOADED = "UPLOADED"
STATUS_VALIDATING = "VALIDATING"
STATUS_PROCESSING = "PROCESSING"
STATUS_CHUNKING = "CHUNKING"
STATUS_EMBEDDING = "EMBEDDING"
STATUS_READY = "READY"
STATUS_FAILED = "FAILED"
STATUS_DELETING = "DELETING"

IN_FLIGHT_STATUSES = (STATUS_VALIDATING, STATUS_PROCESSING, STATUS_CHUNKING, STATUS_EMBEDDING)

# Supported file types: extension -> canonical type
SUPPORTED_EXTENSIONS = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".xlsx": "xlsx",
    ".csv": "csv",
    ".txt": "txt",
    ".md": "md",
    ".markdown": "md",
}

ALLOWED_MIME_TYPES = {
    "pdf": {"application/pdf", "application/x-pdf"},
    "docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
        "application/octet-stream",
    },
    "xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
        "application/octet-stream",
    },
    "csv": {"text/csv", "application/csv", "application/vnd.ms-excel", "text/plain", "application/octet-stream"},
    "txt": {"text/plain", "application/octet-stream"},
    "md": {"text/markdown", "text/x-markdown", "text/plain", "application/octet-stream"},
}

# Refusal reason codes (stored in RAGQueryLog.refusal_reason)
REASON_EMPTY_QUESTION = "empty_question"
REASON_NO_KB = "no_knowledge_base"
REASON_KB_INACTIVE = "knowledge_base_inactive"
REASON_NO_READY_DOCS = "no_ready_documents"
REASON_TENANT_MISMATCH = "tenant_mismatch"
REASON_NO_RETRIEVAL = "no_relevant_chunks"
REASON_LOW_RELEVANCE = "low_relevance"
REASON_MODEL_REFUSED = "model_cannot_answer"
REASON_VALIDATION_FAILED = "answer_validation_failed"
REASON_INJECTION_QUESTION = "prompt_injection_suspected"
REASON_INFRA = "rag_unavailable"
