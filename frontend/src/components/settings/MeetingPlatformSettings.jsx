import React, { useState, useEffect, useCallback } from 'react';
import { Video, RefreshCw, CheckCircle2, AlertTriangle, ExternalLink, Calendar, Users } from 'lucide-react';
import { toast } from 'react-toastify';
import api from '../../services/api';

export default function MeetingPlatformSettings() {
  const [loading, setLoading] = useState(false);
  const [disconnecting, setDisconnecting] = useState('');
  const [connecting, setConnecting] = useState('');
  const [status, setStatus] = useState({
    google_meet: { is_connected: false, is_configured: false, email: '' },
    zoom: { is_connected: false, is_configured: false, email: '' },
    ms_teams: { is_connected: false, is_configured: false, email: '' },
  });

  const fetchStatus = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.get('/auth/meeting-providers/status/');
      if (res.data) {
        setStatus(res.data);
      }
    } catch (e) {
      console.warn('Could not fetch meeting platforms status', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const handleConnect = async (providerKey) => {
    setConnecting(providerKey);
    try {
      let endpoint = '/auth/google/calendar/url/';
      let storageKey = 'calendar_oauth_return_url';
      if (providerKey === 'zoom') {
        endpoint = '/auth/zoom/url/';
        storageKey = 'zoom_oauth_return_url';
      } else if (providerKey === 'ms_teams') {
        endpoint = '/auth/microsoft/url/';
        storageKey = 'microsoft_oauth_return_url';
      }

      const res = await api.get(endpoint);
      const authUrl = res.data?.url || res.data?.authorization_url;
      if (authUrl) {
        localStorage.setItem(storageKey, window.location.pathname + window.location.search);
        window.location.href = authUrl;
      } else {
        toast.error('Authorization URL was not returned.');
      }
    } catch (e) {
      toast.error('Failed to initiate authorization flow.');
    } finally {
      setConnecting('');
    }
  };

  const handleDisconnect = async (providerKey, label) => {
    if (!window.confirm(`Disconnect your ${label} account? Scheduled meetings using this provider will require reconnection.`)) {
      return;
    }
    setDisconnecting(providerKey);
    try {
      let endpoint = '/auth/google/calendar/disconnect/';
      if (providerKey === 'zoom') endpoint = '/auth/zoom/disconnect/';
      else if (providerKey === 'ms_teams') endpoint = '/auth/microsoft/disconnect/';

      await api.post(endpoint);
      toast.success(`${label} disconnected successfully.`);
      fetchStatus();
    } catch (e) {
      toast.error(`Failed to disconnect ${label}.`);
    } finally {
      setDisconnecting('');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-black text-slate-900 tracking-tight">Meeting Platforms & Calendar Integration</h2>
          <p className="text-xs text-slate-500 font-medium mt-0.5">
            Connect your meeting platforms to automatically generate authentic video links and synchronize calendar invitations during prospect qualification.
          </p>
        </div>
        <button
          type="button"
          onClick={fetchStatus}
          disabled={loading}
          className="p-2 border border-slate-200 rounded-xl hover:bg-slate-50 text-slate-600 font-bold text-xs flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-indigo-600' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4">
        {/* Google Meet Card */}
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
            <div className="flex items-center gap-3">
              <div className="w-11 h-11 rounded-xl bg-indigo-50 border border-indigo-100 flex items-center justify-center text-indigo-600 shadow-xs">
                <Video className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-extrabold text-slate-900">Google Meet & Google Calendar</h3>
                  {status.google_meet.is_connected && (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                      Active
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 font-medium">
                  Generates genuine Google Meet links and syncs events to your primary Google Calendar.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {status.google_meet.is_connected ? (
                <button
                  type="button"
                  onClick={() => handleDisconnect('google_meet', 'Google Calendar')}
                  disabled={disconnecting === 'google_meet'}
                  className="px-3.5 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-700 font-bold text-xs rounded-xl border border-rose-200 disabled:opacity-50 cursor-pointer"
                >
                  {disconnecting === 'google_meet' ? 'Disconnecting...' : 'Disconnect'}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => handleConnect('google_meet')}
                  disabled={connecting === 'google_meet'}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs rounded-xl flex items-center gap-2 shadow-xs cursor-pointer disabled:opacity-50"
                >
                  <Video className="w-3.5 h-3.5" />
                  <span>{connecting === 'google_meet' ? 'Connecting...' : 'Connect Google Calendar'}</span>
                </button>
              )}
            </div>
          </div>

          {status.google_meet.is_connected ? (
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 flex items-center justify-between text-xs">
              <span className="font-semibold text-slate-600">
                Connected Account: <strong className="text-slate-900">{status.google_meet.email}</strong>
              </span>
              <span className="text-emerald-700 font-bold flex items-center gap-1 text-[11px]">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> Ready to schedule
              </span>
            </div>
          ) : (
            <div className="bg-amber-50/60 border border-amber-200 rounded-xl p-3 flex items-start gap-2 text-xs text-amber-800">
              <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
              <span>Connect your Google account to automatically generate Meet links and sync meetings.</span>
            </div>
          )}
        </div>

        {/* Zoom Card */}
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
            <div className="flex items-center gap-3">
              <div className="w-11 h-11 rounded-xl bg-sky-50 border border-sky-100 flex items-center justify-center text-sky-600 shadow-xs">
                <Video className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-extrabold text-slate-900">Zoom Meetings</h3>
                  {status.zoom.is_connected && (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                      Active
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 font-medium">
                  Creates scheduled Zoom meetings via Zoom Meetings API and syncs to your connected calendar.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {status.zoom.is_connected ? (
                <button
                  type="button"
                  onClick={() => handleDisconnect('zoom', 'Zoom')}
                  disabled={disconnecting === 'zoom'}
                  className="px-3.5 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-700 font-bold text-xs rounded-xl border border-rose-200 disabled:opacity-50 cursor-pointer"
                >
                  {disconnecting === 'zoom' ? 'Disconnecting...' : 'Disconnect'}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => handleConnect('zoom')}
                  disabled={connecting === 'zoom'}
                  className="px-4 py-2 bg-sky-600 hover:bg-sky-700 text-white font-bold text-xs rounded-xl flex items-center gap-2 shadow-xs cursor-pointer disabled:opacity-50"
                >
                  <Video className="w-3.5 h-3.5" />
                  <span>{connecting === 'zoom' ? 'Connecting...' : 'Connect Zoom'}</span>
                </button>
              )}
            </div>
          </div>

          {status.zoom.is_connected ? (
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 flex items-center justify-between text-xs">
              <span className="font-semibold text-slate-600">
                Connected Zoom Account: <strong className="text-slate-900">{status.zoom.email}</strong>
              </span>
              <span className="text-emerald-700 font-bold flex items-center gap-1 text-[11px]">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> Ready to schedule
              </span>
            </div>
          ) : (
            <div className="bg-amber-50/60 border border-amber-200 rounded-xl p-3 flex items-start gap-2 text-xs text-amber-800">
              <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
              <span>Connect your Zoom account to schedule Zoom video meetings for qualified leads.</span>
            </div>
          )}
        </div>

        {/* Microsoft Teams Card */}
        <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs space-y-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
            <div className="flex items-center gap-3">
              <div className="w-11 h-11 rounded-xl bg-violet-50 border border-violet-100 flex items-center justify-center text-violet-600 shadow-xs">
                <Users className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-extrabold text-slate-900">Microsoft Teams & Outlook Calendar</h3>
                  {status.ms_teams.is_connected && (
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                      Active
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 font-medium">
                  Generates Microsoft Teams video meetings via Microsoft Graph and syncs directly with Outlook Calendar.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {status.ms_teams.is_connected ? (
                <button
                  type="button"
                  onClick={() => handleDisconnect('ms_teams', 'Microsoft 365')}
                  disabled={disconnecting === 'ms_teams'}
                  className="px-3.5 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-700 font-bold text-xs rounded-xl border border-rose-200 disabled:opacity-50 cursor-pointer"
                >
                  {disconnecting === 'ms_teams' ? 'Disconnecting...' : 'Disconnect'}
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => handleConnect('ms_teams')}
                  disabled={connecting === 'ms_teams'}
                  className="px-4 py-2 bg-violet-600 hover:bg-violet-700 text-white font-bold text-xs rounded-xl flex items-center gap-2 shadow-xs cursor-pointer disabled:opacity-50"
                >
                  <Users className="w-3.5 h-3.5" />
                  <span>{connecting === 'ms_teams' ? 'Connecting...' : 'Connect Microsoft 365'}</span>
                </button>
              )}
            </div>
          </div>

          {status.ms_teams.is_connected ? (
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 flex items-center justify-between text-xs">
              <span className="font-semibold text-slate-600">
                Connected Microsoft Account: <strong className="text-slate-900">{status.ms_teams.email}</strong>
              </span>
              <span className="text-emerald-700 font-bold flex items-center gap-1 text-[11px]">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" /> Ready to schedule
              </span>
            </div>
          ) : (
            <div className="bg-amber-50/60 border border-amber-200 rounded-xl p-3 flex items-start gap-2 text-xs text-amber-800">
              <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
              <span>Connect Microsoft 365 to schedule Teams meetings and synchronize your Outlook Calendar.</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

