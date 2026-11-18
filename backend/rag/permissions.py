from rest_framework.permissions import BasePermission

from .services import knowledge_base_service as kbs


class CanUseRAG(BasePermission):
    """PRE / LQ / MANAGER / Super Admin - the same population that may use the WhatsApp module."""

    def has_permission(self, request, view):
        return kbs.can_use_rag(request.user)


class CanConfigureRetrieval(BasePermission):
    """Retrieval tuning (top-K, relevance threshold, refusal wording): MANAGER / Super Admin only."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and kbs.can_configure_retrieval(request.user))


class CanIngestDocuments(BasePermission):
    """Document upload, ingestion, retry, and deletion: Super Admin (is_superuser) only."""

    message = "Only a Super Admin has permission to ingest or manage knowledge base documents."

    def has_permission(self, request, view):
        return kbs.can_ingest_documents(request.user)

