"""
Helpers for LQ email templates / signatures.

* sanitize_email_html  - strips scripts, event handlers, unsafe URLs/CSS (untrusted input).
* render_placeholders  - safe {{placeholder}} substitution (no code execution, whitelist only).
* build_email_content  - shared by the compose-preview endpoint and the real send path
                         so that the preview always equals what is sent.
"""
import difflib
import html as _html
import re

import nh3

MAX_HTML_BYTES = 2_000_000
MAX_PROJECT_BYTES = 10_000_000

ALLOWED_PLACEHOLDERS = (
    'contact_name', 'company_name', 'sender_name', 'sender_email', 'designation', 'website',
)
_PLACEHOLDER_RE = re.compile(r'\{\{\s*([a-zA-Z0-9_\s]+)\s*\}\}')

NORMALIZE_MAP = {
    'contact_name': 'contact_name',
    'contact': 'contact_name',
    'recipient_name': 'contact_name',
    'client_name': 'contact_name',
    'company_name': 'company_name',
    'company': 'company_name',
    'sender_name': 'sender_name',
    'my_name': 'sender_name',
    'your_name': 'sender_name',
    'sender_email': 'sender_email',
    'my_email': 'sender_email',
    'your_email': 'sender_email',
    'designation': 'designation',
    'job_title': 'designation',
    'title': 'designation',
    'website': 'website',
    'company_website': 'website',
}

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
            if v.startswith(('/', '/media/', '/static/')):
                return v
            if v.lower().startswith('cid:'):
                return v
            if not v.lower().startswith(('http://', 'https://')):
                return None
            return v
        if v.startswith('/'):
            return v
        if not _SAFE_URL.match(v):
            return None
        return v
    return value


def ensure_responsive_images(html_str):
    """
    Ensure all <img> tags have max-width: 100% and height: auto so they adapt cleanly
    to desktop, tablet, and mobile email clients without overflowing.
    """
    if not html_str or '<img' not in html_str.lower():
        return html_str

    def _fix_img(match):
        tag = match.group(0)
        style_match = re.search(r'style=(["\'])(.*?)\1', tag, flags=re.IGNORECASE)
        if style_match:
            style_content = style_match.group(2)
            if 'max-width' not in style_content.lower():
                new_style = f"max-width: 100%; height: auto; {style_content}".strip()
                tag = tag[:style_match.start(2)] + new_style + tag[style_match.end(2):]
        else:
            tag = re.sub(r'(?i)<img\b', '<img style="max-width: 100%; height: auto;"', tag, count=1)
        return tag

    return re.sub(r'(?i)<img\b[^>]*>', _fix_img, html_str)


def sanitize_email_html(raw):
    """Return sanitized, email-safe HTML. Never trusts client-side editor output."""
    if not raw:
        return ''
    cleaned = _clean_with_generic(raw)
    return ensure_responsive_images(cleaned)


