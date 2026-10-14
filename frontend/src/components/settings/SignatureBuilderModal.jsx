import React, { useState, useEffect } from 'react';
import {
  PenTool, Upload, X, Check, Save, Star, Eye,
  Globe, Phone, Mail,
} from 'lucide-react';
import { toast } from 'react-toastify';
import { designApi, errorMessage } from '../../services/designApi';

const LinkedInIcon = ({ className = 'w-3.5 h-3.5' }) => (
  <svg className={className} viewBox="0 0 24 24" fill="currentColor">
    <path d="M19 3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14m-.5 15.5v-5.3a3.26 3.26 0 0 0-3.26-3.26c-.85 0-1.84.52-2.28 1.3v-1.11h-2.79v8.37h2.79v-4.93c0-.77.62-1.4 1.39-1.4a1.4 1.4 0 0 1 1.4 1.4v4.93h2.75M6.88 8.56a1.68 1.68 0 0 0 1.68-1.68c0-.93-.75-1.69-1.68-1.69a1.69 1.69 0 0 0-1.69 1.69c0 .93.76 1.68 1.69 1.68m1.39 9.94v-8.37H5.5v8.37h2.77z"/>
  </svg>
);

const TwitterIcon = ({ className = 'w-3.5 h-3.5' }) => (
  <svg className={className} viewBox="0 0 24 24" fill="currentColor">
    <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
  </svg>
);

const FacebookIcon = ({ className = 'w-3.5 h-3.5' }) => (
  <svg className={className} viewBox="0 0 24 24" fill="currentColor">
    <path d="M22 12c0-5.52-4.48-10-10-10S2 6.48 2 12c0 4.84 3.44 8.87 8 9.8V15H8v-3h2V9.5C10 7.57 11.57 6 13.5 6H16v3h-2c-.55 0-1 .45-1 1v2h3v3h-3v6.95c5.05-.5 9-4.76 9-9.95z"/>
  </svg>
);

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
 */
export const buildSignatureHtml = (fields) => {
  const color = esc(fields.accentColor || '#1e3a8a');
  const textColor = esc(fields.textColor || '#334155');
  const font = esc(fields.font || 'Arial, Helvetica, sans-serif');
  const align = ['left', 'center', 'right'].includes(fields.align) ? fields.align : 'left';
  const size = Number(fields.size) || 13;
  const layout = fields.layout || 'side-by-side'; // 'side-by-side' or 'stacked'

  const link = (u, label) => {
    const s = safeUrl(u);
    return s ? `<a href="${s}" target="_blank" rel="noopener noreferrer" style="color:${color};text-decoration:none;margin-right:10px;font-weight:600;font-size:${size - 1}px;">${label}</a>` : '';
  };

  const socials = [
    fields.showLinkedin && fields.linkedin && link(fields.linkedin, 'LinkedIn'),
    fields.showTwitter && fields.twitter && link(fields.twitter, 'X / Twitter'),
    fields.showFacebook && fields.facebook && link(fields.facebook, 'Facebook'),
  ].filter(Boolean).join(' ');

  const contactRows = [
    fields.name && `<div style="font-size:${size + 3}px;font-weight:700;color:${color};margin-bottom:2px;">${esc(fields.name)}</div>`,
    fields.designation && `<div style="color:#64748b;font-size:${size}px;margin-bottom:2px;">${esc(fields.designation)}</div>`,
    fields.company && `<div style="font-weight:700;color:#0f172a;font-size:${size}px;margin-bottom:4px;">${esc(fields.company)}</div>`,
    fields.showPhone && fields.phone && `<div style="font-size:${size - 1}px;margin-top:2px;">📞 <span style="color:${textColor};">${esc(fields.phone)}</span></div>`,
    fields.showEmail && fields.email && `<div style="font-size:${size - 1}px;margin-top:2px;">✉ <a href="mailto:${esc(fields.email)}" style="color:${color};text-decoration:none;">${esc(fields.email)}</a></div>`,
    fields.showWebsite && fields.website && `<div style="font-size:${size - 1}px;margin-top:2px;">🌐 <a href="${safeUrl(fields.website)}" target="_blank" rel="noopener noreferrer" style="color:${color};text-decoration:none;">${esc(fields.website)}</a></div>`,
    socials && `<div style="margin-top:8px;">${socials}</div>`,
  ].filter(Boolean).join('\n');

  const logoImg = (fields.showLogo && fields.logo) ? `
    <img src="${safeUrl(fields.logo)}" alt="${esc(fields.company || 'Logo')}" width="${Number(fields.logoWidth) || 80}" style="max-width:100%;height:auto;display:block;border:0;border-radius:${fields.logoRadius || 0}px;" />
  ` : '';

  const borderStyle = fields.showBorder ? `border-top:2px solid ${color};padding-top:10px;margin-top:12px;` : '';

  if (layout === 'stacked' || !logoImg) {
    return `
      <table cellpadding="0" cellspacing="0" border="0" align="${align}" style="font-family:${font};font-size:${size}px;color:${textColor};${borderStyle}line-height:1.5;">
        ${logoImg ? `<tr><td align="${align}" style="padding-bottom:8px;">${logoImg}</td></tr>` : ''}
        <tr>
          <td align="${align}" style="text-align:${align};">
            ${contactRows || '&nbsp;'}
          </td>
        </tr>
      </table>
    `.trim();
  }

  // Side-by-side layout: Logo on left, Contact on right
  return `
    <table cellpadding="0" cellspacing="0" border="0" align="${align}" style="font-family:${font};font-size:${size}px;color:${textColor};${borderStyle}line-height:1.5;">
      <tr>
        <td valign="top" style="padding-right:16px;vertical-align:top;">
          ${logoImg}
        </td>
        <td valign="top" style="vertical-align:top;border-left:1px solid #e2e8f0;padding-left:16px;">
          ${contactRows || '&nbsp;'}
        </td>
      </tr>
    </table>
  `.trim();
};

