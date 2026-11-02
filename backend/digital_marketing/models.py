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



# ── Native Market Intel CMS Models ───────────────────────────────────────────

class CmsWebsitePage(models.Model):
    """
    Native Market Intel CMS page/article entity stored directly in the Market Intel DB.
    Used for page management, GA Page ID tracking, Search Console & Bing indexing,
    and XML sitemap generation.
    """
    PAGE_TYPE_CHOICES = (
        ('PAGE', 'Web Page'),
        ('ARTICLE', 'Blog Article'),
        ('LANDING', 'Landing Page'),
    )
    STATUS_CHOICES = (
        ('PUBLISHED', 'Published'),
        ('DRAFT', 'Draft'),
        ('ARCHIVED', 'Archived'),
    )

    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True)
    page_id = models.CharField(max_length=100, unique=True)
    page_path = models.CharField(max_length=255, default='/')
    page_type = models.CharField(max_length=30, choices=PAGE_TYPE_CHOICES, default='PAGE')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PUBLISHED')

    summary = models.TextField(blank=True, default='')
    content = models.TextField(blank=True, default='')

    meta_title = models.CharField(max_length=255, blank=True, default='')
    meta_description = models.TextField(blank=True, default='')
    canonical_url = models.URLField(max_length=500, blank=True, default='')

    ga_page_id = models.CharField(max_length=100, blank=True, default='')
    include_in_sitemap = models.BooleanField(default=True)
    sitemap_priority = models.DecimalField(max_digits=3, decimal_places=1, default=0.8)
    sitemap_changefreq = models.CharField(max_length=20, default='weekly')

    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='cms_pages'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at', '-created_at']

    def __str__(self):
        return f"{self.title} ({self.page_id})"


class GoogleAnalyticsConfig(models.Model):
    """
    Native Google Analytics configuration for Market Intel CMS:
    Stores Page ID / Measurement ID configuration and generates tracking snippets.
    """
    page_id = models.CharField(max_length=100, default='G-MKTINTEL01')
    property_id = models.CharField(max_length=100, blank=True, default='482910384')
    site_name = models.CharField(max_length=255, default='Market Intel Official Website')
    site_url = models.URLField(max_length=500, default='https://marketintel.hikasimat.com')
    is_active = models.BooleanField(default=True)
    track_pageviews = models.BooleanField(default=True)
    track_outbound_clicks = models.BooleanField(default=True)
    track_scroll_depth = models.BooleanField(default=True)
    page_id_mappings = models.JSONField(default=list, blank=True)
    google_access_token = models.TextField(blank=True, default='')
    google_refresh_token = models.TextField(blank=True, default='')
    google_token_expiry = models.DateTimeField(null=True, blank=True)
    google_connected_email = models.EmailField(blank=True, default='')
    is_google_connected = models.BooleanField(default=False)

    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='ga_configs'
    )
    updated_at = models.DateTimeField(auto_now=True)

    def get_tracking_code(self, target_page_id=None) -> str:
        active_id = (target_page_id or self.page_id or 'G-MKTINTEL01').strip()
        extra_cfg = []
        if not self.track_pageviews:
            extra_cfg.append("'send_page_view': false")
        if self.track_outbound_clicks:
            extra_cfg.append("'link_attribution': true")
        if self.track_scroll_depth:
            extra_cfg.append("'scroll_depth_tracking': true")
        cfg_str = f", {{ {', '.join(extra_cfg)} }}" if extra_cfg else ""
        return (
            f"<!-- Google tag (gtag.js) & Market Intel Real-Time Tracker -->\n"
            f"<script async src=\"https://www.googletagmanager.com/gtag/js?id={active_id}\"></script>\n"
            f"<script>\n"
            f"  window.dataLayer = window.dataLayer || [];\n"
            f"  function gtag(){{dataLayer.push(arguments);}}\n"
            f"  gtag('js', new Date());\n"
            f"  gtag('config', '{active_id}'{cfg_str});\n\n"
            f"  // Market Intel Real-Time Stream Ingestion\n"
            f"  (function() {{\n"
            f"    try {{\n"
            f"      var hit = {{\n"
            f"        page_path: window.location.pathname || '/',\n"
            f"        page_title: document.title,\n"
            f"        page_id: '{active_id}',\n"
            f"        traffic_source: document.referrer ? (new URL(document.referrer).hostname) : 'Direct',\n"
            f"        device_category: /Mobi|Android/i.test(navigator.userAgent) ? 'Mobile' : 'Desktop'\n"
            f"      }};\n"
            f"      var blob = new Blob([JSON.stringify(hit)], {{type: 'application/json'}});\n"
            f"      if (navigator.sendBeacon) {{\n"
            f"        navigator.sendBeacon('/api/digital-marketing/cms/analytics/collect/', blob);\n"
            f"      }} else {{\n"
            f"        fetch('/api/digital-marketing/cms/analytics/collect/', {{method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify(hit)}});\n"
            f"      }}\n"
            f"    }} catch(e) {{}}\n"
            f"  }})();\n"
            f"</script>"
        )

    def __str__(self):
        return f"GA Config ({self.page_id})"


