import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Briefcase, Mail, Phone, CheckCircle, PhoneOff, PhoneMissed, PhoneCall, AlertCircle, Users, X } from 'lucide-react';
import { useSelector } from 'react-redux';
import api from '../services/api';
import Pagination from '../components/layout/Pagination';

const CALL_STATUS_CONFIG = {
  'Connected':      { bg: 'bg-emerald-500', border: 'border-emerald-400', text: 'text-emerald-700', light: 'bg-emerald-50', ring: 'ring-emerald-400', label: 'Connected', icon: CheckCircle },
  'No Answer':      { bg: 'bg-amber-500',   border: 'border-amber-400',   text: 'text-amber-700',   light: 'bg-amber-50',   ring: 'ring-amber-400',   label: 'No Answer', icon: PhoneMissed },
  'Busy':           { bg: 'bg-orange-500',  border: 'border-orange-400',  text: 'text-orange-700',  light: 'bg-orange-50',  ring: 'ring-orange-400',  label: 'Busy', icon: PhoneCall },
  'Switched Off':   { bg: 'bg-rose-500',    border: 'border-rose-400',    text: 'text-rose-700',    light: 'bg-rose-50',    ring: 'ring-rose-400',    label: 'Switched Off', icon: PhoneOff },
  'Invalid Number': { bg: 'bg-slate-500',   border: 'border-slate-400',   text: 'text-slate-600',   light: 'bg-slate-100',  ring: 'ring-slate-400',   label: 'Invalid Number', icon: AlertCircle },
};

