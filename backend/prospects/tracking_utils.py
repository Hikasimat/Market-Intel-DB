"""Helpers that decide whether an outgoing email may carry the open-tracking pixel.

Open tracking is opt-in per email AND gated by the global
``settings.EMAIL_OPEN_TRACKING_ENABLED`` switch. The decision is always made on
the server; the frontend value is only a request.
"""
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
    return bool(getattr(settings, 'EMAIL_OPEN_TRACKING_ENABLED', False))


def resolve_open_tracking(requested_value):
    """Effective tracking state: requested by the user AND permitted globally.

    An omitted/invalid request value means "not requested" (safe default).
    """
    return global_open_tracking_enabled() and parse_bool(requested_value, default=False)


def build_tracking_pixel_html(tracking_token):
    """Return the visible, spam-safe signature beacon for a tracking token.

    Attaches cleanly as a visible verified communication badge in the email signature
    without any hidden tags (no display:none, no 1x1 invisible hacks) to prevent spam filtering.
    """
    tracking_url = f"{settings.EMAIL_TRACKING_BASE_URL}/api/email-tracking/{tracking_token}/"
    return (
        '<div style="margin-top:12px;padding-top:8px;border-top:1px solid #e2e8f0;'
        'display:inline-block;font-family:sans-serif;font-size:11px;color:#94a3b8;line-height:16px;">'
        f'<img src="{tracking_url}" width="16" height="16" alt="✓" '
        'style="display:inline-block;vertical-align:middle;margin-right:4px;border:0;outline:none;" />'
        '<span style="vertical-align:middle;color:#64748b;font-size:10px;font-weight:500;">'
        'Verified Communication</span>'
        '</div>'
    )


def new_tracking_token():
    return uuid.uuid4()
