import hashlib
import hmac
import json
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from whatsapp.models import (
    WhatsAppConfiguration,
    WhatsAppSession,
    WhatsAppConversation,
    WhatsAppMessage,
    WhatsAppOptOut,
    WhatsAppSafetyEvent,
)
from whatsapp.webhooks import _is_ssrf_safe_url
from prospects.models import Prospect, ProspectContact

User = get_user_model()


class WhatsAppSubsystemTestCase(APITestCase):
    def setUp(self):
        # 1. Superuser / Admin
        self.superuser = User.objects.create_superuser(
            username="admin_wa@example.com",
            email="admin_wa@example.com",
            password="adminpassword123",
        )
        self.superuser.profile.role = "MANAGER"
        self.superuser.profile.save()

        # 2. LQ User
        self.lq_user = User.objects.create_user(
            username="lq_wa@example.com",
            email="lq_wa@example.com",
            password="lqpassword123",
        )
        self.lq_user.profile.role = "LQ"
        self.lq_user.profile.save()

        # 3. PRE User
        self.pre_user = User.objects.create_user(
            username="pre_wa@example.com",
            email="pre_wa@example.com",
            password="prepassword123",
        )
        self.pre_user.profile.role = "PRE"
        self.pre_user.profile.save()

        # 4. WhatsApp Configuration
        self.config, _ = WhatsAppConfiguration.objects.get_or_create(
            id=1,
            defaults={"outbound_enabled": True, "safety_stop_active": False},
        )

        # 5. Sample Session owned by LQ user
        self.lq_session = WhatsAppSession.objects.create(
            session_name="test_lq_session",
            owner=self.lq_user,
            status=WhatsAppSession.Status.READY,
            phone_number="1234567890",
            is_active=True,
        )

        # 6. Sample Prospect & Contact
        self.prospect = Prospect.objects.create(
            company_name="Acme Tech",
            official_email_address="contact@acme.com",
        )
        self.contact = ProspectContact.objects.create(
            prospect=self.prospect,
            contact_name="Alice Smith",
            phone_number="+1234567890",
        )

        # 7. Sample Conversation
        self.conversation = WhatsAppConversation.objects.create(
            session=self.lq_session,
            chat_id="1234567890@c.us",
            whatsapp_name="Alice Smith",
            prospect_contact=self.contact,
        )

    # 1. Health endpoint (no auth required)
    def test_whatsapp_health_anonymous_accessible(self):
        response = self.client.get("/api/whatsapp/health/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("status", response.data)

    # 2. Permissions: PRE user forbidden
    def test_pre_user_forbidden_whatsapp_session_list(self):
        self.client.force_authenticate(user=self.pre_user)
        response = self.client.get("/api/whatsapp/session/list/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # 3. Permissions: LQ user allowed session list
    @patch("whatsapp.client.WAHAClient.get_all_sessions", return_value=[])
    def test_lq_user_allowed_whatsapp_session_list(self, mock_waha):
        self.client.force_authenticate(user=self.lq_user)
        response = self.client.get("/api/whatsapp/session/list/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # 4. Session registration by superuser
    @patch("whatsapp.views.start_session", return_value={"status": "STARTING"})
    def test_session_registration_superuser(self, mock_start):
        self.client.force_authenticate(user=self.superuser)
        data = {"session_name": "new_corp_session"}
        response = self.client.post("/api/whatsapp/session/register/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(WhatsAppSession.objects.filter(session_name="new_corp_session").exists())

    # 5. Session registration duplicate conflict
    def test_session_registration_duplicate_conflict(self):
        self.client.force_authenticate(user=self.superuser)
        data = {"session_name": self.lq_session.session_name}
        response = self.client.post("/api/whatsapp/session/register/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)

    # 6. Session listing scoped to user
    @patch("whatsapp.client.WAHAClient.get_all_sessions", return_value=[])
    def test_session_list_scoped_to_user(self, mock_waha):
        other_user = User.objects.create_user(
            username="other_lq@example.com",
            email="other_lq@example.com",
            password="password",
        )
        other_user.profile.role = "LQ"
        other_user.profile.save()
        WhatsAppSession.objects.create(
            session_name="other_session",
            owner=other_user,
            status=WhatsAppSession.Status.READY,
        )

        self.client.force_authenticate(user=self.lq_user)
        response = self.client.get("/api/whatsapp/session/list/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # response.data is a list of sessions
        returned_names = [s["session_name"] for s in response.data]
        self.assertIn("test_lq_session", returned_names)
        self.assertNotIn("other_session", returned_names)

    # 7. Session start view for non-owned session returns 404
    def test_session_start_view_not_owned(self):
        other_user = User.objects.create_user(
            username="lq_rival@example.com",
            email="lq_rival@example.com",
            password="password",
        )
        other_user.profile.role = "LQ"
        other_user.profile.save()
        self.client.force_authenticate(user=other_user)

        data = {"session_name": self.lq_session.session_name}
        response = self.client.post("/api/whatsapp/session/start/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # 8. Session start view success for owner
    @patch("whatsapp.views.start_session", return_value={"status": "STARTING"})
    def test_session_start_view_success(self, mock_start):
        self.client.force_authenticate(user=self.lq_user)
        data = {"session_name": self.lq_session.session_name}
        response = self.client.post("/api/whatsapp/session/start/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # 9. Session stop view success for owner
    @patch("whatsapp.views.stop_session", return_value={"status": "STOPPED"})
    def test_session_stop_view_success(self, mock_stop):
        self.client.force_authenticate(user=self.lq_user)
        data = {"session_name": self.lq_session.session_name}
        response = self.client.post("/api/whatsapp/session/stop/", data, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    # 10. Conversation list and message retrieval
    def test_conversation_list_and_messages(self):
        self.client.force_authenticate(user=self.lq_user)
        WhatsAppMessage.objects.create(
            conversation=self.conversation,
            waha_message_id="msg_001",
            idempotency_key="idemp_001",
            direction=WhatsAppMessage.Direction.INBOUND,
            status=WhatsAppMessage.Status.DELIVERED,
            full_body="Hello from customer",
            body_preview="Hello from customer",
        )

        response = self.client.get("/api/whatsapp/conversations/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        msg_url = f"/api/whatsapp/conversations/{self.conversation.id}/messages/"
        msg_resp = self.client.get(msg_url)
        self.assertEqual(msg_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(msg_resp.data.get("messages", [])), 1)
        self.assertEqual(msg_resp.data["messages"][0]["full_body"], "Hello from customer")

    # 11. Conversation mark read
    def test_conversation_mark_read(self):
        self.client.force_authenticate(user=self.lq_user)
        self.conversation.unread_count = 5
        self.conversation.save()

        url = f"/api/whatsapp/conversations/{self.conversation.id}/read/"
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.unread_count, 0)

    # 12. Link conversation to CRM contact
    def test_conversation_link_crm(self):
        self.client.force_authenticate(user=self.lq_user)
        new_contact = ProspectContact.objects.create(
            prospect=self.prospect,
            contact_name="Bob Jones",
            phone_number="+9876543210",
        )

        url = f"/api/whatsapp/conversations/{self.conversation.id}/link-crm/"
        response = self.client.post(url, {"prospect_contact_id": str(new_contact.id)}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.prospect_contact_id, new_contact.id)

    # 13. Webhook unauthorized without HMAC
    @override_settings(WHATSAPP_WEBHOOK_SECRET="test_secret_123")
    def test_webhook_unauthorized_without_hmac(self):
        payload = {"event": "message", "session": "test_lq_session", "payload": {}}
        response = self.client.post(
            "/api/whatsapp/webhook/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # 14. Webhook valid HMAC accepted
    def test_webhook_success_with_valid_hmac(self):
        secret = "test_secret_key"
        payload = {
            "event": "session.status",
            "session": self.lq_session.session_name,
            "payload": {"status": "WORKING"},
        }
        raw_body = json.dumps(payload).encode("utf-8")
        computed_sig = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

        with patch.dict("os.environ", {"WHATSAPP_WEBHOOK_SECRET": secret}):
            response = self.client.post(
                "/api/whatsapp/webhook/",
                data=raw_body,
                content_type="application/json",
                HTTP_X_WEBHOOK_HMAC=f"sha256={computed_sig}",
            )
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data.get("status"), "received")

    # 15. Opt-out keyword detection ("STOP")
    def test_webhook_opt_out_keyword(self):
        from whatsapp.services import check_incoming_for_opt_out

        triggered = check_incoming_for_opt_out(
            message_body="Please STOP sending messages",
            phone_digits="5551234567",
        )
        self.assertTrue(triggered)
        self.assertTrue(WhatsAppOptOut.objects.filter(phone_digits="5551234567").exists())

    # 16. SSRF defense blocks loopback, RFC1918, and metadata endpoints
    def test_ssrf_mitigation_blocks_internal_media_url(self):
        allowed_service = "https://waha.mycompany.internal:3000"

        # Loopback blocked
        self.assertFalse(_is_ssrf_safe_url("http://127.0.0.1/evil.jpg", allowed_service))
        self.assertFalse(_is_ssrf_safe_url("http://localhost:8000/internal", allowed_service))

        # Cloud metadata blocked
        self.assertFalse(_is_ssrf_safe_url("http://169.254.169.254/latest/meta-data/", allowed_service))

        # Private RFC1918 addresses blocked
        self.assertFalse(_is_ssrf_safe_url("http://10.0.1.5/admin", allowed_service))
        self.assertFalse(_is_ssrf_safe_url("http://192.168.1.100/secret", allowed_service))

        # Configured WAHA service URL allowed
        self.assertTrue(_is_ssrf_safe_url("https://waha.mycompany.internal:3000/media/pic.jpg", allowed_service))

    # 17. Avatar upload persists via default_storage
    def test_avatar_upload_uses_storage(self):
        self.client.force_authenticate(user=self.lq_user)
        dummy_avatar = SimpleUploadedFile("avatar.png", b"\x89PNG\r\n\x1a\nfakeimage", content_type="image/png")
        url = f"/api/whatsapp/conversations/{self.conversation.id}/avatar/"
        response = self.client.post(url, {"file": dummy_avatar}, format="multipart")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.conversation.refresh_from_db()
        self.assertTrue(self.conversation.custom_avatar_url)
        self.assertIn("whatsapp_avatars", self.conversation.custom_avatar_url)
