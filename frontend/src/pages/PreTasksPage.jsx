import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { fetchLqPipeline, completePreTask } from '../features/lqPipeline/lqPipelineSlice';
import ProspectForm from '../components/prospects/ProspectForm';
import SearchableSelect from '../components/common/SearchableSelect';
import { AlertTriangle, CheckCircle, FileEdit, Building2 } from 'lucide-react';
import { toast } from 'react-toastify';

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

  useEffect(() => {
    if (activeTab === 'PENDING') {
      dispatch(fetchLqPipeline({ pre_task_status: 'ISSUE_SENT_TO_PRE' }));
    } else {
      // Fetch all tasks for the user so we can see historically completed tasks
      dispatch(fetchLqPipeline({}));
    }
  }, [dispatch, activeTab]);

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

  const availableUsers = Array.from(new Set(tasks.map(t => t.prospect?.created_by))).filter(Boolean);
  
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
    <div className="space-y-6">

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white p-4 rounded-2xl shadow-sm border border-slate-200">
        {!isManager ? (
          <div className="flex bg-slate-100 p-1 rounded-lg">
            <button
              onClick={() => setActiveTab('PENDING')}
              className={`px-4 py-2 rounded-md text-sm font-bold transition ${activeTab === 'PENDING' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-600 hover:text-slate-900'}`}
            >
              Pending Tasks
            </button>
            <button
              onClick={() => setActiveTab('COMPLETED')}
              className={`px-4 py-2 rounded-md text-sm font-bold transition ${activeTab === 'COMPLETED' ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-600 hover:text-slate-900'}`}
            >
              Completed Tasks
            </button>
          </div>
        ) : (
          <h2 className="text-sm font-black text-slate-800 uppercase tracking-wider">Pending PRE Tasks</h2>
        )}
        
        {activeTab === 'COMPLETED' && (
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-2">
              <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">From:</label>
              <input
                type="date"
                className="bg-slate-50 border border-slate-200 text-slate-900 text-sm rounded-xl focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 p-2 font-medium"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                max={new Date().toISOString().split('T')[0]}
              />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">To:</label>
              <input
                type="date"
                className="bg-slate-50 border border-slate-200 text-slate-900 text-sm rounded-xl focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 p-2 font-medium"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                max={new Date().toISOString().split('T')[0]}
              />
            </div>
          </div>
        )}

        {isManager && availableUsers.length > 0 && (
          <div className="flex items-center gap-2 ml-auto">
            <label className="text-xs font-bold text-slate-500 uppercase tracking-wider">Assigned PRE:</label>
            <div className="w-48"><SearchableSelect
              value={managerUserFilter}
              onChange={(val) => setManagerUserFilter(val)}
              options={[{value: 'ALL', label: 'All Users'}, ...availableUsers.map(u => ({value: u, label: u}))]}
            /></div>
          </div>
        )}
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-slate-50 text-slate-500 font-bold uppercase tracking-wider text-[10px] border-b border-slate-200">
                <th className="p-4">Reported Prospect</th>
                <th className="p-4">Issue Details</th>
                {isManager && <th className="p-4">Assignment Info</th>}
                <th className="p-4 text-right">Actions</th>
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
                <tr key={task.id} className="hover:bg-slate-50 transition">
                  <td className="p-4 align-top">
                    <div className="flex items-start gap-3">
                      <div className="w-9 h-9 rounded-xl bg-indigo-50 border border-indigo-100 text-indigo-700 font-black text-xs flex items-center justify-center shrink-0 mt-0.5">
                        <Building2 className="w-4 h-4" />
                      </div>
                      <div>
                        <div className="font-bold text-slate-900 text-sm">{task.prospect.company_name}</div>
                        <p className="text-[11px] text-slate-500 mt-0.5">
                          {task.prospect.country_head_office} &bull; {task.prospect.primary_industries}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td className="p-4 align-top max-w-md">
                    <div className={`p-3 rounded-lg border ${activeTab === 'COMPLETED' ? 'bg-emerald-50 border-emerald-100 text-emerald-900' : 'bg-red-50 border-red-100 text-red-900'}`}>
                      <span className={`font-bold block mb-1 ${activeTab === 'COMPLETED' ? 'text-emerald-700' : 'text-red-700'}`}>Category: {task.issue_category}</span>
                      <p className="whitespace-pre-wrap font-mono text-[10px]">{task.issue_details}</p>
                    </div>
                  </td>
                  {isManager && (
                    <td className="p-4 align-top">
                      <div className="flex flex-col gap-2">
                        <div className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-indigo-50 border border-indigo-100 w-max">
                          <span className="text-[10px] font-bold text-indigo-700 uppercase">Assigned PRE:</span>
                          <span className="text-xs font-bold text-slate-800">{task.prospect.created_by || 'Unknown'}</span>
                        </div>
                        <div className="text-[10px] text-slate-500 font-medium">
                          Assigned on: {task.issue_reported_at ? new Date(task.issue_reported_at).toLocaleDateString() : 'N/A'}
                        </div>
                      </div>
                    </td>
                  )}
                  <td className="p-4 align-top text-right">
                    <div className="flex flex-col gap-2 items-end">
                      <button
                        onClick={() => handleOpenProspect(task)}
                        className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-bold transition flex items-center gap-1.5 shadow-sm"
                      >
                        <FileEdit className="w-3.5 h-3.5" /> {isManager ? 'View Prospect' : 'Open Prospect'}
                      </button>
                      {!isManager && activeTab === 'PENDING' && (
                        <button
                          onClick={() => handleCompleteTask(task.id)}
                          disabled={!hasEdited || activeTaskId !== task.id}
                          className={`px-4 py-2 rounded-lg text-xs font-bold transition flex items-center gap-1.5 shadow-sm ${
                            (hasEdited && activeTaskId === task.id) ? 'bg-emerald-600 hover:bg-emerald-700 text-white' : 'bg-slate-100 text-slate-400 cursor-not-allowed'
                          }`}
                        >
                          <CheckCircle className="w-3.5 h-3.5" /> Complete Correction Task
                        </button>
                      )}
                      {!isManager && activeTab === 'COMPLETED' && (
                        <div className="px-4 py-2 bg-emerald-50 text-emerald-700 rounded-xl text-xs font-bold border border-emerald-200 flex items-center gap-1.5 w-max justify-center shadow-sm">
                          <CheckCircle className="w-3.5 h-3.5" /> Completed
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
