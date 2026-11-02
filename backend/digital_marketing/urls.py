from django.urls import path
from .views import (
    DigitalMarketingDashboardView,
    InstagramStatusView,
    InstagramAuthURLView,
    InstagramCallbackView,
    InstagramDisconnectView,
    InstagramPostsView,
    FacebookStatusView,
    FacebookAuthURLView,
    FacebookCallbackView,
    FacebookDisconnectView,
    FacebookPostsView,
    TwitterStatusView,
    TwitterAuthURLView,
    TwitterCallbackView,
    TwitterDisconnectView,
    TwitterTweetsView,
    AdsOverviewView,
    AdsCampaignsView,
    SocialPostDeleteView,
    UniversalPostUploadView,
    ConversationListView,
    ConversationMessagesView,
    ConversationSyncView,
    MetaWebhookView,
    PostCommentsView,
)
from .cms_views import (
    CmsOverviewAPIView,
    CmsPageListCreateAPIView,
    CmsPageDetailAPIView,
    CmsSitemapXmlAPIView,
    GoogleAnalyticsConfigAPIView,
    GoogleAnalyticsDashboardAPIView,
    GoogleAnalyticsCollectAPIView,
    GoogleAnalyticsRealtimeAPIView,
    GoogleCMSAuthURLAPIView,
    GoogleCMSStatusAPIView,
    SearchConsoleDashboardAPIView,
    SearchConsoleDomainListCreateAPIView,
    SearchConsoleDomainVerifyAPIView,
    SearchConsoleSitemapListCreateAPIView,
    SearchConsoleIndexingAPIView,
    BingWebmasterDashboardAPIView,
    BingWebmasterConfigAPIView,
    BingIndexingSubmissionAPIView,
    BingSitemapAPIView,
    GoogleAdsDashboardAPIView,
    GoogleAdsConfigAPIView,
    GoogleAdsCampaignListCreateAPIView,
    GoogleAdsCampaignDetailAPIView,
    GoogleAdsAdGroupListCreateAPIView,
    GoogleAdsKeywordListCreateAPIView,
)

