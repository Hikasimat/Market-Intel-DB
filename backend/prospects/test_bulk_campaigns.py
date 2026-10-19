import uuid
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import GoogleMailCredentials, UserProfile
from prospects.campaign_service import (
    create_campaign,
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
