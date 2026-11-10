import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { toast } from 'react-toastify';
import { fetchProspects, deleteProspect } from '../features/prospects/prospectSlice';
import { fetchMarketEvents } from '../features/marketEvents/marketEventSlice';
import ProspectForm from '../components/prospects/ProspectForm';
import { Plus, Search, Edit2, Trash2, Building2, Eye, CheckCircle, XCircle, X, Activity, Phone } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import Pagination from '../components/layout/Pagination';
import SearchableSelect from '../components/common/SearchableSelect';
import LqPipelinePage from './LqPipelinePage';

const ProspectsPage = () => {
  const dispatch = useDispatch();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = (searchParams.get('tab') === 'outreach' || searchParams.get('tab') === 'pipeline') ? 'outreach' : 'directory';
  const pipelineFilter = searchParams.get('filter') || 'all';

  const { items, loading, error, count } = useSelector((state) => state.prospects);
  const { items: marketEventsList } = useSelector((state) => state.marketEvents);
  const { items: lqItems } = useSelector((state) => state.lqPipeline);
  const { user } = useSelector((state) => state.auth);

  const pendingLqCount = lqItems?.filter(i => i.verification_status !== 'Verified')?.length || 0;

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

  const handleTabSwitch = (newTab) => {
    const nextParams = new URLSearchParams(searchParams);
    if (newTab === 'outreach' || newTab === 'pipeline') {
      nextParams.set('tab', 'outreach');
    } else {
      nextParams.delete('tab');
      nextParams.delete('filter');
    }
    setSearchParams(nextParams);
  };

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
    <div className="space-y-4 min-h-full flex-1 flex flex-col pb-2">
      {/* Header & Unified Module Tab Switcher */}
      <div className="sm:flex sm:items-center sm:justify-between shrink-0 gap-4">
        <div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <Building2 className="w-5 h-5 text-indigo-600" />
            <span>Prospects</span>
          </h1>
          <p className="mt-0.5 text-xs text-slate-500 font-medium">
            {activeTab === 'directory'
              ? 'Manage your market intelligence prospects, corporate structures, and key contacts.'
              : 'Review prospects, execute outreach communications, and qualify opportunities.'}
          </p>
        </div>

        {/* Unified Tab Switcher & Quick Actions */}
        <div className="mt-3 sm:mt-0 flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-2xl border border-slate-200/80">
            <button
              type="button"
              onClick={() => handleTabSwitch('directory')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                activeTab === 'directory'
                  ? 'bg-white text-slate-900 shadow-2xs'
                  : 'text-slate-500 hover:text-slate-900'
              }`}
            >
              <Building2 className="w-3.5 h-3.5 text-indigo-600" />
              <span>Prospect Directory</span>
              <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-slate-100 text-slate-600 border border-slate-200">
                {count || 0}
              </span>
            </button>
            <button
              type="button"
              onClick={() => handleTabSwitch('outreach')}
              className={`flex items-center gap-2 px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all cursor-pointer ${
                activeTab === 'outreach'
                  ? 'bg-white text-slate-900 shadow-2xs'
                  : 'text-slate-500 hover:text-slate-900'
              }`}
            >
              <Phone className="w-3.5 h-3.5 text-indigo-600" />
              <span>Outreach</span>
            </button>
          </div>

          {activeTab === 'directory' && user?.role === 'PRE' && (
            <div className="flex gap-2">
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
            </div>
          )}
        </div>
      </div>

      {/* Main Tab Content */}
      {activeTab === 'outreach' ? (
        <div className="flex-1 flex flex-col min-h-0">
          <LqPipelinePage filter={pipelineFilter} embedded={true} />
        </div>
      ) : (
        /* Filter / Search Card & Directory Table */
        <div className="bg-white rounded-2xl shadow-xs border border-slate-200/80 overflow-hidden flex-1 flex flex-col min-h-0">
          <div className="p-3 border-b border-slate-200/80 bg-slate-50/70 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shrink-0">
            <div className="flex flex-1 max-w-2xl gap-3">
              <form onSubmit={handleSearch} className="flex-1 relative">
                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                  <Search className="h-3.5 w-3.5 text-slate-400" />
                </div>
                <input
                  type="text"
                  className="block w-full pl-9 pr-8 py-1.5 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 bg-white placeholder-slate-400 shadow-2xs hover:border-slate-300 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition"
                  placeholder="Search companies by name..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
                {searchTerm && (
                  <button
                    type="button"
                    onClick={() => setSearchTerm('')}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 p-0.5 rounded-full hover:bg-slate-100 transition"
                    title="Clear search"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
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
            
            <div className="text-xs font-semibold text-slate-500 bg-white px-3 py-1.5 rounded-xl border border-slate-200 shadow-2xs shrink-0">
              Total Records: <span className="font-bold text-slate-800">{count}</span>
            </div>
          </div>
          
          {marketEventFilter && (
            <div className="px-3.5 py-2 bg-indigo-50/70 border-b border-indigo-100 flex items-center justify-between text-xs shrink-0">
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
            <div className="p-3 bg-red-50 border-b border-red-200 text-red-700 text-xs font-medium shrink-0">
              {error}
            </div>
          )}

          <div className="overflow-x-auto flex-1">
            <table className="w-full text-left text-xs border-collapse">
              <thead className="bg-slate-50/80">
                <tr className="border-b border-slate-200 text-slate-500 font-bold uppercase tracking-wider text-[11px]">
                  <th scope="col" className="px-3.5 py-2 w-[26%]">Prospect Name</th>
                  <th scope="col" className="px-3.5 py-2 w-[16%]">Country</th>
                  <th scope="col" className="px-3.5 py-2 w-[12%]">Structure</th>
                  <th scope="col" className="px-3.5 py-2 w-[12%]">Status</th>
                  <th scope="col" className="px-3.5 py-2 w-[24%]">Primary Industry</th>
                  <th scope="col" className="px-3.5 py-2 w-[10%] text-right">Actions</th>
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
                      <td className="px-3.5 py-2">
                        <div className="flex items-center gap-1.5 truncate max-w-[220px]">
                          <Link to={`/prospects/${prospect.id}`} className="text-xs font-bold text-slate-900 hover:text-indigo-600 transition truncate" title={prospect.company_name}>
                            {prospect.company_name}
                          </Link>
                          {prospect.qualification_status === 'Lead Qualified' && (
                            <CheckCircle className="w-3.5 h-3.5 text-emerald-500 shrink-0" title="Lead Qualified" />
                          )}
                          {prospect.qualification_status === 'Lead Freeze' && (
                            <XCircle className="w-3.5 h-3.5 text-red-500 shrink-0" title="Lead Freeze" />
                          )}
                        </div>
                      </td>
                      <td className="px-3.5 py-2 whitespace-nowrap text-xs text-slate-600 truncate max-w-[140px]" title={prospect.country_head_office}>
                        {prospect.country_head_office}
                      </td>
                      <td className="px-3.5 py-2 whitespace-nowrap">
                        <span className="px-2 py-0.5 inline-flex text-[10px] leading-4 font-bold rounded-full bg-slate-100 text-slate-700 border border-slate-200">
                          {prospect.company_structure}
                        </span>
                      </td>
                      <td className="px-3.5 py-2 whitespace-nowrap">
                        <span className={`px-2 py-0.5 inline-flex text-[10px] leading-4 font-bold rounded-full border ${
                          prospect.operational_status === 'Active' ? 'bg-green-50 text-green-700 border-green-200' :
                          prospect.operational_status === 'Inactive' ? 'bg-amber-50 text-amber-700 border-amber-200' :
                          'bg-red-50 text-red-700 border-red-200'
                        }`}>
                          {prospect.operational_status}
                        </span>
                      </td>
                      <td className="px-3.5 py-2 text-xs text-slate-600">
                        <div 
                          className="truncate font-medium text-slate-700 bg-slate-50 border border-slate-200/80 px-2.5 py-1 rounded-lg inline-block max-w-[220px] md:max-w-[260px] xl:max-w-[340px]"
                          title={prospect.primary_industries || '—'}
                        >
                          {prospect.primary_industries || '—'}
                        </div>
                      </td>
                      <td className="px-3.5 py-2 whitespace-nowrap text-right text-xs font-medium">
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
      )}

      <ProspectForm 
        isOpen={isFormOpen} 
        onClose={() => setIsFormOpen(false)} 
        prospect={editingProspect} 
      />
    </div>
  );
};

export default ProspectsPage;
