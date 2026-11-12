import React from 'react';
import { Video, Copy, ExternalLink, Loader2, CheckCircle2, AlertTriangle, Calendar as CalendarIcon, Users } from 'lucide-react';
import { toast } from 'react-toastify';

export const copyToClipboard = async (text) => {
  try {
    await navigator.clipboard.writeText(text);
    toast.success('Meeting link copied');
  } catch {
    toast.error('Could not copy. Please copy the link manually.');
  }
};

export const PROVIDERS = [
  {
    id: 'GOOGLE_MEET',
    name: 'Google Meet',
    tagline: 'Google Calendar sync',
    iconColor: 'bg-indigo-600 text-white',
    badgeClass: 'bg-indigo-50 text-indigo-700 border-indigo-200',
    selectedBorder: 'border-indigo-600 bg-indigo-50/70 ring-2 ring-indigo-200',
    icon: Video,
  },
  {
    id: 'ZOOM',
    name: 'Zoom Meeting',
    tagline: 'Calendar event sync',
    iconColor: 'bg-sky-500 text-white',
    badgeClass: 'bg-sky-50 text-sky-700 border-sky-200',
    selectedBorder: 'border-sky-600 bg-sky-50/70 ring-2 ring-sky-200',
    icon: Video,
  },
  {
    id: 'MS_TEAMS',
    name: 'Microsoft Teams',
    tagline: 'Outlook Calendar sync',
    iconColor: 'bg-violet-600 text-white',
    badgeClass: 'bg-violet-50 text-violet-700 border-violet-200',
    selectedBorder: 'border-violet-600 bg-violet-50/70 ring-2 ring-violet-200',
    icon: Users,
  },
];

