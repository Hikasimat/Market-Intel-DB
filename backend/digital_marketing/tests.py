import os
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase
from accounts.models import UserProfile
from accounts.serializers import UserSerializer
from digital_marketing.models import SocialAccountConnection, SocialPost, AdCampaign
from digital_marketing.services.meta_service import MetaService
from digital_marketing.services.twitter_service import TwitterService


class DigitalMarketingTestCase(APITestCase):
    def setUp(self):
        # 1. Superuser
        self.admin_user = User.objects.create_superuser(
            username='admin@marketintel.test',
            email='admin@marketintel.test',
            password='AdminPassword123!'
        )

        # 2. Manager
        self.manager_user = User.objects.create_user(
            username='manager@marketintel.test',
            email='manager@marketintel.test',
            password='ManagerPassword123!'
        )
        self.manager_user.profile.role = 'MANAGER'
        self.manager_user.profile.save()

        # 3. Lead Qualifier (LQ)
        self.lq_user = User.objects.create_user(
            username='lq@marketintel.test',
            email='lq@marketintel.test',
            password='LqPassword123!'
        )
        self.lq_user.profile.role = 'LQ'
        self.lq_user.profile.save()

        # 4. Prospect Research Engineer (PRE)
        self.pre_user = User.objects.create_user(
            username='pre@marketintel.test',
            email='pre@marketintel.test',
            password='PrePassword123!'
        )
        self.pre_user.profile.role = 'PRE'
        self.pre_user.profile.save()

        # 5. Digital Marketing (DM)
        self.dm_user = User.objects.create_user(
            username='dm@marketintel.test',
            email='dm@marketintel.test',
            password='DmPassword123!'
        )
        self.dm_user.profile.role = 'DM'
        self.dm_user.profile.save()

    # ── Requirement 1 & 2: Role serializer and admin user-management assignment ──

    def test_dm_role_accepted_by_serializer(self):
        """Serializer must accept and serialize the DM role correctly."""
        data = {
            'username': 'dm_new@marketintel.test',
            'email': 'dm_new@marketintel.test',
            'role': 'DM',
            'password': 'StrongPassword123!'
        }
        serializer = UserSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save()
        self.assertEqual(user.profile.role, 'DM')
        self.assertEqual(user.profile.get_role_display(), 'Digital Marketing')

    def test_manager_can_create_dm_user(self):
        """Manager can provision a user with Digital Marketing role."""
        self.client.force_authenticate(user=self.manager_user)
        payload = {
            'username': 'created_dm@marketintel.test',
            'email': 'created_dm@marketintel.test',
            'password': 'Password123!',
            'role': 'DM',
        }
        response = self.client.post('/api/auth/users/', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        new_user = User.objects.get(email='created_dm@marketintel.test')
        self.assertEqual(new_user.profile.role, 'DM')

    def test_dm_user_denied_user_management(self):
        """Digital Marketing users must NOT have user-management access."""
        self.client.force_authenticate(user=self.dm_user)
        # Attempt listing users
        res = self.client.get('/api/auth/users/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Attempt creating a user
        res = self.client.post('/api/auth/users/', {
            'username': 'hacked@marketintel.test',
            'email': 'hacked@marketintel.test',
            'role': 'DM',
        }, format='json')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # ── Requirement 5 & 6: Strict RBAC boundaries ──────────────────────────────

    def test_dm_user_denied_crm_endpoints(self):
        """DM user must be blocked from prospects, LQ pipeline, and manager endpoints."""
        self.client.force_authenticate(user=self.dm_user)

        # Prospects
        res = self.client.get('/api/prospects/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # LQ Pipeline
        res = self.client.get('/api/lq-pipeline/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Manager Dashboard
        res = self.client.get('/api/manager-dashboard/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_non_dm_users_denied_digital_marketing_endpoints(self):
        """PRE, LQ, and Manager users without DM role must be blocked from DM APIs."""
        for user in [self.pre_user, self.lq_user, self.manager_user]:
            self.client.force_authenticate(user=user)
            res = self.client.get('/api/digital-marketing/dashboard/')
            self.assertEqual(
                res.status_code,
                status.HTTP_403_FORBIDDEN,
                f"User with role {user.profile.role} was not denied access to DM dashboard"
            )

            res = self.client.get('/api/digital-marketing/instagram/status/')
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

            res = self.client.get('/api/digital-marketing/facebook/status/')
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

            res = self.client.get('/api/digital-marketing/twitter/status/')
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

            res = self.client.get('/api/digital-marketing/ads/overview/')
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # ── Requirement 4, 8 & 9: Digital marketing endpoints & graceful config ────

    def test_dm_user_can_access_modules(self):
        """DM user has access to DM Dashboard and all 4 social & ad modules."""
        self.client.force_authenticate(user=self.dm_user)

        # 1. Dashboard
        res = self.client.get('/api/digital-marketing/dashboard/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('platforms', res.data)

        # 2. Instagram
        res = self.client.get('/api/digital-marketing/instagram/status/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['is_connected'], False)

        # 3. Facebook
        res = self.client.get('/api/digital-marketing/facebook/status/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['is_connected'], False)

        # 4. Twitter / X
        res = self.client.get('/api/digital-marketing/twitter/status/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['is_connected'], False)

        # 5. Ads & Insights
        res = self.client.get('/api/digital-marketing/ads/overview/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('paid_overview', res.data)
        self.assertIn('organic_overview', res.data)

    def test_missing_credentials_report_clear_error(self):
        """When credentials are not configured, clear configuration guidance is returned."""
        self.client.force_authenticate(user=self.dm_user)

        # Ensure environment variables are empty for this test
        old_app_id = os.environ.pop('META_APP_ID', None)
        old_app_sec = os.environ.pop('META_APP_SECRET', None)
        old_tw_id = os.environ.pop('TWITTER_CLIENT_ID', None)
        old_tw_sec = os.environ.pop('TWITTER_CLIENT_SECRET', None)

        try:
            # Instagram status reports not configured
            res = self.client.get('/api/digital-marketing/instagram/status/')
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            self.assertFalse(res.data['is_configured'])
            self.assertIsNotNone(res.data['config_error'])

            # Initiating OAuth URL returns 503 with clear explanation
            res = self.client.get('/api/digital-marketing/instagram/auth-url/')
            self.assertEqual(res.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
            self.assertIn('not configured', res.data.get('error', ''))

            # Twitter status reports not configured
            res = self.client.get('/api/digital-marketing/twitter/status/')
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            self.assertFalse(res.data['is_configured'])

            res = self.client.get('/api/digital-marketing/twitter/auth-url/')
            self.assertEqual(res.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
            self.assertIn('not configured', res.data.get('error', ''))
        finally:
            if old_app_id: os.environ['META_APP_ID'] = old_app_id
            if old_app_sec: os.environ['META_APP_SECRET'] = old_app_sec
            if old_tw_id: os.environ['TWITTER_CLIENT_ID'] = old_tw_id
            if old_tw_sec: os.environ['TWITTER_CLIENT_SECRET'] = old_tw_sec

    def test_oauth_state_and_token_encryption(self):
        """Tokens are stored encrypted and never leaked via status endpoint."""
        conn = SocialAccountConnection.objects.create(
            user=self.dm_user,
            platform='TWITTER',
            account_id='12345678',
            account_username='marketintel_bot',
            account_name='Market Intel Bot',
        )
        conn.set_access_token('secret_access_token_xyz')
        conn.save()

        # Database field is encrypted
        conn.refresh_from_db()
        self.assertNotEqual(conn.access_token_encrypted, 'secret_access_token_xyz')
        self.assertEqual(conn.get_access_token(), 'secret_access_token_xyz')

        # API status endpoint NEVER leaks access token or encrypted ciphertext
        self.client.force_authenticate(user=self.dm_user)
        res = self.client.get('/api/digital-marketing/twitter/status/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['is_connected'])
        acc_data = res.data['account']
        self.assertNotIn('access_token', acc_data)
        self.assertNotIn('access_token_encrypted', acc_data)
        self.assertNotIn('secret_access_token_xyz', str(res.data))
