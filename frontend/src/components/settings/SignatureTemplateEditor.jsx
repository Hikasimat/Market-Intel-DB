import React, { useState } from 'react';
import DesignEditor from './DesignEditor';

const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const safeUrl = (u) => (/^https?:\/\//i.test((u || '').trim()) ? esc(u.trim()) : '');

const FIELDS = [
  ['name', 'Name', 'e.g. {{sender_name}} or Jane Doe'], ['designation', 'Designation', ''],
  ['company', 'Company name', ''], ['phone', 'Phone', ''], ['email', 'Email', 'e.g. {{sender_email}}'],
  ['website', 'Website (https://…)', ''], ['logo', 'Logo image URL (https://…)', ''],
  ['linkedin', 'LinkedIn URL', ''], ['twitter', 'X / Twitter URL', ''], ['facebook', 'Facebook URL', ''],
];

export const buildSignatureHtml = (f) => {
  const color = esc(f.color || '#1e3a8a');
  const font = esc(f.font || 'Arial, sans-serif');
  const align = ['left', 'center', 'right'].includes(f.align) ? f.align : 'left';
  const size = Number(f.size) || 13;
  const link = (u, label) => (safeUrl(u) ? `<a href="${safeUrl(u)}" style="color:${color};text-decoration:none;margin-right:8px;">${label}</a>` : '');
  const socials = [link(f.linkedin, 'LinkedIn'), link(f.twitter, 'X'), link(f.facebook, 'Facebook')].join('');
  const rows = [
    f.name && `<div style="font-size:${size + 3}px;font-weight:bold;color:${color};">${esc(f.name)}</div>`,
    f.designation && `<div style="color:#475569;">${esc(f.designation)}</div>`,
    f.company && `<div style="font-weight:bold;color:#0f172a;">${esc(f.company)}</div>`,
    f.phone && `<div>📞 ${esc(f.phone)}</div>`,
    f.email && `<div>✉ <a href="mailto:${esc(f.email)}" style="color:${color};text-decoration:none;">${esc(f.email)}</a></div>`,
    safeUrl(f.website) && `<div>🌐 <a href="${safeUrl(f.website)}" style="color:${color};text-decoration:none;">${safeUrl(f.website)}</a></div>`,
    socials && `<div style="margin-top:6px;">${socials}</div>`,
  ].filter(Boolean).join('');
  const logo = safeUrl(f.logo) ? `<td style="padding-right:14px;vertical-align:top;"><img src="${safeUrl(f.logo)}" alt="logo" width="80" style="display:block;border:0;"></td>` : '';
  return `<table cellpadding="0" cellspacing="0" align="${align}" style="font-family:${font};font-size:${size}px;color:#334155;border-top:2px solid ${color};padding-top:8px;"><tr>${logo}<td style="vertical-align:top;line-height:1.5;">${rows || '&nbsp;'}</td></tr></table>`;
};

const SignatureTemplateEditor = (props) => {
  const [f, setF] = useState({ color: '#1e3a8a', font: 'Arial, sans-serif', align: 'left', size: 13 });
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
  return (
    <DesignEditor
      kind="signature" noun="Signature" starterHtml={buildSignatureHtml({ name: '{{sender_name}}', email: '{{sender_email}}', color: '#1e3a8a' })}
      sidebar={({ editorRef }) => (
        <details className="bg-blue-50/60 border border-blue-100 rounded-2xl p-3" open>
          <summary className="text-sm font-bold text-slate-700 cursor-pointer">Quick signature builder (optional) — fill fields, then generate a layout you can keep editing visually</summary>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-2 mt-3">
            {FIELDS.map(([k, label, ph]) => (
              <div key={k}>
                <label className="block text-[11px] font-bold text-slate-500 mb-0.5">{label}</label>
                <input value={f[k] || ''} placeholder={ph} onChange={(e) => set(k, e.target.value)} className="w-full p-2 border border-slate-200 rounded-lg text-xs bg-white" />
              </div>
            ))}
            <div>
              <label className="block text-[11px] font-bold text-slate-500 mb-0.5">Accent color</label>
              <input type="color" value={f.color} onChange={(e) => set('color', e.target.value)} className="h-8 w-full border border-slate-200 rounded-lg bg-white" />
            </div>
            <div>
              <label className="block text-[11px] font-bold text-slate-500 mb-0.5">Font</label>
              <select value={f.font} onChange={(e) => set('font', e.target.value)} className="w-full p-2 border border-slate-200 rounded-lg text-xs bg-white">
                <option value="Arial, sans-serif">Arial</option><option value="Georgia, serif">Georgia</option>
                <option value="Verdana, sans-serif">Verdana</option><option value="'Times New Roman', serif">Times New Roman</option>
              </select>
            </div>
            <div>
              <label className="block text-[11px] font-bold text-slate-500 mb-0.5">Alignment / size</label>
              <div className="flex gap-2">
                <select value={f.align} onChange={(e) => set('align', e.target.value)} className="flex-1 p-2 border border-slate-200 rounded-lg text-xs bg-white">
                  <option value="left">Left</option><option value="center">Center</option><option value="right">Right</option>
                </select>
                <input type="number" min={10} max={20} value={f.size} onChange={(e) => set('size', e.target.value)} className="w-16 p-2 border border-slate-200 rounded-lg text-xs bg-white" />
              </div>
            </div>
          </div>
          <button
            id="generate-signature-btn"
            onClick={() => editorRef.current?.loadHtml(buildSignatureHtml(f))}
            className="mt-3 px-4 py-2 text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white rounded-lg"
          >Generate layout in editor (replaces canvas)</button>
        </details>
      )}
      {...props}
    />
  );
};

export default SignatureTemplateEditor;
