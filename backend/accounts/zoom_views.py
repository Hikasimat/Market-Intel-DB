"""Zoom OAuth endpoints for PRE, LQ, and Manager users."""
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ZoomCredentials
from .serializers import GmailOAuthCallbackSerializer  # reusable {code, state} serializer
from .zoom_services import (
    ZoomAuthError,
    ZoomError,
    ZoomOAuthService,
    get_zoom_credentials,
)


def _can_use_zoom(user):
    if user.is_superuser:
        return True
    profile = getattr(user, 'profile', None)
    return bool(profile and profile.role in ('PRE', 'LQ', 'MANAGER'))


class _ZoomBase(APIView):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if not _can_use_zoom(request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only PRE, Lead Qualifiers and Managers can use Zoom integration.")


class ZoomOAuthURLView(_ZoomBase):
    def get(self, request):
        try:
            url, state = ZoomOAuthService.generate_authorization_url(request.user.id)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({"url": url, "authorization_url": url, "state": state}, status=status.HTTP_200_OK)


class ZoomOAuthCallbackView(_ZoomBase):
    def post(self, request):
        serializer = GmailOAuthCallbackSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        code = serializer.validated_data['code']
        state = serializer.validated_data['state']

        if not ZoomOAuthService.verify_state(state, request.user.id):
            return Response({"detail": "Invalid or expired Zoom authorization state."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            tokens = ZoomOAuthService.exchange_code_for_tokens(code)
            creds = ZoomOAuthService.store_tokens(request.user, tokens)
        except (ValueError, ZoomError) as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Zoom connected successfully.", "email": creds.email},
                        status=status.HTTP_200_OK)


class ZoomOAuthStatusView(_ZoomBase):
    def get(self, request):
        configured = ZoomOAuthService.is_configured()
        creds = get_zoom_credentials(request.user)
        if not creds:
            return Response({"is_connected": False, "is_configured": configured}, status=status.HTTP_200_OK)
        return Response({"is_connected": True, "is_configured": configured, "email": creds.email,
                         "updated_at": creds.updated_at}, status=status.HTTP_200_OK)


class ZoomOAuthDisconnectView(_ZoomBase):
    def post(self, request):
        creds = ZoomCredentials.objects.filter(user=request.user).first()
        if creds:
            ZoomOAuthService.revoke(creds)
            creds.delete()
        return Response({"detail": "Zoom disconnected successfully."}, status=status.HTTP_200_OK)

