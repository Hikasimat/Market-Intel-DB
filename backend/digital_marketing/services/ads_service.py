from decimal import Decimal
from django.db.models import Sum, Avg
from digital_marketing.models import AdCampaign, SocialPost, SocialAccountConnection


class AdsService:
    """
    Consolidates advertising performance across Meta Ads and X Ads,
    and isolates organic performance from paid performance metrics.
    """

    @staticmethod
    def get_aggregated_insights(user):
        """
        Calculates total spend, impressions, reach, clicks, conversions,
        average CPC, and average CTR across authorized paid ad campaigns for the user.
        """
        campaigns = AdCampaign.objects.filter(user=user)
        total_spend = sum(c.spend for c in campaigns) or Decimal('0.00')
        total_impressions = sum(c.impressions for c in campaigns) or 0
        total_reach = sum(c.reach for c in campaigns) or 0
        total_clicks = sum(c.clicks for c in campaigns) or 0
        total_conversions = sum(c.conversions for c in campaigns) or 0

        avg_cpc = Decimal('0.0000')
        if total_clicks > 0:
            avg_cpc = total_spend / Decimal(total_clicks)

        avg_ctr = Decimal('0.000')
        if total_impressions > 0:
            avg_ctr = (Decimal(total_clicks) / Decimal(total_impressions)) * Decimal('100.0')

        meta_campaigns = campaigns.filter(platform='META_ADS')
        twitter_campaigns = campaigns.filter(platform='TWITTER_ADS')

        # Check connection status of ad providers
        meta_connected = SocialAccountConnection.objects.filter(
            user=user, platform__in=['META_ADS', 'FACEBOOK', 'INSTAGRAM'], is_active=True
        ).exists()
        twitter_connected = SocialAccountConnection.objects.filter(
            user=user, platform__in=['TWITTER_ADS', 'TWITTER'], is_active=True
        ).exists()

        # Organic social metrics (strictly separated from paid)
        posts = SocialPost.objects.filter(user=user, status='PUBLISHED')
        total_organic_posts = posts.count()
        total_organic_engagement = 0
        for p in posts:
            m = p.metrics or {}
            total_organic_engagement += (
                int(m.get('likes', 0) or m.get('like_count', 0) or m.get('reactions_count', 0)) +
                int(m.get('comments', 0) or m.get('comments_count', 0) or m.get('reply_count', 0)) +
                int(m.get('retweets', 0) or m.get('retweet_count', 0) or m.get('shares_count', 0))
            )

        return {
            'paid_overview': {
                'total_spend': str(total_spend),
                'total_impressions': total_impressions,
                'total_reach': total_reach,
                'total_clicks': total_clicks,
                'total_conversions': total_conversions,
                'avg_cpc': str(round(avg_cpc, 4)),
                'avg_ctr': str(round(avg_ctr, 3)),
                'active_campaigns_count': campaigns.filter(status='ACTIVE').count(),
                'total_campaigns_count': campaigns.count(),
            },
            'platforms': {
                'meta_ads': {
                    'is_connected': meta_connected,
                    'campaigns_count': meta_campaigns.count(),
                    'spend': str(sum(c.spend for c in meta_campaigns) or Decimal('0.00')),
                    'impressions': sum(c.impressions for c in meta_campaigns),
                    'clicks': sum(c.clicks for c in meta_campaigns),
                },
                'x_ads': {
                    'is_connected': twitter_connected,
                    'campaigns_count': twitter_campaigns.count(),
                    'spend': str(sum(c.spend for c in twitter_campaigns) or Decimal('0.00')),
                    'impressions': sum(c.impressions for c in twitter_campaigns),
                    'clicks': sum(c.clicks for c in twitter_campaigns),
                },
            },
            'organic_overview': {
                'total_posts': total_organic_posts,
                'total_engagement': total_organic_engagement,
                'instagram_posts': posts.filter(platform='INSTAGRAM').count(),
                'facebook_posts': posts.filter(platform='FACEBOOK').count(),
                'twitter_posts': posts.filter(platform='TWITTER').count(),
            }
        }
