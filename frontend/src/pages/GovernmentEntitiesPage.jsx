import React, { useEffect, useState } from 'react';
import { Building2, Plus, Edit2, Search } from 'lucide-react';
import api from '../services/api';
import GovernmentEntityForm from '../components/prospects/GovernmentEntityForm';

const GovernmentEntitiesPage = () => {
  const [entities, setEntities] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isFormOpen, setIsFormOpen] = useState(() => {
    return sessionStorage.getItem(`govEntityFormOpen`) === 'true';
  });
  const [editingEntity, setEditingEntity] = useState(() => {
    const saved = sessionStorage.getItem(`govEntityEditing`);
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch(e) {}
    }
    return null;
  });
  const [searchTerm, setSearchTerm] = useState(() => {
    return sessionStorage.getItem(`govEntitySearch`) || '';
  });

  useEffect(() => {
    sessionStorage.setItem(`govEntitySearch`, searchTerm);
    sessionStorage.setItem(`govEntityFormOpen`, isFormOpen);
    if (editingEntity) {
      sessionStorage.setItem(`govEntityEditing`, JSON.stringify(editingEntity));
    } else {
      sessionStorage.removeItem(`govEntityEditing`);
    }
  }, [searchTerm, isFormOpen, editingEntity]);

  const fetchEntities = async () => {
    setLoading(true);
    try {
      const res = await api.get(`/government-entities/?search=${searchTerm}`);
      setEntities(res.data.results || res.data);
    } catch (err) {
      console.error('Failed to fetch government entities:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchEntities();
  }, [searchTerm]);

  const handleAddClick = () => {
    setEditingEntity(null);
    setIsFormOpen(true);
  };

  const handleEditClick = (entity) => {
    setEditingEntity(entity);
    setIsFormOpen(true);
  };

  return (
    <div className="space-y-4">
      <div className="sm:flex sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <Building2 className="w-5 h-5 text-indigo-600" />
            Government Entities
          </h1>
          <p className="mt-0.5 text-xs text-slate-500 font-medium">
            Manage your public sector entities and hierarchy.
          </p>
        </div>
        <div className="mt-3 sm:mt-0 flex gap-2">
          <button
            onClick={handleAddClick}
            className="inline-flex items-center px-3.5 py-1.5 border border-transparent rounded-xl shadow-xs text-xs font-bold text-white bg-slate-900 hover:bg-black transition-colors"
          >
            <Plus className="-ml-0.5 mr-1.5 w-3.5 h-3.5" aria-hidden="true" />
            Add Entity
          </button>
        </div>
      </div>

      <div className="bg-white p-2.5 rounded-2xl shadow-xs border border-slate-200/80">
        <div className="relative max-w-md">
          <div className="pointer-events-none absolute inset-y-0 left-0 pl-2.5 flex items-center">
            <Search className="h-3.5 w-3.5 text-slate-400" />
          </div>
          <input
            type="text"
            className="block w-full rounded-xl border border-slate-200 pl-8 pr-3 py-1.5 text-xs bg-slate-50/70 focus:bg-white focus:border-indigo-500 outline-none transition"
            placeholder="Search by name or country..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>
      </div>

      <div className="bg-white shadow-xs border border-slate-200/80 rounded-2xl overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-slate-500 text-xs">Loading...</div>
        ) : entities.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-xs">No entities found.</div>
        ) : (
          <table className="min-w-full divide-y divide-slate-100">
            <thead className="bg-slate-50/80">
              <tr>
                <th className="px-4 py-2.5 text-left text-[11px] font-bold text-slate-500 uppercase tracking-wider">Name</th>
                <th className="px-4 py-2.5 text-left text-[11px] font-bold text-slate-500 uppercase tracking-wider">Country</th>
                <th className="px-4 py-2.5 text-left text-[11px] font-bold text-slate-500 uppercase tracking-wider">Level</th>
                <th className="px-4 py-2.5 text-left text-[11px] font-bold text-slate-500 uppercase tracking-wider">Parent Govt</th>
                <th className="relative px-4 py-2.5 text-right text-[11px] font-bold text-slate-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 bg-white">
              {entities.map((entity) => (
                <tr key={entity.id} className="hover:bg-slate-50/70">
                  <td className="whitespace-nowrap px-4 py-2.5 text-xs font-semibold text-slate-900">
                    {entity.name}
                  </td>
                  <td className="whitespace-nowrap px-4 py-2.5 text-xs text-slate-600">{entity.country}</td>
                  <td className="whitespace-nowrap px-4 py-2.5 text-xs">
                    <span className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-bold leading-4 border ${entity.is_state_government ? 'bg-amber-50 text-amber-700 border-amber-200' : 'bg-emerald-50 text-emerald-700 border-emerald-200'}`}>
                      {entity.is_state_government ? `State${entity.state_name ? ` (${entity.state_name})` : ''}` : 'Central'}
                    </span>
                  </td>
                  <td className="whitespace-nowrap px-4 py-2.5 text-xs text-slate-600">
                    {entity.central_government_detail?.name || '-'}
                  </td>
                  <td className="whitespace-nowrap px-4 py-2.5 text-right text-xs">
                    <button
                      onClick={() => handleEditClick(entity)}
                      className="text-slate-400 hover:text-indigo-600 p-1 rounded-lg hover:bg-slate-100 transition"
                      title="Edit"
                    >
                      <Edit2 className="h-3.5 w-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <GovernmentEntityForm
        isOpen={isFormOpen}
        onClose={() => setIsFormOpen(false)}
        entity={editingEntity}
        onSuccess={fetchEntities}
      />
    </div>
  );
};

export default GovernmentEntitiesPage;
