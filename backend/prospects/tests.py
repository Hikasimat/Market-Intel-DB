from datetime import timedelta
from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from .models import Prospect, ProspectImportHistory, EmailVerification, LeadQualification
from .serializers import ProspectSerializer
from .import_services import (
    ImportItem, analyze_items, build_preview, group_rows, import_single_row,
    run_import, read_import_file, ImportFileError, RowImportError, MAX_IMPORT_ROWS,
    STATUS_EXISTS_IN_DB, STATUS_FOUND_IN_FILE,
)
import io
import csv

User = get_user_model()

class ProspectImportServicesTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.factory = RequestFactory()
        self.request = self.factory.post('/')
        self.request.user = self.user

    # 1. 100-row limit enforcement
    def test_max_row_limit(self):
        # Create CSV with MAX_IMPORT_ROWS + 5 rows
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(['company_name'])
        for i in range(MAX_IMPORT_ROWS + 5):
            writer.writerow([f'Company {i}'])
        
        file = SimpleUploadedFile("test.csv", out.getvalue().encode('utf-8'))
        headers, rows, limit_reached = read_import_file(file, max_rows=MAX_IMPORT_ROWS)
        self.assertEqual(len(rows), MAX_IMPORT_ROWS)
        self.assertTrue(limit_reached)

    # 2. Grouping rows with same normalized company name is covered inherently by run_import setup

    def _create_row_payload(self, name, row_num=1, parents=None, email='test@test.com', structure='Parent'):
        return {
            'source_row_numbers': [row_num],
            'data': {
                'company_name': name,
                'country_head_office': 'USA',
                'company_structure': structure,
                'operational_status': 'Active',
                'ownership_sector': 'Private Company',
                'primary_offering_type': 'Products',
                'primary_industries': 'Tech',
                'complete_address': '123 Test St',
                'parent_company_names': parents or '',
                'official_email_address': email
            },
            'emails_to_verify': [{'email': email, 'status': 'VALID', 'type': 'company'}]
        }

    # 3. Best-effort import & Failure Isolation
    def test_failure_isolation(self):
        rows = [
            self._create_row_payload('Valid 1', 1, email='v1@test.com'),
            self._create_row_payload('Invalid 1', 2, email='invalid'), # fails validation
            self._create_row_payload('Valid 2', 3, email='v2@test.com'),
        ]
        # Make Invalid 1 fail validation by passing empty country
        rows[1]['data']['country_head_office'] = ''

        res = run_import(rows, self.request, ProspectSerializer)
        self.assertEqual(res['imported_count'], 2)
        self.assertEqual(res['not_imported_count'], 1)
        self.assertEqual(Prospect.objects.count(), 2)

    # 4. Parent resolution: parents before children
    def test_parent_before_child(self):
        rows = [
            self._create_row_payload('Child', 1, parents='Parent', structure='Subsidiary', email='c@test.com'),
            self._create_row_payload('Parent', 2, email='p@test.com'),
        ]
        res = run_import(rows, self.request, ProspectSerializer)
        self.assertEqual(res['imported_count'], 2)
        parent = Prospect.objects.get(company_name='Parent')
        child = Prospect.objects.get(company_name='Child')
        self.assertIn(parent, child.parent_companies.all())

    # 5. 3-level depth resolution
    def test_3_level_depth(self):
        rows = [
            self._create_row_payload('Grandchild', 1, parents='Child', structure='Subsidiary', email='gc@test.com'),
            self._create_row_payload('Child', 2, parents='Parent', structure='Subsidiary', email='c@test.com'),
            self._create_row_payload('Parent', 3, email='p@test.com'),
        ]
        res = run_import(rows, self.request, ProspectSerializer)
        self.assertEqual(res['imported_count'], 3)
        gc = Prospect.objects.get(company_name='Grandchild')
        self.assertEqual(gc.parent_companies.first().company_name, 'Child')
        c = Prospect.objects.get(company_name='Child')
        self.assertEqual(c.parent_companies.first().company_name, 'Parent')

    # 6. Circular dependencies rejection
    def test_circular_dependency(self):
        rows = [
            self._create_row_payload('A', 1, parents='B', structure='Subsidiary', email='a@test.com'),
            self._create_row_payload('B', 2, parents='C', structure='Subsidiary', email='b@test.com'),
            self._create_row_payload('C', 3, parents='A', structure='Subsidiary', email='c@test.com'),
            self._create_row_payload('Independent', 4, email='ind@test.com')
        ]
        res = run_import(rows, self.request, ProspectSerializer)
        self.assertEqual(res['imported_count'], 1)
        self.assertEqual(res['not_imported_count'], 3)
        self.assertEqual(Prospect.objects.count(), 1)
        self.assertEqual(Prospect.objects.first().company_name, 'Independent')

    # 7. Self-referencing circular dependency
    def test_self_circular(self):
        rows = [
            self._create_row_payload('Self', 1, parents='Self', structure='Subsidiary', email='s@test.com'),
        ]
        res = run_import(rows, self.request, ProspectSerializer)
        self.assertEqual(res['imported_count'], 0)
        self.assertEqual(res['not_imported_count'], 1)

    # 8. Missing parent rejection
    def test_missing_parent(self):
        rows = [
            self._create_row_payload('Child', 1, parents='Missing', structure='Subsidiary', email='c@test.com'),
        ]
        res = run_import(rows, self.request, ProspectSerializer)
        self.assertEqual(res['imported_count'], 0)
        self.assertEqual(res['not_imported_count'], 1)

    # 9. Exact normalized matching
    def test_normalized_matching(self):
        rows = [
            self._create_row_payload('   My Company  ', 1, email='m@test.com'),
            self._create_row_payload('Child', 2, parents='my  company', structure='Subsidiary', email='c@test.com'),
        ]
        res = run_import(rows, self.request, ProspectSerializer)
        self.assertEqual(res['imported_count'], 2)
        c = Prospect.objects.get(company_name='Child')
        self.assertEqual(c.parent_companies.first().company_name, '   My Company  ')

    # 10. Required email verification VALID status
    def test_email_must_be_valid(self):
        row = self._create_row_payload('Test', 1, email='t@test.com')
        row['emails_to_verify'][0]['status'] = 'UNVERIFIED' # Not VALID
        res = run_import([row], self.request, ProspectSerializer)
        self.assertEqual(res['imported_count'], 0)
        self.assertIn("is not verified as VALID", res['not_imported_rows'][0]['reason'])

    # 11. History is created and stored correctly
    def test_history_creation(self):
        rows = [self._create_row_payload('Test', 1, email='t@test.com')]
        res = run_import(rows, self.request, ProspectSerializer, file_name='test.csv')
        self.assertIsNotNone(res['import_history_id'])
        history = ProspectImportHistory.objects.get(id=res['import_history_id'])
        self.assertEqual(history.status, 'COMPLETED')
        self.assertEqual(history.imported_count, 1)
        self.assertEqual(history.file_name, 'test.csv')

    # 12. LQ assignment trigger
    def test_lq_assignment(self):
        rows = [self._create_row_payload('Test', 1, email='t@test.com')]
        run_import(rows, self.request, ProspectSerializer)
        prospect = Prospect.objects.get(company_name='Test')
        self.assertTrue(LeadQualification.objects.filter(prospect=prospect).exists())

    # 13. Duplicate checking against DB
    def test_db_duplicate(self):
        Prospect.objects.create(
            company_name='Existing',
            country_head_office='USA',
            company_structure='Parent',
            operational_status='Active',
            primary_offering_type='Products'
        )
        rows = [self._create_row_payload('Existing', 1, email='e@test.com')]
        res = run_import(rows, self.request, ProspectSerializer)
        self.assertEqual(res['imported_count'], 0)
        self.assertEqual(res['not_imported_count'], 1)

    # 14. Multiple parents
    def test_multiple_parents(self):
        rows = [
            self._create_row_payload('P1', 1, email='p1@test.com'),
            self._create_row_payload('P2', 2, email='p2@test.com'),
            self._create_row_payload('Child', 3, parents='P1; P2', structure='Subsidiary', email='c@test.com'),
        ]
        res = run_import(rows, self.request, ProspectSerializer)
        self.assertEqual(res['imported_count'], 3)
        child = Prospect.objects.get(company_name='Child')
        parents = [p.company_name for p in child.parent_companies.all()]
        self.assertIn('P1', parents)
        self.assertIn('P2', parents)

    # 15. Transaction rollback on serializer error but sibling success
    def test_transaction_rollback_partial(self):
        rows = [
            self._create_row_payload('Good', 1, email='good@test.com'),
            self._create_row_payload('Bad Parent', 2, email='bad@test.com'),
            self._create_row_payload('Bad Child', 3, parents='Bad Parent', structure='Subsidiary', email='bc@test.com'),
        ]
        # Sabotage Bad Parent at serializer level by making its structure invalid
        rows[1]['data']['company_structure'] = 'InvalidStruct'

        res = run_import(rows, self.request, ProspectSerializer)
        self.assertEqual(res['imported_count'], 1)
        self.assertEqual(res['not_imported_count'], 2)
        # Good should be saved
        self.assertTrue(Prospect.objects.filter(company_name='Good').exists())
        # Bad Parent should be rolled back
        self.assertFalse(Prospect.objects.filter(company_name='Bad Parent').exists())
        # Bad Child should fail because its parent failed
        self.assertFalse(Prospect.objects.filter(company_name='Bad Child').exists())


