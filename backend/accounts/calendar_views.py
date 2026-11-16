"""Optional Google Calendar connection endpoints (separate from Gmail/login)."""
import uuid
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .calendar_services import (
    CalendarAuthError,
    CalendarError,
    GoogleCalendarOAuthService,
    get_calendar_credentials,
    list_events,
    delete_event,
    _api_request,
    extract_conference,
)
from .models import GoogleCalendarCredentials
from .oauth_services import GoogleOAuthService
from .serializers import GmailOAuthCallbackSerializer  # plain {code, state} serializer


def _can_use_calendar(user):
    """PRE, LQ and MANAGER users (and superusers) may use Calendar."""
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    return bool(profile and profile.role in ('PRE', 'LQ', 'MANAGER'))


class _CalendarBase(APIView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not _can_use_calendar(request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only PRE, Lead Qualifiers and Managers can use Google Calendar.")


class CalendarOAuthURLView(_CalendarBase):
    def get(self, request):
        try:
            url, state = GoogleCalendarOAuthService.generate_authorization_url(request.user.id)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"url": url, "authorization_url": url, "state": state}, status=status.HTTP_200_OK)


class CalendarOAuthCallbackView(_CalendarBase):
    def post(self, request):
        serializer = GmailOAuthCallbackSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        code = serializer.validated_data['code']
        state = serializer.validated_data['state']

        if not GoogleCalendarOAuthService.verify_state(state, request.user.id):
            return Response({"detail": "Invalid or expired Google Calendar authorization state."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            tokens = GoogleCalendarOAuthService.exchange_code_for_tokens(code)
            creds = GoogleCalendarOAuthService.store_tokens(request.user, tokens)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Google Calendar connected successfully.", "email": creds.email},
                        status=status.HTTP_200_OK)


class CalendarOAuthStatusView(_CalendarBase):
    """Connection state only; tokens/secrets are never returned."""
    def get(self, request):
        configured = GoogleOAuthService.is_configured()
        creds = get_calendar_credentials(request.user)
        if not creds:
            return Response({"is_connected": False, "is_configured": configured}, status=status.HTTP_200_OK)
        return Response({"is_connected": True, "is_configured": configured, "email": creds.email,
                         "updated_at": creds.updated_at}, status=status.HTTP_200_OK)


class CalendarOAuthDisconnectView(_CalendarBase):
    def post(self, request):
        creds = GoogleCalendarCredentials.objects.filter(user=request.user).first()
        if creds:
            GoogleCalendarOAuthService.revoke(creds)
            creds.delete()
        try:
            from .models import GoogleMailCredentials
            from .oauth_services import GmailOAuthService
            mail_creds = GoogleMailCredentials.objects.filter(user=request.user).first()
            if mail_creds:
                GmailOAuthService.revoke_tokens(mail_creds)
                mail_creds.delete()
        except Exception as e:
            pass
        return Response({"detail": "Google account disconnected."}, status=status.HTTP_200_OK)


class MeetingProvidersStatusView(_CalendarBase):
    """Returns connected & configured status for Google Meet, Zoom, and Microsoft Teams."""
    def get(self, request):
        from .zoom_services import ZoomOAuthService, get_zoom_credentials
        from .microsoft_services import MicrosoftOAuthService, get_microsoft_credentials

        g_conf = GoogleOAuthService.is_configured()
        g_creds = get_calendar_credentials(request.user)

        z_conf = ZoomOAuthService.is_configured()
        z_creds = get_zoom_credentials(request.user)

        ms_conf = MicrosoftOAuthService.is_configured()
        ms_creds = get_microsoft_credentials(request.user)

        return Response({
            'google_meet': {
                'is_connected': bool(g_creds),
                'is_configured': g_conf,
                'email': g_creds.email if g_creds else '',
            },
            'zoom': {
                'is_connected': bool(z_creds),
                'is_configured': z_conf,
                'email': z_creds.email if z_creds else '',
            },
            'ms_teams': {
                'is_connected': bool(ms_creds),
                'is_configured': ms_conf,
                'email': ms_creds.email if ms_creds else '',
            },
        }, status=status.HTTP_200_OK)



class CalendarEventsView(_CalendarBase):
    """
    Fetch events directly from Google Calendar primary calendar for the authenticated user.
    """
    def get(self, request):
        creds = get_calendar_credentials(request.user)
        if not creds:
            return Response({
                "is_connected": False,
                "email": None,
                "events": [],
                "detail": "Google Calendar is not connected."
            }, status=status.HTTP_200_OK)

        time_min = request.query_params.get('time_min')
        time_max = request.query_params.get('time_max')

        try:
            events = list_events(creds, time_min=time_min, time_max=time_max)
            # Annotate events with Market Intel DB Meeting recording information
            from prospects.models import Meeting
            meet_urls = [e['meet_url'] for e in events if e.get('meet_url')]
            event_ids = [e['id'] for e in events if e.get('id')]
            meetings_by_link = {m.meeting_link: m for m in Meeting.objects.filter(meeting_link__in=meet_urls)}
            meetings_by_event = {m.google_event_id: m for m in Meeting.objects.filter(google_event_id__in=event_ids)}
            from .models import CalendarEventRecording
            standalone_by_event = {
                r.event_id: r for r in CalendarEventRecording.objects.filter(user=request.user, event_id__in=event_ids)
            }

            for e in events:
                m = meetings_by_event.get(e.get('id')) or meetings_by_link.get(e.get('meet_url'))
                if not (m and m.recording_file):
                    standalone = standalone_by_event.get(e.get('id'))
                    if standalone:
                        m = standalone
                if m:
                    if isinstance(m, Meeting):
                        e['meeting_id'] = m.id
                    e['recording_file'] = m.recording_file.url if m.recording_file else None
                    e['recording_status'] = m.recording_status
                    e['recording_file_size'] = m.recording_file_size
                    e['recording_downloaded_at'] = m.recording_downloaded_at.isoformat() if m.recording_downloaded_at else None

            return Response({
                "is_connected": True,
                "email": creds.email,
                "events": events,
            }, status=status.HTTP_200_OK)
        except CalendarAuthError as exc:
            return Response({
                "is_connected": False,
                "email": creds.email,
                "events": [],
                "detail": str(exc),
                "reauth_required": True,
            }, status=status.HTTP_200_OK)
        except CalendarError as exc:
            return Response({
                "is_connected": True,
                "email": creds.email,
                "events": [],
                "error": str(exc),
            }, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({
                "is_connected": True,
                "email": creds.email,
                "events": [],
                "error": str(exc),
            }, status=status.HTTP_200_OK)

    def post(self, request):
        """Create a calendar event (with optional Google Meet conference)."""
        creds = get_calendar_credentials(request.user)
        summary = request.data.get('summary') or 'New Event'
        description = request.data.get('description', '')
        start = request.data.get('start')
        end = request.data.get('end')
        meet_url = request.data.get('meet_url')
        attendees = request.data.get('attendees') or []
        color_id = request.data.get('color_id')

        if not start or not end:
            return Response({'error': 'start and end times are required.'}, status=status.HTTP_400_BAD_REQUEST)

        if creds:
            try:
                body = {
                    'summary': summary,
                    'description': description,
                    'start': {'dateTime': start} if 'T' in str(start) else {'date': start},
                    'end': {'dateTime': end} if 'T' in str(end) else {'date': end},
                }
                if color_id:
                    body['colorId'] = str(color_id)
                if attendees:
                    clean_att = []
                    for a in attendees:
                        if isinstance(a, str) and a.strip():
                            clean_att.append({'email': a.strip()})
                        elif isinstance(a, dict) and a.get('email'):
                            clean_att.append(a)
                    if clean_att:
                        body['attendees'] = clean_att

                params = {'sendUpdates': 'all' if attendees else 'none'}
                if meet_url and 'meet.google.com' in meet_url:
                    body['conferenceData'] = {
                        'createRequest': {
                            'requestId': uuid.uuid4().hex,
                            'conferenceSolutionKey': {'type': 'hangoutsMeet'},
                        }
                    }
                    params['conferenceDataVersion'] = 1

                created = _api_request(creds, 'POST', '/calendars/primary/events', body=body, params=params)
                status_meet, extracted_url = extract_conference(created)
                return Response({
                    'success': True,
                    'event': {
                        'id': created.get('id'),
                        'summary': created.get('summary'),
                        'description': created.get('description'),
                        'start': created.get('start', {}).get('dateTime') or created.get('start', {}).get('date'),
                        'end': created.get('end', {}).get('dateTime') or created.get('end', {}).get('date'),
                        'meet_url': extracted_url or meet_url,
                        'html_link': created.get('htmlLink'),
                        'attendees': created.get('attendees', []),
                        'color_id': color_id,
                    }
                }, status=status.HTTP_201_CREATED)
            except Exception as exc:
                return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Fallback for disconnected / local mock
        evt_id = f"evt_{uuid.uuid4().hex[:10]}"
        return Response({
            'success': True,
            'event': {
                'id': evt_id,
                'summary': summary,
                'description': description,
                'start': start,
                'end': end,
                'meet_url': meet_url or f"https://meet.google.com/{uuid.uuid4().hex[:3]}-{uuid.uuid4().hex[:4]}-{uuid.uuid4().hex[:3]}",
                'html_link': 'https://calendar.google.com',
                'attendees': [{'email': a} if isinstance(a, str) else a for a in attendees],
                'color_id': color_id,
            }
        }, status=status.HTTP_201_CREATED)

    def delete(self, request):
        """Delete an event by event_id."""
        event_id = request.query_params.get('event_id') or request.data.get('event_id')
        if not event_id:
            return Response({'error': 'event_id is required.'}, status=status.HTTP_400_BAD_REQUEST)

        creds = get_calendar_credentials(request.user)
        if creds and not event_id.startswith('evt_') and not event_id.startswith('mock_') and not event_id.startswith('sample_'):
            try:
                delete_event(creds, event_id)
            except Exception as exc:
                return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'success': True, 'deleted': event_id}, status=status.HTTP_200_OK)


