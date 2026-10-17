from unittest import mock

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounts.models import MailAccount, EmailTemplate, EmailSignatureTemplate
from accounts.template_utils import sanitize_email_html, render_placeholders
from prospects.models import Prospect, ProspectContact, OutreachEmail


def _user(name, role):
    u = User.objects.create_user(username=f'{name}@example.com', email=f'{name}@example.com', password='pw12345!')
    u.profile.role = role
    u.profile.save()
    return u


class _SyncThread:
    """Runs the background SMTP target inline so SMTP can be asserted on."""
    def __init__(self, target=None, *a, **k):
        self._target = target

    def start(self):
        self._target()


class EmailTemplateApiTests(APITestCase):
    def setUp(self):
        self.lq1 = _user('lq1', 'LQ')
        self.lq2 = _user('lq2', 'LQ')
        self.pre = _user('pre', 'PRE')
        self.mgr = _user('mgr', 'MANAGER')
        self.url = '/api/auth/email-templates/'
        self.sig_url = '/api/auth/email-signatures/'

    def _create(self, user, name='T1', **extra):
        self.client.force_authenticate(user=user)
        payload = {'name': name, 'html': '<p>Hello {{contact_name}}</p>', 'project_data': {'pages': []}}
        payload.update(extra)
        return self.client.post(self.url, payload, format='json')

    def test_unauthenticated_denied(self):
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(self.client.get(self.sig_url).status_code, 401)

    def test_non_lq_roles_denied(self):
        # PRE role is strictly denied
        self.client.force_authenticate(user=self.pre)
        for url in (self.url, self.sig_url):
            self.assertEqual(self.client.get(url).status_code, 403)
            self.assertEqual(self.client.post(url, {'name': 'x'}, format='json').status_code, 403)

        # Manager role has access
        self.client.force_authenticate(user=self.mgr)
        for url in (self.url, self.sig_url):
            self.assertEqual(self.client.get(url).status_code, 200)

    def test_lq_crud_and_owner_forced(self):
        r = self._create(self.lq1, owner=self.lq2.id)
        self.assertEqual(r.status_code, 201, r.data)
        obj = EmailTemplate.objects.get(pk=r.data['id'])
        self.assertEqual(obj.owner, self.lq1)
        tid = r.data['id']
        r = self.client.patch(f'{self.url}{tid}/', {'name': 'Renamed'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['name'], 'Renamed')
        self.assertEqual(self.client.delete(f'{self.url}{tid}/').status_code, 204)
        self.assertFalse(EmailTemplate.objects.filter(pk=tid).exists())

    def test_name_required(self):
        self.assertEqual(self._create(self.lq1, name='  ').status_code, 400)

    def test_isolation_between_lq_users(self):
        tid = self._create(self.lq1).data['id']
        self.client.force_authenticate(user=self.lq2)
        self.assertEqual(self.client.get(f'{self.url}{tid}/').status_code, 404)
        self.assertEqual(self.client.patch(f'{self.url}{tid}/', {'name': 'x'}, format='json').status_code, 404)
        self.assertEqual(self.client.delete(f'{self.url}{tid}/').status_code, 404)
        self.assertEqual(self.client.post(f'{self.url}{tid}/set-default/').status_code, 404)
        self.assertEqual(self.client.get(self.url).data['count'], 0)

    def test_default_scoped_per_user_and_unique(self):
        a = self._create(self.lq1, 'A').data
        b = self._create(self.lq1, 'B').data
        c = self._create(self.lq2, 'C').data
        self.assertTrue(a['is_default'])
        self.assertFalse(b['is_default'])
        self.assertTrue(c['is_default'])
        self.client.force_authenticate(user=self.lq1)
        self.client.post(f"{self.url}{b['id']}/set-default/")
        self.assertEqual(EmailTemplate.objects.filter(owner=self.lq1, is_default=True).count(), 1)
        self.assertTrue(EmailTemplate.objects.get(pk=b['id']).is_default)
        self.assertTrue(EmailTemplate.objects.get(pk=c['id']).is_default)  # other user untouched

    def test_signatures_crud_default_and_duplicate(self):
        self.client.force_authenticate(user=self.lq1)
        r = self.client.post(self.sig_url, {'name': 'Sig', 'html': '<b>Me</b>'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertTrue(r.data['is_default'])
        d = self.client.post(f"{self.sig_url}{r.data['id']}/duplicate/")
        self.assertEqual(d.status_code, 201)
        self.assertFalse(d.data['is_default'])
        self.assertEqual(EmailSignatureTemplate.objects.filter(owner=self.lq1).count(), 2)

    def test_malicious_html_sanitized_on_save(self):
        evil = ('<p onclick="x()">Hi</p><script>alert(1)</script>'
                '<a href="javascript:alert(1)">l</a><img src="data:text/html;base64,AAA" onerror="x()">'
                '<div style="background:url(javascript:alert(1))">d</div><iframe src="http://e"></iframe>')
        r = self._create(self.lq1, html=evil)
        self.assertEqual(r.status_code, 201)
        out = r.data['html'].lower()
        for bad in ('<script', 'onclick', 'onerror', 'javascript:', 'data:text', '<iframe', 'alert(1)'):
            self.assertNotIn(bad, out)
        self.assertIn('hi', out)

    def test_safe_raster_image_preserved(self):
        valid_img = '<p>Hi</p><img src="data:image/png;base64,iVBORw0KGgo=" alt="pic">'
        r = self._create(self.lq1, html=valid_img)
        self.assertEqual(r.status_code, 201)
        self.assertIn('data:image/png;base64,ivborw0kggo=', r.data['html'].lower())

    def test_upload_image_success(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_authenticate(user=self.lq1)
        img_bytes = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4'
        upload = SimpleUploadedFile("logo.png", img_bytes, content_type="image/png")
        r = self.client.post(f"{self.url}upload-image/", {'file': upload}, format='multipart')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertIn('url', r.data)
        self.assertTrue(r.data['url'].endswith('.png'))

    def test_upload_image_rejects_invalid(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_authenticate(user=self.lq1)
        bad_file = SimpleUploadedFile("malicious.exe", b"MZ...", content_type="application/octet-stream")
        r = self.client.post(f"{self.url}upload-image/", {'file': bad_file}, format='multipart')
        self.assertEqual(r.status_code, 400)

    def test_persists_across_login(self):
        self._create(self.lq1, 'Persist')
        self.client.force_authenticate(user=None)
        self.client.force_authenticate(user=self.lq1)
        self.assertEqual(self.client.get(self.url).data['results'][0]['name'], 'Persist')


class SanitizerAndPlaceholderTests(APITestCase):
    def test_placeholders_escape_and_missing(self):
        out = render_placeholders('Hi {{contact_name}} {{ company_name }} {{unknown}} {{website}}',
                                  {'contact_name': '<b>x</b>', 'company_name': 'Acme'})
        self.assertEqual(out, 'Hi &lt;b&gt;x&lt;/b&gt; Acme {{unknown}} ')

    def test_placeholders_do_not_execute(self):
        out = render_placeholders('{{ __import__("os") }} {{contact_name}}', {'contact_name': '{{company_name}}'})
        self.assertIn('{{', out)

    def test_sanitizer_keeps_email_markup(self):
        h = sanitize_email_html('<table width="600" cellpadding="0"><tr><td style="color:#f00" bgcolor="#fff">'
                                '<a href="https://a.com">x</a><img src="https://a.com/i.png" width="10"></td></tr></table>')
        self.assertIn('<table', h)
        self.assertIn('color:#f00', h)
        self.assertIn('https://a.com/i.png', h)


@mock.patch('threading.Thread', _SyncThread)
class SmtpIntegrationTests(APITestCase):
    def setUp(self):
        self.lq = _user('lqs', 'LQ')
        self.lq.first_name = 'Sales'
        self.lq.last_name = 'Team'
        self.lq.save()
        self.other = _user('lqo', 'LQ')
        self.ma = MailAccount.objects.create(
            name='M', email_address='sales@example.com', display_name='Sales Team',
            smtp_host='smtp.example.com', smtp_username='s', smtp_app_password_encrypted='x', smtp_status='VERIFIED',
            imap_host='i', imap_username='s', imap_app_password_encrypted='x', default_signature='Default Sig')
        self.lq.profile.mail_account = self.ma
        self.lq.profile.save()
        from accounts.models import GoogleMailCredentials
        self.gcred = GoogleMailCredentials.objects.create(
            user=self.lq, email='sales@example.com',
            access_token_encrypted='enc_tok', refresh_token_encrypted='enc_ref',
            is_active=True, scopes='https://mail.google.com/'
        )
        self.prospect = Prospect.objects.create(
            company_name='Acme Corp', country_head_office='IN', primary_industries='IT',
            company_structure='Parent', operational_status='Active', primary_offering_type='Products',
            official_website_url='https://acme.test')
        self.contact = ProspectContact.objects.create(
            prospect=self.prospect, contact_name='Jane Doe', designation='CTO', official_email='jane@acme.test')
        self.tpl = EmailTemplate.objects.create(
            owner=self.lq, name='T', subject='Intro to {{company_name}}',
            html='<p>Hello {{contact_name}} from {{sender_name}}</p><script>x()</script>', text='')
        self.sig = EmailSignatureTemplate.objects.create(owner=self.lq, name='S', html='<b>{{sender_name}}</b> | {{sender_email}}')
        self.client.force_authenticate(user=self.lq)

    def _send(self, **extra):
        import json
        data = {'prospect': str(self.prospect.id), 'subject': 'Subj', 'body': 'Plain body',
                'recipients': json.dumps([{'email_address': 'jane@acme.test', 'recipient_type': 'TO'}])}
        data.update(extra)
        with mock.patch('accounts.oauth_services.GmailOAuthService.send_message', return_value={'id': 'msg_1', 'threadId': 't_1'}) as gmail_send, \
                mock.patch('smtplib.SMTP') as smtp, \
                mock.patch('utils.encryption.decrypt_password', return_value='pw'):
            r = self.client.post('/api/outreach/emails/', data, format='multipart')
        self._last_gmail_send = gmail_send
        return r, smtp

    def _sent_msg(self, smtp):
        if hasattr(self, '_last_gmail_send') and self._last_gmail_send.called:
            import email
            import email.policy
            raw_bytes = self._last_gmail_send.call_args[0][1]
            return email.message_from_bytes(raw_bytes, policy=email.policy.default)
        return smtp.return_value.send_message.call_args[0][0]

    def test_legacy_send_unchanged_without_template(self):
        r, smtp = self._send()
        self.assertEqual(r.status_code, 201, r.data)
        msg = self._sent_msg(smtp)
        self.assertEqual(msg['Subject'], 'Subj')
        self.assertIn('sales@example.com', msg.get_body(('plain',)).get_content())
        oe = OutreachEmail.objects.get(pk=r.data['id'])
        self.assertTrue(oe.signature)
        self.assertEqual(oe.status, 'WAITING FOR RESPONSE')
        self.assertTrue(oe.tracking_token)

    def test_send_with_template_and_signature(self):
        r, smtp = self._send(template_id=str(self.tpl.id), signature_id=str(self.sig.id), body_edited='false', subject='', open_tracking_enabled='true')
        self.assertEqual(r.status_code, 201, r.data)
        msg = self._sent_msg(smtp)
        self.assertEqual(msg['Subject'], 'Intro to Acme Corp')
        html = msg.get_body(('html',)).get_content()
        self.assertIn('Hello Jane Doe from Sales Team', html)
        self.assertNotIn('<script', html)
        self.assertIn('sales@example.com', html)
        self.assertNotIn('Default Sig', html)  # saved signature replaces, not duplicates
        self.assertIn('/api/email-tracking/', html)
        oe = OutreachEmail.objects.get(pk=r.data['id'])
        self.assertIn('Sales Team | sales@example.com', oe.body)
        self.assertEqual(oe.recipients.count(), 1)

    def test_edited_body_is_respected(self):
        r, smtp = self._send(template_id=str(self.tpl.id), body='My edited <text>', body_edited='true')
        self.assertEqual(r.status_code, 201)
        html = self._sent_msg(smtp).get_body(('html',)).get_content()
        self.assertIn('My edited &lt;text&gt;', html)

    def test_other_users_template_rejected_at_send(self):
        foreign = EmailTemplate.objects.create(owner=self.other, name='F', html='<p>secret</p>')
        r, smtp = self._send(template_id=str(foreign.id))
        self.assertEqual(r.status_code, 400)
        smtp.return_value.send_message.assert_not_called()
        self.assertEqual(OutreachEmail.objects.count(), 0)
        fs = EmailSignatureTemplate.objects.create(owner=self.other, name='F', html='x')
        self.assertEqual(self._send(signature_id=str(fs.id))[0].status_code, 400)

    def test_invalid_id_is_400(self):
        self.assertEqual(self._send(template_id='not-a-uuid')[0].status_code, 400)

    def test_compose_preview_does_not_send(self):
        with mock.patch('smtplib.SMTP') as smtp:
            r = self.client.post('/api/outreach/emails/compose-preview/', {
                'prospect': str(self.prospect.id), 'to_emails': ['jane@acme.test'], 'body': '',
                'template_id': str(self.tpl.id), 'signature_id': str(self.sig.id), 'body_edited': False,
            }, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertIn('Hello Jane Doe', r.data['html'])
        smtp.assert_not_called()
        self.assertEqual(OutreachEmail.objects.count(), 0)

    def test_compose_preview_non_lq_denied(self):
        self.client.force_authenticate(user=_user('p2', 'PRE'))
        r = self.client.post('/api/outreach/emails/compose-preview/', {'prospect': str(self.prospect.id)}, format='json')
        self.assertEqual(r.status_code, 403)

    def test_send_with_embedded_base64_image_converts_to_cid(self):
        b64_png = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        tpl_with_img = EmailTemplate.objects.create(
            owner=self.lq,
            name='Template with Image',
            subject='Subject With Image',
            html=f'<p>Hi {{{{contact_name}}}}</p><img id="ixxwy" src="{b64_png}">',
        )
        r, smtp = self._send(template_id=str(tpl_with_img.id), body_edited='false')
        self.assertEqual(r.status_code, 201, r.data)
        msg = self._sent_msg(smtp)

        # HTML body must have cid: instead of data:image/
        html = msg.get_body(('html',)).get_content()
        self.assertNotIn('data:image/png;base64', html)
        self.assertIn('src="cid:', html)

        # The message must contain the inline image MIME part with Content-ID and Content-Disposition inline
        inline_parts = [p for p in msg.walk() if p.get_content_maintype() == 'image']
        self.assertEqual(len(inline_parts), 1)
        self.assertEqual(inline_parts[0].get_content_type(), 'image/png')
        self.assertTrue(inline_parts[0]['Content-ID'])
        self.assertEqual(inline_parts[0]['Content-Disposition'], 'inline')

