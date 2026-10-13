import React, { useEffect, useRef, useState, Suspense } from 'react';
import { ArrowLeft, Save, Eye, X, Loader2, Code2 } from 'lucide-react';
import { toast } from 'react-toastify';
import { designApi, errorMessage } from '../../services/designApi';

// GrapesJS (+ preset, CSS) is large: load only when an editor is opened.
const GrapesEditor = React.lazy(() => import('./GrapesEditor'));

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

export const PLACEHOLDERS = SMART_TAGS.map((t) => t.key);

const SAMPLE = SMART_TAGS.reduce((acc, t) => {
  acc[t.key] = t.sample;
  return acc;
}, {});

export const fillSample = (html) => {
  if (!html) return '';
  return html.replace(/\{\{\s*([a-zA-Z0-9_\s]+)\s*\}\}/g, (m, k) => {
    const raw = k.trim().toLowerCase().replace(' ', '_');
    const matched = SMART_TAGS.find((t) => t.key === raw || t.key.replace('_', '') === raw);
    return matched ? matched.sample : (SAMPLE[raw] ?? m);
  });
};

/**
 * Shared metadata form + GrapesJS canvas + preview + unsaved-change guard.
 * `sidebar` renders extra controls (signature fields / insert-signature) above the canvas.
 */
