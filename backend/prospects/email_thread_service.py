"""
Normalized Email Thread Ingestion, Matching & Synchronization Service.

Captures:
  1. Outbound Outreach emails (OutreachEmailViewSet.create)
  2. Outbound Inbox emails (GmailMailboxViewSet.send_email_action)
  3. Outbound Bulk Campaign emails (campaign_service.send_single_campaign_recipient)
  4. Inbound & synced Gmail/IMAP replies (sync_imap / sync_mailbox_messages)

Strict ownership & matching boundaries:
  - Every EmailThread and EmailThreadMessage is scoped to its authorized owner (User).
  - Incoming replies are matched ONLY within that owner's threads by:
      1) external_thread_id
      2) In-Reply-To / References matching rfc_message_id
      3) Normalized subject + correspondent email
  - Ambiguous/unmatched inbound emails remain on the owner's authorized mailbox with
    match_status='UNMATCHED' and are never attached to another user or wrong prospect.
  - Zero credentials, OAuth tokens, or BCC recipients are stored or exposed.
"""

import logging
import re
from datetime import datetime, timezone as dt_timezone
from email.utils import parseaddr, parsedate_to_datetime
from typing import Iterable, List, Optional, Tuple

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r"[\w.\-+%]+@[\w.\-]+\.\w+")
_SUBJECT_PREFIX_RE = re.compile(r"^(?:\s*(?:re|fwd?|fw)\s*:\s*)+", re.IGNORECASE)


def normalize_subject(subject: str) -> str:
    raw = str(subject or "").strip()
    if not raw:
        return ""
    cleaned = _SUBJECT_PREFIX_RE.sub("", raw).strip()
    return re.sub(r"\s+", " ", cleaned).lower()[:480]


def extract_email_address(raw_header: str) -> Tuple[str, str]:
    name, addr = parseaddr(str(raw_header or ""))
    addr_clean = (addr or "").strip().lower()
    if not addr_clean:
        m = _EMAIL_RE.search(str(raw_header or ""))
        addr_clean = m.group(0).lower() if m else ""
    return addr_clean, (name or "").strip()[:250]


def parse_email_addresses(raw_value) -> List[str]:
    if not raw_value:
        return []
    if isinstance(raw_value, (list, tuple)):
        joined = ", ".join(str(x) for x in raw_value if x)
    else:
        joined = str(raw_value)
    seen = []
    for match in _EMAIL_RE.findall(joined):
        low = match.lower().strip()
        if low and low not in seen:
            seen.append(low)
    return seen


def compute_snippet(body_text: str = "", body_html: str = "", max_len: int = 240) -> str:
    text = (body_text or "").strip()
    if not text and body_html:
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", body_html)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_len]


def _parse_email_date(raw_date: str):
    if not raw_date:
        return timezone.now()
    try:
        dt = parsedate_to_datetime(str(raw_date))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=dt_timezone.utc)
        return dt
    except Exception:
        return timezone.now()


def _clean_rfc_id(val: str) -> str:
    return str(val or "").strip().strip("<>").strip()[:490]


def _parse_references_list(raw_refs: str) -> List[str]:
    if not raw_refs:
        return []
    ids = []
    for token in re.split(r"[\s,]+", str(raw_refs)):
        clean = _clean_rfc_id(token)
        if clean and "@" in clean:
            ids.append(clean)
    return ids


def _get_user_company(user):
    if not user:
        return None
    profile = getattr(user, "profile", None)
    return getattr(profile, "company", None) if profile else None


def _is_usable_external_thread_id(thread_id: str, rfc_message_id: str = "") -> bool:
    tid = str(thread_id or "").strip()
    if not tid:
        return False
    # OutreachEmail historically initialized thread_id = message_id placeholder containing '@'
    if rfc_message_id and tid.strip("<>") == rfc_message_id.strip("<>"):
        return False
    if "@" in tid and "<" not in tid and "." in tid:
        return False
    return True


