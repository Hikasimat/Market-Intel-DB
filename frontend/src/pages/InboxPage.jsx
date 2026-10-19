import React, { useState, useEffect, useCallback, useRef } from 'react';
import { 
  Mail, Send, AlertTriangle, RefreshCw, ChevronLeft, ChevronRight, Loader2, Paperclip, 
  Building2, Reply, Edit3, X, Download, BarChart2, Eye, Activity, Zap, TrendingUp, Clock,
  Star, FileText, Trash2, MailOpen, ShieldAlert, Undo2, Save, Search,
  Users, User, Sparkles, ExternalLink
} from 'lucide-react';
import { toast } from 'react-toastify';
import { useDispatch, useSelector } from 'react-redux';
import { Link, useNavigate } from 'react-router-dom';
import api from '../services/api';
import TemplatePicker from '../components/lq/TemplatePicker';
import OpenTrackingToggle from '../components/email/OpenTrackingToggle';
import BulkCampaignModal from '../components/email/BulkCampaignModal';
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
import {
  broadcastMailEvent,
  subscribeMailEvents,
  notifyMailSent,
} from '../services/mailSyncService';

const FOLDERS = [
  { id: 'INBOX', label: 'Inbox', icon: Mail },
  { id: 'STARRED', label: 'Starred', icon: Star },
  { id: 'SENT', label: 'Sent', icon: Send },
  { id: 'DRAFT', label: 'Drafts', icon: FileText },
  { id: 'SPAM', label: 'Spam', icon: AlertTriangle },
  { id: 'TRASH', label: 'Trash', icon: Trash2 },
];

