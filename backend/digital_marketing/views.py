import logging
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from accounts.permissions import IsDigitalMarketing
from .models import SocialAccountConnection, SocialPost, AdCampaign
from .serializers import (
    SocialAccountConnectionSerializer,
    SocialPostSerializer,
    AdCampaignSerializer,
    InstagramPublishSerializer,
    FacebookPublishSerializer,
    TwitterTweetSerializer,
    OAuthCallbackSerializer,
)
from .services.meta_service import MetaService
from .services.twitter_service import TwitterService
from .services.ads_service import AdsService

logger = logging.getLogger(__name__)


# ── Digital Marketing Dashboard ──────────────────────────────────────────────

class DigitalMarketingDashboardView(APIView):
    """
    Overview summary for the Digital Marketing workspace:
    Platform connection statuses, recent posts, and high-level reach.
    """
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def get(self, request):
        user = request.user
        connections = SocialAccountConnection.objects.filter(user=user, is_active=True)

        meta_cfg = MetaService.get_config()
        twitter_cfg = TwitterService.get_config()

        ig_conn = connections.filter(platform='INSTAGRAM').first()
        fb_conn = connections.filter(platform='FACEBOOK').first()
        tw_conn = connections.filter(platform='TWITTER').first()

        recent_posts = SocialPost.objects.filter(user=user).order_by('-created_at')[:6]

        insights = AdsService.get_aggregated_insights(user)

        return Response({
            'platforms': {
                'instagram': {
                    'is_connected': bool(ig_conn),
                    'is_configured': meta_cfg['is_configured'],
                    'account_username': ig_conn.account_username if ig_conn else '',
                    'account_name': ig_conn.account_name if ig_conn else '',
                    'profile_picture_url': ig_conn.profile_picture_url if ig_conn else '',
                    'followers_count': ig_conn.metadata.get('followers_count', 0) if ig_conn else 0,
                },
                'facebook': {
                    'is_connected': bool(fb_conn),
                    'is_configured': meta_cfg['is_configured'],
                    'account_name': fb_conn.account_name if fb_conn else '',
                    'fan_count': fb_conn.metadata.get('fan_count', 0) if fb_conn else 0,
                },
                'twitter': {
                    'is_connected': bool(tw_conn),
                    'is_configured': twitter_cfg['is_configured'],
                    'account_username': tw_conn.account_username if tw_conn else '',
                    'account_name': tw_conn.account_name if tw_conn else '',
                    'profile_picture_url': tw_conn.profile_picture_url if tw_conn else '',
                    'followers_count': tw_conn.metadata.get('followers_count', 0) if tw_conn else 0,
                },
                'ads': {
                    'is_connected': bool(connections.filter(platform__in=['META_ADS', 'TWITTER_ADS']).exists()),
                    'is_configured': meta_cfg['is_configured'] or twitter_cfg['is_configured'],
                    'total_spend': insights['paid_overview']['total_spend'],
                    'active_campaigns': insights['paid_overview']['active_campaigns_count'],
                }
            },
            'recent_posts': SocialPostSerializer(recent_posts, many=True).data,
            'aggregated_insights': insights,
        }, status=status.HTTP_200_OK)


# ── Instagram Module Views ───────────────────────────────────────────────────

class InstagramStatusView(APIView):
    """
    Returns authorized Instagram Professional account status, connected details,
    and developer configuration state without exposing tokens.
    """
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def get(self, request):
        cfg = MetaService.get_config()
        conn = SocialAccountConnection.objects.filter(
            user=request.user, platform='INSTAGRAM', is_active=True
        ).first()

        connection_data = None
        if conn:
            connection_data = SocialAccountConnectionSerializer(conn).data

        return Response({
            'is_configured': cfg['is_configured'],
            'config_error': None if cfg['is_configured'] else "Meta App ID or Secret is not configured in backend environment variables (META_APP_ID, META_APP_SECRET).",
            'is_connected': bool(conn),
            'account': connection_data,
            'required_permissions': [
                'instagram_basic',
                'instagram_content_publish',
                'instagram_manage_insights',
                'pages_show_list',
                'pages_read_engagement',
            ],
            'prerequisites': [
                "Instagram account must be a Business or Creator Professional account.",
                "Instagram account must be linked to a Facebook Page.",
                "Meta developer app must have Instagram Graph API and Facebook Login configured.",
            ]
        }, status=status.HTTP_200_OK)