class GoogleAnalyticsPageStat(models.Model):
    """
    Detailed website statistics per page and date for the Google Analytics dashboard.
    """
    date = models.DateField()
    page_id = models.CharField(max_length=100, default='PAGE-HOME')
    page_path = models.CharField(max_length=255, default='/')
    page_title = models.CharField(max_length=255, default='Home')
    page_views = models.PositiveIntegerField(default=0)
    unique_visitors = models.PositiveIntegerField(default=0)
    sessions = models.PositiveIntegerField(default=0)
    engaged_sessions = models.PositiveIntegerField(default=0)
    avg_duration_seconds = models.PositiveIntegerField(default=0)
    bounce_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    conversions = models.PositiveIntegerField(default=0)
    traffic_source = models.CharField(max_length=100, default='Organic Search')
    device_category = models.CharField(max_length=50, default='Desktop')
    country = models.CharField(max_length=100, default='United States')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-page_views']

    def __str__(self):
        return f"{self.date} - {self.page_path} ({self.page_views} views)"


class RealtimeAnalyticsEvent(models.Model):
    """
    Live real-time web traffic events streamed to Market Intel CMS.
    Enables instant tracking and real-time active users right now.
    """
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    page_path = models.CharField(max_length=255, default='/')
    page_id = models.CharField(max_length=100, blank=True, default='')
    page_title = models.CharField(max_length=255, blank=True, default='')
    visitor_id = models.CharField(max_length=100, db_index=True)
    session_id = models.CharField(max_length=100, blank=True, default='')
    event_name = models.CharField(max_length=100, default='page_view')
    traffic_source = models.CharField(max_length=100, default='Direct')
    device_category = models.CharField(max_length=50, default='Desktop')
    country = models.CharField(max_length=100, default='United States')
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default='')

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.timestamp}] {self.event_name} on {self.page_path} ({self.visitor_id})"



class SearchConsoleDomain(models.Model):
    """
    Google Search Console domain registration and verification records.
    """
    PROPERTY_TYPE_CHOICES = (
        ('DOMAIN', 'Domain Property (sc-domain)'),
        ('URL_PREFIX', 'URL Prefix'),
    )
    VERIFICATION_METHOD_CHOICES = (
        ('DNS_TXT', 'DNS TXT Record'),
        ('HTML_META', 'HTML Meta Tag'),
        ('HTML_FILE', 'HTML Verification File'),
    )

    domain = models.CharField(max_length=255, unique=True)
    property_type = models.CharField(max_length=30, choices=PROPERTY_TYPE_CHOICES, default='DOMAIN')
    verification_method = models.CharField(
        max_length=30, choices=VERIFICATION_METHOD_CHOICES, default='DNS_TXT'
    )
    verification_token = models.CharField(max_length=255)
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    permission_level = models.CharField(max_length=50, default='Full Owner')
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='gsc_domains'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_verified', '-created_at']

    def __str__(self):
        return f"{self.domain} ({'Verified' if self.is_verified else 'Pending'})"


