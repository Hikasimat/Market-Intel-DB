from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
import uuid
from django.db import models
from django.core.exceptions import ValidationError

class Prospect(models.Model):
    class Structure(models.TextChoices):
        PARENT = 'Parent', 'Parent Organization'
        BRANCH = 'Branch', 'Branch Office'
        SUBSIDIARY = 'Subsidiary', 'Subsidiary Company'

    class Status(models.TextChoices):
        ACTIVE = 'Active', 'Active'
        INACTIVE = 'Inactive', 'Inactive'
        PERMANENTLY_CLOSED = 'Permanently Closed', 'Permanently Closed'
        ACQUIRED = 'Acquired', 'Acquired'
        MERGED = 'Merged', 'Merged'

    class OfferingType(models.TextChoices):
        PRODUCTS = 'Products', 'Products'
        SERVICES = 'Services', 'Services'
        SOLUTIONS = 'Solutions', 'Solutions'
        MULTIPLE = 'Multiple', 'Multiple'

    class OwnershipSector(models.TextChoices):
        PRIVATE = 'Private Company', 'Private Company'
        GOVERNMENT = 'Government Company', 'Government Company'
        SEMI_GOVERNMENT = 'Semi Government Company', 'Semi Government Company'



    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company_name = models.CharField(max_length=255)
    country_head_office = models.CharField(max_length=255)
    complete_address = models.TextField()

    official_phone_number = models.CharField(max_length=255, blank=True, null=True)
    official_email_address = models.EmailField(blank=True, null=True)
    official_website_url = models.URLField(blank=True, null=True)
    linkedin_company_page = models.URLField(blank=True, null=True)

    primary_industries = models.CharField(max_length=255)

    company_structure = models.CharField(max_length=50, choices=Structure.choices)
    operational_status = models.CharField(max_length=50, choices=Status.choices)

    parent_companies = models.ManyToManyField('self', symmetrical=False, blank=True, related_name='child_companies')
    merging_companies = models.ManyToManyField('self', symmetrical=False, blank=True, related_name='merged_into_prospects')
    dissolved_companies = models.ManyToManyField('self', symmetrical=False, blank=True, related_name='dissolved_into_prospects')
    acquiring_companies = models.ManyToManyField(
        'self', 
        through='ProspectAcquisition', 
        symmetrical=False, 
        blank=True, 
        related_name='acquired_companies_rev'
    )

    ownership_sector = models.CharField(max_length=50, choices=OwnershipSector.choices, default=OwnershipSector.PRIVATE)
    primary_offering_type = models.CharField(max_length=50, choices=OfferingType.choices)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    updated_by = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.company_name

class ProspectOffering(models.Model):
    class OfferingTypeChoice(models.TextChoices):
        PRODUCT = 'Product', 'Product'
        SERVICE = 'Service', 'Service'
        SOLUTION = 'Solution', 'Solution'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name='offerings')
    offering_type = models.CharField(max_length=20, choices=OfferingTypeChoice.choices)
    name = models.CharField(max_length=255)
    display_order = models.IntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.prospect.company_name} - {self.get_offering_type_display()} - {self.name}"

class ProspectContact(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name='key_contacts')
    prefix = models.CharField(max_length=50, blank=True, null=True)
    contact_name = models.CharField(max_length=255)
    designation = models.CharField(max_length=255, blank=True, null=True)
    official_email = models.EmailField(blank=True, null=True)
    phone_number = models.CharField(max_length=255, blank=True, null=True)
    phone_digits = models.CharField(max_length=50, blank=True, null=True, db_index=True)
    linkedin_profile = models.URLField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if self.phone_number:
            import re
            self.phone_digits = re.sub(r"\D+", "", str(self.phone_number))
        else:
            self.phone_digits = None
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.contact_name} ({self.prospect.company_name})"

