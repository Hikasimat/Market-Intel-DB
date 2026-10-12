"""
Helpers for LQ email templates / signatures.

* sanitize_email_html  - strips scripts, event handlers, unsafe URLs/CSS (untrusted input).
* render_placeholders  - safe {{placeholder}} substitution (no code execution, whitelist only).
* build_email_content  - shared by the compose-preview endpoint and the real send path
                         so that the preview always equals what is sent.
"""
import html as _html
import re

import nh3

MAX_HTML_BYTES = 2_000_000
MAX_PROJECT_BYTES = 10_000_000

ALLOWED_PLACEHOLDERS = (
    'contact_name', 'company_name', 'sender_name', 'sender_email', 'designation', 'website',
)
_PLACEHOLDER_RE = re.compile(r'\{\{\s*([a-zA-Z_]+)\s*\}\}')

_TAGS = {
    'a', 'abbr', 'b', 'blockquote', 'br', 'center', 'code', 'col', 'colgroup', 'div', 'em', 'font',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'i', 'img', 'li', 'ol', 'p', 'pre', 'small', 'span',
    'strong', 'sub', 'sup', 'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr', 'u', 'ul',
}
_GENERIC_ATTRS = {'style', 'class', 'id', 'title', 'align', 'valign', 'dir', 'lang'}
_TAG_ATTRS = {
    'a': {'href', 'target', 'name'},
    'img': {'src', 'alt', 'width', 'height', 'border'},
    'table': {'width', 'height', 'border', 'cellpadding', 'cellspacing', 'bgcolor'},
    'td': {'width', 'height', 'colspan', 'rowspan', 'bgcolor', 'background'},
    'th': {'width', 'height', 'colspan', 'rowspan', 'bgcolor'},
    'tr': {'bgcolor', 'height'},
    'col': {'width', 'span'},
    'font': {'color', 'face', 'size'},
}
_URL_ATTRS = {'href', 'src', 'background'}
_BAD_CSS = re.compile(r'(expression\s*\(|javascript:|vbscript:|behaviou?r\s*:|@import|-moz-binding|url\s*\()', re.I)
_SAFE_URL = re.compile(r'^(https?://|mailto:|tel:|#)', re.I)
_SAFE_DATA_IMAGE = re.compile(r'^data:image/(?:png|jpe?g|gif|webp);base64,[A-Za-z0-9+/=\s]+$', re.I)


def _attribute_filter(tag, attr, value):
    if attr == 'style':
        return None if _BAD_CSS.search(value) else value
    if attr in _URL_ATTRS:
        v = value.strip()
        if attr in ('src', 'background'):
            if v.lower().startswith('data:'):
                return v if _SAFE_DATA_IMAGE.match(v) else None
            if not v.lower().startswith(('http://', 'https://')):
                return None
            return v
        if not _SAFE_URL.match(v):
            return None
        return v
    return value


def sanitize_email_html(raw):
    """Return sanitized, email-safe HTML. Never trusts client-side GrapesJS output."""
    if not raw:
        return ''
    return _clean_with_generic(raw)


def _clean_with_generic(raw):
    attrs = {t: set(a) | _GENERIC_ATTRS for t, a in _TAG_ATTRS.items()}
    for t in _TAGS:
        attrs.setdefault(t, set(_GENERIC_ATTRS))
    return nh3.clean(
        raw,
        tags=_TAGS,
        clean_content_tags={'script', 'style', 'iframe', 'object', 'embed', 'noscript', 'template'},
        attributes=attrs,
        link_rel='noopener noreferrer',
        url_schemes={'http', 'https', 'mailto', 'tel', 'data'},
        attribute_filter=_attribute_filter,
        strip_comments=True,
    )


def html_to_text(html_str):
    """Plain-text rendering of (sanitized) HTML."""
    if not html_str:
        return ''
    t = re.sub(r'(?i)<br\s*/?>|</(p|div|tr|h[1-6]|li)>', '\n', html_str)
    t = nh3.clean(t, tags=set(), attributes={})
    t = _html.unescape(t)
    t = re.sub(r'[ \t]+\n', '\n', t)
    return re.sub(r'\n{3,}', '\n\n', t).strip()


def render_placeholders(content, context, escape=True):
    """Replace whitelisted {{placeholders}}; unknown/missing -> ''. Values are HTML-escaped by default."""
    def repl(m):
        key = m.group(1)
        if key not in ALLOWED_PLACEHOLDERS:
            return m.group(0)
        val = str(context.get(key) or '')
        return _html.escape(val) if escape else val
    return _PLACEHOLDER_RE.sub(repl, content or '')


