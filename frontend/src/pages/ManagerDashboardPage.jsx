import React, { useEffect, useState, useCallback, useMemo } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { fetchManagerDashboard } from '../features/manager/managerSlice';
import ManagerEmailActivitySection from '../components/ManagerEmailActivitySection';
import { formatDateTimeForUser, formatTimeForUser } from '../utils/timezone';
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  BarChart2,
  Bot,
  Building2,
  Calendar,
  CheckCircle,
  ClipboardList,
  Clock,
  ExternalLink,
  Eye,
  Mail,
  MessageCircle,
  Pause,
  Phone,
  Play,
  Radio,
  RefreshCw,
  Search,
  Send,
  Shield,
  Sparkles,
  TrendingUp,
  UserCheck,
  Users,
  Video,
  X,
  XCircle,
  Zap,
} from 'lucide-react';

const POLL_INTERVAL_MS = 15000;

const localToday = () => new Date().toLocaleDateString('en-CA');

const STAGE_META = [
  { key: 'lead_qualified', label: 'Lead Qualified', bar: 'bg-emerald-500' },
  { key: 'received_response', label: 'Received Response', bar: 'bg-teal-500' },
  { key: 'waiting_for_response', label: 'Waiting for Response', bar: 'bg-sky-500' },
  { key: 'call_follow_up', label: 'Call Follow-Up', bar: 'bg-amber-500' },
  { key: 'ready_for_outreach', label: 'Ready for Outreach', bar: 'bg-indigo-400' },
  { key: 'lead_freeze', label: 'Lead Not Qualified', bar: 'bg-rose-500' },
];

const WA_STATUS_CLASS = {
  READY: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  AUTHENTICATED: 'bg-teal-100 text-teal-700 border-teal-200',
  STARTING: 'bg-sky-100 text-sky-700 border-sky-200',
  QR_REQUIRED: 'bg-amber-100 text-amber-700 border-amber-200',
  DISCONNECTED: 'bg-slate-100 text-slate-600 border-slate-200',
  STOPPED: 'bg-slate-100 text-slate-600 border-slate-200',
  FAILED: 'bg-rose-100 text-rose-700 border-rose-200',
  NOT_LINKED: 'bg-slate-100 text-slate-500 border-slate-200',
};

const FEED_CATEGORY_STYLES = {
  prospects: { icon: Building2, cls: 'bg-indigo-50 text-indigo-600 border-indigo-200' },
  email: { icon: Mail, cls: 'bg-sky-50 text-sky-600 border-sky-200' },
  whatsapp: { icon: MessageCircle, cls: 'bg-emerald-50 text-emerald-600 border-emerald-200' },
  calls: { icon: Phone, cls: 'bg-amber-50 text-amber-600 border-amber-200' },
  meetings: { icon: Video, cls: 'bg-purple-50 text-purple-600 border-purple-200' },
  tasks: { icon: ClipboardList, cls: 'bg-rose-50 text-rose-600 border-rose-200' },
};

const PROVIDER_LABELS = {
  GOOGLE_MEET: 'Google Meet',
  ZOOM: 'Zoom',
  MS_TEAMS: 'MS Teams',
  MANUAL: 'Manual Link',
};

const KpiCard = ({ title, value, icon: Icon, color, bg, sub, badge }) => (
  <div className="rounded-2xl bg-white border border-slate-200/80 p-4 shadow-xs hover:shadow-sm transition-shadow flex flex-col justify-between">
    <div className="flex items-start justify-between gap-2">
      <div className="min-w-0">
        <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider truncate">{title}</p>
        <div className="flex items-baseline gap-2 mt-1">
          <h3 className="text-2xl font-black text-slate-900 tracking-tight">{value ?? 0}</h3>
          {badge && (
            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-md bg-slate-100 text-slate-600">
              {badge}
            </span>
          )}
        </div>
      </div>
      <div className={`p-2.5 rounded-xl ${bg} ${color} shrink-0`}>
        <Icon className="w-4 h-4" />
      </div>
    </div>
    {sub && <p className="text-[11px] text-slate-500 font-medium mt-2.5 truncate">{sub}</p>}
  </div>
);

