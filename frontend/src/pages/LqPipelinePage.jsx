import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { 
  Building2, AlertTriangle, CheckCircle, Phone, Search, 
  CheckCircle2, AlertCircle, PlayCircle, RefreshCw,
  FileEdit, Mail, XCircle, Activity, Calendar, ChevronDown, ChevronUp, X
} from 'lucide-react';
import { 
  fetchLqPipeline, 
  updateVerification, 
  confirmReverification,
  reportIssueToPre,
  setPage
} from '../features/lqPipeline/lqPipelineSlice';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { toast } from 'react-toastify';
import LqWorkspaceModal from '../components/lq/LqWorkspaceModal';
import Pagination from '../components/layout/Pagination';
import api from '../services/api';

const LqPipelinePage = ({ filter = 'all', embedded = false }) => {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeFilter = searchParams.get('filter') || filter || 'all';

  const handleFilterChange = (newFilter) => {
    const nextParams = new URLSearchParams(searchParams);
    if (newFilter === 'all') {
      nextParams.delete('filter');
    } else {
      nextParams.set('filter', newFilter);
    }
    setSearchParams(nextParams);
  };
  const { items, loading, page, count } = useSelector((state) => state.lqPipeline);
  const { user } = useSelector((state) => state.auth);
  const isManager = user?.role === 'MANAGER';

  useEffect(() => {
    if (searchParams.get('calendar_connected') === '1') {
      const nextParams = new URLSearchParams(searchParams);
      nextParams.delete('calendar_connected');
      setSearchParams(nextParams, { replace: true });
      toast.success('Google Calendar connected successfully! You can now schedule Google Meet meetings.');
    }
  }, [searchParams, setSearchParams]);
  
  const [searchTerm, setSearchTerm] = useState(() => {
    const userId = user?.id || 'default';
    return sessionStorage.getItem(`lqPipelineSearch_${userId}`) || '';
  });
  
  useEffect(() => {
    const userId = user?.id || 'default';
    sessionStorage.setItem(`lqPipelineSearch_${userId}`, searchTerm);
  }, [searchTerm, user]);

  const [globalLogs, setGlobalLogs] = useState([]);
  const [startDate, setStartDate] = useState(() => {
    const userId = user?.id || 'default';
    return sessionStorage.getItem(`lqPipelineStartDate_${userId}`) || '';
  });
  
  const [endDate, setEndDate] = useState(() => {
    const userId = user?.id || 'default';
    return sessionStorage.getItem(`lqPipelineEndDate_${userId}`) || '';
  });

  useEffect(() => {
    const userId = user?.id || 'default';
    sessionStorage.setItem(`lqPipelineStartDate_${userId}`, startDate);
    sessionStorage.setItem(`lqPipelineEndDate_${userId}`, endDate);
  }, [startDate, endDate, user]);
  
  const [selectedLq, setSelectedLq] = useState(() => {
    const userId = user?.id || 'default';
    const saved = sessionStorage.getItem(`lqPipelineEditing_${userId}`);
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch(e) {}
    }
    return null;
  });
  
  const [showWorkspace, setShowWorkspace] = useState(() => {
    const userId = user?.id || 'default';
    return sessionStorage.getItem(`lqPipelineFormOpen_${userId}`) === 'true';
  });

  useEffect(() => {
    const userId = user?.id || 'default';
    sessionStorage.setItem(`lqPipelineFormOpen_${userId}`, showWorkspace);
    if (selectedLq) {
      sessionStorage.setItem(`lqPipelineEditing_${userId}`, JSON.stringify(selectedLq));
    } else {
      sessionStorage.removeItem(`lqPipelineEditing_${userId}`);
    }
  }, [showWorkspace, selectedLq, user]);

  const [verificationFields, setVerificationFields] = useState({
    companyName: null,
    country: null,
    address: null,
    website: null,
    linkedIn: null,
    email: null,
    contactNo: null,
    productService: null
  });

  useEffect(() => {
    dispatch(fetchLqPipeline({ page }));
    api.get('/outreach/communications/')
       .then(res => setGlobalLogs(res.data.results || res.data))
       .catch(err => console.error('Failed to load global communications', err));

    // Real-time automatic updates every 8 seconds so tracker and activities update live
    const interval = setInterval(() => {
      dispatch(fetchLqPipeline({ page }));
      api.get('/outreach/communications/')
         .then(res => setGlobalLogs(res.data.results || res.data))
         .catch(() => {});
    }, 8000);
    return () => clearInterval(interval);
  }, [dispatch, page]);

  const sortedGlobalLogs = [...globalLogs].sort((a, b) => new Date(a.created_at) - new Date(b.created_at));
  
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  
  const startObj = startDate ? new Date(startDate) : null;
  if (startObj) startObj.setHours(0, 0, 0, 0);

  const endObj = endDate ? new Date(endDate) : null;
  if (endObj) endObj.setHours(23, 59, 59, 999);

  const filteredDashboardLogs = (startObj && endObj)
    ? sortedGlobalLogs.filter(log => {
        const d = new Date(log.created_at);
        return d >= startObj && d <= endObj;
      })
    : [];

  // Group by prospect
  const dashboardGrouped = {};
  filteredDashboardLogs.forEach(log => {
    if (!dashboardGrouped[log.prospect]) dashboardGrouped[log.prospect] = [];
    dashboardGrouped[log.prospect].push(log);
  });

  const groupedDashboardProspects = Object.keys(dashboardGrouped).map(prospectIdStr => {
    const prospectId = prospectIdStr;
    const logs = dashboardGrouped[prospectIdStr];
    
    // Fallback: If it's in `items` we can still open the modal, but we rely on the log data for name/date
    const lqItem = items.find(i => i.prospect?.id === prospectId);
    
    // We can just grab the company name and created date from the first log
    const companyName = logs[0]?.prospect_company_name || 'Unknown Company';
    const createdAt = logs[0]?.prospect_created_at || null;
    
    // Calculate breakdown
    const breakdown = {};
    logs.forEach(l => {
      breakdown[l.activity_type] = (breakdown[l.activity_type] || 0) + 1;
    });
    
    return {
      prospectId,
      lqItem,
      companyName,
      createdAt,
      logs,
      breakdown
    };
  });

  const filteredItems = items.filter(item => {
    // Submenu filter logic
    if (activeFilter === 'pending' && (item.verification_status !== 'Unverified' && item.verification_status !== 'In Progress')) return false;
    if (activeFilter === 'verified' && item.verification_status !== 'Verified') return false;
    if (activeFilter === 'issued' && item.pre_task_status !== 'ISSUE_SENT_TO_PRE') return false;

    if (searchTerm) {
      const s = searchTerm.toLowerCase();
      const p = item.prospect;
      return p.company_name?.toLowerCase().includes(s) || 
             p.country_head_office?.toLowerCase().includes(s) || 
             p.primary_industries?.toLowerCase().includes(s);
    }
    return true;
  });

  const pipelineCount = items.length;
  const preIssuesCount = items.filter(i => i.pre_task_status === 'ISSUE_SENT_TO_PRE').length;
  const verifiedCount = items.filter(i => i.verification_status === 'Verified').length;
  
  const todayStart = new Date();
  todayStart.setHours(0, 0, 0, 0);
  const todayLogs = globalLogs.filter(log => new Date(log.created_at) >= todayStart);
  
  const emailsSentTodayCount = todayLogs.filter(log => log.activity_type === 'EMAIL_SENT').length;
  const callsLoggedTodayCount = todayLogs.filter(log => log.activity_type === 'CALL' || log.activity_type === 'CALL_MADE').length;

  const [forcedWorkspaceTab, setForcedWorkspaceTab] = useState(null);
  const [correctedFields, setCorrectedFields] = useState([]);

  const openWorkspace = (lq, forceTab = null) => {
    setSelectedLq(lq);
    setForcedWorkspaceTab(forceTab);
    const savedChecklist = lq.verification_checklist || {};
    const isConfirming = lq.pre_task_status === 'PRE_UPDATED';
    
    const allFieldNames = [
      'companyName', 'country', 'address', 'website', 'linkedIn', 'email', 'contactNo', 
      'productService', 'primaryIndustries', 'companyStructure', 'operationalStatus', 
      'marketEvents', 'keyContacts', 'products', 'services', 'solutions'
    ];

    const mapToFormKeys = {
      companyName: 'company_name',
      country: 'country_head_office',
      address: 'complete_address',
      website: 'official_website_url',
      linkedIn: 'linkedin_company_page',
      email: 'official_email_address',
      contactNo: 'official_phone_number',
      productService: 'primary_offering_type',
      primaryIndustries: 'primary_industries',
      companyStructure: 'company_structure',
      operationalStatus: 'operational_status',
      marketEvents: 'market_event_ids',
      keyContacts: 'key_contacts',
      products: 'products',
      services: 'services',
      solutions: 'solutions'
    };
    
    // Find previously incorrect fields to highlight them
    const previouslyIncorrect = allFieldNames.filter(k => 
      savedChecklist[k] === 'Incorrect' || savedChecklist[mapToFormKeys[k]] === 'Incorrect'
    );
    setCorrectedFields(isConfirming ? previouslyIncorrect : []);
    
    const newFields = {};
    allFieldNames.forEach(key => {
      // Initialize with saved state. Previously incorrect fields will remain incorrect until manually verified by LQ
      if (savedChecklist[key] === 'Incorrect' || savedChecklist[mapToFormKeys[key]] === 'Incorrect') {
        newFields[key] = 'Incorrect';
      } else if (savedChecklist[key] === 'Correct' || savedChecklist[mapToFormKeys[key]] === 'Correct') {
        newFields[key] = 'Correct';
      } else {
        newFields[key] = 'Correct';
      }
    });
    
    setVerificationFields(newFields);
    setShowWorkspace(true);
  };

  const handleFieldToggle = (key, value) => {
    setVerificationFields(prev => ({ ...prev, [key]: value }));
  };

  // Derive issue status
  const incorrectFields = Object.keys(verificationFields).filter(key => verificationFields[key] === 'Incorrect');
  const allCorrect = Object.keys(verificationFields).every(key => verificationFields[key] === 'Correct');
  const hasIncorrect = incorrectFields.length > 0;
  
  const getFieldValue = (key) => {
    if (!selectedLq || !selectedLq.prospect) return '-';
    const p = selectedLq.prospect;
    switch (key) {
      case 'companyName': return p.company_name || '-';
      case 'country': return p.country_head_office || '-';
      case 'address': return p.complete_address || '-';
      case 'website': return p.official_website_url || '-';
      case 'linkedIn': return p.linkedin_company_page || '-';
      case 'email': return p.official_email_address || '-';
      case 'contactNo': return p.official_phone_number || '-';
      case 'productService': return p.primary_offering_type || '-';
      default: return '-';
    }
  };

  const fieldNames = {
    companyName: 'Company Name',
    country: 'Country',
    address: 'Address',
    website: 'Website',
    linkedIn: 'LinkedIn Page',
    email: 'Official Email',
    contactNo: 'Contact No.',
    productService: 'Product, Service & Solution',
    primaryIndustries: 'Primary Industries',
    companyStructure: 'Company Structure',
    operationalStatus: 'Operational Status',
    marketEvents: 'Market Events',
    keyContacts: 'Key Contacts',
    products: 'Products',
    services: 'Services',
    solutions: 'Solutions'
  };

  const incorrectNames = incorrectFields.map(key => fieldNames[key]);
  const autoCategory = incorrectNames.join(', ');
  const autoDetails = incorrectNames.length > 0 ? `The following fields are incorrect and need to be fixed by PRE:\n- ${incorrectNames.join('\n- ')}` : '';

  const handleSubmitIssue = () => {
    dispatch(reportIssueToPre({
      id: selectedLq.id,
      issueData: {
        issue_category: autoCategory,
        issue_details: autoDetails,
        verification_checklist: verificationFields
      }
    }));
    setShowWorkspace(false);
  };

  const handleReadyForOutreach = (stayOpen = false) => {
    dispatch(updateVerification({ 
      id: selectedLq.id, 
      verification_status: 'Verified',
      verification_checklist: verificationFields 
    })).then((action) => {
       if (action.payload && stayOpen) {
         setSelectedLq(action.payload);
       }
    });
    if (!stayOpen) {
      setShowWorkspace(false);
    }
  };

  const handleConfirmReverify = (item) => {
    openWorkspace(item, 'verification');
  };

  return (
    <div className="space-y-4 min-h-full flex-1 flex flex-col pb-2">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl p-5 md:p-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 relative overflow-hidden shadow-sm shrink-0">
        <div className="relative z-10">
          <h1 className="text-xl md:text-2xl font-black text-white tracking-tight mb-1">Outreach Workspace</h1>
          <p className="text-blue-100 text-xs max-w-2xl">Execute outreach communication, log call outcomes, and qualify opportunities.</p>
        </div>
      </div>

      {/* KPI Cards */}
      {!isManager && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="bg-white p-4 rounded-xl border border-emerald-200 bg-emerald-50/30 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-emerald-700">Outreached</span>
              <CheckCircle className="w-4 h-4 text-emerald-600" />
            </div>
            <p className="text-2xl font-black text-emerald-700 mt-1">{verifiedCount}</p>
          </div>
          <div className="bg-white p-4 rounded-xl border border-indigo-200 bg-indigo-50/30 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-indigo-800">Calls Logged (Today)</span>
              <Phone className="w-4 h-4 text-indigo-600" />
            </div>
            <p className="text-2xl font-black text-indigo-800 mt-1">{callsLoggedTodayCount}</p>
          </div>
          <div className="bg-white p-4 rounded-xl border border-sky-200 bg-sky-50/30 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-sky-800">Emails Sent (Today)</span>
              <Mail className="w-4 h-4 text-sky-600" />
            </div>
            <p className="text-2xl font-black text-sky-800 mt-1">{emailsSentTodayCount}</p>
          </div>
        </div>
      )}

      {/* Global Activity Dashboard */}
      {!isManager && (
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden p-6">
          <div className="flex items-center gap-4 mb-4">
            <div className="w-10 h-10 rounded-xl bg-indigo-50 flex items-center justify-center shrink-0">
              <Activity className="w-5 h-5 text-indigo-600" />
            </div>
            <div className="flex-1">
              <h2 className="text-lg font-black text-slate-800">Global Activity Dashboard</h2>
              <p className="text-xs font-semibold text-slate-500">Track outreach history across all prospects by date range.</p>
            </div>
            <div className="flex items-center gap-1.5 bg-white border border-slate-200 rounded-xl shadow-sm px-1.5 py-1">
              <label className="text-[10px] font-extrabold text-slate-500 uppercase tracking-wider pl-1.5 pr-1">Date Range:</label>
              <input 
                type="date" 
                value={startDate}
                max={new Date().toISOString().split('T')[0]}
                onChange={(e) => {
                  setStartDate(e.target.value);
                  setEndDate('');
                }}
                className="px-2 py-1 bg-slate-50 rounded text-sm font-bold focus:outline-none focus:ring-2 focus:ring-indigo-500/30 text-slate-700"
              />
              <span className="text-slate-400 font-bold text-xs px-1">to</span>
              <input 
                type="date" 
                max="9999-12-31"
                min={startDate || undefined}
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                disabled={!startDate}
                className="px-2 py-1 bg-slate-50 rounded text-sm font-bold focus:outline-none focus:ring-2 focus:ring-indigo-500/30 text-slate-700 disabled:opacity-50"
              />
            </div>
          </div>

          {startDate && endDate ? (
            <div className="space-y-3 max-h-[500px] overflow-y-auto pr-2">
              {groupedDashboardProspects.length > 0 ? (
                groupedDashboardProspects.map(group => {
                  return (
                    <div 
                      key={group.prospectId} 
                      className="bg-slate-50 border border-slate-200 rounded-xl overflow-hidden transition-all duration-200 shadow-sm px-4 py-2.5 flex items-center justify-between cursor-pointer hover:bg-indigo-50/50 hover:border-indigo-100 group"
                      onClick={() => navigate(`/outreach-activity/${group.prospectId}`)}
                    >
                      <div className="flex items-center gap-3">
                        <div>
                          <h4 className="font-extrabold text-slate-900 text-sm group-hover:text-indigo-700 transition-colors">{group.companyName}</h4>
                          <p className="text-[10px] font-semibold text-slate-500 mt-0.5">
                            {Object.entries(group.breakdown).map(([type, count]) => `${count} ${type.replace('_MADE', '').replace('_SENT', '')}`).join(' • ')}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center gap-3">
                        <span className="text-xs font-bold text-indigo-600 opacity-0 group-hover:opacity-100 transition-opacity">View Timeline &rarr;</span>
                      </div>
                    </div>
                  );
                })
              ) : (
                <div className="p-6 text-center border-2 border-dashed border-slate-200 rounded-xl bg-slate-50/50">
                  <p className="text-sm font-semibold text-slate-500">No activities recorded in this date range.</p>
                </div>
              )}
            </div>
          ) : (
            <div className="p-8 text-center border-2 border-dashed border-slate-200 rounded-xl bg-slate-50/50">
              <Activity className="w-8 h-8 text-slate-300 mx-auto mb-2" />
              <p className="text-sm font-semibold text-slate-500">
                Please select both a Start Date and an End Date to view activities.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Table Container */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden flex-1 flex flex-col min-h-0">
        <div className="p-3 border-b border-slate-200/80 bg-slate-50/70 flex flex-col md:flex-row md:items-center justify-between gap-3 shrink-0">
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5 flex-1">
            <div className="relative flex-1 max-w-md">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <Search className="h-3.5 w-3.5 text-slate-400" />
              </div>
              <input 
                type="text" 
                placeholder="Filter by master prospect name, country, industry..." 
                className="w-full pl-9 pr-8 py-1.5 bg-white border border-slate-200 rounded-xl text-xs font-medium text-slate-800 placeholder-slate-400 shadow-2xs hover:border-slate-300 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
              {searchTerm && (
                <button
                  type="button"
                  onClick={() => setSearchTerm('')}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 p-0.5 rounded-full hover:bg-slate-100 transition"
                  title="Clear filter"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>

            {/* Quick Status Sub-filters */}
            <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5">
              <button
                type="button"
                onClick={() => handleFilterChange('all')}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold transition cursor-pointer shrink-0 ${
                  activeFilter === 'all'
                    ? 'bg-indigo-600 text-white shadow-2xs'
                    : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'
                }`}
              >
                All Outreach ({items.length})
              </button>
              <button
                type="button"
                onClick={() => handleFilterChange('verified')}
                className={`px-3 py-1.5 rounded-xl text-xs font-bold transition cursor-pointer flex items-center gap-1.5 shrink-0 ${
                  activeFilter === 'verified'
                    ? 'bg-emerald-600 text-white shadow-2xs'
                    : 'bg-white text-slate-600 border border-slate-200 hover:bg-slate-50'
                }`}
              >
                <span>Outreached</span>
                <span className={`px-1.5 py-0.2 rounded-full text-[10px] ${
                  activeFilter === 'verified' ? 'bg-emerald-700 text-white' : 'bg-emerald-100 text-emerald-800'
                }`}>
                  {verifiedCount}
                </span>
              </button>
            </div>
          </div>

          <div className="text-xs font-semibold text-slate-500 bg-white px-3 py-1.5 rounded-xl border border-slate-200 shadow-2xs shrink-0 self-end sm:self-auto">
            Total Records: <span className="font-bold text-slate-800">{filteredItems.length}</span>
          </div>
        </div>

        <div className="overflow-x-auto flex-1">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 font-bold uppercase tracking-wider text-[10px]">
                <th className="px-3.5 py-2">Prospect & Company Details</th>
                <th className="px-3.5 py-2">Status</th>
                {!isManager && <th className="px-3.5 py-2 text-right">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredItems.length === 0 ? (
                <tr>
                  <td colSpan={isManager ? 2 : 3} className="p-8 text-center text-slate-500 bg-slate-50">
                    <div className="flex flex-col items-center justify-center">
                      <div className="w-10 h-10 bg-white rounded-full flex items-center justify-center shadow-sm border border-slate-100 mb-2">
                        <Activity className="w-5 h-5 text-slate-400" />
                      </div>
                      <span className="text-sm font-bold text-slate-700">No records found</span>
                      <p className="text-xs text-slate-500 mt-0.5">There are currently no prospects matching your criteria.</p>
                    </div>
                  </td>
                </tr>
              ) : (
                filteredItems.map(item => {
                  const p = item.prospect;
                  const isLeadFreeze = item.qualification_status === 'Lead Freeze';
                  const isLeadQualified = item.qualification_status === 'Lead Qualified';

                  return (
                    <tr key={item.id} className="hover:bg-slate-50/80 transition">
                      <td className="px-3.5 py-2">
                        <div className="flex items-start gap-2.5">
                          <div className="w-7 h-7 rounded-lg bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center shrink-0 mt-0.5">
                            <Building2 className="w-4 h-4" />
                          </div>
                          <div>
                            <Link to={`/lq-pipeline/${item.id}`} className="font-bold text-indigo-600 hover:text-indigo-800 hover:underline text-xs transition">
                              {p.company_name}
                            </Link>
                            <p className="text-[10px] text-slate-500 truncate max-w-md" title={p.primary_industries || ''}>
                              {p.country_head_office} &bull; {p.primary_industries || '—'}
                            </p>
                            <div className="flex items-center gap-2 mt-1">
                              <span className="text-[9px] font-bold text-slate-600 bg-slate-100 px-1.5 py-0.2 rounded-md border border-slate-200">
                                Calls Logged: {item.calls_logged_count || 0}
                              </span>
                              <span className="text-[9px] font-bold text-slate-600 bg-slate-100 px-1.5 py-0.2 rounded-md border border-slate-200">
                                Emails Sent: {item.emails_sent_count || 0}
                              </span>
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="px-3.5 py-2">
                        {isLeadQualified ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md font-semibold text-[10px] bg-emerald-50 text-emerald-700 border border-emerald-200">
                            <CheckCircle className="w-3 h-3 text-emerald-600" /> Lead Qualified
                          </span>
                        ) : isLeadFreeze ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md font-semibold text-[10px] bg-rose-50 text-rose-700 border border-rose-200">
                            <XCircle className="w-3 h-3 text-rose-600" /> Lead Freeze
                          </span>
                        ) : item.email_status && item.email_status !== 'Not Sent' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md font-semibold text-[10px] bg-blue-50 text-blue-700 border border-blue-200">
                            <Mail className="w-3 h-3 text-blue-600" /> {item.email_status}
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md font-semibold text-[10px] bg-indigo-50 text-indigo-700 border border-indigo-200">
                            <Phone className="w-3 h-3 text-indigo-600" /> Ready for Outreach
                          </span>
                        )}
                      </td>
                      {!isManager && (
                        <td className="px-3.5 py-2 text-right">
                          <button
                            onClick={() => openWorkspace(item)}
                            disabled={isLeadFreeze}
                            title={isLeadFreeze ? 'Outreach disabled — Prospect is Lead Freeze' : ''}
                            className={`w-28 justify-center px-2.5 py-1 rounded text-[10px] font-bold transition flex items-center gap-1 ml-auto cursor-pointer ${
                              isLeadFreeze 
                                ? 'bg-slate-200 text-slate-400 cursor-not-allowed' 
                                : isLeadQualified 
                                ? 'bg-emerald-600 hover:bg-emerald-700 text-white' 
                                : 'bg-indigo-600 hover:bg-indigo-700 text-white'
                            }`}
                          >
                            {isLeadFreeze ? (
                              <><XCircle className="w-3 h-3 text-white" /><span>Lead Freeze</span></>
                            ) : isLeadQualified ? (
                              <><CheckCircle className="w-3.5 h-3.5 text-white" /> <span>Qualified</span></>
                            ) : (
                              <><Phone className="w-3 h-3" /> Outreach</>
                            )}
                          </button>
                        </td>
                      )}
                    </tr>
                );
              }))}
            </tbody>
          </table>
        </div>
        <Pagination 
          currentPage={page} 
          totalCount={count} 
          pageSize={50} 
          onPageChange={(newPage) => dispatch(setPage(newPage))} 
        />
      </div>

      {/* Workspace Modal */}
      {showWorkspace && selectedLq && (
        <LqWorkspaceModal
          selectedLq={selectedLq}
          initialTab="outreach"
          onClose={() => { setShowWorkspace(false); dispatch(fetchLqPipeline()); }}
          hasIncorrect={hasIncorrect}
          allCorrect={allCorrect}
          verificationFields={verificationFields}
          handleFieldToggle={handleFieldToggle}
          handleSubmitIssue={handleSubmitIssue}
          handleReadyForOutreach={handleReadyForOutreach}
          isConfirmingFixes={false}
          correctedFields={correctedFields}
        />
      )}
    </div>
  );
};

export default LqPipelinePage;
