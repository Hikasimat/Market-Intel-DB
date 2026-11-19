import logging
import re
from typing import Optional, Tuple

from django.contrib.auth import get_user_model
from django.db import IntegrityError

from accounts.models import UserProfile
from .models import (
    EmailThread,
    EmailThreadMessage,
    OutreachEmail,
    PreTask,
    Prospect,
    ProspectContact,
)

logger = logging.getLogger(__name__)
User = get_user_model()


def _digits_only(value: Optional[str]) -> str:
    return re.sub(r"\D+", "", str(value or ""))


def resolve_prospect_and_contact_for_phone(
    phone: Optional[str] = None,
    email: Optional[str] = None,
    sender_name: Optional[str] = None,
) -> Tuple[Optional[Prospect], Optional[ProspectContact]]:
    """
    Resolve CRM Prospect and ProspectContact from a phone number (e.g. WhatsApp JID/phone)
    or email address using suffix matching on normalized digits / case-insensitive email.
    """
    contact = None
    prospect = None

    email_clean = (email or "").strip().lower()
    if email_clean:
        contact = (
            ProspectContact.objects.select_related("prospect")
            .filter(official_email__iexact=email_clean)
            .first()
        )
        if contact:
            return contact.prospect, contact
        prospect = Prospect.objects.filter(official_email_address__iexact=email_clean).first()
        if prospect:
            return prospect, None

    digits = _digits_only(phone)
    if digits:
        # Exact match on phone_digits or last-10-digits suffix match (country code tolerant)
        tail = digits[-10:] if len(digits) >= 10 else digits
        contact = (
            ProspectContact.objects.select_related("prospect")
            .filter(phone_digits=digits)
            .first()
        )
        if not contact and len(tail) >= 7:
            contact = (
                ProspectContact.objects.select_related("prospect")
                .filter(phone_digits__endswith=tail)
                .order_by("created_at")
                .first()
            )
        if contact:
            return contact.prospect, contact

        # Fallback to Prospect official_phone_number
        if len(tail) >= 7:
            for cand in Prospect.objects.exclude(official_phone_number__isnull=True).exclude(official_phone_number="").iterator():
                c_digits = _digits_only(cand.official_phone_number)
                if c_digits == digits or (len(c_digits) >= 7 and c_digits.endswith(tail)):
                    return cand, None

    # Weak last-resort fallback by exact company name only if no phone/email match
    name_clean = (sender_name or "").strip()
    if name_clean:
        contact = (
            ProspectContact.objects.select_related("prospect")
            .filter(contact_name__iexact=name_clean)
            .first()
        )
        if contact:
            return contact.prospect, contact

    return prospect, contact


