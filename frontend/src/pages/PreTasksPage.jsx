import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { fetchLqPipeline, completePreTask } from '../features/lqPipeline/lqPipelineSlice';
import ProspectForm from '../components/prospects/ProspectForm';
import SearchableSelect from '../components/common/SearchableSelect';
import { AlertTriangle, CheckCircle, FileEdit, Building2, Mail, MessageSquare, ChevronDown, ChevronUp } from 'lucide-react';
import { toast } from 'react-toastify';
import api from '../services/api';

const PreTasksPage = () => {
  const dispatch = useDispatch();
  const { items, loading } = useSelector((state) => state.lqPipeline);
  const { user } = useSelector((state) => state.auth);
  const isManager = user?.role === 'MANAGER';
  
  const [editingProspect, setEditingProspect] = useState(() => {
    const userId = user?.id || 'default';
    const saved = sessionStorage.getItem(`preTasksEditing_${userId}`);
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch(e) {}
    }
    return null;
  });
  
  const [isFormOpen, setIsFormOpen] = useState(() => {
    const userId = user?.id || 'default';
    return sessionStorage.getItem(`preTasksFormOpen_${userId}`) === 'true';
  });
  
  const [hasEdited, setHasEdited] = useState(false);
  const [highlightFields, setHighlightFields] = useState([]);
  
  const [activeTaskId, setActiveTaskId] = useState(() => {
    const userId = user?.id || 'default';
    const saved = sessionStorage.getItem(`preTasksActiveTask_${userId}`);
    return saved ? parseInt(saved, 10) : null;
  });

  const [activeTab, setActiveTab] = useState(() => {
    const userId = user?.id || 'default';
    return sessionStorage.getItem(`preTasksActiveTab_${userId}`) || 'PENDING';
  });
  
  useEffect(() => {
    const userId = user?.id || 'default';
    sessionStorage.setItem(`preTasksFormOpen_${userId}`, isFormOpen);
    sessionStorage.setItem(`preTasksActiveTab_${userId}`, activeTab);
    
    if (editingProspect) {
      sessionStorage.setItem(`preTasksEditing_${userId}`, JSON.stringify(editingProspect));
    } else {
      sessionStorage.removeItem(`preTasksEditing_${userId}`);
    }
    
    if (activeTaskId) {
      sessionStorage.setItem(`preTasksActiveTask_${userId}`, activeTaskId.toString());
    } else {
      sessionStorage.removeItem(`preTasksActiveTask_${userId}`);
    }
  }, [isFormOpen, editingProspect, activeTaskId, activeTab, user]);

  const [startDate, setStartDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [endDate, setEndDate] = useState(() => new Date().toISOString().split('T')[0]);
  const [managerUserFilter, setManagerUserFilter] = useState('ALL');

  // Automated PRE Tasks (Incoming Email Replies & WhatsApp Escalations)
  const [preTasks, setPreTasks] = useState([]);
  const [preTasksLoading, setPreTasksLoading] = useState(false);
  const [expandedPreTaskId, setExpandedPreTaskId] = useState(null);
  const [completingPreTaskId, setCompletingPreTaskId] = useState(null);

  const loadPreTasks = async () => {
    setPreTasksLoading(true);
    try {
      const res = await api.get('/pre-tasks/', { params: { status: activeTab } });
      const data = Array.isArray(res.data) ? res.data : (res.data?.results || []);
      setPreTasks(data);
    } catch (err) {
      console.error('Failed to load PRE tasks', err);
    } finally {
      setPreTasksLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'PENDING') {
      dispatch(fetchLqPipeline({ pre_task_status: 'ISSUE_SENT_TO_PRE' }));
    } else {
      // Fetch all tasks for the user so we can see historically completed tasks
      dispatch(fetchLqPipeline({}));
    }
    loadPreTasks();
  }, [dispatch, activeTab]);

  const handleCompletePreTaskItem = async (taskId) => {
    setCompletingPreTaskId(taskId);
    try {
      await api.post(`/pre-tasks/${taskId}/complete/`);
      toast.success('Task marked as completed.');
      loadPreTasks();
    } catch (err) {
      toast.error(err?.response?.data?.error || 'Failed to complete task.');
    } finally {
      setCompletingPreTaskId(null);
    }
  };

  const filteredPreTasks = isManager && managerUserFilter !== 'ALL'
    ? preTasks.filter((t) => t.assigned_pre_username === managerUserFilter)
    : preTasks;

  // Filter tasks locally based on tab and date
  let tasks = [];
  if (activeTab === 'PENDING') {
    tasks = items.filter(item => item.pre_task_status === 'ISSUE_SENT_TO_PRE');
  } else if (activeTab === 'COMPLETED') {
    tasks = items.flatMap(item => {
      // Use completed_tasks_log if available for an accurate history
      const log = item.completed_tasks_log || [];
      if (log.length > 0) {
        return log.map(logEntry => {
          const itemDate = logEntry.completed_at ? logEntry.completed_at.split('T')[0] : '';
          let inRange = true;
          if (startDate) inRange = inRange && itemDate >= startDate;
          if (endDate) inRange = inRange && itemDate <= endDate;
          
          if (!inRange) return null;

          return {
            id: logEntry.id,
            isHistoricalLog: true,
            issue_category: logEntry.issue_category,
            issue_details: logEntry.issue_details,
            completed_at: logEntry.completed_at,
            prospect: {
              ...item.prospect,
              created_by: item.prospect?.created_by || logEntry.issue_reported_by // fallback
            }
          };
        }).filter(Boolean);
      }
      
      // Fallback for legacy completed tasks that didn't generate a log
      if (item.pre_task_status === 'ISSUE_SENT_TO_PRE') return [];
      const dateToUse = item.updated_at || item.created_at;
      if (!dateToUse) return [];
      const itemDate = new Date(dateToUse).toISOString().split('T')[0];
      
      let inRange = true;
      if (startDate) inRange = inRange && itemDate >= startDate;
      if (endDate) inRange = inRange && itemDate <= endDate;
      return inRange ? [item] : [];
    });
  }

  const availableUsers = Array.from(
    new Set([
      ...tasks.map((t) => t.prospect?.created_by),
      ...preTasks.map((t) => t.assigned_pre_username),
    ])
  ).filter(Boolean);
  
  const filteredTasks = isManager && managerUserFilter !== 'ALL'
    ? tasks.filter(t => t.prospect?.created_by === managerUserFilter)
    : tasks;

  const handleOpenProspect = (task) => {
    setEditingProspect(task.prospect);
    setActiveTaskId(task.id);
    
    // Extract incorrect fields from the verification checklist
    const checklist = task.verification_checklist || {};
    const incorrects = Object.keys(checklist).filter(key => checklist[key] === 'Incorrect');
    
    // Map them to the formData keys used in ProspectForm
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
      solutions: 'solutions',
      parent_companies_detail: 'parent_companies',
      market_events: 'market_event_ids'
    };
    
    const mappedFields = incorrects.map(k => mapToFormKeys[k] || k).filter(Boolean);
    setHighlightFields(mappedFields);
    
    setHasEdited(false); // Reset to false until they actually submit the form
    setIsFormOpen(true);
  };

  const handleCompleteTask = (lqId) => {
    dispatch(completePreTask(lqId)).then(() => {
      toast.success('Task marked as completed! Confirmation notification sent to LQ.');
      // Re-fetch the list to remove the completed task
      dispatch(fetchLqPipeline({ pre_task_status: 'ISSUE_SENT_TO_PRE' }));
    });
  };

  return (
    <div className="space-y-4 min-h-full flex-1 flex flex-col pb-2">

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white p-3 rounded-2xl shadow-xs border border-slate-200/80 shrink-0">
        <div className="flex bg-slate-100 p-0.5 rounded-xl">
          <button
            onClick={() => setActiveTab('PENDING')}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition ${activeTab === 'PENDING' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-500 hover:text-slate-900'}`}
          >
            Pending Tasks
          </button>
          <button
            onClick={() => setActiveTab('COMPLETED')}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition ${activeTab === 'COMPLETED' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-500 hover:text-slate-900'}`}
          >
            Completed Tasks
          </button>
        </div>
        
        {activeTab === 'COMPLETED' && (
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-1.5">
              <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">From:</label>
              <input
                type="date"
                className="bg-slate-50 border border-slate-200 text-slate-800 text-xs rounded-xl p-1.5 font-medium"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                max={new Date().toISOString().split('T')[0]}
              />
            </div>
            <div className="flex items-center gap-1.5">
              <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">To:</label>
              <input
                type="date"
                className="bg-slate-50 border border-slate-200 text-slate-800 text-xs rounded-xl p-1.5 font-medium"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                max={new Date().toISOString().split('T')[0]}
              />
            </div>
          </div>
        )}

        {isManager && availableUsers.length > 0 && (
          <div className="flex items-center gap-2 ml-auto">
            <label className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Assigned User:</label>
            <div className="w-48"><SearchableSelect
              value={managerUserFilter}
              onChange={(val) => setManagerUserFilter(val)}
              options={[{value: 'ALL', label: 'All Users'}, ...availableUsers.map(u => ({value: u, label: u}))]}
            /></div>
          </div>
        )}
      </div>

      <div className="bg-white rounded-2xl shadow-xs border border-slate-200/80 overflow-hidden flex-1 flex flex-col min-h-0">
        <div className="overflow-x-auto flex-1">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-slate-50/80 text-slate-500 font-bold uppercase tracking-wider text-[10px] border-b border-slate-100">
                <th className="px-3.5 py-2">Reported Prospect</th>
                <th className="px-3.5 py-2">Issue Details</th>
                {isManager && <th className="px-3.5 py-2">Assignment Info</th>}
                <th className="px-3.5 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td colSpan={isManager ? 4 : 3} className="p-8 text-center text-slate-500">Loading tasks...</td>
                </tr>
              ) : filteredTasks.length === 0 ? (
                <tr>
                  <td colSpan={isManager ? 4 : 3} className="p-8 text-center text-slate-500">
                    <CheckCircle className="w-8 h-8 mx-auto text-emerald-400 mb-2" />
                    {activeTab === 'PENDING' ? 'No pending correction tasks!' : 'No completed tasks found for this date range.'}
                  </td>
                </tr>
              ) : filteredTasks.map(task => (
                <tr key={task.id} className="hover:bg-slate-50/80 transition">
                  <td className="px-3.5 py-2.5 align-top">
                    <div className="flex items-start gap-2.5">
                      <div className="w-7 h-7 rounded-lg bg-indigo-50 border border-indigo-100 text-indigo-700 font-black text-xs flex items-center justify-center shrink-0 mt-0.5">
                        <Building2 className="w-3.5 h-3.5" />
                      </div>
                      <div>
                        <div className="font-bold text-slate-900 text-xs">{task.prospect.company_name}</div>
                        <p className="text-[10px] text-slate-500">
                          {task.prospect.country_head_office} &bull; {task.prospect.primary_industries}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td className="px-3.5 py-2.5 align-top max-w-md">
                    <div className={`p-2 rounded-lg border text-xs ${activeTab === 'COMPLETED' ? 'bg-emerald-50 border-emerald-100 text-emerald-900' : 'bg-red-50 border-red-100 text-red-900'}`}>
                      <span className={`font-bold block mb-0.5 text-[11px] ${activeTab === 'COMPLETED' ? 'text-emerald-700' : 'text-red-700'}`}>Category: {task.issue_category}</span>
                      <p className="whitespace-pre-wrap font-mono text-[10px] leading-relaxed">{task.issue_details}</p>
                    </div>
                  </td>
                  {isManager && (
                    <td className="px-3.5 py-2.5 align-top">
                      <div className="flex flex-col gap-1">
                        <div className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-indigo-50 border border-indigo-100 w-max">
                          <span className="text-[9px] font-bold text-indigo-700 uppercase">Assigned User:</span>
                          <span className="text-[10px] font-bold text-slate-800">{task.prospect.created_by || 'Unknown'}</span>
                        </div>
                        <div className="text-[9px] text-slate-500 font-medium">
                          Assigned on: {task.issue_reported_at ? new Date(task.issue_reported_at).toLocaleDateString() : 'N/A'}
                        </div>
                      </div>
                    </td>
                  )}
                  <td className="px-3.5 py-2.5 align-top text-right">
                    <div className="flex flex-col gap-1.5 items-end">
                      <button
                        onClick={() => handleOpenProspect(task)}
                        className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-[10px] font-bold transition flex items-center gap-1 shadow-2xs"
                      >
                        <FileEdit className="w-3 h-3" /> {isManager ? 'View Prospect' : 'Open Prospect'}
                      </button>
                      {!isManager && activeTab === 'PENDING' && (
                        <button
                          onClick={() => handleCompleteTask(task.id)}
                          disabled={!hasEdited || activeTaskId !== task.id}
                          className={`px-3 py-1.5 rounded-lg text-[10px] font-bold transition flex items-center gap-1 shadow-2xs ${
                            (hasEdited && activeTaskId === task.id) ? 'bg-emerald-600 hover:bg-emerald-700 text-white' : 'bg-slate-100 text-slate-400 cursor-not-allowed'
                          }`}
                        >
                          <CheckCircle className="w-3 h-3" /> Complete Task
                        </button>
                      )}
                      {!isManager && activeTab === 'COMPLETED' && (
                        <div className="px-3 py-1 bg-emerald-50 text-emerald-700 rounded-lg text-[10px] font-bold border border-emerald-200 flex items-center gap-1 w-max justify-center shadow-2xs">
                          <CheckCircle className="w-3 h-3" /> Completed
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Email Reply & WhatsApp Escalation PRE Tasks */}
      <div className="bg-white rounded-2xl shadow-xs border border-slate-200/80 overflow-hidden mt-3">
        <div className="px-4 py-2.5 bg-slate-50/90 border-b border-slate-100 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Mail className="w-4 h-4 text-indigo-600" />
            <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider">
              {activeTab === 'COMPLETED' ? 'Completed AI & Email Follow-up Tasks' : 'Email Reply & WhatsApp Escalation Tasks'}
            </h3>
            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-100">
              {filteredPreTasks.length}
            </span>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-slate-50/60 text-slate-500 font-bold uppercase tracking-wider text-[10px] border-b border-slate-100">
                <th className="px-3.5 py-2">Source & Contact</th>
                <th className="px-3.5 py-2">Task & Conversation History</th>
                {isManager && <th className="px-3.5 py-2">Assigned User</th>}
                <th className="px-3.5 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {preTasksLoading ? (
                <tr>
                  <td colSpan={isManager ? 4 : 3} className="p-6 text-center text-slate-500">Loading tasks...</td>
                </tr>
              ) : filteredPreTasks.length === 0 ? (
                <tr>
                  <td colSpan={isManager ? 4 : 3} className="p-6 text-center text-slate-500 text-xs">
                    {activeTab === 'PENDING'
                      ? 'No pending email reply or WhatsApp escalation tasks.'
                      : 'No completed email reply or WhatsApp escalation tasks.'}
                  </td>
                </tr>
              ) : filteredPreTasks.map((pt) => {
                const isExpanded = expandedPreTaskId === pt.id;
                const isEmailReply = pt.task_type === 'EMAIL_REPLY';
                const history = Array.isArray(pt.conversation_history) ? pt.conversation_history : [];
                return (
                  <tr key={pt.id} className="hover:bg-slate-50/70 transition">
                    <td className="px-3.5 py-2.5 align-top min-w-[200px]">
                      <div className="flex flex-col gap-1">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold w-max border ${
                          isEmailReply
                            ? 'bg-sky-50 text-sky-700 border-sky-200'
                            : 'bg-emerald-50 text-emerald-700 border-emerald-200'
                        }`}>
                          {isEmailReply ? <Mail className="w-3 h-3" /> : <MessageSquare className="w-3 h-3" />}
                          {isEmailReply ? 'Email Reply' : 'WhatsApp Escalation'}
                        </span>
                        <div className="font-bold text-slate-900 text-xs mt-0.5">
                          {pt.prospect_company_name || pt.company_name || 'Unlinked Contact'}
                        </div>
                        <div className="text-[11px] text-slate-600">
                          {pt.sender_name || 'Unknown Sender'}
                        </div>
                        {pt.sender_email && (
                          <div className="text-[10px] text-slate-500">{pt.sender_email}</div>
                        )}
                        {pt.sender_phone && (
                          <div className="text-[10px] text-slate-500">{pt.sender_phone}</div>
                        )}
                      </div>
                    </td>
                    <td className="px-3.5 py-2.5 align-top max-w-xl">
                      <div className="font-bold text-slate-800 text-xs mb-1">{pt.title}</div>
                      <p className="text-[11px] text-slate-700 whitespace-pre-wrap leading-relaxed bg-slate-50 border border-slate-200/80 rounded-lg p-2">
                        {pt.description}
                      </p>
                      {history.length > 0 && (
                        <div className="mt-1.5">
                          <button
                            type="button"
                            onClick={() => setExpandedPreTaskId(isExpanded ? null : pt.id)}
                            className="inline-flex items-center gap-1 text-[10px] font-bold text-indigo-600 hover:text-indigo-800"
                          >
                            {isExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                            {isExpanded ? 'Hide' : 'View'} Conversation History ({history.length})
                          </button>
                          {isExpanded && (
                            <div className="mt-1.5 space-y-1.5 max-h-60 overflow-y-auto bg-slate-50 border border-slate-200 rounded-lg p-2">
                              {history.map((msg, idx) => (
                                <div
                                  key={msg.id || idx}
                                  className={`p-2 rounded border text-[10px] ${
                                    msg.direction === 'INBOUND'
                                      ? 'bg-white border-sky-200'
                                      : 'bg-indigo-50/70 border-indigo-100'
                                  }`}
                                >
                                  <div className="flex justify-between items-center font-bold text-slate-600 mb-0.5">
                                    <span>{msg.direction === 'INBOUND' ? (msg.from_name || msg.sender_name || msg.from_email || 'Sender') : 'Our System / AI'}</span>
                                    <span>{msg.timestamp ? new Date(msg.timestamp).toLocaleString() : ''}</span>
                                  </div>
                                  <div className="text-slate-800 whitespace-pre-wrap">{msg.body || msg.snippet}</div>
                                </div>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </td>
                    {isManager && (
                      <td className="px-3.5 py-2.5 align-top">
                        <div className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-indigo-50 border border-indigo-100">
                          <span className="text-[9px] font-bold text-indigo-700 uppercase">User:</span>
                          <span className="text-[10px] font-bold text-slate-800">{pt.assigned_pre_username || 'Unassigned'}</span>
                        </div>
                        <div className="text-[9px] text-slate-500 mt-1">
                          {pt.created_at ? new Date(pt.created_at).toLocaleString() : ''}
                        </div>
                      </td>
                    )}
                    <td className="px-3.5 py-2.5 align-top text-right">
                      {activeTab === 'PENDING' ? (
                        isManager ? (
                          <div className="px-3 py-1 bg-amber-50 text-amber-700 rounded-lg text-[10px] font-bold border border-amber-200 inline-flex items-center gap-1">
                            Pending
                          </div>
                        ) : (
                          <button
                            type="button"
                            disabled={completingPreTaskId === pt.id}
                            onClick={() => handleCompletePreTaskItem(pt.id)}
                            className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white rounded-lg text-[10px] font-bold transition inline-flex items-center gap-1 shadow-2xs"
                          >
                            <CheckCircle className="w-3 h-3" />
                            {completingPreTaskId === pt.id ? 'Completing...' : 'Mark Complete'}
                          </button>
                        )
                      ) : (
                        <div className="px-3 py-1 bg-emerald-50 text-emerald-700 rounded-lg text-[10px] font-bold border border-emerald-200 inline-flex items-center gap-1">
                          <CheckCircle className="w-3 h-3" /> Completed
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      <ProspectForm 
        isOpen={isFormOpen} 
        onClose={() => setIsFormOpen(false)} 
        prospect={editingProspect}
        highlightFields={highlightFields}
        onSuccess={() => {
          setHasEdited(true); // Enable button on successful save
        }}
        readOnly={isManager || activeTab === 'COMPLETED'}
        highlightMode={activeTab === 'COMPLETED' ? 'success' : 'error'}
      />
    </div>
  );
};

export default PreTasksPage;
