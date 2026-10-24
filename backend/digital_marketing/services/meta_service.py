import os
import json
import logging
import urllib.parse
import urllib.request
import urllib.error
from django.conf import settings
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired

logger = logging.getLogger(__name__)

GRAPH_API_VERSION = 'v19.0'
GRAPH_BASE_URL = f'https://graph.facebook.com/{GRAPH_API_VERSION}'


def _http_request(url: str, method: str = 'GET', headers: dict = None, data: dict = None, params: dict = None) -> dict:
    if params:
        query_string = urllib.parse.urlencode(params)
        url = f"{url}?{query_string}" if '?' not in url else f"{url}&{query_string}"

    headers = headers.copy() if headers else {}
    body_bytes = None
    if data is not None:
        if headers.get('Content-Type') == 'application/json':
            body_bytes = json.dumps(data).encode('utf-8')
        else:
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            body_bytes = urllib.parse.urlencode(data).encode('utf-8')

    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode('utf-8')
            res = json.loads(content) if content else {}
            res['status_code'] = resp.status
            return res
    except urllib.error.HTTPError as err:
        err_body = err.read().decode('utf-8') if err.fp else ''
        try:
            err_json = json.loads(err_body)
        except Exception:
            err_json = {'error': {'message': err_body or err.reason}}
        err_json['status_code'] = err.code
        return err_json
    except Exception as exc:
        return {'error': {'message': str(exc)}, 'status_code': 500}