class SearchConsoleSitemap(models.Model):
    """
    Google Search Console page sitemap management and submission status.
    """
    STATUS_CHOICES = (
        ('SUCCESS', 'Success'),
        ('PENDING', 'Pending Fetch'),
        ('HAS_ISSUES', 'Has Issues'),
        ('ERROR', "Couldn't Fetch"),
    )

    domain = models.ForeignKey(
        SearchConsoleDomain, on_delete=models.CASCADE, related_name='sitemaps', null=True, blank=True
    )
    sitemap_url = models.URLField(max_length=500)
    sitemap_type = models.CharField(max_length=50, default='XML Sitemap')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='SUCCESS')
    discovered_pages_count = models.PositiveIntegerField(default=0)
    indexed_pages_count = models.PositiveIntegerField(default=0)
    warnings_count = models.PositiveIntegerField(default=0)
    errors_count = models.PositiveIntegerField(default=0)
    last_submitted_at = models.DateTimeField(auto_now_add=True)
    last_crawled_at = models.DateTimeField(null=True, blank=True)
    submitted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='gsc_sitemaps'
    )

    class Meta:
        ordering = ['-last_submitted_at']

    def __str__(self):
        return f"{self.sitemap_url} ({self.status})"


class SearchConsoleIndexingRequest(models.Model):
    """
    Google Search Console URL Inspection & Page Indexing submission requests.
    """
    ACTION_CHOICES = (
        ('URL_UPDATED', 'Publish / Update URL'),
        ('URL_DELETED', 'Remove URL'),
    )
    STATE_CHOICES = (
        ('SUBMITTED', 'Submitted & Indexed'),
        ('QUEUED', 'Queued for Crawl'),
        ('INDEXED', 'URL is on Google'),
        ('DISCOVERED_NOT_INDEXED', 'Discovered - currently not indexed'),
        ('ERROR', 'Indexing Error'),
    )

    domain = models.ForeignKey(
        SearchConsoleDomain,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='indexing_requests'
    )
    page_url = models.URLField(max_length=500)
    action_type = models.CharField(max_length=30, choices=ACTION_CHOICES, default='URL_UPDATED')
    indexing_state = models.CharField(max_length=40, choices=STATE_CHOICES, default='SUBMITTED')
    coverage_status = models.CharField(max_length=100, default='Submitted and indexed')
    crawl_allowed = models.BooleanField(default=True)
    mobile_usability = models.CharField(max_length=50, default='Usable')
    canonical_url = models.URLField(max_length=500, blank=True, default='')
    last_crawled_at = models.DateTimeField(null=True, blank=True)
    requested_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='gsc_indexing_requests'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[GSC] {self.page_url} ({self.indexing_state})"


class SearchConsolePerformanceMetric(models.Model):
    """
    Google Search Console search performance metrics (queries, pages, clicks, impressions, CTR, position).
    """
    date = models.DateField()
    query = models.CharField(max_length=255)
    page_url = models.URLField(max_length=500)
    country = models.CharField(max_length=100, default='United States')
    device = models.CharField(max_length=50, default='DESKTOP')
    clicks = models.PositiveIntegerField(default=0)
    impressions = models.PositiveIntegerField(default=0)
    ctr = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    position = models.DecimalField(max_digits=5, decimal_places=1, default=1.0)

    class Meta:
        ordering = ['-date', '-clicks']

    def __str__(self):
        return f"GSC {self.query} ({self.clicks} clicks)"


class BingWebmasterConfig(models.Model):
    """
    Bing Webmaster Tools configuration, site verification, API key, and IndexNow settings.
    """
    site_url = models.URLField(max_length=500, default='https://marketintel.hikasimat.com')
    api_key_encrypted = models.TextField(blank=True, default='')
    indexnow_key = models.CharField(max_length=128, default='')
    verification_meta_code = models.CharField(max_length=255, default='')
    cname_record = models.CharField(max_length=255, default='')
    is_verified = models.BooleanField(default=False)
    verified_at = models.DateTimeField(null=True, blank=True)
    auto_indexnow_on_publish = models.BooleanField(default=True)
    daily_url_quota = models.PositiveIntegerField(default=10000)
    daily_quota_used = models.PositiveIntegerField(default=0)
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='bing_configs'
    )
    updated_at = models.DateTimeField(auto_now=True)

    def set_api_key(self, raw_key: str):
        if raw_key:
            self.api_key_encrypted = encryption.encrypt_password(raw_key)
        else:
            self.api_key_encrypted = ''

    def get_api_key(self) -> str:
        if not self.api_key_encrypted:
            return ''
        try:
            return encryption.decrypt_password(self.api_key_encrypted)
        except Exception:
            return ''

    def __str__(self):
        return f"Bing Webmaster ({self.site_url})"