class LeadQualification(models.Model):
    class VerificationStatus(models.TextChoices):
        UNVERIFIED = 'Unverified', 'Unverified'
        IN_PROGRESS = 'In Progress', 'In Progress'
        VERIFIED = 'Verified', 'Verified'

    class QualificationStatus(models.TextChoices):
        UNQUALIFIED = 'Unqualified', 'Unqualified'
        HOT_LEAD = 'Hot Lead', 'Hot Lead'
        QUALIFIED = 'Qualified', 'Qualified'
        NURTURE = 'Nurture', 'Nurture'
        DISQUALIFIED = 'Disqualified', 'Disqualified'
        LEAD_FREEZE = 'Lead Freeze', 'Lead Freeze'
        LEAD_QUALIFIED = 'Lead Qualified', 'Lead Qualified'

    class PreTaskStatus(models.TextChoices):
        NONE = 'NONE', 'None'
        ISSUE_SENT_TO_PRE = 'ISSUE_SENT_TO_PRE', 'Issue Sent to PRE'
        PRE_UPDATED = 'PRE_UPDATED', 'PRE Updated Data'

    prospect = models.OneToOneField(Prospect, on_delete=models.CASCADE, related_name='lead_qualification')

    verification_status = models.CharField(max_length=50, choices=VerificationStatus.choices, default=VerificationStatus.UNVERIFIED)
    qualification_status = models.CharField(max_length=50, choices=QualificationStatus.choices, default=QualificationStatus.UNQUALIFIED)
    pre_task_status = models.CharField(max_length=50, choices=PreTaskStatus.choices, default=PreTaskStatus.NONE)
    verification_checklist = models.JSONField(default=dict, blank=True)
    email_status = models.CharField(max_length=50, default='Not Sent', blank=True, null=True)

    attended_meeting = models.BooleanField(default=False)
    qualification_score = models.IntegerField(default=0)
    lq_notes = models.TextField(blank=True, null=True)
    completed_tasks_log = models.JSONField(default=list, blank=True)

    assigned_lq = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_prospects')

    qualified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='qualifications_performed')
    qualified_at = models.DateTimeField(null=True, blank=True)

    # Audit timestamp: set when attended_meeting transitions False -> True
    attended_at = models.DateTimeField(null=True, blank=True)

    # Qualification decision tracking: who made a qualification decision and when
    decision_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='qualification_decisions')
    decision_at = models.DateTimeField(null=True, blank=True)

    # Issue Reporting
    issue_category = models.CharField(max_length=255, blank=True, null=True)
    issue_details = models.TextField(blank=True, null=True)
    issue_reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='issues_reported')
    issue_reported_at = models.DateTimeField(null=True, blank=True)

    budget = models.BooleanField(default=False)
    authority = models.BooleanField(default=False)
    need = models.BooleanField(default=False)
    timeline = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"LQ for {self.prospect.company_name}"

def assign_lq_to_prospect(prospect):
    """
    Assigns (or re-assigns if NULL) the correct LQ user to a prospect's
    LeadQualification record using round-robin batches of 5.
    Always guaranteed to assign when LQ users exist.
    Returns the assigned User or None.
    """
    from django.contrib.auth import get_user_model
    User = get_user_model()
    lq_users = list(User.objects.filter(profile__role='LQ', is_superuser=False).order_by('id'))
    if not lq_users:
        return None
    N = len(lq_users)
    # Use total prospects excluding this one to get a stable index
    count = Prospect.objects.exclude(id=prospect.id).count()
    current_index = (count // 5) % N
    assigned = lq_users[current_index]
    try:
        lq, created_now = LeadQualification.objects.get_or_create(prospect=prospect)
        lq.assigned_lq = assigned
        lq.save(update_fields=['assigned_lq'])
    except Exception as e:
        print(f"[assign_lq_to_prospect] Error: {e}")
        return None
    return assigned


@receiver(post_save, sender=Prospect)
def create_lead_qualification(sender, instance, created, **kwargs):
    if created:
        assign_lq_to_prospect(instance)



class CallbackReminder(models.Model):
    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name='reminders')
    prospect_contact = models.ForeignKey(ProspectContact, on_delete=models.CASCADE, null=True, blank=True, related_name='reminders')
    scheduled_datetime = models.DateTimeField()
    description = models.TextField(blank=True, null=True)
    is_completed = models.BooleanField(default=False)

    notified_30m = models.BooleanField(default=False)
    notified_15m = models.BooleanField(default=False)
    notified_5m = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Reminder for {self.prospect.company_name} at {self.scheduled_datetime}"