def _refresh_thread_aggregates(thread, latest_msg=None) -> None:
    from .models import EmailThread, EmailThreadMessage

    msgs = EmailThreadMessage.objects.filter(thread=thread).order_by("sent_at", "created_at")
    count = msgs.count()
    last = latest_msg or msgs.last()

    update_fields = ["message_count"]
    thread.message_count = count

    if last:
        eff_dt = last.sent_at or last.created_at
        if eff_dt and (not thread.last_message_at or eff_dt >= thread.last_message_at):
            thread.last_message_at = eff_dt
            thread.last_direction = last.direction
            thread.last_snippet = last.snippet or compute_snippet(last.body_text, last.body_html)
            update_fields.extend(["last_message_at", "last_direction", "last_snippet"])

        if last.direction == EmailThreadMessage.Direction.INBOUND:
            thread.status = (
                EmailThread.Status.REPLIED
                if thread.match_status == EmailThread.MatchStatus.MATCHED or thread.prospect_id
                else EmailThread.Status.UNMATCHED
            )
            update_fields.append("status")
        elif last.status == EmailThreadMessage.Status.FAILED:
            thread.status = EmailThread.Status.FAILED
            update_fields.append("status")
        elif thread.status not in (EmailThread.Status.REPLIED, EmailThread.Status.UNMATCHED):
            thread.status = EmailThread.Status.WAITING_REPLY
            update_fields.append("status")

    thread.save(update_fields=list(set(update_fields)))


def record_outbound_email_in_thread(
    *,
    owner,
    from_email: str,
    sender_name: str = "",
    to_emails: Iterable[str] = (),
    cc_emails: Iterable[str] = (),
    subject: str = "",
    body_text: str = "",
    body_html: str = "",
    source: str = "OUTREACH",
    status: str = "SENT",
    external_thread_id: str = "",
    external_message_id: str = "",
    rfc_message_id: str = "",
    in_reply_to: str = "",
    references_header: str = "",
    prospect=None,
    prospect_contact=None,
    outreach_email=None,
    campaign_recipient=None,
    attachments_metadata: Optional[list] = None,
    sent_at=None,
    dedup_key: str = "",
    trigger_summary: bool = True,
):
    """
    Create or attach an outbound email to an owner-scoped EmailThread and schedule summary.
    Never stores BCC recipients.
    """
    from .models import EmailThread, EmailThreadMessage
    from email_ai.services import schedule_thread_summary

    if not owner:
        return None, None

    to_list = parse_email_addresses(list(to_emails or []))
    cc_list = parse_email_addresses(list(cc_emails or []))
    primary_recipient = to_list[0] if to_list else (cc_list[0] if cc_list else "")
    norm_subj = normalize_subject(subject)
    clean_rfc = _clean_rfc_id(rfc_message_id)
    ext_tid = str(external_thread_id or "").strip() if _is_usable_external_thread_id(external_thread_id, clean_rfc) else ""
    eff_sent_at = sent_at or timezone.now()

    if not dedup_key:
        if outreach_email is not None:
            dedup_key = f"outreach:{outreach_email.id}"
        elif external_message_id:
            dedup_key = f"ext:{external_message_id}"
        elif clean_rfc:
            dedup_key = f"rfc:{clean_rfc}"
        else:
            dedup_key = f"out:{owner.id}:{eff_sent_at.timestamp()}:{norm_subj[:40]}:{primary_recipient}"

    existing = EmailThreadMessage.objects.select_related("thread").filter(
        owner=owner, dedup_key=dedup_key
    ).first()
    if existing:
        return existing.thread, existing

    thread = None
    with transaction.atomic():
        if ext_tid:
            thread = EmailThread.objects.filter(owner=owner, external_thread_id=ext_tid).first()

        if not thread and in_reply_to:
            ref_msg = EmailThreadMessage.objects.select_related("thread").filter(
                owner=owner, rfc_message_id=_clean_rfc_id(in_reply_to)
            ).first()
            if ref_msg:
                thread = ref_msg.thread

        if not thread and norm_subj and len(norm_subj) >= 3 and primary_recipient:
            thread = EmailThread.objects.filter(
                owner=owner,
                normalized_subject=norm_subj,
                correspondent_email=primary_recipient,
            ).order_by("-last_message_at").first()

        if prospect_contact is None and primary_recipient:
            from .models import ProspectContact
            prospect_contact = ProspectContact.objects.select_related("prospect").filter(
                official_email__iexact=primary_recipient
            ).first()
            if prospect_contact and prospect is None:
                prospect = prospect_contact.prospect

        is_matched = bool(prospect or prospect_contact)
        if not thread:
            corr_name = ""
            if prospect_contact and prospect_contact.contact_name:
                corr_name = prospect_contact.contact_name
            elif prospect and prospect.company_name:
                corr_name = prospect.company_name

            thread = EmailThread.objects.create(
                owner=owner,
                company=_get_user_company(owner),
                prospect=prospect,
                prospect_contact=prospect_contact,
                external_thread_id=ext_tid,
                mailbox_email=(from_email or "").strip().lower(),
                correspondent_email=primary_recipient,
                correspondent_name=corr_name,
                subject=(subject or "")[:490],
                normalized_subject=norm_subj,
                match_status=(
                    EmailThread.MatchStatus.MATCHED if is_matched else EmailThread.MatchStatus.UNMATCHED
                ),
                status=(
                    EmailThread.Status.FAILED
                    if status == EmailThreadMessage.Status.FAILED
                    else EmailThread.Status.WAITING_REPLY
                ),
                last_direction=EmailThread.Direction.OUTBOUND,
                last_message_at=eff_sent_at,
                last_snippet=compute_snippet(body_text, body_html),
            )
        else:
            t_fields = []
            if ext_tid and not thread.external_thread_id:
                thread.external_thread_id = ext_tid
                t_fields.append("external_thread_id")
            if prospect and not thread.prospect_id:
                thread.prospect = prospect
                thread.match_status = EmailThread.MatchStatus.MATCHED
                t_fields.extend(["prospect", "match_status"])
            if prospect_contact and not thread.prospect_contact_id:
                thread.prospect_contact = prospect_contact
                thread.match_status = EmailThread.MatchStatus.MATCHED
                t_fields.extend(["prospect_contact", "match_status"])
            if t_fields:
                thread.save(update_fields=list(set(t_fields)))

        try:
            msg_obj = EmailThreadMessage.objects.create(
                thread=thread,
                owner=owner,
                outreach_email=outreach_email,
                campaign_recipient=campaign_recipient,
                direction=EmailThreadMessage.Direction.OUTBOUND,
                source=source,
                status=status,
                external_message_id=str(external_message_id or "")[:250],
                external_thread_id=ext_tid,
                rfc_message_id=clean_rfc,
                in_reply_to=_clean_rfc_id(in_reply_to),
                references_header=str(references_header or "")[:2000],
                dedup_key=dedup_key[:250],
                sender_email=(from_email or "").strip().lower(),
                sender_name=(sender_name or "")[:250],
                to_emails=to_list,
                cc_emails=cc_list,
                subject=(subject or "")[:490],
                body_text=body_text or "",
                body_html=body_html or "",
                snippet=compute_snippet(body_text, body_html),
                attachments_metadata=list(attachments_metadata or []),
                sent_at=eff_sent_at,
            )
        except IntegrityError:
            existing = EmailThreadMessage.objects.select_related("thread").filter(
                owner=owner, dedup_key=dedup_key[:250]
            ).first()
            return (existing.thread if existing else thread), existing

        _refresh_thread_aggregates(thread, msg_obj)

    if trigger_summary:
        schedule_thread_summary(thread.id)

    return thread, msg_obj


