import uuid
from django.utils import timezone
from rest_framework.decorators import action, api_view
from accounts.permissions import IsPRE, IsLQ, IsPREOrLQ, IsManagerOrSuperuser
from rest_framework import viewsets, filters, status
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.permissions import IsAuthenticated
from .models import Prospect, ProspectOffering, ProspectContact, LeadQualification, EmailVerification, AuditReverificationRequest, GovernmentEntity
from .serializers import ProspectSerializer, LeadQualificationSerializer, ProspectContactSerializer, AuditReverificationRequestSerializer, GovernmentEntitySerializer

def apply_lq_distribution_filter(queryset, user, prospect_field_prefix=''):
    """
    Applies the sequential batch distribution logic for LQ users.
    Distributes prospects in batches of 5 based on creation order.
    """
    if user.is_superuser or not hasattr(user, 'profile') or user.profile.role != 'LQ':
        return queryset
        
    from django.contrib.auth import get_user_model
    from django.db.models.expressions import RawSQL
    User = get_user_model()
    
    # Only include non-superusers in the distribution pool
    lq_users = list(User.objects.filter(profile__role='LQ', is_superuser=False).order_by('id').values_list('id', flat=True))
    
    if user.id in lq_users:
        from prospects.models import LeadQualification, Prospect
        
        if queryset.model == LeadQualification:
            filter_kwargs = {'assigned_lq': user}
        elif queryset.model == Prospect:
            filter_kwargs = {'lead_qualification__assigned_lq': user}
        else:
            # For Meeting, CallbackReminder, OutreachEmail, etc.
            # All these have a 'prospect' ForeignKey
            filter_kwargs = {'prospect__lead_qualification__assigned_lq': user}
            
        return queryset.filter(**filter_kwargs)
    return queryset.none()

