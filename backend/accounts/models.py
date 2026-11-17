from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

class UserProfile(models.Model):
    ROLE_CHOICES = (
        ('PRE', 'Prospect Research Engineer'),
        ('MANAGER', 'Manager'),
        ('DM', 'Digital Marketing'),
    )
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='PRE')
    company = models.ForeignKey('companies.Company', on_delete=models.SET_NULL, null=True, blank=True, related_name='user_profiles')
    timezone = models.CharField(max_length=64, default='UTC')
    mail_account = models.ForeignKey('MailAccount', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_users')
    whatsapp_sessions = models.ManyToManyField('whatsapp.WhatsAppSession', blank=True, related_name='assigned_profiles')

    def __str__(self):
        return f"{self.user.username} - {self.get_role_display()}"

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()

class MailAccount(models.Model):
    name = models.CharField(max_length=255, unique=True, help_text="e.g. Sales General Inbox")
    email_address = models.EmailField(unique=True)
    display_name = models.CharField(max_length=255)
    smtp_host = models.CharField(max_length=255)
    smtp_port = models.IntegerField(default=587)
    smtp_security = models.CharField(max_length=20, choices=(('TLS', 'TLS/STARTTLS'), ('SSL', 'SSL/TLS')), default='TLS')
    smtp_username = models.CharField(max_length=255)
    smtp_app_password_encrypted = models.TextField()
    smtp_status = models.CharField(max_length=20, choices=(('CONFIGURED', 'Configured'), ('VERIFIED', 'Verified'), ('FAILED', 'Failed')), default='CONFIGURED')
    imap_host = models.CharField(max_length=255)
    imap_port = models.IntegerField(default=993)
    imap_security = models.CharField(max_length=20, choices=(('TLS', 'TLS/STARTTLS'), ('SSL', 'SSL/TLS')), default='SSL')
    imap_username = models.CharField(max_length=255)
    imap_app_password_encrypted = models.TextField()
    imap_status = models.CharField(max_length=20, choices=(('CONFIGURED', 'Configured'), ('CONNECTED', 'Connected'), ('FAILED', 'Failed')), default='CONFIGURED')
    default_signature = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    last_imap_sync_at = models.DateTimeField(null=True, blank=True)
    last_sync_status = models.CharField(max_length=50, blank=True, null=True)
    last_sync_error = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.email_address})"


import uuid as _uuid


class _OwnedDesignBase(models.Model):
    """Shared fields for LQ-owned reusable email designs (templates / signatures)."""
    id = models.UUIDField(primary_key=True, default=_uuid.uuid4, editable=False)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='+')
    name = models.CharField(max_length=150)
    project_data = models.JSONField(default=dict, blank=True)
    html = models.TextField(blank=True, default='')
    text = models.TextField(blank=True, default='')
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ['-is_default', '-updated_at']

    def __str__(self):
        return f"{self.name} ({self.owner_id})"

    def save(self, *args, **kwargs):
        from django.db import transaction
        with transaction.atomic():
            if self.is_default:
                type(self).objects.filter(owner=self.owner, is_default=True).exclude(pk=self.pk).update(is_default=False)
            super().save(*args, **kwargs)


class EmailTemplate(_OwnedDesignBase):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_templates')
    description = models.CharField(max_length=500, blank=True, default='')
    subject = models.CharField(max_length=255, blank=True, default='')

    class Meta(_OwnedDesignBase.Meta):
        constraints = [
            models.UniqueConstraint(fields=['owner'], condition=models.Q(is_default=True), name='uniq_default_email_template_per_owner'),
        ]


class EmailSignatureTemplate(_OwnedDesignBase):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='email_signatures')

    class Meta(_OwnedDesignBase.Meta):
        constraints = [
            models.UniqueConstraint(fields=['owner'], condition=models.Q(is_default=True), name='uniq_default_email_signature_per_owner'),
        ]


