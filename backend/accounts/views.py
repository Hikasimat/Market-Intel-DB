from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, BasePermission

from rest_framework import viewsets
from django.contrib.auth.models import User
from .serializers import UserSerializer
from .permissions import IsPRE, IsLQ as IsLQPerm

from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from django.conf import settings
from django.utils import timezone

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
        mail_account_id = None
        if profile and profile.mail_account_id:
            mail_account_id = profile.mail_account_id

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
            'mail_account_id': mail_account_id,
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


from .models import MailAccount
from .serializers import MailAccountSerializer
from rest_framework.decorators import action
from rest_framework import status
import smtplib
import imaplib
import email
from email.header import decode_header
import utils.encryption as encryption
import re
import time

class IsLQ(IsLQPerm):
    """Local alias so the rest of this module can reference IsLQ directly."""
    pass

class MailAccountViewSet(viewsets.ModelViewSet):


    @action(detail=False, methods=['get'], url_path='fetch-emails')
    def fetch_emails(self, request):
        """
        Fetch email metadata for the authenticated user's mail account using IMAP UIDs.

        Returns a list of messages with stable UID identifiers instead of sequence numbers.
        Also returns the mailbox UIDVALIDITY so the client can detect mailbox resets.

        Query params:
            folder (str): IMAP folder name, default 'INBOX'
            limit (int): maximum messages to return (newest first), default 20
        """
        user = request.user
        if not hasattr(user, 'profile'):
            return Response({'error': 'No profile found.'}, status=status.HTTP_400_BAD_REQUEST)

        mail_account = MailAccount.objects.filter(
            id=user.profile.mail_account_id, is_active=True
        ).first()
        if not mail_account:
            return Response(
                {'error': 'No active mail account configured.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        folder = request.query_params.get('folder', 'INBOX')
        limit = int(request.query_params.get('limit', 20))

        mail = None
        try:
            password = encryption.decrypt_password(mail_account.imap_app_password_encrypted)
            if mail_account.imap_security == 'SSL':
                mail = imaplib.IMAP4_SSL(mail_account.imap_host, mail_account.imap_port)
            else:
                mail = imaplib.IMAP4(mail_account.imap_host, mail_account.imap_port)
                mail.starttls()

            mail.login(mail_account.imap_username, password)
            select_status, select_data = mail.select(folder)

            if select_status != 'OK':
                return Response(
                    {'error': f'Failed to select folder {folder}'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Extract UIDVALIDITY from the SELECT response
            uidvalidity = None
            for item in select_data:
                if item and isinstance(item, bytes) and b'UIDVALIDITY' in item:
                    try:
                        parts = item.decode().split()
                        idx = parts.index('UIDVALIDITY')
                        uidvalidity = int(parts[idx + 1])
                    except (ValueError, IndexError):
                        pass

            # Use STATUS to get UIDVALIDITY if not found in SELECT response
            if uidvalidity is None:
                status_res, status_data = mail.status(folder, '(UIDVALIDITY)')
                if status_res == 'OK' and status_data:
                    try:
                        status_str = status_data[0].decode()
                        parts = status_str.replace(')', '').split()
                        idx = parts.index('UIDVALIDITY')
                        uidvalidity = int(parts[idx + 1])
                    except (ValueError, IndexError, AttributeError):
                        pass

            # Search using UIDs instead of sequence numbers
            uid_status, uid_data = mail.uid('SEARCH', None, 'ALL')
            if uid_status != 'OK':
                return Response(
                    {'error': 'Failed to search emails'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            all_uids = uid_data[0].split()
            # Fetch up to 1000 recent emails to allow for filtering, we will break when we hit `limit` owned emails
            recent_uids = all_uids[-1000:]
            recent_uids.reverse()  # newest first

            emails_list = []
            from prospects.models import OutreachEmail, ProspectContact, Prospect

            for uid_bytes in recent_uids:
                if len(emails_list) >= limit:
                    break
                    
                uid_str = uid_bytes.decode()
                # Fetch headers using UID command — PEEK avoids marking as read
                res_status, hdr_data = mail.uid(
                    'FETCH', uid_bytes, '(FLAGS BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE MESSAGE-ID IN-REPLY-TO REFERENCES)])'
                )
                if res_status != 'OK':
                    continue

                subject = ''
                from_hdr = ''
                date_hdr = ''
                message_id = ''
                is_unread = True  # default; corrected from FLAGS below

                for part in hdr_data:
                    if isinstance(part, tuple):
                        # part[0] contains FLAGS info, part[1] is the header bytes
                        part_info = part[0].decode() if isinstance(part[0], bytes) else ''
                        flags_str = part_info.upper()
                        is_unread = '\\SEEN' not in flags_str

                        hdr_msg = email.message_from_bytes(part[1])

                        raw_subject = hdr_msg.get('Subject', '')
                        decoded_subject = decode_header(raw_subject)
                        subject_parts = []
                        for s_bytes, enc in decoded_subject:
                            if isinstance(s_bytes, bytes):
                                subject_parts.append(s_bytes.decode(enc or 'utf-8', errors='ignore'))
                            else:
                                subject_parts.append(s_bytes or '')
                        subject = ''.join(subject_parts)

                        from_hdr = hdr_msg.get('From', '')
                        to_hdr = hdr_msg.get('To', '')
                        date_hdr = hdr_msg.get('Date', '')
                        message_id = hdr_msg.get('Message-ID', '')
                        in_reply_to = str(hdr_msg.get('In-Reply-To', ''))
                        references = str(hdr_msg.get('References', ''))

                # Attempt to match prospect company
                prospect_company_name = None
                email_pattern = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+')
                all_emails = email_pattern.findall(from_hdr) + email_pattern.findall(to_hdr)
                if all_emails:
                    from prospects.models import ProspectContact, Prospect
                    contact = ProspectContact.objects.filter(official_email__in=all_emails).select_related('prospect').first()
                    if contact and contact.prospect:
                        prospect_company_name = contact.prospect.company_name
                    else:
                        prospect = Prospect.objects.filter(official_email_address__in=all_emails).first()
                        if prospect:
                            prospect_company_name = prospect.company_name

                if not prospect_company_name and (in_reply_to or references):
                    refs = (in_reply_to + ' ' + references).replace('<', ' ').replace('>', ' ').split()
                    for ref in refs:
                        ref = ref.strip()
                        if not ref:
                            continue
                        oe = OutreachEmail.objects.filter(message_id__icontains=ref).select_related('prospect').first()
                        if oe and oe.prospect:
                            prospect_company_name = oe.prospect.company_name
                            break

                # --- OWNERSHIP FILTERING (REMOVED) ---
                # User requested to display all mail, so we no longer filter by ownership.
                # All emails will be displayed.

                emails_list.append({
                    'uid': uid_str,
                    'id': uid_str,  # backward-compatible field
                    'message_id': message_id,
                    'subject': subject,
                    'from': from_hdr,
                    'to': to_hdr,
                    'date': date_hdr,
                    'is_unread': is_unread,
                    'folder': folder,
                    'prospect_company_name': prospect_company_name,
                })

            return Response({
                'uidvalidity': uidvalidity,
                'messages': emails_list,
            }, status=status.HTTP_200_OK)

        except Exception as e:
            if isinstance(e, ValueError) and "Decryption failed" in str(e):
                return Response({'error': str(e)}, status=status.HTTP_200_OK)
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            if mail is not None:
                try:
                    mail.logout()
                except Exception:
                    pass

    @action(detail=False, methods=['post'], url_path='send-email')
    def send_email_action(self, request):
        user = request.user
        profile = getattr(user, 'profile', None)
        mail_account = MailAccount.objects.filter(id=profile.mail_account_id if profile else None, is_active=True).first()
        if not mail_account:
            return Response({'error': 'No active mail account.'}, status=status.HTTP_400_BAD_REQUEST)
            
        to_address = request.data.get('to')
        subject = request.data.get('subject', '')
        body = request.data.get('body', '')
        
        if not to_address:
            return Response({'error': 'To address is required.'}, status=status.HTTP_400_BAD_REQUEST)
            
        from email.message import EmailMessage
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = f"{mail_account.display_name} <{mail_account.email_address}>" if mail_account.display_name else mail_account.email_address
        msg['To'] = to_address
        msg.set_content(body)
        
        def send_smtp_and_imap():
            import time
            import imaplib
            try:
                password = encryption.decrypt_password(mail_account.smtp_app_password_encrypted)
                if mail_account.smtp_security == 'SSL':
                    server = smtplib.SMTP_SSL(mail_account.smtp_host, mail_account.smtp_port, timeout=30)
                else:
                    server = smtplib.SMTP(mail_account.smtp_host, mail_account.smtp_port, timeout=30)
                    server.starttls()
                server.login(mail_account.smtp_username, password)
                server.send_message(msg)
                server.quit()
                
                try:
                    if mail_account.imap_security == 'SSL':
                        imap = imaplib.IMAP4_SSL(mail_account.imap_host, mail_account.imap_port)
                    else:
                        imap = imaplib.IMAP4(mail_account.imap_host, mail_account.imap_port)
                        imap.starttls()
                    imap.login(mail_account.imap_username, password)
                    # Attempt to save to Sent folder
                    sent_folder = '"[Gmail]/Sent Mail"' if 'gmail' in mail_account.imap_host.lower() else 'Sent'
                    imap.append(sent_folder, '\\Seen', imaplib.Time2Internaldate(time.time()), msg.as_bytes())
                    imap.logout()
                except Exception as e:
                    print(f"Background IMAP append failed: {e}")
            except Exception as e:
                print(f"Background SMTP send failed: {e}")

        import threading
        t = threading.Thread(target=send_smtp_and_imap)
        t.start()
        
        return Response({'success': True})

    @action(detail=False, methods=['get'], url_path='fetch-email-body')
    def fetch_email_body(self, request):
        """
        Fetch the full body of a single email by UID.

        Query params:
            folder (str): IMAP folder name, default 'INBOX'
            uid (str): IMAP UID of the email (stable; preferred)
            email_id (str): legacy alias for uid
        """
        user = request.user
        if not hasattr(user, 'profile'):
            return Response({'error': 'No profile found.'}, status=status.HTTP_400_BAD_REQUEST)

        mail_account = MailAccount.objects.filter(
            id=user.profile.mail_account_id, is_active=True
        ).first()
        if not mail_account:
            return Response(
                {'error': 'No active mail account configured.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        folder = request.query_params.get('folder', 'INBOX')
        # Accept 'uid' (preferred) or legacy 'email_id'
        uid = request.query_params.get('uid') or request.query_params.get('email_id')
        if not uid:
            return Response({'error': 'uid is required.'}, status=status.HTTP_400_BAD_REQUEST)

        mail_conn = None
        try:
            password = encryption.decrypt_password(mail_account.imap_app_password_encrypted)
            if mail_account.imap_security == 'SSL':
                mail_conn = imaplib.IMAP4_SSL(mail_account.imap_host, mail_account.imap_port)
            else:
                mail_conn = imaplib.IMAP4(mail_account.imap_host, mail_account.imap_port)
                mail_conn.starttls()

            mail_conn.login(mail_account.imap_username, password)
            mail_conn.select(folder)

            # Fetch full RFC822 message by UID
            res_status, msg_data = mail_conn.uid('FETCH', uid.encode(), '(RFC822)')

            if res_status != 'OK':
                return Response(
                    {'error': 'Failed to fetch email body.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            html_body = ''
            text_body = ''
            attachments = []
            import base64

            def process_attachment(part):
                filename = part.get_filename()
                if not filename:
                    filename = 'unknown_attachment'
                else:
                    decoded_headers = email.header.decode_header(filename)
                    filename = ''.join([str(t[0], t[1] or 'utf-8') if isinstance(t[0], bytes) else t[0] for t in decoded_headers])
                payload = part.get_payload(decode=True)
                if payload:
                    b64_data = base64.b64encode(payload).decode('utf-8')
                    attachments.append({
                        'filename': filename,
                        'content_type': part.get_content_type(),
                        'data': b64_data,
                        'size': len(payload)
                    })

            for part in msg_data:
                if isinstance(part, tuple):
                    msg = email.message_from_bytes(part[1])
                    if msg.is_multipart():
                        for mp in msg.walk():
                            content_type = mp.get_content_type()
                            disposition = str(mp.get('Content-Disposition', ''))
                            if 'attachment' in disposition or mp.get_filename():
                                process_attachment(mp)
                                continue
                            payload = mp.get_payload(decode=True)
                            if payload is None:
                                continue
                            charset = mp.get_content_charset() or 'utf-8'
                            decoded = payload.decode(charset, errors='ignore')
                            if content_type == 'text/html' and not html_body:
                                html_body = decoded
                            elif content_type == 'text/plain' and not text_body:
                                text_body = decoded
                    else:
                        disposition = str(msg.get('Content-Disposition', ''))
                        if 'attachment' in disposition or msg.get_filename():
                            process_attachment(msg)
                        else:
                            payload = msg.get_payload(decode=True)
                            if payload:
                                charset = msg.get_content_charset() or 'utf-8'
                                decoded = payload.decode(charset, errors='ignore')
                                if msg.get_content_type() == 'text/html':
                                    html_body = decoded
                                else:
                                    text_body = decoded

            return Response({
                'html_body': html_body,
                'text_body': text_body,
                'attachments': attachments,
            }, status=status.HTTP_200_OK)

        except Exception as e:
            if isinstance(e, ValueError) and "Decryption failed" in str(e):
                return Response({'error': str(e)}, status=status.HTTP_200_OK)
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        finally:
            if mail_conn is not None:
                try:
                    mail_conn.logout()
                except Exception:
                    pass

    @action(detail=False, methods=['get'], url_path='check-new-mail')
    def check_new_mail(self, request):
        """
        Lightweight mailbox delta check.

        Instead of fetching all headers, this uses IMAP STATUS to compare the
        current mailbox state against the client's known state.  When new UIDs
        are present, only the missing message metadata is fetched.

        Query params:
            folder (str): IMAP folder name, default 'INBOX'
            uidvalidity (int): client's known UIDVALIDITY (0 if unknown)
            highest_uid (int): client's highest known UID (0 if unknown)

        Returns:
            {
              "uidvalidity": int,
              "uidvalidity_changed": bool,   # True if client must rebuild cache
              "unseen_count": int,
              "highest_uid": int,
              "new_messages": [...]           # only when new UIDs were found
            }
        """
        user = request.user
        if not hasattr(user, 'profile'):
            return Response({'error': 'No profile found.'}, status=status.HTTP_400_BAD_REQUEST)

        mail_account = MailAccount.objects.filter(
            id=user.profile.mail_account_id, is_active=True
        ).first()
        if not mail_account:
            return Response(
                {'error': 'No active mail account configured.'},
                status=status.HTTP_200_OK,
            )

        folder = request.query_params.get('folder', 'INBOX')
        try:
            client_uidvalidity = int(request.query_params.get('uidvalidity', 0))
        except (TypeError, ValueError):
            client_uidvalidity = 0
        try:
            client_highest_uid = int(request.query_params.get('highest_uid', 0))
        except (TypeError, ValueError):
            client_highest_uid = 0

        mail = None
        try:
            password = encryption.decrypt_password(mail_account.imap_app_password_encrypted)
            if mail_account.imap_security == 'SSL':
                mail = imaplib.IMAP4_SSL(mail_account.imap_host, mail_account.imap_port)
            else:
                mail = imaplib.IMAP4(mail_account.imap_host, mail_account.imap_port)
                mail.starttls()

            mail.login(mail_account.imap_username, password)

            # Use STATUS to get mailbox state without fully selecting it
            status_res, status_data = mail.status(folder, '(UIDVALIDITY UIDNEXT UNSEEN)')
            if status_res != 'OK' or not status_data:
                return Response(
                    {'error': f'Failed to get status for folder {folder}'},
                    status=status.HTTP_200_OK,
                )

            status_str = status_data[0].decode() if isinstance(status_data[0], bytes) else str(status_data[0])
            # Parse: '... (UIDVALIDITY 123 UIDNEXT 456 UNSEEN 7)'
            status_str = status_str.replace(')', '').replace('(', '')
            parts = status_str.split()

            def extract(key, default=0):
                try:
                    idx = parts.index(key)
                    return int(parts[idx + 1])
                except (ValueError, IndexError):
                    return default

            server_uidvalidity = extract('UIDVALIDITY')
            server_uidnext = extract('UIDNEXT')
            unseen_count = extract('UNSEEN')

            # UIDNEXT is the next UID to be assigned, so current highest = UIDNEXT - 1
            server_highest_uid = max(0, server_uidnext - 1)

            uidvalidity_changed = (
                client_uidvalidity != 0 and server_uidvalidity != client_uidvalidity
            )

            response_data = {
                'uidvalidity': server_uidvalidity,
                'uidvalidity_changed': uidvalidity_changed,
                'unseen_count': unseen_count,
                'highest_uid': server_highest_uid,
                'new_messages': [],
            }

            if uidvalidity_changed:
                # Client must rebuild the cache; don't mix old UIDs with new ones
                return Response(response_data, status=status.HTTP_200_OK)

            # Check if there are new UIDs the client doesn't have yet
            new_uids_exist = server_highest_uid > client_highest_uid

            if not new_uids_exist:
                return Response(response_data, status=status.HTTP_200_OK)

            # Select the folder to run UID SEARCH
            select_res, _ = mail.select(folder)
            if select_res != 'OK':
                return Response(response_data, status=status.HTTP_200_OK)

            # Search for UIDs the client doesn't know about
            search_criteria = f'{client_highest_uid + 1}:*'
            uid_res, uid_data = mail.uid('SEARCH', None, f'UID {search_criteria}')
            if uid_res != 'OK' or not uid_data or not uid_data[0]:
                return Response(response_data, status=status.HTTP_200_OK)

            new_uid_list = uid_data[0].split()
            new_messages = []

            for uid_bytes in new_uid_list:
                uid_str = uid_bytes.decode()
                try:
                    uid_int = int(uid_str)
                except ValueError:
                    continue

                if uid_int <= client_highest_uid:
                    continue

                fetch_res, hdr_data = mail.uid(
                    'FETCH', uid_bytes,
                    '(FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])'
                )
                if fetch_res != 'OK':
                    continue

                subject = ''
                from_hdr = ''
                date_hdr = ''
                message_id = ''
                is_unread = True

                for part in hdr_data:
                    if isinstance(part, tuple):
                        part_info = part[0].decode() if isinstance(part[0], bytes) else ''
                        is_unread = '\\SEEN' not in part_info.upper()

                        hdr_msg = email.message_from_bytes(part[1])

                        raw_subject = hdr_msg.get('Subject', '')
                        decoded_subject = decode_header(raw_subject)
                        subject_parts = []
                        for s_bytes, enc in decoded_subject:
                            if isinstance(s_bytes, bytes):
                                subject_parts.append(s_bytes.decode(enc or 'utf-8', errors='ignore'))
                            else:
                                subject_parts.append(s_bytes or '')
                        subject = ''.join(subject_parts)

                        from_hdr = hdr_msg.get('From', '')
                        date_hdr = hdr_msg.get('Date', '')
                        message_id = hdr_msg.get('Message-ID', '')

                new_messages.append({
                    'uid': uid_str,
                    'id': uid_str,
                    'message_id': message_id,
                    'subject': subject,
                    'from': from_hdr,
                    'date': date_hdr,
                    'is_unread': is_unread,
                    'folder': folder,
                })

            response_data['new_messages'] = new_messages
            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            if isinstance(e, ValueError) and "Decryption failed" in str(e):
                return Response({'error': str(e)}, status=status.HTTP_200_OK)
            import traceback
            traceback.print_exc()
            return Response({'error': str(e)}, status=status.HTTP_200_OK)
        finally:
            if mail is not None:
                try:
                    mail.logout()
                except Exception:
                    pass

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

    serializer_class = MailAccountSerializer
    permission_classes = [IsLQ]

    def get_queryset(self):
        return MailAccount.objects.all()

    def perform_create(self, serializer):
        mail_account = serializer.save()
        profile = self.request.user.profile
        profile.mail_account = mail_account
        profile.save()

    @action(detail=True, methods=['post'], url_path='set-default')
    def set_default(self, request, pk=None):
        mail_account = self.get_object()
        profile = request.user.profile
        profile.mail_account = mail_account
        profile.save()
        return Response({'status': 'default set'})

    @action(detail=True, methods=['post'], url_path='test-smtp')
    def test_smtp(self, request, pk=None):
        mail_account = self.get_object()
        server = None
        try:
            password = encryption.decrypt_password(mail_account.smtp_app_password_encrypted)
            if mail_account.smtp_security == 'SSL':
                server = smtplib.SMTP_SSL(mail_account.smtp_host, mail_account.smtp_port, timeout=30)
            else:
                server = smtplib.SMTP(mail_account.smtp_host, mail_account.smtp_port, timeout=30)
                server.starttls()
            server.login(mail_account.smtp_username, password)
            mail_account.smtp_status = 'VERIFIED'
            mail_account.save()
            return Response({'message': 'SMTP connection successful.'})
        except Exception as e:
            mail_account.smtp_status = 'FAILED'
            mail_account.save()
            return Response({'error': 'Unable to connect to SMTP server. Please verify the configuration.'}, status=status.HTTP_400_BAD_REQUEST)
        finally:
            if server is not None:
                try:
                    server.quit()
                except Exception:
                    pass

    @action(detail=True, methods=['post'], url_path='test-imap')
    def test_imap(self, request, pk=None):
        mail_account = self.get_object()
        server = None
        try:
            password = encryption.decrypt_password(mail_account.imap_app_password_encrypted)
            if mail_account.imap_security == 'SSL':
                server = imaplib.IMAP4_SSL(mail_account.imap_host, mail_account.imap_port)
            else:
                server = imaplib.IMAP4(mail_account.imap_host, mail_account.imap_port)
                server.starttls()
            server.login(mail_account.imap_username, password)
            mail_account.imap_status = 'CONNECTED'
            mail_account.save()
            return Response({'message': 'IMAP connection successful.'})
        except Exception as e:
            mail_account.imap_status = 'FAILED'
            mail_account.save()
            return Response({'error': 'Unable to connect to IMAP server. Please verify the configuration.'}, status=status.HTTP_400_BAD_REQUEST)
        finally:
            if server is not None:
                try:
                    server.logout()
                except Exception:
                    pass
