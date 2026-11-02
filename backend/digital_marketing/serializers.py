from rest_framework import serializers
from .models import (
    SocialAccountConnection,
    SocialPost,
    AdCampaign,
    ConversationThread,
    DirectMessage,
    CmsWebsitePage,
    GoogleAnalyticsConfig,
    GoogleAnalyticsPageStat,
    RealtimeAnalyticsEvent,
    SearchConsoleDomain,
    SearchConsoleSitemap,
    SearchConsoleIndexingRequest,
    SearchConsolePerformanceMetric,
    BingWebmasterConfig,
    BingUrlSubmission,
    BingSitemap,
    BingPerformanceMetric,
    GoogleAdsConfig,
    GoogleAdsCampaignRecord,
    GoogleAdsAdGroupRecord,
    GoogleAdsKeywordRecord,
    GoogleAdsMutationLog,
)


class SocialAccountConnectionSerializer(serializers.ModelSerializer):
    """
    Exposes safe social account metadata to the frontend.
    Strictly excludes access_token_encrypted and refresh_token_encrypted.
    """
    class Meta:
        model = SocialAccountConnection
        fields = [
            'id',
            'platform',
            'account_id',
            'account_name',
            'account_username',
            'profile_picture_url',
            'token_expiry',
            'scopes',
            'is_active',
            'metadata',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


class SocialPostSerializer(serializers.ModelSerializer):
    """Serializes social post publications and their retrieved metrics."""
    media_display_url = serializers.SerializerMethodField()

    class Meta:
        model = SocialPost
        fields = [
            'id',
            'platform',
            'account_connection',
            'external_post_id',
            'caption',
            'media_url',
            'media_file',
            'media_display_url',
            'media_type',
            'permalink',
            'status',
            'metrics',
            'error_message',
            'published_at',
            'created_at',
        ]
        read_only_fields = ['id', 'status', 'error_message', 'published_at', 'created_at']

    def get_media_display_url(self, obj):
        if obj.media_file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.media_file.url)
            return obj.media_file.url
        return obj.media_url


class PostUploadSerializer(serializers.Serializer):
    platform = serializers.ChoiceField(choices=['INSTAGRAM', 'FACEBOOK', 'TWITTER'])
    caption = serializers.CharField(required=False, allow_blank=True, default='')
    image_file = serializers.FileField(required=False, allow_null=True)
    image_url = serializers.CharField(required=False, allow_blank=True, default='')
    publish_live = serializers.BooleanField(required=False, default=False)


