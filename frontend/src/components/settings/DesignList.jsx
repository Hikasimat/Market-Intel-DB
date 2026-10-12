import React, { useEffect, useState, useCallback } from 'react';
import { Plus, Search, Star, Copy, Trash2, Pencil, Loader2 } from 'lucide-react';
import { toast } from 'react-toastify';
import { designApi, errorMessage } from '../../services/designApi';

/** Generic list used by EmailTemplateList and SignatureTemplateList. */
const DesignList = ({ kind, title, noun, onCreate, onEdit, refreshKey }) => {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [confirmDelete, setConfirmDelete] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await designApi.list(kind, search));
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }, [kind, search]);

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

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="relative">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            id={`${kind}-search`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={`Search ${title.toLowerCase()}...`}
            className="pl-9 pr-3 py-2 text-sm border border-slate-200 rounded-xl bg-white w-72 focus:outline-none focus:ring-2 focus:ring-blue-100"
          />
        </div>
        <button
          id={`new-${kind}-btn`}
          onClick={onCreate}
          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-bold rounded-xl flex items-center gap-2"
        >
          <Plus className="w-4 h-4" /> New {noun}
        </button>
      </div>

      <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
        {loading ? (
          <div className="p-10 flex justify-center text-slate-400"><Loader2 className="w-5 h-5 animate-spin" /></div>
        ) : items.length === 0 ? (
          <div className="p-10 text-center text-sm text-slate-500">No {title.toLowerCase()} yet. Create your first one.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-xs uppercase text-slate-500">
              <tr>
                <th className="text-left px-4 py-3">Name</th>
                <th className="text-left px-4 py-3">Last updated</th>
                <th className="text-left px-4 py-3">Status</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((it) => (
                <tr key={it.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <div className="font-bold text-slate-800">{it.name}</div>
                    {it.description && <div className="text-xs text-slate-500">{it.description}</div>}
                  </td>
                  <td className="px-4 py-3 text-slate-600">{new Date(it.updated_at).toLocaleString()}</td>
                  <td className="px-4 py-3">
                    {it.is_default ? (
                      <span className="px-2 py-0.5 text-[11px] font-bold rounded-full bg-amber-100 text-amber-700">Default</span>
                    ) : (
                      <span className="text-slate-400 text-xs">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-1">
                      <button title="Edit" onClick={() => onEdit(it.id)} className="p-2 rounded-lg hover:bg-blue-50 text-blue-600"><Pencil className="w-4 h-4" /></button>
                      {!it.is_default && (
                        <button title="Set as default" onClick={() => run(() => designApi.setDefault(kind, it.id), 'Default updated')} className="p-2 rounded-lg hover:bg-amber-50 text-amber-600"><Star className="w-4 h-4" /></button>
                      )}
                      <button title="Duplicate" onClick={() => run(() => designApi.duplicate(kind, it.id), `${noun} duplicated`)} className="p-2 rounded-lg hover:bg-slate-100 text-slate-600"><Copy className="w-4 h-4" /></button>
                      <button title="Delete" onClick={() => setConfirmDelete(it)} className="p-2 rounded-lg hover:bg-rose-50 text-rose-600"><Trash2 className="w-4 h-4" /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {confirmDelete && (
        <div className="fixed inset-0 z-[100] bg-slate-900/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-sm p-5 space-y-4">
            <h3 className="font-bold text-slate-800">Delete {noun.toLowerCase()}?</h3>
            <p className="text-sm text-slate-600">“{confirmDelete.name}” will be permanently removed.</p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setConfirmDelete(null)} className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded-lg">Cancel</button>
              <button
                id="confirm-delete-btn"
                onClick={() => { const id = confirmDelete.id; setConfirmDelete(null); run(() => designApi.remove(kind, id), `${noun} deleted`); }}
                className="px-4 py-2 text-xs font-bold bg-rose-600 text-white hover:bg-rose-700 rounded-lg"
              >Delete</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default DesignList;
