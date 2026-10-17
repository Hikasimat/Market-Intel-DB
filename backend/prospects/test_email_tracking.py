"""Regression tests: open-tracking is opt-in per email, gated by the global setting,
and never alters the rest of the send pipeline. No real email is ever sent."""
import email as email_pkg
import json
import shutil
import tempfile
from email import policy
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.apps import apps as django_apps
from rest_framework.test import APITestCase

from accounts.models import EmailSignatureTemplate, EmailTemplate, GoogleMailCredentials
from accounts.oauth_services import GmailOAuthService
from prospects.models import EmailAttachment, OutreachEmail, Prospect, ProspectContact
from prospects.tracking_utils import parse_bool, resolve_open_tracking

B64_PNG = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9a"
           "wAAAABJRU5ErkJggg==")
PIXEL_MARKER = '/api/email-tracking/'
MEDIA = tempfile.mkdtemp(prefix='mi-test-media-')


def _user(name, role):
    u = User.objects.create_user(username=f'{name}@example.com', email=f'{name}@example.com', password='pw12345!')
    u.profile.role = role
    u.profile.save()
    return u


class _SyncThread:
    def __init__(self, target=None, *a, **k):
        self._target = target

    def start(self):
        self._target()


def _parse(raw_bytes):
    return email_pkg.message_from_bytes(raw_bytes, policy=policy.default)


class TrackingResolverTests(APITestCase):
    def test_parse_bool_defaults_safe(self):
        self.assertFalse(parse_bool(None))
        self.assertFalse(parse_bool(''))
        self.assertFalse(parse_bool('false'))
        self.assertFalse(parse_bool('garbage'))
        self.assertTrue(parse_bool('true'))
        self.assertTrue(parse_bool(True))

    @override_settings(EMAIL_OPEN_TRACKING_ENABLED=True)
    def test_global_on_requires_explicit_request(self):
        self.assertFalse(resolve_open_tracking(None))
        self.assertTrue(resolve_open_tracking('true'))

    @override_settings(EMAIL_OPEN_TRACKING_ENABLED=False)
    def test_global_off_overrides_request(self):
        self.assertFalse(resolve_open_tracking('true'))
        self.assertFalse(resolve_open_tracking(True))


