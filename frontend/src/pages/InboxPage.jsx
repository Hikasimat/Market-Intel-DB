import React, { useState, useEffect, useCallback, useRef } from 'react';
import { 
  Mail, Send, AlertTriangle, RefreshCw, ChevronLeft, Loader2, Paperclip, 
  Building2, Reply, Edit3, X, Download, BarChart2, Eye, Activity, Zap, TrendingUp, Clock 
} from 'lucide-react';
import { toast } from 'react-toastify';
import { useDispatch, useSelector } from 'react-redux';
import api from '../services/api';
import TemplatePicker from '../components/lq/TemplatePicker';
import {
  setEmails,
  setInboxLoading,
  setSyncError,
  setActiveFolder,
  mergeEmails,
} from '../features/inbox/inboxSlice';
import {
  getMailboxMessages,
  setMailboxMessages,
  getMailboxState,
  setMailboxState,
  getEmailBody,
  setEmailBody,
  resetMailboxCache,
} from '../services/cache/inboxCacheService';

const FOLDERS = [
  { id: 'INBOX', label: 'Inbox', icon: Mail },
  { id: '"[Gmail]/Sent Mail"', label: 'Sent', icon: Send },
  { id: '"[Gmail]/Spam"', label: 'Spam', icon: AlertTriangle },
];

