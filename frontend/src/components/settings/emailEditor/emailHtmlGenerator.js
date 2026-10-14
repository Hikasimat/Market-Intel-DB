/**
 * emailHtmlGenerator.js
 * Generates 100% email-client compatible HTML (Gmail, Outlook, Apple Mail, etc.)
 * using standard table-based layouts, inline styles, and responsive CSS.
 */

export const SMART_TAGS = [
  {
    key: 'contact_name',
    token: '{{contact_name}}',
    label: 'Contact Name',
    icon: '👤',
    desc: "Recipient's full name",
    sample: 'Jane Doe',
    color: 'bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100 hover:border-blue-300',
  },
  {
    key: 'company_name',
    token: '{{company_name}}',
    label: 'Company Name',
    icon: '🏢',
    desc: "Recipient's company name",
    sample: 'Acme Corp',
    color: 'bg-indigo-50 text-indigo-700 border-indigo-200 hover:bg-indigo-100 hover:border-indigo-300',
  },
  {
    key: 'designation',
    token: '{{designation}}',
    label: 'Job Title',
    icon: '💼',
    desc: "Recipient's designation or role",
    sample: 'Managing Director',
    color: 'bg-violet-50 text-violet-700 border-violet-200 hover:bg-violet-100 hover:border-violet-300',
  },
  {
    key: 'website',
    token: '{{website}}',
    label: 'Company Website',
    icon: '🌐',
    desc: "Recipient's website link",
    sample: 'https://acme.example',
    color: 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100 hover:border-emerald-300',
  },
  {
    key: 'sender_name',
    token: '{{sender_name}}',
    label: 'Your Name (Sender)',
    icon: '✍️',
    desc: 'Your sender display name',
    sample: 'Alex Morgan',
    color: 'bg-amber-50 text-amber-800 border-amber-200 hover:bg-amber-100 hover:border-amber-300',
  },
  {
    key: 'sender_email',
    token: '{{sender_email}}',
    label: 'Your Email (Sender)',
    icon: '✉️',
    desc: 'Your sender email address',
    sample: 'alex@company.com',
    color: 'bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100 hover:border-rose-300',
  },
];

const SAMPLE = SMART_TAGS.reduce((acc, t) => {
  acc[t.key] = t.sample;
  return acc;
}, {});

export const fillSample = (html) => {
  if (!html) return '';
  return html.replace(/\{\{\s*([a-zA-Z0-9_\s]+)\s*\}\}/g, (m, k) => {
    const raw = k.trim().toLowerCase().replace(/\s+/g, '_');
    const matched = SMART_TAGS.find((t) => t.key === raw || t.key.replace('_', '') === raw);
    return matched ? matched.sample : (SAMPLE[raw] ?? m);
  });
};

