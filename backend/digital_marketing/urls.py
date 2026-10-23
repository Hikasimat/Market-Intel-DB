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
)

urlpatterns = [
    # Dashboard summary
    path('dashboard/', DigitalMarketingDashboardView.as_view(), name='dm_dashboard'),

    # Post management
    path('posts/<int:pk>/', SocialPostDeleteView.as_view(), name='dm_post_delete'),

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
]
