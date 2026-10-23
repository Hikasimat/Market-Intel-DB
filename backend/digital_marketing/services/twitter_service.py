import os
import json
import base64
import hashlib
import secrets
import logging
import urllib.parse
import urllib.request
import urllib.error
from django.conf import settings
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired

logger = logging.getLogger(__name__)

TWITTER_API_BASE_URL = 'https://api.twitter.com/2'
TWITTER_OAUTH_URL = 'https://twitter.com/i/oauth2/authorize'
TWITTER_TOKEN_URL = 'https://api.twitter.com/2/oauth2/token'


def _twitter_http_request(url: str, method: str = 'GET', headers: dict = None, data: dict = None, params: dict = None) -> dict:
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
            err_json = {'detail': err_body or err.reason}
        err_json['status_code'] = err.code
        return err_json
    except Exception as exc:
        return {'detail': str(exc), 'status_code': 500}


class TwitterService:
    """
    Handles official Twitter/X API v2 integration with OAuth 2.0 (PKCE):
    - Account connection and profile verification
    - Tweet publishing
    - Recent tweets & organic engagement metrics
    - API quota & rate limit reporting
    - X Ads reporting
    """

    STATE_MAX_AGE = 600  # 10 minutes
    STATE_SALT = 'twitter_oauth_state'

    @staticmethod
    def get_config():
        """Returns Twitter/X app credentials from environment."""
        client_id = os.getenv('TWITTER_CLIENT_ID', '').strip()
        client_secret = os.getenv('TWITTER_CLIENT_SECRET', '').strip()
        redirect_uri = os.getenv(
            'TWITTER_REDIRECT_URI',
            f"{settings.FRONTEND_URL}/digital-marketing/twitter"
        ).strip()
        return {
            'client_id': client_id,
            'client_secret': client_secret,
            'redirect_uri': redirect_uri,
            'is_configured': bool(client_id and client_secret),
        }

    @staticmethod
    def generate_pkce_pair():
        """Generates PKCE code_verifier and code_challenge (S256)."""
        verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(verifier.encode('utf-8')).digest()
        challenge = base64.urlsafe_b64encode(digest).decode('utf-8').replace('=', '')
        return verifier, challenge

    @classmethod
    def generate_auth_url(cls, user_id: int) -> tuple:
        """
        Generates OAuth 2.0 authorization URL with PKCE and signed state.
        Returns (url, state, code_verifier).
        """
        cfg = cls.get_config()
        if not cfg['is_configured']:
            raise ValueError(
                "Twitter/X API credentials not configured. Please set TWITTER_CLIENT_ID and TWITTER_CLIENT_SECRET in the environment."
            )

        code_verifier, code_challenge = cls.generate_pkce_pair()

        signer = TimestampSigner(salt=cls.STATE_SALT)
        payload = json.dumps({'user_id': user_id, 'code_verifier': code_verifier})
        signed_state = signer.sign(payload)

        scopes = ['tweet.read', 'tweet.write', 'users.read', 'offline.access']

        params = {
            'response_type': 'code',
            'client_id': cfg['client_id'],
            'redirect_uri': cfg['redirect_uri'],
            'scope': ' '.join(scopes),
            'state': signed_state,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
        }
        url = f"{TWITTER_OAUTH_URL}?{urllib.parse.urlencode(params)}"
        return url, signed_state, code_verifier

    @classmethod
    def verify_state_and_extract_verifier(cls, state: str, user_id: int) -> tuple:
        """
        Verifies signed state token and extracts the bound code_verifier.
        Returns (is_valid, code_verifier).
        """
        if not state:
            return False, ''
        signer = TimestampSigner(salt=cls.STATE_SALT)
        try:
            unsigned = signer.unsign(state, max_age=cls.STATE_MAX_AGE)
            data = json.loads(unsigned)
            if data.get('user_id') == user_id:
                return True, data.get('code_verifier', '')
            return False, ''
        except (BadSignature, SignatureExpired, Exception) as exc:
            logger.warning("Twitter OAuth state verification failed: %s", exc)
            return False, ''

    @classmethod
    def exchange_code_for_tokens(cls, code: str, code_verifier: str) -> dict:
        """Exchanges authorization code and PKCE code_verifier for X access/refresh tokens."""
        cfg = cls.get_config()
        if not cfg['is_configured']:
            raise ValueError("Twitter/X credentials are missing.")

        auth_header = base64.b64encode(f"{cfg['client_id']}:{cfg['client_secret']}".encode('utf-8')).decode('utf-8')
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f"Basic {auth_header}",
        }
        data = {
            'code': code,
            'grant_type': 'authorization_code',
            'client_id': cfg['client_id'],
            'redirect_uri': cfg['redirect_uri'],
            'code_verifier': code_verifier,
        }

        res = _twitter_http_request(TWITTER_TOKEN_URL, method='POST', headers=headers, data=data)
        if res.get('status_code', 200) != 200:
            error_desc = res.get('error_description') or res.get('error') or res.get('detail') or 'Token exchange with Twitter failed.'
            raise ValueError(error_desc)
        return res

    @staticmethod
    def fetch_user_profile(access_token: str) -> dict:
        """Fetches authorized user profile and public metrics from X API v2."""
        url = f"{TWITTER_API_BASE_URL}/users/me"
        headers = {'Authorization': f'Bearer {access_token}'}
        params = {
            'user.fields': 'profile_image_url,public_metrics,description,verified,created_at'
        }
        res = _twitter_http_request(url, method='GET', headers=headers, params=params)
        if res.get('status_code', 200) != 200:
            if res.get('status_code') == 429:
                raise ValueError("Twitter API rate limit reached. Please wait before retrying.")
            detail = res.get('detail') or res.get('title') or 'Unable to fetch X profile.'
            raise ValueError(detail)

        data = res.get('data', {})
        metrics = data.get('public_metrics', {})
        return {
            'id': data.get('id'),
            'name': data.get('name'),
            'username': data.get('username'),
            'description': data.get('description', ''),
            'profile_image_url': data.get('profile_image_url', ''),
            'followers_count': metrics.get('followers_count', 0),
            'following_count': metrics.get('following_count', 0),
            'tweet_count': metrics.get('tweet_count', 0),
            'listed_count': metrics.get('listed_count', 0),
        }

    @staticmethod
    def post_tweet(access_token: str, text: str) -> dict:
        """Publishes a tweet using official X API v2."""
        if not text or not text.strip():
            raise ValueError("Tweet content cannot be empty.")
        if len(text.strip()) > 280:
            raise ValueError("Tweet exceeds maximum allowed length of 280 characters.")

        url = f"{TWITTER_API_BASE_URL}/tweets"
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }
        payload = {'text': text.strip()}

        res = _twitter_http_request(url, method='POST', headers=headers, data=payload)
        if res.get('status_code', 200) not in (200, 201):
            if res.get('status_code') == 429:
                raise ValueError("X API rate limit reached. Monthly or daily post quota may have been exceeded on this tier.")
            detail = res.get('detail') or res.get('title') or 'Failed to post tweet to X.'
            raise ValueError(detail)

        return res.get('data', {})

    @staticmethod
    def fetch_user_tweets(access_token: str, twitter_user_id: str) -> list:
        """Fetches recent tweets and metrics from X API v2."""
        url = f"{TWITTER_API_BASE_URL}/users/{twitter_user_id}/tweets"
        headers = {'Authorization': f'Bearer {access_token}'}
        params = {
            'tweet.fields': 'created_at,public_metrics,text',
            'max_results': 10,
        }
        res = _twitter_http_request(url, method='GET', headers=headers, params=params)
        if res.get('status_code', 200) != 200:
            return []
        tweets = res.get('data', [])
        formatted = []
        for t in tweets:
            metrics = t.get('public_metrics', {})
            formatted.append({
                'id': t.get('id'),
                'text': t.get('text'),
                'created_at': t.get('created_at'),
                'retweet_count': metrics.get('retweet_count', 0),
                'reply_count': metrics.get('reply_count', 0),
                'like_count': metrics.get('like_count', 0),
                'impression_count': metrics.get('impression_count', 0),
            })
        return formatted

    @staticmethod
    def fetch_x_ads_campaigns(access_token: str, account_id: str = None) -> list:
        """
        Fetches X Ads campaigns if authorized on Twitter Developer portal.
        Returns empty list or raises informative message if Ads API product is not activated.
        """
        url = f"https://ads-api.twitter.com/12/accounts/{account_id}/campaigns" if account_id else "https://ads-api.twitter.com/12/accounts"
        headers = {'Authorization': f'Bearer {access_token}'}
        try:
            res = _twitter_http_request(url, method='GET', headers=headers)
            if res.get('status_code', 200) == 200:
                return res.get('data', [])
        except Exception:
            pass
        return []