class MetaService:
    """
    Handles official Meta Graph API integrations for:
    1. Instagram Professional Accounts (Instagram Graph API)
    2. Facebook Pages
    3. Meta Marketing API (Ads & Insights)
    """

    STATE_MAX_AGE = 600  # 10 minutes
    STATE_SALT = 'meta_oauth_state'

    @classmethod
    def get_redirect_uri(cls, platform: str = 'INSTAGRAM', request=None, custom_redirect_uri: str = None) -> str:
        """
        Determines the appropriate OAuth redirect URI.
        Priority:
        1. Valid custom_redirect_uri from frontend request query param
        2. Extracted origin from request Origin / Referer header (preserves current domain)
        3. Environment variable (META_FACEBOOK_REDIRECT_URI / META_INSTAGRAM_REDIRECT_URI / META_REDIRECT_URI)
        4. Fallback to settings.FRONTEND_URL
        """
        # 1. Custom redirect URI (e.g. sent by frontend from window.location.origin)
        if custom_redirect_uri and isinstance(custom_redirect_uri, str):
            custom_uri = custom_redirect_uri.strip()
            try:
                parsed = urllib.parse.urlparse(custom_uri)
                if parsed.scheme in ('http', 'https') and parsed.netloc:
                    host = parsed.netloc.split(':')[0].lower()
                    allowed_hosts = [h.strip().lower() for h in getattr(settings, 'ALLOWED_HOSTS', []) if h.strip()]
                    cors_origins = [
                        urllib.parse.urlparse(o).netloc.split(':')[0].lower()
                        for o in getattr(settings, 'CORS_ALLOWED_ORIGINS', []) if o
                    ]
                    if (
                        host in ('localhost', '127.0.0.1')
                        or host in allowed_hosts
                        or host in cors_origins
                        or host == 'marketinteldbapp.hikasimat.com'
                        or host.endswith('.hikasimat.com')
                    ):
                        return custom_uri
            except Exception:
                pass

        # 2. Extract origin from request headers (works whether client is localhost or production domain)
        if request:
            origin = request.headers.get('Origin') or request.META.get('HTTP_ORIGIN')
            if not origin:
                referer = request.headers.get('Referer') or request.META.get('HTTP_REFERER')
                if referer:
                    try:
                        p = urllib.parse.urlparse(referer)
                        if p.scheme and p.netloc:
                            origin = f"{p.scheme}://{p.netloc}"
                    except Exception:
                        pass
            if origin:
                clean_origin = origin.rstrip('/')
                if platform == 'FACEBOOK':
                    return f"{clean_origin}/digital-marketing/facebook"
                elif platform == 'INSTAGRAM':
                    return f"{clean_origin}/digital-marketing/instagram"
                elif platform == 'META_ADS':
                    return f"{clean_origin}/digital-marketing/ads"

        # 3. Explicit environment variable overrides
        from dotenv import load_dotenv
        load_dotenv(override=True)
        if platform == 'FACEBOOK':
            env_uri = os.getenv('META_FACEBOOK_REDIRECT_URI', '').strip()
            if env_uri:
                return env_uri
        elif platform == 'INSTAGRAM':
            env_uri = os.getenv('META_INSTAGRAM_REDIRECT_URI', '').strip() or os.getenv('META_REDIRECT_URI', '').strip()
            if env_uri:
                return env_uri

        # 4. Fallback to settings.FRONTEND_URL
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:5173').rstrip('/')
        if platform == 'FACEBOOK':
            return f"{frontend_url}/digital-marketing/facebook"
        elif platform == 'INSTAGRAM':
            return f"{frontend_url}/digital-marketing/instagram"
        return f"{frontend_url}/digital-marketing/instagram"

    @classmethod
    def get_config(cls, platform: str = 'INSTAGRAM', request=None, custom_redirect_uri: str = None):
        """Returns configured Meta credentials or None if missing."""
        from dotenv import load_dotenv
        load_dotenv(override=True)
        app_id = os.getenv('META_APP_ID', '').strip()
        app_secret = os.getenv('META_APP_SECRET', '').strip()
        redirect_uri = cls.get_redirect_uri(platform, request=request, custom_redirect_uri=custom_redirect_uri)
        return {
            'app_id': app_id,
            'app_secret': app_secret,
            'redirect_uri': redirect_uri,
            'is_configured': bool(app_id and app_secret),
        }

    @classmethod
    def generate_auth_url(cls, user_id: int, platform: str = 'INSTAGRAM', redirect_uri: str = None) -> tuple:
        """
        Generates OAuth authorization URL with signed state preventing CSRF.
        platform can be: 'INSTAGRAM', 'FACEBOOK', or 'META_ADS'.
        The exact redirect_uri is bound into the signed state to guarantee exact
        match during the token exchange step.
        """
        cfg = cls.get_config(platform=platform)
        if not cfg['is_configured']:
            raise ValueError(
                "Meta App credentials not configured. Please set META_APP_ID and META_APP_SECRET in the environment."
            )

        effective_redirect_uri = redirect_uri or cfg['redirect_uri']

        signer = TimestampSigner(salt=cls.STATE_SALT)
        payload = json.dumps({
            'user_id': user_id,
            'platform': platform,
            'redirect_uri': effective_redirect_uri,
        })
        signed_state = signer.sign(payload)

        if platform == 'INSTAGRAM':
            default_scopes = [
                'instagram_basic',
                'instagram_content_publish',
                'instagram_manage_messages',
                'instagram_manage_comments',
                'pages_show_list',
                'pages_read_engagement',
                'business_management',
            ]
            env_scopes = os.getenv('META_INSTAGRAM_SCOPES', '')
            scopes = [s.strip() for s in env_scopes.split(',') if s.strip()] if env_scopes else default_scopes
        elif platform == 'FACEBOOK':
            default_scopes = [
                'pages_show_list',
                'pages_read_engagement',
                'pages_manage_posts',
                'pages_messaging',
                'business_management',
            ]
            env_scopes = os.getenv('META_FACEBOOK_SCOPES', '')
            scopes = [s.strip() for s in env_scopes.split(',') if s.strip()] if env_scopes else default_scopes
        elif platform == 'META_ADS':
            scopes = [
                'ads_read',
            ]
        else:
            scopes = ['pages_show_list', 'instagram_basic']

        params = {
            'client_id': cfg['app_id'],
            'redirect_uri': effective_redirect_uri,
            'scope': ','.join(scopes),
            'response_type': 'code',
            'state': signed_state,
            'auth_type': 'rerequest',
        }
        url = f"https://www.facebook.com/{GRAPH_API_VERSION}/dialog/oauth?{urllib.parse.urlencode(params)}"
        return url, signed_state

    @classmethod
    def get_state_payload(cls, state: str, user_id: int) -> dict:
        """Verifies signed state token matches current user and returns payload dict or None."""
        if not state:
            return None
        signer = TimestampSigner(salt=cls.STATE_SALT)
        try:
            unsigned = signer.unsign(state, max_age=cls.STATE_MAX_AGE)
            data = json.loads(unsigned)
            if data.get('user_id') == user_id:
                return data
            return None
        except (BadSignature, SignatureExpired, Exception) as exc:
            logger.warning("Meta OAuth state verification failed: %s", exc)
            return None

    @classmethod
    def verify_state(cls, state: str, user_id: int) -> bool:
        """Verifies signed state token matches current user and hasn't expired."""
        return cls.get_state_payload(state, user_id) is not None

    @classmethod
    def exchange_code_for_token(cls, code: str, platform: str = 'INSTAGRAM', redirect_uri: str = None) -> dict:
        """
        Exchanges authorization code for user access token and exchanges
        for a long-lived 60-day token via Graph API.
        Uses redirect_uri extracted from signed state if provided.
        """
        cfg = cls.get_config(platform=platform)
        if not cfg['is_configured']:
            raise ValueError("Meta credentials are missing.")

        effective_redirect_uri = redirect_uri or cfg['redirect_uri']

        # Step 1: Exchange code for short-lived token
        token_url = f"{GRAPH_BASE_URL}/oauth/access_token"
        params = {
            'client_id': cfg['app_id'],
            'client_secret': cfg['app_secret'],
            'redirect_uri': effective_redirect_uri,
            'code': code,
        }
        res = _http_request(token_url, method='GET', params=params)
        if res.get('status_code', 200) != 200:
            error_info = res.get('error', {})
            raise ValueError(error_info.get('message', 'Failed to exchange authorization code with Meta.'))

        short_token = res.get('access_token')

        # Step 2: Exchange for long-lived access token
        ll_params = {
            'grant_type': 'fb_exchange_token',
            'client_id': cfg['app_id'],
            'client_secret': cfg['app_secret'],
            'fb_exchange_token': short_token,
        }
        ll_res = _http_request(token_url, method='GET', params=ll_params)
        if ll_res.get('status_code', 200) == 200:
            return ll_res
        return res

    @staticmethod
    def fetch_instagram_account(access_token: str) -> dict:
        """
        Finds connected Instagram Business / Creator accounts linked to authorized Facebook Pages.
        Checks both instagram_business_account and connected_instagram_account.
        """
        url = f"{GRAPH_BASE_URL}/me/accounts"
        params = {
            'fields': (
                'id,name,access_token,'
                'instagram_business_account{id,username,name,profile_picture_url,followers_count,media_count,biography},'
                'connected_instagram_account{id,username,name,profile_picture_url}'
            ),
            'access_token': access_token,
        }
        res = _http_request(url, method='GET', params=params)
        if res.get('status_code', 200) != 200:
            err = res.get('error', {})
            raise ValueError(err.get('message', 'Unable to fetch Instagram account details from Meta.'))

        user_info = _http_request(f"{GRAPH_BASE_URL}/me?fields=id,name", method='GET', params={'access_token': access_token})
        perms_info = _http_request(f"{GRAPH_BASE_URL}/me/permissions", method='GET', params={'access_token': access_token})
        print("="*60)
        print(f"[META DEBUG] Logged in User: {user_info.get('name')} (ID: {user_info.get('id')})")
        print(f"[META DEBUG] Granted Permissions: {perms_info.get('data')}")
        print(f"[META DEBUG] Accounts API response: {res}")
        print("="*60)

        pages = list(res.get('data', []))
        if not pages:
            biz_res = _http_request(f"{GRAPH_BASE_URL}/me/businesses?fields=id,name", method='GET', params={'access_token': access_token})
            print(f"[META DEBUG] Businesses API response: {biz_res}")
            for biz in biz_res.get('data', []):
                biz_id = biz.get('id')
                for ep in ['owned_pages', 'client_pages']:
                    bp_res = _http_request(
                        f"{GRAPH_BASE_URL}/{biz_id}/{ep}",
                        method='GET',
                        params={
                            'fields': (
                                'id,name,access_token,'
                                'instagram_business_account{id,username,name,profile_picture_url,followers_count,media_count,biography},'
                                'connected_instagram_account{id,username,name,profile_picture_url}'
                            ),
                            'access_token': access_token,
                        }
                    )
                    print(f"[META DEBUG] Business {biz_id} {ep}: {bp_res}")
                    if bp_res.get('data'):
                        pages.extend(bp_res.get('data'))

        logger.info("Meta pages discovered during Instagram account fetch: %d pages", len(pages))

        for page in pages:
            page_id = page.get('id')
            page_token = page.get('access_token') or access_token
            ig_account = page.get('instagram_business_account')
            conn_ig = page.get('connected_instagram_account')

            # Fallback: query page node directly with page access token
            if not ig_account and not conn_ig and page_id:
                page_node = _http_request(
                    f"{GRAPH_BASE_URL}/{page_id}",
                    method='GET',
                    params={
                        'fields': (
                            'instagram_business_account{id,username,name,profile_picture_url,followers_count,media_count,biography},'
                            'connected_instagram_account{id,username,name,profile_picture_url}'
                        ),
                        'access_token': page_token,
                    }
                )
                if page_node.get('status_code', 200) == 200:
                    ig_account = page_node.get('instagram_business_account')
                    conn_ig = page_node.get('connected_instagram_account')

            # 1. Try official instagram_business_account
            if ig_account:
                return {
                    'page_id': page_id,
                    'page_name': page.get('name'),
                    'page_access_token': page.get('access_token'),
                    'ig_id': ig_account.get('id'),
                    'username': ig_account.get('username'),
                    'name': ig_account.get('name') or ig_account.get('username'),
                    'profile_picture_url': ig_account.get('profile_picture_url', ''),
                    'followers_count': ig_account.get('followers_count', 0),
                    'media_count': ig_account.get('media_count', 0),
                    'biography': ig_account.get('biography', ''),
                }

            # 2. Try connected_instagram_account (from Page Settings -> Linked Accounts)
            if conn_ig:
                ig_id = conn_ig.get('id')
                username = conn_ig.get('username')
                name = conn_ig.get('name') or username
                profile_pic = conn_ig.get('profile_picture_url', '')

                # If basic info is missing, attempt to fetch node directly using page access token
                if not username and ig_id:
                    page_token = page.get('access_token') or access_token
                    ig_node = _http_request(
                        f"{GRAPH_BASE_URL}/{ig_id}",
                        method='GET',
                        params={
                            'fields': 'id,username,name,profile_picture_url',
                            'access_token': page_token,
                        }
                    )
                    if ig_node.get('status_code', 200) == 200:
                        username = ig_node.get('username') or username
                        name = ig_node.get('name') or name or username
                        profile_pic = ig_node.get('profile_picture_url') or profile_pic

                return {
                    'page_id': page.get('id'),
                    'page_name': page.get('name'),
                    'page_access_token': page.get('access_token'),
                    'ig_id': ig_id,
                    'username': username or 'instagram_user',
                    'name': name or username or 'Instagram User',
                    'profile_picture_url': profile_pic,
                    'followers_count': 0,
                    'media_count': 0,
                    'biography': '',
                }

        page_names = [p.get('name') for p in pages if p.get('name')]
        if page_names:
            page_list_str = ", ".join(f"'{name}'" for name in page_names)
            raise ValueError(
                f"Found Facebook Page(s) {page_list_str}, but Meta reports that the linked Instagram account is not yet switched to a Professional (Business or Creator) account. "
                "Please open Instagram, go to Settings -> Account type and tools -> 'Switch to professional account', then try connecting again."
            )

        granted = [p.get('permission') for p in perms_info.get('data', []) if p.get('status') == 'granted']
        user_name = user_info.get('name', 'Unknown')
        raise ValueError(
            f"No Facebook Pages returned for logged-in user '{user_name}'. "
            f"Granted permissions: {granted}. "
            "Please ensure your Facebook user has admin access to the Market Intel DB Page, "
            "or that the page is selected in Facebook permissions."
        )

    @staticmethod
    def fetch_instagram_media(access_token: str, ig_user_id: str) -> list:
        """Fetches recent media items and insights from Instagram Graph API."""
        url = f"{GRAPH_BASE_URL}/{ig_user_id}/media"
        params = {
            'fields': 'id,caption,media_type,media_url,permalink,timestamp,like_count,comments_count',
            'limit': 15,
            'access_token': access_token,
        }
        res = _http_request(url, method='GET', params=params)
        if res.get('status_code', 200) != 200:
            return []
        return res.get('data', [])

    @staticmethod
    def upload_temporary_media(file_obj) -> str:
        """
        Uploads a local image file to a temporary public HTTPS host so Meta Graph API
        can download and publish it when running in local development mode.
        Supports both requests library and Python urllib standard library.
        """
        import os
        import re
        import json
        try:
            file_obj.seek(0)
            file_bytes = file_obj.read()
            raw_name = getattr(file_obj, 'name', 'upload.png')
            file_name = os.path.basename(raw_name) or 'upload.png'
            content_type = getattr(file_obj, 'content_type', 'image/png')
            file_obj.seek(0)

            logger.info("Uploading local image '%s' (%d bytes) to temporary public host for Meta API...", file_name, len(file_bytes))

            # 1. Try requests if installed
            try:
                import requests
                res = requests.post(
                    'https://tmpfiles.org/api/v1/upload',
                    files={'file': (file_name, file_bytes, content_type)},
                    timeout=25
                )
                if res.status_code == 200:
                    data = res.json()
                    raw_url = data.get('data', {}).get('url', '')
                    if raw_url:
                        dl_url = raw_url.replace('tmpfiles.org/', 'tmpfiles.org/dl/')
                        try:
                            page_res = requests.get(dl_url, timeout=15)
                            match = re.search(r'id=["\']img_preview["\']\s+src=["\']([^"\']+)["\']', page_res.text)
                            if not match:
                                match = re.search(r'<a class=["\']download["\']\s+href=["\']([^"\']+)["\']', page_res.text)
                            if match:
                                direct_url = match.group(1)
                                logger.info("Successfully generated direct temporary image URL for Meta (via requests): %s", direct_url)
                                return direct_url
                        except Exception as ex:
                            logger.warning("Could not parse direct image from landing page, falling back to dl_url: %s", ex)
                        return dl_url
                else:
                    logger.warning("tmpfiles.org upload returned status %d: %s", res.status_code, res.text)
            except ImportError:
                pass

            # 2. Pure Python standard library fallback (urllib)
            import uuid
            import urllib.request
            boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
            header = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode('utf-8')
            footer = f"\r\n--{boundary}--\r\n".encode('utf-8')
            body = header + file_bytes + footer

            req = urllib.request.Request(
                'https://tmpfiles.org/api/v1/upload',
                data=body,
                headers={
                    'Content-Type': f'multipart/form-data; boundary={boundary}',
                    'User-Agent': 'MarketIntelDB/1.0'
                },
                method='POST'
            )
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                raw_url = data.get('data', {}).get('url', '')
                if raw_url:
                    dl_url = raw_url.replace('tmpfiles.org/', 'tmpfiles.org/dl/')
                    req_page = urllib.request.Request(dl_url, headers={'User-Agent': 'MarketIntelDB/1.0'})
                    with urllib.request.urlopen(req_page, timeout=15) as page_resp:
                        html = page_resp.read().decode('utf-8', errors='ignore')
                        match = re.search(r'id=["\']img_preview["\']\s+src=["\']([^"\']+)["\']', html)
                        if not match:
                            match = re.search(r'<a class=["\']download["\']\s+href=["\']([^"\']+)["\']', html)
                        if match:
                            direct_url = match.group(1)
                            logger.info("Successfully generated direct temporary image URL for Meta (via urllib): %s", direct_url)
                            return direct_url
                    return dl_url

        except Exception as e:
            logger.warning("Failed to upload temporary media for Meta: %s", e)
            try:
                file_obj.seek(0)
            except Exception:
                pass
        return ''

    @staticmethod
    def publish_instagram_photo(access_token: str, ig_user_id: str, image_url: str, caption: str) -> dict:
        """
        Official Instagram Content Publishing API flow:
        Step 1: Create media container
        Step 2: Check status if asynchronous
        Step 3: Publish media container
        """
        import time

        # Step 1: Create container
        container_url = f"{GRAPH_BASE_URL}/{ig_user_id}/media"
        c_payload = {
            'image_url': image_url,
            'caption': caption,
            'access_token': access_token,
        }
        c_res = _http_request(container_url, method='POST', data=c_payload)
        if c_res.get('status_code', 200) != 200:
            err = c_res.get('error', {})
            raise ValueError(err.get('message', 'Failed to create Instagram media container.'))

        creation_id = c_res.get('id')

        # Step 2: Ensure container is ready for publishing
        status_url = f"{GRAPH_BASE_URL}/{creation_id}"
        for _ in range(5):
            st_res = _http_request(status_url, method='GET', params={'fields': 'status_code', 'access_token': access_token})
            c_status = st_res.get('status_code')
            if not c_status or c_status == 'FINISHED':
                break
            if c_status == 'ERROR':
                raise ValueError("Instagram media container processing failed.")
            if c_status == 'IN_PROGRESS':
                time.sleep(1.5)

        # Step 3: Publish container
        publish_url = f"{GRAPH_BASE_URL}/{ig_user_id}/media_publish"
        p_payload = {
            'creation_id': creation_id,
            'access_token': access_token,
        }
        p_res = _http_request(publish_url, method='POST', data=p_payload)
        if p_res.get('status_code', 200) != 200:
            err = p_res.get('error', {})
            raise ValueError(err.get('message', 'Failed to publish Instagram post.'))

        return p_res

    @staticmethod
    def fetch_facebook_pages(access_token: str) -> list:
        """Fetches authorized Facebook Pages with page-level tokens."""
        url = f"{GRAPH_BASE_URL}/me/accounts"
        params = {
            'fields': 'id,name,category,tasks,access_token,fan_count,picture{url}',
            'access_token': access_token,
        }
        res = _http_request(url, method='GET', params=params)
        pages = list(res.get('data', []))
        if not pages:
            biz_res = _http_request(f"{GRAPH_BASE_URL}/me/businesses?fields=id,name", method='GET', params={'access_token': access_token})
            for biz in biz_res.get('data', []):
                biz_id = biz.get('id')
                for ep in ['owned_pages', 'client_pages']:
                    bp_res = _http_request(
                        f"{GRAPH_BASE_URL}/{biz_id}/{ep}",
                        method='GET',
                        params={
                            'fields': 'id,name,category,tasks,access_token,fan_count,picture{url}',
                            'access_token': access_token,
                        }
                    )
                    if bp_res.get('data'):
                        pages.extend(bp_res.get('data'))
        return pages

    @staticmethod
    def publish_facebook_page_post(page_access_token: str, page_id: str, message: str, link: str = '', image_url: str = '') -> dict:
        """Publishes post or photo to authorized Facebook Page."""
        if image_url:
            url = f"{GRAPH_BASE_URL}/{page_id}/photos"
            payload = {
                'url': image_url,
                'caption': message,
                'access_token': page_access_token,
            }
        else:
            url = f"{GRAPH_BASE_URL}/{page_id}/feed"
            payload = {
                'message': message,
                'access_token': page_access_token,
            }
            if link:
                payload['link'] = link

        res = _http_request(url, method='POST', data=payload)
        if res.get('status_code', 200) != 200:
            err = res.get('error', {})
            error_message = err.get('message', 'Failed to publish post to Facebook Page.')
            if 'Error validating access token' in error_message or err.get('code') == 190:
                error_message = (
                    "Your Facebook session has expired or was invalidated when permissions changed. "
                    "Please click 'Disconnect Account' on this page and reconnect to renew your authorization."
                )
            elif 'pages_manage_posts' in error_message:
                error_message = (
                    "Meta requires 'pages_manage_posts' permission to publish posts to your Facebook Page. "
                    "In developers.facebook.com under your app, add 'pages_manage_posts' to Use Cases / Permissions, "
                    "then Disconnect and Reconnect Facebook."
                )
            raise ValueError(error_message)
        return res

    @staticmethod
    def fetch_facebook_page_posts(page_access_token: str, page_id: str) -> list:
        """Fetches recent posts, attachments, and reaction counts for authorized Facebook Page."""
        url = f"{GRAPH_BASE_URL}/{page_id}/published_posts"
        params = {
            'fields': 'id,message,created_time,permalink_url,shares,attachments{media,target,title,type,url}',
            'limit': 25,
            'access_token': page_access_token,
        }
        res = _http_request(url, method='GET', params=params)
        if res.get('status_code', 200) != 200:
            return []
        posts = res.get('data', [])
        formatted = []
        for p in posts:
            reactions_count = p.get('reactions', {}).get('summary', {}).get('total_count', 0)
            comments_count = p.get('comments', {}).get('summary', {}).get('total_count', 0)
            shares_count = p.get('shares', {}).get('count', 0)
            attachments_data = p.get('attachments', {}).get('data', [])
            image_url = ''
            if attachments_data:
                image_url = attachments_data[0].get('media', {}).get('image', {}).get('src', '')
            formatted.append({
                'id': p.get('id'),
                'message': p.get('message', ''),
                'created_time': p.get('created_time'),
                'permalink_url': p.get('permalink_url', ''),
                'media_url': image_url,
                'reactions_count': reactions_count,
                'comments_count': comments_count,
                'shares_count': shares_count,
            })
        return formatted

    @staticmethod
    def fetch_meta_ad_campaigns(access_token: str, ad_account_id: str = None) -> list:
        """
        Fetches ad accounts and active/paused campaigns via Meta Marketing API.
        Does not mutate campaigns or spend funds.
        """
        if not ad_account_id:
            acc_url = f"{GRAPH_BASE_URL}/me/adaccounts"
            acc_res = _http_request(acc_url, method='GET', params={'fields': 'id,name,account_status', 'access_token': access_token})
            if acc_res.get('status_code', 200) != 200:
                return []
            accounts = acc_res.get('data', [])
            if not accounts:
                return []
            ad_account_id = accounts[0].get('id')

        camp_url = f"{GRAPH_BASE_URL}/{ad_account_id}/campaigns"
        camp_params = {
            'fields': 'id,name,status,objective,daily_budget,insights{spend,impressions,reach,clicks,cpc,ctr,actions}',
            'limit': 20,
            'access_token': access_token,
        }
        res = _http_request(camp_url, method='GET', params=camp_params)
        if res.get('status_code', 200) != 200:
            return []
        data = res.get('data', [])
        results = []
        for c in data:
            insights = c.get('insights', {}).get('data', [{}])[0] if c.get('insights', {}).get('data') else {}
            results.append({
                'id': c.get('id'),
                'name': c.get('name'),
                'status': c.get('status'),
                'objective': c.get('objective'),
                'daily_budget': c.get('daily_budget'),
                'spend': insights.get('spend', '0.00'),
                'impressions': int(insights.get('impressions', 0)),
                'reach': int(insights.get('reach', 0)),
                'clicks': int(insights.get('clicks', 0)),
                'cpc': insights.get('cpc', '0.0000'),
                'ctr': insights.get('ctr', '0.000'),
            })
        return results

    @staticmethod
    def send_direct_message(page_access_token: str, recipient_id: str, text: str, media_url: str = '') -> dict:
        """
        Sends an outbound direct message or image to a customer via Meta Send API.
        Works for both Facebook Messenger PSID and Instagram IGSID.
        """
        url = f"{GRAPH_BASE_URL}/me/messages"
        params = {'access_token': page_access_token}

        message_payload = {}
        if text:
            message_payload['text'] = text
        if media_url:
            message_payload['attachment'] = {
                'type': 'image',
                'payload': {'url': media_url, 'is_reusable': True}
            }

        body = {
            'recipient': {'id': recipient_id},
            'message': message_payload,
            'messaging_type': 'RESPONSE',
        }
        headers = {'Content-Type': 'application/json'}
        res = _http_request(url, method='POST', headers=headers, data=body, params=params)
        if res.get('status_code', 200) != 200:
            err = res.get('error', {})
            error_message = err.get('message', 'Failed to send message.')
            code = err.get('code')
            subcode = err.get('error_subcode')
            if code == 10 or subcode == 2018001 or '24' in error_message:
                error_message = (
                    "Meta standard 24-hour customer window has closed. "
                    "You can only reply to a user within 24 hours of their last incoming message."
                )
            elif 'permission' in error_message.lower():
                error_message = (
                    "Missing messaging permission (pages_messaging or instagram_manage_messages). "
                    "Please ensure messaging permissions are enabled in your Meta App."
                )
            raise ValueError(error_message)
        return res

    @staticmethod
    def fetch_page_conversations(access_token: str, page_id: str, platform: str = 'FACEBOOK') -> list:
        """
        Fetches active conversation threads from Facebook Page or Instagram Business Account.
        """
        url = f"{GRAPH_BASE_URL}/{page_id}/conversations"
        params = {
            'fields': 'id,updated_time,participants,senders,unread_count,snippet,messages{id,message,created_time,from,attachments}',
            'limit': 25,
            'access_token': access_token,
        }
        if platform == 'INSTAGRAM':
            params['platform'] = 'instagram'

        res = _http_request(url, method='GET', params=params)
        if res.get('status_code', 200) != 200:
            err = res.get('error', {})
            msg = err.get('message', '')
            logger.warning("Failed to fetch conversations for page %s: %s", page_id, err)
            if 'instagram_manage_messages' in msg:
                raise ValueError("Missing 'instagram_manage_messages' permission. Please disconnect and reconnect Instagram.")
            elif 'pages_messaging' in msg:
                raise ValueError("Missing 'pages_messaging' permission. Please disconnect and reconnect Facebook.")
            return []
        return res.get('data', [])

    @staticmethod
    def fetch_thread_messages(access_token: str, thread_id: str) -> list:
        """
        Fetches message history within a conversation thread.
        """
        url = f"{GRAPH_BASE_URL}/{thread_id}/messages"
        params = {
            'fields': 'id,created_time,from,to,message,attachments',
            'limit': 50,
            'access_token': access_token,
        }
        res = _http_request(url, method='GET', params=params)
        if res.get('status_code', 200) != 200:
            logger.warning("Failed to fetch thread messages %s: %s", thread_id, res.get('error'))
            return []
        return res.get('data', [])

    @staticmethod
    def fetch_participant_info(access_token: str, participant_id: str, platform: str = 'FACEBOOK') -> dict:
        """
        Fetches participant name and avatar from Meta Graph API.
        """
        url = f"{GRAPH_BASE_URL}/{participant_id}"
        fields = 'first_name,last_name,name,profile_pic' if platform == 'FACEBOOK' else 'name,username,profile_pic'
        params = {
            'fields': fields,
            'access_token': access_token,
        }
        res = _http_request(url, method='GET', params=params)
        if res.get('status_code', 200) == 200:
            name = res.get('name') or f"{res.get('first_name', '')} {res.get('last_name', '')}".strip() or res.get('username') or 'Customer'
            return {
                'name': name,
                'username': res.get('username', ''),
                'avatar_url': res.get('profile_pic', ''),
            }
        return {'name': 'Customer', 'username': '', 'avatar_url': ''}

    @staticmethod
    def fetch_instagram_profile_info(access_token: str, ig_user_id: str) -> dict:
        """Fetches live follower count, following count, and media count."""
        url = f"{GRAPH_BASE_URL}/{ig_user_id}"
        params = {
            'fields': 'id,username,name,followers_count,follows_count,media_count,profile_picture_url',
            'access_token': access_token,
        }
        res = _http_request(url, method='GET', params=params)
        if res.get('status_code', 200) == 200:
            return res
        return {}

    @staticmethod
    def fetch_facebook_page_info(access_token: str, page_id: str) -> dict:
        """Fetches live page followers and fan count."""
        url = f"{GRAPH_BASE_URL}/{page_id}"
        params = {
            'fields': 'id,name,fan_count,followers_count,picture{url}',
            'access_token': access_token,
        }
        res = _http_request(url, method='GET', params=params)
        if res.get('status_code', 200) == 200:
            return res
        return {}

    @staticmethod
    def fetch_media_comments(access_token: str, media_id: str, platform: str = 'INSTAGRAM') -> list:
        """Fetches comments and replies for an Instagram or Facebook post."""
        url = f"{GRAPH_BASE_URL}/{media_id}/comments"
        if platform == 'INSTAGRAM':
            params = {
                'fields': 'id,text,timestamp,username,from,like_count,replies{id,text,timestamp,username,from,like_count}',
                'limit': 50,
                'access_token': access_token,
            }
        else:
            params = {
                'fields': 'id,message,created_time,from,like_count,comment_count',
                'limit': 50,
                'access_token': access_token,
            }

        res = _http_request(url, method='GET', params=params)
        if res.get('status_code', 200) != 200:
            err = res.get('error', {})
            logger.warning("Failed to fetch comments for media %s: %s", media_id, err)
            code = err.get('code')
            msg = err.get('message', '')
            if platform == 'INSTAGRAM' and (code in [10, 200] or 'permission' in msg.lower()):
                raise ValueError(
                    "Meta requires 'instagram_manage_comments' permission to view comments. "
                    "Please click 'Disconnect' and 'Connect Live Instagram' to grant permissions."
                )
            return []

        raw_comments = res.get('data', [])
        formatted = []
        for c in raw_comments:
            replies_data = []
            if 'replies' in c and isinstance(c['replies'], dict):
                replies_data = c['replies'].get('data', [])

            from_obj = c.get('from', {}) if isinstance(c.get('from'), dict) else {}
            username = c.get('username') or from_obj.get('username') or from_obj.get('name') or ''
            name = from_obj.get('name') or username or ('Instagram User' if platform == 'INSTAGRAM' else 'Facebook User')

            formatted_replies = []
            for r in replies_data:
                r_from = r.get('from', {}) if isinstance(r.get('from'), dict) else {}
                r_username = r.get('username') or r_from.get('username') or r_from.get('name') or ''
                r_name = r_from.get('name') or r_username or ('Instagram User' if platform == 'INSTAGRAM' else 'Facebook User')
                formatted_replies.append({
                    'id': r.get('id'),
                    'text': r.get('text') or r.get('message', ''),
                    'username': r_username or r_name,
                    'name': r_name,
                    'timestamp': r.get('timestamp') or r.get('created_time'),
                    'like_count': r.get('like_count', 0),
                })

            formatted.append({
                'id': c.get('id'),
                'text': c.get('text') or c.get('message', ''),
                'username': username or name,
                'name': name,
                'has_username': bool(c.get('username') or from_obj.get('username')),
                'timestamp': c.get('timestamp') or c.get('created_time'),
                'like_count': c.get('like_count', 0),
                'replies': formatted_replies,
            })
        return formatted

    @staticmethod
    def reply_to_comment(access_token: str, target_id: str, message: str, platform: str = 'INSTAGRAM', is_media: bool = False) -> dict:
        """Publishes a public reply to a comment or a top-level comment to a post on Instagram or Facebook."""
        if platform == 'INSTAGRAM':
            endpoint = 'comments' if is_media else 'replies'
        else:
            endpoint = 'comments'

        url = f"{GRAPH_BASE_URL}/{target_id}/{endpoint}"
        params = {'access_token': access_token}
        data = {'message': message}
        res = _http_request(url, method='POST', data=data, params=params)
        if res.get('status_code', 200) != 200:
            err = res.get('error', {})
            error_message = err.get('message', 'Failed to publish comment reply.')
            code = err.get('code')
            if 'Missing Permission' in error_message or code in [10, 100, 200] or 'permission' in error_message.lower():
                if platform == 'INSTAGRAM':
                    error_message = (
                        "Meta requires 'instagram_manage_comments' permission to see commenter names and post replies. "
                        "Please click 'Disconnect Account' on the Instagram page, then click 'Connect Live Instagram' "
                        "to grant the updated comment permissions."
                    )
                else:
                    error_message = (
                        "Meta Graph API requires App Review approval to publish comments to Facebook Page posts via API. "
                        "Please use 'View on Facebook' to reply directly on Facebook."
                    )
            raise ValueError(error_message)
        return res

