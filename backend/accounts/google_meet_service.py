"""Google Meet REST API v2 Service for Meeting Audio/Video Recording Download.

Uses the official Google Meet REST API v2 (https://meet.googleapis.com/v2):
1. Query conference records by meeting space / meeting code (space.meeting_code="xxx-yyyy-zzz").
2. Query recording resources for each conference record (conferenceRecords/{conf_id}/recordings).
3. Download the generated audio/video recording artifact from Google Drive into Market Intel DB storage.
4. Attach downloaded recording file and metadata to the Meeting model in Market Intel DB.
"""
import io
import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone

from .calendar_services import (
    CalendarAPIError,
    CalendarAuthError,
    CalendarError,
    GoogleCalendarOAuthService,
    get_calendar_credentials,
)

logger = logging.getLogger(__name__)

MEET_API_BASE = "https://meet.googleapis.com/v2"
DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"


def extract_meeting_code(url_or_code):
    """Extract standard 10-character Google Meet code (e.g. 'abc-defg-hij') from a URL or raw string."""
    if not url_or_code:
        return ''
    raw = str(url_or_code).strip()
    match = re.search(r'([a-z]{3}-[a-z]{4}-[a-z]{3})', raw.lower())
    if match:
        return match.group(1)
    # Fallback: remove url prefix and query parameters
    cleaned = re.sub(r'^https?://meet\.google\.com/', '', raw, flags=re.IGNORECASE)
    cleaned = cleaned.split('?')[0].split('#')[0].strip('/')
    return cleaned


