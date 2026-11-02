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

    # ── Native Market Intel CMS Test Cases (Requirements 1 - 5) ───────────────

    def test_native_cms_overview_bootstrapping(self):
        """Native CMS bootstraps cleanly in Market Intel DB and returns status."""
        self.client.force_authenticate(user=self.dm_user)
        res = self.client.get('/api/digital-marketing/cms/overview/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['engine'], 'Market Intel Native CMS')
        self.assertIn('integrations', res.data)
        self.assertIn('google_analytics', res.data['integrations'])
        self.assertIn('google_search_console', res.data['integrations'])
        self.assertIn('bing_webmaster', res.data['integrations'])
        self.assertIn('google_ads', res.data['integrations'])

    def test_cms_pages_crud_and_sitemap(self):
        """CMS website pages can be created, edited, and listed in XML sitemap."""
        self.client.force_authenticate(user=self.dm_user)

        # 1. Create page
        page_payload = {
            'title': 'Test CMS Feature Article',
            'slug': 'test-cms-feature-article',
            'page_path': '/insights/test-cms-feature',
            'page_type': 'ARTICLE',
            'status': 'PUBLISHED',
            'summary': 'Test summary',
            'content': '# Content',
            'include_in_sitemap': True,
            'sitemap_priority': '0.9',
        }
        res = self.client.post('/api/digital-marketing/cms/pages/', page_payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        page_id = res.data['page']['id']
        self.assertTrue(res.data['page']['page_id'].startswith('PAGE-'))

        # 2. Patch page
        res = self.client.patch(f'/api/digital-marketing/cms/pages/{page_id}/', {'status': 'DRAFT'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['page']['status'], 'DRAFT')

        # 3. XML Sitemap endpoint
        res = self.client.get('/api/digital-marketing/cms/sitemap.xml?format=json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('xml', res.data)
        self.assertIn('<urlset', res.data['xml'])

    def test_google_analytics_config_and_dashboard(self):
        """GA Page ID configuration, tracking code generation, and statistics dashboard."""
        self.client.force_authenticate(user=self.dm_user)

        # 1. Read config & generated snippet
        res = self.client.get('/api/digital-marketing/cms/analytics/config/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('tracking_code', res.data)
        self.assertIn('gtag(\'config\',', res.data['tracking_code'])

        # 2. Update Page ID configuration
        update_payload = {
            'page_id': 'G-CUSTOMTEST99',
            'property_id': '99887766',
            'track_pageviews': True,
            'track_outbound_clicks': True,
        }
        res = self.client.put('/api/digital-marketing/cms/analytics/config/', update_payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['config']['page_id'], 'G-CUSTOMTEST99')
        self.assertIn('G-CUSTOMTEST99', res.data['tracking_code'])

        # 3. Analytics Dashboard
        res = self.client.get('/api/digital-marketing/cms/analytics/dashboard/?range=30d')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('summary', res.data)
        self.assertIn('page_statistics', res.data)
        self.assertIn('traffic_sources', res.data)

        # 4. Record new page statistic entry
        stat_payload = {
            'page_id': 'PAGE-TEST-001',
            'page_path': '/test-path',
            'page_title': 'Test Page Title',
            'page_views': 120,
            'unique_visitors': 95,
            'sessions': 105,
        }
        res = self.client.post('/api/digital-marketing/cms/analytics/dashboard/', stat_payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_google_search_console_features(self):
        """GSC domain registration, verification, sitemap, indexing requests, and dashboard."""
        self.client.force_authenticate(user=self.dm_user)

        # 1. Dashboard
        res = self.client.get('/api/digital-marketing/cms/search-console/dashboard/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('summary', res.data)
        self.assertIn('domains', res.data)
        self.assertIn('sitemaps', res.data)

        # 2. Register domain
        reg_payload = {
            'domain': 'app.marketintel.test',
            'property_type': 'DOMAIN',
            'verification_method': 'DNS_TXT',
        }
        res = self.client.post('/api/digital-marketing/cms/search-console/domains/', reg_payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        dom_id = res.data['domain']['id']
        self.assertTrue(res.data['domain']['verification_token'])

        # 3. Verify domain
        res = self.client.post(f'/api/digital-marketing/cms/search-console/domains/{dom_id}/verify/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['domain']['is_verified'])

        # 4. Submit Sitemap
        sitemap_res = self.client.post(
            '/api/digital-marketing/cms/search-console/sitemaps/',
            {'sitemap_url': 'https://app.marketintel.test/sitemap.xml'},
            format='json'
        )
        self.assertEqual(sitemap_res.status_code, status.HTTP_201_CREATED)

        # 5. URL Inspection & Indexing submission
        inspect_res = self.client.get('/api/digital-marketing/cms/search-console/indexing/?inspect_url=https://marketintel.hikasimat.com/solutions/prospect-database')
        self.assertEqual(inspect_res.status_code, status.HTTP_200_OK)
        self.assertTrue(inspect_res.data['inspected'])

        index_sub_res = self.client.post(
            '/api/digital-marketing/cms/search-console/indexing/',
            {'page_url': 'https://marketintel.hikasimat.com/pricing', 'action_type': 'URL_UPDATED'},
            format='json'
        )
        self.assertEqual(index_sub_res.status_code, status.HTTP_201_CREATED)

    def test_bing_webmaster_tools_features(self):
        """Bing Webmaster Tools config, verification, IndexNow submission, and sitemaps."""
        self.client.force_authenticate(user=self.dm_user)

        # 1. Dashboard
        res = self.client.get('/api/digital-marketing/cms/bing/dashboard/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('config', res.data)
        self.assertIn('summary', res.data)

        # 2. Update Bing Config & Verify
        res = self.client.put(
            '/api/digital-marketing/cms/bing/config/',
            {'api_key': 'BING-KEY-ABC-123', 'verify_site': True},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['config']['has_api_key'])
        self.assertTrue(res.data['config']['is_verified'])

        # 3. Submit URLs via IndexNow
        res = self.client.post(
            '/api/digital-marketing/cms/bing/indexing/',
            {'urls': 'https://marketintel.hikasimat.com/pricing', 'submission_protocol': 'INDEXNOW'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(res.data['submissions']), 1)

        # 4. Submit Bing Sitemap
        res = self.client.post(
            '/api/digital-marketing/cms/bing/sitemaps/',
            {'sitemap_url': 'https://marketintel.hikasimat.com/sitemap.xml'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

    def test_google_ads_features(self):
        """Google Ads account config, campaigns, ad groups, keywords, budget mutation, and audit trail."""
        self.client.force_authenticate(user=self.dm_user)

        # 1. Dashboard
        res = self.client.get('/api/digital-marketing/cms/google-ads/dashboard/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('summary', res.data)
        self.assertIn('campaigns', res.data)
        self.assertIn('ad_groups', res.data)
        self.assertIn('keywords', res.data)
        self.assertIn('audit_logs', res.data)

        # 2. Update Account Config
        res = self.client.put(
            '/api/digital-marketing/cms/google-ads/config/',
            {'customer_id': '111-222-3333', 'account_name': 'Test Google Ads Account'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['config']['customer_id'], '111-222-3333')

        # 3. Create Campaign
        camp_payload = {
            'name': 'New Q1 Target Search Campaign',
            'channel_type': 'SEARCH',
            'daily_budget': '80.00',
            'bidding_strategy': 'MAXIMIZE_CONVERSIONS',
        }
        res = self.client.post('/api/digital-marketing/cms/google-ads/campaigns/', camp_payload, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        camp_id = res.data['campaign']['id']

        # 4. Pause Campaign
        res = self.client.patch(f'/api/digital-marketing/cms/google-ads/campaigns/{camp_id}/', {'status': 'PAUSED'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['campaign']['status'], 'PAUSED')

        # 5. Update Daily Budget
        res = self.client.patch(f'/api/digital-marketing/cms/google-ads/campaigns/{camp_id}/', {'daily_budget': '95.00'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(str(res.data['campaign']['daily_budget']), '95.00')

        # 6. Create Ad Group
        ag_res = self.client.post(
            '/api/digital-marketing/cms/google-ads/ad-groups/',
            {'campaign': camp_id, 'name': 'Test Ad Group 1', 'cpc_bid': '2.40'},
            format='json'
        )
        self.assertEqual(ag_res.status_code, status.HTTP_201_CREATED)
        ag_id = ag_res.data['ad_group']['id']

        # 7. Create Keyword
        kw_res = self.client.post(
            '/api/digital-marketing/cms/google-ads/keywords/',
            {'ad_group': ag_id, 'keyword_text': 'b2b corporate intelligence', 'match_type': 'PHRASE', 'cpc_bid': '2.10'},
            format='json'
        )
        self.assertEqual(kw_res.status_code, status.HTTP_201_CREATED)

        # 8. Check that mutation audit log recorded the operations
        res = self.client.get('/api/digital-marketing/cms/google-ads/dashboard/')
        self.assertTrue(any(l['resource_name'] == 'New Q1 Target Search Campaign' for l in res.data['audit_logs']))

    # ── Requirement 8: Manager Role Delete User Permission ────────────────────

    def test_manager_can_delete_regular_user(self):
        """Manager must be able to delete a regular user."""
        regular_user = User.objects.create_user(
            username='temp_regular@marketintel.test',
            email='temp_regular@marketintel.test',
            password='Password123!'
        )
        regular_user.profile.role = 'PRE'
        regular_user.profile.save()

        self.client.force_authenticate(user=self.manager_user)
        res = self.client.delete(f'/api/auth/users/{regular_user.id}/')
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(id=regular_user.id).exists())

    def test_manager_cannot_delete_superuser(self):
        """Manager must NOT be allowed to delete a Super Admin user."""
        self.client.force_authenticate(user=self.manager_user)
        res = self.client.delete(f'/api/auth/users/{self.admin_user.id}/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(User.objects.filter(id=self.admin_user.id).exists())

    def test_manager_cannot_delete_themselves(self):
        """Manager must NOT be allowed to delete their own account."""
        self.client.force_authenticate(user=self.manager_user)
        res = self.client.delete(f'/api/auth/users/{self.manager_user.id}/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(User.objects.filter(id=self.manager_user.id).exists())

    # ── Real-Time Google Products Integration Tests ───────────────────────────

    def test_realtime_analytics_collect_and_realtime_dashboard(self):
        """Live hit collection via /analytics/collect/ and real-time active users."""
        collect_res = self.client.post('/api/digital-marketing/cms/analytics/collect/', {
            'page_path': '/insights/2026-apac-corporate-ma-report',
            'page_id': 'PAGE-BLOG-003',
            'page_title': '2026 APAC Corporate M&A Report',
            'visitor_id': 'test-visitor-8849',
            'traffic_source': 'Direct Live Ping',
            'device_category': 'Desktop',
            'country': 'United States',
        })
        self.assertEqual(collect_res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(collect_res.data['status'], 'ok')
        self.assertEqual(collect_res.data['visitor_id'], 'test-visitor-8849')

        self.client.force_authenticate(user=self.dm_user)
        realtime_res = self.client.get('/api/digital-marketing/cms/analytics/realtime/')
        self.assertEqual(realtime_res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(realtime_res.data['active_users_5m'], 1)
        self.assertGreaterEqual(realtime_res.data['page_views_30m'], 1)
        self.assertTrue(any(h['visitor_id'] == 'test-visitor-8849' for h in realtime_res.data['recent_hits']))

    def test_google_cms_status_and_auth_url(self):
        """Google products unified OAuth status and consent URL generation."""
        self.client.force_authenticate(user=self.dm_user)
        status_res = self.client.get('/api/digital-marketing/cms/google/status/')
        self.assertEqual(status_res.status_code, status.HTTP_200_OK)
        self.assertIn('google_analytics', status_res.data)
        self.assertIn('search_console', status_res.data)
        self.assertIn('google_ads', status_res.data)

        auth_url_res = self.client.get('/api/digital-marketing/cms/google/auth-url/')
        self.assertEqual(auth_url_res.status_code, status.HTTP_200_OK)
        self.assertIn('accounts.google.com', auth_url_res.data['url'])
        self.assertIn('analytics.readonly', auth_url_res.data['url'])
        self.assertIn('webmasters.readonly', auth_url_res.data['url'])
        self.assertIn('adwords', auth_url_res.data['url'])

    def test_cms_overview_contains_real_metrics(self):
        """Overview endpoint returns genuine database aggregates with real-time counters."""
        self.client.force_authenticate(user=self.dm_user)
        res = self.client.get('/api/digital-marketing/cms/overview/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn('integrations', res.data)
        self.assertIn('active_users_now', res.data['integrations']['google_analytics'])
        self.assertIsInstance(res.data['integrations']['google_analytics']['total_page_views'], int)
        self.assertIsInstance(res.data['integrations']['google_search_console']['total_clicks'], int)
        self.assertIsInstance(res.data['integrations']['bing_webmaster']['total_clicks'], int)
        self.assertIsInstance(res.data['integrations']['google_ads']['total_spend'], (int, float))