const InboxPage = () => {
  const dispatch = useDispatch();
  const { user } = useSelector((state) => state.auth);
  const { emails, loading, activeFolder } = useSelector((state) => state.inbox);

  const [selectedEmail, setSelectedEmail] = useState(null);
  const [bodyLoading, setBodyLoading] = useState(false);
  const [emailBody, setEmailBodyState] = useState({ html_body: '', text_body: '', attachments: [] });

  const [showCompose, setShowCompose] = useState(false);
  const [composeData, setComposeData] = useState({ to: '', cc: '', bcc: '', subject: '', body: '' });
  const [sendingEmail, setSendingEmail] = useState(false);
  const sendingEmailRef = useRef(false);
  const [templateSelection, setTemplateSelection] = useState({ templateId: '', signatureId: '', baseBody: null });
  const [attachments, setAttachments] = useState([]);
  const [attachmentError, setAttachmentError] = useState('');
  const [showCc, setShowCc] = useState(false);
  const [showBcc, setShowBcc] = useState(false);
  const [senderMailStatus, setSenderMailStatus] = useState(null);
  const fileInputRef = useRef(null);

  const [searchQuery, setSearchQuery] = useState('');

  // Email Tracking State
  const [showTrackingModal, setShowTrackingModal] = useState(false);
  const [trackingModalData, setTrackingModalData] = useState(null);
  const [isRefreshingTracking, setIsRefreshingTracking] = useState(false);
  const [isSimulatingOpen, setIsSimulatingOpen] = useState(false);

  useEffect(() => {
    api.get('/auth/mail-account/')
      .then(res => {
        if (res.data && res.data.length > 0) {
          setSenderMailStatus(res.data[0]);
        }
      })
      .catch(err => console.error('Failed to fetch mail account', err));
  }, []);

  const handleFileChange = (e) => {
    const files = Array.from(e.target.files);
    let currentTotalSize = attachments.reduce((sum, f) => sum + f.size, 0);
    const validFiles = [];

    for (const file of files) {
      const ext = file.name.split('.').pop().toLowerCase();
      if (['exe', 'bat', 'cmd', 'js', 'ps1', 'vbs', 'scr'].includes(ext)) {
        setAttachmentError(`File ${file.name} is not allowed for security reasons.`);
        return;
      }
      if (file.size > 10 * 1024 * 1024) {
        setAttachmentError(`File ${file.name} exceeds the 10MB individual limit.`);
        return;
      }
      if (currentTotalSize + file.size > 25 * 1024 * 1024) {
        setAttachmentError(`Adding ${file.name} exceeds the total 25MB attachment limit.`);
        return;
      }
      currentTotalSize += file.size;
      validFiles.push(file);
    }
    setAttachments(prev => [...prev, ...validFiles]);
    setAttachmentError('');
    e.target.value = '';
  };

  const removeAttachment = (index) => {
    setAttachments(prev => prev.filter((_, i) => i !== index));
    setAttachmentError('');
  };

  const handleCompose = () => {
    setComposeData({ to: '', cc: '', bcc: '', subject: '', body: '' });
    setAttachments([]);
    setAttachmentError('');
    setShowCc(false);
    setShowBcc(false);
    setTemplateSelection({ templateId: '', signatureId: '', baseBody: null });
    setShowCompose(true);
  };

  const handleReply = () => {
    if (!selectedEmail) return;
    const toAddress = selectedEmail.from.match(/<([^>]+)>/)?.[1] || selectedEmail.from;
    setComposeData({
      to: toAddress,
      cc: '',
      bcc: '',
      subject: selectedEmail.subject?.startsWith('Re:') ? selectedEmail.subject : `Re: ${selectedEmail.subject || ''}`,
      body: `\n\n\n--- Original Message ---\nFrom: ${selectedEmail.from}\nDate: ${selectedEmail.date}\nSubject: ${selectedEmail.subject}\n`
    });
    setAttachments([]);
    setAttachmentError('');
    setShowCc(false);
    setShowBcc(false);
    setTemplateSelection({ templateId: '', signatureId: '', baseBody: null });
    setShowCompose(true);
  };

  const sendEmail = async () => {
    if (!composeData.to?.trim()) return toast.error('To address is required');
    if (sendingEmailRef.current || sendingEmail) return;

    sendingEmailRef.current = true;
    setSendingEmail(true);
    const toastId = toast.loading('Sending email in the background...');

    try {
      const formData = new FormData();
      formData.append('to', composeData.to.trim());
      if (composeData.cc?.trim()) formData.append('cc', composeData.cc.trim());
      if (composeData.bcc?.trim()) formData.append('bcc', composeData.bcc.trim());
      formData.append('subject', composeData.subject || '');
      formData.append('body', composeData.body || '');

      if (templateSelection.templateId) {
        formData.append('template_id', templateSelection.templateId);
      }
      if (templateSelection.signatureId) {
        formData.append('signature_id', templateSelection.signatureId);
      }
      formData.append('body_edited', String(!templateSelection.templateId || composeData.body !== templateSelection.baseBody));

      attachments.forEach(file => {
        formData.append('attachments', file);
      });

      await api.post('/auth/mail-account/send-email/', formData);
      toast.dismiss(toastId);
      toast.success('Email sent successfully');
      setShowCompose(false);
      setAttachments([]);
      setComposeData({ to: '', cc: '', bcc: '', subject: '', body: '' });
      setTemplateSelection({ templateId: '', signatureId: '', baseBody: null });
    } catch (err) {
      toast.dismiss(toastId);
      const errMsg = err?.response?.data?.error || 'Failed to send email';
      toast.error(errMsg);
    } finally {
      sendingEmailRef.current = false;
      setSendingEmail(false);
    }
  };

  // Derived: user's mail account ID comes from user.profile via /auth/me/
  // The backend resolves mail account from user.profile.mail_account_id
  // We use user.id as the user-scope key for the cache
  const userId = user?.id;
  // mailAccountId is used as part of the cache key; we don't have it directly
  // on the Redux user object, but we use a stable placeholder since all
  // IMAP calls are scoped by the authenticated session on the backend.
  // If the user has multiple accounts in future, extend this.
  const mailAccountId = user?.mail_account_id || 'default';

  // ─── Folder fetch ─────────────────────────────────────────────────────────

  /**
   * Load messages for a folder.
   * Normal path: IndexedDB cache → render immediately, no backend call.
   * Cache-miss path: backend fetch → store in IndexedDB → render.
   */
  const loadFolder = useCallback(async (folder, bypassCache = false) => {
    dispatch(setInboxLoading(true));
    dispatch(setSyncError(null));

    // Step 1: Try IndexedDB cache
    if (!bypassCache && userId) {
      const cached = await getMailboxMessages(userId, mailAccountId, folder);
      if (cached && cached.length > 0) {
        dispatch(setEmails(cached));
        dispatch(setInboxLoading(false));
        return; // Cache hit — no backend call
      }
    }

    // Step 2: Cache miss — fetch from backend
    try {
      const res = await api.get(
        `/auth/mail-account/fetch-emails/?folder=${encodeURIComponent(folder)}&limit=20`
      );
      const { messages = [], uidvalidity = null } = res.data;

      if (userId) {
        // Compute highest UID from fetched messages
        const highestUid = messages.reduce((max, m) => {
          const uid = parseInt(m.uid, 10);
          return uid > max ? uid : max;
        }, 0);

        await setMailboxMessages(userId, mailAccountId, folder, messages, uidvalidity);
        if (uidvalidity !== null) {
          await setMailboxState(userId, mailAccountId, folder, uidvalidity, highestUid);
        }
      }

      dispatch(setEmails(messages));
    } catch (err) {
      const message = err.response?.data?.error || 'Failed to fetch emails.';
      toast.error(message);
      dispatch(setSyncError(message));
      dispatch(setEmails([]));
    } finally {
      dispatch(setInboxLoading(false));
    }
  }, [userId, mailAccountId, dispatch]);

  // ─── Load on folder change ────────────────────────────────────────────────

  useEffect(() => {
    setSelectedEmail(null);
    setEmailBodyState({ html_body: '', text_body: '', attachments: [] });
    loadFolder(activeFolder);
  }, [activeFolder]); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Folder switch ────────────────────────────────────────────────────────

  const handleFolderSwitch = (folderId) => {
    if (folderId === activeFolder) return;
    dispatch(setActiveFolder(folderId));
    setSelectedEmail(null);
    setEmailBodyState({ html_body: '', text_body: '', attachments: [] });
  };

  // ─── Explicit Sync (bypass cache) ────────────────────────────────────────

  const handleRefresh = () => {
    setSelectedEmail(null);
    setEmailBodyState({ html_body: '', text_body: '', attachments: [] });
    loadFolder(activeFolder, true /* bypassCache */);
  };

  // ─── Open email (body cache-first) ────────────────────────────────────────

  const openEmail = async (email) => {
    setSelectedEmail(email);
    setEmailBodyState({ html_body: '', text_body: '', attachments: [] });

    const uid = email.uid || email.id;

    // Step 1: Check body cache using stable UID (bypass if body has stale unresolved CID)
    if (userId && uid) {
      const cached = await getEmailBody(userId, mailAccountId, activeFolder, uid);
      if (cached && !cached.html_body?.includes('cid:')) {
        setEmailBodyState(cached);
        if (cached.tracking) {
          setSelectedEmail(prev => prev ? { ...prev, tracking: cached.tracking } : prev);
        }
        return; // Cache hit — no backend call
      }
    }

    // Step 2: Cache miss — fetch body from backend
    setBodyLoading(true);
    try {
      const res = await api.get(
        `/auth/mail-account/fetch-email-body/?folder=${encodeURIComponent(activeFolder)}&uid=${encodeURIComponent(uid)}`
      );
      const body = res.data;

      if (userId && uid) {
        await setEmailBody(userId, mailAccountId, activeFolder, uid, body);
      }

      setEmailBodyState(body);
      if (body?.tracking) {
        setSelectedEmail(prev => prev ? { ...prev, tracking: body.tracking } : prev);
      }
    } catch (err) {
      toast.error('Failed to load email body.');
    } finally {
      setBodyLoading(false);
    }
  };

  // ─── UIDVALIDITY change handler ───────────────────────────────────────────

  const handleUidvalidityChange = useCallback(async (folder) => {
    if (!userId) return;
    await resetMailboxCache(userId, mailAccountId, folder);
    // Rebuild from backend
    await loadFolder(folder, true);
  }, [userId, mailAccountId, loadFolder]);

  // ─── Download attachment via Blob ────────────────────────────────────────

  const handleDownloadAttachment = (att) => {
    try {
      if (!att.data) return;
      const byteCharacters = atob(att.data);
      const byteNumbers = new Array(byteCharacters.length);
      for (let i = 0; i < byteCharacters.length; i++) {
        byteNumbers[i] = byteCharacters.charCodeAt(i);
      }
      const byteArray = new Uint8Array(byteNumbers);
      const blob = new Blob([byteArray], { type: att.content_type || 'application/octet-stream' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = att.filename || 'attachment';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setTimeout(() => URL.revokeObjectURL(url), 2000);
    } catch (err) {
      console.error('Download attachment failed:', err);
      // Fallback
      window.open(`data:${att.content_type || 'application/octet-stream'};base64,${att.data}`, '_blank');
    }
  };

  // ─── Email Tracking Analytics ─────────────────────────────────────────────

  const formatTrackingDateTime = (dtStr) => {
    if (!dtStr) return '—';
    try {
      const d = new Date(dtStr);
      return d.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
      });
    } catch {
      return dtStr;
    }
  };

  const handleOpenTrackingModal = async () => {
    const currentTracking = emailBody.tracking || selectedEmail?.tracking;
    setShowTrackingModal(true);
    setTrackingModalData(currentTracking || null);

    const trackingId = currentTracking?.id;
    const trackingToken = currentTracking?.tracking_token;
    const messageId = selectedEmail?.message_id;

    if (trackingId) {
      setIsRefreshingTracking(true);
      try {
        const res = await api.get(`/outreach/emails/${trackingId}/tracking-stats/`);
        setTrackingModalData(res.data);
        setSelectedEmail(prev => prev ? { ...prev, tracking: res.data } : prev);
      } catch (err) {
        console.error('Failed to load tracking stats by ID', err);
      } finally {
        setIsRefreshingTracking(false);
      }
    } else if (trackingToken || messageId) {
      setIsRefreshingTracking(true);
      try {
        const query = trackingToken 
          ? `token=${encodeURIComponent(trackingToken)}` 
          : `message_id=${encodeURIComponent(messageId)}`;
        const res = await api.get(`/outreach/emails/by-token/?${query}`);
        setTrackingModalData(res.data);
        setSelectedEmail(prev => prev ? { ...prev, tracking: res.data } : prev);
      } catch (err) {
        console.error('Failed to load tracking stats by token/messageId', err);
      } finally {
        setIsRefreshingTracking(false);
      }
    }
  };

  const handleRefreshTracking = async () => {
    const currentTracking = trackingModalData || emailBody.tracking || selectedEmail?.tracking;
    const trackingId = currentTracking?.id;
    const trackingToken = currentTracking?.tracking_token;
    const messageId = selectedEmail?.message_id;

    setIsRefreshingTracking(true);
    try {
      let freshData = null;
      if (trackingId) {
        const res = await api.get(`/outreach/emails/${trackingId}/tracking-stats/`);
        freshData = res.data;
      } else if (trackingToken || messageId) {
        const query = trackingToken 
          ? `token=${encodeURIComponent(trackingToken)}` 
          : `message_id=${encodeURIComponent(messageId)}`;
        const res = await api.get(`/outreach/emails/by-token/?${query}`);
        freshData = res.data;
      }
      
      if (freshData) {
        setTrackingModalData(freshData);
        setSelectedEmail(prev => prev ? { ...prev, tracking: freshData } : prev);
        toast.success('Tracking stats refreshed!');
      } else {
        toast.info('No tracking identifier available for this email.');
      }
    } catch (err) {
      console.error('Failed to refresh tracking', err);
      toast.error('Could not refresh tracking stats');
    } finally {
      setIsRefreshingTracking(false);
    }
  };

  const handleSimulateOpen = async () => {
    const currentTracking = trackingModalData || emailBody.tracking || selectedEmail?.tracking;
    const trackingId = currentTracking?.id;
    if (!trackingId) {
      toast.error('No tracking ID available to simulate open.');
      return;
    }
    setIsSimulatingOpen(true);
    try {
      const res = await api.post(`/outreach/emails/${trackingId}/simulate-open/`);
      if (res.data?.data) {
        setTrackingModalData(res.data.data);
        setSelectedEmail(prev => prev ? { ...prev, tracking: res.data.data } : prev);
      }
      toast.success('Test open ping recorded!');
    } catch (err) {
      console.error('Failed to simulate open', err);
      toast.error('Could not record test open');
    } finally {
      setIsSimulatingOpen(false);
    }
  };

  // ─── Body renderer ────────────────────────────────────────────────────────

  const renderBody = () => {
    if (bodyLoading) {
      return (
        <div className="flex items-center justify-center h-full text-slate-400 gap-2">
          <Loader2 className="w-5 h-5 animate-spin" /> Loading email...
        </div>
      );
    }
    if (emailBody.html_body) {
      const sanitizedHtml = (emailBody.html_body || '').replace(/<img[^>]*?email-tracking[^>]*?>/gi, '');
      const respStyle = '<style>img { max-width: 100% !important; height: auto !important; } body { overflow-x: auto; margin: 0; padding: 12px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }</style>';
      const formattedDoc = sanitizedHtml.includes('<head>')
        ? sanitizedHtml.replace('<head>', `<head>${respStyle}`)
        : `${respStyle}${sanitizedHtml}`;
      return (
        <iframe
          srcDoc={formattedDoc}
          sandbox="allow-same-origin allow-popups"
          style={{ width: '100%', height: '100%', border: 'none', background: 'white' }}
          title="Email Content"
        />
      );
    }
    if (emailBody.text_body) {
      return (
        <div className="p-6 overflow-y-auto h-full flex-1 whitespace-pre-wrap text-sm text-slate-800 leading-relaxed">
          {emailBody.text_body}
        </div>
      );
    }
    return (
      <div className="flex items-center justify-center h-full text-slate-400 text-sm italic">
        (Empty Body)
      </div>
    );
  };

  const displayEmails = emails.filter(e => {
    if (searchQuery) {
      if (!e.prospect_company_name) return false;
      return e.prospect_company_name.toLowerCase().includes(searchQuery.toLowerCase());
    }
    return true;
  });

  return (
    <div className="space-y-6 flex flex-col h-[calc(100vh-64px)] overflow-hidden">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 shrink-0">
        <div>
          <h1 className="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-xl bg-sky-600 text-white flex items-center justify-center shadow-md">
              <Mail className="w-5 h-5" />
            </div>
            Mail Inbox
          </h1>
          <p className="text-slate-500 text-sm mt-1 font-medium">View emails from your configured mail account.</p>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={handleCompose} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-sm rounded-xl transition flex items-center gap-2 shadow-sm">
            <Edit3 className="w-4 h-4" /> Compose
          </button>
          <button onClick={handleRefresh} disabled={loading} className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold text-sm rounded-xl transition flex items-center gap-2 border border-slate-200 disabled:opacity-50">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} /> Sync
          </button>
        </div>
      </div>

      <div className="flex-1 min-h-0 bg-white border border-slate-200 rounded-2xl shadow-sm flex overflow-hidden">
        {/* Sidebar */}
        <div className="w-56 border-r border-slate-200 bg-slate-50 flex flex-col shrink-0">
          <div className="p-4 border-b border-slate-200">
            <h2 className="text-xs font-black text-slate-400 uppercase tracking-wider">Folders</h2>
          </div>
          <nav className="flex-1 overflow-y-auto p-2 space-y-1">
            {FOLDERS.map((f) => {
              const Icon = f.icon;
              return (
                <button
                  key={f.id}
                  onClick={() => handleFolderSwitch(f.id)}
                  className={`w-full flex items-center gap-3 px-3 py-2 text-sm font-bold rounded-xl transition ${activeFolder === f.id ? 'bg-sky-100 text-sky-700' : 'text-slate-600 hover:bg-slate-100'}`}
                >
                  <Icon className="w-4 h-4" />
                  {f.label}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Content */}
        <div className="flex-1 flex min-w-0 bg-white overflow-hidden">
          {/* Email list */}
          <div className={`flex flex-col border-r border-slate-100 overflow-y-auto transition-all ${selectedEmail ? 'w-72 shrink-0' : 'flex-1'}`}>
            <div className="p-3 border-b border-slate-100 sticky top-0 bg-white z-10 shrink-0">
              <input 
                type="text" 
                placeholder="Search by company..." 
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 text-slate-800 placeholder-slate-400 rounded-xl px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 focus:border-indigo-500 font-medium transition-all"
              />
            </div>
            {loading ? (
              <div className="flex items-center justify-center h-full text-slate-400 gap-2 font-medium">
                <Loader2 className="w-5 h-5 animate-spin" /> Loading emails...
              </div>
            ) : displayEmails.length === 0 ? (
              <div className="flex items-center justify-center h-full text-slate-400 font-medium">No emails found in this folder.</div>
            ) : (
              <ul className="divide-y divide-slate-100">
                {displayEmails.map((email) => (
                  <li
                    key={email.uid || email.id}
                    onClick={() => openEmail(email)}
                    className={`p-4 cursor-pointer transition ${selectedEmail?.uid === email.uid ? 'bg-sky-50 border-l-2 border-sky-500' : 'hover:bg-slate-50'}`}
                  >
                    <div className="flex items-baseline justify-between gap-2 mb-0.5">
                      <span className={`text-xs truncate flex-1 ${email.is_unread ? 'font-bold text-slate-900' : 'font-medium text-slate-600'}`}>
                        {email.prospect_company_name ? (
                          <span className="inline-flex items-center gap-1 text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200 text-[10px] uppercase font-bold tracking-wider mr-1.5">
                            <Building2 className="w-3 h-3" /> {email.prospect_company_name}
                          </span>
                        ) : null}
                        {activeFolder.includes('Sent') 
                          ? `To: ${email.to?.replace(/<.*>/, '').trim() || email.to}` 
                          : email.from?.replace(/<.*>/, '').trim() || email.from}
                      </span>
                      <div className="flex items-center gap-1.5 shrink-0">
                        {email.tracking && (
                          <span 
                            className={`px-1.5 py-0.2 rounded text-[9px] font-extrabold uppercase border flex items-center gap-1 ${
                              email.tracking.is_opened 
                                ? 'bg-emerald-50 text-emerald-700 border-emerald-300' 
                                : 'bg-amber-50 text-amber-700 border-amber-300'
                            }`}
                            title={email.tracking.is_opened ? `Opened ${email.tracking.open_count || 1}x` : 'Awaiting open'}
                          >
                            <span className={`w-1 h-1 rounded-full ${email.tracking.is_opened ? 'bg-emerald-500' : 'bg-amber-500'}`} />
                            {email.tracking.is_opened ? `${email.tracking.open_count || 1}x` : 'Sent'}
                          </span>
                        )}
                        <span className="text-[10px] text-slate-400 font-medium">{email.date?.split(' ').slice(1, 4).join(' ')}</span>
                      </div>
                    </div>
                    <h4 className={`text-xs truncate ${email.is_unread ? 'font-bold text-slate-800' : 'font-semibold text-slate-600'}`}>
                      {email.subject || '(No Subject)'}
                    </h4>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Email body panel */}
          {selectedEmail && (
            <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
              <div className="p-4 border-b border-slate-100 flex items-start gap-3 shrink-0 bg-white">
                <button
                  onClick={() => { setSelectedEmail(null); setEmailBodyState({ html_body: '', text_body: '' }); }}
                  className="p-1.5 hover:bg-slate-100 rounded-full transition text-slate-500 mt-0.5 shrink-0"
                >
                  <ChevronLeft className="w-5 h-5" />
                </button>
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h2 className="text-base font-bold text-slate-900 leading-tight">{selectedEmail.subject || '(No Subject)'}</h2>
                        {(selectedEmail.tracking || emailBody.tracking) && (
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-extrabold uppercase border flex items-center gap-1 shrink-0 ${
                            (emailBody.tracking || selectedEmail.tracking)?.is_opened
                              ? 'bg-emerald-50 text-emerald-700 border-emerald-300'
                              : 'bg-amber-50 text-amber-700 border-amber-300'
                          }`}>
                            <span className={`w-1.5 h-1.5 rounded-full ${(emailBody.tracking || selectedEmail.tracking)?.is_opened ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'}`} />
                            {(emailBody.tracking || selectedEmail.tracking)?.is_opened 
                              ? `Viewed (${(emailBody.tracking || selectedEmail.tracking)?.open_count || 1}x)` 
                              : 'Not Viewed'}
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-1 text-xs text-slate-500 flex-wrap">
                        <span>From: <span className="font-semibold text-slate-700">{selectedEmail.from}</span></span>
                        {selectedEmail.to && (
                          <>
                            <span className="text-slate-300">·</span>
                            <span>To: <span className="font-semibold text-slate-700">{selectedEmail.to}</span></span>
                          </>
                        )}
                        <span className="text-slate-300">·</span>
                        <span>{selectedEmail.date}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {(activeFolder.includes('Sent') || selectedEmail.tracking || emailBody.tracking) && (
                        <button
                          type="button"
                          onClick={() => handleOpenTrackingModal()}
                          className="px-3 py-1.5 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-extrabold text-xs rounded-xl transition flex items-center gap-1.5 border border-indigo-400/40 shadow-sm cursor-pointer"
                          title="Open email tracking & engagement analytics"
                        >
                          <BarChart2 className="w-3.5 h-3.5 text-indigo-200" />
                          <span>Email Track</span>
                        </button>
                      )}
                      <button onClick={handleReply} className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold rounded-xl transition flex items-center gap-1.5 border border-slate-200 shrink-0">
                        <Reply className="w-3.5 h-3.5" /> Reply
                      </button>
                    </div>
                  </div>
                </div>
              </div>
              <div className="flex-1 overflow-hidden flex flex-col">
                {emailBody.attachments && emailBody.attachments.length > 0 && (
                  <div className="p-4 border-b border-slate-100 bg-slate-50/50 flex flex-wrap gap-2 shrink-0">
                    <span className="text-xs font-bold text-slate-500 w-full mb-1">Attachments ({emailBody.attachments.length})</span>
                    {emailBody.attachments.map((att, idx) => (
                      <button
                        type="button"
                        key={idx}
                        onClick={() => handleDownloadAttachment(att)}
                        className="flex items-center gap-2 px-3 py-1.5 bg-white border border-slate-200 rounded-xl shadow-sm hover:border-sky-300 hover:text-sky-700 transition text-xs font-semibold text-slate-700 cursor-pointer"
                        title={`Download ${att.filename}`}
                      >
                        <Paperclip className="w-3.5 h-3.5 text-slate-400" />
                        <span className="truncate max-w-[200px]">{att.filename}</span>
                        <span className="text-[10px] text-slate-400">({Math.max(1, Math.round((att.size || 0) / 1024))} KB)</span>
                        <Download className="w-3.5 h-3.5 text-slate-400 hover:text-sky-600 ml-0.5" />
                      </button>
                    ))}
                  </div>
                )}
                <div className="flex-1 overflow-hidden">
                  {renderBody()}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {showCompose && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-3 sm:p-5 z-50">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[92vh] overflow-hidden border border-slate-200 flex flex-col">
            {/* Modal Header */}
            <div className="bg-gradient-to-r from-blue-600 via-indigo-600 to-sky-700 p-4 text-white flex items-center justify-between shrink-0 shadow-sm">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-white/15 flex items-center justify-center shadow-xs">
                  <Mail className="w-4 h-4 text-white" />
                </div>
                <div>
                  <h3 className="font-extrabold text-base tracking-tight leading-snug">Compose Email</h3>
                  {senderMailStatus && (
                    <p className="text-[11px] text-blue-100/90 font-medium">
                      From: <span className="font-semibold text-white">{senderMailStatus.display_name || senderMailStatus.email_address}</span> ({senderMailStatus.email_address})
                    </p>
                  )}
                </div>
              </div>
              <button 
                type="button"
                onClick={() => setShowCompose(false)} 
                className="text-white/80 hover:text-white p-1 rounded-lg hover:bg-white/10 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Scrollable Body */}
            <div className="p-4 sm:p-5 flex-1 overflow-y-auto space-y-3.5 text-xs">
              {/* Recipient Fields */}
              <div className="space-y-2 bg-slate-50/80 p-3 rounded-xl border border-slate-200/80">
                {/* To Field */}
                <div className="flex items-center gap-2">
                  <label className="text-[11px] font-bold uppercase tracking-wider text-slate-500 w-12 shrink-0">To:</label>
                  <input 
                    type="text" 
                    value={composeData.to} 
                    onChange={(e) => setComposeData(prev => ({ ...prev, to: e.target.value }))}
                    disabled={sendingEmail}
                    className="flex-1 p-2 bg-white border border-slate-200 rounded-lg text-xs font-semibold text-slate-900 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100" 
                    placeholder="recipient@example.com (comma-separated for multiple)"
                  />
                  <div className="flex items-center gap-1.5 shrink-0 text-[11px] font-bold">
                    {!showCc && (
                      <button
                        type="button"
                        onClick={() => setShowCc(true)}
                        className="px-2 py-1 text-slate-500 hover:text-indigo-600 hover:bg-white rounded-md transition"
                      >
                        Cc
                      </button>
                    )}
                    {!showBcc && (
                      <button
                        type="button"
                        onClick={() => setShowBcc(true)}
                        className="px-2 py-1 text-slate-500 hover:text-indigo-600 hover:bg-white rounded-md transition"
                      >
                        Bcc
                      </button>
                    )}
                  </div>
                </div>

                {/* Cc Field */}
                {showCc && (
                  <div className="flex items-center gap-2">
                    <label className="text-[11px] font-bold uppercase tracking-wider text-blue-600 w-12 shrink-0">Cc:</label>
                    <input 
                      type="text" 
                      value={composeData.cc || ''} 
                      onChange={(e) => setComposeData(prev => ({ ...prev, cc: e.target.value }))}
                      disabled={sendingEmail}
                      className="flex-1 p-2 bg-white border border-slate-200 rounded-lg text-xs font-semibold text-slate-900 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100" 
                      placeholder="cc_recipient@example.com"
                    />
                    <button
                      type="button"
                      onClick={() => { setShowCc(false); setComposeData(prev => ({ ...prev, cc: '' })); }}
                      className="text-slate-400 hover:text-slate-600 p-1 rounded"
                      title="Remove Cc"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )}

                {/* Bcc Field */}
                {showBcc && (
                  <div className="flex items-center gap-2">
                    <label className="text-[11px] font-bold uppercase tracking-wider text-purple-600 w-12 shrink-0">Bcc:</label>
                    <input 
                      type="text" 
                      value={composeData.bcc || ''} 
                      onChange={(e) => setComposeData(prev => ({ ...prev, bcc: e.target.value }))}
                      disabled={sendingEmail}
                      className="flex-1 p-2 bg-white border border-slate-200 rounded-lg text-xs font-semibold text-slate-900 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100" 
                      placeholder="bcc_recipient@example.com"
                    />
                    <button
                      type="button"
                      onClick={() => { setShowBcc(false); setComposeData(prev => ({ ...prev, bcc: '' })); }}
                      className="text-slate-400 hover:text-slate-600 p-1 rounded"
                      title="Remove Bcc"
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                )}
              </div>

              {/* Saved Templates & Signatures Selector */}
              <TemplatePicker
                prospect={null}
                toEmails={composeData.to ? composeData.to.split(/[,;\s]+/).filter(Boolean) : []}
                ccEmails={composeData.cc ? composeData.cc.split(/[,;\s]+/).filter(Boolean) : []}
                emailSubject={composeData.subject}
                emailBody={composeData.body}
                setEmailSubject={(val) => setComposeData(prev => ({ ...prev, subject: val }))}
                setEmailBody={(val) => setComposeData(prev => ({ ...prev, body: val }))}
                selection={templateSelection}
                setSelection={setTemplateSelection}
                disabled={sendingEmail}
              />

              {/* Subject Field */}
              <div>
                <label className="block text-[10px] font-extrabold uppercase tracking-wider text-slate-600 mb-1">Subject</label>
                <input 
                  type="text" 
                  value={composeData.subject} 
                  onChange={(e) => setComposeData(prev => ({ ...prev, subject: e.target.value }))}
                  disabled={sendingEmail}
                  className="w-full p-2.5 bg-white border border-slate-200 rounded-xl text-xs font-bold text-slate-900 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100" 
                  placeholder="Enter subject"
                />
              </div>

              {/* Message Content */}
              <div>
                <label className="block text-[10px] font-extrabold uppercase tracking-wider text-slate-600 mb-1">Message Content</label>
                <textarea 
                  rows={8}
                  value={composeData.body}
                  onChange={(e) => setComposeData(prev => ({ ...prev, body: e.target.value }))}
                  disabled={sendingEmail}
                  className={`w-full p-3 bg-white border border-slate-200 text-xs font-medium text-slate-800 leading-relaxed focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 ${
                    senderMailStatus?.default_signature && !templateSelection.signatureId ? 'rounded-t-xl' : 'rounded-xl'
                  }`}
                  placeholder="Write your email here..."
                />
                {senderMailStatus?.default_signature && !templateSelection.signatureId && (
                  <div className="w-full p-3 bg-slate-50 border border-t-0 border-slate-200 rounded-b-xl text-xs text-slate-500 whitespace-pre-wrap">
                    {senderMailStatus.default_signature}
                  </div>
                )}
              </div>

              {/* Attachments Section */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-[10px] font-extrabold uppercase tracking-wider text-slate-600">Attachments</label>
                  <span className="text-[10px] text-slate-400">Max 10MB per file, 25MB total</span>
                </div>
                <div className="p-3 bg-white border border-slate-200 rounded-xl space-y-2">
                  <input 
                    type="file" 
                    multiple 
                    ref={fileInputRef}
                    onChange={handleFileChange} 
                    disabled={sendingEmail}
                    className="text-xs text-slate-700 file:mr-2 file:py-1 file:px-2.5 file:rounded-lg file:border-0 file:text-xs file:font-bold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 cursor-pointer disabled:opacity-50"
                  />
                  {attachmentError && (
                    <div className="text-red-600 text-[10px] font-bold">{attachmentError}</div>
                  )}
                  {attachments.length > 0 && (
                    <div className="flex flex-wrap gap-2 pt-1">
                      {attachments.map((file, i) => (
                        <div key={i} className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-100 rounded-lg border border-slate-200 text-[11px] font-semibold text-slate-700">
                          <Paperclip className="w-3 h-3 text-slate-400" />
                          <span className="truncate max-w-[160px]">{file.name}</span>
                          <span className="text-slate-400">({(file.size / 1024 / 1024).toFixed(1)}MB)</span>
                          <button 
                            type="button" 
                            onClick={() => removeAttachment(i)} 
                            className="text-red-500 hover:text-red-700 font-bold ml-1 text-sm leading-none"
                            title="Remove attachment"
                          >
                            ×
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div className="bg-slate-50 px-5 py-3 border-t border-slate-200 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={sendingEmail}
                  className="px-3 py-1.5 bg-white hover:bg-slate-100 border border-slate-200 text-slate-700 font-bold text-xs rounded-xl transition flex items-center gap-1.5 shadow-2xs"
                >
                  <Paperclip className="w-3.5 h-3.5 text-indigo-600" />
                  <span>Attach</span>
                  {attachments.length > 0 && (
                    <span className="px-1.5 py-0.2 rounded-full bg-indigo-100 text-indigo-700 text-[10px] font-extrabold">
                      {attachments.length}
                    </span>
                  )}
                </button>
              </div>
              <div className="flex items-center gap-2.5">
                <button 
                  type="button"
                  onClick={() => setShowCompose(false)} 
                  disabled={sendingEmail}
                  className="px-4 py-2 bg-white border border-slate-200 text-slate-700 font-bold text-xs rounded-xl hover:bg-slate-100 transition"
                >
                  Cancel
                </button>
                <button 
                  type="button"
                  onClick={sendEmail} 
                  disabled={sendingEmail || !composeData.to?.trim()} 
                  className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 disabled:cursor-not-allowed text-white font-extrabold text-xs rounded-xl shadow-xs transition flex items-center gap-2"
                >
                  {sendingEmail ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                  <span>{sendingEmail ? 'Sending...' : 'Send'}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Email Tracking Modal Pop-up */}
      {showTrackingModal && (
        <div className="fixed inset-0 bg-slate-950/70 backdrop-blur-xs z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl shadow-2xl max-w-2xl w-full max-h-[92vh] flex flex-col overflow-hidden border border-slate-200 animate-in fade-in zoom-in-95 duration-200">
            {/* Modal Header */}
            <div className="bg-gradient-to-r from-slate-950 via-indigo-950 to-slate-900 p-5 text-white flex items-center justify-between border-b border-indigo-900/50">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-2xl bg-indigo-500/20 text-indigo-300 border border-indigo-400/30 flex items-center justify-center font-bold shadow-inner">
                  <BarChart2 className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-extrabold tracking-tight text-white">Email Tracking & Engagement Analytics</h3>
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-extrabold uppercase border flex items-center gap-1 ${
                      (trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.is_opened
                        ? 'bg-emerald-500/20 text-emerald-300 border-emerald-400/40'
                        : 'bg-amber-500/20 text-amber-300 border-amber-400/40'
                    }`}>
                      <span className={`w-1.5 h-1.5 rounded-full ${(trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.is_opened ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'}`} />
                      {(trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.is_opened 
                        ? `Viewed (${(trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.open_count || 1}x)` 
                        : 'Awaiting Open'}
                    </span>
                  </div>
                  <p className="text-xs text-slate-300 mt-0.5 truncate max-w-md">
                    {selectedEmail?.to || (trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.to_email || 'Recipient'} &bull; <span className="text-indigo-200 font-semibold">{selectedEmail?.subject || (trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.subject || '(No Subject)'}</span>
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowTrackingModal(false)}
                className="w-8 h-8 rounded-xl bg-white/10 hover:bg-white/20 text-slate-300 hover:text-white flex items-center justify-center transition cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Body - Scrollable */}
            <div className="p-6 space-y-6 overflow-y-auto flex-1 text-slate-700 text-xs">
              {/* 4 KPI Metrics */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {/* Total Opens */}
                <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-2xl flex flex-col justify-between">
                  <div className="flex items-center justify-between text-slate-400">
                    <span className="text-[10px] font-extrabold uppercase tracking-wider">Total Opens</span>
                    <Eye className="w-3.5 h-3.5 text-indigo-600" />
                  </div>
                  <div className="mt-2">
                    <span className="text-2xl font-black text-slate-900 tracking-tight">
                      {(trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.open_count || ((trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.is_opened ? 1 : 0)}
                    </span>
                    <span className="text-[10px] text-slate-400 ml-1">times</span>
                  </div>
                  <span className={`text-[10px] font-bold mt-1 ${
                    ((trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.open_count || 0) > 1 
                      ? 'text-indigo-600' 
                      : (trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.is_opened 
                      ? 'text-emerald-600' 
                      : 'text-slate-400'
                  }`}>
                    {((trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.open_count || 0) > 2 
                      ? '🔥 Highly Engaged' 
                      : (trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.is_opened 
                      ? 'Opened & Seen' 
                      : 'Not opened yet'}
                  </span>
                </div>

                {/* Time Spent */}
                <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-2xl flex flex-col justify-between">
                  <div className="flex items-center justify-between text-slate-400">
                    <span className="text-[10px] font-extrabold uppercase tracking-wider">Time Spent</span>
                    <Clock className="w-3.5 h-3.5 text-violet-600" />
                  </div>
                  <div className="mt-2">
                    <span className="text-2xl font-black text-slate-900 tracking-tight">
                      {(trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.estimated_read_time_formatted || 
                       ((trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.total_seconds_spent ? `${(trackingModalData || emailBody.tracking || selectedEmail?.tracking).total_seconds_spent}s` : '0s')}
                    </span>
                  </div>
                  <span className="text-[10px] font-bold text-violet-600 mt-1">
                    {(trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.reading_engagement || 
                     ((trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.is_opened ? 'Read in Detail' : 'No Reading Time')}
                  </span>
                </div>

                {/* First Opened */}
                <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-2xl flex flex-col justify-between">
                  <div className="flex items-center justify-between text-slate-400">
                    <span className="text-[10px] font-extrabold uppercase tracking-wider">First Opened</span>
                    <TrendingUp className="w-3.5 h-3.5 text-emerald-600" />
                  </div>
                  <div className="mt-2">
                    <span className="text-xs font-bold text-slate-900 line-clamp-2">
                      {formatTrackingDateTime(
                        (trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.first_opened_at || 
                        (trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.opened_at
                      )}
                    </span>
                  </div>
                  <span className="text-[10px] text-slate-400 mt-1">Initial Read</span>
                </div>

                {/* Last Opened */}
                <div className="p-3.5 bg-slate-50 border border-slate-200 rounded-2xl flex flex-col justify-between">
                  <div className="flex items-center justify-between text-slate-400">
                    <span className="text-[10px] font-extrabold uppercase tracking-wider">Most Recent</span>
                    <Activity className="w-3.5 h-3.5 text-sky-600" />
                  </div>
                  <div className="mt-2">
                    <span className="text-xs font-bold text-slate-900 line-clamp-2">
                      {formatTrackingDateTime(
                        (trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.last_opened_at || 
                        (trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.opened_at
                      )}
                    </span>
                  </div>
                  <span className="text-[10px] text-slate-400 mt-1">Latest Open</span>
                </div>
              </div>

              {/* Engagement Level Progress Card */}
              <div className="p-4 bg-gradient-to-br from-indigo-50/60 to-slate-50 border border-indigo-100/80 rounded-2xl space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-extrabold text-slate-900 uppercase tracking-wider">Reading & Engagement Level</span>
                  <span className="text-xs font-extrabold text-indigo-700">
                    {(trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.reading_engagement || 
                     ((trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.is_opened ? 'Read in Detail' : 'Unopened')}
                  </span>
                </div>
                {/* Visual meter */}
                <div className="w-full bg-slate-200 rounded-full h-2.5 overflow-hidden flex">
                  <div className={`h-full transition-all duration-500 ${
                    !(trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.is_opened ? 'w-0' :
                    (((trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.open_count >= 3) || (((trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.total_seconds_spent || 0) >= 60)) ? 'w-full bg-gradient-to-r from-indigo-500 to-emerald-500' :
                    (((trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.open_count >= 2) || (((trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.total_seconds_spent || 0) >= 15)) ? 'w-2/3 bg-indigo-600' :
                    'w-1/3 bg-amber-500'
                  }`} />
                </div>
                <div className="flex items-center justify-between text-[10px] text-slate-400 font-semibold pt-0.5">
                  <span>Skimmed (&lt;10s)</span>
                  <span>Read in Detail (10s - 45s)</span>
                  <span>Deeply Engaged (1m+)</span>
                </div>
              </div>

              {/* Detailed Open Event History */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h4 className="text-xs font-extrabold text-slate-900 uppercase tracking-wider flex items-center gap-1.5">
                    <Activity className="w-3.5 h-3.5 text-indigo-600" />
                    Open History & Device Timeline
                  </h4>
                  <span className="text-[11px] text-slate-400">
                    {(trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.open_history?.length || 0} event{((trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.open_history?.length === 1) ? '' : 's'} recorded
                  </span>
                </div>

                {(trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.open_history && (trackingModalData || emailBody.tracking || selectedEmail?.tracking).open_history.length > 0 ? (
                  <div className="divide-y divide-slate-100 border border-slate-200 rounded-2xl overflow-hidden bg-white max-h-48 overflow-y-auto">
                    {[...(trackingModalData || emailBody.tracking || selectedEmail?.tracking).open_history].reverse().map((ev, idx) => (
                      <div key={ev.id || idx} className="p-3 flex items-center justify-between gap-3 hover:bg-slate-50/80 transition text-[11px]">
                        <div className="flex items-center gap-3 min-w-0">
                          <div className="w-7 h-7 rounded-xl bg-indigo-50 border border-indigo-200/60 text-indigo-700 flex items-center justify-center font-extrabold text-xs shrink-0">
                            #{ev.id || (trackingModalData || emailBody.tracking || selectedEmail?.tracking).open_history.length - idx}
                          </div>
                          <div className="min-w-0">
                            <div className="font-extrabold text-slate-800 flex items-center gap-1.5 truncate">
                              <span>{ev.client || 'Mail Client'}</span>
                              <span className="px-1.5 py-0.2 bg-slate-100 text-slate-600 rounded text-[9px] font-semibold border border-slate-200 shrink-0">
                                {ev.device || 'Desktop'}
                              </span>
                            </div>
                            <div className="text-[10px] text-slate-400 flex items-center gap-2 mt-0.5">
                              <span>{formatTrackingDateTime(ev.timestamp)}</span>
                              {ev.ip && <span>&bull; IP: {ev.ip}</span>}
                            </div>
                          </div>
                        </div>
                        <div className="text-right shrink-0">
                          <span className="px-2 py-0.5 bg-emerald-50 text-emerald-700 font-extrabold rounded-md text-[10px] border border-emerald-200/60 block">
                            +{ev.dwell_seconds || 15}s read
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.is_opened ? (
                  <div className="p-4 border border-slate-200 rounded-2xl bg-slate-50 text-center space-y-1">
                    <p className="text-xs font-bold text-slate-700">Email was opened on {formatTrackingDateTime((trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.opened_at || (trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.first_opened_at)}</p>
                    <p className="text-[11px] text-slate-400">Timestamps and device details are recorded for each open.</p>
                  </div>
                ) : (
                  <div className="p-6 border border-dashed border-slate-200 rounded-2xl bg-slate-50/60 text-center space-y-2">
                    <Mail className="w-8 h-8 text-slate-300 mx-auto" />
                    <p className="text-xs font-extrabold text-slate-700">No Open Events Recorded Yet</p>
                    <p className="text-[11px] text-slate-400 max-w-sm mx-auto">
                      When the recipient opens this email, the opening timestamp, device, and reading duration will appear here.
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* Modal Footer */}
            <div className="p-4 bg-slate-50 border-t border-slate-200 flex flex-wrap items-center justify-between gap-2.5">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleSimulateOpen}
                  disabled={isSimulatingOpen || !(trackingModalData?.id || emailBody.tracking?.id || selectedEmail?.tracking?.id)}
                  className="px-3 py-1.5 bg-indigo-50 hover:bg-indigo-100 disabled:opacity-50 text-indigo-700 font-extrabold text-xs rounded-xl border border-indigo-200/80 transition flex items-center gap-1.5 shadow-2xs cursor-pointer"
                  title="Simulate recipient opening the email (test live tracking)"
                >
                  <Zap className={`w-3.5 h-3.5 ${isSimulatingOpen ? 'animate-bounce text-indigo-600' : 'text-indigo-500'}`} />
                  <span>{isSimulatingOpen ? 'Recording...' : '⚡ Test Open Ping'}</span>
                </button>
                <button
                  type="button"
                  onClick={handleRefreshTracking}
                  disabled={isRefreshingTracking}
                  className="px-3 py-1.5 bg-white hover:bg-slate-100 disabled:opacity-50 text-slate-700 font-extrabold text-xs rounded-xl border border-slate-200 transition flex items-center gap-1.5 shadow-2xs cursor-pointer"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isRefreshingTracking ? 'animate-spin text-slate-500' : 'text-slate-400'}`} />
                  <span>{isRefreshingTracking ? 'Refreshing...' : 'Refresh'}</span>
                </button>
              </div>

              <button
                type="button"
                onClick={() => setShowTrackingModal(false)}
                className="px-5 py-1.5 bg-slate-900 hover:bg-slate-800 text-white font-extrabold text-xs rounded-xl transition shadow-sm cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default InboxPage;
