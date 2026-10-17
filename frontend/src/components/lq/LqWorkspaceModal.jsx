import React, { useState, useEffect } from 'react';
import { 
  CheckCircle,
  AlertTriangle,
  Phone,
  Mail,
  Lock,
  ChevronDown,
  ChevronUp,
  TrendingUp,
  Clock,
  Shield,
  ArrowLeft,
  X,
  Building2,
  BarChart2,
  Eye,
  Activity,
  Zap,
  RefreshCw
} from 'lucide-react';
import { useDispatch, useSelector } from 'react-redux';
import { fetchCommunications, sendOutreachEmail, recordCall, syncMail } from '../../features/outreach/outreachSlice';
import { confirmReverification } from '../../features/lqPipeline/lqPipelineSlice';
import { toast } from 'react-toastify';
import api from '../../services/api';
import { localDateTimeToUTC } from '../../utils/timezone';
import TemplatePicker from './TemplatePicker';
import OpenTrackingToggle from '../email/OpenTrackingToggle';
import MeetingProviderPicker, { CreatedMeetingCard } from './MeetingProviderPicker';
import { notifyMailSent } from '../../services/mailSyncService';

const TimeSelect = ({ value, onChange, className }) => {
  const parseTime = (val) => {
    if (!val) return { h: '12', m: '00', ampm: 'PM' };
    let [hours, mins] = val.split(':');
    let h = parseInt(hours, 10);
    let ampm = h >= 12 ? 'PM' : 'AM';
    h = h % 12;
    if (h === 0) h = 12;
    return { h: h.toString().padStart(2, '0'), m: mins || '00', ampm };
  };
  const { h, m, ampm } = parseTime(value);

  const updateTime = (newH, newM, newAmpm) => {
    let hrs = parseInt(newH, 10);
    if (newAmpm === 'PM' && hrs !== 12) hrs += 12;
    if (newAmpm === 'AM' && hrs === 12) hrs = 0;
    onChange(`${hrs.toString().padStart(2, '0')}:${newM}`);
  };

  return (
    <div className={`flex items-center gap-1 ${className || ''}`}>
      <select value={h} onChange={(e) => updateTime(e.target.value, m, ampm)} className="p-2 flex-1 bg-white border border-slate-200 rounded-xl text-xs focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 text-center font-bold">
        {Array.from({length: 12}, (_, i) => String(i+1).padStart(2, '0')).map(hr => <option key={hr} value={hr}>{hr}</option>)}
      </select>
      <span className="font-bold text-slate-700">:</span>
      <select value={m} onChange={(e) => updateTime(h, e.target.value, ampm)} className="p-2 flex-1 bg-white border border-slate-200 rounded-xl text-xs focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 text-center font-bold">
        {Array.from({length: 60}, (_, i) => String(i).padStart(2, '0')).map(min => <option key={min} value={min}>{min}</option>)}
      </select>
      <select value={ampm} onChange={(e) => updateTime(h, m, e.target.value)} className="p-2 flex-1 bg-white border border-slate-200 rounded-xl text-xs focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 text-center font-bold">
        <option value="AM">AM</option>
        <option value="PM">PM</option>
      </select>
    </div>
  );
};

