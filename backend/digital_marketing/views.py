import logging
import hmac
import hashlib
import json
import os
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny

from accounts.permissions import IsDigitalMarketing
from .models import SocialAccountConnection, SocialPost, AdCampaign, ConversationThread, DirectMessage
from .serializers import (
    SocialAccountConnectionSerializer,
    SocialPostSerializer,
    AdCampaignSerializer,
    InstagramPublishSerializer,
    FacebookPublishSerializer,
    TwitterTweetSerializer,
    OAuthCallbackSerializer,
    ConversationThreadSerializer,
    DirectMessageSerializer,
    SendMessageSerializer,
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
            token = (conn.metadata or {}).get('page_access_token') or conn.get_access_token()
            if token and conn.account_id:
                try:
                    prof = MetaService.fetch_instagram_profile_info(token, conn.account_id)
                    if prof:
                        conn.metadata = conn.metadata or {}
                        conn.metadata['followers_count'] = prof.get('followers_count', conn.metadata.get('followers_count', 0))
                        conn.metadata['follows_count'] = prof.get('follows_count', conn.metadata.get('follows_count', 0))
                        conn.metadata['media_count'] = prof.get('media_count', conn.metadata.get('media_count', 0))
                        conn.save(update_fields=['metadata', 'updated_at'])
                except Exception as ex:
                    logger.warning("Could not refresh live IG followers: %s", ex)
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
            custom_redirect = request.query_params.get('redirect_uri')
            redirect_uri = MetaService.get_redirect_uri(
                platform='INSTAGRAM',
                request=request,
                custom_redirect_uri=custom_redirect
            )
            url, signed_state = MetaService.generate_auth_url(
                request.user.id,
                platform='INSTAGRAM',
                redirect_uri=redirect_uri
            )
            return Response({'url': url, 'state': signed_state, 'redirect_uri': redirect_uri}, status=status.HTTP_200_OK)
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

        state_payload = MetaService.get_state_payload(state, request.user.id)
        if not state_payload:
            return Response({'error': 'Invalid or expired OAuth state.'}, status=status.HTTP_400_BAD_REQUEST)

        redirect_uri = state_payload.get('redirect_uri')

        try:
            tokens = MetaService.exchange_code_for_token(code, platform='INSTAGRAM', redirect_uri=redirect_uri)
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
            page_token = ig_info.get('page_access_token') or access_token
            conn.set_access_token(page_token)
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

        pages_list = []
        for p_conn in connections:
            token = p_conn.get_access_token()
            if token and p_conn.account_id:
                try:
                    p_info = MetaService.fetch_facebook_page_info(token, p_conn.account_id)
                    if p_info:
                        p_conn.metadata = p_conn.metadata or {}
                        p_conn.metadata['fan_count'] = p_info.get('fan_count', p_conn.metadata.get('fan_count', 0))
                        p_conn.metadata['followers_count'] = p_info.get('followers_count', p_conn.metadata.get('followers_count', 0))
                        p_conn.save(update_fields=['metadata', 'updated_at'])
                except Exception as ex:
                    logger.warning("Could not refresh live FB page fans: %s", ex)
            pages_list.append(p_conn)

        return Response({
            'is_configured': cfg['is_configured'],
            'config_error': None if cfg['is_configured'] else "Meta App ID or Secret is not configured in backend environment variables.",
            'is_connected': connections.exists(),
            'pages': SocialAccountConnectionSerializer(pages_list, many=True).data,
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
            custom_redirect = request.query_params.get('redirect_uri')
            redirect_uri = MetaService.get_redirect_uri(
                platform='FACEBOOK',
                request=request,
                custom_redirect_uri=custom_redirect
            )
            url, signed_state = MetaService.generate_auth_url(
                request.user.id,
                platform='FACEBOOK',
                redirect_uri=redirect_uri
            )
            return Response({'url': url, 'state': signed_state, 'redirect_uri': redirect_uri}, status=status.HTTP_200_OK)
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

        state_payload = MetaService.get_state_payload(state, request.user.id)
        if not state_payload:
            return Response({'error': 'Invalid or expired OAuth state.'}, status=status.HTTP_400_BAD_REQUEST)

        redirect_uri = state_payload.get('redirect_uri')

        try:
            tokens = MetaService.exchange_code_for_token(code, platform='FACEBOOK', redirect_uri=redirect_uri)
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
            'database_posts': SocialPostSerializer(db_posts, many=True, context={'request': request}).data,
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

            image_url = ''
            if image_file:
                image_url = MetaService.upload_temporary_media(image_file)

            try:
                pub_result = MetaService.publish_facebook_page_post(token, conn.account_id, message, link, image_url=image_url)
                post_id = pub_result.get('id', '') or pub_result.get('post_id', '')
                post = SocialPost.objects.create(
                    user=request.user,
                    platform='FACEBOOK',
                    account_connection=conn,
                    external_post_id=post_id,
                    caption=message,
                    media_url=image_url or link,
                    media_file=image_file,
                    media_type='IMAGE' if image_file else ('LINK' if link else 'TEXT'),
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


class UniversalPostUploadView(APIView):
    """
    Universal Post Publisher: Simultaneously broadcasts a post across Instagram
    and Facebook Page at the same time using official Meta Graph API.
    """
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def post(self, request):
        caption = request.data.get('caption', '').strip() or request.data.get('message', '').strip()
        link = request.data.get('link', '').strip()
        image_file = request.FILES.get('image_file')
        image_url = request.data.get('image_url', '').strip()
        publish_live = str(request.data.get('publish_live', 'false')).lower() in ['true', '1']

        # Parse target platforms
        raw_platforms = request.data.get('platforms', '')
        if isinstance(raw_platforms, list):
            target_platforms = [str(p).upper() for p in raw_platforms]
        elif isinstance(raw_platforms, str) and raw_platforms.strip():
            target_platforms = [p.strip().upper() for p in raw_platforms.split(',') if p.strip()]
        else:
            target_platforms = ['INSTAGRAM', 'FACEBOOK']

        if not caption and not image_file and not image_url and not link:
            return Response({'error': 'Please provide an image, caption, or link to upload.'}, status=status.HTTP_400_BAD_REQUEST)

        # Upload image once to public temporary media if file is provided
        effective_image_url = image_url
        if image_file:
            try:
                effective_image_url = MetaService.upload_temporary_media(image_file)
            except Exception as e:
                logger.warning("Could not upload temporary media for universal post: %s", e)

        published_records = []
        errors = []

        # 1. Instagram broadcast
        if 'INSTAGRAM' in target_platforms:
            ig_conn = SocialAccountConnection.objects.filter(user=request.user, platform='INSTAGRAM', is_active=True).first()
            if publish_live:
                if not effective_image_url:
                    errors.append({'platform': 'INSTAGRAM', 'error': 'Instagram API live publishing requires an image file or URL.'})
                elif not ig_conn:
                    errors.append({'platform': 'INSTAGRAM', 'error': 'No connected Instagram account found.'})
                else:
                    tokens_to_try = [t for t in [(ig_conn.metadata or {}).get('page_access_token'), ig_conn.get_access_token()] if t]
                    ig_pub_result = None
                    ig_last_err = None
                    for token in tokens_to_try:
                        try:
                            ig_pub_result = MetaService.publish_instagram_photo(token, ig_conn.account_id, effective_image_url, caption)
                            break
                        except Exception as ex:
                            ig_last_err = ex

                    if ig_pub_result:
                        ext_id = ig_pub_result.get('id', '')
                        post = SocialPost.objects.create(
                            user=request.user,
                            platform='INSTAGRAM',
                            account_connection=ig_conn,
                            external_post_id=ext_id,
                            caption=caption,
                            media_url=effective_image_url,
                            media_file=image_file,
                            media_type='IMAGE',
                            status='PUBLISHED',
                            published_at=timezone.now(),
                            metrics={'likes': 0, 'comments': 0},
                        )
                        published_records.append({
                            'platform': 'INSTAGRAM',
                            'success': True,
                            'post_id': post.id,
                            'external_id': ext_id,
                            'account': ig_conn.account_username or ig_conn.account_name,
                        })
                    else:
                        errors.append({'platform': 'INSTAGRAM', 'error': str(ig_last_err or 'Failed to publish to Instagram.')})
            else:
                post = SocialPost.objects.create(
                    user=request.user,
                    platform='INSTAGRAM',
                    account_connection=ig_conn if ig_conn else None,
                    caption=caption,
                    media_url=effective_image_url,
                    media_file=image_file,
                    media_type='IMAGE' if effective_image_url else 'TEXT',
                    status='PUBLISHED',
                    published_at=timezone.now(),
                    metrics={'likes': 0, 'comments': 0},
                )
                published_records.append({'platform': 'INSTAGRAM', 'success': True, 'mode': 'WORKSPACE', 'post_id': post.id})

        # 2. Facebook broadcast
        if 'FACEBOOK' in target_platforms:
            fb_conn = SocialAccountConnection.objects.filter(user=request.user, platform='FACEBOOK', is_active=True).first()
            if publish_live:
                if not fb_conn:
                    errors.append({'platform': 'FACEBOOK', 'error': 'No authorized Facebook Page connected.'})
                else:
                    fb_token = fb_conn.get_access_token()
                    if not fb_token:
                        errors.append({'platform': 'FACEBOOK', 'error': 'Facebook Page access token is missing.'})
                    else:
                        try:
                            fb_pub_result = MetaService.publish_facebook_page_post(
                                fb_token, fb_conn.account_id, caption, link, image_url=effective_image_url
                            )
                            fb_ext_id = fb_pub_result.get('id', '') or fb_pub_result.get('post_id', '')
                            post = SocialPost.objects.create(
                                user=request.user,
                                platform='FACEBOOK',
                                account_connection=fb_conn,
                                external_post_id=fb_ext_id,
                                caption=caption,
                                media_url=effective_image_url or link,
                                media_file=image_file,
                                media_type='IMAGE' if effective_image_url else ('LINK' if link else 'TEXT'),
                                status='PUBLISHED',
                                published_at=timezone.now(),
                                metrics={'reactions_count': 0, 'comments_count': 0, 'shares_count': 0},
                            )
                            published_records.append({
                                'platform': 'FACEBOOK',
                                'success': True,
                                'post_id': post.id,
                                'external_id': fb_ext_id,
                                'account': fb_conn.account_name,
                            })
                        except Exception as exc:
                            errors.append({'platform': 'FACEBOOK', 'error': str(exc)})
            else:
                post = SocialPost.objects.create(
                    user=request.user,
                    platform='FACEBOOK',
                    account_connection=fb_conn if fb_conn else None,
                    caption=caption,
                    media_url=effective_image_url or link,
                    media_file=image_file,
                    media_type='IMAGE' if effective_image_url else ('LINK' if link else 'TEXT'),
                    status='PUBLISHED',
                    published_at=timezone.now(),
                    metrics={'reactions_count': 0, 'comments_count': 0, 'shares_count': 0},
                )
                published_records.append({'platform': 'FACEBOOK', 'success': True, 'mode': 'WORKSPACE', 'post_id': post.id})

        # Formulate unified response
        success_names = [f"{r['platform'].title()} ({r.get('account', 'Account')})" for r in published_records if r.get('success')]
        if len(success_names) >= 2:
            detail_msg = f"Universal post published simultaneously to {' and '.join(success_names)}!"
        elif len(success_names) == 1:
            detail_msg = f"Post published successfully to {success_names[0]}."
        elif errors:
            detail_msg = f"Failed to publish: {'; '.join([e['error'] for e in errors])}"
            return Response({'error': detail_msg, 'errors': errors}, status=status.HTTP_400_BAD_REQUEST)
        else:
            detail_msg = "Post uploaded successfully."

        return Response({
            'success': True,
            'detail': detail_msg,
            'published': published_records,
            'errors': errors,
        }, status=status.HTTP_201_CREATED)


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
            custom_redirect = request.query_params.get('redirect_uri')
            redirect_uri = TwitterService.get_redirect_uri(request=request, custom_redirect_uri=custom_redirect)
            url, signed_state, _ = TwitterService.generate_auth_url(request.user.id, redirect_uri=redirect_uri)
            return Response({'url': url, 'state': signed_state, 'redirect_uri': redirect_uri}, status=status.HTTP_200_OK)
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

        is_valid, code_verifier, redirect_uri = TwitterService.verify_state_and_extract_verifier(state, request.user.id)
        if not is_valid or not code_verifier:
            return Response({'error': 'Invalid or expired Twitter/X OAuth state.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tokens = TwitterService.exchange_code_for_tokens(code, code_verifier, redirect_uri=redirect_uri)
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
        serializer = TwitterTweetSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        text = serializer.validated_data['text']
        publish_live = serializer.validated_data.get('publish_live', True)

        conn = SocialAccountConnection.objects.filter(
            user=request.user, platform='TWITTER', is_active=True
        ).first()

        if publish_live:
            if not conn:
                return Response({'error': 'No authorized Twitter/X account connected to publish live.'}, status=status.HTTP_400_BAD_REQUEST)

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
                    'detail': 'Tweet posted successfully to X!',
                    'tweet': SocialPostSerializer(post).data,
                }, status=status.HTTP_201_CREATED)

            except ValueError as exc:
                return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as exc:
                logger.exception("Twitter tweet posting failed: %s", exc)
                return Response({'error': f"Failed to post tweet: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Normal workspace post (stored directly in workspace feed)
        post = SocialPost.objects.create(
            user=request.user,
            platform='TWITTER',
            account_connection=conn if conn else None,
            external_post_id='',
            caption=text,
            media_type='TEXT',
            status='PUBLISHED',
            published_at=timezone.now(),
            metrics={'like_count': 0, 'retweet_count': 0, 'reply_count': 0},
        )
        return Response({
            'success': True,
            'detail': 'Tweet saved to your workspace feed successfully.',
            'tweet': SocialPostSerializer(post).data,
        }, status=status.HTTP_201_CREATED)


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


# ── Unified Social Messaging Views (Instagram DMs & Facebook Messenger) ─────

class ConversationListView(APIView):
    """
    Returns active conversation threads for the authenticated user,
    with filtering by platform ('INSTAGRAM', 'FACEBOOK') and search.
    """
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def get(self, request):
        from django.db import models as db_models
        platform_filter = request.query_params.get('platform', '').upper()
        search_query = request.query_params.get('search', '').strip()

        threads = ConversationThread.objects.filter(user=request.user, is_archived=False)
        if platform_filter in ['INSTAGRAM', 'FACEBOOK']:
            threads = threads.filter(platform=platform_filter)

        if search_query:
            threads = threads.filter(
                db_models.Q(participant_name__icontains=search_query) |
                db_models.Q(participant_username__icontains=search_query) |
                db_models.Q(last_message_text__icontains=search_query)
            )

        unread_total = ConversationThread.objects.filter(user=request.user, is_archived=False).aggregate(
            total=db_models.Sum('unread_count')
        )['total'] or 0

        # Check account connection status for Instagram and Facebook
        has_instagram = SocialAccountConnection.objects.filter(user=request.user, platform='INSTAGRAM', is_active=True).exists()
        has_facebook = SocialAccountConnection.objects.filter(user=request.user, platform='FACEBOOK', is_active=True).exists()

        return Response({
            'conversations': ConversationThreadSerializer(threads, many=True).data,
            'count': threads.count(),
            'unread_total': unread_total,
            'connections': {
                'instagram': has_instagram,
                'facebook': has_facebook,
            }
        }, status=status.HTTP_200_OK)


class ConversationMessagesView(APIView):
    """
    Retrieves message history for a specific thread, and sends outbound replies
    directly via Meta Send API.
    """
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def get(self, request, thread_id):
        thread = ConversationThread.objects.filter(user=request.user, id=thread_id).first()
        if not thread:
            return Response({'error': 'Conversation thread not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Mark unread messages as read
        DirectMessage.objects.filter(thread=thread, sender_type='CUSTOMER', is_read=False).update(is_read=True)
        thread.unread_count = 0
        thread.save(update_fields=['unread_count'])

        messages = thread.messages.all().order_by('timestamp')
        return Response({
            'thread': ConversationThreadSerializer(thread).data,
            'messages': DirectMessageSerializer(messages, many=True).data,
        }, status=status.HTTP_200_OK)

    def post(self, request, thread_id):
        thread = ConversationThread.objects.filter(user=request.user, id=thread_id).first()
        if not thread:
            return Response({'error': 'Conversation thread not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = SendMessageSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        text = serializer.validated_data['text']
        media_url = serializer.validated_data.get('media_url', '')

        conn = thread.account_connection
        if not conn or not conn.is_active:
            return Response({'error': 'Connected social account is no longer active.'}, status=status.HTTP_400_BAD_REQUEST)

        token = (conn.metadata or {}).get('page_access_token') or conn.get_access_token()
        if not token and conn.platform == 'INSTAGRAM':
            fb_conn = SocialAccountConnection.objects.filter(
                user=request.user, platform='FACEBOOK', is_active=True
            ).first()
            if fb_conn:
                token = fb_conn.get_access_token()

        if not token:
            return Response({'error': 'Access token is missing. Please reconnect your account.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            res = MetaService.send_direct_message(
                page_access_token=token,
                recipient_id=thread.participant_id,
                text=text,
                media_url=media_url
            )
            msg_id = res.get('message_id', '')

            # Record outbound message
            now = timezone.now()
            dm = DirectMessage.objects.create(
                thread=thread,
                external_message_id=msg_id,
                sender_type='BUSINESS',
                sender_id=conn.account_id,
                sender_name=conn.account_name or 'Business',
                text=text,
                media_url=media_url,
                media_type='image' if media_url else 'text',
                timestamp=now,
                is_read=True,
                delivery_status='SENT',
            )

            # Update thread preview
            thread.last_message_text = text
            thread.last_message_at = now
            thread.save(update_fields=['last_message_text', 'last_message_at', 'updated_at'])

            return Response({
                'success': True,
                'detail': 'Message sent successfully.',
                'message': DirectMessageSerializer(dm).data,
            }, status=status.HTTP_201_CREATED)

        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Failed to send message: %s", exc)
            return Response({'error': f"Failed to send message: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ConversationSyncView(APIView):
    """
    Polls and synchronizes existing conversations and messages directly from Meta Graph API
    for connected Facebook Pages and Instagram accounts.
    """
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def post(self, request):
        connections = SocialAccountConnection.objects.filter(
            user=request.user,
            platform__in=['FACEBOOK', 'INSTAGRAM'],
            is_active=True
        )

        total_threads_synced = 0
        total_messages_synced = 0
        errors = []

        for conn in connections:
            token = conn.get_access_token()
            if not token or not conn.account_id:
                continue

            try:
                raw_convos = MetaService.fetch_page_conversations(
                    access_token=token,
                    page_id=conn.account_id,
                    platform=conn.platform
                )

                for item in raw_convos:
                    ext_id = item.get('id')
                    snippet = item.get('snippet', '')
                    raw_time = item.get('updated_time')
                    updated_at = timezone.now()
                    if raw_time:
                        try:
                            from django.utils.dateparse import parse_datetime
                            updated_at = parse_datetime(raw_time) or timezone.now()
                        except Exception:
                            pass

                    # Identify customer participant
                    participants = item.get('participants', {}).get('data', [])
                    participant_id = ''
                    participant_name = 'Customer'
                    for p in participants:
                        if str(p.get('id')) != str(conn.account_id):
                            participant_id = str(p.get('id'))
                            participant_name = p.get('name') or p.get('username') or 'Customer'
                            break

                    if not participant_id and participants:
                        participant_id = str(participants[0].get('id'))

                    if not participant_id:
                        continue

                    thread, created = ConversationThread.objects.get_or_create(
                        user=request.user,
                        platform=conn.platform,
                        external_thread_id=ext_id,
                        defaults={
                            'account_connection': conn,
                            'participant_id': participant_id,
                            'participant_name': participant_name,
                            'last_message_text': snippet,
                            'last_message_at': updated_at,
                        }
                    )
                    if not created:
                        thread.last_message_text = snippet
                        thread.last_message_at = updated_at
                        thread.save(update_fields=['last_message_text', 'last_message_at', 'updated_at'])

                    total_threads_synced += 1

                    # Fetch thread messages (use embedded messages if present for 10x faster sync)
                    raw_msgs = item.get('messages', {}).get('data')
                    if raw_msgs is None:
                        raw_msgs = MetaService.fetch_thread_messages(token, ext_id)
                    for m in raw_msgs:
                        mid = m.get('id')
                        m_text = m.get('message', '')
                        m_from = m.get('from', {})
                        from_id = str(m_from.get('id', ''))
                        is_business = (from_id == str(conn.account_id))

                        m_time = timezone.now()
                        if m.get('created_time'):
                            try:
                                from django.utils.dateparse import parse_datetime
                                m_time = parse_datetime(m.get('created_time')) or timezone.now()
                            except Exception:
                                pass

                        msg_obj, m_created = DirectMessage.objects.get_or_create(
                            thread=thread,
                            external_message_id=mid,
                            defaults={
                                'sender_type': 'BUSINESS' if is_business else 'CUSTOMER',
                                'sender_id': from_id,
                                'sender_name': m_from.get('name', 'User'),
                                'text': m_text,
                                'timestamp': m_time,
                                'is_read': is_business,
                                'delivery_status': 'DELIVERED',
                            }
                        )
                        if m_created:
                            total_messages_synced += 1

            except ValueError as ve:
                errors.append(f"{conn.get_platform_display()}: {ve}")
            except Exception as exc:
                logger.warning("Error syncing conversations for connection %s: %s", conn.id, exc)

        if total_threads_synced == 0 and errors:
            return Response({
                'success': False,
                'detail': ' '.join(errors),
                'threads_synced': 0,
            }, status=status.HTTP_400_BAD_REQUEST)

        return Response({
            'success': True,
            'detail': f"Sync complete. Synced {total_threads_synced} conversation(s) and {total_messages_synced} message(s).",
            'threads_synced': total_threads_synced,
            'messages_synced': total_messages_synced,
        }, status=status.HTTP_200_OK)


class MetaWebhookView(APIView):
    """
    Receives real-time incoming messages from Meta (Instagram Direct & Facebook Messenger).
    Verifies subscription handshake on GET, processes messaging events on POST.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        """Webhook verification handshake for Meta Developer App."""
        mode = request.query_params.get('hub.mode')
        token = request.query_params.get('hub.verify_token')
        challenge = request.query_params.get('hub.challenge')

        expected_token = os.getenv('META_WEBHOOK_VERIFY_TOKEN', 'market_intel_meta_webhook_2026')
        if mode == 'subscribe' and token == expected_token:
            return HttpResponse(challenge, content_type='text/plain', status=200)
        return HttpResponse('Verification token mismatch', status=403)

    def post(self, request):
        """Receives incoming message payloads from Meta."""
        try:
            body_bytes = request.body
            payload = json.loads(body_bytes.decode('utf-8'))
        except Exception:
            return HttpResponse('Invalid payload', status=400)

        obj = payload.get('object')
        if obj not in ('page', 'instagram'):
            return HttpResponse('EVENT_RECEIVED', status=200)

        entries = payload.get('entry', [])
        for entry in entries:
            messaging_events = entry.get('messaging', [])
            for evt in messaging_events:
                sender_id = str(evt.get('sender', {}).get('id', ''))
                recipient_id = str(evt.get('recipient', {}).get('id', ''))
                message = evt.get('message', {})
                mid = message.get('mid', '')
                text = message.get('text', '')
                attachments = message.get('attachments', [])
                timestamp_ms = evt.get('timestamp')

                media_url = ''
                if attachments and isinstance(attachments, list):
                    first_att = attachments[0]
                    media_url = first_att.get('payload', {}).get('url', '')

                # Find connection by page/account id
                conn = SocialAccountConnection.objects.filter(
                    account_id__in=[recipient_id, sender_id],
                    is_active=True
                ).first()

                if not conn:
                    continue

                is_incoming = (sender_id != conn.account_id)
                customer_id = sender_id if is_incoming else recipient_id

                thread_ext_id = f"{conn.account_id}_{customer_id}"
                thread, _ = ConversationThread.objects.get_or_create(
                    user=conn.user,
                    platform=conn.platform,
                    external_thread_id=thread_ext_id,
                    defaults={
                        'account_connection': conn,
                        'participant_id': customer_id,
                        'participant_name': 'Customer',
                    }
                )

                now = timezone.now()
                if timestamp_ms:
                    try:
                        from datetime import datetime
                        now = datetime.fromtimestamp(timestamp_ms / 1000.0, tz=timezone.utc)
                    except Exception:
                        pass

                DirectMessage.objects.get_or_create(
                    thread=thread,
                    external_message_id=mid,
                    defaults={
                        'sender_type': 'CUSTOMER' if is_incoming else 'BUSINESS',
                        'sender_id': sender_id,
                        'sender_name': 'Customer' if is_incoming else (conn.account_name or 'Business'),
                        'text': text,
                        'media_url': media_url,
                        'media_type': 'image' if media_url else 'text',
                        'timestamp': now,
                        'is_read': not is_incoming,
                        'delivery_status': 'DELIVERED',
                    }
                )

                thread.last_message_text = text or ('[Image]' if media_url else '')
                thread.last_message_at = now
                if is_incoming:
                    thread.unread_count += 1
                thread.save(update_fields=['last_message_text', 'last_message_at', 'unread_count', 'updated_at'])

        return HttpResponse('EVENT_RECEIVED', status=200)


class PostCommentsView(APIView):
    """
    Fetches comments for an Instagram/Facebook post and allows replying to comments.
    """
    permission_classes = [IsAuthenticated, IsDigitalMarketing]

    def get(self, request, platform, post_id):
        platform_upper = platform.upper()
        conn = SocialAccountConnection.objects.filter(
            user=request.user, platform=platform_upper, is_active=True
        ).first()

        if not conn:
            return Response({'error': f"No connected {platform} account found."}, status=status.HTTP_400_BAD_REQUEST)

        token = (conn.metadata or {}).get('page_access_token') or conn.get_access_token()
        try:
            comments = MetaService.fetch_media_comments(token, post_id, platform=platform_upper)
            return Response({'comments': comments, 'count': len(comments)}, status=status.HTTP_200_OK)
        except ValueError as ve:
            return Response({
                'comments': [],
                'count': 0,
                'permission_required': True,
                'permission_error': str(ve),
            }, status=status.HTTP_200_OK)
        except Exception as exc:
            logger.exception("Failed to fetch comments for post %s: %s", post_id, exc)
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def post(self, request, platform, post_id):
        platform_upper = platform.upper()
        conn = SocialAccountConnection.objects.filter(
            user=request.user, platform=platform_upper, is_active=True
        ).first()

        if not conn:
            return Response({'error': f"No connected {platform} account found."}, status=status.HTTP_400_BAD_REQUEST)

        comment_id = request.data.get('comment_id', '').strip()
        is_media = (not comment_id or comment_id == post_id)
        target_id = post_id if is_media else comment_id
        message = request.data.get('message', '').strip()

        if not message:
            return Response({'error': 'Message text is required.'}, status=status.HTTP_400_BAD_REQUEST)

        token = (conn.metadata or {}).get('page_access_token') or conn.get_access_token()
        try:
            res = MetaService.reply_to_comment(token, target_id, message, platform=platform_upper, is_media=is_media)
            return Response({
                'success': True,
                'detail': 'Comment published successfully.' if is_media else 'Reply published successfully.',
                'result': res,
            }, status=status.HTTP_201_CREATED)
        except ValueError as ve:
            return Response({'error': str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as exc:
            logger.exception("Failed to reply to comment %s: %s", target_id, exc)
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


