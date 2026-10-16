import React, { useState, useEffect, useRef } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import { useNavigate, useLocation } from 'react-router-dom';
import { loginStart, loginSuccess, loginFailure } from '../features/auth/authSlice';
import api from '../services/api';
import { LogIn, Eye, EyeOff, AlertCircle } from 'lucide-react';

const GoogleIcon = () => (
  <svg className="w-5 h-5 mr-3" viewBox="0 0 24 24" aria-hidden="true">
    <path
      fill="#4285F4"
      d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
    />
    <path
      fill="#34A853"
      d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
    />
    <path
      fill="#FBBC05"
      d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
    />
    <path
      fill="#EA4335"
      d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
    />
  </svg>
);

const LoginPage = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);
  const [localError, setLocalError] = useState(null);

  const dispatch = useDispatch();
  const navigate = useNavigate();
  const location = useLocation();
  const { loading, error } = useSelector((state) => state.auth);
  const oauthProcessedRef = useRef(false);

  const navigateByRole = (role) => {
    if (role === 'LQ') navigate('/lq-pipeline');
    else if (role === 'MANAGER') navigate('/manager-dashboard');
    else navigate('/prospects');
  };

  // Handle incoming OAuth redirects (from Google callback)
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const oauthError = params.get('oauth_error') || params.get('error');
    const oauthSuccess = params.get('oauth_success');
    const code = params.get('code');
    const state = params.get('state');

    // Clean URL query params to prevent duplicate triggering
    const cleanUrl = () => {
      window.history.replaceState({}, document.title, window.location.pathname);
    };

    if (oauthError) {
      cleanUrl();
      setLocalError(decodeURIComponent(oauthError));
      return;
    }

    if (oauthSuccess) {
      cleanUrl();
      // Backend callback established session via HttpOnly cookies; fetch user
      const fetchSessionUser = async () => {
        dispatch(loginStart());
        try {
          const meRes = await api.get('/auth/me/');
          dispatch(loginSuccess({ access: null, user: meRes.data }));
          navigateByRole(meRes.data.role);
        } catch (err) {
          dispatch(loginFailure(err.response?.data?.detail || 'Session restoration failed.'));
        }
      };
      fetchSessionUser();
      return;
    }

    if (code && state && !oauthProcessedRef.current) {
      oauthProcessedRef.current = true;
      cleanUrl();
      const processGoogleCallback = async () => {
        setGoogleLoading(true);
        dispatch(loginStart());
        try {
          const response = await api.post('/auth/google/login/', { code, state });
          const tokens = response.data;
          if (tokens.access) {
            api.defaults.headers.common['Authorization'] = `Bearer ${tokens.access}`;
          }
          const meResponse = await api.get('/auth/me/');
          dispatch(loginSuccess({
            access: tokens.access,
            user: meResponse.data,
          }));
          navigateByRole(meResponse.data.role);
        } catch (err) {
          const errMsg = err.response?.data?.detail || err.response?.data?.error || 'Google authentication failed. Please try again.';
          dispatch(loginFailure(errMsg));
          setLocalError(errMsg);
        } finally {
          setGoogleLoading(false);
        }
      };
      processGoogleCallback();
    }
  }, [location.search, dispatch, navigate]);

  // Handle "Continue with Google" click
  const handleGoogleSignIn = async () => {
    setLocalError(null);
    setGoogleLoading(true);
    try {
      const response = await api.get('/auth/google/url/');
      if (response.data?.url) {
        window.location.href = response.data.url;
      } else {
        throw new Error('No authorization URL received.');
      }
    } catch (err) {
      setGoogleLoading(false);
      const msg = err.response?.data?.error || err.response?.data?.detail || 'Failed to initiate Google sign-in. Please ensure Google OAuth is configured.';
      setLocalError(msg);
    }
  };

  // Handle email/password submission
  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalError(null);
    dispatch(loginStart());
    try {
      const response = await api.post('/auth/login/', {
        email: email.trim(),
        password,
      });
      const tokens = response.data;
      if (tokens.access) {
        api.defaults.headers.common['Authorization'] = `Bearer ${tokens.access}`;
      }
      const meResponse = await api.get('/auth/me/');
      dispatch(loginSuccess({
        access: tokens.access,
        user: meResponse.data,
      }));
      navigateByRole(meResponse.data.role);
    } catch (err) {
      const msg = err.response?.data?.detail || err.response?.data?.error || 'Login failed. Please check your credentials.';
      dispatch(loginFailure(msg));
      setLocalError(msg);
    }
  };

  const activeError = localError || error;
  const isBusy = loading || googleLoading;

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-6 bg-white p-8 rounded-2xl shadow-sm border border-slate-200">
        <div>
          <h2 className="text-center text-3xl font-extrabold text-slate-900 tracking-tight">
            MarketIntel DB
          </h2>
          <p className="mt-2 text-center text-sm text-slate-600">
            Sign in to access your workspace
          </p>
        </div>

        {activeError && (
          <div
            role="alert"
            className="flex items-start gap-2 p-3.5 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm"
          >
            <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5 text-red-500" />
            <span className="leading-snug">{activeError}</span>
          </div>
        )}

        {/* Option 1: Continue with Google */}
        <div>
          <button
            type="button"
            id="google-signin-btn"
            onClick={handleGoogleSignIn}
            disabled={isBusy}
            className="w-full flex items-center justify-center py-2.5 px-4 border border-slate-300 rounded-xl text-sm font-semibold text-slate-700 bg-white hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 shadow-sm transition disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <GoogleIcon />
            {googleLoading ? 'Connecting to Google...' : 'Continue with Google'}
          </button>
        </div>

        {/* Divider */}
        <div className="relative my-6">
          <div className="absolute inset-0 flex items-center">
            <div className="w-full border-t border-slate-200" />
          </div>
          <div className="relative flex justify-center text-xs uppercase">
            <span className="bg-white px-3 text-slate-400 font-medium tracking-wider">
              Or sign in with email
            </span>
          </div>
        </div>

        {/* Option 2: Email & Password Authentication */}
        <form className="space-y-4" onSubmit={handleSubmit}>
          <div>
            <label htmlFor="email" className="block text-xs font-semibold uppercase text-slate-600 mb-1">
              Registered Email or Username
            </label>
            <input
              id="email"
              name="email"
              type="text"
              autoComplete="username"
              required
              disabled={isBusy}
              className="appearance-none block w-full px-3.5 py-2.5 border border-slate-300 rounded-xl placeholder-slate-400 text-slate-900 text-sm focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-100"
              placeholder="name@company.com or username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>


          <div>
            <label htmlFor="password" className="block text-xs font-semibold uppercase text-slate-600 mb-1">
              Password
            </label>
            <div className="relative">
              <input
                id="password"
                name="password"
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                required
                disabled={isBusy}
                className="appearance-none block w-full px-3.5 py-2.5 pr-10 border border-slate-300 rounded-xl placeholder-slate-400 text-slate-900 text-sm focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-100"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                id="toggle-password-visibility"
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                onClick={() => setShowPassword(!showPassword)}
                className="absolute inset-y-0 right-0 pr-3 flex items-center text-slate-400 hover:text-slate-600 focus:outline-none"
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <div className="pt-2">
            <button
              type="submit"
              id="email-signin-btn"
              disabled={isBusy}
              className="w-full flex items-center justify-center py-2.5 px-4 border border-transparent text-sm font-semibold rounded-xl text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 shadow-sm transition disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <LogIn className="w-4 h-4 mr-2" />
              {loading && !googleLoading ? 'Signing in...' : 'Sign in'}
            </button>
          </div>
        </form>

        <div className="pt-2 text-center text-xs text-slate-400">
          Account access is managed by system administrators.
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
