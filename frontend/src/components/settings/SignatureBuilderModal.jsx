import React, { useState, useEffect } from 'react';
import {
  PenTool, Upload, X, Check, Save, Star, Eye,
  Globe, Phone, Mail, Plus, Trash2, ExternalLink,
  Image as ImageIcon, UserCheck, ShieldCheck, Link as LinkIcon,
  Sparkles, AlertCircle
} from 'lucide-react';
import { toast } from 'react-toastify';
import { designApi, errorMessage } from '../../services/designApi';

// High-compatibility public CDN social icon URLs (lightweight, ~2KB each, supported across all email clients including Outlook)
export const SOCIAL_PLATFORMS = [
  { id: 'linkedin', name: 'LinkedIn', icon: 'https://cdn-icons-png.flaticon.com/512/3536/3536505.png', placeholder: 'https://linkedin.com/in/... or company/...' },
  { id: 'twitter', name: 'X (Twitter)', icon: 'https://cdn-icons-png.flaticon.com/512/5969/5969020.png', placeholder: 'https://x.com/...' },
  { id: 'facebook', name: 'Facebook', icon: 'https://cdn-icons-png.flaticon.com/512/5968/5968764.png', placeholder: 'https://facebook.com/...' },
  { id: 'instagram', name: 'Instagram', icon: 'https://cdn-icons-png.flaticon.com/512/3955/3955024.png', placeholder: 'https://instagram.com/...' },
  { id: 'youtube', name: 'YouTube', icon: 'https://cdn-icons-png.flaticon.com/512/3670/3670147.png', placeholder: 'https://youtube.com/@...' },
  { id: 'whatsapp', name: 'WhatsApp', icon: 'https://cdn-icons-png.flaticon.com/512/3670/3670051.png', placeholder: 'https://wa.me/...' },
  { id: 'github', name: 'GitHub', icon: 'https://cdn-icons-png.flaticon.com/512/733/733553.png', placeholder: 'https://github.com/...' },
];

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
}[c]));

const safeUrl = (u) => {
  const s = String(u || '').trim();
  if (/^(https?:\/\/|mailto:|tel:)/i.test(s) || /\{\{[a-zA-Z0-9_]+\}\}/i.test(s)) {
    return esc(s);
  }
  return '';
};

/**
 * Builds clean, table-based email signature HTML
 * Fully compliant with signature proportion standards:
 * - Total border option (bounding container border)
 * - 300px to 600px width limit, 70px to 200px height (~3:1 to 4:1 aspect ratio)
 * - Hyperlinks: tel:, mailto:, safeUrl(website)
 * - Multiple websites support
 * - Multiple logos / headshots / badges (horizontal: 200-320px, square/headshot: 60-100px)
 * - Call to Action (CTA) redirecting button
 * - Social icons: 20-28px, icon-only with hyperlink (NO text, NO raw URL)
 */
