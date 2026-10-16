import React, { useEffect, useRef, useState } from 'react';
import { Eye, X, Wand2, Mail, CheckCircle2, User, Users } from 'lucide-react';
import { toast } from 'react-toastify';
import { designApi, composePreview, errorMessage } from '../../services/designApi';

/**
 * Optional template / signature selector for the existing intro-email composer.
 * It only fills the existing subject/body fields and reports the chosen ids upward;
 * sending still goes through the existing explicit "Send" button flow.
 */
const TemplatePicker = ({ prospect, toEmails, ccEmails, emailSubject, emailBody, setEmailSubject, setEmailBody, disabled, selection, setSelection }) => {
  const [templates, setTemplates] = useState([]);
  const [signatures, setSignatures] = useState([]);
  const [previewData, setPreviewData] = useState(null);
  const baseBodyRef = useRef(null);
  const iframeRef = useRef(null);

  const initIframeEditor = () => {
    try {
      const iframe = iframeRef.current;
      if (!iframe) return;
      const doc = iframe.contentDocument || iframe.contentWindow?.document;
      if (!doc || !doc.body) return;

      // Inject ultra-slim 4px scrollbar styling with no chunky buttons
      const styleId = 'slim-scrollbar-injected';
      let styleEl = doc.getElementById(styleId);
      if (!styleEl) {
        styleEl = doc.createElement('style');
        styleEl.id = styleId;
        doc.head.appendChild(styleEl);
      }
      styleEl.textContent = `
        * {
          box-sizing: border-box;
          scrollbar-width: thin !important;
          scrollbar-color: #cbd5e1 transparent !important;
        }
        ::-webkit-scrollbar, *::-webkit-scrollbar {
          width: 4px !important;
          height: 4px !important;
        }
        ::-webkit-scrollbar-track, *::-webkit-scrollbar-track {
          background: transparent !important;
        }
        ::-webkit-scrollbar-thumb, *::-webkit-scrollbar-thumb {
          background: #cbd5e1 !important;
          border-radius: 9999px !important;
        }
        ::-webkit-scrollbar-thumb:hover, *::-webkit-scrollbar-thumb:hover {
          background: #94a3b8 !important;
        }
        ::-webkit-scrollbar-button, *::-webkit-scrollbar-button {
          display: none !important;
          width: 0 !important;
          height: 0 !important;
        }
        ::-webkit-scrollbar-corner, *::-webkit-scrollbar-corner {
          background: transparent !important;
        }
      `;

      // Find the editable body element
      const editableEl = doc.getElementById('editable-email-body') || doc.body;
      if (editableEl) {
        editableEl.setAttribute('contenteditable', 'true');
        editableEl.setAttribute('spellcheck', 'false');

        const syncBodyToParent = () => {
          const text = editableEl.innerText || '';
          setEmailBody(text);
        };

        editableEl.removeEventListener('input', syncBodyToParent);
        editableEl.addEventListener('input', syncBodyToParent);
        editableEl.removeEventListener('blur', syncBodyToParent);
        editableEl.addEventListener('blur', syncBodyToParent);
      }
    } catch (err) {
      console.error('Failed to initialize iframe preview editor:', err);
    }
  };

  useEffect(() => {
    if (previewData) {
      const timer = setTimeout(initIframeEditor, 60);
      return () => clearTimeout(timer);
    }
  }, [previewData]);

  useEffect(() => {
    designApi.list('email').then(setTemplates).catch(() => {});
    designApi.list('signature').then(setSignatures).catch(() => {});
  }, []);

  const parseEmails = (input) => {
    if (!input) return [];
    if (Array.isArray(input)) return input.filter(Boolean);
    if (typeof input === 'string') {
      return input.split(/[,;\s]+/).map(s => s.trim()).filter(Boolean);
    }
    return [];
  };

  const toList = parseEmails(toEmails);
  const ccList = parseEmails(ccEmails);
  const recipients = [...toList, ...ccList];

  const applyTemplate = async (templateId, signatureId = selection.signatureId) => {
    if (!templateId) {
      baseBodyRef.current = null;
      setSelection({ templateId: '', signatureId, baseBody: null });
      return;
    }
    try {
      const r = await composePreview({
        prospect: prospect?.id || null, to_emails: recipients, subject: '', body: '',
        template_id: templateId, signature_id: signatureId || null, body_edited: false,
      });
      if (r.subject) setEmailSubject(r.subject);
      setEmailBody(r.text_body);
      baseBodyRef.current = r.text_body;
      setSelection({ templateId, signatureId, baseBody: r.text_body });
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  // Re-resolve placeholders when recipients change and the user has not edited the text.
  const recKey = recipients.join(',');
  useEffect(() => {
    if (selection.templateId && baseBodyRef.current !== null && emailBody === baseBodyRef.current) {
      applyTemplate(selection.templateId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recKey]);

  const doPreview = async () => {
    try {
      const edited = !selection.templateId || emailBody !== selection.baseBody;
      const r = await composePreview({
        prospect: prospect?.id || null, to_emails: recipients, subject: emailSubject, body: emailBody,
        template_id: selection.templateId || null, signature_id: selection.signatureId || null, body_edited: edited,
      });
      setPreviewData({
        html: r.html,
        subject: emailSubject || r.subject || '(No Subject)',
        from: r.from_address || '',
        to: toList,
        cc: ccList,
      });
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  if (!templates.length && !signatures.length) return null;

  const defTpl = templates.find((t) => t.is_default);
  const defSig = signatures.find((s) => s.is_default);

  return (
    <div className="p-3 bg-indigo-50/60 border border-indigo-100 rounded-xl space-y-2">
      <div className="flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-wider text-indigo-800"><Wand2 className="w-3.5 h-3.5" /> Saved template & signature (optional)</div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <div className="flex gap-1.5">
          <select id="compose-template-select" disabled={disabled} value={selection.templateId} onChange={(e) => applyTemplate(e.target.value)} className="flex-1 p-2 bg-white border border-slate-200 rounded-lg text-xs">
            <option value="">No template (plain message)</option>
            {templates.map((t) => <option key={t.id} value={t.id}>{t.name}{t.is_default ? ' ★' : ''}</option>)}
          </select>
          {defTpl && <button type="button" disabled={disabled} onClick={() => applyTemplate(defTpl.id)} className="px-2 text-[10px] font-bold bg-white border border-slate-200 rounded-lg">Use default</button>}
        </div>
        <div className="flex gap-1.5">
          <select id="compose-signature-select" disabled={disabled} value={selection.signatureId} onChange={(e) => { const sid = e.target.value; setSelection({ ...selection, signatureId: sid }); }} className="flex-1 p-2 bg-white border border-slate-200 rounded-lg text-xs">
            <option value="">Mail account default signature</option>
            {signatures.map((s) => <option key={s.id} value={s.id}>{s.name}{s.is_default ? ' ★' : ''}</option>)}
          </select>
          {defSig && <button type="button" disabled={disabled} onClick={() => setSelection({ ...selection, signatureId: defSig.id })} className="px-2 text-[10px] font-bold bg-white border border-slate-200 rounded-lg">Use default</button>}
        </div>
      </div>
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-slate-500">Nothing is sent until you press the Send button. You can edit the text below.</span>
        <button type="button" id="compose-preview-btn" onClick={doPreview} className="px-3 py-1.5 text-[11px] font-bold bg-white border border-slate-200 rounded-lg flex items-center gap-1.5 hover:bg-slate-50 shadow-xs"><Eye className="w-3.5 h-3.5 text-indigo-600" /> Preview final email</button>
      </div>

      {previewData !== null && (
        <div className="fixed inset-0 z-[200] bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-3 sm:p-5">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[92vh] h-[90vh] flex flex-col overflow-hidden border border-slate-200">
            {/* Modal Header */}
            <div className="flex items-center justify-between px-6 py-3.5 border-b border-slate-200 bg-white">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 shadow-xs">
                  <Mail className="w-4 h-4" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="font-bold text-slate-900 text-sm tracking-tight">Deliverable Email Preview</h3>
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                      Live Preview
                    </span>
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
                      Editable Body
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500">
                    Exact deliverable layout with template design, inline media, and signature
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setPreviewData(null)}
                className="p-1.5 text-slate-400 hover:text-slate-700 rounded-lg hover:bg-slate-100 transition-colors"
                title="Close Preview"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Email Metadata / Envelope Header */}
            <div className="bg-slate-50/80 border-b border-slate-200 px-6 py-4 space-y-3 font-sans">
              {/* Subject Row */}
              <div className="flex items-center gap-3">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400 w-14 shrink-0">Subject</span>
                <div className="flex-1">
                  <input
                    type="text"
                    value={previewData.subject || ''}
                    onChange={(e) => {
                      const newSub = e.target.value;
                      setPreviewData(prev => ({ ...prev, subject: newSub }));
                      setEmailSubject(newSub);
                    }}
                    placeholder="Enter email subject..."
                    className="w-full text-base font-extrabold text-slate-900 tracking-tight leading-snug bg-transparent hover:bg-white focus:bg-white px-2 py-1 -ml-2 rounded-lg border border-transparent hover:border-slate-300 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 outline-none transition"
                  />
                </div>
              </div>

              {/* From Row */}
              <div className="flex items-center gap-3">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400 w-14">From</span>
                <div className="flex items-center gap-2 text-xs">
                  <div className="w-5 h-5 rounded-full bg-indigo-600 text-white flex items-center justify-center text-[10px] font-bold uppercase shadow-xs">
                    {(previewData.from || 'S')[0]}
                  </div>
                  <span className="font-semibold text-slate-800">{previewData.from}</span>
                </div>
              </div>

              {/* To Row */}
              <div className="flex items-start gap-3">
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400 w-14 pt-1">To</span>
                <div className="flex flex-wrap items-center gap-1.5 flex-1">
                  {previewData.to && previewData.to.length > 0 ? (
                    previewData.to.map((addr, idx) => (
                      <span
                        key={idx}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium bg-white text-slate-800 border border-slate-200 shadow-xs"
                      >
                        <User className="w-3 h-3 text-slate-400" />
                        {addr}
                      </span>
                    ))
                  ) : (
                    <span className="text-xs text-amber-600 italic">No recipient selected</span>
                  )}
                </div>
              </div>

              {/* Cc Row (displayed when user adds CC) */}
              {previewData.cc && previewData.cc.length > 0 && (
                <div className="flex items-start gap-3 pt-0.5">
                  <span className="text-[11px] font-bold uppercase tracking-wider text-blue-600 w-14 pt-1">Cc</span>
                  <div className="flex flex-wrap items-center gap-1.5 flex-1">
                    {previewData.cc.map((addr, idx) => (
                      <span
                        key={idx}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200 shadow-xs"
                      >
                        <Users className="w-3 h-3 text-blue-500" />
                        {addr}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Email Canvas Preview Area */}
            <div className="flex-1 bg-slate-100/70 p-4 sm:p-6 overflow-hidden flex flex-col items-center">
              <div className="w-full h-full max-w-3xl bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden flex flex-col">
                <iframe
                  ref={iframeRef}
                  onLoad={initIframeEditor}
                  title="Deliverable email preview"
                  srcDoc={previewData.html}
                  className="w-full flex-1 border-0 bg-white"
                />
              </div>
            </div>

            {/* Modal Bottom Footer */}
            <div className="px-6 py-3 bg-white border-t border-slate-200 flex items-center justify-between text-xs">
              <div className="flex items-center gap-2 text-slate-500 text-[11px]">
                <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                <span>Verified deliverable layout. Changes will be sent on clicking &ldquo;Send&rdquo;.</span>
              </div>
              <button
                type="button"
                onClick={() => setPreviewData(null)}
                className="px-4 py-1.5 font-bold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors text-xs"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default TemplatePicker;
