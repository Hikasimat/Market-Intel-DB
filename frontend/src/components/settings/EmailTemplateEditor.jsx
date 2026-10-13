import React, { useEffect, useState } from 'react';
import { Sparkles, PenTool, GripVertical, Trash2 } from 'lucide-react';
import { toast } from 'react-toastify';
import DesignEditor, { SMART_TAGS } from './DesignEditor';
import { designApi } from '../../services/designApi';

const STARTER = `<table width="100%" cellpadding="0" cellspacing="0" style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0;">
  <tr>
    <td style="padding: 32px 28px;">
      <h2 style="margin: 0 0 16px 0; color: #0f172a; font-size: 20px; font-weight: 700;">
        Hello {{contact_name}},
      </h2>
      <p style="margin: 0 0 14px 0; color: #334155; font-size: 15px; line-height: 1.6;">
        I'm reaching out from {{sender_name}} to introduce our comprehensive solutions tailored for {{company_name}}.
      </p>
      <p style="margin: 0 0 14px 0; color: #334155; font-size: 15px; line-height: 1.6;">
        We would love to schedule a brief 10-minute introductory call to explore how we can support your strategic initiatives.
      </p>
      <p style="margin: 0; color: #334155; font-size: 15px; line-height: 1.6;">
        Looking forward to hearing from you.
      </p>
    </td>
  </tr>
</table>`;

const InsertSignature = ({ editorRef }) => {
  const [sigs, setSigs] = useState([]);
  const [sel, setSel] = useState('');
  useEffect(() => { designApi.list('signature').then(setSigs).catch(() => {}); }, []);
  if (!sigs.length) return null;
  return (
    <div className="flex items-center gap-1.5 text-xs">
      <select 
        id="insert-signature-select" 
        value={sel} 
        onChange={(e) => setSel(e.target.value)} 
        className="p-1.5 px-2.5 border border-slate-300 rounded-xl bg-white text-slate-700 font-medium text-xs outline-none focus:border-indigo-500 shadow-2xs"
      >
        <option value="">Insert saved signature…</option>
        {sigs.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select>
      <button
        type="button"
        disabled={!sel}
        onClick={() => { 
          const s = sigs.find((x) => x.id === sel); 
          if (s) {
            let cleanHtml = (s.html || '')
              .replace(/<head\b[^>]*>[\s\S]*?<\/head>/gi, '')
              .replace(/<title\b[^>]*>[\s\S]*?<\/title>/gi, '')
              .trim();
            cleanHtml = cleanHtml.replace(/^[^<]+(?=<table|<div|<p|<tr|<td)/i, '').trim() || cleanHtml;
            editorRef.current?.appendHtml(cleanHtml); 
            toast.success(`Signature "${s.name}" added to template!`);
          }
        }}
        className="px-3 py-1.5 font-bold border border-slate-200 rounded-xl bg-white hover:bg-slate-50 disabled:opacity-40 text-slate-700 shadow-2xs cursor-pointer transition text-xs flex items-center gap-1"
      >
        <PenTool className="w-3.5 h-3.5 text-indigo-600" />
        <span>Add Signature</span>
      </button>
    </div>
  );
};

const EmailTemplateEditor = (props) => (
  <DesignEditor
    kind="email" noun="Template" starterHtml={STARTER} withSubject withDescription
    sidebar={({ editorRef }) => (
      <div className="bg-gradient-to-r from-indigo-50/80 via-sky-50/70 to-blue-50/80 border border-indigo-100 rounded-2xl p-3.5 shadow-2xs space-y-2.5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h4 className="text-xs font-black text-slate-800 uppercase tracking-wider flex items-center gap-1.5">
              <Sparkles className="w-4 h-4 text-indigo-600" />
              Smart Personalization Tags
            </h4>
          </div>
          <div className="shrink-0 flex items-center gap-2">
            <button
              type="button"
              onClick={() => {
                editorRef.current?.cleanStrayTags?.();
                toast.info('Removed stray tags and cleaned template!', { autoClose: 1500 });
              }}
              className="px-2.5 py-1.5 text-xs font-bold border border-slate-200 rounded-xl bg-white hover:bg-rose-50 hover:border-rose-200 text-slate-600 hover:text-rose-600 shadow-2xs cursor-pointer transition flex items-center gap-1.5"
              title="Remove any accidental stray tags sitting outside the text sections"
            >
              <Trash2 className="w-3.5 h-3.5 text-rose-500" />
              <span>Remove Stray Tags</span>
            </button>
            <InsertSignature editorRef={editorRef} />
          </div>
        </div>

        {/* Drag-and-Drop and One-Click Smart Tag Insertion Pills */}
        <div className="flex flex-wrap items-center gap-2 pt-0.5">
          {SMART_TAGS.map((tag) => (
            <button
              key={tag.key}
              type="button"
              draggable={true}
              onDragStart={(e) => {
                e.dataTransfer.setData('text/plain', tag.token);
                e.dataTransfer.setData('text/html', tag.token);
                e.dataTransfer.setData('text', tag.token);
                e.dataTransfer.effectAllowed = 'copy';
                e.currentTarget.classList.add('opacity-50', 'scale-95');
              }}
              onDragEnd={(e) => {
                e.currentTarget.classList.remove('opacity-50', 'scale-95');
              }}
              onClick={() => {
                editorRef.current?.insertTag?.(tag.token);
                toast.info(`Inserted "${tag.label}" tag!`, { autoClose: 1500 });
              }}
              className={`px-3 py-1.5 rounded-xl border text-xs font-bold transition flex items-center gap-1.5 shadow-2xs hover:scale-[1.02] active:scale-95 cursor-grab active:cursor-grabbing select-none ${tag.color}`}
              title={`${tag.desc} — Drag & drop directly into your email, or click to insert at cursor`}
            >
              <GripVertical className="w-3 h-3 opacity-40 -mr-0.5" />
              <span>{tag.icon}</span>
              <span>{tag.label}</span>
            </button>
          ))}
        </div>
      </div>
    )}
    {...props}
  />
);

export default EmailTemplateEditor;