def placeholder_context(mail_account, prospect, contact):
    return {
        'contact_name': getattr(contact, 'contact_name', '') if contact else '',
        'designation': getattr(contact, 'designation', '') if contact else '',
        'company_name': getattr(prospect, 'company_name', '') if prospect else '',
        'website': getattr(prospect, 'official_website_url', '') if prospect else '',
        'sender_name': getattr(mail_account, 'display_name', '') if mail_account else '',
        'sender_email': getattr(mail_account, 'email_address', '') if mail_account else '',
    }


class ComposeError(Exception):
    pass


def build_email_content(user, mail_account, prospect, to_emails, subject, body,
                        template_id=None, signature_id=None, body_edited=True):
    """
    Resolve the saved template / signature (owner-validated) and return a dict:
      subject, text_body, html_body, signature_text, signature_html
    The caller keeps full control of recipients, attachments, tracking and SMTP.
    """
    from .models import EmailTemplate, EmailSignatureTemplate
    from prospects.models import ProspectContact

    contact = None
    if prospect is not None and to_emails:
        contact = ProspectContact.objects.filter(
            prospect=prospect, official_email__in=[e for e in to_emails if e]
        ).first()
    ctx = placeholder_context(mail_account, prospect, contact)

    template = signature = None
    import uuid as _uuid
    try:
        template_id = _uuid.UUID(str(template_id)) if template_id else None
        signature_id = _uuid.UUID(str(signature_id)) if signature_id else None
    except ValueError:
        raise ComposeError('Invalid template or signature id.')
    if template_id:
        template = EmailTemplate.objects.filter(pk=template_id, owner=user).first()
        if not template:
            raise ComposeError('Email template not found.')
    if signature_id:
        signature = EmailSignatureTemplate.objects.filter(pk=signature_id, owner=user).first()
        if not signature:
            raise ComposeError('Signature not found.')

    out_subject = subject or ''
    text_body = render_placeholders(body or '', ctx, escape=False)
    html_body = None

    if template:
        if not out_subject and template.subject:
            out_subject = render_placeholders(template.subject, ctx, escape=False)
        if not body_edited and template.html:
            # Untouched template -> send the designed HTML (re-sanitized at send time).
            html_body = sanitize_email_html(render_placeholders(template.html, ctx, escape=True))
            text_body = render_placeholders(template.text or html_to_text(template.html), ctx, escape=False)

    if html_body is None:
        html_body = '<div style="font-family: sans-serif;">%s</div>' % _html.escape(text_body).replace('\n', '<br>')

    sig_text = sig_html = ''
    if signature:
        sig_html = sanitize_email_html(render_placeholders(signature.html, ctx, escape=True))
        sig_text = render_placeholders(signature.text or html_to_text(signature.html), ctx, escape=False)

    return {
        'subject': out_subject,
        'text_body': text_body,
        'html_body': html_body,
        'signature_text': sig_text,
        'signature_html': sig_html,
        'has_signature': signature is not None,
        'has_template': template is not None,
    }


_B64_IMG_PATTERN = re.compile(
    r'src\s*=\s*["\']data:image/(?P<subtype>png|jpe?g|gif|webp);base64,(?P<b64>[A-Za-z0-9+/=\s]+)["\']',
    re.IGNORECASE
)


def convert_base64_images_to_cid(html_str, domain='local'):
    """
    Finds all embedded data:image/... URIs in HTML, converts them to standard inline
    cid: references for cross-client compatibility (especially Gmail and Outlook),
    and returns (modified_html, list_of_inline_images).
    list_of_inline_images: [(cid, subtype, bytes), ...]
    """
    import base64
    from email.utils import make_msgid

    inline_images = []

    def repl(match):
        subtype = match.group('subtype').lower()
        if subtype == 'jpg':
            subtype = 'jpeg'
        b64_data = re.sub(r'\s+', '', match.group('b64'))
        try:
            img_bytes = base64.b64decode(b64_data)
        except Exception:
            return match.group(0)

        cid = make_msgid(domain=domain)[1:-1]
        inline_images.append((cid, subtype, img_bytes))
        return f'src="cid:{cid}"'

    modified_html = _B64_IMG_PATTERN.sub(repl, html_str)
    return modified_html, inline_images
