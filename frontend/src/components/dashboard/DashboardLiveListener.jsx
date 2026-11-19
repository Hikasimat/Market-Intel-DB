import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Link } from 'react-router-dom';
import { useSelector } from 'react-redux';
import {
  Mail,
  Sparkles,
  RefreshCw,
  Clock,
  AlertCircle,
  CheckCircle2,
  ArrowRight,
  Send,
  Inbox,
  Calendar,
  Radio,
} from 'lucide-react';
import api from '../../services/api';
import { formatDateTimeForUser } from '../../utils/timezone';

const POLL_INTERVAL_MS = 20000;

const PRIORITY_BADGE = {
  high: 'bg-rose-50 text-rose-700 border-rose-200',
  medium: 'bg-amber-50 text-amber-700 border-amber-200',
  low: 'bg-emerald-50 text-emerald-700 border-emerald-200',
};

const THREAD_STATUS_BADGE = {
  WAITING_REPLY: 'bg-amber-50 text-amber-700 border-amber-200',
  REPLIED: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  FAILED: 'bg-rose-50 text-rose-700 border-rose-200',
  SENT: 'bg-sky-50 text-sky-700 border-sky-200',
};

export default function DashboardLiveListener() {
  const { user } = useSelector((state) => state.auth);
  const [feed, setFeed] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [autoListen, setAutoListen] = useState(true);
  const [errorMsg, setErrorMsg] = useState('');
  const reqGenRef = useRef(0);

  const fetchFeed = useCallback(async ({ sync = true, force = false, silent = false } = {}) => {
    if (!user?.id) return;
    const gen = ++reqGenRef.current;
    if (!silent) {
      setRefreshing(true);
    }
    try {
      const res = force
        ? await api.post('/email-ai/dashboard-feed/refresh/')
        : await api.get(`/email-ai/dashboard-feed/?sync=${sync ? '1' : '0'}`);
      if (reqGenRef.current !== gen) return;
      setFeed(res.data);
      setErrorMsg('');
    } catch (err) {
      if (reqGenRef.current !== gen) return;
      setErrorMsg(err.response?.data?.detail || 'Unable to refresh live activity feed.');
    } finally {
      if (reqGenRef.current === gen) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [user?.id]);

  // Reset cleanly on user change so accounts never share cached feed state
  useEffect(() => {
    reqGenRef.current += 1;
    setFeed(null);
    setErrorMsg('');
    setLoading(true);
    if (user?.id) {
      fetchFeed({ sync: true, force: false, silent: false });
    }
  }, [user?.id, fetchFeed]);

  // Real-time interval polling + instant trigger when new mail notification arrives or tab becomes visible
  useEffect(() => {
    if (!user?.id || !autoListen) return undefined;

    const timer = setInterval(() => {
      if (typeof document === 'undefined' || !document.hidden) {
        fetchFeed({ sync: true, force: false, silent: true });
      }
    }, POLL_INTERVAL_MS);

    const onVisibility = () => {
      if (!document.hidden) {
        fetchFeed({ sync: true, force: false, silent: true });
      }
    };
    const onMailActivity = () => {
      fetchFeed({ sync: false, force: true, silent: true });
    };

    document.addEventListener('visibilitychange', onVisibility);
    window.addEventListener('marketintel:mail-activity', onMailActivity);
    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibility);
      window.removeEventListener('marketintel:mail-activity', onMailActivity);
    };
  }, [user?.id, autoListen, fetchFeed]);

  if (!user) return null;

  const mailbox = feed?.mailbox || {};
  const metrics = feed?.metrics || {};
  const incoming = feed?.incoming_emails || [];
  const outreach = feed?.outreach_activity || [];
  const pending = feed?.pending_actions || [];
  const recommendations = feed?.recommendations || [];

  return (
    <section
      className="bg-white border border-slate-200/80 rounded-2xl shadow-xs overflow-hidden"
      data-testid="dashboard-live-listener"
    >
      {/* Top Real-Time Status & User Mailbox Header */}
      <div className="px-5 py-4 bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 text-white flex flex-col lg:flex-row lg:items-center justify-between gap-3">
        <div className="flex items-start sm:items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-white/10 border border-white/15 flex items-center justify-center shrink-0">
            <Radio className={`w-5 h-5 ${autoListen ? 'text-emerald-400 animate-pulse' : 'text-slate-400'}`} />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="text-sm font-bold tracking-tight">
                Live Activity & AI Recommendations
              </h2>
              <span
                className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border ${
                  autoListen
                    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-400/30'
                    : 'bg-slate-700 text-slate-300 border-slate-600'
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${autoListen ? 'bg-emerald-400' : 'bg-slate-400'}`} />
                {autoListen ? 'Live Listening' : 'Paused'}
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-300 mt-1">
              <span className="inline-flex items-center gap-1.5 font-mono text-indigo-200">
                <Mail className="w-3.5 h-3.5 text-indigo-300" />
                {mailbox.email || user.email || 'No email configured'}
              </span>
              <span className="text-[11px] text-slate-400">
                ({mailbox.connected ? `${mailbox.provider} Active` : 'Mailbox Disconnected'})
              </span>
              {feed?.synced_at && (
                <span className="text-[11px] text-slate-400 flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  Synced {formatDateTimeForUser(feed.synced_at, user?.timezone)}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={() => setAutoListen((prev) => !prev)}
            className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-xs font-semibold text-white border border-white/15 transition cursor-pointer"
          >
            {autoListen ? 'Pause Listener' : 'Resume Listener'}
          </button>
          <button
            type="button"
            disabled={refreshing}
            onClick={() => fetchFeed({ sync: true, force: true, silent: false })}
            className="px-3 py-1.5 rounded-lg bg-indigo-500 hover:bg-indigo-400 text-xs font-semibold text-white flex items-center gap-1.5 transition cursor-pointer disabled:opacity-60"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} />
            {refreshing ? 'Analyzing...' : 'Sync & Refresh AI'}
          </button>
        </div>
      </div>

      {errorMsg && (
        <div className="px-5 py-2.5 bg-amber-50 border-b border-amber-200 text-xs text-amber-800 flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{errorMsg}</span>
        </div>
      )}

      {loading && !feed ? (
        <div className="p-8 flex items-center justify-center gap-2.5 text-slate-500 text-xs font-medium">
          <RefreshCw className="w-4 h-4 animate-spin text-indigo-600" />
          <span>Connecting real-time activity listener for your account...</span>
        </div>
      ) : (
        <div className="p-5 space-y-5">
          {/* AI Executive Summary + Metrics Strip */}
          <div className="rounded-xl bg-indigo-50/70 border border-indigo-100 p-4 flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-indigo-600 text-white shrink-0 mt-0.5">
                <Sparkles className="w-4 h-4" />
              </div>
              <div>
                <p className="text-[11px] font-bold text-indigo-700 uppercase tracking-wider mb-0.5">
                  AI Activity Brief
                </p>
                <p className="text-xs sm:text-sm text-slate-700 leading-relaxed">
                  {feed?.ai_summary || 'Real-time monitoring is active for your account.'}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-3 shrink-0 text-center">
              <div className="px-3 py-1.5 bg-white rounded-lg border border-indigo-100">
                <div className="text-base font-black text-slate-900">{metrics.incoming_count ?? 0}</div>
                <div className="text-[10px] font-semibold text-slate-500">Incoming</div>
              </div>
              <div className="px-3 py-1.5 bg-white rounded-lg border border-indigo-100">
                <div className="text-base font-black text-amber-600">{metrics.waiting_reply_count ?? 0}</div>
                <div className="text-[10px] font-semibold text-slate-500">Awaiting</div>
              </div>
              <div className="px-3 py-1.5 bg-white rounded-lg border border-indigo-100">
                <div className="text-base font-black text-indigo-600">{metrics.pending_tasks_count ?? 0}</div>
                <div className="text-[10px] font-semibold text-slate-500">Tasks</div>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Column 1: AI Recommendations & Follow-Up Actions */}
            <div className="border border-slate-200/80 rounded-xl p-4 bg-slate-50/40 flex flex-col">
              <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center gap-1.5 mb-3">
                <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
                AI Recommended Actions
              </h3>
              <div className="space-y-2.5 flex-1">
                {recommendations.length === 0 ? (
                  <p className="text-xs text-slate-500 italic">No pending recommendations right now.</p>
                ) : (
                  recommendations.map((rec, idx) => (
                    <div key={idx} className="bg-white rounded-lg border border-slate-200/80 p-3 space-y-1.5">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-xs font-bold text-slate-800 leading-snug">{rec.title}</p>
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase border shrink-0 ${
                            PRIORITY_BADGE[rec.priority] || PRIORITY_BADGE.medium
                          }`}
                        >
                          {rec.priority || 'medium'}
                        </span>
                      </div>
                      {rec.rationale && (
                        <p className="text-[11px] text-slate-500 leading-relaxed">{rec.rationale}</p>
                      )}
                      {rec.suggested_action && (
                        <p className="text-[11px] font-medium text-indigo-700">{rec.suggested_action}</p>
                      )}
                      {rec.target_route && (
                        <Link
                          to={rec.target_route}
                          className="inline-flex items-center gap-1 text-[11px] font-bold text-indigo-600 hover:text-indigo-800 pt-0.5"
                        >
                          Open workspace <ArrowRight className="w-3 h-3" />
                        </Link>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Column 2: Real-Time Incoming Mail & Outreach Activity */}
            <div className="border border-slate-200/80 rounded-xl p-4 bg-slate-50/40 flex flex-col">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center gap-1.5">
                  <Inbox className="w-3.5 h-3.5 text-sky-600" />
                  Incoming Mail & Outreach
                </h3>
                <Link to="/inbox" className="text-[11px] font-bold text-indigo-600 hover:underline">
                  Inbox
                </Link>
              </div>
              <div className="space-y-2 flex-1">
                {incoming.length === 0 && outreach.length === 0 ? (
                  <p className="text-xs text-slate-500 italic">
                    No recent incoming emails or outreach threads recorded yet.
                  </p>
                ) : (
                  <>
                    {incoming.slice(0, 3).map((mail) => (
                      <div key={`in-${mail.id}`} className="bg-white rounded-lg border border-sky-100 p-2.5">
                        <div className="flex items-center justify-between gap-2 mb-0.5">
                          <span className="text-[11px] font-bold text-sky-700 truncate">
                            {mail.company_name || mail.sender_name || mail.sender_email}
                          </span>
                          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-sky-50 text-sky-700 border border-sky-200">
                            INBOUND
                          </span>
                        </div>
                        <p className="text-xs font-semibold text-slate-800 truncate">{mail.subject}</p>
                        {mail.snippet && (
                          <p className="text-[11px] text-slate-500 truncate mt-0.5">{mail.snippet}</p>
                        )}
                      </div>
                    ))}
                    {outreach.slice(0, 3).map((th) => (
                      <div key={`th-${th.id}`} className="bg-white rounded-lg border border-slate-200/80 p-2.5">
                        <div className="flex items-center justify-between gap-2 mb-0.5">
                          <span className="text-[11px] font-bold text-slate-700 truncate flex items-center gap-1">
                            <Send className="w-3 h-3 text-slate-400" />
                            {th.company_name || th.correspondent_name || th.correspondent_email}
                          </span>
                          <span
                            className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${
                              THREAD_STATUS_BADGE[th.status] || THREAD_STATUS_BADGE.SENT
                            }`}
                          >
                            {th.status}
                          </span>
                        </div>
                        <p className="text-xs font-medium text-slate-800 truncate">{th.subject}</p>
                      </div>
                    ))}
                  </>
                )}
              </div>
            </div>

            {/* Column 3: Pending Actions & Important Updates */}
            <div className="border border-slate-200/80 rounded-xl p-4 bg-slate-50/40 flex flex-col">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wider flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                  Pending Actions & Updates
                </h3>
                <Link to="/pre-tasks" className="text-[11px] font-bold text-indigo-600 hover:underline">
                  Tasks
                </Link>
              </div>
              <div className="space-y-2 flex-1">
                {pending.length === 0 ? (
                  <p className="text-xs text-slate-500 italic">
                    No pending tasks, failed sends, or upcoming meetings right now.
                  </p>
                ) : (
                  pending.map((item, idx) => (
                    <Link
                      key={idx}
                      to={item.route || '/dashboard'}
                      className="block bg-white rounded-lg border border-slate-200/80 p-2.5 hover:border-indigo-300 transition"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-xs font-bold text-slate-800 truncate">{item.title}</span>
                        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 shrink-0 flex items-center gap-1">
                          {item.kind === 'MEETING' && <Calendar className="w-2.5 h-2.5" />}
                          {item.kind}
                        </span>
                      </div>
                      {item.subtitle && (
                        <p className="text-[11px] text-slate-500 truncate mt-0.5">{item.subtitle}</p>
                      )}
                    </Link>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