const DesignEditor = ({ kind, id, noun, starterHtml, withSubject, withDescription, sidebar, onClose, onSaved }) => {
  const editorRef = useRef(null);
  const [loading, setLoading] = useState(!!id);
  const [saving, setSaving] = useState(false);
  const [meta, setMeta] = useState({ name: '', description: '', subject: '' });
  const [initial, setInitial] = useState(null);
  const [metaDirty, setMetaDirty] = useState(false);
  const [canvasDirty, setCanvasDirty] = useState(false);
  const [error, setError] = useState('');
  const [preview, setPreview] = useState(null); // {html, mobile, source}

  useEffect(() => {
    let active = true;
    (async () => {
      if (!id) { setInitial({ project_data: {}, html: '' }); return; }
      try {
        const d = await designApi.get(kind, id);
        if (!active) return;
        setMeta({ name: d.name || '', description: d.description || '', subject: d.subject || '' });
        setInitial(d);
      } catch (e) {
        toast.error(errorMessage(e));
        onClose();
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, kind]);

  const dirty = metaDirty || canvasDirty;

  useEffect(() => {
    const handler = (e) => { if (dirty) { e.preventDefault(); e.returnValue = ''; } };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [dirty]);

  const guardedClose = () => {
    if (dirty) {
      toast.info('Unsaved changes discarded.');
    }
    onClose();
  };

  const setField = (k, v) => { setMeta((m) => ({ ...m, [k]: v })); setMetaDirty(true); };

  const handleSave = async () => {
    setError('');
    if (!meta.name.trim()) { setError('Name is required.'); return; }
    const data = editorRef.current?.getData();
    if (!data) return;
    const size = (JSON.stringify(data.projectData) || '').length + (data.html || '').length;
    if (size > 10_000_000) {
      setError('Design is too large to save (over 10 MB). Remove large content and try again.');
      return;
    }
    const payload = { name: meta.name.trim(), project_data: data.projectData, html: data.html };
    if (withDescription) payload.description = meta.description;
    if (withSubject) payload.subject = meta.subject;
    setSaving(true);
    try {
      const saved = id ? await designApi.update(kind, id, payload) : await designApi.create(kind, payload);
      toast.success(`${noun} saved`);
      editorRef.current?.markClean();
      setCanvasDirty(false); setMetaDirty(false);
      onSaved(saved);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const openPreview = (source = false) => {
    const data = editorRef.current?.getData();
    if (data) setPreview({ html: data.html, mobile: false, source });
  };

  if (loading || !initial) {
    return <div className="p-10 flex justify-center text-slate-400"><Loader2 className="w-5 h-5 animate-spin" /></div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button onClick={guardedClose} className="flex items-center gap-2 text-sm font-bold text-slate-600 hover:text-slate-900">
          <ArrowLeft className="w-4 h-4" /> Back
        </button>
        <div className="flex gap-2">
          <button id="editor-html-btn" onClick={() => openPreview(true)} className="px-3 py-2 text-xs font-bold border border-slate-200 rounded-xl bg-white hover:bg-slate-50 flex items-center gap-2"><Code2 className="w-4 h-4" /> HTML</button>
          <button id="editor-preview-btn" onClick={() => openPreview(false)} className="px-3 py-2 text-xs font-bold border border-slate-200 rounded-xl bg-white hover:bg-slate-50 flex items-center gap-2"><Eye className="w-4 h-4" /> Preview</button>
          <button id="editor-save-btn" onClick={handleSave} disabled={saving} className="px-4 py-2 text-xs font-bold bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 text-white rounded-xl flex items-center gap-2">
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Save {noun}
          </button>
        </div>
      </div>

      {error && <div className="p-3 bg-rose-50 border border-rose-200 text-rose-700 text-sm rounded-xl">{error}</div>}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 bg-white p-4 border border-slate-200 rounded-2xl">
        <div>
          <label className="block text-xs font-bold text-slate-500 mb-1">{noun} name *</label>
          <input id="design-name" value={meta.name} maxLength={150} onChange={(e) => setField('name', e.target.value)} className="w-full p-2.5 border border-slate-200 rounded-xl text-sm" />
        </div>
        {withSubject && (
          <div>
            <label className="block text-xs font-bold text-slate-500 mb-1">Default subject (optional)</label>
            <input id="design-subject" value={meta.subject} maxLength={255} onChange={(e) => setField('subject', e.target.value)} className="w-full p-2.5 border border-slate-200 rounded-xl text-sm" />
          </div>
        )}
        {withDescription && (
          <div>
            <label className="block text-xs font-bold text-slate-500 mb-1">Description (optional)</label>
            <input id="design-description" value={meta.description} maxLength={500} onChange={(e) => setField('description', e.target.value)} className="w-full p-2.5 border border-slate-200 rounded-xl text-sm" />
          </div>
        )}
      </div>

      {sidebar && sidebar({ editorRef })}

      <Suspense fallback={<div className="p-10 flex justify-center text-slate-400"><Loader2 className="w-5 h-5 animate-spin" /></div>}>
        <GrapesEditor
          ref={editorRef}
          projectData={initial.project_data}
          initialHtml={!id ? starterHtml : ''}
          onDirty={() => setCanvasDirty(true)}
        />
      </Suspense>

      {preview && (
        <div className="fixed inset-0 z-[100] bg-slate-900/60 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-4xl h-[85vh] flex flex-col overflow-hidden">
            <div className="flex items-center justify-between p-3.5 border-b border-slate-100 bg-slate-50">
              <div className="flex items-center gap-2.5">
                <h3 className="font-extrabold text-slate-800 text-sm">
                  {preview.source ? 'HTML Source Code' : '✨ Live Email Preview'}
                </h3>
                {!preview.source && (
                  <span className="px-2.5 py-0.5 rounded-full text-[10px] font-extrabold bg-emerald-100 text-emerald-800 border border-emerald-200 flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    Previewing with sample customer data
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2">
                {!preview.source && (
                  <button onClick={() => setPreview((p) => ({ ...p, mobile: !p.mobile }))} className="px-3 py-1 text-xs font-bold border border-slate-200 rounded-lg bg-white hover:bg-slate-50 transition cursor-pointer">
                    {preview.mobile ? '🖥️ Desktop View' : '📱 Mobile View'}
                  </button>
                )}
                <button onClick={() => setPreview(null)} className="text-slate-400 hover:text-slate-700 p-1 rounded-lg hover:bg-slate-200/50 transition cursor-pointer">
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>
            {preview.source ? (
              <pre className="flex-1 overflow-auto p-4 text-xs bg-slate-50 whitespace-pre-wrap break-all">{preview.html}</pre>
            ) : (
              <div className="flex-1 bg-slate-100 overflow-auto flex justify-center p-4">
                <iframe
                  title="Email preview"
                  sandbox="allow-same-origin allow-popups"
                  srcDoc={fillSample(
                    (() => {
                      const doc = preview.html || '';
                      const respStyle = '<style>img { max-width: 100% !important; height: auto !important; }</style>';
                      return doc.includes('<head>') ? doc.replace('<head>', `<head>${respStyle}`) : `${respStyle}${doc}`;
                    })()
                  )}
                  style={{ width: preview.mobile ? 375 : '100%', height: '100%', background: '#fff', border: 0, borderRadius: preview.mobile ? 12 : 0, boxShadow: preview.mobile ? '0 10px 25px -5px rgba(0,0,0,0.1)' : 'none' }}
                />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default DesignEditor;
