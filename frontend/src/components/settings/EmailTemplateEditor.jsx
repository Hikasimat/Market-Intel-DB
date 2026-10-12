import React, { useEffect, useState } from 'react';
import DesignEditor, { PLACEHOLDERS } from './DesignEditor';
import { designApi } from '../../services/designApi';

const STARTER = `<table width="100%" cellpadding="0" cellspacing="0" style="font-family: Arial, sans-serif;"><tr><td style="padding:24px;">
<h2 style="margin:0 0 12px 0;color:#1e3a8a;">Hello {{contact_name}},</h2>
<p style="margin:0 0 12px 0;color:#334155;font-size:14px;line-height:1.6;">I'm {{sender_name}}. I'd love to introduce our offerings to {{company_name}}.</p>
<p style="margin:0;color:#334155;font-size:14px;line-height:1.6;">Looking forward to hearing from you.</p>
</td></tr></table>`;

const InsertSignature = ({ editorRef }) => {
  const [sigs, setSigs] = useState([]);
  const [sel, setSel] = useState('');
  useEffect(() => { designApi.list('signature').then(setSigs).catch(() => {}); }, []);
  if (!sigs.length) return null;
  return (
    <div className="flex items-center gap-2 text-xs">
      <select id="insert-signature-select" value={sel} onChange={(e) => setSel(e.target.value)} className="p-2 border border-slate-200 rounded-lg bg-white">
        <option value="">Insert a saved signature…</option>
        {sigs.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select>
      <button
        disabled={!sel}
        onClick={() => { const s = sigs.find((x) => x.id === sel); if (s) editorRef.current?.appendHtml(s.html); }}
        className="px-3 py-2 font-bold border border-slate-200 rounded-lg bg-white hover:bg-slate-50 disabled:opacity-40"
      >Insert into this template</button>
      <span className="text-slate-400">(copied once; the signature stays a separate saved item)</span>
    </div>
  );
};

const EmailTemplateEditor = (props) => (
  <DesignEditor
    kind="email" noun="Template" starterHtml={STARTER} withSubject withDescription
    sidebar={({ editorRef }) => (
      <div className="bg-blue-50/60 border border-blue-100 rounded-2xl p-3 space-y-2">
        <div className="text-xs text-slate-600">
          Placeholders (filled at send time, missing values become blank):{' '}
          {PLACEHOLDERS.map((p) => <code key={p} className="mx-0.5 px-1.5 py-0.5 bg-white border border-blue-100 rounded text-[11px]">{`{{${p}}}`}</code>)}
        </div>
        <InsertSignature editorRef={editorRef} />
      </div>
    )}
    {...props}
  />
);

export default EmailTemplateEditor;
