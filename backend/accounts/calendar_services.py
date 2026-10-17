"""Google Calendar authorization + event/Meet creation.

Deliberately separate from ``GmailOAuthService`` / ``GoogleMailCredentials``: its own
consent flow, its own signed state salt, its own encrypted credential row, and only the
narrow ``calendar.events`` scope. Nothing here touches Gmail or login scopes.
"""
import hashlib
import json
import logging
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.utils import timezone

import utils.encryption as encryption
from .oauth_services import GOOGLE_AUTH_URL, GOOGLE_TOKEN_URL, GoogleOAuthService

logger = logging.getLogger(__name__)

CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
CALENDAR_EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events"

# Bounded polling for asynchronous conference creation.
CONFERENCE_POLL_ATTEMPTS = 5
CONFERENCE_POLL_INTERVAL_SECONDS = 1.0
DEFAULT_MEETING_DURATION_MINUTES = 30


class CalendarError(Exception):
    """Base class for Calendar integration failures (safe to show to the user)."""


class CalendarNotConnected(CalendarError):
    pass


class CalendarAuthError(CalendarError):
    """Consent revoked/expired or permission missing: user must re-connect."""


class CalendarAPIError(CalendarError):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class CalendarConferenceError(CalendarError):
    """Google could not create the Meet conference."""


def _calendar_redirect_uri():
    return getattr(
        settings, 'CALENDAR_OAUTH_REDIRECT_URI',
        getattr(settings, 'GMAIL_OAUTH_REDIRECT_URI', 'http://localhost:5173/auth/gmail/callback')
    )


def _has_calendar_scope(scopes):
    if not scopes:
        return False
    scope_set = set(scopes.split())
    return any('calendar' in s for s in scope_set)


def get_calendar_credentials(user):
    """Retrieve active Google Calendar credentials for a user, verifying calendar permission."""
    if not user or not user.is_authenticated:
        return None
    from .models import GoogleCalendarCredentials, GoogleMailCredentials
    creds = GoogleCalendarCredentials.objects.filter(user=user, is_active=True).first()
    if creds and (creds.refresh_token_encrypted or creds.access_token_encrypted):
        if _has_calendar_scope(creds.scopes):
            return creds
        # Inactive because it lacks calendar scope
        creds.is_active = False
        creds.save(update_fields=['is_active', 'updated_at'])

    # Fallback to GoogleMailCredentials ONLY if it actually has calendar permission
    mail_creds = GoogleMailCredentials.objects.filter(user=user, is_active=True).first()
    if mail_creds and (mail_creds.refresh_token_encrypted or mail_creds.access_token_encrypted):
        if _has_calendar_scope(mail_creds.scopes):
            creds, _ = GoogleCalendarCredentials.objects.get_or_create(user=user)
            creds.email = mail_creds.email or user.email or ''
            creds.access_token_encrypted = mail_creds.access_token_encrypted
            creds.refresh_token_encrypted = mail_creds.refresh_token_encrypted
            creds.token_expiry = mail_creds.token_expiry
            creds.scopes = mail_creds.scopes
            creds.is_active = True
            creds.save()
            return creds

    return None