def update_outbound_send_result(
    thread_message_id,
    *,
    external_message_id: str = "",
    external_thread_id: str = "",
    status: Optional[str] = None,
    error_message: str = "",
) -> None:
    from .models import EmailThread, EmailThreadMessage
    from email_ai.services import schedule_thread_summary

    try:
        msg = EmailThreadMessage.objects.select_related("thread").filter(pk=thread_message_id).first()
        if not msg:
            return

        fields = []
        if external_message_id and msg.external_message_id != external_message_id:
            msg.external_message_id = str(external_message_id)[:250]
            fields.append("external_message_id")
        if external_thread_id and _is_usable_external_thread_id(external_thread_id):
            msg.external_thread_id = str(external_thread_id)[:250]
            fields.append("external_thread_id")
            if not msg.thread.external_thread_id:
                msg.thread.external_thread_id = str(external_thread_id)[:250]
                msg.thread.save(update_fields=["external_thread_id"])
        if status and msg.status != status:
            msg.status = status
            fields.append("status")
        if error_message:
            msg.error_message = str(error_message)[:1500]
            fields.append("error_message")
        if fields:
            msg.save(update_fields=fields)

        if status == EmailThreadMessage.Status.FAILED:
            msg.thread.status = EmailThread.Status.FAILED
            msg.thread.save(update_fields=["status"])
            schedule_thread_summary(msg.thread.id, force=True)
    except Exception as exc:
        logger.debug("update_outbound_send_result skipped (%s): %s", thread_message_id, exc)