class Meeting(models.Model):
    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name='meetings')
    prospect_contact = models.ForeignKey(ProspectContact, on_delete=models.CASCADE, null=True, blank=True, related_name='meetings')
    scheduled_datetime = models.DateTimeField()
    meeting_link = models.CharField(max_length=512, blank=True, null=True)
    agenda = models.TextField(blank=True, null=True)
    is_completed = models.BooleanField(default=False)

    # Google Calendar / Meet sync (all optional; manual-link meetings leave these blank)
    MEETING_PROVIDER_CHOICES = (('MANUAL', 'Manual link'), ('GOOGLE_MEET', 'Google Meet'))
    meeting_provider = models.CharField(max_length=20, choices=MEETING_PROVIDER_CHOICES, default='MANUAL')
    google_event_id = models.CharField(max_length=255, blank=True, null=True)
    google_calendar_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    conference_status = models.CharField(max_length=20, blank=True, default='')
    client_request_id = models.CharField(
        max_length=64, blank=True, null=True, unique=True,
        help_text='Idempotency key supplied by the client for Google Meet creation.'
    )

    notified_1h = models.BooleanField(default=False)
    notified_30m = models.BooleanField(default=False)
    notified_15m = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Meeting for {self.prospect.company_name} at {self.scheduled_datetime}"

class OutreachEmail(models.Model):
    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, null=True, blank=True, related_name='outreach_emails')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    sender_mail_account = models.ForeignKey('accounts.MailAccount', on_delete=models.SET_NULL, null=True, blank=True)
    from_email = models.CharField(max_length=255)
    from_name = models.CharField(max_length=255, blank=True, null=True)
    subject = models.CharField(max_length=512)


    body = models.TextField(default='', blank=True)
    signature = models.TextField(blank=True, null=True)
    status = models.CharField(max_length=50, choices=(('NOT SENT', 'Not Sent'), ('SENT', 'Sent'), ('WAITING FOR RESPONSE', 'Waiting for Response'), ('RECEIVED RESPONSE', 'Received Response'), ('FAILED', 'Failed')), default='NOT SENT')
    sent_at = models.DateTimeField(null=True, blank=True)
    message_id = models.CharField(max_length=255, blank=True, null=True)
    thread_id = models.CharField(max_length=255, blank=True, null=True)
    in_reply_to = models.CharField(max_length=255, blank=True, null=True)
    references = models.TextField(blank=True, null=True)
    # Email open tracking
    # Effective state: True only if the user opted in AND the global setting allowed it
    # at send time. Legacy rows (sent before this field existed) are backfilled to True.
    open_tracking_enabled = models.BooleanField(default=False)
    tracking_token = models.UUIDField(default=uuid.uuid4, db_index=True, editable=False)
    is_opened = models.BooleanField(default=False)
    opened_at = models.DateTimeField(null=True, blank=True)
    open_count = models.PositiveIntegerField(default=0)
    first_opened_at = models.DateTimeField(null=True, blank=True)
    last_opened_at = models.DateTimeField(null=True, blank=True)
    total_seconds_spent = models.PositiveIntegerField(default=0)
    open_history = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class AuditReverificationRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = 'Pending', 'Pending'
        CORRECTED = 'Corrected', 'Corrected'

    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name='reverification_requests')
    manager = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='reverifications_sent')
    pre_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='reverifications_received')
    
    highlighted_fields = models.JSONField(default=list)
    manager_notes = models.TextField(blank=True, null=True)
    
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.PENDING)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    resolved_at = models.DateTimeField(null=True, blank=True)
    manager_notified = models.BooleanField(default=False)

    def __str__(self):
        return f"Re-Verify {self.prospect.company_name} (Status: {self.status})"

