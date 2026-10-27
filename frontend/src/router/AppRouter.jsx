import React, { useEffect, Suspense, lazy } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { useSelector, useDispatch } from 'react-redux';
import { loginSuccess, logout } from '../features/auth/authSlice';
import api from '../services/api';

const LoginPage = lazy(() => import('../pages/LoginPage'));
const PreDashboardPage = lazy(() => import('../pages/PreDashboardPage'));
const ProspectsPage = lazy(() => import('../pages/ProspectsPage'));
const MarketEventsPage = lazy(() => import('../pages/MarketEventsPage'));
const MarketEventDetailPage = lazy(() => import('../pages/MarketEventDetailPage'));
const InboxPage = lazy(() => import('../pages/InboxPage'));
const ProspectDetailPage = lazy(() => import('../pages/ProspectDetailPage'));
const GovernmentEntitiesPage = lazy(() => import('../pages/GovernmentEntitiesPage'));
const ImportPreviewPage = lazy(() => import('../pages/ImportPreviewPage'));
const LqPipelinePage = lazy(() => import('../pages/LqPipelinePage'));
const LqPipelineDetailPage = lazy(() => import('../pages/LqPipelineDetailPage'));
const KeyPeoplePage = lazy(() => import('../pages/KeyPeoplePage'));
const KeyPersonDetailPage = lazy(() => import('../pages/KeyPersonDetailPage'));
const UserManagementPage = lazy(() => import('../pages/UserManagementPage'));
const PreTasksPage = lazy(() => import('../pages/PreTasksPage'));
const OutreachActivityDetailPage = lazy(() => import('../pages/OutreachActivityDetailPage'));
const LqCalendarPage = lazy(() => import('../pages/LqCalendarPage'));
const ManagerDashboardPage = lazy(() => import('../pages/ManagerDashboardPage'));
const ManagerAuditPage = lazy(() => import('../pages/ManagerAuditPage'));
const WhatsappPage = lazy(() => import('../pages/WhatsappPage'));
const SettingsPage = lazy(() => import('../pages/SettingsPage'));
const GmailCallbackPage = lazy(() => import('../pages/GmailCallbackPage'));
const CalendarCallbackPage = lazy(() => import('../pages/CalendarCallbackPage'));

const DigitalMarketingDashboardPage = lazy(() => import('../pages/digitalMarketing/DigitalMarketingDashboardPage'));
const InstagramPage = lazy(() => import('../pages/digitalMarketing/InstagramPage'));
const FacebookPage = lazy(() => import('../pages/digitalMarketing/FacebookPage'));
const TwitterPage = lazy(() => import('../pages/digitalMarketing/TwitterPage'));
const AdsInsightsPage = lazy(() => import('../pages/digitalMarketing/AdsInsightsPage'));
const SocialMessagesPage = lazy(() => import('../pages/digitalMarketing/SocialMessagesPage'));

const PageSpinner = () => (
  <div className="min-h-[50vh] flex items-center justify-center">
    <div className="w-8 h-8 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin"></div>
  </div>
);

import Layout from '../components/layout/Layout';

const RoleRoute = ({ children, allowedRoles, requireAdmin }) => {
  const { isAuthenticated, user } = useSelector((state) => state.auth);
  
  if (!isAuthenticated) return <Navigate to="/login" replace />;
  
  if (requireAdmin && !user?.is_superuser) {
    // Manager can access /users (read-only); superuser has full access
    if (user?.role === 'MANAGER') return children;
    return <Navigate to="/" replace />;
  }
  
  if (allowedRoles && user && !allowedRoles.includes(user.role) && !user.is_superuser) {
    // Redirect based on role
    if (user.role === 'LQ') return <Navigate to="/lq-pipeline" replace />;
    if (user.role === 'MANAGER') return <Navigate to="/manager-dashboard" replace />;
    if (user.role === 'DM') return <Navigate to="/digital-marketing" replace />;
    return <Navigate to="/dashboard" replace />;
  }
  
  return children;
};