const KeyPeoplePage = () => {
  const { user } = useSelector((state) => state.auth);
  const [contacts, setContacts] = useState([]);
  const [searchTerm, setSearchTerm] = useState(() => {
    const userId = user?.id || 'default';
    return sessionStorage.getItem(`keyPeopleSearch_${userId}`) || '';
  });
  const [isLoading, setIsLoading] = useState(true);
  const [page, setPage] = useState(() => {
    const userId = user?.id || 'default';
    return parseInt(sessionStorage.getItem(`keyPeoplePage_${userId}`)) || 1;
  });
  const [totalCount, setTotalCount] = useState(0);
  const navigate = useNavigate();

  useEffect(() => {
    const userId = user?.id || 'default';
    sessionStorage.setItem(`keyPeopleSearch_${userId}`, searchTerm);
    sessionStorage.setItem(`keyPeoplePage_${userId}`, page);
  }, [searchTerm, page, user]);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchContacts();
    }, 300);
    return () => clearTimeout(timer);
  }, [searchTerm, page]);

  const fetchContacts = async () => {
    try {
      setIsLoading(true);
      const endpoint = `/key-contacts/?search=${searchTerm}&page=${page}`;
      const response = await api.get(endpoint);
      let data = response.data.results || response.data;
      
      // Filter logic: Show only invalid Key People in PRE (invalid email or invalid phone), while displaying all Key People in LQ.
      if (user?.role === 'PRE') {
        data = data.filter(c => c.email_verification_status === 'INVALID' || c.latest_call_status === 'Invalid Number');
      }
      setContacts(data);
      setTotalCount(response.data.count || data.length);
    } catch (error) {
      console.error('Failed to fetch key contacts:', error);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="space-y-4 min-h-full flex-1 flex flex-col pb-2">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 shrink-0">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-indigo-600 text-white flex items-center justify-center shadow-xs">
              <Users className="w-4 h-4" />
            </div>
            Key People
          </h1>
          <p className="text-slate-500 text-xs mt-0.5 font-medium">Manage and view key contacts associated with prospects.</p>
        </div>
        <div className="text-xs font-semibold text-slate-600 bg-white px-3 py-1.5 rounded-xl border border-slate-200/80 shadow-2xs">
          {contacts.length} Contact{contacts.length !== 1 ? 's' : ''}
        </div>
      </div>

      <div className="bg-white p-3 rounded-2xl border border-slate-200/80 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3 shrink-0">
        <div className="relative w-full sm:w-80">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-400" />
          <input
            type="text"
            placeholder="Search by name, email, or company..."
            className="w-full pl-9 pr-8 py-1.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-medium text-slate-800 placeholder-slate-400 shadow-2xs hover:border-slate-300 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition"
            value={searchTerm}
            onChange={(e) => { setSearchTerm(e.target.value); setPage(1); }}
          />
          {searchTerm && (
            <button
              type="button"
              onClick={() => { setSearchTerm(''); setPage(1); }}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 p-0.5 rounded-full hover:bg-slate-100 transition"
              title="Clear search"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
        <div className="text-xs font-semibold text-slate-500">
          Showing: <span className="font-bold text-slate-800">{contacts.length}</span> contacts
        </div>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {[...Array(8)].map((_, i) => (
            <div key={i} className="bg-white rounded-2xl border border-slate-200 p-5 animate-pulse space-y-3">
              <div className="space-y-2 flex-1">
                <div className="h-3 bg-slate-200 rounded w-3/4" />
                <div className="h-2.5 bg-slate-100 rounded w-1/2" />
              </div>
              <div className="h-2 bg-slate-100 rounded w-full" />
              <div className="h-2 bg-slate-100 rounded w-2/3" />
            </div>
          ))}
        </div>
      ) : contacts.length === 0 ? (
        <div className="bg-white rounded-2xl border border-slate-200 p-16 text-center">
          <Users className="w-14 h-14 text-slate-300 mx-auto mb-4" />
          <p className="font-extrabold text-slate-700 text-lg">No key people found</p>
          <p className="text-slate-400 text-sm mt-1">Try adjusting your search criteria.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
          {contacts.map((contact) => {
            const status = contact.latest_call_status;
            const cfg = status ? CALL_STATUS_CONFIG[status] : null;
            const StatusIcon = cfg ? cfg.icon : null;

            return (
              <div
                key={contact.id}
                onClick={() => navigate(`/key-people/${contact.id}`)}
                className={`relative bg-white rounded-2xl border ${cfg ? `border-2 ${cfg.border}` : 'border-slate-200'} shadow-sm hover:shadow-md transition-all duration-200 cursor-pointer group overflow-hidden p-5 space-y-4`}
              >
                <div>
                  <div className="font-bold text-slate-900 group-hover:text-indigo-700 transition-colors text-base truncate">
                    {contact.contact_name}
                  </div>
                  {contact.designation && (
                    <div className="text-[11px] text-slate-500 font-medium flex items-center gap-1 mt-1">
                      <Briefcase className="w-3 h-3 shrink-0 text-slate-400" />
                      <span className="truncate">{contact.designation}</span>
                    </div>
                  )}
                </div>

                <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-indigo-50 border border-indigo-100 text-[11px] font-semibold text-indigo-700 max-w-full overflow-hidden">
                  <span className="truncate">{contact.prospect_name || 'Unknown Company'}</span>
                </div>

                <div className="space-y-2 pt-3 border-t border-slate-100">
                  {contact.official_email && (
                    <div className="flex items-center justify-between text-[11px] text-slate-600 font-medium min-w-0">
                      <div className="flex items-center gap-2 truncate">
                        <Mail className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                        <span className="truncate">{contact.official_email}</span>
                      </div>
                      {contact.email_verification_status === 'INVALID' && (
                        <span className="shrink-0 ml-2 px-1.5 py-0.5 bg-red-100 text-red-700 text-[9px] font-bold rounded">INVALID</span>
                      )}
                    </div>
                  )}
                  {contact.phone_number && (
                    <div className="flex items-center gap-2 text-[11px] text-slate-700 font-medium">
                      <Phone className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                      <span>{contact.phone_number}</span>
                    </div>
                  )}
                </div>

                {cfg && StatusIcon ? (
                  <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[11px] font-medium border ${cfg.light} ${cfg.border} ${cfg.text}`}>
                    <StatusIcon className="w-3.5 h-3.5 shrink-0" />
                    <span>{status}</span>
                    {contact.latest_communication_outcome && (
                      <span className="ml-0.5 opacity-80">({contact.latest_communication_outcome})</span>
                    )}
                  </div>
                ) : (
                  <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[11px] font-medium bg-slate-50 border border-slate-200 text-slate-500">
                    <Phone className="w-3.5 h-3.5 shrink-0" />
                    No calls recorded
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      {!isLoading && contacts.length > 0 && (
        <Pagination 
          currentPage={page} 
          totalCount={totalCount} 
          pageSize={50} 
          onPageChange={setPage} 
        />
      )}
    </div>
  );
};

export default KeyPeoplePage;