class OutreachEmailRecipient(models.Model):
    outreach_email = models.ForeignKey(OutreachEmail, on_delete=models.CASCADE, related_name='recipients')
    email_address = models.EmailField()
    prospect_contact = models.ForeignKey(ProspectContact, on_delete=models.SET_NULL, null=True, blank=True)
    recipient_type = models.CharField(max_length=10, choices=(('TO', 'TO'), ('CC', 'CC'), ('BCC', 'BCC')))

class EmailAttachment(models.Model):
    outreach_email = models.ForeignKey(OutreachEmail, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='attachments/%Y/%m/%d/')
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=255)
    size = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

class CallActivity(models.Model):
    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name='call_activities')
    prospect_contact = models.ForeignKey(ProspectContact, on_delete=models.SET_NULL, null=True, blank=True, related_name='call_activities')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    company_phone = models.CharField(max_length=255, blank=True, null=True)
    ivr_extension = models.CharField(max_length=50, blank=True, null=True)
    call_status = models.CharField(max_length=100)
    communication_outcome = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    call_started_at = models.DateTimeField(null=True, blank=True)
    call_ended_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class CommunicationActivity(models.Model):
    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name='communication_timeline')
    prospect_contact = models.ForeignKey(ProspectContact, on_delete=models.SET_NULL, null=True, blank=True, related_name='communication_timeline')
    activity_type = models.CharField(max_length=50, choices=(('EMAIL_SENT', 'Email Sent'), ('EMAIL_RECEIVED', 'Email Received'), ('CALL', 'Call')))
    direction = models.CharField(max_length=20, choices=(('OUTBOUND', 'Outbound'), ('INBOUND', 'Inbound')), default='OUTBOUND')
    status = models.CharField(max_length=255, blank=True, null=True)
    outcome = models.CharField(max_length=255, blank=True, null=True)
    subject = models.CharField(max_length=512, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    outreach_email = models.ForeignKey(OutreachEmail, on_delete=models.SET_NULL, null=True, blank=True)
    call_activity = models.ForeignKey(CallActivity, on_delete=models.SET_NULL, null=True, blank=True)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class EmailVerification(models.Model):
    class VerificationStatus(models.TextChoices):
        UNVERIFIED = 'UNVERIFIED', 'Unverified'
        VALID = 'VALID', 'Valid'
        INVALID = 'INVALID', 'Invalid'
        UNKNOWN = 'UNKNOWN', 'Unknown'

    class VerificationMethod(models.TextChoices):
        SYNTAX = 'SYNTAX', 'Syntax'
        DNS = 'DNS', 'DNS'
        MX = 'MX', 'MX'
        SMTP = 'SMTP', 'SMTP'
        COMBINED = 'COMBINED', 'Combined'
        MANUAL_CONFIRMATION = 'MANUAL_CONFIRMATION', 'Manual Confirmation'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    prospect = models.ForeignKey(Prospect, on_delete=models.CASCADE, related_name='email_verifications')
    prospect_contact = models.ForeignKey(ProspectContact, on_delete=models.CASCADE, null=True, blank=True, related_name='email_verifications')
    email_address = models.EmailField()
    verification_status = models.CharField(max_length=50, choices=VerificationStatus.choices, default=VerificationStatus.UNVERIFIED)
    verification_method = models.CharField(max_length=50, choices=VerificationMethod.choices, default=VerificationMethod.COMBINED)

    syntax_valid = models.BooleanField(default=False)
    domain_valid = models.BooleanField(default=False)
    mx_found = models.BooleanField(default=False)
    smtp_checked = models.BooleanField(default=False)
    smtp_valid = models.BooleanField(default=False)

    is_disposable = models.BooleanField(default=False)
    is_role_account = models.BooleanField(default=False)
    is_catch_all = models.BooleanField(default=False)

    reason = models.TextField(blank=True, null=True)

    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='verifications_performed')

    confirmed_by_lq = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='verifications_confirmed')
    confirmed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['prospect', 'prospect_contact', 'email_address'], name='unique_prospect_contact_email_verification')
        ]

    def __str__(self):
        return f"{self.email_address} - {self.verification_status}"

