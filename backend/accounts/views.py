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
                mail = imaplib.IMAP4_SSL(mail_account.imap_host, mail_account.imap_port, timeout=15)
            else:
                mail = imaplib.IMAP4(mail_account.imap_host, mail_account.imap_port, timeout=15)
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

                tracking_info = None
                clean_mid = message_id.strip().strip('<>').strip()
                if clean_mid:
                    matched_oe = OutreachEmail.objects.filter(message_id__icontains=clean_mid).first()
                    if matched_oe:
                        tracking_info = {
                            'id': matched_oe.id,
                            'tracking_token': str(matched_oe.tracking_token),
                            'is_opened': matched_oe.is_opened,
                            'open_count': matched_oe.open_count,
                            'first_opened_at': matched_oe.first_opened_at.isoformat() if matched_oe.first_opened_at else (matched_oe.opened_at.isoformat() if matched_oe.opened_at else None),
                            'last_opened_at': matched_oe.last_opened_at.isoformat() if matched_oe.last_opened_at else (matched_oe.opened_at.isoformat() if matched_oe.opened_at else None),
                            'total_seconds_spent': matched_oe.total_seconds_spent,
                            'open_history': matched_oe.open_history,
                            'reading_engagement': ('Deeply Engaged' if (matched_oe.open_count >= 3 or matched_oe.total_seconds_spent >= 60) else ('Read in Detail' if (matched_oe.total_seconds_spent >= 15 or matched_oe.open_count >= 2) else 'Quick Skim')) if matched_oe.is_opened else 'Not Viewed',
                            'estimated_read_time_formatted': (f"{matched_oe.total_seconds_spent}s" if matched_oe.total_seconds_spent < 60 else f"{matched_oe.total_seconds_spent//60}m {matched_oe.total_seconds_spent%60}s") if (matched_oe.is_opened or matched_oe.total_seconds_spent > 0) else "0s",
                        }

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
                    'tracking': tracking_info,
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
        cc_address = request.data.get('cc')
        bcc_address = request.data.get('bcc')
        subject = request.data.get('subject', '')
        body = request.data.get('body', '')

        def _parse_addrs(val):
            if not val:
                return []
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
                for _, addr in email.utils.getaddresses([str(item)]):
                    addr_clean = addr.strip()
                    if addr_clean and addr_clean.lower() not in [e.lower() for e in extracted]:
                        extracted.append(addr_clean)
            return extracted

        to_list = _parse_addrs(to_address)
        cc_list = [c for c in _parse_addrs(cc_address) if c.lower() not in [t.lower() for t in to_list]]
        bcc_list = [b for b in _parse_addrs(bcc_address) if b.lower() not in [t.lower() for t in to_list] and b.lower() not in [c.lower() for c in cc_list]]

        if not to_list:
            return Response({'error': 'To address is required.'}, status=status.HTTP_400_BAD_REQUEST)

        # Optional saved template / signature
        template_id = request.data.get('template_id') or None
        signature_id = request.data.get('signature_id') or None
        composed = None
        if template_id or signature_id:
            from accounts.template_utils import build_email_content, ComposeError
            try:
                composed = build_email_content(
                    user, mail_account, None, to_list + cc_list, subject, body,
                    template_id=template_id, signature_id=signature_id,
                    body_edited=str(request.data.get('body_edited', 'true')).lower() != 'false',
                )
                subject = composed['subject'] or subject
                body = composed['text_body']
            except (ComposeError, ValueError) as exc:
                return Response({'error': str(exc) or 'Invalid template or signature.'}, status=status.HTTP_400_BAD_REQUEST)

        effective_signature = mail_account.default_signature if (mail_account.default_signature and mail_account.default_signature.strip() != "''") else ''
        if composed and composed['has_signature']:
            effective_signature = composed['signature_text']
        elif not effective_signature and mail_account:
            effective_signature = f"--\n{mail_account.display_name or mail_account.email_address}\n{mail_account.email_address}"

        full_body = body
        if effective_signature:
            full_body += f"\n\n{effective_signature}"

        from email.message import EmailMessage
        from email.utils import make_msgid
        import html

        email_domain = mail_account.email_address.split('@')[-1] if '@' in mail_account.email_address else 'local'
        msg = EmailMessage()
        msg['Subject'] = subject
        msg['From'] = f"{mail_account.display_name} <{mail_account.email_address}>" if mail_account.display_name else mail_account.email_address
        msg['To'] = ', '.join(to_list)
        if cc_list:
            msg['Cc'] = ', '.join(cc_list)
        if bcc_list:
            msg['Bcc'] = ', '.join(bcc_list)
        import uuid
        from django.conf import settings
        from django.utils import timezone
        tracking_token = uuid.uuid4()
        tracking_url = f"{settings.EMAIL_TRACKING_BASE_URL}/api/email-tracking/{tracking_token}/"

        msg['Message-ID'] = make_msgid(domain=email_domain)
        msg.set_content(full_body)

        # HTML alternative
        html_body = html.escape(body).replace('\n', '<br>')
        html_signature = ""
        if composed and composed['has_signature']:
            html_signature = f"\n<div>\n{composed['signature_html']}\n</div>\n"
        elif mail_account.default_signature and mail_account.default_signature.strip() and mail_account.default_signature.strip() != "''":
            sig_safe = html.escape(mail_account.default_signature.strip()).replace('\n', '<br>')
            html_signature = f"\n<div>\n{sig_safe}\n</div>\n"
        elif mail_account:
            s_name = mail_account.display_name or mail_account.email_address
            html_signature = f"\n<div style=\"margin-top:20px;padding-top:12px;border-top:1px solid #e2e8f0;color:#64748b;font-size:13px;line-height:1.5;\">--<br><strong style=\"color:#1e293b;\">{html.escape(s_name)}</strong><br>{html.escape(mail_account.email_address)}</div>\n"

        if composed and composed['has_template'] and composed['html_body']:
            main_html = composed['html_body']
        else:
            main_html = f'<div style="font-family: sans-serif;">{html_body}</div>'

        html_content = f"""<html><body>
{main_html}<br>{html_signature}
<img src="{tracking_url}" width="1" height="1" alt="" style="display:none;width:1px;height:1px;border:0;">
</body></html>"""

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

        def send_smtp_and_imap():
            import time
            import imaplib
            import smtplib
            import utils.encryption as encryption
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

                # For Gmail accounts, Gmail SMTP automatically places sent messages into "[Gmail]/Sent Mail".
                # Appending via IMAP creates an identical duplicate copy of the sent email in the mailbox.
                # Only non-Gmail IMAP servers require manual appending to the Sent folder.
                is_gmail = 'gmail' in (mail_account.imap_host or '').lower() or 'gmail' in (mail_account.smtp_host or '').lower()
                if not is_gmail:
                    try:
                        if mail_account.imap_security == 'SSL':
                            imap = imaplib.IMAP4_SSL(mail_account.imap_host, mail_account.imap_port, timeout=15)
                        else:
                            imap = imaplib.IMAP4(mail_account.imap_host, mail_account.imap_port, timeout=15)
                            imap.starttls()
                        imap.login(mail_account.imap_username, password)
                        sent_folder = 'Sent'
                        imap.append(sent_folder, '\\Seen', imaplib.Time2Internaldate(time.time()), msg.as_bytes())
                        imap.logout()
                    except Exception as e:
                        print(f"Background IMAP append failed: {e}")
            except Exception as e:
                print(f"Background SMTP send failed: {e}")

        import threading
        t = threading.Thread(target=send_smtp_and_imap)
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
            sender_mail_account=mail_account,
            from_email=mail_account.email_address,
            from_name=mail_account.display_name,
            subject=subject,
            body=body,
            signature=effective_signature,
            status='SENT',
            sent_at=timezone.now(),
            message_id=str(msg['Message-ID']),
            tracking_token=tracking_token,
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
        })

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
                mail_conn = imaplib.IMAP4_SSL(mail_account.imap_host, mail_account.imap_port, timeout=15)
            else:
                mail_conn = imaplib.IMAP4(mail_account.imap_host, mail_account.imap_port, timeout=15)
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
            cid_map = {}
            parts_list = []
            import base64
            import re
            import mimetypes
            import urllib.parse
            import html as html_module

            def get_filename(part):
                fname = part.get_filename()
                if not fname:
                    fname = part.get_param('name', header='content-type')
                if not fname:
                    fname = part.get_param('filename', header='content-disposition')
                if fname:
                    try:
                        decoded_headers = email.header.decode_header(fname)
                        parts = []
                        for t in decoded_headers:
                            if isinstance(t[0], bytes):
                                parts.append(t[0].decode(t[1] or 'utf-8', errors='ignore'))
                            else:
                                parts.append(str(t[0]))
                        fname = ''.join(parts)
                    except Exception:
                        pass
                return fname

            for part in msg_data:
                if isinstance(part, tuple):
                    msg = email.message_from_bytes(part[1])
                    for mp in msg.walk():
                        if mp.is_multipart():
                            continue

                        content_type = mp.get_content_type()
                        payload = mp.get_payload(decode=True)
                        if payload is None:
                            continue

                        disposition = str(mp.get('Content-Disposition') or '')
                        cid = mp.get('Content-ID')
                        filename = get_filename(mp)

                        # Capture main HTML or text body
                        if content_type == 'text/html' and not html_body and 'attachment' not in disposition.lower():
                            charset = mp.get_content_charset() or 'utf-8'
                            html_body = payload.decode(charset, errors='ignore')
                        elif content_type == 'text/plain' and not text_body and 'attachment' not in disposition.lower():
                            charset = mp.get_content_charset() or 'utf-8'
                            text_body = payload.decode(charset, errors='ignore')
                        else:
                            parts_list.append({
                                'mp': mp,
                                'content_type': content_type,
                                'disposition': disposition,
                                'cid': cid,
                                'filename': filename,
                                'payload': payload
                            })

            # Build CID map for inline parts
            for item in parts_list:
                cid = item['cid']
                ct = item['content_type']
                payload = item['payload']
                fname = item['filename']
                if cid:
                    clean_cid = cid.strip('<>').strip()
                    b64_data = base64.b64encode(payload).decode('utf-8')
                    data_uri = f"data:{ct};base64,{b64_data}"
                    for key in [
                        clean_cid,
                        cid.strip(),
                        f"<{clean_cid}>",
                        urllib.parse.quote(clean_cid),
                        urllib.parse.unquote(clean_cid),
                        html_module.escape(clean_cid),
                        html_module.unescape(clean_cid)
                    ]:
                        if key:
                            cid_map[key] = data_uri
                    if fname:
                        cid_map[fname] = data_uri

            # Replace any CID references in html_body with base64 data URIs
            orig_html = html_body
            if html_body and cid_map:
                for cid_key, data_uri in cid_map.items():
                    # Replace src="cid:..." or src='cid:...'
                    html_body = re.sub(
                        rf'(?i)src\s*=\s*(["\'])cid:{re.escape(cid_key)}\1',
                        lambda m, u=data_uri: f'src="{u}"',
                        html_body
                    )
                    # Replace bare cid: references (e.g. background, CSS url, src without quotes)
                    html_body = re.sub(
                        rf'(?i)cid:{re.escape(cid_key)}',
                        lambda m, u=data_uri: u,
                        html_body
                    )

            # Determine downloadable attachments
            attachments = []
            for item in parts_list:
                cid = item['cid']
                clean_cid = cid.strip('<>').strip() if cid else ''
                disp = item['disposition']
                fname = item['filename']
                ct = item['content_type']
                payload = item['payload']

                # Check if this part was used as an inline CID image in the HTML body
                is_inline_cid_used = bool(
                    clean_cid and orig_html and (
                        clean_cid in orig_html or 
                        (cid and cid.strip() in orig_html)
                    )
                )

                is_att = False
                if 'attachment' in disp.lower():
                    is_att = True
                elif is_inline_cid_used and 'attachment' not in disp.lower():
                    # Part is an inline image rendered directly in HTML body
                    is_att = False
                elif fname:
                    is_att = True
                elif not ct.startswith('text/') and not is_inline_cid_used:
                    is_att = True

                if is_att:
                    if not fname:
                        ext = mimetypes.guess_extension(ct) or ''
                        fname = f"attachment_{len(attachments)+1}{ext}"
                    attachments.append({
                        'filename': fname,
                        'content_type': ct,
                        'data': base64.b64encode(payload).decode('utf-8'),
                        'size': len(payload)
                    })

            if html_body:
                from accounts.template_utils import ensure_responsive_images
                html_body = ensure_responsive_images(html_body)
                # Strip email tracking pixels before returning to client to prevent sender self-tracking
                html_body = re.sub(r'<img[^>]*?email-tracking[^>]*?>', '', html_body, flags=re.IGNORECASE)

            tracking_info = None
            clean_mid = ''
            if msg_data:
                for item in msg_data:
                    if isinstance(item, tuple) and len(item) > 1:
                        try:
                            p_hdr = email.message_from_bytes(item[1])
                            clean_mid = (p_hdr.get('Message-ID') or '').strip().strip('<>').strip()
                            if clean_mid:
                                break
                        except Exception:
                            pass

            token_match = re.search(r'email-tracking/([a-f0-9\-]{36})', orig_html or '')
            matched_oe = None
            from prospects.models import OutreachEmail
            if token_match:
                matched_oe = OutreachEmail.objects.filter(tracking_token=token_match.group(1)).first()
            if not matched_oe and clean_mid:
                matched_oe = OutreachEmail.objects.filter(message_id__icontains=clean_mid).first()

            if matched_oe:
                tracking_info = {
                    'id': matched_oe.id,
                    'tracking_token': str(matched_oe.tracking_token),
                    'is_opened': matched_oe.is_opened,
                    'open_count': matched_oe.open_count,
                    'first_opened_at': matched_oe.first_opened_at.isoformat() if matched_oe.first_opened_at else (matched_oe.opened_at.isoformat() if matched_oe.opened_at else None),
                    'last_opened_at': matched_oe.last_opened_at.isoformat() if matched_oe.last_opened_at else (matched_oe.opened_at.isoformat() if matched_oe.opened_at else None),
                    'total_seconds_spent': matched_oe.total_seconds_spent,
                    'open_history': matched_oe.open_history,
                    'reading_engagement': ('Deeply Engaged' if (matched_oe.open_count >= 3 or matched_oe.total_seconds_spent >= 60) else ('Read in Detail' if (matched_oe.total_seconds_spent >= 15 or matched_oe.open_count >= 2) else 'Quick Skim')) if matched_oe.is_opened else 'Not Viewed',
                    'estimated_read_time_formatted': (f"{matched_oe.total_seconds_spent}s" if matched_oe.total_seconds_spent < 60 else f"{matched_oe.total_seconds_spent//60}m {matched_oe.total_seconds_spent%60}s") if (matched_oe.is_opened or matched_oe.total_seconds_spent > 0) else "0s",
                }

            return Response({
                'html_body': html_body,
                'text_body': text_body,
                'attachments': attachments,
                'tracking': tracking_info,
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
                mail = imaplib.IMAP4_SSL(mail_account.imap_host, mail_account.imap_port, timeout=15)
            else:
                mail = imaplib.IMAP4(mail_account.imap_host, mail_account.imap_port, timeout=15)
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
                server = imaplib.IMAP4_SSL(mail_account.imap_host, mail_account.imap_port, timeout=15)
            else:
                server = imaplib.IMAP4(mail_account.imap_host, mail_account.imap_port, timeout=15)
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