def _match_thread_for_synced_message(
    owner,
    mailbox_email: str,
    correspondent_email: str,
    external_thread_id: str,
    rfc_message_id: str,
    in_reply_to: str,
    references_header: str,
    subject: str,
):
    from .models import EmailThread, EmailThreadMessage, OutreachEmail

    ext_tid = str(external_thread_id or "").strip()
    norm_subj = normalize_subject(subject)

    # 1. Exact Gmail/provider thread ID on this owner's threads
    if ext_tid:
        thread = EmailThread.objects.filter(owner=owner, external_thread_id=ext_tid).first()
        if thread:
            return thread, None

        # Also check legacy OutreachEmail owned by this user
        oe = OutreachEmail.objects.select_related("prospect").filter(
            created_by=owner, thread_id=ext_tid
        ).first()
        if oe:
            return None, oe

    # 2. In-Reply-To / References RFC Message-ID chain within this owner's messages
    ref_candidates = []
    if in_reply_to:
        ref_candidates.append(_clean_rfc_id(in_reply_to))
    ref_candidates.extend(_parse_references_list(references_header))
    ref_candidates = [c for c in ref_candidates if c]

    if ref_candidates:
        parent_msg = EmailThreadMessage.objects.select_related("thread").filter(
            owner=owner, rfc_message_id__in=ref_candidates
        ).order_by("-sent_at").first()
        if parent_msg:
            return parent_msg.thread, parent_msg.outreach_email

        oe_q = Q()
        for rc in ref_candidates[:5]:
            oe_q |= Q(message_id__icontains=rc)
        oe = OutreachEmail.objects.select_related("prospect").filter(
            created_by=owner
        ).filter(oe_q).first()
        if oe:
            return None, oe

    # 3. Normalized subject + exact correspondent email on this owner's threads
    if norm_subj and len(norm_subj) >= 3 and correspondent_email:
        thread = EmailThread.objects.filter(
            owner=owner,
            normalized_subject=norm_subj,
            correspondent_email=correspondent_email.lower(),
        ).order_by("-last_message_at").first()
        if thread:
            return thread, None

        oe = OutreachEmail.objects.select_related("prospect").filter(
            created_by=owner,
            subject__icontains=norm_subj[:120],
            recipients__email_address__iexact=correspondent_email,
        ).order_by("-sent_at").first()
        if oe:
            return None, oe

    return None, None


def sync_mailbox_messages(cred, limit: int = 30) -> dict:
    """
    Sync Gmail INBOX messages for `cred.user`, persist new EmailThreadMessages
    idempotently, update matching OutreachEmail & CommunicationActivity records,
    and schedule AI thread summaries for newly arrived messages.
    Strict user/mailbox boundary: never attaches emails to another user.
    """
    from accounts.oauth_services import GmailOAuthService

    owner = getattr(cred, "user", None)
    if not owner:
        return {"synced": 0, "skipped": 0, "threads_updated": 0}

    res = GmailOAuthService.fetch_messages(cred, folder="INBOX", limit=limit, user=owner)
    raw_messages = res.get("messages", []) or []
    return ingest_fetched_messages(cred, raw_messages)


