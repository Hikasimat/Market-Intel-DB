from django.test import TestCase, RequestFactory
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from .models import Prospect, ProspectImportHistory, EmailVerification, LeadQualification
from .serializers import ProspectSerializer
from .import_services import (
    ImportItem, analyze_items, build_preview, run_import, read_import_file,
    ImportFileError, RowImportError, MAX_IMPORT_ROWS
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
