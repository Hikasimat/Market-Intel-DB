import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  X,
  BookOpen,
  Upload,
  FileText,
  Trash2,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  ShieldCheck,
  Sliders,
  Sparkles,
  Plus,
  Edit2,
  Check,
  Layers,
  Search,
  Database,
  Link as LinkIcon,
  Unlink,
} from 'lucide-react';
import api from '../../services/api';

const IN_FLIGHT_STATUSES = new Set([
  'UPLOADED',
  'VALIDATING',
  'PROCESSING',
  'CHUNKING',
  'EMBEDDING',
]);

function formatBytes(bytes) {
  const n = Number(bytes || 0);
  if (!n) return '0 B';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function formatDateTime(iso) {
  if (!iso) return '—';
  try {
    return new Date(iso).toLocaleString();
  } catch {
    return String(iso);
  }
}

function statusBadgeStyle(status) {
  switch (status) {
    case 'READY':
      return 'bg-emerald-50 text-emerald-700 border-emerald-200';
    case 'FAILED':
      return 'bg-rose-50 text-rose-700 border-rose-200';
    case 'DELETING':
      return 'bg-slate-100 text-slate-500 border-slate-200';
    default:
      return 'bg-amber-50 text-amber-700 border-amber-200';
  }
}

export default function WhatsAppKnowledgeBaseModal({
  isOpen,
  onClose,
  selectedSession,
  user,
  onShowToast,
}) {
  const [activeTab, setActiveTab] = useState('bases'); // 'bases' | 'documents' | 'settings' | 'test'

  // Knowledge Bases state
  const [knowledgeBases, setKnowledgeBases] = useState([]);
  const [loadingKBs, setLoadingKBs] = useState(false);
  const [selectedKBId, setSelectedKBId] = useState('');
  const [kbStats, setKbStats] = useState(null);

  // Create KB form
  const [newKBName, setNewKBName] = useState('');
  const [newKBDesc, setNewKBDesc] = useState('');
  const [newKBCompanyLevel, setNewKBCompanyLevel] = useState(false);
  const [creatingKB, setCreatingKB] = useState(false);

  // Edit KB state
  const [editingKBId, setEditingKBId] = useState(null);
  const [editKBName, setEditKBName] = useState('');
  const [editKBDesc, setEditKBDesc] = useState('');
  const [savingKB, setSavingKB] = useState(false);

  // Documents state
  const [documents, setDocuments] = useState([]);
  const [loadingDocs, setLoadingDocs] = useState(false);
  const [uploadingDoc, setUploadingDoc] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const fileInputRef = useRef(null);

  // Session AI & Strict RAG settings state
  const [sessionConfigs, setSessionConfigs] = useState([]);
  const [selectedConfigSessionId, setSelectedConfigSessionId] = useState('');
  const [loadingSettings, setLoadingSettings] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [assigningKB, setAssigningKB] = useState(false);

  // Retrieval tuning inputs (for Managers / SuperAdmins)
  const [tuningTopK, setTuningTopK] = useState('');
  const [tuningThreshold, setTuningThreshold] = useState('');
  const [tuningRefusalMsg, setTuningRefusalMsg] = useState('');

  // Test Playground state
  const [testTargetMode, setTestTargetMode] = useState('kb'); // 'kb' | 'session'
  const [testQuestion, setTestQuestion] = useState('');
  const [runningTest, setRunningTest] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const isSuperAdmin = Boolean(user?.is_superuser);
  const isAdminOrManager = Boolean(
    user?.is_superuser ||
      user?.role === 'MANAGER' ||
      user?.profile?.role === 'MANAGER'
  );

  const onShowToastRef = useRef(onShowToast);
  useEffect(() => {
    onShowToastRef.current = onShowToast;
  }, [onShowToast]);

  const selectedSessionRef = useRef(selectedSession);
  useEffect(() => {
    selectedSessionRef.current = selectedSession;
  }, [selectedSession]);

  const notify = useCallback((msg, type = 'info') => {
    if (onShowToastRef.current) {
      onShowToastRef.current(msg, type);
    }
  }, []);

  const fetchKnowledgeBases = useCallback(async (silent = false) => {
    if (!silent) setLoadingKBs(true);
    try {
      const res = await api.get('/rag/knowledge-bases/');
      const list = Array.isArray(res.data)
        ? res.data
        : res.data?.results || [];
      setKnowledgeBases(list);
      setSelectedKBId((prev) => {
        if (prev && list.some((k) => String(k.id) === String(prev))) {
          return prev;
        }
        return list[0]?.id ? String(list[0].id) : '';
      });
    } catch (err) {
      if (!silent && err.response?.status !== 401) {
        notify(
          err.response?.data?.detail || 'Failed to load knowledge bases.',
          'error'
        );
      }
    } finally {
      if (!silent) setLoadingKBs(false);
    }
  }, [notify]);

  const fetchDocumentsAndStats = useCallback(
    async (kbId, silent = false) => {
      if (!kbId) {
        setDocuments([]);
        setKbStats(null);
        return;
      }
      if (!silent) setLoadingDocs(true);
      try {
        const [docsRes, statsRes] = await Promise.all([
          api.get(`/rag/knowledge-bases/${kbId}/documents/`),
          api.get(`/rag/knowledge-bases/${kbId}/statistics/`),
        ]);
        const list = Array.isArray(docsRes.data)
          ? docsRes.data
          : docsRes.data?.results || [];
        setDocuments(list);
        setKbStats(statsRes.data || null);
      } catch (err) {
        if (!silent && err.response?.status !== 401) {
          notify(
            err.response?.data?.detail || 'Failed to load documents.',
            'error'
          );
        }
      } finally {
        if (!silent) setLoadingDocs(false);
      }
    },
    [notify]
  );

  const fetchSessionSettings = useCallback(async (silent = false) => {
    if (!silent) setLoadingSettings(true);
    try {
      const res = await api.get('/rag/session-settings/');
      const list = res.data?.results || [];
      setSessionConfigs(list);
      const curSess = selectedSessionRef.current;
      setSelectedConfigSessionId((prev) => {
        if (prev && list.some((s) => String(s.session_id) === String(prev))) {
          return prev;
        }
        if (curSess?.id && list.some((s) => String(s.session_id) === String(curSess.id))) {
          return String(curSess.id);
        }
        const byName = curSess?.session_name
          ? list.find((s) => s.session_name === curSess.session_name)
          : null;
        if (byName) return String(byName.session_id);
        return list[0]?.session_id ? String(list[0].session_id) : '';
      });
    } catch (err) {
      if (!silent && err.response?.status !== 401) {
        notify(
          err.response?.data?.detail || 'Failed to load WhatsApp AI settings.',
          'error'
        );
      }
    } finally {
      if (!silent) setLoadingSettings(false);
    }
  }, [notify]);

  useEffect(() => {
    if (!isOpen) return;
    fetchKnowledgeBases();
    fetchSessionSettings();
  }, [isOpen, fetchKnowledgeBases, fetchSessionSettings]);

  useEffect(() => {
    if (!isOpen || !selectedKBId) return;
    fetchDocumentsAndStats(selectedKBId);
  }, [isOpen, selectedKBId, fetchDocumentsAndStats]);

  // Poll while any document in the selected KB is still processing
  useEffect(() => {
    if (!isOpen || !selectedKBId) return undefined;
    const hasInFlight = documents.some((d) => IN_FLIGHT_STATUSES.has(d.status));
    if (!hasInFlight) return undefined;
    const timer = setInterval(() => {
      fetchDocumentsAndStats(selectedKBId, true);
      fetchKnowledgeBases(true);
      fetchSessionSettings(true);
    }, 3000);
    return () => clearInterval(timer);
  }, [
    isOpen,
    selectedKBId,
    documents,
    fetchDocumentsAndStats,
    fetchKnowledgeBases,
    fetchSessionSettings,
  ]);

  const currentSessionConfig = sessionConfigs.find(
    (s) => String(s.session_id) === String(selectedConfigSessionId)
  );

  useEffect(() => {
    if (!currentSessionConfig) return;
    setTuningTopK(
      currentSessionConfig.top_k != null ? String(currentSessionConfig.top_k) : ''
    );
    setTuningThreshold(
      currentSessionConfig.min_relevance_threshold != null
        ? String(currentSessionConfig.min_relevance_threshold)
        : ''
    );
    setTuningRefusalMsg(currentSessionConfig.refusal_message || '');
  }, [currentSessionConfig]);

  if (!isOpen) return null;

  const selectedKB = knowledgeBases.find(
    (k) => String(k.id) === String(selectedKBId)
  );

  // ── Knowledge Base CRUD handlers ───────────────────────────────────────────
  const handleCreateKB = async (e) => {
    e.preventDefault();
    if (!newKBName.trim()) {
      notify('Knowledge Base name is required.', 'error');
      return;
    }
    setCreatingKB(true);
    try {
      const res = await api.post('/rag/knowledge-bases/', {
        name: newKBName.trim(),
        description: newKBDesc.trim(),
        company_level: newKBCompanyLevel,
      });
      notify(`Knowledge Base "${res.data.name}" created.`, 'success');
      setNewKBName('');
      setNewKBDesc('');
      setNewKBCompanyLevel(false);
      await fetchKnowledgeBases();
      if (res.data?.id) {
        setSelectedKBId(String(res.data.id));
      }
    } catch (err) {
      const data = err.response?.data;
      const msg =
        data?.name?.[0] ||
        data?.company_level?.[0] ||
        data?.detail ||
        'Could not create knowledge base.';
      notify(msg, 'error');
    } finally {
      setCreatingKB(false);
    }
  };

  const handleToggleKBActive = async (kb) => {
    try {
      await api.patch(`/rag/knowledge-bases/${kb.id}/`, {
        is_active: !kb.is_active,
      });
      notify(
        `Knowledge Base "${kb.name}" ${!kb.is_active ? 'activated' : 'deactivated'}.`,
        'success'
      );
      fetchKnowledgeBases();
      fetchSessionSettings();
    } catch (err) {
      notify(
        err.response?.data?.detail || 'Failed to update knowledge base status.',
        'error'
      );
    }
  };

  const handleSaveEditKB = async (kbId) => {
    if (!editKBName.trim()) {
      notify('Name cannot be empty.', 'error');
      return;
    }
    setSavingKB(true);
    try {
      await api.patch(`/rag/knowledge-bases/${kbId}/`, {
        name: editKBName.trim(),
        description: editKBDesc.trim(),
      });
      notify('Knowledge Base updated.', 'success');
      setEditingKBId(null);
      fetchKnowledgeBases();
      fetchSessionSettings();
    } catch (err) {
      notify(
        err.response?.data?.name?.[0] ||
          err.response?.data?.detail ||
          'Failed to update knowledge base.',
        'error'
      );
    } finally {
      setSavingKB(false);
    }
  };

  const handleDeleteKB = async (kb) => {
    if (
      !window.confirm(
        `Delete Knowledge Base "${kb.name}" and all of its indexed documents? This action cannot be undone.`
      )
    ) {
      return;
    }
    try {
      await api.delete(`/rag/knowledge-bases/${kb.id}/`);
      notify(`Knowledge Base "${kb.name}" deleted.`, 'success');
      if (String(selectedKBId) === String(kb.id)) {
        setSelectedKBId('');
      }
      fetchKnowledgeBases();
      fetchSessionSettings();
    } catch (err) {
      notify(
        err.response?.data?.detail || 'Could not delete knowledge base.',
        'error'
      );
    }
  };

  // ── Document handlers ──────────────────────────────────────────────────────
  const handleFileSelected = async (e) => {
    const file = e.target.files?.[0];
    if (fileInputRef.current) fileInputRef.current.value = '';
    if (!file) return;

    let targetKBId = selectedKBId;
    setUploadingDoc(true);
    setUploadProgress(0);

    try {
      // If Super Admin uploads a file when no Knowledge Base exists yet, auto-create one dynamically
      if (!targetKBId) {
        const kbRes = await api.post('/rag/knowledge-bases/', {
          name: 'General Knowledge Base',
          description: 'Global dynamic knowledge base for WhatsApp AI',
        });
        targetKBId = String(kbRes.data.id);
        setSelectedKBId(targetKBId);
      }

      const formData = new FormData();
      formData.append('file', file);

      await api.post(`/rag/knowledge-bases/${targetKBId}/documents/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (evt) => {
          if (evt.total) {
            setUploadProgress(Math.round((evt.loaded * 100) / evt.total));
          }
        },
      });
      notify(`Uploaded "${file.name}". Ingestion queued.`, 'success');
      fetchDocumentsAndStats(targetKBId);
      fetchKnowledgeBases();
      fetchSessionSettings();
    } catch (err) {
      notify(
        err.response?.data?.detail || `Upload failed for "${file.name}".`,
        'error'
      );
    } finally {
      setUploadingDoc(false);
      setUploadProgress(0);
    }
  };

  const handleRetryDocument = async (doc) => {
    try {
      await api.post(`/rag/documents/${doc.id}/retry/`);
      notify(`Retrying ingestion for "${doc.original_filename}".`, 'info');
      fetchDocumentsAndStats(selectedKBId);
    } catch (err) {
      notify(
        err.response?.data?.detail || 'Could not retry document.',
        'error'
      );
    }
  };

  const handleDeleteDocument = async (doc) => {
    if (
      !window.confirm(
        `Delete document "${doc.original_filename}" and remove all of its vector chunks?`
      )
    ) {
      return;
    }
    try {
      await api.delete(`/rag/documents/${doc.id}/`);
      notify(`Deleted "${doc.original_filename}".`, 'success');
      fetchDocumentsAndStats(selectedKBId);
      fetchKnowledgeBases();
      fetchSessionSettings();
    } catch (err) {
      notify(
        err.response?.data?.detail || 'Could not delete document.',
        'error'
      );
    }
  };

  // ── Session Assignment & Strict RAG Settings handlers ──────────────────────
  const handleAssignKnowledgeBase = async (kbIdValue) => {
    if (!currentSessionConfig) return;
    setAssigningKB(true);
    try {
      if (!kbIdValue) {
        // Unassign if currently assigned
        const assignmentId = currentSessionConfig.knowledge_base?.assignment_id;
        if (assignmentId) {
          await api.delete(`/rag/session-assignments/${assignmentId}/`);
          notify('Knowledge Base unassigned from session.', 'info');
        }
      } else {
        await api.post('/rag/session-assignments/', {
          session: currentSessionConfig.session_id,
          knowledge_base: kbIdValue,
          is_active: true,
        });
        notify('Knowledge Base assigned to WhatsApp session.', 'success');
      }
      await fetchSessionSettings();
      await fetchKnowledgeBases();
    } catch (err) {
      const data = err.response?.data;
      const msg =
        data?.detail ||
        data?.non_field_errors?.[0] ||
        'Could not update knowledge base assignment.';
      notify(msg, 'error');
    } finally {
      setAssigningKB(false);
    }
  };

  const handlePatchSessionSetting = async (payload, successMsg) => {
    if (!currentSessionConfig) return;
    setSavingSettings(true);
    try {
      await api.patch(
        `/rag/session-settings/${currentSessionConfig.session_id}/`,
        payload
      );
      notify(successMsg || 'WhatsApp AI settings updated.', 'success');
      await fetchSessionSettings();
    } catch (err) {
      const data = err.response?.data;
      const msg =
        data?.strict_rag_enabled?.[0] ||
        data?.strict_rag_enabled ||
        data?.detail ||
        'Failed to update session AI settings.';
      notify(String(msg), 'error');
    } finally {
      setSavingSettings(false);
    }
  };

  const handleSaveRetrievalTuning = async (e) => {
    e.preventDefault();
    const payload = {
      refusal_message: tuningRefusalMsg,
      top_k: tuningTopK === '' ? null : Number(tuningTopK),
      min_relevance_threshold:
        tuningThreshold === '' ? null : Number(tuningThreshold),
    };
    await handlePatchSessionSetting(
      payload,
      'Retrieval configuration saved.'
    );
  };

  // ── Test Query handler ─────────────────────────────────────────────────────
  const handleRunTestQuery = async (e) => {
    e.preventDefault();
    if (!testQuestion.trim()) {
      notify('Enter a question to test.', 'error');
      return;
    }
    const payload = { question: testQuestion.trim() };
    if (testTargetMode === 'session') {
      if (!selectedConfigSessionId) {
        notify('Select a WhatsApp session first.', 'error');
        return;
      }
      payload.session_id = String(selectedConfigSessionId);
    } else {
      if (!selectedKBId) {
        notify('Select a Knowledge Base first.', 'error');
        return;
      }
      payload.knowledge_base_id = selectedKBId;
    }

    setRunningTest(true);
    setTestResult(null);
    try {
      const res = await api.post('/rag/test-query/', payload);
      setTestResult(res.data);
    } catch (err) {
      notify(
        err.response?.data?.detail || 'Knowledge Base test query failed.',
        'error'
      );
    } finally {
      setRunningTest(false);
    }
  };

  const sessionKBReady = Boolean(
    currentSessionConfig?.knowledge_base?.readiness?.is_ready
  );

  return (
    <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl max-w-5xl w-full max-h-[90vh] flex flex-col overflow-hidden border border-slate-200">
        {/* Header */}
        <div className="h-16 px-6 bg-[#00a884] text-white flex items-center justify-between flex-shrink-0">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-white/15 flex items-center justify-center">
              <BookOpen className="w-5 h-5 text-white" />
            </div>
            <div>
              <h2 className="font-bold text-base tracking-wide">
                WhatsApp AI Knowledge Base (Strict RAG)
              </h2>
              <p className="text-xs text-emerald-100">
                Ground WhatsApp AI replies exclusively in your uploaded documents
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            {isSuperAdmin ? (
              <span className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-bold bg-white/20 text-white border border-white/30">
                <ShieldCheck className="w-3.5 h-3.5" />
                Super Admin • Document Ingestion Enabled
              </span>
            ) : (
              <span className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-semibold bg-black/20 text-emerald-50 border border-white/15">
                Read-Only Documents • Super Admin Ingests
              </span>
            )}
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded-lg text-white/80 hover:text-white hover:bg-white/10 transition"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Navigation Tabs */}
        <div className="px-6 bg-slate-50 border-b border-slate-200 flex items-center gap-2 overflow-x-auto flex-shrink-0">
          {[
            { id: 'bases', label: 'Knowledge Bases', icon: Database },
            { id: 'documents', label: 'Documents & Ingestion', icon: FileText },
            { id: 'settings', label: 'WhatsApp AI Settings', icon: ShieldCheck },
            { id: 'test', label: 'Test Knowledge Base', icon: Sparkles },
          ].map((tab) => {
            const Icon = tab.icon;
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-3 text-xs font-semibold border-b-2 transition whitespace-nowrap ${
                  active
                    ? 'border-[#00a884] text-[#00a884] bg-white'
                    : 'border-transparent text-slate-600 hover:text-slate-900'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{tab.label}</span>
              </button>
            );
          })}
        </div>

        {/* Body */}
        <div className="p-6 overflow-y-auto flex-1 space-y-6 bg-white">
          {/* =============================================================== */}
          {/* TAB 1: KNOWLEDGE BASES */}
          {/* =============================================================== */}
          {activeTab === 'bases' && (
            <div className="space-y-6">
              {/* Create KB Form — Super Admin Only */}
              {isSuperAdmin ? (
                <form
                  onSubmit={handleCreateKB}
                  className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3"
                >
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
                      <Plus className="w-4 h-4 text-[#00a884]" />
                      Create New Knowledge Base
                    </h3>
                    <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-200">
                      Super Admin Only
                    </span>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <input
                      type="text"
                      value={newKBName}
                      onChange={(e) => setNewKBName(e.target.value)}
                      placeholder="Knowledge Base Name (e.g., Product Catalogue 2026)"
                      className="bg-white border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#00a884]"
                    />
                    <input
                      type="text"
                      value={newKBDesc}
                      onChange={(e) => setNewKBDesc(e.target.value)}
                      placeholder="Description (optional)"
                      className="bg-white border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#00a884]"
                    />
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
                    <span className="text-xs text-slate-500">
                      Created by Super Admin for WhatsApp Strict RAG document ingestion
                    </span>
                    <button
                      type="submit"
                      disabled={creatingKB}
                      className="px-4 py-2 bg-[#00a884] hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-sm transition disabled:opacity-50"
                    >
                      {creatingKB ? 'Creating...' : 'Create Knowledge Base'}
                    </button>
                  </div>
                </form>
              ) : (
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start gap-3 text-xs text-amber-900">
                  <ShieldCheck className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="font-bold text-sm text-amber-900">
                      Knowledge Base & Document Ingestion Managed by Super Admin
                    </p>
                    <p className="mt-0.5 text-amber-800">
                      Only a <strong>Super Admin</strong> can create Knowledge Bases and ingest documents. You can inspect available Knowledge Bases below, assign a ready Knowledge Base to your WhatsApp session in <strong>WhatsApp AI Settings</strong>, and test questions in <strong>Test Knowledge Base</strong>.
                    </p>
                  </div>
                </div>
              )}

              {/* Existing KBs list */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-slate-800">
                    Your Knowledge Bases ({knowledgeBases.length})
                  </h3>
                  <button
                    type="button"
                    onClick={fetchKnowledgeBases}
                    className="text-xs text-[#00a884] hover:underline flex items-center gap-1"
                  >
                    <RefreshCw
                      className={`w-3.5 h-3.5 ${loadingKBs ? 'animate-spin' : ''}`}
                    />
                    Refresh
                  </button>
                </div>

                {knowledgeBases.length === 0 ? (
                  <div className="p-8 text-center border border-dashed border-slate-200 rounded-xl text-slate-400 text-sm">
                    No Knowledge Bases created yet. Create one above to upload documents.
                  </div>
                ) : (
                  <div className="divide-y divide-slate-200 border border-slate-200 rounded-xl overflow-hidden">
                    {knowledgeBases.map((kb) => {
                      const isEditing = editingKBId === kb.id;
                      const readiness = kb.readiness || {};
                      return (
                        <div
                          key={kb.id}
                          className="p-4 bg-white hover:bg-slate-50/70 transition flex flex-col md:flex-row md:items-center justify-between gap-4"
                        >
                          <div className="space-y-1.5 flex-1 min-w-0">
                            {isEditing ? (
                              <div className="space-y-2 max-w-lg">
                                <input
                                  type="text"
                                  value={editKBName}
                                  onChange={(e) => setEditKBName(e.target.value)}
                                  className="w-full border border-slate-300 rounded-lg px-3 py-1.5 text-sm"
                                />
                                <input
                                  type="text"
                                  value={editKBDesc}
                                  onChange={(e) => setEditKBDesc(e.target.value)}
                                  placeholder="Description"
                                  className="w-full border border-slate-300 rounded-lg px-3 py-1.5 text-xs"
                                />
                                <div className="flex gap-2">
                                  <button
                                    type="button"
                                    disabled={savingKB}
                                    onClick={() => handleSaveEditKB(kb.id)}
                                    className="px-3 py-1 bg-[#00a884] text-white rounded-lg text-xs font-semibold flex items-center gap-1"
                                  >
                                    <Check className="w-3.5 h-3.5" /> Save
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => setEditingKBId(null)}
                                    className="px-3 py-1 bg-slate-200 text-slate-700 rounded-lg text-xs font-semibold"
                                  >
                                    Cancel
                                  </button>
                                </div>
                              </div>
                            ) : (
                              <>
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="font-bold text-sm text-slate-800">
                                    {kb.name}
                                  </span>
                                  <span
                                    className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${
                                      kb.is_active
                                        ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                        : 'bg-slate-100 text-slate-600 border-slate-200'
                                    }`}
                                  >
                                    {kb.is_active ? 'Active' : 'Inactive'}
                                  </span>
                                  <span
                                    className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${
                                      readiness.is_ready
                                        ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                        : 'bg-amber-50 text-amber-700 border-amber-200'
                                    }`}
                                  >
                                    {readiness.is_ready
                                      ? `Ready (${readiness.ready_documents}/${readiness.total_documents} docs)`
                                      : `Not Ready (${readiness.ready_documents || 0} ready docs)`}
                                  </span>
                                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 uppercase font-medium">
                                    {kb.scope}
                                  </span>
                                </div>
                                {kb.description && (
                                  <p className="text-xs text-slate-500">
                                    {kb.description}
                                  </p>
                                )}
                                <div className="flex items-center gap-3 text-[11px] text-slate-500 flex-wrap">
                                  <span>
                                    Assigned Sessions:{' '}
                                    {kb.assigned_sessions?.length
                                      ? kb.assigned_sessions
                                          .map((s) => s.session_name)
                                          .join(', ')
                                      : 'None'}
                                  </span>
                                  <span>•</span>
                                  <span>
                                    Created: {formatDateTime(kb.created_at)}
                                  </span>
                                </div>
                              </>
                            )}
                          </div>

                          {/* KB Actions */}
                          <div className="flex items-center gap-2 flex-wrap">
                            <button
                              type="button"
                              onClick={() => {
                                setSelectedKBId(String(kb.id));
                                setActiveTab('documents');
                              }}
                              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-50 text-emerald-700 hover:bg-emerald-100 transition"
                            >
                              Documents ({kb.document_count || 0})
                            </button>
                            <button
                              type="button"
                              onClick={() => {
                                setSelectedKBId(String(kb.id));
                                setTestTargetMode('kb');
                                setActiveTab('test');
                              }}
                              className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200 transition"
                            >
                              Test
                            </button>
                            {kb.can_edit && (
                              <>
                                <button
                                  type="button"
                                  onClick={() => handleToggleKBActive(kb)}
                                  className="px-2.5 py-1.5 rounded-lg text-xs font-medium border border-slate-200 text-slate-700 hover:bg-slate-100 transition"
                                >
                                  {kb.is_active ? 'Deactivate' : 'Activate'}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setEditingKBId(kb.id);
                                    setEditKBName(kb.name);
                                    setEditKBDesc(kb.description || '');
                                  }}
                                  className="p-1.5 rounded-lg text-slate-500 hover:bg-slate-100"
                                  title="Edit Knowledge Base"
                                >
                                  <Edit2 className="w-4 h-4" />
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleDeleteKB(kb)}
                                  className="p-1.5 rounded-lg text-rose-600 hover:bg-rose-50"
                                  title="Delete Knowledge Base"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </button>
                              </>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* =============================================================== */}
          {/* TAB 2: DOCUMENTS & INGESTION */}
          {/* =============================================================== */}
          {activeTab === 'documents' && (
            <div className="space-y-5">
              {/* KB selector + stats bar */}
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 bg-slate-50 p-4 rounded-xl border border-slate-200">
                <div className="flex items-center gap-3 flex-1">
                  <label className="text-xs font-bold uppercase text-slate-600 whitespace-nowrap">
                    Knowledge Base:
                  </label>
                  <select
                    value={selectedKBId}
                    onChange={(e) => setSelectedKBId(e.target.value)}
                    className="bg-white border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#00a884] flex-1 max-w-md"
                  >
                    {knowledgeBases.length === 0 && (
                      <option value="">No Knowledge Base available</option>
                    )}
                    {knowledgeBases.map((kb) => (
                      <option key={kb.id} value={kb.id}>
                        {kb.name} ({kb.readiness?.ready_documents || 0} ready)
                      </option>
                    ))}
                  </select>
                </div>

                {kbStats && (
                  <div className="flex items-center gap-4 text-xs text-slate-600">
                    <span>
                      Total Chunks: <strong>{kbStats.total_chunks || 0}</strong>
                    </span>
                    <span>
                      Storage: <strong>{formatBytes(kbStats.total_size_bytes)}</strong>
                    </span>
                  </div>
                )}
              </div>

              {/* Upload Box — Strictly Restricted to Super Admin */}
              {isSuperAdmin ? (
                <div className="border-2 border-dashed border-emerald-300 bg-emerald-50/40 rounded-xl p-5 flex flex-col sm:flex-row items-center justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <h4 className="text-sm font-semibold text-slate-800 flex items-center gap-2">
                        <Upload className="w-4 h-4 text-[#00a884]" />
                        {selectedKB
                          ? `Ingest Document into "${selectedKB.name}"`
                          : 'Ingest Document (Auto-creates Global Knowledge Base)'}
                      </h4>
                      <span className="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-800 border border-emerald-200">
                        Super Admin Only
                      </span>
                    </div>
                    <p className="text-xs text-slate-500">
                      Supported formats: PDF, DOCX, XLSX, CSV, TXT, Markdown (.md). Max 20 MB.
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".pdf,.docx,.xlsx,.csv,.txt,.md,.markdown"
                      onChange={handleFileSelected}
                      className="hidden"
                    />
                    <button
                      type="button"
                      disabled={uploadingDoc}
                      onClick={() => fileInputRef.current?.click()}
                      className="px-4 py-2 bg-[#00a884] hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-sm transition disabled:opacity-50 flex items-center gap-2"
                    >
                      <Upload className="w-4 h-4" />
                      {uploadingDoc
                        ? `Ingesting (${uploadProgress}%)...`
                        : 'Select File to Ingest'}
                    </button>
                  </div>
                </div>
              ) : (
                <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start gap-3 text-xs text-amber-900">
                  <ShieldCheck className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="font-bold text-sm text-amber-900">
                      Document Ingestion Restricted to Super Admin
                    </p>
                    <p className="mt-0.5 text-amber-800">
                      Only a <strong>Super Admin</strong> has permission to upload, ingest, retry, or delete Knowledge Base documents. You can view ingested documents below, assign a ready Knowledge Base to your WhatsApp session, and test questions in the Test tab.
                    </p>
                  </div>
                </div>
              )}

              {uploadingDoc && (
                <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                  <div
                    className="bg-[#00a884] h-full transition-all"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
              )}

              {/* Documents Table */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-semibold text-slate-800">
                    Uploaded Documents ({documents.length})
                  </h4>
                  <button
                    type="button"
                    onClick={() => fetchDocumentsAndStats(selectedKBId)}
                    className="text-xs text-[#00a884] hover:underline flex items-center gap-1"
                  >
                    <RefreshCw
                      className={`w-3.5 h-3.5 ${loadingDocs ? 'animate-spin' : ''}`}
                    />
                    Refresh Status
                  </button>
                </div>

                {documents.length === 0 ? (
                  <div className="p-8 text-center border border-dashed border-slate-200 rounded-xl text-slate-400 text-sm">
                    No documents uploaded to this Knowledge Base yet.
                  </div>
                ) : (
                  <div className="overflow-x-auto border border-slate-200 rounded-xl">
                    <table className="w-full text-left border-collapse text-xs">
                      <thead>
                        <tr className="bg-slate-50 text-slate-600 border-b border-slate-200">
                          <th className="py-2.5 px-3 font-semibold">Document</th>
                          <th className="py-2.5 px-3 font-semibold">Type / Size</th>
                          <th className="py-2.5 px-3 font-semibold">Status</th>
                          <th className="py-2.5 px-3 font-semibold">Chunks</th>
                          <th className="py-2.5 px-3 font-semibold">Uploaded</th>
                          <th className="py-2.5 px-3 font-semibold">Completed</th>
                          <th className="py-2.5 px-3 font-semibold text-right">
                            Actions
                          </th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-200">
                        {documents.map((doc) => {
                          const inFlight = IN_FLIGHT_STATUSES.has(doc.status);
                          return (
                            <tr key={doc.id} className="hover:bg-slate-50/80">
                              <td className="py-3 px-3">
                                <div className="font-semibold text-slate-800">
                                  {doc.original_filename}{' '}
                                  <span className="text-[10px] text-slate-400 font-normal">
                                    v{doc.version}
                                  </span>
                                </div>
                                {doc.processing_error && (
                                  <div className="mt-1 text-[11px] text-rose-600 bg-rose-50 border border-rose-200 rounded px-2 py-1">
                                    {doc.processing_error}
                                  </div>
                                )}
                              </td>
                              <td className="py-3 px-3 whitespace-nowrap">
                                <span className="uppercase font-mono text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-700 mr-1.5">
                                  {doc.file_type}
                                </span>
                                <span className="text-slate-500">
                                  {formatBytes(doc.file_size)}
                                </span>
                              </td>
                              <td className="py-3 px-3 whitespace-nowrap">
                                <span
                                  className={`inline-flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded-full border ${statusBadgeStyle(
                                    doc.status
                                  )}`}
                                >
                                  {inFlight && (
                                    <RefreshCw className="w-3 h-3 animate-spin" />
                                  )}
                                  {doc.status}
                                </span>
                              </td>
                              <td className="py-3 px-3 whitespace-nowrap font-mono text-slate-700">
                                {doc.total_chunks || 0}
                              </td>
                              <td className="py-3 px-3 whitespace-nowrap text-slate-500">
                                {formatDateTime(doc.created_at)}
                              </td>
                              <td className="py-3 px-3 whitespace-nowrap text-slate-500">
                                {formatDateTime(doc.ready_at)}
                              </td>
                              <td className="py-3 px-3 whitespace-nowrap text-right">
                                {isSuperAdmin ? (
                                  <div className="inline-flex items-center gap-1.5">
                                    {(doc.status === 'FAILED' ||
                                      doc.status === 'UPLOADED') && (
                                      <button
                                        type="button"
                                        onClick={() => handleRetryDocument(doc)}
                                        className="px-2 py-1 rounded bg-amber-50 text-amber-700 hover:bg-amber-100 font-semibold text-[11px]"
                                        title="Retry ingestion"
                                      >
                                        Retry
                                      </button>
                                    )}
                                    <button
                                      type="button"
                                      onClick={() => handleDeleteDocument(doc)}
                                      className="p-1.5 rounded text-rose-600 hover:bg-rose-50"
                                      title="Delete document"
                                    >
                                      <Trash2 className="w-4 h-4" />
                                    </button>
                                  </div>
                                ) : (
                                  <span className="text-[11px] text-slate-400">
                                    Super Admin only
                                  </span>
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* =============================================================== */}
          {/* TAB 3: WHATSAPP AI & STRICT RAG SETTINGS */}
          {/* =============================================================== */}
          {activeTab === 'settings' && (
            <div className="space-y-6">
              {/* Session selector */}
              <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-center gap-3 flex-1">
                  <label className="text-xs font-bold uppercase text-slate-600">
                    WhatsApp Session:
                  </label>
                  <select
                    value={selectedConfigSessionId}
                    onChange={(e) => setSelectedConfigSessionId(e.target.value)}
                    className="bg-white border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#00a884] flex-1 max-w-md"
                  >
                    {sessionConfigs.length === 0 && (
                      <option value="">No active WhatsApp session found</option>
                    )}
                    {sessionConfigs.map((s) => (
                      <option key={s.session_id} value={s.session_id}>
                        {s.session_name}{' '}
                        {s.owner_username ? `(Owner: ${s.owner_username}) ` : ''}
                        {s.phone_number ? `[${s.phone_number}] ` : ''}— {s.status}
                      </option>
                    ))}
                  </select>
                </div>
                <button
                  type="button"
                  onClick={fetchSessionSettings}
                  className="text-xs text-[#00a884] hover:underline flex items-center gap-1"
                >
                  <RefreshCw
                    className={`w-3.5 h-3.5 ${loadingSettings ? 'animate-spin' : ''}`}
                  />
                  Refresh
                </button>
              </div>

              {!currentSessionConfig ? (
                <div className="p-8 text-center text-slate-400 text-sm border border-dashed border-slate-200 rounded-xl">
                  Connect or register a WhatsApp session to configure its AI Knowledge Base settings.
                </div>
              ) : (
                <>
                  {/* Assigned Knowledge Base */}
                  <div className="p-4 border border-slate-200 rounded-xl space-y-3">
                    <div className="flex items-center justify-between">
                      <div>
                        <h4 className="text-sm font-bold text-slate-800">
                          Assigned Knowledge Base
                        </h4>
                        <p className="text-xs text-slate-500">
                          Select which Knowledge Base this WhatsApp session uses to answer customer questions.
                        </p>
                      </div>
                      {currentSessionConfig.knowledge_base && (
                        <span
                          className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${
                            sessionKBReady
                              ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                              : 'bg-amber-50 text-amber-700 border-amber-200'
                          }`}
                        >
                          {sessionKBReady ? 'KB Ready' : 'KB Not Ready'}
                        </span>
                      )}
                    </div>

                    <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
                      <select
                        disabled={assigningKB}
                        value={currentSessionConfig.knowledge_base?.id || ''}
                        onChange={(e) =>
                          handleAssignKnowledgeBase(e.target.value)
                        }
                        className="bg-white border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#00a884] flex-1"
                      >
                        <option value="">
                          Global Dynamic Mode (All Active Ready Knowledge Bases)
                        </option>
                        {knowledgeBases.map((kb) => (
                          <option key={kb.id} value={kb.id}>
                            {kb.name} (
                            {kb.readiness?.is_ready
                              ? `${kb.readiness.ready_documents} ready docs`
                              : 'not ready'}
                            )
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  {/* AI Enabled + Strict RAG Mode Toggles */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="p-4 border border-slate-200 rounded-xl flex items-start justify-between gap-4">
                      <div className="space-y-1">
                        <h4 className="text-sm font-bold text-slate-800">
                          Enable WhatsApp AI Auto-Reply
                        </h4>
                        <p className="text-xs text-slate-500">
                          Automatically reply to incoming customer messages on this WhatsApp session.
                        </p>
                      </div>
                      <input
                        type="checkbox"
                        disabled={savingSettings}
                        checked={Boolean(currentSessionConfig.ai_enabled)}
                        onChange={(e) =>
                          handlePatchSessionSetting({
                            ai_enabled: e.target.checked,
                          })
                        }
                        className="w-5 h-5 accent-[#00a884] cursor-pointer mt-1"
                      />
                    </div>

                    <div className="p-4 border border-emerald-200 bg-emerald-50/30 rounded-xl flex flex-col justify-between gap-3">
                      <div className="flex items-start justify-between gap-4">
                        <div className="space-y-1">
                          <h4 className="text-sm font-bold text-slate-800 flex items-center gap-1.5">
                            <ShieldCheck className="w-4 h-4 text-[#00a884]" />
                            Strict RAG Mode
                          </h4>
                          <p className="text-xs text-slate-600">
                            Answer exclusively from the assigned Knowledge Base. Refuses unrelated questions and never falls back to general Gemini knowledge.
                          </p>
                        </div>
                        <input
                          type="checkbox"
                          disabled={
                            savingSettings ||
                            (!sessionKBReady &&
                              !currentSessionConfig.strict_rag_enabled)
                          }
                          checked={Boolean(
                            currentSessionConfig.strict_rag_enabled
                          )}
                          onChange={(e) =>
                            handlePatchSessionSetting({
                              strict_rag_enabled: e.target.checked,
                            })
                          }
                          className="w-5 h-5 accent-[#00a884] cursor-pointer mt-1 disabled:opacity-40"
                        />
                      </div>

                      {!sessionKBReady && (
                        <div className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 flex items-center gap-2">
                          <AlertCircle className="w-4 h-4 flex-shrink-0 text-amber-600" />
                          <span>
                            Assign an active Knowledge Base with at least one{' '}
                            <strong>READY</strong> document before enabling Strict RAG Mode.
                          </span>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Administrator Retrieval Tuning */}
                  {isAdminOrManager && (
                    <form
                      onSubmit={handleSaveRetrievalTuning}
                      className="p-4 border border-slate-200 rounded-xl space-y-4 bg-slate-50/60"
                    >
                      <div className="flex items-center gap-2">
                        <Sliders className="w-4 h-4 text-[#00a884]" />
                        <h4 className="text-sm font-bold text-slate-800">
                          Administrator Retrieval & Guardrail Settings
                        </h4>
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        <div>
                          <label className="block text-xs font-semibold text-slate-600 mb-1">
                            Top-K Chunks (default:{' '}
                            {currentSessionConfig.effective_top_k})
                          </label>
                          <input
                            type="number"
                            min={1}
                            max={20}
                            value={tuningTopK}
                            onChange={(e) => setTuningTopK(e.target.value)}
                            placeholder="Leave blank for system default (5)"
                            className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-sm"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-semibold text-slate-600 mb-1">
                            Minimum Relevance Threshold (0.0 – 1.0, effective:{' '}
                            {currentSessionConfig.effective_min_relevance_threshold})
                          </label>
                          <input
                            type="number"
                            step="0.01"
                            min={0}
                            max={1}
                            value={tuningThreshold}
                            onChange={(e) => setTuningThreshold(e.target.value)}
                            placeholder="Leave blank for system default (0.30)"
                            className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-sm"
                          />
                        </div>
                      </div>

                      <div>
                        <label className="block text-xs font-semibold text-slate-600 mb-1">
                          Custom Refusal Message (optional)
                        </label>
                        <textarea
                          rows={2}
                          value={tuningRefusalMsg}
                          onChange={(e) => setTuningRefusalMsg(e.target.value)}
                          placeholder={
                            currentSessionConfig.default_refusal_message
                          }
                          className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-xs"
                        />
                      </div>

                      <div className="flex justify-end">
                        <button
                          type="submit"
                          disabled={savingSettings}
                          className="px-4 py-2 bg-[#00a884] hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-sm transition disabled:opacity-50"
                        >
                          Save Retrieval Settings
                        </button>
                      </div>
                    </form>
                  )}
                </>
              )}
            </div>
          )}

          {/* =============================================================== */}
          {/* TAB 4: TEST KNOWLEDGE BASE PLAYGROUND */}
          {/* =============================================================== */}
          {activeTab === 'test' && (
            <div className="space-y-5">
              <div className="bg-emerald-50 border border-emerald-200 rounded-xl px-4 py-3 text-xs text-emerald-900 flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-[#00a884] flex-shrink-0" />
                <span>
                  <strong>Safe Verification Sandbox:</strong> Ask sample customer questions to inspect retrieved chunks, similarity scores, and grounded answers before enabling customer-facing Strict RAG. Testing never sends WhatsApp messages.
                </span>
              </div>

              <form
                onSubmit={handleRunTestQuery}
                className="p-4 bg-slate-50 border border-slate-200 rounded-xl space-y-4"
              >
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">
                      Test Target
                    </label>
                    <select
                      value={testTargetMode}
                      onChange={(e) => setTestTargetMode(e.target.value)}
                      className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-sm"
                    >
                      <option value="kb">Specific Knowledge Base</option>
                      <option value="session">
                        WhatsApp Session (uses its assigned KB & thresholds)
                      </option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-semibold text-slate-600 mb-1">
                      {testTargetMode === 'session'
                        ? 'Select WhatsApp Session'
                        : 'Select Knowledge Base'}
                    </label>
                    {testTargetMode === 'session' ? (
                      <select
                        value={selectedConfigSessionId}
                        onChange={(e) =>
                          setSelectedConfigSessionId(e.target.value)
                        }
                        className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-sm"
                      >
                        {sessionConfigs.map((s) => (
                          <option key={s.session_id} value={s.session_id}>
                            {s.session_name}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <select
                        value={selectedKBId}
                        onChange={(e) => setSelectedKBId(e.target.value)}
                        className="w-full bg-white border border-slate-300 rounded-lg px-3 py-2 text-sm"
                      >
                        {knowledgeBases.map((kb) => (
                          <option key={kb.id} value={kb.id}>
                            {kb.name}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>
                </div>

                <div className="flex gap-2">
                  <input
                    type="text"
                    value={testQuestion}
                    onChange={(e) => setTestQuestion(e.target.value)}
                    placeholder="Ask a customer question (e.g., What are your prices or warranty terms?)"
                    className="flex-1 bg-white border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#00a884]"
                  />
                  <button
                    type="submit"
                    disabled={runningTest}
                    className="px-5 py-2 bg-[#00a884] hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-sm transition disabled:opacity-50 flex items-center gap-2"
                  >
                    <Search className="w-4 h-4" />
                    {runningTest ? 'Testing...' : 'Ask KB'}
                  </button>
                </div>
              </form>

              {testResult && (
                <div className="space-y-4">
                  {/* Answer / Refusal Summary Card */}
                  <div
                    className={`p-4 rounded-xl border ${
                      testResult.answered
                        ? 'bg-emerald-50/50 border-emerald-200'
                        : 'bg-amber-50/60 border-amber-200'
                    }`}
                  >
                    <div className="flex items-center justify-between flex-wrap gap-2 mb-2">
                      <div className="flex items-center gap-2">
                        <span
                          className={`text-xs font-bold px-2.5 py-0.5 rounded-full ${
                            testResult.answered
                              ? 'bg-emerald-600 text-white'
                              : 'bg-amber-600 text-white'
                          }`}
                        >
                          {testResult.answered ? 'GROUNDED ANSWER' : 'REFUSED'}
                        </span>
                        <span className="text-xs text-slate-600">
                          Evidence Found:{' '}
                          <strong>
                            {testResult.evidence_found ? 'Yes' : 'No'}
                          </strong>
                        </span>
                        {testResult.refusal_reason && (
                          <span className="text-xs font-mono bg-white px-2 py-0.5 rounded border border-amber-200 text-amber-800">
                            reason: {testResult.refusal_reason}
                          </span>
                        )}
                      </div>
                      <span className="text-[11px] text-slate-500 font-mono">
                        {testResult.processing_ms} ms
                      </span>
                    </div>

                    <p className="text-sm text-slate-800 whitespace-pre-wrap">
                      {testResult.answered
                        ? testResult.answer
                        : testResult.refusal_message}
                    </p>

                    {/* Cited Sources */}
                    {testResult.sources?.length > 0 && (
                      <div className="mt-3 pt-3 border-t border-emerald-200/70">
                        <p className="text-[11px] font-bold uppercase text-emerald-800 mb-1.5">
                          Cited Source Evidence ({testResult.sources.length})
                        </p>
                        <div className="flex flex-wrap gap-2">
                          {testResult.sources.map((src) => (
                            <span
                              key={src.chunk_id}
                              className="text-xs bg-white border border-emerald-200 text-emerald-900 px-2.5 py-1 rounded-lg"
                            >
                              <strong>{src.document_name}</strong>
                              {src.page_number ? ` • p.${src.page_number}` : ''}
                              {src.sheet_name ? ` • ${src.sheet_name}` : ''}
                              {src.section_heading
                                ? ` • ${src.section_heading}`
                                : ''}{' '}
                              ({(Number(src.similarity || 0) * 100).toFixed(1)}%)
                            </span>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Retrieved Chunks Inspector */}
                  <div className="space-y-2">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-slate-600">
                      Retrieved Chunks ({testResult.retrieved?.length || 0})
                    </h4>
                    {!testResult.retrieved?.length ? (
                      <div className="p-4 text-xs text-slate-400 border border-dashed border-slate-200 rounded-xl text-center">
                        No chunks passed retrieval for this question.
                      </div>
                    ) : (
                      <div className="space-y-2">
                        {testResult.retrieved.map((chunk, idx) => (
                          <div
                            key={chunk.chunk_id || idx}
                            className="p-3 rounded-xl border border-slate-200 bg-slate-50/70 space-y-1.5"
                          >
                            <div className="flex items-center justify-between text-xs">
                              <div className="font-semibold text-slate-800">
                                #{idx + 1} • {chunk.document_name}
                                {chunk.page_number
                                  ? ` (Page ${chunk.page_number})`
                                  : ''}
                                {chunk.sheet_name
                                  ? ` (Sheet: ${chunk.sheet_name})`
                                  : ''}
                                {chunk.section_heading
                                  ? ` — ${chunk.section_heading}`
                                  : ''}
                              </div>
                              <span className="font-mono text-[11px] px-2 py-0.5 rounded bg-white border border-slate-200 text-slate-700">
                                Similarity:{' '}
                                {(Number(chunk.similarity || 0) * 100).toFixed(
                                  1
                                )}
                                %
                              </span>
                            </div>
                            {chunk.text && (
                              <pre className="text-xs text-slate-600 whitespace-pre-wrap font-sans bg-white p-2.5 rounded-lg border border-slate-200/80 max-h-40 overflow-y-auto">
                                {chunk.text}
                              </pre>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
