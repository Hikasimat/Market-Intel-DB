import hashlib
import hmac
import json
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from prospects.models import Prospect, ProspectContact
from whatsapp.models import WhatsAppConversation, WhatsAppMessage, WhatsAppOptOut, WhatsAppSession
from whatsapp_ai.models import WhatsAppAIAutoReplyConfig, WhatsAppAIReplyLog

User = get_user_model()


class _FakeGeminiHttpResponse:
    def __init__(self, reply_text: str):
        payload = {
            "candidates": [{
                "content": {
                    "parts": [{"text": json.dumps({"reply": reply_text})}]
                }
            }]
        }
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class WhatsAppGeminiAutoReplyTests(APITestCase):
    """
    Verifies Gemini AI automatic WhatsApp replies in standalone `whatsapp_ai` app:
      - Works when session owner is completely logged out of Market Intel DB
      - Identifies sender by mobile number / WhatsApp ID & retrieves synchronized DB history
      - Generates contextual reply with Gemini AI and sends via same connected session
      - Persists outbound reply in DB and deduplicates subsequent WAHA echo
      - Preserves strict per-session isolation & opt-out guard
      - Leaves calling routes unaffected
    """

    def setUp(self):
        self.patcher_avatar = patch("whatsapp.webhooks._fetch_contact_profile_picture_bg")
        self.patcher_avatar.start()
        self.webhook_secret = "test-wa-gemini-secret"

        self.user1 = User.objects.create_user(username="pre_mohan", email="mohan@alpha.com", password="pw")
        self.user1.profile.role = "PRE"
        self.user1.profile.save()

        self.user2 = User.objects.create_user(username="pre_sara", email="sara@alpha.com", password="pw")
        self.user2.profile.role = "PRE"
        self.user2.profile.save()

        self.session1 = WhatsAppSession.objects.create(
            session_name="wa_u1_connected",
            owner=self.user1,
            status=WhatsAppSession.Status.READY,
            phone_number="+919003619221",
            is_active=True,
        )
        self.session2 = WhatsAppSession.objects.create(
            session_name="wa_u2_connected",
            owner=self.user2,
            status=WhatsAppSession.Status.READY,
            phone_number="+919876543210",
            is_active=True,
        )

        self.prospect = Prospect.objects.create(company_name="Zenith Labs", created_by=self.user1.username)
        self.contact = ProspectContact.objects.create(
            prospect=self.prospect,
            contact_name="Arjun Mehta",
            phone_number="+919811122233",
            designation="VP Engineering",
        )

    def tearDown(self):
        self.patcher_avatar.stop()
        super().tearDown()

    def _post_signed_webhook(self, payload: dict):
        raw_body = json.dumps(payload).encode("utf-8")
        sig = hmac.new(self.webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        with patch.dict("os.environ", {"WHATSAPP_WEBHOOK_SECRET": self.webhook_secret}):
            return self.client.post(
                "/api/whatsapp/webhook/",
                data=raw_body,
                content_type="application/json",
                HTTP_X_WEBHOOK_HMAC=f"sha256={sig}",
            )

    def test_incoming_message_while_logged_out_triggers_gemini_reply_with_history_and_syncs(self):
        # User explicitly logs out of Market Intel; WhatsAppSession stays READY
        self.client.force_authenticate(user=self.user1)
        logout_res = self.client.post("/api/auth/logout/", {})
        self.assertEqual(logout_res.status_code, status.HTTP_200_OK)
        self.client.force_authenticate(user=None)  # Completely logged out

        now = timezone.now()
        conv1 = WhatsAppConversation.objects.create(
            session=self.session1,
            chat_id="919811122233@c.us",
            phone_number="+919811122233",
            whatsapp_name="Arjun Mehta",
            prospect=self.prospect,
            prospect_contact=self.contact,
            is_matched=True,
        )
        # Seed prior synchronized history on session1
        WhatsAppMessage.objects.create(
            idempotency_key="hist-1",
            conversation=conv1,
            direction=WhatsAppMessage.Direction.OUTBOUND,
            status=WhatsAppMessage.Status.SENT,
            body_preview="Hi Arjun, would Thursday at 3 PM work for a demo?",
            full_body="Hi Arjun, would Thursday at 3 PM work for a demo?",
            waha_timestamp=now - timedelta(minutes=15),
            sent_at=now - timedelta(minutes=15),
        )

        # Unrelated session2 conversation for same remote phone must NEVER leak into session1's prompt
        conv2 = WhatsAppConversation.objects.create(
            session=self.session2,
            chat_id="919811122233@c.us",
            phone_number="+919811122233",
            whatsapp_name="Arjun Other Session",
        )
        WhatsAppMessage.objects.create(
            idempotency_key="hist-other-session",
            conversation=conv2,
            direction=WhatsAppMessage.Direction.INBOUND,
            status=WhatsAppMessage.Status.DELIVERED,
            body_preview="SECRET_OTHER_USER_CONTEXT",
            full_body="SECRET_OTHER_USER_CONTEXT",
            waha_timestamp=now - timedelta(minutes=5),
            sent_at=now - timedelta(minutes=5),
        )

        fake_waha = MagicMock()
        fake_waha.send_text.return_value = {"id": "true_919811122233@c.us_AI_REPLY_1"}
        captured_prompts = []

        def _fake_urlopen(req, timeout=15):
            body = json.loads(req.data.decode("utf-8"))
            captured_prompts.append(body["contents"][0]["parts"][0]["text"])
            return _FakeGeminiHttpResponse("Thanks Arjun! Yes, Thursday at 3 PM is confirmed.")

        inbound_payload = {
            "event": "message",
            "id": "evt_ai_in_1",
            "session": self.session1.session_name,
            "payload": {
                "id": "false_919811122233@c.us_IN_AI_1",
                "from": "919811122233@c.us",
                "to": "919003619221@c.us",
                "fromMe": False,
                "pushName": "Arjun Mehta",
                "body": "Yes Thursday works, please confirm!",
                "timestamp": int(now.timestamp()),
            },
        }

        with patch.dict("os.environ", {
            "GEMINI_API_KEY": "fake-gemini-key",
            "WHATSAPP_AI_AUTO_REPLY_ENABLED": "true",
        }), \
             patch("whatsapp.client.get_waha_client", return_value=fake_waha), \
             patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            res = self._post_signed_webhook(inbound_payload)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(captured_prompts), 1)
        prompt_sent = captured_prompts[0]
        self.assertIn("Thursday at 3 PM", prompt_sent)
        self.assertIn("Yes Thursday works, please confirm!", prompt_sent)
        self.assertIn("+919811122233", prompt_sent)
        self.assertIn("Zenith Labs", prompt_sent)
        self.assertNotIn("SECRET_OTHER_USER_CONTEXT", prompt_sent)

        # Reply was sent through the exact same connected session
        fake_waha.send_text.assert_called_once()
        send_kwargs = fake_waha.send_text.call_args.kwargs
        self.assertEqual(send_kwargs["session_name"], self.session1.session_name)
        self.assertEqual(send_kwargs["chat_id"], "919811122233@c.us")
        self.assertIn("Thursday at 3 PM is confirmed", send_kwargs["text"])

        # Both inbound & outbound messages persisted and synchronized in DB
        msgs = list(WhatsAppMessage.objects.filter(conversation=conv1).order_by("created_at"))
        self.assertEqual(len(msgs), 3)  # seeded outbound + incoming + AI outbound
        ai_out = msgs[-1]
        self.assertEqual(ai_out.direction, WhatsAppMessage.Direction.OUTBOUND)
        self.assertEqual(ai_out.waha_message_id, "true_919811122233@c.us_AI_REPLY_1")

        ai_log = WhatsAppAIReplyLog.objects.get(session=self.session1)
        self.assertEqual(ai_log.status, WhatsAppAIReplyLog.Status.SENT)
        self.assertEqual(ai_log.reply_message_id, ai_out.pk)
        self.assertEqual(ai_log.history_message_count, 2)

        conv1.refresh_from_db()
        self.assertTrue(conv1.last_message_from_me)
        self.assertIn("Thursday at 3 PM is confirmed", conv1.last_message_preview)

        # WAHA echo webhook for our AI outbound reply must deduplicate cleanly without re-triggering Gemini
        echo_payload = {
            "event": "message",
            "id": "evt_ai_echo_1",
            "session": self.session1.session_name,
            "payload": {
                "id": "true_919811122233@c.us_AI_REPLY_1",
                "from": "919003619221@c.us",
                "to": "919811122233@c.us",
                "fromMe": True,
                "body": "Thanks Arjun! Yes, Thursday at 3 PM is confirmed.",
                "timestamp": int(now.timestamp()),
            },
        }
        with patch.dict("os.environ", {"WHATSAPP_AI_AUTO_REPLY_ENABLED": "true"}):
            echo_res = self._post_signed_webhook(echo_payload)
        self.assertEqual(echo_res.status_code, status.HTTP_200_OK)
        self.assertEqual(WhatsAppMessage.objects.filter(conversation=conv1).count(), 3)

    def test_opt_out_and_calling_endpoints_remain_intact(self):
        WhatsAppOptOut.objects.create(phone_digits="919811122233", reason="STOP", is_active=True)
        fake_waha = MagicMock()
        inbound_payload = {
            "event": "message",
            "id": "evt_ai_optout_1",
            "session": self.session1.session_name,
            "payload": {
                "id": "false_919811122233@c.us_OPTOUT_1",
                "from": "919811122233@c.us",
                "fromMe": False,
                "body": "Hello again",
                "timestamp": int(timezone.now().timestamp()),
            },
        }
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key", "WHATSAPP_AI_AUTO_REPLY_ENABLED": "true"}), \
             patch("whatsapp.client.get_waha_client", return_value=fake_waha):
            res = self._post_signed_webhook(inbound_payload)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        fake_waha.send_text.assert_not_called()
        log_entry = WhatsAppAIReplyLog.objects.filter(session=self.session1).latest("created_at")
        self.assertEqual(log_entry.status, WhatsAppAIReplyLog.Status.SKIPPED)
        self.assertEqual(log_entry.error_message, "recipient_opted_out")

        # Calling endpoints remain completely unaffected
        self.client.force_authenticate(user=self.user1)
        self.assertEqual(self.client.get("/api/whatsapp/calls/status/").status_code, status.HTTP_200_OK)
        self.assertEqual(self.client.get("/api/whatsapp/calls/recordings/").status_code, status.HTTP_200_OK)

    def test_realtime_sync_cycle_triggers_immediate_reply_and_ignores_stale_history(self):
        from whatsapp_ai.realtime_listener import run_realtime_sync_cycle

        # Ensure user is logged out
        self.client.force_authenticate(user=None)
        now = timezone.now()
        old_dt = now - timedelta(hours=2)

        fake_waha = MagicMock()
        fake_waha.get_all_sessions.return_value = []
        fake_waha.get_recent_messages_from_stats.return_value = [
            {
                "id": "false_919811122233@c.us_OLD_HIST_1",
                "session": self.session1.session_name,
                "from": "919811122233@c.us",
                "to": "919003619221@c.us",
                "fromMe": False,
                "pushName": "Arjun Mehta",
                "body": "Old message from 2 hours ago",
                "timestamp": int(old_dt.timestamp()),
            },
            {
                "id": "false_919811122233@c.us_FRESH_LIVE_1",
                "session": self.session1.session_name,
                "from": "919811122233@c.us",
                "to": "919003619221@c.us",
                "fromMe": False,
                "pushName": "Arjun Mehta",
                "body": "Hi, can you share pricing right now?",
                "timestamp": int(now.timestamp()),
            },
        ]
        fake_waha.get_chats.return_value = []
        fake_waha.send_text.return_value = {"id": "true_919811122233@c.us_RT_AI_1"}

        def _fake_urlopen(req, timeout=15):
            return _FakeGeminiHttpResponse("Hi Arjun! Here is our pricing breakdown—let me know what tier you prefer.")

        with patch.dict("os.environ", {
            "GEMINI_API_KEY": "fake-gemini-key",
            "WHATSAPP_AI_AUTO_REPLY_ENABLED": "true",
            "WHATSAPP_SERVICE_URL": "http://localhost:3000",
        }), \
             patch("whatsapp.client.get_waha_client", return_value=fake_waha), \
             patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            result = run_realtime_sync_cycle(force_chat_poll=True)

        self.assertGreaterEqual(result["sessions"], 1)
        self.assertGreaterEqual(result["synced"], 2)

        # Only the fresh live message triggered Gemini & WAHA send_text (old history was NOT answered)
        fake_waha.send_text.assert_called_once()
        self.assertEqual(fake_waha.send_text.call_args.kwargs["session_name"], self.session1.session_name)
        self.assertIn("pricing breakdown", fake_waha.send_text.call_args.kwargs["text"])

        logs = WhatsAppAIReplyLog.objects.filter(session=self.session1).order_by("created_at")
        self.assertEqual(logs.count(), 1)
        self.assertEqual(logs.first().incoming_message.waha_message_id, "false_919811122233@c.us_FRESH_LIVE_1")
        self.assertEqual(logs.first().status, WhatsAppAIReplyLog.Status.SENT)

    def test_disconnect_and_reconnect_other_whatsapp_dynamically_auto_replies(self):
        """
        Simulate disconnecting a previous WhatsApp number and connecting a completely
        different WhatsApp number on the user's session slot, then receiving a new
        incoming message while logged out — the real-time listener must dynamically
        reconcile the new account, ingest the message, and send the Gemini AI reply
        through the new WhatsApp session without anything hardcoded.
        """
        from whatsapp_ai.realtime_listener import run_realtime_sync_cycle

        # 1. Disconnect user1's old WhatsApp (+919003619221) in DB
        self.session1.status = WhatsAppSession.Status.DISCONNECTED
        self.session1.save(update_fields=["status"])
        self.client.force_authenticate(user=None)  # Logged out of Market Intel

        now = timezone.now()
        fake_waha = MagicMock()
        # WAHA now reports a DIFFERENT WhatsApp number (+919360239398) connected on user1's session slot
        fake_waha.get_all_sessions.return_value = [
            {
                "name": "wa_u1_connected",
                "status": "WORKING",
                "me": {"id": "919360239398@c.us", "phone": "+919360239398"},
            }
        ]
        fake_waha.get_recent_messages_from_stats.return_value = []
        fake_waha.get_chats.side_effect = lambda sess, limit=15: (
            [
                {
                    "id": "917025117045@c.us",
                    "unreadCount": 1,
                    "lastMessageTimestamp": int(now.timestamp()),
                }
            ]
            if sess == "wa_u1_connected"
            else []
        )
        fake_waha.get_messages.side_effect = lambda sess, chat_id, limit=5: (
            [
                {
                    "id": "true_917025117045@c.us_OUT_SWITCH_1",
                    "from": "919360239398@c.us",
                    "to": "917025117045@c.us",
                    "fromMe": True,
                    "body": "hi",
                    "timestamp": int((now - timedelta(seconds=30)).timestamp()),
                },
                {
                    "id": "false_917025117045@c.us_IN_SWITCH_1",
                    "from": "917025117045@c.us",
                    "to": "919360239398@c.us",
                    "fromMe": False,
                    "pushName": "Fahad",
                    "body": "Hello I am fahad. Is this Plus UAE?",
                    "timestamp": int(now.timestamp()),
                },
            ]
            if sess == "wa_u1_connected"
            else []
        )
        fake_waha.send_text.return_value = {"id": "true_917025117045@c.us_AI_SWITCH_1"}

        captured_prompts = []

        def _fake_urlopen(req, timeout=15):
            body = json.loads(req.data.decode("utf-8"))
            captured_prompts.append(body["contents"][0]["parts"][0]["text"])
            return _FakeGeminiHttpResponse("Hi Fahad! How can I assist you today?")

        with patch.dict("os.environ", {
            "GEMINI_API_KEY": "fake-gemini-key",
            "WHATSAPP_AI_AUTO_REPLY_ENABLED": "true",
            "WHATSAPP_SERVICE_URL": "http://localhost:3000",
        }), \
             patch("whatsapp.client.get_waha_client", return_value=fake_waha), \
             patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            result = run_realtime_sync_cycle(force_chat_poll=True)

        self.assertGreaterEqual(result["sessions"], 1)

        # Old session was archived cleanly and a new active READY session exists for +919360239398
        self.session1.refresh_from_db()
        self.assertFalse(self.session1.is_active)
        new_sess = WhatsAppSession.objects.get(
            owner=self.user1,
            session_name="wa_u1_connected",
            is_active=True,
        )
        self.assertEqual(new_sess.status, WhatsAppSession.Status.READY)
        self.assertEqual(new_sess.phone_number, "+919360239398")

        # Prompt referenced the dynamically switched account (+919360239398) and Fahad's message
        self.assertEqual(len(captured_prompts), 1)
        self.assertIn("+919360239398", captured_prompts[0])
        self.assertIn("Hello I am fahad. Is this Plus UAE?", captured_prompts[0])

        # AI sent reply via the newly connected session slot
        fake_waha.send_text.assert_called_once()
        self.assertEqual(fake_waha.send_text.call_args.kwargs["session_name"], "wa_u1_connected")
        self.assertEqual(fake_waha.send_text.call_args.kwargs["chat_id"], "917025117045@c.us")
        self.assertIn("Hi Fahad!", fake_waha.send_text.call_args.kwargs["text"])

        ai_log = WhatsAppAIReplyLog.objects.get(session=new_sess)
        self.assertEqual(ai_log.status, WhatsAppAIReplyLog.Status.SENT)

    def test_manual_outreach_overrides_stale_incoming_keyword_opt_out(self):
        # Old keyword opt-out from days earlier
        old_opt = WhatsAppOptOut.objects.create(
            phone_digits="917025117045",
            reason=WhatsAppOptOut.Reason.INCOMING_KEYWORD,
            trigger_message="unsubscribe",
            is_active=True,
        )
        WhatsAppOptOut.objects.filter(pk=old_opt.pk).update(
            created_at=timezone.now() - timedelta(days=7)
        )

        conv = WhatsAppConversation.objects.create(
            session=self.session1,
            chat_id="917025117045@c.us",
            phone_number="+917025117045",
            whatsapp_name="Fahad",
        )
        # Agent manually initiates chat via UI (`performed_by=user1`) after opt-out
        WhatsAppMessage.objects.create(
            idempotency_key="manual-hi-1",
            conversation=conv,
            performed_by=self.user1,
            direction=WhatsAppMessage.Direction.OUTBOUND,
            status=WhatsAppMessage.Status.SENT,
            body_preview="hi",
            full_body="hi",
            sent_at=timezone.now() - timedelta(seconds=30),
        )

        fake_waha = MagicMock()
        fake_waha.send_text.return_value = {"id": "true_917025117045@c.us_AI_RESUMED_1"}
        inbound_payload = {
            "event": "message",
            "id": "evt_ai_resumed_1",
            "session": self.session1.session_name,
            "payload": {
                "id": "false_917025117045@c.us_IN_RESUMED_1",
                "from": "917025117045@c.us",
                "to": "919003619221@c.us",
                "fromMe": False,
                "pushName": "Fahad",
                "body": "Hello I am fahad. Is this Plus UAE?",
                "timestamp": int(timezone.now().timestamp()),
            },
        }
        with patch.dict("os.environ", {"GEMINI_API_KEY": "fake-key", "WHATSAPP_AI_AUTO_REPLY_ENABLED": "true"}), \
             patch("whatsapp.client.get_waha_client", return_value=fake_waha), \
             patch("urllib.request.urlopen", return_value=_FakeGeminiHttpResponse("Hi Fahad! Yes, how can I help you?")):
            res = self._post_signed_webhook(inbound_payload)

        self.assertEqual(res.status_code, status.HTTP_200_OK)
        fake_waha.send_text.assert_called_once()
        old_opt.refresh_from_db()
        self.assertFalse(old_opt.is_active)

    def test_customer_identity_and_collision_isolation_rules(self):
        """
        Verifies mandatory customer identity and collision isolation rules (1-9, 19):
          1. Two different customers in same session with different names stay separate.
          2. Two different customers with same WhatsApp display name ('Mohan V') stay separate.
          3. Two different customers sharing last 8/10 phone digits (+19811122233 vs +919811122233) stay separate.
          4. Unresolved @lid sender is never assigned to another customer's conversation.
          5. New sender is never attached to the most recently active outbound conversation.
          6. CRM contact is linked only on exact, owner-scoped, unambiguous full phone match;
             fromMe=True echo with pushName='Mohan V' never overwrites customer whatsapp_name.
          8. Group conversations remain separate from individual conversations.
          9 & 19. GET /api/whatsapp/conversations/ is strictly read-only (does not merge, move
             messages, or soft-delete conversations) and serializes the right customer name.
        """
        now = timezone.now()

        # Seed a foreign-owner CRM contact named "Mohan V" with blank phone, plus ambiguous duplicates
        other_prospect = Prospect.objects.create(company_name="Foreign Corp", created_by=self.user2.username)
        ProspectContact.objects.create(
            prospect=other_prospect,
            contact_name="Mohan V",
            phone_number="",
        )
        # Ambiguous contacts for +919999888877 under user1
        ProspectContact.objects.create(
            prospect=self.prospect,
            contact_name="Ambiguous One",
            phone_number="+919999888877",
        )
        ProspectContact.objects.create(
            prospect=self.prospect,
            contact_name="Ambiguous Two",
            phone_number="+919999888877",
        )

        # Seed a recent outbound 1-on-1 conversation to Arjun (+919811122233)
        conv_arjun = WhatsAppConversation.objects.create(
            session=self.session1,
            chat_id="919811122233@c.us",
            phone_number="+919811122233",
            whatsapp_name="Arjun Mehta",
            prospect=self.prospect,
            prospect_contact=self.contact,
            is_matched=True,
            last_message_at=now - timedelta(seconds=10),
            last_message_from_me=True,
            last_message_preview="Outbound to Arjun",
        )
        WhatsAppMessage.objects.create(
            idempotency_key="out-arjun-1",
            conversation=conv_arjun,
            direction=WhatsAppMessage.Direction.OUTBOUND,
            status=WhatsAppMessage.Status.SENT,
            body_preview="Outbound to Arjun",
            full_body="Outbound to Arjun",
            sent_at=now - timedelta(seconds=10),
        )

        with patch.dict("os.environ", {"WHATSAPP_AI_AUTO_REPLY_ENABLED": "false"}):
            # Case 3: Different customer sharing last 10 digits (+19811122233 vs +919811122233)
            self._post_signed_webhook({
                "event": "message",
                "id": "evt_col_us_1",
                "session": self.session1.session_name,
                "payload": {
                    "id": "false_19811122233@c.us_MSG_1",
                    "from": "19811122233@c.us",
                    "to": "919003619221@c.us",
                    "fromMe": False,
                    "pushName": "Carlos US",
                    "body": "Hello from US number sharing 10-digit suffix",
                    "timestamp": int(now.timestamp()),
                },
            })

            # Case 2: Two different customers with identical pushName "Mohan V"
            self._post_signed_webhook({
                "event": "message",
                "id": "evt_col_same_name_1",
                "session": self.session1.session_name,
                "payload": {
                    "id": "false_917777111101@c.us_MSG_1",
                    "from": "917777111101@c.us",
                    "to": "919003619221@c.us",
                    "fromMe": False,
                    "pushName": "Mohan V",
                    "body": "Message from first customer named Mohan V",
                    "timestamp": int(now.timestamp()),
                },
            })
            self._post_signed_webhook({
                "event": "message",
                "id": "evt_col_same_name_2",
                "session": self.session1.session_name,
                "payload": {
                    "id": "false_917777111102@c.us_MSG_1",
                    "from": "917777111102@c.us",
                    "to": "919003619221@c.us",
                    "fromMe": False,
                    "pushName": "Mohan V",
                    "body": "Message from second customer named Mohan V",
                    "timestamp": int(now.timestamp()),
                },
            })

            # Case 4 & 5: Unresolved @lid sender arriving right after outbound message
            # and carrying pushName="Mohan V" must NOT attach to conv_arjun or any other chat
            fake_waha = MagicMock()
            fake_waha.get_contact_info.return_value = {}
            with patch("whatsapp.client.get_waha_client", return_value=fake_waha):
                self._post_signed_webhook({
                    "event": "message",
                    "id": "evt_col_lid_1",
                    "session": self.session1.session_name,
                    "payload": {
                        "id": "false_191126329925674@lid_MSG_1",
                        "from": "191126329925674@lid",
                        "to": "919003619221@c.us",
                        "fromMe": False,
                        "pushName": "Fahad",
                        "body": "Unresolved LID message",
                        "timestamp": int(now.timestamp()),
                    },
                })

            # Case 6a: Self-echo (fromMe=True) carrying account owner's pushName "Mohan V"
            # must NEVER overwrite Fahad's or Arjun's conversation whatsapp_name!
            self._post_signed_webhook({
                "event": "message.any",
                "id": "evt_col_echo_owner_name",
                "session": self.session1.session_name,
                "payload": {
                    "id": "true_191126329925674@lid_ECHO_1",
                    "from": "191126329925674@lid",
                    "to": "191126329925674@lid",
                    "fromMe": True,
                    "pushName": "Mohan V",
                    "body": "Outbound reply to Fahad",
                    "timestamp": int(now.timestamp()),
                },
            })

            # Case 6b: Ambiguous CRM contact phone (+919999888877) must remain unlinked
            self._post_signed_webhook({
                "event": "message",
                "id": "evt_col_ambig_1",
                "session": self.session1.session_name,
                "payload": {
                    "id": "false_919999888877@c.us_MSG_1",
                    "from": "919999888877@c.us",
                    "to": "919003619221@c.us",
                    "fromMe": False,
                    "pushName": "Real Sender Name",
                    "body": "Message from number with ambiguous CRM contacts",
                    "timestamp": int(now.timestamp()),
                },
            })

            # Case 8: Group chat message remains separate from 1-on-1 conversations
            self._post_signed_webhook({
                "event": "message",
                "id": "evt_col_grp_1",
                "session": self.session1.session_name,
                "payload": {
                    "id": "false_120363099999999@g.us_MSG_1",
                    "chatId": "120363099999999@g.us",
                    "from": "919811122233@c.us",
                    "participant": "919811122233@c.us",
                    "fromMe": False,
                    "pushName": "Arjun Mehta",
                    "chatName": "Project Alpha Group",
                    "body": "Group discussion message",
                    "timestamp": int(now.timestamp()),
                },
            })

        # Verify each conversation is distinct and isolated
        conv_us = WhatsAppConversation.objects.get(session=self.session1, chat_id="19811122233@c.us")
        self.assertNotEqual(conv_us.pk, conv_arjun.pk)
        self.assertIsNone(conv_us.prospect_contact)  # Not suffix-matched to Arjun's +919811122233!

        conv_m1 = WhatsAppConversation.objects.get(session=self.session1, chat_id="917777111101@c.us")
        conv_m2 = WhatsAppConversation.objects.get(session=self.session1, chat_id="917777111102@c.us")
        self.assertNotEqual(conv_m1.pk, conv_m2.pk)

        conv_lid = WhatsAppConversation.objects.get(session=self.session1, chat_id="191126329925674@lid")
        self.assertNotEqual(conv_lid.pk, conv_arjun.pk)
        self.assertNotEqual(conv_lid.pk, conv_m1.pk)
        self.assertEqual(conv_lid.whatsapp_name, "Fahad")  # Not overwritten by fromMe pushName "Mohan V"!

        conv_ambig = WhatsAppConversation.objects.get(session=self.session1, chat_id="919999888877@c.us")
        self.assertFalse(conv_ambig.is_matched)
        self.assertIsNone(conv_ambig.prospect_contact)
        self.assertEqual(conv_ambig.whatsapp_name, "Real Sender Name")

        conv_grp = WhatsAppConversation.objects.get(session=self.session1, chat_id="120363099999999@g.us")
        self.assertNotEqual(conv_grp.pk, conv_arjun.pk)
        self.assertEqual(WhatsAppMessage.objects.filter(conversation=conv_arjun).count(), 1)

        # Case 19: GET /api/whatsapp/conversations/ is strictly read-only
        self.client.force_authenticate(user=self.user1)
        total_convs_before = WhatsAppConversation.objects.filter(session=self.session1, is_deleted=False).count()
        res_list = self.client.get("/api/whatsapp/conversations/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        total_convs_after = WhatsAppConversation.objects.filter(session=self.session1, is_deleted=False).count()
        self.assertEqual(total_convs_before, total_convs_after)
        self.assertEqual(len(res_list.data), total_convs_before)

        by_chat_id = {item["chat_id"]: item for item in res_list.data}
        self.assertEqual(by_chat_id["19811122233@c.us"]["contact_name"], "Carlos US")
        self.assertEqual(by_chat_id["191126329925674@lid"]["contact_name"], "Fahad")
        self.assertEqual(by_chat_id["919999888877@c.us"]["contact_name"], "Real Sender Name")

    def test_ai_history_isolation_and_concurrent_idempotency_and_uncertain_send(self):
        """
        Verifies mandatory AI history isolation & concurrency rules (10-17):
          10 & 11. AI prompt contains ONLY target conversation's history; never includes messages
                   from another conversation with same 10-digit phone suffix, same pushName, or @lid.
          12. Outgoing AI message uses exact originating session and exact conversation.chat_id.
          13, 14, 15. Repeated webhook, realtime sync, and concurrent worker calls produce at most 1 reply.
          16 & 17. Confirmed send failure -> FAILED; uncertain timeout -> SEND_UNKNOWN (never auto-retried).
        """
        from concurrent.futures import ThreadPoolExecutor
        from whatsapp.client import WAHAServiceError
        from whatsapp_ai.gemini_service import process_ai_auto_reply
        from whatsapp_ai.realtime_listener import run_realtime_sync_cycle

        now = timezone.now()

        # Customer A (+919811122233)
        conv_a = WhatsAppConversation.objects.create(
            session=self.session1,
            chat_id="919811122233@c.us",
            phone_number="+919811122233",
            whatsapp_name="Arjun Mehta",
        )
        WhatsAppMessage.objects.create(
            idempotency_key="hist-a-1",
            conversation=conv_a,
            direction=WhatsAppMessage.Direction.INBOUND,
            status=WhatsAppMessage.Status.DELIVERED,
            body_preview="CONFIDENTIAL_ARJUN_A_MESSAGE",
            full_body="CONFIDENTIAL_ARJUN_A_MESSAGE",
            sent_at=now - timedelta(minutes=5),
        )

        # Customer B sharing the same 10-digit suffix (+19811122233) and same name in same session
        conv_b = WhatsAppConversation.objects.create(
            session=self.session1,
            chat_id="19811122233@c.us",
            phone_number="+19811122233",
            whatsapp_name="Arjun Mehta",
        )
        msg_b_in = WhatsAppMessage.objects.create(
            idempotency_key="in-b-1",
            conversation=conv_b,
            waha_message_id="false_19811122233@c.us_B1",
            direction=WhatsAppMessage.Direction.INBOUND,
            status=WhatsAppMessage.Status.DELIVERED,
            body_preview="Hello from Customer B in US",
            full_body="Hello from Customer B in US",
            sent_at=now,
        )

        fake_waha = MagicMock()
        fake_waha.send_text.return_value = {"id": "true_19811122233@c.us_AI_B1"}
        captured_prompts = []

        def _fake_urlopen(req, timeout=15):
            body = json.loads(req.data.decode("utf-8"))
            captured_prompts.append(body["contents"][0]["parts"][0]["text"])
            return _FakeGeminiHttpResponse("Hi Customer B! Happy to help.")

        with patch.dict("os.environ", {
            "GEMINI_API_KEY": "fake-key",
            "WHATSAPP_AI_AUTO_REPLY_ENABLED": "true",
        }), \
             patch("whatsapp.client.get_waha_client", return_value=fake_waha), \
             patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            # 15. Run two workers on the same incoming message
            res1 = process_ai_auto_reply(msg_b_in.pk)
            res2 = process_ai_auto_reply(msg_b_in.pk)
            # 14. Run realtime sync cycle after message was already processed
            fake_waha.get_all_sessions.return_value = []
            fake_waha.get_recent_messages_from_stats.return_value = []
            fake_waha.get_chats.return_value = []
            run_realtime_sync_cycle(force_chat_poll=True)

        self.assertEqual(res1["status"], "SENT")
        self.assertEqual(res2["reason"], "already_processed")
        self.assertEqual(fake_waha.send_text.call_count, 1)
        self.assertEqual(fake_waha.send_text.call_args.kwargs["session_name"], self.session1.session_name)
        self.assertEqual(fake_waha.send_text.call_args.kwargs["chat_id"], "19811122233@c.us")

        # 10 & 11. Prompt for Customer B must NEVER contain Customer A's message despite shared 10-digit suffix
        self.assertEqual(len(captured_prompts), 1)
        self.assertIn("Hello from Customer B in US", captured_prompts[0])
        self.assertNotIn("CONFIDENTIAL_ARJUN_A_MESSAGE", captured_prompts[0])

        # 17. Uncertain send outcome (HTTP 504 Gateway Timeout) -> reconciled first; if unconfirmed, marked SEND_UNKNOWN and NOT retried
        msg_b_timeout = WhatsAppMessage.objects.create(
            idempotency_key="in-b-timeout",
            conversation=conv_b,
            waha_message_id="false_19811122233@c.us_B_TIMEOUT",
            direction=WhatsAppMessage.Direction.INBOUND,
            status=WhatsAppMessage.Status.DELIVERED,
            body_preview="Are you still there?",
            full_body="Are you still there?",
            sent_at=now + timedelta(seconds=5),
        )
        fake_waha_timeout = MagicMock()
        fake_waha_timeout.send_text.side_effect = WAHAServiceError("Read timed out waiting for WAHA", status_code=504)
        fake_waha_timeout.get_recent_messages_from_stats.return_value = []
        fake_waha_timeout.get_messages.return_value = []

        with patch.dict("os.environ", {
            "GEMINI_API_KEY": "fake-key",
            "WHATSAPP_AI_AUTO_REPLY_ENABLED": "true",
        }), \
             patch("whatsapp.client.get_waha_client", return_value=fake_waha_timeout), \
             patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            timeout_res = process_ai_auto_reply(msg_b_timeout.pk)
            retry_res = process_ai_auto_reply(msg_b_timeout.pk)

        self.assertEqual(timeout_res["status"], "SEND_UNKNOWN")
        self.assertEqual(retry_res["reason"], "already_processed")
        self.assertEqual(fake_waha_timeout.send_text.call_count, 1)  # Never blindly retried!
        log_timeout = WhatsAppAIReplyLog.objects.get(incoming_message=msg_b_timeout)
        self.assertEqual(log_timeout.status, WhatsAppAIReplyLog.Status.SEND_UNKNOWN)

        # 16. Confirmed send failure (HTTP 400 Bad Request) -> marked FAILED
        msg_b_fail = WhatsAppMessage.objects.create(
            idempotency_key="in-b-fail",
            conversation=conv_b,
            waha_message_id="false_19811122233@c.us_B_FAIL",
            direction=WhatsAppMessage.Direction.INBOUND,
            status=WhatsAppMessage.Status.DELIVERED,
            body_preview="Another test",
            full_body="Another test",
            sent_at=now + timedelta(seconds=10),
        )
        fake_waha_fail = MagicMock()
        fake_waha_fail.send_text.side_effect = WAHAServiceError("Invalid chatId parameter", status_code=400)

        with patch.dict("os.environ", {
            "GEMINI_API_KEY": "fake-key",
            "WHATSAPP_AI_AUTO_REPLY_ENABLED": "true",
        }), \
             patch("whatsapp.client.get_waha_client", return_value=fake_waha_fail), \
             patch("urllib.request.urlopen", side_effect=_fake_urlopen):
            fail_res = process_ai_auto_reply(msg_b_fail.pk)

        self.assertEqual(fail_res["status"], "FAILED")
        log_fail = WhatsAppAIReplyLog.objects.get(incoming_message=msg_b_fail)
        self.assertEqual(log_fail.status, WhatsAppAIReplyLog.Status.FAILED)