def ingest_fetched_messages(cred, raw_messages: list) -> dict:
    """
    Idempotently persist already-fetched Gmail message metadata dicts into
    EmailThread / EmailThreadMessage for `cred.user`.
    """
    from accounts.oauth_services import GmailOAuthService
    from .models import (
        CommunicationActivity,
        EmailThread,
        EmailThreadMessage,
        Prospect,
        ProspectContact,
    )
    from email_ai.services import schedule_thread_summary

    owner = getattr(cred, "user", None)
    if not owner or not raw_messages:
        return {"synced": 0, "skipped": 0, "threads_updated": 0}

    mailbox_email = (getattr(cred, "email", "") or "").strip().lower()
    synced = 0
    skipped = 0
    touched_threads = set()

    for m in raw_messages:
        msg_id = str(m.get("id") or m.get("uid") or "").strip()
        if not msg_id:
            continue

        rfc_mid = _clean_rfc_id(m.get("message_id") or "")
        ext_tid = str(m.get("thread_id") or m.get("threadId") or "").strip()
        dedup_key = f"gmail:{msg_id}"

        if EmailThreadMessage.objects.filter(owner=owner, dedup_key=dedup_key).exists():
            skipped += 1
            continue

        from_hdr = m.get("from", "")
        to_hdr = m.get("to", "")
        cc_hdr = m.get("cc", "")
        subject = m.get("subject", "") or ""
        in_reply_to = m.get("in_reply_to", "") or ""
        references_header = m.get("references", "") or ""
        snippet = m.get("snippet", "") or ""

        from_email, from_name = extract_email_address(from_hdr)
        to_list = parse_email_addresses(to_hdr)
        cc_list = parse_email_addresses(cc_hdr)

        is_outbound = bool(mailbox_email and from_email == mailbox_email)
        direction = (
            EmailThreadMessage.Direction.OUTBOUND
            if is_outbound
            else EmailThreadMessage.Direction.INBOUND
        )
        correspondent_email = (to_list[0] if (is_outbound and to_list) else from_email)
        correspondent_name = "" if is_outbound else from_name

        # Fetch full body + safe attachment metadata only for net-new messages
        body_text = ""
        body_html = ""
        safe_attachments = []
        try:
            body_info = GmailOAuthService.fetch_message_body(cred, msg_id) or {}
            body_text = body_info.get("text_body") or ""
            body_html = body_info.get("html_body") or ""
            if not body_text.strip() and body_html:
                body_text = compute_snippet(body_html=body_html, max_len=12000)
            for att in (body_info.get("attachments") or []):
                safe_attachments.append({
                    "filename": att.get("filename") or "attachment",
                    "content_type": att.get("mime_type") or att.get("content_type") or "application/octet-stream",
                    "size": int(att.get("size") or 0),
                    "attachment_id": str(att.get("attachment_id") or att.get("id") or ""),
                })
        except Exception as body_err:
            logger.debug("Body fetch skipped for msg %s (%s): %s", msg_id, owner.id, body_err)

        matched_thread, matched_oe = _match_thread_for_synced_message(
            owner=owner,
            mailbox_email=mailbox_email,
            correspondent_email=correspondent_email,
            external_thread_id=ext_tid,
            rfc_message_id=rfc_mid,
            in_reply_to=in_reply_to,
            references_header=references_header,
            subject=subject,
        )

        # Ensure legacy matched OutreachEmail is materialized into an EmailThread first
        if matched_thread is None and matched_oe is not None:
            matched_thread, _ = record_outbound_email_in_thread(
                owner=owner,
                from_email=matched_oe.from_email,
                sender_name=matched_oe.from_name or "",
                to_emails=list(matched_oe.recipients.values_list("email_address", flat=True)),
                subject=matched_oe.subject,
                body_text=compute_snippet(body_html=matched_oe.body, max_len=12000),
                body_html=matched_oe.body,
                source=EmailThreadMessage.Source.OUTREACH,
                status=EmailThreadMessage.Status.SENT,
                external_thread_id=matched_oe.thread_id or ext_tid,
                rfc_message_id=matched_oe.message_id or "",
                prospect=matched_oe.prospect,
                outreach_email=matched_oe,
                sent_at=matched_oe.sent_at or matched_oe.created_at,
                trigger_summary=False,
            )

        # Safe prospect/contact resolution ONLY when unambiguously matched
        resolved_prospect = matched_thread.prospect if matched_thread else None
        resolved_contact = matched_thread.prospect_contact if matched_thread else None
        is_confident_match = bool(matched_thread and (matched_thread.match_status == EmailThread.MatchStatus.MATCHED or resolved_prospect))

        if not matched_thread and correspondent_email:
            contacts = list(
                ProspectContact.objects.select_related("prospect").filter(
                    official_email__iexact=correspondent_email
                )[:2]
            )
            if len(contacts) == 1:
                resolved_contact = contacts[0]
                resolved_prospect = resolved_contact.prospect
                is_confident_match = True
            elif len(contacts) == 0:
                prospects_q = list(
                    Prospect.objects.filter(official_email_address__iexact=correspondent_email)[:2]
                )
                if len(prospects_q) == 1:
                    resolved_prospect = prospects_q[0]
                    is_confident_match = True

        sent_dt = _parse_email_date(m.get("date", ""))
        eff_snippet = compute_snippet(body_text, body_html) or snippet[:240]

        with transaction.atomic():
            if not matched_thread:
                corr_name = (
                    (resolved_contact.contact_name if resolved_contact else "")
                    or correspondent_name
                    or (resolved_prospect.company_name if resolved_prospect else "")
                )
                matched_thread = EmailThread.objects.create(
                    owner=owner,
                    company=_get_user_company(owner),
                    prospect=resolved_prospect if is_confident_match else None,
                    prospect_contact=resolved_contact if is_confident_match else None,
                    external_thread_id=ext_tid,
                    mailbox_email=mailbox_email,
                    correspondent_email=correspondent_email,
                    correspondent_name=corr_name[:250],
                    subject=subject[:490],
                    normalized_subject=normalize_subject(subject),
                    match_status=(
                        EmailThread.MatchStatus.MATCHED
                        if is_confident_match
                        else EmailThread.MatchStatus.UNMATCHED
                    ),
                    status=(
                        EmailThread.Status.REPLIED
                        if (direction == EmailThreadMessage.Direction.INBOUND and is_confident_match)
                        else (
                            EmailThread.Status.UNMATCHED
                            if not is_confident_match
                            else EmailThread.Status.WAITING_REPLY
                        )
                    ),
                    last_direction=direction,
                    last_message_at=sent_dt,
                    last_snippet=eff_snippet,
                )
            elif ext_tid and not matched_thread.external_thread_id:
                matched_thread.external_thread_id = ext_tid
                matched_thread.save(update_fields=["external_thread_id"])

            try:
                created_msg = EmailThreadMessage.objects.create(
                    thread=matched_thread,
                    owner=owner,
                    direction=direction,
                    source=EmailThreadMessage.Source.SYNC,
                    status=(
                        EmailThreadMessage.Status.RECEIVED
                        if direction == EmailThreadMessage.Direction.INBOUND
                        else EmailThreadMessage.Status.SENT
                    ),
                    external_message_id=msg_id,
                    external_thread_id=ext_tid,
                    rfc_message_id=rfc_mid,
                    in_reply_to=_clean_rfc_id(in_reply_to),
                    references_header=str(references_header or "")[:2000],
                    dedup_key=dedup_key,
                    sender_email=from_email,
                    sender_name=from_name,
                    to_emails=to_list,
                    cc_emails=cc_list,
                    subject=subject[:490],
                    body_text=body_text or eff_snippet,
                    body_html=body_html,
                    snippet=eff_snippet,
                    attachments_metadata=safe_attachments,
                    sent_at=sent_dt,
                )
            except IntegrityError:
                skipped += 1
                continue

            _refresh_thread_aggregates(matched_thread, created_msg)

            # Update existing CRM OutreachEmail + CommunicationActivity when a reply matches
            if direction == EmailThreadMessage.Direction.INBOUND and matched_oe and matched_oe.prospect:
                if not CommunicationActivity.objects.filter(
                    outreach_email=matched_oe,
                    direction="INBOUND",
                    notes=body_text or body_html or eff_snippet,
                ).exists():
                    CommunicationActivity.objects.create(
                        prospect=matched_oe.prospect,
                        prospect_contact=matched_oe.recipients.filter(
                            email_address__iexact=from_email
                        ).first().prospect_contact
                        if matched_oe.recipients.filter(email_address__iexact=from_email).exists()
                        else None,
                        activity_type="EMAIL_RECEIVED",
                        direction="INBOUND",
                        status="Received Response",
                        subject=subject[:255],
                        notes=body_text or body_html or eff_snippet,
                        outreach_email=matched_oe,
                        performed_by=owner,
                    )
                if matched_oe.status != "RECEIVED RESPONSE":
                    matched_oe.status = "RECEIVED RESPONSE"
                    matched_oe.save(update_fields=["status"])
                if hasattr(matched_oe.prospect, "lead_qualification"):
                    matched_oe.prospect.lead_qualification.email_status = "Received Response"
                    matched_oe.prospect.lead_qualification.save(update_fields=["email_status"])

            # Automatically create & assign a PRE task when an inbound reply arrives
            # to a previously sent email (Outreach, Campaign, or Outbound Thread).
            if direction == EmailThreadMessage.Direction.INBOUND:
                try:
                    from .task_service import create_email_reply_pre_task
                    matched_contact = matched_thread.prospect_contact
                    if not matched_contact and matched_oe:
                        rec = matched_oe.recipients.filter(email_address__iexact=from_email).first()
                        if rec:
                            matched_contact = rec.prospect_contact
                    create_email_reply_pre_task(
                        inbound_message=created_msg,
                        email_thread=matched_thread,
                        outreach_email=matched_oe,
                        prospect=(matched_oe.prospect if matched_oe else matched_thread.prospect),
                        prospect_contact=matched_contact,
                    )
                except Exception as exc:
                    logger.warning("Failed creating PRE task for inbound email %s: %s", created_msg.id, exc)

        synced += 1
        touched_threads.add(matched_thread.id)

    for tid in touched_threads:
        schedule_thread_summary(tid)

    return {
        "synced": synced,
        "skipped": skipped,
        "threads_updated": len(touched_threads),
    }


