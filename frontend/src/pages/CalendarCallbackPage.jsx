import React, { useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Calendar as CalendarIcon, Loader2 } from 'lucide-react';
import { toast } from 'react-toastify';
import api from '../services/api';

const CalendarCallbackPage = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const processedRef = useRef(false);

  useEffect(() => {
    if (processedRef.current) return;
    processedRef.current = true;

    const error = searchParams.get('error');
    const code = searchParams.get('code');
    const state = searchParams.get('state');

    const returnUrl = localStorage.getItem('calendar_oauth_return_url') || '/lq-pipeline';

    if (error) {
      toast.error(`Google Calendar authorization was cancelled or denied: ${error}`);
      localStorage.removeItem('calendar_oauth_return_url');
      navigate(returnUrl, { replace: true });
      return;
    }

    if (!code || !state) {
      toast.error('Missing authorization code or state from Google Calendar.');
      localStorage.removeItem('calendar_oauth_return_url');
      navigate(returnUrl, { replace: true });
      return;
    }

    const exchangeCode = async () => {
      try {
        const response = await api.post('/auth/google/calendar/callback/', { code, state });
        const email = response.data?.email;
        toast.success(
          email
            ? `Successfully connected Google Calendar (${email})!`
            : 'Successfully connected Google Calendar!'
        );
        localStorage.removeItem('calendar_oauth_return_url');
        const sep = returnUrl.includes('?') ? '&' : '?';
        navigate(`${returnUrl}${sep}calendar_connected=1`, { replace: true });
      } catch (err) {
        const errMsg =
          err.response?.data?.detail ||
          err.response?.data?.error ||
          'Failed to finalize Google Calendar connection. Please try again.';
        toast.error(errMsg);
        localStorage.removeItem('calendar_oauth_return_url');
        navigate(returnUrl, { replace: true });
      }
    };

    exchangeCode();
  }, [searchParams, navigate]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-indigo-50 to-purple-50 flex items-center justify-center p-4">
      <div className="bg-white border border-slate-200/80 rounded-3xl shadow-xl max-w-md w-full p-8 text-center space-y-6">
        <div className="w-16 h-16 mx-auto rounded-2xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-600 flex items-center justify-center">
          <CalendarIcon className="w-8 h-8" />
        </div>

        <div className="space-y-2">
          <h2 className="text-xl font-black text-slate-900 tracking-tight">
            Connecting Google Calendar
          </h2>
          <p className="text-sm text-slate-500 font-medium">
            Exchanging authorization tokens to enable Google Meet scheduling...
          </p>
        </div>

        <div className="flex items-center justify-center gap-3 text-indigo-600 font-bold text-sm bg-indigo-50 py-3 px-4 rounded-xl border border-indigo-100">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span>Securing Calendar Permissions...</span>
        </div>
      </div>
    </div>
  );
};

export default CalendarCallbackPage;
