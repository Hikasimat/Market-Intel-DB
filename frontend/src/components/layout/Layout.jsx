import React, { useState, useEffect, useRef } from 'react';
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import { useSelector, useDispatch } from 'react-redux';
import { toast } from 'react-toastify';
import SearchableSelect from '../common/SearchableSelect';
import { 
  LogOut, Users, Calendar, Activity, ClipboardList, UserCircle, Mail, 
  LayoutDashboard, Shield, BarChart2, Eye, Settings, X, MessageCircle, 
  MessageSquare, Building2, Globe, PanelLeftClose, PanelLeftOpen, Menu,
  Search, Mic, ChevronDown, ChevronRight, Folder, MoreVertical, Plus,
  FileText, CheckSquare, Layers
} from 'lucide-react';
import { logout, loginSuccess } from '../../features/auth/authSlice';
import api from '../../services/api';
import { store } from '../../app/store';
import NotificationCenter from './NotificationCenter';
import { InstagramIcon, FacebookIcon, TwitterXIcon } from '../common/SocialIcons';

const CubeLogo = ({ className = "w-6 h-6" }) => (
  <svg className={`${className} shrink-0`} viewBox="0 0 24 24" fill="none">
    {/* Top Face */}
    <path d="M12 2.5L20.5 7.4L12 12.3L3.5 7.4L12 2.5Z" fill="#1e293b" />
    {/* Left Face */}
    <path d="M3.5 7.4L12 12.3V21.5L3.5 16.6V7.4Z" fill="#0f172a" />
    {/* Right Face */}
    <path d="M20.5 7.4L12 12.3V21.5L20.5 16.6V7.4Z" fill="#334155" />
  </svg>
);