class GoogleMailCredentials(models.Model):
    """
    Stores encrypted OAuth tokens for a user's authorized Gmail mailbox.
    Separated from User/UserProfile and login identity tokens.
    Access and refresh tokens are encrypted at rest with Fernet using
    MAIL_CREDENTIALS_ENCRYPTION_KEY.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='google_mail_credentials')
    email = models.EmailField()
    access_token_encrypted = models.TextField()
    refresh_token_encrypted = models.TextField(blank=True, default='')
    token_expiry = models.DateTimeField(null=True, blank=True)
    scopes = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Google Mail Credential'
        verbose_name_plural = 'Google Mail Credentials'

    def __str__(self):
        return f"GoogleMail({self.email}) for {self.user.username}"


class GoogleCalendarCredentials(models.Model):
    """
    Encrypted OAuth tokens for a user's *optional* Google Calendar connection.
    Fully isolated from GoogleMailCredentials: separate consent, scopes and lifecycle.
    Tokens are Fernet-encrypted at rest and never returned to the frontend.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='google_calendar_credentials')
    email = models.EmailField(blank=True, default='')
    access_token_encrypted = models.TextField()
    refresh_token_encrypted = models.TextField(blank=True, default='')
    token_expiry = models.DateTimeField(null=True, blank=True)
    scopes = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Google Calendar Credential'
        verbose_name_plural = 'Google Calendar Credentials'

    def __str__(self):
        return f"GoogleCalendar({self.email}) for {self.user.username}"


class ZoomCredentials(models.Model):
    """
    Encrypted OAuth tokens for a user's Zoom account.
    Tokens are Fernet-encrypted at rest and never returned to the frontend.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='zoom_credentials')
    email = models.EmailField(blank=True, default='')
    zoom_user_id = models.CharField(max_length=255, blank=True, default='')
    access_token_encrypted = models.TextField()
    refresh_token_encrypted = models.TextField(blank=True, default='')
    token_expiry = models.DateTimeField(null=True, blank=True)
    scopes = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Zoom Credential'
        verbose_name_plural = 'Zoom Credentials'

    def __str__(self):
        return f"Zoom({self.email}) for {self.user.username}"


class MicrosoftCalendarCredentials(models.Model):
    """
    Encrypted OAuth tokens for a user's Microsoft 365 / Outlook / Teams connection.
    Tokens are Fernet-encrypted at rest and never returned to the frontend.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='microsoft_calendar_credentials')
    email = models.EmailField(blank=True, default='')
    ms_user_id = models.CharField(max_length=255, blank=True, default='')
    access_token_encrypted = models.TextField()
    refresh_token_encrypted = models.TextField(blank=True, default='')
    token_expiry = models.DateTimeField(null=True, blank=True)
    scopes = models.TextField(blank=True, default='')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Microsoft Calendar Credential'
        verbose_name_plural = 'Microsoft Calendar Credentials'

    def __str__(self):
        return f"MicrosoftCalendar({self.email}) for {self.user.username}"


class EmailAttachmentLibraryItem(models.Model):
    """
    User-managed attachment library items (up to 5 per user).
    Allows quick re-attachment of standard collaterals, brochures, pitch decks, etc.
    """
    id = models.UUIDField(primary_key=True, default=_uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='attachment_library_items')
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to='attachment_library/%Y/%m/')
    file_size = models.PositiveIntegerField(default=0)
    content_type = models.CharField(max_length=150, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Email Attachment Library Item'
        verbose_name_plural = 'Email Attachment Library Items'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.user.username})"






