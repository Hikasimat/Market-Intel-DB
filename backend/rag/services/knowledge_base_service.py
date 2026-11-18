"""Knowledge-base authorization, resolution (session -> KB), readiness, statistics and safe deletion."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from django.db.models import Count, Q, Sum

from .. import constants as C
from ..models import (
    KnowledgeBase,
    KnowledgeBaseSessionAssignment,
    KnowledgeDocument,
    KnowledgeDocumentChunk,
    SessionRAGConfig,
)
from . import storage_service

audit = logging.getLogger("rag.audit")


# ── user / tenant helpers ────────────────────────────────────────────────────
def _profile(user):
    return getattr(user, "profile", None)


def user_role(user) -> str:
    if getattr(user, "is_superuser", False):
        return "SUPERADMIN"
    p = _profile(user)
    return (p.role if p else "") or ""


def user_company_id(user):
    p = _profile(user)
    return getattr(p, "company_id", None) if p else None


def can_use_rag(user) -> bool:
    return bool(user and user.is_authenticated and user_role(user) in ("SUPERADMIN", "PRE", "LQ", "MANAGER"))


def can_ingest_documents(user) -> bool:
    """Strictly only Super Admin (is_superuser) may upload/ingest, retry, or delete documents."""
    return bool(user and getattr(user, "is_authenticated", False) and getattr(user, "is_superuser", False))


def can_configure_retrieval(user) -> bool:
    return user_role(user) in ("SUPERADMIN", "MANAGER")


def accessible_knowledge_bases(user):
    """KBs the user may see: own KBs + company KBs + Super-Admin shared KBs (when un-tenanted) + assigned KBs."""
    if user.is_superuser:
        return KnowledgeBase.objects.all()
    q = Q(owner=user) | Q(session_assignments__session__owner=user, session_assignments__is_active=True)
    cid = user_company_id(user)
    if cid:
        q |= Q(company_id=cid)
    else:
        q |= Q(owner__is_superuser=True, company__isnull=True)
    return KnowledgeBase.objects.filter(q).distinct()


def can_write_kb(user, kb: KnowledgeBase) -> bool:
    return can_ingest_documents(user)


def tenant_compatible(session_owner, kb: KnowledgeBase) -> bool:
    """A session may only use KBs of ITS OWNER's tenant (or a shared Super-Admin KB in the same/global scope)."""
    if session_owner is None:
        return False
    owner_cid = user_company_id(session_owner)
    if kb.owner_id == session_owner.id and not kb.company_id:
        return True
    if kb.owner_id == session_owner.id and kb.company_id and kb.company_id == owner_cid:
        return True
    if getattr(kb.owner, "is_superuser", False) and (kb.company_id is None or kb.company_id == owner_cid):
        return True
    return bool(kb.company_id and kb.company_id == owner_cid)


def can_manage_session(user, session) -> bool:
    return bool(user.is_superuser or (session.owner_id == user.id))


def can_assign(user, session, kb: KnowledgeBase) -> tuple[bool, str]:
    if not can_manage_session(user, session):
        return False, "You do not own this WhatsApp session."
    if not accessible_knowledge_bases(user).filter(pk=kb.pk).exists():
        return False, "Knowledge base not found."
    if not tenant_compatible(session.owner, kb):
        return False, "This knowledge base does not belong to the session owner's tenant."
    return True, ""


# ── readiness / resolution ───────────────────────────────────────────────────
def ready_documents(kb: KnowledgeBase):
    return kb.documents.filter(status=C.STATUS_READY, is_active=True, total_chunks__gt=0)


def kb_readiness(kb: KnowledgeBase) -> dict:
    ready = ready_documents(kb).count()
    total = kb.documents.exclude(status=C.STATUS_DELETING).count()
    return {
        "is_active": kb.is_active,
        "ready_documents": ready,
        "total_documents": total,
        "is_ready": bool(kb.is_active and ready > 0),
    }


@dataclass
class KBResolution:
    kb: Optional[KnowledgeBase] = None
    kbs: list[KnowledgeBase] = None  # all active READY KBs dynamically resolved for retrieval
    reason: str = ""  # refusal reason code when kb is None

    def __post_init__(self):
        if self.kbs is None:
            self.kbs = [self.kb] if self.kb is not None else []


def get_session_rag_config(session) -> Optional[SessionRAGConfig]:
    return SessionRAGConfig.objects.filter(session=session).first()


