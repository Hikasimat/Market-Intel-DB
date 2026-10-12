import React, { useState, useEffect, useRef } from 'react';
import { Outlet, Link, useLocation, useNavigate } from 'react-router-dom';
import { useSelector, useDispatch } from 'react-redux';
import SearchableSelect from '../common/SearchableSelect';
import { LogOut, Users, Calendar, Activity, ClipboardList, UserCircle, Mail, LayoutDashboard, Shield, BarChart2, Eye, Settings, X, MessageCircle, Building2 } from 'lucide-react';
import { logout, loginSuccess } from '../../features/auth/authSlice';
import api from '../../services/api';
import { store } from '../../app/store';
import NotificationCenter from './NotificationCenter';

const Layout = () => {
  const { user, accessToken, refreshToken } = useSelector((state) => state.auth);
  const unreadCount = useSelector((state) => state.inbox.unreadCount);
  const dispatch = useDispatch();
  const location = useLocation();
  const navigate = useNavigate();
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [selectedTimezone, setSelectedTimezone] = useState(user?.timezone || 'UTC');

  const handleSaveSettings = async () => {
    try {
      await api.patch('/auth/me/', { timezone: selectedTimezone });
      const res = await api.get('/auth/me/');
      dispatch(loginSuccess({ access: accessToken, refresh: refreshToken, user: res.data }));
      setIsSettingsOpen(false);
    } catch(err) {
      alert('Failed to update timezone');
    }
  };

  const handleLogout = async () => {
    // Blacklist the refresh token on the server before clearing client state.
    // This ensures the token cannot be reused even if captured by a third party.
    const currentRefreshToken = store?.getState?.()?.auth?.refreshToken;
    if (currentRefreshToken) {
      try {
        await api.post('/auth/logout/', { refresh: currentRefreshToken });
      } catch (e) {
        // Proceed with client-side logout even if server call fails.
        console.warn('Server logout failed; proceeding with client logout.', e);
      }
    }
    dispatch(logout());
    navigate('/login');
  };

  // Idle Session Timeout (30 minutes)
  const idleTimeoutRef = useRef(null);
  const IDLE_TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes

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

    // Set initial timeout
    resetIdleTimeout();

    // Attach event listeners for user activity
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

  const navItems = [];

  if (user?.role === 'PRE') {
    navItems.push(
      { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
      { path: '/prospects', label: 'Prospects', icon: Users },
      { path: '/government-entities', label: 'Government Entities', icon: Building2 },
      { path: '/key-people', label: 'Key People', icon: UserCircle },
      { path: '/market-events', label: 'Market Events', icon: Calendar },
      { path: '/pre-tasks', label: 'Tasks', icon: ClipboardList }
    );
  }

  if (user?.is_superuser) {
    navItems.push(
      { path: '/users', label: 'User Management', icon: Users }
    );
  } else if (user?.role === 'LQ') {
    navItems.push(
      { 
        path: '/lq-pipeline', 
        label: 'Lead Qualifier Pipeline', 
        icon: Activity,
        subItems: [
          { path: '/lq-pipeline', label: 'All Prospects', exact: true },
          { path: '/lq-pipeline/pending', label: 'Verification Pending', exact: true },
          { path: '/lq-pipeline/verified', label: 'Outreached', exact: true },
          { path: '/lq-pipeline/issued', label: 'Issued Task to PRE', exact: true },
        ]
      },
      { path: '/calendar', label: 'Calendar', icon: Calendar },
      { path: '/key-people', label: 'Key People', icon: UserCircle },
      { path: '/market-events', label: 'Market Events', icon: Calendar },
      { path: '/inbox', label: 'Inbox', icon: Mail, badge: unreadCount > 0 ? unreadCount : null },
      { path: '/whatsapp', label: 'WhatsApp', icon: MessageCircle },
      { path: '/settings', label: 'Settings', icon: Settings }
    );
  } else if (user?.role === 'MANAGER') {
    navItems.push(
      { path: '/manager-dashboard', label: 'Manager Dashboard', icon: Shield },
      { path: '/manager-audit', label: 'Daily Audit', icon: ClipboardList },
      { path: '/prospects', label: 'Prospects', icon: Users },
      { path: '/lq-pipeline', label: 'LQ Pipeline', icon: Activity },
      { path: '/key-people', label: 'Key People', icon: UserCircle },
      { path: '/market-events', label: 'Market Events', icon: Calendar },
      { path: '/pre-tasks', label: 'Tasks', icon: ClipboardList },
      { path: '/users', label: 'User Management', icon: Users },
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 flex font-sans">
      {/* Sidebar */}
      <aside className="w-64 bg-blue-600 sticky top-0 h-screen flex flex-col shrink-0 z-50 text-white">
        <div className="h-20 flex items-center px-6 shrink-0">
          <span className="text-2xl font-black text-white tracking-tight">
            MarketIntel <span className="font-light text-blue-200">DB</span>
          </span>
        </div>
        
        <nav className="flex-1 overflow-y-auto py-4 pl-4 pr-0 space-y-2">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = location.pathname.startsWith(item.path);
            
            return (
              <div key={item.path} className="group space-y-1">
                <Link
                  to={item.path}
                  className={`flex items-center px-4 py-3.5 text-sm font-bold transition-all ${
                    isActive
                      ? 'bg-slate-50 text-blue-600 rounded-l-full'
                      : 'text-blue-100 hover:bg-blue-500 hover:text-white rounded-l-full'
                  }`}
                >
                  <div className="relative mr-4">
                    <Icon className={`w-5 h-5 ${isActive ? 'text-blue-600' : 'text-blue-200'}`} />
                    {item.badge && (
                      <span className="absolute -top-1.5 -right-1.5 min-w-[16px] h-4 bg-rose-500 text-white text-[10px] font-bold rounded-full flex items-center justify-center px-1 shadow-sm">
                        {item.badge > 999 ? '999+' : item.badge}
                      </span>
                    )}
                  </div>
                  {item.label}
                </Link>

                {item.subItems && (
                  <div className="hidden group-hover:block pl-12 pr-4 space-y-1 mt-1 mb-2">
                    {item.subItems.map(sub => {
                      const isSubActive = sub.exact 
                        ? location.pathname === sub.path 
                        : location.pathname.startsWith(sub.path);
                      return (
                        <Link
                          key={sub.path}
                          to={sub.path}
                          className={`block px-4 py-2.5 text-xs font-bold rounded-l-full transition-all ${
                            isSubActive
                              ? 'bg-blue-500 text-white'
                              : 'text-blue-200 hover:bg-blue-500 hover:text-white'
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
        </nav>

        {user && (
          <div className="p-4 bg-blue-700/30 shrink-0">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-1">
                {user.role === 'LQ' && (
                  <div className="mr-1">
                    <NotificationCenter />
                  </div>
                )}

                <button
                  onClick={handleLogout}
                  className="p-1.5 text-blue-200 hover:bg-blue-500 hover:text-white rounded-lg transition-colors"
                  title="Logout"
                >
                  <LogOut className="h-4 w-4" />
                </button>
              </div>
            </div>
            <div className="flex flex-col">
              <div className="text-sm font-medium text-white flex items-center gap-2">
                <span className="font-bold bg-blue-500 text-white px-1.5 py-0.5 rounded-md text-[10px] uppercase tracking-wider">
                  {user.role}
                </span>
                <span className="truncate font-bold">{user.first_name} {user.last_name}</span>
              </div>
              <div className="text-xs text-blue-200 mt-1 font-medium">
                {user.role === 'PRE'
                  ? 'Prospect Research Engineer'
                  : user.role === 'LQ'
                  ? 'Lead Qualifier'
                  : user.role === 'MANAGER'
                  ? 'Manager'
                  : user.is_superuser
                  ? 'Administrator'
                  : user.role}
              </div>
            </div>
          </div>
        )}
      </aside>

      {/* Main Content */}
      <main className="flex-1 min-w-0 h-screen overflow-y-auto bg-slate-50">
        <div className={['/dashboard', '/calendar', '/manager-dashboard'].includes(location.pathname) ? 'h-full' : 'w-full px-4 sm:px-8 lg:px-12 py-8 h-full'}>
          <Outlet />
        </div>
      </main>
      {/* Settings Modal */}
      {isSettingsOpen && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4 z-[100]">
          <div className="bg-white rounded-xl shadow-2xl w-full max-w-sm overflow-hidden">
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
              <button onClick={handleSaveSettings} className="px-4 py-2 text-xs font-bold bg-indigo-600 text-white hover:bg-indigo-700 rounded-lg transition shadow-sm">Save Changes</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Layout;