const Layout = () => {
  const { user, accessToken, refreshToken } = useSelector((state) => state.auth);
  const unreadCount = useSelector((state) => state.inbox.unreadCount);
  const dispatch = useDispatch();
  const location = useLocation();
  const navigate = useNavigate();
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [selectedTimezone, setSelectedTimezone] = useState(user?.timezone || 'UTC');
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [sidebarSearch, setSidebarSearch] = useState('');
  const [isFileSectionOpen, setIsFileSectionOpen] = useState(true);
  const [isAppsSectionOpen, setIsAppsSectionOpen] = useState(true);

  const toggleSidebar = () => setIsSidebarCollapsed((prev) => !prev);

  const handleSaveSettings = async () => {
    try {
      await api.patch('/auth/me/', { timezone: selectedTimezone });
      const res = await api.get('/auth/me/');
      dispatch(loginSuccess({ access: accessToken, refresh: refreshToken, user: res.data }));
      setIsSettingsOpen(false);
      toast.success('Timezone updated successfully.');
    } catch(err) {
      toast.error('Failed to update timezone.');
    }
  };

  const handleLogout = async () => {
    const currentRefreshToken = store?.getState?.()?.auth?.refreshToken;
    if (currentRefreshToken) {
      try {
        await api.post('/auth/logout/', { refresh: currentRefreshToken });
      } catch (e) {
        console.warn('Server logout failed; proceeding with client logout.', e);
      }
    }
    dispatch(logout());
    navigate('/login');
  };

  // Idle Session Timeout (30 minutes)
  const idleTimeoutRef = useRef(null);
  const IDLE_TIMEOUT_MS = 30 * 60 * 1000;

  useEffect(() => {
    if (!user) return;

    const resetIdleTimeout = () => {
      if (idleTimeoutRef.current) {
        clearTimeout(idleTimeoutRef.current);
      }
      idleTimeoutRef.current = setTimeout(() => {
        console.warn('Session expired due to inactivity.');
        handleLogout();
      }, IDLE_TIMEOUT_MS);
    };

    resetIdleTimeout();

    const events = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'];
    events.forEach((event) => {
      window.addEventListener(event, resetIdleTimeout);
    });

    return () => {
      if (idleTimeoutRef.current) clearTimeout(idleTimeoutRef.current);
      events.forEach((event) => {
        window.removeEventListener(event, resetIdleTimeout);
      });
    };
  }, [user]);

  // Primary navigation items according to user roles
  const primaryNavItems = [];

  if (user?.role === 'PRE') {
    primaryNavItems.push(
      { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
      { path: '/pre-tasks', label: 'Tasks', icon: ClipboardList },
      { path: '/prospects', label: 'Prospects', icon: Users },
      { path: '/calendar', label: 'Calendar', icon: Calendar },
      { path: '/inbox', label: 'Email', icon: Mail, badge: unreadCount > 0 ? unreadCount : null },
      { path: '/whatsapp', label: 'WhatsApp', icon: MessageCircle },
      { 
        path: '/lq-pipeline', 
        label: 'LQ Pipeline', 
        icon: Activity,
        subItems: [
          { path: '/lq-pipeline', label: 'All Prospects', exact: true },
          { path: '/lq-pipeline/pending', label: 'Verification Pending', exact: true },
          { path: '/lq-pipeline/verified', label: 'Outreached', exact: true },
          { path: '/lq-pipeline/issued', label: 'Issued Task to PRE', exact: true },
        ]
      },
      { path: '/government-entities', label: 'Government Entities', icon: Building2 },
      { path: '/key-people', label: 'Key People', icon: UserCircle },
      { path: '/market-events', label: 'Market Events', icon: Calendar },
      { path: '/settings', label: 'Settings', icon: Settings }
    );
  } else if (user?.role === 'MANAGER') {
    primaryNavItems.push(
      { path: '/manager-dashboard', label: 'Manager Dashboard', icon: Shield },
      { path: '/pre-tasks', label: 'Tasks', icon: ClipboardList },
      { path: '/prospects', label: 'Prospects', icon: Users },
      { path: '/calendar', label: 'Calendar', icon: Calendar },
      { path: '/inbox', label: 'Email', icon: Mail, badge: unreadCount > 0 ? unreadCount : null },
      { path: '/whatsapp', label: 'WhatsApp', icon: MessageCircle },
      { path: '/lq-pipeline', label: 'LQ Pipeline', icon: Activity },
      { path: '/manager-audit', label: 'Daily Audit', icon: ClipboardList },
      { path: '/key-people', label: 'Key People', icon: UserCircle },
      { path: '/market-events', label: 'Market Events', icon: Calendar },
      { path: '/users', label: 'User Management', icon: Users }
    );
  } else if (user?.role === 'DM') {
    primaryNavItems.push(
      { path: '/digital-marketing', label: 'Dashboard', icon: LayoutDashboard },
      { path: '/digital-marketing/messages', label: 'Messages', icon: MessageSquare },
      { path: '/digital-marketing/instagram', label: 'Instagram', icon: InstagramIcon },
      { path: '/digital-marketing/facebook', label: 'Facebook', icon: FacebookIcon },
      { path: '/digital-marketing/twitter', label: 'Twitter / X', icon: TwitterXIcon },
      { path: '/digital-marketing/ads-insights', label: 'Ads & Insights', icon: BarChart2 },
      { path: '/digital-marketing/cms', label: 'Headless CMS', icon: Globe }
    );
  }

  if (user?.is_superuser && !primaryNavItems.some(item => item.path === '/users')) {
    primaryNavItems.push(
      { path: '/users', label: 'User Management', icon: Users }
    );
  }

  // Filtered by search if user is searching in sidebar
  const filteredNavItems = sidebarSearch.trim()
    ? primaryNavItems.filter(item => item.label.toLowerCase().includes(sidebarSearch.toLowerCase()))
    : primaryNavItems;

  const fileItems = [
    { label: 'Store', path: '/prospects' },
    { label: 'Company', path: '/government-entities' },
    { label: 'Employee', path: '/key-people' },
  ];

  const appItems = [
    { label: 'LQ Pipeline', path: '/lq-pipeline', icon: Activity },
    { label: 'Email', path: '/inbox', icon: Mail },
    { label: 'WhatsApp', path: '/whatsapp', icon: MessageCircle },
  ];

  return (
    <div className="min-h-screen bg-[#f4f5f7] flex font-sans antialiased text-slate-800">
      {/* 
        Modern Taskk-Style Sidebar:
        Expanded: w-64 floating rounded card
        Collapsed: w-[72px] sleek icon rail with dark hover tooltips matching Image 1
        NEVER completely disappears to w-0, so the toggle button is ALWAYS visible!
      */}
      <aside 
        className={`m-3 h-[calc(100vh-24px)] bg-white border border-slate-200/80 rounded-3xl shadow-[0_4px_24px_rgba(0,0,0,0.03)] flex flex-col shrink-0 transition-all duration-300 ease-in-out sticky top-3 z-40 select-none ${
          isSidebarCollapsed ? 'w-[72px] items-center py-4 px-2' : 'w-64 p-3.5'
        }`}
      >
        {/* ─── EXPANDED SIDEBAR VIEW ─── */}
        {!isSidebarCollapsed ? (
          <div className="flex flex-col h-full w-full">
            {/* Header: 3D Cube Logo + Brand Title + Collapse Button */}
            <div className="flex items-center justify-between px-2 pt-1 pb-3 shrink-0">
              <Link to="/dashboard" className="flex items-center gap-2.5 group cursor-pointer">
                <CubeLogo className="w-6 h-6 transition-transform group-hover:scale-105" />
                <span className="font-bold text-slate-900 text-lg tracking-tight">MarketIntel DB</span>
              </Link>
              <button
                type="button"
                onClick={toggleSidebar}
                className="p-1.5 text-slate-400 hover:text-slate-800 hover:bg-slate-100 rounded-xl transition cursor-pointer"
                title="Collapse sidebar"
              >
                <PanelLeftClose className="w-4 h-4" />
              </button>
            </div>

            {/* Search Bar matching Image 1 with Mic icon */}
            <div className="px-1 mb-2 shrink-0">
              <div className="relative flex items-center bg-[#f4f5f6] hover:bg-[#eceef0] focus-within:bg-white focus-within:ring-2 focus-within:ring-slate-200 border border-transparent focus-within:border-slate-300 rounded-xl px-3 py-2 transition-all">
                <Search className="w-4 h-4 text-slate-400 mr-2 shrink-0 pointer-events-none" />
                <input
                  type="text"
                  placeholder="Search"
                  value={sidebarSearch}
                  onChange={(e) => setSidebarSearch(e.target.value)}
                  className="bg-transparent text-xs text-slate-800 placeholder-slate-400 outline-none w-full font-medium"
                />
                {sidebarSearch ? (
                  <button type="button" onClick={() => setSidebarSearch('')} className="p-0.5 text-slate-400 hover:text-slate-600">
                    <X className="w-3.5 h-3.5" />
                  </button>
                ) : (
                  <Mic className="w-4 h-4 text-slate-400 ml-1 shrink-0 hover:text-slate-700 cursor-pointer transition-colors" />
                )}
              </div>
            </div>

            {/* Navigation List */}
            <nav className="flex-1 overflow-y-auto space-y-1 pr-1 custom-scrollbar">
              {filteredNavItems.map((item) => {
                const Icon = item.icon;
                const isActive = location.pathname.startsWith(item.path);

                return (
                  <div key={item.path} className="space-y-0.5">
                    <Link
                      to={item.path}
                      className={`flex items-center justify-between px-3 py-2 rounded-xl text-xs transition-all ${
                        isActive
                          ? 'bg-white text-slate-900 font-semibold border border-slate-200/90 shadow-[0_2px_8px_rgba(0,0,0,0.05)]'
                          : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/70 font-medium'
                      }`}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <Icon className={`w-4 h-4 shrink-0 ${isActive ? 'text-slate-900' : 'text-slate-500'}`} />
                        <span className="truncate">{item.label}</span>
                      </div>
                      {item.badge && (
                        <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-rose-500 text-white shrink-0 shadow-xs">
                          {item.badge > 999 ? '999+' : item.badge}
                        </span>
                      )}
                    </Link>

                    {/* Sub-items if expanded */}
                    {item.subItems && isActive && (
                      <div className="pl-7 pr-2 py-1 space-y-1">
                        {item.subItems.map((sub) => {
                          const isSubActive = sub.exact
                            ? location.pathname === sub.path
                            : location.pathname.startsWith(sub.path);
                          return (
                            <Link
                              key={sub.path}
                              to={sub.path}
                              className={`block px-2.5 py-1.5 text-[11px] rounded-lg transition-all ${
                                isSubActive
                                  ? 'bg-slate-100 text-slate-900 font-semibold'
                                  : 'text-slate-500 hover:text-slate-800 hover:bg-slate-50 font-normal'
                              }`}
                            >
                              {sub.label}
                            </Link>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}

              {/* Collapsible File Section matching Image 1 */}
              {!sidebarSearch && (
                <div className="pt-2 border-t border-slate-100">
                  <button
                    type="button"
                    onClick={() => setIsFileSectionOpen((prev) => !prev)}
                    className="flex items-center justify-between w-full px-2 py-1.5 text-xs text-slate-500 hover:text-slate-800 rounded-lg hover:bg-slate-50 cursor-pointer font-medium transition"
                  >
                    <div className="flex items-center gap-1.5">
                      {isFileSectionOpen ? (
                        <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                      ) : (
                        <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
                      )}
                      <span className="font-semibold text-slate-600">File</span>
                    </div>
                    <div className="flex items-center gap-1 text-slate-400" onClick={(e) => e.stopPropagation()}>
                      <Plus className="w-3.5 h-3.5 hover:text-slate-700 cursor-pointer" />
                      <MoreVertical className="w-3.5 h-3.5 hover:text-slate-700 cursor-pointer" />
                    </div>
                  </button>

                  {isFileSectionOpen && (
                    <div className="pl-4 pr-1 py-1 space-y-0.5">
                      {fileItems.map((fItem) => (
                        <Link
                          key={fItem.label}
                          to={fItem.path}
                          className="flex items-center gap-2.5 px-2.5 py-1.5 text-xs text-slate-600 hover:text-slate-900 hover:bg-slate-100/70 rounded-lg transition font-medium"
                        >
                          <Folder className="w-3.5 h-3.5 text-slate-400" />
                          <span>{fItem.label}</span>
                        </Link>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Collapsible Apps Section matching Image 1 */}
              {!sidebarSearch && (
                <div className="pt-1">
                  <button
                    type="button"
                    onClick={() => setIsAppsSectionOpen((prev) => !prev)}
                    className="flex items-center justify-between w-full px-2 py-1.5 text-xs text-slate-500 hover:text-slate-800 rounded-lg hover:bg-slate-50 cursor-pointer font-medium transition"
                  >
                    <div className="flex items-center gap-1.5">
                      {isAppsSectionOpen ? (
                        <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
                      ) : (
                        <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
                      )}
                      <span className="font-semibold text-slate-600">Apps</span>
                    </div>
                    <div className="flex items-center gap-1 text-slate-400" onClick={(e) => e.stopPropagation()}>
                      <Plus className="w-3.5 h-3.5 hover:text-slate-700 cursor-pointer" />
                      <MoreVertical className="w-3.5 h-3.5 hover:text-slate-700 cursor-pointer" />
                    </div>
                  </button>

                  {isAppsSectionOpen && (
                    <div className="pl-4 pr-1 py-1 space-y-0.5">
                      {appItems.map((aItem) => {
                        const AppIcon = aItem.icon;
                        const isAppActive = location.pathname.startsWith(aItem.path);
                        return (
                          <Link
                            key={aItem.label}
                            to={aItem.path}
                            className={`flex items-center gap-2.5 px-2.5 py-1.5 text-xs rounded-lg transition font-medium ${
                              isAppActive
                                ? 'bg-slate-100 text-slate-900 font-semibold'
                                : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100/70'
                            }`}
                          >
                            <AppIcon className="w-3.5 h-3.5 text-slate-400" />
                            <span>{aItem.label}</span>
                          </Link>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </nav>

            {/* User Profile Card at Bottom */}
            {user && (
              <div className="pt-3 border-t border-slate-100 shrink-0 mt-auto">
                <div className="flex items-center justify-between p-2 bg-[#f8f9fa] rounded-2xl border border-slate-200/60">
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div className="w-8 h-8 rounded-full bg-slate-900 text-white font-bold text-xs flex items-center justify-center shrink-0">
                      {user.first_name?.[0] || user.username?.[0] || 'U'}
                    </div>
                    <div className="min-w-0 flex flex-col">
                      <div className="text-xs font-bold text-slate-900 truncate">
                        {user.first_name ? `${user.first_name} ${user.last_name || ''}` : user.username}
                      </div>
                      <div className="text-[10px] text-slate-500 font-semibold uppercase tracking-wider truncate">
                        {user.role}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-1 shrink-0">
                    {(user.role === 'PRE' || user.role === 'LQ') && (
                      <NotificationCenter />
                    )}
                    <button
                      type="button"
                      onClick={() => setIsSettingsOpen(true)}
                      className="p-1.5 text-slate-400 hover:text-slate-700 hover:bg-slate-200/60 rounded-lg transition cursor-pointer"
                      title="User Settings"
                    >
                      <Settings className="w-3.5 h-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={handleLogout}
                      className="p-1.5 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-lg transition cursor-pointer"
                      title="Logout"
                    >
                      <LogOut className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        ) : (
          /* ─── COLLAPSED ICON RAIL VIEW (Matching Image 1 Left Rail) ─── */
          <div className="flex flex-col h-full w-full items-center justify-between">
            {/* Top Logo & Expand Button */}
            <div className="flex flex-col items-center gap-3 shrink-0 pt-1">
              <button
                type="button"
                onClick={toggleSidebar}
                className="group relative p-2 hover:bg-slate-100 rounded-2xl transition cursor-pointer"
                title="Expand sidebar"
              >
                <CubeLogo className="w-7 h-7" />
                {/* Black Tooltip matching Image 1 */}
                <div className="absolute left-full ml-3 px-2.5 py-1 bg-[#18181b] text-white text-[11px] font-semibold rounded-md shadow-xl pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-150 z-50 whitespace-nowrap flex items-center">
                  Expand MarketIntel DB
                  <div className="absolute -left-1 top-1/2 -translate-y-1/2 w-2 h-2 bg-[#18181b] rotate-45" />
                </div>
              </button>

              <button
                type="button"
                onClick={toggleSidebar}
                className="group relative p-1.5 text-slate-400 hover:text-slate-900 hover:bg-slate-100 rounded-xl transition cursor-pointer"
                title="Expand sidebar"
              >
                <PanelLeftOpen className="w-4 h-4" />
                <div className="absolute left-full ml-3 px-2.5 py-1 bg-[#18181b] text-white text-[11px] font-semibold rounded-md shadow-xl pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-150 z-50 whitespace-nowrap flex items-center">
                  Expand sidebar
                  <div className="absolute -left-1 top-1/2 -translate-y-1/2 w-2 h-2 bg-[#18181b] rotate-45" />
                </div>
              </button>
            </div>

            {/* Centered Vertical Icon Rail */}
            <nav className="flex-1 overflow-y-auto my-2 flex flex-col items-center space-y-1.5 py-1 w-full custom-scrollbar">
              {primaryNavItems.map((item) => {
                const Icon = item.icon;
                const isActive = location.pathname.startsWith(item.path);

                return (
                  <div key={item.path} className="group relative flex items-center justify-center">
                    <Link
                      to={item.path}
                      className={`p-2.5 rounded-xl transition-all flex items-center justify-center ${
                        isActive
                          ? 'bg-white border border-slate-200/90 shadow-[0_2px_8px_rgba(0,0,0,0.06)] text-slate-900'
                          : 'text-slate-500 hover:text-slate-900 hover:bg-slate-100/80'
                      }`}
                    >
                      <Icon className="w-4 h-4 shrink-0" />
                      {item.badge && (
                        <span className="absolute top-1 right-1 w-2 h-2 bg-rose-500 rounded-full" />
                      )}
                    </Link>

                    {/* Sleek Black Tooltip matching Tasks tooltip in Image 1 */}
                    <div className="absolute left-full ml-3 px-2.5 py-1 bg-[#18181b] text-white text-[11px] font-semibold rounded-md shadow-xl pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-150 z-50 whitespace-nowrap flex items-center">
                      {item.label}
                      <div className="absolute -left-1 top-1/2 -translate-y-1/2 w-2 h-2 bg-[#18181b] rotate-45" />
                    </div>
                  </div>
                );
              })}

              {/* Divider matching Image 1 */}
              <div className="w-8 border-t border-slate-200/80 my-1" />

              {/* Bottom Folder icons for File and Apps in rail matching Image 1 */}
              <div className="group relative flex items-center justify-center">
                <Link
                  to="/prospects"
                  className="p-2.5 rounded-xl text-slate-500 hover:text-slate-900 hover:bg-slate-100/80 transition"
                >
                  <Folder className="w-4 h-4 shrink-0" />
                </Link>
                <div className="absolute left-full ml-3 px-2.5 py-1 bg-[#18181b] text-white text-[11px] font-semibold rounded-md shadow-xl pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-150 z-50 whitespace-nowrap flex items-center">
                  Files (Store, Company, Employee)
                  <div className="absolute -left-1 top-1/2 -translate-y-1/2 w-2 h-2 bg-[#18181b] rotate-45" />
                </div>
              </div>

              <div className="group relative flex items-center justify-center">
                <Link
                  to="/lq-pipeline"
                  className="p-2.5 rounded-xl text-slate-500 hover:text-slate-900 hover:bg-slate-100/80 transition"
                >
                  <Layers className="w-4 h-4 shrink-0" />
                </Link>
                <div className="absolute left-full ml-3 px-2.5 py-1 bg-[#18181b] text-white text-[11px] font-semibold rounded-md shadow-xl pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-150 z-50 whitespace-nowrap flex items-center">
                  Apps
                  <div className="absolute -left-1 top-1/2 -translate-y-1/2 w-2 h-2 bg-[#18181b] rotate-45" />
                </div>
              </div>
            </nav>

            {/* Bottom Profile in rail */}
            {user && (
              <div className="flex flex-col items-center gap-2 pt-2 border-t border-slate-100 shrink-0">
                <div className="group relative flex items-center justify-center">
                  <div className="w-8 h-8 rounded-full bg-slate-900 text-white font-bold text-xs flex items-center justify-center cursor-pointer shadow-xs">
                    {user.first_name?.[0] || user.username?.[0] || 'U'}
                  </div>
                  <div className="absolute left-full ml-3 px-2.5 py-1 bg-[#18181b] text-white text-[11px] font-semibold rounded-md shadow-xl pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-150 z-50 whitespace-nowrap flex items-center">
                    {user.first_name ? `${user.first_name} ${user.last_name || ''}` : user.username} ({user.role})
                    <div className="absolute -left-1 top-1/2 -translate-y-1/2 w-2 h-2 bg-[#18181b] rotate-45" />
                  </div>
                </div>

                <div className="group relative flex items-center justify-center">
                  <button
                    type="button"
                    onClick={handleLogout}
                    className="p-2 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-xl transition cursor-pointer"
                    title="Logout"
                  >
                    <LogOut className="w-4 h-4" />
                  </button>
                  <div className="absolute left-full ml-3 px-2.5 py-1 bg-[#18181b] text-white text-[11px] font-semibold rounded-md shadow-xl pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-150 z-50 whitespace-nowrap flex items-center">
                    Logout
                    <div className="absolute -left-1 top-1/2 -translate-y-1/2 w-2 h-2 bg-[#18181b] rotate-45" />
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </aside>

      {/* Main Application Area */}
      <main className="flex-1 min-w-0 h-screen overflow-y-auto bg-[#f4f5f7] transition-all duration-300">
        <div className={['/dashboard', '/calendar', '/manager-dashboard'].includes(location.pathname) || location.pathname.startsWith('/inbox') ? 'h-full w-full' : 'w-full px-4 sm:px-8 lg:px-12 py-6 h-full'}>
          <Outlet context={{ isSidebarCollapsed, setIsSidebarCollapsed, toggleSidebar }} />
        </div>
      </main>

      {/* Settings Modal */}
      {isSettingsOpen && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4 z-[100]">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden border border-slate-200">
            <div className="flex items-center justify-between p-4 border-b border-slate-100">
              <h3 className="font-bold text-slate-800">User Settings</h3>
              <button onClick={() => setIsSettingsOpen(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-500 mb-1.5">Time Zone</label>
                <SearchableSelect 
                  value={selectedTimezone} 
                  onChange={(val) => setSelectedTimezone(val)}
                  options={[
                    { value: 'UTC', label: 'UTC' },
                    { value: 'America/New_York', label: 'Eastern Time (US & Canada)' },
                    { value: 'America/Chicago', label: 'Central Time (US & Canada)' },
                    { value: 'America/Denver', label: 'Mountain Time (US & Canada)' },
                    { value: 'America/Los_Angeles', label: 'Pacific Time (US & Canada)' },
                    { value: 'Europe/London', label: 'London' },
                    { value: 'Europe/Paris', label: 'Paris' },
                    { value: 'Asia/Dubai', label: 'Dubai' },
                    { value: 'Asia/Kolkata', label: 'India (IST)' },
                    { value: 'Asia/Singapore', label: 'Singapore' },
                    { value: 'Australia/Sydney', label: 'Sydney' }
                  ]}
                />
                <p className="text-[10px] text-slate-400 mt-1">Calendar and notifications will be displayed in this time zone.</p>
              </div>
            </div>
            <div className="p-4 bg-slate-50 border-t border-slate-100 flex justify-end gap-2">
              <button onClick={() => setIsSettingsOpen(false)} className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-200 rounded-lg transition">Cancel</button>
              <button onClick={handleSaveSettings} className="px-4 py-2 text-xs font-bold bg-slate-900 text-white hover:bg-slate-800 rounded-lg transition shadow-xs">Save Changes</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Layout;
