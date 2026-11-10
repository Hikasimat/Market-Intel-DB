import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  Plus, Search, Star, Copy, Trash2, Pencil, Loader2,
  LayoutTemplate, FileText
} from 'lucide-react';
import { toast } from 'react-toastify';
import { designApi, errorMessage } from '../../services/designApi';

const isTemplateHtml = (item) => {
  const pd = item?.project_data;
  if (pd && pd.is_plain_text) return false;
  return true;
};

const EmailTemplateList = ({ onCreate, onCreateHtml, onEdit, refreshKey }) => {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('all'); // 'all' | 'html' | 'plain'
  const [confirmDelete, setConfirmDelete] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await designApi.list('email', search));
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    const t = setTimeout(load, 250);
    return () => clearTimeout(t);
  }, [load, refreshKey]);

  const run = async (fn, okMsg) => {
    try {
      await fn();
      toast.success(okMsg);
      load();
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  const filteredItems = useMemo(() => {
    if (filterType === 'html') {
      return items.filter(isTemplateHtml);
    }
    if (filterType === 'plain') {
      return items.filter((it) => !isTemplateHtml(it));
    }
    return items;
  }, [items, filterType]);

  const htmlCount = useMemo(() => items.filter(isTemplateHtml).length, [items]);
  const plainCount = useMemo(() => items.filter((it) => !isTemplateHtml(it)).length, [items]);

  return (
    <div className="space-y-4">
      {/* Top Bar: Search, Type Filters, and Action Buttons */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {/* Search Box */}
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              id="email-template-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search email templates..."
              className="pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-xl bg-white w-64 focus:outline-none focus:ring-2 focus:ring-blue-100"
            />
          </div>

          {/* Filter Pills */}
          <div className="flex items-center bg-slate-100 p-1 rounded-xl border border-slate-200 text-xs font-semibold text-slate-600">
            <button
              type="button"
              onClick={() => setFilterType('all')}
              className={`px-3 py-1.5 rounded-lg transition cursor-pointer ${
                filterType === 'all'
                  ? 'bg-white text-slate-900 shadow-xs font-bold'
                  : 'hover:text-slate-900'
              }`}
            >
              All ({items.length})
            </button>
            <button
              type="button"
              onClick={() => setFilterType('html')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition cursor-pointer ${
                filterType === 'html'
                  ? 'bg-white text-blue-700 shadow-xs font-bold'
                  : 'hover:text-slate-900'
              }`}
            >
              <LayoutTemplate className="w-3.5 h-3.5 text-blue-600" />
              <span>HTML Templates ({htmlCount})</span>
            </button>
            <button
              type="button"
              onClick={() => setFilterType('plain')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition cursor-pointer ${
                filterType === 'plain'
                  ? 'bg-white text-slate-900 shadow-xs font-bold'
                  : 'hover:text-slate-900'
              }`}
            >
              <FileText className="w-3.5 h-3.5 text-slate-600" />
              <span>Plain-Text ({plainCount})</span>
            </button>
          </div>
        </div>

        {/* Action Buttons: Both Custom HTML & Plain-Text Options */}
        <div className="flex items-center gap-2">
          {/* Custom HTML Template Creation Button */}
          <button
            type="button"
            id="new-html-template-btn"
            onClick={onCreateHtml || onCreate}
            className="px-3.5 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white text-sm font-bold rounded-xl flex items-center gap-2 shadow-xs transition cursor-pointer"
            title="Create a customized HTML template using the visual block builder"
          >
            <LayoutTemplate className="w-4 h-4" />
            <span>+ Customize HTML Template</span>
          </button>

          {/* Plain-Text Template Creation Button */}
          <button
            type="button"
            id="new-plain-template-btn"
            onClick={onCreate}
            className="px-3.5 py-2 bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 text-sm font-bold rounded-xl flex items-center gap-2 shadow-xs transition cursor-pointer"
            title="Create a plain-text email template"
          >
            <FileText className="w-4 h-4 text-slate-500" />
            <span>+ Plain-Text Template</span>
          </button>
        </div>
      </div>

      {/* Templates Table */}
      <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-2xs">
        {loading ? (
          <div className="p-10 flex justify-center text-slate-400">
            <Loader2 className="w-5 h-5 animate-spin" />
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="p-10 text-center text-sm text-slate-500 space-y-2">
            <div>
              {filterType === 'html'
                ? 'No HTML templates yet.'
                : filterType === 'plain'
                ? 'No plain-text templates yet.'
                : 'No email templates found.'}
            </div>
            <div className="flex justify-center gap-2 pt-2">
              <button
                type="button"
                onClick={onCreateHtml || onCreate}
                className="px-3 py-1.5 text-xs font-bold bg-blue-50 text-blue-700 border border-blue-200 rounded-lg hover:bg-blue-100 transition"
              >
                + Create HTML Template
              </button>
              <button
                type="button"
                onClick={onCreate}
                className="px-3 py-1.5 text-xs font-bold bg-slate-50 text-slate-700 border border-slate-200 rounded-lg hover:bg-slate-100 transition"
              >
                + Create Plain-Text Template
              </button>
            </div>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="text-left px-4 py-3">Template</th>
                <th className="text-left px-4 py-3">Format</th>
                <th className="text-left px-4 py-3">Subject</th>
                <th className="text-left px-4 py-3">Last Updated</th>
                <th className="text-left px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredItems.map((it) => {
                const isHtml = isTemplateHtml(it);
                return (
                  <tr key={it.id} className="hover:bg-slate-50/70 transition">
                    <td className="px-4 py-3">
                      <div className="font-bold text-slate-800">{it.name}</div>
                      {it.description && <div className="text-xs text-slate-500">{it.description}</div>}
                    </td>
                    <td className="px-4 py-3">
                      {isHtml ? (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold rounded-full bg-blue-100 text-blue-800">
                          <LayoutTemplate className="w-3 h-3" /> HTML
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold rounded-full bg-slate-100 text-slate-700">
                          <FileText className="w-3 h-3" /> Plain Text
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-600 max-w-[200px] truncate">
                      {it.subject || <span className="text-slate-400 italic">No subject</span>}
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">
                      {new Date(it.updated_at).toLocaleDateString()}
                    </td>
                    <td className="px-4 py-3">
                      {it.is_default ? (
                        <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-amber-100 text-amber-800">
                          Default
                        </span>
                      ) : (
                        <span className="text-slate-400 text-xs">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-1">
                        <button
                          title={`Edit ${isHtml ? 'HTML' : 'Plain-Text'} Template`}
                          onClick={() => onEdit(it.id, isHtml)}
                          className="p-1.5 rounded-lg hover:bg-blue-50 text-blue-600 transition"
                        >
                          <Pencil className="w-4 h-4" />
                        </button>
                        {!it.is_default && (
                          <button
                            title="Set as default"
                            onClick={() => run(() => designApi.setDefault('email', it.id), 'Default template updated')}
                            className="p-1.5 rounded-lg hover:bg-amber-50 text-amber-600 transition"
                          >
                            <Star className="w-4 h-4" />
                          </button>
                        )}
                        <button
                          title="Duplicate"
                          onClick={() => run(() => designApi.duplicate('email', it.id), 'Template duplicated')}
                          className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-600 transition"
                        >
                          <Copy className="w-4 h-4" />
                        </button>
                        <button
                          title="Delete"
                          onClick={() => setConfirmDelete(it)}
                          className="p-1.5 rounded-lg hover:bg-rose-50 text-rose-600 transition"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Delete Confirmation Modal */}
      {confirmDelete && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-2xl max-w-sm w-full p-5 space-y-4 shadow-xl border border-slate-200">
            <h3 className="font-bold text-slate-900 text-base">Delete Template?</h3>
            <p className="text-xs text-slate-600">
              Are you sure you want to delete <strong className="text-slate-800">{confirmDelete.name}</strong>? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setConfirmDelete(null)}
                className="px-3.5 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded-xl transition"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => {
                  const it = confirmDelete;
                  setConfirmDelete(null);
                  run(() => designApi.remove('email', it.id), 'Template deleted');
                }}
                className="px-3.5 py-2 text-xs font-bold bg-rose-600 hover:bg-rose-700 text-white rounded-xl transition"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default EmailTemplateList;