const DEFAULT_SIGNATURE_FIELDS = {
  signatureName: '',
  name: '{{sender_name}}',
  designation: 'Managing Partner',
  company: 'Market Intel DB',
  phone: '+971 4 123 4567',
  email: '{{sender_email}}',
  website: 'https://example.com',
  showPhone: true,
  showEmail: true,
  showWebsite: true,
  showLogo: false,
  logo: '',
  logoWidth: 80,
  logoRadius: 0,
  showLinkedin: true,
  linkedin: 'https://linkedin.com/company/example',
  showTwitter: false,
  twitter: '',
  showFacebook: false,
  facebook: '',
  accentColor: '#1e3a8a',
  textColor: '#334155',
  font: 'Arial, Helvetica, sans-serif',
  size: 13,
  align: 'left',
  layout: 'side-by-side',
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

  const handleUploadLogo = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const res = await designApi.uploadImage('signature', file);
      if (res.url) {
        update('logo', res.url);
        update('showLogo', true);
        toast.success('Logo uploaded!');
      }
    } catch (err) {
      toast.error('Failed to upload logo.');
    }
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
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl h-[90vh] flex flex-col overflow-hidden border border-slate-200">
        {/* Modal Top Bar */}
        <div className="flex items-center justify-between p-4 border-b border-slate-200 bg-slate-50">
          <div className="flex items-center gap-2">
            <div className="p-2 bg-indigo-100 text-indigo-700 rounded-xl">
              <PenTool className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-black text-slate-800">
                {initialId ? 'Edit Email Signature' : 'Create Professional Signature'}
              </h2>
              <p className="text-xs text-slate-500">
                Simple visual builder — fill fields and see live preview instantly.
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
                { id: 'basic', label: '1. Basic Info' },
                { id: 'media', label: '2. Logo & Social' },
                { id: 'appearance', label: '3. Appearance' },
              ].map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => setActiveTab(t.id)}
                  className={`flex-1 py-3 text-center border-b-2 transition cursor-pointer ${
                    activeTab === t.id
                      ? 'border-indigo-600 text-indigo-600 bg-white'
                      : 'border-transparent text-slate-500 hover:text-slate-800'
                  }`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {/* Scrollable Form Content */}
            <div className="flex-1 overflow-y-auto p-5 space-y-4 text-xs">
              {/* STEP 1: BASIC INFO */}
              {activeTab === 'basic' && (
                <div className="space-y-3">
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">
                      Signature Template Name *
                    </label>
                    <input
                      type="text"
                      value={fields.signatureName}
                      onChange={(e) => update('signatureName', e.target.value)}
                      placeholder="e.g. Default Corporate Signature"
                      className="w-full p-2.5 border border-slate-200 rounded-xl bg-white text-xs font-medium focus:ring-2 focus:ring-indigo-100"
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

                  <div className="space-y-2 pt-2 border-t border-slate-100">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-slate-700">Phone Number</span>
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

                  <div className="space-y-2 pt-2 border-t border-slate-100">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-slate-700">Email Address</span>
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

                  <div className="space-y-2 pt-2 border-t border-slate-100">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-slate-700">Website URL</span>
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
                      <input
                        type="text"
                        value={fields.website}
                        onChange={(e) => update('website', e.target.value)}
                        placeholder="https://example.com"
                        className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
                      />
                    )}
                  </div>
                </div>
              )}

              {/* STEP 2: LOGO & SOCIAL */}
              {activeTab === 'media' && (
                <div className="space-y-4">
                  {/* Company Logo Section */}
                  <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-slate-800">Company Logo</span>
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
                              onChange={handleUploadLogo}
                              className="hidden"
                            />
                          </label>
                          <span className="text-[11px] text-slate-400">or paste URL below</span>
                        </div>

                        <input
                          type="text"
                          value={fields.logo}
                          onChange={(e) => update('logo', e.target.value)}
                          placeholder="https://example.com/logo.png"
                          className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
                        />

                        <div className="flex items-center gap-4">
                          <div className="flex-1">
                            <span className="text-[11px] text-slate-500 font-semibold block mb-1">
                              Width: {fields.logoWidth}px
                            </span>
                            <input
                              type="range"
                              min="40"
                              max="160"
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
                              className="p-1.5 border border-slate-200 rounded-lg text-xs bg-white"
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

                  {/* Social Links */}
                  <div className="space-y-3">
                    <span className="font-bold text-slate-800 block">Social Links</span>

                    {/* LinkedIn */}
                    <div className="space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-slate-600 font-semibold flex items-center gap-1.5">
                          <LinkedInIcon className="w-3.5 h-3.5 text-blue-600" /> LinkedIn
                        </span>
                        <input
                          type="checkbox"
                          checked={fields.showLinkedin}
                          onChange={(e) => update('showLinkedin', e.target.checked)}
                          className="rounded accent-indigo-600 cursor-pointer"
                        />
                      </div>
                      {fields.showLinkedin && (
                        <input
                          type="text"
                          value={fields.linkedin}
                          onChange={(e) => update('linkedin', e.target.value)}
                          placeholder="https://linkedin.com/..."
                          className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
                        />
                      )}
                    </div>

                    {/* X / Twitter */}
                    <div className="space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-slate-600 font-semibold flex items-center gap-1.5">
                          <TwitterIcon className="w-3.5 h-3.5 text-slate-700" /> X (Twitter)
                        </span>
                        <input
                          type="checkbox"
                          checked={fields.showTwitter}
                          onChange={(e) => update('showTwitter', e.target.checked)}
                          className="rounded accent-indigo-600 cursor-pointer"
                        />
                      </div>
                      {fields.showTwitter && (
                        <input
                          type="text"
                          value={fields.twitter}
                          onChange={(e) => update('twitter', e.target.value)}
                          placeholder="https://x.com/..."
                          className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
                        />
                      )}
                    </div>

                    {/* Facebook */}
                    <div className="space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-slate-600 font-semibold flex items-center gap-1.5">
                          <FacebookIcon className="w-3.5 h-3.5 text-blue-700" /> Facebook
                        </span>
                        <input
                          type="checkbox"
                          checked={fields.showFacebook}
                          onChange={(e) => update('showFacebook', e.target.checked)}
                          className="rounded accent-indigo-600 cursor-pointer"
                        />
                      </div>
                      {fields.showFacebook && (
                        <input
                          type="text"
                          value={fields.facebook}
                          onChange={(e) => update('facebook', e.target.value)}
                          placeholder="https://facebook.com/..."
                          className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
                        />
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* STEP 3: APPEARANCE */}
              {activeTab === 'appearance' && (
                <div className="space-y-4">
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
                        <span className="text-[10px] text-slate-500">Logo on left, details on right</span>
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
                      <label className="block font-semibold text-slate-600 mb-1">Accent Color</label>
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
                        className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
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
                        className="w-full p-2 border border-slate-200 rounded-xl bg-white text-xs"
                      >
                        <option value="left">Left</option>
                        <option value="center">Center</option>
                        <option value="right">Right</option>
                      </select>
                    </div>
                  </div>

                  {/* Top Divider Line Toggle */}
                  <div className="flex items-center justify-between p-3 bg-slate-50 border border-slate-200 rounded-xl">
                    <span className="font-semibold text-slate-700">Top Divider Line</span>
                    <input
                      type="checkbox"
                      checked={fields.showBorder}
                      onChange={(e) => update('showBorder', e.target.checked)}
                      className="rounded accent-indigo-600 cursor-pointer"
                    />
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
                className="text-[11px] font-bold text-indigo-600 hover:text-indigo-800"
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
                This signature will render cleanly across all major email clients including Outlook & Gmail.
              </div>
            </div>
          </div>
        </div>

        {/* Modal Bottom Bar / Actions */}
        <div className="flex items-center justify-between p-4 border-t border-slate-200 bg-white">
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
              className="px-4 py-2 text-xs font-bold border border-amber-300 bg-amber-50 hover:bg-amber-100 text-amber-800 rounded-xl transition flex items-center gap-1.5 cursor-pointer"
            >
              <Star className="w-3.5 h-3.5 text-amber-600" />
              <span>Save & Set as Default</span>
            </button>

            <button
              type="button"
              disabled={saving}
              onClick={() => handleSave(false)}
              className="px-5 py-2 text-xs font-bold bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-xl shadow-sm transition flex items-center gap-1.5 cursor-pointer"
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
