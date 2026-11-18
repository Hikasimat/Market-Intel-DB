from market_events.serializers import MarketEventSimpleSerializer
from rest_framework import serializers
from .models import (
    Prospect, ProspectOffering, ProspectContact, AuditReverificationRequest,
    ProspectShareholding, GovernmentEntity, ProspectAcquisition,
    EmailCampaign, EmailCampaignRecipient, EmailCampaignAttachment,
    EmailThread, EmailThreadMessage
)

class ProspectOfferingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProspectOffering
        fields = ['id', 'offering_type', 'name', 'display_order', 'created_at']
        read_only_fields = ['id', 'created_at']

class GovernmentEntitySimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = GovernmentEntity
        fields = ['id', 'name', 'country', 'is_state_government']

class GovernmentEntitySerializer(serializers.ModelSerializer):
    central_government_detail = GovernmentEntitySimpleSerializer(source='central_government', read_only=True)

    class Meta:
        model = GovernmentEntity
        fields = [
            'id', 'name', 'country', 'is_state_government', 'state_name', 'central_government',
            'central_government_detail', 'official_website', 'official_email',
            'phone_number', 'complete_address', 'created_at', 'updated_at',
            'created_by', 'updated_by'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by']

class ProspectContactSerializer(serializers.ModelSerializer):
    prospect_name = serializers.CharField(source='prospect.company_name', read_only=True)
    latest_call_status = serializers.SerializerMethodField()
    latest_communication_outcome = serializers.SerializerMethodField()
    email_verification_status = serializers.SerializerMethodField()
    email_verification_id = serializers.SerializerMethodField()

    def get_latest_call_status(self, obj):
        activities = list(obj.call_activities.all())
        if activities:
            activities.sort(key=lambda x: x.created_at, reverse=True)
            return activities[0].call_status
        return None

    def get_latest_communication_outcome(self, obj):
        activities = list(obj.call_activities.all())
        if activities:
            activities.sort(key=lambda x: x.created_at, reverse=True)
            return activities[0].communication_outcome
        return None

    def get_email_verification_status(self, obj):
        verifications = [v for v in obj.prospect.email_verifications.all() if v.email_address == obj.official_email]
        if verifications:
            verifications.sort(key=lambda x: x.updated_at, reverse=True)
            return verifications[0].verification_status
        return None

    def get_email_verification_id(self, obj):
        verifications = [v for v in obj.prospect.email_verifications.all() if v.email_address == obj.official_email]
        if verifications:
            verifications.sort(key=lambda x: x.updated_at, reverse=True)
            return str(verifications[0].id)
        return None

    class Meta:
        model = ProspectContact
        fields = ['id', 'prospect', 'prospect_name', 'prefix', 'contact_name', 'designation', 'official_email', 'phone_number', 'linkedin_profile', 'latest_call_status', 'latest_communication_outcome', 'email_verification_status', 'email_verification_id', 'created_at', 'updated_at']
        read_only_fields = ['id', 'prospect', 'prospect_name', 'latest_call_status', 'latest_communication_outcome', 'email_verification_status', 'email_verification_id', 'created_at', 'updated_at']

class ProspectShareholdingSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.company_name', read_only=True)
    individual_name = serializers.CharField(source='contact.contact_name', read_only=True)
    government_entity_name = serializers.CharField(source='government_entity.name', read_only=True)
    contact_index = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    is_self = serializers.BooleanField(write_only=True, required=False, default=False)

    class Meta:
        model = ProspectShareholding
        fields = ['id', 'holder_type', 'company', 'company_name', 'contact', 'individual_name', 'government_entity', 'government_entity_name', 'other_name', 'share_percentage', 'contact_index', 'is_self']
        read_only_fields = ['id', 'company_name', 'individual_name', 'government_entity_name']

class ProspectSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Prospect
        fields = ['id', 'company_name', 'country_head_office', 'primary_industries', 'company_structure', 'operational_status', 'ownership_sector']

class ProspectAcquisitionSerializer(serializers.ModelSerializer):
    acquiring_prospect_detail = ProspectSimpleSerializer(source='acquiring_prospect', read_only=True)
    
    class Meta:
        model = ProspectAcquisition
        fields = ['id', 'acquiring_prospect', 'acquiring_prospect_detail', 'acquired_shares']

class ProspectSerializer(serializers.ModelSerializer):
    parent_companies_detail = ProspectSimpleSerializer(source='parent_companies', many=True, read_only=True)
    child_companies_detail = ProspectSimpleSerializer(source='child_companies', many=True, read_only=True)
    merging_companies_detail = ProspectSimpleSerializer(source='merging_companies', many=True, read_only=True)
    dissolved_companies_detail = ProspectSimpleSerializer(source='dissolved_companies', many=True, read_only=True)
    merged_into_prospects_detail = ProspectSimpleSerializer(source='merged_into_prospects', many=True, read_only=True)
    dissolved_into_prospects_detail = ProspectSimpleSerializer(source='dissolved_into_prospects', many=True, read_only=True)
    
    # New M2M related name
    acquired_companies_detail = ProspectSimpleSerializer(source='acquired_companies_rev', many=True, read_only=True)
    acquiring_companies = ProspectAcquisitionSerializer(source='acquisition_records', many=True, read_only=True)


    products = serializers.SerializerMethodField()
    services = serializers.SerializerMethodField()
    solutions = serializers.SerializerMethodField()
    key_contacts = ProspectContactSerializer(many=True, required=False)
    shareholdings = ProspectShareholdingSerializer(many=True, required=False)
    company_email_verification_status = serializers.SerializerMethodField()
    qualification_status = serializers.SerializerMethodField()

    def get_qualification_status(self, obj):
        if hasattr(obj, 'lead_qualification'):
            return obj.lead_qualification.qualification_status
        return None

    market_events = serializers.SerializerMethodField(read_only=True)
    market_event_ids = serializers.ListField(
        child=serializers.UUIDField(), write_only=True, required=False
    )

    pre_task_status = serializers.SerializerMethodField()
    audit_reverify_fields = serializers.SerializerMethodField()
    lead_qualification = serializers.SerializerMethodField()

    def get_pre_task_status(self, obj):
        if hasattr(obj, 'lead_qualification') and obj.lead_qualification:
            return obj.lead_qualification.pre_task_status
        return None

    def get_lead_qualification(self, obj):
        lq = getattr(obj, 'lead_qualification', None)
        if lq:
            return {
                'id': lq.id,
                'pre_task_status': lq.pre_task_status,
                'verification_status': lq.verification_status,
                'qualification_status': lq.qualification_status,
                'issue_category': lq.issue_category,
                'issue_details': lq.issue_details,
                'verification_checklist': lq.verification_checklist,
            }
        return None

    def get_audit_reverify_fields(self, obj):
        if hasattr(obj, 'reverification_requests'):
            requests = [r for r in obj.reverification_requests.all() if r.status == 'Pending']
            if requests:
                requests.sort(key=lambda x: x.created_at, reverse=True)
                return requests[0].highlighted_fields
        return []

    # Internal writes for nested relationships
    offerings_data = ProspectOfferingSerializer(many=True, write_only=True, required=False)
    acquiring_companies_data = serializers.ListField(child=serializers.DictField(), write_only=True, required=False)

    class Meta:
        model = Prospect
        fields = [
            'id', 'company_name', 'country_head_office', 'complete_address',
            'official_phone_number', 'official_email_address', 'official_website_url',
            'linkedin_company_page', 'primary_industries', 'company_structure',
            'operational_status', 'ownership_sector', 'parent_companies', 'parent_companies_detail', 'child_companies_detail',
            'merging_companies', 'merging_companies_detail', 'dissolved_companies', 'dissolved_companies_detail',
            'merged_into_prospects_detail', 'dissolved_into_prospects_detail',
            'acquiring_companies', 'acquired_companies_detail',
            'primary_offering_type', 'products', 'services', 'solutions',
            'offerings_data', 'acquiring_companies_data', 'key_contacts', 'shareholdings', 'created_at', 'updated_at',
            'created_by', 'updated_by', 'market_events', 'market_event_ids', 'company_email_verification_status', 'qualification_status', 'pre_task_status', 'audit_reverify_fields', 'lead_qualification'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by', 'updated_by', 'market_events', 'market_event_ids', 'company_email_verification_status', 'qualification_status', 'pre_task_status', 'audit_reverify_fields', 'lead_qualification']

    def get_company_email_verification_status(self, obj):
        if not obj.official_email_address:
            return None
        verifications = [v for v in obj.email_verifications.all() if v.email_address == obj.official_email_address]
        if verifications:
            verifications.sort(key=lambda x: x.updated_at, reverse=True)
            return verifications[0].verification_status
        return None

    def get_market_events(self, obj):
        events = [p.market_event for p in obj.market_event_participations.select_related('market_event')]
        return MarketEventSimpleSerializer(events, many=True).data

    def get_products(self, obj):
        offerings = [o for o in obj.offerings.all() if o.offering_type == ProspectOffering.OfferingTypeChoice.PRODUCT]
        return ProspectOfferingSerializer(offerings, many=True).data

    def get_services(self, obj):
        offerings = [o for o in obj.offerings.all() if o.offering_type == ProspectOffering.OfferingTypeChoice.SERVICE]
        return ProspectOfferingSerializer(offerings, many=True).data

    def get_solutions(self, obj):
        offerings = [o for o in obj.offerings.all() if o.offering_type == ProspectOffering.OfferingTypeChoice.SOLUTION]
        return ProspectOfferingSerializer(offerings, many=True).data

    def validate(self, data):
        structure = data.get('company_structure')
        parent_companies = data.get('parent_companies', [])
        status = data.get('operational_status')

        is_import = self.context.get('is_import', False)

        # Branch and Subsidiary require parent (skip if importing via CSV)
        if structure in [Prospect.Structure.BRANCH, Prospect.Structure.SUBSIDIARY]:
            if not parent_companies and not is_import:
                raise serializers.ValidationError({"parent_companies": "At least one parent company is required for Branch or Subsidiary."})


        # Self-parent prevention
        if self.instance and self.instance in parent_companies:
            raise serializers.ValidationError({"parent_companies": "A prospect cannot be its own parent."})

        return data

    def create(self, validated_data):
        offerings_data = validated_data.pop('offerings_data', [])
        contacts_data = validated_data.pop('key_contacts', [])
        shareholdings_data = validated_data.pop('shareholdings', [])
        parent_companies = validated_data.pop('parent_companies', [])
        merging_companies = validated_data.pop('merging_companies', [])
        dissolved_companies = validated_data.pop('dissolved_companies', [])
        market_event_ids = validated_data.pop('market_event_ids', [])
        acquiring_companies_data = validated_data.pop('acquiring_companies_data', [])

        prospect = Prospect.objects.create(**validated_data)

        from django.db import transaction
        from market_events.models import MarketEventParticipation

        with transaction.atomic():
            if market_event_ids:
                market_event_ids = list(set(market_event_ids))
                for event_id in market_event_ids:
                    from market_events.models import MarketEvent
                    event = MarketEvent.objects.filter(id=event_id).first()
                    if not event:
                        raise serializers.ValidationError(f"MarketEvent {event_id} does not exist.")
                    MarketEventParticipation.objects.create(market_event_id=event_id, prospect=prospect)

        if parent_companies:
            prospect.parent_companies.set(parent_companies)

        if prospect.operational_status == Prospect.Status.MERGED:
            if merging_companies:
                prospect.merging_companies.set(merging_companies)
            if dissolved_companies:
                prospect.dissolved_companies.set(dissolved_companies)
                for dissolved in dissolved_companies:
                    dissolved.operational_status = Prospect.Status.INACTIVE
                    dissolved.save(update_fields=['operational_status'])

        for offering in offerings_data:
            ProspectOffering.objects.create(prospect=prospect, **offering)

        created_contacts = []
        for contact in contacts_data:
            created_contacts.append(ProspectContact.objects.create(prospect=prospect, **contact))
            
        for sh_data in shareholdings_data:
            contact_index = sh_data.pop('contact_index', None)
            is_self = sh_data.pop('is_self', False)
            if sh_data.get('holder_type') == 'Individual' and contact_index is not None:
                if 0 <= contact_index < len(created_contacts):
                    sh_data['contact'] = created_contacts[contact_index]
            if sh_data.get('holder_type') == 'Company' and is_self:
                sh_data['company'] = prospect
            ProspectShareholding.objects.create(prospect=prospect, **sh_data)

        if prospect.operational_status == Prospect.Status.ACQUIRED:
            for acq in acquiring_companies_data:
                ProspectAcquisition.objects.create(
                    acquired_prospect=prospect,
                    acquiring_prospect_id=acq.get('acquiring_company'),
                    acquired_shares=acq.get('acquired_shares')
                )


        # Always assign an LQ user immediately after creation.
        # This runs at the serializer level — the deepest possible hook —
        # so it works regardless of view, signal, or server state.
        try:
            from .models import assign_lq_to_prospect
            assign_lq_to_prospect(prospect)
        except Exception as e:
            print(f"[ProspectSerializer.create] LQ assignment error: {e}")

        return prospect

    def update(self, instance, validated_data):
        offerings_data = validated_data.pop('offerings_data', None)
        contacts_data = validated_data.pop('key_contacts', None)
        shareholdings_data = validated_data.pop('shareholdings', None)
        parent_companies = validated_data.pop('parent_companies', None)
        merging_companies = validated_data.pop('merging_companies', None)
        dissolved_companies = validated_data.pop('dissolved_companies', None)
        market_event_ids = validated_data.pop('market_event_ids', None)
        acquiring_companies_data = validated_data.pop('acquiring_companies_data', None)

        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        from django.db import transaction
        from market_events.models import MarketEventParticipation

        if market_event_ids is not None:
            with transaction.atomic():
                market_event_ids = list(set(market_event_ids))
                existing_participations = MarketEventParticipation.objects.filter(prospect=instance)
                existing_event_ids = list(existing_participations.values_list('market_event_id', flat=True))

                # Delete removed ones
                existing_participations.exclude(market_event_id__in=market_event_ids).delete()

                # Add new ones
                for event_id in market_event_ids:
                    if event_id not in existing_event_ids:
                        from market_events.models import MarketEvent
                        event = MarketEvent.objects.filter(id=event_id).first()
                        if not event:
                            raise serializers.ValidationError(f"MarketEvent {event_id} does not exist.")
                        MarketEventParticipation.objects.create(market_event_id=event_id, prospect=instance)

        if parent_companies is not None:
            instance.parent_companies.set(parent_companies)

        if instance.operational_status == Prospect.Status.MERGED:
            if merging_companies is not None:
                instance.merging_companies.set(merging_companies)
            if dissolved_companies is not None:
                instance.dissolved_companies.set(dissolved_companies)
                for dissolved in dissolved_companies:
                    dissolved.operational_status = Prospect.Status.INACTIVE
                    dissolved.save(update_fields=['operational_status'])
        else:
            instance.merging_companies.clear()
            instance.dissolved_companies.clear()

        if instance.operational_status != Prospect.Status.ACQUIRED:
            instance.acquisition_records.all().delete()
        elif acquiring_companies_data is not None:
            instance.acquisition_records.all().delete()
            for acq in acquiring_companies_data:
                ProspectAcquisition.objects.create(
                    acquired_prospect=instance,
                    acquiring_prospect_id=acq.get('acquiring_company'),
                    acquired_shares=acq.get('acquired_shares')
                )

        if offerings_data is not None:
            instance.offerings.all().delete()
            for offering in offerings_data:
                ProspectOffering.objects.create(prospect=instance, **offering)

        if contacts_data is not None:
            raw_contacts = self.initial_data.get('key_contacts', [])
            existing_contacts = {str(c.id): c for c in instance.key_contacts.all()}
            seen_ids = []

            for i, contact_data in enumerate(contacts_data):
                raw_id = None
                if i < len(raw_contacts) and isinstance(raw_contacts[i], dict):
                    raw_id = str(raw_contacts[i].get('id', ''))

                if raw_id and raw_id in existing_contacts:
                    c_inst = existing_contacts[raw_id]
                    for k, v in contact_data.items():
                        setattr(c_inst, k, v)
                    c_inst.save()
                    seen_ids.append(raw_id)
                else:
                    new_c = ProspectContact.objects.create(prospect=instance, **contact_data)
                    seen_ids.append(str(new_c.id))

            for c_id, c_inst in existing_contacts.items():
                if c_id not in seen_ids:
                    c_inst.delete()

        if shareholdings_data is not None:
            raw_shareholdings = self.initial_data.get('shareholdings', [])
            existing_sh = {str(sh.id): sh for sh in instance.shareholdings.all()}
            seen_sh_ids = []
            
            # Need to get all current contacts for new shareholdings linking by index
            current_contacts = list(instance.key_contacts.all())

            for i, sh_data in enumerate(shareholdings_data):
                raw_id = None
                if i < len(raw_shareholdings) and isinstance(raw_shareholdings[i], dict):
                    raw_id = str(raw_shareholdings[i].get('id', ''))
                
                contact_index = sh_data.pop('contact_index', None)
                is_self = sh_data.pop('is_self', False)
                if sh_data.get('holder_type') == 'Individual' and not sh_data.get('contact') and contact_index is not None:
                    if 0 <= contact_index < len(current_contacts):
                        sh_data['contact'] = current_contacts[contact_index]
                if sh_data.get('holder_type') == 'Company' and is_self:
                    sh_data['company'] = instance

                if raw_id and raw_id in existing_sh:
                    sh_inst = existing_sh[raw_id]
                    for k, v in sh_data.items():
                        setattr(sh_inst, k, v)
                    sh_inst.save()
                    seen_sh_ids.append(raw_id)
                else:
                    new_sh = ProspectShareholding.objects.create(prospect=instance, **sh_data)
                    seen_sh_ids.append(str(new_sh.id))

            for sh_id, sh_inst in existing_sh.items():
                if sh_id not in seen_sh_ids:
                    sh_inst.delete()

        return instance

from .models import LeadQualification

class LeadQualificationSerializer(serializers.ModelSerializer):
    prospect = ProspectSerializer(read_only=True)
    emails_sent_count = serializers.SerializerMethodField()
    calls_logged_count = serializers.SerializerMethodField()
    latest_email_content = serializers.SerializerMethodField()

    def get_emails_sent_count(self, obj):
        if hasattr(obj, 'emails_sent_annotated'):
            return obj.emails_sent_annotated
        from .models import CommunicationActivity
        return CommunicationActivity.objects.filter(prospect=obj.prospect, activity_type='EMAIL_SENT').count()

    def get_calls_logged_count(self, obj):
        if hasattr(obj, 'calls_logged_annotated'):
            return obj.calls_logged_annotated
        from .models import CommunicationActivity
        return CommunicationActivity.objects.filter(prospect=obj.prospect, activity_type='CALL').count()

    def get_latest_email_content(self, obj):
        from .models import OutreachEmail, EmailCampaignRecipient
        if not getattr(obj, 'prospect_id', None):
            return None

        # 1. Check latest sent OutreachEmail (created by direct outreach or campaign send)
        sent_oe = (
            OutreachEmail.objects
            .prefetch_related('recipients')
            .filter(prospect_id=obj.prospect_id, status__in=['SENT', 'RECEIVED RESPONSE', 'OPENED'])
            .order_by('-sent_at', '-created_at')
            .first()
        )
        if sent_oe:
            to_addrs = [r.email_address for r in sent_oe.recipients.all() if r.recipient_type == 'TO' and r.email_address]
            cc_addrs = [r.email_address for r in sent_oe.recipients.all() if r.recipient_type == 'CC' and r.email_address]
            camp_rec = (
                EmailCampaignRecipient.objects
                .select_related('campaign')
                .filter(outreach_email=sent_oe)
                .first()
            )
            return {
                'source': 'CAMPAIGN_SENT' if camp_rec else 'OUTREACH_SENT',
                'status': sent_oe.status,
                'subject': sent_oe.subject or '',
                'body': sent_oe.body or '',
                'sent_at': sent_oe.sent_at.isoformat() if sent_oe.sent_at else None,
                'to_emails': to_addrs,
                'cc_emails': cc_addrs,
                'campaign_id': str(camp_rec.campaign_id) if camp_rec else None,
                'campaign_name': camp_rec.campaign.name if camp_rec and camp_rec.campaign else None,
                'section_number': camp_rec.section_number if camp_rec else None,
            }

        # 2. Check latest EmailCampaignRecipient (SENT, SENDING, PENDING, or AI DRAFT) for this prospect
        camp_rec = (
            EmailCampaignRecipient.objects
            .select_related('campaign', 'outreach_email')
            .filter(prospect_id=obj.prospect_id)
            .exclude(campaign__status='CANCELLED')
            .order_by('-sent_at', '-created_at')
            .first()
        )
        if camp_rec:
            subj = (camp_rec.custom_subject or '').strip() or (camp_rec.campaign.subject if camp_rec.campaign else '')
            body = (camp_rec.custom_body or '').strip() or (camp_rec.campaign.body if camp_rec.campaign else '')
            return {
                'source': 'CAMPAIGN_SENT' if camp_rec.status == 'SENT' else 'CAMPAIGN_DRAFT',
                'status': camp_rec.status,
                'subject': subj,
                'body': body,
                'sent_at': camp_rec.sent_at.isoformat() if camp_rec.sent_at else None,
                'to_emails': [camp_rec.email_address] if camp_rec.email_address else [],
                'cc_emails': [],
                'campaign_id': str(camp_rec.campaign_id),
                'campaign_name': camp_rec.campaign.name if camp_rec.campaign else None,
                'section_number': camp_rec.section_number,
            }

        return None

    class Meta:
        model = LeadQualification
        fields = [
            'id', 'prospect', 'verification_status', 'pre_task_status',
            'qualification_status', 'qualification_score', 'lq_notes',
            'email_status', 'budget', 'authority', 'need', 'timeline',
            'verification_checklist', 'issue_category', 'issue_details',
            'completed_tasks_log',
            'emails_sent_count', 'calls_logged_count', 'latest_email_content',
            'attended_meeting', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'prospect', 'pre_task_status', 'created_at', 'updated_at', 'completed_tasks_log']

from .models import CallbackReminder


class CallbackReminderSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='prospect.company_name', read_only=True)
    key_person_name = serializers.SerializerMethodField()

    class Meta:
        model = CallbackReminder
        fields = [
            'id', 'prospect', 'company_name', 'key_person_name', 'scheduled_datetime',
            'description', 'is_completed', 'notified_30m',
            'notified_15m', 'notified_5m', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_key_person_name(self, obj):
        if hasattr(obj, 'prospect_contact') and obj.prospect_contact:
            return obj.prospect_contact.contact_name
        contacts = list(obj.prospect.key_contacts.all())
        if contacts:
            return contacts[0].contact_name
        return None

from .models import Meeting

class MeetingSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='prospect.company_name', read_only=True)
    key_person_name = serializers.SerializerMethodField()
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = Meeting
        fields = [
            'id', 'prospect', 'company_name', 'key_person_name', 'prospect_contact', 'scheduled_datetime',
            'meeting_date', 'meeting_time', 'timezone',
            'meeting_link', 'agenda', 'is_completed',
            'meeting_provider', 'conference_status', 'status',
            'provider_meeting_id', 'calendar_event_id', 'calendar_type',
            'created_by', 'created_by_username',
            'recording_file', 'recording_status', 'recording_downloaded_at',
            'recording_file_size', 'recording_mime_type',
            'google_conference_record_id', 'google_recording_id', 'recording_drive_file_id',
            'transcript_text', 'transcript_segments', 'speaker_segments', 'diarization_participants',
            'transcription_status', 'transcription_backend', 'transcription_completed_at',
            'cbe_meeting_id', 'cbe_session_id', 'cbe_recording_id', 'cbe_delivery_id',
            'notified_1h', 'notified_30m', 'notified_15m',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'conference_status',
            'provider_meeting_id', 'calendar_event_id', 'calendar_type',
            'created_by', 'created_by_username',
            'recording_file', 'recording_status', 'recording_downloaded_at',
            'recording_file_size', 'recording_mime_type',
            'google_conference_record_id', 'google_recording_id', 'recording_drive_file_id',
            'transcript_text', 'transcript_segments', 'speaker_segments', 'diarization_participants',
            'transcription_status', 'transcription_backend', 'transcription_completed_at',
            'cbe_meeting_id', 'cbe_session_id', 'cbe_recording_id', 'cbe_delivery_id',
        ]

    def get_key_person_name(self, obj):
        if hasattr(obj, 'prospect_contact') and obj.prospect_contact:
            return obj.prospect_contact.contact_name
        contacts = list(obj.prospect.key_contacts.all())
        if contacts:
            return contacts[0].contact_name
        return None


from .models import OutreachEmail, OutreachEmailRecipient, EmailAttachment, CallActivity, CommunicationActivity

class EmailAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailAttachment
        fields = ['id', 'original_filename', 'mime_type', 'size', 'created_at']

class OutreachEmailRecipientSerializer(serializers.ModelSerializer):
    class Meta:
        model = OutreachEmailRecipient
        fields = ['id', 'email_address', 'prospect_contact', 'recipient_type']

class OutreachEmailSerializer(serializers.ModelSerializer):
    recipients = OutreachEmailRecipientSerializer(many=True, read_only=True)
    attachments = EmailAttachmentSerializer(many=True, read_only=True)
    estimated_read_time_formatted = serializers.SerializerMethodField()
    reading_engagement = serializers.SerializerMethodField()

    def get_estimated_read_time_formatted(self, obj):
        seconds = obj.total_seconds_spent or 0
        if not obj.open_tracking_enabled:
            return "0s"
        if not obj.is_opened and seconds == 0:
            return "0s"
        if seconds < 60:
            return f"{seconds}s"
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins}m {secs}s" if secs else f"{mins}m"

    def get_reading_engagement(self, obj):
        if not obj.open_tracking_enabled:
            return "Open tracking disabled"
        if not obj.is_opened:
            return "Not Viewed"
        secs = obj.total_seconds_spent or 0
        opens = obj.open_count or 1
        if opens >= 3 or secs >= 60:
            return "Deeply Engaged"
        elif secs >= 15 or opens >= 2:
            return "Read in Detail"
        else:
            return "Quick Skim"

    class Meta:
        model = OutreachEmail
        fields = [
            'id', 'prospect', 'created_by', 'sender_mail_account', 'from_email', 'from_name',
            'subject', 'body', 'signature', 'status', 'sent_at', 'message_id', 'thread_id',
            'in_reply_to', 'references', 'created_at', 'updated_at', 'recipients', 'attachments',
            'is_opened', 'opened_at', 'tracking_token', 'open_tracking_enabled', 'open_count', 'first_opened_at',
            'last_opened_at', 'total_seconds_spent', 'open_history',
            'estimated_read_time_formatted', 'reading_engagement'
        ]
        read_only_fields = [
            'id', 'created_by', 'sender_mail_account', 'status', 'sent_at', 'message_id',
            'thread_id', 'in_reply_to', 'references', 'created_at', 'updated_at', 'is_opened',
            'opened_at', 'tracking_token', 'open_tracking_enabled', 'open_count', 'first_opened_at', 'last_opened_at',
            'total_seconds_spent', 'open_history'
        ]

class CallActivitySerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return 'System'

    class Meta:
        model = CallActivity
        fields = [
            'id', 'prospect', 'prospect_contact', 'created_by', 'created_by_name',
            'company_phone', 'ivr_extension', 'call_status', 'communication_outcome',
            'notes', 'call_started_at', 'call_ended_at', 'created_at'
        ]
        read_only_fields = ['id', 'created_by', 'created_by_name', 'created_at']

class CommunicationActivitySerializer(serializers.ModelSerializer):
    performed_by_name = serializers.SerializerMethodField()
    outreach_email_detail = OutreachEmailSerializer(source='outreach_email', read_only=True)
    call_activity_detail = CallActivitySerializer(source='call_activity', read_only=True)
    contact_name = serializers.CharField(source='prospect_contact.contact_name', read_only=True, allow_null=True)
    prospect_company_name = serializers.CharField(source='prospect.company_name', read_only=True)
    prospect_created_at = serializers.DateTimeField(source='prospect.created_at', read_only=True)

    def get_performed_by_name(self, obj):
        if obj.performed_by:
            return obj.performed_by.get_full_name() or obj.performed_by.username
        return 'System'

    class Meta:
        model = CommunicationActivity
        fields = [
            'id', 'prospect', 'prospect_company_name', 'prospect_created_at', 'prospect_contact', 'contact_name', 'activity_type', 'direction',
            'status', 'outcome', 'subject', 'notes', 'outreach_email', 'outreach_email_detail',
            'call_activity', 'call_activity_detail', 'performed_by', 'performed_by_name', 'created_at'
        ]
        read_only_fields = ['id', 'performed_by', 'performed_by_name', 'created_at']

