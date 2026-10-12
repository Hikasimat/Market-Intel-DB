import React, { useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { useSelector, useDispatch } from 'react-redux';
import { loginSuccess, logout } from '../features/auth/authSlice';
import api from '../services/api';
import LoginPage from '../pages/LoginPage';
import PreDashboardPage from '../pages/PreDashboardPage';
import ProspectsPage from '../pages/ProspectsPage';
import MarketEventsPage from '../pages/MarketEventsPage';
import MarketEventDetailPage from '../pages/MarketEventDetailPage';
import InboxPage from '../pages/InboxPage';
import ProspectDetailPage from '../pages/ProspectDetailPage';
import GovernmentEntitiesPage from '../pages/GovernmentEntitiesPage';
import ImportPreviewPage from '../pages/ImportPreviewPage';
import LqPipelinePage from '../pages/LqPipelinePage';
import LqPipelineDetailPage from '../pages/LqPipelineDetailPage';
import KeyPeoplePage from '../pages/KeyPeoplePage';
import KeyPersonDetailPage from '../pages/KeyPersonDetailPage';
import UserManagementPage from '../pages/UserManagementPage';
import PreTasksPage from '../pages/PreTasksPage';
import OutreachActivityDetailPage from '../pages/OutreachActivityDetailPage';
import LqCalendarPage from '../pages/LqCalendarPage';
import ManagerDashboardPage from '../pages/ManagerDashboardPage';
import ManagerAuditPage from '../pages/ManagerAuditPage';
import WhatsappPage from '../pages/WhatsappPage';
import SettingsPage from '../pages/SettingsPage';

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
    return <Navigate to="/prospects" replace />;
  }
  
  return children;
};

const AppRouter = () => {
  const dispatch = useDispatch();
  const { isAuthenticated, user, accessToken, refreshToken } = useSelector((state) => state.auth);

  useEffect(() => {
    const fetchUser = async () => {
      if (isAuthenticated && !user && accessToken) {
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
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        
        {/* ── Manager routes ────────────────────────────────── */}
        <Route path="/manager-dashboard" element={
          <RoleRoute allowedRoles={['MANAGER']}><Layout /></RoleRoute>
        }>
          <Route index element={<ManagerDashboardPage />} />
        </Route>

        {/* ── PRE / LQ / Manager shared routes ─────────────── */}
        <Route path="/" element={
          <RoleRoute allowedRoles={['PRE', 'LQ', 'MANAGER']}><Layout /></RoleRoute>
        }>
          {/* Default redirect by role */}
          <Route index element={
            user?.role === 'LQ'
              ? <Navigate to="/lq-pipeline" replace />
              : user?.role === 'MANAGER'
              ? <Navigate to="/manager-dashboard" replace />
              : <Navigate to="/dashboard" replace />
          } />
          
          <Route path="dashboard" element={<RoleRoute allowedRoles={['PRE']}><PreDashboardPage /></RoleRoute>} />
          
          {/* Prospects — PRE full, MANAGER read-only */}
          <Route path="prospects" element={<RoleRoute allowedRoles={['PRE', 'MANAGER']}><ProspectsPage /></RoleRoute>} />
          <Route path="prospects/import-preview" element={<RoleRoute allowedRoles={['PRE']}><ImportPreviewPage /></RoleRoute>} />
          <Route path="prospects/:id" element={<RoleRoute allowedRoles={['PRE', 'MANAGER']}><ProspectDetailPage /></RoleRoute>} />

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

          <Route path="outreach-activity/:prospectId" element={<RoleRoute allowedRoles={['LQ']}><OutreachActivityDetailPage /></RoleRoute>} />
          <Route path="inbox" element={<RoleRoute allowedRoles={['LQ']}><InboxPage /></RoleRoute>} />
          <Route path="calendar" element={<RoleRoute allowedRoles={['LQ']}><LqCalendarPage /></RoleRoute>} />
          <Route path="whatsapp" element={<RoleRoute allowedRoles={['LQ']}><WhatsappPage /></RoleRoute>} />
          <Route path="settings" element={<RoleRoute allowedRoles={['LQ']}><SettingsPage /></RoleRoute>} />
        </Route>
      </Routes>
    </Router>
  );
};

export default AppRouter;