def sync_authorized_mailboxes(
    owner_ids: Iterable[int],
    *,
    pre_user_id: Optional[int] = None,
    force: bool = False,
    limit: int = 25,
    cooldown_seconds: int = 30,
) -> dict:
    """
    Synchronize active Gmail mailboxes for the authorized PRE/LQ users so
    incoming replies appear automatically in the Manager Dashboard.
    Throttled per user with cache cooldown unless `force=True`.
    """
    from accounts.models import GoogleMailCredentials
    from django.core.cache import cache

    target_ids = list(owner_ids or [])
    if pre_user_id is not None:
        target_ids = [uid for uid in target_ids if uid == pre_user_id]
    if not target_ids:
        return {"synced": 0, "accounts_checked": 0}

    creds = list(
        GoogleMailCredentials.objects.select_related("user").filter(
            user_id__in=target_ids,
            is_active=True,
        )
    )
    total_synced = 0
    accounts_checked = 0
    for cred in creds:
        cd_key = f"mgr_mail_sync_cd_{cred.user_id}"
        if not force and cache.get(cd_key):
            continue
        cache.set(cd_key, True, cooldown_seconds)
        accounts_checked += 1
        try:
            res = sync_mailbox_messages(cred, limit=limit)
            total_synced += int(res.get("synced") or 0)
        except Exception as exc:
            logger.debug("Manager mailbox sync skipped for user %s: %s", cred.user_id, exc)

    return {"synced": total_synced, "accounts_checked": accounts_checked}


