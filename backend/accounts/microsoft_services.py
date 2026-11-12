"""Microsoft 365 OAuth authorization + Teams Meeting & Outlook Calendar creation.

Isolated credential row, signed state salt, encrypted storage, and token refresh.
Uses Microsoft Graph API v1.0.
"""
import hashlib
import json
import logging
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta
from zoneinfo import ZoneInfo

from django.conf import settings
from django.core.cache import cache
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.utils import timezone

import utils.encryption as encryption

logger = logging.getLogger(__name__)

MS_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MS_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
DEFAULT_MEETING_DURATION_MINUTES = 30


class MicrosoftError(Exception):
    """Base exception for Microsoft integration errors."""


class MicrosoftNotConnected(MicrosoftError):
    pass


class MicrosoftAuthError(MicrosoftError):
    """Consent revoked/expired or permission missing."""


class MicrosoftAPIError(MicrosoftError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def _microsoft_redirect_uri():
    return getattr(
        settings, 'MICROSOFT_OAUTH_REDIRECT_URI',
        'http://localhost:5173/auth/microsoft/callback'
    )


def get_microsoft_credentials(user):
    """Retrieve active Microsoft credentials for a user."""
    if not user or not user.is_authenticated:
        return None
    from .models import MicrosoftCalendarCredentials
    creds = MicrosoftCalendarCredentials.objects.filter(user=user, is_active=True).first()
    if creds and (creds.refresh_token_encrypted or creds.access_token_encrypted):
        return creds
    return None


class MicrosoftOAuthService:
    STATE_MAX_AGE = 600
    STATE_SALT = 'ms-oauth-state'
    SCOPES = [
        'offline_access',
        'User.Read',
        'Calendars.ReadWrite',
        'OnlineMeetings.ReadWrite',
    ]

    @classmethod
    def is_configured(cls):
        return bool(
            getattr(settings, 'MICROSOFT_CLIENT_ID', '').strip() and
            getattr(settings, 'MICROSOFT_CLIENT_SECRET', '').strip()
        )

    @classmethod
    def generate_authorization_url(cls, user_id):
        if not cls.is_configured():
            raise ValueError("Microsoft OAuth credentials are not configured on the server.")
        raw_state = f"{user_id}:{secrets.token_urlsafe(24)}"
        signed_state = TimestampSigner(salt=cls.STATE_SALT).sign(raw_state)
        params = {
            'client_id': settings.MICROSOFT_CLIENT_ID,
            'response_type': 'code',
            'redirect_uri': _microsoft_redirect_uri(),
            'response_mode': 'query',
            'scope': ' '.join(cls.SCOPES),
            'state': signed_state,
        }
        return f"{MS_AUTH_URL}?{urllib.parse.urlencode(params)}", signed_state

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
        if consume and not cache.add(f"ms-oauth-used:{nonce}", 1, cls.STATE_MAX_AGE):
            return False
        return True

    @classmethod
    def exchange_code_for_tokens(cls, code):
        if not cls.is_configured():
            raise ValueError("Microsoft OAuth credentials are not configured on the server.")
        payload = urllib.parse.urlencode({
            'client_id': settings.MICROSOFT_CLIENT_ID,
            'client_secret': settings.MICROSOFT_CLIENT_SECRET,
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': _microsoft_redirect_uri(),
            'scope': ' '.join(cls.SCOPES),
        }).encode('utf-8')
        req = urllib.request.Request(
            MS_TOKEN_URL,
            data=payload,
            method='POST',
            headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            raw = e.read().decode('utf-8', errors='ignore')
            logger.warning("Microsoft token exchange failed (%s): %s", e.code, raw)
            raise MicrosoftAPIError(f"Microsoft token exchange failed: {raw}", status=e.code)
        except Exception as e:
            logger.error("Microsoft token exchange network error: %s", e)
            raise MicrosoftAPIError("Unable to reach Microsoft OAuth server.")

        return data

    @classmethod
    def store_tokens(cls, user, tokens):
        from .models import MicrosoftCalendarCredentials
        access_token = tokens.get('access_token')
        if not access_token:
            raise ValueError("Failed to receive access token from Microsoft.")

        email, ms_user_id = '', ''
        try:
            user_info = _ms_api_request_raw(access_token, 'GET', '/me')
            email = user_info.get('mail') or user_info.get('userPrincipalName') or user.email or ''
            ms_user_id = str(user_info.get('id') or '')
        except Exception as exc:
            logger.warning("Could not fetch Microsoft user profile: %s", exc)
            email = user.email or ''

        creds, _ = MicrosoftCalendarCredentials.objects.get_or_create(user=user)
        creds.email = email
        creds.ms_user_id = ms_user_id
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
            raise MicrosoftAuthError("Microsoft account needs to be reconnected.")

        refresh_token = encryption.decrypt_password(creds.refresh_token_encrypted)
        payload = urllib.parse.urlencode({
            'client_id': settings.MICROSOFT_CLIENT_ID,
            'client_secret': settings.MICROSOFT_CLIENT_SECRET,
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'scope': ' '.join(cls.SCOPES),
        }).encode('utf-8')
        req = urllib.request.Request(
            MS_TOKEN_URL,
            data=payload,
            method='POST',
            headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            raw = e.read().decode('utf-8', errors='ignore')
            logger.warning("Microsoft token refresh failed (%s): %s", e.code, raw)
            if e.code in (400, 401):
                creds.is_active = False
                creds.save(update_fields=['is_active', 'updated_at'])
                raise MicrosoftAuthError("Microsoft access was revoked or expired. Please reconnect.")
            raise MicrosoftAPIError("Could not refresh Microsoft access.", status=e.code)
        except Exception as e:
            logger.error("Microsoft token refresh network error: %s", e)
            raise MicrosoftAPIError("Unable to reach Microsoft server.")

        new_token = data.get('access_token')
        if not new_token:
            raise MicrosoftAPIError("Microsoft returned no access token.")
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
        """Best effort local cleanup for Microsoft."""
        try:
            creds.is_active = False
            creds.save(update_fields=['is_active', 'updated_at'])
        except Exception as e:
            logger.info("Microsoft revoke: %s", e)


def _ms_api_request_raw(token, method, path, body=None, params=None):
    url = f"{MS_GRAPH_BASE}{path}"
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


def ms_api_request(creds, method, path, body=None, params=None):
    token = MicrosoftOAuthService.get_valid_access_token(creds)
    try:
        return _ms_api_request_raw(token, method, path, body=body, params=params)
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', errors='ignore')
        logger.warning("Microsoft Graph API %s %s failed (%s): %s", method, path, e.code, raw[:300])
        if e.code in (401, 403):
            creds.is_active = False
            creds.save(update_fields=['is_active', 'updated_at'])
            raise MicrosoftAuthError("Microsoft authorization was revoked or expired. Please reconnect.")
        raise MicrosoftAPIError(f"Microsoft request failed: {raw}", status=e.code)
    except MicrosoftError:
        raise
    except Exception as e:
        logger.error("Microsoft Graph API network error: %s", e)
        raise MicrosoftAPIError("Unable to reach Microsoft Graph. Please try again.")


def create_teams_meeting_and_event(creds, *, summary, description, start_dt, tz_name, attendees, duration_minutes=None):
    """Create a Microsoft Teams meeting and sync it to Outlook Calendar."""
    duration = duration_minutes or getattr(settings, 'MEETING_DEFAULT_DURATION_MINUTES', DEFAULT_MEETING_DURATION_MINUTES)
    try:
        tz = ZoneInfo(tz_name or 'UTC')
    except Exception:
        tz, tz_name = ZoneInfo('UTC'), 'UTC'

    start_local = start_dt.astimezone(tz)
    end_local = start_local + timedelta(minutes=duration)

    # 1. Primary path: POST /me/events with isOnlineMeeting=true & onlineMeetingProvider=teamsForBusiness
    body = {
        'subject': summary,
        'body': {
            'contentType': 'HTML',
            'content': f"<p>{description or ''}</p>",
        },
        'start': {
            'dateTime': start_local.strftime('%Y-%m-%dT%H:%M:%S'),
            'timeZone': tz_name,
        },
        'end': {
            'dateTime': end_local.strftime('%Y-%m-%dT%H:%M:%S'),
            'timeZone': tz_name,
        },
        'location': {
            'displayName': 'Microsoft Teams Meeting',
        },
        'isOnlineMeeting': True,
        'onlineMeetingProvider': 'teamsForBusiness',
    }
    if attendees:
        body['attendees'] = [
            {'emailAddress': {'address': a, 'name': a}, 'type': 'required'}
            for a in attendees
        ]

    event_id = None
    join_url = None
    try:
        event = ms_api_request(creds, 'POST', '/me/events', body=body)
        event_id = event.get('id')
        online_meeting = event.get('onlineMeeting') or {}
        join_url = online_meeting.get('joinUrl') or event.get('onlineMeetingUrl')
    except Exception as exc:
        logger.info("Direct online meeting via /me/events failed, trying onlineMeetings fallback: %s", exc)

    # 2. Fallback path if direct event online meeting did not produce joinUrl:
    if not join_url:
        meeting_body = {
            'startDateTime': start_dt.strftime('%Y-%m-%dT%H:%M:%SZ'),
            'endDateTime': (start_dt + timedelta(minutes=duration)).strftime('%Y-%m-%dT%H:%M:%SZ'),
            'subject': summary,
        }
        meeting_data = ms_api_request(creds, 'POST', '/me/onlineMeetings', body=meeting_body)
        join_url = meeting_data.get('joinWebUrl')
        meeting_id = meeting_data.get('id')

        if not join_url:
            raise MicrosoftAPIError("Microsoft Teams meeting URL could not be generated.")

        # If event wasn't created yet or needs join URL embedded:
        if not event_id:
            body['isOnlineMeeting'] = False
            del body['onlineMeetingProvider']
            body['location'] = {
                'displayName': 'Microsoft Teams Meeting',
                'locationUri': join_url,
            }
            body['body']['content'] = f"<p>{description or ''}</p><p><a href=\"{join_url}\">Join Microsoft Teams Meeting</a></p>"
            event = ms_api_request(creds, 'POST', '/me/events', body=body)
            event_id = event.get('id')
    else:
        meeting_id = event.get('onlineMeeting', {}).get('conferenceId') or event_id

    return {
        'event_id': event_id,
        'meeting_id': meeting_id or event_id,
        'join_url': join_url,
        'status': 'READY',
    }


def create_outlook_event_for_zoom(creds, *, summary, description, start_dt, tz_name, attendees, zoom_join_url, duration_minutes=None):
    """Add a scheduled Zoom meeting to the user's Outlook Calendar."""
    duration = duration_minutes or getattr(settings, 'MEETING_DEFAULT_DURATION_MINUTES', DEFAULT_MEETING_DURATION_MINUTES)
    try:
        tz = ZoneInfo(tz_name or 'UTC')
    except Exception:
        tz, tz_name = ZoneInfo('UTC'), 'UTC'

    start_local = start_dt.astimezone(tz)
    end_local = start_local + timedelta(minutes=duration)

    body = {
        'subject': f"{summary} (Zoom Meeting)",
        'body': {
            'contentType': 'HTML',
            'content': f"<p>{description or ''}</p><p><a href=\"{zoom_join_url}\">Join Zoom Meeting</a></p>",
        },
        'start': {
            'dateTime': start_local.strftime('%Y-%m-%dT%H:%M:%S'),
            'timeZone': tz_name,
        },
        'end': {
            'dateTime': end_local.strftime('%Y-%m-%dT%H:%M:%S'),
            'timeZone': tz_name,
        },
        'location': {
            'displayName': 'Zoom Meeting',
            'locationUri': zoom_join_url,
        },
    }
    if attendees:
        body['attendees'] = [
            {'emailAddress': {'address': a, 'name': a}, 'type': 'required'}
            for a in attendees
        ]

    event = ms_api_request(creds, 'POST', '/me/events', body=body)
    return event.get('id')


def delete_outlook_event(creds, event_id):
    """Best effort cleanup of an Outlook event."""
    if not event_id:
        return
    try:
        ms_api_request(creds, 'DELETE', f'/me/events/{event_id}')
    except Exception as e:
        logger.warning("Could not delete Outlook event %s: %s", event_id, e)