class GoogleCalendarOAuthService:
    STATE_MAX_AGE = 600
    STATE_SALT = 'calendar-oauth-state'
    SCOPES = [
        "https://mail.google.com/",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/calendar",
        CALENDAR_EVENTS_SCOPE,
    ]

    # ── Authorization ────────────────────────────────────────────────────────
    @classmethod
    def generate_authorization_url(cls, user_id):
        if not GoogleOAuthService.is_configured():
            raise ValueError("Google OAuth credentials are not configured on the server.")
        raw_state = f"{user_id}:{secrets.token_urlsafe(24)}"
        signed_state = TimestampSigner(salt=cls.STATE_SALT).sign(raw_state)
        params = {
            'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
            'redirect_uri': _calendar_redirect_uri(),
            'response_type': 'code',
            'access_type': 'offline',
            'prompt': 'consent',
            'scope': ' '.join(cls.SCOPES),
            'include_granted_scopes': 'false',
            'state': signed_state,
        }
        return f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}", signed_state

    @classmethod
    def verify_state(cls, received_state, expected_user_id, consume=True):
        """State must be signed, fresh, bound to this user, and single-use."""
        if not received_state:
            return False
        try:
            unsigned = TimestampSigner(salt=cls.STATE_SALT).unsign(received_state, max_age=cls.STATE_MAX_AGE)
        except (BadSignature, SignatureExpired):
            return False
        user_part, _, nonce = unsigned.partition(':')
        if str(user_part) != str(expected_user_id) or not nonce:
            return False
        if consume and not cache.add(f"calendar-oauth-used:{nonce}", 1, cls.STATE_MAX_AGE):
            return False  # replay
        return True

    @classmethod
    def exchange_code_for_tokens(cls, code):
        return GoogleOAuthService.exchange_code_for_tokens(code=code, redirect_uri=_calendar_redirect_uri())

    @classmethod
    def store_tokens(cls, user, tokens):
        """Persist encrypted tokens. Accepts Calendar scopes and preserves refresh tokens."""
        from .models import GoogleCalendarCredentials, GoogleMailCredentials
        access_token = tokens.get('access_token')
        scope = tokens.get('scope', '') or ''
        if not access_token:
            raise ValueError("Failed to receive access token from Google.")
        scope_words = set(scope.split())
        has_cal_permission = any('calendar' in s for s in scope_words)
        if not has_cal_permission and scope:
            raise ValueError("Google Calendar permission was not granted. Please allow calendar access.")
        creds, _ = GoogleCalendarCredentials.objects.get_or_create(user=user)
        creds.email = user.email or ''
        creds.access_token_encrypted = encryption.encrypt_password(access_token)
        if tokens.get('refresh_token'):
            creds.refresh_token_encrypted = encryption.encrypt_password(tokens['refresh_token'])
        if not creds.refresh_token_encrypted:
            # Check existing mail credentials refresh token
            mail_creds = GoogleMailCredentials.objects.filter(user=user).first()
            if mail_creds and mail_creds.refresh_token_encrypted:
                creds.refresh_token_encrypted = mail_creds.refresh_token_encrypted
            else:
                raise ValueError("Google did not return a refresh token. Please reconnect and grant offline access.")
        creds.token_expiry = timezone.now() + timedelta(seconds=tokens.get('expires_in', 3600))
        creds.scopes = scope or ' '.join(cls.SCOPES)
        creds.is_active = True
        creds.save()

        # Seamlessly sync active GoogleMailCredentials so mail, inbox, and sending work immediately
        try:
            mail_creds, _ = GoogleMailCredentials.objects.get_or_create(user=user)
            mail_creds.email = creds.email
            mail_creds.access_token_encrypted = creds.access_token_encrypted
            if creds.refresh_token_encrypted:
                mail_creds.refresh_token_encrypted = creds.refresh_token_encrypted
            mail_creds.token_expiry = creds.token_expiry
            mail_creds.scopes = creds.scopes
            mail_creds.is_active = True
            mail_creds.save()
        except Exception as e:
            logger.warning("Could not sync GoogleMailCredentials: %s", e)

        return creds

    # ── Token lifecycle ──────────────────────────────────────────────────────
    @classmethod
    def refresh_access_token(cls, creds):
        if not creds.refresh_token_encrypted:
            creds.is_active = False
            creds.save(update_fields=['is_active', 'updated_at'])
            raise CalendarAuthError("Google Calendar needs to be reconnected.")
        refresh_token = encryption.decrypt_password(creds.refresh_token_encrypted)
        payload = urllib.parse.urlencode({
            'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
            'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
        }).encode('utf-8')
        req = urllib.request.Request(
            GOOGLE_TOKEN_URL, data=payload, method='POST',
            headers={'Content-Type': 'application/x-www-form-urlencoded', 'Accept': 'application/json'},
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='ignore')
            logger.warning("Calendar token refresh failed (%s): %s", e.code, body)
            if e.code in (400, 401) and ('invalid_grant' in body or 'invalid_client' in body or e.code == 401):
                creds.is_active = False
                creds.save(update_fields=['is_active', 'updated_at'])
                raise CalendarAuthError("Google Calendar access was revoked or expired. Please reconnect Google Calendar.")
            raise CalendarAPIError("Could not refresh Google Calendar access. Please try again.", status=e.code)
        except Exception as e:
            logger.error("Calendar token refresh network error: %s", e)
            raise CalendarAPIError("Unable to reach Google. Please try again.")

        new_token = data.get('access_token')
        if not new_token:
            raise CalendarAPIError("Google returned no access token.")
        creds.access_token_encrypted = encryption.encrypt_password(new_token)
        creds.token_expiry = timezone.now() + timedelta(seconds=data.get('expires_in', 3600))
        creds.is_active = True
        creds.save(update_fields=['access_token_encrypted', 'token_expiry', 'is_active', 'updated_at'])

        try:
            from .models import GoogleMailCredentials
            mail_creds = GoogleMailCredentials.objects.filter(user=creds.user).first()
            if mail_creds:
                mail_creds.access_token_encrypted = creds.access_token_encrypted
                mail_creds.token_expiry = creds.token_expiry
                mail_creds.is_active = True
                mail_creds.save(update_fields=['access_token_encrypted', 'token_expiry', 'is_active', 'updated_at'])
        except Exception as sync_err:
            logger.warning("Could not sync refreshed token to GoogleMailCredentials: %s", sync_err)

        return new_token

    @classmethod
    def get_valid_access_token(cls, creds):
        if not creds.token_expiry or creds.token_expiry <= timezone.now() + timedelta(seconds=60):
            return cls.refresh_access_token(creds)
        return encryption.decrypt_password(creds.access_token_encrypted)

    @classmethod
    def revoke(cls, creds):
        """Best-effort revoke at Google; local deletion never depends on it."""
        try:
            token = encryption.decrypt_password(creds.refresh_token_encrypted or creds.access_token_encrypted)
            req = urllib.request.Request(
                GOOGLE_REVOKE_URL, data=urllib.parse.urlencode({'token': token}).encode('utf-8'), method='POST',
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
            )
            urllib.request.urlopen(req, timeout=10).close()
        except Exception as e:  # noqa: BLE001 - best effort only
            logger.info("Calendar token revoke skipped/failed: %s", e)


