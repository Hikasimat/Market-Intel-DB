"""
Email AI Service (`email_ai.services`).

Houses:
1. Gemini AI Personalized Email Generation for:
   - Outreach Workspace (`OUTREACH`)
   - Email Inbox Compose (`INBOX`)
   - Bulk Email Campaign (`CAMPAIGN`)
2. Email Thread Summarization & User-Wise Daily Email Activity AI Summaries
   (migrated from `prospects.email_summarizer`).
"""

import hashlib
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


def _get_setting(name: str, default: str = "") -> str:
    val = getattr(settings, name, None)
    if val is None or val == "":
        val = os.environ.get(name, default)
    return str(val or default).strip()


def _strip_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    cleaned = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", raw_html)
    cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _clean_message_text(msg) -> str:
    text = (msg.body_text or "").strip()
    if not text and msg.body_html:
        text = _strip_html(msg.body_html)
    if not text and msg.snippet:
        text = msg.snippet.strip()
    text = re.sub(r"\s+", " ", text).strip()
    return text


def compute_thread_content_hash(messages) -> str:
    parts = []
    for m in messages:
        parts.append(
            "|".join([
                str(m.id),
                str(m.direction or ""),
                str(m.status or ""),
                str(m.sent_at.isoformat() if m.sent_at else ""),
                _clean_message_text(m)[:1500],
            ])
        )
    joined = "\n".join(parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def _truncate_words(text: str, max_len: int) -> str:
    cleaned = str(text or "").strip()
    if len(cleaned) <= max_len:
        return cleaned
    clipped = cleaned[:max_len].rsplit(" ", 1)[0].strip()
    if not clipped:
        clipped = cleaned[:max_len].strip()
    return f"{clipped}..."


def _generate_extractive_summary(thread, messages) -> Tuple[str, str]:
    """
    Build a concise, strictly factual extractive summary directly from thread messages.
    Zero fabrication.
    """
    if not messages:
        return "No messages recorded in this email thread yet.", "Await activity"

    total = len(messages)
    outbound_msgs = [m for m in messages if m.direction == "OUTBOUND"]
    inbound_msgs = [m for m in messages if m.direction == "INBOUND"]
    latest = messages[-1]
    first = messages[0]

    correspondent = thread.correspondent_name or thread.correspondent_email or "contact"
    subject_label = thread.subject or "(No Subject)"

    first_excerpt = _truncate_words(_clean_message_text(first), 160)
    latest_excerpt = _truncate_words(_clean_message_text(latest), 220)

    parts = [f"Thread '{subject_label}' with {correspondent} ({total} message{'s' if total != 1 else ''}: {len(outbound_msgs)} sent, {len(inbound_msgs)} received)."]

    if first_excerpt and first.id != latest.id:
        parts.append(f"Initial message ({first.direction.lower()}): \"{first_excerpt}\"")

    if latest.direction == "INBOUND":
        parts.append(f"Latest reply from {latest.sender_email or correspondent}: \"{latest_excerpt}\"")
        next_action = f"Review reply from {correspondent} and send follow-up response."
    elif latest.status == "FAILED":
        err = (latest.error_message or "delivery failure")[:120]
        parts.append(f"Latest outbound attempt failed ({err}).")
        next_action = f"Verify recipient address and retry sending to {correspondent}."
    else:
        if latest_excerpt:
            parts.append(f"Latest outbound email: \"{latest_excerpt}\"")
        next_action = f"Follow up if no reply is received from {correspondent}."

    return " ".join(parts).strip(), next_action[:480]


def _resolve_provider_and_key() -> Tuple[str, str, str]:
    """Return (provider_name, api_key, model_name)."""
    configured = _get_setting("EMAIL_SUMMARY_PROVIDER", "auto").lower()
    gemini_key = _get_setting("GEMINI_API_KEY", "")
    openai_key = _get_setting("OPENAI_API_KEY", "")

    if configured in ("extractive", "local", "disabled", "none"):
        return "extractive", "", "extractive-v1"
    if configured == "gemini":
        model = _get_setting("EMAIL_SUMMARY_MODEL", "gemini-3.8-flash")
        return "gemini", gemini_key, model
    if configured == "openai":
        model = _get_setting("EMAIL_SUMMARY_MODEL", "gpt-4o-mini")
        return "openai", openai_key, model

    # auto mode
    if gemini_key:
        model = _get_setting("EMAIL_SUMMARY_MODEL", "gemini-3.8-flash")
        return "gemini", gemini_key, model
    if openai_key:
        model = _get_setting("EMAIL_SUMMARY_MODEL", "gpt-4o-mini")
        return "openai", openai_key, model
    return "extractive", "", "extractive-v1"


def _build_llm_prompt(thread, messages) -> str:
    transcript_lines = []
    bounded = messages[-15:] if len(messages) > 15 else messages
    for idx, m in enumerate(bounded, start=1):
        ts = m.sent_at.isoformat() if m.sent_at else "unknown-time"
        body = _clean_message_text(m)[:1200]
        transcript_lines.append(
            f"[{idx}] {m.direction} | {ts} | From: {m.sender_email} | Status: {m.status}\n"
            f"Subject: {m.subject}\n"
            f"Body: {body}\n"
        )

    prospect_label = thread.prospect.company_name if thread.prospect else "Unmatched prospect"
    correspondent = thread.correspondent_email or "unknown"

    return (
        "You are summarizing a B2B sales email conversation for a sales manager.\n"
        "RULES:\n"
        "1. Summarize ONLY facts explicitly stated in the messages below.\n"
        "2. Do NOT invent names, dates, amounts, commitments, or topics.\n"
        "3. Return strictly valid JSON with keys 'summary' (2-3 concise sentences) "
        "and 'next_action' (one concise actionable next step <= 140 chars).\n\n"
        f"Prospect: {prospect_label}\n"
        f"Correspondent: {correspondent}\n"
        f"Thread Subject: {thread.subject}\n\n"
        "Messages:\n" + "\n".join(transcript_lines)
    )


def _parse_json_summary(raw_text: str) -> Optional[Tuple[str, str]]:
    text = (raw_text or "").strip()
    if not text:
        return None
    fence_match = re.search(r"\{.*\}", text, re.DOTALL)
    if fence_match:
        try:
            data = json.loads(fence_match.group(0))
            summary = str(data.get("summary") or "").strip()
            next_action = str(data.get("next_action") or "").strip()
            if summary:
                return summary[:2000], next_action[:480]
        except Exception:
            pass
    return text[:2000], ""


def _discover_gemini_models(api_key: str, timeout: int) -> list:
    """Query Google AI Studio /v1beta/models and return free/flash generateContent models in preference order."""
    from django.core.cache import cache

    cached = cache.get("gemini_discovered_flash_models")
    if isinstance(cached, list) and cached:
        return cached

    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    discovered = []
    for item in (data.get("models") or []):
        methods = item.get("supportedGenerationMethods") or []
        if "generateContent" not in methods:
            continue
        raw_name = str(item.get("name") or "").strip()
        short_name = raw_name.replace("models/", "", 1).strip()
        if not short_name:
            continue
        low = short_name.lower()
        if any(skip in low for skip in ("embedding", "imagen", "veo", "tts", "audio", "robotics", "aqa")):
            continue
        discovered.append(short_name)

    def _rank(name: str):
        low = name.lower()
        is_flash = 0 if "flash" in low else 1
        is_lite = 0 if "lite" in low else 1
        is_latest = 0 if "latest" in low else 1
        return (is_flash, is_lite, is_latest, name)

    discovered.sort(key=_rank)
    if discovered:
        cache.set("gemini_discovered_flash_models", discovered[:8], 3600)
    return discovered[:8]


def _call_gemini(prompt: str, api_key: str, model: str, timeout: int, max_output_tokens: int = 1024) -> Tuple[str, str, str]:
    from django.core.cache import cache

    candidate_models = []
    cached_winner = cache.get("gemini_working_free_model")
    for cand in [
        cached_winner,
        model,
        "gemini-3.8-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-flash-latest",
        "gemini-2.0-flash-lite",
    ]:
        if cand and cand not in candidate_models:
            candidate_models.append(cand)

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": max_output_tokens,
            "responseMimeType": "application/json",
        },
    }).encode("utf-8")

    def _invoke(cand_model: str) -> Tuple[str, str, str]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{cand_model}:generateContent?key={api_key}"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        candidates = data.get("candidates") or []
        parts = (((candidates[0] if candidates else {}).get("content") or {}).get("parts") or [])
        raw_text = "".join(str(p.get("text") or "") for p in parts)
        parsed = _parse_json_summary(raw_text)
        if not parsed:
            raise ValueError(f"Gemini ({cand_model}) returned empty summary response")
        cache.set("gemini_working_free_model", cand_model, 3600)
        return parsed[0], parsed[1], cand_model

    last_error = None
    saw_not_found = False
    for idx, cand_model in enumerate(candidate_models):
        try:
            return _invoke(cand_model)
        except urllib.error.HTTPError as http_err:
            err_body = ""
            try:
                err_body = http_err.read().decode("utf-8", errors="ignore")[:400]
            except Exception:
                pass
            last_error = f"HTTP {http_err.code} on {cand_model}: {err_body or http_err.reason}"
            if http_err.code == 404:
                saw_not_found = True
            if http_err.code in (400, 404, 429) and idx + 1 < len(candidate_models):
                continue
        except Exception as exc:
            last_error = f"{cand_model}: {exc}"
            if idx + 1 < len(candidate_models):
                continue
            raise

    if saw_not_found:
        try:
            for disc_model in _discover_gemini_models(api_key, timeout):
                if disc_model in candidate_models:
                    continue
                try:
                    return _invoke(disc_model)
                except urllib.error.HTTPError as http_err:
                    err_body = ""
                    try:
                        err_body = http_err.read().decode("utf-8", errors="ignore")[:400]
                    except Exception:
                        pass
                    last_error = f"HTTP {http_err.code} on {disc_model}: {err_body or http_err.reason}"
                    continue
                except Exception as exc:
                    last_error = f"{disc_model}: {exc}"
                    continue
        except Exception as disc_err:
            logger.debug("Gemini model discovery skipped: %s", disc_err)

    raise ValueError(last_error or "Gemini request failed")


