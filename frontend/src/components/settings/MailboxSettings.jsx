import React, { useState, useEffect, useCallback } from 'react';
import { Mail, ShieldCheck, CheckCircle2, AlertCircle, RefreshCw, Trash2, Plus, ExternalLink } from 'lucide-react';
import { toast } from 'react-toastify';
import api from '../../services/api';

const MailboxSettings = () => {
  const [gmailStatus, setGmailStatus] = useState({ is_connected: false, email: '' });
  const [loadingGmail, setLoadingGmail] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [disconnecting, setDisconnecting] = useState(false);

  const [mailAccounts, setMailAccounts] = useState([]);
  const [loadingAccounts, setLoadingAccounts] = useState(false);

  const fetchGmailStatus = useCallback(async () => {
    setLoadingGmail(true);
    try {
      const res = await api.get('/auth/google/gmail/status/');
      setGmailStatus(res.data);
    } catch (err) {
      console.error('Failed to fetch Gmail status', err);
    } finally {
      setLoadingGmail(false);
    }
  }, []);

  const fetchMailAccounts = useCallback(async () => {
    setLoadingAccounts(true);
    try {
      const res = await api.get('/auth/mail-account/');
      setMailAccounts(res.data || []);
    } catch (err) {
      console.error('Failed to fetch mail accounts', err);
    } finally {
      setLoadingAccounts(false);
    }
  }, []);

  useEffect(() => {
    fetchGmailStatus();
    fetchMailAccounts();
  }, [fetchGmailStatus, fetchMailAccounts]);

  const handleConnectGmail = async () => {
    setConnecting(true);
    try {
      const res = await api.get('/auth/google/gmail/url/');
      if (res.data?.url) {
        window.location.href = res.data.url;
      } else {
        toast.error('Failed to get Gmail authorization link.');
      }
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to start Gmail connection.');
    } finally {
      setConnecting(false);
    }
  };

  const handleDisconnectGmail = async () => {
    if (!window.confirm('Disconnect your Gmail mailbox? You will no longer receive or send emails using this Google account.')) return;
    setDisconnecting(true);
    try {
      await api.post('/auth/google/gmail/disconnect/');
      toast.success('Gmail mailbox disconnected.');
      fetchGmailStatus();
      fetchMailAccounts();
    } catch (err) {
      toast.error('Failed to disconnect Gmail.');
    } finally {
      setDisconnecting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Google OAuth Mailbox Card */}
      <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-2xl bg-sky-50 border border-sky-100 flex items-center justify-center text-sky-600">
              <Mail className="w-6 h-6" />
            </div>
            <div>
              <h2 className="text-base font-extrabold text-slate-900 tracking-tight flex items-center gap-2">
                Google Mail (Gmail OAuth)
                {gmailStatus.is_connected && (
                  <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                    Active
                  </span>
                )}
              </h2>
              <p className="text-xs text-slate-500 font-medium mt-0.5">
                Connect your Google account securely via OAuth 2.0. No app passwords or port configurations required.
              </p>
            </div>
          </div>

          <div>
            {gmailStatus.is_connected ? (
              <button
                onClick={handleDisconnectGmail}
                disabled={disconnecting}
                className="px-4 py-2 bg-rose-50 hover:bg-rose-100 text-rose-700 font-bold text-xs rounded-xl transition border border-rose-200 disabled:opacity-50"
              >
                {disconnecting ? 'Disconnecting...' : 'Disconnect Gmail'}
              </button>
            ) : (
              <button
                onClick={handleConnectGmail}
                disabled={connecting}
                className="px-4 py-2.5 bg-sky-600 hover:bg-sky-700 text-white font-bold text-xs rounded-xl transition flex items-center gap-2 shadow-sm disabled:opacity-50"
              >
                <svg className="w-4 h-4 shrink-0" viewBox="0 0 24 24">
                  <path fill="#ffffff" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                  <path fill="#ffffff" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                  <path fill="#ffffff" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
                  <path fill="#ffffff" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
                </svg>
                {connecting ? 'Redirecting...' : 'Connect with Google'}
              </button>
            )}
          </div>
        </div>

        <div className="pt-4 text-xs text-slate-600 space-y-2">
          {gmailStatus.is_connected ? (
            <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-3.5 flex items-center justify-between">
              <div>
                <span className="font-semibold text-slate-500">Authorized Account: </span>
                <span className="font-bold text-slate-900">{gmailStatus.email}</span>
              </div>
              <div className="flex items-center gap-1.5 text-emerald-700 font-bold text-[11px]">
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                <span>Ready for Inbox & Outreach</span>
              </div>
            </div>
          ) : (
            <div className="bg-amber-50/60 border border-amber-200/70 rounded-xl p-3.5 flex items-start gap-2.5 text-amber-900">
              <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
              <p>
                No Gmail account is currently linked. Connecting Google Mail allows you to access your inbox directly and send tracked emails through the MarketIntel DB pipeline.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Connected Mailboxes */}
      <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-base font-extrabold text-slate-900 tracking-tight">Active Mailboxes</h3>
            <p className="text-xs text-slate-500 font-medium">
              Mail accounts currently available for your user session.
            </p>
          </div>
          <button
            onClick={() => { fetchGmailStatus(); fetchMailAccounts(); }}
            className="p-2 hover:bg-slate-100 rounded-xl text-slate-600 transition"
            title="Refresh accounts"
          >
            <RefreshCw className={`w-4 h-4 ${loadingAccounts || loadingGmail ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {mailAccounts.length === 0 ? (
          <div className="text-center py-6 text-xs text-slate-400 font-medium">
            No mail accounts configured yet. Connect Gmail above to get started.
          </div>
        ) : (
          <div className="divide-y divide-slate-100 border border-slate-200 rounded-xl overflow-hidden">
            {mailAccounts.map((acc) => (
              <div key={acc.id} className="p-4 flex items-center justify-between bg-white hover:bg-slate-50/60 transition">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-xl flex items-center justify-center font-bold text-xs bg-sky-50 text-sky-600 border border-sky-100">
                    G
                  </div>
                  <div>
                    <div className="font-extrabold text-slate-900 text-xs flex items-center gap-2">
                      {acc.name || acc.display_name}
                      {acc.provider === 'GMAIL_OAUTH' && (
                        <span className="text-[10px] font-bold px-1.5 py-0.2 bg-blue-50 text-blue-700 border border-blue-200 rounded">
                          Google Mail
                        </span>
                      )}
                    </div>
                    <div className="text-[11px] text-slate-500 font-medium">{acc.email_address}</div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                    Connected
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default MailboxSettings;