class BingUrlSubmission(models.Model):
    """
    Bing Webmaster Tools & IndexNow URL submission log.
    """
    PROTOCOL_CHOICES = (
        ('INDEXNOW', 'IndexNow Instant Ping'),
        ('BING_API', 'Bing Webmaster URL Submission API'),
    )
    STATUS_CHOICES = (
        ('ACCEPTED', 'Accepted (HTTP 200)'),
        ('INDEXED', 'Indexed on Bing'),
        ('QUEUED', 'Queued for Bingbot'),
        ('ERROR', 'Submission Failed'),
    )

    page_url = models.URLField(max_length=500)
    submission_protocol = models.CharField(max_length=30, choices=PROTOCOL_CHOICES, default='INDEXNOW')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='ACCEPTED')
    http_status_code = models.PositiveIntegerField(default=200)
    response_message = models.CharField(
        max_length=255, default='URL submitted to Bing Webmaster & IndexNow cluster'
    )
    submitted_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='bing_submissions'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[Bing] {self.page_url} ({self.status})"


class BingSitemap(models.Model):
    """
    Bing Webmaster Tools sitemap submission and index status.
    """
    STATUS_CHOICES = (
        ('SUCCESS', 'Processed'),
        ('PENDING', 'Pending Crawl'),
        ('ERROR', 'Crawl Error'),
    )

    sitemap_url = models.URLField(max_length=500)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='SUCCESS')
    urls_discovered = models.PositiveIntegerField(default=0)
    urls_indexed = models.PositiveIntegerField(default=0)
    last_submitted_at = models.DateTimeField(auto_now_add=True)
    last_crawled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-last_submitted_at']

    def __str__(self):
        return f"[Bing Sitemap] {self.sitemap_url} ({self.status})"


class BingPerformanceMetric(models.Model):
    """
    Bing Webmaster Tools search performance & crawl metrics.
    """
    date = models.DateField()
    query = models.CharField(max_length=255)
    page_url = models.URLField(max_length=500)
    impressions = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)
    ctr = models.DecimalField(max_digits=6, decimal_places=2, default=0.00)
    avg_position = models.DecimalField(max_digits=5, decimal_places=1, default=1.0)
    crawled_pages = models.PositiveIntegerField(default=0)
    crawl_errors = models.PositiveIntegerField(default=0)
    indexed_pages = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-date', '-clicks']

    def __str__(self):
        return f"Bing {self.query} ({self.clicks} clicks)"


class GoogleAdsConfig(models.Model):
    """
    Native Google Ads account connection & configuration inside Market Intel.
    """
    customer_id = models.CharField(max_length=32, blank=True, default='')
    manager_customer_id = models.CharField(max_length=32, blank=True, default='')
    account_name = models.CharField(max_length=255, blank=True, default='')
    currency_code = models.CharField(max_length=10, default='USD')
    time_zone = models.CharField(max_length=64, default='America/New_York')
    developer_token_encrypted = models.TextField(blank=True, default='')
    client_id = models.CharField(max_length=255, blank=True, default='')
    client_secret_encrypted = models.TextField(blank=True, default='')
    refresh_token_encrypted = models.TextField(blank=True, default='')
    connected_email = models.EmailField(blank=True, default='')
    is_connected = models.BooleanField(default=False)
    auto_tagging_enabled = models.BooleanField(default=True)
    conversion_tracking_id = models.CharField(max_length=100, blank=True, default='')
    accessible_customers = models.JSONField(default=list, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='google_ads_configs'
    )
    updated_at = models.DateTimeField(auto_now=True)

    def set_developer_token(self, token: str):
        self.developer_token_encrypted = encryption.encrypt_password(token) if token else ''

    def has_developer_token(self) -> bool:
        return bool(self.developer_token_encrypted)

    def __str__(self):
        return f"Google Ads ({self.customer_id} - {self.account_name})"


