"""
Real-time WhatsApp listener and webhook self-healer for `whatsapp_ai`.

Ensures incoming WhatsApp messages trigger immediate Gemini AI replies even when:
  - All Market Intel users are logged out of the web UI, or
  - WAHA delivers messages without reaching the local Django webhook endpoint
    (e.g., localhost / Docker networking or webhook config drift).
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Optional

from django.conf import settings
from django.db import connection
from django.utils import timezone

from .gemini_service import (
    _get_setting,
    _is_auto_reply_globally_enabled,
    catch_up_unreplied_fresh_inbound_messages,
)

logger = logging.getLogger(__name__)

_LISTENER_START_LOCK = threading.Lock()
_CYCLE_LOCK = threading.Lock()
_LISTENER_THREAD: Optional[threading.Thread] = None
_STOP_EVENT = threading.Event()
_LAST_CHAT_POLL_TS: float = 0.0

_EXCLUDED_MANAGE_COMMANDS = frozenset({
    "migrate",
    "makemigrations",
    "collectstatic",
    "shell",
    "shell_plus",
    "dbshell",
    "createsuperuser",
    "changepassword",
    "check",
    "test",
    "dumpdata",
    "loaddata",
    "showmigrations",
    "sqlmigrate",
    "flush",
    "inspectdb",
    "run_rag_worker",
    "verify_vector_setup",
    "evaluate_rag",
    "reembed_rag",
    "purge_rag_query_logs",
    "process_campaign_queue",
})


def _get_poll_interval_seconds() -> float:
    try:
        val = float(_get_setting("WHATSAPP_AI_POLL_INTERVAL_SECONDS", "2.0") or "2.0")
        return max(1.0, min(val, 30.0))
    except (TypeError, ValueError):
        return 2.0


def _get_chat_poll_interval_seconds() -> float:
    try:
        val = float(_get_setting("WHATSAPP_AI_CHAT_POLL_INTERVAL_SECONDS", "6.0") or "6.0")
        return max(2.0, min(val, 60.0))
    except (TypeError, ValueError):
        return 6.0


def _detect_local_server_port() -> str:
    env_port = _get_setting("PORT", "") or _get_setting("DJANGO_PORT", "")
    if env_port:
        return env_port
    argv = list(sys.argv)
    for idx, arg in enumerate(argv):
        if str(arg).lower() == "runserver" and idx + 1 < len(argv):
            next_arg = str(argv[idx + 1]).strip()
            if not next_arg.startswith("-"):
                cand = next_arg.split(":")[-1]
                if cand.isdigit():
                    return cand
    return "8000"


def _resolve_default_webhook_url() -> str:
    return _get_setting("WHATSAPP_WEBHOOK_PUBLIC_URL", "")


def _reconcile_live_waha_sessions(client) -> bool:
    """
    Dynamically discover currently connected (WORKING) sessions in WAHA and reconcile
    them against Market Intel's PostgreSQL WhatsAppSession records (handling account
    disconnect/reconnect switches even when no user is actively polling the QR screen).
    Returns False when WAHA is unreachable so the caller skips further WAHA HTTP calls
    in the same cycle.
    """
    from whatsapp.models import WhatsAppSession
    from whatsapp.services import normalize_phone_digits, reconcile_connected_session
    from whatsapp.webhooks import _resolve_originating_session

    try:
        waha_sessions = client.get_all_sessions()
    except Exception as exc:
        logger.debug("WAHA session discovery skipped: %s", exc)
        return False

    if not isinstance(waha_sessions, list):
        return True

    for ws in waha_sessions:
        if not isinstance(ws, dict):
            continue
        w_name = str(ws.get("name") or "").strip()
        w_status = str(ws.get("status") or "").upper()
        if not w_name or w_status not in ("WORKING", "READY", "ONLINE", "AUTHENTICATED"):
            continue

        session_obj = _resolve_originating_session(w_name)
        if not session_obj:
            continue

        me_info = ws.get("me") if isinstance(ws.get("me"), dict) else {}
        raw_phone = str(me_info.get("phone") or (me_info.get("id") or "").split("@")[0].split(":")[0]).strip()
        live_digits = normalize_phone_digits(raw_phone)
        db_digits = normalize_phone_digits(session_obj.phone_number or "")

        if live_digits and (
            session_obj.status != WhatsAppSession.Status.READY
            or not session_obj.is_active
            or live_digits != db_digits
        ):
            try:
                reconcile_connected_session(session_obj, raw_phone, source="realtime_listener")
            except Exception as rec_exc:
                logger.debug("Realtime session reconcile error for %s: %s", w_name, rec_exc)
        elif session_obj.status != WhatsAppSession.Status.READY or not session_obj.is_active:
            session_obj.status = WhatsAppSession.Status.READY
            session_obj.is_active = True
            session_obj.save(update_fields=["status", "is_active", "updated_at"])
    return True


def _coerce_epoch_dt(raw_ts) -> Optional[datetime]:
    if raw_ts is None or raw_ts == "":
        return None
    try:
        ts_val = float(raw_ts)
        if ts_val <= 0:
            return None
        if ts_val > 1e12:
            ts_val /= 1000.0
        return datetime.fromtimestamp(ts_val, tz=dt_timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _sync_waha_chats_for_session(client, session) -> int:
    from whatsapp.models import WhatsAppConversation
    from whatsapp.webhooks import _normalize_chat_jid, sync_recent_waha_messages

    try:
        chats = client.get_chats(session.session_name, limit=15)
    except Exception as exc:
        logger.debug("WAHA chat poll skipped for %s: %s", session.session_name, exc)
        return 0

    if not isinstance(chats, list) or not chats:
        return 0

    existing_last_ts = {}
    for cid_val, last_dt in (
        WhatsAppConversation.objects
        .filter(session=session, is_deleted=False)
        .values_list("chat_id", "last_message_at")
    ):
        norm_cid = _normalize_chat_jid(str(cid_val or "").strip())
        if norm_cid and (norm_cid not in existing_last_ts or (last_dt and (existing_last_ts[norm_cid] is None or last_dt > existing_last_ts[norm_cid]))):
            existing_last_ts[norm_cid] = last_dt

    synced_total = 0
    checked_chats = 0
    for chat in chats:
        if not isinstance(chat, dict):
            continue
        raw_chat_id = (
            chat.get("id")
            or chat.get("chatId")
            or chat.get("_serialized")
            or (chat.get("jid") if isinstance(chat.get("jid"), str) else "")
            or ""
        )
        if isinstance(raw_chat_id, dict):
            raw_chat_id = raw_chat_id.get("_serialized") or raw_chat_id.get("user") or ""
        chat_id = _normalize_chat_jid(str(raw_chat_id).strip())
        if not chat_id or chat_id == "status@broadcast":
            continue

        last_msg_obj = chat.get("lastMessage") if isinstance(chat.get("lastMessage"), dict) else {}
        chat_dt = (
            _coerce_epoch_dt(chat.get("lastMessageTimestamp"))
            or _coerce_epoch_dt(chat.get("conversationTimestamp"))
            or _coerce_epoch_dt(chat.get("timestamp"))
            or _coerce_epoch_dt(last_msg_obj.get("timestamp"))
        )
        unread_count = int(chat.get("unreadCount") or 0)
        db_last = existing_last_ts.get(chat_id)
        if unread_count <= 0 and chat_dt is not None and db_last is not None and (chat_dt + timedelta(seconds=2)) < db_last:
            continue

        if checked_chats >= 6:
            break
        checked_chats += 1

        try:
            msgs = client.get_messages(session.session_name, chat_id, limit=5)
        except Exception as exc:
            logger.debug("WAHA get_messages skipped for %s/%s: %s", session.session_name, chat_id, exc)
            continue

        if not isinstance(msgs, list) or not msgs:
            continue

        normalized = []
        for item in msgs:
            if not isinstance(item, dict):
                continue
            copy_item = dict(item)
            if not str(copy_item.get("session") or "").strip():
                copy_item["session"] = session.session_name
            normalized.append(copy_item)

        if normalized:
            synced_total += sync_recent_waha_messages(
                normalized,
                default_session_name=session.session_name,
                days=2,
            )

    return synced_total


def run_realtime_sync_cycle(*, force_chat_poll: bool = False) -> dict[str, int]:
    """
    Execute a single real-time check across all connected READY WhatsApp sessions.
    Safe to call when all Market Intel users are logged out.
    """
    global _LAST_CHAT_POLL_TS

    if not _is_auto_reply_globally_enabled():
        return {"sessions": 0, "synced": 0, "scheduled": 0}

    if not _CYCLE_LOCK.acquire(blocking=False):
        return {"sessions": 0, "synced": 0, "scheduled": 0}

    try:
        from whatsapp.client import get_waha_client
        from whatsapp.models import WhatsAppSession
        from whatsapp.webhooks import sync_recent_waha_messages

        client = None
        waha_reachable = False
        try:
            client = get_waha_client()
            waha_reachable = _reconcile_live_waha_sessions(client)
        except Exception as exc:
            logger.debug("WAHA client/reconcile skipped: %s", exc)

        ready_sessions = list(
            WhatsAppSession.objects
            .filter(is_active=True, status=WhatsAppSession.Status.READY)
            .exclude(session_name="")
            .exclude(session_name__startswith="hist_")
        )
        if not ready_sessions:
            return {"sessions": 0, "synced": 0, "scheduled": 0}

        synced_total = 0
        if client is not None and waha_reachable:
            try:
                target_url = _resolve_default_webhook_url()
                if target_url:
                    try:
                        client.ensure_webhook_configured(target_url)
                    except Exception as exc:
                        logger.debug("Webhook self-heal skipped: %s", exc)

                try:
                    recent_msgs = client.get_recent_messages_from_stats(force=True)
                except Exception as exc:
                    logger.debug("WAHA stats fetch skipped: %s", exc)
                    recent_msgs = []

                if isinstance(recent_msgs, list) and recent_msgs:
                    for sess in ready_sessions:
                        sess_msgs = [
                            m for m in recent_msgs
                            if isinstance(m, dict) and str(m.get("session") or "").strip() == sess.session_name
                        ]
                        if sess_msgs:
                            synced_total += sync_recent_waha_messages(
                                sess_msgs,
                                default_session_name=sess.session_name,
                                days=2,
                            )

                now_ts = time.monotonic()
                chat_interval = _get_chat_poll_interval_seconds()
                if force_chat_poll or (now_ts - _LAST_CHAT_POLL_TS >= chat_interval):
                    _LAST_CHAT_POLL_TS = now_ts
                    for sess in ready_sessions:
                        synced_total += _sync_waha_chats_for_session(client, sess)
            except Exception as exc:
                logger.debug("Realtime WAHA cycle skipped: %s", exc)

        scheduled = catch_up_unreplied_fresh_inbound_messages()
        return {
            "sessions": len(ready_sessions),
            "synced": synced_total,
            "scheduled": scheduled,
            "waha_reachable": waha_reachable,
        }
    finally:
        _CYCLE_LOCK.release()


def _listener_loop() -> None:
    poll_interval = _get_poll_interval_seconds()
    logger.info(
        "WhatsApp Gemini AI real-time listener started (poll_interval=%.1fs).",
        poll_interval,
    )
    # Short initial delay so Django migrations/startup finish cleanly first
    if _STOP_EVENT.wait(1.5):
        return

    while not _STOP_EVENT.is_set():
        wait_secs = poll_interval
        try:
            res = run_realtime_sync_cycle()
            if isinstance(res, dict) and res.get("waha_reachable") is False:
                wait_secs = max(poll_interval, 30.0)
        except Exception as exc:
            logger.debug("WhatsApp AI listener cycle error: %s", exc)
        finally:
            try:
                connection.close()
            except Exception:
                pass
        _STOP_EVENT.wait(wait_secs)


def should_autostart_listener() -> bool:
    """
    Start automatically in live web server processes (WSGI/ASGI or Django runserver
    inner reloader worker), while never starting inside tests or management CLI tasks.
    """
    if "test" in sys.argv:
        return False
    if not _is_auto_reply_globally_enabled():
        return False

    polling_flag = _get_setting("WHATSAPP_AI_REALTIME_POLLING", "true").lower()
    if polling_flag in ("0", "false", "no", "off"):
        return False

    argv = [str(a).lower() for a in sys.argv]
    if any(cmd in argv for cmd in _EXCLUDED_MANAGE_COMMANDS):
        return False

    if "runserver" in argv:
        return os.environ.get("RUN_MAIN") == "true" or "--noreload" in argv

    return any(srv in " ".join(argv) for srv in ("gunicorn", "uwsgi", "daphne", "uvicorn", "run_whatsapp_ai_listener"))


def start_realtime_listener() -> bool:
    global _LISTENER_THREAD

    with _LISTENER_START_LOCK:
        if _LISTENER_THREAD is not None and _LISTENER_THREAD.is_alive():
            return False
        _STOP_EVENT.clear()
        thread = threading.Thread(
            target=_listener_loop,
            name="whatsapp-ai-realtime-listener",
            daemon=True,
        )
        thread.start()
        _LISTENER_THREAD = thread
        return True


def stop_realtime_listener() -> None:
    _STOP_EVENT.set()
