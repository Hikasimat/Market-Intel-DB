import React, { useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Mail, Calendar as CalendarIcon, Loader2 } from 'lucide-react';
import { toast } from 'react-toastify';
import api from '../services/api';

const GmailCallbackPage = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const processedRef = useRef(false);

  useEffect(() => {
    if (processedRef.current) return;
    processedRef.current = true;

    const error = searchParams.get('error');
    const code = searchParams.get('code');
    const state = searchParams.get('state');

    const calendarReturnUrl = localStorage.getItem('calendar_oauth_return_url');

    if (error) {
      if (calendarReturnUrl) {
        toast.error(`Google Calendar authorization was cancelled or denied: ${error}`);
        localStorage.removeItem('calendar_oauth_return_url');
        navigate(calendarReturnUrl, { replace: true });
      } else {
        toast.error(`Gmail authorization was cancelled or denied: ${error}`);
        navigate('/inbox', { replace: true });
      }
      return;
    }

    if (!code || !state) {
      if (calendarReturnUrl) {
        toast.error('Missing authorization code or state from Google Calendar.');
        localStorage.removeItem('calendar_oauth_return_url');
        navigate(calendarReturnUrl, { replace: true });
      } else {
        toast.error('Missing authorization code or state from Google.');
        navigate('/inbox', { replace: true });
      }
      return;
    }

    const exchangeCode = async () => {
      if (calendarReturnUrl) {
        try {
          const response = await api.post('/auth/google/calendar/callback/', { code, state });
          const email = response.data?.email;
          toast.success(
            email
              ? `Successfully connected Google Calendar (${email})!`
              : 'Successfully connected Google Calendar!'
          );
          localStorage.removeItem('calendar_oauth_return_url');
          const sep = calendarReturnUrl.includes('?') ? '&' : '?';
          navigate(`${calendarReturnUrl}${sep}calendar_connected=1`, { replace: true });
        } catch (err) {
          const errMsg =
            err.response?.data?.detail ||
            err.response?.data?.error ||
            'Failed to finalize Google Calendar connection. Please try again.';
          toast.error(errMsg);
          localStorage.removeItem('calendar_oauth_return_url');
          navigate(calendarReturnUrl, { replace: true });
        }
        return;
      }

      try {
        const response = await api.post('/auth/google/gmail/callback/', { code, state });
        const email = response.data?.email;
        toast.success(
          email
            ? `Successfully connected Gmail mailbox (${email})!`
            : 'Successfully connected Gmail mailbox!'
        );
        navigate('/inbox?gmail_connected=1', { replace: true });
      } catch (err) {
        const errMsg =
          err.response?.data?.detail ||
          err.response?.data?.error ||
          'Failed to finalize Gmail connection. Please try again.';
        toast.error(errMsg);
        navigate('/inbox', { replace: true });
      }
    };

    exchangeCode();
  }, [searchParams, navigate]);

  const isCal = Boolean(localStorage.getItem('calendar_oauth_return_url'));

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-sky-50 to-indigo-50 flex items-center justify-center p-4">
      <div className="bg-white border border-slate-200/80 rounded-3xl shadow-xl max-w-md w-full p-8 text-center space-y-6">
        <div className="w-16 h-16 mx-auto rounded-2xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-600 flex items-center justify-center">
          {isCal ? <CalendarIcon className="w-8 h-8" /> : <Mail className="w-8 h-8" />}
        </div>

        <div className="space-y-2">
          <h2 className="text-xl font-black text-slate-900 tracking-tight">
            {isCal ? 'Connecting Google Calendar' : 'Connecting Google Mail'}
          </h2>
          <p className="text-sm text-slate-500 font-medium">
            {isCal
              ? 'Exchanging authorization tokens to enable Google Meet & Calendar scheduling...'
              : 'Exchanging authorization tokens and preparing your inbox for tracked outreach...'}
          </p>
        </div>

        <div className="flex items-center justify-center gap-3 text-indigo-600 font-bold text-sm bg-indigo-50 py-3 px-4 rounded-xl border border-indigo-100">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span>Securing OAuth Credentials...</span>
        </div>
      </div>
    </div>
  );
};

export default GmailCallbackPage;

