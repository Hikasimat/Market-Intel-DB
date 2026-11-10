import React, { useEffect, useState } from 'react';
import { Target, Zap, Trophy, Flame, Activity, Users, Star, ArrowUpRight, CheckCircle, TrendingUp, Calendar } from 'lucide-react';
import api from '../services/api';

const CircularProgress = ({ percentage, colorClass, size = 120, strokeWidth = 8, label }) => {
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (Math.min(percentage, 100) / 100) * circumference;

  return (
    <div className="relative flex flex-col items-center justify-center">
      <svg width={size} height={size} className="transform -rotate-90">
        <circle
          className="text-slate-100"
          strokeWidth={strokeWidth}
          stroke="currentColor"
          fill="transparent"
          r={radius}
          cx={size / 2}
          cy={size / 2}
        />
        <circle
          className={colorClass}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          stroke="currentColor"
          fill="transparent"
          r={radius}
          cx={size / 2}
          cy={size / 2}
          style={{ transition: 'stroke-dashoffset 1s ease-out' }}
        />
      </svg>
      <div className="absolute flex flex-col items-center justify-center text-center">
        <span className="text-2xl font-black text-slate-800">{percentage.toFixed(0)}%</span>
        {label && <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mt-0.5">{label}</span>}
      </div>
    </div>
  );
};

const MetricCard = ({ title, value, subtitle, icon: Icon, colorClass, bgIconClass }) => (
  <div className={`relative overflow-hidden rounded-2xl bg-white border border-slate-200 p-6 shadow-sm`}>
    <div className="flex justify-between items-start mb-4 relative z-10">
      <div>
        <p className="text-sm font-bold text-slate-500 uppercase tracking-wider mb-1">{title}</p>
        <h3 className="text-4xl font-black text-slate-800">{value}</h3>
      </div>
      <div className={`p-3 rounded-xl ${bgIconClass} ${colorClass}`}>
        <Icon className="w-6 h-6" />
      </div>
    </div>
    <p className="text-xs font-semibold text-slate-500 relative z-10">{subtitle}</p>
  </div>
);

const PreDashboardPage = () => {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState(null);

  useEffect(() => {
    const fetchStats = async () => {
      try {
        const response = await api.get('/pre-dashboard-stats/');
        setStats(response.data);
      } catch (error) {
        console.error('Failed to fetch dashboard stats', error);
        setErrorMsg(error.response?.data?.error || error.message);
      } finally {
        setLoading(false);
      }
    };
    fetchStats();
  }, []);

  if (loading) {
    return (
      <div className="min-h-[calc(100vh-64px)] bg-slate-50 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Activity className="w-12 h-12 text-indigo-600 animate-pulse" />
          <p className="text-indigo-600 font-bold uppercase tracking-widest animate-pulse">Initializing Dashboard...</p>
        </div>
      </div>
    );
  }

  if (errorMsg) {
    return (
      <div className="min-h-[calc(100vh-64px)] bg-slate-50 flex items-center justify-center p-6 text-center">
        <div className="bg-red-50 border border-red-200 p-6 rounded-2xl max-w-lg w-full">
          <Activity className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-red-700 mb-2">Error Loading Dashboard</h2>
          <p className="text-red-600">{errorMsg}</p>
        </div>
      </div>
    );
  }

  if (!stats) return null;

  return (
    <div className="min-h-[calc(100vh-64px)] bg-slate-50 p-6 md:p-8 lg:p-10 font-sans text-slate-800 max-w-[1600px] mx-auto">
      
      {/* Header */}
      <div className="w-full mx-auto mb-10 flex flex-col md:flex-row md:items-end justify-between gap-6">
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-indigo-50 border border-indigo-100 text-indigo-700 text-xs font-bold uppercase tracking-wider mb-3">
            <Flame className="w-4 h-4 text-orange-500" />
            Performance Tracking Active
          </div>
          <h1 className="text-4xl md:text-5xl font-black text-slate-900 tracking-tight">
            Engagement <span className="text-indigo-600">Dashboard</span>
          </h1>
          <p className="text-slate-500 font-medium mt-2 max-w-xl">
            Track your daily and monthly prospect-entry targets. Convert prospects to unlock achievements and maintain your streak.
          </p>
        </div>
        
        <div className="flex items-center gap-4 bg-white border border-slate-200 p-4 rounded-2xl shadow-sm">
          <div className="text-right">
            <p className="text-xs font-bold text-slate-500 uppercase tracking-widest">Monthly Target</p>
            <p className="text-2xl font-black text-slate-800">{stats.monthly_target}</p>
          </div>
          <div className="w-px h-10 bg-slate-200"></div>
          <div className="text-right">
            <p className="text-xs font-bold text-slate-500 uppercase tracking-widest">Daily Goal</p>
            <p className="text-2xl font-black text-indigo-600">{stats.daily_target}</p>
          </div>
        </div>
      </div>

      <div className="w-full mx-auto space-y-8">
        
        {/* Top KPI Row */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <MetricCard 
            title="Entered Today" 
            value={stats.entered_today} 
            subtitle={`Goal: ${stats.daily_target} / day`}
            icon={Zap} 
            colorClass="text-amber-500"
            bgIconClass="bg-amber-50"
          />
          <MetricCard 
            title="Entered This Month" 
            value={stats.entered_this_month} 
            subtitle={`Goal: ${stats.monthly_target} prospects`}
            icon={Target} 
            colorClass="text-indigo-600"
            bgIconClass="bg-indigo-50"
          />
          <MetricCard 
            title="Total Entered" 
            value={stats.total_entered} 
            subtitle="All time total prospects"
            icon={Users} 
            colorClass="text-sky-500"
            bgIconClass="bg-sky-50"
          />
          <MetricCard 
            title="Lead Qualified" 
            value={stats.total_lead_qualified} 
            subtitle="Successfully converted prospects"
            icon={Trophy} 
            colorClass="text-emerald-500"
            bgIconClass="bg-emerald-50"
          />
        </div>

        {/* Task Metrics Row */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
          <MetricCard 
            title="Tasks Today" 
            value={stats.tasks_completed_today} 
            subtitle={`${stats.tasks_received_today} received today`}
            icon={Activity} 
            colorClass="text-indigo-500"
            bgIconClass="bg-indigo-50"
          />
          <MetricCard 
            title="Tasks This Month" 
            value={stats.tasks_completed_month} 
            subtitle={`${stats.tasks_received_month} received this month`}
            icon={Calendar} 
            colorClass="text-sky-600"
            bgIconClass="bg-sky-50"
          />
          <MetricCard 
            title="Total Tasks Received" 
            value={stats.total_tasks_received} 
            subtitle="All time tasks received"
            icon={Target} 
            colorClass="text-amber-500"
            bgIconClass="bg-amber-50"
          />
          <MetricCard 
            title="Total Tasks Completed" 
            value={stats.completed_tasks} 
            subtitle="All time tasks completed"
            icon={CheckCircle} 
            colorClass="text-emerald-500"
            bgIconClass="bg-emerald-50"
          />
        </div>

        {/* Progress Section */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Main Progress Panel */}
          <div className="lg:col-span-2 bg-white border border-slate-200 rounded-3xl p-8 shadow-sm relative overflow-hidden">
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-indigo-500 via-sky-500 to-emerald-500"></div>
            
            <h2 className="text-xl font-black text-slate-800 flex items-center gap-3 mb-8">
              <TrendingUp className="w-6 h-6 text-indigo-600" />
              Target Progression
            </h2>

            <div className="flex flex-col md:flex-row items-center justify-around gap-8 md:gap-4">
              
              <div className="flex flex-col items-center">
                <CircularProgress percentage={stats.daily_average} colorClass="text-amber-500" label="Daily Avg" />
                <p className="text-sm font-medium text-slate-500 mt-4 text-center max-w-[150px]">
                  Daily entry target completion
                </p>
              </div>

              <div className="hidden md:block w-px h-32 bg-slate-200"></div>

              <div className="flex flex-col items-center">
                <CircularProgress percentage={stats.monthly_average} colorClass="text-indigo-600" label="Monthly Avg" size={150} strokeWidth={10} />
                <p className="text-sm font-medium text-slate-500 mt-4 text-center max-w-[150px]">
                  Overall monthly progress
                </p>
              </div>

              <div className="hidden md:block w-px h-32 bg-slate-200"></div>

              <div className="flex flex-col items-center">
                <CircularProgress percentage={stats.task_completion_average} colorClass="text-emerald-500" label="Task Avg" />
                <div className="flex flex-col items-center mt-3">
                  <p className="text-sm font-bold text-slate-800">
                    {stats.completed_tasks} / {stats.total_tasks_received} Tasks
                  </p>
                  <p className="text-xs font-medium text-slate-500 mt-1 text-center max-w-[150px]">
                    Task completion rate
                  </p>
                </div>
              </div>

            </div>

            {/* Linear Progress Bar for Monthly Goal */}
            <div className="mt-10">
              <div className="flex justify-between items-end mb-2">
                <span className="text-sm font-bold text-slate-500 tracking-wide">MONTHLY TARGET COMPLETION</span>
                <span className="text-sm font-black text-indigo-600">{stats.entered_this_month} / {stats.monthly_target} prospects</span>
              </div>
              <div className="h-4 w-full bg-slate-100 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-indigo-500 rounded-full relative"
                  style={{ width: `${Math.min((stats.entered_this_month / stats.monthly_target) * 100, 100)}%` }}
                >
                  <div className="absolute inset-0 bg-white/20 w-full h-full animate-[shimmer_2s_infinite]"></div>
                </div>
              </div>
            </div>
          </div>

          {/* Qualification Metrics */}
          <div className="bg-white border border-slate-200 rounded-3xl p-8 shadow-sm flex flex-col justify-between relative overflow-hidden">
            <div className="absolute -bottom-10 -right-10 opacity-5">
              <Star className="w-64 h-64 text-slate-900" />
            </div>

            <div>
              <h2 className="text-xl font-black text-slate-800 flex items-center gap-3 mb-6 relative z-10">
                <CheckCircle className="w-6 h-6 text-emerald-500" />
                Qualification Breakdown
              </h2>

              <div className="space-y-4 relative z-10">
                <div className="bg-emerald-50 rounded-2xl p-4 border border-emerald-100 flex items-center justify-between">
                  <div>
                    <p className="text-xs font-bold text-emerald-600 uppercase tracking-widest mb-1">Qualified Leads</p>
                    <h3 className="text-2xl font-black text-emerald-700">{stats.total_lead_qualified} <span className="text-sm font-bold text-emerald-500 text-opacity-80">({stats.lead_qualified_percentage}%)</span></h3>
                  </div>
                  <div className="p-3 bg-emerald-100 rounded-xl border border-emerald-200">
                    <Trophy className="w-6 h-6 text-emerald-600" />
                  </div>
                </div>

                <div className="bg-sky-50 rounded-2xl p-4 border border-sky-100 flex items-center justify-between">
                  <div>
                    <p className="text-xs font-bold text-sky-600 uppercase tracking-widest mb-1">LQ Attended</p>
                    <h3 className="text-2xl font-black text-sky-700">{stats.lq_attended_prospects}</h3>
                  </div>
                  <div className="p-3 bg-sky-100 rounded-xl border border-sky-200">
                    <Users className="w-6 h-6 text-sky-600" />
                  </div>
                </div>

                <div className="bg-rose-50 rounded-2xl p-4 border border-rose-100 flex items-center justify-between">
                  <div>
                    <p className="text-xs font-bold text-rose-600 uppercase tracking-widest mb-1">Not Qualified</p>
                    <h3 className="text-2xl font-black text-rose-700">{stats.unqualified_prospects}</h3>
                  </div>
                  <div className="p-3 bg-rose-100 rounded-xl border border-rose-200">
                    <Target className="w-6 h-6 text-rose-600" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
};

export default PreDashboardPage;
