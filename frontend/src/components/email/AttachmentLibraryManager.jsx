import React, { useState, useEffect, useRef } from 'react';
import { 
  Paperclip, 
  Upload, 
  Trash2, 
  Download, 
  FileText, 
  FileSpreadsheet, 
  FileImage, 
  FileCode, 
  File as FileIcon, 
  X, 
  Check, 
  AlertCircle, 
  Loader2, 
  Plus, 
  FolderOpen,
  CheckCircle2,
  HardDrive
} from 'lucide-react';
import api from '../../services/api';
import { toast } from 'react-toastify';

export const MAX_LIBRARY_FILES = 5;
export const MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024; // 10MB
export const BLOCKED_EXTENSIONS = ['exe', 'bat', 'cmd', 'js', 'ps1', 'vbs', 'scr', 'sh', 'com', 'msi', 'jar'];

export default function AttachmentLibraryManager({
  onAttachFiles,
  onClose,
  existingAttachments = [],
  maxAllowedToAttach = 5,
  isModal = false,
}) {
  const [items, setItems] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isAttaching, setIsAttaching] = useState(false);
  const [deletingId, setDeletingId] = useState(null);
  const [selectedItemIds, setSelectedItemIds] = useState(new Set());
  const [uploadError, setUploadError] = useState('');
  const fileInputRef = useRef(null);

  useEffect(() => {
    fetchLibraryItems();
    setSelectedItemIds(new Set());
    setUploadError('');
  }, []);

  const fetchLibraryItems = async () => {
    setIsLoading(true);
    try {
      const res = await api.get('/auth/attachment-library/');
      const data = Array.isArray(res.data) ? res.data : (res.data?.results || []);
      setItems(data);
    } catch (err) {
      console.error('Failed to load attachment library:', err);
      toast.error('Could not load attachment library.');
    } finally {
      setIsLoading(false);
    }
  };

  const formatFileSize = (bytes) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const getFileIcon = (filename = '', contentType = '') => {
    const ext = filename.split('.').pop()?.toLowerCase();
    if (ext === 'pdf') {
      return <FileText className="w-5 h-5 text-rose-500" />;
    }
    if (['doc', 'docx', 'txt', 'rtf'].includes(ext)) {
      return <FileText className="w-5 h-5 text-blue-500" />;
    }
    if (['xls', 'xlsx', 'csv'].includes(ext)) {
      return <FileSpreadsheet className="w-5 h-5 text-emerald-500" />;
    }
    if (['png', 'jpg', 'jpeg', 'webp', 'gif', 'svg'].includes(ext) || contentType.startsWith('image/')) {
      return <FileImage className="w-5 h-5 text-purple-500" />;
    }
    if (['json', 'xml', 'html', 'css'].includes(ext)) {
      return <FileCode className="w-5 h-5 text-amber-500" />;
    }
    return <FileIcon className="w-5 h-5 text-slate-500" />;
  };

  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploadError('');

    if (items.length >= MAX_LIBRARY_FILES) {
      setUploadError(`You can have at most ${MAX_LIBRARY_FILES} files in your Attachment Library.`);
      e.target.value = '';
      return;
    }

    if (file.size > MAX_FILE_SIZE_BYTES) {
      setUploadError(`File ${file.name} exceeds the 10MB limit.`);
      e.target.value = '';
      return;
    }

    const ext = file.name.split('.').pop()?.toLowerCase();
    if (BLOCKED_EXTENSIONS.includes(ext)) {
      setUploadError(`File type .${ext} is not allowed for email attachments.`);
      e.target.value = '';
      return;
    }

    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    formData.append('name', file.name);

    try {
      const res = await api.post('/auth/attachment-library/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      toast.success(`"${file.name}" added to Attachment Library!`);
      setItems(prev => [res.data, ...prev]);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (err) {
      console.error('Failed to upload file to library:', err);
      const errMsg = err.response?.data?.error || 'Failed to upload file to library.';
      setUploadError(errMsg);
      toast.error(errMsg);
    } finally {
      setIsUploading(false);
    }
  };

  const handleDeleteItem = async (item, e) => {
    e.stopPropagation();
    if (!window.confirm(`Remove "${item.name}" from your Attachment Library?`)) {
      return;
    }

    setDeletingId(item.id);
    try {
      await api.delete(`/auth/attachment-library/${item.id}/`);
      toast.success(`Removed "${item.name}" from Library`);
      setItems(prev => prev.filter(i => i.id !== item.id));
      setSelectedItemIds(prev => {
        const next = new Set(prev);
        next.delete(item.id);
        return next;
      });
    } catch (err) {
      console.error('Failed to delete library item:', err);
      toast.error('Failed to remove file from library.');
    } finally {
      setDeletingId(null);
    }
  };

  const handleDownloadItem = async (item, e) => {
    e.stopPropagation();
    try {
      const res = await api.get(`/auth/attachment-library/${item.id}/download/`, {
        responseType: 'blob',
      });
      const url = window.URL.createObjectURL(new Blob([res.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', item.name);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('Failed to download library file:', err);
      toast.error('Failed to download file.');
    }
  };

  const isAlreadyAttachedInEmail = (item) => {
    return existingAttachments.some(
      att => att.name === item.name && Math.abs(att.size - item.file_size) < 100
    );
  };

  const toggleSelect = (item) => {
    if (isAlreadyAttachedInEmail(item)) return;
    setSelectedItemIds(prev => {
      const next = new Set(prev);
      if (next.has(item.id)) {
        next.delete(item.id);
      } else {
        const currentSelectedCount = next.size;
        const availableSlotsInEmail = maxAllowedToAttach - existingAttachments.length;
        if (currentSelectedCount >= availableSlotsInEmail) {
          toast.warning(`Email can have at most ${maxAllowedToAttach} attachments total (${existingAttachments.length} already attached).`);
          return prev;
        }
        next.add(item.id);
      }
      return next;
    });
  };

  const handleAttachSingle = async (item, e) => {
    e.stopPropagation();
    if (isAlreadyAttachedInEmail(item)) {
      toast.info(`"${item.name}" is already attached to this email.`);
      return;
    }
    const availableSlots = maxAllowedToAttach - existingAttachments.length;
    if (availableSlots <= 0) {
      toast.warning(`Maximum of ${maxAllowedToAttach} attachments already reached in email.`);
      return;
    }
    await processAndAttachItems([item]);
  };

  const handleAttachSelected = async () => {
    if (selectedItemIds.size === 0) return;
    const selectedItems = items.filter(i => selectedItemIds.has(i.id));
    await processAndAttachItems(selectedItems);
  };

  const processAndAttachItems = async (itemsToAttach) => {
    if (!onAttachFiles) return;
    setIsAttaching(true);
    const preparedFiles = [];

    try {
      for (const item of itemsToAttach) {
        const res = await api.get(`/auth/attachment-library/${item.id}/download/`, {
          responseType: 'blob',
        });
        const blob = res.data;
        const fileObj = new File([blob], item.name, {
          type: item.content_type || blob.type || 'application/octet-stream',
          lastModified: Date.now(),
        });
        preparedFiles.push(fileObj);
      }

      onAttachFiles(preparedFiles);
      toast.success(`Attached ${preparedFiles.length} file(s) from Library!`);
      if (onClose) onClose();
    } catch (err) {
      console.error('Failed to prepare library attachments:', err);
      toast.error('Failed to attach files from library.');
    } finally {
      setIsAttaching(false);
    }
  };

  const isComposerMode = typeof onAttachFiles === 'function';
  const remainingSlots = MAX_LIBRARY_FILES - items.length;

  return (
    <div className={`space-y-5 ${isModal ? '' : 'p-6 bg-white border border-slate-200/80 rounded-2xl shadow-xs'}`}>
      {/* Header Info (for inline settings tab) */}
      {!isModal && (
        <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-100 gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-100 text-indigo-700 flex items-center justify-center shadow-xs">
              <FolderOpen className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-base font-bold text-slate-800">Email Attachments Library</h3>
                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold ${
                  items.length >= MAX_LIBRARY_FILES 
                    ? 'bg-amber-100 text-amber-800 border border-amber-200' 
                    : 'bg-indigo-50 text-indigo-700 border border-indigo-200/80'
                }`}>
                  {items.length} / {MAX_LIBRARY_FILES} Files
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                Save up to 5 frequently sent collateral files. Whenever you compose or send an email, you can attach them with one click.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Error Message */}
      {uploadError && (
        <div className="flex items-center gap-2 p-3 bg-rose-50 border border-rose-200 text-rose-700 rounded-xl text-xs font-semibold">
          <AlertCircle className="w-4 h-4 shrink-0 text-rose-600" />
          <span>{uploadError}</span>
        </div>
      )}

      {/* Files List */}
      <div>
        <div className="flex items-center justify-between mb-2.5">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Stored Library Files ({items.length} / {MAX_LIBRARY_FILES})
          </span>
          {isComposerMode && items.length > 0 && (
            <span className="text-[11px] text-slate-400">
              Click to select or click &quot;Attach&quot;
            </span>
          )}
        </div>

        {isLoading ? (
          <div className="py-12 flex flex-col items-center justify-center text-slate-400 gap-2">
            <Loader2 className="w-6 h-6 animate-spin text-indigo-600" />
            <span className="text-xs font-medium">Loading library files...</span>
          </div>
        ) : items.length === 0 ? (
          <div className="py-10 border-2 border-dashed border-slate-200 rounded-2xl flex flex-col items-center justify-center text-center p-6 bg-slate-50/50">
            <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center text-slate-400 mb-3">
              <Paperclip className="w-6 h-6" />
            </div>
            <h4 className="text-sm font-bold text-slate-700">No files in your library</h4>
            <p className="text-xs text-slate-500 max-w-sm mt-1">
              Upload up to 5 collateral files (proposals, brochures, company decks) below. You can easily attach them to any outgoing email.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {items.map((item) => {
              const isSelected = selectedItemIds.has(item.id);
              const isAttached = isAlreadyAttachedInEmail(item);
              const isDeleting = deletingId === item.id;

              return (
                <div
                  key={item.id}
                  onClick={() => isComposerMode && !isAttached && toggleSelect(item)}
                  className={`group relative flex items-center justify-between p-3 rounded-xl border transition-all ${
                    isAttached
                      ? 'bg-slate-50/80 border-slate-200 opacity-70 cursor-not-allowed'
                      : isSelected
                      ? 'bg-indigo-50/70 border-indigo-300 ring-2 ring-indigo-500/20 shadow-xs cursor-pointer'
                      : `bg-white border-slate-200 hover:border-slate-300 hover:shadow-xs ${isComposerMode ? 'cursor-pointer' : ''}`
                  }`}
                >
                  <div className="flex items-center gap-3 min-w-0 pr-3">
                    {isComposerMode && (
                      <div className="shrink-0">
                        {isAttached ? (
                          <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                        ) : (
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => toggleSelect(item)}
                            onClick={(e) => e.stopPropagation()}
                            className="w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500 cursor-pointer"
                          />
                        )}
                      </div>
                    )}

                    <div className="w-9 h-9 rounded-lg bg-slate-100 flex items-center justify-center shrink-0">
                      {getFileIcon(item.name, item.content_type)}
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold text-slate-800 truncate" title={item.name}>
                          {item.name}
                        </span>
                        {isAttached && (
                          <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 text-[10px] font-bold shrink-0">
                            Attached in Email
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 text-[11px] text-slate-400 mt-0.5">
                        <span>{formatFileSize(item.file_size)}</span>
                        <span>•</span>
                        <span>{new Date(item.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1.5 shrink-0" onClick={(e) => e.stopPropagation()}>
                    {isComposerMode && !isAttached && (
                      <button
                        type="button"
                        onClick={(e) => handleAttachSingle(item, e)}
                        disabled={isAttaching}
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded-lg text-xs font-bold transition border border-indigo-200/80 cursor-pointer"
                        title="Attach this file to email"
                      >
                        <Paperclip className="w-3.5 h-3.5" />
                        <span>Attach</span>
                      </button>
                    )}

                    <button
                      type="button"
                      onClick={(e) => handleDownloadItem(item, e)}
                      className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-lg transition"
                      title="Download file"
                    >
                      <Download className="w-4 h-4" />
                    </button>

                    <button
                      type="button"
                      onClick={(e) => handleDeleteItem(item, e)}
                      disabled={isDeleting}
                      className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition"
                      title="Delete from Library"
                    >
                      {isDeleting ? (
                        <Loader2 className="w-4 h-4 animate-spin text-rose-500" />
                      ) : (
                        <Trash2 className="w-4 h-4" />
                      )}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Upload Section */}
      <div className="pt-2 border-t border-slate-100">
        {remainingSlots > 0 ? (
          <div className="p-4 bg-slate-50 border border-slate-200/80 rounded-2xl">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <Plus className="w-4 h-4 text-indigo-600" />
                <span className="text-xs font-bold text-slate-800">Add File to Library</span>
              </div>
              <span className="text-[11px] font-semibold text-slate-400">
                {remainingSlots} of {MAX_LIBRARY_FILES} slots free
              </span>
            </div>

            <p className="text-[11px] text-slate-500 mb-3">
              Upload a standard company document (PDF, Word, Excel, image, max 10MB) to make it readily available across all email workflows.
            </p>

            <div className="flex items-center gap-3">
              <input
                ref={fileInputRef}
                type="file"
                id={`library-file-input-${isModal ? 'modal' : 'settings'}`}
                onChange={handleFileUpload}
                disabled={isUploading}
                className="hidden"
              />
              <label
                htmlFor={`library-file-input-${isModal ? 'modal' : 'settings'}`}
                className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition shadow-xs ${
                  isUploading
                    ? 'bg-slate-200 text-slate-500 cursor-not-allowed'
                    : 'bg-indigo-600 hover:bg-indigo-700 text-white cursor-pointer active:scale-98'
                }`}
              >
                {isUploading ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Uploading file...</span>
                  </>
                ) : (
                  <>
                    <Upload className="w-3.5 h-3.5" />
                    <span>Upload File to Library</span>
                  </>
                )}
              </label>
              <span className="text-[11px] text-slate-400">Max 10MB per file</span>
            </div>
          </div>
        ) : (
          <div className="p-3.5 bg-amber-50/70 border border-amber-200/80 rounded-xl flex items-center gap-2.5">
            <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
            <span className="text-xs font-semibold text-amber-800">
              Library is full (5/5 files). Delete an existing file above to upload a new one.
            </span>
          </div>
        )}
      </div>

      {/* Multi-attach Action Bar for Composer Mode */}
      {isComposerMode && (
        <div className="flex items-center justify-between pt-3 border-t border-slate-100">
          <div className="text-xs text-slate-500 font-medium">
            {selectedItemIds.size > 0 
              ? `${selectedItemIds.size} file(s) selected` 
              : 'Select files with checkboxes to attach together'}
          </div>

          <div className="flex items-center gap-2">
            {onClose && (
              <button
                type="button"
                onClick={onClose}
                disabled={isAttaching}
                className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-200/60 rounded-xl transition cursor-pointer"
              >
                Cancel
              </button>
            )}

            <button
              type="button"
              onClick={handleAttachSelected}
              disabled={selectedItemIds.size === 0 || isAttaching}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold transition shadow-xs cursor-pointer ${
                selectedItemIds.size === 0 || isAttaching
                  ? 'bg-slate-200 text-slate-400 cursor-not-allowed'
                  : 'bg-indigo-600 hover:bg-indigo-700 text-white active:scale-98'
              }`}
            >
              {isAttaching ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  <span>Attaching...</span>
                </>
              ) : (
                <>
                  <Paperclip className="w-3.5 h-3.5" />
                  <span>Attach Selected ({selectedItemIds.size})</span>
                </>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

