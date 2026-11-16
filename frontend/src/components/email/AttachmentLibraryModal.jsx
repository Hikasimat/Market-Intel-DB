import React from 'react';
import { FolderOpen, X } from 'lucide-react';
import AttachmentLibraryManager from './AttachmentLibraryManager';

export default function AttachmentLibraryModal({
  isOpen,
  onClose,
  onAttachFiles,
  existingAttachments = [],
  maxAllowedToAttach = 5,
}) {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-slate-900/60 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div 
        className="bg-white rounded-2xl shadow-2xl border border-slate-200/80 w-full max-w-xl overflow-hidden flex flex-col max-h-[90vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4.5 border-b border-slate-100 bg-linear-to-r from-slate-50 via-white to-indigo-50/30">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-100 text-indigo-700 flex items-center justify-center shadow-xs">
              <FolderOpen className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-slate-800">Attachments Library</h3>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                Save up to 5 collateral files to attach with 1 click whenever you send emails.
              </p>
            </div>
          </div>
          <button 
            type="button"
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Content */}
        <div className="p-6 overflow-y-auto flex-1">
          <AttachmentLibraryManager
            isModal={true}
            onAttachFiles={onAttachFiles}
            onClose={onClose}
            existingAttachments={existingAttachments}
            maxAllowedToAttach={maxAllowedToAttach}
          />
        </div>
      </div>
    </div>
  );
}
