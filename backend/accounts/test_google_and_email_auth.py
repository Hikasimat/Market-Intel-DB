import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from rest_framework import status
from django.core.signing import TimestampSigner

from accounts.models import UserProfile, GoogleMailCredentials
from accounts.oauth_services import GoogleOAuthService, GmailOAuthService
import utils.encryption as encryption

# Ensure a valid Fernet encryption key is available for tests
TEST_ENCRYPTION_KEY = encryption.Fernet.generate_key().decode('utf-8')


@override_settings(
    MAIL_CREDENTIALS_ENCRYPTION_KEY=TEST_ENCRYPTION_KEY,
    GOOGLE_OAUTH_CLIENT_ID='test-google-client-id.apps.googleusercontent.com',
    GOOGLE_OAUTH_CLIENT_SECRET='test-google-client-secret',
    GOOGLE_OAUTH_REDIRECT_URI='http://localhost:5173/auth/google/callback',
    GMAIL_OAUTH_REDIRECT_URI='http://localhost:5173/auth/gmail/callback',
)
class GoogleAndEmailAuthTests(TestCase):
    def setUp(self):
        import os
        from django.core.cache import cache
        cache.clear()
        os.environ['MAIL_CREDENTIALS_ENCRYPTION_KEY'] = TEST_ENCRYPTION_KEY

        self.client = APIClient()

        # PRE User (username != email test scenario)
        self.pre_user = User.objects.create_user(
            username='pre_researcher',
            email='pre@marketintel.com',
            password='Password123!',
            first_name='Peter',
            last_name='Research'
        )
        self.pre_user.profile.role = 'PRE'
        self.pre_user.profile.save()

        # LQ User (username == email scenario)
        self.lq_user = User.objects.create_user(
            username='lq@marketintel.com',
            email='lq@marketintel.com',
            password='Password123!',
            first_name='Laura',
            last_name='Qualifier'
        )
        self.lq_user.profile.role = 'LQ'
        self.lq_user.profile.save()

        # Manager User (username != email)
        self.manager_user = User.objects.create_user(
            username='manager_admin_user',
            email='manager@marketintel.com',
            password='Password123!',
            first_name='Mary',
            last_name='Manager'
        )
        self.manager_user.profile.role = 'MANAGER'
        self.manager_user.profile.save()

        # Superuser
        self.superuser = User.objects.create_superuser(
            username='admin_boss',
            email='super@marketintel.com',
            password='Password123!'
        )

        # Inactive User
        self.inactive_user = User.objects.create_user(
            username='inactive_person',
            email='inactive@marketintel.com',
            password='Password123!',
            is_active=False
        )

    # ──────────────────────────────────────────────────────────────────────────
    # 1. EMAIL / PASSWORD AUTHENTICATION TESTS
    # ──────────────────────────────────────────────────────────────────────────

    def test_email_login_success(self):
        """Active user logs in with registered email address and correct password."""
        res = self.client.post('/api/auth/login/', {
            'email': 'pre@marketintel.com',
            'password': 'Password123!',
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('access', res.data)
        self.assertNotIn('refresh', res.data)  # Refresh token should NOT be in body
        self.assertIn('access_token', res.cookies)
        self.assertIn('refresh_token', res.cookies)
        self.assertTrue(res.cookies['access_token']['httponly'])
        self.assertTrue(res.cookies['refresh_token']['httponly'])

    def test_email_login_case_insensitive(self):
        """Email login works with mixed-case email."""
        res = self.client.post('/api/auth/login/', {
            'email': 'PrE@MarketIntel.COM',
            'password': 'Password123!',
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('access', res.data)

    def test_email_login_username_different_from_email(self):
        """Account where username != email logs in successfully using registered email."""
        self.assertNotEqual(self.pre_user.username, self.pre_user.email)
        res = self.client.post('/api/auth/login/', {
            'email': 'pre@marketintel.com',
            'password': 'Password123!',
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_email_login_username_fallback(self):
        """Submitting username instead of email still authenticates cleanly."""
        res = self.client.post('/api/auth/login/', {
            'username': 'pre_researcher',
            'password': 'Password123!',
        })
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_email_login_invalid_password_rejected(self):
        """Wrong password is rejected with generic error."""
        res = self.client.post('/api/auth/login/', {
            'email': 'pre@marketintel.com',
            'password': 'WrongPassword!',
        })
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn('access_token', res.cookies)

    def test_email_login_inactive_user_rejected(self):
        """Inactive user cannot log in even with correct credentials."""
        res = self.client.post('/api/auth/login/', {
            'email': 'inactive@marketintel.com',
            'password': 'Password123!',
        })
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_email_login_unknown_account_generic_error(self):
        """Non-existent email returns generic 401 error without disclosing existence."""
        res = self.client.post('/api/auth/login/', {
            'email': 'nobody@nowhere.com',
            'password': 'Password123!',
        })
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('detail', res.data)

    # ──────────────────────────────────────────────────────────────────────────
    # 2. GOOGLE OAUTH URL & STATE TESTS
    # ──────────────────────────────────────────────────────────────────────────

    def test_google_oauth_url_generation(self):
        """GET /api/auth/google/url/ returns valid Google auth URL and sets state cookie."""
        res = self.client.get('/api/auth/google/url/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('url', res.data)
        self.assertIn('state', res.data)
        auth_url = res.data['url']
        self.assertIn('accounts.google.com', auth_url)
        self.assertIn('scope=openid+email+profile', auth_url)
        self.assertIn('gmail.modify', auth_url)  # Login now also grants mailbox access
        self.assertIn('access_type=offline', auth_url)
        self.assertIn('oauth_state', res.cookies)
        self.assertTrue(res.cookies['oauth_state']['httponly'])

    # ──────────────────────────────────────────────────────────────────────────
    # 3. GOOGLE OAUTH LOGIN & EXISTING-USER ENFORCEMENT
    # ──────────────────────────────────────────────────────────────────────────

    def test_google_login_success_existing_user(self):
        """A verified Google identity matching an existing active user succeeds."""
        signer = TimestampSigner(salt='google-oauth-state')
        valid_state = signer.sign('test-random-state')
        self.client.cookies['oauth_state'] = valid_state

        with patch.object(GoogleOAuthService, 'exchange_code_for_tokens') as mock_exchange, \
             patch.object(GoogleOAuthService, 'verify_id_token') as mock_verify:

            mock_exchange.return_value = {'id_token': 'fake-id-token', 'access_token': 'fake-google-token'}
            mock_verify.return_value = {
                'email': 'pre@marketintel.com',
                'sub': 'google-uid-12345',
                'name': 'Peter Research',
            }

            res = self.client.post('/api/auth/google/login/', {
                'code': 'valid-google-code',
                'state': valid_state,
            })

            self.assertEqual(res.status_code, status.HTTP_200_OK)
            self.assertIn('access', res.data)
            self.assertIn('access_token', res.cookies)
            self.assertIn('refresh_token', res.cookies)

    def test_google_login_unknown_email_rejected_and_never_created(self):
        """Unknown Google user is rejected with 403 and NEVER automatically created."""
        signer = TimestampSigner(salt='google-oauth-state')
        valid_state = signer.sign('test-random-state')
        self.client.cookies['oauth_state'] = valid_state

        unknown_email = 'stranger@example.com'
        self.assertFalse(User.objects.filter(email=unknown_email).exists())

        with patch.object(GoogleOAuthService, 'exchange_code_for_tokens') as mock_exchange, \
             patch.object(GoogleOAuthService, 'verify_id_token') as mock_verify:

            mock_exchange.return_value = {'id_token': 'fake-id-token', 'access_token': 'fake-google-token'}
            mock_verify.return_value = {
                'email': unknown_email,
                'sub': 'google-uid-unknown',
                'name': 'Unknown Person',
            }

            res = self.client.post('/api/auth/google/login/', {
                'code': 'valid-google-code',
                'state': valid_state,
            })

            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
            self.assertIn("not registered", res.data.get('detail', ''))
            # MANDATORY RULE: Must NOT automatically create a user
            self.assertFalse(User.objects.filter(email=unknown_email).exists())

    def test_google_login_inactive_user_rejected(self):
        """Inactive account matched via Google identity is rejected with 403."""
        signer = TimestampSigner(salt='google-oauth-state')
        valid_state = signer.sign('test-random-state')
        self.client.cookies['oauth_state'] = valid_state

        with patch.object(GoogleOAuthService, 'exchange_code_for_tokens') as mock_exchange, \
             patch.object(GoogleOAuthService, 'verify_id_token') as mock_verify:

            mock_exchange.return_value = {'id_token': 'fake-id-token', 'access_token': 'fake-google-token'}
            mock_verify.return_value = {
                'email': 'inactive@marketintel.com',
                'sub': 'google-uid-inactive',
                'name': 'Inactive Person',
            }

            res = self.client.post('/api/auth/google/login/', {
                'code': 'valid-google-code',
                'state': valid_state,
            })

            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
            self.assertIn("inactive", res.data.get('detail', '').lower())

    def test_google_login_invalid_state_rejected(self):
        """Mismatched, forged, or expired OAuth state is rejected."""
        self.client.cookies['oauth_state'] = 'correct_state_cookie'
        res = self.client.post('/api/auth/google/login/', {
            'code': 'any-code',
            'state': 'forged_or_tampered_state',
        })
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("OAuth state", res.data.get('detail', ''))

    def test_google_login_unverified_email_rejected(self):
        """Unverified Google email is strictly rejected."""
        signer = TimestampSigner(salt='google-oauth-state')
        valid_state = signer.sign('test-random-state')
        self.client.cookies['oauth_state'] = valid_state

        with patch.object(GoogleOAuthService, 'exchange_code_for_tokens') as mock_exchange, \
             patch.object(GoogleOAuthService, 'verify_id_token') as mock_verify:

            mock_exchange.return_value = {'id_token': 'fake-id-token', 'access_token': 'fake-google-token'}
            mock_verify.side_effect = ValueError("Google account email is not verified.")

            res = self.client.post('/api/auth/google/login/', {
                'code': 'valid-google-code',
                'state': valid_state,
            })

            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("not verified", res.data.get('detail', ''))

    def test_google_backend_callback_redirect(self):
        """GET /api/auth/google/callback/ redirects to frontend with HttpOnly cookies."""
        signer = TimestampSigner(salt='google-oauth-state')
        valid_state = signer.sign('test-random-state')
        self.client.cookies['oauth_state'] = valid_state

        with patch.object(GoogleOAuthService, 'exchange_code_for_tokens') as mock_exchange, \
             patch.object(GoogleOAuthService, 'verify_id_token') as mock_verify:

            mock_exchange.return_value = {'id_token': 'fake-id-token', 'access_token': 'fake-google-token'}
            mock_verify.return_value = {
                'email': 'lq@marketintel.com',
                'sub': 'google-uid-lq',
                'name': 'Laura Qualifier',
            }

            res = self.client.get(f'/api/auth/google/callback/?code=valid-code&state={valid_state}')
            self.assertEqual(res.status_code, status.HTTP_302_FOUND)
            self.assertIn('oauth_success=1', res.url)
            self.assertIn('access_token', res.cookies)
            self.assertIn('refresh_token', res.cookies)

    # ──────────────────────────────────────────────────────────────────────────
    # 4. CURRENT USER & ROLE PRESERVATION TESTS
    # ──────────────────────────────────────────────────────────────────────────

    def test_me_endpoint_returns_correct_role_and_profile(self):
        """Role and profile information is preserved exactly after authentication."""
        self.client.force_authenticate(user=self.pre_user)
        res = self.client.get('/api/auth/me/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['role'], 'PRE')
        self.assertEqual(res.data['email'], 'pre@marketintel.com')
        self.assertFalse(res.data['is_superuser'])

        self.client.force_authenticate(user=self.lq_user)
        res = self.client.get('/api/auth/me/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['role'], 'LQ')

        self.client.force_authenticate(user=self.manager_user)
        res = self.client.get('/api/auth/me/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['role'], 'MANAGER')

    # ──────────────────────────────────────────────────────────────────────────
    # 5. USER MANAGEMENT & AUTHORIZATION BOUNDARIES
    # ──────────────────────────────────────────────────────────────────────────

    def test_pre_and_lq_cannot_access_user_management(self):
        """Ordinary users (PRE, LQ) cannot access user creation or management."""
        self.client.force_authenticate(user=self.pre_user)
        res = self.client.get('/api/auth/users/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        self.client.force_authenticate(user=self.lq_user)
        res = self.client.get('/api/auth/users/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_user_creation_restrictions(self):
        """Manager can create normal users but CANNOT create superusers."""
        self.client.force_authenticate(user=self.manager_user)
        
        # Valid normal user creation
        res = self.client.post('/api/auth/users/', {
            'email': 'new_recruit@marketintel.com',
            'password': 'Password123!',
            'profile': {'role': 'PRE'}
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        created_user = User.objects.get(email='new_recruit@marketintel.com')
        self.assertEqual(created_user.profile.role, 'PRE')
        self.assertFalse(created_user.is_superuser)

        # Attempting to create superuser must be blocked
        res_super = self.client.post('/api/auth/users/', {
            'email': 'sneaky_super@marketintel.com',
            'password': 'Password123!',
            'is_superuser': True,
            'is_staff': True,
        }, format='json')
        self.assertEqual(res_super.status_code, status.HTTP_403_FORBIDDEN)

    # ──────────────────────────────────────────────────────────────────────────
    # 6. GMAIL MAILBOX OAUTH SEPARATION & ENCRYPTION TESTS
    # ──────────────────────────────────────────────────────────────────────────

    def test_gmail_oauth_url_requires_authentication(self):
        """Unauthenticated client cannot access Gmail authorization URL endpoint."""
        res = self.client.get('/api/auth/google/gmail/url/')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_gmail_oauth_url_requests_gmail_scopes(self):
        """Authenticated user gets Gmail authorization URL requesting gmail scopes."""
        self.client.force_authenticate(user=self.lq_user)
        res = self.client.get('/api/auth/google/gmail/url/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('url', res.data)
        self.assertIn('gmail.send', res.data['url'])
        self.assertIn('gmail.readonly', res.data['url'])
        self.assertIn('access_type=offline', res.data['url'])
        self.assertIn('prompt=consent', res.data['url'])

    def test_gmail_callback_encrypts_tokens_and_stores_server_side(self):
        """Gmail callback persists tokens encrypted with Fernet and never plain text."""
        self.client.force_authenticate(user=self.lq_user)

        # Generate valid gmail state for this user
        signer = TimestampSigner(salt='gmail-oauth-state')
        valid_state = signer.sign(f"{self.lq_user.id}:random-sub-token")

        with patch.object(GmailOAuthService, 'exchange_code_for_tokens') as mock_exchange:
            mock_exchange.return_value = {
                'access_token': 'plain-google-access-secret-12345',
                'refresh_token': 'plain-google-refresh-secret-67890',
                'expires_in': 3600,
                'scope': 'https://www.googleapis.com/auth/gmail.send https://www.googleapis.com/auth/gmail.readonly',
            }

            res = self.client.post('/api/auth/google/gmail/callback/', {
                'code': 'gmail-auth-code',
                'state': valid_state,
            })

            self.assertEqual(res.status_code, status.HTTP_200_OK)
            self.assertEqual(res.data['email'], self.lq_user.email)
            # Response must NOT expose tokens
            self.assertNotIn('access_token', res.data)
            self.assertNotIn('refresh_token', res.data)

            # Inspect database record
            creds = GoogleMailCredentials.objects.get(user=self.lq_user)
            self.assertNotEqual(creds.access_token_encrypted, 'plain-google-access-secret-12345')
            self.assertNotEqual(creds.refresh_token_encrypted, 'plain-google-refresh-secret-67890')
            # Verify they decrypt cleanly using managed encryption key
            self.assertEqual(
                encryption.decrypt_password(creds.access_token_encrypted),
                'plain-google-access-secret-12345'
            )
            self.assertEqual(
                encryption.decrypt_password(creds.refresh_token_encrypted),
                'plain-google-refresh-secret-67890'
            )

    def test_gmail_status_and_disconnect(self):
        """Gmail status returns public metadata only; disconnect removes credentials."""
        self.client.force_authenticate(user=self.lq_user)
        GoogleMailCredentials.objects.create(
            user=self.lq_user,
            email=self.lq_user.email,
            access_token_encrypted=encryption.encrypt_password('token-abc'),
            refresh_token_encrypted=encryption.encrypt_password('refresh-xyz'),
            scopes='https://www.googleapis.com/auth/gmail.send',
            is_active=True
        )

        res_status = self.client.get('/api/auth/google/gmail/status/')
        self.assertEqual(res_status.status_code, status.HTTP_200_OK)
        self.assertTrue(res_status.data['is_connected'])
        self.assertEqual(res_status.data['email'], self.lq_user.email)
        self.assertNotIn('access_token', res_status.data)
        self.assertNotIn('refresh_token', res_status.data)

        # Disconnect
        res_disc = self.client.post('/api/auth/google/gmail/disconnect/')
        self.assertEqual(res_disc.status_code, status.HTTP_200_OK)
        self.assertFalse(GoogleMailCredentials.objects.filter(user=self.lq_user).exists())

    def test_cross_user_gmail_isolation(self):
        """One user cannot access another user's Gmail authorization."""
        GoogleMailCredentials.objects.create(
            user=self.lq_user,
            email='lq@marketintel.com',
            access_token_encrypted=encryption.encrypt_password('lq-secret-token'),
            is_active=True
        )

        # Another LQ user cannot see lq_user's Gmail credentials
        other_lq = User.objects.create_user(
            username='other_lq@marketintel.com',
            email='other_lq@marketintel.com',
            password='Password123!'
        )
        other_lq.profile.role = 'LQ'
        other_lq.profile.save()

        self.client.force_authenticate(user=other_lq)
        res = self.client.get('/api/auth/google/gmail/status/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data['is_connected'])

        # PRE user is denied completely
        self.client.force_authenticate(user=self.pre_user)
        res_pre = self.client.get('/api/auth/google/gmail/status/')
        self.assertEqual(res_pre.status_code, status.HTTP_403_FORBIDDEN)

    def test_login_throttling_is_enforced(self):
        """Verify login endpoint rate throttle (5 requests/minute)."""
        # Rapidly send 5 login attempts
        for _ in range(5):
            self.client.post('/api/auth/login/', {
                'email': 'pre@marketintel.com',
                'password': 'WrongPassword!',
            })
        # 6th attempt should trigger 429 Too Many Requests
        res_6 = self.client.post('/api/auth/login/', {
            'email': 'pre@marketintel.com',
            'password': 'Password123!',
        })
        self.assertEqual(res_6.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_mail_account_viewset_with_gmail_creds(self):
        """Verify MailAccountViewSet list, fetch-emails, and fetch-email-body delegate to Gmail OAuth."""
        self.client.force_authenticate(user=self.lq_user)
        GoogleMailCredentials.objects.create(
            user=self.lq_user,
            email=self.lq_user.email,
            access_token_encrypted=encryption.encrypt_password('token-abc'),
            is_active=True
        )

        # 1. list endpoint includes Gmail entry
        res_list = self.client.get('/api/auth/mail-account/')
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        gmail_entries = [acc for acc in res_list.data if acc.get('provider') == 'GMAIL_OAUTH']
        self.assertEqual(len(gmail_entries), 1)
        self.assertEqual(gmail_entries[0]['email_address'], self.lq_user.email)

        # 2. fetch-emails delegates to GmailOAuthService
        with patch.object(GmailOAuthService, 'fetch_messages') as mock_fetch:
            mock_fetch.return_value = {
                'messages': [{'uid': 'gmail-msg-1', 'id': 'gmail-msg-1', 'subject': 'Test Subject'}],
                'uidvalidity': 1,
            }
            res_fetch = self.client.get('/api/auth/mail-account/fetch-emails/?folder=INBOX')
            self.assertEqual(res_fetch.status_code, status.HTTP_200_OK)
            self.assertEqual(len(res_fetch.data['messages']), 1)
            self.assertEqual(res_fetch.data['messages'][0]['subject'], 'Test Subject')

        # 3. fetch-email-body delegates to GmailOAuthService
        with patch.object(GmailOAuthService, 'fetch_message_body') as mock_body:
            mock_body.return_value = {
                'html_body': '<p>Hello from Gmail</p>',
                'text_body': 'Hello from Gmail',
                'attachments': [],
                'tracking': None,
            }
            res_body = self.client.get('/api/auth/mail-account/fetch-email-body/?uid=gmail-msg-1')
            self.assertEqual(res_body.status_code, status.HTTP_200_OK)
            self.assertEqual(res_body.data['text_body'], 'Hello from Gmail')

    def test_mail_account_send_email_via_gmail(self):
        """Verify send-email action uses Gmail API when Gmail is connected."""
        self.client.force_authenticate(user=self.lq_user)
        GoogleMailCredentials.objects.create(
            user=self.lq_user,
            email=self.lq_user.email,
            access_token_encrypted=encryption.encrypt_password('token-abc'),
            is_active=True
        )

        with patch.object(GmailOAuthService, 'send_message') as mock_send:
            mock_send.return_value = {'id': 'sent-123'}
            res_send = self.client.post('/api/auth/mail-account/send-email/', {
                'to': 'prospect@clientcorp.com',
                'subject': 'Introductory Outreach',
                'body': 'Excited to connect with your team.',
                'provider': 'gmail',
            })
            self.assertEqual(res_send.status_code, status.HTTP_200_OK)
            self.assertTrue(res_send.data['success'])
            self.assertTrue('tracking_token' in res_send.data)

    def test_gmail_message_actions(self):
        """Verify modify-message, trash, untrash, and delete endpoints delegate to GmailOAuthService."""
        self.client.force_authenticate(user=self.lq_user)
        GoogleMailCredentials.objects.create(
            user=self.lq_user,
            email=self.lq_user.email,
            access_token_encrypted=encryption.encrypt_password('token-abc'),
            is_active=True
        )

        with patch.object(GmailOAuthService, 'modify_message') as mock_mod:
            mock_mod.return_value = {'id': 'msg-1', 'labelIds': ['STARRED']}
            res = self.client.post('/api/auth/mail-account/modify-message/', {
                'msg_id': 'msg-1',
                'action': 'star'
            })
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            mock_mod.assert_called_once()
            args, kwargs = mock_mod.call_args
            self.assertEqual(kwargs.get('add_label_ids'), ['STARRED'])

        with patch.object(GmailOAuthService, 'modify_message') as mock_mod:
            mock_mod.return_value = {'id': 'msg-1', 'labelIds': []}
            res = self.client.post('/api/auth/mail-account/modify-message/', {
                'msg_id': 'msg-1',
                'action': 'read'
            })
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            mock_mod.assert_called_once()
            args, kwargs = mock_mod.call_args
            self.assertEqual(kwargs.get('remove_label_ids'), ['UNREAD'])

        with patch.object(GmailOAuthService, 'modify_message') as mock_mod:
            mock_mod.return_value = {'id': 'msg-1', 'labelIds': ['SPAM']}
            res = self.client.post('/api/auth/mail-account/modify-message/', {
                'msg_id': 'msg-1',
                'action': 'spam'
            })
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            mock_mod.assert_called_once()
            args, kwargs = mock_mod.call_args
            self.assertEqual(kwargs.get('add_label_ids'), ['SPAM'])
            self.assertEqual(kwargs.get('remove_label_ids'), ['INBOX'])

        with patch.object(GmailOAuthService, 'trash_message') as mock_trash:
            mock_trash.return_value = {'id': 'msg-1'}
            res = self.client.post('/api/auth/mail-account/trash-message/', {
                'msg_id': 'msg-1'
            })
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            mock_trash.assert_called_once()

        with patch.object(GmailOAuthService, 'untrash_message') as mock_untrash:
            mock_untrash.return_value = {'id': 'msg-1'}
            res = self.client.post('/api/auth/mail-account/untrash-message/', {
                'msg_id': 'msg-1'
            })
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            mock_untrash.assert_called_once()

        with patch.object(GmailOAuthService, 'delete_message') as mock_del:
            mock_del.return_value = {'status': 'deleted'}
            res = self.client.post('/api/auth/mail-account/delete-message/', {
                'msg_id': 'msg-1'
            })
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            mock_del.assert_called_once()

    def test_gmail_drafts(self):
        """Verify save-draft and delete-draft endpoints."""
        self.client.force_authenticate(user=self.lq_user)
        GoogleMailCredentials.objects.create(
            user=self.lq_user,
            email=self.lq_user.email,
            access_token_encrypted=encryption.encrypt_password('token-abc'),
            is_active=True
        )

        with patch.object(GmailOAuthService, 'save_draft') as mock_save:
            mock_save.return_value = {'id': 'draft-101'}
            res = self.client.post('/api/auth/mail-account/save-draft/', {
                'to': 'recipient@acme.com',
                'subject': 'Draft subject',
                'body': 'Draft body content'
            })
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            self.assertTrue(res.data['success'])
            mock_save.assert_called_once()

        with patch.object(GmailOAuthService, 'delete_draft') as mock_del:
            mock_del.return_value = {'status': 'deleted'}
            res = self.client.post('/api/auth/mail-account/delete-draft/', {
                'draft_id': 'draft-101'
            })
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            mock_del.assert_called_once()

    def test_lq_outreach_send_via_gmail_creds(self):
        """Verify LQ outreach can send via Gmail OAuth without requiring SMTP configuration."""
        self.client.force_authenticate(user=self.lq_user)
        GoogleMailCredentials.objects.create(
            user=self.lq_user,
            email=self.lq_user.email,
            access_token_encrypted=encryption.encrypt_password('token-abc'),
            is_active=True
        )
        from prospects.models import Prospect, LeadQualification
        prospect = Prospect.objects.create(
            company_name='Acme Corporation',
            country_head_office='IN',
            complete_address='Acme Tower',
            primary_industries='IT',
            company_structure='Parent',
            operational_status='Active',
            primary_offering_type='Products',
            official_website_url='https://acme.example.com',
            official_email_address='contact@acme.example.com',
        )
        LeadQualification.objects.get_or_create(prospect=prospect)

        with patch.object(GmailOAuthService, 'send_message') as mock_send:
            mock_send.return_value = {'id': 'gmail-outreach-123'}
            res = self.client.post('/api/outreach/emails/', {
                'prospect': prospect.id,
                'subject': 'Partnership Opportunity',
                'body': 'Hello Acme team, let us connect.',
                'recipients': [
                    {'email_address': 'contact@acme.example.com', 'recipient_type': 'TO'}
                ]
            }, format='json')
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)
            self.assertEqual(res.data['from_email'], self.lq_user.email)