class AdCampaignSerializer(serializers.ModelSerializer):
    """Serializes advertising campaign performance metrics for reporting."""
    class Meta:
        model = AdCampaign
        fields = [
            'id',
            'platform',
            'external_campaign_id',
            'name',
            'status',
            'objective',
            'daily_budget',
            'spend',
            'impressions',
            'reach',
            'clicks',
            'conversions',
            'cpc',
            'ctr',
            'start_time',
            'end_time',
            'reporting_period',
            'metrics',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


class InstagramPublishSerializer(serializers.Serializer):
    image_url = serializers.URLField(required=True)
    caption = serializers.CharField(required=False, allow_blank=True, max_length=2200)


class FacebookPublishSerializer(serializers.Serializer):
    message = serializers.CharField(required=True, allow_blank=False)
    link = serializers.URLField(required=False, allow_blank=True)


class TwitterTweetSerializer(serializers.Serializer):
    text = serializers.CharField(required=True, max_length=280)
    publish_live = serializers.BooleanField(required=False, default=True)


class OAuthCallbackSerializer(serializers.Serializer):
    code = serializers.CharField(required=True)
    state = serializers.CharField(required=True)


class DirectMessageSerializer(serializers.ModelSerializer):
    """Serializes individual message items."""
    class Meta:
        model = DirectMessage
        fields = [
            'id',
            'thread',
            'external_message_id',
            'sender_type',
            'sender_id',
            'sender_name',
            'text',
            'media_url',
            'media_type',
            'timestamp',
            'is_read',
            'delivery_status',
            'error_message',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class ConversationThreadSerializer(serializers.ModelSerializer):
    """Serializes conversation threads with recent messages."""
    account_name = serializers.CharField(source='account_connection.account_name', read_only=True)
    account_username = serializers.CharField(source='account_connection.account_username', read_only=True)

    class Meta:
        model = ConversationThread
        fields = [
            'id',
            'platform',
            'account_connection',
            'account_name',
            'account_username',
            'external_thread_id',
            'participant_id',
            'participant_name',
            'participant_username',
            'participant_avatar_url',
            'last_message_text',
            'last_message_at',
            'unread_count',
            'is_archived',
            'created_at',
            'updated_at',
        ]
        read_only_fields = fields


class SendMessageSerializer(serializers.Serializer):
    """Payload for replying to an ongoing conversation."""
    text = serializers.CharField(required=True, allow_blank=False, max_length=2000)
    media_url = serializers.URLField(required=False, allow_blank=True, default='')



# ── Native Market Intel CMS Serializers ──────────────────────────────────────

class CmsWebsitePageSerializer(serializers.ModelSerializer):
    created_by_email = serializers.CharField(source='created_by.email', read_only=True, default='')

    class Meta:
        model = CmsWebsitePage
        fields = [
            'id',
            'title',
            'slug',
            'page_id',
            'page_path',
            'page_type',
            'status',
            'summary',
            'content',
            'meta_title',
            'meta_description',
            'canonical_url',
            'ga_page_id',
            'include_in_sitemap',
            'sitemap_priority',
            'sitemap_changefreq',
            'published_at',
            'created_by_email',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_by_email', 'created_at', 'updated_at']


class GoogleAnalyticsConfigSerializer(serializers.ModelSerializer):
    tracking_code = serializers.SerializerMethodField()

    class Meta:
        model = GoogleAnalyticsConfig
        fields = [
            'id',
            'page_id',
            'property_id',
            'site_name',
            'site_url',
            'is_active',
            'track_pageviews',
            'track_outbound_clicks',
            'track_scroll_depth',
            'page_id_mappings',
            'tracking_code',
            'is_google_connected',
            'google_connected_email',
            'updated_at',
        ]
        read_only_fields = ['id', 'tracking_code', 'is_google_connected', 'google_connected_email', 'updated_at']

    def get_tracking_code(self, obj):
        return obj.get_tracking_code()


class RealtimeAnalyticsEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = RealtimeAnalyticsEvent
        fields = [
            'id',
            'timestamp',
            'page_path',
            'page_id',
            'page_title',
            'visitor_id',
            'session_id',
            'event_name',
            'traffic_source',
            'device_category',
            'country',
            'ip_address',
        ]
        read_only_fields = ['id', 'timestamp']


class GoogleAnalyticsPageStatSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoogleAnalyticsPageStat
        fields = [
            'id',
            'date',
            'page_id',
            'page_path',
            'page_title',
            'page_views',
            'unique_visitors',
            'sessions',
            'engaged_sessions',
            'avg_duration_seconds',
            'bounce_rate',
            'conversions',
            'traffic_source',
            'device_category',
            'country',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class SearchConsoleDomainSerializer(serializers.ModelSerializer):
    dns_txt_record = serializers.SerializerMethodField()
    html_meta_tag = serializers.SerializerMethodField()
    html_file_name = serializers.SerializerMethodField()

    class Meta:
        model = SearchConsoleDomain
        fields = [
            'id',
            'domain',
            'property_type',
            'verification_method',
            'verification_token',
            'is_verified',
            'verified_at',
            'permission_level',
            'dns_txt_record',
            'html_meta_tag',
            'html_file_name',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'verification_token',
            'is_verified',
            'verified_at',
            'dns_txt_record',
            'html_meta_tag',
            'html_file_name',
            'created_at',
            'updated_at',
        ]

    def get_dns_txt_record(self, obj):
        return f"google-site-verification={obj.verification_token}"

    def get_html_meta_tag(self, obj):
        return f'<meta name="google-site-verification" content="{obj.verification_token}" />'

    def get_html_file_name(self, obj):
        return f"google{obj.verification_token[:16]}.html"


class SearchConsoleSitemapSerializer(serializers.ModelSerializer):
    domain_name = serializers.CharField(source='domain.domain', read_only=True, default='')

    class Meta:
        model = SearchConsoleSitemap
        fields = [
            'id',
            'domain',
            'domain_name',
            'sitemap_url',
            'sitemap_type',
            'status',
            'discovered_pages_count',
            'indexed_pages_count',
            'warnings_count',
            'errors_count',
            'last_submitted_at',
            'last_crawled_at',
        ]
        read_only_fields = ['id', 'domain_name', 'last_submitted_at']


class SearchConsoleIndexingRequestSerializer(serializers.ModelSerializer):
    domain_name = serializers.CharField(source='domain.domain', read_only=True, default='')
    requested_by_email = serializers.CharField(source='requested_by.email', read_only=True, default='')

    class Meta:
        model = SearchConsoleIndexingRequest
        fields = [
            'id',
            'domain',
            'domain_name',
            'page_url',
            'action_type',
            'indexing_state',
            'coverage_status',
            'crawl_allowed',
            'mobile_usability',
            'canonical_url',
            'last_crawled_at',
            'requested_by_email',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'domain_name', 'requested_by_email', 'created_at', 'updated_at']


class SearchConsolePerformanceMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = SearchConsolePerformanceMetric
        fields = [
            'id',
            'date',
            'query',
            'page_url',
            'country',
            'device',
            'clicks',
            'impressions',
            'ctr',
            'position',
        ]


class BingWebmasterConfigSerializer(serializers.ModelSerializer):
    has_api_key = serializers.SerializerMethodField()
    masked_api_key = serializers.SerializerMethodField()
    meta_tag_snippet = serializers.SerializerMethodField()
    indexnow_key_url = serializers.SerializerMethodField()

    class Meta:
        model = BingWebmasterConfig
        fields = [
            'id',
            'site_url',
            'has_api_key',
            'masked_api_key',
            'indexnow_key',
            'verification_meta_code',
            'cname_record',
            'is_verified',
            'verified_at',
            'auto_indexnow_on_publish',
            'daily_url_quota',
            'daily_quota_used',
            'meta_tag_snippet',
            'indexnow_key_url',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'has_api_key',
            'masked_api_key',
            'meta_tag_snippet',
            'indexnow_key_url',
            'updated_at',
        ]

    def get_has_api_key(self, obj):
        return bool(obj.api_key_encrypted)

    def get_masked_api_key(self, obj):
        raw = obj.get_api_key()
        if not raw:
            return ''
        if len(raw) <= 8:
            return '••••••••'
        return f"{raw[:4]}••••••••{raw[-4:]}"

    def get_meta_tag_snippet(self, obj):
        return f'<meta name="msvalidate.01" content="{obj.verification_meta_code}" />'

    def get_indexnow_key_url(self, obj):
        base = (obj.site_url or 'https://marketintel.hikasimat.com').rstrip('/')
        return f"{base}/{obj.indexnow_key}.txt"


class BingUrlSubmissionSerializer(serializers.ModelSerializer):
    submitted_by_email = serializers.CharField(source='submitted_by.email', read_only=True, default='')

    class Meta:
        model = BingUrlSubmission
        fields = [
            'id',
            'page_url',
            'submission_protocol',
            'status',
            'http_status_code',
            'response_message',
            'submitted_by_email',
            'created_at',
        ]
        read_only_fields = ['id', 'submitted_by_email', 'created_at']


class BingSitemapSerializer(serializers.ModelSerializer):
    class Meta:
        model = BingSitemap
        fields = [
            'id',
            'sitemap_url',
            'status',
            'urls_discovered',
            'urls_indexed',
            'last_submitted_at',
            'last_crawled_at',
        ]
        read_only_fields = ['id', 'last_submitted_at']


class BingPerformanceMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = BingPerformanceMetric
        fields = [
            'id',
            'date',
            'query',
            'page_url',
            'impressions',
            'clicks',
            'ctr',
            'avg_position',
            'crawled_pages',
            'crawl_errors',
            'indexed_pages',
        ]


class GoogleAdsConfigSerializer(serializers.ModelSerializer):
    has_developer_token = serializers.SerializerMethodField()

    class Meta:
        model = GoogleAdsConfig
        fields = [
            'id',
            'customer_id',
            'manager_customer_id',
            'account_name',
            'currency_code',
            'time_zone',
            'client_id',
            'connected_email',
            'is_connected',
            'auto_tagging_enabled',
            'conversion_tracking_id',
            'accessible_customers',
            'has_developer_token',
            'last_synced_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'has_developer_token', 'updated_at']

    def get_has_developer_token(self, obj):
        return obj.has_developer_token()


class GoogleAdsCampaignRecordSerializer(serializers.ModelSerializer):
    ctr = serializers.SerializerMethodField()
    avg_cpc = serializers.SerializerMethodField()
    cpa = serializers.SerializerMethodField()
    roas = serializers.SerializerMethodField()
    ad_groups_count = serializers.SerializerMethodField()
    keywords_count = serializers.SerializerMethodField()

    class Meta:
        model = GoogleAdsCampaignRecord
        fields = [
            'id',
            'external_campaign_id',
            'name',
            'channel_type',
            'status',
            'bidding_strategy',
            'daily_budget',
            'target_cpa',
            'target_roas',
            'start_date',
            'end_date',
            'locations',
            'languages',
            'impressions',
            'clicks',
            'cost',
            'conversions',
            'conversion_value',
            'ctr',
            'avg_cpc',
            'cpa',
            'roas',
            'ad_groups_count',
            'keywords_count',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'ctr',
            'avg_cpc',
            'cpa',
            'roas',
            'ad_groups_count',
            'keywords_count',
            'created_at',
            'updated_at',
        ]

    def get_ctr(self, obj):
        if not obj.impressions:
            return 0.0
        return round((obj.clicks / obj.impressions) * 100, 2)

    def get_avg_cpc(self, obj):
        if not obj.clicks:
            return 0.0
        return round(float(obj.cost) / obj.clicks, 2)

    def get_cpa(self, obj):
        if not obj.conversions or float(obj.conversions) == 0:
            return 0.0
        return round(float(obj.cost) / float(obj.conversions), 2)

    def get_roas(self, obj):
        if not obj.cost or float(obj.cost) == 0:
            return 0.0
        return round(float(obj.conversion_value) / float(obj.cost), 2)

    def get_ad_groups_count(self, obj):
        return obj.ad_groups.count()

    def get_keywords_count(self, obj):
        return obj.keywords.count()


class GoogleAdsAdGroupRecordSerializer(serializers.ModelSerializer):
    campaign_name = serializers.CharField(source='campaign.name', read_only=True, default='')
    ctr = serializers.SerializerMethodField()
    avg_cpc = serializers.SerializerMethodField()

    class Meta:
        model = GoogleAdsAdGroupRecord
        fields = [
            'id',
            'campaign',
            'campaign_name',
            'external_ad_group_id',
            'name',
            'status',
            'ad_group_type',
            'cpc_bid',
            'headline_1',
            'headline_2',
            'description',
            'final_url',
            'impressions',
            'clicks',
            'cost',
            'conversions',
            'ctr',
            'avg_cpc',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'campaign_name', 'ctr', 'avg_cpc', 'created_at', 'updated_at']

    def get_ctr(self, obj):
        if not obj.impressions:
            return 0.0
        return round((obj.clicks / obj.impressions) * 100, 2)

    def get_avg_cpc(self, obj):
        if not obj.clicks:
            return 0.0
        return round(float(obj.cost) / obj.clicks, 2)


class GoogleAdsKeywordRecordSerializer(serializers.ModelSerializer):
    campaign_name = serializers.CharField(source='campaign.name', read_only=True, default='')
    ad_group_name = serializers.CharField(source='ad_group.name', read_only=True, default='')
    ctr = serializers.SerializerMethodField()
    avg_cpc = serializers.SerializerMethodField()

    class Meta:
        model = GoogleAdsKeywordRecord
        fields = [
            'id',
            'campaign',
            'campaign_name',
            'ad_group',
            'ad_group_name',
            'keyword_text',
            'match_type',
            'status',
            'cpc_bid',
            'quality_score',
            'impressions',
            'clicks',
            'cost',
            'conversions',
            'ctr',
            'avg_cpc',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'campaign_name',
            'ad_group_name',
            'ctr',
            'avg_cpc',
            'created_at',
            'updated_at',
        ]

    def get_ctr(self, obj):
        if not obj.impressions:
            return 0.0
        return round((obj.clicks / obj.impressions) * 100, 2)

    def get_avg_cpc(self, obj):
        if not obj.clicks:
            return 0.0
        return round(float(obj.cost) / obj.clicks, 2)


class GoogleAdsMutationLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoogleAdsMutationLog
        fields = [
            'id',
            'actor_email',
            'operation_type',
            'resource_type',
            'resource_id',
            'resource_name',
            'summary',
            'previous_value',
            'new_value',
            'status',
            'created_at',
        ]
        read_only_fields = fields