class AuditReverificationRequestSerializer(serializers.ModelSerializer):
    manager_name = serializers.CharField(source='manager.username', read_only=True)
    pre_user_name = serializers.CharField(source='pre_user.username', read_only=True)
    prospect_company_name = serializers.CharField(source='prospect.company_name', read_only=True)

    class Meta:
        model = AuditReverificationRequest
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at', 'resolved_at', 'manager_notified']


class EmailCampaignAttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailCampaignAttachment
        fields = ['id', 'original_filename', 'mime_type', 'size', 'created_at']
        read_only_fields = ['id', 'created_at']


class EmailCampaignRecipientSerializer(serializers.ModelSerializer):
    prospect_company_name = serializers.CharField(source='prospect.company_name', read_only=True, allow_null=True)
    prospect_contact_name = serializers.CharField(source='prospect_contact.contact_name', read_only=True, allow_null=True)
    tracking = serializers.SerializerMethodField()
    reply = serializers.SerializerMethodField()

    def get_tracking(self, obj):
        oe = obj.outreach_email
        if not oe:
            return None
        open_count = oe.open_count or 0
        total_seconds = oe.total_seconds_spent or 0
        is_opened = oe.is_opened or open_count > 0

        if not oe.open_tracking_enabled:
            engagement = 'Disabled'
        elif is_opened:
            if open_count >= 3 or total_seconds >= 60:
                engagement = 'Deeply Engaged'
            elif total_seconds >= 15 or open_count >= 2:
                engagement = 'Read in Detail'
            else:
                engagement = 'Quick Skim'
        else:
            engagement = 'Unopened'

        read_time_formatted = (
            f"{total_seconds}s" if total_seconds < 60 else f"{total_seconds // 60}m {total_seconds % 60}s"
        ) if (is_opened or total_seconds > 0) else "0s"

        return {
            'id': oe.id,
            'tracking_token': str(oe.tracking_token),
            'open_tracking_enabled': oe.open_tracking_enabled,
            'is_opened': is_opened,
            'open_count': open_count,
            'first_opened_at': oe.first_opened_at.isoformat() if oe.first_opened_at else (oe.opened_at.isoformat() if oe.opened_at else None),
            'last_opened_at': oe.last_opened_at.isoformat() if oe.last_opened_at else (oe.opened_at.isoformat() if oe.opened_at else None),
            'total_seconds_spent': total_seconds,
            'reading_engagement': engagement,
            'estimated_read_time_formatted': read_time_formatted,
            'open_history': oe.open_history or [],
            'thread_id': oe.thread_id or oe.message_id,
            'message_id': oe.message_id,
            'subject': oe.subject,
            'status': oe.status,
            'recipient_email': obj.email_address,
        }

    def get_reply(self, obj):
        from .models import CommunicationActivity
        reply_act = None
        if obj.outreach_email:
            reply_act = CommunicationActivity.objects.filter(
                outreach_email=obj.outreach_email,
                activity_type='EMAIL_RECEIVED'
            ).order_by('-created_at').first()
        if not reply_act and obj.prospect:
            qs = CommunicationActivity.objects.filter(
                prospect=obj.prospect,
                activity_type='EMAIL_RECEIVED'
            )
            if obj.prospect_contact:
                qs = qs.filter(prospect_contact=obj.prospect_contact)
            if obj.sent_at:
                qs = qs.filter(created_at__gte=obj.sent_at)
            reply_act = qs.order_by('-created_at').first()

        has_reply = bool(reply_act) or (obj.outreach_email and obj.outreach_email.status == 'RECEIVED RESPONSE')
        if has_reply:
            return {
                'has_reply': True,
                'replied_at': reply_act.created_at.isoformat() if reply_act else (obj.outreach_email.updated_at.isoformat() if obj.outreach_email else None),
                'subject': reply_act.subject if reply_act else (f"Re: {obj.campaign.subject}"),
                'snippet': reply_act.notes if reply_act else '',
                'thread_id': (obj.outreach_email.thread_id if obj.outreach_email else None) or (obj.outreach_email.message_id if obj.outreach_email else None),
                'email_address': obj.email_address,
            }
        return {
            'has_reply': False,
            'replied_at': None,
            'subject': None,
            'snippet': None,
            'thread_id': (obj.outreach_email.thread_id if obj.outreach_email else None) or (obj.outreach_email.message_id if obj.outreach_email else None),
            'email_address': obj.email_address,
        }

    class Meta:
        model = EmailCampaignRecipient
        fields = [
            'id', 'email_address', 'recipient_name', 'prospect', 'prospect_company_name',
            'prospect_contact', 'prospect_contact_name', 'section_number',
            'custom_subject', 'custom_body', 'outreach_snapshot',
            'queue_order', 'status', 'attempt_count', 'scheduled_for',
            'last_attempt_at', 'sent_at', 'error_message', 'outreach_email',
            'tracking', 'reply', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class EmailCampaignSerializer(serializers.ModelSerializer):
    created_by_name = serializers.SerializerMethodField()
    total_count = serializers.IntegerField(read_only=True)
    draft_count = serializers.IntegerField(read_only=True)
    sent_count = serializers.IntegerField(read_only=True)
    failed_count = serializers.IntegerField(read_only=True)
    pending_count = serializers.IntegerField(read_only=True)
    sections_count = serializers.SerializerMethodField()
    attachments_count = serializers.SerializerMethodField()

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return 'System'

    def get_attachments_count(self, obj):
        return obj.attachments.count()

    def get_sections_count(self, obj):
        total = obj.total_count
        return (total + 9) // 10 if total > 0 else 0

    class Meta:
        model = EmailCampaign
        fields = [
            'id', 'name', 'sender_email', 'subject', 'interval_seconds', 'open_tracking_enabled',
            'status', 'total_count', 'draft_count', 'sent_count', 'failed_count', 'pending_count',
            'sections_count', 'attachments_count', 'started_at', 'paused_at', 'completed_at',
            'cancelled_at', 'last_sent_at', 'next_eligible_at', 'created_at', 'updated_at',
            'created_by_name'
        ]
        read_only_fields = [
            'id', 'sender_email', 'status', 'total_count', 'draft_count', 'sent_count',
            'failed_count', 'pending_count', 'sections_count', 'attachments_count',
            'started_at', 'paused_at', 'completed_at', 'cancelled_at', 'last_sent_at',
            'next_eligible_at', 'created_at', 'updated_at', 'created_by_name'
        ]


class EmailCampaignDetailSerializer(EmailCampaignSerializer):
    recipients = EmailCampaignRecipientSerializer(many=True, read_only=True)
    attachments = EmailCampaignAttachmentSerializer(many=True, read_only=True)
    sections = serializers.SerializerMethodField()

    def get_sections(self, obj):
        recs = list(obj.recipients.all().order_by('queue_order'))
        by_sec = {}
        for r in recs:
            s_num = r.section_number or ((r.queue_order // 10) + 1)
            by_sec.setdefault(s_num, []).append(r)

        sections_list = []
        for s_num in sorted(by_sec.keys()):
            items = by_sec[s_num]
            total = len(items)
            drafts = sum(1 for r in items if r.status == 'DRAFT')
            pending = sum(1 for r in items if r.status in ('PENDING', 'SENDING', 'RETRY_PENDING'))
            sent = sum(1 for r in items if r.status == 'SENT')
            failed = sum(1 for r in items if r.status == 'FAILED')

            if pending > 0:
                sec_status = 'SENDING'
            elif drafts > 0 and sent == 0 and failed == 0:
                sec_status = 'DRAFT'
            elif sent == total and total > 0:
                sec_status = 'COMPLETED'
            elif sent + failed == total and total > 0:
                sec_status = 'COMPLETED_WITH_ERRORS'
            else:
                sec_status = 'PARTIAL'

            sections_list.append({
                'section_number': s_num,
                'label': f"Section {s_num}",
                'total_count': total,
                'draft_count': drafts,
                'pending_count': pending,
                'sent_count': sent,
                'failed_count': failed,
                'status': sec_status,
                'can_send': (drafts > 0 or failed > 0) and obj.status != 'CANCELLED',
            })
        return sections_list

    class Meta(EmailCampaignSerializer.Meta):
        fields = EmailCampaignSerializer.Meta.fields + ['body', 'template_id', 'signature_id', 'sections', 'recipients', 'attachments']


class EmailThreadMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailThreadMessage
        fields = [
            'id',
            'direction',
            'source',
            'status',
            'external_message_id',
            'sender_email',
            'sender_name',
            'to_emails',
            'cc_emails',
            'subject',
            'body_text',
            'body_html',
            'snippet',
            'attachments_metadata',
            'error_message',
            'sent_at',
            'created_at',
        ]
        read_only_fields = fields


class EmailThreadListSerializer(serializers.ModelSerializer):
    pre_user = serializers.SerializerMethodField()
    prospect_name = serializers.SerializerMethodField()
    prospect_contact_name = serializers.SerializerMethodField()
    latest_sender_email = serializers.SerializerMethodField()
    latest_recipient_email = serializers.SerializerMethodField()

    def get_pre_user(self, obj):
        owner = obj.owner
        if not owner:
            return None
        profile = getattr(owner, 'profile', None)
        return {
            'id': owner.id,
            'name': owner.get_full_name() or owner.username,
            'username': owner.username,
            'email': owner.email,
            'role': getattr(profile, 'role', 'PRE'),
        }

    def get_prospect_name(self, obj):
        if obj.prospect:
            return obj.prospect.company_name
        return None

    def get_prospect_contact_name(self, obj):
        if obj.prospect_contact:
            return obj.prospect_contact.contact_name
        return obj.correspondent_name or None

    def get_latest_sender_email(self, obj):
        if obj.last_direction == EmailThread.Direction.OUTBOUND:
            return obj.mailbox_email
        return obj.correspondent_email

    def get_latest_recipient_email(self, obj):
        if obj.last_direction == EmailThread.Direction.OUTBOUND:
            return obj.correspondent_email
        return obj.mailbox_email

    class Meta:
        model = EmailThread
        fields = [
            'id',
            'pre_user',
            'mailbox_email',
            'correspondent_email',
            'correspondent_name',
            'latest_sender_email',
            'latest_recipient_email',
            'prospect',
            'prospect_name',
            'prospect_contact',
            'prospect_contact_name',
            'external_thread_id',
            'subject',
            'match_status',
            'status',
            'last_direction',
            'last_message_at',
            'last_snippet',
            'message_count',
            'unread_count',
            'summary_text',
            'next_action',
            'summary_status',
            'summary_provider',
            'summary_model',
            'summary_error',
            'summary_generated_at',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


class EmailThreadDetailSerializer(EmailThreadListSerializer):
    messages = serializers.SerializerMethodField()

    def get_messages(self, obj):
        ordered = obj.messages.all().order_by('sent_at', 'created_at')
        return EmailThreadMessageSerializer(ordered, many=True).data

    class Meta(EmailThreadListSerializer.Meta):
        fields = EmailThreadListSerializer.Meta.fields + ['messages']

