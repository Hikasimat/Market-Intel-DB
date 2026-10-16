import sys
from django.core.management.base import BaseCommand
from prospects.models import OutreachEmail, CommunicationActivity, ProspectContact
from django.utils import timezone
import json

class Command(BaseCommand):
    help = 'Synchronize Gmail via Google OAuth to detect email responses and update Outreach threads.'

    def handle(self, *args, **options):
        # Sync active Gmail OAuth accounts
        try:
            from accounts.models import GoogleMailCredentials
            google_creds = GoogleMailCredentials.objects.filter(is_active=True)
            for cred in google_creds:
                try:
                    self.sync_google_account(cred)
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Failed to sync Gmail {cred.email}: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Gmail sync error: {e}"))

    def sync_google_account(self, cred):
        from accounts.oauth_services import GmailOAuthService
        self.stdout.write(f"Syncing Gmail {cred.email}..."); sys.stdout.flush()
        res = GmailOAuthService.fetch_messages(cred, folder='INBOX', limit=20)
        messages = res.get('messages', [])
        for m in messages:
            from_header = m.get('from', '')
            import re
            match = re.search(r'<(.+?)>', from_header)
            from_email = match.group(1) if match else from_header
            if from_email.lower() == cred.email.lower():
                continue

            thread_id = m.get('thread_id') or m.get('threadId')
            subject = m.get('subject', '')

            # Match by thread_id or subject or recipient
            matched_email = None
            if thread_id:
                matched_email = OutreachEmail.objects.filter(thread_id=thread_id).first()
            if not matched_email and subject:
                clean_subj = subject.replace('Re:', '').replace('RE:', '').strip()
                if clean_subj:
                    matched_email = OutreachEmail.objects.filter(subject__icontains=clean_subj, recipients__email_address__iexact=from_email).first()

            if matched_email:
                if CommunicationActivity.objects.filter(outreach_email=matched_email, direction='INBOUND', subject=subject).exists():
                    continue

                contact = ProspectContact.objects.filter(prospect=matched_email.prospect, official_email=from_email).first()
                body_info = GmailOAuthService.fetch_message_body(cred, m.get('id') or m.get('uid'))
                body_text = body_info.get('text_body') or body_info.get('html_body', '')

                CommunicationActivity.objects.create(
                    prospect=matched_email.prospect,
                    prospect_contact=contact,
                    activity_type='EMAIL_RECEIVED',
                    direction='INBOUND',
                    status='Received Response',
                    subject=subject,
                    notes=body_text,
                    outreach_email=matched_email,
                    performed_by=None,
                )

                matched_email.status = 'RECEIVED RESPONSE'
                matched_email.save(update_fields=['status'])

                if hasattr(matched_email.prospect, 'lead_qualification'):
                    matched_email.prospect.lead_qualification.email_status = 'Received Response'
                    matched_email.prospect.lead_qualification.save(update_fields=['email_status'])

        self.stdout.write(self.style.SUCCESS(f"Successfully synced Gmail {cred.email}"))
