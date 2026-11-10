import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { ArrowLeft, Calendar, FileEdit, Building2 } from 'lucide-react';
import api from '../services/api';

const OutreachActivityDetailPage = () => {
  const { prospectId } = useParams();
  const [logs, setLogs] = useState([]);
  const [prospect, setProspect] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Fetch prospect details for the header
    api.get(`/prospects/${prospectId}/`)
       .then(res => setProspect(res.data))
       .catch(err => console.error('Failed to fetch prospect', err));

    // Fetch explicitly for this prospect to avoid pagination dropping records
    api.get(`/outreach/communications/?prospect=${prospectId}`)
       .then(res => {
         const prospectLogs = res.data.results || res.data;
         setLogs(prospectLogs.sort((a, b) => new Date(b.created_at) - new Date(a.created_at)));
       })
       .catch(err => console.error('Failed to fetch logs', err))
       .finally(() => setLoading(false));
  }, [prospectId]);

  if (loading) {
    return (
      <div className="p-8 flex items-center justify-center min-h-[50vh]">
        <div className="flex items-center gap-3 text-slate-500">
          <div className="w-5 h-5 rounded-full border-2 border-indigo-600 border-t-transparent animate-spin" />
          <span className="font-medium">Loading activity details...</span>
        </div>
      </div>
    );
  }

  const companyName = prospect ? prospect.company_name : (logs.length > 0 ? logs[0].prospect_company_name : 'Unknown Company');
  const createdAt = prospect ? prospect.created_at : (logs.length > 0 ? logs[0].prospect_created_at : null);

  // Group by date string
  const logsByDate = {};
  logs.forEach(l => {
    const dStr = new Date(l.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
    if (!logsByDate[dStr]) logsByDate[dStr] = [];
    logsByDate[dStr].push(l);
  });

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <Link to="/prospects?tab=pipeline" className="flex items-center gap-2 text-sm font-semibold text-slate-500 hover:text-indigo-600 transition">
          <ArrowLeft className="w-4 h-4" /> Back to Dashboard
        </Link>
      </div>

      <div className="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
        <div className="p-6 md:p-8 flex flex-col md:flex-row md:items-center justify-between gap-6 border-b border-slate-100 bg-slate-50/50">
          <div className="flex items-center gap-5">
            <div className="w-14 h-14 rounded-2xl bg-indigo-50 border border-indigo-100 flex items-center justify-center shrink-0 shadow-sm text-indigo-600">
              <Building2 className="w-7 h-7" />
            </div>
            <div>
              <h1 className="text-2xl font-black text-slate-900">{companyName}</h1>
              <p className="text-sm font-semibold text-slate-500 mt-1 flex items-center gap-2">
                {createdAt && <span>Created on {new Date(createdAt).toLocaleDateString()}</span>}
              </p>
            </div>
          </div>
        </div>

        <div className="p-6 md:p-8">
          <h2 className="text-sm font-bold text-slate-800 uppercase tracking-wider mb-6">Historical Outreach Timeline</h2>
          
          {logs.length === 0 ? (
            <div className="text-center p-8 border-2 border-dashed border-slate-200 rounded-xl">
              <p className="text-sm font-semibold text-slate-500">No outreach activities recorded for this prospect yet.</p>
            </div>
          ) : (
            <div className="space-y-6 relative before:absolute before:inset-0 before:ml-2 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-slate-200 before:to-transparent">
              {Object.entries(logsByDate).map(([dateStr, logsForDate]) => {
                // Calculate frequency for this day
                const frequency = {};
                logsForDate.forEach(l => {
                  frequency[l.activity_type] = (frequency[l.activity_type] || 0) + 1;
                });
                const frequencyText = Object.entries(frequency).map(([type, count]) => `${count} ${type.replace('_MADE', '').replace('_SENT', '')}`).join(' • ');

                return (
                  <div key={dateStr} className="relative flex items-start">
                    <div className="hidden md:flex flex-col items-end w-32 pt-2 pr-6 shrink-0">
                      <span className="text-xs font-black text-slate-800 uppercase tracking-widest">{dateStr}</span>
                      <span className="text-[10px] font-bold text-slate-400 mt-1">{frequencyText}</span>
                    </div>
                    <div className="flex flex-col items-center justify-center shrink-0 w-5 h-5 rounded-full bg-indigo-50 border-2 border-indigo-200 shadow mt-2 z-10 mx-0 md:mx-auto"></div>
                    <div className="pl-6 md:pl-6 w-full space-y-3">
                      <div className="md:hidden mb-2">
                        <span className="text-[11px] font-black text-slate-800 uppercase tracking-widest block">{dateStr}</span>
                        <span className="text-[10px] font-bold text-slate-500">{frequencyText}</span>
                      </div>
                      
                      {logsForDate.map(log => {
                        const isCall = log.activity_type === 'CALL_MADE';
                        return (
                          <div key={log.id} className="p-4 bg-white border border-slate-200 rounded-xl text-xs space-y-2.5 shadow-sm hover:shadow-md transition">
                            <div className="flex items-start justify-between flex-wrap gap-2">
                              <div className="flex flex-col gap-1.5">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase ${isCall ? 'bg-emerald-100 text-emerald-900' : 'bg-indigo-100 text-indigo-900'}`}>{log.activity_type}</span>
                                  <span className="font-bold text-slate-800 underline decoration-slate-300 underline-offset-2">{log.contact_name || companyName}</span>
                                  {log.status && <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${isCall ? 'bg-emerald-50 text-emerald-800 border-emerald-200' : 'bg-indigo-50 text-indigo-800 border-indigo-200'}`}>{log.status}</span>}
                                  {log.outcome && <span className="px-2 py-0.5 rounded bg-amber-50 text-amber-800 border border-amber-200 text-[10px] font-bold">Outcome: {log.outcome}</span>}
                                </div>
                                <div className="flex items-center gap-1.5 text-slate-500">
                                  <Calendar className="w-3 h-3" />
                                  <span className="text-[10px] font-semibold">{new Date(log.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                                </div>
                              </div>
                              <span className="text-[10px] font-bold bg-slate-50 border border-slate-200 px-2.5 py-1 rounded-xl text-slate-600 shadow-sm">
                                Performed by: {log.performed_by_name || log.created_by_name}
                              </span>
                            </div>
                            {log.notes && (
                              <div className="bg-slate-50 p-3 rounded-xl border border-slate-100">
                                <p className="text-slate-700 font-medium whitespace-pre-line leading-relaxed">{log.notes}</p>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default OutreachActivityDetailPage;