def resolve_pre_user(
    *,
    prospect: Optional[Prospect] = None,
    outreach_email: Optional[OutreachEmail] = None,
    email_thread: Optional[EmailThread] = None,
    whatsapp_session=None,
    fallback_user=None,
):
    """
    Identify the related PRE User for a Prospect / OutreachEmail / EmailThread / WhatsAppSession.
    When `whatsapp_session` is supplied, its owner is always authoritative so one user's
    WhatsApp session never resolves to another user's credentials or inbox.
    Priority order:
      1. whatsapp_session.owner (strictly authoritative when session is given)
      2. prospect.created_by if that user exists and has role PRE (or is the prospect owner)
      3. outreach_email.sent_by / created_by user if active
      4. email_thread.owner if set
      5. prospect.lead_qualification.assigned_lq if active
      6. fallback_user
    """
    # 0. Authoritative WhatsApp session owner first (never substitute another user)
    if whatsapp_session is not None:
        session_user = getattr(whatsapp_session, "owner", None) or getattr(whatsapp_session, "user", None)
        if session_user and session_user.is_active:
            return session_user
        return fallback_user if (fallback_user and getattr(fallback_user, "is_active", False)) else None

    # 1. Prospect creator (primary PRE owner in this CRM)
    if prospect and (prospect.created_by or "").strip():
        creator = (
            User.objects.select_related("profile")
            .filter(username__iexact=prospect.created_by.strip(), is_active=True)
            .first()
        )
        if creator:
            role = getattr(getattr(creator, "profile", None), "role", None)
            if role == "PRE":
                return creator

    # 2. OutreachEmail sender
    if outreach_email and getattr(outreach_email, "created_by", None) and outreach_email.created_by.is_active:
        return outreach_email.created_by

    # 3. EmailThread owner
    if email_thread and getattr(email_thread, "owner", None) and email_thread.owner.is_active:
        return email_thread.owner

    # 4. Prospect creator (any role) or LeadQualification assigned user
    if prospect:
        if (prospect.created_by or "").strip():
            creator = User.objects.filter(username__iexact=prospect.created_by.strip(), is_active=True).first()
            if creator:
                return creator
        lq = getattr(prospect, "lead_qualification", None)
        if lq and lq.assigned_lq and lq.assigned_lq.is_active:
            return lq.assigned_lq

    # 5 & 6. WhatsApp session owner / assigned PRE profiles
    if whatsapp_session is not None:
        session_user = getattr(whatsapp_session, "owner", None) or getattr(whatsapp_session, "user", None)
        if session_user and session_user.is_active:
            return session_user
        try:
            assigned_pre = (
                whatsapp_session.assigned_profiles.select_related("user")
                .filter(role="PRE", user__is_active=True)
                .order_by("user_id")
                .first()
            )
            if assigned_pre:
                return assigned_pre.user
        except Exception:
            pass

    # 7. Explicit fallback user
    if fallback_user and getattr(fallback_user, "is_active", False):
        return fallback_user

    # 8. Default active PRE user in system
    default_pre = (
        UserProfile.objects.select_related("user")
        .filter(role="PRE", user__is_active=True)
        .order_by("user_id")
        .first()
    )
    if default_pre:
        return default_pre.user

    return User.objects.filter(is_active=True).order_by("id").first()


def _format_email_thread_history(email_thread: EmailThread, limit: int = 20) -> list:
    msgs = list(
        EmailThreadMessage.objects.filter(thread=email_thread)
        .order_by("sent_at", "created_at")
    )
    if len(msgs) > limit:
        msgs = msgs[-limit:]
    history = []
    for m in msgs:
        timestamp = m.sent_at or m.created_at
        history.append(
            {
                "id": str(m.id),
                "direction": m.direction,
                "from_email": m.sender_email or "",
                "from_name": m.sender_name or "",
                "to_emails": m.to_emails or [],
                "subject": m.subject or "",
                "snippet": m.snippet or "",
                "body": (m.body_text or m.snippet or "")[:4000],
                "timestamp": timestamp.isoformat() if timestamp else "",
            }
        )
    return history