@override_settings(MEDIA_ROOT=MEDIA, EMAIL_OPEN_TRACKING_ENABLED=True, EMAIL_TRACKING_BASE_URL='https://t.example')
@mock.patch('threading.Thread', _SyncThread)
class EmailTrackingSendTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.lq = _user('lqt', 'LQ')
        self.other = _user('lqother', 'LQ')
        import utils.encryption as encryption
        import os
        if not os.environ.get('MAIL_CREDENTIALS_ENCRYPTION_KEY'):
            os.environ['MAIL_CREDENTIALS_ENCRYPTION_KEY'] = encryption.Fernet.generate_key().decode('utf-8')
        GoogleMailCredentials.objects.create(
            user=self.lq, email=self.lq.email, access_token_encrypted=encryption.encrypt_password('x'), is_active=True)
        self.prospect = Prospect.objects.create(
            company_name='Acme Corp', country_head_office='IN', primary_industries='IT',
            company_structure='Parent', operational_status='Active', primary_offering_type='Products',
            official_website_url='https://acme.test')
        self.contact = ProspectContact.objects.create(
            prospect=self.prospect, contact_name='Jane Doe', designation='CTO', official_email='jane@acme.test')
        self.client.force_authenticate(user=self.lq)

    # ── helpers ──────────────────────────────────────────────────────────────
    def _lq_send(self, files=None, recipients=None, **extra):
        from django.core.serializers.json import DjangoJSONEncoder
        recipients = recipients or [{'email_address': 'jane@acme.test', 'recipient_type': 'TO',
                                     'prospect_contact': str(self.contact.id)}]
        data = {'prospect': str(self.prospect.id), 'subject': 'Subj', 'body': 'Plain body',
                'recipients': json.dumps(recipients, cls=DjangoJSONEncoder)}
        data.update(extra)
        if files:
            data['attachments'] = files
        with mock.patch.object(GmailOAuthService, 'send_message', return_value={'id': 'g1', 'threadId': 'th1'}) as send:
            r = self.client.post('/api/outreach/emails/', data, format='multipart')
        return r, send

    def _inbox_send(self, **extra):
        data = {'to': 'prospect@clientcorp.com', 'subject': 'Hi', 'body': 'Plain body'}
        data.update(extra)
        with mock.patch.object(GmailOAuthService, 'send_message', return_value={'id': 's1'}) as send:
            r = self.client.post('/api/auth/mail-account/send-email/', data, format='multipart')
        return r, send

    @staticmethod
    def _msg(send):
        return _parse(send.call_args[0][1])

    @staticmethod
    def _html(msg):
        return msg.get_body(('html',)).get_content()

    # ── 1 / 10  LQ path defaults ────────────────────────────────────────────
    def test_lq_default_has_no_pixel_and_is_untracked(self):
        r, send = self._lq_send()  # preference omitted entirely
        self.assertEqual(r.status_code, 201, r.data)
        msg = self._msg(send)
        self.assertNotIn(PIXEL_MARKER, self._html(msg))
        self.assertFalse(r.data['open_tracking_enabled'])
        self.assertFalse(OutreachEmail.objects.get(pk=r.data['id']).open_tracking_enabled)
        self.assertEqual(r.data['reading_engagement'], 'Open tracking disabled')

    def test_lq_explicit_false_string_has_no_pixel(self):
        r, send = self._lq_send(open_tracking_enabled='false')
        self.assertNotIn(PIXEL_MARKER, self._html(self._msg(send)))

    # ── 3  explicit opt-in ──────────────────────────────────────────────────
    def test_lq_opt_in_includes_pixel_and_persists_state(self):
        r, send = self._lq_send(open_tracking_enabled='true')
        self.assertEqual(r.status_code, 201, r.data)
        oe = OutreachEmail.objects.get(pk=r.data['id'])
        self.assertTrue(oe.open_tracking_enabled)
        self.assertIn(f'https://t.example/api/email-tracking/{oe.tracking_token}/', self._html(self._msg(send)))

    # ── 4  global override ──────────────────────────────────────────────────
    @override_settings(EMAIL_OPEN_TRACKING_ENABLED=False)
    def test_global_off_beats_client_opt_in_lq(self):
        r, send = self._lq_send(open_tracking_enabled='true')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertNotIn(PIXEL_MARKER, self._html(self._msg(send)))
        self.assertFalse(OutreachEmail.objects.get(pk=r.data['id']).open_tracking_enabled)

    # ── 2  inbox path ───────────────────────────────────────────────────────
    def test_inbox_default_has_no_pixel(self):
        r, send = self._inbox_send()
        self.assertEqual(r.status_code, 200, r.data)
        self.assertNotIn(PIXEL_MARKER, self._html(self._msg(send)))
        self.assertFalse(r.data['open_tracking_enabled'])
        self.assertFalse(OutreachEmail.objects.get(pk=r.data['tracking_id']).open_tracking_enabled)

    def test_inbox_opt_in_has_pixel(self):
        r, send = self._inbox_send(open_tracking_enabled='true')
        self.assertTrue(r.data['open_tracking_enabled'])
        self.assertIn(f"/api/email-tracking/{r.data['tracking_token']}/", self._html(self._msg(send)))

    @override_settings(EMAIL_OPEN_TRACKING_ENABLED=False)
    def test_global_off_beats_client_opt_in_inbox(self):
        r, send = self._inbox_send(open_tracking_enabled='true')
        self.assertNotIn(PIXEL_MARKER, self._html(self._msg(send)))
        self.assertFalse(r.data['open_tracking_enabled'])

    # ── 5 / 6 / 7  rest of the pipeline untouched when tracking is off ─────
    def test_template_signature_inline_image_plaintext_and_headers_preserved(self):
        tpl = EmailTemplate.objects.create(
            owner=self.lq, name='T', subject='Intro to {{company_name}}',
            html=f'<p>Hello {{{{contact_name}}}}</p><img id="i" src="{B64_PNG}">')
        sig = EmailSignatureTemplate.objects.create(owner=self.lq, name='S', html='<b>{{sender_name}}</b> | {{sender_email}}')
        r, send = self._lq_send(template_id=str(tpl.id), signature_id=str(sig.id), body_edited='false', subject='')
        self.assertEqual(r.status_code, 201, r.data)
        msg = self._msg(send)
        html = self._html(msg)
        self.assertIn('Hello Jane Doe', html)
        self.assertNotIn('data:image/png;base64', html)
        self.assertIn('src="cid:', html)  # inline image still converted to CID
        self.assertNotIn(PIXEL_MARKER, html)
        self.assertEqual(msg['Subject'], 'Intro to Acme Corp')
        self.assertEqual(len([p for p in msg.walk() if p.get_content_maintype() == 'image']), 1)
        self.assertTrue(msg.get_body(('plain',)).get_content().strip())  # plain-text alternative kept
        self.assertTrue(msg['Message-ID'])

    def test_recipients_attachments_persistence_and_status_preserved(self):
        recipients = [
            {'email_address': 'jane@acme.test', 'recipient_type': 'TO', 'prospect_contact': self.contact.id},
            {'email_address': 'cc@acme.test', 'recipient_type': 'CC'},
            {'email_address': 'bcc@acme.test', 'recipient_type': 'BCC'},
        ]
        upload = SimpleUploadedFile('brief.txt', b'hello', content_type='text/plain')
        r, send = self._lq_send(files=upload, recipients=recipients)
        self.assertEqual(r.status_code, 201, r.data)
        send.assert_called_once()
        msg = self._msg(send)
        self.assertEqual(msg['To'], 'jane@acme.test')
        self.assertEqual(msg['Cc'], 'cc@acme.test')
        self.assertEqual(msg['Bcc'], 'bcc@acme.test')
        self.assertEqual([p.get_filename() for p in msg.iter_attachments()], ['brief.txt'])
        oe = OutreachEmail.objects.get(pk=r.data['id'])
        self.assertEqual(oe.recipients.count(), 3)
        self.assertEqual(EmailAttachment.objects.filter(outreach_email=oe).count(), 1)
        self.assertEqual(oe.thread_id, 'th1')  # Gmail thread id still captured
        self.assertEqual(oe.status, 'WAITING FOR RESPONSE')
        self.assertEqual(oe.prospect.lead_qualification.email_status if hasattr(self.prospect, 'lead_qualification') else 'Waiting for Response', 'Waiting for Response')

    def test_foreign_template_still_rejected(self):
        foreign = EmailTemplate.objects.create(owner=self.other, name='F', html='<p>secret</p>')
        r, send = self._lq_send(template_id=str(foreign.id))
        self.assertEqual(r.status_code, 400)
        send.assert_not_called()

    def test_non_lq_still_cannot_send(self):
        self.client.force_authenticate(user=_user('prex', 'PRE'))
        r, _ = self._lq_send()
        self.assertEqual(r.status_code, 403)


