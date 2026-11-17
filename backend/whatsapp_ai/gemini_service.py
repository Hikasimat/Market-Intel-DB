"""
Gemini AI auto-reply engine for WhatsApp messaging (`whatsapp_ai` Django app).

Workflow on every live incoming WhatsApp message (works whether or not the
Market Intel user is logged in, as long as their WhatsAppSession is connected):
1. Identify the sender via their normalized mobile number, WhatsApp JID, and CRM link.
2. Retrieve synchronized chronological chat history for that sender within the
   same connected WhatsAppSession from the Market Intel database.
3. Call Google Gemini API with sender context + history + latest message to
   generate a contextual reply.
4. Send the reply via WAHA through the exact same connected WhatsAppSession and
   persist the outbound WhatsAppMessage in the database so conversation history
   stays synchronized for subsequent turns.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import timedelta
from typing import Any, Optional

from django.conf import settings
from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from django.db.models import F, Q
from django.utils import timezone

logger = logging.getLogger(__name__)


def _get_setting(name: str, default: str = "") -> str:
    val = getattr(settings, name, None)
    if val is None or val == "":
        val = os.environ.get(name, default)
    return str(val or default).strip()


def _is_auto_reply_globally_enabled() -> bool:
    running_tests = "test" in sys.argv
    raw = os.environ.get("WHATSAPP_AI_AUTO_REPLY_ENABLED")
    if raw is None or raw == "":
        raw = getattr(settings, "WHATSAPP_AI_AUTO_REPLY_ENABLED", None)
    if raw is None or raw == "":
        # Enabled automatically in live server runtime; opt-in during test suites so
        # unrelated webhook unit tests are never altered by outbound Gemini/WAHA calls.
        return not running_tests
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _get_fresh_sync_window_seconds() -> int:
    try:
        val = int(_get_setting("WHATSAPP_AI_FRESH_SYNC_WINDOW_SECONDS", "300") or "300")
        return max(30, min(val, 1800))
    except (TypeError, ValueError):
        return 300


def _is_fresh_inbound_for_auto_reply(message, session=None) -> bool:
    """
    Determine whether an inbound WhatsAppMessage discovered via history/stats sync
    is a newly arrived real-time message (rather than old backfill history) and is
    eligible for automatic reply (or transient retry).
    """
    from whatsapp.models import WhatsAppMessage, WhatsAppSession
    from .models import WhatsAppAIReplyLog

    if message is None or getattr(message, "direction", None) != WhatsAppMessage.Direction.INBOUND:
        return False

    conversation = getattr(message, "conversation", None)
    sess = session or (conversation.session if conversation else None)
    if not sess or not conversation:
        return False
    if not sess.is_active or sess.status != WhatsAppSession.Status.READY:
        return False

    existing_log = (
        WhatsAppAIReplyLog.objects
        .filter(incoming_message_id=message.pk)
        .values("status", "updated_at")
        .first()
    )
    if existing_log:
        st = existing_log["status"]
        if st in (WhatsAppAIReplyLog.Status.SENT, WhatsAppAIReplyLog.Status.SKIPPED):
            return False
        updated_at = existing_log.get("updated_at")
        now = timezone.now()
        if st == WhatsAppAIReplyLog.Status.PENDING and updated_at and updated_at > now - timedelta(seconds=20):
            return False
        if st == WhatsAppAIReplyLog.Status.FAILED and updated_at and updated_at > now - timedelta(seconds=5):
            return False
        retry_key = f"whatsapp_ai_retry:{message.pk}"
        retries = int(cache.get(retry_key) or 0)
        if retries >= 3:
            return False

    # Only treat freshly received messages within the real-time sync window as live
    msg_ts = getattr(message, "sent_at", None) or getattr(message, "waha_timestamp", None) or getattr(message, "created_at", None)
    if msg_ts is None:
        return False
    cutoff = timezone.now() - timedelta(seconds=_get_fresh_sync_window_seconds())
    if msg_ts < cutoff:
        return False

    # If a human or AI already replied in this conversation after this message, do not auto-reply
    has_newer_reply = WhatsAppMessage.objects.filter(
        conversation_id=conversation.pk,
        direction=WhatsAppMessage.Direction.OUTBOUND,
        sent_at__gte=msg_ts,
    ).exists()
    return not has_newer_reply


def _get_or_create_ai_config(session):
    from .models import WhatsAppAIAutoReplyConfig

    cfg, _ = WhatsAppAIAutoReplyConfig.objects.get_or_create(
        session=session,
        defaults={
            "enabled": True,
            "reply_to_groups": False,
            "max_history_messages": 20,
            "model_name": _get_setting("WHATSAPP_AI_MODEL", ""),
        },
    )
    return cfg


def _extract_sender_identity(conversation, session) -> dict[str, str]:
    """Identify the sender using phone number, WhatsApp JID, name, and CRM details."""
    from whatsapp.services import normalize_phone_digits, normalize_phone_number

    chat_id = str(conversation.chat_id or "").strip()
    digits = normalize_phone_digits(conversation.phone_number or "") or normalize_phone_digits(chat_id)
    phone = normalize_phone_number(conversation.phone_number or "") or (f"+{digits}" if digits else "")
    contact = getattr(conversation, "prospect_contact", None)
    prospect = getattr(conversation, "prospect", None) or (getattr(contact, "prospect", None) if contact else None)

    display_name = (
        (contact.contact_name if contact else "")
        or (conversation.whatsapp_name or "")
        or phone
        or chat_id
        or "WhatsApp User"
    )
    return {
        "sender_id": chat_id,
        "phone_digits": digits,
        "phone_number": phone,
        "display_name": display_name,
        "company_name": prospect.company_name if prospect else "",
        "designation": getattr(contact, "designation", "") if contact else "",
        "account_phone": session.phone_number or "",
        "account_owner": (session.owner.get_full_name() or session.owner.username) if session.owner else "Market Intel",
    }


def retrieve_synchronized_chat_history(conversation, session, limit: int = 20) -> list:
    """
    Retrieve chronological conversation messages associated with the sender's
    mobile number or WhatsApp JID strictly scoped to `session`.
    """
    from whatsapp.models import WhatsAppConversation, WhatsAppMessage
    from whatsapp.services import normalize_phone_digits

    chat_id = str(conversation.chat_id or "").strip()
    is_group = chat_id.endswith("@g.us")
    conv_ids = {conversation.pk}

    if not is_group:
        conv_q = Q(pk=conversation.pk)
        cand_jids = [chat_id] if chat_id else []
        if chat_id.endswith("@c.us"):
            cand_jids.append(chat_id.replace("@c.us", "@s.whatsapp.net"))
        elif chat_id.endswith("@s.whatsapp.net"):
            cand_jids.append(chat_id.replace("@s.whatsapp.net", "@c.us"))
        if cand_jids:
            conv_q |= Q(chat_id__in=cand_jids)

        digits = normalize_phone_digits(conversation.phone_number or "") or normalize_phone_digits(chat_id)
        if digits and len(digits) >= 8:
            suffix = digits[-10:] if len(digits) >= 10 else digits[-8:]
            conv_q |= Q(phone_number__endswith=suffix) | Q(chat_id__startswith=digits)

        matching_ids = (
            WhatsAppConversation.objects
            .filter(session=session, is_deleted=False)
            .filter(conv_q)
            .values_list("pk", flat=True)
        )
        conv_ids.update(matching_ids)

    msgs = list(
        WhatsAppMessage.objects
        .filter(conversation_id__in=list(conv_ids), conversation__session=session)
        .exclude(status__in=[WhatsAppMessage.Status.FAILED, WhatsAppMessage.Status.BLOCKED])
        .order_by("-waha_timestamp", "-sent_at", "-created_at", "-id")[: max(1, int(limit or 20))]
    )
    msgs.reverse()
    return msgs


def _build_gemini_reply_prompt(sender_info: dict, history_msgs: list, incoming_message, custom_instructions: str = "") -> str:
    history_lines = []
    for m in history_msgs:
        ts = (m.waha_timestamp or m.sent_at or m.created_at)
        ts_str = ts.isoformat() if ts else "unknown-time"
        speaker = sender_info["display_name"] if m.direction == "INBOUND" else sender_info["account_owner"]
        text = (m.full_body or m.body_preview or "").strip()
        if not text and m.has_media:
            text = f"[{m.message_type or 'media'} attachment]"
        marker = " <-- LATEST INCOMING MESSAGE" if m.pk == incoming_message.pk else ""
        history_lines.append(f"[{ts_str}] {m.direction} ({speaker}): {text[:1200]}{marker}")

    incoming_text = (incoming_message.full_body or incoming_message.body_preview or "").strip()
    if not incoming_text and incoming_message.has_media:
        incoming_text = f"[{incoming_message.message_type or 'media'} attachment]"

    crm_parts = []
    if sender_info.get("company_name"):
        crm_parts.append(f"Company: {sender_info['company_name']}")
    if sender_info.get("designation"):
        crm_parts.append(f"Role: {sender_info['designation']}")
    crm_line = f"CRM Profile: {', '.join(crm_parts)}\n" if crm_parts else ""

    extra_rule = f"\nAdditional Instructions:\n{custom_instructions.strip()}\n" if custom_instructions.strip() else ""

    return (
        "You are an AI WhatsApp assistant replying on behalf of a Market Intel user whose WhatsApp account is connected.\n"
        "RULES:\n"
        "1. Read the full conversation history and the latest incoming WhatsApp message carefully.\n"
        "2. Write a helpful, polite, concise, natural WhatsApp reply directly addressing the sender's message and context.\n"
        "3. Do NOT fabricate pricing, confidential facts, or confirmed appointments that were not agreed in the history.\n"
        "4. Return strictly valid JSON with a single key \"reply\" containing only the message text to send.\n"
        f"{extra_rule}\n"
        f"Connected Account Owner: {sender_info['account_owner']} ({sender_info['account_phone'] or 'WhatsApp'})\n"
        f"Sender Name: {sender_info['display_name']}\n"
        f"Sender Mobile: {sender_info['phone_number'] or 'Unknown'}\n"
        f"Sender WhatsApp ID: {sender_info['sender_id']}\n"
        f"{crm_line}\n"
        "Synchronized Chat History (oldest to newest):\n"
        + ("\n".join(history_lines) if history_lines else "(No prior messages)")
        + f"\n\nLatest Incoming Message to Reply To:\n{incoming_text}\n"
    )


def _discover_gemini_models(api_key: str, timeout: int) -> list[str]:
    cached = cache.get("whatsapp_ai_gemini_models")
    if isinstance(cached, list) and cached:
        return cached

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    discovered = []
    for item in (data.get("models") or []):
        name = str(item.get("name") or "").replace("models/", "").strip()
        methods = item.get("supportedGenerationMethods") or []
        if not name or "generateContent" not in methods:
            continue
        low = name.lower()
        if "gemini" not in low or any(bad in low for bad in ("pro", "ultra", "embedding", "imagen", "veo", "tts", "audio")):
            continue
        discovered.append(name)

    def _rank(name: str):
        low = name.lower()
        return (
            0 if "flash" in low else 1,
            0 if "lite" in low else 1,
            0 if "latest" in low else 1,
            name,
        )

    discovered.sort(key=_rank)
    if discovered:
        cache.set("whatsapp_ai_gemini_models", discovered[:8], 3600)
    return discovered[:8]


def _parse_gemini_reply_json(raw_text: str) -> str:
    text = (raw_text or "").strip()
    if not text:
        return ""
    fence = re.search(r"\{.*\}", text, re.DOTALL)
    if fence:
        try:
            obj = json.loads(fence.group(0))
            val = str(obj.get("reply") or obj.get("response") or obj.get("message") or "").strip()
            if val:
                return val[:2000]
        except Exception:
            pass
    # Clean accidental code fences if plain text returned
    cleaned = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    return cleaned[:2000]


def generate_gemini_whatsapp_reply(prompt: str, *, model: str = "", timeout: int = 15) -> tuple[str, str]:
    """Call Google Gemini REST API and return (reply_text, model_used)."""
    api_key = _get_setting("GEMINI_API_KEY", "")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not configured.")

    cached_winner = cache.get("whatsapp_ai_working_gemini_model")
    explicit_model = "" if (not model or model == "gemini-3.8-flash") else model
    discovered_models: list[str] = []
    if not cached_winner and not explicit_model and "test" not in sys.argv:
        try:
            discovered_models = _discover_gemini_models(api_key, min(timeout, 8))
        except Exception:
            discovered_models = []

    candidates = []
    for cand in [
        cached_winner,
        explicit_model,
        _get_setting("WHATSAPP_AI_MODEL", ""),
        _get_setting("EMAIL_SUMMARY_MODEL", ""),
        *discovered_models,
        "gemini-2.5-flash",
        "gemini-flash-lite-latest",
        "gemini-2.5-flash-lite",
        "gemini-flash-latest",
        "gemini-2.0-flash-lite",
    ]:
        if cand and cand != "gemini-3.8-flash" and cand not in candidates:
            candidates.append(cand)

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 600,
            "responseMimeType": "application/json",
        },
    }).encode("utf-8")

    def _invoke(cand_model: str) -> tuple[str, str]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{cand_model}:generateContent?key={api_key}"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        cands = data.get("candidates") or []
        parts = (((cands[0] if cands else {}).get("content") or {}).get("parts") or [])
        raw = "".join(str(p.get("text") or "") for p in parts)
        reply = _parse_gemini_reply_json(raw)
        if not reply:
            raise ValueError(f"Gemini ({cand_model}) returned an empty WhatsApp reply.")
        cache.set("whatsapp_ai_working_gemini_model", cand_model, 3600)
        return reply, cand_model

    last_err = None
    saw_404 = False
    for idx, cand_model in enumerate(candidates):
        try:
            return _invoke(cand_model)
        except urllib.error.HTTPError as http_err:
            body_err = ""
            try:
                body_err = http_err.read().decode("utf-8", errors="ignore")[:350]
            except Exception:
                pass
            last_err = f"HTTP {http_err.code} on {cand_model}: {body_err or http_err.reason}"
            if http_err.code == 404:
                saw_404 = True
            if http_err.code in (400, 404, 429) and idx + 1 < len(candidates):
                continue
        except Exception as exc:
            last_err = f"{cand_model}: {exc}"
            if idx + 1 < len(candidates):
                continue
            raise

    if saw_404:
        try:
            for disc in _discover_gemini_models(api_key, timeout):
                if disc in candidates:
                    continue
                try:
                    return _invoke(disc)
                except Exception as exc:
                    last_err = f"{disc}: {exc}"
                    continue
        except Exception:
            pass

    raise ValueError(last_err or "Gemini WhatsApp reply generation failed.")


def process_ai_auto_reply(incoming_message_id) -> Optional[dict[str, Any]]:
    """
    End-to-end Gemini auto-reply execution for a persisted inbound WhatsAppMessage.
    Executes cleanly with zero dependency on an active web/JWT user session so it
    continues functioning 24/7 even when the WhatsApp owner is logged out of Market Intel.
    """
    from whatsapp.client import WAHAServiceError, get_waha_client
    from whatsapp.models import (
        WhatsAppAuditLog,
        WhatsAppConversation,
        WhatsAppMessage,
        WhatsAppOptOut,
        WhatsAppSession,
    )
    from whatsapp.services import _get_config, _write_audit_log
    from .models import WhatsAppAIReplyLog

    if not _is_auto_reply_globally_enabled():
        return {"status": "SKIPPED", "reason": "global_disabled"}

    incoming = (
        WhatsAppMessage.objects
        .select_related(
            "conversation",
            "conversation__session",
            "conversation__session__owner",
            "conversation__prospect_contact",
            "conversation__prospect",
        )
        .filter(pk=incoming_message_id)
        .first()
    )
    if not incoming or incoming.direction != WhatsAppMessage.Direction.INBOUND:
        return None

    conversation = incoming.conversation
    session = conversation.session if conversation else None
    if not conversation or not session:
        return None

    # Idempotency: ensure each incoming message receives at most one AI reply log
    try:
        log_entry, created = WhatsAppAIReplyLog.objects.get_or_create(
            incoming_message=incoming,
            defaults={
                "session": session,
                "conversation": conversation,
                "sender_identifier": conversation.phone_number or conversation.chat_id,
                "status": WhatsAppAIReplyLog.Status.PENDING,
            },
        )
    except IntegrityError:
        return {"status": "SKIPPED", "reason": "already_claimed"}

    if not created:
        if log_entry.status in (
            WhatsAppAIReplyLog.Status.SENT,
            WhatsAppAIReplyLog.Status.SKIPPED,
        ):
            return {"status": log_entry.status, "reason": "already_processed"}
        if log_entry.status == WhatsAppAIReplyLog.Status.PENDING:
            if log_entry.updated_at and log_entry.updated_at > timezone.now() - timedelta(seconds=20):
                return {"status": log_entry.status, "reason": "already_processed"}
        retry_key = f"whatsapp_ai_retry:{incoming.pk}"
        retries = int(cache.get(retry_key) or 0)
        if retries >= 3:
            return {"status": log_entry.status, "reason": "retry_limit_reached"}
        cache.set(retry_key, retries + 1, 600)
        log_entry.status = WhatsAppAIReplyLog.Status.PENDING
        log_entry.error_message = ""
        log_entry.save(update_fields=["status", "error_message", "updated_at"])

    def _skip(reason: str):
        log_entry.status = WhatsAppAIReplyLog.Status.SKIPPED
        log_entry.error_message = reason[:500]
        log_entry.save(update_fields=["status", "error_message", "updated_at"])
        return {"status": "SKIPPED", "reason": reason}

    if not session.is_active or session.status != WhatsAppSession.Status.READY:
        return _skip(f"session_not_ready:{session.status}")

    ai_cfg = _get_or_create_ai_config(session)
    if not ai_cfg.enabled:
        return _skip("session_ai_disabled")

    is_group = str(conversation.chat_id or "").endswith("@g.us")
    if is_group and not ai_cfg.reply_to_groups:
        return _skip("group_chat_skipped")

    wa_cfg = _get_config()
    if not wa_cfg.outbound_enabled or wa_cfg.safety_stop_active:
        return _skip("outbound_safety_stopped")

    sender_info = _extract_sender_identity(conversation, session)
    if sender_info["phone_digits"]:
        active_opt_out = WhatsAppOptOut.objects.filter(
            phone_digits=sender_info["phone_digits"],
            is_active=True,
        ).first()
        if active_opt_out:
            # Mirror manual agent outreach override from whatsapp/services.py: if an agent
            # manually messaged this conversation after an old INCOMING_KEYWORD opt-out,
            # allow AI replies to resume for this conversation.
            manual_resumed = (
                active_opt_out.reason == WhatsAppOptOut.Reason.INCOMING_KEYWORD
                and WhatsAppMessage.objects.filter(
                    conversation=conversation,
                    direction=WhatsAppMessage.Direction.OUTBOUND,
                    performed_by__isnull=False,
                    generated_from_ai_logs__isnull=True,
                    sent_at__gt=active_opt_out.created_at,
                ).exists()
            )
            if manual_resumed:
                active_opt_out.is_active = False
                active_opt_out.reversed_by = session.owner
                active_opt_out.reversed_at = timezone.now()
                active_opt_out.reversal_reason = "Manual agent direct chat resumed conversation"
                active_opt_out.save(update_fields=[
                    "is_active", "reversed_by", "reversed_at", "reversal_reason"
                ])
            else:
                return _skip("recipient_opted_out")

    history_msgs = retrieve_synchronized_chat_history(
        conversation,
        session,
        limit=ai_cfg.max_history_messages or 20,
    )
    log_entry.history_message_count = len(history_msgs)
    log_entry.sender_identifier = sender_info["phone_number"] or sender_info["sender_id"]

    prompt = _build_gemini_reply_prompt(
        sender_info,
        history_msgs,
        incoming,
        custom_instructions=ai_cfg.system_instructions,
    )

    try:
        reply_text, model_used = generate_gemini_whatsapp_reply(
            prompt,
            model=ai_cfg.model_name or _get_setting("WHATSAPP_AI_MODEL", ""),
            timeout=int(_get_setting("WHATSAPP_AI_TIMEOUT", "15") or 15),
        )
    except Exception as exc:
        logger.warning("Gemini WhatsApp auto-reply generation failed for msg %s: %s", incoming.pk, exc)
        log_entry.status = WhatsAppAIReplyLog.Status.FAILED
        log_entry.error_message = str(exc)[:1000]
        log_entry.save(update_fields=["status", "error_message", "history_message_count", "sender_identifier", "updated_at"])
        return {"status": "FAILED", "error": str(exc)}

    # Send through the exact same connected WhatsAppSession (no user login required)
    client = get_waha_client()
    is_lid_chat = str(conversation.chat_id).endswith("@lid")
    reply_to_id = incoming.waha_message_id if is_lid_chat else None
    send_targets = [(conversation.chat_id, reply_to_id)]
    if is_lid_chat:
        if reply_to_id:
            send_targets.append((conversation.chat_id, None))
        if sender_info.get("phone_digits"):
            send_targets.append((f"{sender_info['phone_digits']}@c.us", None))

    waha_resp = None
    last_send_exc = None
    for target_jid, target_reply_to in send_targets:
        try:
            waha_resp = client.send_text(
                session_name=session.session_name,
                chat_id=target_jid,
                text=reply_text,
                reply_to=target_reply_to,
            )
            last_send_exc = None
            break
        except WAHAServiceError as exc:
            last_send_exc = exc
            continue

    if last_send_exc is not None:
        logger.error("WAHA send failed for Gemini AI reply msg %s: %s", incoming.pk, last_send_exc)
        log_entry.status = WhatsAppAIReplyLog.Status.FAILED
        log_entry.reply_text = reply_text
        log_entry.model_used = model_used
        log_entry.error_message = str(last_send_exc)[:1000]
        log_entry.save(update_fields=[
            "status", "reply_text", "model_used", "error_message",
            "history_message_count", "sender_identifier", "updated_at",
        ])
        return {"status": "FAILED", "error": str(last_send_exc)}

    now = timezone.now()
    waha_msg_id = (
        (waha_resp.get("id") or (waha_resp.get("key") or {}).get("id"))
        if isinstance(waha_resp, dict) else None
    )
    body_hash = WhatsAppMessage.compute_body_hash(reply_text)
    idem_key = hashlib.sha256(f"ai_reply:{incoming.pk}:{uuid.uuid4().hex}".encode("utf-8")).hexdigest()

    with transaction.atomic():
        out_msg = WhatsAppMessage.objects.create(
            idempotency_key=idem_key,
            conversation=conversation,
            performed_by=session.owner,
            waha_message_id=waha_msg_id,
            direction=WhatsAppMessage.Direction.OUTBOUND,
            status=WhatsAppMessage.Status.SENT,
            body_preview=reply_text[:200],
            full_body=reply_text,
            body_hash=body_hash,
            message_type="chat",
            waha_timestamp=now,
            sent_at=now,
        )
        WhatsAppConversation.objects.filter(pk=conversation.pk).update(
            last_message_at=now,
            last_message_preview=reply_text[:200],
            last_message_from_me=True,
        )
        WhatsAppSession.objects.filter(pk=session.pk).update(
            send_count=F("send_count") + 1,
            consecutive_failed_sends=0,
            last_successful_message_at=now,
            last_used_at=now,
        )

        log_entry.reply_message = out_msg
        log_entry.reply_text = reply_text
        log_entry.model_used = model_used
        log_entry.status = WhatsAppAIReplyLog.Status.SENT
        log_entry.error_message = ""
        log_entry.replied_at = now
        log_entry.save(update_fields=[
            "reply_message", "reply_text", "model_used", "status",
            "error_message", "replied_at", "history_message_count",
            "sender_identifier", "updated_at",
        ])

    _write_audit_log(
        action=WhatsAppAuditLog.Action.MESSAGE_SENT,
        performed_by=session.owner,
        prospect_contact=conversation.prospect_contact,
        session_name=session.session_name,
        chat_id=conversation.chat_id,
        message_id=out_msg.pk,
        success=True,
        result_code="AI_AUTO_REPLY",
        result_detail=f"Gemini ({model_used}) replied automatically",
    )

    return {
        "status": "SENT",
        "model": model_used,
        "reply_message_id": str(out_msg.pk),
        "reply_text": reply_text,
    }


def schedule_ai_auto_reply(incoming_message_id) -> None:
    """
    Dispatch AI auto-reply asynchronously in production so webhook responses
    stay fast; runs synchronously inside unit tests when explicitly enabled.
    """
    if not _is_auto_reply_globally_enabled():
        return

    if "test" in sys.argv:
        try:
            process_ai_auto_reply(incoming_message_id)
        except Exception as exc:
            logger.warning("Test inline AI auto-reply failed for %s: %s", incoming_message_id, exc)
        return

    def _spawn_worker():
        def _worker():
            try:
                process_ai_auto_reply(incoming_message_id)
            except Exception as exc:
                logger.warning("Async AI auto-reply failed for %s: %s", incoming_message_id, exc)
            finally:
                try:
                    connection.close()
                except Exception:
                    pass

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    if connection.in_atomic_block:
        try:
            transaction.on_commit(_spawn_worker)
            return
        except Exception:
            pass
    _spawn_worker()


def handle_persisted_whatsapp_message(
    sender,
    *,
    session=None,
    conversation=None,
    message=None,
    is_from_me: bool = False,
    is_history_sync: bool = False,
    **kwargs,
) -> None:
    """
    Signal receiver triggered whenever an inbound message is persisted.
    Triggers immediately on live webhooks (`is_history_sync=False`) AND for
    brand-new real-time messages discovered via WAHA stats/chat polling
    (`is_history_sync=True` within the fresh real-time window), while still
    ignoring old 2-day historical backfill messages.
    """
    if is_from_me or message is None:
        return
    if not _is_auto_reply_globally_enabled():
        return
    if is_history_sync and not _is_fresh_inbound_for_auto_reply(message, session=session):
        return
    schedule_ai_auto_reply(message.pk)


def catch_up_unreplied_fresh_inbound_messages() -> int:
    """
    Safety sweep for fresh incoming messages on READY sessions that have not yet
    succeeded with a `SENT` or `SKIPPED` AI reply (e.g., race with status sync,
    autoreload interruption, or transient failure after account switch).
    Ignores historical backfill outside the fresh window.
    """
    from whatsapp.models import WhatsAppMessage, WhatsAppSession
    from .models import WhatsAppAIReplyLog

    if not _is_auto_reply_globally_enabled():
        return 0

    now = timezone.now()
    cutoff = now - timedelta(seconds=_get_fresh_sync_window_seconds())
    pending_msgs = (
        WhatsAppMessage.objects
        .select_related("conversation", "conversation__session")
        .filter(
            direction=WhatsAppMessage.Direction.INBOUND,
            sent_at__gte=cutoff,
            conversation__is_deleted=False,
            conversation__session__is_active=True,
            conversation__session__status=WhatsAppSession.Status.READY,
        )
        .filter(
            Q(ai_reply_log__isnull=True)
            | Q(
                ai_reply_log__status=WhatsAppAIReplyLog.Status.FAILED,
                ai_reply_log__updated_at__lte=now - timedelta(seconds=5),
            )
            | Q(
                ai_reply_log__status=WhatsAppAIReplyLog.Status.PENDING,
                ai_reply_log__updated_at__lte=now - timedelta(seconds=20),
            )
        )
        .order_by("sent_at", "created_at")[:25]
    )

    scheduled = 0
    for msg in pending_msgs:
        sess = msg.conversation.session if msg.conversation else None
        if _is_fresh_inbound_for_auto_reply(msg, session=sess):
            schedule_ai_auto_reply(msg.pk)
            scheduled += 1
    return scheduled