def create_email_reply_pre_task(
    *,
    inbound_message: EmailThreadMessage,
    email_thread: EmailThread,
    outreach_email: Optional[OutreachEmail] = None,
    prospect: Optional[Prospect] = None,
    prospect_contact: Optional[ProspectContact] = None,
) -> Optional[PreTask]:
    """
    Create (idempotently) a PRE Task whenever an inbound reply arrives to an email
    previously sent by our system (via OutreachEmail or an outbound EmailThreadMessage).
    """
    if not inbound_message or inbound_message.direction != EmailThreadMessage.Direction.INBOUND:
        return None

    source_key = f"email_reply:{inbound_message.id}"
    existing = PreTask.objects.filter(source_key=source_key).first()
    if existing:
        return existing

    # Resolve OutreachEmail from inbound_message / email_thread if not directly passed
    if outreach_email is None and inbound_message.outreach_email_id:
        outreach_email = inbound_message.outreach_email
    if outreach_email is None and email_thread is not None:
        outreach_email = (
            OutreachEmail.objects.select_related("prospect", "created_by")
            .filter(id__in=EmailThreadMessage.objects.filter(
                thread=email_thread, outreach_email__isnull=False
            ).values_list("outreach_email_id", flat=True))
            .order_by("-sent_at", "-created_at")
            .first()
        )

    # Confirm this is genuinely a reply to an email previously sent by our system
    has_prior_outbound = False
    if outreach_email is not None:
        has_prior_outbound = True
    elif email_thread is not None:
        has_prior_outbound = EmailThreadMessage.objects.filter(
            thread=email_thread,
            direction=EmailThreadMessage.Direction.OUTBOUND,
        ).exclude(id=inbound_message.id).exists()

    if not has_prior_outbound:
        return None

    # Resolve prospect & contact
    if prospect is None:
        prospect = (
            (outreach_email.prospect if outreach_email else None)
            or email_thread.prospect
        )
    if prospect_contact is None and outreach_email is not None:
        rec = outreach_email.recipients.select_related("prospect_contact").filter(
            email_address__iexact=(inbound_message.sender_email or "")
        ).first() or outreach_email.recipients.select_related("prospect_contact").filter(
            prospect_contact__isnull=False
        ).first()
        if rec:
            prospect_contact = rec.prospect_contact
    if prospect_contact is None and email_thread is not None:
        prospect_contact = email_thread.prospect_contact
    if prospect is None and (inbound_message.sender_email or email_thread.correspondent_email):
        p2, c2 = resolve_prospect_and_contact_for_phone(
            email=inbound_message.sender_email or email_thread.correspondent_email
        )
        prospect = prospect or p2
        prospect_contact = prospect_contact or c2

    pre_user = resolve_pre_user(
        prospect=prospect,
        outreach_email=outreach_email,
        email_thread=email_thread,
    )

    company_name = prospect.company_name if prospect else ""
    sender_email = (inbound_message.sender_email or email_thread.correspondent_email or "").strip()
    sender_name = (
        (inbound_message.sender_name or "").strip()
        or (prospect_contact.contact_name if prospect_contact else "")
        or (email_thread.correspondent_name or "").strip()
        or sender_email
    )
    sender_phone = (
        (prospect_contact.phone_number if prospect_contact else None)
        or (prospect.official_phone_number if prospect else None)
        or ""
    )

    subject = (inbound_message.subject or email_thread.subject or "(No Subject)").strip()
    reply_body = (inbound_message.body_text or inbound_message.snippet or "").strip()
    history = _format_email_thread_history(email_thread)

    title_target = company_name or sender_name or sender_email or "Prospect"
    title = f"Email Reply from {title_target}: {subject}"[:295]

    description_lines = [
        f"Incoming email reply from {sender_name} <{sender_email}>"
        + (f" ({company_name})" if company_name else ""),
        f"Subject: {subject}",
    ]
    if outreach_email:
        description_lines.append(
            f"Original Sent Email Subject: {outreach_email.subject}"
        )
    if reply_body:
        description_lines.extend(["", "Reply Content:", reply_body[:2000]])

    metadata = {
        "subject": subject,
        "original_sent_subject": outreach_email.subject if outreach_email else "",
        "original_sent_at": (
            outreach_email.sent_at.isoformat() if (outreach_email and outreach_email.sent_at) else ""
        ),
        "mailbox_email": email_thread.mailbox_email if email_thread else "",
        "inbound_message_id": str(inbound_message.id),
    }

    try:
        task = PreTask.objects.create(
            task_type=PreTask.TaskType.EMAIL_REPLY,
            status=PreTask.Status.PENDING,
            title=title,
            description="\n".join(description_lines),
            assigned_pre=pre_user,
            assigned_pre_username=pre_user.username if pre_user else "",
            prospect=prospect,
            company_name=company_name,
            prospect_contact=prospect_contact,
            sender_name=sender_name,
            sender_email=sender_email,
            sender_phone=sender_phone,
            outreach_email=outreach_email,
            email_thread=email_thread,
            inbound_message=inbound_message,
            source_key=source_key,
            conversation_history=history,
            metadata=metadata,
        )
        return task
    except IntegrityError:
        return PreTask.objects.filter(source_key=source_key).first()


