"""
Regression tests for email deliverability:
1. Address formatting: commas, quotes, Unicode, and CRLF injection protection.
2. Singleton headers: exactly one Date, Message-ID, From, Subject, Reply-To.
3. Inbox Date omission fix: Inbox send now includes RFC 5322 Date and formataddr.
4. Draft composition: includes Date, formataddr, and sender-domain Message-ID.
5. Tracking markup: 1x1 minimal pixel, no "Verified Communication" badge, no fake checkmark.
6. Stale tracking cleanup: templates/signatures with legacy tracking blocks are cleaned.
7. Tracking configuration validation: invalid public config blocks tracked send with 400,
   while untracked send continues to function.
8. Click endpoint security: open redirect protection against unknown/untracked tokens
   and malicious schemes.
"""
import email as email_pkg
import json
import shutil
import tempfile
import urllib.parse
from email import policy
from unittest import mock

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings, TestCase
from rest_framework.test import APITestCase

from accounts.models import EmailSignatureTemplate, EmailTemplate, GoogleMailCredentials
from accounts.oauth_services import GmailOAuthService
from prospects.models import EmailAttachment, OutreachEmail, Prospect, ProspectContact
from prospects.email_composition import (
    format_sender_address,
    validate_and_sanitize_recipient,
    set_singleton_header,
    extract_domain_from_email,
)
from prospects.tracking_utils import (
    validate_tracking_configuration,
    build_tracking_pixel_html,
    strip_application_tracking_markup,
)

MEDIA = tempfile.mkdtemp(prefix='mi-deliv-test-media-')


class _SyncThread:
    def __init__(self, target=None, *a, **k):
        self._target = target

    def start(self):
        self._target()


def _parse_mime(raw_bytes):
    return email_pkg.message_from_bytes(raw_bytes, policy=policy.default)


class AddressAndHeaderUnitTests(TestCase):
    def test_format_sender_address_with_comma_in_name(self):
        # Without quotes, "Doe, Jane <jane@acme.com>" parses as two addresses: "Doe" and "Jane <jane@acme.com>"
        formatted = format_sender_address("Doe, Jane", "jane@acme.com")
        self.assertEqual(formatted, '"Doe, Jane" <jane@acme.com>')
        parsed = email_pkg.utils.getaddresses([formatted])
        self.assertEqual(parsed, [('Doe, Jane', 'jane@acme.com')])

    def test_format_sender_address_with_quotes_in_name(self):
        formatted = format_sender_address('Jane "The Boss" Doe', "jane@acme.com")
        parsed = email_pkg.utils.getaddresses([formatted])
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0][1], "jane@acme.com")

    def test_format_sender_address_unicode_name(self):
        formatted = format_sender_address("René Dupont", "rene@acme.com")
        parsed = email_pkg.utils.getaddresses([formatted])
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0][1], "rene@acme.com")

    def test_format_sender_address_sanitizes_crlf_injection(self):
        formatted = format_sender_address("Jane\r\nBcc: evil@phish.com", "jane@acme.com")
        self.assertNotIn('\r', formatted)
        self.assertNotIn('\n', formatted)
        parsed = email_pkg.utils.getaddresses([formatted])
        self.assertEqual(len(parsed), 1)
        self.assertEqual(parsed[0][1], "jane@acme.com")

    def test_format_sender_address_empty_display_name(self):
        formatted = format_sender_address("", "jane@acme.com")
        self.assertEqual(formatted, "jane@acme.com")

    def test_format_sender_address_rejects_malformed_email(self):
        with self.assertRaises(ValueError):
            format_sender_address("Jane", "jane @acme.com")
        with self.assertRaises(ValueError):
            format_sender_address("Jane", "jane\r\n@acme.com")
        with self.assertRaises(ValueError):
            format_sender_address("Jane", "")

    def test_validate_and_sanitize_recipient(self):
        self.assertEqual(validate_and_sanitize_recipient("  user@example.com  "), "user@example.com")
        with self.assertRaises(ValueError):
            validate_and_sanitize_recipient("user@example.com\r\nBcc: bad@phish.com")
        with self.assertRaises(ValueError):
            validate_and_sanitize_recipient("not-an-email")
        with self.assertRaises(ValueError):
            validate_and_sanitize_recipient("@nodomain.com")
        with self.assertRaises(ValueError):
            validate_and_sanitize_recipient("user@")
        with self.assertRaises(ValueError):
            validate_and_sanitize_recipient("user @example.com")

    def test_singleton_header_replaces_cleanly(self):
        msg = email_pkg.message.EmailMessage()
        set_singleton_header(msg, 'Subject', 'Subject 1')
        set_singleton_header(msg, 'Subject', 'Subject 2')
        self.assertEqual(msg.get_all('Subject'), ['Subject 2'])


