import logging

from django.db import connection
from django.http import Http404
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from . import conf
from .exceptions import DocumentValidationError, StorageError
from .models import KnowledgeBase, KnowledgeBaseSessionAssignment, KnowledgeDocument, SessionRAGConfig
from .permissions import CanConfigureRetrieval, CanUseRAG
from .serializers import (
    AssignmentSerializer,
    DocumentUploadSerializer,
    KnowledgeBaseSerializer,
    KnowledgeDocumentSerializer,
    SessionSettingsUpdateSerializer,
    TestQuerySerializer,
    session_settings_payload,
)
from .services import document_upload_service, knowledge_base_service as kbs, rag_pipeline_service

logger = logging.getLogger("rag.api")


class UploadThrottle(UserRateThrottle):
    scope = "rag_upload"
    rate = "30/hour"


class TestQueryThrottle(UserRateThrottle):
    scope = "rag_test_query"
    rate = "60/hour"


def _get_kb_or_404(user, pk) -> KnowledgeBase:
    kb = kbs.accessible_knowledge_bases(user).filter(pk=pk).select_related("owner").first()
    if kb is None:
        raise Http404
    return kb


def _get_document_or_404(user, pk) -> KnowledgeDocument:
    doc = KnowledgeDocument.objects.filter(pk=pk, knowledge_base__in=kbs.accessible_knowledge_bases(user)).select_related("knowledge_base").first()
    if doc is None:
        raise Http404
    return doc


def _get_session_or_404(user, session_id):
    from whatsapp.models import WhatsAppSession

    try:
        session = WhatsAppSession.objects.select_related("owner").filter(pk=session_id).first()
    except (ValueError, TypeError):
        session = None
    if session is None or not kbs.can_manage_session(user, session):
        raise Http404  # do not reveal other users' sessions
    return session


