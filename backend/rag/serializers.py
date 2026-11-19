from django.db import transaction
from rest_framework import serializers

from . import conf
from .models import KnowledgeBase, KnowledgeBaseSessionAssignment, KnowledgeDocument, SessionRAGConfig
from .services import knowledge_base_service as kbs


class KnowledgeBaseSerializer(serializers.ModelSerializer):
    company_level = serializers.BooleanField(write_only=True, required=False, default=False)
    scope = serializers.SerializerMethodField()
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    readiness = serializers.SerializerMethodField()
    document_count = serializers.SerializerMethodField()
    assigned_sessions = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    can_ingest = serializers.SerializerMethodField()

    class Meta:
        model = KnowledgeBase
        fields = [
            "id", "name", "description", "is_active", "company_level", "scope", "owner_username",
            "readiness", "document_count", "assigned_sessions", "can_edit", "can_ingest", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_scope(self, obj):
        return "company" if obj.company_id else "personal"

    def get_readiness(self, obj):
        return kbs.kb_readiness(obj)

    def get_document_count(self, obj):
        return obj.documents.exclude(status="DELETING").count()

    def get_assigned_sessions(self, obj):
        user = self.context["request"].user
        qs = obj.session_assignments.filter(is_active=True).select_related("session")
        if not user.is_superuser:
            qs = qs.filter(session__owner=user)
        return [{"session_id": a.session_id, "session_name": a.session.session_name} for a in qs]

    def get_can_edit(self, obj):
        return kbs.can_write_kb(self.context["request"].user, obj)

    def get_can_ingest(self, obj):
        return kbs.can_ingest_documents(self.context["request"].user)

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Name is required.")
        return value

    def validate(self, attrs):
        user = self.context["request"].user
        if self.instance is None:
            name = attrs.get("name")
            if KnowledgeBase.objects.filter(owner=user, name=name).exists():
                raise serializers.ValidationError({"name": "You already have a knowledge base with this name."})
            if attrs.get("company_level"):
                if not kbs.user_company_id(user):
                    raise serializers.ValidationError({"company_level": "Your account is not linked to a company."})
                if kbs.user_role(user) not in ("MANAGER", "SUPERADMIN"):
                    raise serializers.ValidationError({"company_level": "Only managers can create company knowledge bases."})
        elif "name" in attrs and KnowledgeBase.objects.filter(owner=self.instance.owner, name=attrs["name"]).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError({"name": "A knowledge base with this name already exists."})
        return attrs

    def create(self, validated):
        user = self.context["request"].user
        company_level = validated.pop("company_level", False)
        company_id = kbs.user_company_id(user) if company_level else None
        return KnowledgeBase.objects.create(owner=user, company_id=company_id, **validated)

    def update(self, instance, validated):
        validated.pop("company_level", None)  # scope is immutable (tenant boundary)
        return super().update(instance, validated)


class KnowledgeDocumentSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source="created_by.username", read_only=True, default=None)

    class Meta:
        model = KnowledgeDocument
        # storage_key / checksum / internal paths are deliberately NOT exposed.
        fields = [
            "id", "knowledge_base", "original_filename", "file_type", "file_size", "mime_type", "status",
            "processing_error", "total_pages", "total_chunks", "version", "is_active", "created_by",
            "created_at", "updated_at", "ready_at",
        ]
        read_only_fields = fields


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class AssignmentSerializer(serializers.ModelSerializer):
    session_name = serializers.CharField(source="session.session_name", read_only=True)
    session_phone = serializers.CharField(source="session.phone_number", read_only=True)
    knowledge_base_name = serializers.CharField(source="knowledge_base.name", read_only=True)

    class Meta:
        model = KnowledgeBaseSessionAssignment
        fields = [
            "id", "session", "session_name", "session_phone", "knowledge_base", "knowledge_base_name",
            "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        user = self.context["request"].user
        session = attrs.get("session") or (self.instance.session if self.instance else None)
        kb = attrs.get("knowledge_base") or (self.instance.knowledge_base if self.instance else None)
        if self.instance is not None and ("session" in attrs or "knowledge_base" in attrs):
            if attrs.get("session", session) != self.instance.session or attrs.get("knowledge_base", kb) != self.instance.knowledge_base:
                raise serializers.ValidationError("Session and knowledge base cannot be changed; create a new assignment.")
        ok, msg = kbs.can_assign(user, session, kb)
        if not ok:
            raise serializers.ValidationError(msg)
        return attrs

    @transaction.atomic
    def create(self, validated):
        session, kb = validated["session"], validated["knowledge_base"]
        is_active = validated.get("is_active", True)
        if is_active:
            KnowledgeBaseSessionAssignment.objects.filter(session=session, is_active=True).exclude(knowledge_base=kb).update(is_active=False)
        obj, _ = KnowledgeBaseSessionAssignment.objects.update_or_create(
            session=session, knowledge_base=kb, defaults={"is_active": is_active}
        )
        if is_active and kbs.kb_readiness(kb).get("is_ready"):
            SessionRAGConfig.objects.update_or_create(
                session=session,
                defaults={"strict_rag_enabled": True},
            )
        return obj

    @transaction.atomic
    def update(self, instance, validated):
        if validated.get("is_active"):
            KnowledgeBaseSessionAssignment.objects.filter(session=instance.session, is_active=True).exclude(pk=instance.pk).update(is_active=False)
        instance.is_active = validated.get("is_active", instance.is_active)
        instance.save()
        return instance


class TestQuerySerializer(serializers.Serializer):
    question = serializers.CharField(max_length=1000, trim_whitespace=True)
    knowledge_base_id = serializers.UUIDField(required=False)
    session_id = serializers.CharField(required=False)
    history = serializers.ListField(child=serializers.DictField(), required=False, max_length=6)

    def validate(self, attrs):
        if not attrs.get("knowledge_base_id") and not attrs.get("session_id"):
            raise serializers.ValidationError("Provide knowledge_base_id or session_id.")
        return attrs


class SessionSettingsUpdateSerializer(serializers.Serializer):
    ai_enabled = serializers.BooleanField(required=False)
    strict_rag_enabled = serializers.BooleanField(required=False)
    refusal_message = serializers.CharField(required=False, allow_blank=True, max_length=600)
    top_k = serializers.IntegerField(required=False, allow_null=True, min_value=1, max_value=20)
    min_relevance_threshold = serializers.FloatField(required=False, allow_null=True, min_value=0.0, max_value=1.0)


def session_settings_payload(session) -> dict:
    from whatsapp_ai.models import WhatsAppAIAutoReplyConfig

    resolution = kbs.resolve_kb_for_session(session)
    ai_cfg = WhatsAppAIAutoReplyConfig.objects.filter(session=session).first()
    rag_cfg = SessionRAGConfig.objects.filter(session=session).first()
    assignment = (
        KnowledgeBaseSessionAssignment.objects.select_related("knowledge_base")
        .filter(session=session, is_active=True)
        .first()
    )
    kb = assignment.knowledge_base if assignment else resolution.kb
    has_ready_kb = resolution.kb is not None
    strict_enabled = bool(rag_cfg.strict_rag_enabled) if rag_cfg is not None else has_ready_kb
    return {
        "session_id": session.pk,
        "session_name": session.session_name,
        "owner_username": session.owner.username if session.owner else "",
        "phone_number": session.phone_number or "",
        "status": session.status,
        # New/unconfigured sessions default to OFF (False) until explicitly enabled by owner.
        "ai_enabled": bool(ai_cfg.enabled) if ai_cfg else False,
        "strict_rag_enabled": strict_enabled,
        "refusal_message": rag_cfg.refusal_message if rag_cfg else "",
        "default_refusal_message": conf.refusal_message(),
        "top_k": rag_cfg.top_k if rag_cfg else None,
        "min_relevance_threshold": rag_cfg.min_relevance_threshold if rag_cfg else None,
        "effective_top_k": (rag_cfg.top_k if rag_cfg and rag_cfg.top_k else conf.default_top_k()),
        "effective_min_relevance_threshold": (
            rag_cfg.min_relevance_threshold if rag_cfg and rag_cfg.min_relevance_threshold is not None
            else conf.min_relevance_threshold()
        ),
        "knowledge_base": (
            {
                "id": str(assignment.knowledge_base.pk) if assignment else "",
                "name": assignment.knowledge_base.name if assignment else f"Global Dynamic ({len(resolution.kbs)} Ready KB)",
                "assignment_id": str(assignment.pk) if assignment else None,
                "is_global_dynamic": assignment is None,
                "readiness": (
                    kbs.kb_readiness(assignment.knowledge_base)
                    if assignment
                    else {
                        "is_active": True,
                        "ready_documents": sum(kbs.ready_documents(k).count() for k in resolution.kbs),
                        "total_documents": sum(k.documents.exclude(status="DELETING").count() for k in resolution.kbs),
                        "is_ready": has_ready_kb,
                    }
                ),
            }
            if kb else None
        ),
    }