def create_whatsapp_escalation_pre_task(
    *,
    session,
    conversation,
    original_query: str,
    sender_name: str = "",
    sender_phone: str = "",
    sender_email: str = "",
    prospect: Optional[Prospect] = None,
    prospect_contact: Optional[ProspectContact] = None,
    source_key: Optional[str] = None,
    extra_metadata: Optional[dict] = None,
) -> PreTask:
    """
    Create (idempotently when source_key is given) a PRE Task for an unanswered
    WhatsApp business query after the sender confirms executive escalation.
    """
    if source_key:
        existing = PreTask.objects.filter(source_key=source_key).first()
        if existing:
            return existing

    if prospect is None:
        prospect = getattr(conversation, "prospect", None)
    if prospect_contact is None:
        prospect_contact = getattr(conversation, "prospect_contact", None)
    if prospect is None:
        p2, c2 = resolve_prospect_and_contact_for_phone(
            phone=sender_phone or getattr(conversation, "phone_number", None) or getattr(conversation, "chat_id", None),
            email=sender_email,
            sender_name=sender_name or getattr(conversation, "whatsapp_name", None),
        )
        prospect = p2
        prospect_contact = prospect_contact or c2

    pre_user = resolve_pre_user(
        prospect=prospect,
        whatsapp_session=session,
    )

    from whatsapp.models import WhatsAppMessage

    msgs = list(
        WhatsAppMessage.objects.filter(conversation=conversation, is_deleted=False)
        .order_by("waha_timestamp", "created_at")
    )
    if len(msgs) > 25:
        msgs = msgs[-25:]

    history = []
    for m in msgs:
        ts = m.waha_timestamp or m.sent_at or m.created_at
        body_text = (m.full_body or m.body_preview or "")[:4000]
        history.append(
            {
                "id": str(m.id),
                "direction": m.direction,
                "sender_name": (sender_name or getattr(conversation, "whatsapp_name", "") or sender_phone) if m.direction == "INBOUND" else "AI Assistant",
                "sender_phone": sender_phone or getattr(conversation, "phone_number", "") or "",
                "body": body_text,
                "timestamp": ts.isoformat() if ts else "",
            }
        )

    company_name = prospect.company_name if prospect else ""
    display_sender = (
        sender_name
        or (prospect_contact.contact_name if prospect_contact else "")
        or getattr(conversation, "whatsapp_name", "")
        or sender_phone
        or getattr(conversation, "phone_number", "")
        or "WhatsApp Contact"
    )
    resolved_phone = (
        sender_phone
        or (prospect_contact.phone_number if prospect_contact else "")
        or getattr(conversation, "phone_number", "")
        or ""
    )
    resolved_email = (
        sender_email
        or (prospect_contact.official_email if prospect_contact else "")
        or (prospect.official_email_address if prospect else "")
        or ""
    )

    target_label = f"{display_sender} ({company_name})" if company_name else display_sender
    title = f"WhatsApp Escalation from {target_label}"[:295]

    description_lines = [
        f"Sender Query (Not covered in Knowledge Base): {(original_query or '').strip()}",
        f"Contact Name: {display_sender}",
        f"Phone / WhatsApp: {resolved_phone or 'N/A'}",
    ]
    if resolved_email:
        description_lines.append(f"Email: {resolved_email}")
    if company_name:
        description_lines.append(f"Company: {company_name}")

    metadata = {
        "original_query": (original_query or "").strip(),
        "chat_id": getattr(conversation, "chat_id", ""),
        "session_name": getattr(session, "session_name", ""),
        **(extra_metadata or {}),
    }

    try:
        return PreTask.objects.create(
            task_type=PreTask.TaskType.WHATSAPP_ESCALATION,
            status=PreTask.Status.PENDING,
            title=title,
            description="\n".join(description_lines),
            assigned_pre=pre_user,
            assigned_pre_username=pre_user.username if pre_user else "",
            prospect=prospect,
            company_name=company_name,
            prospect_contact=prospect_contact,
            sender_name=display_sender,
            sender_email=resolved_email,
            sender_phone=resolved_phone,
            whatsapp_session=session,
            whatsapp_conversation=conversation,
            source_key=source_key,
            conversation_history=history,
            metadata=metadata,
        )
    except IntegrityError:
        if source_key:
            found = PreTask.objects.filter(source_key=source_key).first()
            if found:
                return found
        raise
