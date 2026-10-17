"""Helpers that decide whether an outgoing email may carry the open-tracking pixel.

Open tracking is opt-in per email AND gated by the global
``settings.EMAIL_OPEN_TRACKING_ENABLED`` switch. The decision is always made on
the server; the frontend value is only a request.
"""
import html
import ipaddress
import re
import urllib.parse
import uuid

from django.conf import settings

_TRUE_VALUES = {'true', '1', 'yes', 'on', 'y', 't'}


def parse_bool(value, default=False):
    """Strictly parse a request value (bool / str / None) into a bool."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in _TRUE_VALUES


def global_open_tracking_enabled():
    """Whether the server allows open tracking according to settings."""
    return bool(getattr(settings, 'EMAIL_OPEN_TRACKING_ENABLED', False))


def validate_tracking_configuration(base_url=None):
    """Validate tracking base URL syntax and production security constraints.

    Returns:
        (is_valid: bool, error_message: str)
    """
    url = (base_url or getattr(settings, 'EMAIL_TRACKING_BASE_URL', '') or '').strip().rstrip('/')
    if not url:
        return False, "EMAIL_TRACKING_BASE_URL is not configured."

    try:
        parsed = urllib.parse.urlsplit(url)
    except Exception as exc:
        return False, f"Malformed EMAIL_TRACKING_BASE_URL: {exc}"

    if not parsed.scheme or not parsed.netloc:
        return False, "EMAIL_TRACKING_BASE_URL must be an absolute URL including scheme and hostname."

    # In production (DEBUG=False and not allow_local), require HTTPS
    is_local_dev = getattr(settings, 'DEBUG', False) or getattr(settings, 'EMAIL_TRACKING_ALLOW_LOCAL', False)

    if parsed.scheme.lower() not in ('http', 'https'):
        return False, f"Unsupported URL scheme '{parsed.scheme}'. Scheme must be HTTPS in production."

    if parsed.scheme.lower() != 'https' and not is_local_dev:
        return False, "EMAIL_TRACKING_BASE_URL must use HTTPS in production environments."

    if parsed.username or parsed.password:
        return False, "EMAIL_TRACKING_BASE_URL must not contain credentials."

    if parsed.query or parsed.fragment:
        return False, "EMAIL_TRACKING_BASE_URL must not contain query parameters or fragments."

    host = (parsed.hostname or '').lower()
    if not host:
        return False, "EMAIL_TRACKING_BASE_URL has an invalid or empty hostname."

    # Validate loopback / private IP literals
    is_loopback = host in ('localhost', '127.0.0.1', '::1')
    is_private_ip = False
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved:
            is_private_ip = True
    except ValueError:
        pass  # Hostname, not IP literal

    if (is_loopback or is_private_ip) and not is_local_dev:
        return (
            False,
            f"EMAIL_TRACKING_BASE_URL hostname '{host}' is a loopback/private address. "
            "Production tracking requires a publicly accessible HTTPS domain."
        )

    # Detect temporary tunnels in production if not explicitly allowed
    if any(tunnel in host for tunnel in ('.trycloudflare.com', '.localtunnel.me', '.ngrok-free.app')) and not is_local_dev:
        return (
            False,
            f"EMAIL_TRACKING_BASE_URL hostname '{host}' is a temporary tunnel. "
            "Production tracking requires an operator-controlled stable domain."
        )

    return True, ""


def is_tracking_configured_and_valid():
    """Check if tracking configuration is valid for use."""
    valid, _ = validate_tracking_configuration()
    return valid


def resolve_open_tracking(requested_value):
    """Effective tracking state: requested by the user AND permitted globally.

    An omitted/invalid request value means "not requested" (safe default).
    """
    return global_open_tracking_enabled() and parse_bool(requested_value, default=False)


def build_tracking_pixel_html(tracking_token):
    """Return a minimal, standard remote tracking beacon for an authorized tracked email.

    Renders a standard 1x1 remote pixel with escaped URL attribute and empty alt text.
    Removes unsupported "Verified Communication" badges and checkmarks.

    Note: Open tracking relies on recipient client remote image loading and cannot
    guarantee inbox placement or delivery across restrictive mail filters.
    """
    base_url = getattr(settings, 'EMAIL_TRACKING_BASE_URL', '').rstrip('/')
    tracking_url = f"{base_url}/api/email-tracking/{tracking_token}/"
    escaped_url = html.escape(tracking_url, quote=True)
    return (
        f'<img src="{escaped_url}" width="1" height="1" alt="" border="0" '
        'style="display:none;width:1px;height:1px;border:0;outline:none;" />'
    )


def strip_application_tracking_markup(html_str):
    """Remove any stale application-owned tracking images or verified communication badges.

    Preserves legitimate customer images (CID inline images, external logos,
    media uploads) and customer layout.
    """
    if not html_str:
        return html_str

    # Remove legacy "Verified Communication" wrapper blocks
    cleaned = re.sub(
        r'<div[^>]*?>\s*<img[^>]*?/api/email-tracking/[^>]*?>\s*<span[^>]*?>\s*Verified Communication\s*</span>\s*</div>',
        '',
        html_str,
        flags=re.IGNORECASE | re.DOTALL
    )

    # Remove any remaining application email-tracking img tags
    cleaned = re.sub(
        r'<img[^>]*?/api/email-tracking/[^>]*?>',
        '',
        cleaned,
        flags=re.IGNORECASE
    )

    # Remove orphan Verified Communication badge spans if any
    cleaned = re.sub(
        r'<span[^>]*?>\s*Verified Communication\s*</span>',
        '',
        cleaned,
        flags=re.IGNORECASE
    )

    return cleaned


def new_tracking_token():
    return uuid.uuid4()
