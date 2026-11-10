import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { toast } from 'react-toastify';
import { fetchProspects, deleteProspect } from '../features/prospects/prospectSlice';
import { fetchMarketEvents } from '../features/marketEvents/marketEventSlice';
import ProspectForm from '../components/prospects/ProspectForm';
import { Plus, Search, Edit2, Trash2, Building2, Eye, CheckCircle, XCircle } from 'lucide-react';
import { Link } from 'react-router-dom';
import Pagination from '../components/layout/Pagination';
import SearchableSelect from '../components/common/SearchableSelect';

const ProspectsPage = () => {
  const dispatch = useDispatch();
  const { items, loading, error, count, next, previous } = useSelector((state) => state.prospects);
  const { items: marketEventsList } = useSelector((state) => state.marketEvents);
  const { user } = useSelector((state) => state.auth);
  const [searchTerm, setSearchTerm] = useState(() => {
    const userId = user?.id || 'default';
    return sessionStorage.getItem(`prospectsSearch_${userId}`) || '';
  });
  const [marketEventFilter, setMarketEventFilter] = useState(() => {
    const userId = user?.id || 'default';
    return sessionStorage.getItem(`prospectsMarketEvent_${userId}`) || '';
  });
  const [isFormOpen, setIsFormOpen] = useState(() => {
    const userId = user?.id || 'default';
    return sessionStorage.getItem(`prospectsFormOpen_${userId}`) === 'true';
  });
  const [editingProspect, setEditingProspect] = useState(() => {
    const userId = user?.id || 'default';
    const saved = sessionStorage.getItem(`prospectsEditing_${userId}`);
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch(e) {}
    }
    return null;
  });
  const [page, setPage] = useState(() => {
    const userId = user?.id || 'default';
    return parseInt(sessionStorage.getItem(`prospectsPage_${userId}`)) || 1;
  });

  useEffect(() => {
    const userId = user?.id || 'default';
    sessionStorage.setItem(`prospectsSearch_${userId}`, searchTerm);
    sessionStorage.setItem(`prospectsMarketEvent_${userId}`, marketEventFilter);
    sessionStorage.setItem(`prospectsPage_${userId}`, page);
    sessionStorage.setItem(`prospectsFormOpen_${userId}`, isFormOpen);
    if (editingProspect) {
      sessionStorage.setItem(`prospectsEditing_${userId}`, JSON.stringify(editingProspect));
    } else {
      sessionStorage.removeItem(`prospectsEditing_${userId}`);
    }
  }, [searchTerm, marketEventFilter, page, user, isFormOpen, editingProspect]);

  useEffect(() => {
    dispatch(fetchMarketEvents({}));
  }, [dispatch]);

  useEffect(() => {
    const params = {
      page: page,
      search: searchTerm,
    };
    if (marketEventFilter) {
      params.market_event = marketEventFilter;
    }
    dispatch(fetchProspects(params));
  }, [dispatch, page, searchTerm, marketEventFilter]);

  const handleAddClick = () => {
    setEditingProspect(null);
    setIsFormOpen(true);
  };

  const handleEditClick = (prospect) => {
    setEditingProspect(prospect);
    setIsFormOpen(true);
  };

  const handleDelete = async (id) => {
    try {
      await dispatch(deleteProspect(id)).unwrap();
      toast.success('Prospect deleted successfully.');
    } catch (err) {
      toast.error('Failed to delete prospect.');
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    setPage(1); // Reset to page 1 on new search
  };

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="sm:flex sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <Building2 className="w-5 h-5 text-indigo-600" />
            Prospects
          </h1>
          <p className="mt-0.5 text-xs text-slate-500 font-medium">
            Manage your market intelligence prospects, corporate structures, and key contacts.
          </p>
        </div>
        <div className="mt-3 sm:mt-0 flex gap-2">
          {user?.role === 'PRE' && (
            <>
              <Link
                to="/prospects/import-preview"
                className="inline-flex items-center px-3.5 py-1.5 border border-slate-300 rounded-xl shadow-xs text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 focus:outline-none transition-colors"
              >
                Import Prospects
              </Link>
              <button
                onClick={handleAddClick}
                className="inline-flex items-center px-3.5 py-1.5 border border-transparent rounded-xl shadow-xs text-xs font-bold text-white bg-slate-900 hover:bg-black focus:outline-none transition-colors"
              >
                <Plus className="-ml-0.5 mr-1.5 w-3.5 h-3.5" aria-hidden="true" />
                Add Prospect
              </button>
            </>
          )}
        </div>
      </div>

      {/* Filter / Search Card */}
      <div className="bg-white rounded-2xl shadow-xs border border-slate-200/80 overflow-hidden">
        <div className="p-3 border-b border-slate-200/80 bg-slate-50/70 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex flex-1 max-w-2xl gap-3">
            <form onSubmit={handleSearch} className="flex-1 relative">
              <div className="absolute inset-y-0 left-0 pl-2.5 flex items-center pointer-events-none">
                <Search className="h-3.5 w-3.5 text-slate-400" />
              </div>
              <input
                type="text"
                className="block w-full pl-8 pr-3 py-1.5 border border-slate-200 rounded-xl text-xs bg-white placeholder-slate-400 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-colors"
                placeholder="Search companies..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
            </form>
            
            <div className="w-56">
              <SearchableSelect
                value={marketEventFilter}
                onChange={(val) => {
                  setMarketEventFilter(val);
                  setPage(1);
                }}
                placeholder="All Market Events"
                options={[
                  {value: '', label: 'All Market Events'},
                  ...((marketEventsList || []).map(event => ({value: event.id, label: event.event_title})))
                ]}
              />
            </div>
          </div>
          
          <div className="text-xs text-slate-500 font-medium">
            Total Records: {count}
          </div>
        </div>
        
        {marketEventFilter && (
          <div className="px-3.5 py-2 bg-indigo-50/70 border-b border-indigo-100 flex items-center justify-between text-xs">
            <div>
              <span className="text-slate-700">
                Showing prospects participating in: <span className="font-bold text-indigo-900">{marketEventsList?.find(e => e.id === marketEventFilter)?.event_title}</span>
              </span>
            </div>
            <button 
              onClick={() => {
                setMarketEventFilter('');
                setPage(1);
              }}
              className="text-[11px] font-bold text-indigo-700 bg-white px-2 py-0.5 rounded-md border border-indigo-200 hover:bg-indigo-100 transition-colors"
            >
              Clear Filter
            </button>
          </div>
        )}

        {error && (
          <div className="p-3 bg-red-50 border-b border-red-200 text-red-700 text-xs font-medium">
            {error}
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-100">
            <thead className="bg-slate-50/80">
              <tr>
                <th scope="col" className="px-4 py-2.5 text-left text-[11px] font-bold text-slate-500 uppercase tracking-wider">Prospect Name</th>
                <th scope="col" className="px-4 py-2.5 text-left text-[11px] font-bold text-slate-500 uppercase tracking-wider">Country</th>
                <th scope="col" className="px-4 py-2.5 text-left text-[11px] font-bold text-slate-500 uppercase tracking-wider">Structure</th>
                <th scope="col" className="px-4 py-2.5 text-left text-[11px] font-bold text-slate-500 uppercase tracking-wider">Status</th>
                <th scope="col" className="px-4 py-2.5 text-left text-[11px] font-bold text-slate-500 uppercase tracking-wider">Primary Industry</th>
                <th scope="col" className="px-4 py-2.5 text-right text-[11px] font-bold text-slate-500 uppercase tracking-wider">Actions</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan="6" className="px-4 py-10 text-center text-slate-500 text-xs">
                    <div className="flex justify-center items-center gap-2">
                      <div className="w-3.5 h-3.5 rounded-full bg-indigo-600 animate-ping"></div>
                      Loading prospects...
                    </div>
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan="6" className="px-4 py-10 text-center text-slate-500 text-xs">
                    No prospects found.
                  </td>
                </tr>
              ) : (
                items.map((prospect) => (
                  <tr key={prospect.id} className="hover:bg-slate-50/70 transition-colors">
                    <td className="px-4 py-2.5 whitespace-nowrap">
                      <div className="flex items-center gap-1.5">
                        <Link to={`/prospects/${prospect.id}`} className="text-xs font-bold text-slate-900 hover:text-indigo-600 transition">
                          {prospect.company_name}
                        </Link>
                        {prospect.qualification_status === 'Lead Qualified' && (
                          <CheckCircle className="w-3.5 h-3.5 text-emerald-500" title="Lead Qualified" />
                        )}
                        {prospect.qualification_status === 'Lead Freeze' && (
                          <XCircle className="w-3.5 h-3.5 text-red-500" title="Lead Freeze" />
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-2.5 whitespace-nowrap text-xs text-slate-600">{prospect.country_head_office}</td>
                    <td className="px-4 py-2.5 whitespace-nowrap">
                      <span className="px-2 py-0.5 inline-flex text-[10px] leading-4 font-bold rounded-full bg-slate-100 text-slate-700 border border-slate-200">
                        {prospect.company_structure}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 whitespace-nowrap">
                      <span className={`px-2 py-0.5 inline-flex text-[10px] leading-4 font-bold rounded-full border ${
                        prospect.operational_status === 'Active' ? 'bg-green-50 text-green-700 border-green-200' :
                        prospect.operational_status === 'Inactive' ? 'bg-amber-50 text-amber-700 border-amber-200' :
                        'bg-red-50 text-red-700 border-red-200'
                      }`}>
                        {prospect.operational_status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 whitespace-nowrap text-xs text-slate-600">{prospect.primary_industries}</td>
                    <td className="px-4 py-2.5 whitespace-nowrap text-right text-xs font-medium">
                      <div className="flex justify-end gap-1.5 items-center">
                        {user?.role === 'PRE' && (
                          <>
                            <Link to={`/prospects/${prospect.id}`} className="p-1 text-slate-400 hover:text-emerald-600 rounded-lg hover:bg-slate-100 transition" title="View Details">
                              <Eye size={15} />
                            </Link>
                            <button onClick={() => handleEditClick(prospect)} className="p-1 text-slate-400 hover:text-indigo-600 rounded-lg hover:bg-slate-100 transition" title="Edit">
                              <Edit2 size={15} />
                            </button>
                            <button onClick={() => handleDelete(prospect.id)} className="p-1 text-slate-400 hover:text-rose-600 rounded-lg hover:bg-slate-100 transition" title="Delete">
                              <Trash2 size={15} />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <Pagination 
          currentPage={page} 
          totalCount={count || 0} 
          pageSize={50} 
          onPageChange={setPage} 
        />
      </div>

      <ProspectForm 
        isOpen={isFormOpen} 
        onClose={() => setIsFormOpen(false)} 
        prospect={editingProspect} 
      />
    </div>
  );
};

export default ProspectsPage;
