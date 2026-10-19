import socket
import logging
import urllib.parse
from datetime import timedelta
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, BasePermission, AllowAny
from rest_framework import status
from django.shortcuts import redirect

from rest_framework import viewsets
from django.contrib.auth.models import User, update_last_login
from .serializers import (
    UserSerializer,
    EmailTokenObtainPairSerializer,
    GoogleOAuthLoginSerializer,
    GmailOAuthCallbackSerializer,
)
from .permissions import IsPRE, IsLQ as IsLQPerm, IsLQOrManager

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from django.conf import settings
from django.utils import timezone

from .oauth_services import GoogleOAuthService, GmailOAuthService, get_mail_credentials
from .models import GoogleMailCredentials
import utils.encryption as encryption

class LoginThrottle(AnonRateThrottle):
    rate = '5/minute'

class RefreshThrottle(UserRateThrottle):
    rate = '20/minute'
class RefreshAnonThrottle(AnonRateThrottle):
    rate = '20/minute'

def set_jwt_cookies(response, access_token, refresh_token):
    cookie_kwargs = {
        'httponly': True,
        'secure': getattr(settings, 'SESSION_COOKIE_SECURE', False),
        'samesite': getattr(settings, 'SESSION_COOKIE_SAMESITE', 'Lax'),
        'path': '/',
    }
    access_expires = timezone.now() + settings.SIMPLE_JWT['ACCESS_TOKEN_LIFETIME']
    refresh_expires = timezone.now() + settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME']
    
    response.set_cookie('access_token', access_token, expires=access_expires, **cookie_kwargs)
    response.set_cookie('refresh_token', refresh_token, expires=refresh_expires, **cookie_kwargs)
    return response

class CookieTokenObtainPairView(TokenObtainPairView):
    throttle_classes = [LoginThrottle]
    serializer_class = EmailTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        if response.status_code == 200:
            access = response.data.get('access')
            refresh = response.data.get('refresh')
            if access and refresh:
                set_jwt_cookies(response, access, refresh)
                if 'refresh' in response.data:
                    del response.data['refresh']
        return response

class CookieTokenRefreshView(TokenRefreshView):
    throttle_classes = [RefreshAnonThrottle, RefreshThrottle]

    def post(self, request, *args, **kwargs):
        data = request.data.copy() if hasattr(request.data, 'copy') else dict(request.data)
        if 'refresh' not in data:
            cookie_refresh = request.COOKIES.get('refresh_token')
            if cookie_refresh:
                data['refresh'] = cookie_refresh
            else:
                return Response({"detail": "Refresh token missing."}, status=status.HTTP_401_UNAUTHORIZED)
                
        serializer = self.get_serializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
        except InvalidToken as e:
            response = Response({"detail": str(e)}, status=status.HTTP_401_UNAUTHORIZED)
            response.delete_cookie('access_token')
            response.delete_cookie('refresh_token')
            return response

        response = Response(serializer.validated_data, status=status.HTTP_200_OK)
        access = serializer.validated_data.get('access')
        refresh = serializer.validated_data.get('refresh', data.get('refresh'))
        if access:
            set_jwt_cookies(response, access, refresh)
            if 'refresh' in response.data:
                del response.data['refresh']
        return response


class GoogleOAuthURLView(APIView):
    """
    Returns the Google OAuth 2.0 authorization URL for user login.
    Signs and sets an HttpOnly oauth_state cookie to prevent CSRF.
    """
    throttle_classes = [LoginThrottle]

    def get(self, request):
        try:
            url, signed_state = GoogleOAuthService.generate_login_url()
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        response = Response({"url": url, "state": signed_state}, status=status.HTTP_200_OK)
        cookie_kwargs = {
            'httponly': True,
            'secure': getattr(settings, 'SESSION_COOKIE_SECURE', False),
            'samesite': getattr(settings, 'SESSION_COOKIE_SAMESITE', 'Lax'),
            'path': '/',
            'max_age': GoogleOAuthService.STATE_MAX_AGE,
        }
        response.set_cookie('oauth_state', signed_state, **cookie_kwargs)
        return response


class GoogleOAuthLoginView(APIView):
    """
    Exchanges Google authorization code for tokens, verifies the ID token,
    authenticates the matching existing active Django User, and issues SimpleJWT tokens.
    Strictly enforces existing-user-only policy (never creates or provisions users).
    """
    throttle_classes = [LoginThrottle]

    def post(self, request):
        serializer = GoogleOAuthLoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        code = serializer.validated_data['code']
        state = serializer.validated_data['state']

        # Validate OAuth state to prevent CSRF and replay attacks
        cookie_state = request.COOKIES.get('oauth_state')
        if not GoogleOAuthService.verify_state(state, cookie_state):
            response = Response(
                {"detail": "Invalid or expired OAuth state. Please try logging in again."},
                status=status.HTTP_400_BAD_REQUEST
            )
            response.delete_cookie('oauth_state')
            return response

        try:
            token_data = GoogleOAuthService.exchange_code_for_tokens(code)
            id_token_jwt = token_data.get('id_token')
            claims = GoogleOAuthService.verify_id_token(id_token_jwt)
        except ValueError as e:
            response = Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            response.delete_cookie('oauth_state')
            return response

        verified_email = claims['email']
        user, match_status = GoogleOAuthService.find_eligible_user(verified_email)

        if match_status == 'NOT_FOUND':
            response = Response(
                {"detail": "Your Google account is not registered. Please contact your administrator to provision an account."},
                status=status.HTTP_403_FORBIDDEN
            )
            response.delete_cookie('oauth_state')
            return response

        if match_status == 'INACTIVE':
            response = Response(
                {"detail": "This account is inactive. Please contact your administrator."},
                status=status.HTTP_403_FORBIDDEN
            )
            response.delete_cookie('oauth_state')
            return response

        if match_status == 'AMBIGUOUS':
            response = Response(
                {"detail": "Multiple accounts found matching this email. Please contact your administrator."},
                status=status.HTTP_400_BAD_REQUEST
            )
            response.delete_cookie('oauth_state')
            return response

        # Eligible existing user -> issue SimpleJWT tokens
        if getattr(settings, 'SIMPLE_JWT', {}).get('UPDATE_LAST_LOGIN', True):
            update_last_login(None, user)

        try:
            GmailOAuthService.store_tokens_from_login(user, token_data, verified_email)
        except Exception:
            pass

        refresh = RefreshToken.for_user(user)
        access = str(refresh.access_token)

        response = Response({"access": access}, status=status.HTTP_200_OK)
        set_jwt_cookies(response, access, str(refresh))
        response.delete_cookie('oauth_state')
        return response


