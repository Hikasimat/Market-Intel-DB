from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
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
        """Test that a Manager cannot delete users."""
        self.client.force_authenticate(user=self.manager_user)
        url = f'/api/auth/users/{self.pre_user.id}/'
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

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