class InstagramAuthURLView(APIView):
    """Generates signed CSRF-protected Meta OAuth authorization URL for Instagram."""
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def get(self, request):
        try:
            url, signed_state = MetaService.generate_auth_url(request.user.id, platform='INSTAGRAM')
            return Response({'url': url, 'state': signed_state}, status=status.HTTP_200_OK)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class InstagramCallbackView(APIView):
    """Handles OAuth callback and associates Instagram Professional account."""
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def post(self, request):
        serializer = OAuthCallbackSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        code = serializer.validated_data['code']
        state = serializer.validated_data['state']

        if not MetaService.verify_state(state, request.user.id):
            return Response({'error': 'Invalid or expired OAuth state.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tokens = MetaService.exchange_code_for_token(code, platform='INSTAGRAM')
            access_token = tokens.get('access_token')
            expires_in = tokens.get('expires_in', 5184000)  # ~60 days default

            ig_info = MetaService.fetch_instagram_account(access_token)

            conn, _ = SocialAccountConnection.objects.get_or_create(
                user=request.user,
                platform='INSTAGRAM',
                account_id=ig_info['ig_id']
            )
            conn.account_name = ig_info.get('name') or ig_info.get('username')
            conn.account_username = ig_info.get('username')
            conn.profile_picture_url = ig_info.get('profile_picture_url', '')
            conn.set_access_token(access_token)
            conn.token_expiry = timezone.now() + timezone.timedelta(seconds=expires_in)
            conn.scopes = 'instagram_basic,instagram_content_publish,instagram_manage_insights'
            conn.is_active = True
            conn.metadata = {
                'page_id': ig_info.get('page_id'),
                'page_name': ig_info.get('page_name'),
                'page_access_token': ig_info.get('page_access_token'),
                'followers_count': ig_info.get('followers_count', 0),
                'media_count': ig_info.get('media_count', 0),
                'biography': ig_info.get('biography', ''),
            }
            conn.save()

            return Response({
                'success': True,
                'detail': 'Instagram Professional account connected successfully.',
                'account': SocialAccountConnectionSerializer(conn).data,
            }, status=status.HTTP_200_OK)

        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Error connecting Instagram account: %s", exc)
            return Response({'error': f"Failed to complete Instagram connection: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class InstagramDisconnectView(APIView):
    """Disconnects authorized Instagram account for the user."""
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def post(self, request):
        SocialAccountConnection.objects.filter(user=request.user, platform='INSTAGRAM').delete()
        return Response({'success': True, 'detail': 'Instagram account disconnected.'}, status=status.HTTP_200_OK)


class InstagramPostsView(APIView):
    """Lists Instagram posts / insights, and publishes new photo posts via official API."""
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def get(self, request):
        conn = SocialAccountConnection.objects.filter(
            user=request.user, platform='INSTAGRAM', is_active=True
        ).first()

        db_posts = SocialPost.objects.filter(user=request.user, platform='INSTAGRAM').order_by('-published_at')

        live_posts = []
        if conn:
            token = conn.get_access_token()
            if token and conn.account_id:
                try:
                    live_posts = MetaService.fetch_instagram_media(token, conn.account_id)
                except Exception as e:
                    logger.warning("Failed to fetch live Instagram posts: %s", e)

        return Response({
            'is_connected': bool(conn),
            'database_posts': SocialPostSerializer(db_posts, many=True, context={'request': request}).data,
            'live_posts': live_posts,
        }, status=status.HTTP_200_OK)

    def post(self, request):
        conn = SocialAccountConnection.objects.filter(
            user=request.user, platform='INSTAGRAM', is_active=True
        ).first()

        caption = request.data.get('caption', '').strip()
        image_url = request.data.get('image_url', '').strip()
        image_file = request.FILES.get('image_file')
        publish_live = str(request.data.get('publish_live', 'false')).lower() in ['true', '1']

        if not image_file and not image_url and not caption:
            return Response({'error': 'Please provide either an image file, an image URL, or a caption.'}, status=status.HTTP_400_BAD_REQUEST)

        # If user explicitly requested live publishing to Instagram Graph API
        if publish_live:
            if not conn:
                return Response({'error': 'No authorized Instagram account connected to publish live.'}, status=status.HTTP_400_BAD_REQUEST)

            # If image_file was uploaded from device but no image_url provided, host it temporarily for Meta
            if not image_url and image_file:
                image_url = MetaService.upload_temporary_media(image_file)
                if not image_url:
                    return Response({
                        'error': 'Could not generate a public image link for your uploaded file. Please paste a public image URL or uncheck "Publish live".'
                    }, status=status.HTTP_400_BAD_REQUEST)

            if not image_url:
                return Response({'error': 'Instagram API live publishing requires an image file or a public image URL.'}, status=status.HTTP_400_BAD_REQUEST)

            tokens_to_try = [t for t in [conn.metadata.get('page_access_token'), conn.get_access_token()] if t]
            if not tokens_to_try:
                return Response({'error': 'Instagram access token is missing.'}, status=status.HTTP_400_BAD_REQUEST)

            last_err = None
            pub_result = None
            for token in tokens_to_try:
                try:
                    pub_result = MetaService.publish_instagram_photo(token, conn.account_id, image_url, caption)
                    break
                except Exception as ex:
                    last_err = ex

            if not pub_result:
                error_msg = str(last_err) if last_err else 'Failed to publish to Instagram Graph API.'
                if 'instagram_content_publish' in error_msg:
                    error_msg += " Please disconnect and reconnect your Instagram account to grant the 'instagram_content_publish' permission."
                return Response({'error': error_msg}, status=status.HTTP_400_BAD_REQUEST)

            post_id = pub_result.get('id', '')
            post = SocialPost.objects.create(
                user=request.user,
                platform='INSTAGRAM',
                account_connection=conn,
                external_post_id=post_id,
                caption=caption,
                media_url=image_url,
                media_file=image_file,
                media_type='IMAGE',
                status='PUBLISHED',
                published_at=timezone.now(),
                metrics={'likes': 0, 'comments': 0},
            )
            return Response({
                'success': True,
                'detail': 'Instagram post published live to your official Instagram account!',
                'post': SocialPostSerializer(post, context={'request': request}).data,
            }, status=status.HTTP_201_CREATED)

        # Normal Post Upload (saved directly to user's workspace / database)
        post = SocialPost.objects.create(
            user=request.user,
            platform='INSTAGRAM',
            account_connection=conn if conn else None,
            caption=caption,
            media_url=image_url,
            media_file=image_file,
            media_type='IMAGE',
            status='PUBLISHED',
            published_at=timezone.now(),
            metrics={'likes': 0, 'comments': 0},
        )
        return Response({
            'success': True,
            'detail': 'Normal post uploaded successfully to your Instagram workspace.',
            'post': SocialPostSerializer(post, context={'request': request}).data,
        }, status=status.HTTP_201_CREATED)


# ── Facebook Module Views ────────────────────────────────────────────────────

class FacebookStatusView(APIView):
    """
    Returns authorized Facebook Pages connection status, authorized pages,
    and developer configuration state without exposing tokens.
    """
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def get(self, request):
        cfg = MetaService.get_config()
        connections = SocialAccountConnection.objects.filter(
            user=request.user, platform='FACEBOOK', is_active=True
        )

        return Response({
            'is_configured': cfg['is_configured'],
            'config_error': None if cfg['is_configured'] else "Meta App ID or Secret is not configured in backend environment variables.",
            'is_connected': connections.exists(),
            'pages': SocialAccountConnectionSerializer(connections, many=True).data,
            'required_permissions': [
                'pages_show_list',
                'pages_read_engagement',
                'business_management',
            ],
            'notes': [
                "Facebook Page management requires authorizing Pages you manage.",
                "Personal profile posts are not supported by the Graph API; Pages are required.",
                "Add 'pages_manage_posts' in Meta Developer App Use Cases if live page publishing is needed.",
            ]
        }, status=status.HTTP_200_OK)


class FacebookAuthURLView(APIView):
    """Generates signed CSRF-protected Meta OAuth authorization URL for Facebook Pages."""
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def get(self, request):
        try:
            url, signed_state = MetaService.generate_auth_url(request.user.id, platform='FACEBOOK')
            return Response({'url': url, 'state': signed_state}, status=status.HTTP_200_OK)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class FacebookCallbackView(APIView):
    """Handles OAuth callback and associates authorized Facebook Pages."""
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def post(self, request):
        serializer = OAuthCallbackSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        code = serializer.validated_data['code']
        state = serializer.validated_data['state']

        if not MetaService.verify_state(state, request.user.id):
            return Response({'error': 'Invalid or expired OAuth state.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tokens = MetaService.exchange_code_for_token(code, platform='FACEBOOK')
            user_access_token = tokens.get('access_token')
            expires_in = tokens.get('expires_in', 5184000)

            pages = MetaService.fetch_facebook_pages(user_access_token)
            if not pages:
                return Response(
                    {'error': 'No Facebook Pages found under this account. Please create or manage a Facebook Page first.'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            saved_pages = []
            for page in pages:
                page_id = page.get('id')
                page_name = page.get('name')
                page_token = page.get('access_token')
                fan_count = page.get('fan_count', 0)
                category = page.get('category', '')
                pic_url = page.get('picture', {}).get('data', {}).get('url', '')

                conn, _ = SocialAccountConnection.objects.get_or_create(
                    user=request.user,
                    platform='FACEBOOK',
                    account_id=page_id
                )
                conn.account_name = page_name
                conn.account_username = page_name
                conn.profile_picture_url = pic_url
                conn.set_access_token(page_token or user_access_token)
                conn.token_expiry = timezone.now() + timezone.timedelta(seconds=expires_in)
                conn.scopes = 'pages_show_list,pages_read_engagement,business_management'
                conn.is_active = True
                conn.metadata = {
                    'category': category,
                    'fan_count': fan_count,
                    'tasks': page.get('tasks', []),
                }
                conn.save()
                saved_pages.append(conn)

            return Response({
                'success': True,
                'detail': f"Connected {len(saved_pages)} Facebook Page(s) successfully.",
                'pages': SocialAccountConnectionSerializer(saved_pages, many=True).data,
            }, status=status.HTTP_200_OK)

        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Error connecting Facebook Pages: %s", exc)
            return Response({'error': f"Failed to connect Facebook Pages: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FacebookDisconnectView(APIView):
    """Disconnects authorized Facebook Pages."""
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def post(self, request):
        page_id = request.data.get('page_id')
        if page_id:
            SocialAccountConnection.objects.filter(user=request.user, platform='FACEBOOK', account_id=page_id).delete()
        else:
            SocialAccountConnection.objects.filter(user=request.user, platform='FACEBOOK').delete()
        return Response({'success': True, 'detail': 'Facebook Page(s) disconnected.'}, status=status.HTTP_200_OK)


class FacebookPostsView(APIView):
    """Lists Facebook posts & insights, and publishes supported posts to authorized Pages."""
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def get(self, request):
        conn = SocialAccountConnection.objects.filter(
            user=request.user, platform='FACEBOOK', is_active=True
        ).first()

        db_posts = SocialPost.objects.filter(user=request.user, platform='FACEBOOK').order_by('-published_at')

        live_posts = []
        if conn:
            token = conn.get_access_token()
            if token and conn.account_id:
                try:
                    live_posts = MetaService.fetch_facebook_page_posts(token, conn.account_id)
                except Exception as e:
                    logger.warning("Failed to fetch live Facebook Page posts: %s", e)

        return Response({
            'is_connected': bool(conn),
            'database_posts': SocialPostSerializer(db_posts, many=True).data,
            'live_posts': live_posts,
        }, status=status.HTTP_200_OK)

    def post(self, request):
        page_id = request.data.get('page_id')
        conn_query = SocialAccountConnection.objects.filter(user=request.user, platform='FACEBOOK', is_active=True)
        conn = conn_query.filter(account_id=page_id).first() if page_id else conn_query.first()

        message = request.data.get('message', '').strip() or request.data.get('caption', '').strip()
        link = request.data.get('link', '').strip()
        image_file = request.FILES.get('image_file')
        publish_live = str(request.data.get('publish_live', 'false')).lower() in ['true', '1']

        if not message and not link and not image_file:
            return Response({'error': 'Please provide a message, link, or image file.'}, status=status.HTTP_400_BAD_REQUEST)

        # If user explicitly requested live publishing to Facebook Page via Meta Graph API
        if publish_live:
            if not conn:
                return Response({'error': 'No authorized Facebook Page connected to publish live.'}, status=status.HTTP_400_BAD_REQUEST)
            token = conn.get_access_token()
            if not token:
                return Response({'error': 'Page access token is missing. Please re-authenticate.'}, status=status.HTTP_400_BAD_REQUEST)
            try:
                pub_result = MetaService.publish_facebook_page_post(token, conn.account_id, message, link)
                post_id = pub_result.get('id', '')
                post = SocialPost.objects.create(
                    user=request.user,
                    platform='FACEBOOK',
                    account_connection=conn,
                    external_post_id=post_id,
                    caption=message,
                    media_url=link,
                    media_file=image_file,
                    media_type='TEXT' if not link and not image_file else ('IMAGE' if image_file else 'LINK'),
                    status='PUBLISHED',
                    published_at=timezone.now(),
                    metrics={'reactions_count': 0, 'comments_count': 0, 'shares_count': 0},
                )
                return Response({
                    'success': True,
                    'detail': 'Post published to Facebook Page successfully.',
                    'post': SocialPostSerializer(post, context={'request': request}).data,
                }, status=status.HTTP_201_CREATED)
            except ValueError as exc:
                return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as exc:
                logger.exception("Facebook publishing failed: %s", exc)
                return Response({'error': f"Publishing failed: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Normal Post Upload (saved directly to user's workspace / database)
        post = SocialPost.objects.create(
            user=request.user,
            platform='FACEBOOK',
            account_connection=conn if conn else None,
            caption=message,
            media_url=link,
            media_file=image_file,
            media_type='TEXT' if not link and not image_file else ('IMAGE' if image_file else 'LINK'),
            status='PUBLISHED',
            published_at=timezone.now(),
            metrics={'reactions_count': 0, 'comments_count': 0, 'shares_count': 0},
        )
        return Response({
            'success': True,
            'detail': 'Normal post uploaded successfully to your Facebook workspace.',
            'post': SocialPostSerializer(post, context={'request': request}).data,
        }, status=status.HTTP_201_CREATED)


class SocialPostDeleteView(APIView):
    """Deletes an uploaded post from the workspace feed."""
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def delete(self, request, pk):
        post = SocialPost.objects.filter(user=request.user, pk=pk).first()
        if not post:
            return Response({'error': 'Post not found.'}, status=status.HTTP_404_NOT_FOUND)
        post.delete()
        return Response({'success': True, 'detail': 'Post deleted.'}, status=status.HTTP_200_OK)


# ── Twitter / X Module Views ─────────────────────────────────────────────────

class TwitterStatusView(APIView):
    """
    Returns Twitter/X account connection status, user profile metrics,
    API access tier information, and configuration status without exposing tokens.
    """
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def get(self, request):
        cfg = TwitterService.get_config()
        conn = SocialAccountConnection.objects.filter(
            user=request.user, platform='TWITTER', is_active=True
        ).first()

        connection_data = None
        if conn:
            connection_data = SocialAccountConnectionSerializer(conn).data

        return Response({
            'is_configured': cfg['is_configured'],
            'config_error': None if cfg['is_configured'] else "Twitter/X client credentials are not configured in backend environment variables (TWITTER_CLIENT_ID, TWITTER_CLIENT_SECRET).",
            'is_connected': bool(conn),
            'account': connection_data,
            'api_info': {
                'api_version': 'v2',
                'auth_type': 'OAuth 2.0 with PKCE',
                'supported_scopes': ['tweet.read', 'tweet.write', 'users.read', 'offline.access'],
                'free_tier_limits': '1,500 Tweets per month (Free tier) or 50,000 Tweets (Basic tier).',
            }
        }, status=status.HTTP_200_OK)


class TwitterAuthURLView(APIView):
    """Generates PKCE OAuth 2.0 authorization URL for Twitter/X."""
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def get(self, request):
        try:
            url, signed_state, _ = TwitterService.generate_auth_url(request.user.id)
            return Response({'url': url, 'state': signed_state}, status=status.HTTP_200_OK)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class TwitterCallbackView(APIView):
    """Exchanges PKCE authorization code for Twitter/X tokens and records connection."""
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def post(self, request):
        serializer = OAuthCallbackSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        code = serializer.validated_data['code']
        state = serializer.validated_data['state']

        is_valid, code_verifier = TwitterService.verify_state_and_extract_verifier(state, request.user.id)
        if not is_valid or not code_verifier:
            return Response({'error': 'Invalid or expired Twitter/X OAuth state.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tokens = TwitterService.exchange_code_for_tokens(code, code_verifier)
            access_token = tokens.get('access_token')
            refresh_token = tokens.get('refresh_token', '')
            expires_in = tokens.get('expires_in', 7200)

            profile = TwitterService.fetch_user_profile(access_token)

            conn, _ = SocialAccountConnection.objects.get_or_create(
                user=request.user,
                platform='TWITTER',
                account_id=profile['id']
            )
            conn.account_name = profile.get('name') or profile.get('username')
            conn.account_username = profile.get('username')
            conn.profile_picture_url = profile.get('profile_image_url', '')
            conn.set_access_token(access_token)
            if refresh_token:
                conn.set_refresh_token(refresh_token)
            conn.token_expiry = timezone.now() + timezone.timedelta(seconds=expires_in)
            conn.scopes = 'tweet.read tweet.write users.read offline.access'
            conn.is_active = True
            conn.metadata = {
                'followers_count': profile.get('followers_count', 0),
                'following_count': profile.get('following_count', 0),
                'tweet_count': profile.get('tweet_count', 0),
                'description': profile.get('description', ''),
            }
            conn.save()

            return Response({
                'success': True,
                'detail': 'Twitter/X account connected successfully.',
                'account': SocialAccountConnectionSerializer(conn).data,
            }, status=status.HTTP_200_OK)

        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Error connecting Twitter/X account: %s", exc)
            return Response({'error': f"Failed to connect Twitter/X account: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TwitterDisconnectView(APIView):
    """Disconnects authorized Twitter/X account."""
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def post(self, request):
        SocialAccountConnection.objects.filter(user=request.user, platform='TWITTER').delete()
        return Response({'success': True, 'detail': 'Twitter/X account disconnected.'}, status=status.HTTP_200_OK)


class TwitterTweetsView(APIView):
    """Lists tweets & public metrics, and publishes new tweets via official X API v2."""
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def get(self, request):
        conn = SocialAccountConnection.objects.filter(
            user=request.user, platform='TWITTER', is_active=True
        ).first()

        db_tweets = SocialPost.objects.filter(user=request.user, platform='TWITTER').order_by('-published_at')

        live_tweets = []
        if conn:
            token = conn.get_access_token()
            if token and conn.account_id:
                try:
                    live_tweets = TwitterService.fetch_user_tweets(token, conn.account_id)
                except Exception as e:
                    logger.warning("Failed to fetch live tweets: %s", e)

        return Response({
            'is_connected': bool(conn),
            'database_tweets': SocialPostSerializer(db_tweets, many=True).data,
            'live_tweets': live_tweets,
        }, status=status.HTTP_200_OK)

    def post(self, request):
        conn = SocialAccountConnection.objects.filter(
            user=request.user, platform='TWITTER', is_active=True
        ).first()
        if not conn:
            return Response({'error': 'No authorized Twitter/X account connected.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = TwitterTweetSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        text = serializer.validated_data['text']
        token = conn.get_access_token()
        if not token:
            return Response({'error': 'Access token is missing. Please re-authenticate.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tweet_data = TwitterService.post_tweet(token, text)
            tweet_id = tweet_data.get('id', '')

            post = SocialPost.objects.create(
                user=request.user,
                platform='TWITTER',
                account_connection=conn,
                external_post_id=tweet_id,
                caption=text,
                media_type='TEXT',
                status='PUBLISHED',
                published_at=timezone.now(),
                metrics={'like_count': 0, 'retweet_count': 0, 'reply_count': 0},
            )

            return Response({
                'success': True,
                'detail': 'Tweet posted successfully.',
                'tweet': SocialPostSerializer(post).data,
            }, status=status.HTTP_201_CREATED)

        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Twitter tweet posting failed: %s", exc)
            return Response({'error': f"Failed to post tweet: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ── Ads & Insights Module Views ──────────────────────────────────────────────

class AdsOverviewView(APIView):
    """
    Returns consolidated advertising metrics (Meta Ads and X Ads strictly separated)
    and organic social insights. Read-only reporting workspace.
    """
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def get(self, request):
        insights = AdsService.get_aggregated_insights(request.user)
        return Response(insights, status=status.HTTP_200_OK)


class AdsCampaignsView(APIView):
    """
    Lists advertising campaigns across Meta Ads and X Ads.
    Supports filtering by platform ('META_ADS', 'TWITTER_ADS') and date range.
    """
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def get(self, request):
        platform_filter = request.query_params.get('platform')
        campaigns = AdCampaign.objects.filter(user=request.user)
        if platform_filter in ['META_ADS', 'TWITTER_ADS']:
            campaigns = campaigns.filter(platform=platform_filter)

        return Response({
            'campaigns': AdCampaignSerializer(campaigns, many=True).data,
            'count': campaigns.count(),
        }, status=status.HTTP_200_OK)