class TrackingConfigValidationTests(TestCase):
    def test_valid_https_url_passes(self):
        valid, msg = validate_tracking_configuration("https://tracking.example.com")
        self.assertTrue(valid, msg)

    @override_settings(DEBUG=False, EMAIL_TRACKING_ALLOW_LOCAL=False)
    def test_http_url_fails_in_production(self):
        valid, msg = validate_tracking_configuration("http://tracking.example.com")
        self.assertFalse(valid)
        self.assertIn("HTTPS", msg)

    @override_settings(DEBUG=False, EMAIL_TRACKING_ALLOW_LOCAL=False)
    def test_localhost_fails_in_production(self):
        valid_https, msg_https = validate_tracking_configuration("https://localhost:8000")
        self.assertFalse(valid_https)
        self.assertIn("loopback", msg_https.lower())

        valid_http, msg_http = validate_tracking_configuration("http://localhost:8000")
        self.assertFalse(valid_http)
        self.assertIn("https", msg_http.lower())

    @override_settings(DEBUG=False, EMAIL_TRACKING_ALLOW_LOCAL=False)
    def test_private_ip_fails_in_production(self):
        valid, msg = validate_tracking_configuration("https://192.168.1.100")
        self.assertFalse(valid)
        self.assertIn("private", msg.lower())

    @override_settings(DEBUG=False, EMAIL_TRACKING_ALLOW_LOCAL=False)
    def test_temporary_tunnel_fails_in_production(self):
        valid, msg = validate_tracking_configuration("https://random-words.trycloudflare.com")
        self.assertFalse(valid)
        self.assertIn("temporary tunnel", msg.lower())

    def test_url_with_credentials_fails(self):
        valid, msg = validate_tracking_configuration("https://user:pass@tracking.example.com")
        self.assertFalse(valid)
        self.assertIn("credentials", msg.lower())

    def test_url_with_query_fails(self):
        valid, msg = validate_tracking_configuration("https://tracking.example.com?foo=bar")
        self.assertFalse(valid)
        self.assertIn("query", msg.lower())

    @override_settings(DEBUG=True)
    def test_localhost_allowed_in_debug_mode(self):
        valid, msg = validate_tracking_configuration("http://localhost:8000")
        self.assertTrue(valid, msg)


class StaleTrackingCleanupTests(TestCase):
    def test_strip_legacy_verified_communication_badge(self):
        legacy_html = (
            '<p>Hello world</p>'
            '<div style="margin-top:12px;padding-top:8px;border-top:1px solid #e2e8f0;display:inline-block;'
            'font-family:sans-serif;font-size:11px;color:#94a3b8;line-height:16px;">'
            '<img src="http://localhost:8000/api/email-tracking/00000000-0000-0000-0000-000000000000/" '
            'width="16" height="16" alt="✓" style="display:inline-block;" />'
            '<span style="color:#64748b;">Verified Communication</span>'
            '</div>'
        )
        cleaned = strip_application_tracking_markup(legacy_html)
        self.assertNotIn('Verified Communication', cleaned)
        self.assertNotIn('/api/email-tracking/', cleaned)
        self.assertNotIn('✓', cleaned)
        self.assertIn('<p>Hello world</p>', cleaned)

    def test_strip_preserves_customer_images(self):
        html_with_customer_img = (
            '<p>Hi</p>'
            '<img src="cid:company-logo@domain" alt="Logo" />'
            '<img src="https://example.com/banner.png" alt="Banner" />'
            '<img src="https://track.example.com/api/email-tracking/11111111-1111-1111-1111-111111111111/" />'
        )
        cleaned = strip_application_tracking_markup(html_with_customer_img)
        self.assertIn('cid:company-logo@domain', cleaned)
        self.assertIn('https://example.com/banner.png', cleaned)
        self.assertNotIn('/api/email-tracking/', cleaned)


