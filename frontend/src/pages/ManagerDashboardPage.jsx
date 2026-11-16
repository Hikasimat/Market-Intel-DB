import React, { useEffect, useState, useCallback } from 'react';
import { Link } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { fetchManagerDashboard } from '../features/manager/managerSlice';
import ManagerEmailActivitySection from '../components/ManagerEmailActivitySection';
import {
  BarChart2, Calendar, Users, CheckCircle, XCircle, Activity,
  Search, ChevronDown, ChevronUp, Eye, TrendingUp, Shield, Zap,
  Building2, UserCheck, ClipboardList, RefreshCw
} from 'lucide-react';

// ── Utility helpers ──────────────────────────────────────────────────────────

const today = () => new Date().toISOString().split('T')[0];

const roleBadge = (role) => {
  const map = {
    PRE: 'bg-indigo-100 text-indigo-700 border-indigo-200',
    LQ: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    MANAGER: 'bg-amber-100 text-amber-700 border-amber-200',
  };
  return map[role] || 'bg-slate-100 text-slate-600 border-slate-200';
};

// ── Small reusable components ────────────────────────────────────────────────

const SummaryCard = ({ title, value, icon: Icon, color, bg, sub }) => (
  <div className="relative overflow-hidden rounded-2xl bg-white border border-slate-200 p-5 shadow-sm">
    <div className="flex items-start justify-between mb-3">
      <div>
        <p className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-1">{title}</p>
        <h3 className="text-3xl font-black text-slate-800">{value ?? '—'}</h3>
      </div>
      <div className={`p-3 rounded-xl ${bg} ${color}`}>
        <Icon className="w-5 h-5" />
      </div>
    </div>
    {sub && <p className="text-xs text-slate-500 font-medium">{sub}</p>}
  </div>
);

const SectionHeader = ({ icon: Icon, title, color = 'text-indigo-600' }) => (
  <h2 className={`text-lg font-black text-slate-800 flex items-center gap-2 mb-4 ${color}`}>
    <Icon className="w-5 h-5" />
    {title}
  </h2>
);

const EmptyRow = ({ cols, msg = 'No data for selected date.' }) => (
  <tr>
    <td colSpan={cols} className="px-6 py-8 text-center text-slate-400 text-sm font-medium italic">
      {msg}
    </td>
  </tr>
);

const Th = ({ children, right }) => (
  <th
    scope="col"
    className={`px-4 py-3 text-${right ? 'right' : 'left'} text-xs font-bold text-slate-500 uppercase tracking-wider`}
  >
    {children}
  </th>
);

const Td = ({ children, right, muted }) => (
  <td className={`px-4 py-3 text-sm text-${right ? 'right' : 'left'} ${muted ? 'text-slate-400' : 'text-slate-700'} whitespace-nowrap`}>
    {children}
  </td>
);

// ── Section: PRE Daily Production ────────────────────────────────────────────