def resolve_kb_for_session(session) -> KBResolution:
    """
    Dynamic & global resolution:
    1. If the session has an explicit active KnowledgeBaseSessionAssignment, validate tenant
       compatibility, active status, and READY documents for that specific KB.
    2. Otherwise (Global Dynamic Mode), dynamically resolve ALL active, tenant-authorized
       KnowledgeBases (including all global KBs ingested by Super Admin) that currently have
       at least one READY document. Zero hardcoded session or KB names/IDs are used.
    """
    assignment = (
        KnowledgeBaseSessionAssignment.objects.select_related("knowledge_base", "knowledge_base__owner", "session__owner")
        .filter(session=session, is_active=True)
        .first()
    )
    if assignment is not None:
        kb = assignment.knowledge_base
        if not kb.is_active:
            return KBResolution(reason=C.REASON_KB_INACTIVE)
        if not tenant_compatible(session.owner, kb):
            audit.error("tenant_mismatch session=%s kb=%s", session.pk, kb.pk)
            return KBResolution(reason=C.REASON_TENANT_MISMATCH)
        if not ready_documents(kb).exists():
            return KBResolution(reason=C.REASON_NO_READY_DOCS)
        return KBResolution(kb=kb, kbs=[kb])

    # Global Dynamic Mode: find all active, tenant-compatible KBs with READY documents
    owner = getattr(session, "owner", None)
    if owner is not None:
        candidates = list(accessible_knowledge_bases(owner).filter(is_active=True).select_related("owner").order_by("-updated_at"))
        compatible = [k for k in candidates if tenant_compatible(owner, k)]
    else:
        compatible = list(
            KnowledgeBase.objects.filter(is_active=True, owner__is_superuser=True, company__isnull=True)
            .select_related("owner")
            .order_by("-updated_at")
        )

    if not compatible:
        return KBResolution(reason=C.REASON_NO_KB)

    ready_kbs = [k for k in compatible if ready_documents(k).exists()]
    if not ready_kbs:
        return KBResolution(reason=C.REASON_NO_READY_DOCS)

    return KBResolution(kb=ready_kbs[0], kbs=ready_kbs)


def session_has_ready_kb(session) -> bool:
    return resolve_kb_for_session(session).kb is not None


# ── statistics ───────────────────────────────────────────────────────────────
def statistics(kb: KnowledgeBase) -> dict:
    docs = kb.documents.all()
    by_status = {row["status"]: row["n"] for row in docs.values("status").annotate(n=Count("id"))}
    agg = docs.aggregate(size=Sum("file_size"), chunks=Sum("total_chunks"))
    return {
        "documents_total": docs.count(),
        "documents_by_status": by_status,
        "total_size_bytes": agg["size"] or 0,
        "total_chunks": KnowledgeDocumentChunk.objects.filter(knowledge_base=kb).count(),
        "assigned_sessions": kb.session_assignments.filter(is_active=True).count(),
        "readiness": kb_readiness(kb),
    }


# ── safe deletion ────────────────────────────────────────────────────────────
def delete_document(document: KnowledgeDocument, *, actor=None) -> None:
    """
    1. mark DELETING (immediately excluded from retrieval),
    2. remove all vector chunks for this document from PostgreSQL + pgvector,
    3. remove the stored original file,
    4. remove the document record (and any orphaned chunks).
    """
    doc_id, kb_id = document.pk, document.knowledge_base_id
    KnowledgeDocument.objects.filter(pk=doc_id).update(status=C.STATUS_DELETING, is_active=False)
    try:
        KnowledgeDocumentChunk.objects.filter(document_id=doc_id).delete()
        storage_service.delete(document.storage_key)
    except Exception as exc:
        KnowledgeDocument.objects.filter(pk=doc_id).update(processing_error=f"Deletion incomplete: {type(exc).__name__}")
        audit.error("document_delete_failed doc=%s kb=%s actor=%s err=%s", doc_id, kb_id, getattr(actor, "pk", None), type(exc).__name__)
        raise
    KnowledgeDocument.objects.filter(pk=doc_id).delete()
    KnowledgeDocumentChunk.objects.filter(document__isnull=True).delete()
    audit.info("document_deleted doc=%s kb=%s actor=%s", doc_id, kb_id, getattr(actor, "pk", None))


def delete_knowledge_base(kb: KnowledgeBase, *, actor=None) -> None:
    kb_id = kb.pk
    KnowledgeBase.objects.filter(pk=kb_id).update(is_active=False)
    KnowledgeDocumentChunk.objects.filter(knowledge_base_id=kb_id).delete()
    for doc in list(kb.documents.all()):
        delete_document(doc, actor=actor)
    KnowledgeBaseSessionAssignment.objects.filter(knowledge_base_id=kb_id).delete()
    kb.delete()
    KnowledgeDocumentChunk.objects.filter(knowledge_base__isnull=True).delete()
    audit.info("knowledge_base_deleted kb=%s actor=%s", kb_id, getattr(actor, "pk", None))
