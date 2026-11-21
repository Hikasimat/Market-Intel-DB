import React, { useState, useEffect, useCallback } from 'react';
import {
  ShieldCheck,
  Calendar as CalendarIcon,
  ChevronRight,
  Users,
  CheckCircle,
  RefreshCw,
  ClipboardList,
  UserCircle,
  X,
} from 'lucide-react';
import { toast } from 'react-toastify';
import { useDispatch, useSelector } from 'react-redux';
import api from '../services/api';
import SearchableSelect from '../components/common/SearchableSelect';
import { fetchManagerAudit } from '../features/manager/managerSlice';
import { formatDateTimeForUser } from '../utils/timezone';

const localToday = () => new Date().toLocaleDateString('en-CA');

const ManagerAuditPage = () => {
  const dispatch = useDispatch();
  const { user } = useSelector((state) => state.auth);
  const { auditData, auditLoading, auditError } = useSelector((state) => state.manager);

  const [activeTab, setActiveTab] = useState('SAMPLING'); // 'SAMPLING' | 'REVERIFY'
  const [reportingDate, setReportingDate] = useState(localToday);
  const [selectedPreUserId, setSelectedPreUserId] = useState('ALL');
  const [reverifyFilter, setReverifyFilter] = useState('ALL'); // 'ALL' | 'Pending' | 'Corrected'

  const [selectedAuditRecord, setSelectedAuditRecord] = useState(null);
  const [reverifyFields, setReverifyFields] = useState([]);
  const [reverifyNotes, setReverifyNotes] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const loadAudit = useCallback(() => {
    dispatch(fetchManagerAudit({ date: reportingDate }));
  }, [dispatch, reportingDate]);

  useEffect(() => {
    loadAudit();
  }, [loadAudit]);

  const handleReverifySubmit = async () => {
    if (!selectedAuditRecord || reverifyFields.length === 0) {
      toast.warning('Please select at least one field to re-verify.');
      return;
    }
    setIsSubmitting(true);
    try {
      await api.post(`/prospects/${selectedAuditRecord.id}/audit-reverify/`, {
        highlighted_fields: reverifyFields,
        manager_notes: reverifyNotes,
      });
      toast.success('Audit Report sent to PRE user for correction.');
      setSelectedAuditRecord(null);
      setReverifyFields([]);
      setReverifyNotes('');
      loadAudit();
    } catch (err) {
      console.error(err);
      toast.error('Failed to send re-verify request.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const toggleReverifyField = (field) => {
    setReverifyFields((prev) =>
      prev.includes(field) ? prev.filter((f) => f !== field) : [...prev, field]
    );
  };

  const formatValue = (val) => {
    if (val === null || val === undefined || val === '') return '-';
    if (Array.isArray(val)) {
      if (val.length === 0) return '-';
      if (typeof val[0] === 'object') {
        return val
          .map(
            (item) =>
              item.contact_name ||
              item.name ||
              item.company_name ||
              item.event_title ||
              JSON.stringify(item)
          )
          .join(', ');
      }
      return val.join(', ');
    }
    if (typeof val === 'object') {
      return val.qualification_status || JSON.stringify(val);
    }
    return String(val);
  };

  const summary = auditData?.summary || {};
  const allSamples = (auditData?.pre_audit_samples || []).filter((sg) => sg.entered_total > 0);
  const visibleSamples =
    selectedPreUserId === 'ALL'
      ? allSamples
      : allSamples.filter((sg) => String(sg.pre_user_id) === String(selectedPreUserId));

  const reverificationRequests = (auditData?.reverification_requests || []).filter((r) => {
    if (reverifyFilter === 'ALL') return true;
    return r.status === reverifyFilter;
  });

  const userTz = user?.timezone || 'UTC';

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 rounded-2xl p-6 md:p-7 flex flex-col md:flex-row items-start md:items-center justify-between gap-5 shadow-sm">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/10 text-indigo-100 text-[11px] font-bold uppercase tracking-wider mb-2.5 border border-white/15">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" /> Unified PRE Quality Assurance
          </div>
          <h1 className="text-2xl md:text-3xl font-black text-white tracking-tight">
            Daily Audit &amp; Re-Verification
          </h1>
          <p className="text-slate-300 text-xs sm:text-sm max-w-2xl mt-1">
            Review sampled prospect records, outreach qualification outcomes, and daily PRE activities in one unified workspace.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex items-center bg-white/10 rounded-xl px-3 py-2 border border-white/15">
            <CalendarIcon className="w-4 h-4 text-indigo-300 mr-2" />
            <input
              type="date"
              className="bg-transparent border-none text-xs font-bold text-white outline-none cursor-pointer"
              value={reportingDate}
              max={localToday()}
              onChange={(e) => {
                setReportingDate(e.target.value || localToday());
                setSelectedPreUserId('ALL');
              }}
            />
          </div>
          <button
            type="button"
            onClick={loadAudit}
            disabled={auditLoading}
            className="px-3.5 py-2 rounded-xl bg-indigo-500 hover:bg-indigo-400 text-white text-xs font-bold inline-flex items-center gap-1.5 transition cursor-pointer disabled:opacity-60"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${auditLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Summary Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5">
        <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-2xs">
          <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Active PREs</p>
          <p className="text-2xl font-black text-slate-900 mt-1">
            {summary.active_pre_users ?? 0}{' '}
            <span className="text-xs font-semibold text-slate-400">/ {summary.total_pre_users ?? 0}</span>
          </p>
        </div>
        <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-2xs">
          <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Entered on Date</p>
          <p className="text-2xl font-black text-indigo-700 mt-1">{summary.total_entered ?? 0}</p>
        </div>
        <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-2xs">
          <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Sampled Records</p>
          <p className="text-2xl font-black text-sky-700 mt-1">{summary.total_sampled ?? 0}</p>
        </div>
        <div className="bg-white border border-slate-200 rounded-2xl p-4 shadow-2xs">
          <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Pending / Corrected</p>
          <p className="text-2xl font-black text-amber-700 mt-1">
            {summary.pending_reverifications ?? 0}{' '}
            <span className="text-sm font-bold text-emerald-600">/ {summary.corrected_reverifications ?? 0}</span>
          </p>
        </div>
      </div>

      {/* Main Split Layout */}
      <div className="flex flex-col lg:flex-row gap-6">
        {/* Mode Switcher */}
        <div className="w-full lg:w-64 shrink-0 flex flex-col gap-2">
          <button
            type="button"
            onClick={() => setActiveTab('SAMPLING')}
            className={`flex items-center justify-between p-4 rounded-xl border text-xs font-bold transition-all cursor-pointer ${
              activeTab === 'SAMPLING'
                ? 'bg-indigo-50 border-indigo-200 text-indigo-700 shadow-xs'
                : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            <div className="flex items-center gap-3">
              <div className={`p-2 rounded-lg ${activeTab === 'SAMPLING' ? 'bg-indigo-100 text-indigo-600' : 'bg-slate-100 text-slate-500'}`}>
                <Users className="w-4 h-4" />
              </div>
              Daily Record Sampling
            </div>
            <ChevronRight className={`w-4 h-4 ${activeTab === 'SAMPLING' ? 'opacity-100' : 'opacity-0'}`} />
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('REVERIFY')}
            className={`flex items-center justify-between p-4 rounded-xl border text-xs font-bold transition-all cursor-pointer ${
              activeTab === 'REVERIFY'
                ? 'bg-amber-50 border-amber-200 text-amber-800 shadow-xs'
                : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'
            }`}
          >
            <div className="flex items-center gap-3">
              <div className={`p-2 rounded-lg ${activeTab === 'REVERIFY' ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-500'}`}>
                <ClipboardList className="w-4 h-4" />
              </div>
              Re-Verification Tracker
            </div>
            <span className="px-2 py-0.5 rounded-full text-[10px] bg-white border border-slate-200 text-slate-700">
              {summary.pending_reverifications ?? 0}
            </span>
          </button>
        </div>

        {/* Content Card */}
        <div className="flex-1 bg-white rounded-2xl border border-slate-200 shadow-xs p-6 overflow-hidden">
          {auditError && (
            <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-xs text-red-700">
              {typeof auditError === 'string' ? auditError : JSON.stringify(auditError)}
            </div>
          )}

          {auditLoading && !auditData ? (
            <div className="flex flex-col items-center justify-center py-20 text-slate-500">
              <div className="w-8 h-8 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin mb-3" />
              <p className="text-xs font-semibold">Loading audit records...</p>
            </div>
          ) : activeTab === 'SAMPLING' ? (
            <div className="space-y-6">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div>
                  <h2 className="text-base font-black text-slate-900">PRE Prospect &amp; Outreach Audit</h2>
                  <p className="text-xs text-slate-500">
                    Up to 10 automatically sampled records per active PRE user with qualification status and daily activities.
                  </p>
                </div>
                {allSamples.length > 0 && (
                  <div className="flex items-center gap-2">
                    <label className="text-xs font-bold text-slate-700">PRE User:</label>
                    <div className="w-52">
                      <SearchableSelect
                        value={selectedPreUserId}
                        onChange={(val) => setSelectedPreUserId(val || 'ALL')}
                        options={[
                          { value: 'ALL', label: `All Active PREs (${allSamples.length})` },
                          ...allSamples.map((sg) => ({
                            value: String(sg.pre_user_id),
                            label: `${sg.pre_name} (${sg.entered_total})`,
                          })),
                        ]}
                      />
                    </div>
                  </div>
                )}
              </div>

              {visibleSamples.length === 0 ? (
                <div className="text-center py-12 text-slate-500 text-xs bg-slate-50 rounded-xl border border-slate-100">
                  No PRE records found for {reportingDate}.
                </div>
              ) : (
                visibleSamples.map((sampleGroup) => (
                  <div key={sampleGroup.pre_user_id} className="border border-slate-200 rounded-xl overflow-hidden">
                    <div className="bg-slate-50 border-b border-slate-200 px-4 py-3 flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <UserCircle className="w-6 h-6 text-indigo-600" />
                        <div>
                          <h3 className="text-sm font-bold text-slate-900">{sampleGroup.pre_name}</h3>
                          <p className="text-[11px] text-slate-500">
                            Entered: {sampleGroup.entered_total} · Sampled: {sampleGroup.sample_count}
                          </p>
                        </div>
                      </div>
                      <span className="text-[11px] font-bold px-2.5 py-1 bg-indigo-100 text-indigo-700 rounded-full">
                        @{sampleGroup.pre_username}
                      </span>
                    </div>

                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-xs border-collapse">
                        <thead>
                          <tr className="bg-white border-b border-slate-100 text-slate-500 uppercase tracking-wider text-[10px]">
                            <th className="p-3">Company</th>
                            <th className="p-3">Country &amp; Industry</th>
                            <th className="p-3">Qualification</th>
                            <th className="p-3">Daily Activities</th>
                            <th className="p-3 text-right">Actions</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {sampleGroup.sample.map((prospect) => (
                            <tr key={prospect.id} className="hover:bg-slate-50/70">
                              <td className="p-3 align-top">
                                <div className="font-bold text-slate-900">{prospect.company_name}</div>
                                <div className="text-[10px] text-slate-400 mt-0.5">
                                  {prospect.created_at ? formatDateTimeForUser(prospect.created_at, userTz) : ''}
                                </div>
                                {prospect.pre_task_status === 'ISSUE_SENT_TO_PRE' && (
                                  <span className="mt-1 inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800 uppercase">
                                    Re-Verify Pending
                                  </span>
                                )}
                              </td>
                              <td className="p-3 align-top text-slate-600">
                                <div>{prospect.country_head_office}</div>
                                <div className="text-[10px] text-slate-400">{prospect.primary_industries}</div>
                              </td>
                              <td className="p-3 align-top whitespace-nowrap">
                                <span
                                  className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                    prospect.qualification_status === 'Lead Qualified'
                                      ? 'bg-emerald-100 text-emerald-700'
                                      : prospect.qualification_status === 'Lead Freeze'
                                      ? 'bg-rose-100 text-rose-700'
                                      : prospect.email_status && prospect.email_status !== 'Not Sent'
                                      ? 'bg-sky-100 text-sky-700'
                                      : 'bg-indigo-50 text-indigo-700'
                                  }`}
                                >
                                  {prospect.qualification_status === 'Lead Qualified'
                                    ? 'Lead Qualified'
                                    : prospect.qualification_status === 'Lead Freeze'
                                    ? 'Lead Not Qualified'
                                    : prospect.email_status && prospect.email_status !== 'Not Sent'
                                    ? prospect.email_status
                                    : 'Ready for Outreach'}
                                </span>
                                {prospect.attended_meeting && (
                                  <div className="text-[10px] font-bold text-indigo-600 mt-1">Meeting Attended</div>
                                )}
                              </td>
                              <td className="p-3 align-top max-w-xs">
                                {prospect.daily_activities?.length > 0 ? (
                                  <ul className="list-disc list-inside text-[11px] text-slate-600 space-y-0.5">
                                    {prospect.daily_activities.map((act, idx) => (
                                      <li key={idx}>{act}</li>
                                    ))}
                                  </ul>
                                ) : (
                                  <span className="text-[11px] text-slate-400 italic">No outreach logged on this date</span>
                                )}
                              </td>
                              <td className="p-3 align-top text-right">
                                <button
                                  type="button"
                                  onClick={() => {
                                    setSelectedAuditRecord(prospect);
                                    setReverifyFields(prospect.audit_reverify_fields || []);
                                    setReverifyNotes('');
                                  }}
                                  className="px-3 py-1.5 bg-white border border-slate-200 hover:bg-indigo-50 hover:border-indigo-200 hover:text-indigo-700 text-slate-700 text-xs font-bold rounded-xl transition cursor-pointer"
                                >
                                  Audit
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))
              )}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-base font-black text-slate-900">Audit Re-Verification Tracker</h2>
                  <p className="text-xs text-slate-500">
                    All field correction requests dispatched by Managers and their resolution status.
                  </p>
                </div>
                <div className="flex items-center gap-1.5 bg-slate-100 p-1 rounded-xl">
                  {['ALL', 'Pending', 'Corrected'].map((st) => (
                    <button
                      key={st}
                      type="button"
                      onClick={() => setReverifyFilter(st)}
                      className={`px-3 py-1 rounded-lg text-xs font-bold transition cursor-pointer ${
                        reverifyFilter === st ? 'bg-white text-slate-900 shadow-2xs' : 'text-slate-600 hover:text-slate-900'
                      }`}
                    >
                      {st}
                    </button>
                  ))}
                </div>
              </div>

              {reverificationRequests.length === 0 ? (
                <div className="text-center py-12 text-slate-500 text-xs bg-slate-50 rounded-xl border border-slate-100">
                  <CheckCircle className="w-8 h-8 text-emerald-400 mx-auto mb-2" />
                  No re-verification requests match this filter.
                </div>
              ) : (
                <div className="overflow-x-auto border border-slate-200 rounded-xl">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="bg-slate-50 border-b border-slate-200 text-slate-500 uppercase tracking-wider text-[10px]">
                        <th className="p-3">Prospect</th>
                        <th className="p-3">Assigned PRE</th>
                        <th className="p-3">Flagged Fields &amp; Notes</th>
                        <th className="p-3">Status</th>
                        <th className="p-3">Timestamps</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 bg-white">
                      {reverificationRequests.map((req) => (
                        <tr key={req.id} className="hover:bg-slate-50/70">
                          <td className="p-3 font-bold text-slate-900">{req.prospect_company_name || '—'}</td>
                          <td className="p-3 text-slate-700 font-semibold">{req.pre_user_name || '—'}</td>
                          <td className="p-3 max-w-md">
                            <div className="flex flex-wrap gap-1 mb-1">
                              {(req.highlighted_fields || []).map((f) => (
                                <span
                                  key={f}
                                  className="px-1.5 py-0.5 rounded bg-rose-50 border border-rose-200 text-rose-700 text-[10px] font-bold"
                                >
                                  {f.replace(/_/g, ' ')}
                                </span>
                              ))}
                            </div>
                            {req.manager_notes && (
                              <p className="text-[11px] text-slate-600">{req.manager_notes}</p>
                            )}
                          </td>
                          <td className="p-3 whitespace-nowrap">
                            <span
                              className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                req.status === 'Corrected'
                                  ? 'bg-emerald-100 text-emerald-700'
                                  : 'bg-amber-100 text-amber-800'
                              }`}
                            >
                              {req.status}
                            </span>
                          </td>
                          <td className="p-3 text-[11px] text-slate-500 whitespace-nowrap">
                            <div>Sent: {req.created_at ? formatDateTimeForUser(req.created_at, userTz) : '—'}</div>
                            {req.resolved_at && (
                              <div className="text-emerald-700">
                                Fixed: {formatDateTimeForUser(req.resolved_at, userTz)}
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Audit & Re-Verify Modal */}
      {selectedAuditRecord && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl w-full max-w-4xl max-h-[90vh] overflow-hidden shadow-2xl flex flex-col">
            <div className="p-6 border-b border-slate-100 flex items-center justify-between shrink-0">
              <div>
                <h3 className="text-lg font-black text-slate-900">
                  Audit Record: {selectedAuditRecord.company_name}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Select fields that require correction by the owning PRE user.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSelectedAuditRecord(null)}
                className="p-2 text-slate-400 hover:text-slate-600 hover:bg-slate-100 rounded-lg cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 flex flex-col lg:flex-row gap-6">
              <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-3.5 auto-rows-max">
                {Object.entries(selectedAuditRecord)
                  .filter(
                    ([key]) =>
                      ![
                        'id',
                        'created_at',
                        'updated_at',
                        'parent_companies',
                        'child_companies',
                        'offerings_data',
                        'market_event_ids',
                        'status_target',
                        'daily_activities',
                        'lead_qualification',
                      ].includes(key)
                  )
                  .map(([key, val]) => {
                    const isSelected = reverifyFields.includes(key);
                    return (
                      <div
                        key={key}
                        className={`rounded-xl p-3 border transition-colors ${
                          isSelected ? 'bg-red-50 border-red-200' : 'bg-slate-50 border-slate-100'
                        }`}
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex-1 min-w-0">
                            <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-1">
                              {key.replace('_detail', '').replace(/_/g, ' ')}
                            </p>
                            <p className="text-xs font-medium text-slate-900 truncate" title={formatValue(val)}>
                              {formatValue(val)}
                            </p>
                          </div>
                          <button
                            type="button"
                            onClick={() => toggleReverifyField(key)}
                            className={`shrink-0 px-2.5 py-1 text-[10px] font-bold rounded uppercase tracking-wider transition cursor-pointer ${
                              isSelected
                                ? 'bg-red-600 text-white shadow-2xs'
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
                    <p className="text-xs font-bold text-red-600 uppercase mb-2">
                      {reverifyFields.length} Fields Selected
                    </p>
                    <div className="flex flex-wrap gap-1.5 max-h-32 overflow-y-auto">
                      {reverifyFields.map((f) => (
                        <span
                          key={f}
                          className="inline-flex items-center px-2 py-1 bg-red-100 text-red-700 text-[10px] font-bold rounded-md"
                        >
                          {f.replace(/_/g, ' ')}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div>
                    <label className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-2 block">
                      Manager Notes (Optional)
                    </label>
                    <textarea
                      className="w-full bg-white border border-slate-200 rounded-xl p-3 text-xs focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 outline-none"
                      rows={4}
                      placeholder="Context for correction..."
                      value={reverifyNotes}
                      onChange={(e) => setReverifyNotes(e.target.value)}
                    />
                  </div>
                </div>
              )}
            </div>

            <div className="p-5 border-t border-slate-100 bg-slate-50 rounded-b-2xl flex justify-end gap-3 shrink-0">
              <button
                type="button"
                onClick={() => setSelectedAuditRecord(null)}
                className="px-4 py-2 bg-white border border-slate-200 text-slate-700 text-xs font-bold rounded-xl hover:bg-slate-100 cursor-pointer"
              >
                Close
              </button>
              {reverifyFields.length > 0 && (
                <button
                  type="button"
                  onClick={handleReverifySubmit}
                  disabled={isSubmitting}
                  className="px-5 py-2 bg-indigo-600 text-white text-xs font-bold rounded-xl hover:bg-indigo-700 shadow-xs disabled:opacity-50 cursor-pointer"
                >
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
