import React, { useEffect, useRef, useState } from 'react';
import {
  ArrowLeft,
  Save,
  Eye,
  X,
  Loader2,
  Code2,
  Monitor,
  Smartphone,
  FileCode,
  Copy,
  Check,
  Upload,
} from 'lucide-react';
import { toast } from 'react-toastify';
import { designApi, errorMessage } from '../../services/designApi';
import SimpleEmailEditor from './emailEditor/SimpleEmailEditor';
import { SMART_TAGS, fillSample } from './emailEditor/emailHtmlGenerator';

export { SMART_TAGS, fillSample };
export const PLACEHOLDERS = SMART_TAGS.map((t) => t.key);

/**
 * Shared metadata form + Simple Email Canvas + preview + unsaved-change guard.
 */
const DesignEditor = ({
  kind,
  id,
  noun,
  starterHtml,
  emptyCanvas = false,
  withSubject,
  withDescription,
  sidebar,
  onClose,
  onSaved,
}) => {
  const editorRef = useRef(null);
  const [loading, setLoading] = useState(!!id);
  const [saving, setSaving] = useState(false);
  const [meta, setMeta] = useState({ name: '', description: '', subject: '' });
  const [initial, setInitial] = useState(null);
  const [metaDirty, setMetaDirty] = useState(false);
  const [canvasDirty, setCanvasDirty] = useState(false);
  const [error, setError] = useState('');
  const [preview, setPreview] = useState(null); // { html, mobile, source, tab: 'view' | 'import' }
  const [importHtmlCode, setImportHtmlCode] = useState('');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    let active = true;
    (async () => {
      if (!id) {
        setInitial({ project_data: {}, html: '' });
        return;
      }
      try {
        const d = await designApi.get(kind, id);
        if (!active) return;
        setMeta({
          name: d.name || '',
          description: d.description || '',
          subject: d.subject || '',
        });
        setInitial(d);
      } catch (e) {
        toast.error(errorMessage(e));
        onClose();
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [id, kind]);

  const dirty = metaDirty || canvasDirty;

  useEffect(() => {
    const handler = (e) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [dirty]);

  const guardedClose = () => {
    if (dirty) {
      toast.info('Unsaved changes discarded.');
    }
    onClose();
  };

  const setField = (k, v) => {
    setMeta((m) => ({ ...m, [k]: v }));
    setMetaDirty(true);
  };

  const handleSave = async () => {
    setError('');
    if (!meta.name.trim()) {
      setError('Name is required.');
      return;
    }
    const data = editorRef.current?.getData();
    if (!data) return;
    const size =
      (JSON.stringify(data.projectData) || '').length + (data.html || '').length;
    if (size > 10_000_000) {
      setError('Design is too large to save (over 10 MB). Remove large content and try again.');
      return;
    }
    const payload = {
      name: meta.name.trim(),
      project_data: data.projectData,
      html: data.html,
    };
    if (withDescription) payload.description = meta.description;
    if (withSubject) payload.subject = meta.subject;
    setSaving(true);
    try {
      const saved = id
        ? await designApi.update(kind, id, payload)
        : await designApi.create(kind, payload);
      toast.success(`${noun} saved`);
      editorRef.current?.markClean();
      setCanvasDirty(false);
      setMetaDirty(false);
      onSaved(saved);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  };

  const openPreview = (source = false, tab = 'view') => {
    const data = editorRef.current?.getData();
    if (data) {
      setPreview({ html: data.html, mobile: false, source, tab });
      setImportHtmlCode('');
      setCopied(false);
    }
  };

  const handleImportHtml = () => {
    if (!importHtmlCode.trim()) {
      toast.warning('Please enter or paste HTML code to import.');
      return;
    }
    try {
      editorRef.current?.loadHtml(importHtmlCode);
      setCanvasDirty(true);
      setPreview(null);
      setImportHtmlCode('');
      toast.success('HTML template imported successfully into canvas!');
    } catch (e) {
      toast.error('Failed to import HTML: ' + (e.message || 'Invalid HTML'));
    }
  };

  const handleCopyHtml = async () => {
    if (!preview?.html) return;
    try {
      await navigator.clipboard.writeText(preview.html);
      setCopied(true);
      toast.success('HTML copied to clipboard!');
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error('Could not copy HTML to clipboard');
    }
  };

  if (loading || !initial) {
    return (
      <div className="p-10 flex justify-center text-slate-400">
        <Loader2 className="w-5 h-5 animate-spin" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Top Header Bar */}
      <div className="flex items-center justify-between">
        <button
          onClick={guardedClose}
          className="flex items-center gap-2 text-sm font-bold text-slate-600 hover:text-slate-900 transition cursor-pointer"
        >
          <ArrowLeft className="w-4 h-4" /> Back
        </button>
        <div className="flex gap-2">
          <button
            id="editor-import-html-btn"
            type="button"
            onClick={() => openPreview(true, 'import')}
            className="px-3 py-2 text-xs font-bold border border-emerald-200 rounded-xl bg-emerald-50 hover:bg-emerald-100 text-emerald-800 flex items-center gap-2 transition cursor-pointer shadow-2xs"
            title="Import raw HTML or custom template code"
          >
            <FileCode className="w-4 h-4 text-emerald-600" /> Import HTML
          </button>
          <button
            id="editor-html-btn"
            type="button"
            onClick={() => openPreview(true, 'view')}
            className="px-3 py-2 text-xs font-bold border border-slate-200 rounded-xl bg-white hover:bg-slate-50 flex items-center gap-2 transition cursor-pointer"
          >
            <Code2 className="w-4 h-4 text-slate-500" /> HTML
          </button>
          <button
            id="editor-preview-btn"
            type="button"
            onClick={() => openPreview(false, 'view')}
            className="px-3 py-2 text-xs font-bold border border-slate-200 rounded-xl bg-white hover:bg-slate-50 flex items-center gap-2 transition cursor-pointer"
          >
            <Eye className="w-4 h-4 text-blue-600" /> Preview
          </button>
          <button
            id="editor-save-btn"
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 text-xs font-bold bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 text-white rounded-xl flex items-center gap-2 shadow-sm transition cursor-pointer"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} Save {noun}
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 bg-rose-50 border border-rose-200 text-rose-700 text-sm rounded-xl">
          {error}
        </div>
      )}

      {/* Metadata Form: Name, Subject, Description */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 bg-white p-4 border border-slate-200 rounded-2xl">
        <div>
          <label className="block text-xs font-bold text-slate-500 mb-1">{noun} name *</label>
          <input
            id="design-name"
            value={meta.name}
            maxLength={150}
            onChange={(e) => setField('name', e.target.value)}
            placeholder={`e.g. Intro Email for ${noun}`}
            className="w-full p-2.5 border border-slate-200 rounded-xl text-sm outline-none focus:ring-2 focus:ring-blue-100"
          />
        </div>
        {withSubject && (
          <div>
            <label className="block text-xs font-bold text-slate-500 mb-1">
              Default subject (optional)
            </label>
            <input
              id="design-subject"
              value={meta.subject}
              maxLength={255}
              onChange={(e) => setField('subject', e.target.value)}
              placeholder="e.g. Solutions for {{company_name}}"
              className="w-full p-2.5 border border-slate-200 rounded-xl text-sm outline-none focus:ring-2 focus:ring-blue-100"
            />
          </div>
        )}
        {withDescription && (
          <div>
            <label className="block text-xs font-bold text-slate-500 mb-1">
              Description (optional)
            </label>
            <input
              id="design-description"
              value={meta.description}
              maxLength={500}
              onChange={(e) => setField('description', e.target.value)}
              placeholder="Internal notes about when to use this template"
              className="w-full p-2.5 border border-slate-200 rounded-xl text-sm outline-none focus:ring-2 focus:ring-blue-100"
            />
          </div>
        )}
      </div>

      {/* Optional sidebar/header controls passed by caller */}
      {sidebar && sidebar({ editorRef })}

      {/* New Lightweight Simple Email Editor */}
      <SimpleEmailEditor
        ref={editorRef}
        projectData={initial.project_data}
        initialHtml={!id ? starterHtml : (initial.html || '')}
        emptyCanvas={!id && (emptyCanvas || kind === 'signature')}
        kind={kind}
        onDirty={() => setCanvasDirty(true)}
      />

      {/* Global Preview & HTML Import/View Modal */}
      {preview && (
        <div className="fixed inset-0 z-[120] bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl h-[88vh] flex flex-col overflow-hidden border border-slate-200">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-4 border-b border-slate-100 bg-slate-50">
              <div className="flex items-center gap-3">
                <h3 className="font-extrabold text-slate-800 text-sm">
                  {preview.source
                    ? preview.tab === 'import'
                      ? '📥 Import HTML Template'
                      : '📄 HTML Source Code'
                    : '✨ Live Email Preview'}
                </h3>
                {!preview.source && (
                  <span className="px-2.5 py-0.5 rounded-full text-[10px] font-extrabold bg-emerald-100 text-emerald-800 border border-emerald-200 flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                    Previewing with sample customer data
                  </span>
                )}
              </div>

              <div className="flex items-center gap-2">
                {preview.source ? (
                  <div className="flex items-center border border-slate-200 rounded-xl bg-white p-0.5">
                    <button
                      type="button"
                      onClick={() => setPreview((p) => ({ ...p, tab: 'view' }))}
                      className={`px-3 py-1 text-xs font-bold rounded-lg flex items-center gap-1.5 transition cursor-pointer ${
                        preview.tab === 'view'
                          ? 'bg-blue-600 text-white shadow-2xs'
                          : 'text-slate-600 hover:bg-slate-100'
                      }`}
                    >
                      <Code2 className="w-3.5 h-3.5" />
                      <span>View HTML</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setPreview((p) => ({ ...p, tab: 'import' }))}
                      className={`px-3 py-1 text-xs font-bold rounded-lg flex items-center gap-1.5 transition cursor-pointer ${
                        preview.tab === 'import'
                          ? 'bg-emerald-600 text-white shadow-2xs'
                          : 'text-slate-600 hover:bg-slate-100'
                      }`}
                    >
                      <FileCode className="w-3.5 h-3.5" />
                      <span>Import HTML</span>
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center border border-slate-200 rounded-xl bg-white p-0.5">
                    <button
                      type="button"
                      onClick={() => setPreview((p) => ({ ...p, mobile: false }))}
                      className={`px-3 py-1 text-xs font-bold rounded-lg flex items-center gap-1.5 transition cursor-pointer ${
                        !preview.mobile ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-100'
                      }`}
                    >
                      <Monitor className="w-3.5 h-3.5" />
                      <span>Desktop</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => setPreview((p) => ({ ...p, mobile: true }))}
                      className={`px-3 py-1 text-xs font-bold rounded-lg flex items-center gap-1.5 transition cursor-pointer ${
                        preview.mobile ? 'bg-blue-600 text-white' : 'text-slate-600 hover:bg-slate-100'
                      }`}
                    >
                      <Smartphone className="w-3.5 h-3.5" />
                      <span>Mobile</span>
                    </button>
                  </div>
                )}
                <button
                  type="button"
                  onClick={() => setPreview(null)}
                  className="text-slate-400 hover:text-slate-700 p-1 rounded-lg hover:bg-slate-200/50 transition cursor-pointer"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Modal Body */}
            {preview.source ? (
              preview.tab === 'import' ? (
                /* Import HTML Tab */
                <div className="flex-1 flex flex-col p-4 bg-slate-50 gap-3 overflow-hidden">
                  <div className="bg-emerald-50 border border-emerald-200 text-emerald-900 px-4 py-2.5 rounded-xl text-xs flex items-start gap-2.5">
                    <FileCode className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                    <div>
                      <p className="font-bold">Paste or import HTML code directly into your template canvas</p>
                      <p className="text-emerald-700 text-[11px] mt-0.5">
                        Supports full HTML documents, email newsletters, signature designs, and table snippets. Once imported, you can visually edit and customize all content on the canvas.
                      </p>
                    </div>
                  </div>
                  <textarea
                    id="import-html-textarea"
                    value={importHtmlCode}
                    onChange={(e) => setImportHtmlCode(e.target.value)}
                    placeholder="Paste your HTML code here (e.g. <table>...</table> or full <!DOCTYPE html>...)..."
                    className="flex-1 w-full p-3 font-mono text-xs bg-slate-900 text-slate-100 rounded-xl border border-slate-700 outline-none focus:ring-2 focus:ring-emerald-500 resize-none select-text"
                  />
                  <div className="flex items-center justify-between pt-1">
                    <span className="text-xs text-slate-500">
                      {importHtmlCode ? `${importHtmlCode.length.toLocaleString()} characters` : 'No code entered yet'}
                    </span>
                    <div className="flex gap-2">
                      <button
                        type="button"
                        onClick={() => setPreview(null)}
                        className="px-3.5 py-2 text-xs font-bold text-slate-600 hover:text-slate-800 bg-white border border-slate-200 rounded-xl cursor-pointer transition hover:bg-slate-50"
                      >
                        Cancel
                      </button>
                      <button
                        type="button"
                        id="btn-confirm-import-html"
                        onClick={handleImportHtml}
                        disabled={!importHtmlCode.trim()}
                        className="px-4 py-2 text-xs font-bold bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-300 text-white rounded-xl flex items-center gap-1.5 transition cursor-pointer shadow-sm disabled:cursor-not-allowed"
                      >
                        <Upload className="w-4 h-4" />
                        <span>Import HTML into Canvas</span>
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                /* View HTML Tab */
                <div className="flex-1 flex flex-col overflow-hidden relative">
                  <div className="absolute top-3 right-3 z-10">
                    <button
                      type="button"
                      onClick={handleCopyHtml}
                      className="px-2.5 py-1.5 text-xs font-bold bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg flex items-center gap-1.5 transition cursor-pointer border border-slate-700 shadow-sm"
                    >
                      {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                      <span>{copied ? 'Copied!' : 'Copy Code'}</span>
                    </button>
                  </div>
                  <pre className="flex-1 overflow-auto p-4 text-xs font-mono bg-slate-900 text-slate-100 whitespace-pre-wrap select-all">
                    {preview.html}
                  </pre>
                </div>
              )
            ) : (
              /* Live Preview */
              <div className="flex-1 bg-slate-100 overflow-auto flex justify-center p-6">
                <iframe
                  title="Email preview"
                  sandbox="allow-same-origin allow-popups"
                  srcDoc={fillSample(preview.html || '')}
                  style={{
                    width: preview.mobile ? '375px' : '100%',
                    maxWidth: preview.mobile ? '375px' : '640px',
                    height: '100%',
                    background: '#fff',
                    border: '1px solid #cbd5e1',
                    borderRadius: preview.mobile ? '24px' : '8px',
                    boxShadow: '0 15px 30px -5px rgba(0,0,0,0.1)',
                  }}
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