class GoogleOAuthCallbackView(APIView):
    """
    Handles direct backend redirects from Google (GET /api/auth/google/callback/).
    Establishes the session via HttpOnly cookies and redirects to frontend.
    Never exposes JWT tokens in query strings.
    """
    throttle_classes = [LoginThrottle]

    def get(self, request):
        error = request.query_params.get('error')
        if error:
            frontend_err = f"{settings.FRONTEND_URL}/login?oauth_error={urllib.parse.quote(error)}"
            response = redirect(frontend_err)
            response.delete_cookie('oauth_state')
            return response

        code = request.query_params.get('code')
        state = request.query_params.get('state')

        if not code or not state:
            frontend_err = f"{settings.FRONTEND_URL}/login?oauth_error={urllib.parse.quote('Missing authorization code or state.')}"
            response = redirect(frontend_err)
            response.delete_cookie('oauth_state')
            return response

        cookie_state = request.COOKIES.get('oauth_state')
        if not GoogleOAuthService.verify_state(state, cookie_state):
            frontend_err = f"{settings.FRONTEND_URL}/login?oauth_error={urllib.parse.quote('Invalid or expired OAuth state.')}"
            response = redirect(frontend_err)
            response.delete_cookie('oauth_state')
            return response

        try:
            token_data = GoogleOAuthService.exchange_code_for_tokens(code)
            id_token_jwt = token_data.get('id_token')
            claims = GoogleOAuthService.verify_id_token(id_token_jwt)
        except ValueError as e:
            frontend_err = f"{settings.FRONTEND_URL}/login?oauth_error={urllib.parse.quote(str(e))}"
            response = redirect(frontend_err)
            response.delete_cookie('oauth_state')
            return response

        verified_email = claims['email']
        user, match_status = GoogleOAuthService.find_eligible_user(verified_email)

        if match_status == 'NOT_FOUND':
            msg = "Your Google account is not registered. Please contact your administrator to provision an account."
            frontend_err = f"{settings.FRONTEND_URL}/login?oauth_error={urllib.parse.quote(msg)}"
            response = redirect(frontend_err)
            response.delete_cookie('oauth_state')
            return response

        if match_status == 'INACTIVE':
            msg = "This account is inactive. Please contact your administrator."
            frontend_err = f"{settings.FRONTEND_URL}/login?oauth_error={urllib.parse.quote(msg)}"
            response = redirect(frontend_err)
            response.delete_cookie('oauth_state')
            return response

        if match_status == 'AMBIGUOUS':
            msg = "Multiple accounts found matching this email. Please contact your administrator."
            frontend_err = f"{settings.FRONTEND_URL}/login?oauth_error={urllib.parse.quote(msg)}"
            response = redirect(frontend_err)
            response.delete_cookie('oauth_state')
            return response

        if getattr(settings, 'SIMPLE_JWT', {}).get('UPDATE_LAST_LOGIN', True):
            update_last_login(None, user)

        try:
            GmailOAuthService.store_tokens_from_login(user, token_data, verified_email)
        except Exception:
            pass

        refresh = RefreshToken.for_user(user)
        access = str(refresh.access_token)

        success_url = f"{settings.FRONTEND_URL}/login?oauth_success=1"
        response = redirect(success_url)
        set_jwt_cookies(response, access, str(refresh))
        response.delete_cookie('oauth_state')
        return response


class GmailOAuthURLView(APIView):
    """
    Generates OAuth authorization URL specifically for Gmail mailbox permissions.
    Protected: User must already be authenticated in the application and have LQ or Manager role.
    """
    permission_classes = [IsLQOrManager]

    def get(self, request):
        try:
            url, state = GmailOAuthService.generate_authorization_url(request.user.id)
            response = Response({"url": url, "state": state}, status=status.HTTP_200_OK)
            cookie_kwargs = {
                'httponly': True,
                'secure': getattr(settings, 'SESSION_COOKIE_SECURE', False),
                'samesite': getattr(settings, 'SESSION_COOKIE_SAMESITE', 'Lax'),
                'path': '/',
                'max_age': GmailOAuthService.STATE_MAX_AGE,
            }
            response.set_cookie('gmail_oauth_state', state, **cookie_kwargs)
            return response
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)