@override_settings(MEDIA_ROOT=MEDIA, EMAIL_OPEN_TRACKING_ENABLED=True, EMAIL_TRACKING_BASE_URL='https://t.example')
@mock.patch('threading.Thread', _SyncThread)
class EmailDeliverabilityIntegrationTests(APITestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        self.user = User.objects.create_user(
            username='sender@example.com',
            email='sender@example.com',
            first_name='Jane',
            last_name='Doe',
            password='pw12345!'
        )
        self.user.profile.role = 'LQ'
        self.user.profile.save()

        import utils.encryption as encryption
        import os
        if not os.environ.get('MAIL_CREDENTIALS_ENCRYPTION_KEY'):
            os.environ['MAIL_CREDENTIALS_ENCRYPTION_KEY'] = encryption.Fernet.generate_key().decode('utf-8')

        GoogleMailCredentials.objects.create(
            user=self.user,
            email=self.user.email,
            access_token_encrypted=encryption.encrypt_password('token-xyz'),
            is_active=True
        )

        self.prospect = Prospect.objects.create(
            company_name='Deliverability Test Corp',
            country_head_office='IN',
            primary_industries='IT',
            company_structure='Parent',
            operational_status='Active',
            primary_offering_type='Products',
            official_website_url='https://deliverability.test'
        )
        self.contact = ProspectContact.objects.create(
            prospect=self.prospect,
            contact_name='Target Recipient',
            designation='VP',
            official_email='target@deliverability.test'
        )
        self.client.force_authenticate(user=self.user)

    def _send_outreach(self, **extra):
        from django.core.serializers.json import DjangoJSONEncoder
        recipients = [{'email_address': 'target@deliverability.test', 'recipient_type': 'TO',
                       'prospect_contact': str(self.contact.id)}]
        data = {
            'prospect': str(self.prospect.id),
            'subject': 'Deliverability Outreach',
            'body': 'Checking headers and formatting.',
            'recipients': json.dumps(recipients, cls=DjangoJSONEncoder)
        }
        data.update(extra)
        with mock.patch.object(GmailOAuthService, 'send_message', return_value={'id': 'msg_outreach', 'threadId': 'th_1'}) as send:
            r = self.client.post('/api/outreach/emails/', data, format='multipart')
        return r, send

    def _send_inbox(self, **extra):
        data = {
            'to': 'target@deliverability.test',
            'subject': 'Inbox Test',
            'body': 'Testing inbox composition headers.'
        }
        data.update(extra)
        with mock.patch.object(GmailOAuthService, 'send_message', return_value={'id': 'msg_inbox'}) as send:
            r = self.client.post('/api/auth/mail-account/send-email/', data, format='multipart')
        return r, send

    # ── 1. OUTREACH DELIVERABILITY TESTS ─────────────────────────────────────

    def test_outreach_from_with_comma_name_is_quoted(self):
        # Update user's name to contain a comma
        self.user.first_name = "Doe,"
        self.user.last_name = "Jane"
        self.user.save()

        r, send = self._send_outreach()
        self.assertEqual(r.status_code, 201, r.data)
        raw_mime = send.call_args[0][1]
        msg = _parse_mime(raw_mime)

        from_header = msg['From']
        self.assertEqual(from_header, '"Doe, Jane" <sender@example.com>')
        parsed = email_pkg.utils.getaddresses([from_header])
        self.assertEqual(parsed, [('Doe, Jane', 'sender@example.com')])

    def test_outreach_singleton_headers_and_date(self):
        r, send = self._send_outreach()
        self.assertEqual(r.status_code, 201)
        raw_mime = send.call_args[0][1]
        msg = _parse_mime(raw_mime)

        # Date header must be present and unique
        self.assertEqual(len(msg.get_all('Date')), 1)
        self.assertTrue(msg['Date'])

        # Message-ID must be present, unique, and contain sender domain
        self.assertEqual(len(msg.get_all('Message-ID')), 1)
        self.assertIn('@example.com>', msg['Message-ID'])

        # From must be unique
        self.assertEqual(len(msg.get_all('From')), 1)

        # Subject must be unique
        self.assertEqual(len(msg.get_all('Subject')), 1)

    def test_outreach_untracked_has_no_tracking_pixel_or_verified_badge(self):
        r, send = self._send_outreach(open_tracking_enabled='false')
        self.assertEqual(r.status_code, 201)
        html_content = _parse_mime(send.call_args[0][1]).get_body(('html',)).get_content()

        self.assertNotIn('/api/email-tracking/', html_content)
        self.assertNotIn('Verified Communication', html_content)
        self.assertNotIn('✓', html_content)

    def test_outreach_tracked_has_minimal_pixel_without_verified_badge(self):
        r, send = self._send_outreach(open_tracking_enabled='true')
        self.assertEqual(r.status_code, 201)
        html_content = _parse_mime(send.call_args[0][1]).get_body(('html',)).get_content()

        oe = OutreachEmail.objects.get(pk=r.data['id'])
        self.assertIn(f'https://t.example/api/email-tracking/{oe.tracking_token}/', html_content)
        # Verify no fake verification badge or checkmark
        self.assertNotIn('Verified Communication', html_content)
        self.assertNotIn('✓', html_content)
        # Verify pixel has 1x1 dimensions
        self.assertIn('width="1" height="1"', html_content)

    def test_outreach_stale_tracking_badge_in_signature_is_stripped(self):
        stale_sig = EmailSignatureTemplate.objects.create(
            owner=self.user,
            name='Stale Sig',
            html=(
                '<div>Best regards</div>'
                '<div style="border-top:1px solid #ccc;">'
                '<img src="http://localhost:8000/api/email-tracking/00000000-0000-0000-0000-000000000000/" width="16" height="16" alt="✓" />'
                '<span>Verified Communication</span>'
                '</div>'
            )
        )
        r, send = self._send_outreach(signature_id=str(stale_sig.id), open_tracking_enabled='false')
        self.assertEqual(r.status_code, 201)
        html_content = _parse_mime(send.call_args[0][1]).get_body(('html',)).get_content()

        self.assertNotIn('Verified Communication', html_content)
        self.assertNotIn('/api/email-tracking/', html_content)
        self.assertIn('Best regards', html_content)

    @override_settings(DEBUG=False, EMAIL_TRACKING_ALLOW_LOCAL=False, EMAIL_TRACKING_BASE_URL='http://localhost:8000')
    def test_outreach_rejects_tracked_send_when_config_invalid(self):
        r, send = self._send_outreach(open_tracking_enabled='true')
        self.assertEqual(r.status_code, 400)
        self.assertIn('EMAIL_TRACKING_BASE_URL', r.data['error'])
        send.assert_not_called()

    @override_settings(DEBUG=False, EMAIL_TRACKING_ALLOW_LOCAL=False, EMAIL_TRACKING_BASE_URL='http://localhost:8000')
    def test_outreach_allows_untracked_send_when_config_invalid(self):
        r, send = self._send_outreach(open_tracking_enabled='false')
        self.assertEqual(r.status_code, 201)
        send.assert_called_once()

    def test_outreach_rejects_malformed_recipient(self):
        recipients = [{'email_address': 'bad-recipient @example.com', 'recipient_type': 'TO'}]
        data = {
            'prospect': str(self.prospect.id),
            'subject': 'Bad recipient',
            'body': 'Body',
            'recipients': json.dumps(recipients)
        }
        r = self.client.post('/api/outreach/emails/', data, format='multipart')
        self.assertEqual(r.status_code, 400)
        self.assertIn('Invalid recipient', r.data['error'])

    # ── 2. INBOX DELIVERABILITY TESTS ────────────────────────────────────────

    def test_inbox_send_includes_date_and_formataddr(self):
        r, send = self._send_inbox()
        self.assertEqual(r.status_code, 200)
        raw_mime = send.call_args[0][1]
        msg = _parse_mime(raw_mime)

        # Date header must be present (fixes previous omission!)
        self.assertEqual(len(msg.get_all('Date')), 1)
        self.assertTrue(msg['Date'])

        # From header must be formatted
        self.assertEqual(len(msg.get_all('From')), 1)
        self.assertEqual(msg['From'], 'Jane Doe <sender@example.com>')

        # Message-ID must be present and contain sender domain
        self.assertEqual(len(msg.get_all('Message-ID')), 1)
        self.assertIn('@example.com>', msg['Message-ID'])

    def test_inbox_send_rejects_malformed_to_address(self):
        r, send = self._send_inbox(to='invalid-email\r\nBcc: evil@phish.com')
        self.assertEqual(r.status_code, 400)
        self.assertIn('Invalid recipient', r.data['error'])
        send.assert_not_called()

    @override_settings(DEBUG=False, EMAIL_TRACKING_ALLOW_LOCAL=False, EMAIL_TRACKING_BASE_URL='http://localhost:8000')
    def test_inbox_rejects_tracked_send_when_config_invalid(self):
        r, send = self._send_inbox(open_tracking_enabled='true')
        self.assertEqual(r.status_code, 400)
        self.assertIn('EMAIL_TRACKING_BASE_URL', r.data['error'])
        send.assert_not_called()

    # ── 3. DRAFT CREATION TESTS ──────────────────────────────────────────────

    def test_save_draft_includes_date_and_sender_domain(self):
        with mock.patch.object(GmailOAuthService, 'save_draft', return_value={'id': 'draft_1'}) as save:
            r = self.client.post('/api/auth/mail-account/save-draft/', {
                'to': 'draft-target@example.com',
                'subject': 'Draft Subj',
                'body': 'Draft body'
            })
        self.assertEqual(r.status_code, 200)
        raw_mime = save.call_args[0][1]
        msg = _parse_mime(raw_mime)

        # Draft must contain Date header
        self.assertTrue(msg['Date'])
        # Message-ID must contain sender domain, not hardcoded gmail.com
        self.assertIn('@example.com>', msg['Message-ID'])
        # From must be formatted
        self.assertEqual(msg['From'], 'Jane Doe <sender@example.com>')

    # ── 4. CLICK TRACKING SECURITY TESTS ─────────────────────────────────────

    def test_click_tracking_rejects_unknown_uuid(self):
        import uuid
        unknown_token = uuid.uuid4()
        r = self.client.get(f'/api/email-tracking/click/{unknown_token}/?url=https://phishing.example.com')
        self.assertEqual(r.status_code, 400)

    def test_click_tracking_rejects_untracked_email(self):
        oe = OutreachEmail.objects.create(
            prospect=self.prospect,
            created_by=self.user,
            from_email='sender@example.com',
            subject='Untracked',
            open_tracking_enabled=False
        )
        r = self.client.get(f'/api/email-tracking/click/{oe.tracking_token}/?url=https://example.com')
        self.assertEqual(r.status_code, 400)

    def test_click_tracking_rejects_unsafe_schemes(self):
        oe = OutreachEmail.objects.create(
            prospect=self.prospect,
            created_by=self.user,
            from_email='sender@example.com',
            subject='Tracked',
            open_tracking_enabled=True
        )
        # JavaScript scheme
        r1 = self.client.get(f'/api/email-tracking/click/{oe.tracking_token}/?url=javascript:alert(1)')
        self.assertEqual(r1.status_code, 400)

        # Protocol-relative URL
        r2 = self.client.get(f'/api/email-tracking/click/{oe.tracking_token}/?url=//evil.example.com')
        self.assertEqual(r2.status_code, 400)

        # CRLF injection
        r3 = self.client.get(f'/api/email-tracking/click/{oe.tracking_token}/?url=https://example.com\r\nSet-Cookie:bad')
        self.assertEqual(r3.status_code, 400)

    def test_click_tracking_redirects_valid_tracked_email(self):
        oe = OutreachEmail.objects.create(
            prospect=self.prospect,
            created_by=self.user,
            from_email='sender@example.com',
            subject='Tracked',
            open_tracking_enabled=True
        )
        r = self.client.get(f'/api/email-tracking/click/{oe.tracking_token}/?url=https://legitimate.example.com/info')
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r['Location'], 'https://legitimate.example.com/info')
        oe.refresh_from_db()
        self.assertTrue(oe.is_opened)
        self.assertEqual(len(oe.open_history), 1)
        self.assertEqual(oe.open_history[0]['type'], 'CLICK')
