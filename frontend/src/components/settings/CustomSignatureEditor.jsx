import React, { useState, useEffect } from 'react';
import {
  ArrowLeft,
  Save,
  Loader2,
  FileCode,
  PenTool,
  Eye,
  Globe,
  Phone,
  Mail,
  Check,
  Upload,
  Info,
  ExternalLink,
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

const cleanUrl = (u) => {
  if (!u) return '';
  const s = String(u).trim();
  if (/^https?:\/\//i.test(s) || /^mailto:/i.test(s) || /^tel:/i.test(s)) {
    return s;
  }
  return `https://${s}`;
};

const escapeHtml = (str) => {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
};

/**
 * Builds clean text and HTML according to user specification:
 * Mohan
 * Software Developer
 * Company Name
 *
 * Email: mohan@example.com
 * Phone: +91 98765 43210
 * Website: www.example.com
 *
 * Clickable website and social media profile links.
 */
export const buildStructuredSignature = (f) => {
  const name = f.name?.trim() || '';
  const designation = f.designation?.trim() || '';
  const company = f.company?.trim() || '';
  const email = f.email?.trim() || '';
  const phone = f.phone?.trim() || '';
  const website = f.website?.trim() || '';
  const linkedin = f.linkedin?.trim() || '';
  const twitter = f.twitter?.trim() || '';

  // Plain-text representation
  const textLines = [];
  if (name) textLines.push(name);
  if (designation) textLines.push(designation);
  if (company) textLines.push(company);

  const contactTextLines = [];
  if (email) contactTextLines.push(`Email: ${email}`);
  if (phone) contactTextLines.push(`Phone: ${phone}`);
  if (website) contactTextLines.push(`Website: ${website}`);
  if (linkedin) contactTextLines.push(`LinkedIn: ${cleanUrl(linkedin)}`);
  if (twitter) contactTextLines.push(`Twitter/X: ${cleanUrl(twitter)}`);

  if (contactTextLines.length > 0) {
    if (textLines.length > 0) textLines.push('');
    textLines.push(...contactTextLines);
  }

  const plainText = textLines.join('\n');

  // Professional Text-Based HTML with clickable links
  const htmlParts = [];
  if (name) {
    htmlParts.push(`<div style="font-size: 15px; font-weight: 700; color: #0f172a; margin-bottom: 2px;">${escapeHtml(name)}</div>`);
  }
  if (designation) {
    htmlParts.push(`<div style="font-size: 13px; color: #475569; margin-bottom: 2px;">${escapeHtml(designation)}</div>`);
  }
  if (company) {
    htmlParts.push(`<div style="font-size: 13px; font-weight: 600; color: #0f172a; margin-bottom: 10px;">${escapeHtml(company)}</div>`);
  }

  const contactHtmlParts = [];
  if (email) {
    contactHtmlParts.push(`<div>Email: <a href="mailto:${escapeHtml(email)}" style="color: #2563eb; text-decoration: none; font-weight: 500;">${escapeHtml(email)}</a></div>`);
  }
  if (phone) {
    const telHref = phone.replace(/[^\d+]/g, '');
    contactHtmlParts.push(`<div>Phone: <a href="tel:${escapeHtml(telHref)}" style="color: #1e293b; text-decoration: none;">${escapeHtml(phone)}</a></div>`);
  }
  if (website) {
    const webHref = cleanUrl(website);
    contactHtmlParts.push(`<div>Website: <a href="${escapeHtml(webHref)}" target="_blank" rel="noopener noreferrer" style="color: #2563eb; text-decoration: none; font-weight: 500;">${escapeHtml(website)}</a></div>`);
  }

  const socialLinks = [];
  if (linkedin) {
    socialLinks.push(`<a href="${escapeHtml(cleanUrl(linkedin))}" target="_blank" rel="noopener noreferrer" style="color: #0077b5; text-decoration: none; font-weight: 600; margin-right: 14px;">LinkedIn</a>`);
  }
  if (twitter) {
    socialLinks.push(`<a href="${escapeHtml(cleanUrl(twitter))}" target="_blank" rel="noopener noreferrer" style="color: #0f172a; text-decoration: none; font-weight: 600; margin-right: 14px;">X / Twitter</a>`);
  }

  if (socialLinks.length > 0) {
    contactHtmlParts.push(`<div style="margin-top: 8px;">${socialLinks.join('')}</div>`);
  }

  let fullHtml = `
<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 13px; color: #1e293b; line-height: 1.5; padding: 4px 0;">
  ${htmlParts.join('\n  ')}
  ${contactHtmlParts.length > 0 ? (htmlParts.length > 0 ? '<div style="height: 6px;"></div>' : '') + htmlParts.length > 0 ? contactHtmlParts.join('\n  ') : contactHtmlParts.join('\n  ') : ''}
</div>
  `.trim();

  return { plainText, fullHtml };
};

const CustomSignatureEditor = ({ id, onClose, onSaved }) => {
  const [signatureName, setSignatureName] = useState('');
  const [name, setName] = useState('');
  const [designation, setDesignation] = useState('');
  const [company, setCompany] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [website, setWebsite] = useState('');
  const [linkedin, setLinkedin] = useState('');
  const [twitter, setTwitter] = useState('');
  const [isDefault, setIsDefault] = useState(false);

  // HTML import state
  const [isHtmlMode, setIsHtmlMode] = useState(false);
  const [htmlCode, setHtmlCode] = useState('');

  const [loading, setLoading] = useState(!!id);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [isDirty, setIsDirty] = useState(false);

  useEffect(() => {
    let active = true;
    if (!id) {
      setSignatureName('Default Signature');
      setName('Mohan');
      setDesignation('Software Developer');
      setCompany('Company Name');
      setEmail('mohan@example.com');
      setPhone('+91 98765 43210');
      setWebsite('www.example.com');
      setLinkedin('https://linkedin.com/in/example');
      return;
    }

    (async () => {
      try {
        const data = await designApi.get('signature', id);
        if (!active) return;
        setSignatureName(data.name || '');
        setIsDefault(!!data.is_default);

        const pd = data.project_data || {};
        const fields = pd.fields || {};

        if (pd.is_html_import || (data.html && !pd.fields)) {
          setIsHtmlMode(true);
          setHtmlCode(data.html || '');
        } else {
          setName(fields.name || data.name || '');
          setDesignation(fields.designation || '');
          setCompany(fields.company || '');
          setEmail(fields.email || '');
          setPhone(fields.phone || '');
          setWebsite(fields.website || '');
          setLinkedin(fields.linkedin || '');
          setTwitter(fields.twitter || '');
        }
      } catch (err) {
        toast.error(errorMessage(err));
        onClose();
      } finally {
        if (active) setLoading(false);
      }
    })();

    return () => {
      active = false;
    };
  }, [id, onClose]);

  const handleFileUpload = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result;
      if (typeof content === 'string') {
        setIsHtmlMode(true);
        setHtmlCode(content);
        setIsDirty(true);
        toast.success(`HTML signature loaded from ${file.name}`);
      }
    };
    reader.onerror = () => {
      toast.error('Failed to read signature HTML file.');
    };
    reader.readAsText(file);
    e.target.value = '';
  };

  const handleSave = async () => {
    setError('');
    if (!signatureName.trim()) {
      setError('Signature name is required.');
      return;
    }

    setSaving(true);
    let payload;

    if (isHtmlMode) {
      if (!htmlCode.trim()) {
        setError('HTML signature code cannot be empty.');
        setSaving(false);
        return;
      }
      payload = {
        name: signatureName.trim(),
        html: htmlCode.trim(),
        text: htmlCode.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim(),
        project_data: {
          is_custom: true,
          is_html_import: true,
          version: 2,
        },
        is_default: isDefault,
      };
    } else {
      const { plainText, fullHtml } = buildStructuredSignature({
        name,
        designation,
        company,
        email,
        phone,
        website,
        linkedin,
        twitter,
      });

      payload = {
        name: signatureName.trim(),
        html: fullHtml,
        text: plainText,
        project_data: {
          is_custom: true,
          version: 2,
          fields: {
            name,
            designation,
            company,
            email,
            phone,
            website,
            linkedin,
            twitter,
          },
        },
        is_default: isDefault,
      };
    }

    try {
      const saved = id
        ? await designApi.update('signature', id, payload)
        : await designApi.create('signature', payload);

      if (isDefault) {
        await designApi.setDefault('signature', saved.id);
        saved.is_default = true;
      }

      toast.success('Signature template saved successfully!');
      setIsDirty(false);
      onSaved(saved);
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const guardedClose = () => {
    if (isDirty) {
      if (!window.confirm('You have unsaved changes. Discard and go back?')) {
        return;
      }
    }
    onClose();
  };

  if (loading) {
    return (
      <div className="p-16 flex items-center justify-center text-slate-400">
        <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
      </div>
    );
  }

  const { fullHtml } = buildStructuredSignature({
    name,
    designation,
    company,
    email,
    phone,
    website,
    linkedin,
    twitter,
  });

  return (
    <div className="space-y-4 max-w-7xl mx-auto">
      {/* Top Header Bar */}
      <div className="flex items-center justify-between bg-white border border-slate-200 px-4 py-3 rounded-2xl shadow-2xs">
        <button
          type="button"
          onClick={guardedClose}
          className="flex items-center gap-2 text-xs font-bold text-slate-600 hover:text-slate-900 transition cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Signatures</span>
        </button>

        <div className="flex items-center gap-2">
          {/* Mode Switcher: Structured Fields vs HTML Import */}
          <div className="flex items-center bg-slate-100 p-1 rounded-xl border border-slate-200 text-xs font-semibold">
            <button
              type="button"
              onClick={() => setIsHtmlMode(false)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition cursor-pointer ${
                !isHtmlMode
                  ? 'bg-white text-slate-900 shadow-xs font-bold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <PenTool className="w-3.5 h-3.5" />
              <span>Structured Text</span>
            </button>
            <button
              type="button"
              onClick={() => setIsHtmlMode(true)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition cursor-pointer ${
                isHtmlMode
                  ? 'bg-white text-blue-700 shadow-xs font-bold'
                  : 'text-slate-600 hover:text-slate-900'
              }`}
            >
              <FileCode className="w-3.5 h-3.5 text-blue-600" />
              <span>HTML Import</span>
            </button>
          </div>

          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 text-white text-xs font-bold rounded-xl transition cursor-pointer shadow-sm"
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            <span>{saving ? 'Saving...' : 'Save Signature'}</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-xs font-medium rounded-xl">
          {error}
        </div>
      )}

      {/* Main Grid: Editor on Left, Live Preview on Right */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Editor Form */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4 space-y-4 shadow-2xs">
          <div>
            <label className="block text-xs font-extrabold text-slate-800 uppercase tracking-wider mb-1">
              Signature Template Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={signatureName}
              onChange={(e) => {
                setSignatureName(e.target.value);
                setIsDirty(true);
              }}
              placeholder="e.g. Mohan Professional Signature"
              className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl font-medium text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition"
            />
          </div>

          {!isHtmlMode ? (
            /* Structured Text Fields */
            <div className="space-y-3.5">
              <div className="p-3 bg-blue-50/50 border border-blue-100 rounded-xl text-[11px] text-blue-800 flex items-start gap-2">
                <Info className="w-3.5 h-3.5 text-blue-600 shrink-0 mt-0.5" />
                <span>
                  Enter your details below. The signature is structured as clean, professional text with clickable website, email, phone, and social profile links.
                </span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Full Name <span className="text-slate-400 font-normal">(e.g. Mohan)</span>
                  </label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => {
                      setName(e.target.value);
                      setIsDirty(true);
                    }}
                    placeholder="Mohan"
                    className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl font-medium text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition"
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Job Title <span className="text-slate-400 font-normal">(e.g. Software Developer)</span>
                  </label>
                  <input
                    type="text"
                    value={designation}
                    onChange={(e) => {
                      setDesignation(e.target.value);
                      setIsDirty(true);
                    }}
                    placeholder="Software Developer"
                    className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl font-medium text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Company Name <span className="text-slate-400 font-normal">(e.g. Company Name)</span>
                </label>
                <input
                  type="text"
                  value={company}
                  onChange={(e) => {
                    setCompany(e.target.value);
                    setIsDirty(true);
                  }}
                  placeholder="Company Name"
                  className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl font-medium text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Email Address <span className="text-slate-400 font-normal">(e.g. mohan@example.com)</span>
                  </label>
                  <div className="relative flex items-center">
                    <Mail className="w-3.5 h-3.5 text-slate-400 absolute left-3 pointer-events-none" />
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => {
                        setEmail(e.target.value);
                        setIsDirty(true);
                      }}
                      placeholder="mohan@example.com"
                      className="w-full pl-9 pr-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl font-medium text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Phone Number <span className="text-slate-400 font-normal">(e.g. +91 98765 43210)</span>
                  </label>
                  <div className="relative flex items-center">
                    <Phone className="w-3.5 h-3.5 text-slate-400 absolute left-3 pointer-events-none" />
                    <input
                      type="text"
                      value={phone}
                      onChange={(e) => {
                        setPhone(e.target.value);
                        setIsDirty(true);
                      }}
                      placeholder="+91 98765 43210"
                      className="w-full pl-9 pr-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl font-medium text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition"
                    />
                  </div>
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Website URL <span className="text-slate-400 font-normal">(Clickable, e.g. www.example.com)</span>
                </label>
                <div className="relative flex items-center">
                  <Globe className="w-3.5 h-3.5 text-slate-400 absolute left-3 pointer-events-none" />
                  <input
                    type="text"
                    value={website}
                    onChange={(e) => {
                      setWebsite(e.target.value);
                      setIsDirty(true);
                    }}
                    placeholder="www.example.com"
                    className="w-full pl-9 pr-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl font-medium text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition"
                  />
                </div>
              </div>

              {/* Social Media Profile Links */}
              <div className="pt-2 border-t border-slate-100 space-y-3">
                <label className="block text-xs font-extrabold text-slate-800 uppercase tracking-wider">
                  Social Media Profile Links (Clickable)
                </label>

                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    LinkedIn Profile URL
                  </label>
                  <div className="relative flex items-center">
                    <div className="absolute left-3 text-sky-700 pointer-events-none">
                      <LinkedInIcon />
                    </div>
                    <input
                      type="text"
                      value={linkedin}
                      onChange={(e) => {
                        setLinkedin(e.target.value);
                        setIsDirty(true);
                      }}
                      placeholder="https://linkedin.com/in/mohan"
                      className="w-full pl-9 pr-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl font-medium text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Twitter / X Profile URL
                  </label>
                  <div className="relative flex items-center">
                    <div className="absolute left-3 text-slate-800 pointer-events-none">
                      <TwitterIcon />
                    </div>
                    <input
                      type="text"
                      value={twitter}
                      onChange={(e) => {
                        setTwitter(e.target.value);
                        setIsDirty(true);
                      }}
                      placeholder="https://x.com/mohan"
                      className="w-full pl-9 pr-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl font-medium text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition"
                    />
                  </div>
                </div>
              </div>
            </div>
          ) : (
            /* HTML Signature Import Mode */
            <div className="space-y-3.5">
              <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-[11px] text-amber-800 flex items-start gap-2">
                <FileCode className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                <span>
                  <strong>HTML Signature Import:</strong> Paste your raw HTML signature code below or upload an HTML file.
                </span>
              </div>

              <div className="flex items-center gap-3">
                <input
                  type="file"
                  id="html-signature-file-input"
                  accept=".html,.htm"
                  onChange={handleFileUpload}
                  className="hidden"
                />
                <label
                  htmlFor="html-signature-file-input"
                  className="inline-flex items-center gap-2 px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-xl border border-slate-200 cursor-pointer transition shadow-2xs"
                >
                  <Upload className="w-3.5 h-3.5" />
                  <span>Upload HTML File</span>
                </label>
                <span className="text-[11px] text-slate-400 font-medium">Or paste raw code below</span>
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Raw HTML Signature Code
                </label>
                <textarea
                  rows={12}
                  value={htmlCode}
                  onChange={(e) => {
                    setHtmlCode(e.target.value);
                    setIsDirty(true);
                  }}
                  placeholder="<table>...</table>"
                  className="w-full p-3 bg-slate-50 border border-slate-200 rounded-xl font-mono text-xs text-slate-800 leading-relaxed focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition resize-y min-h-[260px]"
                />
              </div>
            </div>
          )}

          {/* Set as Default Checkbox */}
          <div className="pt-2 border-t border-slate-100">
            <label className="flex items-center gap-2 text-xs font-bold text-slate-700 cursor-pointer">
              <input
                type="checkbox"
                checked={isDefault}
                onChange={(e) => {
                  setIsDefault(e.target.checked);
                  setIsDirty(true);
                }}
                className="w-4 h-4 rounded text-blue-600 focus:ring-blue-500 border-slate-300"
              />
              <span>Set as my default signature for outreach emails</span>
            </label>
          </div>
        </div>

        {/* Live Preview Panel */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4 space-y-3 shadow-2xs flex flex-col">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <Eye className="w-4 h-4 text-slate-500" />
              <h3 className="text-xs font-extrabold text-slate-800 uppercase tracking-wider">
                Live Signature Preview
              </h3>
            </div>
            <span className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-bold">
              {isHtmlMode ? 'HTML Signature' : 'Structured Text Format'}
            </span>
          </div>

          <div className="text-xs text-slate-400 font-medium">
            This is how your signature will appear below your outreach emails:
          </div>

          <div className="flex-1 bg-white border border-slate-200 rounded-xl p-5 overflow-y-auto shadow-2xs">
            {isHtmlMode ? (
              htmlCode ? (
                <div
                  dangerouslySetInnerHTML={{ __html: htmlCode }}
                  className="prose prose-xs max-w-none"
                />
              ) : (
                <div className="text-slate-400 italic text-xs">No HTML code entered yet.</div>
              )
            ) : (
              /* Rendered structured text signature */
              <div
                dangerouslySetInnerHTML={{ __html: fullHtml }}
                className="select-text"
              />
            )}
          </div>

          <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl space-y-1">
            <div className="text-[11px] font-bold text-slate-700">Preview Output Structure:</div>
            <pre className="text-[10px] font-mono text-slate-600 whitespace-pre leading-relaxed bg-white p-2.5 rounded-lg border border-slate-200 overflow-x-auto">
              {isHtmlMode
                ? '(Raw HTML rendered above)'
                : `${name || '[Name]'}\n${designation || '[Job Title]'}\n${company || '[Company Name]'}\n\nEmail: ${email || '[Email]'}\nPhone: ${phone || '[Phone]'}\nWebsite: ${website || '[Website]'}${linkedin ? `\nLinkedIn: ${cleanUrl(linkedin)}` : ''}${twitter ? `\nTwitter: ${cleanUrl(twitter)}` : ''}`}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CustomSignatureEditor;