class GmailOAuthCallbackView(APIView):
    """
    Exchanges authorization code for Gmail access & refresh tokens.
    Persists tokens encrypted at rest via GoogleMailCredentials.
    Supports both POST (from frontend callback handler) and GET (direct redirect from Google).
    """
    permission_classes = [AllowAny]

    def post(self, request):
        if not request.user or not request.user.is_authenticated:
            return Response({"detail": "Authentication credentials were not provided."}, status=status.HTTP_401_UNAUTHORIZED)

        serializer = GmailOAuthCallbackSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        code = serializer.validated_data['code']
        state = serializer.validated_data['state']

        if not GmailOAuthService.verify_state(state, request.user.id):
            return Response({"detail": "Invalid or expired Gmail OAuth state."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            tokens = GmailOAuthService.exchange_code_for_tokens(code)
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        access_token = tokens.get('access_token')
        refresh_token = tokens.get('refresh_token', '')
        expires_in = tokens.get('expires_in', 3600)
        scope = tokens.get('scope', '')
        id_token_jwt = tokens.get('id_token')

        gmail_email = request.user.email
        if id_token_jwt:
            try:
                claims = GoogleOAuthService.verify_id_token(id_token_jwt)
                gmail_email = claims.get('email', gmail_email)
            except Exception:
                pass

        if not access_token:
            return Response({"detail": "Failed to receive access token from Google."}, status=status.HTTP_400_BAD_REQUEST)

        creds, _ = GoogleMailCredentials.objects.get_or_create(user=request.user)
        creds.email = gmail_email
        creds.access_token_encrypted = encryption.encrypt_password(access_token)
        if refresh_token:
            creds.refresh_token_encrypted = encryption.encrypt_password(refresh_token)
        creds.token_expiry = timezone.now() + timedelta(seconds=expires_in)
        creds.scopes = scope
        creds.is_active = True
        creds.save()

        # Seamlessly sync active GoogleCalendarCredentials
        try:
            from .models import GoogleCalendarCredentials
            cal_creds, _ = GoogleCalendarCredentials.objects.get_or_create(user=request.user)
            cal_creds.email = gmail_email
            cal_creds.access_token_encrypted = encryption.encrypt_password(access_token)
            if refresh_token:
                cal_creds.refresh_token_encrypted = encryption.encrypt_password(refresh_token)
            cal_creds.token_expiry = timezone.now() + timedelta(seconds=expires_in)
            cal_creds.scopes = scope
            cal_creds.is_active = True
            cal_creds.save()
        except Exception as e:
            logger.warning("Could not sync GoogleCalendarCredentials on Gmail callback: %s", e)

        response = Response({
            "detail": "Gmail connected successfully.",
            "email": gmail_email,
            "scopes": scope.split() if scope else [],
        }, status=status.HTTP_200_OK)
        response.delete_cookie('gmail_oauth_state')
        return response

    def get(self, request):
        error = request.query_params.get('error')
        if error:
            return redirect(f"{settings.FRONTEND_URL}/inbox?gmail_error={urllib.parse.quote(error)}")

        code = request.query_params.get('code')
        state = request.query_params.get('state')
        if not code or not state:
            return redirect(f"{settings.FRONTEND_URL}/inbox?gmail_error={urllib.parse.quote('Missing authorization code or state.')}")

        user = request.user if (request.user and request.user.is_authenticated) else None
        if not user:
            # Decode user from signed state
            from django.core.signing import TimestampSigner
            signer = TimestampSigner(salt='gmail_oauth')
            try:
                state_data_raw = signer.unsign(state, max_age=GmailOAuthService.STATE_MAX_AGE)
                state_data = json.loads(state_data_raw)
                uid = state_data.get('user_id')
                user = User.objects.get(id=uid)
            except Exception:
                return redirect(f"{settings.FRONTEND_URL}/inbox?gmail_error={urllib.parse.quote('Invalid or expired Gmail state.')}")
        else:
            if not GmailOAuthService.verify_state(state, user.id):
                return redirect(f"{settings.FRONTEND_URL}/inbox?gmail_error={urllib.parse.quote('Invalid or expired Gmail state.')}")

        try:
            tokens = GmailOAuthService.exchange_code_for_tokens(code)
            access_token = tokens.get('access_token')
            refresh_token = tokens.get('refresh_token', '')
            expires_in = tokens.get('expires_in', 3600)
            scope = tokens.get('scope', '')
            id_token_jwt = tokens.get('id_token')

            gmail_email = user.email
            if id_token_jwt:
                try:
                    claims = GoogleOAuthService.verify_id_token(id_token_jwt)
                    gmail_email = claims.get('email', gmail_email)
                except Exception:
                    pass

            creds, _ = GoogleMailCredentials.objects.get_or_create(user=user)
            creds.email = gmail_email
            creds.access_token_encrypted = encryption.encrypt_password(access_token)
            if refresh_token:
                creds.refresh_token_encrypted = encryption.encrypt_password(refresh_token)
            creds.token_expiry = timezone.now() + timedelta(seconds=expires_in)
            creds.scopes = scope
            creds.is_active = True
            creds.save()

            response = redirect(f"{settings.FRONTEND_URL}/inbox?gmail_connected=1")
            response.delete_cookie('gmail_oauth_state')
            return response
        except Exception as exc:
            return redirect(f"{settings.FRONTEND_URL}/inbox?gmail_error={urllib.parse.quote(str(exc))}")


class GmailOAuthStatusView(APIView):
    """
    Returns connection status and authorized email for Gmail without exposing tokens.
    """
    permission_classes = [IsLQOrManager]

    def get(self, request):
        creds = get_mail_credentials(request.user)
        if not creds:
            return Response({"is_connected": False}, status=status.HTTP_200_OK)

        return Response({
            "is_connected": True,
            "email": creds.email,
            "scopes": creds.scopes.split() if creds.scopes else [],
            "token_expiry": creds.token_expiry,
            "updated_at": creds.updated_at,
        }, status=status.HTTP_200_OK)


class GmailOAuthDisconnectView(APIView):
    """
    Safely disconnects Google OAuth credentials (both mail and calendar) for the current user.
    """
    permission_classes = [IsLQOrManager]

    def post(self, request):
        creds = GoogleMailCredentials.objects.filter(user=request.user).first()
        if creds:
            GmailOAuthService.revoke_tokens(creds)
            creds.delete()
        try:
            from .models import GoogleCalendarCredentials
            from .calendar_services import GoogleCalendarOAuthService
            cal_creds = GoogleCalendarCredentials.objects.filter(user=request.user).first()
            if cal_creds:
                GoogleCalendarOAuthService.revoke(cal_creds)
                cal_creds.delete()
        except Exception:
            pass
        return Response({"detail": "Google authorization disconnected successfully."}, status=status.HTTP_200_OK)


class IsSuperUser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_superuser)

class IsManagerUser(BasePermission):
    """Allows Manager role."""
    def has_permission(self, request, view):
        if request.user and request.user.is_superuser:
            return True
        return bool(
            request.user and
            request.user.is_authenticated and
            hasattr(request.user, 'profile') and
            request.user.profile.role == 'MANAGER'
        )

class UserMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        profile = getattr(user, 'profile', None)
        # Include WhatsApp sessions owned by this user (for session selector).
        whatsapp_sessions = []
        try:
            from whatsapp.models import WhatsAppSession
            sessions = WhatsAppSession.objects.filter(
                owner=user, is_active=True
            ).values('id', 'session_name', 'status', 'phone_number').order_by('-last_used_at', '-created_at')[:10]
            whatsapp_sessions = list(sessions)
        except Exception:
            pass  # WhatsApp may not be configured; degrade gracefully.

        return Response({
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'role': profile.role if profile else 'PRE',
            'timezone': profile.timezone if profile else 'UTC',
            'is_superuser': user.is_superuser,
            'whatsapp_sessions': whatsapp_sessions,
        })

    def patch(self, request):
        user = request.user
        profile = getattr(user, 'profile', None)
        if not profile:
            from .models import UserProfile
            profile = UserProfile.objects.create(user=user)
        
        timezone_val = request.data.get('timezone')
        if timezone_val:
            import zoneinfo
            try:
                zoneinfo.ZoneInfo(timezone_val)
                profile.timezone = timezone_val
                profile.save(update_fields=['timezone'])
            except Exception:
                from rest_framework import status
                return Response({'error': 'Invalid timezone'}, status=status.HTTP_400_BAD_REQUEST)
        
        return Response({'status': 'updated', 'timezone': profile.timezone})

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().select_related('profile').order_by('-date_joined')
    serializer_class = UserSerializer

    def get_permissions(self):
        """
        Superuser: full CRUD.
        Manager: full CRUD (but restricted from handling superusers in methods).
        Others: 403.
        """
        return [IsAuthenticated(), IsManagerUser()]

    def create(self, request, *args, **kwargs):
        # Prevent Manager from creating a superuser
        user = request.user
        is_manager = (
            not user.is_superuser and
            hasattr(user, 'profile') and
            user.profile.role == 'MANAGER'
        )
        if is_manager:
            # Block is_superuser or is_staff from Manager-created users
            if request.data.get('is_superuser') or request.data.get('is_staff'):
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("Managers cannot create superuser or staff accounts.")
            # Strip those fields from data safely
            data = request.data.copy()
            data.pop('is_superuser', None)
            data.pop('is_staff', None)
            # Use mutable copy
            request._full_data = data
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        # Ensure Manager-created users are never superusers
        user = self.request.user
        is_manager = (
            not user.is_superuser and
            hasattr(user, 'profile') and
            user.profile.role == 'MANAGER'
        )
        if is_manager:
            serializer.save(is_superuser=False, is_staff=False)
        else:
            serializer.save()

    def update(self, request, *args, **kwargs):
        # Prevent Manager from editing a superuser or making someone a superuser
        user = request.user
        is_manager = (
            not user.is_superuser and
            hasattr(user, 'profile') and
            user.profile.role == 'MANAGER'
        )
        if is_manager:
            instance = self.get_object()
            if instance.is_superuser:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("Managers cannot edit superuser accounts.")
            
            if request.data.get('is_superuser') or request.data.get('is_staff'):
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("Managers cannot grant superuser or staff status.")
                
            data = request.data.copy()
            data.pop('is_superuser', None)
            data.pop('is_staff', None)
            request._full_data = data
            
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        # Prevent Manager from deleting ANY user account
        user = request.user
        is_manager = (
            not user.is_superuser and
            hasattr(user, 'profile') and
            user.profile.role == 'MANAGER'
        )
        if is_manager:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Managers are not allowed to delete user accounts.")
        return super().destroy(request, *args, **kwargs)
class _SuperOrManager(BasePermission):
    """Allows superuser or Manager role."""
    def has_permission(self, request, view):
        if request.user and request.user.is_superuser:
            return True
        return bool(
            request.user and
            request.user.is_authenticated and
            hasattr(request.user, 'profile') and
            request.user.profile.role == 'MANAGER'
        )


from rest_framework.decorators import action
from rest_framework import status
import email
from email.header import decode_header
import re
import time

class IsLQ(IsLQPerm):
    """Local alias so the rest of this module can reference IsLQ directly."""
    pass

class GmailMailboxViewSet(viewsets.ViewSet):
    """Gmail mailbox endpoints (read, send, drafts, labels) for LQ and Manager users."""
    permission_classes = [IsLQOrManager]


    @action(detail=False, methods=['get'], url_path='fetch-emails')
    def fetch_emails(self, request):
        """
        Fetch email metadata from the signed-in user's Gmail mailbox.

        Query params:
            folder (str): INBOX, STARRED, SENT, DRAFT, SPAM or TRASH (default INBOX)
            limit (int): maximum messages to return (newest first), default 20
            search (str): Gmail search query
        """
        google_creds = get_mail_credentials(request.user)
        if not google_creds:
            return Response(
                {'error': 'Gmail is not connected. Please sign in with Google or connect Gmail.', 'messages': []},
                status=status.HTTP_400_BAD_REQUEST,
            )

        search = request.query_params.get('search', '').strip()
        folder = request.query_params.get('folder', 'INBOX')
        limit = int(request.query_params.get('limit', 20))

        try:
            res = GmailOAuthService.fetch_messages(google_creds, folder=folder, limit=limit, search=search, user=request.user)
            return Response(res, status=status.HTTP_200_OK)
        except Exception as e:
            logging.getLogger(__name__).warning("Gmail fetch_messages error: %s", e)
            return Response({'error': str(e), 'messages': []}, status=status.HTTP_502_BAD_GATEWAY)

    @action(detail=False, methods=['get'], url_path='prospect-responses')
    def prospect_responses(self, request):
        """
        Fetch incoming email messages from authorized prospects and key contacts.
        Uses Gmail server-side search querying known prospect addresses,
        applies canonical ProspectMatcher, and returns matched responses.
        """
        google_creds = get_mail_credentials(request.user)
        if not google_creds:
            return Response(
                {'error': 'Gmail is not connected. Please connect Gmail.', 'messages': [], 'emails': [], 'total': 0},
                status=status.HTTP_400_BAD_REQUEST,
            )

        limit = min(int(request.query_params.get('limit', 25)), 50)
        user_search = request.query_params.get('search', '').strip()

        from prospects.matching_service import ProspectMatcher
        matcher = ProspectMatcher(request.user)
        candidate_emails = matcher.get_authorized_candidate_emails()

        if not candidate_emails:
            # Current user has no accessible prospects with email addresses
            return Response({'messages': [], 'emails': [], 'total': 0, 'partial': False}, status=status.HTTP_200_OK)

        # Batch candidate emails into Gmail query:
        # e.g., "from:(email1 OR email2 ...) -in:sent -in:trash -in:draft"
        query_emails = candidate_emails[:50]
        from_clause = " OR ".join(query_emails)
        gmail_query = f"from:({from_clause}) -in:sent -in:trash -in:draft"
        if user_search:
            gmail_query += f" {user_search}"

        try:
            res = GmailOAuthService.fetch_messages(
                google_creds,
                folder='ALL',
                limit=limit,
                search=gmail_query,
                user=request.user,
                matcher=matcher,
            )
            raw_messages = res.get('messages', [])
            # Only keep messages where prospect_match is True
            matched_messages = [m for m in raw_messages if m.get('prospect_match')]
            return Response({
                'messages': matched_messages,
                'emails': matched_messages,
                'total': len(matched_messages),
                'partial': res.get('partial', False),
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logging.getLogger(__name__).warning("Gmail prospect_responses error: %s", e)
            return Response({'error': str(e), 'messages': [], 'emails': [], 'total': 0}, status=status.HTTP_502_BAD_GATEWAY)

    @action(detail=False, methods=['post'], url_path='send-email')
    def send_email_action(self, request):
        user = request.user
        google_creds = get_mail_credentials(user)
        if not google_creds:
            return Response({'error': 'Gmail is not connected. Please sign in with Google or connect Gmail.'}, status=status.HTTP_400_BAD_REQUEST)

        to_address = request.data.get('to')
        cc_address = request.data.get('cc')
        bcc_address = request.data.get('bcc')
        subject = request.data.get('subject', '')
        body = request.data.get('body', '')

        from prospects.email_composition import (
            format_sender_address,
            validate_and_sanitize_recipient,
            set_singleton_header,
            extract_domain_from_email,
        )

        def _parse_addrs(val):
            if not val:
                return []
            if any(c in str(val) for c in ('\r', '\n', '\x00')):
                raise ValueError("Recipient address contains invalid control characters or newlines.")
            if isinstance(val, list):
                raw_items = val
            elif isinstance(val, str) and val.strip().startswith('['):
                import json
                try:
                    parsed = json.loads(val)
                    raw_items = parsed if isinstance(parsed, list) else [val]
                except Exception:
                    raw_items = [val]
            else:
                raw_items = str(val).replace(';', ',').split(',')

            import email.utils
            extracted = []
            for item in raw_items:
                item_str = str(item).strip()
                if not item_str:
                    continue
                if any(c in item_str for c in ('\r', '\n', '\x00')):
                    raise ValueError("Recipient address contains invalid control characters or newlines.")
                parsed_list = email.utils.getaddresses([item_str])
                if not parsed_list or not any(addr for _, addr in parsed_list):
                    raise ValueError(f"Malformed recipient address: {item_str!r}")
                for _, addr in parsed_list:
                    addr_clean = addr.strip()
                    if addr_clean:
                        validated = validate_and_sanitize_recipient(addr_clean)
                        if validated.lower() not in [e.lower() for e in extracted]:
                            extracted.append(validated)
            return extracted

        try:
            to_list = _parse_addrs(to_address)
            cc_list = [c for c in _parse_addrs(cc_address) if c.lower() not in [t.lower() for t in to_list]]
            bcc_list = [b for b in _parse_addrs(bcc_address) if b.lower() not in [t.lower() for t in to_list] and b.lower() not in [c.lower() for c in cc_list]]
        except ValueError as exc:
            return Response({'error': f'Invalid recipient: {exc}'}, status=status.HTTP_400_BAD_REQUEST)

        if not to_list:
            return Response({'error': 'To address is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Optional saved template / signature
        template_id = request.data.get('template_id') or None
        signature_id = request.data.get('signature_id') or None
        composed = None
        if template_id or signature_id:
            from accounts.template_utils import build_email_content, ComposeError, sender_from_user
            try:
                composed = build_email_content(
                    user, sender_from_user(user), None, to_list + cc_list, subject, body,
                    template_id=template_id, signature_id=signature_id,
                    body_edited=str(request.data.get('body_edited', 'true')).lower() != 'false',
                )
                subject = composed['subject'] or subject
                body = composed['text_body']
            except (ComposeError, ValueError) as exc:
                return Response({'error': str(exc) or 'Invalid template or signature.'}, status=status.HTTP_400_BAD_REQUEST)

        sender_email = google_creds.email
        sender_display_name = user.get_full_name() or user.username
        effective_signature = f"--\n{sender_display_name}\n{sender_email}"

        if composed and composed['has_signature']:
            effective_signature = composed['signature_text']

        full_body = body
        if effective_signature:
            full_body += f"\n\n{effective_signature}"

        from email.message import EmailMessage
        from email.utils import make_msgid, formatdate
        import html

        email_domain = extract_domain_from_email(sender_email)
        msg = EmailMessage()

        try:
            from_header_val = format_sender_address(sender_display_name, sender_email)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        set_singleton_header(msg, 'From', from_header_val)
        reply_to_requested = request.data.get('reply_to')
        if reply_to_requested and reply_to_requested.strip() and reply_to_requested.strip().lower() != sender_email.lower():
            set_singleton_header(msg, 'Reply-To', reply_to_requested.strip())
        set_singleton_header(msg, 'Date', formatdate(localtime=True))
        set_singleton_header(msg, 'Subject', subject or '')
        set_singleton_header(msg, 'To', ', '.join(to_list))
        if cc_list:
            set_singleton_header(msg, 'Cc', ', '.join(cc_list))
        if bcc_list:
            set_singleton_header(msg, 'Bcc', ', '.join(bcc_list))

        # Open tracking: opt-in per email AND permitted by EMAIL_OPEN_TRACKING_ENABLED.
        # A missing request value means NOT tracked (decided server-side).
        import uuid
        from django.conf import settings
        from django.utils import timezone
        from prospects.tracking_utils import (
            parse_bool,
            global_open_tracking_enabled,
            validate_tracking_configuration,
            build_tracking_pixel_html,
            strip_application_tracking_markup,
        )
        requested_tracking = parse_bool(request.data.get('open_tracking_enabled'))
        if requested_tracking and global_open_tracking_enabled():
            valid_cfg, cfg_err = validate_tracking_configuration()
            if not valid_cfg:
                return Response({
                    'error': f'Cannot send tracked email: {cfg_err} Either configure a valid public HTTPS EMAIL_TRACKING_BASE_URL or disable open tracking for this message.'
                }, status=status.HTTP_400_BAD_REQUEST)
            open_tracking_enabled = True
        else:
            open_tracking_enabled = False

        tracking_token = uuid.uuid4()

        set_singleton_header(msg, 'Message-ID', make_msgid(domain=email_domain))
        msg.set_content(full_body)

        # HTML alternative
        html_body = html.escape(body).replace('\n', '<br>')
        from accounts.template_utils import clean_and_embed_signature_html

        if composed and composed['has_template'] and composed['html_body']:
            main_html = composed['html_body']
        else:
            main_html = f'<div style="font-family: sans-serif;">{html_body}</div>'

        if composed and composed['has_signature']:
            html_signature = composed['signature_html']
        else:
            html_signature = f'<div style="color:#64748b;font-size:13px;line-height:1.5;">--<br><strong style="color:#1e293b;">{html.escape(sender_display_name)}</strong><br>{html.escape(sender_email)}</div>'

        integrated_body = clean_and_embed_signature_html(main_html, html_signature)
        raw_html_content = f"<html><body>\n{integrated_body}\n</body></html>"

        # Strip any stale application-owned tracking images or verified communication badges
        cleaned_html = strip_application_tracking_markup(raw_html_content)

        # Inject single tracking pixel only if open tracking is authorized and enabled
        if open_tracking_enabled:
            tracking_pixel = f"\n{build_tracking_pixel_html(tracking_token)}\n"
            if '</body>' in cleaned_html:
                html_content = cleaned_html.replace('</body>', f'{tracking_pixel}</body>', 1)
            else:
                html_content = f'{cleaned_html}{tracking_pixel}'
        else:
            html_content = cleaned_html

        from accounts.template_utils import convert_base64_images_to_cid
        html_content, inline_images = convert_base64_images_to_cid(html_content, domain=email_domain)
        msg.add_alternative(html_content, subtype='html')

        if inline_images:
            html_part = next((p for p in msg.iter_parts() if p.get_content_type() == 'text/html'), None)
            if html_part:
                for cid, subtype, img_bytes in inline_images:
                    html_part.add_related(img_bytes, maintype='image', subtype=subtype, cid=f'<{cid}>')

        # Handle Attachments
        files = request.FILES.getlist('attachments')
        total_size = sum(f.size for f in files)
        if total_size > 25 * 1024 * 1024:
            return Response({'error': 'Total attachment size exceeds 25MB limit.'}, status=status.HTTP_400_BAD_REQUEST)

        import mimetypes
        for f in files:
            if f.size > 10 * 1024 * 1024:
                return Response({'error': f'File {f.name} exceeds 10MB limit.'}, status=status.HTTP_400_BAD_REQUEST)
            ext = f.name.split('.')[-1].lower() if '.' in f.name else ''
            if ext in ['exe', 'bat', 'cmd', 'js', 'ps1', 'vbs', 'scr']:
                return Response({'error': f'File type .{ext} is not allowed.'}, status=status.HTTP_400_BAD_REQUEST)
            mtype, _ = mimetypes.guess_type(f.name)
            maintype, subtype = (mtype.split('/', 1)) if (mtype and '/' in mtype) else ('application', 'octet-stream')
            msg.add_attachment(f.read(), maintype=maintype, subtype=subtype, filename=f.name)
            f.seek(0)

        thread_id = request.data.get('thread_id')
        draft_id = request.data.get('draft_id')

        def send_via_gmail():
            try:
                GmailOAuthService.send_message(google_creds, msg.as_bytes(), thread_id=thread_id)
                if draft_id:
                    try:
                        GmailOAuthService.delete_draft(google_creds, draft_id)
                    except Exception:
                        pass
            except Exception as e:
                import logging
                logging.getLogger(__name__).error("Background Gmail send failed: %s", e)

        import threading
        t = threading.Thread(target=send_via_gmail)
        t.start()

        # Create OutreachEmail tracking record for inbox email
        matched_prospect = None
        from prospects.models import OutreachEmail, Prospect, ProspectContact, OutreachEmailRecipient
        contact = ProspectContact.objects.filter(official_email__in=[t.lower() for t in to_list]).select_related('prospect').first()
        if contact and contact.prospect:
            matched_prospect = contact.prospect
        else:
            matched_prospect = Prospect.objects.filter(official_email_address__in=[t.lower() for t in to_list]).first()

        cf_ip = request.META.get('HTTP_CF_CONNECTING_IP')
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        sender_ip = cf_ip or (x_forwarded_for.split(',')[0].strip() if x_forwarded_for else request.META.get('REMOTE_ADDR', ''))

        outreach_email = OutreachEmail.objects.create(
            prospect=matched_prospect,
            created_by=user,
            from_email=sender_email,
            from_name=sender_display_name,
            subject=subject,
            body=body,
            signature=effective_signature,
            status='SENT',
            sent_at=timezone.now(),
            message_id=str(msg['Message-ID']),
            tracking_token=tracking_token,
            open_tracking_enabled=open_tracking_enabled,
            references=f"sender_ip:{sender_ip}"
        )

        for addr in to_list:
            OutreachEmailRecipient.objects.create(outreach_email=outreach_email, email_address=addr, recipient_type='TO')
        for addr in cc_list:
            OutreachEmailRecipient.objects.create(outreach_email=outreach_email, email_address=addr, recipient_type='CC')
        for addr in bcc_list:
            OutreachEmailRecipient.objects.create(outreach_email=outreach_email, email_address=addr, recipient_type='BCC')

        if matched_prospect:
            from prospects.models import CommunicationActivity
            CommunicationActivity.objects.create(
                prospect=matched_prospect,
                prospect_contact=contact if (contact and contact.prospect_id == matched_prospect.id) else None,
                performed_by=user,
                activity_type='EMAIL_SENT',
                direction='OUTBOUND',
                outreach_email=outreach_email,
                notes=f"Email sent from Inbox to {', '.join(to_list)}\nSubject: {subject}\n\n{body}"
            )

        return Response({
            'success': True,
            'tracking_id': outreach_email.id,
            'tracking_token': str(tracking_token),
            'open_tracking_enabled': open_tracking_enabled,
        })

    @action(detail=False, methods=['get'], url_path='fetch-email-body')
    def fetch_email_body(self, request):
        """
        Fetch the full body of a single Gmail message.

        Query params:
            uid (str): Gmail message id (preferred)
            email_id (str): legacy alias for uid
        """
        google_creds = get_mail_credentials(request.user)
        if not google_creds:
            return Response({'error': 'Gmail is not connected.'}, status=status.HTTP_400_BAD_REQUEST)

        uid = request.query_params.get('uid') or request.query_params.get('email_id')
        if not uid:
            return Response({'error': 'uid is required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            body_data = GmailOAuthService.fetch_message_body(google_creds, uid)
            return Response(body_data, status=status.HTTP_200_OK)
        except Exception as e:
            logging.getLogger(__name__).warning("Gmail fetch_message_body error: %s", e)
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['post'], url_path='modify-message')
    def modify_message(self, request):
        user = request.user
        google_creds = get_mail_credentials(user)
        if not google_creds:
            return Response({'error': 'Google Mail credentials not found.'}, status=status.HTTP_400_BAD_REQUEST)

        msg_id = request.data.get('msg_id') or request.data.get('id') or request.data.get('uid')
        act = request.data.get('action')  # 'star', 'unstar', 'read', 'unread', 'spam', 'unspam'
        if not msg_id or not act:
            return Response({'error': 'msg_id and action are required.'}, status=status.HTTP_400_BAD_REQUEST)

        add_labels = []
        remove_labels = []
        if act == 'star':
            add_labels = ['STARRED']
        elif act == 'unstar':
            remove_labels = ['STARRED']
        elif act == 'read':
            remove_labels = ['UNREAD']
        elif act == 'unread':
            add_labels = ['UNREAD']
        elif act == 'spam':
            add_labels = ['SPAM']
            remove_labels = ['INBOX']
        elif act == 'unspam':
            remove_labels = ['SPAM']
            add_labels = ['INBOX']
        else:
            return Response({'error': f'Unsupported action: {act}'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            res = GmailOAuthService.modify_message(google_creds, msg_id, add_label_ids=add_labels, remove_label_ids=remove_labels)
            return Response({'success': True, 'data': res}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='trash-message')
    def trash_message(self, request):
        user = request.user
        google_creds = get_mail_credentials(user)
        if not google_creds:
            return Response({'error': 'Google Mail credentials not found.'}, status=status.HTTP_400_BAD_REQUEST)
        msg_id = request.data.get('msg_id') or request.data.get('id') or request.data.get('uid')
        if not msg_id:
            return Response({'error': 'msg_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            res = GmailOAuthService.trash_message(google_creds, msg_id)
            return Response({'success': True, 'data': res}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='untrash-message')
    def untrash_message(self, request):
        user = request.user
        google_creds = get_mail_credentials(user)
        if not google_creds:
            return Response({'error': 'Google Mail credentials not found.'}, status=status.HTTP_400_BAD_REQUEST)
        msg_id = request.data.get('msg_id') or request.data.get('id') or request.data.get('uid')
        if not msg_id:
            return Response({'error': 'msg_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            res = GmailOAuthService.untrash_message(google_creds, msg_id)
            return Response({'success': True, 'data': res}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='delete-message')
    def delete_message(self, request):
        user = request.user
        google_creds = get_mail_credentials(user)
        if not google_creds:
            return Response({'error': 'Google Mail credentials not found.'}, status=status.HTTP_400_BAD_REQUEST)
        msg_id = request.data.get('msg_id') or request.data.get('id') or request.data.get('uid')
        if not msg_id:
            return Response({'error': 'msg_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            res = GmailOAuthService.delete_message(google_creds, msg_id)
            return Response({'success': True, 'data': res}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='save-draft')
    def save_draft(self, request):
        user = request.user
        google_creds = get_mail_credentials(user)
        if not google_creds:
            return Response({'error': 'Google Mail credentials not found.'}, status=status.HTTP_400_BAD_REQUEST)

        to_address = request.data.get('to', '')
        cc_address = request.data.get('cc', '')
        bcc_address = request.data.get('bcc', '')
        subject = request.data.get('subject', '')
        body = request.data.get('body', '')
        draft_id = request.data.get('draft_id')
        thread_id = request.data.get('thread_id')

        from email.message import EmailMessage
        from email.utils import make_msgid, formatdate
        from prospects.email_composition import (
            format_sender_address,
            set_singleton_header,
            extract_domain_from_email,
        )
        import html

        sender_email = google_creds.email
        sender_display_name = user.get_full_name() or user.username
        msg = EmailMessage()

        try:
            from_header_val = format_sender_address(sender_display_name, sender_email)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        set_singleton_header(msg, 'From', from_header_val)
        set_singleton_header(msg, 'Date', formatdate(localtime=True))
        set_singleton_header(msg, 'Subject', subject or '')
        if to_address:
            set_singleton_header(msg, 'To', to_address)
        if cc_address:
            set_singleton_header(msg, 'Cc', cc_address)
        if bcc_address:
            set_singleton_header(msg, 'Bcc', bcc_address)

        email_domain = extract_domain_from_email(sender_email)
        set_singleton_header(msg, 'Message-ID', make_msgid(domain=email_domain))
        msg.set_content(body)

        html_body = html.escape(body).replace('\n', '<br>')
        msg.add_alternative(f'<div style="font-family: sans-serif;">{html_body}</div>', subtype='html')

        try:
            res = GmailOAuthService.save_draft(google_creds, msg.as_bytes(), draft_id=draft_id, thread_id=thread_id)
            return Response({'success': True, 'draft': res}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='delete-draft')
    def delete_draft(self, request):
        user = request.user
        google_creds = get_mail_credentials(user)
        if not google_creds:
            return Response({'error': 'Google Mail credentials not found.'}, status=status.HTTP_400_BAD_REQUEST)
        draft_id = request.data.get('draft_id')
        if not draft_id:
            return Response({'error': 'draft_id is required.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            res = GmailOAuthService.delete_draft(google_creds, draft_id)
            return Response({'success': True, 'data': res}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='check-new-mail')
    def check_new_mail(self, request):
        """
        Lightweight unread check for the signed-in user's Gmail mailbox.

        Returns:
            {
              "uidvalidity": int,
              "uidvalidity_changed": bool,
              "unseen_count": int,
              "highest_uid": int,
              "new_messages": [...]           # only when unread messages exist
            }
        """
        google_creds = get_mail_credentials(request.user)
        if not google_creds:
            return Response({'error': 'Gmail is not connected.'}, status=status.HTTP_200_OK)

        empty = {
            'uidvalidity': 1,
            'uidvalidity_changed': False,
            'unseen_count': 0,
            'highest_uid': 0,
            'new_messages': [],
        }
        try:
            unread_res = GmailOAuthService.fetch_messages(google_creds, folder='INBOX', limit=5)
            messages = unread_res.get('messages', [])
            unseen = sum(1 for m in messages if m.get('is_unread'))
            return Response({
                'uidvalidity': 1,
                'uidvalidity_changed': False,
                'unseen_count': unseen,
                'highest_uid': 0,
                'new_messages': messages if unseen > 0 else [],
            }, status=status.HTTP_200_OK)
        except Exception as e:
            logging.getLogger(__name__).warning("Error in check_new_mail: %s", e)
            return Response(empty, status=status.HTTP_200_OK)

    # Legacy endpoint kept for backward compatibility with old fetch_emails URL
    @action(detail=False, methods=['get'], url_path='fetch_emails')
    def fetch_emails_legacy(self, request):
        """Legacy underscore URL — delegates to fetch_emails."""
        return self.fetch_emails(request)

    # Legacy endpoint kept for backward compatibility with old fetch_email_body URL
    @action(detail=False, methods=['get'], url_path='fetch_email_body')
    def fetch_email_body_legacy(self, request):
        """Legacy underscore URL — delegates to fetch_email_body."""
        return self.fetch_email_body(request)

    def list(self, request):
        """Returns the connected Gmail mailbox (if any) for the signed-in user."""
        google_creds = get_mail_credentials(request.user)
        data = []
        if google_creds:
            data.append({
                'id': 'gmail',
                'name': 'Google Mail',
                'display_name': request.user.get_full_name() or request.user.username,
                'email_address': google_creds.email,
                'provider': 'GMAIL_OAUTH',
                'is_active': True,
                'default_signature': '',
            })
        return Response(data)

# Backward-compatible alias for the Gmail Mailbox ViewSet
MailAccountViewSet = GmailMailboxViewSet