const IntegrationPill = ({ label, active, title, accent = 'emerald' }) => {
  const styles = active
    ? accent === 'indigo'
      ? 'bg-indigo-50 text-indigo-700 border-indigo-200'
      : 'bg-emerald-50 text-emerald-700 border-emerald-200'
    : 'bg-slate-50 text-slate-400 border-slate-200/80';
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md border text-[10px] font-bold ${styles}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${active ? (accent === 'indigo' ? 'bg-indigo-500' : 'bg-emerald-500') : 'bg-slate-300'}`} />
      {label}
    </span>
  );
};

const ManagerDashboardPage = () => {
  const dispatch = useDispatch();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useSelector((state) => state.auth);
  const { dashboard, loading, refreshing, error, lastUpdatedAt } = useSelector((state) => state.manager);

  const initialTabParam = searchParams.get('tab');
  const activeTab = ['overview', 'operations', 'email'].includes(initialTabParam)
    ? initialTabParam
    : 'overview';

  const [selectedDate, setSelectedDate] = useState(localToday);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [teamSearch, setTeamSearch] = useState('');
  const [teamSortBy, setTeamSortBy] = useState('prospects_entered');
  const [feedFilter, setFeedFilter] = useState('all');
  const [inspectedMember, setInspectedMember] = useState(null);

  const setActiveTab = (tab) => {
    const next = new URLSearchParams(searchParams);
    if (tab === 'overview') {
      next.delete('tab');
    } else {
      next.set('tab', tab);
    }
    setSearchParams(next, { replace: true });
  };

  const loadData = useCallback(
    (silent = false) => {
      dispatch(fetchManagerDashboard({ date: selectedDate, silent }));
    },
    [dispatch, selectedDate]
  );

  useEffect(() => {
    loadData(false);
  }, [loadData]);

  // Real-time background polling every 15 seconds while tab is visible
  useEffect(() => {
    if (!autoRefresh) return undefined;

    const timer = setInterval(() => {
      if (typeof document === 'undefined' || !document.hidden) {
        loadData(true);
      }
    }, POLL_INTERVAL_MS);

    const onVisibilityChange = () => {
      if (!document.hidden) {
        loadData(true);
      }
    };
    document.addEventListener('visibilitychange', onVisibilityChange);

    return () => {
      clearInterval(timer);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [autoRefresh, loadData]);

  const summary = dashboard?.summary || {};
  const meta = dashboard?.meta || {};
  const funnel = dashboard?.pipeline_funnel || {};
  const team = dashboard?.team_performance || [];
  const whatsappOverview = dashboard?.whatsapp_overview || {};
  const waConfig = whatsappOverview.config || {};
  const waSessions = whatsappOverview.sessions || [];
  const waAiMetrics = whatsappOverview.ai_metrics || {};
  const meetingsOverview = dashboard?.meetings_overview || {};
  const tasksOverview = dashboard?.tasks_overview || {};
  const campaignsOverview = dashboard?.campaigns_overview || {};
  const liveFeed = dashboard?.live_feed || [];

  const filteredTeam = useMemo(() => {
    const q = teamSearch.trim().toLowerCase();
    const rows = q
      ? team.filter(
          (m) =>
            (m.name || '').toLowerCase().includes(q) ||
            (m.username || '').toLowerCase().includes(q) ||
            (m.email || '').toLowerCase().includes(q)
        )
      : [...team];

    rows.sort((a, b) => {
      const av = Number(a[teamSortBy] ?? 0);
      const bv = Number(b[teamSortBy] ?? 0);
      if (bv !== av) return bv - av;
      return (b.total_prospects || 0) - (a.total_prospects || 0);
    });
    return rows;
  }, [team, teamSearch, teamSortBy]);

  const filteredFeed = useMemo(() => {
    if (feedFilter === 'all') return liveFeed;
    return liveFeed.filter((item) => item.category === feedFilter);
  }, [liveFeed, feedFilter]);

  const kpiCards = [
    {
      title: 'Prospects Entered',
      value: summary.prospects_entered ?? 0,
      badge: `${summary.total_prospects ?? 0} total`,
      sub: `${summary.active_pre_users ?? 0} / ${meta.team_size ?? team.length} PRE active`,
      icon: Zap,
      color: 'text-indigo-600',
      bg: 'bg-indigo-50',
    },
    {
      title: 'Lead Qualified',
      value: summary.lead_qualified ?? 0,
      badge: `${funnel.conversion_rate ?? 0}% conv`,
      sub: `${summary.total_lead_qualified ?? 0} total · ${summary.not_lead_qualified ?? 0} not qualified`,
      icon: CheckCircle,
      color: 'text-emerald-600',
      bg: 'bg-emerald-50',
    },
    {
      title: 'Emails & Replies',
      value: summary.emails_sent ?? 0,
      badge: `${summary.emails_received ?? 0} in`,
      sub: `${summary.emails_opened ?? 0} opened · ${summary.waiting_email_replies ?? 0} awaiting reply`,
      icon: Mail,
      color: 'text-sky-600',
      bg: 'bg-sky-50',
    },
    {
      title: 'Calls & WhatsApp',
      value: (summary.calls_logged ?? 0) + (summary.whatsapp_outbound ?? 0),
      badge: `${summary.whatsapp_ai_replies ?? 0} AI`,
      sub: `${summary.calls_logged ?? 0} calls · ${summary.whatsapp_outbound ?? 0} WA out · ${summary.whatsapp_inbound ?? 0} WA in`,
      icon: MessageCircle,
      color: 'text-teal-600',
      bg: 'bg-teal-50',
    },
    {
      title: 'Meetings',
      value: summary.meetings_scheduled_today ?? 0,
      badge: `${summary.upcoming_meetings_7d ?? 0} next 7d`,
      sub: `${summary.meetings_created_today ?? 0} booked · ${summary.meetings_attended ?? 0} attended`,
      icon: Video,
      color: 'text-purple-600',
      bg: 'bg-purple-50',
    },
    {
      title: 'Action Queue',
      value: summary.pending_tasks_total ?? 0,
      badge: `${summary.pending_audit_reverifications ?? 0} audit`,
      sub: `${summary.tasks_completed_today ?? 0} tasks done · ${summary.active_campaigns ?? 0} active campaigns`,
      icon: ClipboardList,
      color: 'text-amber-600',
      bg: 'bg-amber-50',
    },
  ];

  const todayDateStr = localToday();
  const isTodaySelected = selectedDate === todayDateStr;
  const userTz = user?.timezone || 'UTC';

  return (
    <div className="min-h-full bg-[#f4f5f7] p-4 sm:p-6 md:p-7 font-sans text-slate-800 space-y-6">
      {/* Header + Live Status & Date Controls */}
      <div className="flex flex-col xl:flex-row xl:items-center justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2 mb-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-amber-50 border border-amber-200 text-amber-700 text-[11px] font-bold uppercase tracking-wider">
              <Shield className="w-3.5 h-3.5" />
              Manager Command Center
            </span>
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold border ${
                autoRefresh
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : 'bg-slate-100 text-slate-600 border-slate-200'
              }`}
            >
              <Radio className={`w-3 h-3 ${autoRefresh ? 'text-emerald-500 animate-pulse' : 'text-slate-400'}`} />
              {autoRefresh ? 'Live · 15s Sync' : 'Live Paused'}
            </span>
            {lastUpdatedAt && (
              <span className="text-[11px] text-slate-500 font-medium inline-flex items-center gap-1">
                <Clock className="w-3 h-3" />
                Synced {formatTimeForUser(lastUpdatedAt, userTz)}
              </span>
            )}
          </div>
          <h1 className="text-2xl sm:text-3xl font-black text-slate-900 tracking-tight">
            Manager <span className="text-indigo-600">Real-Time Dashboard</span>
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 font-medium mt-1">
            Unified PRE pipeline performance, live outreach telemetry, WhatsApp AI monitoring, and daily audit status.
          </p>
        </div>

        {/* Controls Bar */}
        <div className="flex flex-wrap items-center gap-2.5">
          <div className="flex items-center gap-2 bg-white border border-slate-200 rounded-xl px-3 py-2 shadow-2xs">
            <Calendar className="w-4 h-4 text-slate-400 shrink-0" />
            <input
              type="date"
              value={selectedDate}
              max={todayDateStr}
              onChange={(e) => setSelectedDate(e.target.value || todayDateStr)}
              aria-label="Reporting date"
              className="text-xs font-bold text-slate-800 bg-transparent border-0 outline-none cursor-pointer"
            />
            {!isTodaySelected && (
              <button
                type="button"
                onClick={() => setSelectedDate(todayDateStr)}
                className="px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 hover:bg-indigo-100 text-[11px] font-bold transition"
              >
                Today
              </button>
            )}
          </div>

          <button
            type="button"
            onClick={() => setAutoRefresh((prev) => !prev)}
            className="px-3 py-2 rounded-xl bg-white border border-slate-200 hover:bg-slate-50 text-xs font-bold text-slate-700 shadow-2xs inline-flex items-center gap-1.5 transition cursor-pointer"
          >
            {autoRefresh ? <Pause className="w-3.5 h-3.5 text-slate-500" /> : <Play className="w-3.5 h-3.5 text-emerald-600" />}
            {autoRefresh ? 'Pause Live' : 'Resume Live'}
          </button>

          <button
            type="button"
            onClick={() => loadData(false)}
            disabled={loading || refreshing}
            className="px-3.5 py-2 rounded-xl bg-slate-900 hover:bg-black text-white text-xs font-bold shadow-2xs inline-flex items-center gap-1.5 transition disabled:opacity-60 cursor-pointer"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading || refreshing ? 'animate-spin' : ''}`} />
            {refreshing ? 'Syncing...' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* Tab Switcher */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="inline-flex bg-white p-1 rounded-2xl border border-slate-200/90 shadow-2xs">
          <button
            type="button"
            onClick={() => setActiveTab('overview')}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
              activeTab === 'overview'
                ? 'bg-slate-900 text-white shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <BarChart2 className="w-3.5 h-3.5" />
            Overview &amp; Team
            <span className={`px-1.5 py-0.5 rounded-full text-[10px] ${activeTab === 'overview' ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-600'}`}>
              {team.length}
            </span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('operations')}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
              activeTab === 'operations'
                ? 'bg-slate-900 text-white shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Activity className="w-3.5 h-3.5" />
            Live Operations
            <span className={`px-1.5 py-0.5 rounded-full text-[10px] ${activeTab === 'operations' ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-600'}`}>
              {waSessions.length} WA · {(meetingsOverview.upcoming || []).length} Mtgs
            </span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab('email')}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
              activeTab === 'email'
                ? 'bg-slate-900 text-white shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Mail className="w-3.5 h-3.5" />
            Email Intelligence
          </button>
        </div>

        <div className="flex items-center gap-2 text-xs text-slate-500 font-semibold">
          <span>Reporting: <strong className="text-slate-800">{dashboard?.date || selectedDate}</strong></span>
          {meta.timezone && <span className="text-slate-400">({meta.timezone})</span>}
        </div>
      </div>

      {/* Initial Loading State */}
      {loading && !dashboard && (
        <div className="bg-white border border-slate-200 rounded-2xl p-16 flex flex-col items-center justify-center gap-3 shadow-xs">
          <Activity className="w-9 h-9 text-indigo-600 animate-pulse" />
          <p className="text-xs font-bold uppercase tracking-widest text-indigo-600">
            Loading Real-Time Manager Telemetry...
          </p>
        </div>
      )}

      {/* Fatal Error State */}
      {!loading && error && !dashboard && (
        <div className="bg-red-50 border border-red-200 rounded-2xl p-6 text-center max-w-lg mx-auto">
          <XCircle className="w-10 h-10 text-red-500 mx-auto mb-2" />
          <h2 className="text-base font-bold text-red-800 mb-1">Unable to Load Manager Dashboard</h2>
          <p className="text-xs text-red-600 mb-4">{typeof error === 'string' ? error : JSON.stringify(error)}</p>
          <button
            type="button"
            onClick={() => loadData(false)}
            className="px-4 py-2 bg-red-600 hover:bg-red-700 text-white rounded-xl text-xs font-bold transition"
          >
            Retry
          </button>
        </div>
      )}

      {/* Tab Content */}
      {dashboard && activeTab === 'overview' && (
        <div className="space-y-6">
          {/* 6 Summary KPIs */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3.5">
            {kpiCards.map((card) => (
              <KpiCard key={card.title} {...card} />
            ))}
          </div>

          {/* Pipeline Funnel + Live Activity Stream */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
            {/* Pipeline Funnel */}
            <div className="lg:col-span-5 bg-white border border-slate-200/80 rounded-2xl shadow-xs p-5 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between gap-2 mb-4">
                  <div>
                    <h2 className="text-sm font-black text-slate-900 flex items-center gap-2">
                      <TrendingUp className="w-4 h-4 text-indigo-600" />
                      Live Outreach &amp; Pipeline Funnel
                    </h2>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      Real-time distribution across {funnel.total ?? 0} total prospects
                    </p>
                  </div>
                  <span className="px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-black">
                    {funnel.conversion_rate ?? 0}% LQ
                  </span>
                </div>

                <div className="space-y-2.5">
                  {STAGE_META.map((stage) => {
                    const count = funnel[stage.key] || 0;
                    const pct = funnel.total ? Math.round((count / funnel.total) * 100) : 0;
                    return (
                      <div key={stage.key}>
                        <div className="flex items-center justify-between text-xs mb-1">
                          <span className="font-semibold text-slate-700">{stage.label}</span>
                          <span className="font-bold text-slate-900">
                            {count} <span className="text-slate-400 font-medium">({pct}%)</span>
                          </span>
                        </div>
                        <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                          <div className={`h-full ${stage.bar} rounded-full transition-all duration-500`} style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Live Health Strip */}
              <div className="mt-5 pt-4 border-t border-slate-100 space-y-3">
                <div className="grid grid-cols-2 gap-2.5 text-xs">
                  <div className="rounded-xl bg-amber-50/70 border border-amber-200/80 px-3 py-2">
                    <div className="text-[10px] font-bold text-amber-700 uppercase">Awaiting Email Reply</div>
                    <div className="text-base font-black text-amber-900">{summary.waiting_email_replies ?? 0}</div>
                  </div>
                  <div className="rounded-xl bg-emerald-50/70 border border-emerald-200/80 px-3 py-2">
                    <div className="text-[10px] font-bold text-emerald-700 uppercase">Replied Threads</div>
                    <div className="text-base font-black text-emerald-900">{summary.replied_email_threads ?? 0}</div>
                  </div>
                  <div className="rounded-xl bg-sky-50/70 border border-sky-200/80 px-3 py-2">
                    <div className="text-[10px] font-bold text-sky-700 uppercase">WhatsApp Ready / AI ON</div>
                    <div className="text-base font-black text-sky-900">
                      {summary.whatsapp_sessions_ready ?? 0} / {summary.whatsapp_ai_enabled_sessions ?? 0}
                    </div>
                  </div>
                  <div className="rounded-xl bg-indigo-50/70 border border-indigo-200/80 px-3 py-2">
                    <div className="text-[10px] font-bold text-indigo-700 uppercase">Active Campaigns</div>
                    <div className="text-base font-black text-indigo-900">{summary.active_campaigns ?? 0}</div>
                  </div>
                </div>

                <div className="flex items-center gap-2 pt-1">
                  <Link
                    to="/prospects"
                    className="flex-1 text-center px-3 py-1.5 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-800 text-xs font-bold transition"
                  >
                    View Prospects
                  </Link>
                  <Link
                    to="/prospects?tab=outreach"
                    className="flex-1 text-center px-3 py-1.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold transition"
                  >
                    Open Outreach
                  </Link>
                </div>
              </div>
            </div>

            {/* Real-Time Activity Stream */}
            <div className="lg:col-span-7 bg-white border border-slate-200/80 rounded-2xl shadow-xs flex flex-col overflow-hidden">
              <div className="px-5 py-4 border-b border-slate-100 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <h2 className="text-sm font-black text-slate-900 flex items-center gap-2">
                    <Radio className="w-4 h-4 text-emerald-500 animate-pulse" />
                    Real-Time Team Activity Stream
                  </h2>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    Latest live actions across Prospects, Email, WhatsApp, Calls, Meetings, and Tasks
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-1">
                  {['all', 'prospects', 'email', 'whatsapp', 'calls', 'meetings', 'tasks'].map((cat) => (
                    <button
                      key={cat}
                      type="button"
                      onClick={() => setFeedFilter(cat)}
                      className={`px-2 py-1 rounded-lg text-[10px] font-bold uppercase tracking-wider transition cursor-pointer ${
                        feedFilter === cat
                          ? 'bg-slate-900 text-white'
                          : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                      }`}
                    >
                      {cat}
                    </button>
                  ))}
                </div>
              </div>

              <div className="divide-y divide-slate-100 max-h-[410px] overflow-y-auto">
                {filteredFeed.length === 0 ? (
                  <div className="p-10 text-center text-xs text-slate-400 italic">
                    No activity recorded yet for this filter.
                  </div>
                ) : (
                  filteredFeed.map((item) => {
                    const catStyle = FEED_CATEGORY_STYLES[item.category] || FEED_CATEGORY_STYLES.prospects;
                    const CatIcon = catStyle.icon;
                    return (
                      <Link
                        key={item.id}
                        to={item.route || '/manager-dashboard'}
                        className="px-5 py-3 flex items-start justify-between gap-3 hover:bg-slate-50/90 transition-colors"
                      >
                        <div className="flex items-start gap-3 min-w-0">
                          <div className={`p-2 rounded-xl border shrink-0 mt-0.5 ${catStyle.cls}`}>
                            <CatIcon className="w-3.5 h-3.5" />
                          </div>
                          <div className="min-w-0">
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="text-xs font-bold text-slate-900 truncate">{item.title}</span>
                              {item.badge && (
                                <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-600 uppercase">
                                  {item.badge}
                                </span>
                              )}
                            </div>
                            {item.subtitle && (
                              <p className="text-[11px] text-slate-500 truncate mt-0.5">{item.subtitle}</p>
                            )}
                            <p className="text-[10px] font-semibold text-indigo-600 mt-0.5">
                              {item.actor_name}
                            </p>
                          </div>
                        </div>
                        <div className="text-[10px] text-slate-400 font-medium whitespace-nowrap shrink-0 flex items-center gap-1 mt-0.5">
                          <span>{item.timestamp ? formatDateTimeForUser(item.timestamp, userTz) : ''}</span>
                          <ArrowRight className="w-3 h-3 text-slate-300" />
                        </div>
                      </Link>
                    );
                  })
                )}
              </div>
            </div>
          </div>

          {/* Unified PRE Team Performance Table */}
          <div className="bg-white border border-slate-200/80 rounded-2xl shadow-xs overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-100 bg-slate-50/70 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-black text-slate-900 flex items-center gap-2">
                  <Users className="w-4 h-4 text-indigo-600" />
                  PRE Team Live Performance &amp; Channel Health
                </h2>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  Merged Prospect Research &amp; Outreach accountability for {dashboard.date} (plus live portfolio queues)
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <div className="relative">
                  <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2" />
                  <input
                    type="text"
                    value={teamSearch}
                    onChange={(e) => setTeamSearch(e.target.value)}
                    placeholder="Filter PRE user..."
                    className="pl-8 pr-3 py-1.5 bg-white border border-slate-200 rounded-xl text-xs text-slate-700 w-44 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <select
                  value={teamSortBy}
                  onChange={(e) => setTeamSortBy(e.target.value)}
                  aria-label="Sort team by"
                  className="px-3 py-1.5 bg-white border border-slate-200 rounded-xl text-xs font-semibold text-slate-700 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="prospects_entered">Sort: Prospects Entered</option>
                  <option value="total_activities">Sort: Total Activities</option>
                  <option value="lead_qualified">Sort: Lead Qualified</option>
                  <option value="emails_sent">Sort: Emails Sent</option>
                  <option value="whatsapp_outbound">Sort: WhatsApp Sent</option>
                  <option value="pending_tasks">Sort: Pending Tasks</option>
                </select>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-[11px] font-bold text-slate-500 uppercase tracking-wider">PRE Member &amp; Integrations</th>
                    <th className="px-3 py-3 text-right text-[11px] font-bold text-slate-500 uppercase tracking-wider">Prospects</th>
                    <th className="px-3 py-3 text-right text-[11px] font-bold text-slate-500 uppercase tracking-wider">Qualified</th>
                    <th className="px-3 py-3 text-right text-[11px] font-bold text-slate-500 uppercase tracking-wider">Calls</th>
                    <th className="px-3 py-3 text-right text-[11px] font-bold text-slate-500 uppercase tracking-wider">Emails (S / R)</th>
                    <th className="px-3 py-3 text-right text-[11px] font-bold text-slate-500 uppercase tracking-wider">WhatsApp (Out / AI)</th>
                    <th className="px-3 py-3 text-right text-[11px] font-bold text-slate-500 uppercase tracking-wider">Meetings</th>
                    <th className="px-3 py-3 text-right text-[11px] font-bold text-slate-500 uppercase tracking-wider">Pending Tasks</th>
                    <th className="px-4 py-3 text-right text-[11px] font-bold text-slate-500 uppercase tracking-wider">Inspect</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {filteredTeam.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="px-6 py-10 text-center text-xs text-slate-400 italic">
                        No PRE users match the current filter.
                      </td>
                    </tr>
                  ) : (
                    filteredTeam.map((m) => {
                      const integ = m.integrations || {};
                      const waConnected = ['READY', 'AUTHENTICATED'].includes(integ.whatsapp_status);
                      return (
                        <tr key={m.user_id} className="hover:bg-slate-50/70 transition-colors">
                          <td className="px-4 py-3 align-top">
                            <div className="flex items-start gap-2.5">
                              <div className="w-8 h-8 rounded-full bg-indigo-100 text-indigo-700 font-black text-xs flex items-center justify-center shrink-0 mt-0.5">
                                {(m.name || m.username || 'P')[0].toUpperCase()}
                              </div>
                              <div className="min-w-0">
                                <div className="text-xs font-bold text-slate-900 truncate">{m.name}</div>
                                <div className="text-[11px] text-slate-500 truncate">{m.email || `@${m.username}`}</div>
                                <div className="flex flex-wrap gap-1 mt-1.5">
                                  <IntegrationPill
                                    label="Mail"
                                    active={integ.gmail_connected}
                                    title={integ.gmail_connected ? `Connected: ${integ.gmail_email}` : 'Mailbox not connected'}
                                  />
                                  <IntegrationPill
                                    label="Cal"
                                    active={integ.google_calendar_connected || integ.microsoft_connected}
                                    title="Google / Microsoft Calendar"
                                  />
                                  <IntegrationPill
                                    label="Zoom/Teams"
                                    active={integ.zoom_connected || integ.microsoft_connected}
                                    title="Zoom / Microsoft Teams"
                                  />
                                  <IntegrationPill
                                    label={waConnected ? 'WA Live' : 'WA Off'}
                                    active={waConnected}
                                    title={`WhatsApp: ${integ.whatsapp_status}`}
                                  />
                                  {integ.whatsapp_ai_enabled && (
                                    <IntegrationPill
                                      label="AI ON"
                                      active={true}
                                      accent="indigo"
                                      title="WhatsApp AI Auto-Reply ON"
                                    />
                                  )}
                                </div>
                              </div>
                            </div>
                          </td>
                          <td className="px-3 py-3 text-right whitespace-nowrap">
                            <div className="text-xs font-black text-indigo-700">{m.prospects_entered}</div>
                            <div className="text-[10px] text-slate-400">{m.total_prospects} total</div>
                          </td>
                          <td className="px-3 py-3 text-right whitespace-nowrap">
                            <div className="text-xs font-black text-emerald-700">{m.lead_qualified}</div>
                            <div className="text-[10px] text-slate-400">{m.total_lead_qualified} total</div>
                          </td>
                          <td className="px-3 py-3 text-right whitespace-nowrap text-xs font-bold text-slate-700">
                            {m.calls}
                          </td>
                          <td className="px-3 py-3 text-right whitespace-nowrap">
                            <div className="text-xs font-bold text-sky-700">
                              {m.emails_sent} <span className="text-slate-300">/</span> {m.emails_received}
                            </div>
                            <div className="text-[10px] text-slate-400">{m.emails_opened} opened</div>
                          </td>
                          <td className="px-3 py-3 text-right whitespace-nowrap">
                            <div className="text-xs font-bold text-teal-700">
                              {m.whatsapp_outbound} <span className="text-slate-300">/</span> {m.whatsapp_ai_replies}
                            </div>
                            <div className="text-[10px] text-slate-400">{m.whatsapp_inbound} in</div>
                          </td>
                          <td className="px-3 py-3 text-right whitespace-nowrap">
                            <div className="text-xs font-bold text-purple-700">{m.meetings_today}</div>
                            <div className="text-[10px] text-slate-400">{m.upcoming_meetings} next 7d</div>
                          </td>
                          <td className="px-3 py-3 text-right whitespace-nowrap">
                            <span
                              className={`inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-bold ${
                                m.pending_tasks > 0
                                  ? 'bg-amber-100 text-amber-800'
                                  : 'bg-slate-100 text-slate-500'
                              }`}
                            >
                              {m.pending_tasks}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-right whitespace-nowrap">
                            <button
                              type="button"
                              onClick={() => setInspectedMember(m)}
                              className="px-2.5 py-1 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-[11px] font-bold inline-flex items-center gap-1 cursor-pointer"
                            >
                              <Eye className="w-3 h-3" /> Details
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Daily Quality Audit CTA Banner */}
          <div className="bg-gradient-to-r from-amber-50 to-orange-50 border border-amber-200 rounded-2xl p-5 shadow-xs flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
              <h2 className="text-base font-black text-amber-900 flex items-center gap-2">
                <Shield className="w-4 h-4 text-amber-600" />
                Unified Daily Quality Audit &amp; Re-Verification Tracker
              </h2>
              <p className="text-xs text-amber-800 font-medium mt-1">
                Sample up to 10 prospects per PRE user, inspect outreach &amp; qualification state together, and track{' '}
                <strong>{summary.pending_audit_reverifications ?? 0}</strong> pending re-verification request(s).
              </p>
            </div>
            <Link
              to="/manager-audit"
              className="shrink-0 bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold py-2.5 px-4 rounded-xl shadow-xs transition-colors inline-flex items-center gap-2"
            >
              <ClipboardList className="w-4 h-4" />
              Open Daily Audit
            </Link>
          </div>
        </div>
      )}

      {/* TAB 2: LIVE OPERATIONS */}
      {dashboard && activeTab === 'operations' && (
        <div className="space-y-6">
          {/* WhatsApp & AI Automation Monitor */}
          <div className="bg-white border border-slate-200/80 rounded-2xl shadow-xs overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-100 bg-emerald-50/60 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-black text-emerald-950 flex items-center gap-2">
                  <Bot className="w-4 h-4 text-emerald-600" />
                  WhatsApp Sessions &amp; AI Auto-Reply Monitor
                </h2>
                <p className="text-[11px] text-slate-600 mt-0.5">
                  Per-account connection health, AI toggle state, safety guard status, and AI meeting scheduling telemetry
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-xs font-bold">
                <span
                  className={`px-2.5 py-1 rounded-full border ${
                    waConfig.outbound_enabled !== false
                      ? 'bg-emerald-100 text-emerald-800 border-emerald-200'
                      : 'bg-rose-100 text-rose-800 border-rose-200'
                  }`}
                >
                  Outbound: {waConfig.outbound_enabled !== false ? 'ENABLED' : 'PAUSED'}
                </span>
                {waConfig.safety_stop_active && (
                  <span className="px-2.5 py-1 rounded-full bg-red-600 text-white inline-flex items-center gap-1">
                    <AlertTriangle className="w-3.5 h-3.5" />
                    SAFETY STOP ACTIVE
                  </span>
                )}
                <span className="px-2.5 py-1 rounded-full bg-white border border-slate-200 text-slate-600">
                  Limits: {waConfig.per_user_hourly_limit ?? 20}/hr user · {waConfig.global_hourly_limit ?? 50}/hr global
                </span>
              </div>
            </div>

            {waConfig.safety_stop_active && waConfig.safety_stop_reason && (
              <div className="px-5 py-2.5 bg-red-50 border-b border-red-200 text-xs text-red-700 flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>Safety Guard Reason: {waConfig.safety_stop_reason}</span>
              </div>
            )}

            {/* AI Metrics Strip */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 p-5 border-b border-slate-100 bg-slate-50/40">
              <div className="rounded-xl bg-white border border-slate-200 p-3">
                <div className="text-[10px] font-bold text-slate-400 uppercase">AI Replies Sent</div>
                <div className="text-lg font-black text-emerald-700 mt-0.5">{waAiMetrics.replies_sent_today ?? 0}</div>
              </div>
              <div className="rounded-xl bg-white border border-slate-200 p-3">
                <div className="text-[10px] font-bold text-slate-400 uppercase">AI Replies Failed</div>
                <div className="text-lg font-black text-rose-600 mt-0.5">{waAiMetrics.replies_failed_today ?? 0}</div>
              </div>
              <div className="rounded-xl bg-white border border-slate-200 p-3">
                <div className="text-[10px] font-bold text-slate-400 uppercase">AI Replies Skipped</div>
                <div className="text-lg font-black text-slate-700 mt-0.5">{waAiMetrics.replies_skipped_today ?? 0}</div>
              </div>
              <div className="rounded-xl bg-white border border-slate-200 p-3">
                <div className="text-[10px] font-bold text-slate-400 uppercase">WA Escalations</div>
                <div className="text-lg font-black text-amber-700 mt-0.5">{waAiMetrics.active_escalations_pending ?? 0}</div>
              </div>
              <div className="rounded-xl bg-white border border-slate-200 p-3">
                <div className="text-[10px] font-bold text-slate-400 uppercase">AI Meetings Booked</div>
                <div className="text-lg font-black text-indigo-700 mt-0.5">{waAiMetrics.ai_meetings_scheduled_today ?? 0}</div>
              </div>
              <div className="rounded-xl bg-white border border-slate-200 p-3">
                <div className="text-[10px] font-bold text-slate-400 uppercase">AI Scheduling Live</div>
                <div className="text-lg font-black text-purple-700 mt-0.5">{waAiMetrics.ai_meetings_in_progress ?? 0}</div>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-[11px] font-bold text-slate-500 uppercase tracking-wider">PRE Owner</th>
                    <th className="px-4 py-3 text-left text-[11px] font-bold text-slate-500 uppercase tracking-wider">Session &amp; Phone</th>
                    <th className="px-4 py-3 text-left text-[11px] font-bold text-slate-500 uppercase tracking-wider">Status</th>
                    <th className="px-4 py-3 text-left text-[11px] font-bold text-slate-500 uppercase tracking-wider">AI Auto-Reply</th>
                    <th className="px-4 py-3 text-right text-[11px] font-bold text-slate-500 uppercase tracking-wider">Sent / Rcvd</th>
                    <th className="px-4 py-3 text-right text-[11px] font-bold text-slate-500 uppercase tracking-wider">AI Sent / Failed</th>
                    <th className="px-4 py-3 text-right text-[11px] font-bold text-slate-500 uppercase tracking-wider">Last Used</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {waSessions.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="px-6 py-8 text-center text-xs text-slate-400 italic">
                        No WhatsApp sessions registered for authorized PRE users.
                      </td>
                    </tr>
                  ) : (
                    waSessions.map((s) => (
                      <tr key={s.session_id} className="hover:bg-slate-50/70">
                        <td className="px-4 py-3 text-xs font-bold text-slate-800 whitespace-nowrap">{s.user_name}</td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <div className="text-xs font-semibold text-slate-800">{s.session_name}</div>
                          <div className="text-[11px] text-slate-500 font-mono">{s.phone_number || 'Phone not synced'}</div>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${WA_STATUS_CLASS[s.status] || WA_STATUS_CLASS.DISCONNECTED}`}>
                            {s.status}
                          </span>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <div className="flex items-center gap-1.5">
                            <span
                              className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                                s.ai_enabled
                                  ? 'bg-indigo-100 text-indigo-700 border-indigo-200'
                                  : 'bg-slate-100 text-slate-500 border-slate-200'
                              }`}
                            >
                              {s.ai_enabled ? 'AI ON' : 'AI OFF'}
                            </span>
                            {s.ai_model && <span className="text-[10px] text-slate-400">{s.ai_model}</span>}
                          </div>
                        </td>
                        <td className="px-4 py-3 text-right text-xs font-bold text-slate-700 whitespace-nowrap">
                          {s.sent_today} / {s.received_today}
                        </td>
                        <td className="px-4 py-3 text-right text-xs font-bold whitespace-nowrap">
                          <span className="text-emerald-700">{s.ai_replies_today}</span>
                          <span className="text-slate-300 mx-1">/</span>
                          <span className={s.failed_today > 0 ? 'text-rose-600' : 'text-slate-400'}>{s.failed_today}</span>
                        </td>
                        <td className="px-4 py-3 text-right text-[11px] text-slate-500 whitespace-nowrap">
                          {s.last_used_at ? formatDateTimeForUser(s.last_used_at, userTz) : '—'}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Upcoming Meetings & Recordings */}
          <div className="bg-white border border-slate-200/80 rounded-2xl shadow-xs overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-100 bg-purple-50/60 flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 className="text-sm font-black text-purple-950 flex items-center gap-2">
                  <Video className="w-4 h-4 text-purple-600" />
                  Upcoming Team Meetings &amp; Recording Intelligence
                </h2>
                <p className="text-[11px] text-slate-600 mt-0.5">
                  Next scheduled meetings across Google Meet, Zoom, and Microsoft Teams
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2 text-[11px] font-bold">
                {Object.entries(meetingsOverview.provider_breakdown || {}).map(([prov, cnt]) => (
                  <span key={prov} className="px-2.5 py-1 rounded-full bg-white border border-slate-200 text-slate-700">
                    {PROVIDER_LABELS[prov] || prov}: {cnt}
                  </span>
                ))}
                <span className="px-2.5 py-1 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-200">
                  Recordings: {meetingsOverview.recordings_completed ?? 0}
                </span>
                <span className="px-2.5 py-1 rounded-full bg-indigo-100 text-indigo-800 border border-indigo-200">
                  Transcripts: {meetingsOverview.transcriptions_completed ?? 0}
                </span>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-slate-100">
                <thead className="bg-slate-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-[11px] font-bold text-slate-500 uppercase tracking-wider">Prospect / Contact</th>
                    <th className="px-4 py-3 text-left text-[11px] font-bold text-slate-500 uppercase tracking-wider">Host PRE</th>
                    <th className="px-4 py-3 text-left text-[11px] font-bold text-slate-500 uppercase tracking-wider">Scheduled</th>
                    <th className="px-4 py-3 text-left text-[11px] font-bold text-slate-500 uppercase tracking-wider">Provider</th>
                    <th className="px-4 py-3 text-left text-[11px] font-bold text-slate-500 uppercase tracking-wider">Rec / Transcript</th>
                    <th className="px-4 py-3 text-right text-[11px] font-bold text-slate-500 uppercase tracking-wider">Link</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 bg-white">
                  {(meetingsOverview.upcoming || []).length === 0 ? (
                    <tr>
                      <td colSpan={6} className="px-6 py-8 text-center text-xs text-slate-400 italic">
                        No upcoming scheduled meetings for your team.
                      </td>
                    </tr>
                  ) : (
                    (meetingsOverview.upcoming || []).map((m) => (
                      <tr key={m.id} className="hover:bg-slate-50/70">
                        <td className="px-4 py-3">
                          <div className="text-xs font-bold text-slate-900">{m.company_name}</div>
                          {m.contact_name && <div className="text-[11px] text-slate-500">{m.contact_name}</div>}
                        </td>
                        <td className="px-4 py-3 text-xs font-semibold text-slate-700 whitespace-nowrap">{m.host_name || '—'}</td>
                        <td className="px-4 py-3 text-xs text-slate-700 whitespace-nowrap">
                          {m.scheduled_datetime ? formatDateTimeForUser(m.scheduled_datetime, userTz) : '—'}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-50 text-purple-700 border border-purple-200">
                            {PROVIDER_LABELS[m.meeting_provider] || m.meeting_provider}
                          </span>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-[11px] font-semibold text-slate-600">
                          {m.recording_status} / {m.transcription_status}
                        </td>
                        <td className="px-4 py-3 text-right whitespace-nowrap">
                          {m.meeting_link ? (
                            <a
                              href={m.meeting_link}
                              target="_blank"
                              rel="noreferrer"
                              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-[11px] font-bold"
                            >
                              Join <ExternalLink className="w-3 h-3" />
                            </a>
                          ) : (
                            <span className="text-xs text-slate-400">—</span>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Pending PRE Action Queue + Bulk Campaigns */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
            {/* Pending PRE Tasks */}
            <div className="bg-white border border-slate-200/80 rounded-2xl shadow-xs overflow-hidden flex flex-col">
              <div className="px-5 py-4 border-b border-slate-100 bg-amber-50/60 flex items-center justify-between gap-2">
                <div>
                  <h2 className="text-sm font-black text-amber-950 flex items-center gap-2">
                    <ClipboardList className="w-4 h-4 text-amber-600" />
                    Pending PRE Action Queue
                  </h2>
                  <p className="text-[11px] text-slate-600 mt-0.5">
                    {tasksOverview.email_reply_pending ?? 0} Email Replies · {tasksOverview.whatsapp_escalation_pending ?? 0} WhatsApp Escalations ·{' '}
                    {tasksOverview.pending_audit_reverifications ?? 0} Audit Re-verify
                  </p>
                </div>
                <Link
                  to="/pre-tasks"
                  className="px-3 py-1.5 rounded-lg bg-white border border-amber-200 text-amber-800 hover:bg-amber-100 text-[11px] font-bold"
                >
                  Open Tasks
                </Link>
              </div>
              <div className="divide-y divide-slate-100 flex-1 max-h-96 overflow-y-auto">
                {(tasksOverview.recent_pending || []).length === 0 ? (
                  <div className="p-8 text-center text-xs text-slate-400 italic">
                    All automated follow-up tasks are cleared.
                  </div>
                ) : (
                  (tasksOverview.recent_pending || []).map((t) => (
                    <div key={t.id} className="px-5 py-3 flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-bold border ${
                              t.task_type === 'EMAIL_REPLY'
                                ? 'bg-sky-50 text-sky-700 border-sky-200'
                                : 'bg-emerald-50 text-emerald-700 border-emerald-200'
                            }`}
                          >
                            {t.task_type === 'EMAIL_REPLY' ? 'Email Reply' : 'WA Escalation'}
                          </span>
                          <span className="text-xs font-bold text-slate-900 truncate">{t.company_name || t.sender_name || 'Contact'}</span>
                        </div>
                        <p className="text-xs text-slate-700 mt-1 line-clamp-1">{t.title}</p>
                        <p className="text-[10px] text-indigo-600 font-semibold mt-0.5">
                          Assigned: {t.assigned_pre_name || 'Unassigned'}
                        </p>
                      </div>
                      <span className="text-[10px] text-slate-400 whitespace-nowrap shrink-0">
                        {t.created_at ? formatDateTimeForUser(t.created_at, userTz) : ''}
                      </span>
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Bulk Email Campaigns */}
            <div className="bg-white border border-slate-200/80 rounded-2xl shadow-xs overflow-hidden flex flex-col">
              <div className="px-5 py-4 border-b border-slate-100 bg-sky-50/60 flex items-center justify-between gap-2">
                <div>
                  <h2 className="text-sm font-black text-sky-950 flex items-center gap-2">
                    <Send className="w-4 h-4 text-sky-600" />
                    Bulk Email Campaigns
                  </h2>
                  <p className="text-[11px] text-slate-600 mt-0.5">
                    {campaignsOverview.active_campaigns ?? 0} active · {campaignsOverview.total_campaigns ?? 0} total ·{' '}
                    {campaignsOverview.completed_today ?? 0} completed on {dashboard.date}
                  </p>
                </div>
                <Link
                  to="/email-campaigns"
                  className="px-3 py-1.5 rounded-lg bg-white border border-sky-200 text-sky-800 hover:bg-sky-100 text-[11px] font-bold"
                >
                  View Campaigns
                </Link>
              </div>
              <div className="divide-y divide-slate-100 flex-1 max-h-96 overflow-y-auto">
                {(campaignsOverview.recent_campaigns || []).length === 0 ? (
                  <div className="p-8 text-center text-xs text-slate-400 italic">
                    No bulk email campaigns created by your team yet.
                  </div>
                ) : (
                  (campaignsOverview.recent_campaigns || []).map((c) => {
                    const pct = c.total_count ? Math.round((c.sent_count / c.total_count) * 100) : 0;
                    return (
                      <div key={c.id} className="px-5 py-3.5 space-y-2">
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="text-xs font-bold text-slate-900 truncate">{c.name}</div>
                            <div className="text-[11px] text-slate-500 truncate">
                              {c.created_by_name} · {c.sender_email}
                            </div>
                          </div>
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-200 shrink-0">
                            {c.status}
                          </span>
                        </div>
                        <div>
                          <div className="flex justify-between text-[11px] font-semibold text-slate-600 mb-1">
                            <span>
                              Sent {c.sent_count} / {c.total_count} ({pct}%)
                            </span>
                            {c.failed_count > 0 && <span className="text-rose-600">{c.failed_count} failed</span>}
                          </div>
                          <div className="h-1.5 bg-slate-100 rounded-full overflow-hidden">
                            <div className="h-full bg-sky-500 rounded-full" style={{ width: `${pct}%` }} />
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: EMAIL INTELLIGENCE */}
      {dashboard && activeTab === 'email' && (
        <div className="space-y-6">
          <ManagerEmailActivitySection selectedDate={selectedDate} />
        </div>
      )}

      {/* Inspect PRE Member Snapshot Modal */}
      {inspectedMember && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 max-w-2xl w-full overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-100 bg-slate-50 flex items-center justify-between gap-3">
              <div>
                <h3 className="text-base font-black text-slate-900">{inspectedMember.name}</h3>
                <p className="text-xs text-slate-500">
                  {inspectedMember.email || `@${inspectedMember.username}`} · Reporting {dashboard?.date}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setInspectedMember(null)}
                className="p-1.5 rounded-lg hover:bg-slate-200 text-slate-500 cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-6 space-y-5 max-h-[80vh] overflow-y-auto">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div className="rounded-xl bg-indigo-50 border border-indigo-100 p-3">
                  <div className="text-[10px] font-bold text-indigo-700 uppercase">Entered / Total</div>
                  <div className="text-lg font-black text-indigo-950">
                    {inspectedMember.prospects_entered} / {inspectedMember.total_prospects}
                  </div>
                </div>
                <div className="rounded-xl bg-emerald-50 border border-emerald-100 p-3">
                  <div className="text-[10px] font-bold text-emerald-700 uppercase">Qualified / Total</div>
                  <div className="text-lg font-black text-emerald-950">
                    {inspectedMember.lead_qualified} / {inspectedMember.total_lead_qualified}
                  </div>
                </div>
                <div className="rounded-xl bg-sky-50 border border-sky-100 p-3">
                  <div className="text-[10px] font-bold text-sky-700 uppercase">Emails Out / In</div>
                  <div className="text-lg font-black text-sky-950">
                    {inspectedMember.emails_sent} / {inspectedMember.emails_received}
                  </div>
                </div>
                <div className="rounded-xl bg-amber-50 border border-amber-100 p-3">
                  <div className="text-[10px] font-bold text-amber-700 uppercase">Pending Tasks</div>
                  <div className="text-lg font-black text-amber-950">{inspectedMember.pending_tasks}</div>
                </div>
              </div>

              <div className="rounded-xl border border-slate-200 p-4 space-y-2 text-xs">
                <h4 className="font-black text-slate-800 uppercase tracking-wider text-[11px]">
                  Connected Channels &amp; Automation
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-slate-700">
                  <div>
                    <span className="font-semibold text-slate-500">Mailbox:</span>{' '}
                    {inspectedMember.integrations?.gmail_connected
                      ? inspectedMember.integrations.gmail_email
                      : 'Not Connected'}
                  </div>
                  <div>
                    <span className="font-semibold text-slate-500">Google Calendar:</span>{' '}
                    {inspectedMember.integrations?.google_calendar_connected ? 'Connected' : 'Not Connected'}
                  </div>
                  <div>
                    <span className="font-semibold text-slate-500">Microsoft 365 / Teams:</span>{' '}
                    {inspectedMember.integrations?.microsoft_connected ? 'Connected' : 'Not Connected'}
                  </div>
                  <div>
                    <span className="font-semibold text-slate-500">Zoom:</span>{' '}
                    {inspectedMember.integrations?.zoom_connected ? 'Connected' : 'Not Connected'}
                  </div>
                  <div>
                    <span className="font-semibold text-slate-500">WhatsApp:</span>{' '}
                    {inspectedMember.integrations?.whatsapp_status}{' '}
                    {inspectedMember.integrations?.whatsapp_phone ? `(${inspectedMember.integrations.whatsapp_phone})` : ''}
                  </div>
                  <div>
                    <span className="font-semibold text-slate-500">WhatsApp AI Auto-Reply:</span>{' '}
                    {inspectedMember.integrations?.whatsapp_ai_enabled ? 'ON' : 'OFF'}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
                <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                  <div className="text-slate-500 font-semibold">Calls Logged</div>
                  <div className="font-black text-slate-900 text-base">{inspectedMember.calls}</div>
                </div>
                <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                  <div className="text-slate-500 font-semibold">WhatsApp Out / AI</div>
                  <div className="font-black text-slate-900 text-base">
                    {inspectedMember.whatsapp_outbound} / {inspectedMember.whatsapp_ai_replies}
                  </div>
                </div>
                <div className="p-3 rounded-xl bg-slate-50 border border-slate-200">
                  <div className="text-slate-500 font-semibold">Waiting Email Replies</div>
                  <div className="font-black text-slate-900 text-base">{inspectedMember.waiting_email_threads}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ManagerDashboardPage;
