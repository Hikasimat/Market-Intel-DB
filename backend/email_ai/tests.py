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
