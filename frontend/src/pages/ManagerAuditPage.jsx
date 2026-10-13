import React, { useState, useEffect } from 'react';
import { ShieldCheck, Calendar as CalendarIcon, Clock, ChevronRight, Activity, Users, UserCircle, CheckCircle, Mail, PhoneCall, X } from 'lucide-react';
import { toast } from 'react-toastify';
import api from '../services/api';
import SearchableSelect from '../components/common/SearchableSelect';
const ManagerAuditPage = () => {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [activeTab, setActiveTab] = useState('PRE'); // 'PRE' or 'LQ'
  const [reportingDate, setReportingDate] = useState(() => {
    return new Date().toISOString().split('T')[0];
  });

  const [selectedAuditRecord, setSelectedAuditRecord] = useState(null);
  const [selectedPreUserId, setSelectedPreUserId] = useState('');
  const [selectedLqUserId, setSelectedLqUserId] = useState('');

  const [reverifyFields, setReverifyFields] = useState([]);
  const [reverifyNotes, setReverifyNotes] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleReverifySubmit = async () => {
    if (!selectedAuditRecord || reverifyFields.length === 0) {
      toast.warning('Please select at least one field to re-verify.');
      return;
    }
    setIsSubmitting(true);
    try {
      await api.post(`/prospects/${selectedAuditRecord.id}/audit-reverify/`, {
        highlighted_fields: reverifyFields,
        manager_notes: reverifyNotes
      });
      toast.success('Audit Report sent to PRE user for correction.');
      setSelectedAuditRecord(null);
      setReverifyFields([]);
      setReverifyNotes('');
    } catch (err) {
      console.error(err);
      toast.error('Failed to send re-verify request.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const toggleReverifyField = (field) => {
    setReverifyFields(prev => 
      prev.includes(field) ? prev.filter(f => f !== field) : [...prev, field]
    );
  };

  const formatValue = (val) => {
    if (val === null || val === undefined || val === '') return '-';
    if (Array.isArray(val)) {
      if (val.length === 0) return '-';
      if (typeof val[0] === 'object') {
        return val.map(item => item.contact_name || item.name || item.company_name || item.event_title || JSON.stringify(item)).join(', ');
      }
      return val.join(', ');
    }
    return String(val);
  };

  const fetchAuditData = async (date) => {
    try {
      setLoading(true);
      const res = await api.get(`/manager-dashboard/?date=${date}`);
      const data = res.data;
      setData(data);
      
      const activePre = (data?.pre_audit_samples || []).filter(sg => sg.entered_total > 0);
      if (activePre.length > 0) {
        setSelectedPreUserId(activePre[0].pre_user_id.toString());
      } else {
        setSelectedPreUserId('');
      }

      const activeLq = (data?.audit_samples || []).filter(sg => sg.received_total > 0);
      if (activeLq.length > 0) {
        setSelectedLqUserId(activeLq[0].lq_user_id.toString());
      } else {
        setSelectedLqUserId('');
      }
    } catch (err) {
      console.error('Failed to load audit data', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAuditData(reportingDate);
  }, [reportingDate]);

  const handleDateChange = (e) => {
    setReportingDate(e.target.value);
  };

  const preSamples = (data?.pre_audit_samples || []).filter(sg => sg.entered_total > 0);
  const lqSamples = (data?.audit_samples || []).filter(sg => sg.received_total > 0);

  return (
    <div className="space-y-6">
      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 rounded-2xl p-6 md:p-8 flex flex-col md:flex-row items-start md:items-center justify-between gap-6 shadow-lg relative overflow-hidden">
        <div className="relative z-10">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 text-blue-50 text-xs font-bold uppercase tracking-wider mb-3 border border-white/20">
            <ShieldCheck className="w-3.5 h-3.5" /> Quality Assurance
          </div>
          <h1 className="text-2xl md:text-3xl font-black text-white tracking-tight mb-2">Daily Audit Logs</h1>
          <p className="text-blue-100 text-sm max-w-2xl">Review automatically sampled daily records for PRE and LQ users.</p>
        </div>
        <div className="relative z-10 flex flex-col items-end gap-2">
          <label className="text-xs font-bold text-blue-200 uppercase tracking-wider">Audit Date</label>
          <div className="flex items-center bg-slate-800 rounded-xl p-1 border border-slate-700">
            <div className="pl-3 pr-2 text-slate-400">
              <CalendarIcon className="w-4 h-4" />
            </div>
            <input
              type="date"
              className="bg-transparent border-none text-sm font-bold text-white focus:ring-0 cursor-pointer"
              value={reportingDate}
              max={new Date().toISOString().split('T')[0]}
              onChange={handleDateChange}
            />
          </div>
        </div>
      </div>

      <div className="flex flex-col lg:flex-row gap-6">
        {/* Sidebar */}
        <div className="w-full lg:w-64 shrink-0 flex flex-col gap-2">
          <button
            onClick={() => setActiveTab('PRE')}
            className={`flex items-center justify-between p-4 rounded-xl border font-bold transition-all ${
              activeTab === 'PRE'
                ? 'bg-indigo-50 border-indigo-200 text-indigo-700 shadow-sm'
                : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            <div className="flex items-center gap-3">
              <div className={`p-2 rounded-lg ${activeTab === 'PRE' ? 'bg-indigo-100 text-indigo-600' : 'bg-slate-100 text-slate-500'}`}>
                <Users className="w-5 h-5" />
              </div>
              PRE Audit
            </div>
            <ChevronRight className={`w-4 h-4 ${activeTab === 'PRE' ? 'opacity-100' : 'opacity-0'}`} />
          </button>
          
          <button
            onClick={() => setActiveTab('LQ')}
            className={`flex items-center justify-between p-4 rounded-xl border font-bold transition-all ${
              activeTab === 'LQ'
                ? 'bg-indigo-50 border-indigo-200 text-indigo-700 shadow-sm'
                : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            <div className="flex items-center gap-3">
              <div className={`p-2 rounded-lg ${activeTab === 'LQ' ? 'bg-indigo-100 text-indigo-600' : 'bg-slate-100 text-slate-500'}`}>
                <Activity className="w-5 h-5" />
              </div>
              LQ Audit
            </div>
            <ChevronRight className={`w-4 h-4 ${activeTab === 'LQ' ? 'opacity-100' : 'opacity-0'}`} />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 bg-white rounded-2xl border border-slate-200 shadow-sm p-6 overflow-hidden">
          {loading ? (
            <div className="flex flex-col items-center justify-center py-20 text-slate-500">
              <div className="w-8 h-8 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin mb-4" />
              <p className="font-medium">Loading audit records...</p>
            </div>
          ) : (
            <div className="space-y-8">
              {activeTab === 'PRE' && (
                <>
                  <div className="mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div>
                      <h2 className="text-lg font-black text-slate-900">PRE Master Data Audit</h2>
                      <p className="text-sm text-slate-500">10 automatically sampled records for each PRE user.</p>
                    </div>
                    {preSamples.length > 0 && (
                      <div className="flex items-center gap-2">
                        <label className="text-sm font-bold text-slate-700">Select User:</label>
                        <div className="w-48"><SearchableSelect
                          value={selectedPreUserId}
                          onChange={(val) => setSelectedPreUserId(val)}
                          options={preSamples.map(sg => ({value: sg.pre_user_id, label: sg.pre_name}))}
                        /></div>
                      </div>
                    )}
                  </div>
                  
                  {preSamples.length === 0 ? (
                    <div className="text-center py-12 text-slate-500 bg-slate-50 rounded-xl border border-slate-100">
                      No PRE records found for this date.
                    </div>
                  ) : (
                    preSamples
                      .filter(sg => sg.pre_user_id.toString() === selectedPreUserId.toString())
                      .map(sampleGroup => (
                      <div key={sampleGroup.pre_user_id} className="border border-slate-200 rounded-xl overflow-hidden mb-6">
                        <div className="bg-slate-50 border-b border-slate-200 p-4 flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <UserCircle className="w-6 h-6 text-indigo-500" />
                            <div>
                              <h3 className="font-bold text-slate-900">{sampleGroup.pre_name}</h3>
                              <p className="text-xs text-slate-500">Total Entered: {sampleGroup.entered_total}</p>
                            </div>
                          </div>
                          <div className="text-xs font-bold px-3 py-1 bg-indigo-100 text-indigo-700 rounded-full">
                            Sample: {sampleGroup.sample_count}
                          </div>
                        </div>
                        <div className="p-0">
                          {sampleGroup.sample.length === 0 ? (
                            <p className="text-sm text-slate-500 p-4 text-center">No samples available.</p>
                          ) : (
                            <div className="overflow-x-auto">
                              <table className="w-full text-left text-xs border-collapse">
                                <thead>
                                  <tr className="bg-white border-b border-slate-100 text-slate-500 uppercase tracking-wider text-[10px]">
                                    <th className="p-3">Company</th>
                                    <th className="p-3">Country</th>
                                    <th className="p-3">Created At</th>
                                    <th className="p-3">Actions</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-50">
                                  {sampleGroup.sample.map(prospect => (
                                    <tr key={prospect.id} className="hover:bg-slate-50">
                                      <td className="p-3 font-medium text-slate-900">
                                        {prospect.company_name}
                                        {prospect.pre_task_status === 'ISSUE_SENT_TO_PRE' && (
                                          <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-700 uppercase tracking-wider">Re-verify Sent</span>
                                        )}
                                      </td>
                                      <td className="p-3 text-slate-600">{prospect.country_head_office}</td>
                                      <td className="p-3 text-slate-500">{new Date(prospect.created_at).toLocaleString()}</td>
                                      <td className="p-3 flex items-center gap-2">
                                        <button 
                                          onClick={() => { setSelectedAuditRecord(prospect); setReverifyFields(prospect.audit_reverify_fields || []); setReverifyNotes(''); }}
                                          className="px-3 py-1 bg-white border border-slate-200 text-slate-700 text-xs font-bold rounded-xl hover:bg-slate-50"
                                        >
                                          Audit
                                        </button>
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </>
              )}

              {activeTab === 'LQ' && (
                <>
                  <div className="mb-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                    <div>
                      <h2 className="text-lg font-black text-slate-900">LQ Qualification Audit</h2>
                      <p className="text-sm text-slate-500">10 automatically sampled records and performed activities for each LQ user.</p>
                    </div>
                    {lqSamples.length > 0 && (
                      <div className="flex items-center gap-2">
                        <label className="text-sm font-bold text-slate-700">Select User:</label>
                        <div className="w-48"><SearchableSelect
                          value={selectedLqUserId}
                          onChange={(val) => setSelectedLqUserId(val)}
                          options={lqSamples.map(sg => ({value: sg.lq_user_id, label: sg.lq_name}))}
                        /></div>
                      </div>
                    )}
                  </div>
                  
                  {lqSamples.length === 0 ? (
                    <div className="text-center py-12 text-slate-500 bg-slate-50 rounded-xl border border-slate-100">
                      No LQ records found for this date.
                    </div>
                  ) : (
                    lqSamples
                      .filter(sg => sg.lq_user_id.toString() === selectedLqUserId.toString())
                      .map(sampleGroup => (
                      <div key={sampleGroup.lq_user_id} className="border border-slate-200 rounded-xl overflow-hidden mb-6">
                        <div className="bg-slate-50 border-b border-slate-200 p-4 flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <UserCircle className="w-6 h-6 text-indigo-500" />
                            <div>
                              <h3 className="font-bold text-slate-900">{sampleGroup.lq_name}</h3>
                              <p className="text-xs text-slate-500">Total Received: {sampleGroup.received_total}</p>
                            </div>
                          </div>
                          <div className="text-xs font-bold px-3 py-1 bg-indigo-100 text-indigo-700 rounded-full">
                            Sample: {sampleGroup.sample_count}
                          </div>
                        </div>
                        <div className="p-0">
                          {sampleGroup.sample.length === 0 ? (
                            <p className="text-sm text-slate-500 p-4 text-center">No samples available.</p>
                          ) : (
                            <div className="overflow-x-auto">
                              <table className="w-full text-left text-xs border-collapse">
                                <thead>
                                  <tr className="bg-white border-b border-slate-100 text-slate-500 uppercase tracking-wider text-[10px]">
                                    <th className="p-3">Company</th>
                                    <th className="p-3">Verification</th>
                                    <th className="p-3">Decision</th>
                                    <th className="p-3">Activities Logged Today</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-50">
                                  {sampleGroup.sample.map(prospect => (
                                    <tr key={prospect.id} className="hover:bg-slate-50">
                                      <td className="p-3 font-medium text-slate-900">{prospect.company_name}</td>
                                      <td className="p-3">
                                        <span className={`px-2 py-1 rounded-full text-[10px] font-bold ${
                                          prospect.verification_status === 'Verified' ? 'bg-emerald-100 text-emerald-700' : 'bg-slate-100 text-slate-600'
                                        }`}>
                                          {prospect.verification_status || 'Unverified'}
                                        </span>
                                      </td>
                                      <td className="p-3">
                                        <span className={`px-2 py-1 rounded-full text-[10px] font-bold ${
                                          prospect.qualification_status === 'Lead Qualified' ? 'bg-blue-100 text-blue-700' : 
                                          prospect.qualification_status ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100 text-slate-600'
                                        }`}>
                                          {prospect.qualification_status || 'Unqualified'}
                                        </span>
                                      </td>
                                      <td className="p-3 max-w-xs">
                                        {prospect.lq_activities?.length > 0 ? (
                                          <ul className="list-disc list-inside text-[10px] text-slate-600 space-y-1">
                                            {prospect.lq_activities.map((act, i) => (
                                              <li key={i}>{act}</li>
                                            ))}
                                          </ul>
                                        ) : (
                                          <span className="text-[10px] text-slate-400 italic">No direct activities logged today</span>
                                        )}
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                        </div>
                      </div>
                    ))
                  )}
                </>
              )}
            </div>
          )}
        </div>
      </div>
      
      {/* Modals for Audit and Re-Verify */}
      {selectedAuditRecord && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-4xl max-h-[90vh] overflow-hidden shadow-2xl flex flex-col">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between shrink-0">
              <div>
                <h3 className="text-xl font-black text-slate-900">Audit Record: {selectedAuditRecord.company_name}</h3>
                <p className="text-sm text-slate-500">Review all entered fields. Select fields that require correction by PRE.</p>
              </div>
              <button onClick={() => setSelectedAuditRecord(null)} className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg">
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-6 flex flex-col lg:flex-row gap-6">
              <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-4 auto-rows-max">
                {Object.entries(selectedAuditRecord)
                  .filter(([key]) => !['id', 'created_at', 'updated_at', 'parent_companies', 'child_companies', 'offerings_data', 'market_event_ids', 'status_target'].includes(key))
                  .map(([key, val]) => {
                    const isSelected = reverifyFields.includes(key);
                    return (
                      <div key={key} className={`rounded-xl p-3 border transition-colors ${isSelected ? 'bg-red-50 border-red-200' : 'bg-slate-50 border-slate-100'}`}>
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">{key.replace('_detail', '').replace(/_/g, ' ')}</p>
                            <p className="text-sm font-medium text-slate-900 truncate" title={formatValue(val)}>{formatValue(val)}</p>
                          </div>
                          <button
                            onClick={() => toggleReverifyField(key)}
                            className={`shrink-0 px-2.5 py-1 text-[10px] font-bold rounded uppercase tracking-wider transition ${
                              isSelected 
                                ? 'bg-red-600 text-white shadow-sm' 
                                : 'bg-white border border-slate-200 text-slate-500 hover:bg-slate-100'
                            }`}
                          >
                            Re-Verify
                          </button>
                        </div>
                      </div>
                    );
                })}
              </div>

              {reverifyFields.length > 0 && (
                <div className="w-full lg:w-80 shrink-0 bg-slate-50 border border-slate-200 rounded-xl p-5 flex flex-col h-max">
                  <h4 className="text-sm font-bold text-slate-900 mb-3">Re-Verification Summary</h4>
                  <div className="mb-4">
                    <p className="text-xs font-bold text-red-600 uppercase mb-2">{reverifyFields.length} Fields Selected</p>
                    <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
                      {reverifyFields.map(f => (
                        <span key={f} className="inline-flex items-center px-2 py-1 bg-red-100 text-red-700 text-[10px] font-bold rounded-md">
                          {f.replace(/_/g, ' ')}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2 block">Manager Notes (Optional)</label>
                    <textarea 
                      className="w-full bg-white border border-slate-200 rounded-xl p-3 text-sm focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 focus:border-indigo-500"
                      rows={4}
                      placeholder="Context for correction..."
                      value={reverifyNotes}
                      onChange={(e) => setReverifyNotes(e.target.value)}
                    />
                  </div>
                </div>
              )}
            </div>

            <div className="p-6 border-t border-slate-100 bg-slate-50 rounded-b-2xl flex justify-end gap-3 shrink-0">
              <button onClick={() => setSelectedAuditRecord(null)} className="px-5 py-2.5 bg-white border border-slate-200 text-slate-700 text-sm font-bold rounded-xl hover:bg-slate-50">
                Close
              </button>
              {reverifyFields.length > 0 && (
                <button onClick={handleReverifySubmit} disabled={isSubmitting} className="px-5 py-2.5 bg-indigo-600 text-white text-sm font-bold rounded-xl hover:bg-indigo-700 shadow-lg shadow-indigo-200 disabled:opacity-50">
                  {isSubmitting ? 'Sending...' : 'Send Audit Report'}
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ManagerAuditPage;
