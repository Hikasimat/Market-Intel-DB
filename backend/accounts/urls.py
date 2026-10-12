from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from .views import UserMeView, UserViewSet, MailAccountViewSet, CookieTokenObtainPairView, CookieTokenRefreshView
from .template_views import EmailTemplateViewSet, EmailSignatureTemplateViewSet

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'mail-account', MailAccountViewSet, basename='mail-account')
router.register(r'email-templates', EmailTemplateViewSet, basename='email-template')
router.register(r'email-signatures', EmailSignatureTemplateViewSet, basename='email-signature')


class LogoutView(APIView):
    """
    Server-side logout endpoint.

    Accepts the refresh token and blacklists it so it cannot be
    used to generate new access tokens. The client should also
    clear its local token storage on logout.

    POST /api/auth/logout/
    Body: { "refresh": "<refresh_token>" }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh") or request.COOKIES.get("refresh_token")
        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning("Logout token blacklist error: %s", exc)

        try:
            from whatsapp.models import WhatsAppAuditLog
            from whatsapp.services import _write_audit_log
            _write_audit_log(
                action=WhatsAppAuditLog.Action.AUTH_LOGOUT,
                performed_by=request.user,
                success=True,
                result_detail="User logged out via /auth/logout/",
            )
        except Exception:
            pass

        response = Response({"detail": "Logged out successfully."}, status=status.HTTP_200_OK)
        response.delete_cookie('access_token')
        response.delete_cookie('refresh_token')
        return response

urlpatterns = [
    path('', include(router.urls)),
    path('login/', CookieTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('refresh/', CookieTokenRefreshView.as_view(), name='token_refresh'),
    path('me/', UserMeView.as_view(), name='user_me'),
    path('logout/', LogoutView.as_view(), name='auth_logout'),
]
