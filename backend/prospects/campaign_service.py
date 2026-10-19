import email.message
from email.utils import make_msgid, formatdate
import html
import logging
import mimetypes
import threading
import time
import uuid
from datetime import timedelta
from typing import List, Dict, Any, Optional

from django.conf import settings
from django.db import transaction
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
    incorporating templates, signatures, attachments, and optional open-tracking.
    """
    user = campaign.created_by
    sender_email = campaign.sender_email
    sender_display_name = user.get_full_name() or user.username
    email_domain = extract_domain_from_email(sender_email)

    msg = email.message.EmailMessage()
    from_header_val = format_sender_address(sender_display_name, sender_email)
    set_singleton_header(msg, 'From', from_header_val)
    set_singleton_header(msg, 'To', recipient.email_address)
    set_singleton_header(msg, 'Subject', campaign.subject)
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
                campaign.subject,
                campaign.body,
                template_id=campaign.template_id,
                signature_id=campaign.signature_id,
                body_edited=False,
            )
        except Exception as e:
            logger.warning("Could not apply template/signature to campaign email: %s", e)

    effective_signature = f"--\n{sender_display_name}\n{sender_email}"
    if composed and composed.get('has_signature'):
        effective_signature = composed['signature_text']

    full_text_body = campaign.body
    if effective_signature and effective_signature not in full_text_body:
        full_text_body = f"{full_text_body}\n\n{effective_signature}"

    msg.set_content(full_text_body)

    # HTML body
    html_body_text = html.escape(campaign.body).replace('\n', '<br>')
    from accounts.template_utils import clean_and_embed_signature_html, convert_base64_images_to_cid

    if composed and composed.get('has_template') and composed.get('html_body'):
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
                subject=campaign.subject,
                body=campaign.body,
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

            if recipient.prospect:
                CommunicationActivity.objects.create(
                    prospect=recipient.prospect,
                    prospect_contact=recipient.prospect_contact,
                    performed_by=campaign.created_by,
                    activity_type='EMAIL_SENT',
                    direction='OUTBOUND',
                    outreach_email=outreach_email,
                    subject=campaign.subject,
                    notes=f"Sent via bulk campaign '{campaign.name}' to {recipient.email_address}",
                )

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
    if next_recipient:
        next_recipient.scheduled_for = next_eligible_time
        next_recipient.save(update_fields=['scheduled_for'])


def _check_and_update_campaign_completion(campaign: EmailCampaign):
    """
    Evaluates whether all recipients have finished processing and marks
    the campaign COMPLETED or COMPLETED_WITH_ERRORS.
    """
    remaining = campaign.recipients.filter(
        status__in=[
            EmailCampaignRecipient.Status.PENDING,
            EmailCampaignRecipient.Status.SENDING,
            EmailCampaignRecipient.Status.RETRY_PENDING,
        ]
    ).exists()

    if not remaining:
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

