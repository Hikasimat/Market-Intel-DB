import React, { useState } from 'react';
import { Video, Copy, ExternalLink, Link2, Loader2, CheckCircle2, AlertTriangle } from 'lucide-react';
import { toast } from 'react-toastify';

const INPUT_CLS = 'w-full p-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-semibold focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all';

export const copyToClipboard = async (text) => {
  try {
    await navigator.clipboard.writeText(text);
    toast.success('Meeting link copied');
  } catch {
    toast.error('Could not copy. Please copy the link manually.');
  }
};

/** Google Meet & Calendar scheduler for Lead Qualified meeting form. */
export default function MeetingProviderPicker({
  calendarStatus, calendarLoading, onConnectCalendar, isCreating,
}) {
  const connected = !!calendarStatus?.is_connected;
  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between">
        <label className="block text-[11px] font-extrabold text-slate-800">
          Meeting Type: <span className="text-indigo-600 font-bold">Google Meet</span>
        </label>
        {connected ? (
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
              <CheckCircle2 className="w-3 h-3 text-emerald-600" />
              Connected
            </span>
            <button
              type="button"
              onClick={onConnectCalendar}
              title="Reconnect or grant Calendar permissions"
              className="text-[10px] font-bold text-indigo-600 hover:text-indigo-800 underline cursor-pointer"
            >
              Reconnect
            </button>
          </div>
        ) : null}
      </div>

      <div className="p-3.5 rounded-xl border border-indigo-100 bg-gradient-to-r from-indigo-50/70 to-slate-50 space-y-2.5" id="google-meet-panel">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-indigo-600 text-white flex items-center justify-center shadow-sm">
            <Video className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xs font-black text-slate-900">Google Meet Video Meeting</div>
            <div className="text-[10px] font-medium text-slate-500">
              Synced with primary Google Calendar
            </div>
          </div>
        </div>

        {calendarLoading ? (
          <div className="flex items-center gap-2 text-[11px] font-bold text-slate-500 py-1">
            <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-600" /> Checking Google Calendar connection...
          </div>
        ) : connected ? (
          <div className="space-y-1.5 pt-1 border-t border-indigo-100/60">
            <div className="flex items-center justify-between gap-1.5 text-[11px] font-extrabold text-emerald-700">
              <div className="flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                <span>Google Calendar account: <strong>{calendarStatus?.email}</strong></span>
              </div>
              <button
                type="button"
                onClick={onConnectCalendar}
                className="text-[10px] font-bold text-indigo-600 hover:text-indigo-800 underline cursor-pointer"
              >
                Reconnect
              </button>
            </div>
            <p className="text-[10px] font-medium text-slate-600 leading-relaxed">
              A real Google Meet video conference will be generated on your Google Calendar upon saving. Attendee invitations are automatically dispatched to the key person.
            </p>
          </div>
        ) : (
          <div className="space-y-2 pt-1 border-t border-amber-200/60">
            <div className="flex items-center gap-1.5 text-[11px] font-extrabold text-amber-800">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
              <span>Google Calendar is not connected</span>
            </div>
            <p className="text-[10px] font-medium text-slate-600 leading-relaxed">
              Connect your Google Calendar to automatically generate Google Meet video links and sync scheduled events.
            </p>
            <button
              type="button"
              id="connect-google-calendar"
              onClick={onConnectCalendar}
              disabled={calendarStatus?.is_configured === false}
              className="inline-flex items-center gap-2 px-3.5 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 text-white font-extrabold text-xs rounded-xl shadow-sm transition hover:shadow cursor-pointer"
            >
              <Video className="w-3.5 h-3.5" />
              <span>Connect Google Calendar</span>
            </button>
          </div>
        )}

        {isCreating && (
          <div className="flex items-center gap-2 text-[11px] font-extrabold text-indigo-700 pt-1">
            <Loader2 className="w-3.5 h-3.5 animate-spin" /> Scheduling Google Meet event...
          </div>
        )}
      </div>
    </div>
  );
}

/** Shows the real Meet URL returned by Google (never a placeholder) once created. */
export function CreatedMeetingCard({ meeting, onDismiss, onRefresh, isRefreshing }) {
  if (!meeting) return null;
  const ready = meeting.conference_status === 'READY' && !!meeting.meeting_link;
  return (
    <div className={`p-3 rounded-xl border space-y-2 ${ready ? 'bg-emerald-50 border-emerald-200' : 'bg-amber-50 border-amber-200'}`} id="created-meeting-card">
      <div className="flex items-center justify-between gap-2">
        <span className={`text-[11px] font-extrabold flex items-center gap-1.5 ${ready ? 'text-emerald-800' : 'text-amber-800'}`}>
          {ready ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Loader2 className="w-3.5 h-3.5 animate-spin" />}
          {ready ? 'Google Meet created' : 'Calendar event created — Meet link is still being generated'}
        </span>
        <button type="button" onClick={onDismiss} className="text-[10px] font-bold text-slate-400 hover:text-slate-600">Dismiss</button>
      </div>
      {ready ? (
        <div className="flex flex-wrap items-center gap-2">
          <a href={meeting.meeting_link} target="_blank" rel="noreferrer" className="text-[11px] font-bold text-indigo-700 underline break-all">{meeting.meeting_link}</a>
          <button type="button" onClick={() => copyToClipboard(meeting.meeting_link)} className="px-2 py-1 bg-white border border-slate-200 rounded-lg text-[10px] font-extrabold text-slate-600 flex items-center gap-1">
            <Copy className="w-3 h-3" /> Copy
          </button>
          <a href={meeting.meeting_link} target="_blank" rel="noreferrer" className="px-2 py-1 bg-indigo-600 text-white rounded-lg text-[10px] font-extrabold flex items-center gap-1">
            <ExternalLink className="w-3 h-3" /> Open
          </a>
        </div>
      ) : (
        <button type="button" onClick={onRefresh} disabled={isRefreshing} className="px-2.5 py-1 bg-white border border-amber-300 rounded-lg text-[10px] font-extrabold text-amber-800 disabled:opacity-60">
          {isRefreshing ? 'Checking...' : 'Check for Meet link'}
        </button>
      )}
    </div>
  );
}