def backfill_outreach_emails_to_threads(owner_ids=None) -> int:
    """
    Idempotently backfill historical OutreachEmail rows that do not yet have an
    EmailThreadMessage record so Manager Dashboard sees full historical email activity.
    """
    from .models import EmailThreadMessage, OutreachEmail

    qs = (
        OutreachEmail.objects
        .select_related("prospect", "created_by")
        .prefetch_related("recipients__prospect_contact", "attachments")
        .filter(created_by__isnull=False, thread_message__isnull=True)
    )
    if owner_ids is not None:
        qs = qs.filter(created_by_id__in=list(owner_ids))

    created_count = 0
    for oe in qs.order_by("sent_at", "created_at")[:200]:
        rcpts = list(oe.recipients.all())
        to_emails = [r.email_address for r in rcpts if r.recipient_type == "TO"] or [r.email_address for r in rcpts if r.recipient_type != "BCC"]
        cc_emails = [r.email_address for r in rcpts if r.recipient_type == "CC"]
        first_contact = next((r.prospect_contact for r in rcpts if r.prospect_contact_id), None)
        atts = [
            {
                "filename": a.original_filename,
                "content_type": a.mime_type,
                "size": a.size,
                "attachment_id": str(a.id),
            }
            for a in oe.attachments.all()
        ]
        msg_status = (
            EmailThreadMessage.Status.FAILED
            if "FAIL" in str(oe.status or "").upper()
            else EmailThreadMessage.Status.SENT
        )
        _, msg = record_outbound_email_in_thread(
            owner=oe.created_by,
            from_email=oe.from_email,
            sender_name=oe.from_name or "",
            to_emails=to_emails,
            cc_emails=cc_emails,
            subject=oe.subject,
            body_text=compute_snippet(body_html=oe.body, max_len=12000),
            body_html=oe.body,
            source=EmailThreadMessage.Source.OUTREACH,
            status=msg_status,
            external_thread_id=oe.thread_id or "",
            rfc_message_id=oe.message_id or "",
            prospect=oe.prospect,
            prospect_contact=first_contact,
            outreach_email=oe,
            attachments_metadata=atts,
            sent_at=oe.sent_at or oe.created_at,
            dedup_key=f"outreach:{oe.id}",
            trigger_summary=True,
        )
        if msg:
            created_count += 1
    return created_count