class ProspectShareholding(models.Model):
    class HolderType(models.TextChoices):
        COMPANY = "Company", "Company"
        INDIVIDUAL = "Individual", "Individual"
        GOVERNMENT = "Government", "Country or State"
        OTHER = "Other", "Others"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    prospect = models.ForeignKey(
        Prospect,
        on_delete=models.CASCADE,
        related_name="shareholdings"
    )

    holder_type = models.CharField(
        max_length=20,
        choices=HolderType.choices
    )

    company = models.ForeignKey(
        Prospect,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="owned_shareholdings"
    )

    contact = models.ForeignKey(
        ProspectContact,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="shareholdings"
    )

    government_entity = models.ForeignKey(
        'GovernmentEntity',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="shareholdings"
    )

    other_name = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    share_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.holder_type == self.HolderType.COMPANY:
            if not self.company:
                raise ValidationError("Company is required when holder_type is Company.")
            self.contact = None
            self.government_entity = None
            self.other_name = None
        elif self.holder_type == self.HolderType.INDIVIDUAL:
            if not self.contact:
                raise ValidationError("Contact is required when holder_type is Individual.")
            self.company = None
            self.government_entity = None
            self.other_name = None
        elif self.holder_type == self.HolderType.GOVERNMENT:
            if not self.government_entity:
                raise ValidationError("Government Entity is required when holder_type is Government.")
            self.company = None
            self.contact = None
            self.other_name = None
        elif self.holder_type == self.HolderType.OTHER:
            if not self.other_name:
                raise ValidationError("Name is required when holder_type is Other.")
            self.company = None
            self.contact = None
            self.government_entity = None

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.holder_type == self.HolderType.COMPANY and self.company:
            return f"{self.company.company_name} - {self.share_percentage}%"
        elif self.holder_type == self.HolderType.INDIVIDUAL and self.contact:
            return f"{self.contact.contact_name} - {self.share_percentage}%"
        elif self.holder_type == self.HolderType.GOVERNMENT and self.government_entity:
            return f"{self.government_entity.name} - {self.share_percentage}%"
        elif self.holder_type == self.HolderType.OTHER and self.other_name:
            return f"{self.other_name} - {self.share_percentage}%"
        return f"Shareholding {self.id} - {self.share_percentage}%"

class GovernmentEntity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    country = models.CharField(max_length=255)
    
    is_state_government = models.BooleanField(default=False)
    state_name = models.CharField(max_length=255, blank=True, null=True)
    # A state government belongs to a central government
    central_government = models.ForeignKey(
        'self', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True, 
        related_name='state_entities',
        limit_choices_to={'is_state_government': False}
    )

    official_website = models.URLField(blank=True, null=True)
    official_email = models.EmailField(blank=True, null=True)
    phone_number = models.CharField(max_length=255, blank=True, null=True)
    complete_address = models.TextField(blank=True, null=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.CharField(max_length=255, blank=True, null=True)
    updated_by = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({'State' if self.is_state_government else 'Central'})"


class ProspectImportHistory(models.Model):
    """Lightweight record of a Prospect Excel/CSV import (no file storage)."""
    class Status(models.TextChoices):
        COMPLETED = 'COMPLETED', 'Completed'
        PARTIAL = 'PARTIAL', 'Partial'
        FAILED = 'FAILED', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='prospect_imports')
    file_name = models.CharField(max_length=255, blank=True, default='')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.COMPLETED)
    processed_source_rows = models.PositiveIntegerField(default=0)
    imported_count = models.PositiveIntegerField(default=0)
    not_imported_count = models.PositiveIntegerField(default=0)
    parent_auto_created_count = models.PositiveIntegerField(default=0)
    limit_reached = models.BooleanField(default=False)
    # [{source_row_numbers, company_name, prospect_id}]
    imported_rows = models.JSONField(default=list, blank=True)
    # [{source_row_numbers, company_name, reason}]
    not_imported_rows = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Import {self.file_name} ({self.status})"

