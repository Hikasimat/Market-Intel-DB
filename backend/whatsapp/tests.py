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
    WhatsAppCallRecording,
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

        # 3b. DM User (forbidden)
        self.dm_user = User.objects.create_user(
            username="dm_wa@example.com",
            email="dm_wa@example.com",
            password="dmpassword123",
        )
        self.dm_user.profile.role = "DM"
        self.dm_user.profile.save()

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

    # 2. Permissions: Unauthorized role (DM) forbidden from WhatsApp session list
    def test_unauthorized_role_forbidden_whatsapp_session_list(self):
        self.client.force_authenticate(user=self.dm_user)
        response = self.client.get("/api/whatsapp/session/list/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # 2b. Permissions: PRE user allowed WhatsApp session list
    @patch("whatsapp.client.WAHAClient.get_all_sessions", return_value=[])
    def test_pre_user_allowed_whatsapp_session_list(self, mock_waha):
        self.client.force_authenticate(user=self.pre_user)
        response = self.client.get("/api/whatsapp/session/list/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

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

    # 18. Multi-user session and calling authorization isolation
    def test_multi_user_session_and_calling_isolation(self):
        user_b = User.objects.create_user(
            username="user_b@example.com",
            email="user_b@example.com",
            password="password123",
        )
        user_b.profile.role = "LQ"
        user_b.profile.save()

        session_b = WhatsAppSession.objects.create(
            session_name="session_user_b",
            owner=user_b,
            status=WhatsAppSession.Status.READY,
            phone_number="999888777",
            is_active=True,
        )

        conv_b = WhatsAppConversation.objects.create(
            session=session_b,
            chat_id="999888777@c.us",
            whatsapp_name="Bob User B",
        )

        # Authenticate as User A (lq_user)
        self.client.force_authenticate(user=self.lq_user)

        # User A cannot start or stop User B's session (returns 404 non-disclosing)
        resp_start = self.client.post("/api/whatsapp/session/start/", {"session_name": session_b.session_name})
        self.assertEqual(resp_start.status_code, status.HTTP_404_NOT_FOUND)

        resp_stop = self.client.post("/api/whatsapp/session/stop/", {"session_name": session_b.session_name})
        self.assertEqual(resp_stop.status_code, status.HTTP_404_NOT_FOUND)

        # User A cannot initiate, accept, reject or end call using User B's session (returns 403)
        resp_call_start = self.client.post("/api/whatsapp/calls/start/", {"session_name": session_b.session_name, "to": "123456"})
        self.assertEqual(resp_call_start.status_code, status.HTTP_403_FORBIDDEN)

        resp_call_accept = self.client.post("/api/whatsapp/calls/call_123/accept/", {"session_name": session_b.session_name})
        self.assertEqual(resp_call_accept.status_code, status.HTTP_403_FORBIDDEN)

        resp_call_reject = self.client.post("/api/whatsapp/calls/call_123/reject/", {"session_name": session_b.session_name})
        self.assertEqual(resp_call_reject.status_code, status.HTTP_403_FORBIDDEN)

        resp_call_end = self.client.post("/api/whatsapp/calls/call_123/end/", {"session_name": session_b.session_name})
        self.assertEqual(resp_call_end.status_code, status.HTTP_403_FORBIDDEN)

        resp_call_webrtc = self.client.post("/api/whatsapp/calls/call_123/webrtc/", {"session_name": session_b.session_name, "sdp": "dummy"})
        self.assertEqual(resp_call_webrtc.status_code, status.HTTP_403_FORBIDDEN)

        # User A cannot access User B's conversation messages (returns 404 non-disclosing)
        resp_conv = self.client.get(f"/api/whatsapp/conversations/{conv_b.id}/messages/")
        self.assertEqual(resp_conv.status_code, status.HTTP_404_NOT_FOUND)

    # 19. Call recording upload, listing, stream, and strict multi-user isolation
    def test_call_recording_upload_and_strict_isolation(self):
        user_b = User.objects.create_user(
            username="rec_user_b@example.com",
            email="rec_user_b@example.com",
            password="password123",
        )
        user_b.profile.role = "LQ"
        user_b.profile.save()

        # User A uploads recording
        self.client.force_authenticate(user=self.lq_user)
        audio_file = SimpleUploadedFile("call_rec.webm", b"RIFFfakeaudio\x00\x01\x02", content_type="audio/webm")
        data = {
            "session_name": self.lq_session.session_name,
            "call_id": "call_test_101",
            "participant_phone": "1234567890",
            "participant_name": "Alice Smith",
            "direction": "outbound",
            "duration_seconds": "45",
            "consent_confirmed": "true",
            "file": audio_file,
        }
        upload_resp = self.client.post("/api/whatsapp/calls/recordings/upload/", data, format="multipart")
        self.assertEqual(upload_resp.status_code, status.HTTP_201_CREATED)
        rec_id = upload_resp.data.get("id")
        self.assertTrue(rec_id)

        # User A lists recordings and sees it
        list_resp_a = self.client.get("/api/whatsapp/calls/recordings/")
        self.assertEqual(list_resp_a.status_code, status.HTTP_200_OK)
        rec_ids_a = [r["id"] for r in list_resp_a.data]
        self.assertIn(rec_id, rec_ids_a)

        # User B lists recordings and does NOT see User A's recording
        self.client.force_authenticate(user=user_b)
        list_resp_b = self.client.get("/api/whatsapp/calls/recordings/")
        self.assertEqual(list_resp_b.status_code, status.HTTP_200_OK)
        rec_ids_b = [r["id"] for r in list_resp_b.data]
        self.assertNotIn(rec_id, rec_ids_b)

        # User B attempts to stream, download, or delete User A's recording (returns 403 Forbidden)
        stream_resp_b = self.client.get(f"/api/whatsapp/calls/recordings/{rec_id}/stream/")
        self.assertEqual(stream_resp_b.status_code, status.HTTP_403_FORBIDDEN)

        download_resp_b = self.client.get(f"/api/whatsapp/calls/recordings/{rec_id}/download/")
        self.assertEqual(download_resp_b.status_code, status.HTTP_403_FORBIDDEN)

        delete_resp_b = self.client.delete(f"/api/whatsapp/calls/recordings/{rec_id}/")
        self.assertEqual(delete_resp_b.status_code, status.HTTP_403_FORBIDDEN)

        # User A can stream and delete their own recording
        self.client.force_authenticate(user=self.lq_user)
        stream_resp_a = self.client.get(f"/api/whatsapp/calls/recordings/{rec_id}/stream/")
        self.assertEqual(stream_resp_a.status_code, status.HTTP_200_OK)
        self.assertEqual(stream_resp_a["Content-Type"], "audio/webm")
        if hasattr(stream_resp_a, "close"):
            stream_resp_a.close()

        delete_resp_a = self.client.delete(f"/api/whatsapp/calls/recordings/{rec_id}/")
        self.assertEqual(delete_resp_a.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(WhatsAppCallRecording.objects.filter(id=rec_id).exists())

    # 20. Audio WebSocket token generation
    def test_audio_ws_token_generation(self):
        import base64
        from whatsapp.views import _generate_audio_ws_token

        token = _generate_audio_ws_token(self.lq_user, self.lq_session.session_name, "call_abc_123")
        decoded = base64.urlsafe_b64decode(token).decode("utf-8")
        parts = decoded.split(":")
        self.assertEqual(len(parts), 5)
        self.assertEqual(parts[0], str(self.lq_user.username))
        self.assertEqual(parts[1], self.lq_session.session_name)
        self.assertEqual(parts[2], "abc_123")
        expires_at = int(parts[3])
        self.assertGreater(expires_at, int(timezone.now().timestamp()))
        sig = parts[4]
        self.assertTrue(len(sig) >= 32)
