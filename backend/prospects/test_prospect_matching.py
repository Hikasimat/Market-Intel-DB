import email.utils
from unittest import mock
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import GoogleMailCredentials, UserProfile
from accounts.oauth_services import GmailOAuthService
from prospects.matching_service import ProspectMatcher, extract_clean_email
from prospects.models import Prospect, ProspectContact, LeadQualification

User = get_user_model()


class ProspectMatchingTests(TestCase):
    def setUp(self):
        # Create manager user
        self.manager = User.objects.create_user(username='manager_user', email='manager@example.com', password='pass')
        mgr_p = self.manager.profile
        mgr_p.role = 'MANAGER'
        mgr_p.save()

        # Create LQ user 1
        self.lq1 = User.objects.create_user(username='lq1_user', email='lq1@example.com', password='pass')
        lq1_p = self.lq1.profile
        lq1_p.role = 'LQ'
        lq1_p.save()

        # Create LQ user 2
        self.lq2 = User.objects.create_user(username='lq2_user', email='lq2@example.com', password='pass')
        lq2_p = self.lq2.profile
        lq2_p.role = 'LQ'
        lq2_p.save()

        # Create credentials for lq1
        self.creds_lq1 = GoogleMailCredentials.objects.create(
            user=self.lq1,
            email='lq1@example.com',
            access_token_encrypted='dummy_token',
            is_active=True,
        )

        # Company 1 (Assigned to lq1)
        self.prospect1 = Prospect.objects.create(
            company_name='Example Technologies',
            country_head_office='India',
            complete_address='Bangalore Tech Park',
            official_email_address='contact@example.com',
            primary_industries='IT Services',
            company_structure='Parent',
            operational_status='Active',
            primary_offering_type='Services',
        )
        self.lq_rel1 = self.prospect1.lead_qualification
        self.lq_rel1.assigned_lq = self.lq1
        self.lq_rel1.qualification_status = 'Hot Lead'
        self.lq_rel1.save()

        self.contact1 = ProspectContact.objects.create(
            prospect=self.prospect1,
            contact_name='Priya Sharma',
            designation='CTO',
            official_email='priya@example.com',
        )

        # Company 2 (Assigned to lq2)
        self.prospect2 = Prospect.objects.create(
            company_name='Global Dynamics',
            country_head_office='USA',
            complete_address='Silicon Valley',
            official_email_address='info@globaldynamics.com',
            primary_industries='Software',
            company_structure='Parent',
            operational_status='Active',
            primary_offering_type='Solutions',
        )
        self.lq_rel2 = self.prospect2.lead_qualification
        self.lq_rel2.assigned_lq = self.lq2
        self.lq_rel2.qualification_status = 'Qualified'
        self.lq_rel2.save()

    def test_company_official_email_matches_correct_company(self):
        """Test 1: A company's official email matches the correct company."""
        matcher = ProspectMatcher(self.lq1)
        match = matcher.match_address('contact@example.com')

        self.assertTrue(match['prospect_match'])
        self.assertEqual(match['prospect_match_type'], 'company')
        self.assertEqual(match['prospect_company_name'], 'Example Technologies')
        self.assertEqual(match['prospect_id'], str(self.prospect1.id))
        self.assertIsNone(match['prospect_contact_name'])

    def test_key_person_official_email_matches_correct_person_and_company(self):
        """Test 2: A key person's official email matches the correct key person and parent company."""
        matcher = ProspectMatcher(self.lq1)
        match = matcher.match_address('priya@example.com')

        self.assertTrue(match['prospect_match'])
        self.assertEqual(match['prospect_match_type'], 'key_person')
        self.assertEqual(match['prospect_company_name'], 'Example Technologies')
        self.assertEqual(match['prospect_contact_name'], 'Priya Sharma')
        self.assertEqual(match['prospect_contact_id'], str(self.contact1.id))

    def test_both_tags_appear_for_key_person_match(self):
        """Test 3: Both company tag and key-person tag appear for a key-person match."""
        matcher = ProspectMatcher(self.lq1)
        match = matcher.match_address('priya@example.com')

        tags = match['prospect_tags']
        self.assertEqual(len(tags), 2)
        tag_types = [t['type'] for t in tags]
        self.assertIn('company', tag_types)
        self.assertIn('key_person', tag_types)

    def test_company_only_match_does_not_invent_key_person(self):
        """Test 4: Company-only matches do not invent a key-person name."""
        matcher = ProspectMatcher(self.lq1)
        match = matcher.match_address('contact@example.com')

        self.assertEqual(match['prospect_match_type'], 'company')
        self.assertIsNone(match['prospect_contact_name'])
        self.assertIsNone(match['prospect_contact_id'])
        self.assertEqual(len(match['prospect_tags']), 1)
        self.assertEqual(match['prospect_tags'][0]['type'], 'company')

    def test_comparisons_work_regardless_of_capitalization(self):
        """Test 5: Comparisons work regardless of email-address capitalization."""
        matcher = ProspectMatcher(self.lq1)
        match1 = matcher.match_address('Priya@Example.COM')
        match2 = matcher.match_address('CONTACT@example.com')

        self.assertTrue(match1['prospect_match'])
        self.assertEqual(match1['prospect_contact_name'], 'Priya Sharma')

        self.assertTrue(match2['prospect_match'])
        self.assertEqual(match2['prospect_company_name'], 'Example Technologies')

    def test_display_names_in_from_headers_parsed_correctly(self):
        """Test 6: Display names in RFC From headers are parsed reliably."""
        header1 = 'Priya Sharma <priya@example.com>'
        header2 = '"Official Desk" <contact@example.com>'

        matcher = ProspectMatcher(self.lq1)
        match1 = matcher.match_address(header1)
        match2 = matcher.match_address(header2)

        self.assertTrue(match1['prospect_match'])
        self.assertEqual(match1['prospect_contact_name'], 'Priya Sharma')

        self.assertTrue(match2['prospect_match'])
        self.assertEqual(match2['prospect_company_name'], 'Example Technologies')

    def test_recipient_email_does_not_determine_inbound_sender_identity(self):
        """Test 7: The recipient's email does not determine inbound sender's identity."""
        matcher = ProspectMatcher(self.lq1)
        # Random external sender emailing our prospect's contact address
        inbound_from = 'spammer@random.com'
        match = matcher.match_address(inbound_from)

        self.assertFalse(match['prospect_match'])
        self.assertIsNone(match['prospect_company_name'])

    def test_unknown_senders_remain_ordinary_messages(self):
        """Test 8: Unknown senders remain ordinary messages with prospect_match=False."""
        matcher = ProspectMatcher(self.lq1)
        match = matcher.match_address('stranger@unrelateddomain.org')

        self.assertFalse(match['prospect_match'])
        self.assertIsNone(match['prospect_match_type'])
        self.assertEqual(len(match['prospect_tags']), 0)

    def test_missing_and_malformed_sender_headers_do_not_crash(self):
        """Test 9: Missing and malformed sender addresses do not crash matcher."""
        matcher = ProspectMatcher(self.lq1)

        self.assertFalse(matcher.match_address(None)['prospect_match'])
        self.assertFalse(matcher.match_address('')['prospect_match'])
        self.assertFalse(matcher.match_address('Not An Email')['prospect_match'])
        self.assertFalse(matcher.match_address('<<>>')['prospect_match'])

    def test_ambiguous_matches_do_not_display_misleading_names(self):
        """Test 10: Conflicting companies sharing the same email are flagged ambiguous."""
        # Create two different companies sharing an identical official email address
        p_a = Prospect.objects.create(
            company_name='Company Alpha',
            official_email_address='shared@example.com',
            country_head_office='US',
            primary_industries='IT',
            company_structure='Parent',
            operational_status='Active',
            primary_offering_type='Products',
        )
        p_b = Prospect.objects.create(
            company_name='Company Beta',
            official_email_address='shared@example.com',
            country_head_office='UK',
            primary_industries='Finance',
            company_structure='Parent',
            operational_status='Active',
            primary_offering_type='Services',
        )

        matcher = ProspectMatcher(self.manager)
        match = matcher.match_address('shared@example.com')

        # Must flag ambiguous and avoid attributing to the wrong company
        self.assertFalse(match['prospect_match'])
        self.assertTrue(match['ambiguous'])
        self.assertIsNone(match['prospect_company_name'])

    def test_lq_assignment_and_manager_visibility_respected(self):
        """Test 11: LQ distribution scoping is strictly respected."""
        # LQ1 should NOT match Company 2 (assigned to LQ2)
        matcher_lq1 = ProspectMatcher(self.lq1)
        match_lq1 = matcher_lq1.match_address('info@globaldynamics.com')
        self.assertFalse(match_lq1['prospect_match'])

        # Manager should match both Company 1 and Company 2
        matcher_mgr = ProspectMatcher(self.manager)
        match_mgr1 = matcher_mgr.match_address('priya@example.com')
        match_mgr2 = matcher_mgr.match_address('info@globaldynamics.com')

        self.assertTrue(match_mgr1['prospect_match'])
        self.assertEqual(match_mgr1['prospect_company_name'], 'Example Technologies')

        self.assertTrue(match_mgr2['prospect_match'])
        self.assertEqual(match_mgr2['prospect_company_name'], 'Global Dynamics')

    @mock.patch('accounts.oauth_services.GmailOAuthService.fetch_messages')
    def test_prospect_responses_endpoint(self, mock_fetch):
        """Test 12: Dedicated prospect-responses endpoint returns only matched responses."""
        mock_fetch.return_value = {
            'messages': [
                {
                    'id': 'msg_1',
                    'from': 'Priya Sharma <priya@example.com>',
                    'subject': 'Proposal review',
                    'prospect_match': True,
                    'prospect_company_name': 'Example Technologies',
                    'prospect_contact_name': 'Priya Sharma',
                },
                {
                    'id': 'msg_2',
                    'from': 'newsletter@spam.com',
                    'subject': 'Discount',
                    'prospect_match': False,
                    'prospect_company_name': None,
                }
            ],
            'emails': [],
            'partial': False,
        }

        client = APIClient()
        client.force_authenticate(user=self.lq1)

        res = client.get('/api/auth/mail-account/prospect-responses/')
        self.assertEqual(res.status_code, 200)
        messages = res.data.get('messages', [])
        # Only matched message 1 should be included
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]['id'], 'msg_1')
        self.assertEqual(messages[0]['prospect_company_name'], 'Example Technologies')
