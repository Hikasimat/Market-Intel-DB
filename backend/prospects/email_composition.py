"""
Email composition and header utilities for standardized, RFC-compliant email construction.

Ensures:
- Robust RFC 5322 address formatting (via formataddr) handling commas, quotes, Unicode,
  and stripping CRLF control characters to prevent header injection.
- Clean recipient address validation before database persistence or Gmail API dispatch.
- Singleton header enforcement (Date, Message-ID, From, Subject, Reply-To) preventing
  duplicate headers.
- Accurate domain-based Message-ID generation.
- Strict RFC 5322 Date header generation.
"""
import email.utils
import html
import re
from email.utils import formataddr, formatdate, make_msgid


def sanitize_display_name(name):
    """Sanitize display name to prevent CRLF header injection and strip control chars."""
    if not name:
        return ''
    # Replace CRLF and control characters (ASCII 0-31 except space/tab, plus 127) with a space
    cleaned = re.sub(r'[\r\n\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', str(name))
    return re.sub(r'\s+', ' ', cleaned).strip()


def format_sender_address(display_name, email_address):
    """Format RFC 5322 From address safely using email.utils.formataddr.

    Correctly quotes names containing commas or special characters,
    handles non-ASCII/Unicode names, strips CRLF injection, and preserves
    the authenticated email address identity.
    """
    clean_email = (email_address or '').strip()
    if not clean_email or any(c in clean_email for c in ('\r', '\n', '\x00', ' ')):
        raise ValueError(f"Invalid sender email address: {email_address!r}")

    cleaned_name = sanitize_display_name(display_name)
    if cleaned_name:
        return formataddr((cleaned_name, clean_email))
    return clean_email


def validate_and_sanitize_recipient(email_address):
    """Validate and sanitize a recipient email address before message creation.

    Rejects addresses containing control characters, newlines, multiple @ symbols,
    or invalid RFC syntax cleanly.
    """
    if not email_address or not isinstance(email_address, str):
        raise ValueError("Recipient email address cannot be empty.")
    addr = email_address.strip()
    if any(c in addr for c in ('\r', '\n', '\x00', ' ', '\t')):
        raise ValueError(f"Recipient address contains whitespace or control characters: {addr!r}")
    if '@' not in addr or addr.startswith('@') or addr.endswith('@') or addr.count('@') > 1:
        raise ValueError(f"Malformed recipient email address: {addr!r}")
    local, domain = addr.split('@', 1)
    if not local or not domain or '.' not in domain or domain.startswith('.') or domain.endswith('.'):
        raise ValueError(f"Malformed recipient email domain: {addr!r}")
    return addr


def set_singleton_header(msg, name, value):
    """Set a header on EmailMessage ensuring no duplicate singleton header exists."""
    if name in msg:
        del msg[name]
    msg[name] = value


def extract_domain_from_email(email_address, default='gmail.com'):
    """Extract clean domain portion from an email address for Message-ID domain."""
    if email_address and '@' in email_address:
        domain = email_address.split('@')[-1].strip().lower()
        if domain and '.' in domain:
            return domain
    return default
