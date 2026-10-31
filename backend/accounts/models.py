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


