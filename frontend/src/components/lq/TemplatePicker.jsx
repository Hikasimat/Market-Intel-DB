import React, { useEffect, useRef, useState } from 'react';
import { Eye, X, Wand2 } from 'lucide-react';
import { toast } from 'react-toastify';
import { designApi, composePreview, errorMessage } from '../../services/designApi';

/**
 * Optional template / signature selector for the existing intro-email composer.
 * It only fills the existing subject/body fields and reports the chosen ids upward;
 * sending still goes through the existing explicit "Send" button + SMTP flow.
 */
const TemplatePicker = ({ prospect, toEmails, ccEmails, emailSubject, emailBody, setEmailSubject, setEmailBody, disabled, selection, setSelection }) => {
  const [templates, setTemplates] = useState([]);
  const [signatures, setSignatures] = useState([]);
  const [previewHtml, setPreviewHtml] = useState(null);
  const baseBodyRef = useRef(null);

  useEffect(() => {
    designApi.list('email').then(setTemplates).catch(() => {});
    designApi.list('signature').then(setSignatures).catch(() => {});
  }, []);

  const recipients = [...toEmails, ...ccEmails];

  const applyTemplate = async (templateId, signatureId = selection.signatureId) => {
    if (!templateId) {
      baseBodyRef.current = null;
      setSelection({ templateId: '', signatureId, baseBody: null });
      return;
    }
    try {
      const r = await composePreview({
        prospect: prospect.id, to_emails: recipients, subject: '', body: '',
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
        prospect: prospect.id, to_emails: recipients, subject: emailSubject, body: emailBody,
        template_id: selection.templateId || null, signature_id: selection.signatureId || null, body_edited: edited,
      });
      setPreviewHtml(r.html);
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
        <button type="button" id="compose-preview-btn" onClick={doPreview} className="px-3 py-1.5 text-[11px] font-bold bg-white border border-slate-200 rounded-lg flex items-center gap-1.5 hover:bg-slate-50"><Eye className="w-3.5 h-3.5" /> Preview final email</button>
      </div>

      {previewHtml !== null && (
        <div className="fixed inset-0 z-[200] bg-slate-900/60 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-3xl h-[80vh] flex flex-col overflow-hidden">
            <div className="flex items-center justify-between p-3 border-b border-slate-100">
              <h3 className="font-bold text-slate-800 text-sm">Final email preview — {emailSubject}</h3>
              <button type="button" onClick={() => setPreviewHtml(null)}><X className="w-5 h-5 text-slate-400" /></button>
            </div>
            <iframe title="Final email preview" sandbox="" srcDoc={previewHtml} className="flex-1 bg-white border-0" />
          </div>
        </div>
      )}
    </div>
  );
};

export default TemplatePicker;