class ProspectListFilterAndNavigationTests(APITestCase):
    def setUp(self):
        self.pre1 = User.objects.create_user(username='pre_nav_1', password='p')
        self.pre1.profile.role = 'PRE'
        self.pre1.profile.save()

        self.pre2 = User.objects.create_user(username='pre_nav_2', password='p')
        self.pre2.profile.role = 'PRE'
        self.pre2.profile.save()

        self.manager = User.objects.create_user(username='mgr_nav', password='p')
        self.manager.profile.role = 'MANAGER'
        self.manager.profile.save()

        now = timezone.now()
        self.p_parent = Prospect.objects.create(
            company_name='Alpha Parent Co',
            country_head_office='UAE',
            complete_address='Dubai',
            official_phone_number='+971-4-111-1111',
            official_email_address='info@alphaparent.com',
            primary_industries='Construction',
            company_structure='Parent',
            operational_status='Active',
            primary_offering_type='Products',
            created_by=self.pre1.username,
        )
        self.p_branch = Prospect.objects.create(
            company_name='Beta Branch Co',
            country_head_office='KSA',
            complete_address='Riyadh',
            official_phone_number='+966-11-222-2222',
            official_email_address='contact@betabranch.com',
            primary_industries='Engineering',
            company_structure='Branch',
            operational_status='Active',
            primary_offering_type='Services',
            created_by=self.pre1.username,
        )
        self.p_sub = Prospect.objects.create(
            company_name='Gamma Subsidiary Co',
            country_head_office='Qatar',
            complete_address='Doha',
            official_phone_number='+974-4-333-3333',
            official_email_address='hello@gammasub.com',
            primary_industries='Manufacturing',
            company_structure='Subsidiary',
            operational_status='Active',
            primary_offering_type='Solutions',
            created_by=self.pre1.username,
        )
        self.p_other = Prospect.objects.create(
            company_name='Other User Prospect',
            country_head_office='Oman',
            complete_address='Muscat',
            official_phone_number='+968-2-444-4444',
            official_email_address='sales@otheruser.com',
            primary_industries='Logistics',
            company_structure='Parent',
            operational_status='Active',
            primary_offering_type='Products',
            created_by=self.pre2.username,
        )

        # Deterministic ordering (-updated_at, -id): p_parent (newest), p_branch (middle), p_sub (oldest for pre1), p_other (oldest overall)
        Prospect.objects.filter(pk=self.p_parent.pk).update(updated_at=now)
        Prospect.objects.filter(pk=self.p_branch.pk).update(updated_at=now - timedelta(minutes=1))
        Prospect.objects.filter(pk=self.p_sub.pk).update(updated_at=now - timedelta(minutes=2))
        Prospect.objects.filter(pk=self.p_other.pk).update(updated_at=now - timedelta(minutes=3))

    def test_list_includes_company_contact_fields_and_filters_by_structure(self):
        self.client.force_authenticate(user=self.pre1)
        res = self.client.get('/api/prospects/', {'company_structure': 'Branch'})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.data['results'] if isinstance(res.data, dict) and 'results' in res.data else res.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], str(self.p_branch.id))
        self.assertEqual(results[0]['official_phone_number'], '+966-11-222-2222')
        self.assertEqual(results[0]['official_email_address'], 'contact@betabranch.com')

    def test_navigation_returns_previous_and_next_for_pre_and_respects_filters(self):
        self.client.force_authenticate(user=self.pre1)

        res_first = self.client.get(f'/api/prospects/{self.p_parent.id}/navigation/')
        self.assertEqual(res_first.status_code, status.HTTP_200_OK)
        self.assertEqual(res_first.data, {
            'previous_id': None,
            'next_id': str(self.p_branch.id),
            'current_index': 1,
            'total_count': 3,
        })

        res_mid = self.client.get(f'/api/prospects/{self.p_branch.id}/navigation/')
        self.assertEqual(res_mid.status_code, status.HTTP_200_OK)
        self.assertEqual(res_mid.data, {
            'previous_id': str(self.p_parent.id),
            'next_id': str(self.p_sub.id),
            'current_index': 2,
            'total_count': 3,
        })

        res_last = self.client.get(f'/api/prospects/{self.p_sub.id}/navigation/')
        self.assertEqual(res_last.status_code, status.HTTP_200_OK)
        self.assertEqual(res_last.data, {
            'previous_id': str(self.p_branch.id),
            'next_id': None,
            'current_index': 3,
            'total_count': 3,
        })

        # PRE cannot access another user's prospect
        res_other = self.client.get(f'/api/prospects/{self.p_other.id}/navigation/')
        self.assertEqual(res_other.status_code, status.HTTP_404_NOT_FOUND)

        # Filtering by company_structure narrows navigation set
        res_filtered = self.client.get(
            f'/api/prospects/{self.p_branch.id}/navigation/',
            {'company_structure': 'Branch'}
        )
        self.assertEqual(res_filtered.status_code, status.HTTP_200_OK)
        self.assertEqual(res_filtered.data, {
            'previous_id': None,
            'next_id': None,
            'current_index': 1,
            'total_count': 1,
        })

        # Filtering by search narrows navigation set
        res_search = self.client.get(
            f'/api/prospects/{self.p_sub.id}/navigation/',
            {'search': 'Gamma'}
        )
        self.assertEqual(res_search.status_code, status.HTTP_200_OK)
        self.assertEqual(res_search.data['total_count'], 1)

        # Fallback to unfiltered RBAC list if opened record does not match stale filter
        res_fallback = self.client.get(
            f'/api/prospects/{self.p_parent.id}/navigation/',
            {'company_structure': 'Branch'}
        )
        self.assertEqual(res_fallback.status_code, status.HTTP_200_OK)
        self.assertEqual(res_fallback.data, {
            'previous_id': None,
            'next_id': str(self.p_branch.id),
            'current_index': 1,
            'total_count': 3,
        })

    def test_navigation_allowed_for_manager_across_all_prospects(self):
        self.client.force_authenticate(user=self.manager)
        res = self.client.get(f'/api/prospects/{self.p_other.id}/navigation/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, {
            'previous_id': str(self.p_sub.id),
            'next_id': None,
            'current_index': 4,
            'total_count': 4,
        })

    def test_countries_endpoint_and_case_insensitive_country_filter(self):
        self.client.force_authenticate(user=self.pre1)
        res_countries = self.client.get('/api/prospects/countries/')
        self.assertEqual(res_countries.status_code, status.HTTP_200_OK)
        self.assertEqual(res_countries.data['countries'], ['KSA', 'Qatar', 'UAE'])

        # Case-insensitive list filtering
        res_list = self.client.get('/api/prospects/', {'country_head_office': 'ksa'})
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        results = res_list.data['results'] if isinstance(res_list.data, dict) and 'results' in res_list.data else res_list.data
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['id'], str(self.p_branch.id))

        # Navigation respects country filter
        res_nav = self.client.get(
            f'/api/prospects/{self.p_parent.id}/navigation/',
            {'country_head_office': 'UAE'}
        )
        self.assertEqual(res_nav.status_code, status.HTTP_200_OK)
        self.assertEqual(res_nav.data, {
            'previous_id': None,
            'next_id': None,
            'current_index': 1,
            'total_count': 1,
        })

        # Manager sees countries across all users (case-insensitively deduplicated, sorted)
        self.client.force_authenticate(user=self.manager)
        res_mgr_countries = self.client.get('/api/prospects/countries/')
        self.assertEqual(res_mgr_countries.status_code, status.HTTP_200_OK)
        self.assertEqual(res_mgr_countries.data['countries'], ['KSA', 'Oman', 'Qatar', 'UAE'])

    def test_create_allows_duplicate_name_only_for_branches(self):
        self.client.force_authenticate(user=self.pre1)

        base_payload = {
            'company_name': self.p_parent.company_name,
            'country_head_office': 'UAE',
            'complete_address': 'Abu Dhabi Office',
            'primary_industries': 'Construction',
            'operational_status': 'Active',
            'ownership_sector': 'Private Company',
            'primary_offering_type': 'Products',
        }

        # Duplicate Parent still rejected
        res_dup_parent = self.client.post('/api/prospects/', {
            **base_payload,
            'company_structure': 'Parent',
        }, format='json')
        self.assertEqual(res_dup_parent.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('already been entered', res_dup_parent.data['error'])

        # Duplicate Subsidiary still rejected
        res_dup_sub = self.client.post('/api/prospects/', {
            **base_payload,
            'company_structure': 'Subsidiary',
            'parent_companies': [str(self.p_parent.id)],
        }, format='json')
        self.assertEqual(res_dup_sub.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('already been entered', res_dup_sub.data['error'])

        # Multiple Branches with the exact same name as the Parent are allowed
        res_b1 = self.client.post('/api/prospects/', {
            **base_payload,
            'company_structure': 'Branch',
            'parent_companies': [str(self.p_parent.id)],
        }, format='json')
        self.assertEqual(res_b1.status_code, status.HTTP_201_CREATED)

        res_b2 = self.client.post('/api/prospects/', {
            **base_payload,
            'country_head_office': 'KSA',
            'complete_address': 'Jeddah Branch',
            'company_structure': 'Branch',
            'parent_companies': [str(self.p_parent.id)],
        }, format='json')
        self.assertEqual(res_b2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            Prospect.objects.filter(company_name__iexact=self.p_parent.company_name, company_structure='Branch').count(),
            2
        )

    def test_import_allows_duplicate_branch_names_in_file_and_against_db(self):
        # 1. Parent + 2 same-named Branches inside the same import file
        source_rows = [
            (2, {
                'company_name': 'Global Holdings',
                'country_head_office': 'UAE',
                'complete_address': 'HQ Dubai',
                'primary_industries': 'Tech',
                'company_structure': 'Parent',
                'operational_status': 'Active',
                'ownership_sector': 'Private Company',
                'primary_offering_type': 'Products',
                'parent_company_names': '',
                'official_email_address': 'hq@global.com',
                'official_phone_number': '+97140000001',
            }),
            (3, {
                'company_name': 'Global Holdings',
                'country_head_office': 'UAE',
                'complete_address': 'Branch Abu Dhabi',
                'primary_industries': 'Tech',
                'company_structure': 'Branch',
                'operational_status': 'Active',
                'ownership_sector': 'Private Company',
                'primary_offering_type': 'Products',
                'parent_company_names': 'Global Holdings',
                'official_email_address': 'abudhabi@global.com',
                'official_phone_number': '+97120000002',
            }),
            (4, {
                'company_name': 'Global Holdings',
                'country_head_office': 'KSA',
                'complete_address': 'Branch Riyadh',
                'primary_industries': 'Tech',
                'company_structure': 'Branch',
                'operational_status': 'Active',
                'ownership_sector': 'Private Company',
                'primary_offering_type': 'Products',
                'parent_company_names': 'Global Holdings',
                'official_email_address': 'riyadh@global.com',
                'official_phone_number': '+966110000003',
            }),
        ]
        grouped = group_rows(source_rows, {})
        self.assertEqual(len(grouped), 3)

        preview = build_preview(grouped, self.pre1)
        self.assertEqual([r['validation_status'] for r in preview], ['VALID', 'VALID', 'VALID'])
        self.assertEqual(preview[1]['parent_resolution'][0]['status'], STATUS_FOUND_IN_FILE)
        self.assertEqual(preview[1]['parent_resolution'][0]['source_row'], 2)
        self.assertEqual(preview[2]['parent_resolution'][0]['status'], STATUS_FOUND_IN_FILE)
        self.assertEqual(preview[2]['parent_resolution'][0]['source_row'], 2)

        # 2. Same-named Branches resolving to existing DB Parent vs duplicate Parent still INVALID
        db_source_rows = [
            (2, {
                'company_name': self.p_parent.company_name,
                'country_head_office': 'UAE',
                'complete_address': 'Another HQ',
                'primary_industries': 'Construction',
                'company_structure': 'Parent',
                'operational_status': 'Active',
                'ownership_sector': 'Private Company',
                'primary_offering_type': 'Products',
                'parent_company_names': '',
                'official_email_address': 'dup@alphaparent.com',
                'official_phone_number': '+97149999999',
            }),
            (3, {
                'company_name': self.p_parent.company_name,
                'country_head_office': 'Oman',
                'complete_address': 'Muscat Branch',
                'primary_industries': 'Construction',
                'company_structure': 'Branch',
                'operational_status': 'Active',
                'ownership_sector': 'Private Company',
                'primary_offering_type': 'Products',
                'parent_company_names': self.p_parent.company_name,
                'official_email_address': 'oman@alphaparent.com',
                'official_phone_number': '+96820000001',
            }),
            (4, {
                'company_name': self.p_parent.company_name,
                'country_head_office': 'Bahrain',
                'complete_address': 'Manama Branch',
                'primary_industries': 'Construction',
                'company_structure': 'Branch',
                'operational_status': 'Active',
                'ownership_sector': 'Private Company',
                'primary_offering_type': 'Products',
                'parent_company_names': self.p_parent.company_name,
                'official_email_address': 'bahrain@alphaparent.com',
                'official_phone_number': '+97310000002',
            }),
        ]
        db_grouped = group_rows(db_source_rows, {})
        db_preview = build_preview(db_grouped, self.pre1)
        self.assertEqual(db_preview[0]['validation_status'], 'INVALID')
        self.assertIn('Duplicate company name already in DB.', db_preview[0]['errors'])
        self.assertEqual(db_preview[1]['validation_status'], 'VALID')
        self.assertEqual(db_preview[1]['parent_resolution'][0]['status'], STATUS_EXISTS_IN_DB)
        self.assertEqual(db_preview[2]['validation_status'], 'VALID')
        self.assertEqual(db_preview[2]['parent_resolution'][0]['status'], STATUS_EXISTS_IN_DB)

        # 3. Direct import_single_row allows same-named Branch while rejecting duplicate Parent
        req = RequestFactory().post('/')
        req.user = self.pre1
        branch_item = ImportItem(
            index=0,
            data=db_grouped[1]['data'],
            source_row_numbers=[3],
            company_name=self.p_parent.company_name,
            key=self.p_parent.company_name.casefold(),
        )
        created_branch = import_single_row(branch_item, [self.p_parent.id], [], ProspectSerializer, req)
        self.assertEqual(created_branch.company_name, self.p_parent.company_name)
        self.assertEqual(created_branch.company_structure, 'Branch')
        self.assertIn(self.p_parent, created_branch.parent_companies.all())

        parent_item = ImportItem(
            index=0,
            data=db_grouped[0]['data'],
            source_row_numbers=[2],
            company_name=self.p_parent.company_name,
            key=self.p_parent.company_name.casefold(),
        )
        with self.assertRaises(RowImportError):
            import_single_row(parent_item, [], [], ProspectSerializer, req)