def _call_openai(prompt: str, api_key: str, model: str, timeout: int) -> Tuple[str, str]:
    url = _get_setting("OPENAI_API_BASE_URL", "https://api.openai.com/v1/chat/completions")
    payload = json.dumps({
        "model": model,
        "temperature": 0.1,
        "max_tokens": 400,
        "messages": [
            {"role": "system", "content": "Respond only with JSON keys summary and next_action."},
            {"role": "user", "content": prompt},
        ],
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    choices = data.get("choices") or []
    raw_text = (((choices[0] if choices else {}).get("message") or {}).get("content") or "")
    parsed = _parse_json_summary(raw_text)
    if not parsed:
        raise ValueError("OpenAI returned empty summary response")
    return parsed


def summarize_email_thread(thread_id, force: bool = False) -> dict:
    """
    Generate or refresh the AI summary for `thread_id`.
    Skips redundant regeneration when the content hash is unchanged (unless `force=True`).
    Handles provider outages cleanly without raising out to email/sync workflows.
    """
    from prospects.models import EmailThread, EmailThreadMessage

    thread = EmailThread.objects.select_related("prospect", "prospect_contact", "owner").filter(pk=thread_id).first()
    if not thread:
        return {"status": "missing", "updated": False}

    messages = list(
        EmailThreadMessage.objects.filter(thread=thread).order_by("sent_at", "created_at")
    )
    if not messages:
        thread.summary_text = "No email messages recorded yet."
        thread.next_action = "Send outreach email or sync mailbox."
        thread.summary_status = EmailThread.SummaryStatus.SKIPPED
        thread.summary_provider = "extractive"
        thread.summary_model = "extractive-v1"
        thread.summary_error = ""
        thread.summary_generated_at = timezone.now()
        thread.save(update_fields=[
            "summary_text", "next_action", "summary_status",
            "summary_provider", "summary_model", "summary_error",
            "summary_generated_at",
        ])
        return {"status": thread.summary_status, "updated": True}

    content_hash = compute_thread_content_hash(messages)
    if (
        not force
        and thread.summary_content_hash == content_hash
        and thread.summary_status == EmailThread.SummaryStatus.READY
        and thread.summary_text
    ):
        return {
            "status": thread.summary_status,
            "provider": thread.summary_provider,
            "updated": False,
            "cached": True,
        }

    provider, api_key, model = _resolve_provider_and_key()
    timeout = int(_get_setting("EMAIL_SUMMARY_TIMEOUT", "12") or 12)
    max_retries = max(1, int(_get_setting("EMAIL_SUMMARY_MAX_RETRIES", "2") or 2))

    if provider in ("gemini", "openai") and not api_key:
        provider = "extractive"
        model = "extractive-v1"

    if provider == "extractive":
        summary_text, next_action = _generate_extractive_summary(thread, messages)
        thread.summary_text = summary_text
        thread.next_action = next_action
        thread.summary_status = EmailThread.SummaryStatus.READY
        thread.summary_provider = "extractive"
        thread.summary_model = model
        thread.summary_error = ""
        thread.summary_content_hash = content_hash
        thread.summary_generated_at = timezone.now()
        thread.save(update_fields=[
            "summary_text", "next_action", "summary_status",
            "summary_provider", "summary_model", "summary_error",
            "summary_content_hash", "summary_generated_at",
        ])
        return {"status": thread.summary_status, "provider": "extractive", "updated": True}

    prompt = _build_llm_prompt(thread, messages)
    last_err = None
    for attempt in range(max_retries):
        try:
            used_model = model
            if provider == "gemini":
                summary_text, next_action, used_model = _call_gemini(prompt, api_key, model, timeout)
            else:
                summary_text, next_action = _call_openai(prompt, api_key, model, timeout)

            if not next_action:
                _, next_action = _generate_extractive_summary(thread, messages)

            thread.summary_text = summary_text
            thread.next_action = next_action
            thread.summary_status = EmailThread.SummaryStatus.READY
            thread.summary_provider = provider
            thread.summary_model = used_model
            thread.summary_error = ""
            thread.summary_content_hash = content_hash
            thread.summary_generated_at = timezone.now()
            thread.save(update_fields=[
                "summary_text", "next_action", "summary_status",
                "summary_provider", "summary_model", "summary_error",
                "summary_content_hash", "summary_generated_at",
            ])
            return {"status": thread.summary_status, "provider": provider, "model": used_model, "updated": True}
        except Exception as exc:
            last_err = str(exc)
            logger.warning(
                "AI summary attempt %s/%s failed for thread %s (%s): %s",
                attempt + 1, max_retries, thread.id, provider, exc,
            )
            if attempt + 1 < max_retries:
                time.sleep(0.5 * (attempt + 1))

    fallback_text, fallback_action = _generate_extractive_summary(thread, messages)
    if not thread.summary_text or thread.summary_status == EmailThread.SummaryStatus.FAILED:
        thread.summary_text = fallback_text
        thread.next_action = fallback_action
    thread.summary_status = EmailThread.SummaryStatus.FAILED
    thread.summary_provider = "extractive_fallback"
    thread.summary_model = f"{provider}:{model}"
    thread.summary_error = (last_err or "AI summarization failed")[:1000]
    thread.summary_generated_at = timezone.now()
    thread.save(update_fields=[
        "summary_text", "next_action", "summary_status",
        "summary_provider", "summary_model", "summary_error",
        "summary_generated_at",
    ])
    return {
        "status": thread.summary_status,
        "provider": "extractive_fallback",
        "updated": False,
        "error": thread.summary_error,
    }


def schedule_thread_summary(thread_id, force: bool = False) -> None:
    """
    Non-blocking summary scheduler. Runs in a daemon thread after transaction commit.
    Never blocks email sends or inbox sync.
    """
    def _dispatch():
        if connection.in_atomic_block:
            try:
                summarize_email_thread(thread_id, force=force)
            except Exception as exc:
                logger.debug("Inline summary generation skipped cleanly: %s", exc)
            return

        def _worker():
            try:
                summarize_email_thread(thread_id, force=force)
            except Exception as exc:
                logger.warning("Async summary worker failed for %s: %s", thread_id, exc)
            finally:
                try:
                    connection.close()
                except Exception:
                    pass

        t = threading.Thread(target=_worker, daemon=True)
        t.start()

    try:
        transaction.on_commit(_dispatch)
    except Exception:
        _dispatch()


def _build_daily_user_llm_prompt(user, report_date, metrics: dict, messages: list) -> str:
    """Build a structured, strictly grounded Gemini prompt for a user's daily email activity."""
    user_label = user.get_full_name() or user.username
    lines = []
    bounded = messages[-35:] if len(messages) > 35 else messages
    for idx, m in enumerate(bounded, start=1):
        ts = (m.sent_at or m.created_at).isoformat() if (m.sent_at or m.created_at) else "unknown-time"
        to_list = ", ".join(str(x) for x in (m.to_emails or [])[:3]) or "unknown"
        prospect_name = (
            m.thread.prospect.company_name
            if getattr(m, "thread", None) and m.thread.prospect
            else (getattr(m.thread, "correspondent_name", "") or getattr(m.thread, "correspondent_email", ""))
        )
        thread_status = getattr(m.thread, "status", "") if getattr(m, "thread", None) else ""
        body_excerpt = _clean_message_text(m)[:800]
        lines.append(
            f"[{idx}] {m.direction} | Time: {ts} | Status: {m.status} | ThreadStatus: {thread_status}\n"
            f"    From: {m.sender_email} -> To: {to_list} | Prospect/Contact: {prospect_name}\n"
            f"    Subject: {m.subject or '(No Subject)'}\n"
            f"    Content: {body_excerpt}"
        )

    return (
        "You are an executive B2B sales operations analyst writing a Manager Dashboard daily report "
        "for one team member.\n"
        "RULES:\n"
        "1. Summarize ONLY facts explicitly present in the metrics and emails below. Never fabricate names, companies, numbers, or commitments.\n"
        "2. Cover key topics, prospect discussions, replies received, and pending follow-ups.\n"
        "3. Return strictly valid JSON with keys:\n"
        '   - "summary": 3-5 clear sentences summarizing the user\'s overall daily email conversations, context, and key outcomes.\n'
        '   - "next_action": concise recommended follow-up action for the manager/user (<= 180 chars).\n\n'
        f"User: {user_label} (@{user.username})\n"
        f"Report Date: {report_date.isoformat()}\n"
        f"Emails Received: {metrics['emails_received']}\n"
        f"Emails Sent: {metrics['emails_sent']}\n"
        f"Sent Emails That Received Responses: {metrics['sent_received_responses']}\n"
        f"Pending Responses: {metrics['pending_responses']}\n\n"
        "Emails:\n" + "\n".join(lines)
    )


def _generate_daily_user_extractive_summary(user, report_date, metrics: dict, messages: list) -> Tuple[str, str]:
    user_label = user.get_full_name() or user.username
    sent_count = metrics["emails_sent"]
    recv_count = metrics["emails_received"]
    replied_count = metrics["sent_received_responses"]
    pending_count = metrics["pending_responses"]

    if sent_count == 0 and recv_count == 0:
        return (
            f"No sent or received email activity recorded for {user_label} on {report_date.isoformat()}.",
            "No follow-up needed.",
        )

    subjects = []
    for m in messages:
        subj = (m.subject or "").strip()
        if subj and subj not in subjects:
            subjects.append(subj)
        if len(subjects) >= 4:
            break

    topics_str = ", ".join(f"'{s}'" for s in subjects) if subjects else "general outreach"
    summary = (
        f"On {report_date.isoformat()}, {user_label} sent {sent_count} email(s) and received {recv_count} email(s) "
        f"({replied_count} sent email(s) received responses, {pending_count} pending response). "
        f"Key subjects included {topics_str}."
    )
    if pending_count > 0:
        next_action = f"Follow up on {pending_count} pending outbound email(s) for {user_label}."
    elif recv_count > 0:
        next_action = f"Review {recv_count} inbound reply/replies with {user_label}."
    else:
        next_action = "Monitor outreach responses."
    return summary, next_action[:480]


def generate_daily_user_email_report(
    user,
    report_date,
    day_start,
    day_end,
    force: bool = False,
    timeout_override: Optional[int] = None,
    max_retries_override: Optional[int] = None,
):
    """
    Compute a user's exact daily email counts (received, sent, responded, pending)
    and generate/cache their Gemini AI overall daily email summary in DailyUserEmailReport.
    """
    from django.db.models import Q
    from prospects.models import DailyUserEmailReport, EmailThread, EmailThreadMessage, OutreachEmail

    day_msgs = list(
        EmailThreadMessage.objects
        .select_related("thread", "thread__prospect", "thread__prospect_contact")
        .filter(owner=user)
        .filter(
            Q(sent_at__gte=day_start, sent_at__lt=day_end)
            | Q(sent_at__isnull=True, created_at__gte=day_start, created_at__lt=day_end)
        )
        .order_by("sent_at", "created_at")
    )

    inbound_msgs = [m for m in day_msgs if m.direction == EmailThreadMessage.Direction.INBOUND]
    outbound_msgs = [
        m for m in day_msgs
        if m.direction == EmailThreadMessage.Direction.OUTBOUND
        and m.status != EmailThreadMessage.Status.FAILED
    ]

    unlinked_outreach = list(
        OutreachEmail.objects
        .filter(created_by=user, thread_message__isnull=True, created_at__gte=day_start, created_at__lt=day_end)
        .exclude(status="FAILED")
    )

    emails_received = len(inbound_msgs)
    emails_sent = len(outbound_msgs) + len(unlinked_outreach)

    touched_thread_ids = {m.thread_id for m in outbound_msgs if m.thread_id}
    inbound_by_thread = {}
    if touched_thread_ids:
        for th_id, ts in (
            EmailThreadMessage.objects
            .filter(
                owner=user,
                thread_id__in=touched_thread_ids,
                direction=EmailThreadMessage.Direction.INBOUND,
            )
            .values_list("thread_id", "sent_at")
        ):
            if th_id not in inbound_by_thread:
                inbound_by_thread[th_id] = []
            inbound_by_thread[th_id].append(ts)

    sent_received_responses = 0
    pending_responses = 0
    for m in outbound_msgs:
        m_ts = m.sent_at or m.created_at
        thread_inbounds = inbound_by_thread.get(m.thread_id, [])
        has_reply = False
        if thread_inbounds:
            for in_ts in thread_inbounds:
                if in_ts is None or m_ts is None or in_ts >= m_ts:
                    has_reply = True
                    break
        elif getattr(m, "thread", None) and m.thread.status == EmailThread.Status.REPLIED:
            has_reply = True

        if has_reply:
            sent_received_responses += 1
        else:
            pending_responses += 1

    for oe in unlinked_outreach:
        if oe.status == "RECEIVED RESPONSE":
            sent_received_responses += 1
        else:
            pending_responses += 1

    metrics = {
        "emails_received": emails_received,
        "emails_sent": emails_sent,
        "sent_received_responses": sent_received_responses,
        "pending_responses": pending_responses,
    }

    hash_parts = [
        f"u:{user.id}|d:{report_date.isoformat()}",
        f"r:{emails_received}|s:{emails_sent}|rr:{sent_received_responses}|p:{pending_responses}",
    ]
    for m in day_msgs:
        hash_parts.append(
            f"{m.id}:{m.direction}:{m.status}:{(m.subject or '')[:120]}:{_clean_message_text(m)[:400]}"
        )
    content_hash = hashlib.sha256("\n".join(hash_parts).encode("utf-8")).hexdigest()

    company = getattr(getattr(user, "profile", None), "company", None)
    report, _created = DailyUserEmailReport.objects.get_or_create(
        user=user,
        report_date=report_date,
        defaults={
            "company": company,
            **metrics,
        },
    )

    counts_changed = (
        report.emails_received != emails_received
        or report.emails_sent != emails_sent
        or report.sent_received_responses != sent_received_responses
        or report.pending_responses != pending_responses
        or report.company_id != (company.id if company else None)
    )
    if counts_changed:
        report.emails_received = emails_received
        report.emails_sent = emails_sent
        report.sent_received_responses = sent_received_responses
        report.pending_responses = pending_responses
        report.company = company

    if (
        not force
        and report.content_hash == content_hash
        and report.summary_status in (DailyUserEmailReport.SummaryStatus.READY, DailyUserEmailReport.SummaryStatus.SKIPPED)
        and report.overall_summary
    ):
        if counts_changed:
            report.save(update_fields=[
                "company", "emails_received", "emails_sent",
                "sent_received_responses", "pending_responses", "updated_at",
            ])
        return report

    if emails_received == 0 and emails_sent == 0:
        summary_text, next_action = _generate_daily_user_extractive_summary(user, report_date, metrics, day_msgs)
        report.overall_summary = summary_text
        report.recommended_actions = next_action
        report.summary_status = DailyUserEmailReport.SummaryStatus.SKIPPED
        report.summary_provider = "none"
        report.summary_model = ""
        report.summary_error = ""
        report.content_hash = content_hash
        report.generated_at = timezone.now()
        report.save()
        return report

    provider, api_key, model = _resolve_provider_and_key()
    timeout = timeout_override or int(_get_setting("EMAIL_SUMMARY_TIMEOUT", "15") or 15)
    max_retries = max_retries_override or max(1, int(_get_setting("EMAIL_SUMMARY_MAX_RETRIES", "2") or 2))

    if provider in ("gemini", "openai") and not api_key:
        provider = "extractive"
        model = "extractive-v1"

    if provider == "extractive":
        summary_text, next_action = _generate_daily_user_extractive_summary(user, report_date, metrics, day_msgs)
        report.overall_summary = summary_text
        report.recommended_actions = next_action
        report.summary_status = DailyUserEmailReport.SummaryStatus.READY
        report.summary_provider = "extractive"
        report.summary_model = model
        report.summary_error = ""
        report.content_hash = content_hash
        report.generated_at = timezone.now()
        report.save()
        return report

    prompt = _build_daily_user_llm_prompt(user, report_date, metrics, day_msgs)
    last_err = None
    for attempt in range(max_retries):
        try:
            used_model = model
            if provider == "gemini":
                summary_text, next_action, used_model = _call_gemini(
                    prompt, api_key, model, timeout, max_output_tokens=1536
                )
            else:
                summary_text, next_action = _call_openai(prompt, api_key, model, timeout)

            if not next_action:
                _, next_action = _generate_daily_user_extractive_summary(user, report_date, metrics, day_msgs)

            report.overall_summary = summary_text
            report.recommended_actions = next_action
            report.summary_status = DailyUserEmailReport.SummaryStatus.READY
            report.summary_provider = provider
            report.summary_model = used_model
            report.summary_error = ""
            report.content_hash = content_hash
            report.generated_at = timezone.now()
            report.save()
            return report
        except Exception as exc:
            last_err = str(exc)
            logger.warning(
                "Daily user email AI summary attempt %s/%s failed for user %s (%s): %s",
                attempt + 1, max_retries, user.id, provider, exc,
            )
            if attempt + 1 < max_retries:
                time.sleep(0.4 * (attempt + 1))

    fallback_text, fallback_action = _generate_daily_user_extractive_summary(user, report_date, metrics, day_msgs)
    report.overall_summary = fallback_text
    report.recommended_actions = fallback_action
    report.summary_status = DailyUserEmailReport.SummaryStatus.FAILED
    report.summary_provider = "extractive_fallback"
    report.summary_model = f"{provider}:{model}"
    report.summary_error = (last_err or "AI summarization failed")[:1000]
    report.content_hash = content_hash
    report.generated_at = timezone.now()
    report.save()
    return report


# ---------------------------------------------------------------------------
# Gemini AI Personalized Email Generation (Outreach, Inbox, Campaign)
# ---------------------------------------------------------------------------

def _retrieve_company_portfolio_from_vector_db(
    *,
    user,
    crm_ctx: Dict[str, Any],
    user_prompt: str = "",
) -> Tuple[str, List[str]]:
    """
    Query our PostgreSQL + pgvector RAG Knowledge Base (`rag` app) to retrieve
    our company portfolio, products, services, pricing, and value proposition
    relevant to the target outreach company's industry and offerings.
    Returns (portfolio_text, source_document_names).
    """
    try:
        from rag.models import KnowledgeBase, KnowledgeDocumentChunk
        from rag.services import knowledge_base_service, retrieval_service

        if user and getattr(user, "is_authenticated", False):
            kb_qs = knowledge_base_service.accessible_knowledge_bases(user).filter(is_active=True)
        else:
            kb_qs = KnowledgeBase.objects.filter(is_active=True)

        ready_kbs = [kb for kb in kb_qs if knowledge_base_service.ready_documents(kb).exists()]
        if not ready_kbs:
            return "", []

        query_parts = [
            crm_ctx.get("company_name") or "",
            crm_ctx.get("industry") or "",
            crm_ctx.get("offering_type") or "",
            " ".join((crm_ctx.get("products") or []) + (crm_ctx.get("services") or []) + (crm_ctx.get("solutions") or [])),
            user_prompt or "",
            "company portfolio products services solutions pricing capabilities",
        ]
        search_query = " ".join(p.strip() for p in query_parts if p and p.strip())[:800]

        chunks_text: List[str] = []
        source_names: List[str] = []

        try:
            res = retrieval_service.retrieve(
                ready_kbs,
                query_text=search_query,
                user=user if (user and getattr(user, "is_authenticated", False)) else None,
                top_k=5,
                threshold=0.05,
            )
            chosen = res.chunks or res.candidates[:5]
            for c in chosen:
                chunks_text.append(f"[{c.document_name}] {c.text[:900]}")
                if c.document_name and c.document_name not in source_names:
                    source_names.append(c.document_name)
        except Exception as vec_exc:
            logger.debug("Vector similarity search fallback to direct ready chunks: %s", vec_exc)

        if not chunks_text:
            db_chunks = (
                KnowledgeDocumentChunk.objects
                .select_related("document")
                .filter(
                    knowledge_base__in=ready_kbs,
                    knowledge_base__is_active=True,
                    document__status="READY",
                    document__is_active=True,
                )
                .order_by("document_id", "chunk_index")[:5]
            )
            for ch in db_chunks:
                doc_name = ch.document.original_filename
                chunks_text.append(f"[{doc_name}] {ch.text[:900]}")
                if doc_name and doc_name not in source_names:
                    source_names.append(doc_name)

        return "\n\n".join(chunks_text)[:3500], source_names
    except Exception as exc:
        logger.debug("Portfolio vector DB lookup skipped: %s", exc)
        return "", []


def _resolve_prospect_and_recipient_context(
    *,
    prospect_id: Optional[str] = None,
    recipient_emails: Optional[List[str]] = None,
    company_name: str = "",
    recipient_name: str = "",
    industry: str = "",
    country: str = "",
    phone_number: str = "",
) -> Dict[str, Any]:
    """
    Gather rich CRM context from Prospect / ProspectContact records when available,
    merged with any explicit context passed from the frontend.
    """
    from prospects.models import Prospect, ProspectContact

    ctx: Dict[str, Any] = {
        "company_name": (company_name or "").strip(),
        "recipient_name": (recipient_name or "").strip(),
        "recipient_designation": "",
        "recipient_email": "",
        "phone_number": (phone_number or "").strip(),
        "industry": (industry or "").strip(),
        "country": (country or "").strip(),
        "address": "",
        "offering_type": "",
        "products": [],
        "services": [],
        "solutions": [],
        "website": "",
        "company_structure": "",
        "ownership_sector": "",
        "prospect_obj": None,
    }

    emails_clean = [str(e).strip().lower() for e in (recipient_emails or []) if str(e).strip()]
    if emails_clean:
        ctx["recipient_email"] = emails_clean[0]

    prospect = None
    if prospect_id:
        try:
            prospect = (
                Prospect.objects
                .prefetch_related("key_contacts", "offerings")
                .filter(pk=prospect_id)
                .first()
            )
        except Exception:
            prospect = None

    contact = None
    if emails_clean:
        try:
            contact_qs = ProspectContact.objects.select_related("prospect").filter(
                official_email__iexact=emails_clean[0]
            )
            if prospect:
                contact = contact_qs.filter(prospect=prospect).first() or contact_qs.first()
            else:
                contact = contact_qs.first()
                if contact and contact.prospect:
                    prospect = contact.prospect
        except Exception:
            contact = None

    if not prospect and emails_clean:
        try:
            prospect = (
                Prospect.objects
                .prefetch_related("key_contacts", "offerings")
                .filter(official_email_address__iexact=emails_clean[0])
                .first()
            )
        except Exception:
            prospect = None

    if prospect:
        ctx["prospect_obj"] = prospect
        if not ctx["company_name"]:
            ctx["company_name"] = prospect.company_name or ""
        if not ctx["industry"]:
            ctx["industry"] = prospect.primary_industries or ""
        if not ctx["country"]:
            ctx["country"] = prospect.country_head_office or ""
        if not ctx["phone_number"]:
            ctx["phone_number"] = prospect.official_phone_number or ""
        ctx["address"] = prospect.complete_address or ""
        ctx["offering_type"] = prospect.primary_offering_type or ""
        ctx["website"] = prospect.official_website_url or ""
        ctx["company_structure"] = prospect.company_structure or ""
        ctx["ownership_sector"] = prospect.ownership_sector or ""

        try:
            offerings = list(prospect.offerings.all())
            ctx["products"] = [o.name for o in offerings if o.offering_type == "PRODUCT" and o.name][:6]
            ctx["services"] = [o.name for o in offerings if o.offering_type == "SERVICE" and o.name][:6]
            ctx["solutions"] = [o.name for o in offerings if o.offering_type == "SOLUTION" and o.name][:6]
        except Exception:
            pass

        if not contact:
            try:
                contacts = list(prospect.key_contacts.all())
                if contacts:
                    contact = contacts[0]
            except Exception:
                pass

    if contact:
        if not ctx["recipient_name"] and contact.contact_name:
            ctx["recipient_name"] = contact.contact_name
        if contact.designation:
            ctx["recipient_designation"] = contact.designation
        if not ctx["recipient_email"] and contact.official_email:
            ctx["recipient_email"] = contact.official_email
        if not ctx["phone_number"] and getattr(contact, "phone_number", None):
            ctx["phone_number"] = contact.phone_number

    return ctx


def _build_personalized_email_prompt(
    *,
    user,
    user_prompt: str,
    source_context: str,
    tone: str,
    crm_ctx: Dict[str, Any],
    campaign_name: str = "",
    current_subject: str = "",
    current_body: str = "",
) -> str:
    sender_name = (user.get_full_name() or user.username or "Sales Team").strip()
    sender_company = ""
    try:
        profile = getattr(user, "profile", None)
        if profile and getattr(profile, "company", None):
            sender_company = profile.company.name or ""
    except Exception:
        pass

    context_lines = []
    if crm_ctx.get("company_name"):
        context_lines.append(f"- Prospect Company Name: {crm_ctx['company_name']}")
    if crm_ctx.get("recipient_name"):
        desig = f" ({crm_ctx['recipient_designation']})" if crm_ctx.get("recipient_designation") else ""
        context_lines.append(f"- Recipient Name: {crm_ctx['recipient_name']}{desig}")
    if crm_ctx.get("recipient_email"):
        context_lines.append(f"- Prospect Email Address: {crm_ctx['recipient_email']}")
    if crm_ctx.get("phone_number"):
        context_lines.append(f"- Prospect Mobile / Phone Number: {crm_ctx['phone_number']}")
    if crm_ctx.get("industry"):
        context_lines.append(f"- Primary Industries: {crm_ctx['industry']}")
    if crm_ctx.get("country"):
        context_lines.append(f"- Country / Location: {crm_ctx['country']}")
    if crm_ctx.get("address"):
        context_lines.append(f"- Complete Address: {crm_ctx['address']}")
    if crm_ctx.get("website"):
        context_lines.append(f"- Official Website: {crm_ctx['website']}")
    if crm_ctx.get("company_structure"):
        context_lines.append(f"- Company Structure: {crm_ctx['company_structure']}")
    if crm_ctx.get("ownership_sector"):
        context_lines.append(f"- Ownership Sector: {crm_ctx['ownership_sector']}")
    if crm_ctx.get("offering_type"):
        context_lines.append(f"- Primary Offering Type: {crm_ctx['offering_type']}")
    if crm_ctx.get("products"):
        context_lines.append(f"- Prospect Product Offerings: {', '.join(crm_ctx['products'])}")
    if crm_ctx.get("services"):
        context_lines.append(f"- Prospect Service Offerings: {', '.join(crm_ctx['services'])}")
    if crm_ctx.get("solutions"):
        context_lines.append(f"- Prospect Solution Offerings: {', '.join(crm_ctx['solutions'])}")
    if campaign_name:
        context_lines.append(f"- Campaign Name: {campaign_name}")
    if sender_company:
        context_lines.append(f"- Sender Organization: {sender_company}")
    context_lines.append(f"- Sender Name: {sender_name}")

    mode_instruction = ""
    if source_context == "CAMPAIGN":
        mode_instruction = (
            "This email is for a B2B Email Campaign. Make it engaging, personalized, and suitable "
            "for business decision-makers."
        )
    elif source_context == "INBOX":
        mode_instruction = (
            "This email is being composed in the user's business Email Inbox. Make it direct, clear, "
            "and personalized to the recipient."
        )
    else:
        mode_instruction = (
            "This email is an outreach email in the Outreach Workspace. Tailor it specifically to the "
            "prospect company, their industry, and key contact."
        )

    draft_section = ""
    if current_subject or current_body:
        draft_section = (
            "\nExisting Draft Context (optional reference if user asks to refine/rewrite):\n"
            f"Current Subject: {current_subject[:300]}\n"
            f"Current Body:\n{current_body[:1500]}\n"
        )

    portfolio_section = ""
    if crm_ctx.get("portfolio_text"):
        portfolio_section = (
            "\nOur Company Portfolio & Offerings (Retrieved from Vector DB Knowledge Base):\n"
            f"{crm_ctx['portfolio_text']}\n"
        )

    return (
        "You are an expert B2B sales and executive communication copywriter powered by Google Gemini AI.\n"
        f"{mode_instruction}\n\n"
        "RULES:\n"
        "1. Analyze the Prospect's company name, mobile/phone number, email, product/service/solution offerings, "
        "and primary industries carefully.\n"
        "2. When 'Our Company Portfolio & Offerings (Retrieved from Vector DB Knowledge Base)' is provided below, "
        "connect our company's specific products, services, and strengths from our portfolio to the prospect company's "
        "business, industry, and offerings.\n"
        f"3. Write in a {tone or 'professional'} tone.\n"
        "4. Do NOT use fake placeholder brackets like [Your Name] or [Company Name] when real names are available; "
        f"sign off with '{sender_name}' (unless the user prompt specifies otherwise).\n"
        "5. Return STRICTLY valid JSON with two keys:\n"
        '   - "subject": A compelling, concise, personalized email subject line for this specific company.\n'
        '   - "body": The complete plain-text customized email body with clean paragraph breaks (\\n\\n).\n\n'
        "Target Outreach Company & Sender Context:\n"
        + ("\n".join(context_lines) if context_lines else "- General B2B recipient")
        + portfolio_section
        + draft_section
        + f"\nUser Prompt / Instructions:\n{user_prompt.strip()}\n"
    )


def _parse_generated_email_json(raw_text: str) -> Optional[Tuple[str, str]]:
    text = (raw_text or "").strip()
    if not text:
        return None
    fence_match = re.search(r"\{.*\}", text, re.DOTALL)
    if fence_match:
        try:
            data = json.loads(fence_match.group(0))
            if isinstance(data, dict):
                subj = str(data.get("subject") or data.get("email_subject") or "").strip()
                body = str(data.get("body") or data.get("email_body") or data.get("message") or "").strip()
                if body:
                    return subj[:480], body[:10000]
        except Exception:
            pass
    return None


def _generate_fallback_personalized_email(
    *,
    user,
    user_prompt: str,
    tone: str,
    crm_ctx: Dict[str, Any],
    campaign_name: str = "",
) -> Tuple[str, str]:
    sender_name = (user.get_full_name() or user.username or "Lead Qualification Team").strip()
    company = (crm_ctx.get("company_name") or "").strip()
    recipient_name = (crm_ctx.get("recipient_name") or "").strip()
    if not recipient_name and crm_ctx.get("recipient_email"):
        local_part = crm_ctx["recipient_email"].split("@")[0].replace(".", " ").replace("_", " ").strip()
        if local_part and not local_part.isdigit():
            recipient_name = local_part.title()
    if not recipient_name:
        recipient_name = f"{company} Team" if company else "there"

    industry = (crm_ctx.get("industry") or "").strip()
    country = (crm_ctx.get("country") or "").strip()
    offerings = (crm_ctx.get("products") or []) + (crm_ctx.get("services") or []) + (crm_ctx.get("solutions") or [])

    prompt_clean = (user_prompt or "").strip()
    prompt_low = prompt_clean.lower()

    # Build a tailored subject line based on the user's prompt & context
    if "follow-up" in prompt_low or "follow up" in prompt_low or tone == "followup":
        subject = f"Following Up — {company}" if company else "Quick Follow-Up on Our Previous Conversation"
    elif "walkthrough" in prompt_low or "demo" in prompt_low:
        subject = f"Product Walkthrough & Overview for {company}" if company else "Invitation: Personalized Solution Walkthrough"
    elif "partnership" in prompt_low or "collaborat" in prompt_low:
        subject = f"Strategic Partnership Opportunity — {company}" if company else "Exploring a Strategic Partnership"
    elif campaign_name:
        subject = f"{campaign_name}{f' — {company}' if company else ''}"
    elif company:
        subject = f"Exploring Strategic Alignment & Solutions for {company}"
    else:
        subject = "Introduction & Opportunity to Connect"

    greeting = f"Dear {recipient_name}," if tone != "friendly" else f"Hi {recipient_name},"

    # Extract core topic from user prompt without echoing raw meta-instructions like "Write a personalized..."
    topic_cleaned = re.sub(
        r"^(?:please\s+)?(?:write|draft|create|generate|compose|send)\s+(?:a|an|the)?\s*(?:personalized|polite|concise|short|warm|professional|executive|high-converting|b2b|business)?\s*(?:business\s+|outreach\s+|campaign\s+|follow-up\s+|introduction\s+|introductory\s+)?(?:email|message)?\s*(?:about|regarding|for|to|that|highlighting|introducing|announcing|sharing)?\s*",
        "",
        prompt_clean,
        flags=re.IGNORECASE,
    ).strip().rstrip(".")

    body_paragraphs = [greeting]

    if "follow-up" in prompt_low or "follow up" in prompt_low or tone == "followup":
        if company:
            body_paragraphs.append(
                f"I hope you are having a productive week. I wanted to follow up on our previous outreach regarding {company} and see if you had a chance to review our note."
            )
        else:
            body_paragraphs.append(
                "I hope you are having a productive week. I wanted to quickly follow up on our previous conversation and check if this is a good time to connect."
            )
        if topic_cleaned and len(topic_cleaned) > 12:
            body_paragraphs.append(
                f"Specifically, we would love to discuss {topic_cleaned[0].lower() + topic_cleaned[1:] if len(topic_cleaned) > 1 else topic_cleaned} and share how our team can support your upcoming priorities."
            )
    else:
        if company and industry:
            loc_str = f" in {country}" if country else ""
            off_str = f", particularly your offerings in {', '.join(offerings[:3])}" if offerings else ""
            body_paragraphs.append(
                f"I hope this email finds you well. I have been following {company}'s work across the {industry} sector{loc_str}{off_str}, and I wanted to reach out directly."
            )
        elif company:
            off_str = f" and your focus on {', '.join(offerings[:3])}" if offerings else ""
            body_paragraphs.append(
                f"I hope this email finds you well. I am reaching out after reviewing {company}'s business profile{off_str} to explore how our portfolio can support your key initiatives."
            )
        else:
            body_paragraphs.append(
                "I hope this email finds you well. I am reaching out to introduce our team and share how we help organizations streamline operations, accelerate growth, and achieve measurable results."
            )

        portfolio_text = (crm_ctx.get("portfolio_text") or "").strip()
        portfolio_snippet = ""
        if portfolio_text:
            clean_port = re.sub(r"\[[^\]]+\]\s*", "", portfolio_text).strip()
            first_sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", clean_port) if len(s.strip()) > 20]
            if first_sentences:
                portfolio_snippet = " ".join(first_sentences[:2])[:320]

        if topic_cleaned and len(topic_cleaned) > 10:
            if portfolio_snippet:
                body_paragraphs.append(
                    f"Based on our company portfolio ({portfolio_snippet}), our goal is to help {company or 'your team'} {topic_cleaned[0].lower() + topic_cleaned[1:] if len(topic_cleaned) > 1 else topic_cleaned} with solutions tailored to your {industry or 'business'} operations."
                )
            else:
                body_paragraphs.append(
                    f"Our goal is to help {company or 'your team'} {topic_cleaned[0].lower() + topic_cleaned[1:] if len(topic_cleaned) > 1 else topic_cleaned}, delivering tailored solutions that align with your business objectives."
                )
        elif portfolio_snippet:
            body_paragraphs.append(
                f"From our company portfolio — {portfolio_snippet} — we see strong synergy with {company or 'your organization'}'s {industry or 'core'} offerings."
            )
        else:
            body_paragraphs.append(
                "We specialize in delivering tailored solutions that help teams improve efficiency, reduce operational friction, and drive sustainable ROI."
            )

    phone_num = (crm_ctx.get("phone_number") or "").strip()
    if tone == "concise":
        call_note = f" (or I can reach out to your office at {phone_num})" if phone_num else ""
        body_paragraphs.append(
            f"Would you be open to a brief 10-minute call this week{call_note} to see if there is a fit?"
        )
    else:
        call_note = f" — or let me know if {phone_num} is a convenient number for a quick introductory call" if phone_num else ""
        body_paragraphs.append(
            f"Would you be available for a brief 15-minute introductory call this week{call_note} to explore potential alignment? If another colleague is the best point of contact for this discussion, please feel free to point me in their direction."
        )

    signoff = "Warm regards," if tone == "friendly" else "Best regards,"
    body_paragraphs.append(f"{signoff}\n{sender_name}")

    return subject[:480], "\n\n".join(body_paragraphs)


def _call_gemini_for_email_generation(prompt: str, api_key: str, model: str, timeout: int = 8) -> Tuple[str, str, str]:
    from django.core.cache import cache

    candidate_models = []
    cached_winner = cache.get("gemini_working_free_model")
    for cand in [
        cached_winner,
        "gemini-flash-lite-latest",
        "gemini-flash-latest",
        "gemini-3.8-flash",
        "gemini-3.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-2.5-flash-lite",
        model,
    ]:
        if cand and cand not in candidate_models:
            candidate_models.append(cand)
    candidate_models = candidate_models[:5]

    per_req_timeout = max(6, min(int(timeout or 12), 15))

    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 1200,
            "responseMimeType": "application/json",
        },
    }).encode("utf-8")

    def _invoke(cand_model: str) -> Tuple[str, str, str]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{cand_model}:generateContent?key={api_key}"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=per_req_timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        candidates = data.get("candidates") or []
        parts = (((candidates[0] if candidates else {}).get("content") or {}).get("parts") or [])
        raw_text = "".join(str(p.get("text") or "") for p in parts)
        parsed = _parse_generated_email_json(raw_text)
        if not parsed:
            raise ValueError(f"Gemini ({cand_model}) returned invalid email JSON")
        cache.set("gemini_working_free_model", cand_model, 3600)
        return parsed[0], parsed[1], cand_model

    last_error = None
    for idx, cand_model in enumerate(candidate_models):
        try:
            return _invoke(cand_model)
        except urllib.error.HTTPError as http_err:
            err_body = ""
            try:
                err_body = http_err.read().decode("utf-8", errors="ignore")[:300]
            except Exception:
                pass
            last_error = f"HTTP {http_err.code} on {cand_model}: {err_body or http_err.reason}"
            if http_err.code in (401, 403):
                # Invalid key / Vertex token passed to AI Studio endpoint: fail fast immediately
                break
            if http_err.code in (400, 404, 429) and idx + 1 < len(candidate_models):
                continue
        except Exception as exc:
            last_error = f"{cand_model}: {exc}"
            # On socket/read timeout, fail fast so we return within the frontend's timeout window
            if "timed out" in str(exc).lower() or "timeout" in str(exc).lower():
                break
            if idx + 1 < len(candidate_models):
                continue
            break

    raise ValueError(last_error or "Gemini email generation failed")


