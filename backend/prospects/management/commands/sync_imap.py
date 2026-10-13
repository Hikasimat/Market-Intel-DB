import sys
import imaplib
import email
from email.header import decode_header
from django.core.management.base import BaseCommand
from accounts.models import MailAccount
from prospects.models import OutreachEmail, CommunicationActivity, ProspectContact
from django.utils import timezone
import utils.encryption as encryption
import json

def get_email_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get('Content-Disposition'))
            if 'attachment' not in content_disposition:
                if content_type == 'text/plain':
                    return part.get_payload(decode=True).decode(errors='ignore')
                elif content_type == 'text/html':
                    return part.get_payload(decode=True).decode(errors='ignore')
    else:
        return msg.get_payload(decode=True).decode(errors='ignore')
    return ""

class Command(BaseCommand):
    help = 'Synchronize IMAP to detect email responses and update Outreach threads.'

    def handle(self, *args, **options):
        accounts = MailAccount.objects.filter(is_active=True)
        for account in accounts:
            try:
                self.sync_account(account)
            except Exception as e:
                account.last_sync_status = 'FAILED'
                account.last_sync_error = str(e)
                account.save()
                self.stdout.write(self.style.ERROR(f"Failed to sync {account.email_address}: {e}"))

    def sync_account(self, account):
        self.stdout.write(f"Syncing {account.email_address}..."); sys.stdout.flush()
        password = encryption.decrypt_password(account.imap_app_password_encrypted)
        
        if account.imap_security == 'SSL':
            mail = imaplib.IMAP4_SSL(account.imap_host, account.imap_port, timeout=15)
        else:
            mail = imaplib.IMAP4(account.imap_host, account.imap_port, timeout=15)
            mail.starttls()
            
        mail.login(account.imap_username, password)
        mail.select('inbox')

        # Simple sync: grab UNSEEN messages
        # Ideally, we use UIDVALIDITY and last_seen_uid, but UNSEEN is simpler for this implementation.
        status, response = mail.search(None, 'ALL')
        if status != 'OK':
            mail.logout()
            return
            
        unread_msg_nums = response[0].split()
        # Only process the last 50 emails
        unread_msg_nums = unread_msg_nums[-50:]
        for e_id in unread_msg_nums:
            status, msg_data = mail.fetch(e_id, '(RFC822)')
            if status != 'OK': continue
            
            for response_part in msg_data:
                if isinstance(response_part, tuple):
                    msg = email.message_from_bytes(response_part[1])
                    
                    message_id = msg.get('Message-ID', '').strip()
                    in_reply_to = msg.get('In-Reply-To', '').strip()
                    references = msg.get('References', '')
                    subject = msg.get('Subject', '')
                    from_header = msg.get('From', '')
                    
                    # Try to decode subject
                    decoded_subject, encoding = decode_header(subject)[0]
                    if isinstance(decoded_subject, bytes):
                        subject = decoded_subject.decode(encoding or 'utf-8')
                        
                    # Extract email address from 'From'
                    import re
                    match = re.search(r'<(.+?)>', from_header)
                    from_email = match.group(1) if match else from_header
                    
                    self.stdout.write(f"Processing Msg-ID: {message_id}, In-Reply-To: {in_reply_to}")
                    
                    # Match thread
                    thread_ids = [in_reply_to]
                    if references:
                        thread_ids.extend(references.split())
                    
                    matched_email = None
                    for tid in thread_ids:
                        if not tid: continue
                        tid = tid.strip()
                        # We look for an outgoing email that has this Message-ID
                        matched_email = OutreachEmail.objects.filter(message_id=tid, sender_mail_account=account).first()
                        if matched_email:
                            break
                            
                    if matched_email:
                        self.stdout.write(self.style.SUCCESS(f"Matched thread: {matched_email.id}"))
                        
                        # Avoid duplicates
                        if CommunicationActivity.objects.filter(outreach_email=matched_email, direction='INBOUND', subject=subject).exists():
                            self.stdout.write("Already processed this inbound response.")
                            continue
                            
                        # Try to match the contact
                        contact = ProspectContact.objects.filter(prospect=matched_email.prospect, official_email=from_email).first()
                        
                        # Extract body
                        body_text = get_email_body(msg)

                        # Create inbound CommunicationActivity
                        CommunicationActivity.objects.create(
                            
                            prospect=matched_email.prospect,
                            prospect_contact=contact,
                            activity_type='EMAIL_RECEIVED',
                            direction='INBOUND',
                            status='Received Response',
                            subject=subject,
                            notes=body_text,
                            outreach_email=matched_email,
                            performed_by=None # System matched
                        )
                        
                        # Update OutreachEmail status
                        matched_email.status = 'RECEIVED RESPONSE'
                        matched_email.save()
                        
                        # Update LQ if present
                        if hasattr(matched_email.prospect, 'lead_qualification'):
                            matched_email.prospect.lead_qualification.email_status = 'Received Response'
                            matched_email.prospect.lead_qualification.save()
                            
        account.last_sync_status = 'SUCCESS'
        account.last_sync_error = ''
        account.last_imap_sync_at = timezone.now()
        account.save()
        mail.logout()
        self.stdout.write(self.style.SUCCESS(f"Successfully synced {account.email_address}"))
