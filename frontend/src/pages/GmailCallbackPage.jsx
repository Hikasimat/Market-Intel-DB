import React, { useEffect, useRef } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Mail, Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
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

    if (error) {
      toast.error(`Gmail authorization was cancelled or denied: ${error}`);
      navigate('/inbox', { replace: true });
      return;
    }

    if (!code || !state) {
      toast.error('Missing authorization code or state from Google.');
      navigate('/inbox', { replace: true });
      return;
    }

    const exchangeCode = async () => {
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

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-sky-50 to-indigo-50 flex items-center justify-center p-4">
      <div className="bg-white border border-slate-200/80 rounded-3xl shadow-xl max-w-md w-full p-8 text-center space-y-6">
        <div className="w-16 h-16 mx-auto rounded-2xl bg-sky-500/10 border border-sky-500/20 text-sky-600 flex items-center justify-center">
          <Mail className="w-8 h-8" />
        </div>

        <div className="space-y-2">
          <h2 className="text-xl font-black text-slate-900 tracking-tight">
            Connecting Google Mail
          </h2>
          <p className="text-sm text-slate-500 font-medium">
            Exchanging authorization tokens and preparing your inbox for tracked outreach...
          </p>
        </div>

        <div className="flex items-center justify-center gap-3 text-sky-600 font-bold text-sm bg-sky-50 py-3 px-4 rounded-xl border border-sky-100">
          <Loader2 className="w-5 h-5 animate-spin" />
          <span>Securing OAuth Credentials...</span>
        </div>
      </div>
    </div>
  );
};

export default GmailCallbackPage;
