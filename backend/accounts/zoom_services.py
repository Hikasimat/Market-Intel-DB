"""Zoom OAuth authorization + Zoom Meeting creation.

Isolated credential row, signed state salt, encrypted storage, and token refresh.
"""
import base64
import hashlib
import json
import logging
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.utils import timezone

import utils.encryption as encryption

logger = logging.getLogger(__name__)

ZOOM_AUTH_URL = "https://zoom.us/oauth/authorize"
ZOOM_TOKEN_URL = "https://zoom.us/oauth/token"
ZOOM_REVOKE_URL = "https://zoom.us/oauth/revoke"
ZOOM_API_BASE = "https://api.zoom.us/v2"
DEFAULT_MEETING_DURATION_MINUTES = 30


class ZoomError(Exception):
    """Base exception for Zoom integration errors."""


class ZoomNotConnected(ZoomError):
    pass


class ZoomAuthError(ZoomError):
    """Consent revoked/expired or permission missing."""


class ZoomAPIError(ZoomError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def _zoom_redirect_uri():
    return getattr(
        settings, 'ZOOM_OAUTH_REDIRECT_URI',
        'http://127.0.0.1:5173/auth/zoom/callback'
    )


def get_zoom_credentials(user):
    """Retrieve active Zoom credentials for a user."""
    if not user or not user.is_authenticated:
        return None
    from .models import ZoomCredentials
    creds = ZoomCredentials.objects.filter(user=user, is_active=True).first()
    if creds and (creds.refresh_token_encrypted or creds.access_token_encrypted):
        return creds
    return None


class ZoomOAuthService:
    STATE_MAX_AGE = 600
    STATE_SALT = 'zoom-oauth-state'
    SCOPES = ['meeting:write', 'meeting:read', 'user:read']

    @classmethod
    def is_configured(cls):
        return bool(
            getattr(settings, 'ZOOM_CLIENT_ID', '').strip() and
            getattr(settings, 'ZOOM_CLIENT_SECRET', '').strip()
        )

    @classmethod
    def generate_authorization_url(cls, user_id):
        if not cls.is_configured():
            raise ValueError("Zoom OAuth credentials are not configured on the server.")
        raw_state = f"{user_id}:{secrets.token_urlsafe(24)}"
        signed_state = TimestampSigner(salt=cls.STATE_SALT).sign(raw_state)
        params = {
            'response_type': 'code',
            'client_id': settings.ZOOM_CLIENT_ID,
            'redirect_uri': _zoom_redirect_uri(),
            'state': signed_state,
        }
        return f"{ZOOM_AUTH_URL}?{urllib.parse.urlencode(params)}", signed_state

    @classmethod
    def verify_state(cls, received_state, expected_user_id, consume=True):
        if not received_state:
            return False
        try:
            unsigned = TimestampSigner(salt=cls.STATE_SALT).unsign(received_state, max_age=cls.STATE_MAX_AGE)
        except (BadSignature, SignatureExpired):
            return False
        user_part, _, nonce = unsigned.partition(':')
        if str(user_part) != str(expected_user_id) or not nonce:
            return False
        if consume and not cache.add(f"zoom-oauth-used:{nonce}", 1, cls.STATE_MAX_AGE):
            return False
        return True

    @classmethod
    def exchange_code_for_tokens(cls, code):
        if not cls.is_configured():
            raise ValueError("Zoom OAuth credentials are not configured on the server.")
        auth_header = base64.b64encode(
            f"{settings.ZOOM_CLIENT_ID}:{settings.ZOOM_CLIENT_SECRET}".encode('utf-8')
        ).decode('ascii')
        payload = urllib.parse.urlencode({
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': _zoom_redirect_uri(),
        }).encode('utf-8')
        req = urllib.request.Request(
            ZOOM_TOKEN_URL,
            data=payload,
            method='POST',
            headers={
                'Authorization': f'Basic {auth_header}',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json',
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            raw = e.read().decode('utf-8', errors='ignore')
            logger.warning("Zoom token exchange failed (%s): %s", e.code, raw)
            raise ZoomAPIError(f"Zoom token exchange failed: {raw}", status=e.code)
        except Exception as e:
            logger.error("Zoom token exchange network error: %s", e)
            raise ZoomAPIError("Unable to reach Zoom OAuth server.")

        return data

    @classmethod
    def store_tokens(cls, user, tokens):
        from .models import ZoomCredentials
        access_token = tokens.get('access_token')
        if not access_token:
            raise ValueError("Failed to receive access token from Zoom.")

        # Query user profile for email and zoom user id
        email, zoom_user_id = '', ''
        try:
            user_info = _zoom_api_request_raw(access_token, 'GET', '/users/me')
            email = user_info.get('email') or user.email or ''
            zoom_user_id = str(user_info.get('id') or '')
        except Exception as exc:
            logger.warning("Could not fetch Zoom user profile: %s", exc)
            email = user.email or ''

        creds, _ = ZoomCredentials.objects.get_or_create(user=user)
        creds.email = email
        creds.zoom_user_id = zoom_user_id
        creds.access_token_encrypted = encryption.encrypt_password(access_token)
        if tokens.get('refresh_token'):
            creds.refresh_token_encrypted = encryption.encrypt_password(tokens['refresh_token'])
        creds.token_expiry = timezone.now() + timedelta(seconds=tokens.get('expires_in', 3600))
        creds.scopes = tokens.get('scope', '') or ' '.join(cls.SCOPES)
        creds.is_active = True
        creds.save()
        return creds

    @classmethod
    def refresh_access_token(cls, creds):
        if not creds.refresh_token_encrypted:
            creds.is_active = False
            creds.save(update_fields=['is_active', 'updated_at'])
            raise ZoomAuthError("Zoom needs to be reconnected.")

        refresh_token = encryption.decrypt_password(creds.refresh_token_encrypted)
        auth_header = base64.b64encode(
            f"{settings.ZOOM_CLIENT_ID}:{settings.ZOOM_CLIENT_SECRET}".encode('utf-8')
        ).decode('ascii')
        payload = urllib.parse.urlencode({
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
        }).encode('utf-8')
        req = urllib.request.Request(
            ZOOM_TOKEN_URL,
            data=payload,
            method='POST',
            headers={
                'Authorization': f'Basic {auth_header}',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json',
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            raw = e.read().decode('utf-8', errors='ignore')
            logger.warning("Zoom token refresh failed (%s): %s", e.code, raw)
            if e.code in (400, 401):
                creds.is_active = False
                creds.save(update_fields=['is_active', 'updated_at'])
                raise ZoomAuthError("Zoom access was revoked or expired. Please reconnect Zoom.")
            raise ZoomAPIError("Could not refresh Zoom access.", status=e.code)
        except Exception as e:
            logger.error("Zoom token refresh network error: %s", e)
            raise ZoomAPIError("Unable to reach Zoom server.")

        new_token = data.get('access_token')
        if not new_token:
            raise ZoomAPIError("Zoom returned no access token.")
        creds.access_token_encrypted = encryption.encrypt_password(new_token)
        if data.get('refresh_token'):
            creds.refresh_token_encrypted = encryption.encrypt_password(data['refresh_token'])
        creds.token_expiry = timezone.now() + timedelta(seconds=data.get('expires_in', 3600))
        creds.is_active = True
        creds.save(update_fields=['access_token_encrypted', 'refresh_token_encrypted', 'token_expiry', 'is_active', 'updated_at'])
        return new_token

    @classmethod
    def get_valid_access_token(cls, creds):
        if not creds.token_expiry or creds.token_expiry <= timezone.now() + timedelta(seconds=60):
            return cls.refresh_access_token(creds)
        return encryption.decrypt_password(creds.access_token_encrypted)

    @classmethod
    def revoke(cls, creds):
        """Best effort revoke with Zoom."""
        try:
            token = encryption.decrypt_password(creds.refresh_token_encrypted or creds.access_token_encrypted)
            auth_header = base64.b64encode(
                f"{settings.ZOOM_CLIENT_ID}:{settings.ZOOM_CLIENT_SECRET}".encode('utf-8')
            ).decode('ascii')
            payload = urllib.parse.urlencode({'token': token}).encode('utf-8')
            req = urllib.request.Request(
                ZOOM_REVOKE_URL, data=payload, method='POST',
                headers={'Authorization': f'Basic {auth_header}', 'Content-Type': 'application/x-www-form-urlencoded'}
            )
            urllib.request.urlopen(req, timeout=10).close()
        except Exception as e:
            logger.info("Zoom token revoke skipped/failed: %s", e)


def _zoom_api_request_raw(token, method, path, body=None, params=None):
    url = f"{ZOOM_API_BASE}{path}"
    if params:
        url += '?' + urllib.parse.urlencode(params)
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json', 'Accept': 'application/json'},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        raw = resp.read().decode('utf-8')
        return json.loads(raw) if raw else {}


def zoom_api_request(creds, method, path, body=None, params=None):
    token = ZoomOAuthService.get_valid_access_token(creds)
    try:
        return _zoom_api_request_raw(token, method, path, body=body, params=params)
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', errors='ignore')
        logger.warning("Zoom API %s %s failed (%s): %s", method, path, e.code, raw[:300])
        if e.code in (401, 403):
            creds.is_active = False
            creds.save(update_fields=['is_active', 'updated_at'])
            raise ZoomAuthError("Zoom authorization was revoked or expired. Please reconnect Zoom.")
        raise ZoomAPIError(f"Zoom request failed: {raw}", status=e.code)
    except ZoomError:
        raise
    except Exception as e:
        logger.error("Zoom API network error: %s", e)
        raise ZoomAPIError("Unable to reach Zoom. Please try again.")


def create_zoom_meeting(creds, *, summary, description, start_dt, tz_name, duration_minutes=None):
    """Create a real Zoom meeting using Zoom Meetings API."""
    duration = duration_minutes or getattr(settings, 'MEETING_DEFAULT_DURATION_MINUTES', DEFAULT_MEETING_DURATION_MINUTES)
    start_time_iso = start_dt.strftime('%Y-%m-%dT%H:%M:%SZ')
    payload = {
        'topic': summary,
        'type': 2,  # Scheduled meeting
        'start_time': start_time_iso,
        'duration': duration,
        'timezone': tz_name or 'UTC',
        'agenda': description or '',
        'settings': {
            'host_video': True,
            'participant_video': True,
            'join_before_host': False,
            'waiting_room': True,
        },
    }
    data = zoom_api_request(creds, 'POST', '/users/me/meetings', body=payload)
    meeting_id = str(data.get('id') or '')
    join_url = data.get('join_url')
    if not join_url:
        raise ZoomAPIError("Zoom did not return a valid join URL.")

    return {
        'meeting_id': meeting_id,
        'join_url': join_url,
        'password': data.get('password', ''),
        'start_url': data.get('start_url', ''),
        'status': 'READY',
    }


def delete_zoom_meeting(creds, meeting_id):
    """Best effort cleanup of a created Zoom meeting."""
    if not meeting_id:
        return
    try:
        zoom_api_request(creds, 'DELETE', f'/meetings/{meeting_id}')
    except Exception as e:
        logger.warning("Could not delete Zoom meeting %s: %s", meeting_id, e)

