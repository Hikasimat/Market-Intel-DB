import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch
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
            created_by=self.lq_user.username,
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


class WhatsAppMultiAccountIsolationTestCase(APITestCase):
    """
    Automated verification of WhatsApp chat history isolation, session bounding,
    and message delivery status (single-tick, double-tick, blue double-tick).
    """
    def setUp(self):
        self.secret = "test_webhook_secret_key"

        # Patch background avatar fetching to prevent SQLite thread locking
        self.patcher_avatar = patch("whatsapp.webhooks._fetch_contact_profile_picture_bg")
        self.mock_avatar = self.patcher_avatar.start()

        # User A (PRE role)
        self.user_a = User.objects.create_user(
            username="user_a_pre@example.com",
            email="user_a_pre@example.com",
            password="passwordA123",
        )
        self.user_a.profile.role = "PRE"
        self.user_a.profile.save()

        # User B (PRE role)
        self.user_b = User.objects.create_user(
            username="user_b_pre@example.com",
            email="user_b_pre@example.com",
            password="passwordB123",
        )
        self.user_b.profile.role = "PRE"
        self.user_b.profile.save()

        # Session for User A (phone +919003619221)
        self.session_a = WhatsAppSession.objects.create(
            session_name="user_a_session_9003619221",
            owner=self.user_a,
            status=WhatsAppSession.Status.READY,
            phone_number="919003619221",
            is_active=True,
        )

        # Session for User B (phone +919876543210)
        self.session_b = WhatsAppSession.objects.create(
            session_name="user_b_session_9876543210",
            owner=self.user_b,
            status=WhatsAppSession.Status.READY,
            phone_number="919876543210",
            is_active=True,
        )

        # Common remote contact communicating with both User A and User B
        self.remote_chat_id = "9360239398@c.us"

        # Conversation for User A with remote contact
        self.conv_a = WhatsAppConversation.objects.create(
            session=self.session_a,
            chat_id=self.remote_chat_id,
            whatsapp_name="Common Remote Contact",
        )

        # Conversation for User B with the SAME remote contact
        self.conv_b = WhatsAppConversation.objects.create(
            session=self.session_b,
            chat_id=self.remote_chat_id,
            whatsapp_name="Common Remote Contact",
        )

    def tearDown(self):
        super().tearDown()
        self.patcher_avatar.stop()

    def _post_signed_webhook(self, payload):
        raw_body = json.dumps(payload).encode("utf-8")
        computed_sig = hmac.new(self.secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        with patch.dict("os.environ", {"WHATSAPP_WEBHOOK_SECRET": self.secret}):
            return self.client.post(
                "/api/whatsapp/webhook/",
                data=raw_body,
                content_type="application/json",
                HTTP_X_WEBHOOK_HMAC=f"sha256={computed_sig}",
            )

    # Test A: Conversation message isolation between sessions with the same remote contact
    def test_conversation_messages_isolated_between_sessions(self):
        # Create messages in User A's conversation
        msg_a_out = WhatsAppMessage.objects.create(
            conversation=self.conv_a,
            waha_message_id="msg_a_out_1",
            idempotency_key="idemp_a_out_1",
            direction=WhatsAppMessage.Direction.OUTBOUND,
            status=WhatsAppMessage.Status.SENT,
            full_body="Hello from User A to 9360239398",
            body_preview="Hello from User A to 9360239398",
        )
        msg_a_in = WhatsAppMessage.objects.create(
            conversation=self.conv_a,
            waha_message_id="msg_a_in_1",
            idempotency_key="idemp_a_in_1",
            direction=WhatsAppMessage.Direction.INBOUND,
            status=WhatsAppMessage.Status.DELIVERED,
            full_body="Reply from 9360239398 to User A",
            body_preview="Reply from 9360239398 to User A",
        )

        # Create messages in User B's conversation (same remote contact!)
        msg_b_out = WhatsAppMessage.objects.create(
            conversation=self.conv_b,
            waha_message_id="msg_b_out_1",
            idempotency_key="idemp_b_out_1",
            direction=WhatsAppMessage.Direction.OUTBOUND,
            status=WhatsAppMessage.Status.SENT,
            full_body="Hello from User B to 9360239398",
            body_preview="Hello from User B to 9360239398",
        )
        msg_b_in = WhatsAppMessage.objects.create(
            conversation=self.conv_b,
            waha_message_id="msg_b_in_1",
            idempotency_key="idemp_b_in_1",
            direction=WhatsAppMessage.Direction.INBOUND,
            status=WhatsAppMessage.Status.DELIVERED,
            full_body="Reply from 9360239398 to User B",
            body_preview="Reply from 9360239398 to User B",
        )

        # 1. User A retrieves messages from conv_a -> must see ONLY User A's messages
        self.client.force_authenticate(user=self.user_a)
        resp_a = self.client.get(f"/api/whatsapp/conversations/{self.conv_a.id}/messages/")
        self.assertEqual(resp_a.status_code, status.HTTP_200_OK)
        returned_bodies_a = [m["full_body"] for m in resp_a.data.get("messages", [])]
        self.assertIn("Hello from User A to 9360239398", returned_bodies_a)
        self.assertIn("Reply from 9360239398 to User A", returned_bodies_a)
        self.assertNotIn("Hello from User B to 9360239398", returned_bodies_a)
        self.assertNotIn("Reply from 9360239398 to User B", returned_bodies_a)

        # 2. User A attempts to retrieve messages from conv_b -> 404 Forbidden/Not Found
        resp_a_forbidden = self.client.get(f"/api/whatsapp/conversations/{self.conv_b.id}/messages/")
        self.assertEqual(resp_a_forbidden.status_code, status.HTTP_404_NOT_FOUND)

        # 3. User B retrieves messages from conv_b -> must see ONLY User B's messages
        self.client.force_authenticate(user=self.user_b)
        resp_b = self.client.get(f"/api/whatsapp/conversations/{self.conv_b.id}/messages/")
        self.assertEqual(resp_b.status_code, status.HTTP_200_OK)
        returned_bodies_b = [m["full_body"] for m in resp_b.data.get("messages", [])]
        self.assertIn("Hello from User B to 9360239398", returned_bodies_b)
        self.assertIn("Reply from 9360239398 to User B", returned_bodies_b)
        self.assertNotIn("Hello from User A to 9360239398", returned_bodies_b)
        self.assertNotIn("Reply from 9360239398 to User A", returned_bodies_b)

        # 4. User B attempts to retrieve messages from conv_a -> 404 Forbidden/Not Found
        resp_b_forbidden = self.client.get(f"/api/whatsapp/conversations/{self.conv_a.id}/messages/")
        self.assertEqual(resp_b_forbidden.status_code, status.HTTP_404_NOT_FOUND)

    # Test B: Inbound webhook message routing strictly isolated by session
    def test_webhook_inbound_message_isolated_to_target_session(self):
        payload_a = {
            "event": "message",
            "session": self.session_a.session_name,
            "payload": {
                "id": "false_9360239398@c.us_inbound_msg_a",
                "from": self.remote_chat_id,
                "to": "919003619221@c.us",
                "body": "Confidential message for User A only",
                "fromMe": False,
                "timestamp": 1700000100,
            },
        }
        resp_a = self._post_signed_webhook(payload_a)
        self.assertEqual(resp_a.status_code, status.HTTP_200_OK)

        payload_b = {
            "event": "message",
            "session": self.session_b.session_name,
            "payload": {
                "id": "false_9360239398@c.us_inbound_msg_b",
                "from": self.remote_chat_id,
                "to": "919876543210@c.us",
                "body": "Confidential message for User B only",
                "fromMe": False,
                "timestamp": 1700000200,
            },
        }
        resp_b = self._post_signed_webhook(payload_b)
        self.assertEqual(resp_b.status_code, status.HTTP_200_OK)

        # Messages in User A's conversation must have ONLY User A's message
        messages_a = list(self.conv_a.messages.values_list("full_body", flat=True))
        self.assertIn("Confidential message for User A only", messages_a)
        self.assertNotIn("Confidential message for User B only", messages_a)

        # Messages in User B's conversation must have ONLY User B's message
        messages_b = list(self.conv_b.messages.values_list("full_body", flat=True))
        self.assertIn("Confidential message for User B only", messages_b)
        self.assertNotIn("Confidential message for User A only", messages_b)

    # Test C: Message ACK routing isolated to originating session
    def test_message_ack_isolated_to_originating_session(self):
        # Both conversations have an outbound message with identical raw ID
        msg_a = WhatsAppMessage.objects.create(
            conversation=self.conv_a,
            waha_message_id="ack_test_id_100",
            idempotency_key="idemp_ack_a_100",
            direction=WhatsAppMessage.Direction.OUTBOUND,
            status=WhatsAppMessage.Status.SENT,
            full_body="User A outbound message",
        )
        msg_b = WhatsAppMessage.objects.create(
            conversation=self.conv_b,
            waha_message_id="ack_test_id_100",
            idempotency_key="idemp_ack_b_100",
            direction=WhatsAppMessage.Direction.OUTBOUND,
            status=WhatsAppMessage.Status.SENT,
            full_body="User B outbound message",
        )

        # ACK arrives for User A's session: ack=3 (DELIVERED)
        ack_payload = {
            "event": "message.ack",
            "session": self.session_a.session_name,
            "payload": {
                "id": f"true_{self.remote_chat_id}_ack_test_id_100",
                "rawId": "ack_test_id_100",
                "ack": 3,
                "ackName": "DEVICE",
                "fromMe": True,
                "to": self.remote_chat_id,
            },
        }
        resp = self._post_signed_webhook(ack_payload)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # User A's message must be updated to DELIVERED
        msg_a.refresh_from_db()
        self.assertEqual(msg_a.status, WhatsAppMessage.Status.DELIVERED)

        # User B's message must REMAIN SENT (untouched)
        msg_b.refresh_from_db()
        self.assertEqual(msg_b.status, WhatsAppMessage.Status.SENT)

    # Test D: Monotonic delivery status transitions (Ticks: SENT -> DELIVERED -> READ)
    def test_monotonic_message_status_ticks(self):
        msg = WhatsAppMessage.objects.create(
            conversation=self.conv_a,
            waha_message_id="monotonic_msg_200",
            idempotency_key="idemp_monotonic_200",
            direction=WhatsAppMessage.Direction.OUTBOUND,
            status=WhatsAppMessage.Status.PENDING,
            full_body="Tick transition test message",
        )

        def send_ack(ack_code, ack_name):
            return self._post_signed_webhook({
                "event": "message.ack",
                "session": self.session_a.session_name,
                "payload": {
                    "id": f"true_{self.remote_chat_id}_monotonic_msg_200",
                    "rawId": "monotonic_msg_200",
                    "ack": ack_code,
                    "ackName": ack_name,
                    "fromMe": True,
                    "to": self.remote_chat_id,
                },
            })

        # 1. PENDING -> SENT (ack=2, SERVER)
        resp = send_ack(2, "SERVER")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        msg.refresh_from_db()
        self.assertEqual(msg.status, WhatsAppMessage.Status.SENT)

        # 2. SENT -> DELIVERED (ack=3, DEVICE)
        resp = send_ack(3, "DEVICE")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        msg.refresh_from_db()
        self.assertEqual(msg.status, WhatsAppMessage.Status.DELIVERED)

        # 3. DELIVERED -> READ (ack=4, READ)
        resp = send_ack(4, "READ")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        msg.refresh_from_db()
        self.assertEqual(msg.status, WhatsAppMessage.Status.READ)

        # 4. Out-of-order delayed ack 2 (SENT) arrives -> status must NOT regress!
        resp = send_ack(2, "SERVER")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        msg.refresh_from_db()
        self.assertEqual(msg.status, WhatsAppMessage.Status.READ)

        # 5. Out-of-order delayed ack 3 (DELIVERED) arrives -> status must NOT regress!
        resp = send_ack(3, "DEVICE")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        msg.refresh_from_db()
        self.assertEqual(msg.status, WhatsAppMessage.Status.READ)

    # Test E: Webhook strictly rejects payload missing session
    def test_webhook_rejects_missing_session(self):
        payload_no_session = {
            "event": "message",
            "payload": {
                "id": "false_9360239398@c.us_no_session",
                "from": self.remote_chat_id,
                "to": "919003619221@c.us",
                "body": "Should fail",
                "fromMe": False,
            },
        }
        resp = self._post_signed_webhook(payload_no_session)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    # Test F: Webhook strictly rejects unknown session name without affecting DB
    def test_webhook_rejects_unknown_session(self):
        payload_unknown_session = {
            "event": "message",
            "session": "non_existent_rogue_session",
            "payload": {
                "id": "false_9360239398@c.us_unknown_session",
                "from": self.remote_chat_id,
                "to": "919003619221@c.us",
                "body": "Should be rejected cleanly",
                "fromMe": False,
            },
        }
        resp = self._post_signed_webhook(payload_unknown_session)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # Verify no message was created for unknown session
        self.assertFalse(WhatsAppMessage.objects.filter(full_body="Should be rejected cleanly").exists())

    # Test G: Group incoming message from another member is visible to connected user
    def test_group_incoming_message_from_other_member_visible(self):
        group_jid = "120363023456789@g.us"
        group_conv = WhatsAppConversation.objects.create(
            session=self.session_a,
            chat_id=group_jid,
            whatsapp_name="Project Group Alpha",
        )

        # 1. Connected user A sent a message in the group
        msg_out = WhatsAppMessage.objects.create(
            conversation=group_conv,
            waha_message_id=f"true_{group_jid}_out_101",
            idempotency_key="idemp_group_out_101",
            direction=WhatsAppMessage.Direction.OUTBOUND,
            status=WhatsAppMessage.Status.SENT,
            full_body="Welcome everyone to the group!",
            body_preview="Welcome everyone to the group!",
        )

        # 2. Another group member (919876543210) sends a message into the group
        member_phone = "919876543210@c.us"
        payload_group_in = {
            "event": "message",
            "session": self.session_a.session_name,
            "payload": {
                "id": f"false_{group_jid}_in_member_202",
                "rawId": "in_member_202",
                "timestamp": int(timezone.now().timestamp()),
                "from": member_phone,
                "fromMe": False,
                "to": group_jid,
                "participant": member_phone,
                "phone": "919876543210",
                "pushName": "Bob Member",
                "body": "Thanks for adding me!",
                "hasMedia": False,
                "ack": 3,
                "ackName": "DEVICE",
                "_data": {
                    "key": {
                        "remoteJid": group_jid,
                        "fromMe": False,
                        "id": "in_member_202",
                        "participant": "919876543210@s.whatsapp.net",
                    },
                    "message": {
                        "conversation": "Thanks for adding me!",
                    },
                    "messageTimestamp": int(timezone.now().timestamp()),
                    "pushName": "Bob Member",
                },
            },
        }

        resp = self._post_signed_webhook(payload_group_in)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        # Verify the incoming group message was saved under the group conversation
        saved_msg = WhatsAppMessage.objects.filter(
            conversation=group_conv,
            full_body="Thanks for adding me!",
        ).first()
        self.assertIsNotNone(saved_msg, "Group message from other member was not saved under the group conversation!")
        self.assertEqual(saved_msg.direction, WhatsAppMessage.Direction.INBOUND)
        self.assertEqual(saved_msg.error_code, "Bob Member")

        # 3. User A queries messages for this group conversation -> must see both messages
        self.client.force_authenticate(user=self.user_a)
        resp_msgs = self.client.get(f"/api/whatsapp/conversations/{group_conv.id}/messages/")
        self.assertEqual(resp_msgs.status_code, status.HTTP_200_OK)
        returned_bodies = [m["full_body"] for m in resp_msgs.data.get("messages", [])]
        self.assertIn("Welcome everyone to the group!", returned_bodies)
        self.assertIn("Thanks for adding me!", returned_bodies)


class WhatsAppDynamicSyncAndLifecycleTestCase(APITestCase):
    """
    Comprehensive test suite covering Part A requirements:
    - Dynamic unlimited multi-user sessions with deterministic HMAC naming
    - No hardcoded session names / 'default' fallback leaks
    - Persistent DB storage (messages, timestamps, media, reply context, acks, groups, @lid)
    - Scenario A: Logout preserves owner, phone_number, conversations, messages
    - Scenario B: Reconnect same number restores history and syncs missing messages idempotently
    - Scenario C: Reconnect different number preserves old account history separately without merging
    - Calling endpoints regression intact
    """

    WEBHOOK_SECRET = "test-dynamic-webhook-secret"

    def setUp(self):
        self.patcher_secret = patch("django.conf.settings.WHATSAPP_WEBHOOK_SECRET", self.WEBHOOK_SECRET, create=True)
        self.patcher_secret.start()
        self.addCleanup(self.patcher_secret.stop)
        self._env_patch = patch.dict("os.environ", {"WHATSAPP_WEBHOOK_SECRET": self.WEBHOOK_SECRET})
        self._env_patch.start()
        self.addCleanup(self._env_patch.stop)

        from django.core.cache import cache
        cache.clear()

        self.patcher_avatar = patch("whatsapp.webhooks._fetch_contact_profile_picture_bg")
        self.patcher_avatar.start()
        self.addCleanup(self.patcher_avatar.stop)
        self.patcher_media = patch("whatsapp.webhooks._download_and_save_media_bg")
        self.patcher_media.start()
        self.addCleanup(self.patcher_media.stop)

        WhatsAppConfiguration.objects.get_or_create(pk=1, defaults={"outbound_enabled": True})

        self.user1 = User.objects.create_user(username="dyn_pre1", password="p1", email="dyn1@test.com")
        self.user1.profile.role = "PRE"
        self.user1.profile.save()

        self.user2 = User.objects.create_user(username="dyn_pre2", password="p2", email="dyn2@test.com")
        self.user2.profile.role = "PRE"
        self.user2.profile.save()

        self.user3 = User.objects.create_user(username="dyn_pre3", password="p3", email="dyn3@test.com")
        self.user3.profile.role = "LQ"
        self.user3.profile.save()

        self.prospect = Prospect.objects.create(company_name="Acme Dynamics Ltd")
        self.contact = ProspectContact.objects.create(
            prospect=self.prospect,
            contact_name="Alice KeyPerson",
            phone_number="+919811122233",
        )

    def _post_signed_webhook(self, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        sig = hmac.new(self.WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return self.client.post(
            "/api/whatsapp/webhook/",
            data=body,
            content_type="application/json",
            HTTP_X_WEBHOOK_HMAC=f"sha256={sig}",
        )

    def test_1_dynamic_multi_user_connection_and_isolation(self):
        """Users 1, 2, 3 get independent deterministic sessions and connect unique numbers concurrently."""
        from whatsapp.client import WAHAServiceError
        fake_waha = MagicMock()
        fake_waha.get_session_status.side_effect = WAHAServiceError("not found", status_code=404)
        fake_waha.get_qr.return_value = {"qr": "data:image/png;base64,FAKEQR", "qrBase64": "data:image/png;base64,FAKEQR"}

        with patch("whatsapp.client.get_waha_client", return_value=fake_waha), \
             patch("whatsapp.services.get_waha_client", return_value=fake_waha):
            sessions_by_user = {}
            for idx, u in enumerate([self.user1, self.user2, self.user3], start=1):
                self.client.force_authenticate(user=u)
                resp = self.client.get("/api/whatsapp/qr/")
                self.assertEqual(resp.status_code, status.HTTP_200_OK)
                sname = resp.data.get("session_name")
                self.assertTrue(sname.startswith(f"wa_u{u.id}_"))
                self.assertNotEqual(sname, "default")
                sessions_by_user[idx] = sname

        self.assertEqual(len(set(sessions_by_user.values())), 3)

        # Simulate WAHA session.connected webhooks with varied phone formats
        phones = ["+919876500001", "919876500002", "+91 98765 00003"]
        for idx, raw_phone in enumerate(phones, start=1):
            res = self._post_signed_webhook({
                "event": "session.connected",
                "id": f"evt_conn_{idx}",
                "session": sessions_by_user[idx],
                "payload": {"me": {"phone": raw_phone}},
            })
            self.assertEqual(res.status_code, status.HTTP_200_OK)

        s1 = WhatsAppSession.objects.get(session_name=sessions_by_user[1])
        s2 = WhatsAppSession.objects.get(session_name=sessions_by_user[2])
        s3 = WhatsAppSession.objects.get(session_name=sessions_by_user[3])
        self.assertEqual(s1.status, WhatsAppSession.Status.READY)
        self.assertEqual(s1.owner, self.user1)
        self.assertEqual(s1.phone_number, "+919876500001")
        self.assertEqual(s2.phone_number, "+919876500002")
        self.assertEqual(s3.phone_number, "+919876500003")

    def test_2_persistence_dedup_media_reply_ack_and_contact_rename(self):
        """Inbound/outbound messages persist with timestamps, media, reply context, name updates, and idempotency."""
        from whatsapp.services import get_or_create_user_session
        s1 = get_or_create_user_session(self.user1, create=True)
        s1.status = WhatsAppSession.Status.READY
        s1.phone_number = "+919876500001"
        s1.save()

        ts_in = 1710000100
        inbound_payload = {
            "event": "message",
            "id": "evt_in_media_1",
            "session": s1.session_name,
            "payload": {
                "id": "false_919811122233@c.us_MSG001",
                "from": "919811122233@s.whatsapp.net",
                "to": "919876500001@c.us",
                "fromMe": False,
                "timestamp": ts_in,
                "pushName": "Alice Updated",
                "body": "Please see attached brochure",
                "hasMedia": True,
                "mediaUrl": "/api/files/brochure.pdf",
                "media": {"mimetype": "application/pdf", "filename": "brochure.pdf"},
            },
        }
        self.assertEqual(self._post_signed_webhook(inbound_payload).status_code, status.HTTP_200_OK)
        # Duplicate webhook with same payload id must not duplicate message
        self.assertEqual(self._post_signed_webhook(inbound_payload).status_code, status.HTTP_200_OK)

        conv = WhatsAppConversation.objects.get(
            session=s1,
            chat_id__in=["919811122233@c.us", "919811122233@s.whatsapp.net"],
        )
        self.assertEqual(conv.whatsapp_name, "Alice Updated")
        self.assertEqual(WhatsAppMessage.objects.filter(conversation=conv).count(), 1)
        msg1 = WhatsAppMessage.objects.get(conversation=conv)
        self.assertTrue(msg1.has_media)
        self.assertEqual(msg1.media_mime_type, "application/pdf")
        self.assertEqual(msg1.media_url, "/api/files/brochure.pdf")
        self.assertEqual(int(msg1.waha_timestamp.timestamp()), ts_in)

        # Outbound send -> WAHA echo webhook -> ACK update -> no duplicate outbound record
        fake_waha = MagicMock()
        fake_waha.send_text.return_value = {"id": "true_919811122233@c.us_OUT999"}
        self.client.force_authenticate(user=self.user1)
        with patch("whatsapp.client.get_waha_client", return_value=fake_waha), \
             patch("whatsapp.services.get_waha_client", return_value=fake_waha):
            send_resp = self.client.post("/api/whatsapp/send/", {
                "prospect_contact_id": str(self.contact.id),
                "message_body": "Thanks Alice, reviewing now.",
            }, format="json")
        self.assertEqual(send_resp.status_code, status.HTTP_201_CREATED)

        echo_payload = {
            "event": "message",
            "id": "evt_echo_out_1",
            "session": s1.session_name,
            "payload": {
                "id": "true_919811122233@c.us_OUT999",
                "from": "919876500001@c.us",
                "to": conv.chat_id,
                "fromMe": True,
                "timestamp": ts_in + 60,
                "body": "Thanks Alice, reviewing now.",
                "quotedMsgId": "false_919811122233@c.us_MSG001",
            },
        }
        self.assertEqual(self._post_signed_webhook(echo_payload).status_code, status.HTTP_200_OK)
        self.assertEqual(WhatsAppMessage.objects.filter(conversation=conv, direction="OUTBOUND").count(), 1)

        ack_payload = {
            "event": "message.ack",
            "id": "evt_ack_out_1",
            "session": s1.session_name,
            "payload": {
                "id": "true_919811122233@c.us_OUT999",
                "ack": 4,
                "ackName": "READ",
            },
        }
        self.assertEqual(self._post_signed_webhook(ack_payload).status_code, status.HTTP_200_OK)
        out_msg = WhatsAppMessage.objects.get(conversation=conv, direction="OUTBOUND")
        self.assertEqual(out_msg.status, WhatsAppMessage.Status.READ)

    def test_3_logout_preserves_history_and_reconnect_same_number_syncs_missing(self):
        """Scenario A & Scenario B: Logout keeps all history; reconnect same number restores and syncs delta."""
        from whatsapp.services import get_or_create_user_session
        s1 = get_or_create_user_session(self.user1, create=True)
        s1.status = WhatsAppSession.Status.READY
        s1.phone_number = "+919876500001"
        s1.save()

        conv = WhatsAppConversation.objects.create(
            session=s1,
            chat_id="919000011111@c.us",
            phone_number="+919000011111",
            account_phone="+919876500001",
            whatsapp_name="Existing Client",
            last_message_at=timezone.now(),
        )
        WhatsAppMessage.objects.create(
            conversation=conv,
            idempotency_key="orig-1",
            waha_message_id="false_919000011111@c.us_OLD1",
            direction=WhatsAppMessage.Direction.INBOUND,
            full_body="Message before logout",
            body_preview="Message before logout",
            waha_timestamp=timezone.now(),
            sent_at=timezone.now(),
        )

        # Scenario A: Logout via API preserves session.owner, session.phone_number, convs & messages
        fake_waha = MagicMock()
        fake_waha.logout_session.return_value = {"status": "DISCONNECTED"}
        self.client.force_authenticate(user=self.user1)
        with patch("whatsapp.client.get_waha_client", return_value=fake_waha), \
             patch("whatsapp.services.get_waha_client", return_value=fake_waha):
            logout_resp = self.client.post("/api/whatsapp/session/logout/", {"session_name": s1.session_name}, format="json")
        self.assertEqual(logout_resp.status_code, status.HTTP_200_OK)

        s1.refresh_from_db()
        self.assertEqual(s1.status, WhatsAppSession.Status.DISCONNECTED)
        self.assertEqual(s1.owner, self.user1)
        self.assertEqual(s1.phone_number, "+919876500001")
        self.assertEqual(WhatsAppConversation.objects.filter(session=s1).count(), 1)
        self.assertEqual(WhatsAppMessage.objects.filter(conversation=conv).count(), 1)

        # Scenario B: Reconnect same number without leading '+' via webhook
        self._post_signed_webhook({
            "event": "session.connected",
            "id": "evt_reconn_same",
            "session": s1.session_name,
            "payload": {"me": {"phone": "919876500001"}},
        })
        s1.refresh_from_db()
        self.assertTrue(s1.is_active)
        self.assertEqual(s1.status, WhatsAppSession.Status.READY)
        self.assertEqual(s1.phone_number, "+919876500001")

        # Sync history: WAHA returns duplicate OLD1 plus NEW2 (offline missing message)
        now_ts = int(timezone.now().timestamp())
        fake_sync_waha = MagicMock()
        fake_sync_waha.get_recent_messages_from_stats.return_value = []
        fake_sync_waha.get_chats.return_value = [{"id": "919000011111@c.us", "name": "Existing Client"}]
        fake_sync_waha.get_messages_paginated.return_value = [
            {
                "id": "false_919000011111@c.us_OLD1",
                "from": "919000011111@c.us",
                "to": "919876500001@c.us",
                "fromMe": False,
                "body": "Message before logout",
                "timestamp": now_ts - 120,
            },
            {
                "id": "false_919000011111@c.us_NEW2",
                "from": "919000011111@c.us",
                "to": "919876500001@c.us",
                "fromMe": False,
                "body": "Offline missed message",
                "timestamp": now_ts - 30,
            },
        ]
        fake_sync_waha.get_groups.return_value = []
        with patch("whatsapp.client.get_waha_client", return_value=fake_sync_waha):
            sync_resp = self.client.post("/api/whatsapp/sync-history/", {"days": 2}, format="json")
            self.assertEqual(sync_resp.status_code, status.HTTP_200_OK)
            self.assertEqual(sync_resp.data["synced"], 1)
            self.assertEqual(WhatsAppMessage.objects.filter(conversation=conv).count(), 2)

            list_resp = self.client.get("/api/whatsapp/conversations/")
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_resp.data), 1)
        msgs_resp = self.client.get(f"/api/whatsapp/conversations/{conv.id}/messages/")
        bodies = [m["full_body"] for m in msgs_resp.data["messages"]]
        self.assertEqual(bodies, ["Message before logout", "Offline missed message"])

    def test_4_reconnect_different_number_preserves_old_history_without_merging(self):
        """Scenario C: Reconnecting a different WhatsApp number archives old session & keeps histories separate."""
        from whatsapp.services import get_or_create_user_session
        s_old = get_or_create_user_session(self.user1, create=True)
        s_old.status = WhatsAppSession.Status.READY
        s_old.phone_number = "+919876500001"
        s_old.save()

        conv_old = WhatsAppConversation.objects.create(
            session=s_old,
            chat_id="919000022222@c.us",
            phone_number="+919000022222",
            account_phone="+919876500001",
            whatsapp_name="Old Number Contact",
            last_message_at=timezone.now(),
        )
        WhatsAppMessage.objects.create(
            conversation=conv_old,
            idempotency_key="old-acc-1",
            waha_message_id="false_919000022222@c.us_M1",
            direction=WhatsAppMessage.Direction.INBOUND,
            full_body="Secret old number history",
            body_preview="Secret old number history",
        )

        # User 1 connects a different number on next login
        self._post_signed_webhook({
            "event": "session.connected",
            "id": "evt_switch_new",
            "session": s_old.session_name,
            "payload": {"me": {"phone": "+919999900099"}},
        })

        s_old.refresh_from_db()
        self.assertFalse(s_old.is_active)
        self.assertEqual(s_old.phone_number, "+919876500001")
        # Old history must NOT be deleted!
        self.assertEqual(WhatsAppConversation.objects.filter(session=s_old).count(), 1)
        self.assertEqual(WhatsAppMessage.objects.filter(conversation=conv_old).count(), 1)

        s_new = WhatsAppSession.objects.get(owner=self.user1, is_active=True)
        self.assertNotEqual(s_new.id, s_old.id)
        self.assertEqual(s_new.phone_number, "+919999900099")
        self.assertEqual(s_new.status, WhatsAppSession.Status.READY)

        # New active account does not merge old number's conversations
        self.client.force_authenticate(user=self.user1)
        fake_waha = MagicMock()
        fake_waha.get_groups.return_value = []
        with patch("whatsapp.client.get_waha_client", return_value=fake_waha):
            convs_new = self.client.get("/api/whatsapp/conversations/")
        self.assertEqual(convs_new.status_code, status.HTTP_200_OK)
        self.assertEqual(len(convs_new.data), 0)

    def test_5_cross_session_lid_isolation_and_calling_routes_intact(self):
        """@lid resolution must not leak across sessions; unowned 'default' webhook is rejected; calling routes work."""
        from whatsapp.services import get_or_create_user_session
        s1 = get_or_create_user_session(self.user1, create=True)
        s1.status = WhatsAppSession.Status.READY
        s1.phone_number = "+919876500001"
        s1.save()

        s2 = get_or_create_user_session(self.user2, create=True)
        s2.status = WhatsAppSession.Status.READY
        s2.phone_number = "+919876500002"
        s2.save()

        WhatsAppConversation.objects.create(
            session=s1,
            chat_id="919811122233@c.us",
            prospect_contact=self.contact,
            prospect=self.prospect,
            metadata={"lid_chat_id": "2262000111222@lid"},
        )

        # Same @lid arrives on User 2's session -> must NOT match User 1's conversation/prospect via @lid
        res_u2 = self._post_signed_webhook({
            "event": "message",
            "id": "evt_lid_u2",
            "session": s2.session_name,
            "payload": {
                "id": "false_2262000111222@lid_L1",
                "from": "2262000111222@lid",
                "fromMe": False,
                "body": "Hello User 2",
                "timestamp": int(timezone.now().timestamp()),
            },
        })
        self.assertEqual(res_u2.status_code, status.HTTP_200_OK)
        self.assertTrue(WhatsAppConversation.objects.filter(session=s2, chat_id="2262000111222@lid").exists())
        u2_conv = WhatsAppConversation.objects.get(session=s2, chat_id="2262000111222@lid")
        self.assertIsNone(u2_conv.prospect_contact)

        # Unowned "default" webhook must not create data
        self._post_signed_webhook({
            "event": "message",
            "id": "evt_unowned_default",
            "session": "default",
            "payload": {
                "id": "false_919999988888@c.us_X1",
                "from": "919999988888@c.us",
                "fromMe": False,
                "body": "Should never persist under unowned default",
            },
        })
        self.assertFalse(WhatsAppMessage.objects.filter(full_body="Should never persist under unowned default").exists())

        # Regression: Calling endpoints remain operational and untouched
        self.client.force_authenticate(user=self.user1)
        rec_resp = self.client.get("/api/whatsapp/calls/recordings/")
        self.assertEqual(rec_resp.status_code, status.HTTP_200_OK)
        call_status_resp = self.client.get("/api/whatsapp/calls/status/")
        self.assertEqual(call_status_resp.status_code, status.HTTP_200_OK)

        # Contact info (with linked prospect colleagues) & anonymous <img> profile-pic SVG fallback
        info_resp = self.client.get("/api/whatsapp/contact-info/919811122233@c.us/")
        self.assertEqual(info_resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(info_resp.data.get("members", [])), 1)

        self.client.force_authenticate(user=None)
        anon_pic_resp = self.client.get("/api/whatsapp/profile-pic/120363413990423012@g.us/")
        self.assertEqual(anon_pic_resp.status_code, status.HTTP_200_OK)

    def test_6_dynamic_session_ownership_and_query_params(self):
        """Legacy unowned user/HMAC sessions bind dynamically; status/conversations honor owned session params; create_group never falls back to default."""
        from whatsapp.services import generate_user_session_name, reconcile_connected_session
        from whatsapp.webhooks import _resolve_originating_session
        from whatsapp.client import WAHAClient, WAHAServiceError

        # 1. Stale unowned 'default' holding user1's phone is deactivated on reconcile
        stale_default = WhatsAppSession.objects.create(
            session_name="default",
            owner=None,
            status=WhatsAppSession.Status.READY,
            phone_number="+919003619221",
            is_active=True,
        )
        u1_det_name = generate_user_session_name(self.user1)
        # Existing unowned row carrying verified deterministic HMAC name dynamically binds owner
        u1_session = WhatsAppSession.objects.create(
            session_name=u1_det_name,
            owner=None,
            status=WhatsAppSession.Status.STARTING,
            is_active=True,
        )
        resolved = _resolve_originating_session(u1_det_name)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.owner_id, self.user1.id)

        active_u1, _, _ = reconcile_connected_session(resolved, "+91 90036 19221", source="test")
        self.assertEqual(active_u1.owner_id, self.user1.id)
        self.assertEqual(active_u1.phone_number, "+919003619221")
        stale_default.refresh_from_db()
        self.assertFalse(stale_default.is_active)

        # 2. Status & Conversations endpoints honor explicit owned session_name / session_id and reject others with 404
        u2_det_name = generate_user_session_name(self.user2)
        u2_session = WhatsAppSession.objects.create(
            session_name=u2_det_name,
            owner=self.user2,
            status=WhatsAppSession.Status.READY,
            phone_number="+919876500002",
            is_active=True,
        )
        WhatsAppConversation.objects.create(
            session=active_u1,
            chat_id="919811122233@c.us",
            whatsapp_name="Alice U1",
            account_phone="+919003619221",
        )

        self.client.force_authenticate(user=self.user1)
        fake_waha = MagicMock()
        fake_waha.get_session_status.return_value = {"status": "WORKING"}
        fake_waha.get_groups.return_value = []
        with patch("whatsapp.client.get_waha_client", return_value=fake_waha), \
             patch("whatsapp.services.get_waha_client", return_value=fake_waha):
            own_status = self.client.get(f"/api/whatsapp/status/?session_name={u1_det_name}")
            self.assertEqual(own_status.status_code, status.HTTP_200_OK)
            self.assertEqual(own_status.data["session"]["session_name"], u1_det_name)

            other_status = self.client.get(f"/api/whatsapp/status/?session_name={u2_det_name}")
            self.assertEqual(other_status.status_code, status.HTTP_404_NOT_FOUND)

            own_convs = self.client.get(f"/api/whatsapp/conversations/?session_id={active_u1.pk}")
            self.assertEqual(own_convs.status_code, status.HTTP_200_OK)
            self.assertEqual(len(own_convs.data), 1)

            other_convs = self.client.get(f"/api/whatsapp/conversations/?session_id={u2_session.pk}")
            self.assertEqual(other_convs.status_code, status.HTTP_404_NOT_FOUND)

        # 3. create_group rejects 'default' and does not fall back to 'default'
        client_inst = WAHAClient()
        with self.assertRaises(WAHAServiceError):
            client_inst.create_group("default", "Test Group", ["919811122233"])

        # 4. Status endpoint dynamically reconciles WORKING + new scanned phone from QR_REQUIRED
        curr_u1 = WhatsAppSession.objects.get(owner=self.user1, is_active=True)
        curr_u1.status = WhatsAppSession.Status.QR_REQUIRED
        curr_u1.save(update_fields=["status"])
        fake_waha.get_session_status.return_value = {
            "status": "WORKING",
            "me": {"id": "919360239398@c.us", "phone": "+919360239398"},
        }
        with patch("whatsapp.client.get_waha_client", return_value=fake_waha), \
             patch("whatsapp.services.get_waha_client", return_value=fake_waha):
            switched_status = self.client.get("/api/whatsapp/status/")
        self.assertEqual(switched_status.status_code, status.HTTP_200_OK)
        self.assertEqual(switched_status.data["status"], WhatsAppSession.Status.READY)
        self.assertEqual(switched_status.data["phone_number"], "+919360239398")