def generate_personalized_email(
    *,
    user,
    user_prompt: str,
    source_context: str = "OUTREACH",
    tone: str = "professional",
    prospect_id: Optional[str] = None,
    recipient_emails: Optional[List[str]] = None,
    company_name: str = "",
    recipient_name: str = "",
    industry: str = "",
    country: str = "",
    phone_number: str = "",
    campaign_name: str = "",
    current_subject: str = "",
    current_body: str = "",
) -> Dict[str, Any]:
    """
    Generate a personalized subject + body using Google Gemini AI (with resilient
    model discovery and smart template fallback so the user is never blocked) and
    persist an EmailAIGenerationLog audit entry.
    """
    from .models import EmailAIGenerationLog

    source_norm = str(source_context or "OUTREACH").strip().upper()
    if source_norm not in ("OUTREACH", "INBOX", "CAMPAIGN"):
        source_norm = "OUTREACH"

    crm_ctx = _resolve_prospect_and_recipient_context(
        prospect_id=prospect_id,
        recipient_emails=recipient_emails,
        company_name=company_name,
        recipient_name=recipient_name,
        industry=industry,
        country=country,
        phone_number=phone_number,
    )
    portfolio_text, portfolio_sources = _retrieve_company_portfolio_from_vector_db(
        user=user, crm_ctx=crm_ctx, user_prompt=user_prompt
    )
    if portfolio_text:
        crm_ctx["portfolio_text"] = portfolio_text
        crm_ctx["portfolio_sources"] = portfolio_sources

    llm_prompt = _build_personalized_email_prompt(
        user=user,
        user_prompt=user_prompt,
        source_context=source_norm,
        tone=tone,
        crm_ctx=crm_ctx,
        campaign_name=campaign_name,
        current_subject=current_subject,
        current_body=current_body,
    )

    api_key = _get_setting("GEMINI_API_KEY", "")
    model = _get_setting("EMAIL_AI_MODEL", _get_setting("EMAIL_SUMMARY_MODEL", "gemini-2.5-flash"))
    timeout = int(_get_setting("EMAIL_AI_TIMEOUT", "8") or 8)

    subject = ""
    body = ""
    provider = "gemini"
    used_model = model
    status_val = EmailAIGenerationLog.Status.SUCCESS
    err_msg = ""

    if api_key:
        try:
            subject, body, used_model = _call_gemini_for_email_generation(
                llm_prompt, api_key=api_key, model=model, timeout=timeout
            )
        except Exception as exc:
            err_msg = str(exc)[:1000]
            logger.warning("Gemini personalized email generation fallback triggered: %s", err_msg)
            subject, body = _generate_fallback_personalized_email(
                user=user,
                user_prompt=user_prompt,
                tone=tone,
                crm_ctx=crm_ctx,
                campaign_name=campaign_name,
            )
            provider = "fallback"
            used_model = "smart-template-v1"
            status_val = EmailAIGenerationLog.Status.FALLBACK
    else:
        subject, body = _generate_fallback_personalized_email(
            user=user,
            user_prompt=user_prompt,
            tone=tone,
            crm_ctx=crm_ctx,
            campaign_name=campaign_name,
        )
        provider = "fallback"
        used_model = "smart-template-v1"
        status_val = EmailAIGenerationLog.Status.FALLBACK
        err_msg = "GEMINI_API_KEY not configured; used personalized smart template."

    log_entry = None
    try:
        log_entry = EmailAIGenerationLog.objects.create(
            user=user,
            prospect=crm_ctx.get("prospect_obj"),
            source_context=source_norm,
            user_prompt=user_prompt,
            tone=tone or "professional",
            generated_subject=subject,
            generated_body=body,
            provider=provider,
            model_used=used_model,
            status=status_val,
            error_message=err_msg,
        )
    except Exception as log_err:
        logger.debug("EmailAIGenerationLog create skipped: %s", log_err)

    return {
        "id": str(log_entry.id) if log_entry else None,
        "subject": subject,
        "body": body,
        "provider": provider,
        "model": used_model,
        "status": status_val,
        "context_used": {
            "company_name": crm_ctx.get("company_name") or "",
            "recipient_name": crm_ctx.get("recipient_name") or "",
            "phone_number": crm_ctx.get("phone_number") or "",
            "industry": crm_ctx.get("industry") or "",
            "country": crm_ctx.get("country") or "",
            "offerings": (crm_ctx.get("products") or []) + (crm_ctx.get("services") or []) + (crm_ctx.get("solutions") or []),
            "portfolio_sources": crm_ctx.get("portfolio_sources") or [],
        },
    }
