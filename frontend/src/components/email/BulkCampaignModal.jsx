import React, { useState, useEffect, useRef, useCallback } from 'react';
import { 
  X, Send, Users, CheckCircle2, AlertCircle, Clock, Pause, Play, Ban, 
  Paperclip, Search, Plus, Trash2, RefreshCw, Eye, Sparkles, Building2, 
  User, CheckSquare, Square, ChevronRight, FileText, Info, ShieldCheck,
  AlertTriangle
} from 'lucide-react';
import { toast } from 'react-toastify';
import api from '../../services/api';
import TemplatePicker from '../lq/TemplatePicker';
import OpenTrackingToggle from './OpenTrackingToggle';

const STEPS = [
  { id: 'compose', label: '1. Compose' },
  { id: 'recipients', label: '2. Recipients' },
  { id: 'confirm', label: '3. Review' },
  { id: 'monitor', label: 'Campaign Monitor' }
];

export default function BulkCampaignModal({ isOpen, onClose }) {
  const [currentTab, setCurrentTab] = useState('compose');

  // Form State
  const [campaignName, setCampaignName] = useState('');
  const [emailSubject, setEmailSubject] = useState('');
  const [emailBody, setEmailBody] = useState('');
  const [templateSelection, setTemplateSelection] = useState({ templateId: '', signatureId: '', baseBody: null });
  const [openTrackingEnabled, setOpenTrackingEnabled] = useState(false);
  const [attachments, setAttachments] = useState([]);
  const [attachmentError, setAttachmentError] = useState('');

  // Recipients State
  const [directorySearch, setDirectorySearch] = useState('');
  const [directoryItems, setDirectoryItems] = useState([]);
  const [loadingDirectory, setLoadingDirectory] = useState(false);
  const [selectedRecipients, setSelectedRecipients] = useState([]); // [{ email, name, prospect_id, prospect_contact_id, company_name, type }]
  const [pasteInput, setPasteInput] = useState('');

  // Campaigns list / Monitor State
  const [campaigns, setCampaigns] = useState([]);
  const [loadingCampaigns, setLoadingCampaigns] = useState(false);
  const [activeCampaignDetail, setActiveCampaignDetail] = useState(null);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  // Poll timer
  const pollTimerRef = useRef(null);

  // Fetch Directory
  const fetchDirectory = useCallback(async (searchQuery = '') => {
    setLoadingDirectory(true);
    try {
      const res = await api.get(`/email-campaigns/recipient-directory/?search=${encodeURIComponent(searchQuery)}`);
      setDirectoryItems(res.data?.results || []);
    } catch (err) {
      console.error('Failed to load recipient directory', err);
    } finally {
      setLoadingDirectory(false);
    }
  }, []);

  // Fetch Campaigns List
  const fetchCampaigns = useCallback(async () => {
    setLoadingCampaigns(true);
    try {
      const res = await api.get('/email-campaigns/');
      const list = res.data?.results || res.data || [];
      setCampaigns(list);
      return list;
    } catch (err) {
      console.error('Failed to fetch campaigns', err);
      return [];
    } finally {
      setLoadingCampaigns(false);
    }
  }, []);

  // Fetch Campaign Details
  const fetchCampaignDetail = useCallback(async (campaignId) => {
    if (!campaignId) return;
    setLoadingDetail(true);
    try {
      const res = await api.get(`/email-campaigns/${campaignId}/`);
      setActiveCampaignDetail(res.data);
    } catch (err) {
      console.error('Failed to load campaign detail', err);
    } finally {
      setLoadingDetail(false);
    }
  }, []);

  // Initial load when modal opens
  useEffect(() => {
    if (isOpen) {
      fetchDirectory('');
      fetchCampaigns().then((list) => {
        // If an active campaign exists, start on monitor tab
        const active = list.find(c => ['RUNNING', 'QUEUED', 'PAUSED'].includes(c.status));
        if (active) {
          fetchCampaignDetail(active.id);
        }
      });
    } else {
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    }
  }, [isOpen, fetchDirectory, fetchCampaigns, fetchCampaignDetail]);

  // Live polling for active campaign monitor
  useEffect(() => {
    if (isOpen && currentTab === 'monitor' && activeCampaignDetail?.id) {
      const isLive = ['RUNNING', 'QUEUED', 'PAUSED'].includes(activeCampaignDetail.status);
      if (isLive) {
        pollTimerRef.current = setInterval(() => {
          fetchCampaignDetail(activeCampaignDetail.id);
          fetchCampaigns();
        }, 5000);
      }
      return () => {
        if (pollTimerRef.current) clearInterval(pollTimerRef.current);
      };
    }
  }, [isOpen, currentTab, activeCampaignDetail?.id, activeCampaignDetail?.status, fetchCampaignDetail, fetchCampaigns]);

  if (!isOpen) return null;

  // File Handlers
  const handleFileChange = (e) => {
    const files = Array.from(e.target.files);
    let currentTotalSize = attachments.reduce((sum, f) => sum + f.size, 0);
    const validFiles = [];

    for (const file of files) {
      if (currentTotalSize + file.size > 25 * 1024 * 1024) {
        setAttachmentError('Total attachment size exceeds 25MB limit.');
        return;
      }
      if (file.size > 10 * 1024 * 1024) {
        setAttachmentError(`File ${file.name} exceeds 10MB limit.`);
        return;
      }
      const ext = file.name.split('.').pop()?.toLowerCase();
      if (['exe', 'bat', 'cmd', 'js', 'ps1', 'vbs', 'scr'].includes(ext)) {
        setAttachmentError(`File type .${ext} is not allowed.`);
        return;
      }
      currentTotalSize += file.size;
      validFiles.push(file);
    }

    setAttachmentError('');
    setAttachments(prev => [...prev, ...validFiles]);
    e.target.value = '';
  };

  const removeAttachment = (index) => {
    setAttachments(prev => prev.filter((_, i) => i !== index));
  };

  // Recipient selection toggling
  const handleToggleRecipient = (item) => {
    const emailNorm = item.email.toLowerCase();
    const exists = selectedRecipients.some(r => r.email.toLowerCase() === emailNorm);
    if (exists) {
      setSelectedRecipients(prev => prev.filter(r => r.email.toLowerCase() !== emailNorm));
    } else {
      setSelectedRecipients(prev => [...prev, {
        email: item.email,
        name: item.name,
        company_name: item.company_name,
        type: item.type,
        prospect_id: item.prospect_id,
        prospect_contact_id: item.prospect_contact_id
      }]);
    }
  };

  const handleSelectAllFiltered = () => {
    const newItems = [...selectedRecipients];
    directoryItems.forEach(item => {
      const emailNorm = item.email.toLowerCase();
      if (!newItems.some(r => r.email.toLowerCase() === emailNorm)) {
        newItems.push({
          email: item.email,
          name: item.name,
          company_name: item.company_name,
          type: item.type,
          prospect_id: item.prospect_id,
          prospect_contact_id: item.prospect_contact_id
        });
      }
    });
    setSelectedRecipients(newItems);
    toast.success(`Selected ${directoryItems.length} filtered recipients`);
  };

  const handleAddPastedEmails = () => {
    if (!pasteInput.trim()) return;
    const splitEmails = pasteInput.split(/[,;\n\r\s]+/).map(e => e.trim()).filter(Boolean);
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    let addedCount = 0;
    const currentList = [...selectedRecipients];

    splitEmails.forEach(raw => {
      if (emailRegex.test(raw)) {
        const norm = raw.toLowerCase();
        if (!currentList.some(r => r.email.toLowerCase() === norm)) {
          currentList.push({
            email: norm,
            name: norm.split('@')[0],
            company_name: 'Custom Recipient',
            type: 'custom',
            prospect_id: null,
            prospect_contact_id: null
          });
          addedCount++;
        }
      }
    });

    setSelectedRecipients(currentList);
    setPasteInput('');
    if (addedCount > 0) {
      toast.success(`Added ${addedCount} unique recipient(s)`);
    } else {
      toast.info('No new valid email addresses found.');
    }
  };

  const handleRemoveSelectedRecipient = (email) => {
    setSelectedRecipients(prev => prev.filter(r => r.email.toLowerCase() !== email.toLowerCase()));
  };

  // Launch Campaign
  const handleLaunchCampaign = async () => {
    if (!campaignName.trim()) return toast.error('Campaign Name is required');
    if (!emailSubject.trim()) return toast.error('Subject is required');
    if (!emailBody.trim()) return toast.error('Email Body is required');
    if (selectedRecipients.length === 0) return toast.error('At least one recipient is required');

    setSubmitting(true);
    const toastId = toast.loading('Initializing persistent campaign queue...');

    try {
      const formData = new FormData();
      formData.append('name', campaignName.trim());
      formData.append('subject', emailSubject.trim());
      formData.append('body', emailBody);
      formData.append('open_tracking_enabled', String(openTrackingEnabled));

      if (templateSelection.templateId) {
        formData.append('template_id', templateSelection.templateId);
      }
      if (templateSelection.signatureId) {
        formData.append('signature_id', templateSelection.signatureId);
      }

      formData.append('recipients', JSON.stringify(selectedRecipients.map(r => ({
        email: r.email,
        name: r.name,
        prospect_id: r.prospect_id,
        prospect_contact_id: r.prospect_contact_id
      }))));

      attachments.forEach(file => {
        formData.append('attachments', file);
      });

      const res = await api.post('/email-campaigns/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      toast.dismiss(toastId);
      toast.success('Bulk email campaign queued successfully!');
      
      setActiveCampaignDetail(res.data);
      fetchCampaigns();
      setCurrentTab('monitor');

      // Reset form
      setCampaignName('');
      setEmailSubject('');
      setEmailBody('');
      setSelectedRecipients([]);
      setAttachments([]);
    } catch (err) {
      toast.dismiss(toastId);
      const msg = err.response?.data?.error || 'Failed to start campaign';
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  // Campaign controls
  const handlePause = async (id) => {
    try {
      const res = await api.post(`/email-campaigns/${id}/pause/`);
      toast.info('Campaign paused.');
      setActiveCampaignDetail(res.data);
      fetchCampaigns();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to pause campaign');
    }
  };

  const handleResume = async (id) => {
    try {
      const res = await api.post(`/email-campaigns/${id}/resume/`);
      toast.success('Campaign resumed.');
      setActiveCampaignDetail(res.data);
      fetchCampaigns();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to resume campaign');
    }
  };

  const handleCancel = async (id) => {
    if (!window.confirm('Are you sure you want to cancel this campaign? Pending emails will not be sent.')) return;
    try {
      const res = await api.post(`/email-campaigns/${id}/cancel/`);
      toast.warn('Campaign cancelled.');
      setActiveCampaignDetail(res.data);
      fetchCampaigns();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to cancel campaign');
    }
  };

  // Calculate approximate duration for confirmation
  const totalRecipientsCount = selectedRecipients.length;
  const estimatedSeconds = Math.max(0, (totalRecipientsCount - 1) * 90);
  const estimatedHours = Math.floor(estimatedSeconds / 3600);
  const estimatedMinutes = Math.floor((estimatedSeconds % 3600) / 60);
  const estimatedRemainingSecs = estimatedSeconds % 60;
  const formattedDuration = estimatedHours > 0
    ? `${estimatedHours} hr ${estimatedMinutes} min`
    : `${estimatedMinutes} min ${estimatedRemainingSecs} sec`;

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-3 sm:p-5 overflow-y-auto">
      <div className="bg-white rounded-3xl shadow-2xl border border-slate-200 w-full max-w-5xl h-[92vh] flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        
        {/* Top Header - Google Workspace Style */}
        <div className="px-6 py-4 bg-white border-b border-slate-200/80 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center">
              <Users className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-slate-900 tracking-tight">Bulk Email Campaign</h2>
                <span className="px-2.5 py-0.5 rounded-full text-[11px] font-medium bg-blue-50 text-blue-700 border border-blue-200/60 flex items-center gap-1">
                  <Clock className="w-3 h-3" /> 90s pacing
                </span>
              </div>
              <p className="text-xs text-slate-500">
                Paced sequential delivery protecting your sender reputation and deliverability.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-slate-700 rounded-full hover:bg-slate-100 transition cursor-pointer"
            title="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Step Navigation Bar - Google Segmented Tabs */}
        <div className="px-6 py-2.5 bg-slate-50/70 border-b border-slate-200/80 flex items-center justify-between shrink-0">
          <div className="flex items-center gap-1.5 p-1 bg-slate-200/60 rounded-full">
            {STEPS.map((s) => (
              <button
                key={s.id}
                type="button"
                onClick={() => setCurrentTab(s.id)}
                className={`px-4 py-1.5 rounded-full text-xs font-medium transition flex items-center gap-1.5 cursor-pointer ${
                  currentTab === s.id
                    ? 'bg-white text-blue-700 shadow-xs font-semibold'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-white/50'
                }`}
              >
                {s.label}
                {s.id === 'recipients' && selectedRecipients.length > 0 && (
                  <span className={`px-1.5 py-0.2 rounded-full text-[10px] font-bold ${currentTab === s.id ? 'bg-blue-100 text-blue-800' : 'bg-slate-200 text-slate-700'}`}>
                    {selectedRecipients.length}
                  </span>
                )}
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
            {campaigns.length > 0 && (
              <button
                type="button"
                onClick={() => {
                  fetchCampaigns();
                  setCurrentTab('monitor');
                }}
                className="px-3 py-1.5 text-blue-600 hover:text-blue-800 hover:bg-blue-50/60 rounded-full font-medium transition flex items-center gap-1.5 cursor-pointer"
              >
                <Clock className="w-3.5 h-3.5" />
                <span>{campaigns.length} Campaign(s)</span>
              </button>
            )}
          </div>
        </div>

        {/* Body Content */}
        <div className="flex-1 overflow-y-auto p-6 bg-slate-50/50">

          {/* TAB 1: COMPOSE */}
          {currentTab === 'compose' && (
            <div className="max-w-3xl mx-auto space-y-5">
              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1.5">
                  Campaign name <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. Q4 Enterprise Outreach"
                  value={campaignName}
                  onChange={(e) => setCampaignName(e.target.value)}
                  className="w-full bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm font-normal text-slate-900 focus:ring-2 focus:ring-blue-100 focus:border-blue-500 outline-none transition"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1.5">
                  Subject <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  placeholder="Subject line for all recipients..."
                  value={emailSubject}
                  onChange={(e) => setEmailSubject(e.target.value)}
                  className="w-full bg-white border border-slate-200 rounded-xl px-4 py-2.5 text-sm font-normal text-slate-900 focus:ring-2 focus:ring-blue-100 focus:border-blue-500 outline-none transition"
                />
              </div>

              {/* Template Picker Integration */}
              <div className="bg-white p-4 rounded-2xl border border-slate-200/80 shadow-xs">
                <TemplatePicker
                  toEmails={selectedRecipients.map(r => r.email)}
                  emailSubject={emailSubject}
                  emailBody={emailBody}
                  setEmailSubject={setEmailSubject}
                  setEmailBody={setEmailBody}
                  selection={templateSelection}
                  setSelection={setTemplateSelection}
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-700 mb-1.5">
                  Message body <span className="text-rose-500">*</span>
                </label>
                <textarea
                  rows={8}
                  placeholder="Write your email body here..."
                  value={emailBody}
                  onChange={(e) => setEmailBody(e.target.value)}
                  className="w-full bg-white border border-slate-200 rounded-xl p-4 text-sm text-slate-900 focus:ring-2 focus:ring-blue-100 focus:border-blue-500 outline-none transition leading-relaxed resize-y font-normal"
                />
              </div>

              {/* Attachments & Open Tracking */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-white p-4 rounded-2xl border border-slate-200/80">
                <div className="flex items-center gap-3">
                  <label className="px-3.5 py-2 bg-slate-100 hover:bg-slate-200/80 text-slate-700 font-medium text-xs rounded-full cursor-pointer transition flex items-center gap-1.5 border border-slate-200">
                    <Paperclip className="w-3.5 h-3.5 text-slate-500" />
                    <span>Attach files (max 25MB)</span>
                    <input type="file" multiple onChange={handleFileChange} className="hidden" />
                  </label>
                  {attachments.length > 0 && (
                    <span className="text-xs font-medium text-slate-600">
                      {attachments.length} file(s) attached ({Math.round(attachments.reduce((sum, f) => sum + f.size, 0) / 1024)} KB)
                    </span>
                  )}
                </div>

                <OpenTrackingToggle
                  id="bulk-campaign-open-tracking"
                  checked={openTrackingEnabled}
                  onChange={setOpenTrackingEnabled}
                />
              </div>

              {attachmentError && (
                <div className="p-3 bg-rose-50 border border-rose-200 text-rose-700 text-xs font-medium rounded-xl flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{attachmentError}</span>
                </div>
              )}

              {attachments.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {attachments.map((file, i) => (
                    <div key={i} className="flex items-center gap-2 px-3 py-1.5 bg-white border border-slate-200 rounded-full text-xs font-medium text-slate-800 shadow-2xs">
                      <Paperclip className="w-3.5 h-3.5 text-slate-400" />
                      <span className="truncate max-w-xs">{file.name}</span>
                      <button type="button" onClick={() => removeAttachment(i)} className="text-slate-400 hover:text-rose-600 transition">
                        <X className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <div className="flex justify-end pt-2">
                <button
                  type="button"
                  onClick={() => {
                    if (!campaignName.trim() || !emailSubject.trim() || !emailBody.trim()) {
                      return toast.error('Please fill in campaign name, subject, and body before proceeding');
                    }
                    setCurrentTab('recipients');
                  }}
                  className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-medium text-xs rounded-full transition flex items-center gap-2 shadow-xs hover:shadow-md cursor-pointer"
                >
                  <span>Next: Choose recipients</span>
                  <ChevronRight className="w-4 h-4" />
                </button>
              </div>
            </div>
          )}

          {/* TAB 2: SELECT RECIPIENTS */}
          {currentTab === 'recipients' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-full">
              {/* Left Column: Directory & Search */}
              <div className="lg:col-span-7 flex flex-col h-full bg-white rounded-2xl border border-slate-200/80 p-4 shadow-xs overflow-hidden">
                <div className="flex items-center justify-between mb-3 shrink-0">
                  <div>
                    <h3 className="font-semibold text-slate-900 text-sm">Contacts & Companies</h3>
                    <p className="text-xs text-slate-500">Select recipients from your accessible pipeline</p>
                  </div>
                  <button
                    type="button"
                    onClick={handleSelectAllFiltered}
                    disabled={directoryItems.length === 0}
                    className="px-3 py-1 bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 font-medium text-xs rounded-full transition disabled:opacity-50 cursor-pointer"
                  >
                    Select all ({directoryItems.length})
                  </button>
                </div>

                <div className="relative mb-3 shrink-0">
                  <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400 pointer-events-none" />
                  <input
                    type="text"
                    placeholder="Search by name, company, or email..."
                    value={directorySearch}
                    onChange={(e) => {
                      setDirectorySearch(e.target.value);
                      fetchDirectory(e.target.value);
                    }}
                    className="w-full bg-slate-50 border border-slate-200 rounded-full pl-9 pr-4 py-2 text-xs font-normal text-slate-900 focus:ring-2 focus:ring-blue-100 focus:border-blue-500 outline-none transition"
                  />
                </div>

                {/* Directory Items List */}
                <div className="flex-1 overflow-y-auto divide-y divide-slate-100 border border-slate-100 rounded-xl">
                  {loadingDirectory ? (
                    <div className="flex items-center justify-center p-8 text-slate-400 text-xs font-semibold gap-2">
                      <RefreshCw className="w-4 h-4 animate-spin" /> Loading pipeline recipients...
                    </div>
                  ) : directoryItems.length === 0 ? (
                    <div className="p-8 text-center text-slate-400 text-xs font-medium">
                      No matching prospects or contacts found in your authorized pipeline.
                    </div>
                  ) : (
                    directoryItems.map((item) => {
                      const isSelected = selectedRecipients.some(r => r.email.toLowerCase() === item.email.toLowerCase());
                      return (
                        <div
                          key={item.id}
                          onClick={() => handleToggleRecipient(item)}
                          className={`p-3 flex items-center justify-between cursor-pointer transition select-none ${
                            isSelected ? 'bg-indigo-50/70 border-l-2 border-indigo-500' : 'hover:bg-slate-50'
                          }`}
                        >
                          <div className="flex items-center gap-3 min-w-0">
                            <button type="button" className="text-slate-400 shrink-0">
                              {isSelected ? (
                                <CheckSquare className="w-4 h-4 text-indigo-600 fill-indigo-100" />
                              ) : (
                                <Square className="w-4 h-4 text-slate-300" />
                              )}
                            </button>
                            <div className="min-w-0">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="font-bold text-slate-900 text-xs truncate">{item.name}</span>
                                {item.type === 'company' ? (
                                  <span className="px-1.5 py-0.2 rounded text-[10px] font-bold text-emerald-700 bg-emerald-50 border border-emerald-200">
                                    Company
                                  </span>
                                ) : (
                                  <span className="px-1.5 py-0.2 rounded text-[10px] font-bold text-indigo-700 bg-indigo-50 border border-indigo-200 flex items-center gap-1">
                                    <User className="w-2.5 h-2.5" /> {item.company_name}
                                  </span>
                                )}
                              </div>
                              <p className="text-[11px] text-slate-500 truncate">{item.email}</p>
                            </div>
                          </div>
                          {item.designation && (
                            <span className="text-[10px] font-medium text-slate-400 shrink-0 ml-2">
                              {item.designation}
                            </span>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>

                {/* Paste bulk emails textarea */}
                <div className="mt-4 pt-3 border-t border-slate-100 shrink-0">
                  <label className="block text-xs font-medium text-slate-700 mb-1.5">
                    Or paste email addresses (comma, semicolon, or line separated)
                  </label>
                  <div className="flex gap-2">
                    <textarea
                      rows={2}
                      placeholder="e.g., contact1@example.com, contact2@example.com"
                      value={pasteInput}
                      onChange={(e) => setPasteInput(e.target.value)}
                      className="flex-1 bg-slate-50 border border-slate-200 rounded-xl p-2.5 text-xs text-slate-900 outline-none focus:ring-2 focus:ring-blue-100 focus:border-blue-500 transition"
                    />
                    <button
                      type="button"
                      onClick={handleAddPastedEmails}
                      className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white font-medium text-xs rounded-full shrink-0 transition shadow-2xs self-end cursor-pointer"
                    >
                      Add
                    </button>
                  </div>
                </div>
              </div>

              {/* Right Column: Selected Recipients Chips & Next Button */}
              <div className="lg:col-span-5 flex flex-col h-full bg-white rounded-2xl border border-slate-200 p-4 shadow-xs overflow-hidden">
                <div className="flex items-center justify-between mb-3 shrink-0">
                  <div className="flex items-center gap-2">
                    <h3 className="font-bold text-slate-900 text-sm">Selected Recipients</h3>
                    <span className="px-2 py-0.5 rounded-full text-xs font-black bg-indigo-100 text-indigo-800">
                      {selectedRecipients.length}
                    </span>
                  </div>
                  {selectedRecipients.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setSelectedRecipients([])}
                      className="text-xs font-bold text-rose-600 hover:text-rose-800 transition"
                    >
                      Clear All
                    </button>
                  )}
                </div>

                <div className="flex-1 overflow-y-auto space-y-2 p-1 border border-slate-100 rounded-xl">
                  {selectedRecipients.length === 0 ? (
                    <div className="p-8 text-center text-slate-400 text-xs font-medium">
                      No recipients selected yet. Check items from the pipeline directory on the left or paste emails below.
                    </div>
                  ) : (
                    selectedRecipients.map((rec) => (
                      <div
                        key={rec.email}
                        className="flex items-center justify-between p-2.5 bg-slate-50 border border-slate-200 rounded-xl text-xs"
                      >
                        <div className="min-w-0 pr-2">
                          <p className="font-bold text-slate-800 truncate">{rec.name || rec.email}</p>
                          <p className="text-[11px] text-slate-500 truncate">{rec.email}</p>
                        </div>
                        <button
                          type="button"
                          onClick={() => handleRemoveSelectedRecipient(rec.email)}
                          className="text-slate-400 hover:text-rose-600 p-1 transition shrink-0"
                          title="Remove recipient"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ))
                  )}
                </div>

                <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between shrink-0">
                  <button
                    type="button"
                    onClick={() => setCurrentTab('compose')}
                    className="px-4 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-full font-medium text-xs transition cursor-pointer"
                  >
                    Back
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      if (selectedRecipients.length === 0) {
                        return toast.error('Please select at least one recipient');
                      }
                      setCurrentTab('confirm');
                    }}
                    disabled={selectedRecipients.length === 0}
                    className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-medium text-xs rounded-full transition flex items-center gap-1.5 shadow-xs hover:shadow-md disabled:opacity-50 cursor-pointer"
                  >
                    <span>Next: Review</span>
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: REVIEW & SEND */}
          {currentTab === 'confirm' && (
            <div className="max-w-2xl mx-auto space-y-5 bg-white p-6 sm:p-7 rounded-2xl border border-slate-200 shadow-xs">
              <div className="flex items-center gap-3 pb-4 border-b border-slate-100">
                <div className="w-10 h-10 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center shrink-0">
                  <Send className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-semibold text-slate-900 text-base">Review campaign</h3>
                  <p className="text-xs text-slate-500">Check your details before sending.</p>
                </div>
              </div>

              {/* Metrics Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="p-3.5 bg-slate-50/80 border border-slate-200/70 rounded-xl">
                  <span className="text-[11px] font-medium text-slate-500">Recipients</span>
                  <p className="text-xl font-semibold text-slate-900 mt-0.5">{totalRecipientsCount}</p>
                </div>
                <div className="p-3.5 bg-slate-50/80 border border-slate-200/70 rounded-xl">
                  <span className="text-[11px] font-medium text-slate-500">Sending pace</span>
                  <p className="text-xl font-semibold text-slate-900 mt-0.5">90s interval</p>
                </div>
                <div className="p-3.5 bg-slate-50/80 border border-slate-200/70 rounded-xl">
                  <span className="text-[11px] font-medium text-slate-500">Estimated duration</span>
                  <p className="text-xl font-semibold text-slate-900 mt-0.5">{formattedDuration}</p>
                </div>
              </div>

              {/* Safe Delivery Reassurance Banner */}
              <div className="flex items-start gap-2.5 p-3.5 bg-blue-50/60 border border-blue-100 rounded-xl text-xs text-blue-900">
                <Clock className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
                <p className="leading-relaxed">
                  <span className="font-semibold text-blue-950">Safe delivery pacing: </span>
                  Emails send 1 at a time every 90 seconds to maximize deliverability. Delivery runs automatically in the background.
                </p>
              </div>

              {/* Summary Details */}
              <div className="divide-y divide-slate-100 rounded-xl border border-slate-200/70 bg-white overflow-hidden text-xs">
                <div className="flex justify-between items-center px-4 py-3">
                  <span className="text-slate-500 font-medium">Campaign name</span>
                  <span className="font-semibold text-slate-900">{campaignName || 'Untitled Campaign'}</span>
                </div>
                <div className="flex justify-between items-center px-4 py-3">
                  <span className="text-slate-500 font-medium">Subject</span>
                  <span className="font-semibold text-slate-900 truncate max-w-xs">{emailSubject || '(No subject)'}</span>
                </div>
                <div className="flex justify-between items-center px-4 py-3">
                  <span className="text-slate-500 font-medium">Open tracking</span>
                  <span className={`inline-flex items-center gap-1.5 font-medium ${openTrackingEnabled ? 'text-emerald-700' : 'text-slate-600'}`}>
                    <span className={`w-1.5 h-1.5 rounded-full ${openTrackingEnabled ? 'bg-emerald-500' : 'bg-slate-400'}`} />
                    {openTrackingEnabled ? 'Enabled' : 'Disabled'}
                  </span>
                </div>
                {attachments.length > 0 && (
                  <div className="flex justify-between items-center px-4 py-3">
                    <span className="text-slate-500 font-medium">Attachments</span>
                    <span className="font-semibold text-slate-900">{attachments.length} file(s) attached</span>
                  </div>
                )}
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-between pt-3 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setCurrentTab('recipients')}
                  disabled={submitting}
                  className="px-4 py-2 text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-full font-medium text-xs transition cursor-pointer"
                >
                  Back
                </button>
                <button
                  type="button"
                  onClick={handleLaunchCampaign}
                  disabled={submitting || totalRecipientsCount === 0}
                  className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 active:bg-blue-800 text-white font-medium text-sm rounded-full transition flex items-center gap-2 shadow-xs hover:shadow-md disabled:opacity-50 cursor-pointer"
                >
                  <Send className="w-4 h-4" />
                  <span>{submitting ? 'Starting campaign...' : 'Send campaign'}</span>
                </button>
              </div>
            </div>
          )}

          {/* TAB 4: CAMPAIGN MONITOR */}
          {currentTab === 'monitor' && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-full">
              {/* Left Column: Campaigns List */}
              <div className="lg:col-span-4 flex flex-col h-full bg-white rounded-2xl border border-slate-200 p-4 shadow-xs overflow-hidden">
                <div className="flex items-center justify-between mb-3 shrink-0">
                  <h3 className="font-bold text-slate-900 text-sm">Campaigns</h3>
                  <button
                    type="button"
                    onClick={fetchCampaigns}
                    disabled={loadingCampaigns}
                    className="p-1.5 text-slate-400 hover:text-slate-600 rounded-lg hover:bg-slate-100 transition"
                    title="Refresh campaigns"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${loadingCampaigns ? 'animate-spin' : ''}`} />
                  </button>
                </div>

                <div className="flex-1 overflow-y-auto space-y-2">
                  {campaigns.length === 0 ? (
                    <div className="p-8 text-center text-slate-400 text-xs font-medium">
                      No campaigns found. Click "1. Compose" to create one.
                    </div>
                  ) : (
                    campaigns.map((c) => {
                      const isSelected = activeCampaignDetail?.id === c.id;
                      const statusColor = 
                        c.status === 'RUNNING' ? 'bg-blue-50 text-blue-700 border-blue-200' :
                        c.status === 'QUEUED' ? 'bg-indigo-50 text-indigo-700 border-indigo-200' :
                        c.status === 'PAUSED' ? 'bg-amber-50 text-amber-700 border-amber-200' :
                        c.status === 'COMPLETED' ? 'bg-emerald-50 text-emerald-700 border-emerald-200' :
                        c.status === 'COMPLETED_WITH_ERRORS' ? 'bg-rose-50 text-rose-700 border-rose-200' :
                        'bg-slate-100 text-slate-600 border-slate-200';
                      
                      const statusLabel = 
                        c.status === 'RUNNING' ? 'In progress' :
                        c.status === 'QUEUED' ? 'Queued' :
                        c.status === 'PAUSED' ? 'Paused' :
                        c.status === 'COMPLETED' ? 'Completed' :
                        c.status === 'COMPLETED_WITH_ERRORS' ? 'Completed (errors)' :
                        c.status === 'CANCELLED' ? 'Cancelled' : c.status;

                      return (
                        <div
                          key={c.id}
                          onClick={() => fetchCampaignDetail(c.id)}
                          className={`p-3 rounded-xl border cursor-pointer transition ${
                            isSelected
                              ? 'bg-blue-50/70 border-blue-300 shadow-2xs'
                              : 'bg-white border-slate-200 hover:border-slate-300'
                          }`}
                        >
                          <div className="flex items-center justify-between gap-1 mb-1">
                            <h4 className="font-semibold text-slate-900 text-xs truncate flex-1">{c.name}</h4>
                            <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium border ${statusColor}`}>
                              {statusLabel}
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-500 truncate mb-2">{c.subject}</p>
                          <div className="flex items-center justify-between text-[10px] text-slate-400 font-medium">
                            <span>{c.sent_count}/{c.total_count} sent</span>
                            <span>{new Date(c.created_at).toLocaleDateString()}</span>
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>

                <div className="mt-3 pt-3 border-t border-slate-100 shrink-0">
                  <button
                    type="button"
                    onClick={() => setCurrentTab('compose')}
                    className="w-full py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium text-xs rounded-full transition flex items-center justify-center gap-1.5 shadow-2xs cursor-pointer"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Create new campaign</span>
                  </button>
                </div>
              </div>

              {/* Right Column: Active Campaign Detail & Controls */}
              <div className="lg:col-span-8 flex flex-col h-full bg-white rounded-2xl border border-slate-200 p-5 shadow-xs overflow-hidden">
                {!activeCampaignDetail ? (
                  <div className="flex flex-col items-center justify-center h-full text-slate-400 text-xs font-medium p-8">
                    <Clock className="w-8 h-8 text-slate-300 mb-2" />
                    <span>Select a campaign from the left column to view real-time progress and queue controls.</span>
                  </div>
                ) : (
                  <div className="flex flex-col h-full overflow-hidden space-y-4">
                    {/* Header info & Controls */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100 shrink-0">
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-semibold text-slate-900 text-base">{activeCampaignDetail.name}</h3>
                          <span className={`px-2.5 py-0.5 rounded-full text-[10px] font-medium border ${
                            activeCampaignDetail.status === 'RUNNING' ? 'bg-blue-50 text-blue-700 border-blue-300 animate-pulse' :
                            activeCampaignDetail.status === 'PAUSED' ? 'bg-amber-50 text-amber-700 border-amber-300' :
                            activeCampaignDetail.status === 'COMPLETED' ? 'bg-emerald-50 text-emerald-700 border-emerald-300' :
                            'bg-slate-100 text-slate-700 border-slate-300'
                          }`}>
                            {activeCampaignDetail.status === 'RUNNING' ? 'In progress' :
                             activeCampaignDetail.status === 'QUEUED' ? 'Queued' :
                             activeCampaignDetail.status === 'PAUSED' ? 'Paused' :
                             activeCampaignDetail.status === 'COMPLETED' ? 'Completed' :
                             activeCampaignDetail.status}
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 mt-0.5 font-normal">Subject: {activeCampaignDetail.subject}</p>
                      </div>

                      {/* Control buttons */}
                      <div className="flex items-center gap-2 shrink-0">
                        {['RUNNING', 'QUEUED'].includes(activeCampaignDetail.status) && (
                          <button
                            type="button"
                            onClick={() => handlePause(activeCampaignDetail.id)}
                            className="px-3.5 py-1.5 bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 hover:border-slate-300 font-medium text-xs rounded-full transition flex items-center gap-1.5 shadow-2xs cursor-pointer"
                          >
                            <Pause className="w-3.5 h-3.5" /> Pause
                          </button>
                        )}
                        {activeCampaignDetail.status === 'PAUSED' && (
                          <button
                            type="button"
                            onClick={() => handleResume(activeCampaignDetail.id)}
                            className="px-3.5 py-1.5 bg-blue-600 hover:bg-blue-700 text-white font-medium text-xs rounded-full transition flex items-center gap-1.5 shadow-2xs cursor-pointer"
                          >
                            <Play className="w-3.5 h-3.5" /> Resume
                          </button>
                        )}
                        {['RUNNING', 'QUEUED', 'PAUSED'].includes(activeCampaignDetail.status) && (
                          <button
                            type="button"
                            onClick={() => handleCancel(activeCampaignDetail.id)}
                            className="px-3.5 py-1.5 bg-white hover:bg-rose-50 text-rose-700 border border-rose-200 font-medium text-xs rounded-full transition flex items-center gap-1.5 cursor-pointer"
                          >
                            <Ban className="w-3.5 h-3.5" /> Cancel
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Progress Bar & Stats */}
                    <div className="space-y-3 shrink-0">
                      <div>
                        <div className="flex justify-between text-xs font-medium text-slate-600 mb-1.5">
                          <span>Progress: {activeCampaignDetail.sent_count} of {activeCampaignDetail.total_count} sent</span>
                          <span className="font-semibold text-slate-900">
                            {activeCampaignDetail.total_count > 0 
                              ? Math.round((activeCampaignDetail.sent_count / activeCampaignDetail.total_count) * 100) 
                              : 0}%
                          </span>
                        </div>
                        <div className="w-full h-2 bg-slate-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-blue-600 transition-all duration-500 rounded-full"
                            style={{
                              width: `${activeCampaignDetail.total_count > 0 
                                ? (activeCampaignDetail.sent_count / activeCampaignDetail.total_count) * 100 
                                : 0}%`
                            }}
                          />
                        </div>
                      </div>

                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-center text-xs">
                        <div className="p-2.5 bg-slate-50 border border-slate-200/70 rounded-xl">
                          <span className="text-[11px] text-slate-500 font-medium">Total</span>
                          <p className="font-semibold text-slate-900 text-sm mt-0.5">{activeCampaignDetail.total_count}</p>
                        </div>
                        <div className="p-2.5 bg-emerald-50/70 border border-emerald-200/70 rounded-xl">
                          <span className="text-[11px] text-emerald-700 font-medium">Sent</span>
                          <p className="font-semibold text-emerald-800 text-sm mt-0.5">{activeCampaignDetail.sent_count}</p>
                        </div>
                        <div className="p-2.5 bg-blue-50/70 border border-blue-200/70 rounded-xl">
                          <span className="text-[11px] text-blue-700 font-medium">In queue</span>
                          <p className="font-semibold text-blue-800 text-sm mt-0.5">{activeCampaignDetail.pending_count}</p>
                        </div>
                        <div className="p-2.5 bg-rose-50/70 border border-rose-200/70 rounded-xl">
                          <span className="text-[11px] text-rose-700 font-medium">Failed</span>
                          <p className="font-semibold text-rose-800 text-sm mt-0.5">{activeCampaignDetail.failed_count}</p>
                        </div>
                      </div>

                      {/* Next Send Time Banner */}
                      {['RUNNING', 'QUEUED'].includes(activeCampaignDetail.status) && activeCampaignDetail.next_eligible_at && (
                        <div className="p-3 bg-blue-50/70 border border-blue-200/70 rounded-xl text-xs text-blue-900 flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            <Clock className="w-4 h-4 text-blue-600 shrink-0" />
                            <span>Next email sends at:</span>
                          </div>
                          <span className="font-semibold text-blue-950 font-mono">
                            {new Date(activeCampaignDetail.next_eligible_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Recipients Queue Table */}
                    <div className="flex-1 overflow-hidden flex flex-col border border-slate-200 rounded-xl">
                      <div className="px-3 py-2 bg-slate-50/80 border-b border-slate-200 flex items-center justify-between text-xs font-medium text-slate-600 shrink-0">
                        <span>Recipients ({activeCampaignDetail.recipients?.length || 0})</span>
                        <span className="text-[11px] text-slate-500">90s interval</span>
                      </div>
                      <div className="flex-1 overflow-y-auto divide-y divide-slate-100">
                        {activeCampaignDetail.recipients?.map((r, i) => (
                          <div key={r.id} className="p-2.5 flex items-center justify-between text-xs hover:bg-slate-50 transition">
                            <div className="flex items-center gap-2.5 min-w-0">
                              <span className="w-5 text-[11px] font-mono text-slate-400 shrink-0">#{i + 1}</span>
                              <div className="min-w-0">
                                <p className="font-medium text-slate-900 truncate">
                                  {r.recipient_name || r.prospect_company_name || r.email_address}
                                </p>
                                <p className="text-[11px] text-slate-500 truncate">{r.email_address}</p>
                              </div>
                            </div>

                            <div className="flex items-center gap-2 shrink-0 ml-2">
                              {r.error_message && (
                                <span className="text-[10px] text-rose-600 max-w-[150px] truncate" title={r.error_message}>
                                  {r.error_message}
                                </span>
                              )}
                              <span className={`px-2 py-0.5 rounded-full text-[10px] font-medium border ${
                                r.status === 'SENT' ? 'bg-emerald-50 text-emerald-700 border-emerald-300' :
                                r.status === 'SENDING' ? 'bg-blue-50 text-blue-700 border-blue-300 animate-pulse' :
                                r.status === 'RETRY_PENDING' ? 'bg-amber-50 text-amber-700 border-amber-300' :
                                r.status === 'FAILED' ? 'bg-rose-50 text-rose-700 border-rose-300' :
                                'bg-slate-100 text-slate-600 border-slate-200'
                              }`}>
                                {r.status === 'SENT' ? 'Sent' : r.status === 'SENDING' ? 'Sending' : r.status === 'PENDING' ? 'In queue' : r.status}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
