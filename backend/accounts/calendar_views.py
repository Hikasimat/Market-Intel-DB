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

