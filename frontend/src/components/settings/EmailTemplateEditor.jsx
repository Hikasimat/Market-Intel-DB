import React, { useEffect, useState } from 'react';
import DesignEditor from './DesignEditor';
import PlainTextTemplateEditor from './PlainTextTemplateEditor';
import { designApi } from '../../services/designApi';
import { Loader2, LayoutTemplate, FileText } from 'lucide-react';

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

/**
 * Flexible Email Template Editor supporting BOTH:
 * 1. The previous customized HTML visual template builder (DesignEditor)
 * 2. Plain-Text template creation (PlainTextTemplateEditor)
 */
const EmailTemplateEditor = ({ id, isHtml, onClose, onSaved }) => {
  const [mode, setMode] = useState(isHtml ? 'html' : (isHtml === false ? 'plain' : 'html'));
  const [loading, setLoading] = useState(!!id && isHtml === undefined);

  useEffect(() => {
    if (isHtml !== undefined) {
      setMode(isHtml ? 'html' : 'plain');
      return;
    }
    if (id) {
      designApi.get('email', id)
        .then((data) => {
          const pd = data?.project_data;
          const isPlainText = pd && pd.is_plain_text;
          setMode(isPlainText ? 'plain' : 'html');
        })
        .catch(() => {
          setMode('html');
        })
        .finally(() => {
          setLoading(false);
        });
    }
  }, [id, isHtml]);

  if (loading) {
    return (
      <div className="p-16 flex items-center justify-center text-slate-400">
        <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
      </div>
    );
  }

  if (mode === 'html') {
    return (
      <div className="space-y-3">
        {/* Mode Switcher Bar */}
        <div className="flex items-center justify-between bg-blue-50/70 border border-blue-200 px-4 py-2 rounded-xl text-xs">
          <div className="flex items-center gap-2 font-bold text-blue-900">
            <LayoutTemplate className="w-4 h-4 text-blue-600" />
            <span>Customize Template Workspace (Visual HTML Template Builder)</span>
          </div>
          <button
            type="button"
            onClick={() => setMode('plain')}
            className="text-blue-700 hover:text-blue-900 font-semibold underline flex items-center gap-1.5 cursor-pointer"
          >
            <FileText className="w-3.5 h-3.5" />
            <span>Switch to Plain-Text Template</span>
          </button>
        </div>

        {/* Previous Customized HTML Template Workspace */}
        <DesignEditor
          kind="email"
          id={id}
          noun="Template"
          starterHtml={STARTER}
          withSubject
          withDescription
          onClose={onClose}
          onSaved={onSaved}
        />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Mode Switcher Bar */}
      <div className="flex items-center justify-between bg-slate-100 border border-slate-200 px-4 py-2 rounded-xl text-xs">
        <div className="flex items-center gap-2 font-bold text-slate-800">
          <FileText className="w-4 h-4 text-slate-600" />
          <span>Plain-Text Email Template</span>
        </div>
        <button
          type="button"
          onClick={() => setMode('html')}
          className="text-blue-600 hover:text-blue-800 font-bold underline flex items-center gap-1.5 cursor-pointer"
        >
          <LayoutTemplate className="w-3.5 h-3.5" />
          <span>Switch to Customize HTML Template Builder</span>
        </button>
      </div>

      {/* Plain-Text Template Editor */}
      <PlainTextTemplateEditor
        id={id}
        onClose={onClose}
        onSaved={onSaved}
      />
    </div>
  );
};

export default EmailTemplateEditor;
