"""Optional Google Calendar connection endpoints (separate from Gmail/login)."""
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
)
from .models import GoogleCalendarCredentials
from .oauth_services import GoogleOAuthService
from .serializers import GmailOAuthCallbackSerializer  # plain {code, state} serializer


def _can_use_calendar(user):
    """LQ and MANAGER users (and superusers) may use Calendar; PRE role cannot."""
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    return bool(profile and profile.role in ('LQ', 'MANAGER'))


class _CalendarBase(APIView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not _can_use_calendar(request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only Lead Qualifiers and Managers can use Google Calendar.")


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
            }, status=status.HTTP_502_BAD_GATEWAY)