urlpatterns = [
    # Messaging endpoints (Instagram DMs & Facebook Messenger)
    path('conversations/', ConversationListView.as_view(), name='dm_conversations_list'),
    path('conversations/sync/', ConversationSyncView.as_view(), name='dm_conversations_sync'),
    path('conversations/<int:thread_id>/messages/', ConversationMessagesView.as_view(), name='dm_conversations_messages'),
    path('webhooks/meta/', MetaWebhookView.as_view(), name='dm_meta_webhook'),

    # Dashboard summary
    path('dashboard/', DigitalMarketingDashboardView.as_view(), name='dm_dashboard'),

    # Post management, universal broadcast & comments
    path('posts/universal/', UniversalPostUploadView.as_view(), name='dm_universal_post_upload'),
    path('posts/<int:pk>/', SocialPostDeleteView.as_view(), name='dm_post_delete'),
    path('posts/<str:platform>/<str:post_id>/comments/', PostCommentsView.as_view(), name='dm_post_comments'),

    # Instagram endpoints
    path('instagram/status/', InstagramStatusView.as_view(), name='dm_instagram_status'),
    path('instagram/auth-url/', InstagramAuthURLView.as_view(), name='dm_instagram_auth_url'),
    path('instagram/callback/', InstagramCallbackView.as_view(), name='dm_instagram_callback'),
    path('instagram/disconnect/', InstagramDisconnectView.as_view(), name='dm_instagram_disconnect'),
    path('instagram/posts/', InstagramPostsView.as_view(), name='dm_instagram_posts'),

    # Facebook endpoints
    path('facebook/status/', FacebookStatusView.as_view(), name='dm_facebook_status'),
    path('facebook/auth-url/', FacebookAuthURLView.as_view(), name='dm_facebook_auth_url'),
    path('facebook/callback/', FacebookCallbackView.as_view(), name='dm_facebook_callback'),
    path('facebook/disconnect/', FacebookDisconnectView.as_view(), name='dm_facebook_disconnect'),
    path('facebook/posts/', FacebookPostsView.as_view(), name='dm_facebook_posts'),

    # Twitter / X endpoints
    path('twitter/status/', TwitterStatusView.as_view(), name='dm_twitter_status'),
    path('twitter/auth-url/', TwitterAuthURLView.as_view(), name='dm_twitter_auth_url'),
    path('twitter/callback/', TwitterCallbackView.as_view(), name='dm_twitter_callback'),
    path('twitter/disconnect/', TwitterDisconnectView.as_view(), name='dm_twitter_disconnect'),
    path('twitter/tweets/', TwitterTweetsView.as_view(), name='dm_twitter_tweets'),

    # Ads & Insights endpoints
    path('ads/overview/', AdsOverviewView.as_view(), name='dm_ads_overview'),
    path('ads/campaigns/', AdsCampaignsView.as_view(), name='dm_ads_campaigns'),

    # Native Market Intel CMS endpoints
    path('cms/overview/', CmsOverviewAPIView.as_view(), name='dm_cms_overview'),
    path('cms/pages/', CmsPageListCreateAPIView.as_view(), name='dm_cms_pages'),
    path('cms/pages/<int:pk>/', CmsPageDetailAPIView.as_view(), name='dm_cms_page_detail'),
    path('cms/sitemap.xml', CmsSitemapXmlAPIView.as_view(), name='dm_cms_sitemap_xml'),

    # 1. Google Analytics (Page ID config, Tracking Code, Analytics Dashboard, Real-Time Stream & Collector)
    path('cms/analytics/config/', GoogleAnalyticsConfigAPIView.as_view(), name='dm_cms_ga_config'),
    path('cms/analytics/dashboard/', GoogleAnalyticsDashboardAPIView.as_view(), name='dm_cms_ga_dashboard'),
    path('cms/analytics/collect/', GoogleAnalyticsCollectAPIView.as_view(), name='dm_cms_ga_collect'),
    path('cms/analytics/realtime/', GoogleAnalyticsRealtimeAPIView.as_view(), name='dm_cms_ga_realtime'),

    # Google Products Unified OAuth Connection
    path('cms/google/auth-url/', GoogleCMSAuthURLAPIView.as_view(), name='dm_cms_google_auth_url'),
    path('cms/google/status/', GoogleCMSStatusAPIView.as_view(), name='dm_cms_google_status'),

    # 2. Google Search Console (Dashboard, Domains & Verification, Sitemaps, Indexing Requests)
    path('cms/search-console/dashboard/', SearchConsoleDashboardAPIView.as_view(), name='dm_cms_gsc_dashboard'),
    path('cms/search-console/domains/', SearchConsoleDomainListCreateAPIView.as_view(), name='dm_cms_gsc_domains'),
    path('cms/search-console/domains/<int:pk>/verify/', SearchConsoleDomainVerifyAPIView.as_view(), name='dm_cms_gsc_domain_verify'),
    path('cms/search-console/sitemaps/', SearchConsoleSitemapListCreateAPIView.as_view(), name='dm_cms_gsc_sitemaps'),
    path('cms/search-console/indexing/', SearchConsoleIndexingAPIView.as_view(), name='dm_cms_gsc_indexing'),

    # 3. Bing Webmaster Tools (Dashboard, Config & Verification, URL Indexing / IndexNow, Sitemaps)
    path('cms/bing/dashboard/', BingWebmasterDashboardAPIView.as_view(), name='dm_cms_bing_dashboard'),
    path('cms/bing/config/', BingWebmasterConfigAPIView.as_view(), name='dm_cms_bing_config'),
    path('cms/bing/indexing/', BingIndexingSubmissionAPIView.as_view(), name='dm_cms_bing_indexing'),
    path('cms/bing/sitemaps/', BingSitemapAPIView.as_view(), name='dm_cms_bing_sitemaps'),

    # 4. Google Ads (Dashboard, Account Config, Campaigns, Ad Groups, Keywords)
    path('cms/google-ads/dashboard/', GoogleAdsDashboardAPIView.as_view(), name='dm_cms_gads_dashboard'),
    path('cms/google-ads/config/', GoogleAdsConfigAPIView.as_view(), name='dm_cms_gads_config'),
    path('cms/google-ads/campaigns/', GoogleAdsCampaignListCreateAPIView.as_view(), name='dm_cms_gads_campaigns'),
    path('cms/google-ads/campaigns/<int:pk>/', GoogleAdsCampaignDetailAPIView.as_view(), name='dm_cms_gads_campaign_detail'),
    path('cms/google-ads/ad-groups/', GoogleAdsAdGroupListCreateAPIView.as_view(), name='dm_cms_gads_ad_groups'),
    path('cms/google-ads/ad-groups/<int:pk>/', GoogleAdsAdGroupListCreateAPIView.as_view(), name='dm_cms_gads_ad_group_detail'),
    path('cms/google-ads/keywords/', GoogleAdsKeywordListCreateAPIView.as_view(), name='dm_cms_gads_keywords'),
    path('cms/google-ads/keywords/<int:pk>/', GoogleAdsKeywordListCreateAPIView.as_view(), name='dm_cms_gads_keyword_detail'),
]