class GoogleCalendarSyncRecordingView(_CalendarBase):
    """Sync Google Meet audio recording for a calendar event or meet URL."""

    def post(self, request):
        from accounts.google_meet_service import GoogleMeetRestService, extract_meeting_code
        from prospects.models import Meeting, Prospect
        from django.utils import timezone

        meeting_id = request.data.get('meeting_id')
        event_id = request.data.get('event_id')
        meet_url = request.data.get('meet_url')

        meeting = None
        if meeting_id:
            meeting = Meeting.objects.filter(id=meeting_id).first()
        if not meeting and event_id:
            meeting = Meeting.objects.filter(google_event_id=event_id).first()
        if not meeting and meet_url:
            code = extract_meeting_code(meet_url)
            if code:
                meeting = Meeting.objects.filter(meeting_link__icontains=code).first()

        if not meeting:
            if not (event_id and meet_url):
                return Response({'error': 'No meeting found for this event or URL.'}, status=status.HTTP_404_NOT_FOUND)
            from .models import CalendarEventRecording
            meeting, _ = CalendarEventRecording.objects.get_or_create(
                user=request.user, event_id=event_id,
                defaults={'meeting_link': meet_url},
            )
            if not meeting.meeting_link:
                meeting.meeting_link = meet_url
                meeting.save(update_fields=['meeting_link', 'updated_at'])
        elif meeting.google_calendar_owner_id not in (None, request.user.id) and meeting.created_by_id != request.user.id \
                and not request.user.is_superuser:
            return Response({'error': 'Only the meeting host can sync this recording.'}, status=status.HTTP_403_FORBIDDEN)

        res = GoogleMeetRestService.sync_meeting_recording(meeting)
        return Response({
            'success': res.get('success', False),
            'status': res.get('status'),
            'recording_url': meeting.recording_file.url if meeting.recording_file else None,
            'meeting_id': meeting.id if isinstance(meeting, Meeting) else None,
            'detail': res.get('detail') or res.get('error'),
            'file_size': meeting.recording_file_size,
        }, status=status.HTTP_200_OK if res.get('success') else (status.HTTP_202_ACCEPTED if res.get('status') == 'PROCESSING' else status.HTTP_200_OK))


