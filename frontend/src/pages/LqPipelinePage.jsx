import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { 
  Building2, AlertTriangle, CheckCircle, Phone, Search, 
  CheckCircle2, AlertCircle, PlayCircle, RefreshCw,
  FileEdit, Mail, XCircle, Activity, Calendar, ChevronDown, ChevronUp
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

const LqPipelinePage = ({ filter = 'all' }) => {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
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

    // Auto-refresh every 30 seconds so new prospect assignments appear without manual refresh
    const interval = setInterval(() => {
      dispatch(fetchLqPipeline({ page }));
    }, 30000);
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
    if (filter === 'pending' && (item.verification_status !== 'Unverified' && item.verification_status !== 'In Progress')) return false;
    if (filter === 'verified' && item.verification_status !== 'Verified') return false;
    if (filter === 'issued' && item.pre_task_status !== 'ISSUE_SENT_TO_PRE') return false;

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
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl p-6 md:p-8 flex flex-col md:flex-row items-start md:items-center justify-between gap-6 relative overflow-hidden shadow-sm">
        <div className="relative z-10">

          <h1 className="text-2xl md:text-3xl font-black text-white tracking-tight mb-2">Lead Verification & Outreach Workspace</h1>
          <p className="text-blue-100 text-sm max-w-2xl">Review and verify prospect master data, qualify opportunities, and continue the lead qualification workflow.</p>
        </div>
      </div>

      {/* KPI Cards */}
      {!isManager && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-slate-500">LQ Pipeline Prospects</span>
              <Building2 className="w-4 h-4 text-slate-400" />
            </div>
            <p className="text-2xl font-black text-slate-900 mt-1">{pipelineCount}</p>
          </div>
          <div className="bg-white p-4 rounded-xl border border-amber-200 bg-amber-50/30 shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-amber-900">Issues Sent to PRE</span>
              <AlertTriangle className="w-4 h-4 text-amber-600" />
            </div>
            <p className="text-2xl font-black text-amber-900 mt-1">{preIssuesCount}</p>
          </div>
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

      {/* PRE Updated Confirmation Banner for LQ */}
      {!isManager && items.some(i => i.pre_task_status === 'PRE_UPDATED') && (
        <div className="bg-emerald-50 border-2 border-emerald-300 rounded-2xl p-4 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3 animate-in fade-in">
          <div className="flex items-start gap-3">
            <div className="w-9 h-9 rounded-xl bg-emerald-100 text-emerald-700 flex items-center justify-center shrink-0 mt-0.5">
              <CheckCircle className="w-5 h-5 text-emerald-600" />
            </div>
            <div>
              <h4 className="font-black text-emerald-950 text-sm flex items-center gap-2">
                <span>PRE Has Completed Data Updates</span>
                <span className="px-2 py-0.5 rounded-full bg-emerald-200 text-emerald-900 text-[10px] font-extrabold uppercase">
                  {items.filter(i => i.pre_task_status === 'PRE_UPDATED').length} Prospect(s) Ready
                </span>
              </h4>
              <p className="text-xs text-emerald-800 mt-1">
                PRE has updated the missing information (such as missing email addresses) for {items.filter(i => i.pre_task_status === 'PRE_UPDATED').map(i => i.prospect?.company_name).filter(Boolean).slice(0, 3).join(', ')}{items.filter(i => i.pre_task_status === 'PRE_UPDATED').length > 3 ? '...' : ''}. Click &quot;Confirm Fixes&quot; on the record to review and proceed with outreach.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Table Container */}
      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="p-4 border-b border-slate-200 space-y-3">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-center gap-3 flex-1">
              <div className="relative flex-1 max-w-md">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input 
                  type="text" 
                  placeholder="Filter by master prospect name, country, industry..." 
                  className="w-full pl-9 pr-4 py-2 bg-slate-50 border border-slate-200 rounded-xl text-sm"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
            </div>
          </div>
        </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 font-bold uppercase tracking-wider text-[10px]">
                <th className="p-3.5">Master Prospect & PRE Data</th>
                <th className="p-3.5">PRE Task Status</th>
                <th className="p-3.5">Verification Status</th>
                {!isManager && <th className="p-3.5 text-right">Actions</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredItems.length === 0 ? (
                <tr>
                  <td colSpan={isManager ? 3 : 4} className="p-12 text-center text-slate-500 bg-slate-50">
                    <div className="flex flex-col items-center justify-center">
                      <div className="w-12 h-12 bg-white rounded-full flex items-center justify-center shadow-sm border border-slate-100 mb-3">
                        <Activity className="w-6 h-6 text-slate-400" />
                      </div>
                      <span className="text-base font-bold text-slate-700">No records found</span>
                      <p className="text-sm text-slate-500 mt-1">There are currently no prospects matching your criteria.</p>
                    </div>
                  </td>
                </tr>
              ) : (
                filteredItems.map(item => {
                  const p = item.prospect;
                const isIssue = item.pre_task_status === 'ISSUE_SENT_TO_PRE';
                const isUpdated = item.pre_task_status === 'PRE_UPDATED';
                const isLeadFreeze = item.qualification_status === 'Lead Freeze';
                const isLeadQualified = item.qualification_status === 'Lead Qualified';

                return (
                  <tr key={item.id} className="hover:bg-slate-50/80 transition">
                    <td className="p-3.5">
                      <div className="flex items-start gap-3">
                        <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-100 text-indigo-600 flex items-center justify-center shrink-0 mt-0.5">
                          <Building2 className="w-5 h-5" />
                        </div>
                        <div>
                          <Link to={`/lq-pipeline/${item.id}`} className="font-bold text-indigo-600 hover:text-indigo-800 hover:underline text-sm transition">
                            {p.company_name}
                          </Link>
                          <p className="text-[11px] text-slate-500 mt-0.5">
                            {p.country_head_office} &bull; {p.primary_industries}
                          </p>
                          <div className="flex items-center gap-3 mt-1.5">
                            <span className="text-[10px] font-bold text-slate-600 bg-slate-100 px-2 py-0.5 rounded-xl border border-slate-200">
                              Calls Logged: {item.calls_logged_count || 0}
                            </span>
                            <span className="text-[10px] font-bold text-slate-600 bg-slate-100 px-2 py-0.5 rounded-xl border border-slate-200">
                              Emails Sent: {item.emails_sent_count || 0}
                            </span>
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="p-3.5">
                      {isIssue && (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-amber-50 text-amber-700 border border-amber-200 font-semibold text-[10px]">
                          <AlertTriangle className="w-3 h-3" /> Issue Sent to PRE
                        </span>
                      )}
                      {isUpdated && (
                        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-xl bg-slate-100 text-slate-700 border border-slate-200 font-semibold text-[10px]">
                          <RefreshCw className="w-3 h-3 text-emerald-500" /> PRE Updated Data
                        </span>
                      )}
                      {!isIssue && !isUpdated && <span className="text-slate-400 italic text-[10px]">None</span>}
                    </td>
                    <td className="p-3.5">
                      <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md font-semibold text-[10px] border ${
                        item.verification_status === 'Verified' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' :
                        'bg-slate-50 text-slate-600 border-slate-200'
                      }`}>
                        {item.verification_status}
                      </span>
                    </td>
                    {!isManager && (
                      <td className="p-3.5 text-right">
                        {isUpdated ? (
                          <button
                            onClick={() => handleConfirmReverify(item)}
                            className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-[11px] font-bold transition flex items-center gap-1 ml-auto"
                          >
                            <CheckCircle className="w-3 h-3" /> Confirm Fixes
                          </button>
                        ) : (
                          <button
                            onClick={() => openWorkspace(item)}
                            disabled={isLeadFreeze}
                            title={isLeadFreeze ? 'Outreach disabled — Prospect is Lead Freeze' : ''}
                            className={`w-32 justify-center px-3 py-1.5 rounded text-[11px] font-bold transition flex items-center gap-1 ml-auto ${
                              isLeadFreeze ? 'bg-slate-200 text-slate-400 cursor-not-allowed' : 
                              isLeadQualified ? 'bg-emerald-600 hover:bg-emerald-700 text-white' :
                              isIssue ? 'bg-amber-600 hover:bg-amber-700 text-white' :
                              item.verification_status === 'Verified' ? 'bg-indigo-600 hover:bg-indigo-700 text-white' : 
                              'bg-slate-800 hover:bg-slate-900 text-white'
                            }`}
                          >
                            {isLeadFreeze ? (
                              <><XCircle className="w-3 h-3 text-white" /><span>Lead Freeze</span></>
                            ) : isLeadQualified ? (
                              <><CheckCircle className="w-4 h-4 text-white" /> <span>Lead Qualified</span></>
                            ) : item.verification_status === 'Verified' ? (
                              <><Phone className="w-3 h-3" /> Outreach</>
                            ) : (
                              <><FileEdit className="w-3 h-3" /> Verify</>
                            )}
                          </button>
                        )}
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
          initialTab={forcedWorkspaceTab || (selectedLq.verification_status === 'Verified' ? 'outreach' : 'verification')}
          onClose={() => { setShowWorkspace(false); dispatch(fetchLqPipeline()); }}
          hasIncorrect={hasIncorrect}
          allCorrect={allCorrect}
          verificationFields={verificationFields}
          handleFieldToggle={handleFieldToggle}
          handleSubmitIssue={handleSubmitIssue}
          handleReadyForOutreach={handleReadyForOutreach}
          isConfirmingFixes={selectedLq.pre_task_status === 'PRE_UPDATED'}
          correctedFields={correctedFields}
        />
      )}
    </div>
  );
};

export default LqPipelinePage;
