"""Microsoft 365 OAuth endpoints for Teams & Outlook Calendar."""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .microsoft_services import (
    MicrosoftAuthError,
    MicrosoftError,
    MicrosoftOAuthService,
    get_microsoft_credentials,
)
from .models import MicrosoftCalendarCredentials
from .serializers import GmailOAuthCallbackSerializer


def _can_use_microsoft(user):
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    return bool(profile and profile.role in ('PRE', 'LQ', 'MANAGER'))


class _MicrosoftBase(APIView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not _can_use_microsoft(request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only PRE, Lead Qualifiers and Managers can use Microsoft integration.")


class MicrosoftOAuthURLView(_MicrosoftBase):
    def get(self, request):
        try:
            url, state = MicrosoftOAuthService.generate_authorization_url(request.user.id)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"url": url, "authorization_url": url, "state": state}, status=status.HTTP_200_OK)


class MicrosoftOAuthCallbackView(_MicrosoftBase):
    def post(self, request):
        serializer = GmailOAuthCallbackSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        code = serializer.validated_data['code']
        state = serializer.validated_data['state']

        if not MicrosoftOAuthService.verify_state(state, request.user.id):
            return Response({"detail": "Invalid or expired Microsoft authorization state."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            tokens = MicrosoftOAuthService.exchange_code_for_tokens(code)
            creds = MicrosoftOAuthService.store_tokens(request.user, tokens)
        except (ValueError, MicrosoftError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Microsoft 365 connected successfully.", "email": creds.email},
                        status=status.HTTP_200_OK)


class MicrosoftOAuthStatusView(_MicrosoftBase):
    def get(self, request):
        configured = MicrosoftOAuthService.is_configured()
        creds = get_microsoft_credentials(request.user)
        if not creds:
            return Response({"is_connected": False, "is_configured": configured}, status=status.HTTP_200_OK)
        return Response({"is_connected": True, "is_configured": configured, "email": creds.email,
                         "updated_at": creds.updated_at}, status=status.HTTP_200_OK)


class MicrosoftOAuthDisconnectView(_MicrosoftBase):
    def post(self, request):
        creds = MicrosoftCalendarCredentials.objects.filter(user=request.user).first()
        if creds:
            MicrosoftOAuthService.revoke(creds)
            creds.delete()
        return Response({"detail": "Microsoft 365 disconnected successfully."}, status=status.HTTP_200_OK)

