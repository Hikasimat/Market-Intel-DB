import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q

from . import conf
from . import constants as C
from .fields import EmbeddingField


class KnowledgeBase(models.Model):
    """
    A tenant-scoped collection of documents.

    Tenant = `company` when set (company-level KB shared with that company's
    users), otherwise the owning user (personal KB).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="rag_knowledge_bases")
    company = models.ForeignKey(
        "companies.Company", on_delete=models.CASCADE, null=True, blank=True, related_name="rag_knowledge_bases"
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "name"], name="rag_kb_unique_owner_name"),
        ]
        indexes = [models.Index(fields=["owner", "is_active"]), models.Index(fields=["company", "is_active"])]

    def __str__(self):
        return self.name

    @property
    def tenant_key(self) -> str:
        return f"company-{self.company_id}" if self.company_id else f"user-{self.owner_id}"


class KnowledgeDocument(models.Model):
    class Status(models.TextChoices):
        UPLOADED = C.STATUS_UPLOADED, "Uploaded"
        VALIDATING = C.STATUS_VALIDATING, "Validating"
        PROCESSING = C.STATUS_PROCESSING, "Processing"
        CHUNKING = C.STATUS_CHUNKING, "Chunking"
        EMBEDDING = C.STATUS_EMBEDDING, "Embedding"
        READY = C.STATUS_READY, "Ready"
        FAILED = C.STATUS_FAILED, "Failed"
        DELETING = C.STATUS_DELETING, "Deleting"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    knowledge_base = models.ForeignKey(KnowledgeBase, on_delete=models.CASCADE, related_name="documents")
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=10)
    file_size = models.PositiveBigIntegerField(default=0)
    storage_key = models.CharField(max_length=512, blank=True, default="")  # never exposed via API
    mime_type = models.CharField(max_length=127, blank=True, default="")
    checksum_sha256 = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.UPLOADED, db_index=True)
    processing_error = models.TextField(blank=True, default="")
    total_pages = models.PositiveIntegerField(default=0)  # pages or sheets
    total_chunks = models.PositiveIntegerField(default=0)
    version = models.PositiveIntegerField(default=1)
    # Only the single active version of a document is retrievable. A new version
    # becomes active only after it is fully READY (see ingestion_worker).
    is_active = models.BooleanField(default=False)
    replaces = models.ForeignKey("self", on_delete=models.SET_NULL, null=True, blank=True, related_name="replaced_by")
    processing_attempts = models.PositiveIntegerField(default=0)
    processing_started_at = models.DateTimeField(null=True, blank=True)
    ready_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="rag_documents"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["knowledge_base", "original_filename", "version"], name="rag_doc_unique_name_version"
            ),
        ]
        indexes = [models.Index(fields=["knowledge_base", "status", "is_active"])]

    def __str__(self):
        return f"{self.original_filename} v{self.version} [{self.status}]"


class KnowledgeDocumentChunk(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(KnowledgeDocument, on_delete=models.CASCADE, related_name="chunks")
    # Denormalised on purpose: lets the vector query filter by knowledge base
    # directly in SQL without a join on the hot path.
    knowledge_base = models.ForeignKey(KnowledgeBase, on_delete=models.CASCADE, related_name="chunks")
    chunk_index = models.PositiveIntegerField()
    text = models.TextField()
    embedding = EmbeddingField(dimensions=1024)
    embedding_model = models.CharField(max_length=128)
    embedding_dimension = models.PositiveIntegerField()
    page_number = models.PositiveIntegerField(null=True, blank=True)
    sheet_name = models.CharField(max_length=255, blank=True, default="")
    section_heading = models.CharField(max_length=500, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    token_count = models.PositiveIntegerField(default=0)
    content_checksum = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document_id", "chunk_index"]
        constraints = [
            models.UniqueConstraint(fields=["document", "chunk_index"], name="rag_chunk_unique_doc_index"),
        ]
        indexes = [
            models.Index(fields=["knowledge_base", "embedding_model"]),
            models.Index(fields=["document", "content_checksum"]),
        ]
        # The HNSW cosine index is created in migration 0002 (PostgreSQL only).


class KnowledgeBaseSessionAssignment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        "whatsapp.WhatsAppSession", on_delete=models.CASCADE, related_name="rag_assignments"
    )
    knowledge_base = models.ForeignKey(KnowledgeBase, on_delete=models.CASCADE, related_name="session_assignments")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            # At most one ACTIVE knowledge base per WhatsApp session.
            models.UniqueConstraint(
                fields=["session"], condition=Q(is_active=True), name="rag_one_active_assignment_per_session"
            ),
            models.UniqueConstraint(fields=["session", "knowledge_base"], name="rag_assignment_unique_pair"),
        ]


class SessionRAGConfig(models.Model):
    """
    Per-session Strict RAG switch (kept in `rag` so the existing
    WhatsAppAIAutoReplyConfig model/migrations stay untouched).
    Absence of a row == strict mode OFF == legacy behaviour.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField("whatsapp.WhatsAppSession", on_delete=models.CASCADE, related_name="rag_config")
    strict_rag_enabled = models.BooleanField(default=False)
    refusal_message = models.TextField(blank=True, default="")
    top_k = models.PositiveSmallIntegerField(null=True, blank=True)
    min_relevance_threshold = models.FloatField(null=True, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def effective_refusal_message(self) -> str:
        return (self.refusal_message or "").strip() or conf.refusal_message()


class RAGQueryLog(models.Model):
    class AnswerStatus(models.TextChoices):
        ANSWERED = "ANSWERED", "Answered"
        REFUSED = "REFUSED", "Refused"
        ERROR = "ERROR", "Error"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        "whatsapp.WhatsAppSession", on_delete=models.SET_NULL, null=True, blank=True, related_name="rag_query_logs"
    )
    knowledge_base = models.ForeignKey(KnowledgeBase, on_delete=models.SET_NULL, null=True, blank=True, related_name="query_logs")
    source = models.CharField(max_length=16, default="whatsapp")  # whatsapp | test
    question = models.TextField(blank=True, default="")  # truncated; see rag_pipeline_service
    retrieval_status = models.CharField(max_length=32, blank=True, default="")
    retrieved_chunk_ids = models.JSONField(default=list, blank=True)
    similarity_scores = models.JSONField(default=list, blank=True)
    source_document_ids = models.JSONField(default=list, blank=True)
    model_used = models.CharField(max_length=128, blank=True, default="")
    answer_status = models.CharField(max_length=10, choices=AnswerStatus.choices, default=AnswerStatus.REFUSED)
    refusal_reason = models.CharField(max_length=64, blank=True, default="")
    processing_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["session", "-created_at"]), models.Index(fields=["knowledge_base", "-created_at"])]


class IngestionJob(models.Model):
    """DB-backed queue used when RAG_QUEUE_BACKEND=local (dev). Production uses SQS."""

    class Status(models.TextChoices):
        QUEUED = "QUEUED", "Queued"
        RUNNING = "RUNNING", "Running"
        DONE = "DONE", "Done"
        FAILED = "FAILED", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(KnowledgeDocument, on_delete=models.CASCADE, related_name="ingestion_jobs")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField(auto_now_add=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at"]
        indexes = [models.Index(fields=["status", "available_at"])]
