import json
import logging
import secrets
import urllib.parse
import urllib.request
import urllib.error
from datetime import timedelta
import jwt
from django.conf import settings
from django.contrib.auth.models import User
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.utils import timezone
import utils.encryption as encryption

logger = logging.getLogger(__name__)

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"

# Cached JWKS client for signature verification
_jwks_client = None

def get_jwks_client():
    global _jwks_client
    if _jwks_client is None:
        _jwks_client = jwt.PyJWKClient(GOOGLE_JWKS_URL)
    return _jwks_client


class GoogleOAuthService:
    STATE_MAX_AGE = 600  # 10 minutes

    @classmethod
    def is_configured(cls):
        return bool(
            getattr(settings, 'GOOGLE_OAUTH_CLIENT_ID', '').strip() and
            getattr(settings, 'GOOGLE_OAUTH_CLIENT_SECRET', '').strip()
        )

    @classmethod
    def generate_login_url(cls):
        """
        Generates Google OAuth 2.0 authorization URL for application login.
        Requests identity scopes plus Gmail mailbox scopes (offline) so the
        user's mailbox is connected automatically at login. Login identity
        and mailbox tokens are still stored separately.
        """
        if not cls.is_configured():
            raise ValueError("Google OAuth credentials are not configured on the server.")

        raw_state = secrets.token_urlsafe(32)
        signer = TimestampSigner(salt='google-oauth-state')
        signed_state = signer.sign(raw_state)

        params = {
            'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
            'redirect_uri': settings.GOOGLE_OAUTH_REDIRECT_URI,
            'response_type': 'code',
            'scope': 'openid email profile ' + ' '.join(GmailOAuthService.GMAIL_SCOPES),
            'access_type': 'offline',
            'state': signed_state,
            'prompt': 'select_account consent',
        }
        url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
        return url, signed_state

    @classmethod
    def verify_state(cls, received_state, cookie_state=None):
        """
        Validates the OAuth state against cookie state and signed timestamp.
        Prevents CSRF, tampering, and replay attacks.
        """
        if not received_state:
            return False

        if cookie_state and received_state != cookie_state:
            return False

        signer = TimestampSigner(salt='google-oauth-state')
        try:
            signer.unsign(received_state, max_age=cls.STATE_MAX_AGE)
            return True
        except (BadSignature, SignatureExpired):
            return False

    @classmethod
    def exchange_code_for_tokens(cls, code, redirect_uri=None):
        """
        Securely exchanges authorization code for Google tokens.
        """
        redirect_uri = redirect_uri or settings.GOOGLE_OAUTH_REDIRECT_URI
        payload = urllib.parse.urlencode({
            'code': code,
            'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
            'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
            'redirect_uri': redirect_uri,
            'grant_type': 'authorization_code',
        }).encode('utf-8')

        req = urllib.request.Request(
            GOOGLE_TOKEN_URL,
            data=payload,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json',
            },
            method='POST',
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                return data
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8', errors='ignore')
            logger.warning("Google token exchange failed: %s %s", e.code, err_body)
            raise ValueError("Failed to exchange authorization code with Google.")
        except Exception as e:
            logger.error("Error communicating with Google token endpoint: %s", e)
            raise ValueError("Unable to reach Google OAuth services.")

    @classmethod
    def verify_id_token(cls, id_token_jwt):
        """
        Cryptographically verifies the Google ID token signature using Google's JWKS.
        Validates issuer, audience, expiration, and required claims.
        Strictly requires email_verified is True.
        """
        if not id_token_jwt:
            raise ValueError("Missing ID token.")

        client_id = settings.GOOGLE_OAUTH_CLIENT_ID

        try:
            jwks = get_jwks_client()
            signing_key = jwks.get_signing_key_from_jwt(id_token_jwt)
            claims = jwt.decode(
                id_token_jwt,
                signing_key.key,
                algorithms=["RS256"],
                audience=client_id,
                issuer=["https://accounts.google.com", "accounts.google.com"],
                options={"verify_exp": True},
            )
        except Exception as e:
            logger.warning("Google ID token validation failed: %s", e)
            raise ValueError("Invalid or unverifiable Google identity token.")

        if claims.get('email_verified') is not True:
            raise ValueError("Google account email is not verified.")

        email = (claims.get('email') or '').strip().lower()
        if not email:
            raise ValueError("No email found in Google identity token.")

        return {
            'email': email,
            'sub': claims.get('sub'),
            'name': claims.get('name', ''),
        }

    @classmethod
    def find_eligible_user(cls, verified_email):
        """
        Finds the existing Django User matching the verified email.
        Enforces:
        - NEVER automatically creates or provisions an account.
        - NEVER activates an inactive account.
        - Resolves by email, falling back to username.
        - Rejects ambiguous multi-user matches.
        Returns: (user, status_code_string)
            status_code_string: 'OK', 'NOT_FOUND', 'INACTIVE', 'AMBIGUOUS'
        """
        normalized_email = verified_email.strip().lower()

        users = User.objects.filter(email__iexact=normalized_email)
        if not users.exists():
            users = User.objects.filter(username__iexact=normalized_email)

        count = users.count()
        if count == 0:
            return None, 'NOT_FOUND'
        if count > 1:
            return None, 'AMBIGUOUS'

        user = users.first()
        if not user.is_active:
            return None, 'INACTIVE'

        return user, 'OK'