/** Multi-provider picker & connection panel for Lead Qualified workflow. */
export default function MeetingProviderPicker({
  selectedProvider,
  onSelectProvider,
  providersStatus,
  loadingStatus,
  onConnectProvider,
  isCreating,
}) {
  const currentProvider = PROVIDERS.find((p) => p.id === selectedProvider) || null;

  // Determine status for the currently selected provider
  const googleStatus = providersStatus?.google_meet || {};
  const zoomStatus = providersStatus?.zoom || {};
  const msStatus = providersStatus?.ms_teams || {};

  let currentStatus = { is_connected: false, email: '' };
  if (selectedProvider === 'GOOGLE_MEET') {
    currentStatus = googleStatus;
  } else if (selectedProvider === 'ZOOM') {
    currentStatus = zoomStatus;
  } else if (selectedProvider === 'MS_TEAMS') {
    currentStatus = msStatus;
  }

  const isConnected = !!currentStatus?.is_connected;

  // For Zoom, check whether an eligible calendar is connected (Google or Outlook)
  const zoomCalendarConnected = !!googleStatus?.is_connected || !!msStatus?.is_connected;
  const zoomCalendarEmail = googleStatus?.is_connected ? googleStatus.email : msStatus?.email;
  const zoomCalendarName = googleStatus?.is_connected ? 'Google Calendar' : (msStatus?.is_connected ? 'Outlook Calendar' : 'Calendar');

  return (
    <div className="space-y-3">
      {/* Step 2 Ask: Which meeting platform would you like to use? */}
      <div>
        <label className="block text-[11px] font-extrabold text-slate-800 mb-1.5">
          Which meeting platform would you like to use? <span className="text-rose-500">*</span>
        </label>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
          {PROVIDERS.map((provider) => {
            const isSelected = selectedProvider === provider.id;
            const Icon = provider.icon;
            let provStatus = false;
            if (provider.id === 'GOOGLE_MEET') provStatus = !!googleStatus.is_connected;
            if (provider.id === 'ZOOM') provStatus = !!zoomStatus.is_connected;
            if (provider.id === 'MS_TEAMS') provStatus = !!msStatus.is_connected;

            return (
              <button
                key={provider.id}
                type="button"
                onClick={() => onSelectProvider(provider.id)}
                className={`p-3 rounded-xl border text-left transition-all flex items-start gap-2.5 cursor-pointer ${
                  isSelected
                    ? provider.selectedBorder
                    : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50'
                }`}
              >
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 shadow-sm ${provider.iconColor}`}>
                  <Icon className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-black text-slate-900 truncate">{provider.name}</span>
                    {provStatus && (
                      <span className="w-2 h-2 rounded-full bg-emerald-500" title="Connected" />
                    )}
                  </div>
                  <span className="text-[10px] font-semibold text-slate-500 block truncate">{provider.tagline}</span>
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Selected Provider Connection Panel */}
      {selectedProvider && (
        <div className="p-3.5 rounded-xl border border-slate-200 bg-gradient-to-r from-slate-50 to-indigo-50/40 space-y-2.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className={`text-[10px] font-black uppercase px-2 py-0.5 rounded-full border ${currentProvider?.badgeClass || 'bg-slate-100 text-slate-700'}`}>
                {currentProvider?.name}
              </span>
              <span className="text-xs font-bold text-slate-700">Platform Integration</span>
            </div>
            {isConnected ? (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
                <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                Connected
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-700 border border-amber-200">
                <AlertTriangle className="w-3 h-3 text-amber-600" />
                Not Connected
              </span>
            )}
          </div>

          {loadingStatus ? (
            <div className="flex items-center gap-2 text-[11px] font-bold text-slate-500 py-1">
              <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-600" /> Checking connection status...
            </div>
          ) : isConnected ? (
            <div className="space-y-1.5 pt-1 border-t border-slate-200/60">
              <div className="flex items-center justify-between gap-1.5 text-[11px] font-extrabold text-emerald-800">
                <div className="flex items-center gap-1.5 truncate">
                  <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                  <span className="truncate">Authorized Account: <strong>{currentStatus.email}</strong></span>
                </div>
                <button
                  type="button"
                  onClick={() => onConnectProvider(selectedProvider)}
                  className="text-[10px] font-bold text-indigo-600 hover:text-indigo-800 underline cursor-pointer shrink-0"
                >
                  Reconnect
                </button>
              </div>

              {selectedProvider === 'GOOGLE_MEET' && (
                <p className="text-[10px] font-medium text-slate-600 leading-relaxed">
                  A genuine Google Meet video link will be generated and scheduled on your primary Google Calendar. Key contacts receive automated invitations.
                </p>
              )}

              {selectedProvider === 'ZOOM' && (
                <div className="space-y-1">
                  <p className="text-[10px] font-medium text-slate-600 leading-relaxed">
                    A genuine Zoom meeting link will be generated via Zoom Meetings API.
                  </p>
                  {zoomCalendarConnected ? (
                    <div className="flex items-center gap-1.5 text-[10px] font-bold text-emerald-700">
                      <CalendarIcon className="w-3 h-3 text-emerald-600 shrink-0" />
                      <span>Calendar Synchronization: {zoomCalendarName} ({zoomCalendarEmail})</span>
                    </div>
                  ) : (
                    <div className="flex items-center justify-between gap-1 text-[10px] font-semibold text-amber-800 bg-amber-50 p-1.5 rounded-lg border border-amber-200">
                      <span>Sync requires connected calendar (Google or Outlook).</span>
                      <button
                        type="button"
                        onClick={() => onConnectProvider('GOOGLE_MEET')}
                        className="text-indigo-600 font-bold underline"
                      >
                        Connect Calendar
                      </button>
                    </div>
                  )}
                </div>
              )}

              {selectedProvider === 'MS_TEAMS' && (
                <p className="text-[10px] font-medium text-slate-600 leading-relaxed">
                  A genuine Microsoft Teams video meeting will be created via Microsoft Graph and synced directly with your Outlook Calendar.
                </p>
              )}
            </div>
          ) : (
            <div className="space-y-2 pt-1 border-t border-amber-200/60">
              <div className="flex items-center gap-1.5 text-[11px] font-extrabold text-amber-800">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                <span>{currentProvider?.name} is not connected</span>
              </div>
              <p className="text-[10px] font-medium text-slate-600 leading-relaxed">
                Connect your {currentProvider?.name} account to automatically generate authentic meeting links and synchronize scheduled calendar events.
              </p>
              <button
                type="button"
                onClick={() => onConnectProvider(selectedProvider)}
                className="inline-flex items-center gap-2 px-3.5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-extrabold text-xs rounded-xl shadow-sm transition hover:shadow cursor-pointer"
              >
                <Video className="w-3.5 h-3.5" />
                <span>Connect {currentProvider?.name}</span>
              </button>
            </div>
          )}

          {isCreating && (
            <div className="flex items-center gap-2 text-[11px] font-extrabold text-indigo-700 pt-1">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Scheduling {currentProvider?.name} event...
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** Shows the real meeting URL returned by provider API once created. */
export function CreatedMeetingCard({ meeting, onDismiss, onRefresh, isRefreshing }) {
  if (!meeting) return null;

  const providerId = meeting.meeting_provider || 'GOOGLE_MEET';
  const providerMeta = PROVIDERS.find((p) => p.id === providerId) || PROVIDERS[0];
  const ready = meeting.conference_status === 'READY' && !!meeting.meeting_link;

  const calendarTypeLabel =
    meeting.calendar_type === 'GOOGLE_CALENDAR'
      ? 'Google Calendar'
      : meeting.calendar_type === 'OUTLOOK_CALENDAR'
      ? 'Outlook Calendar'
      : providerId === 'GOOGLE_MEET'
      ? 'Google Calendar'
      : providerId === 'MS_TEAMS'
      ? 'Outlook Calendar'
      : 'Connected Calendar';

  return (
    <div
      className={`p-3.5 rounded-xl border space-y-2.5 ${
        ready ? 'bg-emerald-50/80 border-emerald-200' : 'bg-amber-50/80 border-amber-200'
      }`}
      id="created-meeting-card"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className={`px-2 py-0.5 rounded-full text-[10px] font-black border uppercase ${providerMeta.badgeClass}`}>
            {providerMeta.name}
          </span>
          <span
            className={`text-[11px] font-extrabold flex items-center gap-1.5 ${
              ready ? 'text-emerald-800' : 'text-amber-800'
            }`}
          >
            {ready ? <CheckCircle2 className="w-3.5 h-3.5" /> : <Loader2 className="w-3.5 h-3.5 animate-spin" />}
            {ready ? 'Meeting Created & Scheduled' : 'Generating meeting link...'}
          </span>
        </div>
        <button
          type="button"
          onClick={onDismiss}
          className="text-[10px] font-bold text-slate-400 hover:text-slate-600 cursor-pointer"
        >
          Dismiss
        </button>
      </div>

      {ready ? (
        <div className="space-y-2">
          {/* Meeting details */}
          <div className="text-[11px] text-slate-700 flex flex-wrap items-center gap-x-3 gap-y-1 font-semibold">
            {meeting.meeting_date && (
              <span>
                📅 <strong>{meeting.meeting_date}</strong> {meeting.meeting_time ? `at ${meeting.meeting_time}` : ''}
              </span>
            )}
            <span className="text-emerald-700 flex items-center gap-1">
              <CalendarIcon className="w-3 h-3" /> Synced with {calendarTypeLabel}
            </span>
          </div>

          {meeting.agenda && (
            <div className="text-[11px] text-slate-600 bg-white/70 p-2 rounded-lg border border-slate-200/60 font-medium">
              <span className="font-bold text-slate-700">Agenda:</span> {meeting.agenda}
            </div>
          )}

          {/* Action links */}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <a
              href={meeting.meeting_link}
              target="_blank"
              rel="noreferrer"
              className="text-[11px] font-bold text-indigo-700 underline break-all"
            >
              {meeting.meeting_link}
            </a>
            <button
              type="button"
              onClick={() => copyToClipboard(meeting.meeting_link)}
              className="px-2.5 py-1 bg-white border border-slate-200 rounded-lg text-[10px] font-extrabold text-slate-700 hover:bg-slate-50 flex items-center gap-1 shadow-xs cursor-pointer"
            >
              <Copy className="w-3 h-3" /> Copy Meeting Link
            </button>
            <a
              href={meeting.meeting_link}
              target="_blank"
              rel="noreferrer"
              className="px-2.5 py-1 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-[10px] font-extrabold flex items-center gap-1 shadow-xs"
            >
              <ExternalLink className="w-3 h-3" /> Open
            </a>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={onRefresh}
          disabled={isRefreshing}
          className="px-2.5 py-1 bg-white border border-amber-300 rounded-lg text-[10px] font-extrabold text-amber-800 disabled:opacity-60 cursor-pointer"
        >
          {isRefreshing ? 'Checking...' : 'Check for Meeting link'}
        </button>
      )}
    </div>
  );
}