class GoogleAdsCampaignRecord(models.Model):
    """
    Native Google Ads campaign managed inside Market Intel CMS.
    """
    CHANNEL_CHOICES = (
        ('SEARCH', 'Search'),
        ('PERFORMANCE_MAX', 'Performance Max'),
        ('DISPLAY', 'Display'),
        ('VIDEO', 'Video / YouTube'),
        ('DEMAND_GEN', 'Demand Gen'),
    )
    STATUS_CHOICES = (
        ('ENABLED', 'Enabled'),
        ('PAUSED', 'Paused'),
        ('REMOVED', 'Removed'),
    )
    BIDDING_CHOICES = (
        ('MAXIMIZE_CONVERSIONS', 'Maximize Conversions'),
        ('MAXIMIZE_CLICKS', 'Maximize Clicks'),
        ('TARGET_CPA', 'Target CPA'),
        ('TARGET_ROAS', 'Target ROAS'),
        ('MANUAL_CPC', 'Manual CPC'),
    )

    external_campaign_id = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    channel_type = models.CharField(max_length=40, choices=CHANNEL_CHOICES, default='SEARCH')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ENABLED')
    bidding_strategy = models.CharField(
        max_length=40, choices=BIDDING_CHOICES, default='MAXIMIZE_CONVERSIONS'
    )
    daily_budget = models.DecimalField(max_digits=12, decimal_places=2, default=50.00)
    target_cpa = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    target_roas = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    locations = models.CharField(max_length=255, default='United States, United Kingdom, India')
    languages = models.CharField(max_length=255, default='English')

    impressions = models.BigIntegerField(default=0)
    clicks = models.BigIntegerField(default=0)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    conversions = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    conversion_value = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='google_ads_campaigns'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-status', '-cost', '-created_at']

    def __str__(self):
        return f"{self.name} ({self.status})"


class GoogleAdsAdGroupRecord(models.Model):
    """
    Google Ads Ad Group belonging to a GoogleAdsCampaignRecord.
    """
    STATUS_CHOICES = (
        ('ENABLED', 'Enabled'),
        ('PAUSED', 'Paused'),
    )

    campaign = models.ForeignKey(
        GoogleAdsCampaignRecord, on_delete=models.CASCADE, related_name='ad_groups'
    )
    external_ad_group_id = models.CharField(max_length=64, blank=True, default='')
    name = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ENABLED')
    ad_group_type = models.CharField(max_length=50, default='SEARCH_STANDARD')
    cpc_bid = models.DecimalField(max_digits=10, decimal_places=2, default=2.50)
    headline_1 = models.CharField(max_length=120, blank=True, default='')
    headline_2 = models.CharField(max_length=120, blank=True, default='')
    description = models.TextField(blank=True, default='')
    final_url = models.URLField(max_length=500, blank=True, default='https://marketintel.hikasimat.com')

    impressions = models.BigIntegerField(default=0)
    clicks = models.BigIntegerField(default=0)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    conversions = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-clicks', '-created_at']

    def __str__(self):
        return f"{self.name} ({self.campaign.name})"


class GoogleAdsKeywordRecord(models.Model):
    """
    Google Ads Keyword criterion with match type, quality score, and performance metrics.
    """
    MATCH_CHOICES = (
        ('EXACT', 'Exact Match'),
        ('PHRASE', 'Phrase Match'),
        ('BROAD', 'Broad Match'),
    )
    STATUS_CHOICES = (
        ('ENABLED', 'Enabled'),
        ('PAUSED', 'Paused'),
    )

    campaign = models.ForeignKey(
        GoogleAdsCampaignRecord, on_delete=models.CASCADE, related_name='keywords'
    )
    ad_group = models.ForeignKey(
        GoogleAdsAdGroupRecord, on_delete=models.CASCADE, related_name='keywords'
    )
    keyword_text = models.CharField(max_length=255)
    match_type = models.CharField(max_length=20, choices=MATCH_CHOICES, default='PHRASE')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ENABLED')
    cpc_bid = models.DecimalField(max_digits=10, decimal_places=2, default=2.00)
    quality_score = models.PositiveSmallIntegerField(default=8)

    impressions = models.BigIntegerField(default=0)
    clicks = models.BigIntegerField(default=0)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    conversions = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-clicks', '-quality_score']

    def __str__(self):
        return f"{self.keyword_text} [{self.match_type}]"


class GoogleAdsMutationLog(models.Model):
    """
    Audit trail of all Google Ads management operations executed within Market Intel.
    """
    actor = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='google_ads_mutations'
    )
    actor_email = models.CharField(max_length=255, blank=True, default='')
    operation_type = models.CharField(max_length=64)
    resource_type = models.CharField(max_length=64, default='CAMPAIGN')
    resource_id = models.CharField(max_length=64, blank=True, default='')
    resource_name = models.CharField(max_length=255, blank=True, default='')
    summary = models.TextField(blank=True, default='')
    previous_value = models.JSONField(default=dict, blank=True)
    new_value = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, default='SUCCESS')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.operation_type} on {self.resource_name} ({self.status})"
