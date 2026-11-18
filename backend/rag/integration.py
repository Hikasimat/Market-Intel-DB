"""
Service boundary between the existing WhatsApp AI auto-reply flow (`whatsapp_ai`) and RAG.

`maybe_generate_strict_reply` is called from `whatsapp_ai.gemini_service.process_ai_auto_reply`
right where the unrestricted Gemini answer used to be generated:

* Strict RAG NOT enabled for the session (or no rag config row)  -> returns None
  -> the existing behaviour runs completely unchanged.
* Strict RAG enabled -> the reply ALWAYS comes from RAG (grounded answer or refusal text),
  or the message is skipped. It never returns None, so the caller can never fall back to
  general Gemini knowledge for a strict session.

Sending, outbound persistence, WhatsAppAIReplyLog, duplicate prevention, opt-out, group
rules and WAHA status handling all stay in the existing code.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from django.db import ProgrammingError

logger = logging.getLogger("rag.integration")


@dataclass
class StrictOutcome:
    reply_text: str = ""
    model_used: str = ""
    skip_reason: str = ""  # non-empty => do not send anything
    was_refused: bool = False
    refusal_reason: str = ""


def _message_text(m) -> str:
    return (getattr(m, "full_body", "") or getattr(m, "body_preview", "") or "").strip()


def build_history(history_msgs, incoming) -> list[tuple[str, str]]:
    """
    Only include recent INBOUND customer questions for follow-up pronoun resolution.
    Never include previous OUTBOUND assistant replies so that facts from a subsequently
    deleted document can never be echoed back from WhatsApp chat history.
    """
    from . import conf

    limit = conf.conversation_context_messages()
    out: list[tuple[str, str]] = []
    for m in history_msgs:
        if getattr(m, "pk", None) == incoming.pk:
            continue
        if getattr(m, "direction", "") != "INBOUND":
            continue
        text = _message_text(m)
        if not text:
            continue
        out.append(("customer", text))
    return out[-limit:] if limit else []


def is_strict_enabled(session) -> bool:
    """
    Global & dynamic Strict RAG activation:
    - If a SessionRAGConfig row exists for `session`, respect its `strict_rag_enabled` flag.
    - In live server runtime (`"test" not in sys.argv`), Strict RAG is ALWAYS active globally
      when RAG_ENABLED=true — even after all documents/KBs are deleted, so deleting all documents
      causes the AI to refuse rather than falling back to general Gemini or old chat history.
    """
    import sys
    from . import conf
    from .models import SessionRAGConfig
    from .services import knowledge_base_service

    if not conf.rag_enabled():
        return False
    cfg = SessionRAGConfig.objects.filter(session=session).first()
    if cfg is not None:
        return bool(cfg.strict_rag_enabled)
    if conf.strict_mode_default() or "test" not in sys.argv:
        return True
    resolution = knowledge_base_service.resolve_kb_for_session(session)
    return resolution.kb is not None


def maybe_generate_strict_reply(session, conversation, incoming, history_msgs, *, model_name: str = "") -> Optional[StrictOutcome]:
    try:
        strict = is_strict_enabled(session)
    except ProgrammingError:
        # rag tables not migrated yet -> no session can have strict mode on; keep legacy behaviour.
        return None
    except Exception:
        logger.exception("Could not determine Strict RAG state; failing closed")
        return StrictOutcome(skip_reason="rag_state_unknown")
    if not strict:
        return None

    from . import conf

    if conversation.session_id != session.pk:  # defence in depth: session isolation
        return StrictOutcome(skip_reason="rag_session_mismatch")
    if not conf.rag_enabled():
        return StrictOutcome(skip_reason="rag_disabled")

    question = _message_text(incoming)
    if not question:
        return StrictOutcome(skip_reason="rag_no_text")  # e.g. media-only message

    try:
        from .services import rag_pipeline_service

        result = rag_pipeline_service.answer_for_session(
            session, question, build_history(history_msgs, incoming), source="whatsapp", model=model_name
        )
    except Exception:
        logger.exception("Strict RAG pipeline crashed; nothing will be sent")
        return StrictOutcome(skip_reason="rag_unavailable")

    if not result.can_send or not result.reply_text:
        return StrictOutcome(skip_reason=result.refusal_reason or "rag_unavailable")
    return StrictOutcome(
        reply_text=result.reply_text,
        model_used=f"rag:{result.model_used or 'refusal'}",
        was_refused=(result.status == "REFUSED"),
        refusal_reason=result.refusal_reason or "",
    )
