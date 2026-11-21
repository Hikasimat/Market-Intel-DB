import email.message
from email.utils import make_msgid, formatdate
import html
import logging
import mimetypes
import re
import threading
import time
import uuid
from datetime import timedelta
from typing import List, Dict, Any, Optional

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.db.models import Case, When, IntegerField
from django.utils import timezone

from accounts.oauth_services import GmailOAuthService, get_mail_credentials
from prospects.email_composition import (
    format_sender_address,
    validate_and_sanitize_recipient,
    set_singleton_header,
    extract_domain_from_email,
)
from prospects.matching_service import extract_clean_email, ProspectMatcher
from prospects.models import (
    EmailCampaign,
    EmailCampaignRecipient,
    EmailCampaignAttachment,
    OutreachEmail,
    OutreachEmailRecipient,
    CommunicationActivity,
    Prospect,
    ProspectContact,
)

logger = logging.getLogger(__name__)

DISALLOWED_EXTENSIONS = {'exe', 'bat', 'cmd', 'js', 'ps1', 'vbs', 'scr', 'sh'}
MAX_TOTAL_ATTACHMENT_SIZE = 25 * 1024 * 1024  # 25 MB
MAX_SINGLE_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10 MB


def create_campaign(
    user,
    name: str,
    subject: str,
    body: str,
    recipients_data: List[Any],
    template_id: Optional[str] = None,
    signature_id: Optional[str] = None,
    open_tracking_enabled: bool = False,
    attachments_files: Optional[List[Any]] = None,
    interval_seconds: int = 90,
) -> EmailCampaign:
    """
    Validates sender credentials, recipient list, templates, and attachments,
    and transactionally queues a new EmailCampaign with deterministic ordering.
    """
    google_creds = get_mail_credentials(user)
    if not google_creds:
        raise ValueError("Google Mail is not connected. Connect Gmail before creating a campaign.")

    if not name or not name.strip():
        raise ValueError("Campaign name is required.")

    if not subject or not subject.strip():
        raise ValueError("Email subject is required.")

    if not body or not body.strip():
        raise ValueError("Email body is required.")

    if not recipients_data:
        raise ValueError("At least one recipient is required.")

    # Validate tracking configuration if requested
    from prospects.tracking_utils import (
        global_open_tracking_enabled,
        validate_tracking_configuration,
    )
    effective_tracking = False
    if open_tracking_enabled and global_open_tracking_enabled():
        valid_cfg, cfg_err = validate_tracking_configuration()
        if not valid_cfg:
            raise ValueError(f"Cannot enable open tracking: {cfg_err}")
        effective_tracking = True

    # Validate attachments
    files = attachments_files or []
    total_size = sum(f.size for f in files)
    if total_size > MAX_TOTAL_ATTACHMENT_SIZE:
        raise ValueError("Total attachment size exceeds the 25MB limit.")

    for f in files:
        if f.size > MAX_SINGLE_ATTACHMENT_SIZE:
            raise ValueError(f"Attachment {f.name} exceeds the 10MB limit.")
        ext = f.name.split('.')[-1].lower() if '.' in f.name else ''
        if ext in DISALLOWED_EXTENSIONS:
            raise ValueError(f"Attachment type .{ext} is not allowed.")

    # Deduplicate and validate recipients case-insensitively
    seen_emails = set()
    normalized_recipients = []

    matcher = ProspectMatcher(user)

    for item in recipients_data:
        raw_email = None
        item_name = None
        p_id = None
        c_id = None

        if isinstance(item, str):
            raw_email = item
        elif isinstance(item, dict):
            raw_email = item.get('email') or item.get('email_address')
            item_name = item.get('name') or item.get('contact_name')
            p_id = item.get('prospect_id')
            c_id = item.get('prospect_contact_id')

        clean_addr = extract_clean_email(raw_email)
        if not clean_addr:
            continue

        try:
            validated = validate_and_sanitize_recipient(clean_addr)
        except Exception:
            continue

        norm_key = validated.lower()
        if norm_key in seen_emails:
            continue
        seen_emails.add(norm_key)

        # Match prospect/contact if not explicitly supplied
        matched_prospect = None
        matched_contact = None

        if p_id:
            matched_prospect = Prospect.objects.filter(id=p_id).first()
        if c_id:
            matched_contact = ProspectContact.objects.filter(id=c_id).first()

        if not matched_prospect and not matched_contact:
            match_res = matcher.match_address(norm_key)
            if match_res.get('prospect_match'):
                if match_res.get('prospect_id'):
                    matched_prospect = Prospect.objects.filter(id=match_res['prospect_id']).first()
                if match_res.get('prospect_contact_id'):
                    matched_contact = ProspectContact.objects.filter(id=match_res['prospect_contact_id']).first()

        normalized_recipients.append({
            'email': norm_key,
            'name': item_name or (matched_contact.contact_name if matched_contact else (matched_prospect.company_name if matched_prospect else '')),
            'prospect': matched_prospect,
            'prospect_contact': matched_contact,
        })

    if not normalized_recipients:
        raise ValueError("No valid unique recipient addresses found.")

    with transaction.atomic():
        now = timezone.now()
        campaign = EmailCampaign.objects.create(
            name=name.strip(),
            created_by=user,
            sender_email=google_creds.email,
            subject=subject.strip(),
            body=body,
            template_id=str(template_id) if template_id else None,
            signature_id=str(signature_id) if signature_id else None,
            open_tracking_enabled=effective_tracking,
            interval_seconds=max(90, int(interval_seconds)),
            status=EmailCampaign.Status.QUEUED,
            next_eligible_at=now,
        )

        recipient_objs = []
        for idx, r_data in enumerate(normalized_recipients):
            # Recipient 0 is immediately eligible; subsequent are queued
            scheduled_time = now if idx == 0 else None
            recipient_objs.append(
                EmailCampaignRecipient(
                    campaign=campaign,
                    email_address=r_data['email'],
                    recipient_name=r_data['name'] or None,
                    prospect=r_data['prospect'],
                    prospect_contact=r_data['prospect_contact'],
                    section_number=(idx // 10) + 1,
                    queue_order=idx,
                    status=EmailCampaignRecipient.Status.PENDING,
                    scheduled_for=scheduled_time,
                )
            )

        EmailCampaignRecipient.objects.bulk_create(recipient_objs)

        # Store attachments securely
        for f in files:
            mtype, _ = mimetypes.guess_type(f.name)
            mime_type = mtype or 'application/octet-stream'
            EmailCampaignAttachment.objects.create(
                campaign=campaign,
                file=f,
                original_filename=f.name,
                mime_type=mime_type,
                size=f.size,
            )

        transaction.on_commit(trigger_background_worker)

    return campaign


def compose_campaign_mime_message(campaign: EmailCampaign, recipient: EmailCampaignRecipient, tracking_token: Optional[uuid.UUID] = None) -> email.message.EmailMessage:
    """
    Constructs an individual RFC-compliant MIME message for a single recipient,
    incorporating per-recipient AI customized subject/body (when present),
    templates, signatures, attachments, and optional open-tracking.
    """
    user = campaign.created_by
    sender_email = campaign.sender_email
    sender_display_name = user.get_full_name() or user.username
    email_domain = extract_domain_from_email(sender_email)

    effective_subject = (getattr(recipient, 'custom_subject', '') or '').strip() or campaign.subject
    effective_body = (getattr(recipient, 'custom_body', '') or '').strip() or campaign.body

    msg = email.message.EmailMessage()
    from_header_val = format_sender_address(sender_display_name, sender_email)
    set_singleton_header(msg, 'From', from_header_val)
    set_singleton_header(msg, 'To', recipient.email_address)
    set_singleton_header(msg, 'Subject', effective_subject)
    set_singleton_header(msg, 'Date', formatdate(localtime=True))
    set_singleton_header(msg, 'Message-ID', make_msgid(domain=email_domain))

    # Base body
    composed = None
    if campaign.template_id or campaign.signature_id:
        from accounts.template_utils import build_email_content, sender_from_user
        try:
            composed = build_email_content(
                user,
                sender_from_user(user),
                None,
                [recipient.email_address],
                effective_subject,
                effective_body,
                template_id=campaign.template_id,
                signature_id=campaign.signature_id,
                body_edited=bool((getattr(recipient, 'custom_body', '') or '').strip()),
            )
        except Exception as e:
            logger.warning("Could not apply template/signature to campaign email: %s", e)

    effective_signature = f"--\n{sender_display_name}\n{sender_email}"
    if composed and composed.get('has_signature'):
        effective_signature = composed['signature_text']

    full_text_body = effective_body
    if effective_signature and effective_signature not in full_text_body:
        full_text_body = f"{full_text_body}\n\n{effective_signature}"

    msg.set_content(full_text_body)

    # HTML body
    html_body_text = html.escape(effective_body).replace('\n', '<br>')
    from accounts.template_utils import clean_and_embed_signature_html, convert_base64_images_to_cid

    if composed and composed.get('has_template') and composed.get('html_body') and not (getattr(recipient, 'custom_body', '') or '').strip():
        main_html = composed['html_body']
    else:
        main_html = f'<div style="font-family: sans-serif;">{html_body_text}</div>'

    if composed and composed.get('has_signature') and composed.get('signature_html'):
        html_sig = composed['signature_html']
    else:
        html_sig = f'<div style="color:#64748b;font-size:13px;line-height:1.5;">--<br><strong style="color:#1e293b;">{html.escape(sender_display_name)}</strong><br>{html.escape(sender_email)}</div>'

    integrated_body = clean_and_embed_signature_html(main_html, html_sig)
    raw_html = f"<html><body>\n{integrated_body}\n</body></html>"

    from prospects.tracking_utils import strip_application_tracking_markup, build_tracking_pixel_html
    cleaned_html = strip_application_tracking_markup(raw_html)

    if campaign.open_tracking_enabled and tracking_token:
        pixel_html = f"\n{build_tracking_pixel_html(tracking_token)}\n"
        if '</body>' in cleaned_html:
            cleaned_html = cleaned_html.replace('</body>', f'{pixel_html}</body>', 1)
        else:
            cleaned_html = f'{cleaned_html}{pixel_html}'

    html_content, inline_images = convert_base64_images_to_cid(cleaned_html, domain=email_domain)
    msg.add_alternative(html_content, subtype='html')

    if inline_images:
        html_part = next((p for p in msg.iter_parts() if p.get_content_type() == 'text/html'), None)
        if html_part:
            for cid, subtype, img_bytes in inline_images:
                html_part.add_related(img_bytes, maintype='image', subtype=subtype, cid=f'<{cid}>')

    # Add Campaign Attachments
    for att in campaign.attachments.all():
        try:
            att.file.open('rb')
            file_bytes = att.file.read()
            att.file.close()
            mtype = att.mime_type or 'application/octet-stream'
            maintype, subtype = mtype.split('/', 1) if '/' in mtype else ('application', 'octet-stream')
            msg.add_attachment(file_bytes, maintype=maintype, subtype=subtype, filename=att.original_filename)
        except Exception as e:
            logger.error("Failed to read campaign attachment %s: %s", att.original_filename, e)

    return msg


def send_single_campaign_recipient(recipient_id: uuid.UUID) -> bool:
    """
    Processes an individual queue item:
    1. Claims the recipient with select_for_update in a short transaction.
    2. Sends the email via Gmail API without holding a DB transaction open.
    3. On confirmed acceptance, updates timestamps, schedules the next recipient at least 90s later.
    4. Handles transient and permanent errors with bounded backoff.
    """
    now = timezone.now()

    # Step 1: Claim the recipient atomically
    with transaction.atomic():
        recipient = (
            EmailCampaignRecipient.objects.select_for_update(skip_locked=True)
            .select_related('campaign', 'campaign__created_by')
            .filter(id=recipient_id, status__in=[EmailCampaignRecipient.Status.PENDING, EmailCampaignRecipient.Status.RETRY_PENDING])
            .first()
        )
        if not recipient:
            return False

        campaign = recipient.campaign
        if campaign.status in [EmailCampaign.Status.PAUSED, EmailCampaign.Status.CANCELLED]:
            return False

        # Guard: Ensure at least 90 seconds since last provider send attempt
        if campaign.last_sent_at:
            earliest_eligible = campaign.last_sent_at + timedelta(seconds=campaign.interval_seconds)
            if now < earliest_eligible:
                recipient.scheduled_for = earliest_eligible
                recipient.save(update_fields=['scheduled_for'])
                campaign.next_eligible_at = earliest_eligible
                campaign.save(update_fields=['next_eligible_at'])
                return False

        recipient.status = EmailCampaignRecipient.Status.SENDING
        recipient.last_attempt_at = now
        recipient.attempt_count += 1
        recipient.save(update_fields=['status', 'last_attempt_at', 'attempt_count'])

        if campaign.status == EmailCampaign.Status.QUEUED:
            campaign.status = EmailCampaign.Status.RUNNING
            campaign.started_at = now
            campaign.save(update_fields=['status', 'started_at'])

    # Step 2: Compose and send outside the DB transaction
    google_creds = get_mail_credentials(campaign.created_by)
    if not google_creds:
        with transaction.atomic():
            recipient.status = EmailCampaignRecipient.Status.FAILED
            recipient.error_message = "Sender Google Mail credentials not active or not found."
            recipient.save(update_fields=['status', 'error_message'])
            _advance_next_recipient(campaign, recipient.queue_order, timezone.now() + timedelta(seconds=campaign.interval_seconds))
        return False

    tracking_token = uuid.uuid4() if campaign.open_tracking_enabled else None
    try:
        mime_msg = compose_campaign_mime_message(campaign, recipient, tracking_token=tracking_token)
        raw_bytes = mime_msg.as_bytes()
    except Exception as exc:
        logger.error("Failed to compose campaign email for %s: %s", recipient.email_address, exc)
        with transaction.atomic():
            recipient.status = EmailCampaignRecipient.Status.FAILED
            recipient.error_message = f"Composition error: {exc}"
            recipient.save(update_fields=['status', 'error_message'])
            _advance_next_recipient(campaign, recipient.queue_order, timezone.now() + timedelta(seconds=campaign.interval_seconds))
        return False

    # Execute provider send
    send_success = False
    gmail_resp = None
    error_detail = None
    is_transient = False

    try:
        gmail_resp = GmailOAuthService.send_message(google_creds, raw_bytes)
        # Gmail API returns {'id': '...', 'threadId': '...'} on success
        if gmail_resp and 'id' in gmail_resp:
            send_success = True
        else:
            error_detail = f"Unexpected response from Gmail: {gmail_resp}"
            is_transient = True
    except Exception as exc:
        error_str = str(exc)
        logger.warning("Gmail send error for recipient %s: %s", recipient.email_address, error_str)
        error_detail = error_str
        # Determine if transient
        if any(w in error_str.lower() for w in ['timeout', 'timed out', 'connection', '503', '500', '429', 'rate', 'quota']):
            is_transient = True
        else:
            is_transient = False

    # Step 3: Record the provider outcome
    completed_at = timezone.now()

    effective_subject = (getattr(recipient, 'custom_subject', '') or '').strip() or campaign.subject
    effective_body = (getattr(recipient, 'custom_body', '') or '').strip() or campaign.body

    with transaction.atomic():
        if send_success:
            recipient.status = EmailCampaignRecipient.Status.SENT
            recipient.sent_at = completed_at
            recipient.error_message = None

            # Create OutreachEmail tracking record
            outreach_email = OutreachEmail.objects.create(
                prospect=recipient.prospect,
                created_by=campaign.created_by,
                from_email=campaign.sender_email,
                from_name=campaign.created_by.get_full_name() or campaign.created_by.username,
                subject=effective_subject,
                body=effective_body,
                status='SENT',
                sent_at=completed_at,
                message_id=str(mime_msg['Message-ID']),
                thread_id=gmail_resp.get('threadId') if gmail_resp else None,
                open_tracking_enabled=campaign.open_tracking_enabled,
                tracking_token=tracking_token or uuid.uuid4(),
            )
            OutreachEmailRecipient.objects.create(
                outreach_email=outreach_email,
                email_address=recipient.email_address,
                prospect_contact=recipient.prospect_contact,
                recipient_type='TO',
            )
            recipient.outreach_email = outreach_email
            recipient.save(update_fields=['status', 'sent_at', 'error_message', 'outreach_email'])

            from .email_thread_service import compute_snippet, record_outbound_email_in_thread
            camp_atts = [
                {"filename": a.original_filename, "content_type": a.mime_type, "size": a.size, "attachment_id": str(a.id)}
                for a in campaign.attachments.all()
            ]
            record_outbound_email_in_thread(
                owner=campaign.created_by,
                from_email=outreach_email.from_email,
                sender_name=outreach_email.from_name or "",
                to_emails=[recipient.email_address],
                subject=effective_subject,
                body_text=compute_snippet(body_html=outreach_email.body, max_len=12000),
                body_html=outreach_email.body,
                source='CAMPAIGN',
                status='SENT',
                external_thread_id=(gmail_resp.get('threadId') if gmail_resp else "") or "",
                external_message_id=(gmail_resp.get('id') if gmail_resp else "") or "",
                rfc_message_id=str(mime_msg['Message-ID']),
                prospect=recipient.prospect,
                prospect_contact=recipient.prospect_contact,
                outreach_email=outreach_email,
                campaign_recipient=recipient,
                attachments_metadata=camp_atts,
                sent_at=completed_at,
                dedup_key=f"campaign:{recipient.id}",
            )

            if recipient.prospect:
                CommunicationActivity.objects.create(
                    prospect=recipient.prospect,
                    prospect_contact=recipient.prospect_contact,
                    performed_by=campaign.created_by,
                    activity_type='EMAIL_SENT',
                    direction='OUTBOUND',
                    outreach_email=outreach_email,
                    subject=effective_subject,
                    notes=f"Sent via bulk campaign '{campaign.name}' (Section {recipient.section_number}) to {recipient.email_address}",
                )
                try:
                    from prospects.models import LeadQualification
                    LeadQualification.objects.filter(
                        prospect=recipient.prospect,
                        email_status='Not Sent',
                    ).update(email_status='Waiting for Response')
                except Exception:
                    pass

            # Advance next send time strictly by interval_seconds (90s minimum)
            next_send_time = completed_at + timedelta(seconds=campaign.interval_seconds)
            campaign.last_sent_at = completed_at
            campaign.next_eligible_at = next_send_time
            campaign.save(update_fields=['last_sent_at', 'next_eligible_at'])

            _advance_next_recipient(campaign, recipient.queue_order, next_send_time)
            _check_and_update_campaign_completion(campaign)
            return True

        else:
            # Handle failure
            if is_transient and recipient.attempt_count < recipient.max_retries:
                # Bounded backoff retry: never shorter than interval_seconds (90s)
                backoff_multiplier = 2 ** (recipient.attempt_count - 1)
                backoff_secs = max(campaign.interval_seconds, campaign.interval_seconds * backoff_multiplier)
                retry_time = completed_at + timedelta(seconds=backoff_secs)

                recipient.status = EmailCampaignRecipient.Status.RETRY_PENDING
                recipient.scheduled_for = retry_time
                recipient.error_message = f"Transient error: {error_detail}"
                recipient.save(update_fields=['status', 'scheduled_for', 'error_message'])

                campaign.next_eligible_at = retry_time
                campaign.save(update_fields=['next_eligible_at'])
            else:
                recipient.status = EmailCampaignRecipient.Status.FAILED
                recipient.error_message = error_detail or "Failed to send email."
                recipient.save(update_fields=['status', 'error_message'])

                try:
                    from .email_thread_service import record_outbound_email_in_thread
                    record_outbound_email_in_thread(
                        owner=campaign.created_by,
                        from_email=getattr(google_creds, 'email', '') or '',
                        to_emails=[recipient.email_address],
                        subject=effective_subject,
                        body_text=effective_body or '',
                        source='CAMPAIGN',
                        status='FAILED',
                        prospect=recipient.prospect,
                        prospect_contact=recipient.prospect_contact,
                        campaign_recipient=recipient,
                        sent_at=completed_at,
                        dedup_key=f"campaign:{recipient.id}",
                    )
                except Exception:
                    pass

                # Advance next recipient after preserving provider pacing
                next_time = completed_at + timedelta(seconds=campaign.interval_seconds)
                campaign.next_eligible_at = next_time
                campaign.save(update_fields=['next_eligible_at'])
                _advance_next_recipient(campaign, recipient.queue_order, next_time)
                _check_and_update_campaign_completion(campaign)

            return False


def _advance_next_recipient(campaign: EmailCampaign, current_order: int, next_eligible_time):
    """
    Ensures the next pending recipient in the deterministic queue
    has scheduled_for set to the calculated eligible time.
    """
    next_recipient = (
        campaign.recipients
        .filter(status=EmailCampaignRecipient.Status.PENDING, queue_order__gt=current_order)
        .order_by('queue_order')
        .first()
    )
    if not next_recipient:
        next_recipient = (
            campaign.recipients
            .filter(status=EmailCampaignRecipient.Status.PENDING)
            .order_by('queue_order')
            .first()
        )
    if next_recipient:
        next_recipient.scheduled_for = next_eligible_time
        next_recipient.save(update_fields=['scheduled_for'])


def _check_and_update_campaign_completion(campaign: EmailCampaign):
    """
    Evaluates whether all queued recipients have finished processing.
    If unapproved DRAFT sections remain, transitions the campaign back to DRAFT
    (awaiting the user's review and Send click on the next section).
    Otherwise marks the campaign COMPLETED or COMPLETED_WITH_ERRORS.
    """
    remaining_active = campaign.recipients.filter(
        status__in=[
            EmailCampaignRecipient.Status.PENDING,
            EmailCampaignRecipient.Status.SENDING,
            EmailCampaignRecipient.Status.RETRY_PENDING,
        ]
    ).exists()

    if not remaining_active:
        has_drafts = campaign.recipients.filter(status=EmailCampaignRecipient.Status.DRAFT).exists()
        if has_drafts:
            campaign.status = EmailCampaign.Status.DRAFT
            campaign.next_eligible_at = None
            campaign.save(update_fields=['status', 'next_eligible_at'])
            return

        has_failures = campaign.recipients.filter(status=EmailCampaignRecipient.Status.FAILED).exists()
        campaign.status = (
            EmailCampaign.Status.COMPLETED_WITH_ERRORS if has_failures else EmailCampaign.Status.COMPLETED
        )
        campaign.completed_at = timezone.now()
        campaign.next_eligible_at = None
        campaign.save(update_fields=['status', 'completed_at', 'next_eligible_at'])


def recover_stale_sending_jobs():
    """
    Identifies jobs stuck in SENDING state (e.g. from an abrupt process termination).
    If a job has been SENDING for more than 10 minutes, resets it to RETRY_PENDING.
    """
    threshold = timezone.now() - timedelta(minutes=10)
    stale_recipients = EmailCampaignRecipient.objects.filter(
        status=EmailCampaignRecipient.Status.SENDING,
        last_attempt_at__lt=threshold,
    )
    for r in stale_recipients:
        logger.warning("Recovering stale sending recipient %s in campaign %s", r.id, r.campaign_id)
        r.status = EmailCampaignRecipient.Status.RETRY_PENDING
        r.scheduled_for = timezone.now() + timedelta(seconds=r.campaign.interval_seconds)
        r.error_message = "Recovered after unacknowledged worker timeout."
        r.save(update_fields=['status', 'scheduled_for', 'error_message'])


def process_campaign_queue(max_jobs: Optional[int] = None) -> int:
    """
    Primary worker processing loop iteration.
    Scans for campaigns and recipients due for sending and dispatches them safely.
    Returns the count of recipients processed in this cycle.
    """
    recover_stale_sending_jobs()

    now = timezone.now()
    active_campaigns = EmailCampaign.objects.filter(
        status__in=[EmailCampaign.Status.QUEUED, EmailCampaign.Status.RUNNING],
    ).order_by('created_at')

    processed_count = 0

    for campaign in active_campaigns:
        if max_jobs and processed_count >= max_jobs:
            break

        # Check 90-second minimum gap between consecutive sends
        if campaign.last_sent_at:
            earliest_eligible = campaign.last_sent_at + timedelta(seconds=campaign.interval_seconds)
            if now < earliest_eligible:
                continue

        # Find the next eligible recipient
        due_recipient = (
            campaign.recipients
            .filter(
                status__in=[EmailCampaignRecipient.Status.PENDING, EmailCampaignRecipient.Status.RETRY_PENDING],
                scheduled_for__lte=now,
            )
            .order_by('queue_order')
            .first()
        )

        if not due_recipient:
            # Check if campaign has completed
            _check_and_update_campaign_completion(campaign)
            continue

        success = send_single_campaign_recipient(due_recipient.id)
        processed_count += 1

    return processed_count


def pause_campaign(campaign: EmailCampaign, user) -> EmailCampaign:
    """Pauses an active campaign."""
    if campaign.status not in [EmailCampaign.Status.QUEUED, EmailCampaign.Status.RUNNING]:
        raise ValueError(f"Cannot pause a campaign in '{campaign.status}' status.")

    campaign.status = EmailCampaign.Status.PAUSED
    campaign.paused_at = timezone.now()
    campaign.save(update_fields=['status', 'paused_at'])
    return campaign


def resume_campaign(campaign: EmailCampaign, user) -> EmailCampaign:
    """
    Resumes a paused campaign without resetting or shortening the required 90-second delay.
    """
    if campaign.status != EmailCampaign.Status.PAUSED:
        raise ValueError("Campaign is not paused.")

    now = timezone.now()
    campaign.status = EmailCampaign.Status.RUNNING
    campaign.paused_at = None

    # Calculate next eligible time strictly respecting last_sent_at + interval
    if campaign.last_sent_at:
        min_allowed = campaign.last_sent_at + timedelta(seconds=campaign.interval_seconds)
        campaign.next_eligible_at = max(now, min_allowed)
    else:
        campaign.next_eligible_at = now

    campaign.save(update_fields=['status', 'paused_at', 'next_eligible_at'])

    # Update next pending recipient's scheduled_for
    next_recipient = (
        campaign.recipients
        .filter(status__in=[EmailCampaignRecipient.Status.PENDING, EmailCampaignRecipient.Status.RETRY_PENDING])
        .order_by('queue_order')
        .first()
    )
    if next_recipient:
        next_recipient.scheduled_for = campaign.next_eligible_at
        next_recipient.save(update_fields=['scheduled_for'])

    trigger_background_worker()

    return campaign


def cancel_campaign(campaign: EmailCampaign, user) -> EmailCampaign:
    """Cancels a campaign and marks remaining pending recipients as cancelled."""
    if campaign.status in [EmailCampaign.Status.COMPLETED, EmailCampaign.Status.CANCELLED]:
        raise ValueError(f"Campaign is already {campaign.status.lower()}.")

    now = timezone.now()
    with transaction.atomic():
        campaign.status = EmailCampaign.Status.CANCELLED
        campaign.cancelled_at = now
        campaign.next_eligible_at = None
        campaign.save(update_fields=['status', 'cancelled_at', 'next_eligible_at'])

        # Cancel remaining pending recipients
        campaign.recipients.filter(
            status__in=[EmailCampaignRecipient.Status.PENDING, EmailCampaignRecipient.Status.RETRY_PENDING]
        ).update(status=EmailCampaignRecipient.Status.FAILED, error_message="Campaign was cancelled by user.")

    return campaign


_worker_lock = threading.Lock()
_worker_running = False


def _background_worker_loop():
    global _worker_running
    try:
        from django.db import close_old_connections
        while True:
            close_old_connections()
            from prospects.models import EmailCampaign
            active_exists = EmailCampaign.objects.filter(
                status__in=[EmailCampaign.Status.QUEUED, EmailCampaign.Status.RUNNING]
            ).exists()
            if not active_exists:
                break

            try:
                process_campaign_queue(max_jobs=5)
            except Exception as e:
                logger.error("Error in background campaign worker iteration: %s", e)

            close_old_connections()
            time.sleep(3)
    except Exception as exc:
        logger.exception("Fatal error in background campaign worker thread: %s", exc)
    finally:
        with _worker_lock:
            _worker_running = False
        try:
            from django.db import connection
            connection.close()
        except Exception:
            pass


def trigger_background_worker():
    """
    Spawns an asynchronous in-process background worker daemon if one is not already running.
    Ensures campaign queues are actively dispatched in local development and environments
    without external cron / systemd workers.
    """
    from django.db import connection
    if connection.in_atomic_block and str(getattr(settings, 'DATABASES', {}).get('default', {}).get('ENGINE', '')).endswith('sqlite3'):
        return
    global _worker_running
    with _worker_lock:
        if _worker_running:
            return
        _worker_running = True
        worker_thread = threading.Thread(
            target=_background_worker_loop,
            name="CampaignQueueWorkerThread",
            daemon=True,
        )
        worker_thread.start()


# ---------------------------------------------------------------------------
# AI-Powered Outreach Analysis, Sectioned Draft Generation (10/Section) & Send
# ---------------------------------------------------------------------------

SECTION_SIZE = 10
MAX_SECTIONS_PER_CAMPAIGN = 5
MAX_RECIPIENTS_PER_CAMPAIGN = SECTION_SIZE * MAX_SECTIONS_PER_CAMPAIGN  # 50 drafts per campaign (5 sections × 10)

_LIVE_SYNC_LOCK = threading.Lock()
_LIVE_SYNC_CACHE_KEY = "prospects:campaign_live_sync_lock"
_LIVE_SYNC_CACHE_TTL_SECONDS = 180


def _acquire_live_sync_lock() -> Optional[str]:
    if not _LIVE_SYNC_LOCK.acquire(blocking=False):
        return None
    token = uuid.uuid4().hex
    try:
        acquired = cache.add(_LIVE_SYNC_CACHE_KEY, token, timeout=_LIVE_SYNC_CACHE_TTL_SECONDS)
    except Exception:
        return token
    if not acquired:
        try:
            _LIVE_SYNC_LOCK.release()
        except RuntimeError:
            pass
        return None
    return token


def _release_live_sync_lock(token: Optional[str]) -> None:
    try:
        if token:
            try:
                if cache.get(_LIVE_SYNC_CACHE_KEY) == token:
                    cache.delete(_LIVE_SYNC_CACHE_KEY)
            except Exception:
                pass
    finally:
        try:
            if _LIVE_SYNC_LOCK.locked():
                _LIVE_SYNC_LOCK.release()
        except RuntimeError:
            pass


def _get_next_ai_outreach_campaign_number(base_name: str = "AI Outreach Campaign") -> int:
    open_statuses = {
        EmailCampaign.Status.DRAFT,
        EmailCampaign.Status.QUEUED,
        EmailCampaign.Status.RUNNING,
        EmailCampaign.Status.PAUSED,
    }
    pattern = re.compile(
        rf"^{re.escape(base_name)}\s*(?:—|-)\s*Campaign\s+(\d+)$",
        re.IGNORECASE,
    )
    used_numbers = set()
    has_open_legacy = False
    for cname, cstatus in EmailCampaign.objects.values_list("name", "status"):
        name_str = (cname or "").strip()
        match = pattern.match(name_str)
        if match:
            try:
                used_numbers.add(int(match.group(1)))
            except (TypeError, ValueError):
                pass
        elif name_str == f"{base_name} (Unsent Mail Auto-Draft)" and cstatus in open_statuses:
            has_open_legacy = True
    if has_open_legacy:
        used_numbers.add(1)
    return max(used_numbers, default=0) + 1


def _resolve_prospect_owner_user(
    creator_username: Optional[str],
    user_cache: Optional[Dict[str, Any]] = None,
):
    uname = (creator_username or "").strip()
    if not uname:
        return None
    key = uname.lower()
    if user_cache is not None and key in user_cache:
        return user_cache[key]
    from django.contrib.auth import get_user_model
    User = get_user_model()
    owner = User.objects.filter(username=uname).first()
    if not owner:
        owner = User.objects.filter(username__iexact=uname).first()
    if user_cache is not None:
        user_cache[key] = owner
    return owner


def _resolve_campaign_sender_email(owner_user) -> str:
    google_creds = get_mail_credentials(owner_user)
    return (
        google_creds.email
        if google_creds and getattr(google_creds, "email", None)
        else (getattr(owner_user, "email", "") or f"{owner_user.username}@marketintel.local")
    )


def _get_vector_db_portfolio_summary(user) -> Dict[str, Any]:
    """
    Inspect the PostgreSQL + pgvector RAG Knowledge Base (`rag` app) to report
    whether company portfolio documents are ingested and ready for AI email drafting.
    """
    try:
        from rag.models import KnowledgeBase, KnowledgeDocumentChunk
        from rag.services import knowledge_base_service

        if user and getattr(user, "is_authenticated", False):
            kb_qs = knowledge_base_service.accessible_knowledge_bases(user).filter(is_active=True)
        else:
            kb_qs = KnowledgeBase.objects.filter(is_active=True)

        doc_names: List[str] = []
        ready_kbs = []
        for kb in kb_qs:
            r_docs = list(knowledge_base_service.ready_documents(kb).values_list("original_filename", flat=True))
            if r_docs:
                ready_kbs.append(kb)
                for d_name in r_docs:
                    if d_name and d_name not in doc_names:
                        doc_names.append(d_name)

        chunks_count = 0
        if ready_kbs:
            chunks_count = KnowledgeDocumentChunk.objects.filter(
                knowledge_base__in=ready_kbs,
                document__status="READY",
                document__is_active=True,
            ).count()

        return {
            "portfolio_ready": len(doc_names) > 0 and chunks_count > 0,
            "portfolio_documents": doc_names,
            "portfolio_chunks_count": chunks_count,
        }
    except Exception as exc:
        logger.debug("Vector DB portfolio summary check skipped: %s", exc)
        return {
            "portfolio_ready": False,
            "portfolio_documents": [],
            "portfolio_chunks_count": 0,
        }


def _get_all_sent_outreach_markers() -> tuple[set, set]:
    """
    Collects all prospect IDs and lowercase email addresses that have ALREADY been sent
    an email across every channel in the system:
      1. OutreachEmail (status in SENT, RECEIVED RESPONSE, OPENED)
      2. EmailCampaignRecipient (status == SENT)
      3. CommunicationActivity (activity_type == EMAIL_SENT)
      4. EmailThreadMessage (direction == OUTBOUND, status == SENT)
      5. LeadQualification (email_status not in ['', 'Not Sent'])
    Returns (sent_prospect_ids, sent_emails).
    """
    from prospects.models import EmailThreadMessage, LeadQualification

    sent_prospect_ids = set(
        OutreachEmail.objects.filter(
            prospect__isnull=False,
            status__in=["SENT", "RECEIVED RESPONSE", "OPENED"],
        ).values_list("prospect_id", flat=True)
    )
    sent_prospect_ids.update(
        EmailCampaignRecipient.objects.filter(
            prospect__isnull=False,
            status=EmailCampaignRecipient.Status.SENT,
        ).values_list("prospect_id", flat=True)
    )
    sent_prospect_ids.update(
        CommunicationActivity.objects.filter(
            prospect__isnull=False,
            activity_type="EMAIL_SENT",
        ).values_list("prospect_id", flat=True)
    )
    sent_prospect_ids.update(
        EmailThreadMessage.objects.filter(
            direction=EmailThreadMessage.Direction.OUTBOUND,
            status=EmailThreadMessage.Status.SENT,
            thread__prospect__isnull=False,
        ).values_list("thread__prospect_id", flat=True)
    )
    sent_prospect_ids.update(
        LeadQualification.objects.exclude(
            email_status__in=["", "Not Sent"]
        ).exclude(
            email_status__isnull=True
        ).values_list("prospect_id", flat=True)
    )

    sent_emails = {
        str(e).strip().lower()
        for e in OutreachEmailRecipient.objects.filter(
            outreach_email__status__in=["SENT", "RECEIVED RESPONSE", "OPENED"]
        ).values_list("email_address", flat=True)
        if e
    }
    sent_emails.update(
        str(e).strip().lower()
        for e in EmailCampaignRecipient.objects.filter(
            status=EmailCampaignRecipient.Status.SENT
        ).values_list("email_address", flat=True)
        if e
    )
    for to_list, corr_email in EmailThreadMessage.objects.filter(
        direction=EmailThreadMessage.Direction.OUTBOUND,
        status=EmailThreadMessage.Status.SENT,
    ).values_list("to_emails", "thread__correspondent_email"):
        if corr_email:
            clean_c = extract_clean_email(str(corr_email))
            if clean_c:
                sent_emails.add(clean_c.lower())
        if isinstance(to_list, list):
            for addr in to_list:
                clean_a = extract_clean_email(str(addr or ""))
                if clean_a:
                    sent_emails.add(clean_a.lower())

    return sent_prospect_ids, sent_emails


def get_unsent_outreach_records(
    user,
    search: str = "",
    prospect_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Analyze all accessible outreach records (`Prospect` & `ProspectContact`) and identify
    every outreach record where an email has NOT yet been sent for THAT prospect.
    Extracts company name, mobile/phone number, email address, product/service/solution
    offerings, primary industries, and other relevant outreach details.
    """
    from django.db.models import Q

    prospects_qs = (
        Prospect.objects.all()
        .select_related("lead_qualification")
        .prefetch_related("key_contacts", "offerings")
        .exclude(lead_qualification__qualification_status="Lead Freeze")
        .order_by("-updated_at")
    )

    if not user.is_superuser and hasattr(user, "profile"):
        role = getattr(user.profile, "role", None)
        if role in ("PRE", "LQ"):
            prospects_qs = prospects_qs.filter(created_by=user.username)

    if prospect_ids:
        clean_ids = [str(pid).strip() for pid in prospect_ids if str(pid).strip()]
        if clean_ids:
            prospects_qs = prospects_qs.filter(id__in=clean_ids)

    sent_prospect_ids, _sent_emails = _get_all_sent_outreach_markers()

    search_low = (search or "").strip().lower()
    records: List[Dict[str, Any]] = []

    for p in prospects_qs:
        # Check strictly whether THIS outreach prospect has already been sent an email
        if p.id in sent_prospect_ids:
            continue

        contacts = list(p.key_contacts.all())
        primary_contact = None
        chosen_email = ""

        # Check key contacts first for a valid email, or company official email
        cand_company_email = extract_clean_email(p.official_email_address or "")
        if cand_company_email:
            try:
                cand_company_email = validate_and_sanitize_recipient(cand_company_email).lower()
            except Exception:
                cand_company_email = ""

        for c in contacts:
            c_email = extract_clean_email(c.official_email or "")
            if c_email:
                try:
                    c_email = validate_and_sanitize_recipient(c_email).lower()
                except Exception:
                    c_email = ""
            if c_email:
                primary_contact = c
                chosen_email = c_email
                break
            if not primary_contact:
                primary_contact = c

        if not chosen_email and cand_company_email:
            chosen_email = cand_company_email

        if not chosen_email:
            continue

        offerings_objs = list(p.offerings.all())
        products = [o.name for o in offerings_objs if o.offering_type == "PRODUCT" and o.name]
        services = [o.name for o in offerings_objs if o.offering_type == "SERVICE" and o.name]
        solutions = [o.name for o in offerings_objs if o.offering_type == "SOLUTION" and o.name]
        all_offerings = products + services + solutions

        phone_number = (
            (p.official_phone_number or "").strip()
            or (getattr(primary_contact, "phone_number", "") or "").strip()
        )
        recipient_name = (
            (primary_contact.contact_name if primary_contact and primary_contact.contact_name else "")
            or p.company_name
            or ""
        ).strip()
        designation = (
            (primary_contact.designation if primary_contact and primary_contact.designation else "")
            or "Company Official Contact"
        ).strip()

        if search_low:
            haystack = " ".join([
                p.company_name or "",
                chosen_email,
                phone_number,
                p.primary_industries or "",
                p.country_head_office or "",
                recipient_name,
                " ".join(all_offerings),
            ]).lower()
            if search_low not in haystack:
                continue

        records.append({
            "prospect_id": str(p.id),
            "prospect_contact_id": str(primary_contact.id) if primary_contact else None,
            "company_name": p.company_name or "",
            "phone_number": phone_number,
            "email": chosen_email,
            "recipient_name": recipient_name,
            "designation": designation,
            "primary_industries": p.primary_industries or "",
            "offering_type": p.primary_offering_type or "",
            "products": products,
            "services": services,
            "solutions": solutions,
            "offerings": all_offerings,
            "country": p.country_head_office or "",
            "address": p.complete_address or "",
            "website": p.official_website_url or "",
            "company_structure": p.company_structure or "",
            "ownership_sector": p.ownership_sector or "",
            "created_by": (p.created_by or "").strip(),
            "lq_status": getattr(getattr(p, "lead_qualification", None), "qualification_status", "Unqualified"),
        })

    portfolio_info = _get_vector_db_portfolio_summary(user)
    total_unsent = len(records)
    estimated_sections = (total_unsent + SECTION_SIZE - 1) // SECTION_SIZE if total_unsent > 0 else 0
    estimated_campaigns = (
        (total_unsent + MAX_RECIPIENTS_PER_CAMPAIGN - 1) // MAX_RECIPIENTS_PER_CAMPAIGN
        if total_unsent > 0
        else 0
    )

    return {
        "records": records,
        "total_unsent": total_unsent,
        "section_size": SECTION_SIZE,
        "max_per_campaign": MAX_RECIPIENTS_PER_CAMPAIGN,
        "max_sections_per_campaign": MAX_SECTIONS_PER_CAMPAIGN,
        "estimated_sections": estimated_sections,
        "estimated_campaigns": estimated_campaigns,
        "portfolio": portfolio_info,
    }


def _chunk_list(items: List[Any], chunk_size: int) -> List[List[Any]]:
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def create_ai_drafted_campaigns(
    user,
    name: str,
    user_prompt: str = "",
    tone: str = "professional",
    prospect_ids: Optional[List[str]] = None,
    recipients_data: Optional[List[Any]] = None,
    template_id: Optional[str] = None,
    signature_id: Optional[str] = None,
    open_tracking_enabled: bool = True,
    attachments_files: Optional[List[Any]] = None,
    interval_seconds: int = 90,
) -> List[EmailCampaign]:
    """
    1. Identifies all eligible outreach records with unsent emails (or uses explicit selection).
    2. Checks our company portfolio in the PostgreSQL + pgvector Knowledge Base and uses
       Google Gemini to generate a unique, customized email draft (subject + body) for each
       outreach record based on Company Name, Mobile Number, Email, Product Offerings, and
       Primary Industries.
    3. Splits into campaigns of at most 50 drafts per campaign (5 sections × 10 drafts).
       If there are more than 50 drafts (e.g. 51–100+), creates Campaign 1 (50 drafts,
       Sections 1–5), Campaign 2 (next 50 drafts, Sections 1–5), and so on.
    4. Within each campaign, organizes drafts into sections of 10 (Section 1..5) in DRAFT status.
    """
    from concurrent.futures import ThreadPoolExecutor
    from django.db import close_old_connections
    from email_ai.services import generate_personalized_email

    if not name or not name.strip():
        name = f"AI Outreach Campaign — {timezone.now().strftime('%b %d, %Y %H:%M')}"

    from prospects.tracking_utils import (
        global_open_tracking_enabled,
        validate_tracking_configuration,
    )
    effective_tracking = False
    if open_tracking_enabled and global_open_tracking_enabled():
        valid_cfg, _cfg_err = validate_tracking_configuration()
        if valid_cfg:
            effective_tracking = True

    files = attachments_files or []
    total_size = sum(f.size for f in files)
    if total_size > MAX_TOTAL_ATTACHMENT_SIZE:
        raise ValueError("Total attachment size exceeds the 25MB limit.")

    for f in files:
        if f.size > MAX_SINGLE_ATTACHMENT_SIZE:
            raise ValueError(f"Attachment {f.name} exceeds the 10MB limit.")
        ext = f.name.split(".")[-1].lower() if "." in f.name else ""
        if ext in DISALLOWED_EXTENSIONS:
            raise ValueError(f"Attachment type .{ext} is not allowed.")

    # Resolve target outreach records
    unsent_analysis = get_unsent_outreach_records(user=user, prospect_ids=prospect_ids)
    target_records = list(unsent_analysis["records"])

    # If explicit recipients_data was provided and no unsent records matched, merge/resolve them
    if recipients_data and not target_records:
        seen = set()
        matcher = ProspectMatcher(user)
        for item in recipients_data:
            raw_email = item.get("email") or item.get("email_address") if isinstance(item, dict) else str(item)
            clean_addr = extract_clean_email(raw_email)
            if not clean_addr:
                continue
            try:
                validated = validate_and_sanitize_recipient(clean_addr).lower()
            except Exception:
                continue
            if validated in seen:
                continue
            seen.add(validated)

            p_id = item.get("prospect_id") if isinstance(item, dict) else None
            c_id = item.get("prospect_contact_id") if isinstance(item, dict) else None
            matched_p = Prospect.objects.prefetch_related("key_contacts", "offerings").filter(id=p_id).first() if p_id else None
            matched_c = ProspectContact.objects.filter(id=c_id).first() if c_id else None
            if not matched_p:
                m_res = matcher.match_address(validated)
                if m_res.get("prospect_id"):
                    matched_p = Prospect.objects.prefetch_related("key_contacts", "offerings").filter(id=m_res["prospect_id"]).first()
                if m_res.get("prospect_contact_id"):
                    matched_c = ProspectContact.objects.filter(id=m_res["prospect_contact_id"]).first()

            offerings_objs = list(matched_p.offerings.all()) if matched_p else []
            products = [o.name for o in offerings_objs if o.offering_type == "PRODUCT" and o.name]
            services = [o.name for o in offerings_objs if o.offering_type == "SERVICE" and o.name]
            solutions = [o.name for o in offerings_objs if o.offering_type == "SOLUTION" and o.name]
            target_records.append({
                "prospect_id": str(matched_p.id) if matched_p else None,
                "prospect_contact_id": str(matched_c.id) if matched_c else None,
                "company_name": (matched_p.company_name if matched_p else (item.get("company_name") if isinstance(item, dict) else "")) or "",
                "phone_number": (matched_p.official_phone_number if matched_p else "") or (matched_c.phone_number if matched_c else "") or "",
                "email": validated,
                "recipient_name": (item.get("name") if isinstance(item, dict) else None) or (matched_c.contact_name if matched_c else (matched_p.company_name if matched_p else "")),
                "designation": (matched_c.designation if matched_c else "") or "Contact",
                "primary_industries": (matched_p.primary_industries if matched_p else "") or "",
                "offering_type": (matched_p.primary_offering_type if matched_p else "") or "",
                "products": products,
                "services": services,
                "solutions": solutions,
                "offerings": products + services + solutions,
                "country": (matched_p.country_head_office if matched_p else "") or "",
                "address": (matched_p.complete_address if matched_p else "") or "",
                "website": (matched_p.official_website_url if matched_p else "") or "",
                "created_by": (matched_p.created_by if matched_p else "") or "",
            })

    if not target_records:
        raise ValueError("No eligible outreach records with unsent emails were found.")

    is_manager_or_super = bool(
        getattr(user, "is_superuser", False)
        or getattr(getattr(user, "profile", None), "role", None) == "MANAGER"
    )
    user_cache: Dict[str, Any] = {}
    grouped_by_owner: Dict[Any, tuple[Any, List[Dict[str, Any]]]] = {}
    for rec in target_records:
        if rec.get("prospect_id"):
            owner_user = _resolve_prospect_owner_user(rec.get("created_by"), user_cache)
            if not is_manager_or_super:
                if not owner_user or owner_user.id != user.id:
                    continue
            else:
                if not owner_user:
                    continue
        else:
            owner_user = user

        if owner_user.id not in grouped_by_owner:
            grouped_by_owner[owner_user.id] = (owner_user, [])
        grouped_by_owner[owner_user.id][1].append(rec)

    if not grouped_by_owner:
        raise ValueError("No eligible outreach records with a valid prospect creator were found.")

    effective_prompt = (user_prompt or "").strip() or (
        "Write a highly customized B2B outreach email introducing our company portfolio and solutions, "
        "tailored specifically to this company's primary industries, product/service offerings, and business profile."
    )

    # Read attachment bytes once so multiple split campaigns can each receive their own attachment copy
    attachment_payloads = []
    for f in files:
        f.seek(0)
        raw_data = f.read()
        mtype, _ = mimetypes.guess_type(f.name)
        attachment_payloads.append({
            "name": f.name,
            "mime_type": mtype or "application/octet-stream",
            "size": len(raw_data),
            "bytes": raw_data,
        })

    from django.db import connection
    from django.core.files.base import ContentFile

    base_name = name.strip()
    created_campaigns: List[EmailCampaign] = []

    for owner_user, owner_records in grouped_by_owner.values():
        owner_sender_email = _resolve_campaign_sender_email(owner_user)

        def _draft_one(rec: Dict[str, Any], _owner=owner_user) -> Dict[str, Any]:
            close_old_connections()
            try:
                gen = generate_personalized_email(
                    user=_owner,
                    user_prompt=effective_prompt,
                    source_context="CAMPAIGN",
                    tone=tone or "professional",
                    prospect_id=rec.get("prospect_id"),
                    recipient_emails=[rec["email"]],
                    company_name=rec.get("company_name") or "",
                    recipient_name=rec.get("recipient_name") or "",
                    industry=rec.get("primary_industries") or "",
                    country=rec.get("country") or "",
                    phone_number=rec.get("phone_number") or "",
                    campaign_name=base_name,
                )
                return {
                    "record": rec,
                    "subject": (gen.get("subject") or "").strip() or f"Strategic Alignment — {rec.get('company_name') or base_name}",
                    "body": (gen.get("body") or "").strip(),
                    "provider": gen.get("provider") or "gemini",
                    "model": gen.get("model") or "",
                    "portfolio_sources": (gen.get("context_used") or {}).get("portfolio_sources") or [],
                }
            finally:
                close_old_connections()

        if connection.in_atomic_block or len(owner_records) <= 2:
            drafted_items = [_draft_one(r) for r in owner_records]
        else:
            max_workers = min(4, len(owner_records))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                drafted_items = list(executor.map(_draft_one, owner_records))

        prospect_map = {
            str(p.id): p
            for p in Prospect.objects.filter(
                id__in=[r["prospect_id"] for r in owner_records if r.get("prospect_id")]
            )
        }
        contact_map = {
            str(c.id): c
            for c in ProspectContact.objects.filter(
                id__in=[r["prospect_contact_id"] for r in owner_records if r.get("prospect_contact_id")]
            )
        }

        batches = _chunk_list(drafted_items, MAX_RECIPIENTS_PER_CAMPAIGN)

        with transaction.atomic():
            for batch_idx, batch_items in enumerate(batches, start=1):
                camp_name = base_name if len(batches) == 1 else f"{base_name} — Campaign {batch_idx}"
                first_subject = batch_items[0]["subject"] if batch_items else camp_name
                first_body = batch_items[0]["body"] if batch_items else effective_prompt

                campaign = EmailCampaign.objects.create(
                    name=camp_name,
                    created_by=owner_user,
                    sender_email=owner_sender_email,
                    subject=first_subject,
                    body=first_body,
                    template_id=str(template_id) if template_id else None,
                    signature_id=str(signature_id) if signature_id else None,
                    open_tracking_enabled=effective_tracking,
                    interval_seconds=max(90, int(interval_seconds or 90)),
                    status=EmailCampaign.Status.DRAFT,
                    next_eligible_at=None,
                )

                recipient_objs = []
                for idx, item in enumerate(batch_items):
                    rec = item["record"]
                    sec_num = (idx // SECTION_SIZE) + 1
                    snapshot = {
                        "company_name": rec.get("company_name") or "",
                        "phone_number": rec.get("phone_number") or "",
                        "email": rec.get("email") or "",
                        "recipient_name": rec.get("recipient_name") or "",
                        "designation": rec.get("designation") or "",
                        "primary_industries": rec.get("primary_industries") or "",
                        "offering_type": rec.get("offering_type") or "",
                        "products": rec.get("products") or [],
                        "services": rec.get("services") or [],
                        "solutions": rec.get("solutions") or [],
                        "offerings": rec.get("offerings") or [],
                        "country": rec.get("country") or "",
                        "address": rec.get("address") or "",
                        "website": rec.get("website") or "",
                        "ai_provider": item.get("provider") or "gemini",
                        "ai_model": item.get("model") or "",
                        "portfolio_sources": item.get("portfolio_sources") or [],
                        "user_prompt": effective_prompt,
                        "tone": tone or "professional",
                    }
                    recipient_objs.append(
                        EmailCampaignRecipient(
                            campaign=campaign,
                            email_address=rec["email"],
                            recipient_name=rec.get("recipient_name") or rec.get("company_name") or None,
                            prospect=prospect_map.get(str(rec.get("prospect_id"))),
                            prospect_contact=contact_map.get(str(rec.get("prospect_contact_id"))),
                            section_number=sec_num,
                            custom_subject=item["subject"][:512],
                            custom_body=item["body"],
                            outreach_snapshot=snapshot,
                            queue_order=idx,
                            status=EmailCampaignRecipient.Status.DRAFT,
                            scheduled_for=None,
                        )
                    )

                EmailCampaignRecipient.objects.bulk_create(recipient_objs)

                for att_info in attachment_payloads:
                    EmailCampaignAttachment.objects.create(
                        campaign=campaign,
                        file=ContentFile(att_info["bytes"], name=att_info["name"]),
                        original_filename=att_info["name"],
                        mime_type=att_info["mime_type"],
                        size=att_info["size"],
                    )

                created_campaigns.append(campaign)

    return created_campaigns


def create_ai_drafted_campaign(
    user,
    name: str,
    user_prompt: str = "",
    tone: str = "professional",
    prospect_ids: Optional[List[str]] = None,
    recipients_data: Optional[List[Any]] = None,
    template_id: Optional[str] = None,
    signature_id: Optional[str] = None,
    open_tracking_enabled: bool = True,
    attachments_files: Optional[List[Any]] = None,
    interval_seconds: int = 90,
) -> EmailCampaign:
    """
    Wrapper returning the primary EmailCampaign (while creating additional campaigns
    automatically in `_created_campaigns` whenever records exceed 50).
    """
    campaigns = create_ai_drafted_campaigns(
        user=user,
        name=name,
        user_prompt=user_prompt,
        tone=tone,
        prospect_ids=prospect_ids,
        recipients_data=recipients_data,
        template_id=template_id,
        signature_id=signature_id,
        open_tracking_enabled=open_tracking_enabled,
        attachments_files=attachments_files,
        interval_seconds=interval_seconds,
    )
    primary = campaigns[0]
    primary._created_campaigns = campaigns
    return primary


def update_campaign_recipient_draft(
    campaign: EmailCampaign,
    recipient_id: str,
    custom_subject: str,
    custom_body: str,
) -> EmailCampaignRecipient:
    """
    Allows the user to edit an individual AI-generated email draft within a section before sending.
    """
    recipient = campaign.recipients.filter(id=recipient_id).first()
    if not recipient:
        raise ValueError("Recipient draft not found in this campaign.")
    if recipient.status == EmailCampaignRecipient.Status.SENT:
        raise ValueError("Cannot edit a draft that has already been sent.")

    if custom_subject is not None and custom_subject.strip():
        recipient.custom_subject = custom_subject.strip()[:512]
    if custom_body is not None and custom_body.strip():
        recipient.custom_body = custom_body.strip()

    recipient.save(update_fields=["custom_subject", "custom_body"])
    return recipient


def regenerate_campaign_recipient_draft(
    campaign: EmailCampaign,
    recipient_id: str,
    user,
    user_prompt: str = "",
    tone: str = "professional",
) -> EmailCampaignRecipient:
    """
    Re-runs Google Gemini + Vector DB portfolio lookup for a single recipient draft in a section.
    """
    from email_ai.services import generate_personalized_email

    recipient = campaign.recipients.select_related("prospect", "prospect_contact").filter(id=recipient_id).first()
    if not recipient:
        raise ValueError("Recipient draft not found in this campaign.")
    if recipient.status == EmailCampaignRecipient.Status.SENT:
        raise ValueError("Cannot regenerate a draft that has already been sent.")

    snap = dict(recipient.outreach_snapshot or {})
    effective_prompt = (
        (user_prompt or "").strip()
        or snap.get("user_prompt")
        or "Write a highly customized B2B outreach email introducing our company portfolio and solutions, tailored to this company."
    )
    effective_tone = (tone or "").strip() or snap.get("tone") or "professional"

    gen = generate_personalized_email(
        user=user,
        user_prompt=effective_prompt,
        source_context="CAMPAIGN",
        tone=effective_tone,
        prospect_id=str(recipient.prospect_id) if recipient.prospect_id else None,
        recipient_emails=[recipient.email_address],
        company_name=snap.get("company_name") or (recipient.prospect.company_name if recipient.prospect else ""),
        recipient_name=recipient.recipient_name or snap.get("recipient_name") or "",
        industry=snap.get("primary_industries") or (recipient.prospect.primary_industries if recipient.prospect else ""),
        country=snap.get("country") or (recipient.prospect.country_head_office if recipient.prospect else ""),
        phone_number=snap.get("phone_number") or (recipient.prospect.official_phone_number if recipient.prospect else ""),
        campaign_name=campaign.name,
        current_subject=recipient.custom_subject,
        current_body=recipient.custom_body,
    )

    recipient.custom_subject = ((gen.get("subject") or "").strip() or recipient.custom_subject)[:512]
    recipient.custom_body = (gen.get("body") or "").strip() or recipient.custom_body
    snap["ai_provider"] = gen.get("provider") or "gemini"
    snap["ai_model"] = gen.get("model") or ""
    snap["portfolio_sources"] = (gen.get("context_used") or {}).get("portfolio_sources") or snap.get("portfolio_sources") or []
    snap["user_prompt"] = effective_prompt
    snap["tone"] = effective_tone
    recipient.outreach_snapshot = snap
    recipient.save(update_fields=["custom_subject", "custom_body", "outreach_snapshot"])
    return recipient


def send_campaign_section(
    campaign: EmailCampaign,
    section_number: int,
    user,
    updated_drafts: Optional[List[Dict[str, Any]]] = None,
) -> EmailCampaign:
    """
    Queues and starts sending ONLY the customized email drafts in `section_number`
    (up to 10 emails in that section), enforcing the 90-second interval between consecutive emails.
    Other sections remain in DRAFT status until their own Send button is clicked.
    """
    if campaign.status == EmailCampaign.Status.CANCELLED:
        raise ValueError("Cannot send a section of a cancelled campaign.")

    google_creds = get_mail_credentials(campaign.created_by)
    if not google_creds:
        google_creds = get_mail_credentials(user)
    if not google_creds:
        raise ValueError("Google Mail is not connected. Connect Gmail before sending campaign emails.")

    sec_num = int(section_number or 1)
    if sec_num < 1:
        raise ValueError("Invalid section number.")

    with transaction.atomic():
        if google_creds.email and campaign.sender_email != google_creds.email:
            campaign.sender_email = google_creds.email
            campaign.save(update_fields=["sender_email"])

        # Apply any inline review edits submitted with the Send click
        if updated_drafts and isinstance(updated_drafts, list):
            for d_item in updated_drafts:
                if not isinstance(d_item, dict):
                    continue
                r_id = d_item.get("id") or d_item.get("recipient_id")
                if not r_id:
                    continue
                rec_obj = campaign.recipients.filter(id=r_id, section_number=sec_num).first()
                if rec_obj and rec_obj.status != EmailCampaignRecipient.Status.SENT:
                    subj_val = d_item.get("custom_subject")
                    body_val = d_item.get("custom_body")
                    changed = []
                    if subj_val is not None and str(subj_val).strip():
                        rec_obj.custom_subject = str(subj_val).strip()[:512]
                        changed.append("custom_subject")
                    if body_val is not None and str(body_val).strip():
                        rec_obj.custom_body = str(body_val).strip()
                        changed.append("custom_body")
                    if changed:
                        rec_obj.save(update_fields=changed)

        section_recipients = list(
            campaign.recipients.select_for_update()
            .filter(section_number=sec_num)
            .order_by("queue_order")
        )
        if not section_recipients:
            raise ValueError(f"Section {sec_num} does not exist in this campaign.")

        eligible_to_queue = [
            r for r in section_recipients
            if r.status in (EmailCampaignRecipient.Status.DRAFT, EmailCampaignRecipient.Status.FAILED)
        ]
        already_queued = [
            r for r in section_recipients
            if r.status in (
                EmailCampaignRecipient.Status.PENDING,
                EmailCampaignRecipient.Status.SENDING,
                EmailCampaignRecipient.Status.RETRY_PENDING,
            )
        ]

        if not eligible_to_queue and not already_queued:
            raise ValueError(f"All emails in Section {sec_num} have already been sent.")

        now = timezone.now()
        if campaign.last_sent_at:
            earliest_eligible = max(now, campaign.last_sent_at + timedelta(seconds=campaign.interval_seconds))
        else:
            earliest_eligible = now

        # Check if another recipient in the campaign is already scheduled/active
        existing_scheduled = (
            campaign.recipients.filter(
                status__in=[
                    EmailCampaignRecipient.Status.PENDING,
                    EmailCampaignRecipient.Status.SENDING,
                    EmailCampaignRecipient.Status.RETRY_PENDING,
                ],
                scheduled_for__isnull=False,
            )
            .exists()
        )

        for idx, r in enumerate(eligible_to_queue):
            r.status = EmailCampaignRecipient.Status.PENDING
            r.error_message = None
            if idx == 0 and not existing_scheduled:
                r.scheduled_for = earliest_eligible
                existing_scheduled = True
            else:
                r.scheduled_for = None
            r.save(update_fields=["status", "error_message", "scheduled_for"])

        # Ensure at least one PENDING recipient has scheduled_for set
        first_pending = (
            campaign.recipients.filter(status=EmailCampaignRecipient.Status.PENDING)
            .order_by("queue_order")
            .first()
        )
        if first_pending and not first_pending.scheduled_for:
            first_pending.scheduled_for = earliest_eligible
            first_pending.save(update_fields=["scheduled_for"])

        campaign.interval_seconds = max(90, int(campaign.interval_seconds or 90))
        if campaign.status not in (EmailCampaign.Status.RUNNING, EmailCampaign.Status.QUEUED):
            campaign.status = EmailCampaign.Status.RUNNING if campaign.started_at else EmailCampaign.Status.QUEUED
        campaign.completed_at = None
        if not campaign.next_eligible_at or campaign.next_eligible_at < earliest_eligible:
            campaign.next_eligible_at = earliest_eligible
        campaign.save(update_fields=["interval_seconds", "status", "completed_at", "next_eligible_at"])

        transaction.on_commit(trigger_background_worker)

    return campaign


def _rebalance_campaign_sections(campaign: EmailCampaign) -> None:
    """
    Ensures all recipients in `campaign` have contiguous `queue_order` (0..N-1)
    and `section_number = (idx // 10) + 1` (10 drafts per section).
    """
    recs = list(campaign.recipients.all().order_by("queue_order", "created_at"))
    to_update = []
    for idx, r in enumerate(recs):
        expected_sec = (idx // SECTION_SIZE) + 1
        if r.queue_order != idx or r.section_number != expected_sec:
            r.queue_order = idx
            r.section_number = expected_sec
            to_update.append(r)
    if to_update:
        EmailCampaignRecipient.objects.bulk_update(to_update, ["queue_order", "section_number"])


def prune_sent_recipients_from_draft_campaigns(user=None) -> int:
    """
    Live Sent-Mail Check:
    Scans all unapproved `DRAFT` recipients across active/draft campaigns and removes
    any `DRAFT` recipient whose outreach prospect or email address has ALREADY been sent
    an email (via Outreach Workspace, Inbox, Gmail sync, or another campaign).
    Re-balances remaining sections (10 per section) and updates campaign completion state.
    Returns the number of stale draft recipients removed.
    """
    sent_prospect_ids, sent_emails = _get_all_sent_outreach_markers()
    if not sent_prospect_ids and not sent_emails:
        return 0

    draft_qs = EmailCampaignRecipient.objects.select_related("campaign").filter(
        status=EmailCampaignRecipient.Status.DRAFT,
        campaign__status__in=[
            EmailCampaign.Status.DRAFT,
            EmailCampaign.Status.QUEUED,
            EmailCampaign.Status.RUNNING,
            EmailCampaign.Status.PAUSED,
        ],
    )
    if user and getattr(user, "is_authenticated", False) and not user.is_superuser:
        role = getattr(getattr(user, "profile", None), "role", None)
        if role != "MANAGER":
            draft_qs = draft_qs.filter(campaign__created_by=user)

    affected_campaign_ids = set()
    delete_ids = []
    for rec in draft_qs:
        email_low = (rec.email_address or "").strip().lower()
        if rec.prospect_id:
            is_already_sent = rec.prospect_id in sent_prospect_ids
        else:
            is_already_sent = bool(email_low and email_low in sent_emails)
        if is_already_sent:
            delete_ids.append(rec.id)
            affected_campaign_ids.add(rec.campaign_id)

    if not delete_ids:
        return 0

    with transaction.atomic():
        deleted_count, _ = EmailCampaignRecipient.objects.filter(
            id__in=delete_ids,
            status=EmailCampaignRecipient.Status.DRAFT,
        ).delete()
        for cid in affected_campaign_ids:
            camp = EmailCampaign.objects.filter(id=cid).first()
            if not camp:
                continue
            if camp.recipients.count() == 0:
                camp.delete()
            else:
                _rebalance_campaign_sections(camp)
                _check_and_update_campaign_completion(camp)

    return deleted_count


def deduplicate_draft_campaign_recipients(user=None) -> int:
    """
    Scans open campaigns (DRAFT, QUEUED, RUNNING, PAUSED) and removes duplicate
    unapproved DRAFT recipients referencing the same prospect or email address,
    deleting any DRAFT campaigns that become empty and repairing exact duplicate
    auto-draft campaign names.
    """
    open_statuses = [
        EmailCampaign.Status.DRAFT,
        EmailCampaign.Status.QUEUED,
        EmailCampaign.Status.RUNNING,
        EmailCampaign.Status.PAUSED,
    ]
    is_manager_or_super = True
    if user and getattr(user, "is_authenticated", False) and not user.is_superuser:
        role = getattr(getattr(user, "profile", None), "role", None)
        if role != "MANAGER":
            is_manager_or_super = False

    rec_qs = (
        EmailCampaignRecipient.objects.select_related("campaign")
        .filter(campaign__status__in=open_statuses)
        .annotate(
            is_draft_rank=Case(
                When(status=EmailCampaignRecipient.Status.DRAFT, then=1),
                default=0,
                output_field=IntegerField(),
            )
        )
        .order_by("is_draft_rank", "campaign__created_at", "queue_order", "created_at")
    )
    if not is_manager_or_super:
        rec_qs = rec_qs.filter(campaign__created_by=user)

    seen_prospect_ids = set()
    seen_emails_no_prospect = set()
    delete_ids = []
    affected_campaign_ids = set()

    for rec in rec_qs:
        email_low = (rec.email_address or "").strip().lower()
        if rec.prospect_id:
            if rec.prospect_id in seen_prospect_ids and rec.status == EmailCampaignRecipient.Status.DRAFT:
                delete_ids.append(rec.id)
                affected_campaign_ids.add(rec.campaign_id)
            else:
                seen_prospect_ids.add(rec.prospect_id)
        elif email_low:
            if email_low in seen_emails_no_prospect and rec.status == EmailCampaignRecipient.Status.DRAFT:
                delete_ids.append(rec.id)
                affected_campaign_ids.add(rec.campaign_id)
            else:
                seen_emails_no_prospect.add(email_low)

    deleted_count = 0
    if delete_ids:
        with transaction.atomic():
            deleted_count, _ = EmailCampaignRecipient.objects.filter(
                id__in=delete_ids,
                status=EmailCampaignRecipient.Status.DRAFT,
            ).delete()
            for cid in affected_campaign_ids:
                camp = EmailCampaign.objects.filter(id=cid).first()
                if not camp:
                    continue
                if camp.recipients.count() == 0:
                    if camp.status == EmailCampaign.Status.DRAFT:
                        camp.delete()
                else:
                    _rebalance_campaign_sections(camp)
                    _check_and_update_campaign_completion(camp)

    # Resolve any surviving exact duplicate names among open DRAFT auto-draft campaigns
    auto_camps = list(
        EmailCampaign.objects.filter(name__startswith="AI Outreach Campaign").order_by("created_at")
    )
    seen_names = set()
    for camp in auto_camps:
        cname = (camp.name or "").strip()
        if cname in seen_names:
            can_rename = (
                camp.status == EmailCampaign.Status.DRAFT
                and (
                    user is None
                    or is_manager_or_super
                    or camp.created_by_id == getattr(user, "id", None)
                )
            )
            if can_rename:
                next_num = _get_next_ai_outreach_campaign_number("AI Outreach Campaign")
                new_name = f"AI Outreach Campaign — Campaign {next_num}"
                while new_name in seen_names:
                    next_num += 1
                    new_name = f"AI Outreach Campaign — Campaign {next_num}"
                camp.name = new_name
                camp.save(update_fields=["name"])
                seen_names.add(new_name)
                continue
        seen_names.add(cname)

    return deleted_count


def reconcile_draft_campaign_ownership(user=None) -> int:
    """
    Reassigns pure-DRAFT auto-draft campaigns ('AI Outreach Campaign...') whose
    prospects were entered by a different user back to the actual prospect
    creators (`Prospect.created_by`), and cleans up any empty leftover campaigns.
    Never modifies campaigns that have SENT/PENDING/SENDING/FAILED/RETRY_PENDING
    recipients, non-DRAFT campaign status, or manually composed campaigns.
    """
    is_manager_or_super = True
    if user and getattr(user, "is_authenticated", False) and not user.is_superuser:
        role = getattr(getattr(user, "profile", None), "role", None)
        if role != "MANAGER":
            is_manager_or_super = False

    draft_camps_qs = EmailCampaign.objects.filter(
        status=EmailCampaign.Status.DRAFT,
        name__startswith="AI Outreach Campaign",
    ).order_by("created_at")
    if not is_manager_or_super and user is not None:
        draft_camps_qs = draft_camps_qs.filter(created_by=user)

    open_statuses = [
        EmailCampaign.Status.DRAFT,
        EmailCampaign.Status.QUEUED,
        EmailCampaign.Status.RUNNING,
        EmailCampaign.Status.PAUSED,
    ]
    user_cache: Dict[str, Any] = {}
    reconciled_count = 0

    for camp in list(draft_camps_qs):
        # Safety guard: only reconcile pure unstarted DRAFT campaigns
        if camp.recipients.exclude(status=EmailCampaignRecipient.Status.DRAFT).exists():
            continue

        recs = list(
            camp.recipients.select_related("prospect").order_by("queue_order", "created_at")
        )
        if not recs:
            continue

        owners_by_id: Dict[Any, tuple[Any, List[EmailCampaignRecipient]]] = {}
        camp_owner_username_low = (getattr(camp.created_by, "username", "") or "").strip().lower()
        has_own_prospect_rec = False

        for rec in recs:
            if not rec.prospect_id or not rec.prospect:
                continue
            creator_uname = (rec.prospect.created_by or "").strip()
            if creator_uname and creator_uname.lower() == camp_owner_username_low:
                has_own_prospect_rec = True
            owner_user = _resolve_prospect_owner_user(creator_uname, user_cache)
            if not owner_user:
                continue
            if owner_user.id not in owners_by_id:
                owners_by_id[owner_user.id] = (owner_user, [])
            owners_by_id[owner_user.id][1].append(rec)

        if not owners_by_id:
            continue

        # Case A: Entire campaign belongs to a single other user (camp creator entered none of them)
        if len(owners_by_id) == 1 and not has_own_prospect_rec:
            only_owner, only_recs = next(iter(owners_by_id.values()))
            if only_owner.id != camp.created_by_id:
                with transaction.atomic():
                    camp.created_by = only_owner
                    camp.sender_email = _resolve_campaign_sender_email(only_owner)
                    camp.save(update_fields=["created_by", "sender_email"])
                reconciled_count += len(only_recs)
            continue

        # Case B: Mixed creators inside one wrongly-attributed DRAFT campaign
        foreign_entries = [
            (oid, ouser, orecs)
            for oid, (ouser, orecs) in owners_by_id.items()
            if oid != camp.created_by_id
        ]
        if not foreign_entries:
            continue

        with transaction.atomic():
            for _oid, owner_user, owner_recs in foreign_entries:
                owner_sender = _resolve_campaign_sender_email(owner_user)
                target_camps = list(
                    EmailCampaign.objects.filter(
                        created_by=owner_user,
                        status=EmailCampaign.Status.DRAFT,
                        name__startswith="AI Outreach Campaign",
                    )
                    .exclude(id=camp.id)
                    .order_by("created_at")
                )
                touched_targets = set()

                for rec in owner_recs:
                    rec_email_low = (rec.email_address or "").strip().lower()
                    already_in_owner_open = (
                        EmailCampaignRecipient.objects.filter(
                            campaign__created_by=owner_user,
                            campaign__status__in=open_statuses,
                            prospect_id=rec.prospect_id,
                        )
                        .exclude(campaign_id=camp.id)
                        .exists()
                    )
                    if already_in_owner_open:
                        rec.delete()
                        reconciled_count += 1
                        continue

                    target = None
                    for tc in reversed(target_camps):
                        if tc.recipients.count() >= MAX_RECIPIENTS_PER_CAMPAIGN:
                            continue
                        existing_tc_emails = {
                            (e or "").strip().lower()
                            for e in tc.recipients.values_list("email_address", flat=True)
                            if e
                        }
                        if rec_email_low in existing_tc_emails:
                            continue
                        target = tc
                        break

                    if target is None:
                        next_num = _get_next_ai_outreach_campaign_number("AI Outreach Campaign")
                        target = EmailCampaign.objects.create(
                            name=f"AI Outreach Campaign — Campaign {next_num}",
                            created_by=owner_user,
                            sender_email=owner_sender,
                            subject=rec.custom_subject or camp.subject or f"AI Outreach Campaign — Campaign {next_num}",
                            body=rec.custom_body or camp.body or "",
                            template_id=camp.template_id,
                            signature_id=camp.signature_id,
                            open_tracking_enabled=camp.open_tracking_enabled,
                            interval_seconds=camp.interval_seconds,
                            status=EmailCampaign.Status.DRAFT,
                            next_eligible_at=None,
                        )
                        target_camps.append(target)

                    rec.campaign = target
                    rec.queue_order = target.recipients.count()
                    rec.save(update_fields=["campaign", "queue_order"])
                    touched_targets.add(target.id)
                    reconciled_count += 1

                for tid in touched_targets:
                    tcamp = EmailCampaign.objects.filter(id=tid).first()
                    if tcamp:
                        _rebalance_campaign_sections(tcamp)

            camp_fresh = EmailCampaign.objects.filter(id=camp.id).first()
            if camp_fresh:
                if camp_fresh.recipients.count() == 0:
                    camp_fresh.delete()
                else:
                    _rebalance_campaign_sections(camp_fresh)

    return reconciled_count


def sync_live_unsent_outreach_ai_drafts(
    user,
    *,
    auto_draft: bool = True,
    campaign_id: Optional[str] = None,
    user_prompt: str = "",
    tone: str = "professional",
    max_drafts: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Live Sent-Mail Check & Automatic AI Drafting for Unsent Outreach Records:
    1. Checks all sent-mail channels (`OutreachEmail`, `EmailThreadMessage`, `CommunicationActivity`,
       `EmailCampaignRecipient(status='SENT')`, `LeadQualification.email_status`) and prunes any
       `DRAFT` campaign recipients that have already been sent an email.
    2. Deduplicates any duplicate unapproved `DRAFT` recipients across open campaigns.
    3. Reconciles pure-DRAFT auto-draft campaign ownership back to actual prospect creators.
    4. Identifies all accessible outreach records where an email has NOT yet been sent.
    5. When `auto_draft=True`, automatically generates customized Google Gemini + Vector DB portfolio
       email drafts owned strictly by each prospect's creator (`Prospect.created_by`), organizing
       them into sections of 10 drafts per section and capping each campaign at 50 drafts.
    """
    from email_ai.services import generate_personalized_email

    open_statuses = [
        EmailCampaign.Status.DRAFT,
        EmailCampaign.Status.QUEUED,
        EmailCampaign.Status.RUNNING,
        EmailCampaign.Status.PAUSED,
    ]
    is_manager_or_super = bool(
        getattr(user, "is_superuser", False)
        or getattr(getattr(user, "profile", None), "role", None) == "MANAGER"
    )

    def _get_open_campaigns() -> List[EmailCampaign]:
        qs = EmailCampaign.objects.filter(status__in=open_statuses).order_by("created_at")
        if not is_manager_or_super:
            qs = qs.filter(created_by=user)
        return list(qs)

    lock_token = None
    if auto_draft:
        lock_token = _acquire_live_sync_lock()
        if lock_token is None:
            open_campaigns = _get_open_campaigns()
            unsent_analysis = get_unsent_outreach_records(user=user)
            campaign = None
            if campaign_id:
                campaign = next((c for c in open_campaigns if str(c.id) == str(campaign_id)), None)
            if not campaign and open_campaigns:
                campaign = open_campaigns[-1]
            return {
                "unsent_analysis": unsent_analysis,
                "active_campaign": campaign,
                "active_campaigns": open_campaigns,
                "pruned_sent_drafts": 0,
                "deduplicated_drafts": 0,
                "reconciled_ownership_count": 0,
                "newly_drafted_count": 0,
                "remaining_undrafted_count": 0,
                "sync_in_progress": True,
                "checked_at": timezone.now().isoformat(),
            }

    try:
        pruned_count = prune_sent_recipients_from_draft_campaigns(user=user)
        deduplicated_count = deduplicate_draft_campaign_recipients(user=user)
        reconciled_count = reconcile_draft_campaign_ownership(user=user)
        unsent_analysis = get_unsent_outreach_records(user=user)
        unsent_records = unsent_analysis["records"]
        open_campaigns = _get_open_campaigns()

        # Requested campaign takes display priority if valid and open, else most recent open campaign
        campaign = None
        if campaign_id:
            campaign = next((c for c in open_campaigns if str(c.id) == str(campaign_id)), None)
        if not campaign and open_campaigns:
            campaign = open_campaigns[-1]

        # Collect already-drafted prospect IDs across ALL visible open/draft campaigns so we never double-draft
        existing_prospect_ids = {
            str(pid)
            for pid in EmailCampaignRecipient.objects.filter(
                campaign__in=open_campaigns,
                prospect__isnull=False,
            ).values_list("prospect_id", flat=True)
        }
        existing_emails_without_prospect = {
            (e or "").strip().lower()
            for e in EmailCampaignRecipient.objects.filter(
                campaign__in=open_campaigns,
                prospect__isnull=True,
            ).values_list("email_address", flat=True)
            if e
        }
        missing_records = [
            r for r in unsent_records
            if (
                str(r["prospect_id"]) not in existing_prospect_ids
                if r.get("prospect_id")
                else r["email"].lower() not in existing_emails_without_prospect
            )
        ]

        user_cache: Dict[str, Any] = {}
        draftable_pairs: List[tuple[Any, Dict[str, Any]]] = []
        for rec in missing_records:
            if not rec.get("prospect_id"):
                continue
            owner_user = _resolve_prospect_owner_user(rec.get("created_by"), user_cache)
            if not owner_user:
                continue
            if not is_manager_or_super and owner_user.id != user.id:
                continue
            draftable_pairs.append((owner_user, rec))

        total_missing = len(draftable_pairs)
        newly_drafted_count = 0

        if auto_draft and draftable_pairs:
            batch_pairs = (
                draftable_pairs[:max_drafts]
                if max_drafts is not None and max_drafts > 0
                else list(draftable_pairs)
            )
            effective_prompt = (user_prompt or "").strip() or (
                "Write a highly customized B2B outreach email introducing our company portfolio and solutions, "
                "tailored specifically to this company's primary industries, product/service offerings, and business profile."
            )

            grouped_pairs: Dict[Any, tuple[Any, List[Dict[str, Any]]]] = {}
            for owner_user, rec in batch_pairs:
                if owner_user.id not in grouped_pairs:
                    grouped_pairs[owner_user.id] = (owner_user, [])
                grouped_pairs[owner_user.id][1].append(rec)

            for owner_user, owner_batch in grouped_pairs.values():
                # Find an open campaign owned strictly by the prospect's creator with < 50 recipients
                capacity_campaign = None
                for oc in reversed(open_campaigns):
                    if oc.created_by_id == owner_user.id and oc.recipients.count() < MAX_RECIPIENTS_PER_CAMPAIGN:
                        capacity_campaign = oc
                        break

                records_for_existing = []
                overflow_records = list(owner_batch)
                if capacity_campaign:
                    existing_cap_emails = {
                        (e or "").strip().lower()
                        for e in capacity_campaign.recipients.values_list("email_address", flat=True)
                        if e
                    }
                    remaining_slots = MAX_RECIPIENTS_PER_CAMPAIGN - capacity_campaign.recipients.count()
                    if remaining_slots > 0:
                        eligible_for_cap = [
                            r for r in owner_batch
                            if (r.get("email") or "").strip().lower() not in existing_cap_emails
                        ]
                        chosen_cap = eligible_for_cap[:remaining_slots]
                        chosen_keys = {
                            str(r["prospect_id"]) if r.get("prospect_id") else r["email"].lower()
                            for r in chosen_cap
                        }
                        records_for_existing = chosen_cap
                        overflow_records = [
                            r for r in owner_batch
                            if (str(r["prospect_id"]) if r.get("prospect_id") else r["email"].lower()) not in chosen_keys
                        ]

                if records_for_existing and capacity_campaign:
                    from concurrent.futures import ThreadPoolExecutor
                    from django.db import close_old_connections, connection

                    def _draft_existing_one(rec: Dict[str, Any], _owner=owner_user, _camp_name=capacity_campaign.name) -> Dict[str, Any]:
                        close_old_connections()
                        try:
                            gen = generate_personalized_email(
                                user=_owner,
                                user_prompt=effective_prompt,
                                source_context="CAMPAIGN",
                                tone=tone or "professional",
                                prospect_id=rec.get("prospect_id"),
                                recipient_emails=[rec["email"]],
                                company_name=rec.get("company_name") or "",
                                recipient_name=rec.get("recipient_name") or "",
                                industry=rec.get("primary_industries") or "",
                                country=rec.get("country") or "",
                                phone_number=rec.get("phone_number") or "",
                                campaign_name=_camp_name,
                            )
                            return {
                                "record": rec,
                                "subject": (gen.get("subject") or "").strip() or f"Strategic Alignment — {rec.get('company_name') or _camp_name}",
                                "body": (gen.get("body") or "").strip(),
                                "provider": gen.get("provider") or "gemini",
                                "model": gen.get("model") or "",
                                "portfolio_sources": (gen.get("context_used") or {}).get("portfolio_sources") or [],
                            }
                        finally:
                            close_old_connections()

                    if connection.in_atomic_block or len(records_for_existing) <= 2:
                        drafted_existing = [_draft_existing_one(r) for r in records_for_existing]
                    else:
                        max_workers = min(4, len(records_for_existing))
                        with ThreadPoolExecutor(max_workers=max_workers) as executor:
                            drafted_existing = list(executor.map(_draft_existing_one, records_for_existing))

                    prospect_map = {
                        str(p.id): p
                        for p in Prospect.objects.filter(
                            id__in=[r["prospect_id"] for r in records_for_existing if r.get("prospect_id")]
                        )
                    }
                    contact_map = {
                        str(c.id): c
                        for c in ProspectContact.objects.filter(
                            id__in=[r["prospect_contact_id"] for r in records_for_existing if r.get("prospect_contact_id")]
                        )
                    }

                    with transaction.atomic():
                        latest_open = _get_open_campaigns()
                        cur_prospect_ids = {
                            str(pid)
                            for pid in EmailCampaignRecipient.objects.filter(
                                campaign__in=latest_open,
                                prospect__isnull=False,
                            ).values_list("prospect_id", flat=True)
                        }
                        cur_no_prospect_emails = {
                            (e or "").strip().lower()
                            for e in EmailCampaignRecipient.objects.filter(
                                campaign__in=latest_open,
                                prospect__isnull=True,
                            ).values_list("email_address", flat=True)
                            if e
                        }
                        cur_cap_emails = {
                            (e or "").strip().lower()
                            for e in capacity_campaign.recipients.values_list("email_address", flat=True)
                            if e
                        }

                        start_order = capacity_campaign.recipients.count()
                        new_recipient_objs = []
                        offset = 0
                        for item in drafted_existing:
                            rec = item["record"]
                            pid = str(rec["prospect_id"]) if rec.get("prospect_id") else None
                            email_low = (rec["email"] or "").strip().lower()
                            if pid and pid in cur_prospect_ids:
                                continue
                            if not pid and email_low in cur_no_prospect_emails:
                                continue
                            if email_low in cur_cap_emails:
                                continue

                            q_order = start_order + offset
                            sec_num = (q_order // SECTION_SIZE) + 1
                            offset += 1
                            if pid:
                                cur_prospect_ids.add(pid)
                            else:
                                cur_no_prospect_emails.add(email_low)
                            cur_cap_emails.add(email_low)

                            snapshot = {
                                "company_name": rec.get("company_name") or "",
                                "phone_number": rec.get("phone_number") or "",
                                "email": rec.get("email") or "",
                                "recipient_name": rec.get("recipient_name") or "",
                                "designation": rec.get("designation") or "",
                                "primary_industries": rec.get("primary_industries") or "",
                                "offering_type": rec.get("offering_type") or "",
                                "products": rec.get("products") or [],
                                "services": rec.get("services") or [],
                                "solutions": rec.get("solutions") or [],
                                "offerings": rec.get("offerings") or [],
                                "country": rec.get("country") or "",
                                "address": rec.get("address") or "",
                                "website": rec.get("website") or "",
                                "ai_provider": item.get("provider") or "gemini",
                                "ai_model": item.get("model") or "",
                                "portfolio_sources": item.get("portfolio_sources") or [],
                                "user_prompt": effective_prompt,
                                "tone": tone or "professional",
                            }
                            new_recipient_objs.append(
                                EmailCampaignRecipient(
                                    campaign=capacity_campaign,
                                    email_address=rec["email"],
                                    recipient_name=rec.get("recipient_name") or rec.get("company_name") or None,
                                    prospect=prospect_map.get(str(rec.get("prospect_id"))),
                                    prospect_contact=contact_map.get(str(rec.get("prospect_contact_id"))),
                                    section_number=sec_num,
                                    custom_subject=item["subject"][:512],
                                    custom_body=item["body"],
                                    outreach_snapshot=snapshot,
                                    queue_order=q_order,
                                    status=EmailCampaignRecipient.Status.DRAFT,
                                    scheduled_for=None,
                                )
                            )

                        if new_recipient_objs:
                            EmailCampaignRecipient.objects.bulk_create(new_recipient_objs)
                            _rebalance_campaign_sections(capacity_campaign)
                            if capacity_campaign.status in (EmailCampaign.Status.COMPLETED, EmailCampaign.Status.COMPLETED_WITH_ERRORS):
                                capacity_campaign.status = EmailCampaign.Status.DRAFT
                                capacity_campaign.completed_at = None
                                capacity_campaign.save(update_fields=["status", "completed_at"])
                            newly_drafted_count += len(new_recipient_objs)
                            campaign = campaign or capacity_campaign

                # Create sequential uniquely numbered campaigns owned strictly by the prospect creator
                if overflow_records:
                    overflow_chunks = _chunk_list(overflow_records, MAX_RECIPIENTS_PER_CAMPAIGN)
                    for chunk in overflow_chunks:
                        camp_num = _get_next_ai_outreach_campaign_number("AI Outreach Campaign")
                        created_batch = create_ai_drafted_campaigns(
                            user=owner_user,
                            name=f"AI Outreach Campaign — Campaign {camp_num}",
                            user_prompt=effective_prompt,
                            tone=tone,
                            prospect_ids=[r["prospect_id"] for r in chunk if r.get("prospect_id")] or None,
                            recipients_data=chunk,
                        )
                        open_campaigns.extend(created_batch)
                        newly_drafted_count += sum(c.recipients.count() for c in created_batch)
                    if not campaign and open_campaigns:
                        campaign = open_campaigns[-1]

        remaining_undrafted_count = max(0, total_missing - newly_drafted_count)
        if campaign:
            campaign = EmailCampaign.objects.filter(id=campaign.id).first() or campaign

        return {
            "unsent_analysis": unsent_analysis,
            "active_campaign": campaign,
            "active_campaigns": open_campaigns,
            "pruned_sent_drafts": pruned_count,
            "deduplicated_drafts": deduplicated_count,
            "reconciled_ownership_count": reconciled_count,
            "newly_drafted_count": newly_drafted_count,
            "remaining_undrafted_count": remaining_undrafted_count,
            "sync_in_progress": False,
            "checked_at": timezone.now().isoformat(),
        }
    finally:
        if lock_token is not None:
            _release_live_sync_lock(lock_token)