class KnowledgeBaseViewSet(viewsets.ModelViewSet):
    permission_classes = [CanUseRAG]
    serializer_class = KnowledgeBaseSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    filter_backends: list = []

    def get_queryset(self):
        return kbs.accessible_knowledge_bases(self.request.user).select_related("owner").order_by("-created_at")

    def perform_create(self, serializer):
        if not kbs.can_ingest_documents(self.request.user):
            raise PermissionDenied("Only a Super Admin has permission to create knowledge bases and ingest documents.")
        serializer.save()

    def perform_update(self, serializer):
        if not kbs.can_ingest_documents(self.request.user):
            raise PermissionDenied("Only a Super Admin has permission to modify knowledge bases.")
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        kb = self.get_object()
        if not kbs.can_ingest_documents(request.user):
            raise PermissionDenied("Only a Super Admin has permission to delete knowledge bases.")
        try:
            kbs.delete_knowledge_base(kb, actor=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except StorageError:
            return Response({"detail": "Some files could not be removed. The knowledge base was deactivated; retry deletion."}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get", "post"], url_path="documents", parser_classes=[MultiPartParser, FormParser], throttle_classes=[UploadThrottle])
    def documents(self, request, pk=None):
        kb = self.get_object()
        if request.method == "GET":
            qs = kb.documents.exclude(status="DELETING").select_related("created_by").order_by("-created_at")
            page = self.paginate_queryset(qs)
            ser = KnowledgeDocumentSerializer(page, many=True)
            return self.get_paginated_response(ser.data)
        if not kbs.can_ingest_documents(request.user):
            raise PermissionDenied("Only a Super Admin has permission to upload and ingest documents.")
        if not kbs.can_write_kb(request.user, kb):
            raise PermissionDenied("You cannot upload to this knowledge base.")
        up = DocumentUploadSerializer(data=request.data)
        up.is_valid(raise_exception=True)
        try:
            doc = document_upload_service.upload_document(kb, request.user, up.validated_data["file"])
        except DocumentValidationError as exc:
            code = status.HTTP_409_CONFLICT if exc.code == "duplicate_document" else (
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE if exc.code == "file_too_large" else status.HTTP_400_BAD_REQUEST
            )
            return Response({"detail": str(exc), "code": exc.code}, status=code)
        except StorageError:
            return Response({"detail": "The document could not be stored. Please retry."}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(KnowledgeDocumentSerializer(doc).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"], url_path="statistics")
    def statistics(self, request, pk=None):
        return Response(kbs.statistics(self.get_object()))


class DocumentDetailView(APIView):
    permission_classes = [CanUseRAG]

    def get(self, request, pk):
        return Response(KnowledgeDocumentSerializer(_get_document_or_404(request.user, pk)).data)

    def delete(self, request, pk):
        if not kbs.can_ingest_documents(request.user):
            raise PermissionDenied("Only a Super Admin has permission to delete ingested documents.")
        doc = _get_document_or_404(request.user, pk)
        if not kbs.can_write_kb(request.user, doc.knowledge_base):
            raise PermissionDenied("You cannot delete this document.")
        try:
            kbs.delete_document(doc, actor=request.user)
        except Exception:
            return Response({"detail": "Deletion is incomplete and will be retried; the document is already excluded from answers."}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentRetryView(APIView):
    permission_classes = [CanUseRAG]

    def post(self, request, pk):
        if not kbs.can_ingest_documents(request.user):
            raise PermissionDenied("Only a Super Admin has permission to retry document ingestion.")
        doc = _get_document_or_404(request.user, pk)
        if not kbs.can_write_kb(request.user, doc.knowledge_base):
            raise PermissionDenied("You cannot retry this document.")
        try:
            doc = document_upload_service.retry_document(doc, user=request.user)
        except DocumentValidationError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_409_CONFLICT)
        return Response(KnowledgeDocumentSerializer(doc).data, status=status.HTTP_202_ACCEPTED)


class AssignmentViewSet(viewsets.ModelViewSet):
    permission_classes = [CanUseRAG]
    serializer_class = AssignmentSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    filter_backends: list = []

    def get_queryset(self):
        user = self.request.user
        qs = KnowledgeBaseSessionAssignment.objects.select_related("session", "knowledge_base")
        if not user.is_superuser:
            qs = qs.filter(session__owner=user)  # only assignments of sessions the user owns
        kb_id = self.request.query_params.get("knowledge_base")
        if kb_id:
            qs = qs.filter(knowledge_base_id=kb_id)
        return qs.order_by("-created_at")


class SessionSettingsView(APIView):
    """Per-session AI + Strict RAG settings. GET list / GET detail / PATCH detail."""

    permission_classes = [CanUseRAG]

    def get(self, request, session_id=None):
        from whatsapp.models import WhatsAppSession

        if session_id is not None:
            return Response(session_settings_payload(_get_session_or_404(request.user, session_id)))
        qs = WhatsAppSession.objects.select_related("owner").filter(is_active=True).exclude(session_name__startswith="hist_")
        if not request.user.is_superuser:
            qs = qs.filter(owner=request.user)
        return Response({"results": [session_settings_payload(s) for s in qs.order_by("-created_at")]})

    def patch(self, request, session_id):
        session = _get_session_or_404(request.user, session_id)
        ser = SessionSettingsUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        tuning_keys = {"refusal_message", "top_k", "min_relevance_threshold"} & set(data)
        if tuning_keys and not kbs.can_configure_retrieval(request.user):
            raise PermissionDenied("Only administrators can change retrieval settings.")

        if "ai_enabled" in data:
            from whatsapp_ai.gemini_service import _get_or_create_ai_config

            cfg = _get_or_create_ai_config(session)
            cfg.enabled = data["ai_enabled"]
            cfg.save(update_fields=["enabled", "updated_at"])

        rag_cfg, _ = SessionRAGConfig.objects.get_or_create(session=session)
        if data.get("strict_rag_enabled") is True:
            resolution = kbs.resolve_kb_for_session(session)
            if resolution.kb is None:
                raise ValidationError({
                    "strict_rag_enabled": (
                        "Strict RAG requires an active knowledge base with READY documents assigned to this session "
                        f"({resolution.reason})."
                    )
                })
        for key in ("strict_rag_enabled", "refusal_message", "top_k", "min_relevance_threshold"):
            if key in data:
                setattr(rag_cfg, key, data[key])
        rag_cfg.updated_by = request.user
        rag_cfg.save()
        return Response(session_settings_payload(session))


class TestQueryView(APIView):
    """Ask a question against a KB without sending any WhatsApp message."""

    permission_classes = [CanUseRAG]
    parser_classes = [JSONParser]
    throttle_classes = [TestQueryThrottle]

    def post(self, request):
        if not conf.rag_enabled():
            return Response({"detail": "RAG is disabled."}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        ser = TestQuerySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data
        history = [
            (("customer" if h.get("role") == "customer" else "assistant"), str(h.get("text", ""))[:600])
            for h in data.get("history", []) if h.get("text")
        ]
        if data.get("session_id"):
            session = _get_session_or_404(request.user, data["session_id"])
            result = rag_pipeline_service.answer_for_session(session, data["question"], history, source="test", include_chunk_text=True)
        else:
            kb = _get_kb_or_404(request.user, data["knowledge_base_id"])
            result = rag_pipeline_service.answer_for_kb(kb, request.user, data["question"], history)
        if result.status == "ERROR":
            return Response({"detail": "The knowledge base is temporarily unavailable.", "refusal_reason": result.refusal_reason}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({
            "answered": result.status == "ANSWERED",
            "evidence_found": result.retrieval_status == "ok",
            "answer": result.reply_text if result.status == "ANSWERED" else "",
            "refusal_message": result.reply_text if result.status == "REFUSED" else "",
            "refusal_reason": result.refusal_reason,
            "validation_detail": result.detail if kbs.can_configure_retrieval(request.user) else "",
            "sources": result.sources,
            "retrieved": result.retrieved,
            "processing_ms": result.processing_ms,
        })


class HealthView(APIView):
    permission_classes = [CanUseRAG]

    def get(self, request):
        pgvector = None
        if connection.vendor == "postgresql":
            with connection.cursor() as cur:
                cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
                row = cur.fetchone()
                pgvector = row[0] if row else None
        payload = {
            "rag_enabled": conf.rag_enabled(),
            "database_vendor": connection.vendor,
            "pgvector_installed": pgvector is not None,
            "embedding_model": conf.embedding_model_id(),
            "embedding_dimensions": conf.embedding_dimensions(),
            "storage_backend": conf.storage_backend(),
            "queue_backend": conf.queue_backend(),
        }
        if request.user.is_superuser:
            payload["pgvector_version"] = pgvector
        return Response(payload)