class CalendarEventRecording(models.Model):
    """Meet recording for a Google Calendar event that has no linked prospect Meeting.

    Mirrors the recording fields of prospects.Meeting so GoogleMeetRestService can
    treat both the same way.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='calendar_event_recordings')
    event_id = models.CharField(max_length=255)
    meeting_link = models.CharField(max_length=512, blank=True, default='')
    recording_file = models.FileField(upload_to='meeting_recordings/%Y/%m/', null=True, blank=True)
    recording_status = models.CharField(max_length=50, blank=True, default='NONE')
    recording_downloaded_at = models.DateTimeField(null=True, blank=True)
    recording_file_size = models.BigIntegerField(null=True, blank=True)
    recording_mime_type = models.CharField(max_length=100, blank=True, default='')
    google_conference_record_id = models.CharField(max_length=255, blank=True, default='')
    google_recording_id = models.CharField(max_length=255, blank=True, default='')
    recording_drive_file_id = models.CharField(max_length=255, blank=True, default='')
    transcript_text = models.TextField(blank=True, default='')
    transcript_segments = models.JSONField(default=list, blank=True)
    speaker_segments = models.JSONField(default=list, blank=True)
    diarization_participants = models.JSONField(default=list, blank=True)
    transcription_status = models.CharField(max_length=50, blank=True, default='NONE')
    transcription_backend = models.CharField(max_length=64, blank=True, default='')
    transcription_completed_at = models.DateTimeField(null=True, blank=True)
    cbe_meeting_id = models.CharField(max_length=255, blank=True, default='')
    cbe_session_id = models.CharField(max_length=255, blank=True, default='')
    cbe_recording_id = models.CharField(max_length=255, blank=True, default='')
    cbe_delivery_id = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'event_id')

    # Duck-typing so GoogleMeetRestService.sync_meeting_recording works unchanged.
    meeting_provider = 'GOOGLE_MEET'

    @property
    def google_calendar_owner(self):
        return self.user

    @property
    def created_by(self):
        return self.user

    def __str__(self):
        return f"Recording for event {self.event_id} ({self.user_id})"


class MeetingAutomationJob(models.Model):
    """
    Tracks scheduled meetings discovered across all users' calendars and CRM Meeting records,
    their webhook dispatch to the Custom Browser Engine (CBE), and stored diarization /
    transcription artifacts returned via the CBE completion webhook.
    """

    class SourceType(models.TextChoices):
        MEETING_RECORD = 'MEETING_RECORD', 'Meeting Record'
        GOOGLE_CALENDAR = 'GOOGLE_CALENDAR', 'Google Calendar'
        MICROSOFT_CALENDAR = 'MICROSOFT_CALENDAR', 'Microsoft Calendar'
        EMAIL = 'EMAIL', 'Email'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        DISPATCHED = 'DISPATCHED', 'Dispatched to Webhook'
        PROCESSING = 'PROCESSING', 'Processing in CBE'
        COMPLETED = 'COMPLETED', 'Completed'
        FAILED = 'FAILED', 'Failed'
        SKIPPED = 'SKIPPED', 'Skipped'

    id = models.UUIDField(primary_key=True, default=_uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='meeting_automation_jobs',
    )
    meeting = models.ForeignKey(
        'prospects.Meeting',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='automation_jobs',
    )
    calendar_recording = models.ForeignKey(
        CalendarEventRecording,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='automation_jobs',
    )
    source_type = models.CharField(
        max_length=32,
        choices=SourceType.choices,
        default=SourceType.GOOGLE_CALENDAR,
    )
    external_event_id = models.CharField(max_length=255, blank=True, default='', db_index=True)
    idempotency_key = models.CharField(max_length=128, unique=True)

    title = models.CharField(max_length=500, blank=True, default='')
    meeting_link = models.CharField(max_length=512, blank=True, default='')
    platform = models.CharField(max_length=32, blank=True, default='')
    organizer_email = models.EmailField(blank=True, default='')
    attendees = models.JSONField(default=list, blank=True)

    scheduled_start = models.DateTimeField(db_index=True)
    scheduled_end = models.DateTimeField(null=True, blank=True)

    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    webhook_url_used = models.CharField(max_length=512, blank=True, default='')
    cbe_job_id = models.CharField(max_length=255, blank=True, default='', db_index=True)
    cbe_meeting_id = models.CharField(max_length=255, blank=True, default='', db_index=True)
    cbe_session_id = models.CharField(max_length=255, blank=True, default='')
    cbe_recording_id = models.CharField(max_length=255, blank=True, default='')
    cbe_delivery_id = models.CharField(max_length=255, blank=True, default='', db_index=True)

    dispatch_response = models.JSONField(default=dict, blank=True)
    transcript_text = models.TextField(blank=True, default='')
    transcript_segments = models.JSONField(default=list, blank=True)
    speaker_segments = models.JSONField(default=list, blank=True)
    participants = models.JSONField(default=list, blank=True)
    recording_metadata = models.JSONField(default=dict, blank=True)
    webhook_payload = models.JSONField(default=dict, blank=True)
    last_error = models.TextField(blank=True, default='')

    dispatched_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-scheduled_start', '-created_at']
        indexes = [
            models.Index(fields=['user', 'status', 'scheduled_start']),
            models.Index(fields=['external_event_id']),
        ]

    def __str__(self):
        return f"MeetingAutomationJob({self.user_id}, {self.title or self.external_event_id}, {self.status})"