def _clean_with_generic(raw):
    attrs = {t: set(a) | _GENERIC_ATTRS for t, a in _TAG_ATTRS.items()}
    for t in _TAGS:
        attrs.setdefault(t, set(_GENERIC_ATTRS))
    return nh3.clean(
        raw,
        tags=_TAGS,
        clean_content_tags={'script', 'style', 'iframe', 'object', 'embed', 'noscript', 'template', 'head', 'title', 'meta'},
        attributes=attrs,
        link_rel='noopener noreferrer',
        url_schemes={'http', 'https', 'mailto', 'tel', 'data', 'cid'},
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
        raw_key = m.group(1).strip()
        norm_key = raw_key.lower().replace(' ', '_')
        canonical_key = NORMALIZE_MAP.get(norm_key, norm_key)
        if canonical_key not in ALLOWED_PLACEHOLDERS:
            return m.group(0)
        val = str(context.get(canonical_key) or '')
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


def update_template_html_with_body(template_html, base_text, edited_text, ctx):
    """
    Applies edited body text into template_html so that the template design,
    tables, styling, headers, footers, and embedded images are fully preserved.
    """
    rendered_html = render_placeholders(template_html, ctx, escape=True)
    if not edited_text or edited_text.strip() == (base_text or '').strip():
        return rendered_html

    base_lines = [l.strip() for l in (base_text or '').splitlines() if l.strip()]
    edited_lines = [l.strip() for l in edited_text.splitlines() if l.strip()]

    if not base_lines:
        content_html = "".join(f'<p style="margin: 0 0 12px 0; color: #334155; font-size: 14px; line-height: 1.6;">{_html.escape(l)}</p>' for l in edited_lines)
        m = re.search(r'(<td[^>]*>)(.*?)(</td>)', rendered_html, flags=re.DOTALL | re.IGNORECASE)
        if m:
            return rendered_html[:m.start(2)] + content_html + rendered_html[m.end(2):]
        return rendered_html + content_html

    sm = difflib.SequenceMatcher(None, base_lines, edited_lines)
    opcodes = sm.get_opcodes()
    has_match = any(tag == 'equal' for tag, _, _, _, _ in opcodes)

    result_html = rendered_html
    replaced_any = False

    if has_match:
        for tag, i1, i2, j1, j2 in opcodes:
            if tag == 'replace':
                old_chunk = " ".join(base_lines[i1:i2])
                new_chunk = "<br>".join(_html.escape(l) for l in edited_lines[j1:j2])
                escaped_old = _html.escape(old_chunk)
                if escaped_old in result_html:
                    result_html = result_html.replace(escaped_old, new_chunk, 1)
                    replaced_any = True
                else:
                    for old_line, new_line in zip(base_lines[i1:i2], edited_lines[j1:j2]):
                        esc_l = _html.escape(old_line)
                        if esc_l in result_html:
                            result_html = result_html.replace(esc_l, _html.escape(new_line), 1)
                            replaced_any = True
            elif tag == 'delete':
                for old_line in base_lines[i1:i2]:
                    esc_l = _html.escape(old_line)
                    if esc_l in result_html:
                        result_html = result_html.replace(esc_l, '', 1)
                        replaced_any = True
            elif tag == 'insert':
                new_chunk = "".join(f'<p style="margin: 12px 0 0 0; color: #334155; font-size: 14px; line-height: 1.6;">{_html.escape(l)}</p>' for l in edited_lines[j1:j2])
                if i1 > 0 and i1 - 1 < len(base_lines):
                    prev_esc = _html.escape(base_lines[i1 - 1])
                    idx = result_html.find(prev_esc)
                    if idx != -1:
                        end_tag = result_html.find('</', idx)
                        if end_tag != -1:
                            close_tag_end = result_html.find('>', end_tag) + 1
                            result_html = result_html[:close_tag_end] + new_chunk + result_html[close_tag_end:]
                            replaced_any = True

    if not replaced_any:
        content_html = "".join(f'<p style="margin: 0 0 12px 0; color: #334155; font-size: 14px; line-height: 1.6;">{_html.escape(l)}</p>' for l in edited_lines)
        m = re.search(r'(<td[^>]*>)(.*?)(</td>)', result_html, flags=re.DOTALL | re.IGNORECASE)
        if m:
            result_html = result_html[:m.start(2)] + content_html + result_html[m.end(2):]
        else:
            subbed, count = re.subn(r'<(p|h[1-6]|div)[^>]*>.*?</\1>', content_html, result_html, count=1, flags=re.DOTALL | re.IGNORECASE)
            if count > 0:
                result_html = subbed
            else:
                result_html = f'<div style="font-family: Arial, sans-serif;">{content_html}</div>'

    return result_html


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
        base_text = render_placeholders(template.text or html_to_text(template.html), ctx, escape=False)
        if not body_edited or not text_body or text_body.strip() == base_text.strip():
            # Untouched template -> send the designed HTML
            html_body = sanitize_email_html(render_placeholders(template.html, ctx, escape=True))
            text_body = base_text
        elif template.html:
            # Body edited -> apply the edited text into the designed template HTML
            html_body = sanitize_email_html(
                update_template_html_with_body(template.html, base_text, text_body, ctx)
            )

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
    Finds all embedded data:image/... URIs and local /media/... images in HTML,
    converts them to standard inline cid: references for cross-client compatibility
    (so images render flawlessly in Gmail, Outlook, Apple Mail without external host proxy issues),
    and returns (modified_html, list_of_inline_images).
    list_of_inline_images: [(cid, subtype, bytes), ...]
    """
    import os
    import base64
    from email.utils import make_msgid
    from django.conf import settings
    from django.core.files.storage import default_storage

    inline_images = []

    # 1. Convert base64 data URIs to inline CID
    def repl_b64(match):
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

    modified_html = _B64_IMG_PATTERN.sub(repl_b64, html_str)

    # 2. Convert local /media/ image URLs to inline CID attachments
    media_img_re = re.compile(r'src\s*=\s*["\'](?P<url>[^"\']*?/media/[^"\']+)["\']', re.IGNORECASE)

    def repl_media(match):
        url = match.group('url')
        if 'track' in url.lower():
            return match.group(0)

        rel_path = url.split('/media/')[-1].split('?')[0].split('#')[0]
        if not rel_path:
            return match.group(0)
        import urllib.parse
        rel_path = urllib.parse.unquote(rel_path)

        img_bytes = None
        try:
            if default_storage.exists(rel_path):
                with default_storage.open(rel_path, 'rb') as f:
                    img_bytes = f.read()
        except Exception:
            pass

        if not img_bytes and hasattr(settings, 'MEDIA_ROOT') and settings.MEDIA_ROOT:
            local_path = os.path.join(settings.MEDIA_ROOT, rel_path.replace('/', os.sep))
            if os.path.isfile(local_path):
                try:
                    with open(local_path, 'rb') as f:
                        img_bytes = f.read()
                except Exception:
                    pass

        if not img_bytes:
            return match.group(0)

        ext = os.path.splitext(rel_path)[1].lower().lstrip('.')
        subtype = ext if ext in ('png', 'jpeg', 'jpg', 'gif', 'webp') else 'png'
        if subtype == 'jpg':
            subtype = 'jpeg'

        cid = make_msgid(domain=domain)[1:-1]
        inline_images.append((cid, subtype, img_bytes))
        return f'src="cid:{cid}"'

    modified_html = media_img_re.sub(repl_media, modified_html)
    return modified_html, inline_images
