from django.db import models
from django.contrib.auth.models import User
import utils.encryption as encryption


class SocialAccountConnection(models.Model):
    """
    Stores authorized connection metadata and encrypted tokens for social platforms.
    Sensitive tokens (access token, refresh token) are Fernet-encrypted at rest and
    NEVER returned directly to API clients.
    """
    PLATFORM_CHOICES = (
        ('INSTAGRAM', 'Instagram'),
        ('FACEBOOK', 'Facebook'),
        ('TWITTER', 'Twitter / X'),
        ('META_ADS', 'Meta Ads'),
        ('TWITTER_ADS', 'X Ads'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='social_connections')
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    account_id = models.CharField(max_length=255, blank=True, default='')
    account_name = models.CharField(max_length=255, blank=True, default='')
    account_username = models.CharField(max_length=255, blank=True, default='')
    profile_picture_url = models.URLField(max_length=1000, blank=True, default='')

    # Encrypted credentials
    access_token_encrypted = models.TextField(blank=True, default='')
    refresh_token_encrypted = models.TextField(blank=True, default='')
    token_expiry = models.DateTimeField(null=True, blank=True)
    scopes = models.TextField(blank=True, default='')

    is_active = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'platform', 'account_id'],
                name='uniq_user_platform_account'
            )
        ]

    def __str__(self):
        return f"{self.get_platform_display()} - {self.account_username or self.account_name} ({self.user.username})"

    def set_access_token(self, token: str):
        if token:
            self.access_token_encrypted = encryption.encrypt_password(token)
        else:
            self.access_token_encrypted = ''

    def get_access_token(self) -> str:
        if not self.access_token_encrypted:
            return ''
        try:
            return encryption.decrypt_password(self.access_token_encrypted)
        except Exception:
            return ''

    def set_refresh_token(self, token: str):
        if token:
            self.refresh_token_encrypted = encryption.encrypt_password(token)
        else:
            self.refresh_token_encrypted = ''

    def get_refresh_token(self) -> str:
        if not self.refresh_token_encrypted:
            return ''
        try:
            return encryption.decrypt_password(self.refresh_token_encrypted)
        except Exception:
            return ''


class SocialPost(models.Model):
    """
    Stores published and managed social content with performance metrics.
    """
    PLATFORM_CHOICES = (
        ('INSTAGRAM', 'Instagram'),
        ('FACEBOOK', 'Facebook'),
        ('TWITTER', 'Twitter / X'),
    )

    STATUS_CHOICES = (
        ('PUBLISHED', 'Published'),
        ('DRAFT', 'Draft'),
        ('FAILED', 'Failed'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='social_posts')
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    account_connection = models.ForeignKey(
        SocialAccountConnection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='posts'
    )
    external_post_id = models.CharField(max_length=255, blank=True, default='')
    caption = models.TextField(blank=True, default='')
    media_url = models.URLField(max_length=1000, blank=True, default='')
    media_file = models.FileField(upload_to='social_posts/%Y/%m/', null=True, blank=True)
    media_type = models.CharField(max_length=50, default='IMAGE')
    permalink = models.URLField(max_length=1000, blank=True, default='')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PUBLISHED')

    # Metrics dictionary (likes, comments, retweets, impressions, reach, etc.)
    metrics = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default='')

    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-published_at', '-created_at']

    def __str__(self):
        return f"{self.platform} Post {self.external_post_id or self.id} ({self.status})"


class AdCampaign(models.Model):
    """
    Organized view of advertising campaigns and performance insights.
    Read-only / reporting representation — never automatically initiates spend.
    """
    PLATFORM_CHOICES = (
        ('META_ADS', 'Meta Ads'),
        ('TWITTER_ADS', 'X Ads'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ad_campaigns')
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    account_connection = models.ForeignKey(
        SocialAccountConnection,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='campaigns'
    )
    external_campaign_id = models.CharField(max_length=255)
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=50, default='PAUSED')
    objective = models.CharField(max_length=100, blank=True, default='')

    daily_budget = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    spend = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    impressions = models.BigIntegerField(default=0)
    reach = models.BigIntegerField(default=0)
    clicks = models.BigIntegerField(default=0)
    conversions = models.BigIntegerField(default=0)
    cpc = models.DecimalField(max_digits=10, decimal_places=4, default=0.0000)
    ctr = models.DecimalField(max_digits=6, decimal_places=3, default=0.000)

    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    reporting_period = models.CharField(max_length=100, default='Last 30 Days')
    metrics = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.get_platform_display()} - {self.name} ({self.status})"


class ConversationThread(models.Model):
    """
    Represents an ongoing Direct Message conversation with a customer / follower
    across Instagram Direct or Facebook Messenger.
    """
    PLATFORM_CHOICES = (
        ('INSTAGRAM', 'Instagram'),
        ('FACEBOOK', 'Facebook'),
    )

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='dm_conversations')
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    account_connection = models.ForeignKey(
        SocialAccountConnection,
        on_delete=models.CASCADE,
        related_name='conversations'
    )
    # The external conversation/thread ID from Meta or the recipient ID (PSID/IGSID)
    external_thread_id = models.CharField(max_length=255)
    participant_id = models.CharField(max_length=255)  # Customer PSID or IGSID
    participant_name = models.CharField(max_length=255, blank=True, default='Customer')
    participant_username = models.CharField(max_length=255, blank=True, default='')
    participant_avatar_url = models.URLField(max_length=1000, blank=True, default='')

    last_message_text = models.TextField(blank=True, default='')
    last_message_at = models.DateTimeField(null=True, blank=True)
    unread_count = models.PositiveIntegerField(default=0)
    is_archived = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_message_at', '-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'platform', 'external_thread_id'],
                name='uniq_user_platform_thread'
            )
        ]

    def __str__(self):
        return f"{self.get_platform_display()} Thread - {self.participant_name or self.participant_id}"


class DirectMessage(models.Model):
    """
    Individual message sent or received within a ConversationThread.
    """
    SENDER_CHOICES = (
        ('CUSTOMER', 'Customer'),
        ('BUSINESS', 'Business'),
    )
    DELIVERY_STATUS_CHOICES = (
        ('SENT', 'Sent'),
        ('DELIVERED', 'Delivered'),
        ('READ', 'Read'),
        ('FAILED', 'Failed'),
    )

    thread = models.ForeignKey(ConversationThread, on_delete=models.CASCADE, related_name='messages')
    external_message_id = models.CharField(max_length=255, blank=True, default='')
    sender_type = models.CharField(max_length=20, choices=SENDER_CHOICES)
    sender_id = models.CharField(max_length=255, blank=True, default='')
    sender_name = models.CharField(max_length=255, blank=True, default='')

    text = models.TextField(blank=True, default='')
    media_url = models.URLField(max_length=1000, blank=True, default='')
    media_type = models.CharField(max_length=50, blank=True, default='text')

    timestamp = models.DateTimeField()
    is_read = models.BooleanField(default=False)
    delivery_status = models.CharField(max_length=20, choices=DELIVERY_STATUS_CHOICES, default='SENT')
    error_message = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp', 'created_at']

    def __str__(self):
        return f"[{self.sender_type}] {self.text[:30]}"

