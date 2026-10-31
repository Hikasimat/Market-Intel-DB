import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Bell, Clock, X, Mail } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import api from '../../services/api';
import { setUnreadCount, mergeEmails } from '../../features/inbox/inboxSlice';
import {
  getMailboxState,
  setMailboxState,
  getNotifiedUids,
  markUidsNotified,
  mergeMailboxMessages,
  resetMailboxCache,
} from '../../services/cache/inboxCacheService';
import { formatTimeForUser, formatDateTimeForUser } from '../../utils/timezone';

/** Reminder polling interval: 30 seconds (unchanged) */
const REMINDER_INTERVAL_MS = 30_000;
/** New-mail polling interval: 60 seconds */
const NEW_MAIL_INTERVAL_MS = 60_000;
/** Primary folder to poll for new mail */
const POLL_FOLDER = 'INBOX';

export default function NotificationCenter() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const { user } = useSelector((state) => state.auth);

  // ─── Reminder state (unchanged) ─────────────────────────────────────────
  const [reminders, setReminders] = useState([]);
  const [meetings, setMeetings] = useState([]);
  const [isOpen, setIsOpen] = useState(false);
  const [activeToasts, setActiveToasts] = useState([]);

  // ─── New-mail state ──────────────────────────────────────────────────────
  // We store toasts separately so mail and reminder toasts don't interfere.
  const [mailToasts, setMailToasts] = useState([]);

  // Ref to avoid stale-closure issues in intervals
  const userRef = useRef(user);
  useRef(() => { userRef.current = user; });
  useEffect(() => { userRef.current = user; }, [user]);

  // ─── Reminder logic (unchanged) ─────────────────────────────────────────

  useEffect(() => {
    if (!user) return;
    fetchReminders();
    const intervalId = setInterval(fetchReminders, REMINDER_INTERVAL_MS);
    return () => clearInterval(intervalId);
  }, [user]);

  const fetchReminders = async () => {
    if (!userRef.current) return;
    try {
      const [cbRes, mRes] = await Promise.all([
        api.get('/reminders/pending/'),
        api.get('/meetings/pending/')
      ]);
      const cbData = cbRes.data;
      const mData = mRes.data;
      setReminders(cbData);
      setMeetings(mData);
      checkNotifications(cbData, mData);
      
      if (userRef.current?.role === 'MANAGER') {
        const auditRes = await api.get('/audit-reverifications/');
        const audits = auditRes.data;
        audits.forEach(audit => {
          if (audit.status === 'CORRECTED' && !audit.manager_notified) {
            triggerAuditToast(audit);
          }
        });
      }
    } catch (err) {
      // Non-fatal; retain existing reminder state
    }
  };

  const checkNotifications = (currentReminders, currentMeetings) => {
    const now = new Date();
    currentReminders.forEach((reminder) => {
      const scheduledTime = new Date(reminder.scheduled_datetime);
      const diffMs = scheduledTime - now;
      const diffMins = Math.floor(diffMs / 60000);
      if (diffMins >= 0) {
        if (diffMins <= 5 && !reminder.notified_5m) {
          triggerReminderToast(reminder, '5m', `Call ${reminder.company_name} in 5 mins!`, 'reminders');
        } else if (diffMins <= 15 && diffMins > 5 && !reminder.notified_15m) {
          triggerReminderToast(reminder, '15m', `Call ${reminder.company_name} in 15 mins!`, 'reminders');
        } else if (diffMins <= 30 && diffMins > 15 && !reminder.notified_30m) {
          triggerReminderToast(reminder, '30m', `Call ${reminder.company_name} in 30 mins.`, 'reminders');
        }
      }
    });

    currentMeetings.forEach((meeting) => {
      const scheduledTime = new Date(meeting.scheduled_datetime);
      const diffMs = scheduledTime - now;
      const diffMins = Math.floor(diffMs / 60000);
      if (diffMins >= 0) {
        if (diffMins <= 15 && !meeting.notified_15m) {
          triggerReminderToast(meeting, '15m', `Meeting with ${meeting.company_name} in ${diffMins} mins!`, 'meetings');
        } else if (diffMins <= 30 && diffMins > 15 && !meeting.notified_30m) {
          triggerReminderToast(meeting, '30m', `Meeting with ${meeting.company_name} in ${diffMins} mins!`, 'meetings');
        } else if (diffMins <= 60 && diffMins > 30 && !meeting.notified_1h) {
          triggerReminderToast(meeting, '1h', `Meeting with ${meeting.company_name} in ${diffMins} mins.`, 'meetings');
        }
      }
    });
  };

  const triggerReminderToast = async (item, interval, message, typePath) => {
    const newToast = {
      id: `${item.id}-${interval}-${typePath}`,
      type: 'reminder',
      item,
      message,
      time: formatTimeForUser(new Date().toISOString(), user?.timezone),
    };
    setActiveToasts((prev) => [...prev, newToast]);
    try {
      await api.patch(`/${typePath}/${item.id}/mark-notified/`, { interval });
    } catch (err) {
      // Non-fatal; notification already shown
    }
    setTimeout(() => removeToast(newToast.id), 10000);
  };

  const triggerAuditToast = async (audit) => {
    const newToast = {
      id: `audit-${audit.id}`,
      type: 'audit',
      item: audit,
      message: `PRE User ${audit.pre_user_name || 'Unknown'} corrected fields for ${audit.prospect_company_name}.`,
      time: formatTimeForUser(new Date().toISOString(), user?.timezone),
    };
    // Ensure we don't duplicate active toasts
    setActiveToasts((prev) => {
      if (prev.find(t => t.id === newToast.id)) return prev;
      return [...prev, newToast];
    });
    try {
      await api.post(`/audit-reverifications/${audit.id}/mark-notified/`);
    } catch (err) {}
    setTimeout(() => removeToast(newToast.id), 10000);
  };

  const removeToast = (id) => {
    setActiveToasts((prev) => prev.filter((t) => t.id !== id));
  };

  // ─── New-mail polling (separate from reminders) ─────────────────────────

  const checkNewMail = useCallback(async () => {
    const currentUser = userRef.current;
    if (!currentUser?.id) return;

    // Skip if user has no mail account configured
    // The backend will return an error if no account exists; we handle that silently.
    const userId = currentUser.id;
    const mailAccountId = currentUser.mail_account_id || 'default';

    try {
      // Get the client's known mailbox state from IndexedDB
      const state = await getMailboxState(userId, mailAccountId, POLL_FOLDER);
      const uidvalidity = state?.uidvalidity || 0;
      const highestUid = state?.highestUid || 0;

      const res = await api.get(
        `/auth/mail-account/check-new-mail/?folder=${encodeURIComponent(POLL_FOLDER)}&uidvalidity=${uidvalidity}&highest_uid=${highestUid}`
      );
      const data = res.data;

      // Update unread count in Redux (for nav badge)
      if (typeof data.unseen_count === 'number') {
        dispatch(setUnreadCount(data.unseen_count));
      }

      // Handle UIDVALIDITY change — rebuild mailbox cache
      if (data.uidvalidity_changed) {
        await resetMailboxCache(userId, mailAccountId, POLL_FOLDER);
        // Update state with new UIDVALIDITY; next full fetch will repopulate
        if (data.uidvalidity) {
          await setMailboxState(userId, mailAccountId, POLL_FOLDER, data.uidvalidity, 0);
        }
        return;
      }

      // Update stored mailbox state
      if (data.uidvalidity && data.highest_uid !== undefined) {
        await setMailboxState(
          userId, mailAccountId, POLL_FOLDER,
          data.uidvalidity, data.highest_uid
        );
      }

      const newMessages = data.new_messages || [];
      if (newMessages.length === 0) return;

      // Merge new messages into IndexedDB cache
      await mergeMailboxMessages(userId, mailAccountId, POLL_FOLDER, newMessages);
      // Merge into Redux state
      dispatch(mergeEmails(newMessages));

      // Deduplicate notifications — only notify UIDs not previously seen
      const alreadyNotified = await getNotifiedUids(userId, mailAccountId, POLL_FOLDER);
      const genuinelyNew = newMessages.filter((m) => !alreadyNotified.has(m.uid));

      if (genuinelyNew.length === 0) return;

      // Mark these UIDs as notified (persisted so reloads don't re-trigger)
      await markUidsNotified(
        userId, mailAccountId, POLL_FOLDER,
        genuinelyNew.map((m) => m.uid)
      );

      // Show mail toast notification(s)
      if (genuinelyNew.length === 1) {
        const msg = genuinelyNew[0];
        const senderName = msg.from?.replace(/<.*>/, '').trim() || msg.from || 'Unknown sender';
        triggerMailToast(msg.uid, `New email from ${senderName}`);
      } else {
        triggerMailToast(
          `batch-${Date.now()}`,
          `${genuinelyNew.length} new emails in Inbox`
        );
      }
    } catch (err) {
      // Transient mail/network error — retain cache, do nothing destructive.
      // No popup so we don't spam the user on repeated failures.
      if (err.response?.status === 400) {
        // No mail account configured; skip silently
        return;
      }
    }
  }, [dispatch]);

  const triggerMailToast = (uid, message) => {
    const toastId = `mail-${uid}`;
    setMailToasts((prev) => {
      if (prev.find((t) => t.id === toastId)) return prev; // already shown
      return [...prev, { id: toastId, message, time: formatTimeForUser(new Date().toISOString(), user?.timezone) }];
    });
    setTimeout(() => removeMailToast(toastId), 10000);
  };

  const removeMailToast = (id) => {
    setMailToasts((prev) => prev.filter((t) => t.id !== id));
  };

  useEffect(() => {
    // Only start mail polling for authenticated PRE / LQ users
    if (!user || (user.role !== 'PRE' && user.role !== 'LQ')) return;

    checkNewMail();
    const intervalId = setInterval(checkNewMail, NEW_MAIL_INTERVAL_MS);
    return () => clearInterval(intervalId);
  }, [user, checkNewMail]);

  // ─── Helpers ─────────────────────────────────────────────────────────────

  const formatTime = (isoString) => {
    return formatDateTimeForUser(isoString, user?.timezone);
  };

  const totalBadge = reminders.length + meetings.length;

  // ─── Render ──────────────────────────────────────────────────────────────

  return (
    <>
      <div className="relative">
        <button
          onClick={() => setIsOpen(!isOpen)}
          className="relative p-1.5 text-blue-200 hover:bg-blue-500 hover:text-white transition-colors rounded-lg"
          title="Notifications"
        >
          <Bell className="w-4 h-4" />
          {totalBadge > 0 && (
            <span className="absolute top-1.5 right-1.5 w-2.5 h-2.5 bg-rose-500 rounded-full border-2 border-white"></span>
          )}
        </button>

        {isOpen && (
          <div className="absolute bottom-full left-0 mb-2 w-80 bg-white rounded-xl shadow-xl border border-slate-200 z-50 overflow-hidden">
            <div className="p-3 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
              <h3 className="font-bold text-slate-800 text-sm">Scheduled Callbacks & Meetings</h3>
              <span className="px-2 py-0.5 bg-indigo-100 text-indigo-800 text-[10px] font-bold rounded-full">{totalBadge} Pending</span>
            </div>
            <div className="max-h-96 overflow-y-auto p-2 space-y-2">
              {totalBadge === 0 ? (
                <div className="p-6 text-center text-slate-400 text-xs italic">
                  No upcoming events scheduled.
                </div>
              ) : (
                <>
                  {meetings.map((m) => (
                    <div key={`m-${m.id}`} className="p-3 bg-white border border-sky-100 rounded-xl hover:border-sky-200 transition shadow-sm">
                      <div className="flex items-center gap-2 mb-1.5">
                        <Clock className="w-3.5 h-3.5 text-sky-500" />
                        <span className="text-xs font-bold text-slate-700">{formatTime(m.scheduled_datetime)}</span>
                        <span className="ml-auto text-[10px] bg-sky-100 text-sky-800 px-1.5 py-0.5 rounded font-bold">Meeting</span>
                      </div>
                      <h4 className="font-extrabold text-sm text-slate-900 truncate">{m.company_name}</h4>
                      {m.agenda && <p className="text-xs text-slate-500 mt-1 truncate">{m.agenda}</p>}
                    </div>
                  ))}
                  {reminders.map((r) => (
                    <div key={`r-${r.id}`} className="p-3 bg-white border border-amber-100 rounded-xl hover:border-amber-200 transition shadow-sm">
                      <div className="flex items-center gap-2 mb-1.5">
                        <Clock className="w-3.5 h-3.5 text-amber-500" />
                        <span className="text-xs font-bold text-slate-700">{formatTime(r.scheduled_datetime)}</span>
                        <span className="ml-auto text-[10px] bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded font-bold">Callback</span>
                      </div>
                      <h4 className="font-extrabold text-sm text-slate-900 truncate">{r.company_name}</h4>
                      {r.description && <p className="text-xs text-slate-500 mt-1 truncate">{r.description}</p>}
                    </div>
                  ))}
                </>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Toast Notifications Container — reminders & meetings */}
      <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-3 pointer-events-none">
        {activeToasts.map((toast) => {
          const isMeeting = toast.id.includes('meetings');
          const borderColor = isMeeting ? 'border-sky-500' : 'border-amber-500';
          const iconBg = isMeeting ? 'bg-sky-100 text-sky-700' : 'bg-amber-100 text-amber-700';
          const title = isMeeting ? 'Upcoming Meeting!' : 'Upcoming Callback!';

          return (
            <div key={toast.id} className={`pointer-events-auto bg-white border-l-4 ${borderColor} rounded-lg shadow-2xl p-4 w-72 transform transition-all flex items-start gap-3`}>
              <div className={`${iconBg} rounded-full p-2 shrink-0`}>
                <Bell className="w-4 h-4" />
              </div>
              <div className="flex-1">
                <h4 className="text-sm font-extrabold text-slate-900">{title}</h4>
                <p className="text-xs text-slate-600 font-medium mt-0.5">{toast.message}</p>
                <div className="text-[10px] text-slate-400 mt-1">{toast.time}</div>
              </div>
              <button onClick={() => removeToast(toast.id)} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            </div>
          );
        })}

        {/* Mail toast notifications (sky/blue) */}
        {mailToasts.map((toast) => (
          <div
            key={toast.id}
            className="pointer-events-auto bg-white border-l-4 border-sky-500 rounded-xl shadow-2xl p-4 w-72 transform transition-all flex items-start gap-3 cursor-pointer"
            onClick={() => { navigate('/inbox'); removeMailToast(toast.id); }}
          >
            <div className="bg-sky-100 text-sky-700 rounded-full p-2 shrink-0">
              <Mail className="w-4 h-4" />
            </div>
            <div className="flex-1">
              <h4 className="text-sm font-extrabold text-slate-900">New Mail</h4>
              <p className="text-xs text-slate-600 font-medium mt-0.5">{toast.message}</p>
              <div className="text-[10px] text-slate-400 mt-1">{toast.time}</div>
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); removeMailToast(toast.id); }}
              className="text-slate-400 hover:text-slate-600"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>
    </>
  );
}
