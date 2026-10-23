from rest_framework import serializers
from .models import SocialAccountConnection, SocialPost, AdCampaign


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


class OAuthCallbackSerializer(serializers.Serializer):
    code = serializers.CharField(required=True)
    state = serializers.CharField(required=True)