@override_settings(EMAIL_OPEN_TRACKING_ENABLED=True)
class TrackingEndpointTests(APITestCase):
    """Pixel endpoint + analytics: tracked emails keep working, untracked never record opens."""

    def setUp(self):
        self.lq = _user('lqe', 'LQ')
        self.prospect = Prospect.objects.create(
            company_name='Beta', country_head_office='IN', primary_industries='IT',
            company_structure='Parent', operational_status='Active', primary_offering_type='Products',
            official_website_url='https://beta.test')

    def _email(self, tracked):
        return OutreachEmail.objects.create(
            prospect=self.prospect, created_by=self.lq, from_email='a@b.c', subject='s',
            open_tracking_enabled=tracked, references='sender_ip:10.0.0.1')

    def _hit(self, oe):
        return self.client.get(f'/api/email-tracking/{oe.tracking_token}/', REMOTE_ADDR='203.0.113.9',
                               HTTP_USER_AGENT='Mozilla/5.0 Outlook')

    def test_tracked_email_records_open(self):
        oe = self._email(True)
        r = self._hit(oe)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r['Content-Type'], 'image/gif')
        oe.refresh_from_db()
        self.assertEqual(oe.open_count, 1)
        self.assertTrue(oe.is_opened)

    def test_untracked_email_never_accumulates_opens(self):
        oe = self._email(False)
        for _ in range(3):
            self.assertEqual(self._hit(oe).status_code, 200)  # still returns a harmless GIF
        oe.refresh_from_db()
        self.assertEqual(oe.open_count, 0)
        self.assertFalse(oe.is_opened)
        self.assertEqual(oe.open_history, [])

    def test_untracked_click_not_recorded(self):
        oe = self._email(False)
        self.client.get(f'/api/email-tracking/click/{oe.tracking_token}/?url=/x')
        oe.refresh_from_db()
        self.assertEqual(oe.open_history, [])

    def test_simulate_open_rejected_for_untracked(self):
        self.client.force_authenticate(user=self.lq)
        oe = self._email(False)
        r = self.client.post(f'/api/outreach/emails/{oe.id}/simulate-open/')
        self.assertEqual(r.status_code, 400)
        oe.refresh_from_db()
        self.assertEqual(oe.open_count, 0)

    def test_tracked_stats_and_untracked_status_via_api(self):
        self.client.force_authenticate(user=self.lq)
        tracked, untracked = self._email(True), self._email(False)
        self._hit(tracked)
        t = self.client.get(f'/api/outreach/emails/{tracked.id}/tracking-stats/').data
        self.assertEqual(t['open_count'], 1)
        self.assertTrue(t['open_tracking_enabled'])
        self.assertNotEqual(t['reading_engagement'], 'Open tracking disabled')
        u = self.client.get(f'/api/outreach/emails/{untracked.id}/tracking-stats/').data
        self.assertFalse(u['open_tracking_enabled'])
        self.assertEqual(u['reading_engagement'], 'Open tracking disabled')
        self.assertEqual(self.client.get(
            f'/api/outreach/emails/by-token/?token={tracked.tracking_token}').status_code, 200)

    def test_legacy_backfill_marks_existing_emails_tracked(self):
        legacy = self._email(False)  # simulates a pre-migration row (column default False)
        import importlib
        mig = importlib.import_module('prospects.migrations.0042_backfill_legacy_open_tracking')
        mig.backfill_legacy_tracking(django_apps, None)
        legacy.refresh_from_db()
        self.assertTrue(legacy.open_tracking_enabled)
