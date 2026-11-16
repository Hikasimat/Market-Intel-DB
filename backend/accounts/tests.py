from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from django.contrib.auth.models import User
from accounts.models import UserProfile, MailAccount
from utils.encryption import decrypt_password

class AccountsTestCase(APITestCase):
    def setUp(self):
        # Sample Data: Create Superuser
        self.superuser = User.objects.create_superuser(
            username='admin@example.com',
            email='admin@example.com',
            password='adminpassword'
        )
        self.superuser.profile.role = 'MANAGER'
        self.superuser.profile.save()

        # Sample Data: Create Manager User
        self.manager_user = User.objects.create_user(
            username='manager@example.com',
            email='manager@example.com',
            password='managerpassword'
        )
        self.manager_user.profile.role = 'MANAGER'
        self.manager_user.profile.save()

        # Sample Data: Create PRE User 2
        self.lq_user = User.objects.create_user(
            username='lq@example.com',
            email='lq@example.com',
            password='lqpassword'
        )
        self.lq_user.profile.role = 'PRE'
        self.lq_user.profile.save()

        # Sample Data: Create PRE User
        self.pre_user = User.objects.create_user(
            username='pre@example.com',
            email='pre@example.com',
            password='prepassword'
        )
        self.pre_user.profile.role = 'PRE'
        self.pre_user.profile.save()

        # Sample Data: Create MailAccount
        self.mail_account = MailAccount.objects.create(
            name='Test Sales',
            email_address='sales@example.com',
            display_name='Sales Team',
            smtp_host='smtp.example.com',
            smtp_username='sales@example.com',
            smtp_app_password_encrypted='encrypted_smtp',
            imap_host='imap.example.com',
            imap_username='sales@example.com',
            imap_app_password_encrypted='encrypted_imap'
        )
        self.lq_user.profile.mail_account = self.mail_account
        self.lq_user.profile.save()

    def test_user_me_get(self):
        """Test retrieving current user's profile details."""
        self.client.force_authenticate(user=self.lq_user)
        url = '/api/auth/me/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'lq@example.com')
        self.assertEqual(response.data['role'], 'PRE')
        self.assertEqual(response.data['mail_account_id'], self.mail_account.id)

    def test_user_me_patch_timezone(self):
        """Test updating user's timezone."""
        self.client.force_authenticate(user=self.pre_user)
        url = '/api/auth/me/'
        response = self.client.patch(url, {'timezone': 'Europe/London'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['timezone'], 'Europe/London')
        self.pre_user.profile.refresh_from_db()
        self.assertEqual(self.pre_user.profile.timezone, 'Europe/London')

    def test_user_me_patch_invalid_timezone(self):
        """Test updating user's timezone with invalid timezone."""
        self.client.force_authenticate(user=self.pre_user)
        url = '/api/auth/me/'
        response = self.client.patch(url, {'timezone': 'Invalid/Timezone'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_manager_cannot_create_superuser(self):
        """Test that a Manager cannot create a superuser."""
        self.client.force_authenticate(user=self.manager_user)
        url = '/api/auth/users/'
        data = {
            'username': 'newsuper@example.com',
            'email': 'newsuper@example.com',
            'password': 'password123',
            'is_superuser': True,
            'is_staff': True,
            'profile': {'role': 'PRE'}
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_create_normal_user(self):
        """Test that a Manager can create a normal user."""
        self.client.force_authenticate(user=self.manager_user)
        url = '/api/auth/users/'
        data = {
            'email': 'newlq@example.com',
            'password': 'password123',
            'profile': {'role': 'PRE'}
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        new_user = User.objects.get(email='newlq@example.com')
        self.assertFalse(new_user.is_superuser)
        self.assertEqual(new_user.profile.role, 'PRE')

    def test_manager_cannot_delete_user(self):
        """Test that a Manager can delete regular users but cannot delete superusers."""
        self.client.force_authenticate(user=self.manager_user)
        # Manager can delete regular PRE user
        url_pre = f'/api/auth/users/{self.pre_user.id}/'
        resp_pre = self.client.delete(url_pre)
        self.assertEqual(resp_pre.status_code, status.HTTP_204_NO_CONTENT)

        # Manager CANNOT delete superuser
        url_admin = f'/api/auth/users/{self.superuser.id}/'
        resp_admin = self.client.delete(url_admin)
        self.assertEqual(resp_admin.status_code, status.HTTP_403_FORBIDDEN)

    def test_mail_account_creation(self):
        """Test creating a MailAccount encrypts passwords."""
        self.client.force_authenticate(user=self.lq_user)
        url = '/api/auth/mail-account/'
        data = {
            'name': 'Support',
            'email_address': 'support@example.com',
            'display_name': 'Support Team',
            'smtp_host': 'smtp.example.com',
            'smtp_username': 'support@example.com',
            'smtp_app_password': 'smtp_secret_pass',
            'imap_host': 'imap.example.com',
            'imap_username': 'support@example.com',
            'imap_app_password': 'imap_secret_pass'
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mail_account = MailAccount.objects.get(email_address='support@example.com')
        self.assertEqual(decrypt_password(mail_account.smtp_app_password_encrypted), 'smtp_secret_pass')
        self.assertEqual(decrypt_password(mail_account.imap_app_password_encrypted), 'imap_secret_pass')
        
    def test_pre_user_cannot_access_users_api(self):
        """Test that a PRE user gets 403 on the users endpoint."""
        self.client.force_authenticate(user=self.pre_user)
        url = '/api/auth/users/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_send_email_action_with_template_and_attachments(self):
        """Test send-email endpoint with template, Cc, Bcc, and file attachments."""
        from django.core.files.uploadedfile import SimpleUploadedFile
        from accounts.models import EmailTemplate, GoogleMailCredentials
        import utils.encryption as encryption
        from unittest.mock import patch

        self.client.force_authenticate(user=self.lq_user)
        GoogleMailCredentials.objects.create(
            user=self.lq_user,
            email=self.lq_user.email,
            access_token_encrypted=encryption.encrypt_password('dummy_access_token'),
            refresh_token_encrypted=encryption.encrypt_password('dummy_refresh_token'),
            is_active=True
        )
        tpl = EmailTemplate.objects.create(
            name='Inbox Test Template',
            subject='Welcome to our company',
            html='<p>Hello, this is a test template.</p>',
            owner=self.lq_user
        )

        dummy_file = SimpleUploadedFile("test_doc.pdf", b"%PDF-1.4 test content", content_type="application/pdf")
        
        with patch('threading.Thread') as mock_thread:
            response = self.client.post('/api/auth/mail-account/send-email/', {
                'to': 'recipient@example.com',
                'cc': 'cc_recipient@example.com',
                'bcc': 'bcc_recipient@example.com',
                'subject': 'Custom Subject',
                'body': 'Hello, this is edited body.',
                'template_id': str(tpl.id),
                'attachments': [dummy_file]
            }, format='multipart')

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data.get('success'), True)
            self.assertTrue(mock_thread.called)

    def test_send_email_action_multiple_attachments_delivery(self):
        """Test composing and sending email with multiple attachments of different MIME types."""
        import email
        from email import policy
        from django.core.files.uploadedfile import SimpleUploadedFile
        from accounts.models import GoogleMailCredentials
        from prospects.models import EmailAttachment, OutreachEmail
        import utils.encryption as encryption
        from unittest.mock import patch

        self.client.force_authenticate(user=self.lq_user)
        GoogleMailCredentials.objects.get_or_create(
            user=self.lq_user,
            defaults={
                'email': self.lq_user.email,
                'access_token_encrypted': encryption.encrypt_password('dummy_access_token'),
                'refresh_token_encrypted': encryption.encrypt_password('dummy_refresh_token'),
                'is_active': True,
            }
        )

        file1 = SimpleUploadedFile("report.pdf", b"%PDF-1.4 sample content", content_type="application/pdf")
        file2 = SimpleUploadedFile("chart.png", b"\x89PNG\r\n\x1a\nfakeimage", content_type="image/png")
        file3 = SimpleUploadedFile("notes.txt", b"plain text notes", content_type="text/plain")

        captured_raw_bytes = []

        def fake_send(credentials, raw_bytes, thread_id=None):
            captured_raw_bytes.append(raw_bytes)
            return {'id': 'msg_123', 'threadId': 'th_123'}

        with patch('accounts.oauth_services.GmailOAuthService.send_message', side_effect=fake_send):
            response = self.client.post('/api/auth/mail-account/send-email/', {
                'to': 'client@example.com',
                'subject': 'Quarterly Report & Charts',
                'body': 'Please find the attached report, chart, and notes.',
                'attachments': [file1, file2, file3]
            }, format='multipart')

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data.get('success'), True)

            # Wait briefly or join thread
            import time
            time.sleep(0.5)

            # Verify EmailAttachment records in DB
            tracking_id = response.data.get('tracking_id')
            self.assertIsNotNone(tracking_id)
            db_attachments = EmailAttachment.objects.filter(outreach_email_id=tracking_id)
            self.assertEqual(db_attachments.count(), 3)
            filenames = {att.original_filename for att in db_attachments}
            self.assertEqual(filenames, {'report.pdf', 'chart.png', 'notes.txt'})

            # Verify captured raw MIME message delivered to Gmail API has all 3 attachments
            self.assertTrue(len(captured_raw_bytes) > 0)
            parsed_email = email.message_from_bytes(captured_raw_bytes[0], policy=policy.default)
            msg_attachments = list(parsed_email.iter_attachments())
            self.assertEqual(len(msg_attachments), 3)
            attachment_names = [a.get_filename() for a in msg_attachments]
            self.assertIn('report.pdf', attachment_names)
            self.assertIn('chart.png', attachment_names)
            self.assertIn('notes.txt', attachment_names)


class EmailAttachmentLibraryTests(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username='alice', password='password123', email='alice@example.com')
        self.user2 = User.objects.create_user(username='bob', password='password123', email='bob@example.com')

        self.client1 = APIClient()
        self.client1.force_authenticate(user=self.user1)

        self.client2 = APIClient()
        self.client2.force_authenticate(user=self.user2)

    def test_empty_library(self):
        res = self.client1.get('/api/auth/attachment-library/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data if isinstance(res.data, list) else res.data.get('results', [])
        self.assertEqual(len(results), 0)

    def test_upload_library_file_success(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from accounts.models import EmailAttachmentLibraryItem
        file = SimpleUploadedFile("brochure.pdf", b"Dummy PDF content", content_type="application/pdf")
        res = self.client1.post('/api/auth/attachment-library/', {'file': file, 'name': 'Company Brochure'}, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['name'], 'Company Brochure')
        self.assertEqual(res.data['file_size'], len(b"Dummy PDF content"))
        self.assertTrue(EmailAttachmentLibraryItem.objects.filter(user=self.user1, name='Company Brochure').exists())

    def test_max_five_files_enforced(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from accounts.models import EmailAttachmentLibraryItem
        for i in range(1, 6):
            f = SimpleUploadedFile(f"file_{i}.pdf", b"data", content_type="application/pdf")
            res = self.client1.post('/api/auth/attachment-library/', {'file': f}, format='multipart')
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        self.assertEqual(EmailAttachmentLibraryItem.objects.filter(user=self.user1).count(), 5)

        # 6th upload must fail
        f6 = SimpleUploadedFile("file_6.pdf", b"data", content_type="application/pdf")
        res6 = self.client1.post('/api/auth/attachment-library/', {'file': f6}, format='multipart')
        self.assertEqual(res6.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('limit reached', res6.data['error'])

    def test_blocked_file_type(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile("malware.exe", b"MZ...", content_type="application/octet-stream")
        res = self.client1.post('/api/auth/attachment-library/', {'file': f}, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('.exe is not allowed', res.data['error'])

    def test_file_size_limit(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        oversized = SimpleUploadedFile("large.pdf", b"X" * (11 * 1024 * 1024), content_type="application/pdf")
        res = self.client1.post('/api/auth/attachment-library/', {'file': oversized}, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('exceeds the 10MB limit', res.data['error'])

    def test_delete_frees_slot(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from accounts.models import EmailAttachmentLibraryItem
        item_ids = []
        for i in range(5):
            f = SimpleUploadedFile(f"file_{i}.pdf", b"content", content_type="application/pdf")
            r = self.client1.post('/api/auth/attachment-library/', {'file': f}, format='multipart')
            item_ids.append(r.data['id'])

        del_res = self.client1.delete(f'/api/auth/attachment-library/{item_ids[0]}/')
        self.assertEqual(del_res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(EmailAttachmentLibraryItem.objects.filter(user=self.user1).count(), 4)

        new_f = SimpleUploadedFile("file_new.pdf", b"new content", content_type="application/pdf")
        res = self.client1.post('/api/auth/attachment-library/', {'file': new_f}, format='multipart')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(EmailAttachmentLibraryItem.objects.filter(user=self.user1).count(), 5)

    def test_user_isolation(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile("alice_doc.pdf", b"Alice secret", content_type="application/pdf")
        r = self.client1.post('/api/auth/attachment-library/', {'file': f}, format='multipart')
        alice_file_id = r.data['id']

        bob_list = self.client2.get('/api/auth/attachment-library/')
        bob_results = bob_list.data if isinstance(bob_list.data, list) else bob_list.data.get('results', [])
        self.assertEqual(len(bob_results), 0)

        bob_del = self.client2.delete(f'/api/auth/attachment-library/{alice_file_id}/')
        self.assertEqual(bob_del.status_code, status.HTTP_404_NOT_FOUND)

    def test_download_file(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile("presentation.pdf", b"Slide 1 2 3", content_type="application/pdf")
        r = self.client1.post('/api/auth/attachment-library/', {'file': f}, format='multipart')
        item_id = r.data['id']

        down_res = self.client1.get(f'/api/auth/attachment-library/{item_id}/download/')
        self.assertEqual(down_res.status_code, status.HTTP_200_OK)
        content = b"".join(down_res.streaming_content) if down_res.streaming else down_res.content
        self.assertEqual(content, b"Slide 1 2 3")