const PreProductionSection = ({ data }) => (
  <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
    <div className="px-6 py-4 border-b border-slate-100 bg-indigo-50">
      <SectionHeader icon={Zap} title="PRE Daily Production" color="text-indigo-700" />
    </div>
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-100">
        <thead className="bg-slate-50">
          <tr>
            <Th>PRE User</Th>
            <Th right>Prospects Entered</Th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-slate-100">
          {!data?.length
            ? <EmptyRow cols={2} />
            : data.map(u => (
              <tr key={u.user_id} className="hover:bg-slate-50 transition-colors">
                <Td>
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-full bg-indigo-100 flex items-center justify-center text-xs font-bold text-indigo-700">
                      {u.name[0]}
                    </div>
                    <span className="font-medium text-slate-800">{u.name}</span>
                  </div>
                </Td>
                <Td right>
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold ${u.prospects_entered > 0 ? 'bg-indigo-100 text-indigo-700' : 'bg-slate-100 text-slate-500'}`}>
                    {u.prospects_entered}
                  </span>
                </Td>
              </tr>
            ))
          }
        </tbody>
      </table>
    </div>
  </div>
);

// ── Section: LQ Daily Performance ────────────────────────────────────────────

const LqPerformanceSection = ({ data }) => (
  <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
    <div className="px-6 py-4 border-b border-slate-100 bg-emerald-50">
      <SectionHeader icon={TrendingUp} title="LQ Daily Performance" color="text-emerald-700" />
    </div>
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-100">
        <thead className="bg-slate-50">
          <tr>
            <Th>LQ User</Th>
            <Th right>Received</Th>
            <Th right>Attended</Th>
            <Th right>Lead Qualified</Th>
            <Th right>Not LQ</Th>
            <Th right>Calls</Th>
            <Th right>Emails</Th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-slate-100">
          {!data?.length
            ? <EmptyRow cols={7} />
            : data.map(u => (
              <tr key={u.user_id} className="hover:bg-slate-50 transition-colors">
                <Td>
                  <div className="flex items-center gap-2">
                    <div className="w-7 h-7 rounded-full bg-emerald-100 flex items-center justify-center text-xs font-bold text-emerald-700">
                      {u.name[0]}
                    </div>
                    <span className="font-medium text-slate-800">{u.name}</span>
                  </div>
                </Td>
                <Td right><span className="font-bold text-slate-700">{u.received}</span></Td>
                <Td right><span className={`font-bold ${u.attended > 0 ? 'text-sky-600' : 'text-slate-400'}`}>{u.attended}</span></Td>
                <Td right><span className={`font-bold ${u.lead_qualified > 0 ? 'text-emerald-600' : 'text-slate-400'}`}>{u.lead_qualified}</span></Td>
                <Td right><span className={`font-bold ${u.not_lead_qualified > 0 ? 'text-rose-500' : 'text-slate-400'}`}>{u.not_lead_qualified}</span></Td>
                <Td right muted>{u.calls}</Td>
                <Td right muted>{u.emails_sent}</Td>
              </tr>
            ))
          }
        </tbody>
      </table>
    </div>
  </div>
);

// ── Section: PRE → LQ Distribution ──────────────────────────────────────────

const DistributionSection = ({ data }) => (
  <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
    <div className="px-6 py-4 border-b border-slate-100 bg-sky-50">
      <SectionHeader icon={BarChart2} title="PRE → LQ Distribution" color="text-sky-700" />
    </div>
    <div className="p-6">
      {!data?.length ? (
        <p className="text-slate-400 text-sm text-center py-4 italic">No records received on selected date.</p>
      ) : (
        <div className="space-y-4">
          {data.map(lq => (
            <div key={lq.lq_user_id} className="bg-slate-50 rounded-xl p-4 border border-slate-200">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <div className="w-7 h-7 rounded-full bg-emerald-100 flex items-center justify-center text-xs font-bold text-emerald-700">
                    {lq.lq_name[0]}
                  </div>
                  <span className="font-bold text-slate-800 text-sm">{lq.lq_name}</span>
                </div>
                <span className="text-xs font-bold text-slate-500">
                  {lq.received} record{lq.received !== 1 ? 's' : ''} received
                </span>
              </div>
              {lq.received > 0 && Object.keys(lq.pre_source).length > 0 ? (
                <div className="space-y-2">
                  {Object.entries(lq.pre_source).map(([preName, count]) => {
                    const pct = Math.round((count / lq.received) * 100);
                    return (
                      <div key={preName}>
                        <div className="flex items-center justify-between mb-1 text-xs">
                          <span className="font-medium text-slate-600">{preName}</span>
                          <span className="font-bold text-indigo-600">{count} ({pct}%)</span>
                        </div>
                        <div className="h-2 bg-slate-200 rounded-full overflow-hidden">
                          <div className="h-full bg-indigo-500 rounded-full" style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-xs text-slate-400 italic">No records from PRE on this date.</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  </div>
);

// ── Section: Daily Audit Sample ──────────────────────────────────────────────

const AuditSection = () => {
  return (
    <div className="bg-gradient-to-r from-amber-50 to-amber-100 border border-amber-200 rounded-2xl p-6 shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
      <div>
        <h2 className="text-lg font-black text-amber-800 flex items-center gap-2 mb-1">
          <Shield className="w-5 h-5" />
          Daily Quality Audit
        </h2>
        <p className="text-sm text-amber-700 font-medium max-w-2xl">
          Review 10 automatically sampled records for each PRE and LQ user, including detailed daily activities.
        </p>
      </div>
      <Link 
        to="/manager-audit" 
        className="shrink-0 bg-amber-600 hover:bg-amber-700 text-white font-bold py-2.5 px-5 rounded-xl shadow-sm transition-colors flex items-center gap-2"
      >
        <ClipboardList className="w-4 h-4" />
        View Daily Audit
      </Link>
    </div>
  );
};

// ── Main Page ────────────────────────────────────────────────────────────────

const ManagerDashboardPage = () => {
  const dispatch = useDispatch();
  const { dashboard, loading, error } = useSelector((state) => state.manager);
  const [selectedDate, setSelectedDate] = useState(today());

  const loadData = useCallback(() => {
    dispatch(fetchManagerDashboard(selectedDate));
  }, [dispatch, selectedDate]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const summary = dashboard?.summary || {};
  const summaryCards = [
    { title: 'PRE Entered', value: summary.pre_entered ?? 0, icon: Zap, color: 'text-indigo-600', bg: 'bg-indigo-50', sub: `${summary.pre_users_active ?? 0} active PRE users` },
    { title: 'LQ Received', value: summary.lq_received ?? 0, icon: Users, color: 'text-sky-600', bg: 'bg-sky-50', sub: `${summary.lq_users_active ?? 0} active LQ users` },
    { title: 'Attended', value: summary.attended ?? 0, icon: UserCheck, color: 'text-purple-600', bg: 'bg-purple-50', sub: 'attended_meeting flagged' },
    { title: 'Lead Qualified', value: summary.lead_qualified ?? 0, icon: CheckCircle, color: 'text-emerald-600', bg: 'bg-emerald-50', sub: 'qualification decisions' },
    { title: 'Not Lead Qualified', value: summary.not_lead_qualified ?? 0, icon: XCircle, color: 'text-rose-500', bg: 'bg-rose-50', sub: 'decided non-LQ' },
    { title: 'Activities', value: summary.activities ?? 0, icon: Activity, color: 'text-amber-600', bg: 'bg-amber-50', sub: 'calls + emails logged' },
  ];

  return (
    <div className="min-h-[calc(100vh-64px)] bg-slate-50 p-6 md:p-8 font-sans text-slate-800">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-end justify-between gap-4 mb-8">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-amber-50 border border-amber-200 text-amber-700 text-xs font-bold uppercase tracking-wider mb-3">
            <Shield className="w-4 h-4" />
            Manager Audit & Monitoring
          </div>
          <h1 className="text-4xl font-black text-slate-900 tracking-tight">
            Manager <span className="text-amber-600">Dashboard</span>
          </h1>
          <p className="text-slate-500 mt-2 font-medium">
            Daily PRE/LQ performance, audit samples, and activity monitoring.
          </p>
        </div>

        {/* Date picker + refresh */}
        <div className="flex items-center gap-3 bg-white border border-slate-200 rounded-2xl px-4 py-3 shadow-sm">
          <Calendar className="w-5 h-5 text-slate-400 shrink-0" />
          <input
            type="date"
            value={selectedDate}
            max={today()}
            onChange={(e) => setSelectedDate(e.target.value)}
            className="text-sm font-bold text-slate-800 bg-transparent border-0 outline-0 cursor-pointer"
          />
          <button
            onClick={loadData}
            disabled={loading}
            className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 hover:text-slate-700 transition-colors disabled:opacity-50"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Loading */}
      {loading && (
        <div className="flex flex-col items-center gap-4 py-20">
          <Activity className="w-10 h-10 text-amber-600 animate-pulse" />
          <p className="text-amber-700 font-bold uppercase tracking-widest animate-pulse text-sm">Loading Analytics...</p>
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <div className="bg-red-50 border border-red-200 rounded-2xl p-6 text-center max-w-lg mx-auto">
          <XCircle className="w-10 h-10 text-red-500 mx-auto mb-3" />
          <h2 className="text-lg font-bold text-red-700 mb-2">Error Loading Dashboard</h2>
          <p className="text-red-600 text-sm">{typeof error === 'string' ? error : JSON.stringify(error)}</p>
          <button onClick={loadData} className="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-bold hover:bg-red-700 transition-colors">
            Retry
          </button>
        </div>
      )}

      {/* Dashboard content */}
      {!loading && !error && dashboard && (
        <div className="space-y-8">
          {/* Reporting period badge */}
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-white border border-slate-200 text-slate-600 text-xs font-bold shadow-sm">
            <Calendar className="w-3.5 h-3.5 text-amber-500" />
            Reporting for: {dashboard.date}
          </div>

          {/* Summary KPI row */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
            {summaryCards.map((card) => (
              <SummaryCard key={card.title} {...card} />
            ))}
          </div>

          {/* PRE Production + LQ Performance */}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            <PreProductionSection data={dashboard.pre_users} />
            <LqPerformanceSection data={dashboard.lq_users} />
          </div>

          {/* Distribution */}
          <DistributionSection data={dashboard.lq_pre_distribution} />

          {/* Audit */}
          <AuditSection />

          {/* PRE Email Activity & Conversation Summaries */}
          <ManagerEmailActivitySection selectedDate={selectedDate} />

        </div>
      )}

      {/* Empty state when no data loaded yet */}
      {!loading && !error && !dashboard && (
        <div className="flex flex-col items-center gap-3 py-20 text-slate-400">
          <ClipboardList className="w-12 h-12" />
          <p className="font-medium">Select a date to load analytics.</p>
        </div>
      )}
    </div>
  );
};

export default ManagerDashboardPage;
