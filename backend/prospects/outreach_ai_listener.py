"""
Live Sent-Mail & Unsent Outreach AI Draft Listener (`prospects.outreach_ai_listener`).

Continuously monitors:
1. Sent emails across Outreach Workspace (`OutreachEmail`), Email Inbox / Gmail Sync
   (`EmailThreadMessage`), Communication Timeline (`CommunicationActivity`), and
   Bulk Campaigns (`EmailCampaignRecipient`), immediately pruning any `DRAFT` campaign
   recipients whose outreach email has already been sent.
2. Unsent outreach records (`Prospect` / `ProspectContact` where no email has been sent),
   automatically ensuring customized Google Gemini + Vector DB portfolio email drafts
   are generated and organized into sections of 10 drafts per section.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
from typing import Optional

from django.conf import settings
from django.db import close_old_connections, connection, transaction
from django.db.models.signals import post_save

logger = logging.getLogger(__name__)

_LISTENER_LOCK = threading.Lock()
_CYCLE_LOCK = threading.Lock()
_LISTENER_THREAD: Optional[threading.Thread] = None
_WAKE_EVENT = threading.Event()
_STOP_EVENT = threading.Event()

_EXCLUDED_COMMANDS = frozenset({
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


def should_autostart_outreach_listener() -> bool:
    """
    Returns True only when running inside the live web server process (`runserver`,
    Gunicorn, Daphne, Uvicorn) and False during migrations or unit tests.
    """
    flag = str(os.environ.get("OUTREACH_AI_LISTENER_ENABLED", "true")).strip().lower()
    if flag in ("0", "false", "no", "off"):
        return False

    argv = [str(a).lower() for a in sys.argv]
    for cmd in _EXCLUDED_COMMANDS:
        if cmd in argv:
            return False

    if "pytest" in argv[0] or any("test" in a for a in argv[1:3]):
        return False

    if "runserver" in argv:
        if "--noreload" not in argv and os.environ.get("RUN_MAIN") != "true":
            return False
        return True

    server_binaries = ("gunicorn", "daphne", "uvicorn", "hypercorn", "waitress")
    if any(b in argv[0] for b in server_binaries):
        return True

    return False


def wake_outreach_ai_listener() -> None:
    """Signals the background listener thread to run a sent-mail & unsent-outreach check immediately."""
    _WAKE_EVENT.set()


def run_live_sent_mail_and_draft_cycle(auto_draft_for_users: bool = True) -> dict:
    """
    Executes one non-overlapping cycle of the live sent-mail check & unsent outreach AI drafter.
    """
    if not _CYCLE_LOCK.acquire(blocking=False):
        return {"skipped": True}

    try:
        close_old_connections()
        from django.contrib.auth import get_user_model
        from prospects.campaign_service import (
            prune_sent_recipients_from_draft_campaigns,
            sync_live_unsent_outreach_ai_drafts,
        )
        from prospects.models import EmailCampaign

        pruned = prune_sent_recipients_from_draft_campaigns()
        drafted_total = 0

        if auto_draft_for_users:
            User = get_user_model()
            # Sync active campaigns that are currently in DRAFT / QUEUED / RUNNING state
            creator_ids = list(
                EmailCampaign.objects.filter(
                    status__in=[
                        EmailCampaign.Status.DRAFT,
                        EmailCampaign.Status.QUEUED,
                        EmailCampaign.Status.RUNNING,
                    ]
                )
                .values_list("created_by_id", flat=True)
                .distinct()
            )
            users = list(User.objects.filter(id__in=creator_ids, is_active=True))
            for u in users:
                try:
                    res = sync_live_unsent_outreach_ai_drafts(user=u, auto_draft=True)
                    drafted_total += int(res.get("newly_drafted_count") or 0)
                    pruned += int(res.get("pruned_sent_drafts") or 0)
                except Exception as u_exc:
                    logger.debug("Live outreach AI sync skipped for user %s: %s", u.id, u_exc)

        return {"pruned_sent_drafts": pruned, "newly_drafted_count": drafted_total}
    except Exception as exc:
        logger.debug("Live outreach AI listener cycle error: %s", exc)
        return {"error": str(exc)}
    finally:
        try:
            close_old_connections()
        except Exception:
            pass
        _CYCLE_LOCK.release()


def _listener_loop() -> None:
    poll_seconds = 15.0
    logger.info("OutreachAISentMailListener started (interval=%ss).", poll_seconds)
    while not _STOP_EVENT.is_set():
        _WAKE_EVENT.wait(timeout=poll_seconds)
        _WAKE_EVENT.clear()
        if _STOP_EVENT.is_set():
            break
        run_live_sent_mail_and_draft_cycle(auto_draft_for_users=True)


def start_outreach_ai_listener() -> bool:
    """Starts the background daemon thread if not already running."""
    global _LISTENER_THREAD
    with _LISTENER_LOCK:
        if _LISTENER_THREAD is not None and _LISTENER_THREAD.is_alive():
            return False
        _STOP_EVENT.clear()
        _LISTENER_THREAD = threading.Thread(
            target=_listener_loop,
            name="OutreachAISentMailListener",
            daemon=True,
        )
        _LISTENER_THREAD.start()
        return True


def _on_sent_mail_activity_saved(sender, instance, **kwargs) -> None:
    """
    Signal receiver triggered whenever an OutreachEmail, EmailThreadMessage, or
    CommunicationActivity is saved. Immediately prunes any matching DRAFT campaign
    recipients so an already-emailed outreach company is never drafted/sent again.
    """
    def _prune_now():
        try:
            from prospects.campaign_service import prune_sent_recipients_from_draft_campaigns
            prune_sent_recipients_from_draft_campaigns()
        except Exception as exc:
            logger.debug("Inline sent-mail draft prune skipped: %s", exc)
        wake_outreach_ai_listener()

    if connection.in_atomic_block:
        try:
            transaction.on_commit(_prune_now)
        except Exception:
            _prune_now()
    else:
        _prune_now()


def _on_prospect_or_contact_saved(sender, instance, **kwargs) -> None:
    """
    Signal receiver triggered when a Prospect or ProspectContact is created/updated.
    Wakes the live listener so any new unsent outreach record is detected.
    """
    wake_outreach_ai_listener()


def register_outreach_ai_signals() -> None:
    """Connects post_save signals on sent-mail and outreach models."""
    from prospects.models import (
        CommunicationActivity,
        EmailThreadMessage,
        OutreachEmail,
        Prospect,
        ProspectContact,
    )

    for model_cls, uid in [
        (OutreachEmail, "prospects.outreach_ai.on_outreach_email_saved"),
        (EmailThreadMessage, "prospects.outreach_ai.on_thread_message_saved"),
        (CommunicationActivity, "prospects.outreach_ai.on_comm_activity_saved"),
    ]:
        post_save.connect(_on_sent_mail_activity_saved, sender=model_cls, dispatch_uid=uid)

    for model_cls, uid in [
        (Prospect, "prospects.outreach_ai.on_prospect_saved"),
        (ProspectContact, "prospects.outreach_ai.on_contact_saved"),
    ]:
        post_save.connect(_on_prospect_or_contact_saved, sender=model_cls, dispatch_uid=uid)