# ── Calendar API ────────────────────────────────────────────────────────────
def _api_request(creds, method, path, body=None, params=None):
    """Call the Calendar API with the user's own (auto-refreshed) token."""
    token = GoogleCalendarOAuthService.get_valid_access_token(creds)
    url = f"{CALENDAR_API_BASE}{path}"
    if params:
        url += '?' + urllib.parse.urlencode(params)
    data = json.dumps(body).encode('utf-8') if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json', 'Accept': 'application/json'},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode('utf-8')
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode('utf-8', errors='ignore')
        reason, message = '', ''
        try:
            err = json.loads(raw).get('error', {})
            message = err.get('message', '') if isinstance(err, dict) else str(err)
            errors = err.get('errors') if isinstance(err, dict) else None
            reason = (errors[0].get('reason') if errors else '') or ''
        except Exception:  # noqa: BLE001
            pass
        logger.warning("Calendar API %s %s failed (%s): %s", method, path, e.code, raw[:300])
        msg_lower = (message or '').lower()
        is_auth_or_perm_error = (
            e.code == 401
            or (e.code == 403 and (
                reason in ('insufficientPermissions', 'forbidden', 'authError', 'PERMISSION_DENIED', 'accessDenied')
                or any(k in msg_lower for k in ('insufficient', 'permission', 'scope', 'auth', 'unauthorized', 'revoked'))
            ))
        )
        if is_auth_or_perm_error:
            creds.is_active = False
            creds.save(update_fields=['is_active', 'updated_at'])
            raise CalendarAuthError("Google Calendar permission is missing or was revoked. Please reconnect Google Calendar.")
        if e.code == 403 and reason in ('accessNotConfigured', 'SERVICE_DISABLED'):
            raise CalendarAPIError("The Google Calendar API is not enabled for this project.", status=e.code)
        raise CalendarAPIError(message or "Google Calendar request failed.", status=e.code)
    except CalendarError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.error("Calendar API network error: %s", e)
        raise CalendarAPIError("Unable to reach Google Calendar. Please try again.")


def deterministic_event_id(user_id, client_request_id):
    """Stable Google event id (lowercase hex is valid) so retries cannot create duplicates."""
    return hashlib.sha1(f"mi:{user_id}:{client_request_id}".encode('utf-8')).hexdigest()


def extract_conference(event):
    """Return (status, meet_url) where status is READY | PENDING | FAILED."""
    cd = (event or {}).get('conferenceData') or {}
    status_code = ((cd.get('createRequest') or {}).get('status') or {}).get('statusCode')
    url = None
    for ep in cd.get('entryPoints') or []:
        if ep.get('entryPointType') == 'video' and ep.get('uri'):
            url = ep['uri']
            break
    url = url or (event or {}).get('hangoutLink')
    if url and url.startswith('https://meet.google.com/'):
        return 'READY', url
    if status_code == 'pending':
        return 'PENDING', None
    return 'FAILED', None


def build_event_body(*, summary, description, start_dt, duration_minutes, tz_name, attendees, request_id, event_id):
    from zoneinfo import ZoneInfo
    try:
        tz = ZoneInfo(tz_name or 'UTC')
    except Exception:  # noqa: BLE001
        tz, tz_name = ZoneInfo('UTC'), 'UTC'
    start_local = start_dt.astimezone(tz)
    end_local = start_local + timedelta(minutes=duration_minutes)
    body = {
        'id': event_id,
        'summary': summary,
        'description': description or '',
        'start': {'dateTime': start_local.isoformat(), 'timeZone': tz_name},
        'end': {'dateTime': end_local.isoformat(), 'timeZone': tz_name},
        'conferenceData': {
            'createRequest': {
                'requestId': request_id,
                'conferenceSolutionKey': {'type': 'hangoutsMeet'},
            }
        },
    }
    if attendees:
        body['attendees'] = [{'email': a} for a in attendees]
    return body


