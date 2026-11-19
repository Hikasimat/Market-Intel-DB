import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from email_ai.models import EmailAIGenerationLog
from prospects.models import Prospect, ProspectContact
from prospects.test_manager_email_activity import ManagerEmailActivityAndSummaryTestCase  # noqa: F401

User = get_user_model()


class _FakeGeminiHttpResponse:
    def __init__(self, payload: dict):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class EmailAIPersonalizedGenerationTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="pre_user",
            password="password123",
            email="pre@marketintel.com",
            first_name="Alex",
            last_name="Morgan",
        )
        self.user.profile.role = "PRE"
        self.user.profile.save()

        self.prospect = Prospect.objects.create(
            company_name="TCS",
            country_head_office="India",
            complete_address="Mumbai, India",
            primary_industries="IT Services & Consulting",
            company_structure="Parent",
            operational_status="Active",
            primary_offering_type="Services",
            official_email_address="contact@tcs.com",
            created_by=self.user.username,
        )
        self.contact = ProspectContact.objects.create(
            prospect=self.prospect,
            contact_name="Rajesh Kumar",
            designation="VP of Digital Transformation",
            official_email="rajesh.kumar@tcs.com",
        )

    @patch("email_ai.services.urllib.request.urlopen")
    def test_generate_personalized_email_for_outreach_inbox_and_campaign(self, mock_urlopen):
        mock_urlopen.return_value = _FakeGeminiHttpResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        {
                                            "subject": "AI-Driven Cloud Modernization for TCS",
                                            "body": "Dear Rajesh Kumar,\n\nWe would love to discuss AI cloud modernization for TCS.\n\nBest regards,\nAlex Morgan",
                                        }
                                    )
                                }
                            ]
                        }
                    }
                ]
            }
        )

        self.client.force_authenticate(user=self.user)

        for ctx in ("OUTREACH", "INBOX", "CAMPAIGN"):
            resp = self.client.post(
                "/api/email-ai/generate/",
                {
                    "prompt": "Write a personalized introduction about our AI automation platform",
                    "source_context": ctx,
                    "tone": "professional",
                    "prospect_id": str(self.prospect.id),
                    "recipient_emails": ["rajesh.kumar@tcs.com"],
                },
                format="json",
            )
            self.assertEqual(resp.status_code, status.HTTP_200_OK)
            self.assertEqual(resp.data["subject"], "AI-Driven Cloud Modernization for TCS")
            self.assertIn("Rajesh Kumar", resp.data["body"])
            self.assertEqual(resp.data["context_used"]["company_name"], "TCS")

        self.assertEqual(EmailAIGenerationLog.objects.count(), 3)

    def test_generate_requires_non_empty_prompt(self):
        self.client.force_authenticate(user=self.user)
        resp = self.client.post(
            "/api/email-ai/generate/",
            {"prompt": "   ", "source_context": "OUTREACH"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_email_draft_quality_no_assumed_timelines_and_no_cliches(self):
        from prospects.models import ProspectOffering

        ProspectOffering.objects.create(
            prospect=self.prospect,
            offering_type="SERVICE",
            name="Cloud Migration Services",
        )
        self.client.force_authenticate(user=self.user)

        # 1. Fallback draft (no GEMINI_API_KEY): rich, company-specific, zero assumed timelines or clichés
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
            res = self.client.post(
                "/api/email-ai/generate/",
                {
                    "prompt": "Introduce our enterprise analytics solutions tailored to TCS",
                    "source_context": "OUTREACH",
                    "tone": "professional",
                    "prospect_id": str(self.prospect.id),
                    "recipient_emails": ["rajesh.kumar@tcs.com"],
                },
                format="json",
            )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        body_low = res.data["body"].lower()
        self.assertIn("tcs", body_low)
        self.assertIn("cloud migration services", body_low)
        self.assertNotIn("next week", body_low)
        self.assertNotIn("this week", body_low)
        self.assertNotIn("hope this email finds you well", body_low)
        self.assertNotIn("operational goals", body_low)

        # 2. Gemini response with unrequested 'next week' is sanitized automatically
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}), \
             patch("email_ai.services.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _FakeGeminiHttpResponse({
                "candidates": [{
                    "content": {
                        "parts": [{
                            "text": json.dumps({
                                "subject": "Supporting Cloud Scale at TCS",
                                "body": "Dear Rajesh Kumar,\n\nWould you be open to a brief call next week to discuss Cloud Migration Services?\n\nBest regards,\nAlex Morgan",
                            })
                        }]
                    }
                }]
            })
            res_gem = self.client.post(
                "/api/email-ai/generate/",
                {
                    "prompt": "Introduce Cloud Migration solutions for TCS",
                    "source_context": "OUTREACH",
                    "prospect_id": str(self.prospect.id),
                    "recipient_emails": ["rajesh.kumar@tcs.com"],
                },
                format="json",
            )
        self.assertEqual(res_gem.status_code, status.HTTP_200_OK)
        self.assertNotIn("next week", res_gem.data["body"].lower())

        # 3. Explicit user-requested timeframe IS preserved
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}), \
             patch("email_ai.services.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _FakeGeminiHttpResponse({
                "candidates": [{
                    "content": {
                        "parts": [{
                            "text": json.dumps({
                                "subject": "Follow-up on TCS Roadmap",
                                "body": "Dear Rajesh Kumar,\n\nHappy to connect next week per your request.\n\nBest regards,\nAlex Morgan",
                            })
                        }]
                    }
                }]
            })
            res_explicit = self.client.post(
                "/api/email-ai/generate/",
                {
                    "prompt": "Reply confirming availability next week per their request",
                    "source_context": "INBOX",
                    "prospect_id": str(self.prospect.id),
                },
                format="json",
            )
        self.assertIn("next week", res_explicit.data["body"].lower())

    def test_dashboard_live_feed_strict_user_isolation_and_ai_recommendations(self):
        from datetime import timedelta
        from django.utils import timezone
        import utils.encryption as encryption
        from accounts.models import GoogleMailCredentials
        from prospects.models import EmailThread, EmailThreadMessage, PreTask

        user_b = User.objects.create_user(
            username="other_pre",
            password="password123",
            email="other@marketintel.com",
        )
        GoogleMailCredentials.objects.create(
            user=self.user,
            email="alex.connected@marketintel.com",
            access_token_encrypted=encryption.encrypt_password("tok_a"),
            refresh_token_encrypted=encryption.encrypt_password("ref_a"),
            token_expiry=timezone.now() + timedelta(hours=1),
            is_active=True,
        )
        GoogleMailCredentials.objects.create(
            user=user_b,
            email="other.connected@marketintel.com",
            access_token_encrypted=encryption.encrypt_password("tok_b"),
            refresh_token_encrypted=encryption.encrypt_password("ref_b"),
            token_expiry=timezone.now() + timedelta(hours=1),
            is_active=True,
        )

        th_a = EmailThread.objects.create(
            owner=self.user,
            prospect=self.prospect,
            mailbox_email="alex.connected@marketintel.com",
            correspondent_email="rajesh.kumar@tcs.com",
            correspondent_name="Rajesh Kumar",
            subject="TCS Cloud Proposal",
            status=EmailThread.Status.WAITING_REPLY,
            last_direction="INBOUND",
            last_snippet="Please share pricing tiers for Q1.",
            last_message_at=timezone.now(),
            message_count=1,
        )
        EmailThreadMessage.objects.create(
            thread=th_a,
            owner=self.user,
            direction=EmailThreadMessage.Direction.INBOUND,
            sender_email="rajesh.kumar@tcs.com",
            sender_name="Rajesh Kumar",
            subject="TCS Cloud Proposal",
            snippet="Please share pricing tiers for Q1.",
            sent_at=timezone.now(),
        )
        PreTask.objects.create(
            task_type=PreTask.TaskType.EMAIL_REPLY,
            status=PreTask.Status.PENDING,
            title="Reply to TCS pricing inquiry",
            assigned_pre=self.user,
            prospect=self.prospect,
            company_name="TCS",
            source_key="dash-task-a",
        )

        th_b = EmailThread.objects.create(
            owner=user_b,
            mailbox_email="other.connected@marketintel.com",
            correspondent_email="secret@competitor.com",
            correspondent_name="Secret Lead",
            subject="SECRET_USER_B_THREAD",
            status=EmailThread.Status.WAITING_REPLY,
            last_direction="INBOUND",
            last_snippet="CONFIDENTIAL_B_SNIPPET",
            last_message_at=timezone.now(),
            message_count=1,
        )
        EmailThreadMessage.objects.create(
            thread=th_b,
            owner=user_b,
            direction=EmailThreadMessage.Direction.INBOUND,
            sender_email="secret@competitor.com",
            subject="SECRET_USER_B_THREAD",
            snippet="CONFIDENTIAL_B_SNIPPET",
            sent_at=timezone.now(),
        )

        self.client.force_authenticate(user=self.user)
        with patch.dict("os.environ", {"GEMINI_API_KEY": ""}):
            feed_res = self.client.get("/api/email-ai/dashboard-feed/")

        self.assertEqual(feed_res.status_code, status.HTTP_200_OK)
        self.assertEqual(feed_res.data["mailbox"]["email"], "alex.connected@marketintel.com")
        self.assertTrue(feed_res.data["mailbox"]["connected"])
        self.assertEqual(len(feed_res.data["incoming_emails"]), 1)
        self.assertEqual(feed_res.data["incoming_emails"][0]["subject"], "TCS Cloud Proposal")
        self.assertNotIn("SECRET_USER_B_THREAD", json.dumps(feed_res.data))
        self.assertGreaterEqual(len(feed_res.data["recommendations"]), 1)

        # Refresh with Gemini AI mock
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key"}), \
             patch("email_ai.services.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = _FakeGeminiHttpResponse({
                "candidates": [{
                    "content": {
                        "parts": [{
                            "text": json.dumps({
                                "ai_summary": "Rajesh Kumar at TCS requested pricing tiers on your active thread.",
                                "recommendations": [{
                                    "title": "Send pricing overview to TCS",
                                    "rationale": "Rajesh Kumar replied asking for pricing tiers.",
                                    "priority": "high",
                                    "action_type": "reply_email",
                                    "suggested_action": "Draft an executive response in Inbox.",
                                    "target_route": "/inbox",
                                    "entity_label": "TCS",
                                }],
                            })
                        }]
                    }
                }]
            })
            ref_res = self.client.post("/api/email-ai/dashboard-feed/refresh/")
        self.assertEqual(ref_res.status_code, status.HTTP_200_OK)
        self.assertIn("Rajesh Kumar", ref_res.data["ai_summary"])
        self.assertEqual(ref_res.data["recommendations"][0]["title"], "Send pricing overview to TCS")

