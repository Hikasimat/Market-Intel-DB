import React, { useState, useEffect, useRef } from 'react';
import {
  ArrowLeft,
  Save,
  Loader2,
  FileText,
  Eye,
  Info,
} from 'lucide-react';
import { toast } from 'react-toastify';
import { designApi, errorMessage } from '../../services/designApi';

const SMART_VARIABLES = [
  { key: '{{contact_name}}', label: 'Contact Name', desc: 'Recipient contact person' },
  { key: '{{company_name}}', label: 'Company Name', desc: 'Prospect company name' },
  { key: '{{sender_name}}', label: 'Sender Name', desc: 'Your full name' },
  { key: '{{sender_email}}', label: 'Sender Email', desc: 'Your outreach email' },
  { key: '{{designation}}', label: 'Job Title', desc: 'Your official designation' },
  { key: '{{website}}', label: 'Website', desc: 'Company website URL' },
];

const SAMPLE_DATA = {
  '{{contact_name}}': 'John Doe',
  '{{company_name}}': 'Acme Global Industries',
  '{{sender_name}}': 'Mohan',
  '{{sender_email}}': 'mohan@example.com',
  '{{designation}}': 'Software Developer',
  '{{website}}': 'www.example.com',
};

const escapeHtml = (str) => {
  return String(str || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
};

const htmlToPlainText = (html) => {
  if (!html) return '';
  try {
    const doc = new DOMParser().parseFromString(html, 'text/html');
    return doc.body.textContent || doc.body.innerText || '';
  } catch {
    return html.replace(/<[^>]+>/g, '');
  }
};

/**
 * PlainTextTemplateEditor
 * Dedicated plain-text email template creator & editor with smart tag insertion and live preview.
 */
export default function PlainTextTemplateEditor({ id, onClose, onSaved }) {
  const [name, setName] = useState('');
  const [subject, setSubject] = useState('');
  const [description, setDescription] = useState('');
  const [body, setBody] = useState('');
  const [loading, setLoading] = useState(!!id);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [isDirty, setIsDirty] = useState(false);

  const bodyTextareaRef = useRef(null);

  useEffect(() => {
    let active = true;
    if (!id) {
      setBody(
        `Dear {{contact_name}},\n\nI am reaching out from {{company_name}} to introduce our comprehensive solutions.\n\nWe would welcome an opportunity for a brief introductory call this week to discuss potential alignment.\n\nBest regards,\n{{sender_name}}\n{{designation}}`
      );
      return;
    }

    (async () => {
      try {
        const data = await designApi.get('email', id);
        if (!active) return;
        setName(data.name || '');
        setSubject(data.subject || '');
        setDescription(data.description || '');

        if (data.text) {
          setBody(data.text);
        } else if (data.html) {
          setBody(htmlToPlainText(data.html));
        } else {
          setBody('');
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

  const handleInsertVariable = (tag) => {
    const textarea = bodyTextareaRef.current;
    if (!textarea) {
      setBody((prev) => prev + tag);
      setIsDirty(true);
      return;
    }

    const start = textarea.selectionStart ?? body.length;
    const end = textarea.selectionEnd ?? body.length;
    const nextBody = body.substring(0, start) + tag + body.substring(end);
    setBody(nextBody);
    setIsDirty(true);

    setTimeout(() => {
      textarea.focus();
      textarea.setSelectionRange(start + tag.length, start + tag.length);
    }, 0);
  };

  const handleSave = async () => {
    setError('');
    if (!name.trim()) {
      setError('Template name is required.');
      return;
    }

    setSaving(true);
    const plainTextBody = body || '';
    const safeWrappedHtml = plainTextBody
      ? `<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 14px; line-height: 1.6; color: #1e293b; white-space: pre-wrap;">${escapeHtml(plainTextBody)}</div>`
      : '';

    const payload = {
      name: name.trim(),
      subject: subject.trim(),
      description: description.trim(),
      text: plainTextBody,
      html: safeWrappedHtml,
      project_data: { is_plain_text: true, version: 2 },
    };

    try {
      const saved = id
        ? await designApi.update('email', id, payload)
        : await designApi.create('email', payload);

      toast.success('Plain-text email template saved successfully!');
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

  const renderSamplePreview = (text) => {
    if (!text) return '';
    let rendered = text;
    Object.entries(SAMPLE_DATA).forEach(([tag, val]) => {
      rendered = rendered.split(tag).join(val);
    });
    return rendered;
  };

  if (loading) {
    return (
      <div className="p-16 flex items-center justify-center text-slate-400">
        <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
      </div>
    );
  }

  return (
    <div className="space-y-4 max-w-7xl mx-auto">
      {/* Top Action Bar */}
      <div className="flex items-center justify-between bg-white border border-slate-200 px-4 py-3 rounded-2xl shadow-2xs">
        <button
          type="button"
          onClick={guardedClose}
          className="flex items-center gap-2 text-xs font-bold text-slate-600 hover:text-slate-900 transition cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Templates</span>
        </button>
        <div className="flex items-center gap-2">
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 bg-slate-100 rounded-lg text-[11px] font-bold text-slate-600">
            <FileText className="w-3.5 h-3.5 text-slate-500" />
            <span>Plain-Text Template</span>
          </div>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 text-white text-xs font-bold rounded-xl transition cursor-pointer shadow-sm"
          >
            {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
            <span>{saving ? 'Saving...' : 'Save Template'}</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-xs font-medium rounded-xl">
          {error}
        </div>
      )}

      {/* Main Grid: Editor on Left, Real-Time Preview on Right */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Editor Form */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4 space-y-4 shadow-2xs">
          <div>
            <label className="block text-xs font-extrabold text-slate-800 uppercase tracking-wider mb-1">
              Template Name <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setIsDirty(true);
              }}
              placeholder="e.g. Initial Outreach - Enterprise"
              className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl font-medium text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition"
            />
          </div>

          <div>
            <label className="block text-xs font-extrabold text-slate-800 uppercase tracking-wider mb-1">
              Default Email Subject
            </label>
            <input
              type="text"
              value={subject}
              onChange={(e) => {
                setSubject(e.target.value);
                setIsDirty(true);
              }}
              placeholder="e.g. Strategic Introduction — {{company_name}}"
              className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl font-medium text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition"
            />
          </div>

          <div>
            <label className="block text-xs font-extrabold text-slate-800 uppercase tracking-wider mb-1">
              Description (Optional)
            </label>
            <input
              type="text"
              value={description}
              onChange={(e) => {
                setDescription(e.target.value);
                setIsDirty(true);
              }}
              placeholder="e.g. First contact email for newly qualified prospects"
              className="w-full px-3 py-2 text-xs bg-slate-50 border border-slate-200 rounded-xl font-medium text-slate-900 focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition"
            />
          </div>

          {/* Smart Variable Insertion Chips */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="block text-xs font-extrabold text-slate-800 uppercase tracking-wider">
                Insert Smart Variables
              </label>
              <span className="text-[10px] text-slate-400 font-medium">Click to insert at cursor</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {SMART_VARIABLES.map((v) => (
                <button
                  key={v.key}
                  type="button"
                  onClick={() => handleInsertVariable(v.key)}
                  className="px-2.5 py-1 bg-slate-100 hover:bg-blue-50 hover:text-blue-700 hover:border-blue-200 border border-slate-200 rounded-lg text-[11px] font-semibold text-slate-700 transition cursor-pointer"
                  title={v.desc}
                >
                  + {v.label} <span className="text-slate-400 font-normal text-[10px]">({v.key})</span>
                </button>
              ))}
            </div>
          </div>

          {/* Plain-Text Email Body */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="block text-xs font-extrabold text-slate-800 uppercase tracking-wider">
                Email Message Content (Plain Text Only)
              </label>
              <span className="text-[10px] text-slate-400 font-medium">
                {body.length} characters | {body.trim() ? body.trim().split(/\s+/).length : 0} words
              </span>
            </div>
            <textarea
              ref={bodyTextareaRef}
              rows={14}
              value={body}
              onChange={(e) => {
                setBody(e.target.value);
                setIsDirty(true);
              }}
              placeholder="Type your plain-text email message template here..."
              className="w-full p-3.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-mono text-slate-800 leading-relaxed focus:bg-white focus:outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition resize-y min-h-[280px]"
            />
            <p className="text-[10px] text-slate-400 mt-1">
              Plain text only. Use smart variable tags above to personalize emails for each recipient.
            </p>
          </div>
        </div>

        {/* Live Preview Panel */}
        <div className="bg-white border border-slate-200 rounded-2xl p-4 space-y-3 shadow-2xs flex flex-col">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <Eye className="w-4 h-4 text-slate-500" />
              <h3 className="text-xs font-extrabold text-slate-800 uppercase tracking-wider">
                Live Plain-Text Preview
              </h3>
            </div>
            <span className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded font-bold">
              Simulated with sample prospect data
            </span>
          </div>

          <div className="space-y-2">
            <div className="text-xs text-slate-500 font-semibold">
              <span className="text-slate-400">Subject: </span>
              <span className="text-slate-900 font-bold">
                {renderSamplePreview(subject) || '(No Subject)'}
              </span>
            </div>
          </div>

          <div className="flex-1 bg-slate-50 border border-slate-200 rounded-xl p-4 overflow-y-auto">
            <div className="text-xs font-sans text-slate-800 whitespace-pre-wrap leading-relaxed select-text">
              {renderSamplePreview(body) || (
                <span className="text-slate-400 italic">No message body entered yet.</span>
              )}
            </div>
          </div>

          <div className="p-2.5 bg-blue-50/60 border border-blue-100 rounded-xl text-[11px] text-blue-800 flex items-start gap-2">
            <Info className="w-3.5 h-3.5 text-blue-600 shrink-0 mt-0.5" />
            <span>
              This template will be sent as clean plain-text. Variables will automatically resolve to real contact and company details when sent to prospects.
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

