import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import GoogleMailCredentials, UserProfile
from prospects.campaign_service import (
    _LIVE_SYNC_LOCK,
    create_campaign,
    create_ai_drafted_campaign,
    deduplicate_draft_campaign_recipients,
    get_unsent_outreach_records,
    sync_live_unsent_outreach_ai_drafts,
    send_campaign_section,
    update_campaign_recipient_draft,
    send_single_campaign_recipient,
    process_campaign_queue,
    pause_campaign,
    resume_campaign,
    cancel_campaign,
    recover_stale_sending_jobs,
)
from prospects.models import (
    EmailCampaign,
    EmailCampaignRecipient,
    OutreachEmail,
    CommunicationActivity,
    Prospect,
    ProspectContact,
    ProspectOffering,
)

User = get_user_model()


class BulkEmailCampaignTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='lq_user', email='lq@example.com', password='password123')
        profile = self.user.profile
        profile.role = 'LQ'
        profile.save()
        self.creds = GoogleMailCredentials.objects.create(
            user=self.user,
            email='lq@example.com',
            access_token_encrypted='dummy_token',
            is_active=True,
        )

        self.other_user = User.objects.create_user(username='other_lq', email='other@example.com', password='password123')
        other_prof = self.other_user.profile
        other_prof.role = 'LQ'
        other_prof.save()

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.prospect = Prospect.objects.create(
            company_name='Acme Corp',
            country_head_office='USA',
            complete_address='123 Main St',
            official_email_address='info@acme.com',
            primary_industries='Technology',
            company_structure='Parent',
            operational_status='Active',
            primary_offering_type='Products',
        )
        self.contact = ProspectContact.objects.create(
            prospect=self.prospect,
            contact_name='Alice Smith',
            official_email='alice@acme.com',
        )

    def test_campaign_creation_with_multiple_recipients(self):
        """Test 1: Campaign creation with multiple unique recipients."""
        recipients = [
            {'email': 'first@example.com', 'name': 'First User'},
            {'email': 'second@example.com', 'name': 'Second User'},
            {'email': 'third@example.com', 'name': 'Third User'},
        ]
        campaign = create_campaign(
            user=self.user,
            name='Q4 Launch',
            subject='Introducing Acme',
            body='Hello there,\nCheck our latest platform.',
            recipients_data=recipients,
            interval_seconds=90,
        )

        self.assertEqual(campaign.name, 'Q4 Launch')
        self.assertEqual(campaign.status, EmailCampaign.Status.QUEUED)
        self.assertEqual(campaign.recipients.count(), 3)
        self.assertEqual(campaign.interval_seconds, 90)

    def test_case_insensitive_deduplication(self):
        """Test 2: Duplicate email addresses are deduplicated case-insensitively."""
        recipients = [
            'Test@Example.com',
            'test@example.com',
            'TEST@EXAMPLE.COM',
            'other@example.com',
        ]
        campaign = create_campaign(
            user=self.user,
            name='Dedupe Test',
            subject='Dedupe Subject',
            body='Body',
            recipients_data=recipients,
        )
        self.assertEqual(campaign.recipients.count(), 2)
        emails = list(campaign.recipients.values_list('email_address', flat=True))
        self.assertIn('test@example.com', emails)
        self.assertIn('other@example.com', emails)

    def test_first_recipient_is_immediately_eligible(self):
        """Test 3: The first recipient is immediately eligible (scheduled_for <= now)."""
        now = timezone.now()
        recipients = ['one@example.com', 'two@example.com']
        campaign = create_campaign(
            user=self.user,
            name='First Eligible',
            subject='Subject',
            body='Body',
            recipients_data=recipients,
        )
        rec0 = campaign.recipients.get(queue_order=0)
        rec1 = campaign.recipients.get(queue_order=1)

        self.assertIsNotNone(rec0.scheduled_for)
        self.assertLessEqual(rec0.scheduled_for, timezone.now())
        self.assertIsNone(rec1.scheduled_for)

    @mock.patch('accounts.oauth_services.GmailOAuthService.send_message')
    def test_second_recipient_eligible_only_after_90s(self, mock_send):
        """Test 4: Second recipient is not eligible earlier than 90s after first send."""
        mock_send.return_value = {'id': 'msg_001', 'threadId': 'th_001'}

        campaign = create_campaign(
            user=self.user,
            name='Pacing Test',
            subject='Subject',
            body='Body',
            recipients_data=['one@example.com', 'two@example.com'],
            interval_seconds=90,
        )

        rec0 = campaign.recipients.get(queue_order=0)
        rec1 = campaign.recipients.get(queue_order=1)

        # Process first recipient
        success = send_single_campaign_recipient(rec0.id)
        self.assertTrue(success)
        rec0.refresh_from_db()
        self.assertEqual(rec0.status, EmailCampaignRecipient.Status.SENT)
        self.assertIsNotNone(rec0.sent_at)

        # Refresh campaign and second recipient
        campaign.refresh_from_db()
        rec1.refresh_from_db()

        self.assertIsNotNone(campaign.last_sent_at)
        expected_next = campaign.last_sent_at + timedelta(seconds=90)
        self.assertAlmostEqual(
            campaign.next_eligible_at.timestamp(),
            expected_next.timestamp(),
            delta=2
        )
        self.assertEqual(rec1.scheduled_for, campaign.next_eligible_at)

        # Attempt to process recipient 2 immediately before 90s has elapsed
        # Should NOT send
        processed_early = send_single_campaign_recipient(rec1.id)
        self.assertFalse(processed_early)
        rec1.refresh_from_db()
        self.assertEqual(rec1.status, EmailCampaignRecipient.Status.PENDING)
        self.assertEqual(mock_send.call_count, 1)

    @mock.patch('accounts.oauth_services.GmailOAuthService.send_message')
    def test_third_and_later_recipients_sequential_pacing(self, mock_send):
        """Test 5 & 6: Third recipient and larger campaigns follow strict sequential interval."""
        mock_send.return_value = {'id': 'msg_dummy', 'threadId': 'th_dummy'}

        campaign = create_campaign(
            user=self.user,
            name='Multi Recipient',
            subject='Subject',
            body='Body',
            recipients_data=['r1@example.com', 'r2@example.com', 'r3@example.com'],
            interval_seconds=90,
        )

        rec1 = campaign.recipients.get(queue_order=0)
        rec2 = campaign.recipients.get(queue_order=1)
        rec3 = campaign.recipients.get(queue_order=2)

        # Send r1
        send_single_campaign_recipient(rec1.id)
        campaign.refresh_from_db()
        rec2.refresh_from_db()
        self.assertEqual(mock_send.call_count, 1)

        # Simulate 90 seconds elapsed
        send_time_r1 = campaign.last_sent_at
        future_time_1 = send_time_r1 + timedelta(seconds=91)
        with mock.patch('django.utils.timezone.now', return_value=future_time_1):
            success2 = send_single_campaign_recipient(rec2.id)
            self.assertTrue(success2)

        self.assertEqual(mock_send.call_count, 2)
        campaign.refresh_from_db()
        rec3.refresh_from_db()

        # Recipient 3 must now be scheduled at least 90s after recipient 2
        send_time_r2 = campaign.last_sent_at
        self.assertEqual(send_time_r2, future_time_1)
        expected_r3 = send_time_r2 + timedelta(seconds=90)
        self.assertEqual(rec3.scheduled_for, expected_r3)

        # Verify r3 cannot send prematurely
        with mock.patch('django.utils.timezone.now', return_value=send_time_r2 + timedelta(seconds=45)):
            success3_early = send_single_campaign_recipient(rec3.id)
            self.assertFalse(success3_early)

        # Verify r3 sends when interval is reached
        future_time_2 = send_time_r2 + timedelta(seconds=91)
        with mock.patch('django.utils.timezone.now', return_value=future_time_2):
            success3 = send_single_campaign_recipient(rec3.id)
            self.assertTrue(success3)

        self.assertEqual(mock_send.call_count, 3)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, EmailCampaign.Status.COMPLETED)

    @mock.patch('accounts.oauth_services.GmailOAuthService.send_message')
    def test_paused_campaigns_do_not_send(self, mock_send):
        """Test 7: Paused campaigns do not continue sending."""
        mock_send.return_value = {'id': 'msg_001'}

        campaign = create_campaign(
            user=self.user,
            name='Pause Test',
            subject='Subject',
            body='Body',
            recipients_data=['one@example.com'],
        )
        pause_campaign(campaign, self.user)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, EmailCampaign.Status.PAUSED)

        # Worker run must skip paused campaign
        count = process_campaign_queue(max_jobs=5)
        self.assertEqual(count, 0)
        self.assertEqual(mock_send.call_count, 0)

    @mock.patch('accounts.oauth_services.GmailOAuthService.send_message')
    def test_resumed_campaigns_continue_without_shortening_delay(self, mock_send):
        """Test 8: Resumed campaigns continue without resetting or shortening delay."""
        mock_send.return_value = {'id': 'msg_001'}

        campaign = create_campaign(
            user=self.user,
            name='Resume Delay Test',
            subject='Subject',
            body='Body',
            recipients_data=['one@example.com', 'two@example.com'],
            interval_seconds=90,
        )
        rec0 = campaign.recipients.get(queue_order=0)
        send_single_campaign_recipient(rec0.id)
        campaign.refresh_from_db()
        t0 = campaign.last_sent_at

        # Pause immediately at t0 + 10s
        with mock.patch('django.utils.timezone.now', return_value=t0 + timedelta(seconds=10)):
            pause_campaign(campaign, self.user)

        # Resume at t0 + 30s (still 60s remaining before next send is allowed)
        with mock.patch('django.utils.timezone.now', return_value=t0 + timedelta(seconds=30)):
            resume_campaign(campaign, self.user)
            campaign.refresh_from_db()
            # Must still require t0 + 90s
            self.assertEqual(campaign.next_eligible_at, t0 + timedelta(seconds=90))

    def test_cancelled_campaign_does_not_dispatch(self):
        """Test 9: Cancelled campaigns do not dispatch further recipients."""
        campaign = create_campaign(
            user=self.user,
            name='Cancel Test',
            subject='Subject',
            body='Body',
            recipients_data=['one@example.com', 'two@example.com'],
        )
        cancel_campaign(campaign, self.user)
        campaign.refresh_from_db()
        self.assertEqual(campaign.status, EmailCampaign.Status.CANCELLED)

        # Remaining recipients must be marked FAILED/cancelled
        for r in campaign.recipients.all():
            self.assertEqual(r.status, EmailCampaignRecipient.Status.FAILED)

    @mock.patch('accounts.oauth_services.GmailOAuthService.send_message')
    def test_transient_error_enters_retry_process(self, mock_send):
        """Test 10: Transient errors enter the retry process with backoff."""
        mock_send.side_effect = Exception("503 Service Unavailable: rate limit exceeded")

        campaign = create_campaign(
            user=self.user,
            name='Retry Test',
            subject='Subject',
            body='Body',
            recipients_data=['retry@example.com'],
            interval_seconds=90,
        )
        rec = campaign.recipients.first()

        success = send_single_campaign_recipient(rec.id)
        self.assertFalse(success)

        rec.refresh_from_db()
        self.assertEqual(rec.status, EmailCampaignRecipient.Status.RETRY_PENDING)
        self.assertEqual(rec.attempt_count, 1)
        self.assertIn("rate limit", rec.error_message)
        # Scheduled retry must be at least 90s later
        self.assertGreaterEqual(rec.scheduled_for, timezone.now() + timedelta(seconds=89))

    @mock.patch('accounts.oauth_services.GmailOAuthService.send_message')
    def test_permanent_failure_recorded_correctly(self, mock_send):
        """Test 11: Permanent failures are recorded correctly and next recipient proceeds."""
        mock_send.side_effect = Exception("550 5.1.1 Recipient address rejected: User unknown")

        campaign = create_campaign(
            user=self.user,
            name='Permanent Fail Test',
            subject='Subject',
            body='Body',
            recipients_data=['bad@example.com', 'good@example.com'],
            interval_seconds=90,
        )
        rec0 = campaign.recipients.get(queue_order=0)
        rec1 = campaign.recipients.get(queue_order=1)

        success = send_single_campaign_recipient(rec0.id)
        self.assertFalse(success)

        rec0.refresh_from_db()
        self.assertEqual(rec0.status, EmailCampaignRecipient.Status.FAILED)

        # Recipient 1 is scheduled at now + 90s so queue is not blocked
        rec1.refresh_from_db()
        self.assertIsNotNone(rec1.scheduled_for)

    @mock.patch('accounts.oauth_services.GmailOAuthService.send_message')
    def test_successful_send_marked_only_after_gmail_confirms(self, mock_send):
        """Test 12: Successful sends marked SENT only after provider confirms acceptance."""
        mock_send.return_value = {'id': 'gmail_msg_123', 'threadId': 'th_123'}

        campaign = create_campaign(
            user=self.user,
            name='Confirm Send',
            subject='Subject',
            body='Body',
            recipients_data=[{'email': 'alice@acme.com', 'prospect_id': str(self.prospect.id)}],
        )
        rec = campaign.recipients.first()

        # Before send: status is PENDING, no OutreachEmail
        self.assertEqual(rec.status, EmailCampaignRecipient.Status.PENDING)
        self.assertIsNone(rec.sent_at)
        self.assertEqual(OutreachEmail.objects.count(), 0)

        success = send_single_campaign_recipient(rec.id)
        self.assertTrue(success)

        rec.refresh_from_db()
        self.assertEqual(rec.status, EmailCampaignRecipient.Status.SENT)
        self.assertIsNotNone(rec.sent_at)
        self.assertIsNotNone(rec.outreach_email)
        self.assertEqual(rec.outreach_email.status, 'SENT')
        self.assertEqual(rec.outreach_email.thread_id, 'th_123')

        # Communication activity logged
        activity = CommunicationActivity.objects.filter(outreach_email=rec.outreach_email).first()
        self.assertIsNotNone(activity)
        self.assertEqual(activity.activity_type, 'EMAIL_SENT')

    def test_stale_sending_jobs_recovered(self):
        """Test 13: Stale jobs from worker crashes do not silently lose campaigns."""
        campaign = create_campaign(
            user=self.user,
            name='Stale Test',
            subject='Subject',
            body='Body',
            recipients_data=['stale@example.com'],
        )
        rec = campaign.recipients.first()
        rec.status = EmailCampaignRecipient.Status.SENDING
        rec.last_attempt_at = timezone.now() - timedelta(minutes=15)
        rec.save()

        recover_stale_sending_jobs()
        rec.refresh_from_db()
        self.assertEqual(rec.status, EmailCampaignRecipient.Status.RETRY_PENDING)
        self.assertIn("Recovered", rec.error_message)

    @mock.patch('accounts.oauth_services.GmailOAuthService.send_message')
    def test_concurrent_worker_lock_protection(self, mock_send):
        """Test 14: Concurrent workers cannot claim and send the same recipient."""
        mock_send.return_value = {'id': 'msg_concur'}

        campaign = create_campaign(
            user=self.user,
            name='Concurrency Test',
            subject='Subject',
            body='Body',
            recipients_data=['single@example.com'],
        )
        rec = campaign.recipients.first()

        # Simulate Worker 1 claims item
        rec.status = EmailCampaignRecipient.Status.SENDING
        rec.save()

        # Worker 2 attempts to process same item
        result = send_single_campaign_recipient(rec.id)
        self.assertFalse(result)
        self.assertEqual(mock_send.call_count, 0)

    def test_unauthorized_user_cannot_access_or_control_campaign(self):
        """Test 15: Unauthorized user cannot read, pause, or cancel another user's campaign."""
        campaign = create_campaign(
            user=self.user,
            name='User Isolation Test',
            subject='Subject',
            body='Body',
            recipients_data=['test@example.com'],
        )

        other_client = APIClient()
        other_client.force_authenticate(user=self.other_user)

        # Other user cannot see campaign in list
        res_list = other_client.get('/api/email-campaigns/')
        self.assertEqual(res_list.status_code, 200)
        self.assertEqual(len(res_list.data.get('results', [])), 0)

        # Other user cannot pause campaign
        res_pause = other_client.post(f'/api/email-campaigns/{campaign.id}/pause/')
        self.assertEqual(res_pause.status_code, 404)

        # Other user cannot cancel campaign
        res_cancel = other_client.post(f'/api/email-campaigns/{campaign.id}/cancel/')
        self.assertEqual(res_cancel.status_code, 404)

    def test_unsent_outreach_analysis_excludes_already_sent_prospects(self):
        """Test 16: Analyzes outreach data and identifies only records where emails have not been sent."""
        # Create 2 unsent prospects and 1 already-sent prospect for lq_user
        p_unsent_1 = Prospect.objects.create(
            company_name='Alpha Robotics Ltd',
            country_head_office='UAE',
            complete_address='Dubai Silicon Oasis',
            official_phone_number='+971 50 111 2233',
            official_email_address='contact@alpharobotics.ae',
            primary_industries='Industrial Automation',
            company_structure='Parent',
            operational_status='Active',
            primary_offering_type='Products',
            created_by=self.user.username,
        )
        ProspectOffering.objects.create(
            prospect=p_unsent_1,
            offering_type='PRODUCT',
            name='Autonomous Warehouse Drones',
        )

        p_sent = Prospect.objects.create(
            company_name='Beta Logistics LLC',
            country_head_office='UAE',
            complete_address='Jebel Ali',
            official_phone_number='+971 50 999 8877',
            official_email_address='info@betalogistics.ae',
            primary_industries='Supply Chain',
            company_structure='Parent',
            operational_status='Active',
            primary_offering_type='Services',
            created_by=self.user.username,
        )
        OutreachEmail.objects.create(
            prospect=p_sent,
            created_by=self.user,
            from_email='lq@example.com',
            subject='Already Sent Email',
            body='Sent previously',
            status='SENT',
        )

        analysis = get_unsent_outreach_records(self.user)
        company_names = [r['company_name'] for r in analysis['records']]
        self.assertIn('Alpha Robotics Ltd', company_names)
        self.assertNotIn('Beta Logistics LLC', company_names)

        alpha_rec = next(r for r in analysis['records'] if r['company_name'] == 'Alpha Robotics Ltd')
        self.assertEqual(alpha_rec['phone_number'], '+971 50 111 2233')
        self.assertEqual(alpha_rec['email'], 'contact@alpharobotics.ae')
        self.assertEqual(alpha_rec['primary_industries'], 'Industrial Automation')
        self.assertIn('Autonomous Warehouse Drones', alpha_rec['offerings'])

    @mock.patch('accounts.oauth_services.GmailOAuthService.send_message')
    def test_ai_drafts_grouped_into_sections_of_10_and_sent_per_section_with_90s_interval(self, mock_send):
        """
        Test 17:
        - Generates customized AI email drafts for 15 unsent outreach records (using Vector DB portfolio + outreach data)
        - Organizes into Section 1 (10 drafts) and Section 2 (5 drafts), all starting in DRAFT status
        - User reviews & edits a draft in Section 1, then clicks Send on Section 1
        - Only Section 1 (10 emails) transitions to PENDING and sends with 90-second intervals using each recipient's custom draft
        - Section 2 (5 emails) remains in DRAFT status until its own Send button is clicked
        """
        mock_send.return_value = {'id': 'gmail_sec_msg', 'threadId': 'th_sec'}

        # Seed a ready Vector DB Knowledge Base document + chunk so portfolio retrieval is exercised
        from rag.models import KnowledgeBase, KnowledgeDocument, KnowledgeDocumentChunk
        kb = KnowledgeBase.objects.create(
            name='Our Company Portfolio',
            is_active=True,
            owner=self.user,
        )
        doc = KnowledgeDocument.objects.create(
            knowledge_base=kb,
            original_filename='company_portfolio.pdf',
            file_type='pdf',
            file_size=2048,
            storage_key='rag_kb/test/company_portfolio.pdf',
            checksum_sha256='a' * 64,
            status='READY',
            total_chunks=1,
            is_active=True,
            created_by=self.user,
        )
        KnowledgeDocumentChunk.objects.create(
            document=doc,
            knowledge_base=kb,
            chunk_index=0,
            text='MarketIntel Enterprise AI Suite: Automated B2B intelligence, predictive analytics, and ERP integration.',
            token_count=20,
            content_checksum='b' * 64,
            embedding=[0.01] * 1024,
            embedding_model='amazon.titan-embed-text-v2:0',
            embedding_dimension=1024,
        )

        # Create 15 unsent outreach prospects for lq_user
        created_ids = []
        for idx in range(1, 16):
            p = Prospect.objects.create(
                company_name=f'Outreach Co {idx:02d}',
                country_head_office='United Arab Emirates',
                complete_address=f'Building {idx}, Business Bay',
                official_phone_number=f'+971 55 000 {idx:04d}',
                official_email_address=f'contact{idx:02d}@outreachco{idx:02d}.com',
                primary_industries=f'Industry Sector {idx}',
                company_structure='Parent',
                operational_status='Active',
                primary_offering_type='Solutions',
                created_by=self.user.username,
            )
            ProspectOffering.objects.create(
                prospect=p,
                offering_type='PRODUCT',
                name=f'Specialized Product {idx}',
            )
            created_ids.append(str(p.id))

        campaign = create_ai_drafted_campaign(
            user=self.user,
            name='AI Sectioned Outreach Campaign',
            user_prompt='Pitch our MarketIntel Enterprise AI Suite tailored to their offerings and industry.',
            tone='professional',
            prospect_ids=created_ids,
        )

        self.assertEqual(campaign.status, EmailCampaign.Status.DRAFT)
        self.assertEqual(campaign.total_count, 15)
        self.assertEqual(campaign.draft_count, 15)
        self.assertEqual(campaign.pending_count, 0)

        sec1_recs = list(campaign.recipients.filter(section_number=1).order_by('queue_order'))
        sec2_recs = list(campaign.recipients.filter(section_number=2).order_by('queue_order'))
        self.assertEqual(len(sec1_recs), 10)
        self.assertEqual(len(sec2_recs), 5)

        # Verify each draft has a customized subject, body, and outreach_snapshot with portfolio source
        for r in sec1_recs + sec2_recs:
            self.assertEqual(r.status, EmailCampaignRecipient.Status.DRAFT)
            self.assertTrue(bool(r.custom_subject))
            self.assertTrue(bool(r.custom_body))
            self.assertIn(r.outreach_snapshot['company_name'], r.custom_body)
            self.assertIn('company_portfolio.pdf', r.outreach_snapshot.get('portfolio_sources', []))

        # Worker should NOT send anything while recipients are in DRAFT status
        self.assertEqual(process_campaign_queue(max_jobs=10), 0)
        self.assertEqual(mock_send.call_count, 0)

        # User edits the first draft in Section 1 during review
        first_rec = sec1_recs[0]
        update_campaign_recipient_draft(
            campaign=campaign,
            recipient_id=str(first_rec.id),
            custom_subject='Custom Reviewed Subject for Outreach Co',
            custom_body='Custom Reviewed Body for Outreach Co with our portfolio details.',
        )

        # User clicks Send on Section 1 ONLY
        send_campaign_section(campaign=campaign, section_number=1, user=self.user)
        campaign.refresh_from_db()
        self.assertIn(campaign.status, [EmailCampaign.Status.QUEUED, EmailCampaign.Status.RUNNING])
        self.assertEqual(campaign.recipients.filter(section_number=1, status=EmailCampaignRecipient.Status.PENDING).count(), 10)
        # Section 2 must still be in DRAFT status!
        self.assertEqual(campaign.recipients.filter(section_number=2, status=EmailCampaignRecipient.Status.DRAFT).count(), 5)

        # Send first email in Section 1
        sent_ok = send_single_campaign_recipient(first_rec.id)
        self.assertTrue(sent_ok)
        first_rec.refresh_from_db()
        self.assertEqual(first_rec.status, EmailCampaignRecipient.Status.SENT)
        self.assertEqual(first_rec.outreach_email.subject, 'Custom Reviewed Subject for Outreach Co')
        self.assertEqual(first_rec.outreach_email.body, 'Custom Reviewed Body for Outreach Co with our portfolio details.')

        # Second email in Section 1 must be scheduled 90 seconds after first email
        second_rec = sec1_recs[1]
        second_rec.refresh_from_db()
        campaign.refresh_from_db()
        self.assertEqual(second_rec.scheduled_for, campaign.last_sent_at + timedelta(seconds=90))

        # Cannot send second email before 90 seconds have elapsed
        self.assertFalse(send_single_campaign_recipient(second_rec.id))

    def test_live_sent_mail_listener_prunes_sent_and_autodrafts_new_unsent_outreach(self):
        """
        Test 18:
        - Live listener auto-drafts unsent outreach records into a campaign
        - When an email is sent to one of those outreach records via Outreach Workspace / Inbox,
          the live sent-mail check immediately prunes that recipient's unapproved DRAFT from the campaign
        - When a new unsent outreach prospect is added, the live listener automatically drafts a
          customized email for it and appends it into the campaign sections
        """
        p1 = Prospect.objects.create(
            company_name='Gamma Solar Systems',
            country_head_office='UAE',
            complete_address='Masdar City',
            official_phone_number='+971 50 333 4444',
            official_email_address='hello@gammasolar.ae',
            primary_industries='Renewable Energy',
            company_structure='Parent',
            operational_status='Active',
            primary_offering_type='Products',
            created_by=self.user.username,
        )
        p2 = Prospect.objects.create(
            company_name='Delta Cloud FinTech',
            country_head_office='UAE',
            complete_address='DIFC',
            official_phone_number='+971 50 555 6666',
            official_email_address='contact@deltacloud.ae',
            primary_industries='Financial Services',
            company_structure='Parent',
            operational_status='Active',
            primary_offering_type='Solutions',
            created_by=self.user.username,
        )

        # 1. Run live sync -> automatically creates AI Outreach Campaign with 2 unsent drafts
        sync1 = sync_live_unsent_outreach_ai_drafts(user=self.user, auto_draft=True)
        camp = sync1['active_campaign']
        self.assertIsNotNone(camp)
        self.assertEqual(camp.recipients.filter(status='DRAFT').count(), 2)

        # 2. Now simulate sending an outreach email to Gamma Solar Systems outside the campaign
        OutreachEmail.objects.create(
            prospect=p1,
            created_by=self.user,
            from_email='lq@example.com',
            subject='Direct Outreach Sent to Gamma',
            body='Sent directly from Outreach Workspace',
            status='SENT',
        )

        # 3. Also create a new unsent outreach company (Epsilon MedTech)
        p3 = Prospect.objects.create(
            company_name='Epsilon MedTech',
            country_head_office='UAE',
            complete_address='Dubai Healthcare City',
            official_phone_number='+971 50 777 8888',
            official_email_address='info@epsilonmed.ae',
            primary_industries='Healthcare Technology',
            company_structure='Parent',
            operational_status='Active',
            primary_offering_type='Products',
            created_by=self.user.username,
        )

        # 4. Run live sync -> Gamma Solar must be pruned (already sent!), and Epsilon MedTech auto-drafted!
        sync2 = sync_live_unsent_outreach_ai_drafts(user=self.user, auto_draft=True, campaign_id=str(camp.id))
        camp.refresh_from_db()
        draft_emails = list(camp.recipients.filter(status='DRAFT').values_list('email_address', flat=True))
        self.assertNotIn('hello@gammasolar.ae', draft_emails)
        self.assertIn('contact@deltacloud.ae', draft_emails)
        self.assertIn('info@epsilonmed.ae', draft_emails)
        self.assertEqual(sync2['newly_drafted_count'], 1)

    @mock.patch('accounts.oauth_services.GmailOAuthService.send_message')
    @mock.patch('email_ai.services.generate_personalized_email')
    def test_campaign_overflow_after_50_creates_second_campaign_and_reflects_on_outreach_mail_content(self, mock_gen, mock_send):
        """
        Test 19:
        - Creating AI drafts for 55 unsent outreach records automatically creates:
          * Campaign 1 with 50 drafts (5 sections × 10 drafts)
          * Campaign 2 with 5 drafts (Section 1)
        - When a new 56th unsent prospect is added later and live sync runs, it goes into Campaign 2 (Section 1, #6)
          rather than exceeding Campaign 1's 50-record limit.
        - When a campaign email is sent for a prospect, LeadQualification.email_status updates and
          LeadQualificationSerializer exposes `latest_email_content` with the exact sent subject, body, and campaign info.
        """
        mock_send.return_value = {'id': 'gmail_msg_55', 'threadId': 'th_55'}
        mock_gen.side_effect = lambda **kw: {
            'subject': f"Custom AI Subject for {kw.get('company_name')}",
            'body': f"Dear {kw.get('company_name')},\n\nTailored pitch for {kw.get('industry')}.",
            'provider': 'gemini',
            'model': 'gemini-flash-lite-latest',
            'context_used': {'portfolio_sources': ['portfolio.pdf']},
        }

        from prospects.campaign_service import create_ai_drafted_campaigns
        from prospects.models import LeadQualification
        from prospects.serializers import LeadQualificationSerializer

        created_prospects = []
        for idx in range(1, 56):
            p = Prospect.objects.create(
                company_name=f'Scale Co {idx:02d}',
                country_head_office='UAE',
                complete_address=f'Office {idx}',
                official_phone_number=f'+971 50 888 {idx:04d}',
                official_email_address=f'team{idx:02d}@scaleco{idx:02d}.ae',
                primary_industries='Technology',
                company_structure='Parent',
                operational_status='Active',
                primary_offering_type='Products',
                created_by=self.user.username,
            )
            created_prospects.append(p)

        campaigns = create_ai_drafted_campaigns(
            user=self.user,
            name='Q4 Mass Outreach',
            prospect_ids=[str(p.id) for p in created_prospects],
        )
        self.assertEqual(len(campaigns), 2)
        camp1, camp2 = campaigns[0], campaigns[1]

        self.assertEqual(camp1.name, 'Q4 Mass Outreach — Campaign 1')
        self.assertEqual(camp1.recipients.count(), 50)
        self.assertEqual(sorted(set(camp1.recipients.values_list('section_number', flat=True))), [1, 2, 3, 4, 5])

        self.assertEqual(camp2.name, 'Q4 Mass Outreach — Campaign 2')
        self.assertEqual(camp2.recipients.count(), 5)
        self.assertEqual(sorted(set(camp2.recipients.values_list('section_number', flat=True))), [1])

        # Add 56th unsent prospect and verify live sync puts it in Campaign 2 (not Campaign 1 which already has 50)
        Prospect.objects.create(
            company_name='Scale Co 56',
            country_head_office='UAE',
            complete_address='Office 56',
            official_phone_number='+971 50 888 0056',
            official_email_address='team56@scaleco56.ae',
            primary_industries='Technology',
            company_structure='Parent',
            operational_status='Active',
            primary_offering_type='Products',
            created_by=self.user.username,
        )
        sync_res = sync_live_unsent_outreach_ai_drafts(user=self.user, auto_draft=True)
        self.assertEqual(sync_res['newly_drafted_count'], 1)
        camp1.refresh_from_db()
        camp2.refresh_from_db()
        self.assertEqual(camp1.recipients.count(), 50)
        self.assertEqual(camp2.recipients.count(), 6)

        # Send Section 1 of Campaign 1 -> first recipient sends -> reflects on Outreach Mail Content
        send_campaign_section(campaign=camp1, section_number=1, user=self.user)
        first_rec = camp1.recipients.order_by('queue_order').first()
        self.assertTrue(send_single_campaign_recipient(first_rec.id))

        lq_obj = LeadQualification.objects.get(prospect=first_rec.prospect)
        self.assertEqual(lq_obj.email_status, 'Waiting for Response')
        serialized = LeadQualificationSerializer(lq_obj).data
        latest = serialized['latest_email_content']
        self.assertIsNotNone(latest)
        self.assertEqual(latest['source'], 'CAMPAIGN_SENT')
        self.assertEqual(latest['campaign_name'], 'Q4 Mass Outreach — Campaign 1')
        self.assertEqual(latest['section_number'], 1)
        self.assertIn(first_rec.prospect.company_name, latest['subject'])
        self.assertIn(first_rec.prospect.company_name, latest['body'])

    @mock.patch('email_ai.services.generate_personalized_email')
    def test_live_sync_concurrency_lock_prevents_duplicate_campaigns(self, mock_gen):
        """Test 20: Active live-sync lock skips concurrent auto-draft mutation safely."""
        mock_gen.side_effect = lambda **kw: {
            'subject': f"Subj {kw.get('company_name')}",
            'body': f"Body {kw.get('company_name')}",
            'provider': 'gemini',
            'model': 'gemini-flash-lite-latest',
            'context_used': {},
        }
        Prospect.objects.create(
            company_name='LockGuard Co',
            country_head_office='UAE',
            complete_address='Dubai',
            official_email_address='lock@guard.ae',
            primary_industries='Tech',
            company_structure='Parent',
            operational_status='Active',
            primary_offering_type='Products',
            created_by=self.user.username,
        )

        self.assertTrue(_LIVE_SYNC_LOCK.acquire(blocking=False))
        try:
            res = sync_live_unsent_outreach_ai_drafts(user=self.user, auto_draft=True)
            self.assertTrue(res['sync_in_progress'])
            self.assertEqual(res['newly_drafted_count'], 0)
            self.assertEqual(EmailCampaign.objects.count(), 0)
            self.assertEqual(mock_gen.call_count, 0)
        finally:
            _LIVE_SYNC_LOCK.release()

    @mock.patch('email_ai.services.generate_personalized_email')
    def test_live_sync_sequential_unique_naming_never_collides_or_skips(self, mock_gen):
        """Test 21: Sequential Campaign N naming ignores completed count shrink and never skips or collides."""
        mock_gen.side_effect = lambda **kw: {
            'subject': f"Subj {kw.get('company_name')}",
            'body': f"Body {kw.get('company_name')}",
            'provider': 'gemini',
            'model': 'gemini-flash-lite-latest',
            'context_used': {},
        }

        EmailCampaign.objects.create(
            name='AI Outreach Campaign (Unsent Mail Auto-Draft)',
            created_by=self.user,
            sender_email='lq@example.com',
            subject='Legacy Done',
            body='Body',
            status=EmailCampaign.Status.COMPLETED,
        )

        for idx in range(1, 56):
            Prospect.objects.create(
                company_name=f'Seq Co {idx:03d}',
                country_head_office='UAE',
                complete_address=f'Addr {idx}',
                official_email_address=f'seq{idx:03d}@seqco.ae',
                primary_industries='Energy',
                company_structure='Parent',
                operational_status='Active',
                primary_offering_type='Products',
                created_by=self.user.username,
            )

        sync1 = sync_live_unsent_outreach_ai_drafts(user=self.user, auto_draft=True)
        self.assertEqual(sync1['newly_drafted_count'], 55)
        self.assertEqual(sync1['remaining_undrafted_count'], 0)

        camp1 = EmailCampaign.objects.get(name='AI Outreach Campaign — Campaign 1')
        camp2 = EmailCampaign.objects.get(name='AI Outreach Campaign — Campaign 2')
        self.assertEqual(camp1.recipients.count(), 50)
        self.assertEqual(camp2.recipients.count(), 5)

        # Complete Campaign 1 (with SENT recipients) and add 50 more prospects -> 45 fill Campaign 2, 5 overflow into Campaign 3 (no collision!)
        camp1.recipients.update(status=EmailCampaignRecipient.Status.SENT)
        camp1.status = EmailCampaign.Status.COMPLETED
        camp1.save(update_fields=['status'])

        for idx in range(56, 106):
            Prospect.objects.create(
                company_name=f'Seq Co {idx:03d}',
                country_head_office='UAE',
                complete_address=f'Addr {idx}',
                official_email_address=f'seq{idx:03d}@seqco.ae',
                primary_industries='Energy',
                company_structure='Parent',
                operational_status='Active',
                primary_offering_type='Products',
                created_by=self.user.username,
            )

        sync2 = sync_live_unsent_outreach_ai_drafts(user=self.user, auto_draft=True)
        self.assertEqual(sync2['newly_drafted_count'], 50)
        camp2.refresh_from_db()
        camp3 = EmailCampaign.objects.get(name='AI Outreach Campaign — Campaign 3')
        self.assertEqual(camp2.recipients.count(), 50)
        self.assertEqual(camp3.recipients.count(), 5)

        all_names = list(EmailCampaign.objects.values_list('name', flat=True))
        self.assertEqual(len(all_names), len(set(all_names)))

    def test_deduplicate_draft_campaign_recipients_cleans_duplicate_drafts_and_empty_campaigns(self):
        """Test 22: Duplicate DRAFT recipients across open campaigns are pruned and empty duplicate campaigns removed."""
        prospects = []
        for idx in range(1, 4):
            prospects.append(
                Prospect.objects.create(
                    company_name=f'Dedup Co {idx}',
                    country_head_office='UAE',
                    complete_address='Dubai',
                    official_email_address=f'dedup{idx}@example.ae',
                    primary_industries='Tech',
                    company_structure='Parent',
                    operational_status='Active',
                    primary_offering_type='Products',
                    created_by=self.user.username,
                )
            )

        c_done = EmailCampaign.objects.create(
            name='Completed Ref Campaign',
            created_by=self.user,
            sender_email='lq@example.com',
            subject='Done',
            body='Body',
            status=EmailCampaign.Status.COMPLETED,
        )
        c_open_1 = EmailCampaign.objects.create(
            name='AI Outreach Campaign — Campaign 2',
            created_by=self.user,
            sender_email='lq@example.com',
            subject='Subj 1',
            body='Body 1',
            status=EmailCampaign.Status.DRAFT,
        )
        c_open_2 = EmailCampaign.objects.create(
            name='AI Outreach Campaign — Campaign 2',
            created_by=self.user,
            sender_email='lq@example.com',
            subject='Subj 2',
            body='Body 2',
            status=EmailCampaign.Status.DRAFT,
        )

        for idx, p in enumerate(prospects):
            EmailCampaignRecipient.objects.create(
                campaign=c_open_1,
                email_address=p.official_email_address,
                prospect=p,
                section_number=1,
                queue_order=idx,
                status=EmailCampaignRecipient.Status.DRAFT,
            )
            EmailCampaignRecipient.objects.create(
                campaign=c_open_2,
                email_address=p.official_email_address,
                prospect=p,
                section_number=1,
                queue_order=idx,
                status=EmailCampaignRecipient.Status.DRAFT,
            )

        res = sync_live_unsent_outreach_ai_drafts(user=self.user, auto_draft=False)
        self.assertEqual(res['deduplicated_drafts'], 3)
        self.assertFalse(EmailCampaign.objects.filter(id=c_open_2.id).exists())
        self.assertTrue(EmailCampaign.objects.filter(id=c_open_1.id).exists())
        self.assertTrue(EmailCampaign.objects.filter(id=c_done.id).exists())
        c_open_1.refresh_from_db()
        self.assertEqual(c_open_1.recipients.count(), 3)

    @mock.patch('email_ai.services.generate_personalized_email')
    def test_manager_live_sync_does_not_duplicate_pre_user_open_drafts(self, mock_gen):
        """Test 23: Manager live-sync considers all open campaigns so PRE users' drafts are never double-drafted."""
        self.prospect.delete()
        mock_gen.side_effect = lambda **kw: {
            'subject': f"Subj {kw.get('company_name')}",
            'body': f"Body {kw.get('company_name')}",
            'provider': 'gemini',
            'model': 'gemini-flash-lite-latest',
            'context_used': {},
        }

        pre_user = User.objects.create_user(username='pre_owner', email='pre@example.com', password='password123')
        pre_user.profile.role = 'PRE'
        pre_user.profile.save()
        GoogleMailCredentials.objects.create(
            user=pre_user,
            email='pre@example.com',
            access_token_encrypted='dummy',
            is_active=True,
        )

        manager_user = User.objects.create_user(username='mgr_user', email='mgr@example.com', password='password123')
        manager_user.profile.role = 'MANAGER'
        manager_user.profile.save()
        GoogleMailCredentials.objects.create(
            user=manager_user,
            email='mgr@example.com',
            access_token_encrypted='dummy',
            is_active=True,
        )

        p_pre = Prospect.objects.create(
            company_name='PRE Owned Co',
            country_head_office='UAE',
            complete_address='Dubai',
            official_email_address='preowned@co.ae',
            primary_industries='Tech',
            company_structure='Parent',
            operational_status='Active',
            primary_offering_type='Products',
            created_by=pre_user.username,
        )
        p_mgr = Prospect.objects.create(
            company_name='Manager Owned Co',
            country_head_office='UAE',
            complete_address='Dubai',
            official_email_address='mgrowned@co.ae',
            primary_industries='Tech',
            company_structure='Parent',
            operational_status='Active',
            primary_offering_type='Products',
            created_by=manager_user.username,
        )
        p_new = Prospect.objects.create(
            company_name='Brand New Unsent Co',
            country_head_office='UAE',
            complete_address='Dubai',
            official_email_address='brandnew@co.ae',
            primary_industries='Tech',
            company_structure='Parent',
            operational_status='Active',
            primary_offering_type='Products',
            created_by=pre_user.username,
        )

        c_pre = EmailCampaign.objects.create(
            name='AI Outreach Campaign — Campaign 1',
            created_by=pre_user,
            sender_email='pre@example.com',
            subject='PRE',
            body='Body',
            status=EmailCampaign.Status.DRAFT,
        )
        EmailCampaignRecipient.objects.create(
            campaign=c_pre,
            email_address=p_pre.official_email_address,
            prospect=p_pre,
            section_number=1,
            queue_order=0,
            status=EmailCampaignRecipient.Status.DRAFT,
        )

        c_mgr = EmailCampaign.objects.create(
            name='AI Outreach Campaign — Campaign 2',
            created_by=manager_user,
            sender_email='mgr@example.com',
            subject='MGR',
            body='Body',
            status=EmailCampaign.Status.DRAFT,
        )
        EmailCampaignRecipient.objects.create(
            campaign=c_mgr,
            email_address=p_mgr.official_email_address,
            prospect=p_mgr,
            section_number=1,
            queue_order=0,
            status=EmailCampaignRecipient.Status.DRAFT,
        )

        res = sync_live_unsent_outreach_ai_drafts(user=manager_user, auto_draft=True)
        self.assertEqual(res['newly_drafted_count'], 1)
        self.assertEqual(EmailCampaignRecipient.objects.filter(prospect=p_pre).count(), 1)
        self.assertEqual(EmailCampaignRecipient.objects.filter(prospect=p_mgr).count(), 1)
        self.assertEqual(EmailCampaignRecipient.objects.filter(prospect=p_new).count(), 1)
        self.assertEqual(EmailCampaignRecipient.objects.get(prospect=p_new).campaign.created_by, pre_user)

    @mock.patch('email_ai.services.generate_personalized_email')
    def test_live_sync_endpoint_respects_max_drafts_and_returns_remaining(self, mock_gen):
        """Test 24: live-sync endpoint processes incremental batches (max_drafts) and reports remaining_undrafted_count."""
        mock_gen.side_effect = lambda **kw: {
            'subject': f"Subj {kw.get('company_name')}",
            'body': f"Body {kw.get('company_name')}",
            'provider': 'gemini',
            'model': 'gemini-flash-lite-latest',
            'context_used': {},
        }

        for idx in range(1, 6):
            Prospect.objects.create(
                company_name=f'Batch Co {idx}',
                country_head_office='UAE',
                complete_address='Dubai',
                official_email_address=f'batch{idx}@example.ae',
                primary_industries='Tech',
                company_structure='Parent',
                operational_status='Active',
                primary_offering_type='Products',
                created_by=self.user.username,
            )

        r1 = self.client.post('/api/email-campaigns/live-sync/', {'auto_draft': True, 'max_drafts': 2}, format='json')
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.data['newly_drafted_count'], 2)
        self.assertEqual(r1.data['remaining_undrafted_count'], 3)
        self.assertFalse(r1.data['sync_in_progress'])

        r2 = self.client.post('/api/email-campaigns/live-sync/', {'auto_draft': True, 'max_drafts': 2}, format='json')
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r2.data['newly_drafted_count'], 2)
        self.assertEqual(r2.data['remaining_undrafted_count'], 1)
        self.assertFalse(r2.data['sync_in_progress'])

        r3 = self.client.post('/api/email-campaigns/live-sync/', {'auto_draft': True, 'max_drafts': 2}, format='json')
        self.assertEqual(r3.status_code, 200)
        self.assertEqual(r3.data['newly_drafted_count'], 1)
        self.assertEqual(r3.data['remaining_undrafted_count'], 0)
        self.assertFalse(r3.data['sync_in_progress'])

        self.assertEqual(EmailCampaign.objects.count(), 1)
        self.assertEqual(EmailCampaign.objects.first().recipients.count(), 5)

    @mock.patch('email_ai.services.generate_personalized_email')
    def test_manager_with_zero_entered_prospects_never_gets_campaign_created_on_live_sync(self, mock_gen):
        """Test 25: A Manager who entered 0 prospects never gets a campaign created under them during live-sync."""
        self.prospect.delete()
        mock_gen.side_effect = lambda **kw: {
            'subject': f"Subj {kw.get('company_name')}",
            'body': f"Body {kw.get('company_name')}",
            'provider': 'gemini',
            'model': 'gemini-flash-lite-latest',
            'context_used': {},
        }

        pre_user = User.objects.create_user(username='mohan_user', email='mohan@example.com', password='password123')
        pre_user.profile.role = 'PRE'
        pre_user.profile.save()
        GoogleMailCredentials.objects.create(
            user=pre_user,
            email='mohan@example.com',
            access_token_encrypted='dummy',
            is_active=True,
        )

        manager_user = User.objects.create_user(username='saif_manager', email='saif@example.com', password='password123')
        manager_user.profile.role = 'MANAGER'
        manager_user.profile.save()

        for idx in range(1, 4):
            Prospect.objects.create(
                company_name=f'Mohan Entered Co {idx}',
                country_head_office='UAE',
                complete_address='Dubai',
                official_email_address=f'mohan{idx}@co.ae',
                primary_industries='Tech',
                company_structure='Parent',
                operational_status='Active',
                primary_offering_type='Products',
                created_by=pre_user.username,
            )

        res = sync_live_unsent_outreach_ai_drafts(user=manager_user, auto_draft=True)
        self.assertEqual(res['newly_drafted_count'], 3)
        self.assertEqual(EmailCampaign.objects.filter(created_by=manager_user).count(), 0)
        self.assertEqual(EmailCampaign.objects.filter(created_by=pre_user).count(), 1)
        self.assertEqual(EmailCampaign.objects.get(created_by=pre_user).recipients.count(), 3)

    def test_reconcile_draft_campaign_ownership_reassigns_existing_manager_drafts_to_prospect_creator(self):
        """Test 26: Pure-DRAFT manager campaigns (single and mixed creators) are reassigned to actual prospect creators while COMPLETED campaigns stay untouched."""
        self.prospect.delete()

        pre_user = User.objects.create_user(username='creator_a', email='creatora@example.com', password='password123')
        pre_user.profile.role = 'PRE'
        pre_user.profile.save()
        GoogleMailCredentials.objects.create(
            user=pre_user,
            email='creatora@gmail.com',
            access_token_encrypted='dummy',
            is_active=True,
        )

        pre_user_2 = User.objects.create_user(username='creator_b', email='creatorb@example.com', password='password123')
        pre_user_2.profile.role = 'PRE'
        pre_user_2.profile.save()
        GoogleMailCredentials.objects.create(
            user=pre_user_2,
            email='creatorb@gmail.com',
            access_token_encrypted='dummy',
            is_active=True,
        )

        manager_user = User.objects.create_user(username='mgr_rec', email='mgrrec@example.com', password='password123')
        manager_user.profile.role = 'MANAGER'
        manager_user.profile.save()

        c21 = EmailCampaign.objects.create(
            name='AI Outreach Campaign — Campaign 21',
            created_by=manager_user,
            sender_email='mgrrec@example.com',
            subject='C21',
            body='Body',
            status=EmailCampaign.Status.DRAFT,
        )
        for idx in range(1, 4):
            p = Prospect.objects.create(
                company_name=f'CreatorA Co {idx}',
                country_head_office='UAE',
                complete_address='Dubai',
                official_email_address=f'ca{idx}@example.ae',
                primary_industries='Tech',
                company_structure='Parent',
                operational_status='Active',
                primary_offering_type='Products',
                created_by=pre_user.username,
            )
            EmailCampaignRecipient.objects.create(
                campaign=c21,
                email_address=p.official_email_address,
                prospect=p,
                section_number=1,
                queue_order=idx - 1,
                status=EmailCampaignRecipient.Status.DRAFT,
            )

        c22 = EmailCampaign.objects.create(
            name='AI Outreach Campaign — Campaign 22',
            created_by=manager_user,
            sender_email='mgrrec@example.com',
            subject='C22',
            body='Body',
            status=EmailCampaign.Status.DRAFT,
        )
        mixed_specs = [
            (pre_user, 'ca4@example.ae'),
            (pre_user, 'ca5@example.ae'),
            (pre_user_2, 'cb1@example.ae'),
            (pre_user_2, 'cb2@example.ae'),
        ]
        for idx, (creator, email) in enumerate(mixed_specs):
            p = Prospect.objects.create(
                company_name=f'Mixed Co {idx}',
                country_head_office='UAE',
                complete_address='Dubai',
                official_email_address=email,
                primary_industries='Tech',
                company_structure='Parent',
                operational_status='Active',
                primary_offering_type='Products',
                created_by=creator.username,
            )
            EmailCampaignRecipient.objects.create(
                campaign=c22,
                email_address=p.official_email_address,
                prospect=p,
                section_number=1,
                queue_order=idx,
                status=EmailCampaignRecipient.Status.DRAFT,
            )

        c_done = EmailCampaign.objects.create(
            name='AI Outreach Campaign — Campaign 10',
            created_by=manager_user,
            sender_email='mgrrec@example.com',
            subject='Done',
            body='Body',
            status=EmailCampaign.Status.COMPLETED,
        )

        res = sync_live_unsent_outreach_ai_drafts(user=manager_user, auto_draft=False)
        self.assertEqual(res['reconciled_ownership_count'], 7)
        self.assertEqual(EmailCampaign.objects.filter(created_by=manager_user, status=EmailCampaign.Status.DRAFT).count(), 0)
        self.assertEqual(EmailCampaignRecipient.objects.filter(campaign__created_by=pre_user).count(), 5)
        self.assertEqual(EmailCampaignRecipient.objects.filter(campaign__created_by=pre_user_2).count(), 2)
        c_done.refresh_from_db()
        self.assertEqual(c_done.created_by, manager_user)
        c21.refresh_from_db()
        self.assertEqual(c21.sender_email, 'creatora@gmail.com')

    @mock.patch('email_ai.services.generate_personalized_email')
    def test_manager_generate_ai_drafts_attributes_campaigns_to_prospect_creators(self, mock_gen):
        """Test 27: Manual create_ai_drafted_campaigns invoked by a Manager attributes campaigns to each prospect's creator."""
        self.prospect.delete()
        mock_gen.side_effect = lambda **kw: {
            'subject': f"Subj {kw.get('company_name')}",
            'body': f"Body {kw.get('company_name')}",
            'provider': 'gemini',
            'model': 'gemini-flash-lite-latest',
            'context_used': {},
        }

        pre_user = User.objects.create_user(username='owner_pre', email='owner@example.com', password='password123')
        pre_user.profile.role = 'PRE'
        pre_user.profile.save()
        GoogleMailCredentials.objects.create(
            user=pre_user,
            email='owner@gmail.com',
            access_token_encrypted='dummy',
            is_active=True,
        )

        manager_user = User.objects.create_user(username='mgr_gen', email='mgrgen@example.com', password='password123')
        manager_user.profile.role = 'MANAGER'
        manager_user.profile.save()

        pids = []
        for idx in range(1, 3):
            p = Prospect.objects.create(
                company_name=f'Manual Gen Co {idx}',
                country_head_office='UAE',
                complete_address='Dubai',
                official_email_address=f'manual{idx}@example.ae',
                primary_industries='Tech',
                company_structure='Parent',
                operational_status='Active',
                primary_offering_type='Products',
                created_by=pre_user.username,
            )
            pids.append(str(p.id))

        from prospects.campaign_service import create_ai_drafted_campaigns
        camps = create_ai_drafted_campaigns(
            user=manager_user,
            name='Team Outreach',
            prospect_ids=pids,
        )
        self.assertEqual(EmailCampaign.objects.filter(created_by=manager_user).count(), 0)
        self.assertEqual(len(camps), 1)
        self.assertEqual(camps[0].created_by, pre_user)
        self.assertEqual(camps[0].sender_email, 'owner@gmail.com')