const InboxPage = () => {
  const dispatch = useDispatch();
  const { user } = useSelector((state) => state.auth);
  const { emails, loading, activeFolder } = useSelector((state) => state.inbox);

  const [selectedEmail, setSelectedEmail] = useState(null);
  const [bodyLoading, setBodyLoading] = useState(false);
  const [emailBody, setEmailBodyState] = useState({ html_body: '', text_body: '', attachments: [] });

  const [showCompose, setShowCompose] = useState(false);
  const [composeData, setComposeData] = useState({ to: '', cc: '', bcc: '', subject: '', body: '', draft_id: null, thread_id: null });
  const [savingDraft, setSavingDraft] = useState(false);
  const [sendingEmail, setSendingEmail] = useState(false);
  const sendingEmailRef = useRef(false);
  const [templateSelection, setTemplateSelection] = useState({ templateId: '', signatureId: '', baseBody: null });
  const [openTrackingEnabled, setOpenTrackingEnabled] = useState(false);
  const [attachments, setAttachments] = useState([]);
  const [attachmentError, setAttachmentError] = useState('');
  const [showCc, setShowCc] = useState(false);
  const [showBcc, setShowBcc] = useState(false);
  const [senderMailStatus, setSenderMailStatus] = useState(null);
  const [gmailStatus, setGmailStatus] = useState({ is_connected: false, email: '' });
  const [connectingGmail, setConnectingGmail] = useState(false);
  const [disconnectingGmail, setDisconnectingGmail] = useState(false);
  const fileInputRef = useRef(null);

  const [searchQuery, setSearchQuery] = useState('');

  // Bulk Email Campaign & Prospect Responses State
  const [showBulkCampaign, setShowBulkCampaign] = useState(false);
  const [isProspectResponsesView, setIsProspectResponsesView] = useState(false);
  const [prospectEmails, setProspectEmails] = useState([]);
  const [prospectLoading, setProspectLoading] = useState(false);
  const [prospectError, setProspectError] = useState(null);

  // Email Tracking State
  const [showTrackingModal, setShowTrackingModal] = useState(false);
  const [trackingModalData, setTrackingModalData] = useState(null);
  const [isRefreshingTracking, setIsRefreshingTracking] = useState(false);
  const [isSimulatingOpen, setIsSimulatingOpen] = useState(false);

  const fetchGmailStatus = useCallback(async () => {
    try {
      const res = await api.get('/auth/google/gmail/status/');
      setGmailStatus(res.data);
    } catch (err) {
      console.error('Failed to fetch Gmail status', err);
    }
  }, []);

  const fetchMailAccount = useCallback(async () => {
    try {
      const res = await api.get('/auth/mail-account/');
      if (res.data && res.data.length > 0) {
        setSenderMailStatus(res.data[0]);
      }
    } catch (err) {
      console.error('Failed to fetch mail account', err);
    }
  }, []);

  useEffect(() => {
    fetchMailAccount();
    fetchGmailStatus();

    const searchParams = new URLSearchParams(window.location.search);
    if (searchParams.get('gmail_connected')) {
      toast.success('Gmail mailbox connected successfully!');
      window.history.replaceState({}, '', window.location.pathname);
      fetchGmailStatus();
      fetchMailAccount();
    } else if (searchParams.get('gmail_error')) {
      toast.error(`Gmail connection error: ${decodeURIComponent(searchParams.get('gmail_error'))}`);
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, [fetchGmailStatus, fetchMailAccount]);

  const handleConnectGmail = async () => {
    setConnectingGmail(true);
    try {
      const res = await api.get('/auth/google/gmail/url/');
      if (res.data?.url) {
        window.location.href = res.data.url;
      } else {
        toast.error('Failed to retrieve Gmail authorization URL.');
      }
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to start Gmail connection.');
    } finally {
      setConnectingGmail(false);
    }
  };

  const handleDisconnectGmail = async () => {
    if (!window.confirm('Are you sure you want to disconnect your Gmail mailbox?')) return;
    setDisconnectingGmail(true);
    try {
      await api.post('/auth/google/gmail/disconnect/');
      toast.success('Gmail disconnected successfully.');
      setGmailStatus({ is_connected: false, email: '' });
      fetchMailAccount();
      loadFolder(activeFolder, true);
    } catch (err) {
      toast.error('Failed to disconnect Gmail.');
    } finally {
      setDisconnectingGmail(false);
    }
  };

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
    setComposeData({ to: '', cc: '', bcc: '', subject: '', body: '', draft_id: null, thread_id: null });
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
      body: `\n\n\n--- Original Message ---\nFrom: ${selectedEmail.from}\nDate: ${selectedEmail.date}\nSubject: ${selectedEmail.subject}\n`,
      draft_id: null,
      thread_id: selectedEmail.thread_id || selectedEmail.uid || selectedEmail.id,
    });
    setAttachments([]);
    setAttachmentError('');
    setShowCc(false);
    setShowBcc(false);
    setTemplateSelection({ templateId: '', signatureId: '', baseBody: null });
    setShowCompose(true);
  };

  const handleOpenDraft = async (email) => {
    let html = '';
    let text = '';
    try {
      const res = await api.get(`/auth/mail-account/fetch-email-body/?folder=DRAFT&uid=${encodeURIComponent(email.uid || email.id)}`);
      html = res.data?.html_body || '';
      text = res.data?.text_body || '';
    } catch (e) {
      // ignore
    }
    const cleanBody = text || html.replace(/<[^>]*>/g, '').trim();
    setComposeData({
      to: email.to?.replace(/<.*>/, '').trim() || email.to || '',
      cc: '',
      bcc: '',
      subject: email.subject || '',
      body: cleanBody,
      draft_id: email.uid || email.id,
      thread_id: email.thread_id || null,
    });
    setAttachments([]);
    setAttachmentError('');
    setShowCc(false);
    setShowBcc(false);
    setTemplateSelection({ templateId: '', signatureId: '', baseBody: null });
    setShowCompose(true);
  };

  const handleSaveDraft = async () => {
    setSavingDraft(true);
    const toastId = toast.loading('Saving draft to Gmail...');
    try {
      const res = await api.post('/auth/mail-account/save-draft/', {
        to: composeData.to?.trim() || '',
        cc: composeData.cc?.trim() || '',
        bcc: composeData.bcc?.trim() || '',
        subject: composeData.subject || '',
        body: composeData.body || '',
        draft_id: composeData.draft_id,
        thread_id: composeData.thread_id,
      });
      toast.dismiss(toastId);
      const newDraftId = res.data?.draft?.id || composeData.draft_id;
      setComposeData(prev => ({ ...prev, draft_id: newDraftId }));
      toast.success('Draft saved successfully');
      broadcastMailEvent('DRAFT_SAVED', { folder: 'DRAFT' });
      if (activeFolder === 'DRAFT') {
        loadFolder('DRAFT', true);
      }
    } catch (err) {
      toast.dismiss(toastId);
      toast.error(err.response?.data?.error || 'Failed to save draft');
    } finally {
      setSavingDraft(false);
    }
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
      if (composeData.draft_id) formData.append('draft_id', composeData.draft_id);
      if (composeData.thread_id) formData.append('thread_id', composeData.thread_id);

      if (templateSelection.templateId) {
        formData.append('template_id', templateSelection.templateId);
      }
      if (templateSelection.signatureId) {
        formData.append('signature_id', templateSelection.signatureId);
      }
      formData.append('body_edited', String(!templateSelection.templateId || composeData.body !== templateSelection.baseBody));

      formData.append('open_tracking_enabled', String(openTrackingEnabled));

      attachments.forEach(file => {
        formData.append('attachments', file);
      });

      await api.post('/auth/mail-account/send-email/', formData);
      toast.dismiss(toastId);
      toast.success('Email sent successfully');
      setShowCompose(false);
      setAttachments([]);
      setOpenTrackingEnabled(false);
      setComposeData({ to: '', cc: '', bcc: '', subject: '', body: '', draft_id: null, thread_id: null });
      setTemplateSelection({ templateId: '', signatureId: '', baseBody: null });

      await notifyMailSent(userId, mailAccountId);
      if (activeFolder === 'DRAFT' || activeFolder === 'SENT') {
        loadFolder(activeFolder, true);
      }
    } catch (err) {
      toast.dismiss(toastId);
      const errMsg = err?.response?.data?.error || 'Failed to send email';
      toast.error(errMsg);
    } finally {
      sendingEmailRef.current = false;
      setSendingEmail(false);
    }
  };

  const handleToggleStar = async (e, email) => {
    if (e) e.stopPropagation();
    const newStarred = !email.is_starred;
    const action = newStarred ? 'star' : 'unstar';
    
    // Optimistic update
    const updated = emails.map(m => (m.uid === email.uid || m.id === email.id) ? { ...m, is_starred: newStarred } : m);
    dispatch(setEmails(updated));
    if (selectedEmail && (selectedEmail.uid === email.uid || selectedEmail.id === email.id)) {
      setSelectedEmail(prev => ({ ...prev, is_starred: newStarred }));
    }

    try {
      await api.post('/auth/mail-account/modify-message/', {
        msg_id: email.uid || email.id,
        action,
      });
      toast.success(newStarred ? 'Starred' : 'Unstarred');
    } catch (err) {
      toast.error('Failed to update star');
      loadFolder(activeFolder, true);
    }
  };

  const handleToggleRead = async (e, email) => {
    if (e) e.stopPropagation();
    const newUnread = !email.is_unread;
    const action = newUnread ? 'unread' : 'read';

    // Optimistic update
    const updated = emails.map(m => (m.uid === email.uid || m.id === email.id) ? { ...m, is_unread: newUnread } : m);
    dispatch(setEmails(updated));
    if (selectedEmail && (selectedEmail.uid === email.uid || selectedEmail.id === email.id)) {
      setSelectedEmail(prev => ({ ...prev, is_unread: newUnread }));
    }

    try {
      await api.post('/auth/mail-account/modify-message/', {
        msg_id: email.uid || email.id,
        action,
      });
      toast.success(newUnread ? 'Marked as unread' : 'Marked as read');
    } catch (err) {
      toast.error('Failed to update read status');
    }
  };

  const handleTrashMessage = async (email) => {
    try {
      await api.post('/auth/mail-account/trash-message/', {
        msg_id: email.uid || email.id,
      });
      toast.success('Moved to Trash');
      dispatch(setEmails(emails.filter(m => (m.uid || m.id) !== (email.uid || email.id))));
      if (selectedEmail && (selectedEmail.uid === email.uid || selectedEmail.id === email.id)) {
        setSelectedEmail(null);
        setEmailBodyState({ html_body: '', text_body: '', attachments: [] });
      }
    } catch (err) {
      toast.error('Failed to move to Trash');
    }
  };

  const handleUntrashMessage = async (email) => {
    try {
      await api.post('/auth/mail-account/untrash-message/', {
        msg_id: email.uid || email.id,
      });
      toast.success('Restored from Trash to Inbox');
      dispatch(setEmails(emails.filter(m => (m.uid || m.id) !== (email.uid || email.id))));
      if (selectedEmail && (selectedEmail.uid === email.uid || selectedEmail.id === email.id)) {
        setSelectedEmail(null);
        setEmailBodyState({ html_body: '', text_body: '', attachments: [] });
      }
    } catch (err) {
      toast.error('Failed to restore message');
    }
  };

  const handleDeleteForever = async (email) => {
    if (!window.confirm('Are you sure you want to permanently delete this email? This cannot be undone.')) return;
    try {
      await api.post('/auth/mail-account/delete-message/', {
        msg_id: email.uid || email.id,
      });
      toast.success('Permanently deleted');
      dispatch(setEmails(emails.filter(m => (m.uid || m.id) !== (email.uid || email.id))));
      if (selectedEmail && (selectedEmail.uid === email.uid || selectedEmail.id === email.id)) {
        setSelectedEmail(null);
        setEmailBodyState({ html_body: '', text_body: '', attachments: [] });
      }
    } catch (err) {
      toast.error('Failed to delete message');
    }
  };

  const handleToggleSpam = async (email) => {
    const isSpamFolder = activeFolder === 'SPAM' || activeFolder.includes('Spam') || email.is_spam;
    const action = isSpamFolder ? 'unspam' : 'spam';
    try {
      await api.post('/auth/mail-account/modify-message/', {
        msg_id: email.uid || email.id,
        action,
      });
      toast.success(isSpamFolder ? 'Marked as Not Spam and moved to Inbox' : 'Reported as Spam');
      dispatch(setEmails(emails.filter(m => (m.uid || m.id) !== (email.uid || email.id))));
      if (selectedEmail && (selectedEmail.uid === email.uid || selectedEmail.id === email.id)) {
        setSelectedEmail(null);
        setEmailBodyState({ html_body: '', text_body: '', attachments: [] });
      }
    } catch (err) {
      toast.error('Failed to update spam status');
    }
  };

  // Derived: user's mail account ID comes from user.profile via /auth/me/
  const userId = user?.id;
  const mailAccountId = user?.mail_account_id || 'default';

  // ─── Folder fetch ─────────────────────────────────────────────────────────

  const loadSeqRef = useRef(0);
  const inFlightRef = useRef(false);
  const emailsRef = useRef([]);
  const activeFolderRef = useRef(activeFolder);
  emailsRef.current = emails;
  activeFolderRef.current = activeFolder;

  const mailSignature = (list) =>
    (list || []).map(m => `${m.uid || m.id}:${m.is_unread ? 1 : 0}${m.is_starred ? 1 : 0}`).join('|');

  const loadFolder = useCallback(async (folder, bypassCache = false, search = '', silent = false) => {
    // Never stack background polls on top of an in-flight request
    if (silent && inFlightRef.current) return;

    const seq = ++loadSeqRef.current;
    inFlightRef.current = true;
    const isStale = () => seq !== loadSeqRef.current || folder !== activeFolderRef.current;

    if (!silent) {
      dispatch(setSyncError(null));
    }

    // Step 1: Try IndexedDB cache (only when no active search)
    let hasCached = false;
    if (!bypassCache && !search && userId) {
      const cached = await getMailboxMessages(userId, mailAccountId, folder);
      if (cached && cached.length > 0 && !isStale()) {
        dispatch(setEmails(cached));
        hasCached = true;
        if (!silent) {
          dispatch(setInboxLoading(false));
        }
        // Do NOT return! Always revalidate with server in the background (Live SWR)
      }
    }

    if (!hasCached && !silent) {
      dispatch(setInboxLoading(true));
    }

    // Step 2: Background revalidation or explicit fetch from backend (Live SWR)
    try {
      const searchParam = search ? `&search=${encodeURIComponent(search)}` : '';
      const res = await api.get(
        `/auth/mail-account/fetch-emails/?folder=${encodeURIComponent(folder)}&limit=25${searchParam}`
      );
      if (isStale()) return; // a newer request / folder switch superseded this one

      const { messages = [], emails: rawEmails = [], uidvalidity = null, partial = false, error = null } = res.data;
      const finalMessages = messages.length > 0 ? messages : rawEmails;

      // Incomplete or errored responses must never replace a good list
      if (error || (partial && silent && emailsRef.current.length > 0)) return;

      if (userId && !search && !partial) {
        const highestUid = finalMessages.reduce((max, m) => {
          const uid = parseInt(m.uid, 10);
          return uid > max ? uid : max;
        }, 0);

        await setMailboxMessages(userId, mailAccountId, folder, finalMessages, uidvalidity);
        if (uidvalidity !== null) {
          await setMailboxState(userId, mailAccountId, folder, uidvalidity, highestUid);
        }
      }

      if (isStale()) return;
      // Only touch the UI when something actually changed (prevents flicker)
      if (mailSignature(finalMessages) !== mailSignature(emailsRef.current)) {
        dispatch(setEmails(finalMessages));
      }
    } catch (err) {
      if (isStale()) return;
      // Keep showing the existing list on transient failures
      if (!hasCached && !silent && emailsRef.current.length === 0) {
        const message = err.response?.data?.error || 'Failed to fetch emails.';
        toast.error(message);
        dispatch(setSyncError(message));
      }
    } finally {
      if (seq === loadSeqRef.current) {
        inFlightRef.current = false;
        if (!silent) {
          dispatch(setInboxLoading(false));
        }
      }
    }
  }, [userId, mailAccountId, dispatch]);

  // ─── Prospect Responses fetch (virtual view) ──────────────────────────────

  const loadProspectResponses = useCallback(async (silent = false) => {
    if (silent && inFlightRef.current) return;
    const seq = ++loadSeqRef.current;
    inFlightRef.current = true;

    if (!silent) {
      setProspectLoading(true);
      setProspectError(null);
    }

    try {
      const searchParam = searchQuery ? `&search=${encodeURIComponent(searchQuery)}` : '';
      const res = await api.get(`/auth/mail-account/prospect-responses/?limit=25${searchParam}`);
      if (seq !== loadSeqRef.current) return;

      const messages = res.data?.messages || [];
      setProspectEmails(messages);
    } catch (err) {
      if (seq !== loadSeqRef.current) return;
      const msg = err.response?.data?.error || 'Failed to fetch prospect responses.';
      setProspectError(msg);
      if (!silent) toast.error(msg);
    } finally {
      if (seq === loadSeqRef.current) {
        inFlightRef.current = false;
        if (!silent) setProspectLoading(false);
      }
    }
  }, [searchQuery]);

  // ─── Load on folder change ────────────────────────────────────────────────

  useEffect(() => {
    if (isProspectResponsesView) return;
    setSelectedEmail(null);
    setEmailBodyState({ html_body: '', text_body: '', attachments: [] });
    dispatch(setEmails([]));
    loadFolder(activeFolder, false, searchQuery);
  }, [activeFolder, isProspectResponsesView]); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Live Polling: Auto-sync active folder or prospect responses in background ───

  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === 'visible' && !searchQuery) {
        if (isProspectResponsesView) {
          loadProspectResponses(true /* silent */);
        } else {
          loadFolder(activeFolder, true, '', true /* silent */);
        }
      }
    }, 15000);
    return () => clearInterval(timer);
  }, [activeFolder, searchQuery, loadFolder, isProspectResponsesView, loadProspectResponses]);

  // ─── Live Focus / Visibility: Sync immediately on window focus or tab visibility ───

  useEffect(() => {
    const handleVisibilityOrFocus = () => {
      if (document.visibilityState === 'visible' && !searchQuery) {
        if (isProspectResponsesView) {
          loadProspectResponses(true /* silent */);
        } else {
          loadFolder(activeFolder, true, '', true /* silent */);
        }
      }
    };
    window.addEventListener('focus', handleVisibilityOrFocus);
    document.addEventListener('visibilitychange', handleVisibilityOrFocus);
    return () => {
      window.removeEventListener('focus', handleVisibilityOrFocus);
      document.removeEventListener('visibilitychange', handleVisibilityOrFocus);
    };
  }, [activeFolder, searchQuery, loadFolder, isProspectResponsesView, loadProspectResponses]);

  // ─── Cross-Component & Cross-Tab Live Events ──────────────────────────────

  useEffect(() => {
    const unsubscribe = subscribeMailEvents(async (event) => {
      if (['MAIL_SENT', 'MAIL_RECEIVED', 'DRAFT_SAVED', 'MAIL_MUTATED'].includes(event?.type)) {
        if (isProspectResponsesView) {
          loadProspectResponses(true);
        } else {
          // Silently reload current active folder
          loadFolder(activeFolder, true, searchQuery, true);
        }
        // If an email was sent and current folder is not SENT, reset the SENT cache so it reflects immediately when switched to
        if (event.type === 'MAIL_SENT' && activeFolder !== 'SENT' && userId) {
          try {
            await resetMailboxCache(userId, mailAccountId, 'SENT');
          } catch (e) {
            // ignore
          }
        }
      }
    });
    return unsubscribe;
  }, [activeFolder, searchQuery, loadFolder, userId, mailAccountId, isProspectResponsesView, loadProspectResponses]);

  // ─── Folder switch ────────────────────────────────────────────────────────

  const handleFolderSwitch = (folderId) => {
    setIsProspectResponsesView(false);
    if (folderId === activeFolder && !isProspectResponsesView) return;
    dispatch(setActiveFolder(folderId));
    setSelectedEmail(null);
    setEmailBodyState({ html_body: '', text_body: '', attachments: [] });
  };

  const handleSwitchToProspectResponses = () => {
    setIsProspectResponsesView(true);
    setSelectedEmail(null);
    setEmailBodyState({ html_body: '', text_body: '', attachments: [] });
    loadProspectResponses(false);
  };

  // ─── Explicit Sync (bypass cache) ────────────────────────────────────────

  const handleRefresh = () => {
    setSelectedEmail(null);
    setEmailBodyState({ html_body: '', text_body: '', attachments: [] });
    if (isProspectResponsesView) {
      loadProspectResponses(false);
    } else {
      loadFolder(activeFolder, true /* bypassCache */, searchQuery);
    }
  };

  const handleSearchSubmit = (e) => {
    if (e) e.preventDefault();
    setSelectedEmail(null);
    if (isProspectResponsesView) {
      loadProspectResponses(false);
    } else {
      loadFolder(activeFolder, true, searchQuery);
    }
  };

  // ─── Open email (body cache-first) ────────────────────────────────────────

  const openEmail = async (email) => {
    setSelectedEmail(email);
    setEmailBodyState({ html_body: '', text_body: '', attachments: [] });

    const uid = email.uid || email.id;
    const currentFolder = isProspectResponsesView ? 'INBOX' : activeFolder;

    // Step 1: Check body cache using stable UID (bypass if body has stale unresolved CID)
    if (userId && uid) {
      const cached = await getEmailBody(userId, mailAccountId, currentFolder, uid);
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
        `/auth/mail-account/fetch-email-body/?folder=${encodeURIComponent(currentFolder)}&uid=${encodeURIComponent(uid)}`
      );
      const body = res.data;

      if (userId && uid) {
        await setEmailBody(userId, mailAccountId, currentFolder, uid, body);
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

  const currentList = isProspectResponsesView ? prospectEmails : emails;
  const isListLoading = isProspectResponsesView ? prospectLoading : loading;
  const displayEmails = currentList.filter(e => {
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      const matchSubject = e.subject?.toLowerCase().includes(q);
      const matchCompany = e.prospect_company_name?.toLowerCase().includes(q);
      const matchContact = e.prospect_contact_name?.toLowerCase().includes(q);
      const matchFrom = e.from?.toLowerCase().includes(q);
      return matchSubject || matchCompany || matchContact || matchFrom;
    }
    return true;
  });

  return (
    <div className="space-y-6 flex flex-col h-[calc(100vh-64px)] overflow-hidden">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 shrink-0">
        <div>
          <h1 className="text-xl font-semibold text-slate-900 tracking-tight flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-600 text-white flex items-center justify-center shadow-xs">
              <Mail className="w-4 h-4" />
            </div>
            Inbox
          </h1>
          <p className="text-slate-500 text-xs mt-1 font-normal">
            {gmailStatus.is_connected
              ? `Connected to Google Mail (${gmailStatus.email}). Tracking enabled.`
              : senderMailStatus
              ? `Connected to ${senderMailStatus.email_address}.`
              : 'View emails and send tracked messages from your configured mailbox.'}
          </p>
        </div>
        <div className="flex items-center gap-2.5 flex-wrap">
          {gmailStatus.is_connected ? (
            <div className="flex items-center gap-2 bg-slate-50 border border-slate-200/80 px-3.5 py-1.5 rounded-full text-xs font-medium text-slate-700 shadow-2xs">
              <span className="w-2 h-2 rounded-full bg-emerald-500 shrink-0"></span>
              <span className="text-slate-500 shrink-0">Gmail:</span>
              <span className="truncate max-w-[140px] sm:max-w-xs text-slate-800 font-medium">{gmailStatus.email}</span>
              <button
                type="button"
                onClick={handleDisconnectGmail}
                disabled={disconnectingGmail}
                className="ml-1 text-[11px] font-medium text-slate-400 hover:text-rose-600 transition underline disabled:opacity-50 cursor-pointer"
              >
                {disconnectingGmail ? '...' : 'Disconnect'}
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={handleConnectGmail}
              disabled={connectingGmail}
              className="px-4 py-2 bg-white hover:bg-slate-50 text-slate-700 font-medium text-sm rounded-full transition flex items-center gap-2 border border-slate-200 shadow-2xs hover:border-slate-300 disabled:opacity-50 cursor-pointer"
              title="Connect your Google Mail account via OAuth"
            >
              <svg className="w-4 h-4 shrink-0" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"/>
                <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
              </svg>
              <span>{connectingGmail ? 'Connecting...' : 'Connect Gmail'}</span>
            </button>
          )}

          <button
            type="button"
            onClick={() => setShowBulkCampaign(true)}
            className="px-4 py-2 bg-white hover:bg-slate-50 border border-slate-200 hover:border-slate-300 text-slate-800 font-medium text-sm rounded-full transition flex items-center gap-2 shadow-2xs cursor-pointer"
            title="Create and monitor safe 90-second bulk campaigns"
          >
            <Users className="w-4 h-4 text-blue-600" />
            <span>Bulk Campaign</span>
          </button>
          <button 
            type="button"
            onClick={handleCompose} 
            className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white font-medium text-sm rounded-full transition flex items-center gap-2 shadow-xs hover:shadow cursor-pointer"
          >
            <Edit3 className="w-4 h-4" />
            <span>Compose</span>
          </button>
          <button 
            type="button"
            onClick={handleRefresh} 
            disabled={isListLoading} 
            className="px-3.5 py-2 bg-white hover:bg-slate-50 border border-slate-200 hover:border-slate-300 text-slate-700 font-medium text-sm rounded-full transition flex items-center gap-2 shadow-2xs disabled:opacity-50 cursor-pointer"
          >
            <RefreshCw className={`w-4 h-4 text-slate-500 ${isListLoading ? 'animate-spin' : ''}`} />
            <span>Sync</span>
          </button>
        </div>
      </div>

      <div className="flex-1 min-h-0 bg-white border border-slate-200 rounded-2xl shadow-xs flex overflow-hidden">
        {/* Sidebar */}
        <div className="w-56 border-r border-slate-200/80 bg-slate-50/60 flex flex-col shrink-0">
          <div className="p-3.5 border-b border-slate-200/60">
            <h2 className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Mail</h2>
          </div>
          <nav className="flex-1 overflow-y-auto p-2 space-y-1">
            {FOLDERS.map((f) => {
              const Icon = f.icon;
              const isActive = !isProspectResponsesView && activeFolder === f.id;
              return (
                <button
                  key={f.id}
                  onClick={() => handleFolderSwitch(f.id)}
                  className={`w-full flex items-center gap-3 px-3.5 py-2 text-sm font-medium rounded-full transition cursor-pointer ${
                    isActive ? 'bg-blue-50 text-blue-700 font-semibold' : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                  }`}
                >
                  <Icon className={`w-4 h-4 ${isActive ? 'text-blue-600' : 'text-slate-500'}`} />
                  {f.label}
                </button>
              );
            })}

            <div className="pt-3 pb-1 px-1">
              <div className="h-px bg-slate-200/80 mb-2" />
              <span className="text-[10px] font-semibold tracking-wider text-slate-400 uppercase px-2">Prospects</span>
            </div>

            <button
              type="button"
              onClick={handleSwitchToProspectResponses}
              className={`w-full flex items-center justify-between px-3.5 py-2 text-sm font-medium rounded-full transition cursor-pointer ${
                isProspectResponsesView 
                  ? 'bg-emerald-50 text-emerald-800 font-semibold border border-emerald-200/80' 
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              }`}
              title="Inbound email responses from matched prospects and key contacts"
            >
              <div className="flex items-center gap-2.5 truncate">
                <Building2 className={`w-4 h-4 shrink-0 ${isProspectResponsesView ? 'text-emerald-700' : 'text-slate-500'}`} />
                <span className="truncate">Prospect Responses</span>
              </div>
              <span className={`text-[10px] px-2 py-0.5 rounded-full font-medium shrink-0 ${
                isProspectResponsesView ? 'bg-emerald-100 text-emerald-900' : 'bg-slate-200 text-slate-600'
              }`}>
                Prospects
              </span>
            </button>
          </nav>
        </div>

        {/* Content */}
        <div className="flex-1 flex min-w-0 bg-white overflow-hidden">
          {/* Email list */}
          <div className={`flex flex-col border-r border-slate-100 overflow-y-auto transition-all ${selectedEmail ? 'w-80 shrink-0' : 'flex-1'}`}>
            <div className="p-3 border-b border-slate-100 sticky top-0 bg-white z-10 shrink-0">
              <form onSubmit={handleSearchSubmit} className="relative flex items-center">
                <Search className="w-4 h-4 absolute left-3.5 text-slate-400 pointer-events-none" />
                <input 
                  type="text" 
                  placeholder="Search in mail..." 
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="w-full bg-slate-100/80 hover:bg-slate-100 border border-slate-200/60 text-slate-900 placeholder-slate-400 rounded-full pl-10 pr-8 py-2 text-xs outline-none focus:border-blue-500 focus:bg-white focus:ring-2 focus:ring-blue-100 font-normal transition-all"
                />
                {searchQuery && (
                  <button
                    type="button"
                    onClick={() => {
                      setSearchQuery('');
                      loadFolder(activeFolder, true, '');
                    }}
                    className="absolute right-2.5 p-1 text-slate-400 hover:text-slate-600 rounded-full"
                    title="Clear search"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </form>
            </div>
            {isProspectResponsesView && (
              <div className="bg-emerald-50/70 border-b border-emerald-200/60 px-4 py-2 text-xs flex items-center justify-between text-emerald-900 shrink-0">
                <div className="flex items-center gap-2 min-w-0">
                  <Sparkles className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                  <span className="font-medium truncate">Responses from matched prospects & contacts</span>
                </div>
                <span className="text-[10px] font-medium text-emerald-800 bg-emerald-100 px-2.5 py-0.5 rounded-full shrink-0">
                  {displayEmails.length} {displayEmails.length === 1 ? 'response' : 'responses'}
                </span>
              </div>
            )}
            {isListLoading ? (
              <div className="flex items-center justify-center h-full text-slate-400 gap-2 font-normal text-xs">
                <Loader2 className="w-4 h-4 animate-spin text-blue-600" /> Loading messages...
              </div>
            ) : displayEmails.length === 0 ? (
              isProspectResponsesView ? (
                <div className="flex flex-col items-center justify-center h-full p-8 text-center max-w-sm mx-auto space-y-3">
                  <div className="w-12 h-12 rounded-full bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-600 shadow-2xs">
                    <Building2 className="w-6 h-6" />
                  </div>
                  <div className="space-y-1">
                    <h3 className="font-semibold text-slate-800 text-sm">No prospect responses yet</h3>
                    <p className="text-slate-500 text-xs leading-relaxed">
                      Emails arriving from companies or key people in your prospect directory will automatically appear here.
                    </p>
                  </div>
                </div>
              ) : !gmailStatus.is_connected && (!senderMailStatus || senderMailStatus.provider === 'GMAIL_OAUTH') ? (
                <div className="flex flex-col items-center justify-center h-full p-8 text-center max-w-sm mx-auto space-y-4">
                  <div className="w-12 h-12 rounded-full bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600 shadow-2xs">
                    <Mail className="w-6 h-6" />
                  </div>
                  <div className="space-y-1">
                    <h3 className="font-semibold text-slate-800 text-base">Connect Google Mail</h3>
                    <p className="text-slate-500 text-xs leading-relaxed">
                      Connect your Gmail account via Google OAuth to view your inbox, sync sent messages, and track outreach effortlessly.
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={handleConnectGmail}
                    disabled={connectingGmail}
                    className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-medium text-sm rounded-full transition flex items-center gap-2 shadow-xs hover:shadow disabled:opacity-50 cursor-pointer"
                  >
                    <svg className="w-4 h-4 shrink-0" viewBox="0 0 24 24">
                      <path fill="#ffffff" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                      <path fill="#ffffff" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                      <path fill="#ffffff" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"/>
                    </svg>
                    <span>{connectingGmail ? 'Connecting...' : 'Connect Gmail'}</span>
                  </button>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center h-full text-slate-400 font-normal p-6 text-center space-y-2 text-xs">
                  <Mail className="w-8 h-8 text-slate-300" />
                  <span>No emails found in this folder.</span>
                </div>
              )
            ) : (
              <ul className="divide-y divide-slate-100">
                {displayEmails.map((email) => (
                  <li
                    key={email.uid || email.id}
                    onClick={() => {
                      if (activeFolder === 'DRAFT') {
                        handleOpenDraft(email);
                      } else {
                        openEmail(email);
                      }
                    }}
                    className={`p-3.5 cursor-pointer transition ${selectedEmail?.uid === email.uid ? 'bg-blue-50/70 border-l-2 border-blue-600' : 'hover:bg-slate-50/80'}`}
                  >
                    <div className="flex items-center justify-between gap-1.5 mb-1">
                      <div className="flex items-center gap-1.5 min-w-0 flex-1">
                        <button
                          type="button"
                          onClick={(e) => handleToggleStar(e, email)}
                          className="p-1 text-slate-300 hover:text-amber-400 rounded-full hover:bg-slate-100 transition shrink-0"
                          title={email.is_starred ? 'Starred' : 'Star message'}
                        >
                          <Star className={`w-3.5 h-3.5 ${email.is_starred ? 'fill-amber-400 text-amber-400' : ''}`} />
                        </button>

                        <span className={`text-xs truncate flex-1 flex items-center gap-1.5 flex-wrap ${email.is_unread ? 'font-semibold text-slate-900' : 'font-normal text-slate-700'}`}>
                          {email.prospect_company_name ? (
                            (email.prospect_lq_id || email.prospect_id) ? (
                              <Link
                                to={`/lq-pipeline/${email.prospect_lq_id || email.prospect_id}`}
                                onClick={(e) => e.stopPropagation()}
                                className="inline-flex items-center gap-1 text-emerald-800 bg-emerald-50 hover:bg-emerald-100 hover:text-emerald-950 px-2 py-0.5 rounded-full border border-emerald-200/80 text-[10px] font-medium shrink-0 transition"
                                title={`View ${email.prospect_company_name} in LQ Pipeline`}
                              >
                                <Building2 className="w-3 h-3 text-emerald-600" /> {email.prospect_company_name}
                              </Link>
                            ) : (
                              <span className="inline-flex items-center gap-1 text-emerald-800 bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200/80 text-[10px] font-medium shrink-0" title={`Company: ${email.prospect_company_name}`}>
                                <Building2 className="w-3 h-3 text-emerald-600" /> {email.prospect_company_name}
                              </span>
                            )
                          ) : null}
                          {email.prospect_contact_name ? (
                            <span className="inline-flex items-center gap-1 text-indigo-800 bg-indigo-50 px-2 py-0.5 rounded-full border border-indigo-200/80 text-[10px] font-medium shrink-0" title={`Contact: ${email.prospect_contact_name}`}>
                              <User className="w-3 h-3 text-indigo-600" /> {email.prospect_contact_name}
                            </span>
                          ) : null}
                          <span className="truncate">
                            {!isProspectResponsesView && (activeFolder === 'SENT' || activeFolder.includes('Sent')) 
                              ? `To: ${email.to?.replace(/<.*>/, '').trim() || email.to}` 
                              : !isProspectResponsesView && activeFolder === 'DRAFT'
                              ? `Draft: ${email.to?.replace(/<.*>/, '').trim() || '(No Recipient)'}`
                              : email.from?.replace(/<.*>/, '').trim() || email.from}
                          </span>
                        </span>
                      </div>

                      <div className="flex items-center gap-1.5 shrink-0">
                        {email.tracking && (
                          email.tracking.open_tracking_enabled === false ? (
                            <span 
                              className="px-2 py-0.5 rounded-full text-[10px] font-medium text-slate-500 bg-slate-100 border border-slate-200"
                              title="Open tracking disabled"
                            >
                              Untracked
                            </span>
                          ) : (
                            <span 
                              className={`px-2 py-0.5 rounded-full text-[10px] font-medium border flex items-center gap-1 ${
                                email.tracking.is_opened 
                                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200' 
                                  : 'bg-amber-50 text-amber-700 border-amber-200'
                              }`}
                              title={email.tracking.is_opened ? `Opened ${email.tracking.open_count || 1}x` : 'Awaiting open'}
                            >
                              <span className={`w-1.5 h-1.5 rounded-full ${email.tracking.is_opened ? 'bg-emerald-500' : 'bg-amber-500'}`} />
                              {email.tracking.is_opened ? `${email.tracking.open_count || 1}x` : 'Sent'}
                            </span>
                          )
                        )}
                        <span className="text-[10px] text-slate-400 font-normal">{email.date?.split(' ').slice(1, 4).join(' ')}</span>
                      </div>
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <h4 className={`text-xs truncate flex-1 ${email.is_unread ? 'font-semibold text-slate-900' : 'font-normal text-slate-700'}`}>
                        {email.subject || '(No Subject)'}
                      </h4>
                      {email.is_unread && (
                        <span className="w-2 h-2 rounded-full bg-blue-600 shrink-0" title="Unread" />
                      )}
                    </div>
                    {email.snippet && (
                      <p className="text-[11px] text-slate-400 truncate mt-0.5 font-normal">{email.snippet}</p>
                    )}
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
                  className="p-2 hover:bg-slate-100 rounded-full transition text-slate-600 mt-0.5 shrink-0 cursor-pointer"
                  title="Back to list"
                >
                  <ChevronLeft className="w-5 h-5" />
                </button>
                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-4">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <h2 className="text-base font-semibold text-slate-900 leading-tight">{selectedEmail.subject || '(No Subject)'}</h2>
                        {(selectedEmail.tracking || emailBody.tracking) && (
                          (selectedEmail.tracking || emailBody.tracking)?.open_tracking_enabled === false ? (
                            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-medium text-slate-500 bg-slate-100 border border-slate-200 shrink-0">
                              Untracked
                            </span>
                          ) : (
                            <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-medium border flex items-center gap-1.5 shrink-0 ${
                              (emailBody.tracking || selectedEmail.tracking)?.is_opened
                                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                : 'bg-amber-50 text-amber-700 border-amber-200'
                            }`}>
                              <span className={`w-1.5 h-1.5 rounded-full ${(emailBody.tracking || selectedEmail.tracking)?.is_opened ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'}`} />
                              {(emailBody.tracking || selectedEmail.tracking)?.is_opened 
                                ? `Viewed (${(emailBody.tracking || selectedEmail.tracking)?.open_count || 1}x)` 
                                : 'Sent'}
                            </span>
                          )
                        )}
                      </div>

                      {/* Prospect Identification Card */}
                      {(selectedEmail.prospect_match || selectedEmail.prospect_company_name) && (() => {
                        const targetLqId = selectedEmail.prospect_lq_id || selectedEmail.prospect_id;
                        return (
                          <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-3 mt-2.5 mb-1 flex items-center justify-between flex-wrap gap-2">
                            <div className="flex items-center gap-2.5">
                              <div className="w-8 h-8 rounded-full bg-emerald-100 text-emerald-800 flex items-center justify-center font-medium shadow-2xs shrink-0">
                                <Building2 className="w-4 h-4 text-emerald-700" />
                              </div>
                              <div>
                                <div className="flex items-center gap-1.5 flex-wrap">
                                  {targetLqId ? (
                                    <Link
                                      to={`/lq-pipeline/${targetLqId}`}
                                      className="font-semibold text-xs text-slate-900 hover:text-indigo-600 hover:underline flex items-center gap-1 transition group"
                                      title="Open related Lead Qualification Pipeline record"
                                    >
                                      <span>{selectedEmail.prospect_company_name}</span>
                                      <ExternalLink className="w-3 h-3 text-slate-400 group-hover:text-indigo-600 transition" />
                                    </Link>
                                  ) : (
                                    <span className="font-semibold text-xs text-slate-900">
                                      {selectedEmail.prospect_company_name}
                                    </span>
                                  )}
                                  {targetLqId ? (
                                    <Link
                                      to={`/lq-pipeline/${targetLqId}`}
                                      className="px-2 py-0.5 bg-emerald-100 hover:bg-emerald-200 text-emerald-800 text-[10px] font-medium rounded-full transition flex items-center gap-1 cursor-pointer"
                                      title="Open related Lead Qualification Pipeline record"
                                    >
                                      <span>Matched Company</span>
                                      <ChevronRight className="w-2.5 h-2.5 text-emerald-700" />
                                    </Link>
                                  ) : (
                                    <span className="px-2 py-0.5 bg-emerald-100 text-emerald-800 text-[10px] font-medium rounded-full">
                                      Matched Company
                                    </span>
                                  )}
                                  {selectedEmail.prospect_contact_name && (
                                    <>
                                      <span className="text-slate-300">·</span>
                                      <span className="font-medium text-xs text-indigo-900 flex items-center gap-1">
                                        <User className="w-3 h-3 text-indigo-600" />
                                        {selectedEmail.prospect_contact_name}
                                      </span>
                                      <span className="px-2 py-0.5 bg-indigo-100 text-indigo-800 text-[10px] font-medium rounded-full">
                                        Contact
                                      </span>
                                    </>
                                  )}
                                </div>
                                <p className="text-[11px] text-slate-500 font-normal mt-0.5">
                                  Matched prospect from your directory.
                                </p>
                              </div>
                            </div>

                            {targetLqId && (
                              <Link
                                to={`/lq-pipeline/${targetLqId}`}
                                className="px-3 py-1.5 bg-white hover:bg-indigo-50 border border-slate-200 hover:border-indigo-300 text-indigo-600 hover:text-indigo-700 rounded-lg text-xs font-semibold shadow-2xs transition flex items-center gap-1.5"
                                title="Open related Lead Qualification Pipeline record"
                              >
                                <span>View in LQ Pipeline</span>
                                <ChevronRight className="w-3.5 h-3.5" />
                              </Link>
                            )}
                          </div>
                        );
                      })()}

                      <div className="flex items-center gap-2 mt-1 text-xs text-slate-500 flex-wrap">
                        <span>From: <span className="font-medium text-slate-700">{selectedEmail.from}</span></span>
                        {selectedEmail.to && (
                          <>
                            <span className="text-slate-300">·</span>
                            <span>To: <span className="font-medium text-slate-700">{selectedEmail.to}</span></span>
                          </>
                        )}
                        <span className="text-slate-300">·</span>
                        <span>{selectedEmail.date}</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0 flex-wrap">
                      {/* Star / Unstar button */}
                      <button
                        type="button"
                        onClick={(e) => handleToggleStar(e, selectedEmail)}
                        className={`p-2 rounded-full border transition cursor-pointer ${
                          selectedEmail.is_starred
                            ? 'bg-amber-50 border-amber-200 text-amber-500 hover:bg-amber-100'
                            : 'bg-white border-slate-200 text-slate-400 hover:text-amber-500 hover:bg-slate-50'
                        }`}
                        title={selectedEmail.is_starred ? 'Starred' : 'Not starred'}
                      >
                        <Star className={`w-3.5 h-3.5 ${selectedEmail.is_starred ? 'fill-amber-400 text-amber-400' : ''}`} />
                      </button>

                      {/* Mark Read / Unread */}
                      <button
                        type="button"
                        onClick={(e) => handleToggleRead(e, selectedEmail)}
                        className="p-2 rounded-full border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 transition cursor-pointer"
                        title={selectedEmail.is_unread ? 'Mark as Read' : 'Mark as Unread'}
                      >
                        {selectedEmail.is_unread ? <MailOpen className="w-3.5 h-3.5 text-blue-600" /> : <Mail className="w-3.5 h-3.5 text-slate-500" />}
                      </button>

                      {/* Draft actions */}
                      {activeFolder === 'DRAFT' && (
                        <button
                          type="button"
                          onClick={() => handleOpenDraft(selectedEmail)}
                          className="px-3.5 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded-full transition flex items-center gap-1.5 shadow-2xs cursor-pointer"
                        >
                          <Edit3 className="w-3.5 h-3.5" />
                          <span>Edit Draft</span>
                        </button>
                      )}

                      {/* Spam toggle */}
                      {activeFolder === 'SPAM' ? (
                        <button
                          type="button"
                          onClick={() => handleToggleSpam(selectedEmail)}
                          className="px-3.5 py-1.5 bg-emerald-50 hover:bg-emerald-100 border border-emerald-200 text-emerald-800 text-xs font-medium rounded-full transition flex items-center gap-1 cursor-pointer"
                          title="Not Spam (Move to Inbox)"
                        >
                          <Undo2 className="w-3.5 h-3.5" />
                          <span>Not Spam</span>
                        </button>
                      ) : activeFolder !== 'TRASH' && activeFolder !== 'DRAFT' ? (
                        <button
                          type="button"
                          onClick={() => handleToggleSpam(selectedEmail)}
                          className="p-2 rounded-full border border-slate-200 bg-white text-slate-500 hover:text-rose-600 hover:bg-rose-50 transition cursor-pointer"
                          title="Report Spam"
                        >
                          <ShieldAlert className="w-3.5 h-3.5" />
                        </button>
                      ) : null}

                      {/* Trash / Untrash / Delete Forever */}
                      {activeFolder === 'TRASH' ? (
                        <>
                          <button
                            type="button"
                            onClick={() => handleUntrashMessage(selectedEmail)}
                            className="px-3.5 py-1.5 bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-700 text-xs font-medium rounded-full transition flex items-center gap-1 cursor-pointer"
                            title="Restore to Inbox"
                          >
                            <Undo2 className="w-3.5 h-3.5" />
                            <span>Restore</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => handleDeleteForever(selectedEmail)}
                            className="px-3.5 py-1.5 bg-rose-50 hover:bg-rose-100 border border-rose-200 text-rose-700 text-xs font-medium rounded-full transition flex items-center gap-1 cursor-pointer"
                            title="Delete Forever"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                            <span>Delete</span>
                          </button>
                        </>
                      ) : (
                        <button
                          type="button"
                          onClick={() => handleTrashMessage(selectedEmail)}
                          className="p-2 rounded-full border border-slate-200 bg-white text-slate-500 hover:text-rose-600 hover:bg-rose-50 transition cursor-pointer"
                          title="Move to Trash"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}

                      {/* Email Tracking */}
                      {(activeFolder.includes('Sent') || activeFolder === 'SENT' || selectedEmail.tracking || emailBody.tracking) && (
                        <button
                          type="button"
                          onClick={() => handleOpenTrackingModal()}
                          className="px-3.5 py-1.5 bg-white hover:bg-slate-50 border border-slate-200 hover:border-slate-300 text-slate-700 font-medium text-xs rounded-full transition flex items-center gap-1.5 shadow-2xs cursor-pointer"
                          title="Open email tracking & engagement analytics"
                        >
                          <BarChart2 className="w-3.5 h-3.5 text-blue-600" />
                          <span>Track</span>
                        </button>
                      )}

                      {/* Reply */}
                      {activeFolder !== 'DRAFT' && (
                        <button onClick={handleReply} className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium rounded-full transition flex items-center gap-1.5 shadow-2xs shrink-0 cursor-pointer">
                          <Reply className="w-3.5 h-3.5" /> Reply
                        </button>
                      )}
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
            <div className="bg-white border-b border-slate-200 px-5 py-3 text-slate-800 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center">
                  <Mail className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="font-semibold text-sm text-slate-900 leading-snug">New message</h3>
                  {senderMailStatus && (
                    <p className="text-[11px] text-slate-500 font-normal">
                      From: <span className="text-slate-700 font-medium">{senderMailStatus.display_name || senderMailStatus.email_address}</span> ({senderMailStatus.email_address})
                    </p>
                  )}
                </div>
              </div>
              <button 
                type="button"
                onClick={() => setShowCompose(false)} 
                className="text-slate-400 hover:text-slate-700 p-1.5 rounded-full hover:bg-slate-100 transition cursor-pointer"
                title="Close"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Scrollable Body */}
            <div className="p-4 sm:p-5 flex-1 overflow-y-auto space-y-3.5 text-xs">
              {/* Recipient Fields */}
              <div className="space-y-2 bg-slate-50/70 p-3 rounded-xl border border-slate-200/80">
                {/* To Field */}
                <div className="flex items-center gap-2">
                  <label className="text-xs font-medium text-slate-500 w-10 shrink-0">To:</label>
                  <input 
                    type="text" 
                    value={composeData.to} 
                    onChange={(e) => setComposeData(prev => ({ ...prev, to: e.target.value }))}
                    disabled={sendingEmail}
                    className="flex-1 p-2 bg-white border border-slate-200 rounded-lg text-xs font-normal text-slate-900 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition" 
                    placeholder="recipient@example.com (comma-separated for multiple)"
                  />
                  <div className="flex items-center gap-1 shrink-0 text-xs font-medium">
                    {!showCc && (
                      <button
                        type="button"
                        onClick={() => setShowCc(true)}
                        className="px-2.5 py-1 text-slate-500 hover:text-blue-600 hover:bg-white rounded-md transition cursor-pointer"
                      >
                        Cc
                      </button>
                    )}
                    {!showBcc && (
                      <button
                        type="button"
                        onClick={() => setShowBcc(true)}
                        className="px-2.5 py-1 text-slate-500 hover:text-blue-600 hover:bg-white rounded-md transition cursor-pointer"
                      >
                        Bcc
                      </button>
                    )}
                  </div>
                </div>

                {/* Cc Field */}
                {showCc && (
                  <div className="flex items-center gap-2">
                    <label className="text-xs font-medium text-blue-600 w-10 shrink-0">Cc:</label>
                    <input 
                      type="text" 
                      value={composeData.cc || ''} 
                      onChange={(e) => setComposeData(prev => ({ ...prev, cc: e.target.value }))}
                      disabled={sendingEmail}
                      className="flex-1 p-2 bg-white border border-slate-200 rounded-lg text-xs font-normal text-slate-900 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition" 
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
                    <label className="text-xs font-medium text-blue-600 w-10 shrink-0">Bcc:</label>
                    <input 
                      type="text" 
                      value={composeData.bcc || ''} 
                      onChange={(e) => setComposeData(prev => ({ ...prev, bcc: e.target.value }))}
                      disabled={sendingEmail}
                      className="flex-1 p-2 bg-white border border-slate-200 rounded-lg text-xs font-normal text-slate-900 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition" 
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
                <label className="block text-xs font-medium text-slate-700 mb-1">Subject</label>
                <input 
                  type="text" 
                  value={composeData.subject} 
                  onChange={(e) => setComposeData(prev => ({ ...prev, subject: e.target.value }))}
                  disabled={sendingEmail}
                  className="w-full p-2.5 bg-white border border-slate-200 rounded-xl text-xs font-normal text-slate-900 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition" 
                  placeholder="Subject"
                />
              </div>

              {/* Message Content */}
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1">Message</label>
                <textarea 
                  rows={8}
                  value={composeData.body}
                  onChange={(e) => setComposeData(prev => ({ ...prev, body: e.target.value }))}
                  disabled={sendingEmail}
                  className={`w-full p-3 bg-white border border-slate-200 text-xs font-normal text-slate-800 leading-relaxed focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 transition ${
                    senderMailStatus?.default_signature && !templateSelection.signatureId ? 'rounded-t-xl' : 'rounded-xl'
                  }`}
                  placeholder="Write your email here..."
                />
                {senderMailStatus?.default_signature && !templateSelection.signatureId && (
                  <div className="w-full p-3 bg-slate-50 border border-t-0 border-slate-200 rounded-b-xl text-xs text-slate-500 whitespace-pre-wrap font-normal">
                    {senderMailStatus.default_signature}
                  </div>
                )}
              </div>

              {/* Attachments Section */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-medium text-slate-700">Attachments</label>
                  <span className="text-[11px] text-slate-400">Max 10MB per file, 25MB total</span>
                </div>
                <div className="p-3 bg-white border border-slate-200 rounded-xl space-y-2">
                  <input 
                    type="file" 
                    multiple 
                    ref={fileInputRef}
                    onChange={handleFileChange} 
                    disabled={sendingEmail}
                    className="text-xs text-slate-700 file:mr-2 file:py-1 file:px-3 file:rounded-full file:border-0 file:text-xs file:font-medium file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 cursor-pointer disabled:opacity-50"
                  />
                  {attachmentError && (
                    <div className="text-red-600 text-[10px] font-medium">{attachmentError}</div>
                  )}
                  {attachments.length > 0 && (
                    <div className="flex flex-wrap gap-2 pt-1">
                      {attachments.map((file, i) => (
                        <div key={i} className="flex items-center gap-1.5 px-3 py-1 bg-slate-100 rounded-full border border-slate-200 text-xs font-medium text-slate-700">
                          <Paperclip className="w-3 h-3 text-slate-400" />
                          <span className="truncate max-w-[160px]">{file.name}</span>
                          <span className="text-slate-400 font-normal">({(file.size / 1024 / 1024).toFixed(1)}MB)</span>
                          <button 
                            type="button" 
                            onClick={() => removeAttachment(i)} 
                            className="text-slate-400 hover:text-rose-600 font-bold ml-1 text-sm leading-none cursor-pointer"
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

              {/* Email Open Tracking Toggle */}
              <div className="pt-1">
                <OpenTrackingToggle 
                  checked={openTrackingEnabled} 
                  onChange={setOpenTrackingEnabled} 
                  disabled={sendingEmail} 
                />
              </div>
            </div>

            {/* Modal Footer */}
            <div className="bg-slate-50/80 px-5 py-3 border-t border-slate-200 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={sendingEmail}
                  className="px-3.5 py-1.5 bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 font-medium text-xs rounded-full transition flex items-center gap-1.5 shadow-2xs cursor-pointer"
                >
                  <Paperclip className="w-3.5 h-3.5 text-blue-600" />
                  <span>Attach</span>
                  {attachments.length > 0 && (
                    <span className="px-1.5 py-0.2 rounded-full bg-blue-100 text-blue-700 text-[10px] font-medium">
                      {attachments.length}
                    </span>
                  )}
                </button>
              </div>
              <div className="flex items-center gap-2.5">
                <button 
                  type="button"
                  onClick={() => setShowCompose(false)} 
                  disabled={sendingEmail || savingDraft}
                  className="px-4 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 font-medium text-xs rounded-full transition cursor-pointer"
                >
                  Discard
                </button>
                <button
                  type="button"
                  onClick={handleSaveDraft}
                  disabled={sendingEmail || savingDraft}
                  className="px-4 py-2 bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 font-medium text-xs rounded-full transition flex items-center gap-1.5 disabled:opacity-50 shadow-2xs cursor-pointer"
                  title="Save Draft to Gmail"
                >
                  {savingDraft ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5 text-slate-500" />}
                  <span>{savingDraft ? 'Saving...' : 'Save Draft'}</span>
                </button>
                <button 
                  type="button"
                  onClick={sendEmail} 
                  disabled={sendingEmail || savingDraft || !composeData.to?.trim()} 
                  className="px-6 py-2 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 disabled:bg-slate-300 disabled:cursor-not-allowed text-white font-medium text-xs rounded-full shadow-xs hover:shadow transition flex items-center gap-2 cursor-pointer"
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
            <div className="bg-white border-b border-slate-200 px-6 py-4 text-slate-800 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
                  <BarChart2 className="w-5 h-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="text-sm font-semibold text-slate-900">Email engagement & tracking</h3>
                    {(trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.open_tracking_enabled === false ? (
                      <span className="px-2 py-0.5 rounded-full text-[10px] font-medium border bg-slate-100 text-slate-600 border-slate-200">
                        Tracking Disabled
                      </span>
                    ) : (
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium border flex items-center gap-1 ${
                        (trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.is_opened
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                          : 'bg-amber-50 text-amber-700 border-amber-200'
                      }`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${(trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.is_opened ? 'bg-emerald-500 animate-pulse' : 'bg-amber-500'}`} />
                        {(trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.is_opened 
                          ? `Viewed (${(trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.open_count || 1}x)` 
                          : 'Awaiting Open'}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-500 mt-0.5 truncate max-w-md">
                    {selectedEmail?.to || (trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.to_email || 'Recipient'} &bull; <span className="text-slate-700 font-medium">{selectedEmail?.subject || (trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.subject || '(No Subject)'}</span>
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowTrackingModal(false)}
                className="p-1.5 rounded-full hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition cursor-pointer"
                title="Close"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Body - Scrollable */}
            <div className="p-6 space-y-6 overflow-y-auto flex-1 text-slate-700 text-xs">
              {(trackingModalData || emailBody.tracking || selectedEmail?.tracking)?.open_tracking_enabled === false && (
                <div className="p-3 bg-slate-100 border border-slate-300 rounded-xl text-slate-700 text-xs font-semibold flex items-center gap-2">
                  <span>🛡️ Open tracking was disabled for this email. Deliverability was prioritized and no tracking pixel was injected.</span>
                </div>
              )}
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
            <div className="p-4 bg-slate-50/80 border-t border-slate-200 flex flex-wrap items-center justify-between gap-2.5">
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleSimulateOpen}
                  disabled={isSimulatingOpen || !(trackingModalData?.id || emailBody.tracking?.id || selectedEmail?.tracking?.id)}
                  className="px-3.5 py-1.5 bg-blue-50 hover:bg-blue-100 disabled:opacity-50 text-blue-700 font-medium text-xs rounded-full border border-blue-200 transition flex items-center gap-1.5 shadow-2xs cursor-pointer"
                  title="Simulate recipient opening the email (test live tracking)"
                >
                  <Zap className={`w-3.5 h-3.5 ${isSimulatingOpen ? 'animate-bounce text-blue-600' : 'text-blue-500'}`} />
                  <span>{isSimulatingOpen ? 'Recording...' : 'Test open ping'}</span>
                </button>
                <button
                  type="button"
                  onClick={handleRefreshTracking}
                  disabled={isRefreshingTracking}
                  className="px-3.5 py-1.5 bg-white hover:bg-slate-50 disabled:opacity-50 text-slate-700 font-medium text-xs rounded-full border border-slate-200 transition flex items-center gap-1.5 shadow-2xs cursor-pointer"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${isRefreshingTracking ? 'animate-spin text-slate-500' : 'text-slate-400'}`} />
                  <span>{isRefreshingTracking ? 'Refreshing...' : 'Refresh'}</span>
                </button>
              </div>

              <button
                type="button"
                onClick={() => setShowTrackingModal(false)}
                className="px-5 py-2 bg-slate-900 hover:bg-slate-800 text-white font-medium text-xs rounded-full transition shadow-2xs cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Bulk Email Campaign Modal */}
      <BulkCampaignModal
        isOpen={showBulkCampaign}
        onClose={() => setShowBulkCampaign(false)}
      />
    </div>
  );
};

export default InboxPage;