export const ensureResponsiveImages = (html) => {
  if (!html || !html.includes('<img')) return html;
  return html.replace(/<img\b([^>]*)>/gi, (match, attrs) => {
    if (/style\s*=\s*["'][^"']*max-width/i.test(attrs)) {
      return match;
    }
    if (/style\s*=\s*(["'])([^"']*)(\1)/i.test(attrs)) {
      return match.replace(/style\s*=\s*(["'])([^"']*)(\1)/i, 'style=$1max-width: 100%; height: auto; display: block; $2$1');
    }
    return `<img style="max-width: 100%; height: auto; display: block;" ${attrs}>`;
  });
};

export const resolveImageUrl = (url) => {
  if (!url) return '';
  const trimmed = String(url).trim();
  // If the URL points to an expired trycloudflare tunnel or local backend, normalize it to /media/...
  const match = trimmed.match(/^https?:\/\/[^/]+(\/media\/.*)$/i);
  if (match) {
    const isCloudflare = /trycloudflare\.com/i.test(trimmed);
    const isLocalhost = /localhost|127\.0\.0\.1/i.test(trimmed);
    if (isCloudflare || isLocalhost) {
      return match[1];
    }
  }
  return trimmed;
};

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[c]));

export const safeUrl = (u) => {
  const s = String(u || '').trim();
  if (/^(https?:\/\/|mailto:|tel:|#|\/)/i.test(s) || /\{\{[a-zA-Z0-9_]+\}\}/i.test(s)) {
    return s.replace(/"/g, '&quot;');
  }
  if (s) {
    return `https://${s}`.replace(/"/g, '&quot;');
  }
  return '';
};

/**
 * Render an individual element (used both at root level and inside columns)
 */
export const renderElementHtml = (el, isNested = false) => {
  if (!el) return '';
  const type = el.type;

  switch (type) {
    case 'header': {
      const bg = el.backgroundColor || '#1e293b';
      const textCol = el.textColor || '#ffffff';
      const align = el.align || 'center';
      const pad = el.padding || '24px';
      const border = el.border?.enabled ? `border: ${el.border.width || 1}px solid ${el.border.color || '#e2e8f0'};` : '';
      const resolvedLogo = resolveImageUrl(el.logoUrl);
      const logo = el.logoUrl ? `<img src="${safeUrl(resolvedLogo)}" alt="Logo" width="${Number(el.logoWidth) || 120}" style="max-width: 100%; height: auto; margin-bottom: 12px; display: inline-block;" />` : '';
      const title = el.title ? `<h1 style="margin: 0; font-size: 22px; font-weight: 700; color: ${textCol}; line-height: 1.3;">${el.title}</h1>` : '';
      const subtitle = el.subtitle ? `<p style="margin: 6px 0 0 0; font-size: 14px; color: ${textCol}; opacity: 0.85; line-height: 1.4;">${el.subtitle}</p>` : '';
      return `
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: ${bg}; ${border}">
          <tr>
            <td align="${align}" style="padding: ${pad}; text-align: ${align};">
              ${logo}
              ${title}
              ${subtitle}
            </td>
          </tr>
        </table>
      `;
    }

    case 'text': {
      const align = el.align || 'left';
      const fontFamily = el.fontFamily || 'Arial, Helvetica, sans-serif';
      const fontSize = el.fontSize ? `${el.fontSize}px` : (isNested ? '14px' : '15px');
      const color = el.color || '#334155';
      const lineHeight = el.lineHeight || '1.4';
      const defaultPad = isNested
        ? (el.backgroundColor && el.backgroundColor !== 'transparent' ? '6px 10px' : '2px 4px')
        : (el.backgroundColor && el.backgroundColor !== 'transparent' ? '12px 18px' : '8px 12px');
      const pad = el.padding || defaultPad;
      const bg = el.backgroundColor && el.backgroundColor !== 'transparent' ? `background-color: ${el.backgroundColor};` : '';
      const border = el.border?.enabled ? `border: ${el.border.width || 1}px solid ${el.border.color || '#e2e8f0'};` : '';
      const rawContent = el.content || '<p>Click to edit this text...</p>';
      const cleanContent = rawContent.replace(/<p(\s+style="([^"]*)")?>/gi, (match, _, existingStyle) => {
        if (existingStyle && /margin/i.test(existingStyle)) {
          return match;
        }
        const baseMargin = 'margin: 0 0 3px 0;';
        return existingStyle
          ? `<p style="${baseMargin} ${existingStyle}">`
          : `<p style="${baseMargin}">`;
      });
      return `
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="${bg} ${border}">
          <tr>
            <td style="padding: ${pad}; font-family: ${fontFamily}; font-size: ${fontSize}; color: ${color}; line-height: ${lineHeight}; text-align: ${align};">
              ${cleanContent}
            </td>
          </tr>
        </table>
      `;
    }

    case 'image': {
      const align = el.align || 'center';
      const pad = el.padding || (isNested ? '4px 6px' : '10px 14px');
      const widthVal = el.width ? Number(el.width) : 320;
      const widthAttr = widthVal ? `width="${widthVal}"` : 'width="100%"';
      const styleWidth = widthVal ? `max-width: ${widthVal}px;` : 'max-width: 100%;';
      const resolvedImg = resolveImageUrl(el.url);
      const bg = el.backgroundColor && el.backgroundColor !== 'transparent' ? `background-color: ${el.backgroundColor};` : '';
      const border = el.border?.enabled ? `border: ${el.border.width || 1}px solid ${el.border.color || '#e2e8f0'};` : '';
      const img = `<img src="${safeUrl(resolvedImg)}" alt="${esc(el.alt || 'Image')}" ${widthAttr} style="${styleWidth} width: 100%; height: auto; display: block; border: 0;" />`;
      const linkedImg = el.linkUrl ? `<a href="${safeUrl(el.linkUrl)}" target="_blank" rel="noopener noreferrer" style="text-decoration: none; display: inline-block;">${img}</a>` : img;
      return `
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="${bg} ${border}">
          <tr>
            <td align="${align}" style="padding: ${pad}; text-align: ${align}; ${bg}">
              ${linkedImg}
            </td>
          </tr>
        </table>
      `;
    }

    case 'button': {
      const align = el.align || 'center';
      const pad = el.padding || '16px';
      const bg = el.backgroundColor || '#2563eb';
      const textCol = el.textColor || '#ffffff';
      const fontSize = el.fontSize ? `${el.fontSize}px` : '15px';
      const radius = el.borderRadius !== undefined ? `${el.borderRadius}px` : '8px';
      const url = safeUrl(el.url || '#');
      const label = el.label || 'Click Here';
      return `
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td align="${align}" style="padding: ${pad}; text-align: ${align};">
              <!--[if mso]>
              <v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word" href="${url}" style="height:44px;v-text-anchor:middle;width:200px;" arcsize="18%" strokecolor="${bg}" fillcolor="${bg}">
                <w:anchorlock/>
                <center style="color:${textCol};font-family:Arial,sans-serif;font-size:${fontSize};font-weight:bold;">${esc(label)}</center>
              </v:roundrect>
              <![endif]-->
              <a href="${url}" target="_blank" rel="noopener noreferrer" style="background-color: ${bg}; border-radius: ${radius}; color: ${textCol}; display: inline-block; font-family: Arial, Helvetica, sans-serif; font-size: ${fontSize}; font-weight: 700; line-height: 44px; text-align: center; text-decoration: none; width: auto; padding: 0 28px; -webkit-text-size-adjust: none; mso-hide: all;">
                ${esc(label)}
              </a>
            </td>
          </tr>
        </table>
      `;
    }

    case 'divider': {
      const color = el.color || '#e2e8f0';
      const thick = el.thickness || 1;
      const width = el.width || 100;
      const top = el.paddingTop !== undefined ? el.paddingTop : 16;
      const bottom = el.paddingBottom !== undefined ? el.paddingBottom : 16;
      const bg = el.backgroundColor && el.backgroundColor !== 'transparent' ? `background-color: ${el.backgroundColor};` : '';
      return `
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="${bg}">
          <tr>
            <td style="padding-top: ${top}px; padding-bottom: ${bottom}px; ${bg}">
              <table width="${width}%" align="${el.align || 'center'}" cellpadding="0" cellspacing="0" border="0" style="margin: 0 auto;">
                <tr>
                  <td style="border-top: ${thick}px solid ${color}; font-size: 1px; line-height: 1px; height: 1px;">&nbsp;</td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      `;
    }

    case 'spacer': {
      const h = Number(el.height) || 24;
      const bg = el.backgroundColor && el.backgroundColor !== 'transparent' ? `background-color: ${el.backgroundColor};` : '';
      return `
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="${bg}">
          <tr>
            <td height="${h}" style="font-size: 1px; line-height: ${h}px; height: ${h}px; mso-line-height-rule: exactly; ${bg}">&nbsp;</td>
          </tr>
        </table>
      `;
    }

    case 'row': {
      const cols = el.columns || [];
      if (!cols.length) return '';
      const colTds = cols.map((col) => {
        const w = col.widthPercent || Math.round(100 / cols.length);
        const bg = col.backgroundColor && col.backgroundColor !== 'transparent' ? `background-color: ${col.backgroundColor};` : '';
        const pad = col.padding || '4px';
        const border = col.border?.enabled ? `border: ${col.border.width || 1}px solid ${col.border.color || '#e2e8f0'};` : '';
        const content = (col.elements || []).map((child) => renderElementHtml(child, true)).join('\n');
        return `
          <td class="col-stack" width="${w}%" valign="top" style="width: ${w}%; padding: ${pad}; ${bg} ${border} box-sizing: border-box;">
            ${content || '&nbsp;'}
          </td>
        `;
      }).join('\n');
      const rowBg = el.backgroundColor && el.backgroundColor !== 'transparent' ? `background-color: ${el.backgroundColor};` : '';
      const rowBorder = el.border?.enabled ? `border: ${el.border.width || 1}px solid ${el.border.color || '#e2e8f0'};` : '';
      return `
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="${rowBg} ${rowBorder}">
          <tr>
            ${colTds}
          </tr>
        </table>
      `;
    }

    case 'signature': {
      const sigHtml = el.html || '';
      return `
        <table width="100%" cellpadding="0" cellspacing="0" border="0">
          <tr>
            <td style="padding: ${isNested ? '4px' : '12px'};">
              ${sigHtml}
            </td>
          </tr>
        </table>
      `;
    }

    case 'footer': {
      const bg = el.backgroundColor || '#f8fafc';
      const textCol = el.textColor || '#64748b';
      const align = el.align || 'center';
      const pad = el.padding || '16px 14px';
      const border = el.border?.enabled ? `border-top: ${el.border.width || 1}px solid ${el.border.color || '#e2e8f0'};` : 'border-top: 1px solid #e2e8f0;';
      const text = el.text ? `<p style="margin: 0 0 6px 0; font-size: 12px; color: ${textCol}; line-height: 1.4;">${el.text}</p>` : '';
      const unsub = el.unsubscribeText ? `
        <p style="margin: 4px 0 0 0; font-size: 11px; color: ${textCol}; opacity: 0.85;">
          ${el.unsubscribeText} ${el.unsubscribeUrl ? `<a href="${safeUrl(el.unsubscribeUrl)}" style="color: ${textCol}; text-decoration: underline;">Unsubscribe</a>` : ''}
        </p>
      ` : '';
      return `
        <table width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color: ${bg}; ${border}">
          <tr>
            <td align="${align}" style="padding: ${pad}; text-align: ${align}; font-family: Arial, Helvetica, sans-serif;">
              ${text}
              ${unsub}
            </td>
          </tr>
        </table>
      `;
    }

    default:
      return '';
  }
};

/**
 * Render a column layout block
 */
const renderColumnsBlock = (block) => {
  const cols = block.columns || [];
  if (!cols.length) return '';

  const colTds = cols.map((col) => {
    const w = col.widthPercent || Math.round(100 / cols.length);
    const bg = col.backgroundColor && col.backgroundColor !== 'transparent' ? `background-color: ${col.backgroundColor};` : '';
    const pad = col.padding || '6px';
    const border = col.border?.enabled ? `border: ${col.border.width || 1}px solid ${col.border.color || '#e2e8f0'};` : '';
    const content = (col.elements || []).map((child) => renderElementHtml(child, true)).join('\n');
    return `
      <td class="col-stack" width="${w}%" valign="top" style="width: ${w}%; padding: ${pad}; ${bg} ${border} box-sizing: border-box;">
        ${content || '&nbsp;'}
      </td>
    `;
  }).join('\n');

  const blockBg = block.backgroundColor && block.backgroundColor !== 'transparent' ? `background-color: ${block.backgroundColor};` : '';
  const blockBorder = block.border?.enabled ? `border: ${block.border.width || 1}px solid ${block.border.color || '#e2e8f0'};` : '';
  const blockPad = block.padding || '0px';

  return `
    <table width="100%" cellpadding="0" cellspacing="0" border="0" style="${blockBg} ${blockBorder}">
      <tr>
        <td style="padding: ${blockPad};">
          <table width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
              ${colTds}
            </tr>
          </table>
        </td>
      </tr>
    </table>
  `;
};

/**
 * Generate complete email document HTML
 */
export const generateEmailHtml = (templateState) => {
  const { blocks = [], globalStyles = {} } = templateState || {};
  const canvasBg = globalStyles.backgroundColor || '#f1f5f9';
  const containerBg = globalStyles.canvasColor || '#ffffff';
  const maxWidth = globalStyles.maxWidth || '600px';

  const bodyContent = blocks.map((block) => {
    if (block.type === 'columns') {
      return renderColumnsBlock(block);
    }
    return renderElementHtml(block, false);
  }).join('\n');

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Email</title>
  <!--[if mso]>
  <style type="text/css">
    body, table, td, p, a, h1, h2, h3 { font-family: Arial, Helvetica, sans-serif !important; }
  </style>
  <![endif]-->
  <style type="text/css">
    body { margin: 0; padding: 0; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }
    table, td { border-collapse: collapse; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }
    p, h1, h2, h3, h4, h5, h6 { margin: 0; padding: 0; }
    p { margin-bottom: 3px; }
    p:last-child { margin-bottom: 0; }
    a { text-decoration: none; color: inherit; }
    img { border: 0; height: auto; line-height: 100%; outline: none; text-decoration: none; -ms-interpolation-mode: bicubic; max-width: 100%; }
    @media only screen and (max-width: 620px) {
      .email-container { width: 100% !important; max-width: 100% !important; border-radius: 0 !important; }
      .col-stack { display: block !important; width: 100% !important; max-width: 100% !important; box-sizing: border-box !important; }
    }
  </style>
</head>
<body style="margin: 0; padding: 24px 0; background-color: ${canvasBg};">
  <center>
    <!--[if mso]>
    <table align="center" border="0" cellspacing="0" cellpadding="0" width="600">
    <tr><td>
    <![endif]-->
    <table class="email-container" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width: ${maxWidth}; margin: 0 auto; background-color: ${containerBg}; border-radius: 8px; overflow: hidden; border: 1px solid #e2e8f0;">
      <tr>
        <td style="padding: 0;">
          ${bodyContent}
        </td>
      </tr>
    </table>
    <!--[if mso]>
    </td></tr></table>
    <![endif]-->
  </center>
</body>
</html>`;
};

/**
 * Migration helper: If an existing template only has raw HTML and no blocks JSON,
 * safely wraps the content into an editable block so nothing is lost.
 */
export const parseHtmlToBlocks = (html) => {
  if (!html || !html.trim()) {
    return [];
  }

  // Extract body contents if a full document is provided
  let innerHtml = html;
  let extractedStyles = '';
  const styleMatch = html.match(/<style\b[^>]*>([\s\S]*?)<\/style>/gi);
  if (styleMatch) {
    extractedStyles = styleMatch.join('\n');
  }

  const bodyMatch = /<body[^>]*>([\s\S]*?)<\/body>/i.exec(html);
  if (bodyMatch) {
    innerHtml = (extractedStyles ? extractedStyles + '\n' : '') + bodyMatch[1];
  }

  // Remove mso conditionals and clean scripts
  innerHtml = innerHtml
    .replace(/<!--\[if[\s\S]*?<!\[endif\]-->/gi, '')
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '')
    .trim();

  // If the inner HTML was wrapped in a standard email-container table, unwrap it cleanly
  const containerMatch = /<table[^>]*class=["'][^"']*email-container[^"']*["'][^>]*>[\s\S]*?<td[^>]*style=["'][^"']*padding:\s*0[^"']*["'][^>]*>([\s\S]*?)<\/td>[\s\S]*?<\/table>/i.exec(innerHtml);
  if (containerMatch && containerMatch[1]?.trim()) {
    innerHtml = containerMatch[1].trim();
  }

  const hasComplexLayout = /<table|<div|<section/i.test(innerHtml);

  return [
    {
      id: `block_${Date.now()}_imported`,
      type: 'text',
      content: innerHtml,
      align: 'left',
      fontSize: 14,
      color: '#334155',
      lineHeight: '1.5',
      padding: hasComplexLayout ? '0px' : '12px 16px',
      backgroundColor: 'transparent',
    },
  ];
};
