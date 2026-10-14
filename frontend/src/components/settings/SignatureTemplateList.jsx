import React, { useEffect, useState, useCallback, useMemo } from 'react';
import {
  Plus, Search, Star, Copy, Trash2, Pencil, Loader2,
  LayoutTemplate, PenTool, Filter, Sparkles
} from 'lucide-react';
import { toast } from 'react-toastify';
import { designApi, errorMessage } from '../../services/designApi';

const isSignatureCustom = (item) => {
  const pd = item?.project_data;
  if (!pd) return false;
  // If it has blocks or explicit custom flag or doesn't have standard fields
  if (pd.blocks && Array.isArray(pd.blocks)) return true;
  if (pd.is_custom || pd.kind === 'signature_custom') return true;
  return false;
};

const SignatureTemplateList = ({ onCreate, onCreateCustom, onEdit, refreshKey }) => {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [filterType, setFilterType] = useState('all'); // 'all' | 'custom' | 'standard'
  const [confirmDelete, setConfirmDelete] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await designApi.list('signature', search));
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
    if (filterType === 'custom') {
      return items.filter(isSignatureCustom);
    }
    if (filterType === 'standard') {
      return items.filter((it) => !isSignatureCustom(it));
    }
    return items;
  }, [items, filterType]);

  const customCount = useMemo(() => items.filter(isSignatureCustom).length, [items]);
  const standardCount = useMemo(() => items.filter((it) => !isSignatureCustom(it)).length, [items]);

  return (
    <div className="space-y-4">
      {/* Top Bar: Search, Custom Filter, and Action Buttons */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          {/* Search Box */}
          <div className="relative">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              id="signature-search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search signatures..."
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
              id="filter-custom-templates-btn"
              onClick={() => setFilterType('custom')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition cursor-pointer ${
                filterType === 'custom'
                  ? 'bg-white text-blue-700 shadow-xs font-bold'
                  : 'hover:text-slate-900'
              }`}
            >
              <LayoutTemplate className="w-3.5 h-3.5 text-blue-600" />
              <span>Custom Templates ({customCount})</span>
            </button>
            <button
              type="button"
              onClick={() => setFilterType('standard')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg transition cursor-pointer ${
                filterType === 'standard'
                  ? 'bg-white text-indigo-700 shadow-xs font-bold'
                  : 'hover:text-slate-900'
              }`}
            >
              <PenTool className="w-3.5 h-3.5 text-indigo-600" />
              <span>Standard Signatures ({standardCount})</span>
            </button>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2">
          {/* Custom Template Workspace Button */}
          <button
            type="button"
            id="new-custom-signature-btn"
            onClick={onCreateCustom || onCreate}
            className="px-3.5 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 text-white text-sm font-bold rounded-xl flex items-center gap-2 shadow-xs transition cursor-pointer"
            title="Open the exact email template creation workspace for designing a signature"
          >
            <LayoutTemplate className="w-4 h-4" />
            <span>+ Custom Template</span>
          </button>

          {/* Standard Form Wizard Button */}
          <button
            type="button"
            id="new-signature-btn"
            onClick={onCreate}
            className="px-3.5 py-2 bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 text-sm font-bold rounded-xl flex items-center gap-2 shadow-xs transition cursor-pointer"
            title="Create standard signature with form wizard"
          >
            <Plus className="w-4 h-4 text-slate-500" />
            <span>New Signature</span>
          </button>
        </div>
      </div>

      {/* Signatures Table */}
      <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-2xs">
        {loading ? (
          <div className="p-10 flex justify-center text-slate-400">
            <Loader2 className="w-5 h-5 animate-spin" />
          </div>
        ) : filteredItems.length === 0 ? (
          <div className="p-10 text-center text-sm text-slate-500 space-y-2">
            <div>
              {filterType === 'custom'
                ? 'No custom template signatures yet.'
                : filterType === 'standard'
                ? 'No standard signatures yet.'
                : 'No signatures found.'}
            </div>
            <div className="flex justify-center gap-2 pt-2">
              <button
                type="button"
                onClick={onCreateCustom || onCreate}
                className="px-3 py-1.5 text-xs font-bold bg-blue-50 text-blue-700 border border-blue-200 rounded-lg hover:bg-blue-100 transition"
              >
                + Create Custom Template
              </button>
              <button
                type="button"
                onClick={onCreate}
                className="px-3 py-1.5 text-xs font-bold bg-slate-50 text-slate-700 border border-slate-200 rounded-lg hover:bg-slate-100 transition"
              >
                + Create Standard Signature
              </button>
            </div>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500 border-b border-slate-100">
              <tr>
                <th className="text-left px-4 py-3">Signature Name</th>
                <th className="text-left px-4 py-3">Format / Builder</th>
                <th className="text-left px-4 py-3">Last updated</th>
                <th className="text-left px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredItems.map((it) => {
                const isCustom = isSignatureCustom(it);
                return (
                  <tr key={it.id} className="hover:bg-slate-50/80 transition">
                    <td className="px-4 py-3">
                      <div className="font-bold text-slate-800">{it.name}</div>
                      {it.description && <div className="text-xs text-slate-500">{it.description}</div>}
                    </td>
                    <td className="px-4 py-3">
                      {isCustom ? (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-bold bg-blue-50 text-blue-700 border border-blue-200">
                          <LayoutTemplate className="w-3 h-3 text-blue-500" />
                          Custom Template
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                          <PenTool className="w-3 h-3 text-slate-500" />
                          Standard
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-slate-600 text-xs">
                      {new Date(it.updated_at).toLocaleString()}
                    </td>
                    <td className="px-4 py-3">
                      {it.is_default ? (
                        <span className="px-2.5 py-0.5 text-[11px] font-bold rounded-full bg-amber-100 text-amber-700 border border-amber-200">
                          Default
                        </span>
                      ) : (
                        <span className="text-slate-400 text-xs">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex justify-end gap-1">
                        <button
                          title="Edit"
                          onClick={() => onEdit(it.id, isCustom)}
                          className="p-2 rounded-lg hover:bg-blue-50 text-blue-600 transition"
                        >
                          <Pencil className="w-4 h-4" />
                        </button>
                        {!it.is_default && (
                          <button
                            title="Set as default"
                            onClick={() => run(() => designApi.setDefault('signature', it.id), 'Default updated')}
                            className="p-2 rounded-lg hover:bg-amber-50 text-amber-600 transition"
                          >
                            <Star className="w-4 h-4" />
                          </button>
                        )}
                        <button
                          title="Duplicate"
                          onClick={() => run(() => designApi.duplicate('signature', it.id), 'Signature duplicated')}
                          className="p-2 rounded-lg hover:bg-slate-100 text-slate-600 transition"
                        >
                          <Copy className="w-4 h-4" />
                        </button>
                        <button
                          title="Delete"
                          onClick={() => setConfirmDelete(it)}
                          className="p-2 rounded-lg hover:bg-rose-50 text-rose-600 transition"
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
        <div className="fixed inset-0 z-[100] bg-slate-900/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-sm p-5 space-y-4">
            <h3 className="font-bold text-slate-800">Delete signature?</h3>
            <p className="text-sm text-slate-600">“{confirmDelete.name}” will be permanently removed.</p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setConfirmDelete(null)}
                className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                id="confirm-delete-btn"
                onClick={() => {
                  const id = confirmDelete.id;
                  setConfirmDelete(null);
                  run(() => designApi.remove('signature', id), 'Signature deleted');
                }}
                className="px-4 py-2 text-xs font-bold bg-rose-600 text-white hover:bg-rose-700 rounded-lg"
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

export default SignatureTemplateList;
