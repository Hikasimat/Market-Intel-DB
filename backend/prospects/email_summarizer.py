"""
Configurable AI summarization service for Market Intel DB email conversations.

Supports:
  - Google Gemini REST API (when GEMINI_API_KEY is configured)
  - OpenAI Chat Completions REST API (when OPENAI_API_KEY is configured)
  - Deterministic extractive fallback (when unconfigured or on API unavailability)

Strictly summarizes ONLY facts present in the recorded thread messages without
fabricating details. Never blocks email sends or inbox sync.
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
from typing import Optional, Tuple

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
    # Bound prompt size safely while preserving latest exchanges
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
    # Strip optional markdown code fences
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
        # Exclude embedding, image-only, tts, robotics, or computer-use models
        if any(skip in low for skip in ("embedding", "imagen", "veo", "tts", "audio", "robotics", "aqa")):
            continue
        discovered.append(short_name)

    # Prefer newest Flash-Lite / Flash free-tier models first
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


def _call_gemini(prompt: str, api_key: str, model: str, timeout: int) -> Tuple[str, str, str]:
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
            "maxOutputTokens": 1024,
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

    # Dynamically query /v1beta/models to find any currently available free Flash model on this API key
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
    from .models import EmailThread, EmailThreadMessage

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

    # If provider requested external AI without an API key, degrade safely to extractive
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

    # Graceful failure handling: compute honest fallback text and record exact failure reason
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
            # Inside unit-test transaction wrappers, avoid rogue SQLite background threads;
            # generate synchronously using fast local fallback or mocked provider only if needed.
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

