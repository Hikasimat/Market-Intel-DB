"""
Strict-RAG orchestration.

question -> guardrail pre-check -> KB resolution (tenant-checked) -> understand ->
embed -> tenant-filtered retrieval -> relevance gate -> grounded Gemini JSON ->
independent validation (retry once, stricter) -> answer | fixed refusal.

There is NO general-knowledge fallback anywhere in this module. Content problems
produce the (admin-configurable) refusal text; infrastructure problems produce
status=ERROR and `can_send=False` so nothing unsupported can ever be sent.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from .. import conf
from .. import constants as C
from ..exceptions import AuthorizationError, EmbeddingError, RAGError, RAGInfrastructureError
from ..models import KnowledgeBase, RAGQueryLog, SessionRAGConfig
from . import (
    answer_generation_service,
    answer_validation_service,
    context_builder_service,
    guardrails_service,
    knowledge_base_service,
    query_understanding_service,
    retrieval_service,
)

logger = logging.getLogger("rag.pipeline")


@dataclass
class RAGResult:
    status: str  # ANSWERED | REFUSED | ERROR
    reply_text: str = ""  # text to send (answer or refusal); empty on ERROR
    can_send: bool = False
    refusal_reason: str = ""
    model_used: str = ""
    knowledge_base_id: Optional[str] = None
    retrieval_status: str = ""
    sources: list[dict] = field(default_factory=list)
    retrieved: list[dict] = field(default_factory=list)  # for the admin test UI / evaluation
    processing_ms: int = 0
    log_id: Optional[str] = None
    detail: str = ""


def _refusal_text(cfg: Optional[SessionRAGConfig]) -> str:
    return cfg.effective_refusal_message() if cfg else conf.refusal_message()


def _chunk_view(c, *, include_text: bool) -> dict:
    d = {
        "chunk_id": c.chunk_id,
        "document_id": c.document_id,
        "document_name": c.document_name,
        "page_number": c.page_number,
        "sheet_name": c.sheet_name,
        "section_heading": c.section_heading,
        "similarity": round(c.similarity, 4),
    }
    if include_text:
        d["text"] = c.text[:1200]
    return d


def _log(session, kb, source, question, result: RAGResult, chunks) -> None:
    try:
        log = RAGQueryLog.objects.create(
            session=session,
            knowledge_base=kb,
            source=source,
            question=(question or "")[:500],
            retrieval_status=result.retrieval_status,
            retrieved_chunk_ids=[c.chunk_id for c in chunks],
            similarity_scores=[round(c.similarity, 4) for c in chunks],
            source_document_ids=sorted({c.document_id for c in chunks}),
            model_used=result.model_used[:128],
            answer_status=result.status,
            refusal_reason=result.refusal_reason[:64],
            processing_ms=result.processing_ms,
        )
        result.log_id = str(log.pk)
    except Exception:
        logger.exception("Could not write RAGQueryLog")


def _refuse(reason: str, cfg, **kw) -> RAGResult:
    return RAGResult(status="REFUSED", reply_text=_refusal_text(cfg), can_send=True, refusal_reason=reason, **kw)


def answer_for_session(
    session,
    question: str,
    history: list[tuple[str, str]] | None = None,
    *,
    source: str = "whatsapp",
    include_chunk_text: bool = False,
    model: str = "",
) -> RAGResult:
    """Entry point for WhatsApp (and the admin test interface when a session is chosen)."""
    cfg = knowledge_base_service.get_session_rag_config(session)
    resolution = knowledge_base_service.resolve_kb_for_session(session)
    return _run(
        resolution.kbs or resolution.kb,
        resolution.reason,
        question,
        history or [],
        cfg=cfg,
        session=session,
        user=None,
        source=source,
        include_chunk_text=include_chunk_text,
        model=model,
        kb_for_log=resolution.kb,
    )


def answer_for_kb(
    kb: KnowledgeBase, user, question: str, history=None, *, include_chunk_text: bool = True, model: str = ""
) -> RAGResult:
    """Admin test interface (user already authenticated; authorisation re-checked inside retrieval)."""
    reason = ""
    if not kb.is_active:
        reason = C.REASON_KB_INACTIVE
    elif not knowledge_base_service.ready_documents(kb).exists():
        reason = C.REASON_NO_READY_DOCS
    return _run(
        None if reason else kb, reason, question, history or [], cfg=None, session=None, user=user,
        source="test", include_chunk_text=include_chunk_text, model=model, kb_for_log=kb,
    )


def _run(kb, kb_reason, question, history, *, cfg, session, user, source, include_chunk_text, model, kb_for_log=None) -> RAGResult:
    started = time.monotonic()
    chunks_for_log: list = []
    primary_kb = kb_for_log or (kb[0] if isinstance(kb, list) and kb else (kb if not isinstance(kb, list) else None))

    def finish(res: RAGResult) -> RAGResult:
        res.processing_ms = int((time.monotonic() - started) * 1000)
        res.knowledge_base_id = str(primary_kb.pk) if primary_kb else None
        _log(session, primary_kb, source, question, res, chunks_for_log)
        return res

    plan = query_understanding_service.understand(
        question, [t for role, t in history if role == "customer"][-2:]
    )
    if not plan.normalized:
        return finish(_refuse(C.REASON_EMPTY_QUESTION, cfg))
    if not kb:
        return finish(_refuse(kb_reason or C.REASON_NO_KB, cfg))
    if guardrails_service.question_injection_suspected(plan.normalized):
        return finish(_refuse(C.REASON_INJECTION_QUESTION, cfg))

    top_k = (cfg.top_k if cfg and cfg.top_k else None) or conf.default_top_k()
    threshold = cfg.min_relevance_threshold if (cfg and cfg.min_relevance_threshold is not None) else conf.min_relevance_threshold()

    try:
        retrieval = retrieval_service.retrieve(
            kb, query_text=plan.retrieval_query, session=session, user=user, top_k=top_k, threshold=threshold
        )
    except AuthorizationError:
        logger.error("RAG authorization failure kb=%s", getattr(primary_kb, "pk", None))
        return finish(_refuse(C.REASON_TENANT_MISMATCH, cfg))
    except (EmbeddingError, RAGError, Exception) as exc:  # noqa: BLE001 - never fall back to general knowledge
        logger.error("RAG retrieval unavailable (%s)", type(exc).__name__)
        return finish(RAGResult(status="ERROR", refusal_reason=C.REASON_INFRA, retrieval_status="error", detail=type(exc).__name__))

    chunks_for_log = retrieval.chunks or retrieval.candidates[:top_k]
    retrieved_view = [_chunk_view(c, include_text=include_chunk_text) for c in (retrieval.chunks or retrieval.candidates[:top_k])]
    if retrieval.status != "ok":
        reason = C.REASON_NO_RETRIEVAL if retrieval.status == "no_results" else C.REASON_LOW_RELEVANCE
        return finish(_refuse(reason, cfg, retrieval_status=retrieval.status, retrieved=retrieved_view))

    context = context_builder_service.build_context(retrieval.chunks)
    chunks_for_log = context.included

    try:
        validation, model_used = _generate_and_validate(plan.normalized, history, context, model)
    except RAGInfrastructureError as exc:
        logger.error("RAG generation unavailable: %s", exc)
        return finish(RAGResult(status="ERROR", refusal_reason=C.REASON_INFRA, retrieval_status="ok", retrieved=retrieved_view, detail="generation_unavailable"))

    if validation is None or not validation.ok:
        code = validation.reason if validation else "unknown"
        return finish(
            _refuse(C.REASON_VALIDATION_FAILED, cfg, retrieval_status="ok", retrieved=retrieved_view, model_used=model_used, detail=code)
        )
    if not validation.can_answer:
        return finish(
            _refuse(C.REASON_MODEL_REFUSED, cfg, retrieval_status="ok", retrieved=retrieved_view, model_used=model_used, detail=validation.reason)
        )

    by_id = {c.chunk_id: c for c in context.included}
    sources = [_chunk_view(by_id[i], include_text=False) for i in validation.source_ids if i in by_id]
    chunks_for_log = [by_id[i] for i in validation.source_ids if i in by_id] or context.included
    return finish(
        RAGResult(
            status="ANSWERED", reply_text=validation.answer, can_send=True, model_used=model_used,
            retrieval_status="ok", sources=sources, retrieved=retrieved_view,
        )
    )


def _generate_and_validate(question, history, context, model):
    """Generate; if validation fails retry ONCE with stricter instructions; else give up (-> refusal)."""
    model_used = model
    last = None
    for stricter in (False, True):
        gen = answer_generation_service.generate_answer(question, history, context, model=model, stricter=stricter)
        model_used = gen.model_used
        last = answer_validation_service.validate(gen.data, context, model=model)
        if last.ok:
            return last, model_used
        logger.info("RAG answer rejected (%s)%s", last.reason, " - retrying stricter" if not stricter else "")
    return last, model_used
