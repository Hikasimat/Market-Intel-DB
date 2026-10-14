import React, { useEffect, useState } from 'react';
import SignatureBuilderModal, { buildSignatureHtml } from './SignatureBuilderModal';
import DesignEditor from './DesignEditor';
import { designApi } from '../../services/designApi';
import { Loader2, LayoutTemplate, PenTool } from 'lucide-react';

export { buildSignatureHtml };


/**
 * Flexible signature editor supporting both:
 * 1. The visual drag-and-drop custom template builder workspace (DesignEditor)
 * 2. The standard form wizard (SignatureBuilderModal)
 */
const SignatureTemplateEditor = ({ id, isCustom, onClose, onSaved }) => {
  const [mode, setMode] = useState(isCustom ? 'custom' : 'standard');
  const [loading, setLoading] = useState(!!id && isCustom === undefined);

  useEffect(() => {
    if (isCustom !== undefined) {
      setMode(isCustom ? 'custom' : 'standard');
      return;
    }
    if (id) {
      designApi.get('signature', id)
        .then((data) => {
          const pd = data?.project_data;
          const hasBlocks = pd && Array.isArray(pd.blocks) && pd.blocks.length > 0;
          const customFlag = pd && (pd.is_custom || pd.kind === 'signature_custom');
          setMode(hasBlocks || customFlag ? 'custom' : 'standard');
        })
        .catch(() => {
          setMode('standard');
        })
        .finally(() => {
          setLoading(false);
        });
    }
  }, [id, isCustom]);

  if (loading) {
    return (
      <div className="p-16 flex items-center justify-center text-slate-400">
        <Loader2 className="w-6 h-6 animate-spin text-blue-600" />
      </div>
    );
  }

  if (mode === 'custom') {
    return (
      <div className="space-y-3">
        {/* Workspace Mode Bar */}
        <div className="flex items-center justify-between bg-blue-50/70 border border-blue-200 px-4 py-2 rounded-xl text-xs">
          <div className="flex items-center gap-2 font-bold text-blue-900">
            <LayoutTemplate className="w-4 h-4 text-blue-600" />
            <span>Custom Template Workspace (Visual Signature Builder)</span>
          </div>
          <button
            type="button"
            onClick={() => setMode('standard')}
            className="text-blue-700 hover:text-blue-900 font-semibold underline flex items-center gap-1 cursor-pointer"
          >
            <PenTool className="w-3.5 h-3.5" />
            <span>Switch to Standard Form Wizard</span>
          </button>
        </div>

        {/* Exact Email Template Workspace */}
        <DesignEditor
          kind="signature"
          id={id}
          noun="Signature"
          starterHtml={null}
          emptyCanvas={true}
          withDescription={true}
          withSubject={false}
          onClose={onClose}
          onSaved={onSaved}
        />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Workspace Mode Bar for new signatures */}
      {!id && (
        <div className="flex items-center justify-between bg-slate-100 border border-slate-200 px-4 py-2 rounded-xl text-xs">
          <div className="flex items-center gap-2 font-bold text-slate-800">
            <PenTool className="w-4 h-4 text-slate-600" />
            <span>Standard Form Wizard</span>
          </div>
          <button
            type="button"
            onClick={() => setMode('custom')}
            className="text-blue-600 hover:text-blue-800 font-bold underline flex items-center gap-1 cursor-pointer"
          >
            <LayoutTemplate className="w-3.5 h-3.5" />
            <span>Switch to Custom Template Builder</span>
          </button>
        </div>
      )}

      <SignatureBuilderModal
        initialId={id}
        onClose={onClose}
        onSaved={onSaved}
      />
    </div>
  );
};

export default SignatureTemplateEditor;