class GovernmentEntityViewSet(viewsets.ModelViewSet):
    serializer_class = GovernmentEntitySerializer
    permission_classes = [IsPRE]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_state_government', 'country']
    search_fields = ['name', 'country']
    ordering_fields = ['name', 'created_at']

    def get_queryset(self):
        queryset = GovernmentEntity.objects.all().select_related('central_government').order_by('-updated_at')
        user = self.request.user
        if not user.is_superuser and hasattr(user, 'profile'):
            role = user.profile.role
            if role == 'PRE':
                queryset = queryset.filter(created_by=user.username)
        return queryset

    def create(self, request, *args, **kwargs):
        name = request.data.get('name')
        country = request.data.get('country')
        if name and country and GovernmentEntity.objects.filter(name__iexact=name.strip(), country__iexact=country.strip()).exists():
            return Response(
                {'error': 'A government entity with this name and country already exists.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user.username)

class ProspectViewSet(viewsets.ModelViewSet):
    serializer_class = ProspectSerializer
    permission_classes = [IsPRE]

    def get_permissions(self):
        # Manager (and superuser) can read all prospects but cannot mutate
        user = getattr(self.request, 'user', None)
        is_manager = (
            user and not user.is_superuser and
            hasattr(user, 'profile') and
            getattr(user.profile, 'role', None) == 'MANAGER'
        )
        if is_manager:
            if self.action in ['list', 'retrieve', 'audit_reverify']:
                return [IsManagerOrSuperuser()]
            raise PermissionDenied('Managers cannot modify prospect data.')
        if self.action in ['list', 'retrieve', 'add_contact']:
            permission_classes = [IsPREOrLQ]
        else:
            permission_classes = [IsPRE]
        return [permission() for permission in permission_classes]

    def _is_manager(self):
        user = self.request.user
        return (
            not user.is_superuser and
            hasattr(user, 'profile') and
            getattr(user.profile, 'role', None) == 'MANAGER'
        )

    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['company_structure', 'operational_status', 'country_head_office', 'primary_offering_type']
    search_fields = ['company_name', 'country_head_office', 'primary_industries']
    ordering_fields = ['company_name', 'created_at', 'updated_at']

    def get_queryset(self):
        queryset = Prospect.objects.all().prefetch_related(
            'email_verifications',
            'market_event_participations__market_event',
            'offerings',
            'key_contacts',
            'parent_companies',
            'child_companies',
            'reverification_requests',
            'lead_qualification'
        ).order_by('-updated_at')

        # Role-based filtering
        user = self.request.user
        if not user.is_superuser and hasattr(user, 'profile'):
            role = user.profile.role
            if role == 'PRE':
                queryset = queryset.filter(created_by=user.username)
            elif role == 'LQ':
                queryset = apply_lq_distribution_filter(queryset, user, 'id__')
            # MANAGER sees all prospects (no filter)

        market_event = self.request.query_params.get('market_event')
        if market_event:
            queryset = queryset.filter(market_event_participations__market_event=market_event).distinct()
        return queryset

    def create(self, request, *args, **kwargs):
        # Duplicate validation by exact company name (case-insensitive)
        company_name = request.data.get('company_name')
        if company_name and Prospect.objects.filter(company_name__iexact=company_name.strip()).exists():
            return Response(
                {'error': 'A prospect with this company name has already been entered.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            print("VALIDATION ERROR:", serializer.errors)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def perform_update(self, serializer):
        prospect = serializer.save()
        user = self.request.user
        if not user.is_superuser and hasattr(user, 'profile') and user.profile.role == 'PRE':
            pending_reqs = AuditReverificationRequest.objects.filter(
                prospect=prospect,
                status=AuditReverificationRequest.Status.PENDING
            )
            if pending_reqs.exists():
                pending_reqs.update(
                    status=AuditReverificationRequest.Status.CORRECTED,
                    resolved_at=timezone.now()
                )

    @action(detail=True, methods=['post'], url_path='audit-reverify')
    def audit_reverify(self, request, pk=None):
        prospect = self.get_object()
        highlighted_fields = request.data.get('highlighted_fields', [])
        manager_notes = request.data.get('manager_notes', '')

        if not highlighted_fields:
            return Response({'error': 'Please provide fields to highlight for re-verification.'}, status=status.HTTP_400_BAD_REQUEST)

        pre_user = None
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            pre_user = User.objects.get(username=prospect.created_by)
        except User.DoesNotExist:
            pass

        req = AuditReverificationRequest.objects.create(
            prospect=prospect,
            manager=request.user,
            pre_user=pre_user,
            highlighted_fields=highlighted_fields,
            manager_notes=manager_notes
        )
        
        try:
            lq = prospect.lead_qualification
            lq.pre_task_status = LeadQualification.PreTaskStatus.ISSUE_SENT_TO_PRE
            lq.issue_category = 'Audit: Re-Verification Required'
            lq.issue_details = f"Manager Notes: {manager_notes}\nFields: {', '.join(highlighted_fields)}"
            lq.issue_reported_by = request.user
            lq.issue_reported_at = timezone.now()
            for field in highlighted_fields:
                lq.verification_checklist[field] = 'Incorrect'
            lq.save()
        except Exception as e:
            print("Failed to update LeadQualification on audit_reverify:", e)
            
        from .serializers import AuditReverificationRequestSerializer
        return Response(AuditReverificationRequestSerializer(req).data, status=status.HTTP_201_CREATED)

    def perform_create(self, serializer):
        prospect = serializer.save(created_by=self.request.user.username)
        # Always call assign_lq_to_prospect after creation to guarantee assignment.
        # This runs AFTER the post_save signal, so if the signal already assigned,
        # this is a harmless idempotent re-assignment of the same user.
        # If the signal failed or ran with stale code, this ensures assignment.
        try:
            from .models import assign_lq_to_prospect
            assigned = assign_lq_to_prospect(prospect)
            if assigned:
                print(f"[perform_create] Assigned '{prospect.company_name}' to LQ: {assigned.username}")
            else:
                print(f"[perform_create] WARNING: No LQ users found, could not assign '{prospect.company_name}'")
        except Exception as e:
            print(f"[perform_create] LQ assignment error: {e}")

    @action(detail=True, methods=['post'], url_path='add-contact')
    def add_contact(self, request, pk=None):
        prospect = self.get_object()
        contact_name = request.data.get('contact_name')
        designation = request.data.get('designation', '')
        official_email = request.data.get('official_email', '')
        phone_number = request.data.get('phone_number', '')

        if not contact_name or not contact_name.strip():
            return Response({'error': 'Contact name is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Duplicate prevention: check if same email or phone already exists for this prospect
        existing_qs = ProspectContact.objects.filter(prospect=prospect)
        if official_email and official_email.strip():
            if existing_qs.filter(official_email__iexact=official_email.strip()).exists():
                existing = existing_qs.filter(official_email__iexact=official_email.strip()).first()
                return Response({'status': 'duplicate', 'message': 'This contact already exists.', 'contact': {'id': str(existing.id), 'contact_name': existing.contact_name, 'designation': existing.designation, 'official_email': existing.official_email, 'phone_number': existing.phone_number}}, status=status.HTTP_200_OK)
        if phone_number and phone_number.strip():
            if existing_qs.filter(phone_number=phone_number.strip()).exists():
                existing = existing_qs.filter(phone_number=phone_number.strip()).first()
                return Response({'status': 'duplicate', 'message': 'This contact already exists.', 'contact': {'id': str(existing.id), 'contact_name': existing.contact_name, 'designation': existing.designation, 'official_email': existing.official_email, 'phone_number': existing.phone_number}}, status=status.HTTP_200_OK)

        ProspectContact.objects.create(
            prospect=prospect,
            contact_name=contact_name.strip(),
            designation=designation.strip() if designation else '',
            official_email=official_email.strip() if official_email else '',
            phone_number=phone_number.strip() if phone_number else ''
        )
        return Response({'status': 'contact added'}, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path='import/blueprint', permission_classes=[IsPRE])
    def import_blueprint(self, request):
        import io
        import openpyxl
        from django.http import HttpResponse
        
        headers = [
            'Company Name', 'Country', 'Complete Address', 'Primary Industries', 'Official Phone Number', 
            'Official Email Address', 'Official Website URL', 'LinkedIn Company Page', 'Company Structure', 
            'Parent Company / Parent Companies', 'Operational Status', 'Target / Surviving Company', 
            'Company Type', 'Primary Offering Type', 'Merging Companies', 'Dissolved Companies', 
            'Acquiring Company', 'Acquired Shares (%)', 'Acquired Companies', 'Stakeholders / Shareholders', 
            'Key Contacts / Personnel - Contact Name', 'Key Contacts / Personnel - Designation / Role', 
            'Key Contacts / Personnel - Official Email', 'Key Contacts / Personnel - Phone Number', 
            'Market Offerings - Products Offered', 'Market Offerings - Services Provided', 
            'Market Offerings - Solutions Provided', 'Market Events - Associated Market Events'
        ]
        
        sample_row = [
            'Acme Corp', 'United Arab Emirates', '123 Tech St, Dubai, UAE', 'Technology', '+971 4 555 0199', 
            'info@acme.example.com', 'https://acme.example.com', 'https://linkedin.com/company/acme', 'Independent', 
            'Parent Corp', 'Active', 'Surviving', 'Private Company', 'Multiple', 
            'Merge Corp', 'Dissolve Corp', 'Acquire Corp', '100', 'Acquired Corp 1;Acquired Corp 2', 
            'John Smith (Individual):50;Tech Corp (Company):50', 'John Doe', 'CEO', 'john@acme.example.com', 
            '+971 4 555 0101', 'Enterprise Cloud Servers', 'IT Strategy & Consulting', 'Digital Transformation Package', 'Tech Summit 2026;AI Expo'
        ]
        
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Prospects Import"
        
        ws.append(headers)
        ws.append(sample_row)
        
        from openpyxl.worksheet.datavalidation import DataValidation
        
        dv_structure = DataValidation(type="list", formula1='"Parent,Branch,Subsidiary"', allow_blank=True)
        ws.add_data_validation(dv_structure)
        dv_structure.add("I2:I1048576")
        
        dv_status = DataValidation(type="list", formula1='"Active,Inactive,Permanently Closed,Acquired,Merged"', allow_blank=True)
        ws.add_data_validation(dv_status)
        dv_status.add("K2:K1048576")
        
        dv_company_type = DataValidation(type="list", formula1='"Private Company,Government Company,Semi Government Company"', allow_blank=True)
        ws.add_data_validation(dv_company_type)
        dv_company_type.add("M2:M1048576")
        
        dv_offering = DataValidation(type="list", formula1='"Products,Services,Solutions,Multiple"', allow_blank=True)
        ws.add_data_validation(dv_offering)
        dv_offering.add("N2:N1048576")
        
        from openpyxl.styles import PatternFill, Font
        header_fill = PatternFill(start_color="E2E8F0", end_color="E2E8F0", fill_type="solid")
        header_font = Font(bold=True)
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            ws.column_dimensions[cell.column_letter].width = 25
            
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        
        response = HttpResponse(output.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="prospect_blueprint.xlsx"'
        return response

    @action(detail=False, methods=['post'], url_path='import/headers', permission_classes=[IsPRE])
    def import_headers(self, request):
        from .import_services import read_import_file, ImportFileError
        if 'file' not in request.FILES:
            return Response({'error': 'No file uploaded.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            headers, _, _ = read_import_file(request.FILES['file'], headers_only=True)
        except ImportFileError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'headers': headers}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='import/preview', permission_classes=[IsPRE])
    def import_preview(self, request):
        import json
        from .import_services import read_import_file, group_rows, build_preview, ImportFileError, MAX_IMPORT_ROWS
        if 'file' not in request.FILES:
            return Response({'error': 'No file uploaded.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            _, source_rows, limit_reached = read_import_file(request.FILES['file'])
        except ImportFileError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            mapping = json.loads(request.data.get('mapping', '{}')) or {}
            if not isinstance(mapping, dict):
                mapping = {}
        except (TypeError, ValueError):
            mapping = {}

        # Preview only inspects/resolves; nothing is written to the database here.
        rows = build_preview(group_rows(source_rows, mapping), request.user)
        return Response({
            'rows': rows,
            'meta': {
                'max_rows': MAX_IMPORT_ROWS,
                'processed_source_rows': len(source_rows),
                'limit_reached': limit_reached,
            }
        }, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'], url_path='import/commit', permission_classes=[IsPRE])
    def import_commit(self, request):
        from .import_services import run_import
        rows = request.data.get('rows', [])
        if not rows or not isinstance(rows, list):
            return Response({'error': 'No data to import.'}, status=status.HTTP_400_BAD_REQUEST)

        # Best-effort import: each company is imported in its own transaction.
        result = run_import(
            rows,
            request,
            self.get_serializer_class(),
            file_name=request.data.get('file_name', ''),
            client_limit_reached=bool(request.data.get('limit_reached', False)),
        )
        http_status = status.HTTP_201_CREATED if result['imported_count'] else status.HTTP_200_OK
        return Response(result, status=http_status)

    @action(detail=False, methods=['get'], url_path='import/history', permission_classes=[IsPRE])
    def import_history(self, request):
        from .models import ProspectImportHistory
        from .import_services import serialize_history
        qs = ProspectImportHistory.objects.select_related('created_by')
        if not request.user.is_superuser:
            qs = qs.filter(created_by=request.user)
        return Response([serialize_history(h) for h in qs.order_by('-created_at')[:20]], status=status.HTTP_200_OK)

    @action(detail=True, methods=['post'], url_path='merge', permission_classes=[IsPRE])
    def merge(self, request, pk=None):
        from django.db import transaction
        company_to_merge_id = request.data.get('merged_company_id')
        owner_company_id = request.data.get('owner_company_id')
        
        if str(pk) != owner_company_id:
            return Response({'error': 'Owner company ID does not match the URL.'}, status=status.HTTP_400_BAD_REQUEST)
            
        if owner_company_id == company_to_merge_id:
            return Response({'error': 'Cannot merge a company with itself.'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            owner_company = Prospect.objects.get(id=owner_company_id)
            merged_company = Prospect.objects.get(id=company_to_merge_id)
        except Prospect.DoesNotExist:
            return Response({'error': 'One or both companies not found.'}, status=status.HTTP_404_NOT_FOUND)
            
        with transaction.atomic():
            merged_company.operational_status = Prospect.Status.MERGED
            merged_company.save()
            
        return Response({'status': 'success'}, status=status.HTTP_200_OK)

class LQPipelineViewSet(viewsets.ModelViewSet):
    serializer_class = LeadQualificationSerializer
    permission_classes = [IsPREOrLQ]

    def get_permissions(self):
        """Manager can read all LQ pipeline records but cannot mutate."""
        user = getattr(self.request, 'user', None)
        is_manager = (
            user and not user.is_superuser and
            hasattr(user, 'profile') and
            getattr(user.profile, 'role', None) == 'MANAGER'
        )
        if is_manager:
            if self.action in ['list', 'retrieve']:
                return [IsManagerOrSuperuser()]
            raise PermissionDenied('Managers cannot modify LQ pipeline data.')
        return [IsPREOrLQ()]

    def get_queryset(self):
        from django.db.models import Count, Q
        queryset = LeadQualification.objects.all().select_related('prospect').prefetch_related(
            'prospect__email_verifications',
            'prospect__market_event_participations__market_event',
            'prospect__offerings',
            'prospect__key_contacts',
            'prospect__parent_companies',
            'prospect__child_companies',
            'prospect__reverification_requests',
            'prospect__lead_qualification'
        ).annotate(
            emails_sent_annotated=Count(
                'prospect__communication_timeline',
                filter=Q(prospect__communication_timeline__activity_type='EMAIL_SENT'),
                distinct=True
            ),
            calls_logged_annotated=Count(
                'prospect__communication_timeline',
                filter=Q(prospect__communication_timeline__activity_type='CALL'),
                distinct=True
            )
        ).order_by('-updated_at')
        user = self.request.user
        if not user.is_superuser and hasattr(user, 'profile'):
            role = user.profile.role
            if role == 'PRE':
                queryset = queryset.filter(prospect__created_by=user.username)
            elif role == 'LQ':
                queryset = apply_lq_distribution_filter(queryset, user, 'prospect_id__')
            # MANAGER sees all records (no filter)
        return queryset


    def _evaluate_qualification_status(self, lq):
        from .models import CallActivity, ProspectContact, LeadQualification
        from django.utils import timezone
        import datetime
        
        contacts = ProspectContact.objects.filter(prospect=lq.prospect)
        if not contacts.exists():
            return
            
        all_lead_qualified = True
        all_not_interested = True
        latest_not_interested_date = None
        
        for contact in contacts:
            latest_call = CallActivity.objects.filter(prospect_contact=contact).order_by('-created_at').first()
            if not latest_call:
                all_lead_qualified = False
                all_not_interested = False
                break
                
            if latest_call.communication_outcome != 'Lead Qualified':
                all_lead_qualified = False
            if latest_call.communication_outcome != 'Not Interested':
                all_not_interested = False
            else:
                if latest_not_interested_date is None or latest_call.created_at > latest_not_interested_date:
                    latest_not_interested_date = latest_call.created_at

        updated = False
        if all_lead_qualified and lq.qualification_status != LeadQualification.QualificationStatus.LEAD_QUALIFIED:
            lq.qualification_status = LeadQualification.QualificationStatus.LEAD_QUALIFIED
            updated = True
            
        if all_not_interested and latest_not_interested_date:
            if timezone.now() < latest_not_interested_date + datetime.timedelta(days=30):
                if lq.qualification_status != LeadQualification.QualificationStatus.LEAD_FREEZE:
                    lq.qualification_status = LeadQualification.QualificationStatus.LEAD_FREEZE
                    updated = True
            else:
                if lq.qualification_status == LeadQualification.QualificationStatus.LEAD_FREEZE:
                    lq.qualification_status = LeadQualification.QualificationStatus.UNQUALIFIED
                    updated = True
        elif not all_not_interested and not all_lead_qualified:
            # Revert to UNQUALIFIED if consensus is broken
            if lq.qualification_status in [LeadQualification.QualificationStatus.LEAD_QUALIFIED, LeadQualification.QualificationStatus.LEAD_FREEZE]:
                lq.qualification_status = LeadQualification.QualificationStatus.UNQUALIFIED
                updated = True

        if updated:
            lq.save(update_fields=['qualification_status'])

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        for lq in queryset:
            self._evaluate_qualification_status(lq)
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        self._evaluate_qualification_status(instance)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        """
        Override to instrument audit timestamps on attended_meeting / qualification_status changes.
        The existing LQ workspace PATCH flow is unchanged; we only add the new audit fields.
        """
        instance = self.get_object()
        now = timezone.now()

        # ── attended_at: set when attended_meeting transitions False -> True ──
        new_attended = request.data.get('attended_meeting')
        if new_attended is True or str(new_attended).lower() == 'true':
            if not instance.attended_meeting:
                # Only set if not already set (preserve original timestamp)
                if not instance.attended_at:
                    instance.attended_at = now

        # ── decision_by / decision_at: set when qualification_status changes ──
        new_status = request.data.get('qualification_status')
        DECIDED_STATUSES = {'Lead Qualified', 'Disqualified', 'Lead Freeze', 'Nurture'}
        if new_status and new_status in DECIDED_STATUSES:
            if instance.qualification_status != new_status:
                # New decision being recorded
                instance.decision_by = request.user
                instance.decision_at = now

        # Save the audit fields we computed above before the regular update
        update_audit = []
        if not instance.attended_meeting and (new_attended is True or str(new_attended).lower() == 'true'):
            if instance.attended_at == now:
                update_audit.append('attended_at')
        if new_status and new_status in DECIDED_STATUSES and instance.qualification_status != new_status:
            update_audit.append('decision_by')
            update_audit.append('decision_at')

        if update_audit:
            # Save audit fields first without modifying the state
            LeadQualification.objects.filter(pk=instance.pk).update(**{
                field: getattr(instance, field) for field in update_audit
            })

        # Proceed with normal DRF partial_update (honours all existing behaviour)
        kwargs['partial'] = True
        return super().update(request, *args, **kwargs)

        filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['verification_status', 'pre_task_status', 'qualification_status']
    search_fields = ['prospect__company_name', 'prospect__country_head_office', 'prospect__primary_industries']
    ordering_fields = ['created_at', 'updated_at', 'qualification_score']

    @action(detail=True, methods=['post'], url_path='report-issue')
    def report_issue(self, request, pk=None):
        lq = self.get_object()
        lq.pre_task_status = LeadQualification.PreTaskStatus.ISSUE_SENT_TO_PRE
        lq.issue_category = request.data.get('issue_category', '')
        lq.issue_details = request.data.get('issue_details', '')
        lq.verification_checklist = request.data.get('verification_checklist', lq.verification_checklist)
        lq.issue_reported_by = request.user
        lq.issue_reported_at = timezone.now()
        lq.save()
        return Response(self.get_serializer(lq).data)

    @action(detail=True, methods=['post'], url_path='complete-pre-task')
    def complete_pre_task(self, request, pk=None):
        import uuid
        from django.utils import timezone
        
        lq = self.get_object()
        
        # Log the completed task
        task_log = {
            'id': str(uuid.uuid4()),
            'issue_category': lq.issue_category,
            'issue_details': lq.issue_details,
            'issue_reported_by': lq.issue_reported_by.username if lq.issue_reported_by else None,
            'issue_reported_at': lq.issue_reported_at.isoformat() if lq.issue_reported_at else None,
            'completed_at': timezone.now().isoformat(),
            'prospect_company_name': lq.prospect.company_name,
            'prospect_country': lq.prospect.country_head_office,
            'prospect_industries': lq.prospect.primary_industries,
        }
        
        if not isinstance(lq.completed_tasks_log, list):
            lq.completed_tasks_log = []
        lq.completed_tasks_log.append(task_log)
        
        lq.pre_task_status = LeadQualification.PreTaskStatus.PRE_UPDATED
        lq.save(update_fields=['pre_task_status', 'completed_tasks_log'])
        return Response(self.get_serializer(lq).data)

    @action(detail=True, methods=['post'], url_path='confirm-reverification')
    def confirm_reverification(self, request, pk=None):
        lq = self.get_object()
        lq.pre_task_status = LeadQualification.PreTaskStatus.NONE
        lq.save(update_fields=['pre_task_status'])
        return Response(self.get_serializer(lq).data)

    @action(detail=True, methods=['post'], url_path='verify')
    def verify(self, request, pk=None):
        lq = self.get_object()
        lq.verification_status = request.data.get('verification_status', lq.verification_status)
        lq.verification_checklist = request.data.get('verification_checklist', lq.verification_checklist)
        lq.save(update_fields=['verification_status', 'verification_checklist'])
        return Response(self.get_serializer(lq).data)

    @action(detail=True, methods=['post'], url_path='qualification')
    def qualification(self, request, pk=None):
        lq = self.get_object()
        lq.qualification_status = request.data.get('qualification_status', lq.qualification_status)
        lq.qualification_score = request.data.get('qualification_score', lq.qualification_score)
        lq.lq_notes = request.data.get('lq_notes', lq.lq_notes)
        lq.budget = request.data.get('budget', lq.budget)
        lq.authority = request.data.get('authority', lq.authority)
        lq.need = request.data.get('need', lq.need)
        lq.timeline = request.data.get('timeline', lq.timeline)
        lq.qualified_by = request.user
        lq.qualified_at = timezone.now()
        lq.save()
        return Response(self.get_serializer(lq).data)

from .models import CallbackReminder
from .serializers import CallbackReminderSerializer

class CallbackReminderViewSet(viewsets.ModelViewSet):
    serializer_class = CallbackReminderSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        user = getattr(self.request, 'user', None)
        is_manager = (
            user and not user.is_superuser and
            hasattr(user, 'profile') and
            getattr(user.profile, 'role', None) == 'MANAGER'
        )
        if is_manager:
            if self.action in ['list', 'retrieve', 'pending']:
                return [IsManagerOrSuperuser()]
            raise PermissionDenied('Managers cannot modify reminders.')
        return [IsAuthenticated()]

    def get_queryset(self):
        queryset = CallbackReminder.objects.filter(is_completed=False).order_by('scheduled_datetime')
        user = self.request.user
        if not user.is_superuser and hasattr(user, 'profile') and user.profile.role == 'LQ':
            queryset = apply_lq_distribution_filter(queryset, user, 'prospect_id__')
        return queryset

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=False, methods=['get'], url_path='pending')
    def pending(self, request):
        reminders = self.get_queryset().filter(scheduled_datetime__gt=timezone.now())
        return Response(self.get_serializer(reminders, many=True).data)

    @action(detail=True, methods=['patch'], url_path='mark-notified')
    def mark_notified(self, request, pk=None):
        reminder = self.get_object()
        interval = request.data.get('interval')
        if interval == '30m':
            reminder.notified_30m = True
        elif interval == '15m':
            reminder.notified_15m = True
        elif interval == '5m':
            reminder.notified_5m = True
        reminder.save()
        return Response(self.get_serializer(reminder).data)

from .models import Meeting
from .serializers import MeetingSerializer

class MeetingViewSet(viewsets.ModelViewSet):
    serializer_class = MeetingSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        user = getattr(self.request, 'user', None)
        is_manager = (
            user and not user.is_superuser and
            hasattr(user, 'profile') and
            getattr(user.profile, 'role', None) == 'MANAGER'
        )
        if is_manager:
            if self.action in ['list', 'retrieve', 'pending']:
                return [IsManagerOrSuperuser()]
            raise PermissionDenied('Managers cannot modify meetings.')
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        queryset = Meeting.objects.filter(is_completed=False).order_by('scheduled_datetime')
        # Superusers see all meetings
        if user.is_superuser:
            return queryset
        # LQ users: filter meetings by prospects assigned to them via distribution
        if hasattr(user, 'profile') and user.profile.role == 'LQ':
            from django.contrib.auth import get_user_model
            from django.db.models import Subquery, OuterRef
            User = get_user_model()
            lq_users = list(User.objects.filter(
                profile__role='LQ', is_superuser=False
            ).order_by('id').values_list('id', flat=True))
            if user.id in lq_users:
                N = len(lq_users)
                current_index = lq_users.index(user.id)
                # Get all prospect IDs in batches of 5
                all_prospects = list(
                    Prospect.objects.order_by('created_at', 'id').values_list('id', flat=True)
                )
                my_prospect_ids = [
                    pid for i, pid in enumerate(all_prospects)
                    if ((i // 5) % N) == current_index
                ]
                return queryset.filter(prospect_id__in=my_prospect_ids)
            return queryset.none()
        # PRE or other roles: show all meetings
        return queryset

    @action(detail=False, methods=['get'], url_path='pending')
    def pending(self, request):
        meetings = self.get_queryset().filter(scheduled_datetime__gt=timezone.now())
        return Response(self.get_serializer(meetings, many=True).data)


    @action(detail=True, methods=['patch'], url_path='mark-notified')
    def mark_notified(self, request, pk=None):
        meeting = self.get_object()
        interval = request.data.get('interval')
        if interval == '1h':
            meeting.notified_1h = True
        elif interval == '30m':
            meeting.notified_30m = True
        elif interval == '15m':
            meeting.notified_15m = True
        meeting.save()
        return Response(self.get_serializer(meeting).data)


class ProspectContactViewSet(viewsets.ModelViewSet):
    serializer_class = ProspectContactSerializer
    permission_classes = [IsPREOrLQ]

    def get_permissions(self):
        user = getattr(self.request, 'user', None)
        is_manager = (
            user and not user.is_superuser and
            hasattr(user, 'profile') and
            getattr(user.profile, 'role', None) == 'MANAGER'
        )
        if is_manager:
            if self.action in ['list', 'retrieve']:
                return [IsManagerOrSuperuser()]
            raise PermissionDenied('Managers cannot modify key contacts.')
        return [IsPREOrLQ()]
    def get_queryset(self):
        queryset = ProspectContact.objects.all().select_related('prospect').prefetch_related(
            'call_activities',
            'prospect__email_verifications'
        ).order_by('-created_at')
        user = self.request.user
        if not user.is_superuser and hasattr(user, 'profile'):
            if user.profile.role == 'PRE':
                queryset = queryset.filter(prospect__created_by=user.username)
            elif user.profile.role == 'LQ':
                queryset = apply_lq_distribution_filter(queryset, user, 'prospect_id__')
        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user.username)


    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['contact_name', 'official_email', 'prospect__company_name']
    ordering_fields = ['created_at', 'updated_at']

from .models import OutreachEmail, OutreachEmailRecipient, EmailAttachment, CallActivity, CommunicationActivity, ProspectContact
from .serializers import OutreachEmailSerializer, CallActivitySerializer, CommunicationActivitySerializer
from django.utils import timezone
from accounts.models import MailAccount
import smtplib
from email.message import EmailMessage
from email.utils import make_msgid
import utils.encryption as encryption

class CommunicationActivityViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CommunicationActivitySerializer
    permission_classes = [IsPREOrLQ]

    def get_permissions(self):
        user = getattr(self.request, 'user', None)
        is_manager = (
            user and not user.is_superuser and
            hasattr(user, 'profile') and
            getattr(user.profile, 'role', None) == 'MANAGER'
        )
        if is_manager:
            return [IsManagerOrSuperuser()]
        return [IsPREOrLQ()]

    def get_queryset(self):
        queryset = CommunicationActivity.objects.all().order_by('-created_at')
        prospect_id = self.request.query_params.get('prospect')
        contact_id = self.request.query_params.get('contact')
        if prospect_id:
            queryset = queryset.filter(prospect_id=prospect_id)
        if contact_id:
            queryset = queryset.filter(prospect_contact_id=contact_id)
            
        user = self.request.user
        if not user.is_superuser and hasattr(user, 'profile') and user.profile.role == 'LQ':
            queryset = apply_lq_distribution_filter(queryset, user, 'prospect_id__')
            
        return queryset

class CallActivityViewSet(viewsets.ModelViewSet):
    serializer_class = CallActivitySerializer
    permission_classes = [IsPREOrLQ]

    def get_permissions(self):
        user = getattr(self.request, 'user', None)
        is_manager = (
            user and not user.is_superuser and
            hasattr(user, 'profile') and
            getattr(user.profile, 'role', None) == 'MANAGER'
        )
        if is_manager:
            if self.action in ['list', 'retrieve']:
                return [IsManagerOrSuperuser()]
            raise PermissionDenied('Managers cannot create or modify call activities.')
        return [IsPREOrLQ()]

    def get_queryset(self):
        queryset = CallActivity.objects.all().order_by('-created_at')
        prospect_id = self.request.query_params.get('prospect')
        contact_id = self.request.query_params.get('contact')
        if prospect_id:
            queryset = queryset.filter(prospect_id=prospect_id)
        if contact_id:
            queryset = queryset.filter(prospect_contact_id=contact_id)
            
        user = self.request.user
        if not user.is_superuser and hasattr(user, 'profile') and user.profile.role == 'LQ':
            queryset = apply_lq_distribution_filter(queryset, user, 'prospect_id__')
            
        return queryset

    def perform_create(self, serializer):
        if hasattr(self.request.user, 'profile') and self.request.user.profile.role != 'LQ':
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only LQ users can record calls.")
        
        direction = self.request.data.get('direction', 'OUTBOUND')
        started_at_str = self.request.data.get('call_started_at')
        
        call = serializer.save(created_by=self.request.user)
        
        if started_at_str:
            from django.utils.dateparse import parse_datetime
            dt = parse_datetime(started_at_str)
            if dt:
                CallActivity.objects.filter(id=call.id).update(call_started_at=dt)
                call.refresh_from_db()

        # Create CommunicationActivity
        comm = CommunicationActivity.objects.create(
            prospect=call.prospect,
            prospect_contact=call.prospect_contact,
            activity_type='CALL',
            direction=direction,
            status=call.call_status,
            outcome=call.communication_outcome,
            notes=call.notes,
            call_activity=call,
            performed_by=self.request.user
        )

class OutreachEmailViewSet(viewsets.ModelViewSet):
    serializer_class = OutreachEmailSerializer

    def get_permissions(self):
        # Emails are LQ-only; Manager cannot mutate and effectively sees nothing
        return [IsPREOrLQ()]

    def get_queryset(self):
        if hasattr(self.request.user, 'profile') and self.request.user.profile.role != 'LQ':
            return OutreachEmail.objects.none()
        queryset = OutreachEmail.objects.all().order_by('-created_at')
        prospect_id = self.request.query_params.get('prospect')
        if prospect_id:
            queryset = queryset.filter(prospect_id=prospect_id)
            
        user = self.request.user
        if not user.is_superuser and hasattr(user, 'profile') and user.profile.role == 'LQ':
            queryset = apply_lq_distribution_filter(queryset, user, 'prospect_id__')
            
        return queryset

    def create(self, request, *args, **kwargs):
        if hasattr(self.request.user, 'profile') and self.request.user.profile.role != 'LQ':
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only LQ users can send emails.")
        user = request.user
        mail_account = MailAccount.objects.filter(id=user.profile.mail_account_id, is_active=True).first()
        if not mail_account:
            return Response({'error': 'No active mail account found for the current user.'}, status=status.HTTP_400_BAD_REQUEST)

        if mail_account.smtp_status != 'VERIFIED':
            return Response({'error': 'Sender SMTP account is not verified.'}, status=status.HTTP_400_BAD_REQUEST)

        prospect_id = request.data.get('prospect')
        subject = request.data.get('subject')
        body = request.data.get('body') or ''
        recipients_data = request.data.get('recipients', [])

        # Create EmailMessage
        from email.utils import formatdate
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = f"{mail_account.display_name} <{mail_account.email_address}>"
        msg['Reply-To'] = mail_account.email_address
        msg['Date'] = formatdate(localtime=True)

        to_emails = []
        cc_emails = []
        bcc_emails = []

        import json
        if isinstance(recipients_data, str):
            recipients_data = json.loads(recipients_data)

        # PRE-FLIGHT RECIPIENT CHECKS
        prospect = Prospect.objects.filter(id=prospect_id).first()
        if not prospect:
            return Response({'error': 'Prospect not found.'}, status=status.HTTP_400_BAD_REQUEST)

        for rcpt in recipients_data:
            email = rcpt.get('email_address')
            contact_id = rcpt.get('prospect_contact')

            # Verification check removed per user request

            rtype = rcpt.get('recipient_type', 'TO').upper()
            if rtype == 'TO': to_emails.append(email)
            elif rtype == 'CC': cc_emails.append(email)
            elif rtype == 'BCC': bcc_emails.append(email)

        if to_emails: msg['To'] = ', '.join(to_emails)
        if cc_emails: msg['Cc'] = ', '.join(cc_emails)
        if bcc_emails: msg['Bcc'] = ', '.join(bcc_emails)

        msg_id = make_msgid(domain=mail_account.email_address.split('@')[-1] if '@' in mail_account.email_address else 'local')
        msg['Message-ID'] = msg_id

        # Email open tracking
        import uuid
        from django.conf import settings
        import html
        tracking_token = uuid.uuid4()
        tracking_url = f"{settings.EMAIL_TRACKING_BASE_URL}/api/email-tracking/{tracking_token}/"

        # Optional saved template / signature (owner-validated at send time).
        template_id = request.data.get('template_id') or None
        signature_id = request.data.get('signature_id') or None
        composed = None
        if template_id or signature_id:
            from accounts.template_utils import build_email_content, ComposeError
            try:
                composed = build_email_content(
                    user, mail_account, prospect, to_emails + cc_emails, subject, body,
                    template_id=template_id, signature_id=signature_id,
                    body_edited=str(request.data.get('body_edited', 'true')).lower() != 'false',
                )
            except (ComposeError, ValueError) as exc:
                return Response({'error': str(exc) or 'Invalid template or signature.'}, status=status.HTTP_400_BAD_REQUEST)
            subject = composed['subject']
            del msg['Subject']
            msg['Subject'] = subject
            body = composed['text_body']

        effective_signature = mail_account.default_signature
        if composed and composed['has_signature']:
            effective_signature = composed['signature_text']

        full_body = body
        if effective_signature:
            full_body += f"\n\n{effective_signature}"

        msg.set_content(full_body)
        
        # HTML alternative with tracking pixel
        html_body = html.escape(body).replace('\n', '<br>')
        html_signature = ""
        if composed and composed['has_signature']:
            html_signature = f"\n<div>\n{composed['signature_html']}\n</div>\n"
        elif mail_account.default_signature:
            sig_safe = html.escape(mail_account.default_signature).replace('\n', '<br>')
            html_signature = f"\n<div>\n{sig_safe}\n</div>\n"

        if composed and composed['has_template'] and composed['html_body']:
            main_html = composed['html_body']
        else:
            main_html = f'<div style="font-family: sans-serif;">{html_body}</div>'

        html_content = f"""<html><body>
{main_html}<br>{html_signature}
<img src="{tracking_url}" width="1" height="1" alt="" style="display:none;width:1px;height:1px;border:0;">
</body></html>"""

        # Convert embedded Base64 images to inline MIME CID attachments for cross-client
        # rendering (major clients like Gmail and Outlook block or print raw data:image URIs)
        from accounts.template_utils import convert_base64_images_to_cid
        email_domain = mail_account.email_address.split('@')[-1] if '@' in mail_account.email_address else 'local'
        html_content, inline_images = convert_base64_images_to_cid(html_content, domain=email_domain)
        msg.add_alternative(html_content, subtype='html')

        if inline_images:
            html_part = next((p for p in msg.iter_parts() if p.get_content_type() == 'text/html'), None)
            if html_part:
                for cid, subtype, img_bytes in inline_images:
                    html_part.add_related(img_bytes, maintype='image', subtype=subtype, cid=f'<{cid}>')

        # Handle Attachments
        files = request.FILES.getlist('attachments')
        total_size = sum(f.size for f in files)
        if total_size > 25 * 1024 * 1024:
            return Response({'error': 'Total attachment size exceeds 25MB limit.'}, status=status.HTTP_400_BAD_REQUEST)

        for f in files:
            if f.size > 10 * 1024 * 1024:
                return Response({'error': f'File {f.name} exceeds 10MB limit.'}, status=status.HTTP_400_BAD_REQUEST)
            ext = f.name.split('.')[-1].lower() if '.' in f.name else ''
            if ext in ['exe', 'bat', 'cmd', 'js', 'ps1', 'vbs', 'scr']:
                return Response({'error': f'File type .{ext} is not allowed.'}, status=status.HTTP_400_BAD_REQUEST)
            msg.add_attachment(f.read(), maintype='application', subtype='octet-stream', filename=f.name)
            f.seek(0)

        # Send via SMTP in background
        def send_smtp():
            import smtplib
            import utils.encryption as encryption
            
            _SMTP_TIMEOUT = 30
            server = None
            try:
                password = encryption.decrypt_password(mail_account.smtp_app_password_encrypted)
                if mail_account.smtp_security == 'SSL':
                    server = smtplib.SMTP_SSL(mail_account.smtp_host, mail_account.smtp_port, timeout=_SMTP_TIMEOUT)
                else:
                    server = smtplib.SMTP(mail_account.smtp_host, mail_account.smtp_port, timeout=_SMTP_TIMEOUT)
                    server.starttls()
                server.login(mail_account.smtp_username, password)
                server.send_message(msg)
            except smtplib.SMTPRecipientsRefused as e:
                for rcpt_email, (code, msg_bytes) in e.recipients.items():
                    if code >= 500:
                        verification = EmailVerification.objects.filter(prospect=prospect, email_address=rcpt_email).first()
                        if verification:
                            verification.verification_status = 'INVALID'
                            verification.reason = f'Permanent SMTP failure: {code} {msg_bytes.decode("utf-8", errors="ignore")}'
                            verification.save()

                            lq = prospect.lead_qualification
                            lq.pre_task_status = LeadQualification.PreTaskStatus.ISSUE_SENT_TO_PRE
                            lq.issue_category = 'Email Verification'
                            lq.issue_details = f"Email could not be delivered to {rcpt_email}. Verification updated to Invalid."
                            lq.save()
            except Exception as e:
                print(f"Background SMTP send failed: {e}")
            finally:
                if server is not None:
                    try:
                        server.quit()
                    except Exception:
                        pass

        # Persistence
        outreach_email = OutreachEmail.objects.create(
            prospect=prospect,
            created_by=user,
            sender_mail_account=mail_account,
            from_email=mail_account.email_address,
            from_name=mail_account.display_name,
            subject=subject,
            body=full_body,
            signature=effective_signature,
            status='WAITING FOR RESPONSE',
            sent_at=timezone.now(),
            message_id=msg_id,
            thread_id=msg_id,
            tracking_token=tracking_token
        )

        for rcpt in recipients_data:
            contact_id = rcpt.get('prospect_contact')
            contact = ProspectContact.objects.filter(id=contact_id).first() if contact_id else None
            OutreachEmailRecipient.objects.create(
                outreach_email=outreach_email,
                email_address=rcpt.get('email_address'),
                prospect_contact=contact,
                recipient_type=rcpt.get('recipient_type', 'TO').upper()
            )

        for f in files:
            EmailAttachment.objects.create(
                outreach_email=outreach_email,
                file=f,
                original_filename=f.name,
                mime_type=f.content_type,
                size=f.size
            )

        # Create CommunicationActivity
        primary_contact_id = recipients_data[0].get('prospect_contact') if recipients_data else None
        primary_contact = ProspectContact.objects.filter(id=primary_contact_id).first() if primary_contact_id else None

        CommunicationActivity.objects.create(
            prospect=prospect,
            prospect_contact=primary_contact,
            activity_type='EMAIL_SENT',
            direction='OUTBOUND',
            status='Waiting for Response',
            subject=subject,
            outreach_email=outreach_email,
            performed_by=user
        )

        # Update LeadQualification email status if it exists
        if hasattr(prospect, 'lead_qualification'):
            prospect.lead_qualification.email_status = 'Waiting for Response'
            prospect.lead_qualification.save()

        # Start the background SMTP send
        import threading
        t = threading.Thread(target=send_smtp)
        t.start()

        serializer = self.get_serializer(outreach_email)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=['post'], url_path='compose-preview')
    def compose_preview(self, request):
        """Render exactly what would be sent for a saved template/signature. Never sends."""
        if not hasattr(request.user, 'profile') or request.user.profile.role != 'LQ':
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only LQ users can preview emails.")
        from accounts.template_utils import build_email_content, ComposeError
        mail_account = MailAccount.objects.filter(id=request.user.profile.mail_account_id, is_active=True).first()
        prospect = Prospect.objects.filter(id=request.data.get('prospect')).first()
        to_emails = request.data.get('to_emails') or []
        try:
            composed = build_email_content(
                request.user, mail_account, prospect, list(to_emails),
                request.data.get('subject') or '', request.data.get('body') or '',
                template_id=request.data.get('template_id') or None,
                signature_id=request.data.get('signature_id') or None,
                body_edited=bool(request.data.get('body_edited', True)),
            )
        except (ComposeError, ValueError) as exc:
            return Response({'error': str(exc) or 'Invalid template or signature.'}, status=status.HTTP_400_BAD_REQUEST)
        sig_html = composed['signature_html'] if composed['has_signature'] else ''
        if not composed['has_signature'] and mail_account and mail_account.default_signature:
            import html as _h
            sig_html = _h.escape(mail_account.default_signature).replace('\n', '<br>')
        return Response({
            'subject': composed['subject'],
            'text_body': composed['text_body'],
            'html': composed['html_body'] + ('<br><div>' + sig_html + '</div>' if sig_html else ''),
        })

    @action(detail=False, methods=['post'])
    def sync_imap(self, request):
        if hasattr(request.user, 'profile') and request.user.profile.role != 'LQ':
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only LQ users can sync emails.")

        from django.core.management import call_command

        try:
            call_command('sync_imap')
            return Response({'message': 'IMAP Sync completed successfully.'}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': f"Error running sync_imap: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

from django.views import View
from django.http import HttpResponse

class EmailTrackingView(View):
    def get(self, request, tracking_token, *args, **kwargs):
        # 1x1 transparent GIF base64 decoded
        PIXEL_GIF_DATA = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'

        try:
            email = OutreachEmail.objects.filter(tracking_token=tracking_token).first()
            if email and not email.is_opened:
                email.is_opened = True
                email.opened_at = timezone.now()
                email.save(update_fields=['is_opened', 'opened_at'])
        except Exception:
            pass  # Fail silently to avoid leaking info or breaking the pixel

        response = HttpResponse(PIXEL_GIF_DATA, content_type='image/gif')
        response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response['Pragma'] = 'no-cache'
        response['Expires'] = '0'
        return response

@api_view(['GET'])
def pre_dashboard_stats(request):
    user = request.user
    if not user.is_authenticated or (not user.is_superuser and getattr(user, 'profile', None) and user.profile.role != 'PRE'):
        return Response({'error': 'Unauthorized'}, status=status.HTTP_403_FORBIDDEN)
        
    import calendar
    import datetime
    
    now = timezone.now()
    year = now.year
    month = now.month
    
    total_days = calendar.monthrange(year, month)[1]
    
    # Calculate working days by only subtracting the 4 holidays from the total days in the month (30 or 31)
    holidays = 4
    working_days = total_days - holidays
    if working_days <= 0:
        working_days = 1 # Fallback
        
    monthly_target = 1560
    daily_target = monthly_target / working_days
    
    # Entered Today
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    entered_today = Prospect.objects.filter(created_by=user.username, created_at__gte=today_start).count()
    
    # Entered This Month
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    entered_this_month = Prospect.objects.filter(created_by=user.username, created_at__gte=month_start).count()
    
    # Lead Qualified Count (total ever)
    total_entered = Prospect.objects.filter(created_by=user.username).count()
    total_lq = LeadQualification.objects.filter(prospect__created_by=user.username, qualification_status='Lead Qualified').count()
    total_lq_attended = LeadQualification.objects.filter(prospect__created_by=user.username).exclude(verification_status='Unverified', qualification_status='Unqualified').count()
    from django.db.models import Q, Exists, OuterRef
    from .models import CallActivity
    total_unqualified = LeadQualification.objects.filter(
        prospect__created_by=user.username
    ).filter(
        Q(qualification_status='Lead Freeze') |
        (Q(qualification_status='Unqualified') & Exists(
            CallActivity.objects.filter(
                prospect=OuterRef('prospect'),
                communication_outcome='Not Interested'
            )
        ))
    ).count()
    
    # Current day in month for actual progress calculation
    passed_days = now.day
    # Assume holidays are evenly distributed, or just subtract a proportional amount
    
    # Assume holidays are evenly distributed, or just subtract a proportional amount
    passed_working_days = passed_days - int(holidays * (passed_days / total_days))
    if passed_working_days <= 0:
        passed_working_days = 1
        
    daily_avg = (entered_today / daily_target) * 100 if daily_target else 0
    monthly_avg = (entered_this_month / monthly_target) * 100 if monthly_target else 0
    actual_progress = (entered_this_month / (daily_target * passed_working_days)) * 100 if passed_working_days else 0
    
    tasks_received_today = 0
    tasks_received_month = 0
    total_tasks_received = 0
    
    tasks_completed_today = 0
    tasks_completed_month = 0
    completed_tasks = 0
    
    lqs_for_tasks = LeadQualification.objects.filter(prospect__created_by=user.username)
    for lq in lqs_for_tasks:
        # Check active task
        if lq.pre_task_status == 'ISSUE_SENT_TO_PRE':
            total_tasks_received += 1
            if lq.issue_reported_at:
                if lq.issue_reported_at >= today_start:
                    tasks_received_today += 1
                if lq.issue_reported_at >= month_start:
                    tasks_received_month += 1
                    
        has_logs = isinstance(lq.completed_tasks_log, list) and len(lq.completed_tasks_log) > 0
        
        # Check fallback completed task (before log was added)
        if lq.pre_task_status == 'PRE_UPDATED' and not has_logs:
            total_tasks_received += 1
            completed_tasks += 1
            if lq.updated_at >= today_start:
                tasks_received_today += 1
                tasks_completed_today += 1
            if lq.updated_at >= month_start:
                tasks_received_month += 1
                tasks_completed_month += 1
                
        # Check logged tasks
        if isinstance(lq.completed_tasks_log, list):
            for log_entry in lq.completed_tasks_log:
                total_tasks_received += 1
                completed_tasks += 1
                
                # Check completed time
                completed_at_str = log_entry.get('completed_at')
                if completed_at_str:
                    try:
                        completed_at = datetime.datetime.fromisoformat(completed_at_str)
                        if completed_at >= today_start:
                            tasks_completed_today += 1
                        if completed_at >= month_start:
                            tasks_completed_month += 1
                    except Exception:
                        pass
                
                # Check reported time
                reported_at_str = log_entry.get('issue_reported_at')
                if reported_at_str:
                    try:
                        reported_at = datetime.datetime.fromisoformat(reported_at_str)
                        if reported_at >= today_start:
                            tasks_received_today += 1
                        if reported_at >= month_start:
                            tasks_received_month += 1
                    except Exception:
                        pass

    task_completion_average = (completed_tasks / total_tasks_received * 100) if total_tasks_received else 0
    
    lq_percentage = (total_lq / total_entered) * 100 if total_entered else 0
    
    return Response({
        'monthly_target': monthly_target,
        'daily_target': round(daily_target, 2),
        'working_days_in_month': working_days,
        'entered_today': entered_today,
        'entered_this_month': entered_this_month,
        'total_entered': total_entered,
        'total_lead_qualified': total_lq,
        'lq_attended_prospects': total_lq_attended,
        'unqualified_prospects': total_unqualified,
        'daily_average': round(min(daily_avg, 100), 1),
        'monthly_average': round(min(monthly_avg, 100), 1),
        'lead_qualified_percentage': round(lq_percentage, 1),
        'tasks_received_today': tasks_received_today,
        'tasks_completed_today': tasks_completed_today,
        'tasks_received_month': tasks_received_month,
        'tasks_completed_month': tasks_completed_month,
        'total_tasks_received': total_tasks_received,
        'completed_tasks': completed_tasks,
        'task_completion_average': round(task_completion_average, 1)
    })

class AuditReverificationRequestViewSet(viewsets.ModelViewSet):
    serializer_class = AuditReverificationRequestSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        user = self.request.user
        queryset = AuditReverificationRequest.objects.all().order_by('-updated_at')
        if user.is_superuser:
            return queryset
        if hasattr(user, 'profile'):
            if user.profile.role == 'MANAGER':
                return queryset.filter(manager=user)
            elif user.profile.role == 'PRE':
                return queryset.filter(pre_user=user)
        return queryset.none()

    @action(detail=True, methods=['post'], url_path='mark-notified')
    def mark_notified(self, request, pk=None):
        req = self.get_object()
        req.manager_notified = True
        req.save(update_fields=['manager_notified'])
        return Response({'status': 'marked as notified'})