class ProspectAcquisition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    acquired_prospect = models.ForeignKey(Prospect, related_name='acquisition_records', on_delete=models.CASCADE)
    acquiring_prospect = models.ForeignKey(Prospect, related_name='acquired_records', on_delete=models.CASCADE)
    acquired_shares = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('acquired_prospect', 'acquiring_prospect')

    def __str__(self):
        return f"{self.acquiring_prospect.company_name} acquired {self.acquired_prospect.company_name}"


class EmailCampaign(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Draft'
        QUEUED = 'QUEUED', 'Queued'
        RUNNING = 'RUNNING', 'Running'
        PAUSED = 'PAUSED', 'Paused'
        COMPLETED = 'COMPLETED', 'Completed'
        COMPLETED_WITH_ERRORS = 'COMPLETED_WITH_ERRORS', 'Completed with Errors'
        CANCELLED = 'CANCELLED', 'Cancelled'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='email_campaigns')
    sender_email = models.EmailField()
    subject = models.CharField(max_length=512)
    body = models.TextField()
    template_id = models.CharField(max_length=255, blank=True, null=True)
    signature_id = models.CharField(max_length=255, blank=True, null=True)
    open_tracking_enabled = models.BooleanField(default=False)
    interval_seconds = models.PositiveIntegerField(default=90)
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.QUEUED)

    # State tracking and scheduling timestamps
    started_at = models.DateTimeField(null=True, blank=True)
    paused_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    next_eligible_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Campaign: {self.name} ({self.status})"

    @property
    def total_count(self):
        return self.recipients.count()

    @property
    def sent_count(self):
        return self.recipients.filter(status='SENT').count()

    @property
    def failed_count(self):
        return self.recipients.filter(status='FAILED').count()

    @property
    def pending_count(self):
        return self.recipients.filter(status__in=['PENDING', 'SENDING', 'RETRY_PENDING']).count()


class EmailCampaignRecipient(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        SENDING = 'SENDING', 'Sending'
        SENT = 'SENT', 'Sent'
        RETRY_PENDING = 'RETRY_PENDING', 'Retry Pending'
        FAILED = 'FAILED', 'Failed'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(EmailCampaign, on_delete=models.CASCADE, related_name='recipients')
    email_address = models.EmailField()
    recipient_name = models.CharField(max_length=255, blank=True, null=True)
    prospect = models.ForeignKey(Prospect, on_delete=models.SET_NULL, null=True, blank=True, related_name='campaign_recipients')
    prospect_contact = models.ForeignKey(ProspectContact, on_delete=models.SET_NULL, null=True, blank=True, related_name='campaign_recipients')
    queue_order = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=50, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveIntegerField(default=0)
    max_retries = models.PositiveIntegerField(default=3)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, null=True)
    outreach_email = models.ForeignKey(OutreachEmail, on_delete=models.SET_NULL, null=True, blank=True, related_name='campaign_recipients')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['queue_order', 'created_at']
        constraints = [
            models.UniqueConstraint(fields=['campaign', 'email_address'], name='unique_campaign_recipient_email')
        ]

    def __str__(self):
        return f"{self.email_address} in {self.campaign.name} ({self.status})"


class EmailCampaignAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    campaign = models.ForeignKey(EmailCampaign, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='campaign_attachments/%Y/%m/%d/')
    original_filename = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=255)
    size = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.original_filename} ({self.campaign.name})"