class GoogleMeetRestService:
    """Service to interact with Google Meet REST API v2 and download meeting recordings."""

    @classmethod
    def _get_access_token(cls, creds):
        """Retrieve valid, auto-refreshed access token for the connected Google OAuth user."""
        return GoogleCalendarOAuthService.get_valid_access_token(creds)

    @classmethod
    def _api_request(cls, creds, method, url, body=None, params=None, is_stream=False):
        token = cls._get_access_token(creds)
        if params:
            url += ('&' if '?' in url else '?') + urllib.parse.urlencode(params)
        data = json.dumps(body).encode('utf-8') if body is not None else None
        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json',
        }
        if data is not None:
            headers['Content-Type'] = 'application/json'

        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            if is_stream:
                return resp
            raw = resp.read().decode('utf-8')
            return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read().decode('utf-8', errors='ignore')
            logger.warning("Google Meet/Drive API %s %s failed (%s): %s", method, url, e.code, raw[:300])
            if e.code in (401, 403):
                msg = "Google Meet/Drive permission is missing or was revoked. Please reconnect Google account."
                raise CalendarAuthError(msg)
            raise CalendarAPIError(f"Google API request failed: {raw}", status=e.code)
        except Exception as e:
            logger.error("Google Meet/Drive network error: %s", e)
            raise CalendarAPIError(f"Unable to reach Google API: {e}")

    @classmethod
    def enable_auto_recording_on_space(cls, creds, meeting_code_or_url):
        """Enable automatic recording generation on a Google Meet space via Meet REST API v2.

        Uses PATCH https://meet.googleapis.com/v2/spaces/{meeting_code}
        with updateMask=config.artifactConfig.recordingConfig.autoRecordingGeneration
        so that when a licensed Workspace host joins, recording starts automatically.
        Best-effort: never raises if the user's account/plan or scope doesn't support auto-recording.
        """
        code = extract_meeting_code(meeting_code_or_url)
        if not code:
            return False
        url = f"{MEET_API_BASE}/spaces/{code}"
        params = {'updateMask': 'config.artifactConfig.recordingConfig.autoRecordingGeneration'}
        body = {
            'config': {
                'artifactConfig': {
                    'recordingConfig': {
                        'autoRecordingGeneration': 'ON'
                    }
                }
            }
        }
        try:
            cls._api_request(creds, 'PATCH', url, body=body, params=params)
            logger.info("Enabled autoRecordingGeneration=ON for Google Meet space %s", code)
            return True
        except Exception as exc:
            logger.info("Could not set autoRecordingGeneration on space %s (plan/scope may not support it): %s", code, exc)
            return False

    @classmethod
    def list_conference_records(cls, creds, meeting_code=None, page_size=20):
        """List conference records from Google Meet REST API v2.

        Uses filter=space.meeting_code="{meeting_code}" to target the specific meeting.
        """
        url = f"{MEET_API_BASE}/conferenceRecords"
        params = {'pageSize': page_size}
        if meeting_code:
            code = extract_meeting_code(meeting_code)
            params['filter'] = f'space.meeting_code="{code}"'

        try:
            data = cls._api_request(creds, 'GET', url, params=params)
            return data.get('conferenceRecords', [])
        except CalendarAPIError as e:
            # If space.meeting_code filter is unsupported on a specific space type, try fallback without filter
            if meeting_code and 'filter' in str(e).lower():
                logger.info("Retrying conferenceRecords without meeting_code filter...")
                data = cls._api_request(creds, 'GET', url, params={'pageSize': page_size})
                return data.get('conferenceRecords', [])
            raise

    @classmethod
    def list_recordings_for_conference(cls, creds, conference_record_name):
        """List recordings for a specific conference record via Google Meet REST API v2."""
        # conference_record_name is e.g. "conferenceRecords/C_XXXXXXXXXX"
        cleaned_name = conference_record_name.strip().lstrip('/')
        url = f"{MEET_API_BASE}/{cleaned_name}/recordings"
        data = cls._api_request(creds, 'GET', url)
        return data.get('recordings', [])

    @classmethod
    def get_drive_file_metadata(cls, creds, drive_file_id):
        """Get file metadata (name, mimeType, size) from Google Drive API."""
        url = f"{DRIVE_API_BASE}/files/{drive_file_id}"
        params = {'fields': 'id,name,mimeType,size,webContentLink,createdTime'}
        return cls._api_request(creds, 'GET', url, params=params)

    @classmethod
    def download_drive_file_content(cls, creds, drive_file_id):
        """Download file content from Google Drive API using user's OAuth Bearer token."""
        url = f"{DRIVE_API_BASE}/files/{drive_file_id}?alt=media"
        token = cls._get_access_token(creds)
        req = urllib.request.Request(
            url,
            method='GET',
            headers={'Authorization': f'Bearer {token}'}
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='ignore')
            logger.warning("Drive media download failed (%s): %s", e.code, body[:300])
            if e.code in (401, 403):
                raise CalendarAuthError("Google Drive permission missing or expired to download recording.")
            raise CalendarAPIError(f"Drive download failed: {body}", status=e.code)
        except Exception as e:
            logger.error("Drive download stream error: %s", e)
            raise CalendarAPIError(f"Drive download stream error: {e}")

    @classmethod
    def sync_meeting_recording(cls, meeting):
        """Download and attach Google Meet audio/video recording to a Meeting in Market Intel DB.

        1. Ensures meeting provider is GOOGLE_MEET.
        2. Retrieves the host's connected Google OAuth credentials.
        3. Calls Google Meet REST API v2 to fetch conference record & recordings.
        4. Downloads the file content from Google Drive and saves to Meeting.recording_file.
        5. Updates recording status, file size, mime type, and downloaded timestamp.
        """
        if not meeting:
            return {'success': False, 'error': 'No meeting provided.', 'status': 'FAILED'}

        if meeting.meeting_provider != 'GOOGLE_MEET':
            return {
                'success': False,
                'error': f'Meeting provider is {meeting.meeting_provider}, not GOOGLE_MEET.',
                'status': 'INVALID_PROVIDER'
            }

        meeting_code = extract_meeting_code(meeting.meeting_link)
        if not meeting_code:
            return {
                'success': False,
                'error': 'No valid Google Meet code found in meeting link.',
                'status': 'INVALID_LINK'
            }

        # The host user who connected Google OAuth and scheduled/hosted the meeting
        host_user = meeting.google_calendar_owner or meeting.created_by
        if not host_user:
            return {
                'success': False,
                'error': 'No Google Calendar owner or host user associated with this meeting.',
                'status': 'NO_HOST'
            }

        creds = get_calendar_credentials(host_user)
        if not creds:
            return {
                'success': False,
                'error': f'Connected Google OAuth user ({host_user.username}) has no active Google credentials.',
                'status': 'NOT_CONNECTED'
            }

        try:
            meeting.recording_status = 'DOWNLOADING'
            meeting.save(update_fields=['recording_status', 'updated_at'])

            # 1. Query Google Meet REST API v2 for conference records
            conf_records = cls.list_conference_records(creds, meeting_code=meeting_code)
            if not conf_records:
                meeting.recording_status = 'NOT_FOUND'
                meeting.save(update_fields=['recording_status', 'updated_at'])
                return {
                    'success': False,
                    'status': 'NOT_FOUND',
                    'detail': f'No Google Meet conference records found for code "{meeting_code}". Ensure the meeting was hosted and ended.'
                }

            # 2. Iterate through conference records to locate generated recordings
            found_recording = None
            found_conf_record = None

            for conf in conf_records:
                conf_name = conf.get('name')
                if not conf_name:
                    continue
                recordings = cls.list_recordings_for_conference(creds, conf_name)
                for rec in recordings:
                    drive_dest = rec.get('driveDestination') or {}
                    drive_file_id = drive_dest.get('file')
                    state = rec.get('state')

                    if drive_file_id:
                        found_recording = rec
                        found_conf_record = conf
                        break
                    elif state in ('STARTED', 'ENDED'):
                        # Recording is still being processed by Google Meet
                        found_recording = rec
                        found_conf_record = conf

                if found_recording and (found_recording.get('driveDestination') or {}).get('file'):
                    break

            if not found_recording:
                meeting.recording_status = 'NOT_FOUND'
                meeting.save(update_fields=['recording_status', 'updated_at'])
                return {
                    'success': False,
                    'status': 'NOT_FOUND',
                    'detail': (
                        f'Conference record found ({conf_records[0].get("name")}), but no recording was saved in Google Meet. '
                        'Please ensure "Record meeting" (Activities → Recording → Start recording) was turned on during the call, '
                        'and wait 1–2 minutes after the call ends for Google to save the file to Drive.'
                    )
                }

            drive_dest = found_recording.get('driveDestination') or {}
            drive_file_id = drive_dest.get('file')

            # If recording exists but file is not generated yet (e.g. Google is still encoding the media)
            if not drive_file_id:
                state = found_recording.get('state', 'UNKNOWN')
                meeting.recording_status = 'PROCESSING'
                meeting.google_conference_record_id = found_conf_record.get('name', '')
                meeting.google_recording_id = found_recording.get('name', '')
                meeting.save(update_fields=['recording_status', 'google_conference_record_id', 'google_recording_id', 'updated_at'])
                return {
                    'success': False,
                    'status': 'PROCESSING',
                    'state': state,
                    'detail': 'Google Meet is currently generating the recording file. Please try again shortly.'
                }

            # 3. Retrieve metadata from Google Drive API
            meta = cls.get_drive_file_metadata(creds, drive_file_id)
            orig_filename = meta.get('name') or f"meet_recording_{meeting_code}_{int(timezone.now().timestamp())}.mp4"
            mime_type = meta.get('mimeType') or 'video/mp4'
            file_size = int(meta.get('size') or 0)

            # Sanitize filename
            clean_filename = re.sub(r'[^a-zA-Z0-9_.-]', '_', orig_filename)
            if not clean_filename.endswith(('.mp4', '.m4a', '.webm', '.ogg', '.wav', '.mp3')):
                clean_filename += '.mp4'

            # 4. Download file bytes from Google Drive API
            file_bytes = cls.download_drive_file_content(creds, drive_file_id)
            if not file_bytes:
                raise CalendarAPIError("Downloaded recording file was empty.")

            # 5. Save to Market Intel DB Meeting model
            django_file = ContentFile(file_bytes, name=clean_filename)
            meeting.recording_file.save(clean_filename, django_file, save=False)
            meeting.recording_status = 'COMPLETED'
            meeting.recording_downloaded_at = timezone.now()
            meeting.recording_file_size = len(file_bytes) or file_size
            meeting.recording_mime_type = mime_type
            meeting.google_conference_record_id = found_conf_record.get('name', '')
            meeting.google_recording_id = found_recording.get('name', '')
            meeting.recording_drive_file_id = drive_file_id
            meeting.save()

            logger.info("Successfully downloaded Google Meet recording for Meeting ID %s (%s bytes)", meeting.id, len(file_bytes))

            return {
                'success': True,
                'status': 'COMPLETED',
                'recording_url': meeting.recording_file.url if meeting.recording_file else None,
                'filename': clean_filename,
                'file_size': meeting.recording_file_size,
                'mime_type': meeting.recording_mime_type,
                'downloaded_at': meeting.recording_downloaded_at.isoformat(),
            }

        except CalendarAuthError as exc:
            meeting.recording_status = 'FAILED'
            meeting.save(update_fields=['recording_status', 'updated_at'])
            return {'success': False, 'status': 'AUTH_ERROR', 'error': str(exc)}
        except CalendarAPIError as exc:
            meeting.recording_status = 'FAILED'
            meeting.save(update_fields=['recording_status', 'updated_at'])
            return {'success': False, 'status': 'API_ERROR', 'error': str(exc)}
        except Exception as exc:
            logger.exception("Unexpected error syncing meeting recording: %s", exc)
            meeting.recording_status = 'FAILED'
            meeting.save(update_fields=['recording_status', 'updated_at'])
            return {'success': False, 'status': 'ERROR', 'error': f'Failed to download meeting recording: {exc}'}

