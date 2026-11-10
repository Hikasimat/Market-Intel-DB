import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Bell, Clock, X, Mail, MessageCircle, Phone, PhoneCall, PhoneOff } from 'lucide-react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import api from '../../services/api';
import { setUnreadCount, mergeEmails } from '../../features/inbox/inboxSlice';
import { setWhatsappUnreadCount, setIncomingCall, setIsCallingPaired } from '../../features/whatsapp/whatsappSlice';
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
/** WhatsApp message polling interval: 10 seconds */
const WHATSAPP_POLL_INTERVAL_MS = 10_000;
/** WhatsApp call polling interval: 2.5 seconds */
const WHATSAPP_CALL_POLL_INTERVAL_MS = 2_500;
/** Primary folder to poll for new mail */
const POLL_FOLDER = 'INBOX';

export default function NotificationCenter() {
  const dispatch = useDispatch();
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useSelector((state) => state.auth);

  // ─── Reminder state (unchanged) ─────────────────────────────────────────
  const [reminders, setReminders] = useState([]);
  const [meetings, setMeetings] = useState([]);
  const [isOpen, setIsOpen] = useState(false);
  const [activeToasts, setActiveToasts] = useState([]);

  // ─── New-mail state ──────────────────────────────────────────────────────
  // We store toasts separately so mail and reminder toasts don't interfere.
  const [mailToasts, setMailToasts] = useState([]);

  // ─── WhatsApp notification state ─────────────────────────────────────────
  const [whatsappToasts, setWhatsappToasts] = useState([]);
  const [incomingCall, setIncomingCallState] = useState(null);
  const notifiedWhatsappRef = useRef(new Map());
  const isFirstWhatsappPollRef = useRef(true);

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

  // ─── WhatsApp polling & notifications ──────────────────────────────────

  const playMessageSound = () => {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      const ctx = new AudioCtx();
      const now = ctx.currentTime;
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(587.33, now);
      osc.frequency.setValueAtTime(880, now + 0.08);
      gain.gain.setValueAtTime(0.08, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.25);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.25);
      setTimeout(() => ctx.close().catch(() => {}), 300);
    } catch (_) {}
  };

  const triggerWhatsappToast = (toastId, title, message) => {
    playMessageSound();
    setWhatsappToasts((prev) => {
      if (prev.find((t) => t.id === toastId)) return prev;
      return [
        ...prev,
        {
          id: toastId,
          title,
          message,
          time: formatTimeForUser(new Date().toISOString(), user?.timezone),
        },
      ];
    });
    setTimeout(() => removeWhatsappToast(toastId), 10000);
  };

  const removeWhatsappToast = (id) => {
    setWhatsappToasts((prev) => prev.filter((t) => t.id !== id));
  };

  const markCallHandled = useCallback((rawCallId) => {
    const clean = String(rawCallId || '').replace(/^call_/, '').trim();
    if (!clean) return;
    try {
      const saved = sessionStorage.getItem('wa_handled_call_ids');
      const set = saved ? new Set(JSON.parse(saved)) : new Set();
      set.add(clean);
      sessionStorage.setItem('wa_handled_call_ids', JSON.stringify(Array.from(set).slice(-200)));
    } catch (_) {}
  }, []);

  const isCallHandled = useCallback((rawCallId) => {
    const clean = String(rawCallId || '').replace(/^call_/, '').trim();
    if (!clean) return true;
    try {
      const saved = sessionStorage.getItem('wa_handled_call_ids');
      const set = saved ? new Set(JSON.parse(saved)) : new Set();
      return set.has(clean);
    } catch (_) {
      return false;
    }
  }, []);

  const checkWhatsAppCalling = useCallback(async () => {
    const currentUser = userRef.current;
    if (!currentUser?.id) return;

    try {
      const res = await api.get('/whatsapp/calls/status/');
      const paired = Boolean(res.data?.calling?.paired || res.data?.paired || res.data?.connected);
      dispatch(setIsCallingPaired(paired));

      const incoming = res.data?.incoming_call;
      if (incoming && incoming.call_id) {
        const cleanId = String(incoming.call_id).replace(/^call_/, '').trim();
        if (!cleanId || incoming.status !== 'ringing' || isCallHandled(cleanId)) {
          setIncomingCallState(null);
          dispatch(setIncomingCall(null));
        } else {
          const callObj = { ...incoming, call_id: cleanId };
          setIncomingCallState(callObj);
          dispatch(setIncomingCall(callObj));
        }
      } else {
        setIncomingCallState(null);
        dispatch(setIncomingCall(null));
      }
    } catch (_) {}
  }, [dispatch, isCallHandled]);

  useEffect(() => {
    if (!user) return;
    checkWhatsAppCalling();
    const interval = setInterval(checkWhatsAppCalling, WHATSAPP_CALL_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [user, checkWhatsAppCalling]);

  // Audible ring tone for incoming calls when user is NOT on /whatsapp
  useEffect(() => {
    if (!incomingCall || location.pathname === '/whatsapp') return;
    let ringInterval = null;
    let ringCtx = null;
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      ringCtx = new AudioCtx();
      const playTone = () => {
        if (!ringCtx || ringCtx.state === 'closed') return;
        if (ringCtx.state === 'suspended') ringCtx.resume().catch(() => {});
        const now = ringCtx.currentTime;
        const osc = ringCtx.createOscillator();
        const gain = ringCtx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(440, now);
        osc.frequency.setValueAtTime(480, now + 0.1);
        gain.gain.setValueAtTime(0.14, now);
        gain.gain.exponentialRampToValueAtTime(0.001, now + 0.8);
        osc.connect(gain);
        gain.connect(ringCtx.destination);
        osc.start(now);
        osc.stop(now + 0.8);
      };
      playTone();
      ringInterval = setInterval(playTone, 2000);
    } catch (_) {}
    return () => {
      if (ringInterval) clearInterval(ringInterval);
      if (ringCtx) ringCtx.close().catch(() => {});
    };
  }, [incomingCall, location.pathname]);

  const handleDeclineCall = async (call) => {
    const cleanId = String(call?.call_id || '').replace(/^call_/, '').trim();
    if (!cleanId) return;
    markCallHandled(cleanId);
    setIncomingCallState(null);
    dispatch(setIncomingCall(null));
    try {
      await api.post(`/whatsapp/calls/${encodeURIComponent(cleanId)}/reject/`, {
        session_name: call.session_name || 'default',
      });
    } catch (_) {}
  };

  const handleAcceptCall = async (call) => {
    const cleanId = String(call?.call_id || '').replace(/^call_/, '').trim();
    if (!cleanId) return;
    markCallHandled(cleanId);
    setIncomingCallState(null);
    dispatch(setIncomingCall(null));
    try {
      await api.post(`/whatsapp/calls/${encodeURIComponent(cleanId)}/accept/`, {
        session_name: call.session_name || 'default',
      });
    } catch (_) {}
    navigate('/whatsapp', { state: { autoAcceptCall: call } });
  };

  const checkNewWhatsApp = useCallback(async () => {
    const currentUser = userRef.current;
    if (!currentUser?.id) return;

    try {
      const res = await api.get('/whatsapp/conversations/');
      const convList = Array.isArray(res.data) ? res.data : [];

      // Calculate total unread count across all conversations
      const totalUnread = convList.reduce((acc, c) => acc + (c.unread_count || 0), 0);
      dispatch(setWhatsappUnreadCount(totalUnread));

      // On initial poll, seed the map of last seen unread timestamps to avoid toast spam on mount
      if (isFirstWhatsappPollRef.current) {
        convList.forEach((c) => {
          if (c.id) {
            notifiedWhatsappRef.current.set(c.id, {
              lastMsgAt: c.last_message_at || '',
              unreadCount: c.unread_count || 0,
            });
          }
        });
        isFirstWhatsappPollRef.current = false;
        return;
      }

      // Check for newly arrived unread messages
      for (const conv of convList) {
        const prevRecord = notifiedWhatsappRef.current.get(conv.id) || { lastMsgAt: '', unreadCount: 0 };
        const hasNewUnread = (conv.unread_count || 0) > 0 && (
          (conv.unread_count || 0) > prevRecord.unreadCount ||
          (conv.last_message_at && conv.last_message_at !== prevRecord.lastMsgAt)
        );

        if (hasNewUnread && !conv.last_message_from_me) {
          const sender = conv.whatsapp_name || conv.prospect_contact?.name || conv.phone_number || 'New contact';
          const snippet = conv.last_message_preview || 'New message received';
          const toastId = `wa-${conv.id}-${conv.last_message_at || Date.now()}`;
          triggerWhatsappToast(toastId, `WhatsApp from ${sender}`, snippet);
        }

        notifiedWhatsappRef.current.set(conv.id, {
          lastMsgAt: conv.last_message_at || '',
          unreadCount: conv.unread_count || 0,
        });
      }
    } catch (err) {
      // Non-critical; ignore network issues silently
    }
  }, [dispatch]);

  useEffect(() => {
    // Start WhatsApp polling for authenticated users (PRE, MANAGER, LQ)
    if (!user) return;

    checkNewWhatsApp();
    const intervalId = setInterval(checkNewWhatsApp, WHATSAPP_POLL_INTERVAL_MS);
    return () => clearInterval(intervalId);
  }, [user, checkNewWhatsApp]);

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

        {/* WhatsApp toast notifications (emerald/green) */}
        {whatsappToasts.map((toast) => (
          <div
            key={toast.id}
            className="pointer-events-auto bg-white border-l-4 border-emerald-500 rounded-xl shadow-2xl p-4 w-72 transform transition-all flex items-start gap-3 cursor-pointer"
            onClick={() => { navigate('/whatsapp'); removeWhatsappToast(toast.id); }}
          >
            <div className="bg-emerald-100 text-emerald-700 rounded-full p-2 shrink-0">
              <MessageCircle className="w-4 h-4" />
            </div>
            <div className="flex-1">
              <h4 className="text-sm font-extrabold text-slate-900">{toast.title || 'New WhatsApp Message'}</h4>
              <p className="text-xs text-slate-600 font-medium mt-0.5">{toast.message}</p>
              <div className="text-[10px] text-slate-400 mt-1">{toast.time}</div>
            </div>
            <button
              onClick={(e) => { e.stopPropagation(); removeWhatsappToast(toast.id); }}
              className="text-slate-400 hover:text-slate-600"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        ))}
      </div>

      {/* Global WhatsApp Incoming Call Modal (active when user is anywhere else in the application) */}
      {incomingCall && location.pathname !== '/whatsapp' && (
        <div className="fixed top-6 right-6 z-[9999] pointer-events-auto bg-slate-900/95 backdrop-blur-md text-white border-2 border-emerald-500 rounded-2xl shadow-2xl p-5 w-88 max-w-[calc(100vw-2rem)] animate-in fade-in zoom-in-95 duration-200">
          <div className="flex items-center gap-3.5 mb-3.5">
            <div className="w-12 h-12 rounded-full bg-emerald-500/20 border border-emerald-400 flex items-center justify-center shrink-0">
              <PhoneCall className="w-6 h-6 text-emerald-400 animate-bounce" />
            </div>
            <div className="flex-1 min-w-0 text-left">
              <div className="flex items-center gap-2">
                <span className="text-[11px] uppercase tracking-wider font-extrabold text-emerald-400">Incoming WhatsApp Call</span>
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
              </div>
              <h4 className="text-sm font-bold text-white truncate mt-0.5">
                {incomingCall.caller_name || incomingCall.caller_phone || 'WhatsApp Contact'}
              </h4>
              <p className="text-xs text-slate-300 font-mono truncate">
                {incomingCall.caller_phone || 'WhatsApp Voice Call'}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2.5 pt-2.5 border-t border-slate-700/60">
            <button
              type="button"
              onClick={() => handleDeclineCall(incomingCall)}
              className="flex-1 py-2 px-3 rounded-xl bg-rose-600 hover:bg-rose-700 text-white text-xs font-bold transition flex items-center justify-center gap-1.5 shadow-md active:scale-95 cursor-pointer"
            >
              <PhoneOff className="w-4 h-4" />
              <span>Decline</span>
            </button>
            <button
              type="button"
              onClick={() => handleAcceptCall(incomingCall)}
              className="flex-1 py-2 px-3 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-bold transition flex items-center justify-center gap-1.5 shadow-lg shadow-emerald-500/30 ring-2 ring-emerald-400/50 active:scale-95 cursor-pointer animate-pulse"
            >
              <PhoneCall className="w-4 h-4" />
              <span>Accept</span>
            </button>
          </div>
        </div>
      )}
    </>
  );
}
