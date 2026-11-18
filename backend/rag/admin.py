from django.contrib import admin

from .models import (
    IngestionJob,
    KnowledgeBase,
    KnowledgeBaseSessionAssignment,
    KnowledgeDocument,
    RAGQueryLog,
    SessionRAGConfig,
)


@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "company", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "owner__username")


@admin.register(KnowledgeDocument)
class KnowledgeDocumentAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "knowledge_base", "status", "version", "is_active", "total_chunks", "created_at")
    list_filter = ("status", "file_type", "is_active")
    exclude = ("storage_key",)
    readonly_fields = ("checksum_sha256",)


@admin.register(KnowledgeBaseSessionAssignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("session", "knowledge_base", "is_active", "created_at")


@admin.register(SessionRAGConfig)
class SessionRAGConfigAdmin(admin.ModelAdmin):
    list_display = ("session", "strict_rag_enabled", "top_k", "min_relevance_threshold", "updated_at")
    list_filter = ("strict_rag_enabled",)


@admin.register(RAGQueryLog)
class RAGQueryLogAdmin(admin.ModelAdmin):
    list_display = ("created_at", "source", "answer_status", "refusal_reason", "retrieval_status", "processing_ms")
    list_filter = ("answer_status", "source", "refusal_reason")
    readonly_fields = [f.name for f in RAGQueryLog._meta.fields]


@admin.register(IngestionJob)
class IngestionJobAdmin(admin.ModelAdmin):
    list_display = ("document", "status", "attempts", "available_at", "updated_at")
    list_filter = ("status",)
