class RAGError(Exception):
    """Base class. Messages must be safe to log (never include document text)."""


class DocumentValidationError(RAGError):
    """Upload rejected (type, size, signature, empty, duplicate...)."""

    def __init__(self, message: str, code: str = "invalid_document"):
        super().__init__(message)
        self.code = code


class DuplicateDocumentError(DocumentValidationError):
    def __init__(self, message: str = "An identical document already exists in this knowledge base."):
        super().__init__(message, code="duplicate_document")


class DocumentParseError(RAGError):
    """Malformed or unreadable document."""


class OCRRequiredError(DocumentParseError):
    """Scanned PDF with no extractable text and no OCR backend available."""


class StorageError(RAGError):
    pass


class EmbeddingError(RAGError):
    """Embedding generation failed. Callers must stop - never substitute a model."""


class EmbeddingConfigError(EmbeddingError):
    pass


class RAGInfrastructureError(RAGError):
    """Retrieval/generation infrastructure failure (not a content problem).
    In strict mode this must produce NO answer rather than a general-knowledge one."""


class AuthorizationError(RAGError):
    pass