class GmailOAuthService:
    GMAIL_SCOPES = [
        "https://mail.google.com/",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/calendar.events",
    ]
    STATE_MAX_AGE = 600

    @classmethod
    def generate_authorization_url(cls, user_id):
        """
        Generates authorization URL specifically for Gmail mailbox permissions.
        Separate from user login.
        Requests offline access and consent prompt so refresh token is returned.
        """
        if not GoogleOAuthService.is_configured():
            raise ValueError("Google OAuth credentials are not configured on the server.")

        raw_state = f"{user_id}:{secrets.token_urlsafe(24)}"
        signer = TimestampSigner(salt='gmail-oauth-state')
        signed_state = signer.sign(raw_state)

        params = {
            'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
            'redirect_uri': settings.GMAIL_OAUTH_REDIRECT_URI,
            'response_type': 'code',
            'access_type': 'offline',
            'prompt': 'consent',
            'scope': ' '.join(cls.GMAIL_SCOPES),
            'state': signed_state,
        }
        url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
        return url, signed_state

    @classmethod
    def verify_state(cls, received_state, expected_user_id):
        if not received_state:
            return False
        signer = TimestampSigner(salt='gmail-oauth-state')
        try:
            unsigned = signer.unsign(received_state, max_age=cls.STATE_MAX_AGE)
            user_part = unsigned.split(':', 1)[0]
            return str(user_part) == str(expected_user_id)
        except (BadSignature, SignatureExpired):
            return False

    @classmethod
    def exchange_code_for_tokens(cls, code):
        return GoogleOAuthService.exchange_code_for_tokens(
            code=code,
            redirect_uri=settings.GMAIL_OAUTH_REDIRECT_URI
        )

    @classmethod
    def refresh_access_token(cls, credentials):
        """
        Refreshes an expired Gmail access token using the stored encrypted refresh token.
        Persists the newly encrypted access token.
        """
        if not credentials.refresh_token_encrypted:
            raise ValueError("No Gmail refresh token available. Re-authorization required.")

        refresh_token = encryption.decrypt_password(credentials.refresh_token_encrypted)
        payload = urllib.parse.urlencode({
            'client_id': settings.GOOGLE_OAUTH_CLIENT_ID,
            'client_secret': settings.GOOGLE_OAUTH_CLIENT_SECRET,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token',
        }).encode('utf-8')

        req = urllib.request.Request(
            GOOGLE_TOKEN_URL,
            data=payload,
            headers={
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json',
            },
            method='POST',
        )

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8', errors='ignore')
            logger.warning("Gmail token refresh failed (%s): %s", e.code, err_body)
            credentials.is_active = False
            credentials.save(update_fields=['is_active'])
            raise ValueError("Gmail grant was revoked or expired. Please re-authorize Gmail.")

        new_access_token = data.get('access_token')
        expires_in = data.get('expires_in', 3600)

        credentials.access_token_encrypted = encryption.encrypt_password(new_access_token)
        credentials.token_expiry = timezone.now() + timedelta(seconds=expires_in)
        credentials.is_active = True
        credentials.save(update_fields=['access_token_encrypted', 'token_expiry', 'is_active', 'updated_at'])

        try:
            from .models import GoogleCalendarCredentials
            cal_creds = GoogleCalendarCredentials.objects.filter(user=credentials.user).first()
            if cal_creds:
                cal_creds.access_token_encrypted = credentials.access_token_encrypted
                cal_creds.token_expiry = credentials.token_expiry
                cal_creds.is_active = True
                cal_creds.save(update_fields=['access_token_encrypted', 'token_expiry', 'is_active', 'updated_at'])
        except Exception as sync_err:
            logger.warning("Could not sync refreshed token to GoogleCalendarCredentials: %s", sync_err)

        return new_access_token

    @classmethod
    def get_valid_access_token(cls, credentials):
        """
        Returns a valid, unexpired access token for Gmail, refreshing if necessary.
        """
        now = timezone.now()
        # If token expires in less than 60 seconds or already expired, refresh it
        if not credentials.token_expiry or credentials.token_expiry <= now + timedelta(seconds=60):
            return cls.refresh_access_token(credentials)
        return encryption.decrypt_password(credentials.access_token_encrypted)

    @classmethod
    def store_tokens_from_login(cls, user, tokens, email):
        """
        Persist Gmail tokens obtained during Google login (when Gmail scope was granted),
        so the user does not have to link the mailbox a second time.
        """
        scope = tokens.get('scope', '') or ''
        access_token = tokens.get('access_token')
        if not access_token or ('gmail' not in scope and 'mail.google.com' not in scope):
            return None
        creds, _ = cls._get_or_create_creds(user)
        creds.email = email or user.email
        creds.access_token_encrypted = encryption.encrypt_password(access_token)
        if tokens.get('refresh_token'):
            creds.refresh_token_encrypted = encryption.encrypt_password(tokens['refresh_token'])
        creds.token_expiry = timezone.now() + timedelta(seconds=tokens.get('expires_in', 3600))
        creds.scopes = scope
        creds.is_active = True
        creds.save()

        # Seamlessly sync active GoogleCalendarCredentials so calendar and meetings work immediately
        try:
            from .models import GoogleCalendarCredentials
            cal_creds, _ = GoogleCalendarCredentials.objects.get_or_create(user=user)
            cal_creds.email = creds.email
            cal_creds.access_token_encrypted = creds.access_token_encrypted
            if creds.refresh_token_encrypted:
                cal_creds.refresh_token_encrypted = creds.refresh_token_encrypted
            cal_creds.token_expiry = creds.token_expiry
            cal_creds.scopes = creds.scopes
            cal_creds.is_active = True
            cal_creds.save()
        except Exception as e:
            logger.warning("Could not sync GoogleCalendarCredentials on login: %s", e)

        return creds

    @staticmethod
    def _get_or_create_creds(user):
        from .models import GoogleMailCredentials
        return GoogleMailCredentials.objects.get_or_create(user=user)


    @classmethod
    def get_credentials(cls, user):
        """
        Retrieve active Google Mail credentials for a user.
        If only GoogleCalendarCredentials exists and is active, automatically creates/syncs GoogleMailCredentials.
        """
        if not user or not user.is_authenticated:
            return None
        from .models import GoogleMailCredentials, GoogleCalendarCredentials
        creds = GoogleMailCredentials.objects.filter(user=user, is_active=True).first()
        if creds and (creds.refresh_token_encrypted or creds.access_token_encrypted):
            return creds

        # Fallback to GoogleCalendarCredentials if it has active tokens
        cal_creds = GoogleCalendarCredentials.objects.filter(user=user, is_active=True).first()
        if cal_creds and (cal_creds.refresh_token_encrypted or cal_creds.access_token_encrypted):
            creds, _ = GoogleMailCredentials.objects.get_or_create(user=user)
            creds.email = cal_creds.email or user.email or ''
            creds.access_token_encrypted = cal_creds.access_token_encrypted
            creds.refresh_token_encrypted = cal_creds.refresh_token_encrypted
            creds.token_expiry = cal_creds.token_expiry
            creds.scopes = cal_creds.scopes
            creds.is_active = True
            creds.save()
            return creds

        return None

    @classmethod
    def fetch_messages(cls, credentials, folder='INBOX', limit=20, search=''):
        """
        Fetches messages from Gmail via Gmail REST API.
        Maps folders to Gmail query filters (in:inbox, is:starred, in:sent, in:draft, in:spam, in:trash).
        Supports server-side search query syntax.
        Returns list of message metadata matching application's inbox format.
        """
        token = cls.get_valid_access_token(credentials)
        folder_clean = (folder or 'INBOX').replace('"', '').strip().upper()
        if 'SENT' in folder_clean:
            folder_query = 'in:sent'
        elif 'SPAM' in folder_clean:
            folder_query = 'in:spam'
        elif 'STARRED' in folder_clean:
            folder_query = 'is:starred'
        elif 'DRAFT' in folder_clean:
            folder_query = 'in:draft'
        elif 'TRASH' in folder_clean or 'BIN' in folder_clean:
            folder_query = 'in:trash'
        elif 'ALL' in folder_clean:
            folder_query = ''
        else:
            folder_query = 'in:inbox'

        query_parts = []
        if folder_query:
            query_parts.append(folder_query)
        if search and search.strip():
            query_parts.append(search.strip())
        final_query = ' '.join(query_parts)

        query_param = f"&q={urllib.parse.quote(final_query)}" if final_query else ""
        url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults={min(int(limit), 50)}{query_param}"
        req = urllib.request.Request(
            url,
            headers={
                'Authorization': f'Bearer {token}',
                'Accept': 'application/json',
            }
        )
        # Raise on list failure so callers can keep showing the previous list
        # instead of treating a transient error as an empty mailbox.
        with urllib.request.urlopen(req, timeout=15) as resp:
            res_data = json.loads(resp.read().decode('utf-8'))

        messages = res_data.get('messages', [])[:limit]
        emails_list = []

        import re
        email_pattern = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+')

        def _fetch_meta(msg_id):
            msg_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}?format=metadata&metadataHeaders=From&metadataHeaders=To&metadataHeaders=Subject&metadataHeaders=Date&metadataHeaders=Message-ID"
            for _attempt in range(3):
                try:
                    m_req = urllib.request.Request(
                        msg_url,
                        headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
                    )
                    with urllib.request.urlopen(m_req, timeout=10) as m_resp:
                        return json.loads(m_resp.read().decode('utf-8'))
                except Exception:
                    continue
            return None

        # Parallel fetch keeps Gmail's newest-first order and is far faster/more reliable
        from concurrent.futures import ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=6) as pool:
            metas = list(pool.map(_fetch_meta, [m['id'] for m in messages]))
        partial = any(md is None for md in metas)

        for m, m_data in zip(messages, metas):
            if m_data is None:
                continue
            msg_id = m['id']

            headers = {h.get('name', '').lower(): h.get('value', '') for h in m_data.get('payload', {}).get('headers', [])}
            subject = headers.get('subject', '')
            from_hdr = headers.get('from', '')
            to_hdr = headers.get('to', '')
            date_hdr = headers.get('date', '')
            msg_id_hdr = headers.get('message-id', '')
            label_ids = m_data.get('labelIds', [])
            is_unread = 'UNREAD' in label_ids
            is_starred = 'STARRED' in label_ids
            is_draft = 'DRAFT' in label_ids
            is_spam = 'SPAM' in label_ids
            is_trash = 'TRASH' in label_ids
            thread_id = m_data.get('threadId', '')

            # Match prospect company name
            prospect_company_name = None
            try:
                from prospects.models import ProspectContact, Prospect, OutreachEmail
                all_addrs = email_pattern.findall(from_hdr) + email_pattern.findall(to_hdr)
                if all_addrs:
                    contact = ProspectContact.objects.filter(official_email__in=all_addrs).select_related('prospect').first()
                    if contact and contact.prospect:
                        prospect_company_name = contact.prospect.company_name
                    else:
                        prospect = Prospect.objects.filter(official_email_address__in=all_addrs).first()
                        if prospect:
                            prospect_company_name = prospect.company_name
            except Exception:
                pass

            # Match email tracking
            tracking_info = None
            clean_mid = msg_id_hdr.strip().strip('<>').strip()
            if clean_mid:
                try:
                    from prospects.models import OutreachEmail
                    matched_oe = OutreachEmail.objects.filter(message_id__icontains=clean_mid).first()
                    if matched_oe:
                        tracking_info = {
                            'id': matched_oe.id,
                            'tracking_token': str(matched_oe.tracking_token),
                            'open_tracking_enabled': matched_oe.open_tracking_enabled,
                            'is_opened': matched_oe.is_opened,
                            'open_count': matched_oe.open_count,
                            'first_opened_at': matched_oe.first_opened_at.isoformat() if matched_oe.first_opened_at else (matched_oe.opened_at.isoformat() if matched_oe.opened_at else None),
                            'last_opened_at': matched_oe.last_opened_at.isoformat() if matched_oe.last_opened_at else (matched_oe.opened_at.isoformat() if matched_oe.opened_at else None),
                            'total_seconds_spent': matched_oe.total_seconds_spent,
                            'open_history': matched_oe.open_history,
                            'reading_engagement': 'Open tracking disabled' if not matched_oe.open_tracking_enabled else (('Deeply Engaged' if (matched_oe.open_count >= 3 or matched_oe.total_seconds_spent >= 60) else ('Read in Detail' if (matched_oe.total_seconds_spent >= 15 or matched_oe.open_count >= 2) else 'Quick Skim')) if matched_oe.is_opened else 'Not Viewed'),
                            'estimated_read_time_formatted': (f"{matched_oe.total_seconds_spent}s" if matched_oe.total_seconds_spent < 60 else f"{matched_oe.total_seconds_spent//60}m {matched_oe.total_seconds_spent%60}s") if (matched_oe.is_opened or matched_oe.total_seconds_spent > 0) else "0s",
                        }
                except Exception:
                    pass

            emails_list.append({
                'uid': msg_id,
                'id': msg_id,
                'thread_id': thread_id,
                'subject': subject,
                'from': from_hdr,
                'to': to_hdr,
                'date': date_hdr,
                'snippet': m_data.get('snippet', ''),
                'is_unread': is_unread,
                'is_starred': is_starred,
                'is_draft': is_draft,
                'is_spam': is_spam,
                'is_trash': is_trash,
                'label_ids': label_ids,
                'message_id': msg_id_hdr,
                'folder': folder,
                'is_owned': True,
                'prospect_company_name': prospect_company_name,
                'tracking': tracking_info,
            })

        return {'messages': emails_list, 'emails': emails_list, 'uidvalidity': 1, 'partial': partial}

    @classmethod
    def fetch_message_body(cls, credentials, msg_id):
        """
        Fetches full message body and attachment metadata from Gmail REST API.
        """
        token = cls.get_valid_access_token(credentials)
        url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}?format=full"
        req = urllib.request.Request(
            url,
            headers={
                'Authorization': f'Bearer {token}',
                'Accept': 'application/json',
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                m_data = json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            logger.error("Failed to fetch Gmail message body %s: %s", msg_id, e)
            return {'html_body': '', 'text_body': '', 'attachments': [], 'tracking': None}

        html_body = ''
        text_body = ''
        attachments = []
        import base64
        import re

        def _extract_parts(part):
            nonlocal html_body, text_body, attachments
            mime_type = part.get('mimeType', '')
            body_data = part.get('body', {}).get('data')
            filename = part.get('filename')
            att_id = part.get('body', {}).get('attachmentId')

            if filename and (att_id or body_data):
                att_entry = {
                    'filename': filename,
                    'size': part.get('body', {}).get('size', 0),
                    'attachment_id': att_id,
                    'part_index': len(attachments),
                    'content_type': mime_type,
                    'data': '',
                }
                if body_data:
                    try:
                        raw = base64.urlsafe_b64decode(body_data.encode('ASCII') + b'===')
                        att_entry['data'] = base64.b64encode(raw).decode('utf-8')
                    except Exception:
                        pass
                attachments.append(att_entry)

            if body_data and not filename:
                try:
                    decoded = base64.urlsafe_b64decode(body_data.encode('ASCII') + b'===').decode('utf-8', errors='ignore')
                    if mime_type == 'text/html':
                        html_body = decoded
                    elif mime_type == 'text/plain' and not text_body:
                        text_body = decoded
                except Exception:
                    pass

            for subpart in part.get('parts', []):
                _extract_parts(subpart)

        payload = m_data.get('payload', {})
        _extract_parts(payload)

        # Download attachment bodies if missing base64 data
        for att in attachments:
            if not att.get('data') and att.get('attachment_id'):
                try:
                    att_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}/attachments/{att['attachment_id']}"
                    att_req = urllib.request.Request(
                        att_url,
                        headers={
                            'Authorization': f'Bearer {token}',
                            'Accept': 'application/json',
                        }
                    )
                    with urllib.request.urlopen(att_req, timeout=10) as att_resp:
                        att_resp_data = json.loads(att_resp.read().decode('utf-8'))
                        raw_att = base64.urlsafe_b64decode(att_resp_data.get('data', '').encode('ASCII') + b'===')
                        att['data'] = base64.b64encode(raw_att).decode('utf-8')
                except Exception as exc:
                    logger.warning("Could not download attachment %s: %s", att.get('filename'), exc)

        orig_html = html_body
        if not html_body and text_body:
            html_body = f"<pre>{text_body}</pre>"

        if html_body:
            try:
                from accounts.template_utils import ensure_responsive_images
                html_body = ensure_responsive_images(html_body)
            except Exception:
                pass
            html_body = re.sub(r'<img[^>]*?email-tracking[^>]*?>', '', html_body, flags=re.IGNORECASE)

        # Detect tracking stats
        tracking_info = None
        clean_mid = ''
        for h in m_data.get('payload', {}).get('headers', []):
            if h.get('name', '').lower() == 'message-id':
                clean_mid = h.get('value', '').strip().strip('<>').strip()
                break

        token_match = re.search(r'email-tracking/([a-f0-9\-]{36})', orig_html or '')
        matched_oe = None
        try:
            from prospects.models import OutreachEmail
            if token_match:
                matched_oe = OutreachEmail.objects.filter(tracking_token=token_match.group(1)).first()
            if not matched_oe and clean_mid:
                matched_oe = OutreachEmail.objects.filter(message_id__icontains=clean_mid).first()

            if matched_oe:
                tracking_info = {
                    'id': matched_oe.id,
                    'tracking_token': str(matched_oe.tracking_token),
                    'open_tracking_enabled': matched_oe.open_tracking_enabled,
                    'is_opened': matched_oe.is_opened,
                    'open_count': matched_oe.open_count,
                    'first_opened_at': matched_oe.first_opened_at.isoformat() if matched_oe.first_opened_at else (matched_oe.opened_at.isoformat() if matched_oe.opened_at else None),
                    'last_opened_at': matched_oe.last_opened_at.isoformat() if matched_oe.last_opened_at else (matched_oe.opened_at.isoformat() if matched_oe.opened_at else None),
                    'total_seconds_spent': matched_oe.total_seconds_spent,
                    'open_history': matched_oe.open_history,
                    'reading_engagement': 'Open tracking disabled' if not matched_oe.open_tracking_enabled else (('Deeply Engaged' if (matched_oe.open_count >= 3 or matched_oe.total_seconds_spent >= 60) else ('Read in Detail' if (matched_oe.total_seconds_spent >= 15 or matched_oe.open_count >= 2) else 'Quick Skim')) if matched_oe.is_opened else 'Not Viewed'),
                    'estimated_read_time_formatted': (f"{matched_oe.total_seconds_spent}s" if matched_oe.total_seconds_spent < 60 else f"{matched_oe.total_seconds_spent//60}m {matched_oe.total_seconds_spent%60}s") if (matched_oe.is_opened or matched_oe.total_seconds_spent > 0) else "0s",
                }
        except Exception:
            pass

        label_ids = m_data.get('labelIds', [])
        return {
            'id': msg_id,
            'thread_id': m_data.get('threadId', ''),
            'label_ids': label_ids,
            'is_unread': 'UNREAD' in label_ids,
            'is_starred': 'STARRED' in label_ids,
            'is_draft': 'DRAFT' in label_ids,
            'is_spam': 'SPAM' in label_ids,
            'is_trash': 'TRASH' in label_ids,
            'html_body': html_body,
            'text_body': text_body,
            'attachments': attachments,
            'tracking': tracking_info,
        }

    @classmethod
    def send_message(cls, credentials, raw_mime_bytes, thread_id=None):
        """
        Sends an email message via Gmail REST API.
        """
        token = cls.get_valid_access_token(credentials)
        import base64
        encoded_message = base64.urlsafe_b64encode(raw_mime_bytes).decode('utf-8')
        body = {'raw': encoded_message}
        if thread_id:
            body['threadId'] = thread_id
        payload = json.dumps(body).encode('utf-8')

        url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode('utf-8'))

    @classmethod
    def modify_message(cls, credentials, msg_id, add_label_ids=None, remove_label_ids=None):
        """
        Modifies labels on a Gmail message (e.g. STARRED, UNREAD, SPAM, INBOX).
        """
        token = cls.get_valid_access_token(credentials)
        url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}/modify"
        payload = json.dumps({
            'addLabelIds': add_label_ids or [],
            'removeLabelIds': remove_label_ids or [],
        }).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode('utf-8'))

    @classmethod
    def trash_message(cls, credentials, msg_id):
        """
        Moves a message to Gmail Trash.
        """
        token = cls.get_valid_access_token(credentials)
        url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}/trash"
        req = urllib.request.Request(
            url,
            data=b'{}',
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode('utf-8'))

    @classmethod
    def untrash_message(cls, credentials, msg_id):
        """
        Restores a message from Gmail Trash.
        """
        token = cls.get_valid_access_token(credentials)
        url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}/untrash"
        req = urllib.request.Request(
            url,
            data=b'{}',
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode('utf-8'))

    @classmethod
    def delete_message(cls, credentials, msg_id):
        """
        Permanently deletes a message from Gmail.
        """
        token = cls.get_valid_access_token(credentials)
        url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}"
        req = urllib.request.Request(
            url,
            headers={
                'Authorization': f'Bearer {token}',
                'Accept': 'application/json',
            },
            method='DELETE',
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {'status': 'deleted'}

    @classmethod
    def save_draft(cls, credentials, raw_mime_bytes, draft_id=None, thread_id=None):
        """
        Creates or updates a Gmail draft.
        """
        import base64
        token = cls.get_valid_access_token(credentials)
        encoded_message = base64.urlsafe_b64encode(raw_mime_bytes).decode('utf-8')
        msg_obj = {'raw': encoded_message}
        if thread_id:
            msg_obj['threadId'] = thread_id

        if draft_id:
            url = f"https://gmail.googleapis.com/gmail/v1/users/me/drafts/{draft_id}"
            payload = json.dumps({'id': draft_id, 'message': msg_obj}).encode('utf-8')
            method = 'PUT'
        else:
            url = "https://gmail.googleapis.com/gmail/v1/users/me/drafts"
            payload = json.dumps({'message': msg_obj}).encode('utf-8')
            method = 'POST'

        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            method=method,
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode('utf-8'))

    @classmethod
    def delete_draft(cls, credentials, draft_id):
        """
        Deletes a draft from Gmail.
        """
        token = cls.get_valid_access_token(credentials)
        url = f"https://gmail.googleapis.com/gmail/v1/users/me/drafts/{draft_id}"
        req = urllib.request.Request(
            url,
            headers={
                'Authorization': f'Bearer {token}',
                'Accept': 'application/json',
            },
            method='DELETE',
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {'status': 'deleted'}

    @classmethod
    def send_draft(cls, credentials, draft_id):
        """
        Sends an existing Gmail draft.
        """
        token = cls.get_valid_access_token(credentials)
        url = "https://gmail.googleapis.com/gmail/v1/users/me/drafts/send"
        payload = json.dumps({'id': draft_id}).encode('utf-8')
        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            method='POST',
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode('utf-8'))


get_mail_credentials = GmailOAuthService.get_credentials


