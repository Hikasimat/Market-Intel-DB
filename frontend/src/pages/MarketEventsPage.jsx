import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate } from 'react-router-dom';
import { toast } from 'react-toastify';
import { Calendar, Search, Plus, MapPin, Eye, Edit2, Trash2 } from 'lucide-react';
import { fetchMarketEvents, deleteMarketEvent, setSearch, setPage } from '../features/marketEvents/marketEventSlice';
import MarketEventForm from '../components/marketEvents/MarketEventForm';
import Pagination from '../components/layout/Pagination';

const MarketEventsPage = () => {
  const dispatch = useDispatch();
  const navigate = useNavigate();

  const { items: events, loading, error, search, page, count } = useSelector((state) => state.marketEvents);
  const { user } = useSelector((state) => state.auth);

  // PRE users (and superusers) can create, edit, and delete events.
  // LQ users have read-only access enforced on both frontend and backend.
  const canMutate = user?.role === 'PRE' || user?.is_superuser;

  const [isFormOpen, setIsFormOpen] = useState(() => {
    const userId = user?.id || 'default';
    return sessionStorage.getItem(`marketEventFormOpen_${userId}`) === 'true';
  });
  const [editingEvent, setEditingEvent] = useState(() => {
    const userId = user?.id || 'default';
    const saved = sessionStorage.getItem(`marketEventEditing_${userId}`);
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch(e) {}
    }
    return null;
  });

  useEffect(() => {
    const userId = user?.id || 'default';
    sessionStorage.setItem(`marketEventFormOpen_${userId}`, isFormOpen);
    if (editingEvent) {
      sessionStorage.setItem(`marketEventEditing_${userId}`, JSON.stringify(editingEvent));
    } else {
      sessionStorage.removeItem(`marketEventEditing_${userId}`);
    }
  }, [isFormOpen, editingEvent, user]);

  useEffect(() => {
    dispatch(fetchMarketEvents({ search, page }));
  }, [dispatch, search, page]);

  const handleSearch = (e) => {
    dispatch(setSearch(e.target.value));
  };

  const handleAdd = () => {
    if (!canMutate) return;
    setEditingEvent(null);
    setIsFormOpen(true);
  };

  const handleEdit = (event, e) => {
    if (!canMutate) return;
    e.stopPropagation();
    setEditingEvent(event);
    setIsFormOpen(true);
  };

  const handleDelete = async (id, e) => {
    if (!canMutate) return;
    e.stopPropagation();
    try {
      await dispatch(deleteMarketEvent(id)).unwrap();
      dispatch(fetchMarketEvents({ search }));
      toast.success('Market event deleted successfully.');
    } catch (err) {
      toast.error('Failed to delete market event.');
    }
  };

  // Utility to format date correctly (prevent timezone issues)
  const formatDate = (dateString) => {
    if (!dateString) return '';
    const [year, month, day] = dateString.split('-');
    return `${day}-${month}-${year}`;
  };

  return (
    <div className="space-y-4">
      {/* Header section */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-bold text-slate-900 flex items-center gap-2">
            <Calendar className="w-5 h-5 text-indigo-600" />
            Market Events
          </h1>
          <p className="mt-0.5 text-xs text-slate-500 max-w-xl">
            Track industry events and the prospects participating in each event.
          </p>
        </div>
        {/* Add button — only visible to PRE/superuser */}
        {canMutate && (
          <button
            onClick={handleAdd}
            className="inline-flex items-center gap-1.5 bg-slate-900 text-white px-3.5 py-1.5 rounded-xl font-bold text-xs shadow-xs hover:bg-black transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            Add Market Event
          </button>
        )}
      </div>

      {/* Filters/Search */}
      <div className="bg-white p-2.5 rounded-2xl shadow-xs border border-slate-200/80">
        <div className="relative max-w-md">
          <div className="absolute inset-y-0 left-0 pl-2.5 flex items-center pointer-events-none">
            <Search className="h-3.5 w-3.5 text-slate-400" />
          </div>
          <input
            type="text"
            className="block w-full pl-8 pr-3 py-1.5 border border-slate-200 rounded-xl text-xs bg-slate-50/70 focus:bg-white focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-colors placeholder:text-slate-400"
            placeholder="Search by event title or country..."
            value={search}
            onChange={handleSearch}
          />
        </div>
      </div>

      {/* Main Content */}
      <div className="bg-white border border-slate-200/80 rounded-2xl shadow-xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs whitespace-nowrap">
            <thead className="bg-slate-50/80 border-b border-slate-100 text-slate-500 uppercase tracking-wider text-[11px] font-bold">
              <tr>
                <th className="px-4 py-2.5">Event Title</th>
                <th className="px-4 py-2.5">Host Country</th>
                <th className="px-4 py-2.5">Event Date</th>
                <th className="px-4 py-2.5">Participating Companies</th>
                <th className="px-4 py-2.5 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 bg-white">
              {loading && events?.length === 0 ? (
                <tr>
                  <td colSpan="5" className="px-6 py-12 text-center text-slate-500">
                    Loading events...
                  </td>
                </tr>
              ) : error ? (
                <tr>
                  <td colSpan="5" className="px-6 py-12 text-center text-red-500">
                    Error loading events. Please try again.
                  </td>
                </tr>
              ) : events?.length === 0 ? (
                <tr>
                  <td colSpan="5" className="px-6 py-12 text-center">
                    <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-slate-100 mb-4">
                      <Calendar className="w-6 h-6 text-slate-400" />
                    </div>
                    <h3 className="text-sm font-semibold text-slate-900 mb-1">No market events found</h3>
                    <p className="text-sm text-slate-500">
                      {search ? "Try adjusting your search query." : "Get started by adding a new market event."}
                    </p>
                  </td>
                </tr>
              ) : (
                (events || []).map((event) => (
                  <tr
                    key={event.id}
                    className="hover:bg-slate-50 transition-colors cursor-pointer group"
                    onClick={() => navigate(`/market-events/${event.id}`)}
                  >
                    <td className="px-4 py-2.5">
                      <div className="font-semibold text-xs text-slate-900 truncate max-w-md">
                        {event.event_title}
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-xs">
                      <div className="flex items-center gap-1.5 text-slate-600">
                        <MapPin className="w-3.5 h-3.5 text-slate-400" />
                        {event.host_country}
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-slate-600">
                      {formatDate(event.event_date)}
                    </td>
                    <td className="px-4 py-2.5 text-xs">
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-100">
                        {event.participating_companies_count} Companies
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right text-xs">
                      <div className="flex items-center justify-end gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                        {/* View — available to all */}
                        <button
                          onClick={(e) => { e.stopPropagation(); navigate(`/market-events/${event.id}`); }}
                          className="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-md transition-colors"
                          title="View"
                        >
                          <Eye className="w-4 h-4" />
                        </button>
                        {/* Edit — PRE/superuser only */}
                        {canMutate && (
                          <button
                            onClick={(e) => handleEdit(event, e)}
                            className="p-1.5 text-slate-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-md transition-colors"
                            title="Edit"
                          >
                            <Edit2 className="w-4 h-4" />
                          </button>
                        )}
                        {/* Delete — PRE/superuser only */}
                        {canMutate && (
                          <button
                            onClick={(e) => handleDelete(event.id, e)}
                            className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors"
                            title="Delete"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
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
          onPageChange={(newPage) => dispatch(setPage(newPage))} 
        />
      </div>

      {/* Form modal — only rendered for PRE/superuser */}
      {canMutate && (
        <MarketEventForm
          isOpen={isFormOpen}
          onClose={() => setIsFormOpen(false)}
          initialData={editingEvent}
        />
      )}
    </div>
  );
};

export default MarketEventsPage;