export default function LqWorkspaceModal({ 
  selectedLq,
  initialTab = 'verification',
  onClose,
  hasIncorrect,
  allCorrect,
  verificationFields,
  handleFieldToggle,
  handleSubmitIssue,
  handleReadyForOutreach,
  isConfirmingFixes,
  correctedFields = []
}) {
  const [activeTab, setActiveTab] = useState(initialTab);
  const dispatch = useDispatch();
  const { user } = useSelector(state => state.auth);
  
  // Get safe prospect reference
  const prospect = selectedLq?.prospect || {};
  const [localVerified, setLocalVerified] = useState(selectedLq?.verification_status === 'Verified');
  const isVerified = localVerified;
  const isLeadQualified = selectedLq?.qualification_status === 'Lead Qualified';

  // --- OUTREACH  // Outreach State
  // Initialize from prop, but will be overridden by fresh fetch below
  const [emailProgress, setEmailProgress] = useState(selectedLq?.email_status || 'Not Sent');
  const [emailCollapsed, setEmailCollapsed] = useState(selectedLq?.email_status && selectedLq.email_status !== 'Not Sent');
  const defaultToEmail = prospect?.key_contacts?.length > 0 && prospect.key_contacts[0].official_email ? prospect.key_contacts[0].official_email : '';
  const [toEmails, setToEmails] = useState(defaultToEmail ? [defaultToEmail] : []);
  const [ccEmails, setCcEmails] = useState([]);
  const [customRecipientInput, setCustomRecipientInput] = useState('');
  const [emailSubject, setEmailSubject] = useState(`Company Introduction & Solutions Overview — ${prospect.company_name || ''}`);
  const [emailBody, setEmailBody] = useState(`Dear ${prospect.company_name || 'Team'},\n\nWe are pleased to introduce our solution portfolio tailored for ${prospect.primary_industries || 'your industry'}. We would love to schedule a brief introductory discussion to explore potential alignment.\n\nBest regards,\nLead Qualification Team`);
  const [templateSelection, setTemplateSelection] = useState({ templateId: '', signatureId: '', baseBody: null });
  const [openTrackingEnabled, setOpenTrackingEnabled] = useState(false);
  const [attachments, setAttachments] = useState([]);
  const [attachmentError, setAttachmentError] = useState('');
  const [isSendingEmail, setIsSendingEmail] = useState(false);
  const [senderMailStatus, setSenderMailStatus] = useState(null);
  const [showTrackingModal, setShowTrackingModal] = useState(false);
  const [liveTrackingData, setLiveTrackingData] = useState(null);
  const [isRefreshingTracking, setIsRefreshingTracking] = useState(false);
  const [isSimulatingOpen, setIsSimulatingOpen] = useState(false);

  // Call Outcome State
  const [callStatus, setCallStatus] = useState('Connected');
  const [ivrExtension, setIvrExtension] = useState('');
  const [communicationOutcome, setCommunicationOutcome] = useState(selectedLq?.qualification_status === 'Lead Qualified' ? 'Lead Qualified' : '');
  const [callTranscriptNotes, setCallTranscriptNotes] = useState('');
  
  // Key People selection for call
  const [selectedContactId, setSelectedContactId] = useState('');
  const [selectedContactData, setSelectedContactData] = useState(null);
  const [generalCallSpokeTo, setGeneralCallSpokeTo] = useState('');
  const [generalCallDesignation, setGeneralCallDesignation] = useState('');

  // Detailed Call Form Fields
  const [requestedEmailConfirm, setRequestedEmailConfirm] = useState(prospect?.official_email_address || '');
  const [duplicateRequestedEmailContact, setDuplicateRequestedEmailContact] = useState(null);
  const [newRequestedContactName, setNewRequestedContactName] = useState('');
  const [newRequestedContactMobile, setNewRequestedContactMobile] = useState('');
  const [newRequestedContactDesignation, setNewRequestedContactDesignation] = useState('');

  useEffect(() => {
    if (requestedEmailConfirm && requestedEmailConfirm.trim()) {
      const found = prospect?.key_contacts?.find(c => 
        c.official_email && c.official_email.toLowerCase() === requestedEmailConfirm.toLowerCase()
      );
      if (found) {
        setDuplicateRequestedEmailContact(found);
      } else {
        setDuplicateRequestedEmailContact(null);
      }
    } else {
      setDuplicateRequestedEmailContact(null);
    }
  }, [requestedEmailConfirm, prospect]);

  const [callbackDate, setCallbackDate] = useState('');
  const [callbackTime, setCallbackTime] = useState('');
  const [callbackDescription, setCallbackDescription] = useState('');
  const [transferredPersonName, setTransferredPersonName] = useState('');
  const [transferredDesignation, setTransferredDesignation] = useState('');
  const [sharedContactName, setSharedContactName] = useState('');
  const [sharedContactDesignation, setSharedContactDesignation] = useState('');
  const [sharedContactPhone, setSharedContactPhone] = useState('');
  const [sharedContactEmail, setSharedContactEmail] = useState('');
  const [attendedMeeting, setAttendedMeeting] = useState(false);
  
  const [duplicateContact, setDuplicateContact] = useState(null);
  const [useDuplicateContact, setUseDuplicateContact] = useState(false);

  useEffect(() => {
    if ((sharedContactEmail && sharedContactEmail.trim()) || (sharedContactPhone && sharedContactPhone.trim())) {
      const found = prospect?.key_contacts?.find(c => 
        (sharedContactEmail && c.official_email && c.official_email.toLowerCase() === sharedContactEmail.toLowerCase()) ||
        (sharedContactPhone && c.phone_number && c.phone_number === sharedContactPhone)
      );
      if (found) {
        setDuplicateContact(found);
      } else {
        setDuplicateContact(null);
        setUseDuplicateContact(false);
      }
    } else {
      setDuplicateContact(null);
      setUseDuplicateContact(false);
    }
  }, [sharedContactEmail, sharedContactPhone, prospect]);
  const [notInterestedReason, setNotInterestedReason] = useState('');
  const [leadQualifiedDescription, setLeadQualifiedDescription] = useState('');
  const [meetingDate, setMeetingDate] = useState('');
  const [meetingTime, setMeetingTime] = useState('');
  const [meetingLink, setMeetingLink] = useState('');
  const [meetingProvider, setMeetingProvider] = useState('GOOGLE_MEET');
  const [calendarStatus, setCalendarStatus] = useState(null);
  const [calendarLoading, setCalendarLoading] = useState(false);
  const [createdMeeting, setCreatedMeeting] = useState(null);
  const [isCreatingMeeting, setIsCreatingMeeting] = useState(false);
  const [isRefreshingMeet, setIsRefreshingMeet] = useState(false);

  // Inbound State
  const [inboundMode, setInboundMode] = useState(false);
  const [inboundDate, setInboundDate] = useState(() => {
    const d = new Date();
    return d.toISOString().split('T')[0];
  });
  const [inboundTime, setInboundTime] = useState(() => {
    const d = new Date();
    return d.toTimeString().slice(0,5);
  });

  // Backend Outreach Logs State
  const [outreachLogs, setOutreachLogs] = useState([]);
  // === KEY FIX: On mount, always fetch fresh LQ data + outreach logs from backend ===
  // This ensures that email_status and communication history are NOT stale from props
  useEffect(() => {
    if (selectedLq?.id && prospect?.id) {
      // Fetch fresh LQ data to get persisted email_status
      api.get(`/lq-pipeline/${selectedLq.id}/`)
        .then(res => {
          const freshStatus = res.data?.email_status || 'Not Sent';
          setEmailProgress(freshStatus);
          setEmailCollapsed(freshStatus !== 'Not Sent');
        })
        .catch(err => console.error('Failed to fetch fresh LQ data', err));
      
      // Also fetch outreach logs immediately on open (not just on tab switch)
      fetchOutreachLogs();
        
      // Fetch sender mail account status
      api.get('/auth/mail-account/')
        .then(res => {
          if(res.data && res.data.length > 0) {
            setSenderMailStatus(res.data[0]);
          }
        }).catch(err => console.error('Failed to fetch mail account', err));
    }
  }, [selectedLq?.id]);

  // Live auto-sync for email replies while workspace modal is open
  useEffect(() => {
    if (!selectedLq?.id) return;
    if (emailProgress !== 'Sent' && emailProgress !== 'Waiting for Response') return;

    const interval = setInterval(async () => {
      try {
        await dispatch(syncMail()).unwrap();
        await fetchOutreachLogs();
        const res = await api.get(`/lq-pipeline/${selectedLq.id}/`);
        if (res.data?.email_status && res.data.email_status !== emailProgress) {
          setEmailProgress(res.data.email_status);
        }
      } catch (e) {
        // Silent background check
      }
    }, 12000);

    return () => clearInterval(interval);
  }, [selectedLq?.id, emailProgress, dispatch]);
  
  const fetchOutreachLogs = async (contactId) => {
    try {
      const logs = await dispatch(fetchCommunications(prospect.id)).unwrap();
      setOutreachLogs(logs);
      const cid = contactId !== undefined ? contactId : selectedContactId;
      const relevantLogs = cid
        ? logs.filter(log => log.prospect_contact === cid && log.activity_type === 'CALL')
        : logs.filter(log => !log.prospect_contact && log.activity_type === 'CALL');
      const latestCall = relevantLogs[0];
      if (latestCall) {
        setCallStatus(latestCall.status || 'Connected');
        setCommunicationOutcome(latestCall.outcome || '');
      }
    } catch (err) {
      console.error("Failed to fetch outreach logs", err);
    }
  };

  // Helpers for dropdown display
  const getContactLatestCall = (contactId) => {
    const relevantLogs = outreachLogs.filter(log => log.prospect_contact === contactId && log.activity_type === 'CALL');
    const latest = relevantLogs[0];
    if (latest) {
      if (latest.outcome) return `${latest.status} (${latest.outcome})`;
      return latest.status;
    }
    return null;
  };


  const isContactLockedCheck = (contactId) => {
    const relevantLogs = contactId
      ? outreachLogs.filter(log => log.prospect_contact === contactId && log.activity_type === 'CALL')
      : outreachLogs.filter(log => !log.prospect_contact && log.activity_type === 'CALL');
    const latest = relevantLogs[0];
    
    if (latest && (latest.outcome === 'Lead Qualified' || latest.outcome === 'Not Interested')) {
      return true;
    }

    const isIssuePending = selectedLq.pre_task_status === 'ISSUE_SENT_TO_PRE' || localIssueSent;
    if (isIssuePending && latest && latest.status === 'Invalid Number') {
      return true;
    }

    return false;
  };

  const getGeneralLatestCall = () => {
    const relevantLogs = outreachLogs.filter(log => !log.prospect_contact && log.activity_type === 'CALL');
    const latest = relevantLogs[0];
    if (latest) {
      if (latest.outcome) return `${latest.status} (${latest.outcome})`;
      return latest.status;
    }
    return null;
  };

  // When selected contact changes, restore their call state from logs
  useEffect(() => {
    if (outreachLogs.length === 0) return;
    const relevantLogs = selectedContactId
      ? outreachLogs.filter(log => log.prospect_contact === selectedContactId && log.activity_type === 'CALL')
      : outreachLogs.filter(log => !log.prospect_contact && log.activity_type === 'CALL');
    const latestCall = relevantLogs[0];
    if (latestCall) {
      setCallStatus(latestCall.status || 'Connected');
      setCommunicationOutcome(latestCall.outcome || '');
    } else {
      setCallStatus('Connected');
      setCommunicationOutcome('');
    }
    setCallTranscriptNotes('');
    setCallError('');
  }, [selectedContactId]);
  const isEmailSent = ['Sent', 'Waiting for Response', 'Received Response'].includes(emailProgress);
  const sentEmailData = outreachLogs.find(log => log.activity_type === 'EMAIL_SENT')?.outreach_email_detail;

  const handleOpenTrackingModal = async () => {
    setShowTrackingModal(true);
    if (sentEmailData?.id) {
      setIsRefreshingTracking(true);
      try {
        const res = await api.get(`/outreach/emails/${sentEmailData.id}/tracking-stats/`);
        setLiveTrackingData(res.data);
      } catch (err) {
        console.error("Failed to load tracking stats", err);
        setLiveTrackingData(sentEmailData);
      } finally {
        setIsRefreshingTracking(false);
      }
    } else {
      setLiveTrackingData(sentEmailData || null);
    }
  };

  const handleRefreshTracking = async () => {
    if (!sentEmailData?.id) return;
    setIsRefreshingTracking(true);
    try {
      await fetchOutreachLogs();
      const res = await api.get(`/outreach/emails/${sentEmailData.id}/tracking-stats/`);
      setLiveTrackingData(res.data);
      toast.success("Tracking stats refreshed!");
    } catch (err) {
      console.error("Failed to refresh tracking", err);
      toast.error("Could not refresh tracking stats");
    } finally {
      setIsRefreshingTracking(false);
    }
  };

  const fetchCalendarStatus = async () => {
    setCalendarLoading(true);
    try {
      const res = await api.get('/auth/google/calendar/status/');
      setCalendarStatus(res.data);
    } catch (e) {
      console.warn('Failed to fetch calendar status', e);
      setCalendarStatus({ is_connected: false, is_configured: false });
    } finally {
      setCalendarLoading(false);
    }
  };

  useEffect(() => {
    fetchCalendarStatus();
  }, []);

  const handleConnectCalendar = async () => {
    try {
      const res = await api.get('/auth/google/calendar/url/');
      const authUrl = res.data?.url || res.data?.authorization_url;
      if (authUrl) {
        localStorage.setItem('calendar_oauth_return_url', window.location.pathname + window.location.search);
        window.location.href = authUrl;
      } else {
        toast.error('Google Calendar authorization URL was not returned.');
      }
    } catch (e) {
      toast.error('Could not initiate Google Calendar connection.');
    }
  };

  const handleRefreshMeetLink = async () => {
    if (!createdMeeting?.id) return;
    setIsRefreshingMeet(true);
    try {
      const res = await api.post(`/meetings/${createdMeeting.id}/refresh-meet-link/`);
      setCreatedMeeting(res.data);
      if (res.data?.meeting_link) {
        setMeetingLink(res.data.meeting_link);
      }
      toast.success('Meeting link refreshed.');
    } catch (e) {
      toast.error(e.response?.data?.error || 'Failed to refresh Meet link.');
    } finally {
      setIsRefreshingMeet(false);
    }
  };

  const handleSimulateOpen = async () => {
    if (!sentEmailData?.id) return;
    setIsSimulatingOpen(true);
    try {
      const res = await api.post(`/outreach/emails/${sentEmailData.id}/simulate-open/`);
      if (res.data?.data) {
        setLiveTrackingData(res.data.data);
      }
      await fetchOutreachLogs();
      toast.success("Test open ping recorded!");
    } catch (err) {
      console.error("Failed to simulate open", err);
      toast.error("Could not record test open");
    } finally {
      setIsSimulatingOpen(false);
    }
  };

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

  const activeEmailTracking = liveTrackingData || sentEmailData;

  const toggleToRecipient = (email) => {
    if (toEmails.includes(email)) setToEmails(toEmails.filter(e => e !== email));
    else setToEmails([...toEmails, email]);
  };
  const toggleCcRecipient = (email) => {
    if (ccEmails.includes(email)) setCcEmails(ccEmails.filter(e => e !== email));
    else setCcEmails([...ccEmails, email]);
  };
const handleAddCustomRecipient = (e) => {
    e.preventDefault();
    const em = customRecipientInput.trim();
    if (em && !ccEmails.includes(em) && !toEmails.includes(em)) {
      setCcEmails([...ccEmails, em]);
      setCustomRecipientInput('');
    }
  };

  const handleFileChange = (e) => {
    const files = Array.from(e.target.files);
    setAttachmentError('');
    let validFiles = [];
    let currentTotalSize = attachments.reduce((acc, file) => acc + file.size, 0);
    
    for (const file of files) {
      if (file.size > 10 * 1024 * 1024) {
        setAttachmentError(`File ${file.name} exceeds the 10MB limit.`);
        return;
      }
      const ext = file.name.split('.').pop().toLowerCase();
      const blockedExts = ['exe', 'bat', 'cmd', 'js', 'ps1', 'vbs', 'scr'];
      if (blockedExts.includes(ext)) {
        setAttachmentError(`File type .${ext} is not allowed for email attachments.`);
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
    e.target.value = '';
  };

  const removeAttachment = (index) => {
    setAttachments(prev => prev.filter((_, i) => i !== index));
    setAttachmentError('');
  };

  const handleSendIntroEmail = async (e) => {
    e.preventDefault();
    if (toEmails.length === 0 && ccEmails.length === 0) return;
    if (isSendingEmail) return;
    
    setIsSendingEmail(true);
    try {
      const formData = new FormData();
      formData.append('prospect', prospect.id);
      formData.append('subject', emailSubject);
      formData.append('body', emailBody);
      if (templateSelection.templateId || templateSelection.signatureId) {
        if (templateSelection.templateId) formData.append('template_id', templateSelection.templateId);
        if (templateSelection.signatureId) formData.append('signature_id', templateSelection.signatureId);
        formData.append('body_edited', String(!templateSelection.templateId || emailBody !== templateSelection.baseBody));
      }
      formData.append('open_tracking_enabled', String(openTrackingEnabled));
      
      const recList = [
        ...toEmails.map(r => ({ email_address: r, recipient_type: 'TO' })),
        ...ccEmails.map(r => ({ email_address: r, recipient_type: 'CC' }))
      ];
      formData.append('recipients', JSON.stringify(recList));

      attachments.forEach(file => {
        formData.append('attachments', file);
      });
      
      const res = await dispatch(sendOutreachEmail(formData)).unwrap();
      
      // Update UI explicitly on success
      setEmailProgress('Waiting for Response');
      setEmailCollapsed(true);
      
      fetchOutreachLogs();
      toast.success("Email sent successfully!");
      notifyMailSent();
    } catch (err) {
      console.error("Failed to log email", err);
      const errorMsg = err.error || err.detail || (typeof err === 'string' ? err : JSON.stringify(err));
      toast.error("Failed to send email: " + errorMsg);
    } finally {
      setIsSendingEmail(false);
    }
  };

  const handleUpdateEmailProgressStatus = async (status) => {
    setEmailProgress(status);
    if (['Sent', 'Waiting for Response', 'Received Response'].includes(status)) {
      setEmailCollapsed(true);
    }
    
    try {
      await api.patch(`/lq-pipeline/${selectedLq.id}/`, { email_status: status });
      // Depending on requirements, we can also manually create a CommunicationActivity here, 
      // but usually the email progress is sufficient unless a response is received.
      fetchOutreachLogs();
    } catch (err) {
      console.error("Failed to update email status", err);
    }
  };

  const [callError, setCallError] = useState('');
  const [localIssueSent, setLocalIssueSent] = useState(false);
  const [isSubmittingActivity, setIsSubmittingActivity] = useState(false);

  const handleSaveInbound = async (e) => {
    e.preventDefault();
    if (!callTranscriptNotes.trim()) {
      setCallError('Notes are required for inbound communications.');
      return;
    }
    
    setCallError('');
    setIsSubmittingActivity(true);
    try {
      const callPhone = selectedContactId
        ? (prospect?.key_contacts?.find(c => c.id === selectedContactId)?.phone_number || prospect.official_phone_number || '')
        : (prospect.official_phone_number || '');
        
      await dispatch(recordCall({
        prospect: prospect.id,
        prospect_contact: selectedContactId || null,
        call_status: 'Inbound',
        communication_outcome: 'Inbound Message',
        company_phone: callPhone,
        notes: `[Data Entered For: ${inboundDate} at ${inboundTime}]\n${callTranscriptNotes.trim()}`,
        direction: 'INBOUND',
        call_started_at: localDateTimeToUTC(inboundDate, inboundTime, user?.timezone)
      })).unwrap();

      fetchOutreachLogs();
      setCallTranscriptNotes('');
      toast.success("Inbound activity recorded successfully.");
    } catch (err) {
      console.error("Failed to save inbound activity", err);
      setCallError('Failed to save inbound activity. Please try again.');
    } finally {
      setIsSubmittingActivity(false);
    }
  };

  const handleLogCallOutcome = async (e) => {
    e.preventDefault();
    setCallError('');

    // === VALIDATION ===
    // 1. If 'Connected', must select a communication outcome
    if (callStatus === 'Connected') {
      if (!communicationOutcome) {
        setCallError('Please select a Communication Progress Outcome (Step 2).');
        return;
      }
      
      // 1b. If calling general company line, must provide Person Contacted
      if (selectedContactId === '') {
        if (!generalCallSpokeTo.trim()) {
          setCallError('Please provide the Name of the Person Contacted for the Company Official Number.');
          return;
        }
      }
    }
    // 2. Call Back Later requires date and time
    if (callStatus === 'Connected' && communicationOutcome === 'Call Back Later') {
      if (!callbackDate || !callbackTime) {
        setCallError('Date and Time are required for "Call Back Later".');
        return;
      }
    }
    // 3b. Not Interested — description (reason) is MANDATORY
    if (callStatus === 'Connected' && communicationOutcome === 'Not Interested') {
      if (!notInterestedReason.trim()) {
        setCallError('Description (Reason for Disinterest) is required for "Not Interested".');
        return;
      }
    }
    // 3c. Lead Qualified
    if (callStatus === 'Connected' && communicationOutcome === 'Lead Qualified') {
      if (!meetingDate || !meetingTime) {
        setCallError('Meeting Date and Time are required.');
        return;
      }
      if (!leadQualifiedDescription.trim()) {
        setCallError('Meeting Agenda is required.');
        return;
      }
    }
    // 3d. Requested Email Contact validation
    if (callStatus === 'Connected' && communicationOutcome === 'Requested Email') {
      if (!requestedEmailConfirm.trim()) {
        setCallError('Confirm Email Address is required.');
        return;
      }
      if (!duplicateRequestedEmailContact) {
        if (!newRequestedContactName.trim() || !newRequestedContactDesignation.trim()) {
          setCallError('Name and Designation are required to register the new email contact.');
          return;
        }
      }
    }
    // 4. Prevent pure duplicate submissions (if user didn't pick the existing contact)
    if (callStatus === 'Connected' && communicationOutcome === 'Shared Another Contact') {
      if (!useDuplicateContact && duplicateContact) {
        setCallError('This contact already exists. Please use "Select this contact" or enter a different contact.');
        return;
      }
    }
    // 5. Must have some meaningful content — at least notes or an outcome
    if (!communicationOutcome && !callTranscriptNotes.trim() && callStatus === 'Connected') {
      setCallError('Please add notes or select an outcome before saving.');
      return;
    }

    // === BUILD LOG ===
    let detailsParts = [`Call Status: ${callStatus}`];
    if (ivrExtension.trim()) detailsParts.push(`IVR Ext: ${ivrExtension.trim()}`);
    if (selectedContactId === '' && (generalCallSpokeTo.trim() || generalCallDesignation.trim())) {
      let spokeStr = [];
      if (generalCallSpokeTo.trim()) spokeStr.push(generalCallSpokeTo.trim());
      if (generalCallDesignation.trim()) spokeStr.push(`(${generalCallDesignation.trim()})`);
      detailsParts.push(`Spoke To: ${spokeStr.join(' ')}`);
    }
    
    if (callStatus === 'Connected' && communicationOutcome) {
      if (communicationOutcome === 'Requested Email') detailsParts.push(`Outcome: Requested Email (Confirmed: ${requestedEmailConfirm})`);
      else if (communicationOutcome === 'Call Back Later') {
        detailsParts.push(`Outcome: Call Back Later (Scheduled: ${callbackDate} at ${callbackTime})`);
        if (callbackDescription) detailsParts.push(`Description: ${callbackDescription}`);
      }
      else if (communicationOutcome === 'Call Transferred') detailsParts.push(`Outcome: Transferred to ${transferredPersonName} (${transferredDesignation})`);
      else if (communicationOutcome === 'Shared Another Contact') detailsParts.push(`Outcome: Shared Contact ${sharedContactName} - ${sharedContactDesignation} (Ph: ${sharedContactPhone || 'N/A'}, Email: ${sharedContactEmail || 'N/A'})`);
      else if (communicationOutcome === 'Not Interested') detailsParts.push(`Outcome: Not Interested (Reason: ${notInterestedReason})`);
      else if (communicationOutcome === 'Lead Qualified') {
        detailsParts.push(`Outcome: Lead Qualified (Meeting Scheduled: ${meetingDate} at ${meetingTime})`);
        if (meetingLink) detailsParts.push(`Link: ${meetingLink}`);
        detailsParts.push(`Agenda: ${leadQualifiedDescription}`);
      }
    }
    
    if (callTranscriptNotes.trim()) detailsParts.push(`Notes: ${callTranscriptNotes.trim()}`);
    
    let callOutcome = communicationOutcome || '';
    
    // Check if we need to create a new Requested Email contact
    if (callStatus === 'Connected' && communicationOutcome === 'Requested Email' && !duplicateRequestedEmailContact) {
      try {
        await api.post(`/prospects/${prospect.id}/add-contact/`, {
          contact_name: newRequestedContactName,
          designation: newRequestedContactDesignation,
          phone_number: newRequestedContactMobile,
          official_email: requestedEmailConfirm,
          source: 'LQ'
        });
        toast.success('New Key Contact registered successfully.');
      } catch (err) {
        console.error("Failed to create requested email contact", err);
        setCallError('Failed to save the new Key Contact. Please try again.');
        return;
      }
    }
    
    try {
      const callPhone = selectedContactId
        ? (prospect?.key_contacts?.find(c => c.id === selectedContactId)?.phone_number || prospect.official_phone_number || '')
        : (prospect.official_phone_number || '');
      await dispatch(recordCall({
        prospect: prospect.id,
        prospect_contact: selectedContactId || null,
        call_status: callStatus,
        communication_outcome: communicationOutcome || '',
        company_phone: callPhone,
        ivr_extension: ivrExtension,
        notes: detailsParts.join(' | ')
      })).unwrap();
      
      // If Invalid Number, report issue to PRE and close
      if (callStatus === 'Invalid Number') {
        try {
          const fieldToMark = selectedContactId ? 'keyContacts' : 'contactNo';
          const updatedChecklist = { ...verificationFields, [fieldToMark]: 'Incorrect' };

          await api.post(`/lq-pipeline/${selectedLq.id}/report-issue/`, {
            issue_category: 'Invalid Phone Number',
            issue_details: `The phone number is invalid. Please find the correct contact number.`,
            verification_checklist: updatedChecklist
          });
          toast.info(`Issue reported to PRE: Invalid Number (${fieldToMark === 'keyContacts' ? 'Key Contact' : 'Official Number'}).`);
          setLocalIssueSent(true);
        } catch (err) {
          console.error("Failed to report invalid number issue", err);
        }
      }

      fetchOutreachLogs();
    } catch (err) {
      console.error("Failed to log call outcome", err);
      setCallError('Failed to save activity. Please try again.');
      return;
    }
    
    setCallTranscriptNotes('');
    setCommunicationOutcome('');
    setCallError('');

    // Reminders
    if (callStatus === 'Connected' && communicationOutcome === 'Call Back Later') {
      if (callbackDate && callbackTime) {
        try {
          const scheduled_datetime = localDateTimeToUTC(callbackDate, callbackTime, user?.timezone);
          api.post('/reminders/', { prospect: prospect.id, prospect_contact: selectedContactId || null, scheduled_datetime, description: callbackDescription || 'Call Back Later' });
          setCallbackDate(''); setCallbackTime(''); setCallbackDescription('');
        } catch (e) {}
      }
    }

    // If Shared Another Contact and NOT a duplicate, save to backend
    if (callStatus === 'Connected' && communicationOutcome === 'Shared Another Contact' && sharedContactName.trim() && !useDuplicateContact) {
      try {
        await api.post(`/prospects/${prospect.id}/add-contact/`, {
          contact_name: sharedContactName.trim(),
          designation: sharedContactDesignation.trim(),
          official_email: sharedContactEmail.trim(),
          phone_number: sharedContactPhone.trim()
        });
      } catch (error) {
        console.error("Failed to add key contact", error);
      }
    }
    // Always reset shared contact form
    if (communicationOutcome === 'Shared Another Contact') {
      setSharedContactName('');
      setSharedContactDesignation('');
      setSharedContactPhone('');
      setSharedContactEmail('');
      setDuplicateContact(null);
      setUseDuplicateContact(false);
    }

    // === STATUS UPDATES & MODAL CLOSE AFTER SAVE ===
    // Not Interested
    if (callStatus === 'Connected' && communicationOutcome === 'Not Interested') {
      setNotInterestedReason('');
      toast.success("Activity saved successfully. Prospect marked as Not Interested.");
      return;
    }

    // Prospect Selected → set qualification_status to 'Lead Qualified' + close
    if (callStatus === 'Connected' && communicationOutcome === 'Lead Qualified') {
      setIsCreatingMeeting(true);
      try {
        let savedMeeting = null;
        // Save Meeting if date & time exist
        if (meetingDate && meetingTime) {
          const scheduled_datetime = localDateTimeToUTC(meetingDate, meetingTime, user?.timezone);
          const clientReqId = window.crypto?.randomUUID ? window.crypto.randomUUID() : (`req-${Date.now()}-${Math.random().toString(36).slice(2)}`);
          const payload = {
            prospect: prospect.id,
            prospect_contact: selectedContactId || null,
            scheduled_datetime,
            agenda: leadQualifiedDescription,
            meeting_provider: 'GOOGLE_MEET',
            client_request_id: clientReqId,
          };
          const meetRes = await api.post(`/meetings/`, payload);
          savedMeeting = meetRes?.data;
          setCreatedMeeting(savedMeeting);
          if (savedMeeting?.meeting_link) {
            setMeetingLink(savedMeeting.meeting_link);
          }
        }

        await api.patch(`/lq-pipeline/${selectedLq.id}/`, { 
            qualification_status: 'Lead Qualified',
            attended_meeting: attendedMeeting 
        });

        toast.success(
          savedMeeting?.meeting_provider === 'GOOGLE_MEET'
            ? (savedMeeting.conference_status === 'CONFIRMED'
                ? 'Meeting scheduled with Google Meet! Link ready.'
                : 'Meeting scheduled. Google Meet link is being generated.')
            : 'Activity saved successfully. Lead Qualified!'
        );
      } catch (err) {
        console.error('Failed to update qualification status or schedule meeting', err);
        const errMsg = err.response?.data?.error || err.response?.data?.detail || 'Failed to update qualification status or schedule meeting';
        toast.error(errMsg);
        if (
          err.response?.status === 409 ||
          err.response?.data?.code === 'calendar_reauth_required' ||
          err.response?.data?.code === 'calendar_not_connected' ||
          String(errMsg).toLowerCase().includes('reconnect')
        ) {
          setCalendarStatus({ is_connected: false, is_configured: true, email: '' });
        }
        setIsCreatingMeeting(false);
        return;
      } finally {
        setIsCreatingMeeting(false);
      }
      return;
    }
    
    toast.success("Activity saved successfully.");
  };

  const getFieldValue = (key) => {
    switch (key) {
      case 'companyName': return prospect.company_name || '-';
      case 'country': return prospect.country_head_office || '-';
      case 'address': return prospect.complete_address || '-';
      case 'website': return prospect.official_website_url || '-';
      case 'linkedIn': return prospect.linkedin_company_page || '-';
      case 'email': return prospect?.official_email_address || '-';
      case 'contactNo': return prospect.official_phone_number || '-';
      case 'productService': return prospect.primary_offering_type || '-';
      case 'primaryIndustries': return prospect.primary_industries || '-';
      case 'companyStructure': return prospect.company_structure || '-';
      case 'operationalStatus': return prospect.operational_status || '-';
      case 'marketEvents': return prospect.market_events?.length ? prospect.market_events.map(e => e.name).join(', ') : '-';
      case 'keyContacts': return prospect.key_contacts?.length ? prospect.key_contacts.map(c => `${c.contact_name} (${c.designation || 'No Designation'}) - ${c.official_email || 'No Email'}`).join(', ') : '-';
      case 'products': return prospect.products?.length ? prospect.products.map(p => p.name).join(', ') : '-';
      case 'services': return prospect.services?.length ? prospect.services.map(p => p.name).join(', ') : '-';
      case 'solutions': return prospect.solutions?.length ? prospect.solutions.map(p => p.name).join(', ') : '-';
      default: return '-';
    }
  };

  const fieldNames = {
    companyName: 'Company Name',
    country: 'Country',
    address: 'Address',
    website: 'Website',
    linkedIn: 'LinkedIn Page',
    email: 'Official Email',
    contactNo: 'Contact No.',
    productService: 'Product, Service & Solution',
    primaryIndustries: 'Primary Industries',
    companyStructure: 'Company Structure',
    operationalStatus: 'Operational Status',
    marketEvents: 'Market Events',
    keyContacts: 'Key Contacts',
    products: 'Products',
    services: 'Services',
    solutions: 'Solutions'
  };

  // Helper for automated issues
  const incorrectFields = Object.keys(verificationFields).filter(key => verificationFields[key] === 'Incorrect');
  const autoIssueCategory = incorrectFields.map(key => fieldNames[key]).join(', ');
  const autoDetails = incorrectFields.length > 0 
    ? `The following fields are incorrect and need to be fixed by PRE:\n${incorrectFields.map(k => `- ${fieldNames[k]}`).join('\n')}` 
    : '';

  return (
    <div className="fixed inset-0 bg-slate-900/70 backdrop-blur-sm flex items-center justify-center p-4 z-50 font-sans">
      <div className="bg-white rounded-2xl shadow-2xl max-w-5xl w-full overflow-hidden border border-slate-200 flex flex-col max-h-[92vh]">
        {/* Modal Header */}
        <div className="bg-gradient-to-r from-emerald-950 via-slate-900 to-indigo-950 p-5 text-white flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div>
              <div className="flex items-center gap-2">
              </div>
              <h3 className="text-xl font-bold text-white mt-1">{prospect.company_name}</h3>
            </div>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-white p-1.5 rounded-xl hover:bg-slate-800 transition cursor-pointer">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Navigation Tabs */}
        {initialTab !== 'outreach' && (
          <div className="bg-slate-100 border-b border-slate-200 px-6 pt-3 flex items-center gap-2 shrink-0">
            <button
              onClick={() => setActiveTab('verification')}
              className={`px-4 py-2.5 font-extrabold text-xs rounded-t-xl transition flex items-center gap-2 cursor-pointer ${
                activeTab === 'verification' ? 'bg-white text-slate-900 border-t-2 border-sky-600 shadow-sm' : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/60'
              }`}
            >
              <Shield className={`w-4 h-4 ${activeTab === 'verification' ? 'text-sky-600' : 'text-slate-400'}`} />
              <span>Field Verification & Data Details</span>
            </button>
            <button
              onClick={() => setActiveTab('outreach')}
              className={`px-4 py-2.5 font-extrabold text-xs rounded-t-xl transition flex items-center gap-2 cursor-pointer ${
                activeTab === 'outreach' ? 'bg-white text-slate-900 border-t-2 border-emerald-600 shadow-sm' : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200/60'
              }`}
            >
              {isVerified ? (
                <Phone className={`w-4 h-4 ${activeTab === 'outreach' ? 'text-emerald-600' : 'text-slate-400'}`} />
              ) : (
                <Lock className="w-4 h-4 text-amber-500" />
              )}
              <span>Outreach & Call Outcomes</span>
              {!isVerified && <span className="px-1.5 py-0.5 bg-amber-100 text-amber-800 text-[10px] rounded font-bold border border-amber-300">Locked</span>}
            </button>
          </div>
        )}

        {/* Modal Scrollable Content Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6 bg-slate-50">
          {activeTab === 'verification' && (
            <div className="space-y-6">
              <div className="p-4 bg-sky-50 border border-sky-200 rounded-xl flex items-start gap-3">
                <div className="w-8 h-8 rounded-full bg-sky-600 text-white font-black flex items-center justify-center shrink-0 mt-0.5 text-sm">
                  <Shield className="w-4 h-4" />
                </div>
                <div>
                  <h4 className="font-extrabold text-sky-950 text-sm">Prospect Field Verification Workspace</h4>
                  <p className="text-xs text-sky-800 mt-0.5">Validate master prospect information before initiating outreach.</p>
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                {/* Left Side: PRE Master Data */}
                <div className="space-y-4">
                  <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
                    <div className="flex items-center justify-between mb-4 pb-2 border-b border-slate-100">
                      <h3 className="font-bold text-slate-800">PRE Master Data</h3>
                      <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider bg-slate-100 px-2 py-1 rounded">Read-Only</span>
                    </div>
                    <div className="space-y-3">
                      <div>
                        <span className="block text-[10px] font-bold text-slate-400 uppercase">Company Name:</span>
                        <span className="font-medium text-sm text-slate-900">{prospect.company_name}</span>
                      </div>
                      <div>
                        <span className="block text-[10px] font-bold text-slate-400 uppercase">Country:</span>
                        <span className="font-medium text-sm text-slate-900">{prospect.country_head_office}</span>
                      </div>
                      <div>
                        <span className="block text-[10px] font-bold text-slate-400 uppercase">Industries:</span>
                        <span className="font-medium text-sm text-slate-900">{prospect.primary_industries}</span>
                      </div>
                    </div>
                  </div>

                  {hasIncorrect && (
                    <div className="bg-amber-50 p-5 rounded-xl border border-amber-200 shadow-sm">
                      <h3 className="font-bold text-amber-900 mb-3 flex items-center gap-2">
                        <AlertTriangle className="w-4 h-4 text-amber-600" />
                        Issue Report (Auto-Generated)
                      </h3>
                      <div className="space-y-3">
                        <div>
                          <label className="block text-[10px] font-bold text-amber-700 uppercase mb-1">Issue Category</label>
                          <input readOnly type="text" className="w-full p-2 border border-amber-200 rounded-xl text-sm bg-white text-amber-900 font-medium" value={autoIssueCategory} />
                        </div>
                        <div>
                          <label className="block text-[10px] font-bold text-amber-700 uppercase mb-1">Details</label>
                          <textarea readOnly className="w-full p-2 border border-amber-200 rounded-xl text-sm bg-white text-amber-900 font-medium" rows="3" value={autoDetails}></textarea>
                        </div>
                      </div>
                    </div>
                  )}
                </div>

                {/* Right Side: Verification Checklist */}
                <div className="space-y-4">
                  <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
                    <h3 className="font-bold text-slate-800 mb-4 pb-2 border-b border-slate-100">Verification Checklist</h3>
                    <div className="space-y-3">
                      {Object.entries(fieldNames).map(([key, label]) => (
                        <div key={key} className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 p-3 bg-slate-50 border border-slate-100 rounded-xl">
                          <div className="flex-1 min-w-0 pr-4">
                            <div className="flex items-center gap-2 mb-1">
                              <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">{label}</label>
                              {isConfirmingFixes && correctedFields.includes(key) && (
                                <span className="px-1.5 py-0.5 bg-emerald-100 text-emerald-700 text-[9px] font-black rounded uppercase tracking-widest border border-emerald-200">Fixed by PRE</span>
                              )}
                            </div>
                            <div className="text-sm font-medium text-slate-900 truncate" title={getFieldValue(key)}>{getFieldValue(key)}</div>
                          </div>
                          <div className="flex bg-white rounded-xl border border-slate-200 overflow-hidden shrink-0 shadow-sm mt-2 sm:mt-0">
                            <button
                              type="button"
                              onClick={() => handleFieldToggle(key, 'Correct')}
                              className={`px-3 py-1.5 text-xs font-bold transition ${verificationFields[key] === 'Correct' ? 'bg-emerald-600 text-white' : 'text-slate-500 hover:bg-slate-50'}`}
                            >Correct</button>
                            <button
                              type="button"
                              onClick={() => handleFieldToggle(key, 'Incorrect')}
                              className={`px-3 py-1.5 text-xs font-bold transition border-l border-slate-200 ${verificationFields[key] === 'Incorrect' ? 'bg-amber-600 text-white' : 'text-slate-500 hover:bg-slate-50'}`}
                            >Incorrect</button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
              
              <div className="flex justify-end gap-3 pt-4 border-t border-slate-200">
                {hasIncorrect ? (
                  <button onClick={handleSubmitIssue} className="px-5 py-2 text-sm font-bold text-white bg-amber-600 hover:bg-amber-700 rounded-lg transition shadow-sm flex items-center gap-2">
                    <AlertTriangle className="w-4 h-4" /> Submit Issue to PRE
                  </button>
                ) : allCorrect ? (
                  <button onClick={async () => { 
                    if (isConfirmingFixes) {
                      await dispatch(confirmReverification(selectedLq.id));
                    }
                    if (!localVerified) {
                      await handleReadyForOutreach(true); 
                      setLocalVerified(true);
                    }
                    setActiveTab('outreach'); 
                  }} className="px-5 py-2 text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg transition shadow-sm flex items-center gap-2">
                    <CheckCircle className="w-4 h-4" /> {(selectedLq?.verification_status === 'Verified' || localVerified) ? 'Move back to Outreach' : 'Ready for Outreach'}
                  </button>
                ) : (
                  <button disabled className="px-5 py-2 text-sm font-bold text-slate-400 bg-slate-100 rounded-lg cursor-not-allowed">
                    Verify All Fields
                  </button>
                )}
              </div>
            </div>
          )}

          {activeTab === 'outreach' && (

            <div className="space-y-6">
              {!isVerified ? (
                <div className="p-8 bg-white border border-slate-200 rounded-2xl text-center space-y-4 shadow-sm">
                  <div className="w-14 h-14 rounded-full bg-amber-100 text-amber-700 mx-auto flex items-center justify-center font-black shadow-sm">
                    <Lock className="w-7 h-7 text-amber-600" />
                  </div>
                  <div>
                    <span className="px-2.5 py-1 rounded bg-amber-100 text-amber-800 font-extrabold text-[11px] uppercase tracking-wider border border-amber-200">Verification Required</span>
                    <h4 className="text-lg font-black text-slate-900 mt-2">🔒 Outreach & Call Outcomes Locked</h4>
                    <p className="text-sm text-slate-600 mt-1 max-w-md mx-auto leading-relaxed">Outreach features activate only after the prospect’s 8 data fields are fully verified.</p>
                  </div>
                  <button onClick={() => setActiveTab('verification')} className="px-5 py-2.5 bg-sky-600 hover:bg-sky-700 text-white font-extrabold text-sm rounded-xl transition cursor-pointer shadow-md inline-flex items-center gap-2">
                    <Shield className="w-4 h-4" /> Go to Field Verification
                  </button>
                </div>
              ) : (
                <div className="space-y-6">
                  {/* Email Section */}
                  <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm">
                    <div className="bg-gradient-to-r from-slate-900 to-indigo-950 p-4 text-white flex flex-col md:flex-row md:items-center justify-between gap-4">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-xl bg-indigo-500/20 text-indigo-300 border border-indigo-400/30 flex items-center justify-center font-bold shrink-0">
                          <Mail className="w-5 h-5" />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <h4 className="text-sm font-extrabold text-white">{prospect.company_name}</h4>
                            {/* Email open tracking indicator */}
                            {isEmailSent && (
                              <button
                                type="button"
                                onClick={() => handleOpenTrackingModal()}
                                className={`px-2.5 py-0.5 rounded text-[10px] font-extrabold uppercase border flex items-center gap-1 cursor-pointer transition hover:scale-105 ${
                                  sentEmailData?.open_tracking_enabled === false
                                    ? 'bg-slate-800 text-slate-400 border-slate-700'
                                    : sentEmailData?.is_opened
                                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-400/30'
                                      : 'bg-slate-700 text-slate-300 border-slate-600'
                                }`}
                                title={sentEmailData?.open_tracking_enabled === false ? 'Open tracking was disabled for deliverability' : 'Click to view detailed email tracking analytics'}
                              >
                                {sentEmailData?.open_tracking_enabled === false
                                  ? '🛡️ Untracked'
                                  : sentEmailData?.is_opened
                                    ? `👁 Viewed${(sentEmailData?.open_count || 1) > 1 ? ` (${sentEmailData.open_count}x)` : ''}`
                                    : 'Not Viewed'}
                              </button>
                            )}
                          </div>
                          <p className="text-xs text-slate-300 mt-0.5">{isEmailSent ? '' : 'Send introductory email to enable call outcomes.'}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        <div className="hidden sm:flex items-center gap-1 bg-slate-800/80 p-1 rounded-xl border border-slate-700/80 text-[11px]">
                          {['Sent', 'Waiting for Response', 'Received Response'].map(st => (
                            <button key={st} disabled={true} className={`px-2.5 py-1 rounded-lg font-bold transition cursor-not-allowed ${emailProgress === st ? 'bg-indigo-600 text-white' : 'text-slate-400 opacity-70'}`}>{st}</button>
                          ))}
                        </div>
                        {/* EMAIL TRACK BUTTON ON HEADER */}
                        {isEmailSent && (
                          <button
                            type="button"
                            onClick={() => handleOpenTrackingModal()}
                            className="px-3 py-1.5 bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-extrabold text-xs rounded-xl transition flex items-center gap-1.5 border border-indigo-400/40 shadow-sm cursor-pointer"
                            title="Open advanced email tracking analytics"
                          >
                            <BarChart2 className="w-3.5 h-3.5 text-indigo-200" />
                            <span>Email Track</span>
                          </button>
                        )}
                        {(emailProgress === 'Sent' || emailProgress === 'Waiting for Response') && (
                          <button
                            type="button"
                            onClick={async (e) => {
                              e.stopPropagation();
                              const toastId = toast.loading('Checking for replies...');
                              try {
                                await dispatch(syncMail()).unwrap();
                                await fetchOutreachLogs();
                                try {
                                  const res = await api.get(`/lq-pipeline/${selectedLq.id}/`);
                                  if (res.data?.email_status) {
                                    setEmailProgress(res.data.email_status);
                                  }
                                } catch (e) {
                                  console.error("Failed to refresh pipeline status after sync", e);
                                }
                                toast.dismiss(toastId);
                                toast.success('Inbox synced!');
                              } catch (err) {
                                toast.dismiss(toastId);
                                toast.error('Sync failed.');
                              }
                            }}
                            className="px-2.5 py-1 bg-sky-600 hover:bg-sky-500 text-white font-extrabold text-[10px] rounded-xl uppercase tracking-wider transition border border-sky-400/40"
                          >
                            ↻ Sync
                          </button>
                        )}
                        <button onClick={() => setEmailCollapsed(!emailCollapsed)} className="px-3 py-1.5 bg-white/10 hover:bg-white/20 text-white font-extrabold text-xs rounded-xl transition flex items-center gap-1.5 border border-white/10">
                          {emailCollapsed ? <><span className="hidden sm:inline">{isEmailSent ? 'View Full Mail' : 'Expand Draft'}</span><ChevronDown className="w-3.5 h-3.5" /></> : <><span className="hidden sm:inline">Collapse</span><ChevronUp className="w-3.5 h-3.5" /></>}
                        </button>
                      </div>
                    </div>
                    {!emailCollapsed && (
                      <div className="p-5 bg-slate-50 border-t border-slate-200 space-y-4 text-xs">
                        <div className="space-y-2">
                          <label className="block font-extrabold text-slate-800 uppercase tracking-wider text-[10px]">Select Introduction Email Recipients</label>
                          <div className="grid grid-cols-1 gap-2">
                            {prospect?.key_contacts?.map(contact => contact.official_email && (
                              <div key={contact.id} className={`flex flex-col gap-2 p-2.5 rounded-xl border transition ${toEmails.includes(contact.official_email) ? 'bg-indigo-50 border-indigo-300' : 'bg-white border-slate-200'}`}>
                                <label className="flex items-center gap-2.5 cursor-pointer">
                                  <input type="checkbox" checked={toEmails.includes(contact.official_email)} onChange={() => toggleToRecipient(contact.official_email)} disabled={isEmailSent} className="accent-indigo-600 disabled:opacity-50" />
                                  <div className="overflow-hidden flex-1">
                                    <span className={`block truncate text-sm ${toEmails.includes(contact.official_email) ? 'text-indigo-950 font-bold' : 'text-slate-700'}`}>{contact.official_email}</span>
                                    <span className="text-[10px] text-slate-400 font-semibold">{contact.contact_name} ({contact.designation}) - TO</span>
                                  </div>
                                </label>
                              </div>
                            ))}
                            
                            {prospect?.official_email_address && (
                              <div className={`flex flex-col gap-2 p-2.5 rounded-xl border transition ${ccEmails.includes(prospect.official_email_address) ? 'bg-indigo-50 border-indigo-300' : 'bg-white border-slate-200'}`}>
                                <label className="flex items-center gap-2.5 cursor-pointer">
                                  <input type="checkbox" checked={ccEmails.includes(prospect.official_email_address)} onChange={() => toggleCcRecipient(prospect.official_email_address)} disabled={isEmailSent} className="accent-indigo-600 disabled:opacity-50" />
                                  <div className="overflow-hidden flex-1">
                                    <span className={`block truncate text-sm ${ccEmails.includes(prospect.official_email_address) ? 'text-indigo-950 font-bold' : 'text-slate-700'}`}>{prospect.official_email_address}</span>
                                    <span className="text-[10px] text-slate-400 font-semibold">Reception / Official Email - CC</span>
                                  </div>
                                </label>

                              </div>
                            )}
                            
                            {(!prospect?.official_email_address && (!prospect?.key_contacts || prospect.key_contacts.length === 0)) && (
                              <div className="p-2.5 rounded-xl border border-amber-200 bg-amber-50 text-amber-700 text-xs font-semibold">
                                No official company email or key contacts found for this prospect. Please update the prospect details.
                              </div>
                            )}

                            {ccEmails.filter(email => email !== prospect?.official_email_address).map((email) => (
                              <label key={email} className="flex items-center gap-2.5 p-2.5 rounded-xl border transition cursor-pointer bg-slate-50 border-indigo-200 text-slate-800 font-bold">
                                <input type="checkbox" checked={true} onChange={() => toggleCcRecipient(email)} disabled={isEmailSent} className="accent-indigo-600 disabled:opacity-50" />
                                <div className="overflow-hidden">
                                  <span className="block truncate text-sm">{email}</span>
                                  <span className="text-[10px] text-indigo-500 font-extrabold uppercase">CC</span>
                                </div>
                              </label>
                            ))}
                          </div>

                        </div>
                        <TemplatePicker
                          prospect={prospect}
                          toEmails={toEmails}
                          ccEmails={ccEmails}
                          emailSubject={emailSubject}
                          emailBody={emailBody}
                          setEmailSubject={setEmailSubject}
                          setEmailBody={setEmailBody}
                          disabled={isEmailSent}
                          selection={templateSelection}
                          setSelection={setTemplateSelection}
                        />
                        <div>
                          <label className="block font-extrabold text-slate-800 mb-1 uppercase tracking-wider text-[10px]">Email Subject</label>
                          <input type="text" value={emailSubject} onChange={(e) => setEmailSubject(e.target.value)} disabled={isEmailSent} className="w-full p-2.5 bg-white border border-slate-200 rounded-xl font-bold text-slate-900 text-xs disabled:bg-slate-100 disabled:text-slate-500" />
                        </div>
                        <div>
                          <label className="block font-extrabold text-slate-800 mb-1 uppercase tracking-wider text-[10px]">Email Message Content</label>
                          <textarea rows={4} value={emailBody} onChange={(e) => setEmailBody(e.target.value)} disabled={isEmailSent} className="w-full p-3 bg-white border border-slate-200 rounded-t-xl text-xs font-medium text-slate-800 leading-relaxed focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 disabled:bg-slate-100 disabled:text-slate-500" />
                          {senderMailStatus && senderMailStatus.default_signature && !templateSelection.signatureId && (
                            <div className="w-full p-3 bg-slate-50 border border-t-0 border-slate-200 rounded-b-xl text-xs text-slate-500 whitespace-pre-wrap">
                              {senderMailStatus.default_signature}
                            </div>
                          )}
                        </div>
                        <div>
                          <label className="block font-extrabold text-slate-800 mb-1 uppercase tracking-wider text-[10px]">Attachments</label>
                          <div className="p-3 bg-white border border-slate-200 rounded-xl space-y-2">
                            <input 
                              type="file" 
                              multiple 
                              onChange={handleFileChange} 
                              disabled={isEmailSent}
                              className="text-xs text-slate-700 file:mr-2 file:py-1 file:px-2 file:rounded file:border-0 file:text-xs file:font-semibold file:bg-indigo-50 file:text-indigo-700 hover:file:bg-indigo-100 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                            />
                            {attachmentError && (
                              <div className="text-red-600 text-[10px] font-bold">{attachmentError}</div>
                            )}
                            {attachments.length > 0 && (
                              <div className="flex flex-wrap gap-2 mt-2">
                                {attachments.map((file, i) => (
                                  <div key={i} className="flex items-center gap-1.5 px-2 py-1 bg-slate-100 rounded-xl border border-slate-200 text-[10px] font-semibold text-slate-700">
                                    <span className="truncate max-w-[120px]">{file.name}</span>
                                    <span className="text-slate-400">({(file.size / 1024 / 1024).toFixed(1)}MB)</span>
                                    <button type="button" onClick={() => removeAttachment(i)} className="text-red-500 hover:text-red-700 font-bold ml-1">×</button>
                                  </div>
                                ))}
                              </div>
                            )}
                            <p className="text-[9px] text-slate-400 font-medium">Max 10MB per file, 25MB total. Executables not allowed.</p>
                          </div>
                        </div>
                        <div className="py-2">
                          <OpenTrackingToggle 
                            checked={openTrackingEnabled} 
                            onChange={setOpenTrackingEnabled} 
                            disabled={isSendingEmail || isEmailSent} 
                          />
                        </div>
                        <div className="flex items-center justify-between border-t border-slate-200 pt-3">
                          <div className="flex items-center gap-1.5 text-[11px] font-bold text-slate-600">
                            <span>Selected Recipients:</span><span className="px-2 py-0.5 rounded bg-indigo-100 text-indigo-800 font-extrabold">{toEmails.length + ccEmails.length} Address(es)</span>
                          </div>
                          <button type="button" onClick={handleSendIntroEmail} disabled={isSendingEmail || (toEmails.length === 0 && ccEmails.length === 0) || isEmailSent} className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 disabled:cursor-not-allowed text-white font-black rounded-xl text-xs transition cursor-pointer shadow-sm flex items-center gap-2">
                            <Mail className="w-4 h-4" /> <span>{isSendingEmail ? 'Sending Email...' : 'Send Introduction Email & Mark Sent'}</span>
                          </button>
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Call Section */}
                  <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm">
                    <div className="bg-gradient-to-r from-emerald-950 via-slate-900 to-teal-950 p-4 text-white flex items-center justify-between">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-xl bg-emerald-500/20 text-emerald-300 border border-emerald-400/30 flex items-center justify-center font-bold shrink-0"><Phone className="w-5 h-5" /></div>
                        <div>
                          <h4 className="text-sm font-extrabold text-white flex items-center gap-2">
                            <span>Call Outcome & Communication Progress</span>
                            {!isEmailSent && <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-400/30 text-[10px] uppercase font-extrabold flex items-center gap-1"><Lock className="w-3 h-3 text-amber-400" /> Locked</span>}
                          </h4>
                          <p className="text-xs text-slate-300 mt-0.5">Record phone call status, IVR extension, and live conversation outcomes.</p>
                        </div>
                      </div>
                      {prospect.official_phone_number && !isContactLockedCheck(null) && (
                        <a href={`tel:${prospect.official_phone_number}`} className="hidden sm:flex px-3 py-1.5 bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-black text-xs rounded-xl transition items-center gap-1.5 shadow-sm">
                          <Phone className="w-3.5 h-3.5" /> <span>Call {prospect.official_phone_number}</span>
                        </a>
                      )}
                    </div>
                    {!isEmailSent ? (
                      <div className="p-8 bg-slate-50/80 text-center space-y-3 border-t border-slate-200">
                        <div className="w-12 h-12 rounded-full bg-amber-100 text-amber-700 mx-auto flex items-center justify-center font-black">
                          <Lock className="w-6 h-6 text-amber-600" />
                        </div>
                        <h5 className="font-extrabold text-slate-900 text-sm">Call Outcome Locked Until Email Marked as Sent</h5>
                        <p className="text-xs text-slate-600 max-w-md mx-auto leading-relaxed">The Lead Qualifier must send the Company Introduction Email first.</p>
                        <button type="button" onClick={() => setEmailCollapsed(false)} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white font-bold text-xs rounded-xl transition cursor-pointer inline-flex items-center gap-1.5 shadow-sm">
                          <Mail className="w-3.5 h-3.5" /> <span>Open Company Introduction Email</span>
                        </button>
                      </div>
                    ) : (
                      <>
                        <div className="flex border-b border-slate-200">
                          <button 
                            type="button"
                            onClick={() => setInboundMode(false)}
                            className={`flex-1 py-3 text-xs font-bold transition-all border-b-2 ${!inboundMode ? 'border-indigo-600 text-indigo-700 bg-indigo-50/30' : 'border-transparent text-slate-500 hover:bg-slate-50 hover:text-slate-700'}`}
                          >
                            Outbound Call
                          </button>
                          <button 
                            type="button"
                            onClick={() => setInboundMode(true)}
                            className={`flex-1 py-3 text-xs font-bold transition-all border-b-2 ${inboundMode ? 'border-emerald-600 text-emerald-700 bg-emerald-50/30' : 'border-transparent text-slate-500 hover:bg-slate-50 hover:text-slate-700'}`}
                          >
                            Inbound Call/Message
                          </button>
                        </div>
                      <form onSubmit={inboundMode ? handleSaveInbound : handleLogCallOutcome} className="p-5 space-y-5 text-xs">
                        {/* Key People Dropdown + Phone Display */}
                        <div className="p-4 bg-white border border-slate-200 rounded-xl space-y-4 shadow-sm">
                          <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center">
                            <div className="flex-1">
                              <label className="block font-extrabold text-slate-700 text-[10px] uppercase tracking-wider mb-1.5">Select Key Person</label>
                              <select
                                value={selectedContactId}
                                onChange={(e) => {
                                  const id = e.target.value;
                                  setSelectedContactId(id);
                                  const contact = prospect?.key_contacts?.find(c => c.id === id);
                                  setSelectedContactData(contact || null);
                                  setCallStatus('Connected');
                                  setCommunicationOutcome('');
                                  setCallTranscriptNotes('');
                                  // Load existing logs for this contact
                                  const relevantLogs = id
                                    ? outreachLogs.filter(log => log.prospect_contact === id && log.activity_type === 'CALL')
                                    : outreachLogs.filter(log => !log.prospect_contact && log.activity_type === 'CALL');
                                  const latestCall = relevantLogs[0];
                                  if (latestCall) {
                                    setCallStatus(latestCall.status || 'Connected');
                                    setCommunicationOutcome(latestCall.outcome || '');
                                  }
                                }}
                                className="w-full p-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-bold text-slate-900 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all cursor-pointer"
                              >
                                <option value="">
                                  Company Official Number (General) {getGeneralLatestCall() ? ` - ${getGeneralLatestCall()}` : ''}
                                </option>
                                {prospect?.key_contacts?.map(contact => {
                                  const callStatusStr = getContactLatestCall(contact.id);
                                  return (
                                    <option key={contact.id} value={contact.id}>
                                      {contact.contact_name}{contact.designation ? ` - ${contact.designation}` : ''}
                                      {callStatusStr ? ` - ${callStatusStr}` : ''}
                                    </option>
                                  );
                                })}
                              </select>
                            </div>
                            {!inboundMode && (
                              <div className="flex items-center gap-2 w-full sm:w-auto shrink-0">
                                <label className="text-xs font-bold text-slate-700 whitespace-nowrap">IVR Ext:</label>
                                <input type="text" value={ivrExtension} onChange={(e) => setIvrExtension(e.target.value)} placeholder="e.g. Ext. 104" className="p-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-extrabold text-slate-900 w-28 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all" />
                              </div>
                            )}
                          </div>
                          <div className="flex items-center gap-2 pt-3 border-t border-slate-100">
                            <Phone className="w-4 h-4 text-slate-500 shrink-0" />
                            {selectedContactId && selectedContactData ? (
                              <div className="flex items-center gap-2 w-full">
                                <span className="font-extrabold text-slate-800 text-xs">
                                  {selectedContactData.contact_name}: <span className="text-slate-600 font-medium">{selectedContactData.phone_number || 'No phone on record'}</span>
                                </span>
                              </div>
                            ) : (
                              <div className="flex flex-col w-full gap-3">
                                <div className="flex items-center gap-2">
                                  <span className="font-extrabold text-slate-800 text-xs">
                                    Official Company Number: <span className="text-slate-600 font-medium">{prospect.official_phone_number || 'No phone'}</span>
                                  </span>
                                </div>
                                <div className="mt-1 pt-3 border-t border-slate-100">
                                  <label className="block text-[10px] font-bold text-slate-700 mb-1.5 uppercase tracking-wider">Person Contacted * <span className="font-normal text-slate-500 normal-case tracking-normal">Who did you speak to?</span></label>
                                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                    <input 
                                      type="text" 
                                      value={generalCallSpokeTo} 
                                      onChange={(e) => setGeneralCallSpokeTo(e.target.value)} 
                                      placeholder="Name (e.g. John, Unknown)" 
                                      className="w-full p-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-semibold text-slate-900 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all"
                                    />
                                    <input 
                                      type="text" 
                                      value={generalCallDesignation} 
                                      onChange={(e) => setGeneralCallDesignation(e.target.value)} 
                                      placeholder="Designation (Optional)" 
                                      className="w-full p-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-semibold text-slate-900 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all"
                                    />
                                  </div>
                                </div>
                              </div>
                            )}
                          </div>
                        </div>
                        {!inboundMode && (
                          <div className="pt-2">
                            <label className="block font-extrabold text-slate-700 mb-2.5 uppercase tracking-wider text-[10px]">1. Record Call Status Outcome</label>
                            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                              {[
                                { label: 'Connected',      active: 'bg-emerald-50 border-emerald-500 text-emerald-900 shadow-sm ring-1 ring-emerald-500/20', idle: 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50 hover:border-slate-200' },
                                { label: 'No Answer',      active: 'bg-amber-50 border-amber-500 text-amber-900 shadow-sm ring-1 ring-amber-500/20',   idle: 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50 hover:border-slate-200' },
                                { label: 'Busy',           active: 'bg-orange-50 border-orange-500 text-orange-900 shadow-sm ring-1 ring-orange-500/20', idle: 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50 hover:border-slate-200' },
                                { label: 'Switched Off',   active: 'bg-rose-50 border-rose-500 text-rose-900 shadow-sm ring-1 ring-rose-500/20',       idle: 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50 hover:border-slate-200' },
                                { label: 'Invalid Number', active: 'bg-slate-100 border-slate-500 text-slate-900 shadow-sm ring-1 ring-slate-500/20',    idle: 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50 hover:border-slate-200' },
                              ].map(({ label, active, idle }) => (
                                <button
                                  key={label}
                                  type="button"
                                  disabled={isContactLockedCheck(selectedContactId)}
                                  onClick={() => setCallStatus(label)}
                                  className={`p-2.5 rounded-lg border text-center font-extrabold text-xs transition-all ${callStatus === label ? active : idle} ${isContactLockedCheck(selectedContactId) ? 'opacity-50 cursor-not-allowed bg-slate-50' : ''}`}
                                >
                                  {label}
                                </button>
                              ))}
                            </div>
                          </div>
                        )}
                        {!inboundMode && callStatus === 'Connected' && (
                          <div className="space-y-4 pt-4 border-t border-slate-100">
                            <div>
                              <label className="block font-extrabold text-slate-700 mb-2.5 uppercase tracking-wider text-[10px] flex items-center gap-1.5">
                                <TrendingUp className="w-3.5 h-3.5 text-sky-600" />
                                <span>2. Record Communication Progress Outcome</span>
                              </label>
                              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                                {['Requested Email', 'Call Back Later', 'Call Transferred', 'Shared Another Contact', 'Not Interested', 'Lead Qualified'].map(out => (
                                  <button key={out} type="button" disabled={isContactLockedCheck(selectedContactId)} onClick={() => setCommunicationOutcome(out)} className={`p-2.5 rounded-lg border text-left font-bold text-xs transition flex items-center justify-between ${
                                    communicationOutcome === out ?
                                      out === 'Not Interested' ? 'bg-rose-50 border-rose-500 text-rose-900 shadow-sm ring-1 ring-rose-500/20' :
                                      out === 'Lead Qualified' ? 'bg-emerald-50 border-emerald-500 text-emerald-900 shadow-sm ring-1 ring-emerald-500/20' :
                                      'bg-sky-50 border-sky-500 text-sky-900 shadow-sm ring-1 ring-sky-500/20'
                                    : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-50 hover:border-slate-200'
                                  } ${isContactLockedCheck(selectedContactId) ? 'opacity-50 cursor-not-allowed hover:bg-transparent bg-slate-50' : ''}`}>
                                    <span>{out}</span>{communicationOutcome === out && <CheckCircle className={`w-4 h-4 ${out === 'Not Interested' ? 'text-rose-500' : out === 'Lead Qualified' ? 'text-emerald-500' : 'text-sky-500'}`} />}
                                  </button>
                                ))}
                              </div>
                            </div>
                            
                            {/* Dynamic forms */}
                            {communicationOutcome === 'Requested Email' && (
                              <div className="p-4 bg-white border border-slate-200 rounded-xl space-y-3 shadow-sm">
                                <span className="font-extrabold text-slate-800 flex items-center gap-1.5 text-xs">✉️ Prospect Requested Info Email</span>
                                <div>
                                  <label className="block text-[11px] font-bold text-slate-700 mb-1.5">Confirm Email Address:</label>
                                  <input type="email" value={requestedEmailConfirm} onChange={(e) => setRequestedEmailConfirm(e.target.value)} className="w-full p-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-semibold focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all" placeholder="e.g. contact@company.com" />
                                </div>
                                
                                {requestedEmailConfirm && requestedEmailConfirm.trim() && (
                                  <>
                                    {duplicateRequestedEmailContact ? (
                                      <div className="p-2.5 bg-amber-50 border border-amber-200 rounded-xl flex items-start gap-2">
                                        <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                                        <div>
                                          <p className="text-[11px] font-extrabold text-amber-900">Email Already Exists</p>
                                          <p className="text-[10px] font-medium text-amber-800 mt-0.5">
                                            This email belongs to <span className="font-bold">{duplicateRequestedEmailContact.contact_name}</span> ({duplicateRequestedEmailContact.designation}). No new contact will be created.
                                          </p>
                                        </div>
                                      </div>
                                    ) : (
                                      <div className="space-y-2 pt-2 border-t border-sky-200/50">
                                        <p className="text-[11px] font-bold text-slate-600 flex items-center gap-1">
                                          <Shield className="w-3.5 h-3.5 text-indigo-500" /> New Email Detected: Please register contact
                                        </p>
                                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                          <div>
                                            <label className="block text-[10px] font-bold text-slate-700 mb-1">Key Person Name <span className="text-red-500">*</span></label>
                                            <input type="text" value={newRequestedContactName} onChange={(e) => setNewRequestedContactName(e.target.value)} className="w-full p-2 bg-white border border-sky-300 rounded-xl text-xs font-semibold" placeholder="Name" />
                                          </div>
                                          <div>
                                            <label className="block text-[10px] font-bold text-slate-700 mb-1">Mobile Number</label>
                                            <input type="text" value={newRequestedContactMobile} onChange={(e) => setNewRequestedContactMobile(e.target.value)} className="w-full p-2 bg-white border border-sky-300 rounded-xl text-xs font-semibold" placeholder="Optional" />
                                          </div>
                                          <div className="sm:col-span-2">
                                            <label className="block text-[10px] font-bold text-slate-700 mb-1">Designation/Role <span className="text-red-500">*</span></label>
                                            <input type="text" value={newRequestedContactDesignation} onChange={(e) => setNewRequestedContactDesignation(e.target.value)} className="w-full p-2 bg-white border border-sky-300 rounded-xl text-xs font-semibold" placeholder="e.g. IT Director" />
                                          </div>
                                        </div>
                                      </div>
                                    )}
                                  </>
                                )}
                              </div>
                            )}
                            {communicationOutcome === 'Call Back Later' && (
                              <div className="p-3.5 bg-amber-50 border border-amber-200 rounded-xl space-y-3">
                                <span className="font-extrabold text-amber-950 block text-xs">⏰ Prospect Requested Call Back Later</span>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                  <div>
                                    <label className="block text-[11px] font-bold text-slate-700 mb-1">Date <span className="text-red-500">*</span></label>
                                    <input type="date" max="9999-12-31" required value={callbackDate} onChange={(e) => setCallbackDate(e.target.value)} className="w-full p-2 bg-white border border-amber-300 rounded-xl text-xs font-semibold" />
                                  </div>
                                  <div>
                                    <label className="block text-[11px] font-bold text-slate-700 mb-1">Time <span className="text-red-500">*</span></label>
                                    <TimeSelect value={callbackTime} onChange={setCallbackTime} />
                                  </div>
                                </div>
                                <div>
                                  <label className="block text-[11px] font-bold text-slate-700 mb-1">Description</label>
                                  <textarea rows={2} value={callbackDescription} onChange={(e) => setCallbackDescription(e.target.value)} placeholder="Any specific context for this callback..." className="w-full p-2 bg-white border border-amber-300 rounded-xl text-xs font-semibold resize-none" />
                                </div>
                              </div>
                            )}
                            {communicationOutcome === 'Call Transferred' && (
                              <div className="p-3.5 bg-indigo-50 border border-indigo-200 rounded-xl space-y-3">
                                <span className="font-extrabold text-indigo-950 text-xs">🔄 Call Transferred to Decision Maker</span>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                                  <div><label className="block text-[10px] font-bold text-slate-700 mb-0.5">Person Name:</label><input type="text" value={transferredPersonName} onChange={(e) => setTransferredPersonName(e.target.value)} className="w-full p-2 bg-white border border-indigo-300 rounded-xl" /></div>
                                  <div><label className="block text-[10px] font-bold text-slate-700 mb-0.5">Designation:</label><input type="text" value={transferredDesignation} onChange={(e) => setTransferredDesignation(e.target.value)} className="w-full p-2 bg-white border border-indigo-300 rounded-xl" /></div>
                                </div>
                              </div>
                            )}
                            {communicationOutcome === 'Shared Another Contact' && (
                              <div className="p-4 bg-white border border-slate-200 rounded-xl space-y-4 shadow-sm">
                                <span className="font-extrabold text-slate-800 text-xs flex items-center gap-1.5">👤 Shared Another Contact Information</span>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                  <div><label className="block text-[10px] font-bold text-slate-700 mb-1.5">Name:</label><input type="text" value={sharedContactName} onChange={(e) => setSharedContactName(e.target.value)} className="w-full p-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all" /></div>
                                  <div><label className="block text-[10px] font-bold text-slate-700 mb-1.5">Designation:</label><input type="text" value={sharedContactDesignation} onChange={(e) => setSharedContactDesignation(e.target.value)} className="w-full p-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all" /></div>
                                  <div><label className="block text-[10px] font-bold text-slate-700 mb-1.5">Phone:</label><input type="text" value={sharedContactPhone} onChange={(e) => setSharedContactPhone(e.target.value)} className="w-full p-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all" /></div>
                                  <div><label className="block text-[10px] font-bold text-slate-700 mb-1.5">Email:</label><input type="email" value={sharedContactEmail} onChange={(e) => setSharedContactEmail(e.target.value)} className="w-full p-2.5 bg-slate-50 border border-slate-200 rounded-xl focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all" /></div>
                                </div>
                                {duplicateContact && (
                                  <div className="mt-2 p-2 bg-amber-100 border border-amber-300 rounded text-amber-900 text-xs flex flex-col sm:flex-row items-center justify-between gap-2">
                                    <span>⚠️ This key contact already exists: <strong>{duplicateContact.contact_name} {duplicateContact.designation ? `(${duplicateContact.designation})` : ''}</strong></span>
                                    <button 
                                      type="button" 
                                      onClick={() => {
                                        setSharedContactName(duplicateContact.contact_name || '');
                                        setSharedContactDesignation(duplicateContact.designation || '');
                                        setSharedContactEmail(duplicateContact.official_email || '');
                                        setSharedContactPhone(duplicateContact.phone_number || '');
                                        setUseDuplicateContact(true);
                                      }}
                                      className="px-2 py-1 bg-amber-200 hover:bg-amber-300 text-amber-900 rounded font-bold transition whitespace-nowrap"
                                    >
                                      Select this contact
                                    </button>
                                  </div>
                                )}
                              </div>
                            )}
                            {communicationOutcome === 'Not Interested' && (
                              <div className="p-4 bg-white border border-slate-200 rounded-xl space-y-4 shadow-sm">
                                <span className="font-extrabold text-slate-800 text-xs flex items-center gap-1.5">🚫 Company Not Interested — <span className="text-rose-600 font-semibold">Outreach will be closed after saving</span></span>
                                <div>
                                  <label className="block text-[11px] font-bold text-slate-700 mb-1.5">Reason for Disinterest <span className="text-rose-500">*</span></label>
                                  <input
                                    type="text"
                                    value={notInterestedReason}
                                    onChange={(e) => setNotInterestedReason(e.target.value)}
                                    placeholder="e.g. Budget frozen, not the right time..."
                                    className={`w-full p-2.5 bg-slate-50 border rounded-lg text-xs font-semibold focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all ${notInterestedReason.trim() ? 'border-slate-200' : 'border-rose-300 ring-1 ring-rose-200'}`}
                                  />
                                </div>
                                <p className="text-[10px] text-slate-500 font-semibold flex items-center gap-1.5"><AlertTriangle className="w-3.5 h-3.5 text-rose-500" /> Prospect Status will be set to <strong className="text-slate-700">Lead Freeze</strong>. The Outreach button will be disabled.</p>
                              </div>
                            )}
                            {communicationOutcome === 'Lead Qualified' && (
                              <div className="p-4 bg-white border border-slate-200 rounded-xl space-y-4 shadow-sm">
                                <span className="font-extrabold text-slate-800 flex items-center gap-1.5 text-xs">✅ Lead Qualified & Schedule Meeting</span>
                                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                                  <div>
                                    <label className="block text-[11px] font-bold text-slate-700 mb-1.5">Meeting Date *</label>
                                    <input type="date" max="9999-12-31" required value={meetingDate} onChange={(e) => setMeetingDate(e.target.value)} className="w-full p-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-semibold focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all" />
                                  </div>
                                  <div>
                                    <label className="block text-[11px] font-bold text-slate-700 mb-1.5">Meeting Time *</label>
                                    <TimeSelect value={meetingTime} onChange={setMeetingTime} />
                                  </div>
                                </div>
                                <div>
                                  <MeetingProviderPicker
                                    calendarStatus={calendarStatus}
                                    calendarLoading={calendarLoading}
                                    onConnectCalendar={handleConnectCalendar}
                                    isCreating={isCreatingMeeting}
                                  />
                                  {createdMeeting && (
                                    <div className="mt-3">
                                      <CreatedMeetingCard
                                        meeting={createdMeeting}
                                        onDismiss={() => setCreatedMeeting(null)}
                                        onRefresh={handleRefreshMeetLink}
                                        isRefreshing={isRefreshingMeet}
                                      />
                                    </div>
                                  )}
                                </div>
                                <div>
                                  <label className="block text-[11px] font-bold text-slate-700 mb-1.5">Agenda *</label>
                                  <textarea rows={2} value={leadQualifiedDescription} onChange={(e) => setLeadQualifiedDescription(e.target.value)} className={`w-full p-2.5 bg-slate-50 border rounded-lg text-xs font-semibold resize-none focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all ${leadQualifiedDescription.trim() ? 'border-slate-200' : 'border-rose-300 ring-1 ring-rose-200'}`} />
                                </div>
                                <div className="flex items-center gap-2 mt-2">
                                  <input type="checkbox" id="attendedMeeting" checked={attendedMeeting} onChange={(e) => setAttendedMeeting(e.target.checked)} className="w-4 h-4 text-sky-600 rounded border-slate-200 focus:ring-sky-500" />
                                  <label htmlFor="attendedMeeting" className="text-[11px] font-bold text-slate-700 cursor-pointer">Prospect Attended Meeting</label>
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                        {inboundMode && (
                          <div className="p-4 bg-emerald-50/50 border border-emerald-200 rounded-xl mt-4">
                            <span className="font-extrabold text-emerald-900 text-xs mb-3 block uppercase tracking-wider">📅 Inbound Data Entry Details</span>
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                              <div>
                                <label className="block text-[10px] font-bold text-slate-700 mb-1.5">Date Received *</label>
                                <input type="date" value={inboundDate} onChange={(e) => setInboundDate(e.target.value)} className="w-full p-2.5 bg-white border border-emerald-300 rounded-xl text-xs font-semibold focus:outline-none" required />
                              </div>
                              <div>
                                <label className="block text-[10px] font-bold text-slate-700 mb-1.5">Time Received *</label>
                                <TimeSelect value={inboundTime} onChange={setInboundTime} />
                              </div>
                            </div>
                          </div>
                        )}

                        {/* Hide transcript when a structured outcome form is already capturing detail */}
                        {(inboundMode || !['Requested Email', 'Call Back Later', 'Call Transferred', 'Shared Another Contact', 'Not Interested', 'Lead Qualified'].includes(communicationOutcome)) && (
                          <div className="p-4 bg-white border border-slate-200 rounded-xl space-y-2 shadow-sm mt-4">
                            <label className="block font-extrabold text-slate-700 mb-1.5 text-[10px] uppercase tracking-wider">{inboundMode ? 'Inbound Message / Notes *' : 'Call Transcript & Discussion Summary'}</label>
                            <textarea rows={3} value={callTranscriptNotes} onChange={(e) => setCallTranscriptNotes(e.target.value)} placeholder={inboundMode ? "Enter notes regarding the inbound message..." : "Enter notes from call conversation..."} className="w-full p-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs font-semibold focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all resize-none" />
                          </div>
                        )}
                        <div className="flex flex-col gap-2 pt-1">
                          {callError && (
                            <div className="flex items-center gap-2 p-2.5 bg-red-50 border border-red-200 rounded-xl text-red-700 text-xs font-bold">
                              <AlertTriangle className="w-4 h-4 shrink-0 text-red-500" />
                              <span>{callError}</span>
                            </div>
                          )}
                          <div className="flex justify-end">
                            {(() => {
                              const isContactInvalid = !inboundMode && isContactLockedCheck(selectedContactId);
                              const isDisabled = isContactInvalid || isSubmittingActivity;
                              return (
                                <button type="submit" disabled={isDisabled} className={`px-5 py-2.5 font-extrabold text-xs rounded-xl transition shadow-sm flex items-center gap-2 ${isDisabled ? 'bg-slate-300 text-slate-500 cursor-not-allowed' : 'bg-emerald-600 hover:bg-emerald-700 text-white cursor-pointer'}`}>
                                  <Phone className="w-4 h-4" /><span>{isSubmittingActivity ? 'Saving...' : (inboundMode ? 'Record Inbound Activity' : 'Record Call Outcome & Save Activity')}</span>
                                </button>
                              );
                            })()}
                          </div>
                        </div>
                      </form>
                      </>
                    )}
                  </div>

                  {/* Outreach Logs */}
                  <div className="bg-white rounded-2xl border border-slate-200 p-5 space-y-3 shadow-sm">
                    <h5 className="font-extrabold text-slate-900 text-xs uppercase tracking-wider flex items-center gap-2">
                      <Clock className="w-4 h-4 text-slate-500" />
                      <span>Communication History ({outreachLogs.length})</span>
                    </h5>
                    {outreachLogs.length > 0 ? (
                      <div className="space-y-2.5 max-h-56 overflow-y-auto">
                        {outreachLogs.map(log => (
                          <div key={log.id} className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl text-xs space-y-1.5">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className={`px-2 py-0.5 rounded text-[10px] font-black uppercase ${log.activity_type === 'CALL_MADE' ? 'bg-emerald-100 text-emerald-900' : 'bg-indigo-100 text-indigo-900'}`}>{log.activity_type}</span>
                                {log.status && <span className={`px-2 py-0.5 rounded text-[10px] font-bold border ${log.activity_type === 'CALL_MADE' ? 'bg-emerald-50 text-emerald-800 border-emerald-200' : 'bg-indigo-50 text-indigo-800 border-indigo-200'}`}>{log.activity_type}: {log.status}</span>}
                                <span className="px-2 py-0.5 rounded bg-blue-50 text-blue-800 border border-blue-200 text-[10px] font-bold">Contact: {log.contact_name || prospect?.company_name}</span>
                              </div>
                              <span className="text-[10px] text-slate-400 font-semibold flex items-center gap-1">
                                {new Date(log.created_at).toLocaleString()} 
                                <span className="bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded ml-1">{log.created_by_name}</span>
                              </span>
                            </div>
                            <p className="text-slate-700 font-medium whitespace-pre-line leading-relaxed max-h-48 overflow-y-auto bg-white p-2 rounded border border-slate-100">{log.notes}</p>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <p className="text-xs text-slate-400 italic p-4 text-center border border-dashed border-slate-200 rounded-xl">
                        No communication logged yet for {prospect.company_name}. Complete the Introduction Email above to begin.
                      </p>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="p-4 bg-white border-t border-slate-200 flex items-center justify-end shrink-0">
          <button onClick={onClose} className="px-5 py-2 bg-slate-800 hover:bg-slate-900 text-white text-sm font-bold rounded-xl transition cursor-pointer shadow-sm">
            Done / Close Workspace
          </button>
        </div>

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
                      {activeEmailTracking?.open_tracking_enabled === false ? (
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-extrabold uppercase border bg-slate-500/20 text-slate-300 border-slate-400/40 flex items-center gap-1">
                          Tracking Disabled
                        </span>
                      ) : (
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-extrabold uppercase border flex items-center gap-1 ${
                          activeEmailTracking?.is_opened
                            ? 'bg-emerald-500/20 text-emerald-300 border-emerald-400/40'
                            : 'bg-amber-500/20 text-amber-300 border-amber-400/40'
                        }`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${activeEmailTracking?.is_opened ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'}`} />
                          {activeEmailTracking?.is_opened ? `Viewed (${activeEmailTracking?.open_count || 1}x)` : 'Awaiting Open'}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-300 mt-0.5 truncate max-w-md">
                      {prospect.company_name} &bull; <span className="text-indigo-200 font-semibold">{activeEmailTracking?.subject || 'Introductory Email'}</span>
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
                {activeEmailTracking?.open_tracking_enabled === false && (
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
                        {activeEmailTracking?.open_count || (activeEmailTracking?.is_opened ? 1 : 0)}
                      </span>
                      <span className="text-[10px] text-slate-400 ml-1">times</span>
                    </div>
                    <span className={`text-[10px] font-bold mt-1 ${
                      (activeEmailTracking?.open_count || 0) > 1 ? 'text-indigo-600' : activeEmailTracking?.is_opened ? 'text-emerald-600' : 'text-slate-400'
                    }`}>
                      {(activeEmailTracking?.open_count || 0) > 2 ? '🔥 Highly Engaged' : activeEmailTracking?.is_opened ? 'Opened & Seen' : 'Not opened yet'}
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
                        {activeEmailTracking?.estimated_read_time_formatted || (activeEmailTracking?.total_seconds_spent ? `${activeEmailTracking.total_seconds_spent}s` : '0s')}
                      </span>
                    </div>
                    <span className="text-[10px] font-bold text-violet-600 mt-1">
                      {activeEmailTracking?.reading_engagement || (activeEmailTracking?.is_opened ? 'Read in Detail' : 'No Reading Time')}
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
                        {formatTrackingDateTime(activeEmailTracking?.first_opened_at || activeEmailTracking?.opened_at)}
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
                        {formatTrackingDateTime(activeEmailTracking?.last_opened_at || activeEmailTracking?.opened_at)}
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
                      {activeEmailTracking?.reading_engagement || (activeEmailTracking?.is_opened ? 'Read in Detail' : 'Unopened')}
                    </span>
                  </div>
                  {/* Visual meter */}
                  <div className="w-full bg-slate-200 rounded-full h-2.5 overflow-hidden flex">
                    <div className={`h-full transition-all duration-500 ${
                      !activeEmailTracking?.is_opened ? 'w-0' :
                      (activeEmailTracking?.open_count >= 3 || (activeEmailTracking?.total_seconds_spent || 0) >= 60) ? 'w-full bg-gradient-to-r from-indigo-500 to-emerald-500' :
                      (activeEmailTracking?.open_count >= 2 || (activeEmailTracking?.total_seconds_spent || 0) >= 15) ? 'w-2/3 bg-indigo-600' :
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
                      {activeEmailTracking?.open_history?.length || 0} event{activeEmailTracking?.open_history?.length === 1 ? '' : 's'} recorded
                    </span>
                  </div>

                  {activeEmailTracking?.open_history && activeEmailTracking.open_history.length > 0 ? (
                    <div className="divide-y divide-slate-100 border border-slate-200 rounded-2xl overflow-hidden bg-white max-h-48 overflow-y-auto">
                      {[...activeEmailTracking.open_history].reverse().map((ev, idx) => (
                        <div key={ev.id || idx} className="p-3 flex items-center justify-between gap-3 hover:bg-slate-50/80 transition text-[11px]">
                          <div className="flex items-center gap-3 min-w-0">
                            <div className="w-7 h-7 rounded-xl bg-indigo-50 border border-indigo-200/60 text-indigo-700 flex items-center justify-center font-extrabold text-xs shrink-0">
                              #{ev.id || activeEmailTracking.open_history.length - idx}
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
                  ) : activeEmailTracking?.is_opened ? (
                    <div className="p-4 border border-slate-200 rounded-2xl bg-slate-50 text-center space-y-1">
                      <p className="text-xs font-bold text-slate-700">Email was opened on {formatTrackingDateTime(activeEmailTracking?.opened_at)}</p>
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
                    disabled={isSimulatingOpen || !sentEmailData?.id}
                    className="px-3 py-1.5 bg-indigo-50 hover:bg-indigo-100 disabled:opacity-50 text-indigo-700 font-extrabold text-xs rounded-xl border border-indigo-200/80 transition flex items-center gap-1.5 shadow-2xs cursor-pointer"
                    title="Simulate recipient opening the email (test live tracking)"
                  >
                    <Zap className={`w-3.5 h-3.5 ${isSimulatingOpen ? 'animate-bounce text-indigo-600' : 'text-indigo-500'}`} />
                    <span>{isSimulatingOpen ? 'Recording...' : '⚡ Test Open Ping'}</span>
                  </button>
                  <button
                    type="button"
                    onClick={handleRefreshTracking}
                    disabled={isRefreshingTracking || !sentEmailData?.id}
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
    </div>
  );
}
