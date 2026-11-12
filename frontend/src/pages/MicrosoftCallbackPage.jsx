import React, { useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Calendar as CalendarIcon, Loader2 } from 'lucide-react';
import { toast } from 'react-toastify';
import api from '../services/api';

const MicrosoftCallbackPage = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const processedRef = useRef(false);

  useEffect(() => {
    if (processedRef.current) return;
    processedRef.current = true;

    const error = searchParams.get('error');
    const errorDescription = searchParams.get('error_description');
    const code = searchParams.get('code');
    const state = searchParams.get('state');

    const returnUrl = localStorage.getItem('microsoft_oauth_return_url') || '/prospects?tab=outreach';

    if (error) {
      toast.error(`Microsoft authorization was cancelled or denied: ${errorDescription || error}`);
      localStorage.removeItem('microsoft_oauth_return_url');
      navigate(returnUrl, { replace: true });
      return;
    }

    if (!code || !state) {
      toast.error('Missing authorization code or state from Microsoft.');
      localStorage.removeItem('microsoft_oauth_return_url');
      navigate(returnUrl, { replace: true });
      return;
    }

    const exchangeCode = async () => {
      try {
        const response = await api.post('/auth/microsoft/callback/', { code, state });
        const email = response.data?.email;
        toast.success(
          email
            ? `Successfully connected Microsoft 365 (${email})!`
            : 'Successfully connected Microsoft 365!'
        );
        localStorage.removeItem('microsoft_oauth_return_url');
        const sep = returnUrl.includes('?') ? '&' : '?';
        navigate(`${returnUrl}${sep}microsoft_connected=1`, { replace: true });
      } catch (err) {
        const errMsg =
          err.response?.data?.detail ||
          err.response?.data?.error ||
          'Failed to finalize Microsoft connection. Please try again.';
        toast.error(errMsg);
        localStorage.removeItem('microsoft_oauth_return_url');
        navigate(returnUrl, { replace: true });
      }
    };

    exchangeCode();
  }, [searchParams, navigate]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-teal-50 to-indigo-50 flex items-center justify-center p-4">
      <div className="bg-white border border-slate-200/80 rounded-3xl shadow-xl max-w-md w-full p-8 text-center space-y-6">
        <div className="w-16 h-16 mx-auto rounded-2xl bg-teal-500/10 border border-teal-500/20 text-teal-600 flex items-center justify-center">
          <CalendarIcon className="w-8 h-8" />
        </div>

        <div className="space-y-2">
          <h2 className="text-xl font-black text-slate-900 tracking-tight">
            Connecting Microsoft 365
          </h2>
          <p className="text-sm text-slate-500 font-medium">
            Exchanging authorization tokens to enable Teams meetings and Outlook Calendar sync...
          </p>
        </div>

        <div className="flex items-center justify-center gap-3 text-teal-600 font-bold text-sm bg-teal-50 py-3 px-4 rounded-xl border border-teal-100">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span>Securing Microsoft Permissions...</span>
        </div>
      </div>
    </div>
  );
};

export default MicrosoftCallbackPage;