def create_meet_event(creds, *, summary, description, start_dt, tz_name, attendees, client_request_id,
                      duration_minutes=None):
    """Create a primary-calendar event with a real Meet conference.

    Returns dict(event_id, status, meet_url). status is READY or PENDING; failures raise.
    Retries with the same ``client_request_id`` reuse the same Google event (no duplicate).
    """
    duration = duration_minutes or getattr(settings, 'MEETING_DEFAULT_DURATION_MINUTES', DEFAULT_MEETING_DURATION_MINUTES)
    event_id = deterministic_event_id(creds.user_id, client_request_id)
    conf_request_id = hashlib.sha1(f"conf:{event_id}".encode('utf-8')).hexdigest()
    body = build_event_body(
        summary=summary, description=description, start_dt=start_dt, duration_minutes=duration,
        tz_name=tz_name, attendees=attendees, request_id=conf_request_id, event_id=event_id,
    )
    params = {'conferenceDataVersion': 1, 'sendUpdates': 'all' if attendees else 'none'}
    try:
        event = _api_request(creds, 'POST', '/calendars/primary/events', body=body, params=params)
    except CalendarAPIError as e:
        if e.status == 409:  # same event id already created by an earlier attempt
            event = _api_request(creds, 'GET', f'/calendars/primary/events/{event_id}',
                                 params={'conferenceDataVersion': 1})
        else:
            raise

    event_id = event.get('id') or event_id
    status, url = extract_conference(event)
    attempts = 0
    while status == 'PENDING' and attempts < CONFERENCE_POLL_ATTEMPTS:
        attempts += 1
        time.sleep(CONFERENCE_POLL_INTERVAL_SECONDS)
        event = _api_request(creds, 'GET', f'/calendars/primary/events/{event_id}',
                             params={'conferenceDataVersion': 1})
        status, url = extract_conference(event)

    if status == 'FAILED':
        delete_event(creds, event_id)  # avoid an orphan event with no Meet link
        raise CalendarConferenceError("Google could not generate a Meet link for this event. Please retry.")
    return {'event_id': event_id, 'status': status, 'meet_url': url}


def get_event_conference(creds, event_id):
    event = _api_request(creds, 'GET', f'/calendars/primary/events/{event_id}', params={'conferenceDataVersion': 1})
    status, url = extract_conference(event)
    return {'event_id': event_id, 'status': status, 'meet_url': url}


def delete_event(creds, event_id):
    """Best-effort cleanup; never raises."""
    try:
        _api_request(creds, 'DELETE', f'/calendars/primary/events/{event_id}', params={'sendUpdates': 'none'})
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not delete Google event %s: %s", event_id, e)


def list_events(creds, time_min=None, time_max=None, max_results=250):
    """Fetch events from Google Calendar primary calendar."""
    params = {
        'singleEvents': 'true',
        'orderBy': 'startTime',
        'maxResults': max_results,
    }
    if time_min:
        params['timeMin'] = time_min.isoformat() if hasattr(time_min, 'isoformat') else str(time_min)
    if time_max:
        params['timeMax'] = time_max.isoformat() if hasattr(time_max, 'isoformat') else str(time_max)

    data = _api_request(creds, 'GET', '/calendars/primary/events', params=params)
    items = data.get('items', []) if isinstance(data, dict) else []
    events = []
    for item in items:
        if item.get('status') == 'cancelled':
            continue
        status_conf, meet_url = extract_conference(item)
        start_obj = item.get('start', {})
        end_obj = item.get('end', {})
        start_val = start_obj.get('dateTime') or start_obj.get('date')
        end_val = end_obj.get('dateTime') or end_obj.get('date')

        attendees = [
            {
                'email': a.get('email', ''),
                'name': a.get('displayName') or a.get('email', ''),
                'response': a.get('responseStatus', 'needsAction'),
                'self': bool(a.get('self')),
            }
            for a in item.get('attendees', []) if isinstance(a, dict)
        ]

        events.append({
            'id': item.get('id'),
            'summary': item.get('summary') or '(No Title)',
            'description': item.get('description') or '',
            'start': start_val,
            'end': end_val,
            'start_timezone': start_obj.get('timeZone'),
            'end_timezone': end_obj.get('timeZone'),
            'meet_url': meet_url,
            'conference_status': status_conf,
            'html_link': item.get('htmlLink') or f"https://calendar.google.com/calendar/r/eventedit/{item.get('id')}",
            'attendees': attendees,
            'location': item.get('location') or '',
            'status': item.get('status', 'confirmed'),
        })
    return events