export const buildSignatureHtml = (fields) => {
  const color = esc(fields.accentColor || '#1e3a8a');
  const textColor = esc(fields.textColor || '#334155');
  const font = esc(fields.font || 'Arial, Helvetica, sans-serif');
  const align = ['left', 'center', 'right'].includes(fields.align) ? fields.align : 'left';
  const size = Number(fields.size) || 13;
  const layout = fields.layout || 'side-by-side';
  const iconSize = Math.max(20, Math.min(28, Number(fields.socialIconSize) || 24));

  // 1. Social Links with Logo only, no text/url, pure hyperlink format
  const activeSocials = [];
  SOCIAL_PLATFORMS.forEach((p) => {
    const isShown = fields[`show_${p.id}`] ?? fields[`show${p.id.charAt(0).toUpperCase() + p.id.slice(1)}`];
    const url = fields[p.id] || fields[`${p.id}_url`];
    if (isShown && url) {
      const href = safeUrl(url);
      if (href) {
        activeSocials.push(`
          <a href="${href}" target="_blank" rel="noopener noreferrer" style="display:inline-block;text-decoration:none;margin-right:8px;vertical-align:middle;">
            <img src="${p.icon}" alt="${esc(p.name)}" width="${iconSize}" height="${iconSize}" style="width:${iconSize}px;height:${iconSize}px;display:inline-block;border:0;vertical-align:middle;" />
          </a>
        `.trim());
      }
    }
  });

  const socialsHtml = activeSocials.length > 0 
    ? `<div style="margin-top:10px;line-height:1;">${activeSocials.join(' ')}</div>` 
    : '';

  // 2. Websites list (Primary website + multiple secondary websites)
  const websiteItems = [];
  if (fields.showWebsite && fields.website) {
    websiteItems.push({
      url: fields.website,
      label: fields.websiteLabel || fields.website.replace(/^https?:\/\//i, '').replace(/\/$/, '')
    });
  }
  if (Array.isArray(fields.websites)) {
    fields.websites.forEach(w => {
      if (w?.url && w.url.trim()) {
        websiteItems.push({
          url: w.url.trim(),
          label: w.label ? w.label.trim() : w.url.replace(/^https?:\/\//i, '').replace(/\/$/, '')
        });
      }
    });
  }

  const websitesHtml = websiteItems.length > 0 ? (
    `<div style="font-size:${size - 1}px;margin-top:2px;">` +
    `🌐 ` +
    websiteItems.map(site => (
      `<a href="${safeUrl(site.url)}" target="_blank" rel="noopener noreferrer" style="color:${color};text-decoration:none;font-weight:600;">${esc(site.label)}</a>`
    )).join(` <span style="color:#cbd5e1;margin:0 4px;">•</span> `) +
    `</div>`
  ) : '';

  // 3. Clean telephone link
  const cleanPhone = String(fields.phone || '').replace(/[^0-9+]/g, '');
  const phoneHtml = (fields.showPhone && fields.phone) ? (
    `<div style="font-size:${size - 1}px;margin-top:2px;">` +
    `📞 <a href="tel:${cleanPhone}" style="color:${textColor};text-decoration:none;">${esc(fields.phone)}</a>` +
    `</div>`
  ) : '';

  // 4. Clean mailto link
  const emailHtml = (fields.showEmail && fields.email) ? (
    `<div style="font-size:${size - 1}px;margin-top:2px;">` +
    `✉ <a href="mailto:${esc(fields.email)}" style="color:${color};text-decoration:none;font-weight:500;">${esc(fields.email)}</a>` +
    `</div>`
  ) : '';

  // 5. Call To Action (CTA) Button
  const ctaHtml = (fields.showCta && fields.ctaText && fields.ctaUrl) ? `
    <table cellpadding="0" cellspacing="0" border="0" style="margin-top:10px;margin-bottom:2px;">
      <tr>
        <td align="center" style="background-color:${color};border-radius:6px;padding:6px 14px;mso-padding-alt:0;">
          <a href="${safeUrl(fields.ctaUrl)}" target="_blank" rel="noopener noreferrer" style="color:#ffffff;font-size:${size}px;font-weight:700;text-decoration:none;display:inline-block;font-family:${font};">
            ${esc(fields.ctaText)} &rarr;
          </a>
        </td>
      </tr>
    </table>
  `.trim() : '';

  // Contact details block
  const contactRows = [
    fields.name && `<div style="font-size:${size + 3}px;font-weight:700;color:${color};margin-bottom:2px;letter-spacing:-0.2px;">${esc(fields.name)}</div>`,
    fields.designation && `<div style="color:#64748b;font-size:${size}px;margin-bottom:2px;">${esc(fields.designation)}</div>`,
    fields.company && `<div style="font-weight:700;color:#0f172a;font-size:${size}px;margin-bottom:4px;">${esc(fields.company)}</div>`,
    phoneHtml,
    emailHtml,
    websitesHtml,
    ctaHtml,
    socialsHtml,
  ].filter(Boolean).join('\n');

  // 6. Multiple Logos & Headshots
  // Collect primary logo and secondary headshot/badge
  const renderedLogos = [];

  // Primary Company Logo
  if (fields.showLogo && fields.logo) {
    const w = Number(fields.logoWidth) || 100;
    const r = Number(fields.logoRadius) || 0;
    const imgTag = `<img src="${safeUrl(fields.logo)}" alt="${esc(fields.company || 'Company Logo')}" width="${w}" style="max-width:${w}px;width:${w}px;height:auto;display:block;border:0;border-radius:${r}px;" />`;
    const wrapped = fields.logoLink ? `<a href="${safeUrl(fields.logoLink)}" target="_blank" rel="noopener noreferrer" style="display:block;text-decoration:none;">${imgTag}</a>` : imgTag;
    renderedLogos.push(wrapped);
  }

  // Secondary Headshot / Badge / Logo
  if (fields.showSecondaryLogo && fields.secondaryLogo) {
    const sw = Number(fields.secondaryLogoWidth) || 70;
    const sr = Number(fields.secondaryLogoRadius) || (fields.secondaryLogoType === 'headshot' ? 50 : 6);
    const imgTag = `<img src="${safeUrl(fields.secondaryLogo)}" alt="Badge or Headshot" width="${sw}" style="max-width:${sw}px;width:${sw}px;height:auto;display:block;border:0;border-radius:${sr}px;" />`;
    const wrapped = fields.secondaryLogoLink ? `<a href="${safeUrl(fields.secondaryLogoLink)}" target="_blank" rel="noopener noreferrer" style="display:block;text-decoration:none;">${imgTag}</a>` : imgTag;
    renderedLogos.push(wrapped);
  }

  // Extra logos from array if added
  if (Array.isArray(fields.extraLogos)) {
    fields.extraLogos.forEach((el, idx) => {
      if (el?.url) {
        const ew = Number(el.width) || 70;
        const er = Number(el.radius) || 0;
        const imgTag = `<img src="${safeUrl(el.url)}" alt="${esc(el.alt || `Logo ${idx + 2}`)}" width="${ew}" style="max-width:${ew}px;width:${ew}px;height:auto;display:block;border:0;border-radius:${er}px;" />`;
        const wrapped = el.link ? `<a href="${safeUrl(el.link)}" target="_blank" rel="noopener noreferrer" style="display:block;text-decoration:none;">${imgTag}</a>` : imgTag;
        renderedLogos.push(wrapped);
      }
    });
  }

  const logosHtml = renderedLogos.length > 0 ? (
    `<div style="display:flex;flex-direction:column;gap:10px;align-items:${align === 'center' ? 'center' : 'flex-start'};">` +
    renderedLogos.join('\n') +
    `</div>`
  ) : '';

  // 7. Border Style & Proportion (Total border, top line, left accent, none)
  const borderMode = fields.borderStyle || (fields.showBorder ? 'total-border' : 'none');
  let containerStyle = `max-width:600px;width:100%;font-family:${font};font-size:${size}px;color:${textColor};line-height:1.45;box-sizing:border-box;`;

  if (borderMode === 'total-border') {
    containerStyle += `border:1px solid #e2e8f0;border-radius:10px;padding:14px 18px;background-color:#ffffff;box-shadow:0 1px 3px rgba(0,0,0,0.04);`;
  } else if (borderMode === 'top-line') {
    containerStyle += `border-top:2px solid ${color};padding-top:10px;margin-top:10px;`;
  } else if (borderMode === 'left-accent') {
    containerStyle += `border-left:3px solid ${color};padding-left:14px;`;
  } else {
    containerStyle += `padding:4px 0;`;
  }

  if (layout === 'stacked' || renderedLogos.length === 0) {
    return `
      <table cellpadding="0" cellspacing="0" border="0" align="${align}" style="${containerStyle}">
        ${logosHtml ? `<tr><td align="${align}" style="padding-bottom:10px;">${logosHtml}</td></tr>` : ''}
        <tr>
          <td align="${align}" style="text-align:${align};">
            ${contactRows || '&nbsp;'}
          </td>
        </tr>
      </table>
    `.trim();
  }

  // Side-by-side layout: Logo(s) on left, Contact on right with neat separator
  return `
    <table cellpadding="0" cellspacing="0" border="0" align="${align}" style="${containerStyle}">
      <tr>
        <td valign="top" style="padding-right:16px;vertical-align:top;">
          ${logosHtml}
        </td>
        <td valign="top" style="vertical-align:top;border-left:1px solid #e2e8f0;padding-left:16px;">
          ${contactRows || '&nbsp;'}
        </td>
      </tr>
    </table>
  `.trim();
};

export const DEFAULT_SIGNATURE_FIELDS = {
  signatureName: '',
  name: '{{sender_name}}',
  designation: 'Managing Partner',
  company: 'Market Intel DB',
  phone: '+971 4 123 4567',
  email: '{{sender_email}}',
  website: 'https://example.com',
  websiteLabel: '',
  websites: [], // [{ id, url, label }]
  showPhone: true,
  showEmail: true,
  showWebsite: true,

  // Primary Company Logo
  showLogo: false,
  logo: '',
  logoWidth: 120, // 200-320px for horizontal, 60-100px for square
  logoRadius: 0,
  logoLink: '',

  // Secondary Image / Headshot / Badge
  showSecondaryLogo: false,
  secondaryLogo: '',
  secondaryLogoType: 'headshot', // 'headshot' | 'badge' | 'logo'
  secondaryLogoWidth: 70,
  secondaryLogoRadius: 50,
  secondaryLogoLink: '',
  extraLogos: [],

  // Social Links
  showLinkedin: true,
  linkedin: 'https://linkedin.com/company/example',
  showTwitter: false,
  twitter: '',
  showFacebook: false,
  facebook: '',
  showInstagram: false,
  instagram: '',
  showYoutube: false,
  youtube: '',
  showWhatsapp: false,
  whatsapp: '',
  showGithub: false,
  github: '',
  socialIconSize: 24, // 20 - 28 px

  // Call to Action (CTA) Button
  showCta: false,
  ctaText: 'Schedule a Meeting',
  ctaUrl: 'https://example.com/meeting',

  // Appearance & Proportion Rules
  accentColor: '#1e3a8a',
  textColor: '#334155',
  font: 'Arial, Helvetica, sans-serif',
  size: 13,
  align: 'left',
  layout: 'side-by-side',
  borderStyle: 'total-border', // 'total-border' | 'top-line' | 'left-accent' | 'none'
  showBorder: true,
  is_default: false,
};

const SignatureBuilderModal = ({
  initialId = null,
  initialData = null,
  onClose,
  onSaved,
}) => {
  const [fields, setFields] = useState(DEFAULT_SIGNATURE_FIELDS);
  const [loading, setLoading] = useState(!!initialId && !initialData);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState('basic'); // 'basic' | 'media' | 'appearance'
  const [previewSample, setPreviewSample] = useState(true);

  useEffect(() => {
    if (initialData) {
      const proj = initialData.project_data || {};
      setFields((prev) => ({
        ...prev,
        signatureName: initialData.name || '',
        is_default: !!initialData.is_default,
        ...(proj.fields || {}),
      }));
      setLoading(false);
    } else if (initialId) {
      designApi.get('signature', initialId)
        .then((data) => {
          const proj = data.project_data || {};
          setFields((prev) => ({
            ...prev,
            signatureName: data.name || '',
            is_default: !!data.is_default,
            ...(proj.fields || {}),
          }));
        })
        .catch((err) => toast.error(errorMessage(err)))
        .finally(() => setLoading(false));
    }
  }, [initialId, initialData]);

  const update = (k, v) => setFields((p) => ({ ...p, [k]: v }));

  const handleUploadImage = async (fieldKey, showKey, file) => {
    if (!file) return;
    try {
      const res = await designApi.uploadImage('signature', file);
      if (res.url) {
        update(fieldKey, res.url);
        if (showKey) update(showKey, true);
        toast.success('Image uploaded successfully!');
      }
    } catch (err) {
      toast.error('Failed to upload image.');
    }
  };

  // Additional websites helpers
  const addWebsiteRow = () => {
    const newSite = { id: `site-${Date.now()}`, url: '', label: '' };
    update('websites', [...(fields.websites || []), newSite]);
  };

  const updateWebsiteRow = (id, key, val) => {
    const list = (fields.websites || []).map(s => s.id === id ? { ...s, [key]: val } : s);
    update('websites', list);
  };

  const removeWebsiteRow = (id) => {
    update('websites', (fields.websites || []).filter(s => s.id !== id));
  };

  const handleSave = async (makeDefault = false) => {
    if (!fields.signatureName.trim()) {
      toast.error('Please enter a name for this signature.');
      setActiveTab('basic');
      return;
    }

    setSaving(true);
    const html = buildSignatureHtml(fields);
    const payload = {
      name: fields.signatureName.trim(),
      html,
      project_data: { version: 2, fields },
      is_default: makeDefault || fields.is_default,
    };

    try {
      let saved;
      if (initialId) {
        saved = await designApi.update('signature', initialId, payload);
      } else {
        saved = await designApi.create('signature', payload);
      }
      if (makeDefault) {
        await designApi.setDefault('signature', saved.id);
        saved.is_default = true;
      }
      toast.success('Signature saved successfully!');
      onSaved(saved);
      onClose();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const rawHtml = buildSignatureHtml(fields);
  const previewHtml = previewSample
    ? rawHtml.replace('{{sender_name}}', 'Alex Morgan').replace('{{sender_email}}', 'alex@company.com')
    : rawHtml;

  return (
    <div className="fixed inset-0 z-[120] bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl h-[92vh] flex flex-col overflow-hidden border border-slate-200">
        {/* Modal Top Bar */}
        <div className="flex items-center justify-between p-4 px-6 border-b border-slate-200 bg-linear-to-r from-slate-50 via-white to-indigo-50/40">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-indigo-100 text-indigo-700 rounded-xl shadow-xs">
              <PenTool className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-black text-slate-800">
                {initialId ? 'Edit Professional Signature' : 'Create Professional Signature'}
              </h2>
              <p className="text-xs text-slate-500">
                Standard signature template with total border, multiple logos, websites, CTA &amp; hyperlinked social icons.
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-200/50 transition cursor-pointer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-slate-200 overflow-hidden">
          {/* Left: Configuration Steps */}
          <div className="flex flex-col h-full overflow-hidden bg-white">
            {/* Steps Navigation Tabs */}
            <div className="flex border-b border-slate-200 bg-slate-50/50 text-xs font-bold">
              {[
                { id: 'basic', label: '1. Basic Info & Links' },
                { id: 'media', label: '2. Logos & Social Icons' },
                { id: 'appearance', label: '3. Proportions & Border' },
              ].map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setActiveTab(t.id)}
                  className={`flex-1 py-3 text-center border-b-2 transition cursor-pointer ${
                    activeTab === t.id
                      ? 'border-indigo-600 text-indigo-600 bg-white shadow-2xs'
                      : 'border-transparent text-slate-500 hover:text-slate-800'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {/* Scrollable Form Content */}
            <div className="flex-1 overflow-y-auto p-5 space-y-4 text-xs">
              {/* STEP 1: BASIC INFO & LINKS */}
              {activeTab === 'basic' && (
                <div className="space-y-3.5">
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">
                      Signature Template Name *
                    </label>
                    <input
                      type="text"
                      value={fields.signatureName}
                      onChange={(e) => update('signatureName', e.target.value)}
                      placeholder="e.g. Executive Corporate Signature"
                      className="w-full p-2.5 border border-slate-200 rounded-xl bg-white text-xs font-semibold focus:ring-2 focus:ring-indigo-100"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block font-semibold text-slate-600 mb-1">Full Name</label>
                      <input
                        type="text"
                        value={fields.name}
                        onChange={(e) => update('name', e.target.value)}
                        placeholder="{{sender_name}} or Jane Doe"
                        className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
                      />
                    </div>
                    <div>
                      <label className="block font-semibold text-slate-600 mb-1">Designation</label>
                      <input
                        type="text"
                        value={fields.designation}
                        onChange={(e) => update('designation', e.target.value)}
                        placeholder="e.g. Managing Partner"
                        className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block font-semibold text-slate-600 mb-1">Company Name</label>
                    <input
                      type="text"
                      value={fields.company}
                      onChange={(e) => update('company', e.target.value)}
                      placeholder="e.g. Plus UAE Consulting"
                      className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
                    />
                  </div>

                  {/* Phone with tel: hyperlink */}
                  <div className="space-y-1.5 pt-2 border-t border-slate-100">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-slate-700 flex items-center gap-1.5">
                        <Phone className="w-3.5 h-3.5 text-indigo-600" /> Phone Number (tel: hyperlink)
                      </span>
                      <label className="flex items-center gap-1.5 text-[11px] text-slate-500 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={fields.showPhone}
                          onChange={(e) => update('showPhone', e.target.checked)}
                          className="rounded accent-indigo-600"
                        />
                        <span>Enable</span>
                      </label>
                    </div>
                    {fields.showPhone && (
                      <input
                        type="text"
                        value={fields.phone}
                        onChange={(e) => update('phone', e.target.value)}
                        placeholder="+971 4 123 4567"
                        className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
                      />
                    )}
                  </div>

                  {/* Email with mailto: hyperlink */}
                  <div className="space-y-1.5 pt-2 border-t border-slate-100">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-slate-700 flex items-center gap-1.5">
                        <Mail className="w-3.5 h-3.5 text-indigo-600" /> Email Address (mailto: hyperlink)
                      </span>
                      <label className="flex items-center gap-1.5 text-[11px] text-slate-500 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={fields.showEmail}
                          onChange={(e) => update('showEmail', e.target.checked)}
                          className="rounded accent-indigo-600"
                        />
                        <span>Enable</span>
                      </label>
                    </div>
                    {fields.showEmail && (
                      <input
                        type="text"
                        value={fields.email}
                        onChange={(e) => update('email', e.target.value)}
                        placeholder="{{sender_email}} or you@company.com"
                        className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
                      />
                    )}
                  </div>

                  {/* Websites (Supports 2 or more websites) */}
                  <div className="space-y-2 pt-2 border-t border-slate-100">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-slate-700 flex items-center gap-1.5">
                        <Globe className="w-3.5 h-3.5 text-indigo-600" /> Website URLs (Clickable Hyperlinks)
                      </span>
                      <label className="flex items-center gap-1.5 text-[11px] text-slate-500 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={fields.showWebsite}
                          onChange={(e) => update('showWebsite', e.target.checked)}
                          className="rounded accent-indigo-600"
                        />
                        <span>Enable</span>
                      </label>
                    </div>

                    {fields.showWebsite && (
                      <div className="space-y-2">
                        {/* Primary Website */}
                        <div className="grid grid-cols-2 gap-2">
                          <input
                            type="text"
                            value={fields.website}
                            onChange={(e) => update('website', e.target.value)}
                            placeholder="https://example.com"
                            className="p-2 border border-slate-200 rounded-xl bg-white text-xs"
                          />
                          <input
                            type="text"
                            value={fields.websiteLabel}
                            onChange={(e) => update('websiteLabel', e.target.value)}
                            placeholder="Display Label (e.g. Website)"
                            className="p-2 border border-slate-200 rounded-xl bg-white text-xs"
                          />
                        </div>

                        {/* Additional Websites */}
                        {(fields.websites || []).map((site) => (
                          <div key={site.id} className="grid grid-cols-5 gap-2 items-center">
                            <input
                              type="text"
                              value={site.url}
                              onChange={(e) => updateWebsiteRow(site.id, 'url', e.target.value)}
                              placeholder="https://portal.example.com"
                              className="col-span-3 p-2 border border-slate-200 rounded-xl bg-white text-xs"
                            />
                            <input
                              type="text"
                              value={site.label}
                              onChange={(e) => updateWebsiteRow(site.id, 'label', e.target.value)}
                              placeholder="Label (e.g. Portal)"
                              className="col-span-1 p-2 border border-slate-200 rounded-xl bg-white text-xs"
                            />
                            <button
                              type="button"
                              onClick={() => removeWebsiteRow(site.id)}
                              className="col-span-1 p-2 text-slate-400 hover:text-rose-600 rounded-xl hover:bg-rose-50 transition cursor-pointer flex justify-center"
                              title="Remove website"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ))}

                        <button
                          type="button"
                          onClick={addWebsiteRow}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200/80 transition cursor-pointer"
                        >
                          <Plus className="w-3.5 h-3.5" />
                          <span>Add Another Website</span>
                        </button>
                      </div>
                    )}
                  </div>

                  {/* Call to Action Button */}
                  <div className="space-y-2 pt-2 border-t border-slate-100">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-slate-700 flex items-center gap-1.5">
                        <Sparkles className="w-3.5 h-3.5 text-indigo-600" /> Call to Action Button (Redirecting Button)
                      </span>
                      <label className="flex items-center gap-1.5 text-[11px] text-slate-500 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={fields.showCta}
                          onChange={(e) => update('showCta', e.target.checked)}
                          className="rounded accent-indigo-600"
                        />
                        <span>Enable CTA</span>
                      </label>
                    </div>

                    {fields.showCta && (
                      <div className="grid grid-cols-2 gap-2 p-3 bg-slate-50 rounded-xl border border-slate-200">
                        <div>
                          <label className="block text-[11px] text-slate-500 font-semibold mb-1">Button Text</label>
                          <input
                            type="text"
                            value={fields.ctaText}
                            onChange={(e) => update('ctaText', e.target.value)}
                            placeholder="e.g. Schedule a Meeting"
                            className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] text-slate-500 font-semibold mb-1">Redirect URL</label>
                          <input
                            type="text"
                            value={fields.ctaUrl}
                            onChange={(e) => update('ctaUrl', e.target.value)}
                            placeholder="https://calendly.com/... or website"
                            className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
                          />
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* STEP 2: LOGOS & SOCIAL ICONS */}
              {activeTab === 'media' && (
                <div className="space-y-4">
                  {/* Primary Company Logo Section */}
                  <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-800 flex items-center gap-1.5">
                        <ImageIcon className="w-4 h-4 text-indigo-600" /> Primary Company Logo
                      </span>
                      <label className="flex items-center gap-1.5 text-[11px] text-slate-600 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={fields.showLogo}
                          onChange={(e) => update('showLogo', e.target.checked)}
                          className="rounded accent-indigo-600"
                        />
                        <span>Include Logo</span>
                      </label>
                    </div>

                    {fields.showLogo && (
                      <div className="space-y-2 pt-2 border-t border-slate-200">
                        <div className="flex items-center gap-2">
                          <label className="px-3 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 rounded-lg font-bold cursor-pointer transition flex items-center gap-1.5">
                            <Upload className="w-3.5 h-3.5" />
                            <span>Upload Logo</span>
                            <input
                              type="file"
                              accept="image/*"
                              onChange={(e) => handleUploadImage('logo', 'showLogo', e.target.files?.[0])}
                              className="hidden"
                            />
                          </label>
                          <span className="text-[11px] text-slate-400">or paste image URL below</span>
                        </div>

                        <input
                          type="text"
                          value={fields.logo}
                          onChange={(e) => update('logo', e.target.value)}
                          placeholder="https://example.com/logo.png"
                          className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
                        />

                        <input
                          type="text"
                          value={fields.logoLink}
                          onChange={(e) => update('logoLink', e.target.value)}
                          placeholder="Logo Click URL (e.g. https://yourcompany.com)"
                          className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
                        />

                        <div className="flex items-center gap-4 pt-1">
                          <div className="flex-1">
                            <span className="text-[11px] text-slate-500 font-semibold block mb-1">
                              Width: {fields.logoWidth}px (Rule: 200–320px horizontal, 60–100px square)
                            </span>
                            <input
                              type="range"
                              min="40"
                              max="320"
                              step="5"
                              value={fields.logoWidth}
                              onChange={(e) => update('logoWidth', Number(e.target.value))}
                              className="w-full accent-indigo-600 cursor-pointer"
                            />
                          </div>
                          <div>
                            <span className="text-[11px] text-slate-500 font-semibold block mb-1">
                              Corner Radius
                            </span>
                            <select
                              value={fields.logoRadius}
                              onChange={(e) => update('logoRadius', Number(e.target.value))}
                              className="p-1.5 border border-slate-200 rounded-lg text-xs bg-white cursor-pointer"
                            >
                              <option value={0}>Square (0px)</option>
                              <option value={6}>Rounded (6px)</option>
                              <option value={40}>Circle</option>
                            </select>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Secondary Image: Headshot or Certification Badge */}
                  <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-800 flex items-center gap-1.5">
                        <UserCheck className="w-4 h-4 text-emerald-600" /> Secondary Image (Headshot / Cert Badge)
                      </span>
                      <label className="flex items-center gap-1.5 text-[11px] text-slate-600 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={fields.showSecondaryLogo}
                          onChange={(e) => update('showSecondaryLogo', e.target.checked)}
                          className="rounded accent-indigo-600"
                        />
                        <span>Include Secondary</span>
                      </label>
                    </div>

                    {fields.showSecondaryLogo && (
                      <div className="space-y-2 pt-2 border-t border-slate-200">
                        <div className="flex items-center gap-3">
                          <select
                            value={fields.secondaryLogoType}
                            onChange={(e) => update('secondaryLogoType', e.target.value)}
                            className="p-1.5 border border-slate-200 rounded-lg text-xs bg-white cursor-pointer"
                          >
                            <option value="headshot">Profile Headshot (Photo)</option>
                            <option value="badge">Certification / ISO Badge</option>
                            <option value="logo">Partner / Secondary Logo</option>
                          </select>

                          <label className="px-3 py-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 border border-emerald-200 rounded-lg font-bold cursor-pointer transition flex items-center gap-1.5">
                            <Upload className="w-3.5 h-3.5" />
                            <span>Upload Image</span>
                            <input
                              type="file"
                              accept="image/*"
                              onChange={(e) => handleUploadImage('secondaryLogo', 'showSecondaryLogo', e.target.files?.[0])}
                              className="hidden"
                            />
                          </label>
                        </div>

                        <input
                          type="text"
                          value={fields.secondaryLogo}
                          onChange={(e) => update('secondaryLogo', e.target.value)}
                          placeholder="https://example.com/headshot.jpg"
                          className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
                        />

                        <input
                          type="text"
                          value={fields.secondaryLogoLink}
                          onChange={(e) => update('secondaryLogoLink', e.target.value)}
                          placeholder="Redirect Link URL (optional)"
                          className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
                        />

                        <div className="flex items-center gap-4 pt-1">
                          <div className="flex-1">
                            <span className="text-[11px] text-slate-500 font-semibold block mb-1">
                              Width: {fields.secondaryLogoWidth}px (Rule: 60–100px square/headshot)
                            </span>
                            <input
                              type="range"
                              min="40"
                              max="120"
                              step="5"
                              value={fields.secondaryLogoWidth}
                              onChange={(e) => update('secondaryLogoWidth', Number(e.target.value))}
                              className="w-full accent-indigo-600 cursor-pointer"
                            />
                          </div>
                          <div>
                            <span className="text-[11px] text-slate-500 font-semibold block mb-1">
                              Shape
                            </span>
                            <select
                              value={fields.secondaryLogoRadius}
                              onChange={(e) => update('secondaryLogoRadius', Number(e.target.value))}
                              className="p-1.5 border border-slate-200 rounded-lg text-xs bg-white cursor-pointer"
                            >
                              <option value={50}>Circle (50%)</option>
                              <option value={8}>Rounded (8px)</option>
                              <option value={0}>Square (0px)</option>
                            </select>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Social Links (With Logo Only, No URL, Pure Hyperlink Format) */}
                  <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="font-bold text-slate-800 block">
                          Social Media Links (Icon Logos Only &bull; Hyperlinked)
                        </span>
                        <span className="text-[11px] text-slate-500">
                          Renders crisp 24px icon logos with no raw text or URL displayed.
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="text-[11px] text-slate-500 font-semibold">Size:</span>
                        <select
                          value={fields.socialIconSize || 24}
                          onChange={(e) => update('socialIconSize', Number(e.target.value))}
                          className="p-1 border border-slate-200 rounded text-xs bg-white cursor-pointer"
                        >
                          <option value={20}>20 px</option>
                          <option value={24}>24 px (Default)</option>
                          <option value={28}>28 px</option>
                        </select>
                      </div>
                    </div>

                    <div className="space-y-2.5 pt-2 border-t border-slate-200">
                      {SOCIAL_PLATFORMS.map((p) => {
                        const showKey = `show_${p.id}`;
                        const isChecked = fields[showKey] ?? fields[`show${p.id.charAt(0).toUpperCase() + p.id.slice(1)}`];
                        const val = fields[p.id] || fields[`${p.id}_url`] || '';

                        return (
                          <div key={p.id} className="space-y-1">
                            <div className="flex items-center justify-between">
                              <span className="text-slate-700 font-semibold flex items-center gap-2">
                                <img src={p.icon} alt={p.name} className="w-4 h-4 object-contain" />
                                <span>{p.name}</span>
                              </span>
                              <input
                                type="checkbox"
                                checked={!!isChecked}
                                onChange={(e) => {
                                  update(showKey, e.target.checked);
                                  update(`show${p.id.charAt(0).toUpperCase() + p.id.slice(1)}`, e.target.checked);
                                }}
                                className="rounded accent-indigo-600 cursor-pointer"
                              />
                            </div>
                            {isChecked && (
                              <input
                                type="text"
                                value={val}
                                onChange={(e) => update(p.id, e.target.value)}
                                placeholder={p.placeholder}
                                className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
                              />
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}

              {/* STEP 3: PROPORTIONS & BORDER */}
              {activeTab === 'appearance' && (
                <div className="space-y-4">
                  {/* Border Style Choice (Total Border rule) */}
                  <div>
                    <label className="block font-bold text-slate-700 mb-1.5">Signature Border Style</label>
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={() => {
                          update('borderStyle', 'total-border');
                          update('showBorder', true);
                        }}
                        className={`p-3 rounded-xl border text-left transition cursor-pointer ${
                          fields.borderStyle === 'total-border' || (!fields.borderStyle && fields.showBorder)
                            ? 'border-indigo-600 bg-indigo-50/50 text-indigo-900 ring-2 ring-indigo-500/20'
                            : 'border-slate-200 hover:bg-slate-50'
                        }`}
                      >
                        <span className="font-bold block text-xs">Total Border (Full Box)</span>
                        <span className="text-[10px] text-slate-500">Neat bounding card border with rounded corners</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          update('borderStyle', 'top-line');
                          update('showBorder', true);
                        }}
                        className={`p-3 rounded-xl border text-left transition cursor-pointer ${
                          fields.borderStyle === 'top-line'
                            ? 'border-indigo-600 bg-indigo-50/50 text-indigo-900 ring-2 ring-indigo-500/20'
                            : 'border-slate-200 hover:bg-slate-50'
                        }`}
                      >
                        <span className="font-bold block text-xs">Top Divider Line</span>
                        <span className="text-[10px] text-slate-500">Accent separator line above signature</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          update('borderStyle', 'left-accent');
                          update('showBorder', true);
                        }}
                        className={`p-3 rounded-xl border text-left transition cursor-pointer ${
                          fields.borderStyle === 'left-accent'
                            ? 'border-indigo-600 bg-indigo-50/50 text-indigo-900 ring-2 ring-indigo-500/20'
                            : 'border-slate-200 hover:bg-slate-50'
                        }`}
                      >
                        <span className="font-bold block text-xs">Left Accent Bar</span>
                        <span className="text-[10px] text-slate-500">Vertical colored brand strip</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => {
                          update('borderStyle', 'none');
                          update('showBorder', false);
                        }}
                        className={`p-3 rounded-xl border text-left transition cursor-pointer ${
                          fields.borderStyle === 'none'
                            ? 'border-indigo-600 bg-indigo-50/50 text-indigo-900 ring-2 ring-indigo-500/20'
                            : 'border-slate-200 hover:bg-slate-50'
                        }`}
                      >
                        <span className="font-bold block text-xs">No Border</span>
                        <span className="text-[10px] text-slate-500">Clean borderless layout</span>
                      </button>
                    </div>
                  </div>

                  {/* Layout Style Choice */}
                  <div>
                    <label className="block font-bold text-slate-700 mb-1.5">Layout Style</label>
                    <div className="grid grid-cols-2 gap-2">
                      <button
                        type="button"
                        onClick={() => update('layout', 'side-by-side')}
                        className={`p-3 rounded-xl border text-left transition cursor-pointer ${
                          fields.layout === 'side-by-side'
                            ? 'border-indigo-600 bg-indigo-50/50 text-indigo-900'
                            : 'border-slate-200 hover:bg-slate-50'
                        }`}
                      >
                        <span className="font-bold block text-xs">Side-by-Side</span>
                        <span className="text-[10px] text-slate-500">Logos on left, details on right</span>
                      </button>

                      <button
                        type="button"
                        onClick={() => update('layout', 'stacked')}
                        className={`p-3 rounded-xl border text-left transition cursor-pointer ${
                          fields.layout === 'stacked'
                            ? 'border-indigo-600 bg-indigo-50/50 text-indigo-900'
                            : 'border-slate-200 hover:bg-slate-50'
                        }`}
                      >
                        <span className="font-bold block text-xs">Stacked</span>
                        <span className="text-[10px] text-slate-500">Top-to-bottom layout</span>
                      </button>
                    </div>
                  </div>

                  {/* Colors */}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block font-semibold text-slate-600 mb-1">Brand Accent Color</label>
                      <div className="flex items-center gap-2">
                        <input
                          type="color"
                          value={fields.accentColor}
                          onChange={(e) => update('accentColor', e.target.value)}
                          className="w-8 h-8 rounded-lg cursor-pointer border border-slate-200"
                        />
                        <span className="text-[11px] text-slate-500 font-mono">{fields.accentColor}</span>
                      </div>
                    </div>

                    <div>
                      <label className="block font-semibold text-slate-600 mb-1">Text Color</label>
                      <div className="flex items-center gap-2">
                        <input
                          type="color"
                          value={fields.textColor}
                          onChange={(e) => update('textColor', e.target.value)}
                          className="w-8 h-8 rounded-lg cursor-pointer border border-slate-200"
                        />
                        <span className="text-[11px] text-slate-500 font-mono">{fields.textColor}</span>
                      </div>
                    </div>
                  </div>

                  {/* Typography & Alignment */}
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block font-semibold text-slate-600 mb-1">Font Family</label>
                      <select
                        value={fields.font}
                        onChange={(e) => update('font', e.target.value)}
                        className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs cursor-pointer"
                      >
                        <option value="Arial, Helvetica, sans-serif">Arial</option>
                        <option value="Georgia, serif">Georgia</option>
                        <option value="Verdana, Geneva, sans-serif">Verdana</option>
                        <option value="'Times New Roman', Times, serif">Times New Roman</option>
                      </select>
                    </div>

                    <div>
                      <label className="block font-semibold text-slate-600 mb-1">Alignment</label>
                      <select
                        value={fields.align}
                        onChange={(e) => update('align', e.target.value)}
                        className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs cursor-pointer"
                      >
                        <option value="left">Left</option>
                        <option value="center">Center</option>
                        <option value="right">Right</option>
                      </select>
                    </div>
                  </div>

                  {/* Sizing & Proportion Rules Reference Card */}
                  <div className="p-3.5 bg-slate-50 border border-slate-200/80 rounded-xl space-y-1.5 text-[11px] text-slate-600">
                    <div className="font-bold text-slate-800 flex items-center gap-1.5">
                      <ShieldCheck className="w-3.5 h-3.5 text-indigo-600" />
                      <span>Signature Sizing Standards Enforced</span>
                    </div>
                    <ul className="list-disc list-inside space-y-0.5 text-slate-500 text-[10px]">
                      <li><strong>Max Width:</strong> Kept strictly under 600px (Desktop ~3:1 ratio, 150–200px height)</li>
                      <li><strong>Mobile View:</strong> Auto-scales to 320px with zero horizontal scrolling</li>
                      <li><strong>Horizontal Logos:</strong> 200–320px wide × 40–60px tall</li>
                      <li><strong>Square Logos &amp; Headshots:</strong> 60–100px</li>
                      <li><strong>Social Icons:</strong> 20–28px &bull; Icon-only &bull; Hyperlinked</li>
                    </ul>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Right: Live Preview Panel */}
          <div className="flex flex-col h-full bg-slate-100/70 p-5 overflow-hidden">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs font-black uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                <Eye className="w-4 h-4 text-indigo-600" />
                Live Email Preview
              </span>
              <button
                type="button"
                onClick={() => setPreviewSample(!previewSample)}
                className="text-[11px] font-bold text-indigo-600 hover:text-indigo-800 cursor-pointer"
              >
                {previewSample ? 'Show Smart Tags' : 'Fill Sample Data'}
              </button>
            </div>

            {/* Email Container Simulation */}
            <div className="flex-1 bg-white rounded-2xl border border-slate-200 shadow-sm p-6 overflow-auto flex flex-col justify-between">
              {/* Dummy email body so the user sees the signature in context */}
              <div className="text-slate-400 text-xs space-y-2 select-none border-b border-dashed border-slate-200 pb-4 mb-4">
                <p className="font-semibold text-slate-600">Hi Jane Doe,</p>
                <p>Thank you for taking the time to speak with our team. Please let me know if you have any questions.</p>
                <p>Best regards,</p>
              </div>

              {/* Rendered Signature Output */}
              <div
                className="mt-2"
                dangerouslySetInnerHTML={{ __html: previewHtml }}
              />

              <div className="mt-8 text-[11px] text-slate-400 text-center">
                This signature will render cleanly across all major email clients including Outlook, Apple Mail &amp; Gmail.
              </div>
            </div>
          </div>
        </div>

        {/* Modal Bottom Bar / Actions */}
        <div className="flex items-center justify-between p-4 px-6 border-t border-slate-200 bg-white">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded-xl transition cursor-pointer"
          >
            Cancel
          </button>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={saving}
              onClick={() => handleSave(true)}
              className="px-4 py-2 text-xs font-bold border border-amber-300 bg-amber-50 hover:bg-amber-100 text-amber-800 rounded-xl transition flex items-center gap-1.5 cursor-pointer shadow-2xs"
            >
              <Star className="w-3.5 h-3.5 text-amber-600" />
              <span>Save &amp; Set as Default</span>
            </button>

            <button
              type="button"
              disabled={saving}
              onClick={() => handleSave(false)}
              className="px-5 py-2 text-xs font-bold bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-xl shadow-xs transition flex items-center gap-1.5 cursor-pointer"
            >
              <Save className="w-3.5 h-3.5" />
              <span>{saving ? 'Saving...' : 'Save Signature'}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default SignatureBuilderModal;