const AppRouter = () => {
  const dispatch = useDispatch();
  const { isAuthenticated, user, accessToken, refreshToken } = useSelector((state) => state.auth);

  useEffect(() => {
    const fetchUser = async () => {
      if (isAuthenticated && !user) {
        try {
          const response = await api.get('/auth/me/');
          dispatch(loginSuccess({ access: accessToken, refresh: refreshToken, user: response.data }));
        } catch (error) {
          dispatch(logout());
        }
      }
    };
    fetchUser();
  }, [isAuthenticated, user, accessToken, refreshToken, dispatch]);

  // Show a loading screen while user is being fetched to prevent premature redirects
  if (isAuthenticated && !user) {
    return <div className="min-h-screen bg-slate-50 flex items-center justify-center">Loading session...</div>;
  }

  return (
    <Router>
      <Suspense fallback={<PageSpinner />}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/auth/google/callback" element={<LoginPage />} />
          <Route path="/auth/gmail/callback" element={<GmailCallbackPage />} />
          <Route path="/auth/calendar/callback" element={<CalendarCallbackPage />} />
          
          {/* ── Manager routes ────────────────────────────────── */}
          <Route path="/manager-dashboard" element={
            <RoleRoute allowedRoles={['MANAGER']}><Layout /></RoleRoute>
          }>
            <Route index element={<ManagerDashboardPage />} />
          </Route>

          {/* ── PRE / LQ / Manager / DM shared routes ─────────────── */}
          <Route path="/" element={
            <RoleRoute allowedRoles={['PRE', 'LQ', 'MANAGER', 'DM']}><Layout /></RoleRoute>
          }>
            {/* Default redirect by role */}
            <Route index element={
              user?.role === 'LQ'
                ? <Navigate to="/lq-pipeline" replace />
                : user?.role === 'MANAGER'
                ? <Navigate to="/manager-dashboard" replace />
                : user?.role === 'DM'
                ? <Navigate to="/digital-marketing" replace />
                : <Navigate to="/dashboard" replace />
            } />
            
            <Route path="dashboard" element={<RoleRoute allowedRoles={['PRE']}><PreDashboardPage /></RoleRoute>} />
            
            {/* Prospects — PRE full, MANAGER read-only, LQ can view detail of assigned prospects */}
            <Route path="prospects" element={<RoleRoute allowedRoles={['PRE', 'MANAGER']}><ProspectsPage /></RoleRoute>} />
            <Route path="prospects/import-preview" element={<RoleRoute allowedRoles={['PRE']}><ImportPreviewPage /></RoleRoute>} />
            <Route path="prospects/:id" element={<RoleRoute allowedRoles={['PRE', 'LQ', 'MANAGER']}><ProspectDetailPage /></RoleRoute>} />

            <Route path="government-entities" element={<RoleRoute allowedRoles={['PRE']}><GovernmentEntitiesPage /></RoleRoute>} />

            {/* Market Events — PRE full, LQ + MANAGER read-only */}
            <Route path="market-events" element={<RoleRoute allowedRoles={['PRE', 'LQ', 'MANAGER']}><MarketEventsPage /></RoleRoute>} />
            <Route path="market-events/:id" element={<RoleRoute allowedRoles={['PRE', 'LQ', 'MANAGER']}><MarketEventDetailPage /></RoleRoute>} />

            {/* PRE tasks — PRE full, MANAGER read-only */}
            <Route path="pre-tasks" element={<RoleRoute allowedRoles={['PRE', 'MANAGER']}><PreTasksPage /></RoleRoute>} />

            {/* Key People — PRE + LQ full, MANAGER read-only */}
            <Route path="key-people" element={<RoleRoute allowedRoles={['PRE', 'LQ', 'MANAGER']}><KeyPeoplePage /></RoleRoute>} />
            <Route path="key-people/:id" element={<RoleRoute allowedRoles={['PRE', 'LQ', 'MANAGER']}><KeyPersonDetailPage /></RoleRoute>} />

            {/* User management — Superuser full, MANAGER create+view */}
            <Route path="users" element={<RoleRoute requireAdmin={true}><UserManagementPage /></RoleRoute>} />

            {/* Manager Audit */}
            <Route path="manager-audit" element={<RoleRoute allowedRoles={['MANAGER']}><ManagerAuditPage /></RoleRoute>} />

            {/* LQ Pipeline — LQ full, MANAGER read-only */}
            <Route path="lq-pipeline" element={<RoleRoute allowedRoles={['LQ', 'MANAGER']}><LqPipelinePage filter="all" /></RoleRoute>} />
            <Route path="lq-pipeline/pending" element={<RoleRoute allowedRoles={['LQ', 'MANAGER']}><LqPipelinePage filter="pending" /></RoleRoute>} />
            <Route path="lq-pipeline/verified" element={<RoleRoute allowedRoles={['LQ', 'MANAGER']}><LqPipelinePage filter="verified" /></RoleRoute>} />
            <Route path="lq-pipeline/issued" element={<RoleRoute allowedRoles={['LQ', 'MANAGER']}><LqPipelinePage filter="issued" /></RoleRoute>} />
            <Route path="lq-pipeline/:id" element={<RoleRoute allowedRoles={['LQ', 'MANAGER']}><LqPipelineDetailPage /></RoleRoute>} />

            <Route path="outreach-activity/:prospectId" element={<RoleRoute allowedRoles={['LQ', 'MANAGER']}><OutreachActivityDetailPage /></RoleRoute>} />
            <Route path="inbox" element={<RoleRoute allowedRoles={['LQ', 'MANAGER']}><InboxPage /></RoleRoute>} />
            <Route path="calendar" element={<RoleRoute allowedRoles={['LQ', 'MANAGER']}><LqCalendarPage /></RoleRoute>} />
            <Route path="whatsapp" element={<RoleRoute allowedRoles={['LQ']}><WhatsappPage /></RoleRoute>} />
            <Route path="settings" element={<RoleRoute allowedRoles={['LQ']}><SettingsPage /></RoleRoute>} />

            {/* ── Digital Marketing Workspace ────────────────────────────── */}
            <Route path="digital-marketing" element={<RoleRoute allowedRoles={['DM']}><DigitalMarketingDashboardPage /></RoleRoute>} />
            <Route path="digital-marketing/messages" element={<RoleRoute allowedRoles={['DM']}><SocialMessagesPage /></RoleRoute>} />
            <Route path="digital-marketing/instagram" element={<RoleRoute allowedRoles={['DM']}><InstagramPage /></RoleRoute>} />
            <Route path="digital-marketing/facebook" element={<RoleRoute allowedRoles={['DM']}><FacebookPage /></RoleRoute>} />
            <Route path="digital-marketing/twitter" element={<RoleRoute allowedRoles={['DM']}><TwitterPage /></RoleRoute>} />
            <Route path="digital-marketing/ads-insights" element={<RoleRoute allowedRoles={['DM']}><AdsInsightsPage /></RoleRoute>} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </Router>
  );
};

export default AppRouter;
