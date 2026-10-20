import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useSelector } from 'react-redux';
import {
  Search,
  MoreVertical,
  Paperclip,
  Smile,
  Send,
  Phone,
  Video,
  RefreshCw,
  Plus,
  Trash2,
  X,
  ChevronDown,
  Mic,
  Square,
  Play,
  Pause,
  Download,
  Image as ImageIcon,
  FileText,
  Check,
  CheckCheck,
  Clock,
  AlertCircle,
  ExternalLink,
  User,
  MessageSquare,
  LogOut,
  ArrowLeft,
  ZoomIn,
  ZoomOut,
  Maximize2,
  Link as LinkIcon,
  Unlink,
  Camera,
  Building,
  Mail,
  Briefcase,
  Edit2
} from 'lucide-react';
import api from '../services/api';

const API_BASE = api.defaults.baseURL || '/api';
const HOST_URL = (API_BASE && API_BASE.startsWith('http'))
  ? API_BASE.replace(/\/api\/?$/, '')
  : '';

// ---------------------------------------------------------------------------
// High-Resolution Contact Avatar Component
// ---------------------------------------------------------------------------
function ContactAvatar({ chat, size = "md", avatarVersion }) {
  const [imgError, setImgError] = useState(false);
  const [imgLoaded, setImgLoaded] = useState(false);

  // Avatar Source Resolution
  let avatarSrc = "";
  if (chat?.custom_avatar_url) {
    const rawUrl = String(chat.custom_avatar_url).trim();
    if (rawUrl.startsWith("http://") || rawUrl.startsWith("https://") || rawUrl.startsWith("data:")) {
      avatarSrc = rawUrl;
    } else {
      const cleanPath = rawUrl.startsWith("/") ? rawUrl : `/${rawUrl}`;
      avatarSrc = `${HOST_URL}${cleanPath}`;
    }
  } else if (chat?.chat_id && !chat.chat_id.startsWith("temp-")) {
    avatarSrc = `${API_BASE}/whatsapp/profile-pic/${encodeURIComponent(chat.chat_id)}/?v=${avatarVersion || 1}`;
  }

  useEffect(() => {
    setImgError(false);
    setImgLoaded(false);
  }, [avatarSrc]);

  if (!chat) return null;

  const sizeClasses = {
    sm: "w-10 h-10 text-xs",
    md: "w-12 h-12 text-sm",
    lg: "w-28 h-28 text-3xl",
  }[size] || "w-12 h-12 text-sm";

  const iconSizes = {
    sm: "w-5 h-5",
    md: "w-6 h-6",
    lg: "w-14 h-14",
  }[size] || "w-6 h-6";

  const displayName = chat.contact_name || chat.whatsapp_name || "";
  const hasLetters = /[a-zA-Z]/.test(displayName);

  let initials = "";
  if (hasLetters) {
    const words = displayName.trim().split(/\s+/).filter(w => /[a-zA-Z]/.test(w));
    if (words.length === 1) {
      initials = words[0].slice(0, 2).toUpperCase();
    } else if (words.length > 1) {
      initials = (words[0][0] + words[words.length - 1][0]).toUpperCase();
    }
  } else {
    const rawNum = chat.phone_number || chat.prospect_phone || chat.chat_id || "";
    const cleanDigits = rawNum.replace(/\D/g, "").slice(-2);
    if (cleanDigits) initials = cleanDigits;
  }

  // Deterministic palette for avatar background
  const PALETTE = [
    "bg-emerald-600 text-white",
    "bg-teal-600 text-white",
    "bg-sky-600 text-white",
    "bg-blue-600 text-white",
    "bg-indigo-600 text-white",
    "bg-violet-600 text-white",
    "bg-purple-600 text-white",
    "bg-rose-600 text-white",
    "bg-amber-600 text-white",
    "bg-slate-600 text-white",
  ];
  const charCodeSum = (chat.chat_id || displayName || "avatar").split("").reduce((acc, c) => acc + c.charCodeAt(0), 0);
  const colorClass = PALETTE[charCodeSum % PALETTE.length];

  const shouldRenderImg = Boolean(avatarSrc) && !imgError;

  return (
    <div className={`${sizeClasses} rounded-full flex-shrink-0 flex items-center justify-center font-bold overflow-hidden relative shadow-sm select-none ${colorClass}`}>
      {shouldRenderImg && (
        <img
          src={avatarSrc}
          className={`w-full h-full object-cover absolute inset-0 z-10 transition-opacity duration-200 ${imgLoaded ? 'opacity-100' : 'opacity-0'}`}
          onLoad={() => setImgLoaded(true)}
          onError={() => setImgError(true)}
          alt={displayName || "Contact avatar"}
        />
      )}
      <div className="relative z-0 flex items-center justify-center w-full h-full">
        {initials ? (
          <span>{initials}</span>
        ) : (
          <User className={`${iconSizes} text-white/90`} />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Audio Voice Player Component
// ---------------------------------------------------------------------------
function WhatsAppAudioPlayer({ src, isMe }) {
  const [isPlaying, setIsPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const audioRef = useRef(null);

  const togglePlay = () => {
    if (!audioRef.current) return;
    if (isPlaying) {
      audioRef.current.pause();
    } else {
      audioRef.current.play().catch(e => console.error("Audio playback error:", e));
    }
    setIsPlaying(!isPlaying);
  };

  const handleTimeUpdate = () => {
    if (audioRef.current) {
      setCurrentTime(audioRef.current.currentTime);
    }
  };

  const handleLoadedMetadata = () => {
    if (audioRef.current) {
      setDuration(audioRef.current.duration || 0);
    }
  };

  const handleEnded = () => {
    setIsPlaying(false);
    setCurrentTime(0);
  };

  const handleSeek = (e) => {
    const time = parseFloat(e.target.value);
    setCurrentTime(time);
    if (audioRef.current) {
      audioRef.current.currentTime = time;
    }
  };

  const formatAudioTime = (sec) => {
    if (!sec || isNaN(sec)) return "0:00";
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <div className={`flex items-center gap-3 p-2 rounded-xl min-w-[240px] max-w-[320px] ${
      isMe ? 'bg-[#c5f3be]/60' : 'bg-slate-100/90'
    }`}>
      <audio
        ref={audioRef}
        src={src}
        onTimeUpdate={handleTimeUpdate}
        onLoadedMetadata={handleLoadedMetadata}
        onEnded={handleEnded}
        preload="metadata"
      />
      <button
        type="button"
        onClick={togglePlay}
        className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 transition-transform active:scale-95 shadow-sm ${
          isMe ? 'bg-emerald-600 text-white hover:bg-emerald-700' : 'bg-emerald-500 text-white hover:bg-emerald-600'
        }`}
      >
        {isPlaying ? <Pause className="w-5 h-5 fill-current" /> : <Play className="w-5 h-5 fill-current ml-0.5" />}
      </button>

      <div className="flex-1 flex flex-col justify-center">
        <input
          type="range"
          min="0"
          max={duration || 100}
          value={currentTime}
          onChange={handleSeek}
          className="w-full h-1.5 bg-slate-300 rounded-lg appearance-none cursor-pointer accent-emerald-600"
        />
        <div className="flex justify-between items-center mt-1 text-[11px] text-slate-500 font-medium">
          <span>{formatAudioTime(currentTime)}</span>
          <span className="flex items-center gap-1">
            <Mic className="w-3 h-3 text-emerald-600" />
            {formatAudioTime(duration)}
          </span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main WhatsappPage Component
// ---------------------------------------------------------------------------
export default function WhatsappPage() {
  const { user } = useSelector((state) => state.auth);

  // Session & Connection state
  const [sessions, setSessions] = useState([]);
  const [selectedSession, setSelectedSession] = useState(null);
  const [sessionStatus, setSessionStatus] = useState(null);
  const [qrCodeData, setQrCodeData] = useState(null);
  const [loadingQR, setLoadingQR] = useState(false);
  const [qrExpired, setQrExpired] = useState(false);
  const [showSessionDropdown, setShowSessionDropdown] = useState(false);

  // Phone Pairing code alternative
  const [linkWithPhone, setLinkWithPhone] = useState(false);
  const [pairingPhone, setPairingPhone] = useState('');
  const [pairingCode, setPairingCode] = useState(null);
  const [requestingCode, setRequestingCode] = useState(false);

  // Conversations & Chat
  const [chats, setChats] = useState([]);
  const [selectedChat, setSelectedChat] = useState(null);
  const [messages, setMessages] = useState([]);
  const [message, setMessage] = useState('');
  const [loadingChats, setLoadingChats] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [chatFilter, setChatFilter] = useState('all'); // 'all', 'unread', 'key'
  const [showMsgSearch, setShowMsgSearch] = useState(false);
  const [msgSearchQuery, setMsgSearchQuery] = useState('');
  const [showProfilePanel, setShowProfilePanel] = useState(false);
  const [wahaContact, setWahaContact] = useState(null);

  // Media Sending & Preview
  const [attachPreview, setAttachPreview] = useState(null);
  const [isSendingMedia, setIsSendingMedia] = useState(false);
  const [showAttachMenu, setShowAttachMenu] = useState(false);
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);

  // Audio Recording (Voice Notes)
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const recordingTimerRef = useRef(null);

  // Media Lightbox Modal
  const [lightboxMedia, setLightboxMedia] = useState(null);

  // New Chat Modal
  const [showNewChatModal, setShowNewChatModal] = useState(false);
  const [newChatPhone, setNewChatPhone] = useState('');
  const [keyPeople, setKeyPeople] = useState([]);
  const [loadingKeyPeople, setLoadingKeyPeople] = useState(false);

  // Avatar & CRM Linking
  const [avatarVersion, setAvatarVersion] = useState(Date.now());
  const [showLinkCRMModal, setShowLinkCRMModal] = useState(false);
  const [crmSearchQuery, setCrmSearchQuery] = useState('');
  const [crmSearchResults, setCrmSearchResults] = useState([]);
  const [loadingCrmSearch, setLoadingCrmSearch] = useState(false);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const avatarFileInputRef = useRef(null);

  // Contact Renaming & Phone State
  const [isEditingName, setIsEditingName] = useState(false);
  const [editNameValue, setEditNameValue] = useState('');
  const [savingName, setSavingName] = useState(false);
  const [isEditingPhone, setIsEditingPhone] = useState(false);
  const [editPhoneValue, setEditPhoneValue] = useState('');
  const [savingPhone, setSavingPhone] = useState(false);

  // Notifications
  const [toastMessage, setToastMessage] = useState(null);

  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);
  const qrPollTimerRef = useRef(null);

  const showToast = (text, type = 'info') => {
    setToastMessage({ text, type });
    setTimeout(() => setToastMessage(null), type === 'error' ? 5000 : 3000);
  };

  // -------------------------------------------------------------------
  // 1. Session & QR Code Management
  // -------------------------------------------------------------------
  const fetchSessions = useCallback(async () => {
    try {
      const res = await api.get('/whatsapp/session/list/');
      setSessions(res.data);
      if (res.data && res.data.length > 0) {
        setSelectedSession(res.data[0]);
      }
    } catch (err) {
      console.error('Failed to fetch WhatsApp sessions:', err);
    }
  }, []);

  useEffect(() => {
    fetchSessions();
  }, [fetchSessions]);

  // Fetch live QR or Connection state for current user's session
  const fetchQR = useCallback(async () => {
    setLoadingQR(true);
    try {
      const res = await api.get('/whatsapp/qr/');
      const data = res.data;
      setSessionStatus(data);

      if (data.status === 'WORKING' || data.connected) {
        setQrCodeData(null);
        setQrExpired(false);
        setSelectedSession(prev => ({
          ...(prev || {}),
          session_name: data.session_name || prev?.session_name,
          status: 'READY',
          phone_number: data.phone_number || prev?.phone_number
        }));
      } else if (data.status === 'SCAN_QR_CODE') {
        const qr = data.qrBase64 || data.qr || data.value;
        setQrCodeData(qr);
        setQrExpired(false);
      }
    } catch (err) {
      console.error('Failed to get QR code status:', err);
      setQrExpired(true);
    } finally {
      setLoadingQR(false);
    }
  }, []);

  // QR Polling: Auto-refresh QR and auto-detect when phone connects
  useEffect(() => {
    const isReady = selectedSession?.status === 'READY' || sessionStatus?.status === 'WORKING';
    if (!isReady) {
      fetchQR();
      qrPollTimerRef.current = setInterval(() => {
        fetchQR();
      }, 3000);
    } else {
      if (qrPollTimerRef.current) clearInterval(qrPollTimerRef.current);
    }

    return () => {
      if (qrPollTimerRef.current) clearInterval(qrPollTimerRef.current);
    };
  }, [selectedSession?.status, sessionStatus?.status, fetchQR]);

  // Request 8-digit Pairing Code via Phone Number
  const handleRequestPairingCode = async (e) => {
    e?.preventDefault();
    const clean = pairingPhone.replace(/\D/g, '');
    if (!clean) {
      showToast('Please enter a valid phone number with country code.', 'error');
      return;
    }
    setRequestingCode(true);
    try {
      const sessionName = selectedSession?.session_name || '';
      const res = await api.post('/whatsapp/pair-code/', {
        session_name: sessionName,
        phone_number: clean,
      });
      if (res.data?.code) {
        setPairingCode(res.data.code);
        showToast('Pairing code generated! Check your phone.', 'success');
      } else {
        showToast('Code generated. Follow prompt on your WhatsApp mobile app.', 'info');
      }
    } catch (err) {
      showToast(err.response?.data?.detail || 'Failed to request pairing code.', 'error');
    } finally {
      setRequestingCode(false);
    }
  };

  // Disconnect / Logout Session
  const handleLogoutSession = async () => {
    if (!window.confirm("Are you sure you want to disconnect WhatsApp? You will need to scan the QR code again.")) return;
    try {
      const sessionName = selectedSession?.session_name || '';
      await api.post('/whatsapp/session/logout/', { session_name: sessionName });
      showToast('WhatsApp session disconnected.', 'info');
      setSelectedSession(prev => prev ? { ...prev, status: 'DISCONNECTED', phone_number: null } : null);
      setSessionStatus({ status: 'SCAN_QR_CODE', connected: false });
      setChats([]);
      setSelectedChat(null);
      setMessages([]);
      fetchQR();
    } catch (err) {
      showToast(err.response?.data?.detail || 'Failed to disconnect session.', 'error');
    }
  };

  // -------------------------------------------------------------------
  // 2. Conversations & Real-Time Sync
  // -------------------------------------------------------------------
  const fetchConversations = useCallback(async (isPolling = false) => {
    try {
      const response = await api.get('/whatsapp/conversations/');
      setChats(response.data);
    } catch (error) {
      console.error('Failed to fetch conversations:', error);
    } finally {
      if (!isPolling) setLoadingChats(false);
    }
  }, []);

  const fetchMessages = useCallback(async (conversationId, isPolling = false) => {
    if (!conversationId || String(conversationId).startsWith('temp-')) {
      setMessages([]);
      if (!isPolling) setLoadingMessages(false);
      return;
    }
    if (!isPolling) setLoadingMessages(true);
    try {
      const response = await api.get(`/whatsapp/conversations/${conversationId}/messages/`);
      const sorted = (response.data.messages || []).reverse();
      setMessages(sorted);
      if (!isPolling) {
        setTimeout(scrollToBottom, 150);
      }
    } catch (error) {
      console.error('Failed to fetch messages:', error);
    } finally {
      if (!isPolling) setLoadingMessages(false);
    }
  }, []);

  useEffect(() => {
    if (selectedSession && selectedSession.status === 'READY') {
      fetchConversations(false);
    }
  }, [selectedSession, fetchConversations]);

  useEffect(() => {
    if (selectedChat) {
      if (!String(selectedChat.id).startsWith('temp-')) {
        fetchMessages(selectedChat.id);
      } else {
        setMessages([]);
      }
      // Fetch contact info
      setWahaContact(null);
      if (selectedChat.chat_id) {
        api.get(`/whatsapp/contact-info/${selectedChat.chat_id}/`)
          .then(r => {
            if (r.data?.phoneNumber) setWahaContact(r.data);
          })
          .catch(err => console.error('Contact info error:', err));
      }
    }
  }, [selectedChat, fetchMessages]);

  // Polling for new incoming messages & conversations
  useEffect(() => {
    const isReady = selectedSession?.status === 'READY';
    if (!isReady) return;

    const interval = setInterval(() => {
      fetchConversations(true);
      if (selectedChat && !String(selectedChat.id).startsWith('temp-')) {
        fetchMessages(selectedChat.id, true);
      }
    }, 4000);

    return () => clearInterval(interval);
  }, [selectedSession, selectedChat, fetchConversations, fetchMessages]);

  useEffect(() => {
    if (messages.length > 0) {
      scrollToBottom();
    }
  }, [messages.length]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleSyncHistory = async () => {
    if (!selectedChat || String(selectedChat.id).startsWith('temp-')) return;
    try {
      showToast('Syncing messages from WhatsApp...', 'info');
      const response = await api.post(`/whatsapp/conversations/${selectedChat.id}/sync/`);
      showToast(response.data.detail || 'Sync complete.', 'success');
      fetchMessages(selectedChat.id);
    } catch (error) {
      showToast(error.response?.data?.detail || 'Failed to sync history', 'error');
    }
  };

  const handleMarkRead = async (chat) => {
    if (!chat || String(chat.id).startsWith('temp-')) return;
    try {
      await api.post(`/whatsapp/conversations/${chat.id}/read/`);
      setChats(prev => prev.map(c =>
        c.id === chat.id ? { ...c, unread_count: 0 } : c
      ));
    } catch {
      // Non-critical
    }
  };

  // -------------------------------------------------------------------
  // 3. Send Text Message
  // -------------------------------------------------------------------
  const handleSendMessage = async () => {
    if (!message.trim() || !selectedChat) return;
    const body = message.trim();
    setMessage('');
    try {
      const response = await api.post('/whatsapp/send/', {
        prospect_contact_id: selectedChat.prospect_contact || null,
        chat_id: selectedChat.chat_id,
        message_body: body,
      });

      setMessages(prev => [...prev, response.data]);
      setTimeout(scrollToBottom, 100);

      // If this was a synthetic / temp chat, refresh conversations and select the real one
      if (String(selectedChat.id).startsWith('temp-')) {
        const chatsRes = await api.get('/whatsapp/conversations/');
        const freshChats = chatsRes.data || [];
        setChats(freshChats);
        const createdConv = freshChats.find(c => c.chat_id === selectedChat.chat_id);
        if (createdConv) {
          setSelectedChat(createdConv);
        }
      } else {
        setChats(prevChats => prevChats.map(c =>
          c.id === selectedChat.id
            ? { ...c, last_message_preview: body, last_message_at: new Date().toISOString(), last_message_from_me: true }
            : c
        ));
      }
    } catch (error) {
      console.error('Failed to send message:', error);
      showToast(error.response?.data?.detail || 'Failed to send message.', 'error');
    }
  };

  // -------------------------------------------------------------------
  // 4. Send Media & Files
  // -------------------------------------------------------------------
  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setShowAttachMenu(false);
    const url = URL.createObjectURL(file);
    setAttachPreview({ file, url, mime: file.type || 'application/octet-stream', name: file.name, size: file.size });
    e.target.value = '';
  };

  const handleSendMedia = async () => {
    if (!attachPreview || !selectedChat) return;
    setIsSendingMedia(true);
    try {
      const formData = new FormData();
      formData.append('file', attachPreview.file);
      formData.append('chat_id', selectedChat.chat_id);
      if (message.trim()) formData.append('caption', message.trim());

      const response = await api.post('/whatsapp/send-media/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      setAttachPreview(null);
      setMessage('');

      if (response.data && response.data.id) {
        setMessages(prev => [...prev, response.data]);
        setTimeout(scrollToBottom, 100);
      } else {
        setTimeout(() => fetchMessages(selectedChat.id), 1000);
      }

      showToast('Media sent successfully!', 'success');
    } catch (err) {
      showToast(err.response?.data?.detail || 'Failed to send media.', 'error');
    } finally {
      setIsSendingMedia(false);
    }
  };

  // -------------------------------------------------------------------
  // 5. In-Browser Voice Note Recorder
  // -------------------------------------------------------------------
  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        const audioFile = new File([audioBlob], `voice_note_${Date.now()}.webm`, { type: 'audio/webm' });
        const previewUrl = URL.createObjectURL(audioBlob);
        setAttachPreview({
          file: audioFile,
          url: previewUrl,
          mime: 'audio/webm',
          name: 'Voice Note',
          size: audioBlob.size,
          isVoiceNote: true
        });
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
      setRecordingSeconds(0);
      recordingTimerRef.current = setInterval(() => {
        setRecordingSeconds(sec => sec + 1);
      }, 1000);
    } catch (err) {
      console.error("Microphone access error:", err);
      showToast("Could not access microphone. Please allow microphone permissions.", "error");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      clearInterval(recordingTimerRef.current);
    }
  };

  const cancelRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      clearInterval(recordingTimerRef.current);
      setAttachPreview(null);
    }
  };

  // -------------------------------------------------------------------
  // 6. Delete Message & Chat
  // -------------------------------------------------------------------
  const handleDeleteMessage = async (messageId) => {
    try {
      await api.delete(`/whatsapp/messages/${messageId}/`);
      setMessages(prev => prev.filter(m => m.id !== messageId));
      showToast('Message deleted.', 'success');
    } catch (err) {
      showToast(err.response?.data?.detail || 'Failed to delete message.', 'error');
    }
  };

  const handleDeleteChat = async () => {
    if (!selectedChat) return;
    if (!window.confirm("Delete this conversation?")) return;
    try {
      await api.delete(`/whatsapp/conversations/${selectedChat.id}/`);
      setChats(prev => prev.filter(c => c.id !== selectedChat.id));
      setSelectedChat(null);
      setMessages([]);
      showToast('Conversation deleted.', 'success');
    } catch (err) {
      showToast(err.response?.data?.detail || 'Failed to delete conversation.', 'error');
    }
  };

  // -------------------------------------------------------------------
  // 7. CRM Linking & Key People Helpers
  // -------------------------------------------------------------------
  const fetchKeyPeople = async (searchTerm = '') => {
    setLoadingKeyPeople(true);
    try {
      const res = await api.get('/whatsapp/crm-contacts/', {
        params: searchTerm ? { search: searchTerm } : {}
      });
      setKeyPeople(res.data || []);
    } catch (e) {
      console.error("Failed to load CRM key contacts:", e);
    } finally {
      setLoadingKeyPeople(false);
    }
  };

  const handleSearchCRM = async (query = '') => {
    setLoadingCrmSearch(true);
    try {
      const res = await api.get('/whatsapp/crm-contacts/', {
        params: query ? { search: query } : {}
      });
      setCrmSearchResults(res.data || []);
    } catch (err) {
      console.error('Failed to search CRM contacts:', err);
    } finally {
      setLoadingCrmSearch(false);
    }
  };

  const handleLinkToCRM = async (contactId) => {
    if (!selectedChat) return;
    try {
      const res = await api.post(`/whatsapp/conversations/${selectedChat.id}/link-crm/`, {
        prospect_contact_id: contactId
      });
      const updated = res.data;
      setSelectedChat(prev => ({ ...prev, ...updated }));
      setChats(prev => prev.map(c => c.id === updated.id ? { ...c, ...updated } : c));
      setShowLinkCRMModal(false);
      setAvatarVersion(Date.now());
      showToast(contactId ? `Linked to ${updated.contact_name || 'CRM Contact'}!` : 'Unlinked from CRM.', 'success');
      // Refresh contact info in panel
      api.get(`/whatsapp/contact-info/${updated.chat_id}/`)
        .then(r => setWahaContact(r.data))
        .catch(() => {});
    } catch (err) {
      showToast(err.response?.data?.detail || 'Failed to update CRM link.', 'error');
    }
  };

  const handleAvatarUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file || !selectedChat) return;
    setUploadingAvatar(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const res = await api.post(`/whatsapp/conversations/${selectedChat.id}/avatar/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      const newUrl = res.data.custom_avatar_url;
      setAvatarVersion(Date.now());
      setSelectedChat(prev => ({ ...prev, custom_avatar_url: newUrl }));
      setChats(prev => prev.map(c => c.id === selectedChat.id ? { ...c, custom_avatar_url: newUrl } : c));
      showToast('Profile picture updated!', 'success');
    } catch (err) {
      showToast(err.response?.data?.detail || 'Failed to upload profile picture.', 'error');
    } finally {
      setUploadingAvatar(false);
      if (avatarFileInputRef.current) avatarFileInputRef.current.value = '';
    }
  };

  const handleSaveContactName = async () => {
    if (!selectedChat) return;
    const trimmed = editNameValue.trim();
    if (!trimmed) {
      setIsEditingName(false);
      return;
    }
    setSavingName(true);
    try {
      const res = await api.patch(`/whatsapp/conversations/${selectedChat.id}/`, {
        whatsapp_name: trimmed,
      });
      const updated = res.data;
      const newName = updated.whatsapp_name || trimmed;
      setSelectedChat(prev => ({
        ...prev,
        whatsapp_name: newName,
        contact_name: updated.contact_name || newName,
      }));
      setChats(prev => prev.map(c => c.id === selectedChat.id ? {
        ...c,
        whatsapp_name: newName,
        contact_name: updated.contact_name || newName,
      } : c));
      setIsEditingName(false);
      setAvatarVersion(Date.now());
      showToast('Contact name updated successfully!', 'success');
    } catch (err) {
      console.error('Failed to update contact name:', err);
      showToast(err.response?.data?.detail || 'Failed to update contact name.', 'error');
    } finally {
      setSavingName(false);
    }
  };

  const handleSaveContactPhone = async () => {
    if (!selectedChat) return;
    const trimmed = editPhoneValue.trim();
    setSavingPhone(true);
    try {
      const res = await api.patch(`/whatsapp/conversations/${selectedChat.id}/`, {
        phone: trimmed,
      });
      const updated = res.data;
      setSelectedChat(prev => ({
        ...prev,
        phone_number: updated.phone_number || trimmed,
        prospect_phone: updated.prospect_phone || trimmed,
        is_matched: updated.is_matched,
        contact_name: updated.contact_name || prev.contact_name,
        prospect_name: updated.prospect_name || prev.prospect_name,
        whatsapp_name: updated.whatsapp_name || prev.whatsapp_name,
      }));
      setChats(prev => prev.map(c => c.id === selectedChat.id ? {
        ...c,
        phone_number: updated.phone_number || trimmed,
        prospect_phone: updated.prospect_phone || trimmed,
        is_matched: updated.is_matched,
        contact_name: updated.contact_name || c.contact_name,
        prospect_name: updated.prospect_name || c.prospect_name,
        whatsapp_name: updated.whatsapp_name || c.whatsapp_name,
      } : c));
      setIsEditingPhone(false);
      showToast('Phone number updated successfully!', 'success');
    } catch (err) {
      console.error('Failed to update phone number:', err);
      showToast(err.response?.data?.detail || 'Failed to update phone number.', 'error');
    } finally {
      setSavingPhone(false);
    }
  };

  const handleStartNewChat = (chatId, contactName, prospectName, contactId = null) => {
    let formattedId = chatId.trim();
    if (!formattedId.includes('@')) {
      const cleanDigits = formattedId.replace(/\D/g, '');
      formattedId = `${cleanDigits}@c.us`;
    }

    // Check if conversation already exists in chats list
    const existing = chats.find(c => c.chat_id === formattedId);
    if (existing) {
      setSelectedChat(existing);
      setShowNewChatModal(false);
      return;
    }

    const cleanDigits = formattedId.split('@')[0].split(':')[0].replace(/\D/g, '');
    const syntheticPhone = cleanDigits ? `+${cleanDigits}` : '';

    const syntheticChat = {
      id: 'temp-' + Date.now(),
      chat_id: formattedId,
      phone_number: syntheticPhone,
      contact_name: contactName || syntheticPhone,
      prospect_name: prospectName || '',
      whatsapp_name: contactName || '',
      unread_count: 0,
      prospect_contact: contactId,
      last_message_preview: 'New conversation',
      last_message_at: new Date().toISOString(),
      is_synthetic: true
    };

    setChats(prev => [syntheticChat, ...prev]);
    setSelectedChat(syntheticChat);
    setMessages([]);
    setShowNewChatModal(false);
  };

  // -------------------------------------------------------------------
  // Helpers
  // -------------------------------------------------------------------
  const buildMediaSrc = useCallback((msg) => {
    const raw = msg.media_url || msg.media_file || '';
    if (!raw) return '';
    return `${API_BASE}/whatsapp/media-proxy/?message_id=${msg.id}`;
  }, []);

  const formatMessageTime = (dateString) => {
    if (!dateString) return '';
    return new Date(dateString).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const formatChatDate = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    if (date.toDateString() === today.toDateString()) {
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else if (date.toDateString() === yesterday.toDateString()) {
      return 'Yesterday';
    } else {
      return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
    }
  };

  const formatPhone = (val) => {
    if (!val) return '';
    if (typeof val !== 'string') return '';
    if (val.includes('@lid')) return '';
    const num = val.split('@')[0].split(':')[0].replace(/\D/g, '');
    if (!num || num.length < 7 || num.length > 15) return '';
    return `+${num}`;
  };

  const getContactDisplayName = (chat) => {
    if (!chat) return 'Contact';
    // 1. CRM Key Person Name (e.g. "Mohanraj")
    if (chat.contact_name) return chat.contact_name;

    // 2. WhatsApp Profile PushName (e.g. "Rocky", "Mohanraj")
    if (chat.whatsapp_name && !chat.whatsapp_name.startsWith('+') && !chat.whatsapp_name.includes('@')) {
      return chat.whatsapp_name;
    }

    // 3. Known phone number
    const phone = chat.phone_number || chat.prospect_phone || formatPhone(chat.chat_id);
    if (phone) return phone.startsWith('+') ? phone : `+${phone}`;

    // 4. Fallback name
    if (chat.whatsapp_name) return chat.whatsapp_name;

    return 'WhatsApp Contact';
  };

  const getContactSubtext = (chat) => {
    if (!chat) return '';
    const rawPhone = chat.phone_number || chat.prospect_phone || formatPhone(chat.chat_id);
    const phone = rawPhone ? (rawPhone.startsWith('+') ? rawPhone : `+${rawPhone}`) : '';

    if (chat.is_matched && chat.prospect_name) {
      const parts = [chat.prospect_name];
      if (chat.contact_designation) parts.push(chat.contact_designation);
      if (phone) parts.push(phone);
      return parts.join(' • ');
    }

    if (phone) {
      return phone;
    }

    return 'WhatsApp Direct';
  };

  // Filter conversations
  const filteredChats = chats.filter(chat => {
    if (chatFilter === 'unread' && chat.unread_count === 0) return false;
    if (chatFilter === 'key' && !chat.is_matched) return false;

    if (!searchQuery) return true;
    const name = getContactDisplayName(chat).toLowerCase();
    const phone = (chat.phone_number || chat.prospect_phone || formatPhone(chat.chat_id) || '').toLowerCase();
    const comp = (chat.prospect_name || '').toLowerCase();
    const rawId = (chat.chat_id || '').toLowerCase();
    const q = searchQuery.toLowerCase();
    return name.includes(q) || phone.includes(q) || comp.includes(q) || rawId.includes(q);
  });

  // Check if session is authenticated
  const isConnected = selectedSession?.status === 'READY' || sessionStatus?.status === 'WORKING';

  // ===================================================================
  // RENDER: UNCONNECTED / QR CODE SCREEN
  // ===================================================================
  if (!isConnected) {
    return (
      <div className="min-h-[calc(100vh-4.5rem)] bg-[#eae6df] flex flex-col justify-between relative overflow-hidden font-sans">
        {/* Top Emerald Header Banner */}
        <div className="bg-[#00a884] h-56 w-full px-8 py-6 text-white flex items-center justify-between shadow-sm">
          <div className="flex items-center gap-3 max-w-5xl mx-auto w-full">
            <div className="w-10 h-10 bg-white/20 backdrop-blur rounded-full flex items-center justify-center">
              <Phone className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-wide">WHATSAPP WEB</h1>
              <p className="text-xs text-emerald-100">Market Intelligence CRM Live Communication</p>
            </div>
          </div>
        </div>

        {/* Floating Centered Card */}
        <div className="flex-1 -mt-32 max-w-5xl mx-auto w-full px-4 mb-8 z-10">
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 overflow-hidden flex flex-col md:flex-row">
            
            {/* Left Steps Column */}
            <div className="p-8 md:p-12 flex-1 flex flex-col justify-between">
              <div>
                <h2 className="text-2xl font-light text-slate-800 mb-6">
                  To use WhatsApp on your computer:
                </h2>

                <ol className="space-y-5 text-slate-600 text-sm md:text-base">
                  <li className="flex items-start gap-4">
                    <span className="w-6 h-6 rounded-full bg-emerald-100 text-emerald-700 font-bold text-xs flex items-center justify-center flex-shrink-0 mt-0.5">
                      1
                    </span>
                    <span>Open <strong>WhatsApp</strong> on your phone</span>
                  </li>
                  <li className="flex items-start gap-4">
                    <span className="w-6 h-6 rounded-full bg-emerald-100 text-emerald-700 font-bold text-xs flex items-center justify-center flex-shrink-0 mt-0.5">
                      2
                    </span>
                    <span>
                      Tap <strong>Menu</strong> (Android 3 dots) or <strong>Settings</strong> (iPhone gear) and select <strong>Linked Devices</strong>
                    </span>
                  </li>
                  <li className="flex items-start gap-4">
                    <span className="w-6 h-6 rounded-full bg-emerald-100 text-emerald-700 font-bold text-xs flex items-center justify-center flex-shrink-0 mt-0.5">
                      3
                    </span>
                    <span>
                      Tap on <strong>Link a device</strong>
                    </span>
                  </li>
                  <li className="flex items-start gap-4">
                    <span className="w-6 h-6 rounded-full bg-emerald-100 text-emerald-700 font-bold text-xs flex items-center justify-center flex-shrink-0 mt-0.5">
                      4
                    </span>
                    <span>
                      Point your phone to this screen to capture the QR code
                    </span>
                  </li>
                </ol>
              </div>

              {/* Link With Phone Option */}
              <div className="mt-8 pt-6 border-t border-slate-100">
                {!linkWithPhone ? (
                  <button
                    type="button"
                    onClick={() => setLinkWithPhone(true)}
                    className="text-emerald-600 hover:text-emerald-700 font-semibold text-sm flex items-center gap-1.5 transition"
                  >
                    <span>Link with phone number instead</span>
                    <ChevronDown className="w-4 h-4 rotate-270" />
                  </button>
                ) : (
                  <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                    <div className="flex justify-between items-center mb-3">
                      <span className="text-xs font-semibold text-slate-700 uppercase tracking-wider">Link with Phone Number</span>
                      <button onClick={() => { setLinkWithPhone(false); setPairingCode(null); }} className="text-xs text-slate-400 hover:text-slate-600">Use QR Code</button>
                    </div>

                    {!pairingCode ? (
                      <form onSubmit={handleRequestPairingCode} className="flex gap-2">
                        <input
                          type="text"
                          value={pairingPhone}
                          onChange={e => setPairingPhone(e.target.value)}
                          placeholder="e.g. 919003619221"
                          className="flex-1 bg-white border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 font-mono"
                        />
                        <button
                          type="submit"
                          disabled={requestingCode}
                          className="bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold px-4 py-2 rounded-lg transition disabled:opacity-50"
                        >
                          {requestingCode ? 'Requesting...' : 'Get Code'}
                        </button>
                      </form>
                    ) : (
                      <div className="text-center py-2">
                        <p className="text-xs text-slate-500 mb-2">Enter this code on your phone when prompted:</p>
                        <div className="inline-flex items-center gap-2 bg-white px-5 py-3 rounded-xl border-2 border-emerald-500 shadow-sm font-mono text-xl tracking-widest font-bold text-slate-800">
                          {pairingCode}
                        </div>
                        <p className="text-[11px] text-slate-400 mt-2">Waiting for confirmation on phone...</p>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Right QR Code Column */}
            <div className="bg-slate-50 p-8 md:p-12 flex flex-col items-center justify-center border-t md:border-t-0 md:border-l border-slate-100 min-w-[320px]">
              <div className="relative p-4 bg-white rounded-2xl shadow-md border border-slate-200">
                {qrCodeData ? (
                  <div className="relative">
                    <img
                      src={qrCodeData.startsWith('data:') ? qrCodeData : `data:image/png;base64,${qrCodeData}`}
                      alt="Scan WhatsApp QR Code"
                      className="w-64 h-64 object-contain rounded-lg"
                    />
                    {qrExpired && (
                      <div className="absolute inset-0 bg-white/90 backdrop-blur-sm flex flex-col items-center justify-center gap-3 p-4 text-center rounded-lg">
                        <AlertCircle className="w-10 h-10 text-amber-500" />
                        <span className="text-sm font-semibold text-slate-700">QR code expired</span>
                        <button
                          onClick={fetchQR}
                          className="bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold px-4 py-2 rounded-lg flex items-center gap-2 shadow-sm transition"
                        >
                          <RefreshCw className="w-3.5 h-3.5" /> Reload QR Code
                        </button>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="w-64 h-64 flex flex-col items-center justify-center gap-3 text-center p-4">
                    <RefreshCw className="w-8 h-8 text-emerald-600 animate-spin" />
                    <span className="text-sm font-semibold text-slate-700">Connecting to WhatsApp...</span>
                    <span className="text-xs text-slate-500">Generating live QR code</span>
                    <button
                      onClick={fetchQR}
                      className="mt-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold px-4 py-2 rounded-lg flex items-center gap-2 shadow-sm transition"
                    >
                      <RefreshCw className="w-3.5 h-3.5" /> Refresh
                    </button>
                  </div>
                )}
              </div>

              <div className="mt-6 flex items-center gap-2 text-xs text-slate-500">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                <span>Auto-refreshing & detecting connection...</span>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom subtle note */}
        <div className="text-center pb-6 text-xs text-slate-500">
          Powered by WAHA & Market Intelligence Lead Quality Engine. Your messages are encrypted and synchronized in real-time.
        </div>
      </div>
    );
  }

  // ===================================================================
  // RENDER: CONNECTED WHATSAPP INTERFACE
  // ===================================================================
  const connectedMe = sessionStatus?.me || {};
  const currentUserName = connectedMe.name || user?.username || 'My WhatsApp';
  const currentUserPhone = formatPhone(connectedMe.phone || selectedSession?.phone_number || '');

  return (
    <div className="flex h-[calc(100vh-4.25rem)] bg-[#f0f2f5] overflow-hidden relative font-sans">
      
      {/* Toast Notification */}
      {toastMessage && (
        <div className={`fixed top-5 right-5 z-50 px-4 py-3 rounded-xl shadow-xl flex items-center gap-3 border transition-all animate-bounce ${
          toastMessage.type === 'error' ? 'bg-red-50 border-red-200 text-red-800' :
          toastMessage.type === 'success' ? 'bg-emerald-50 border-emerald-200 text-emerald-800' :
          'bg-slate-800 text-white border-slate-700'
        }`}>
          <span className="text-sm font-medium">{toastMessage.text}</span>
          <button onClick={() => setToastMessage(null)} className="opacity-60 hover:opacity-100">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* LEFT COLUMN: CHATS SIDEBAR (WhatsApp Web Look & Feel) */}
      {/* ----------------------------------------------------------------- */}
      <div className="w-[380px] md:w-[420px] flex-shrink-0 border-r border-[#e9edef] flex flex-col bg-white">
        
        {/* Sidebar Header */}
        <div className="h-16 px-4 bg-[#f0f2f5] flex items-center justify-between border-b border-[#e9edef]">
          {/* User Profile Badge */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-emerald-600 text-white flex items-center justify-center font-bold text-base shadow-sm overflow-hidden">
              {currentUserName.charAt(0).toUpperCase()}
            </div>
            <div className="flex flex-col">
              <span className="text-sm font-semibold text-slate-800 leading-tight truncate max-w-[150px]">
                {currentUserName}
              </span>
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                <span className="text-xs text-slate-500 font-mono">{currentUserPhone || 'Online'}</span>
              </div>
            </div>
          </div>

          {/* Action Icons */}
          <div className="flex items-center gap-2 text-slate-600">
            <button
              onClick={() => { setShowNewChatModal(true); fetchKeyPeople(); }}
              className="p-2 rounded-full hover:bg-slate-200 transition"
              title="New Chat"
            >
              <MessageSquare className="w-5 h-5" />
            </button>

            <button
              onClick={() => fetchConversations(false)}
              className="p-2 rounded-full hover:bg-slate-200 transition"
              title="Refresh Chats"
            >
              <RefreshCw className={`w-5 h-5 ${loadingChats ? 'animate-spin' : ''}`} />
            </button>

            <div className="relative">
              <button
                onClick={() => setShowSessionDropdown(prev => !prev)}
                className="p-2 rounded-full hover:bg-slate-200 transition"
                title="Options"
              >
                <MoreVertical className="w-5 h-5" />
              </button>

              {showSessionDropdown && (
                <div className="absolute right-0 mt-2 w-56 bg-white rounded-xl shadow-xl border border-slate-200 py-2 z-50 text-sm">
                  <div className="px-4 py-2 border-b border-slate-100">
                    <p className="text-xs text-slate-400 font-medium">Session: {selectedSession?.session_name}</p>
                    <p className="text-xs font-semibold text-emerald-600">Connected</p>
                  </div>
                  <button
                    onClick={() => { setShowNewChatModal(true); setShowSessionDropdown(false); fetchKeyPeople(); }}
                    className="w-full text-left px-4 py-2.5 hover:bg-slate-50 flex items-center gap-2 text-slate-700"
                  >
                    <Plus className="w-4 h-4 text-emerald-600" /> New Chat
                  </button>
                  <button
                    onClick={() => { handleLogoutSession(); setShowSessionDropdown(false); }}
                    className="w-full text-left px-4 py-2.5 hover:bg-red-50 flex items-center gap-2 text-red-600"
                  >
                    <LogOut className="w-4 h-4" /> Disconnect WhatsApp
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Search & Filter Bar */}
        <div className="p-2.5 bg-white border-b border-[#e9edef] space-y-2">
          <div className="relative flex items-center bg-[#f0f2f5] rounded-xl px-3 py-1.5 focus-within:ring-2 focus-within:ring-[#00a884]/30">
            <Search className="w-4 h-4 text-slate-400 mr-2 flex-shrink-0" />
            <input
              type="text"
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              placeholder="Search or start new chat"
              className="w-full bg-transparent border-none text-sm focus:outline-none placeholder:text-slate-500"
            />
            {searchQuery && (
              <button onClick={() => setSearchQuery('')} className="text-slate-400 hover:text-slate-600">
                <X className="w-4 h-4" />
              </button>
            )}
          </div>

          {/* Quick Filter Pills */}
          <div className="flex gap-1.5 px-1">
            <button
              onClick={() => setChatFilter('all')}
              className={`px-3 py-1 rounded-full text-xs font-medium transition ${
                chatFilter === 'all' ? 'bg-[#00a884] text-white' : 'bg-[#f0f2f5] text-slate-600 hover:bg-slate-200'
              }`}
            >
              All
            </button>
            <button
              onClick={() => setChatFilter('unread')}
              className={`px-3 py-1 rounded-full text-xs font-medium transition ${
                chatFilter === 'unread' ? 'bg-[#00a884] text-white' : 'bg-[#f0f2f5] text-slate-600 hover:bg-slate-200'
              }`}
            >
              Unread
            </button>
            <button
              onClick={() => setChatFilter('key')}
              className={`px-3 py-1 rounded-full text-xs font-medium transition ${
                chatFilter === 'key' ? 'bg-[#00a884] text-white' : 'bg-[#f0f2f5] text-slate-600 hover:bg-slate-200'
              }`}
            >
              CRM Contacts
            </button>
          </div>
        </div>

        {/* Conversation List */}
        <div className="flex-1 overflow-y-auto divide-y divide-[#f0f2f5]">
          {loadingChats && chats.length === 0 ? (
            <div className="p-8 text-center text-slate-400 flex flex-col items-center gap-2">
              <RefreshCw className="w-6 h-6 animate-spin text-emerald-600" />
              <span className="text-sm">Loading chats...</span>
            </div>
          ) : filteredChats.length === 0 ? (
            <div className="p-8 text-center text-slate-400">
              <MessageSquare className="w-12 h-12 mx-auto mb-2 opacity-30" />
              <p className="text-sm font-medium text-slate-600">No conversations found</p>
              <button
                onClick={() => { setShowNewChatModal(true); fetchKeyPeople(); }}
                className="mt-3 text-xs text-emerald-600 hover:underline font-semibold"
              >
                + Start a new conversation
              </button>
            </div>
          ) : (
            filteredChats.map(chat => {
              const isSelected = selectedChat?.id === chat.id;
              const name = getContactDisplayName(chat);

              return (
                <div
                  key={chat.id}
                  onClick={() => { setSelectedChat(chat); handleMarkRead(chat); }}
                  className={`flex items-center gap-3 px-4 py-3 cursor-pointer transition select-none ${
                    isSelected ? 'bg-[#f0f2f5]' : 'hover:bg-[#f5f6f6]'
                  }`}
                >
                  {/* Avatar */}
                  <ContactAvatar chat={chat} size="md" avatarVersion={avatarVersion} />

                  {/* Chat Info */}
                  <div className="flex-1 min-w-0">
                    <div className="flex justify-between items-baseline mb-0.5">
                      <h3 className="font-semibold text-slate-800 text-sm truncate flex items-center gap-1.5">
                        <span className="truncate">{name}</span>
                        {chat.is_matched && (
                          <span className="px-1.5 py-0.2 text-[10px] bg-emerald-100 text-emerald-700 rounded font-normal">
                            CRM
                          </span>
                        )}
                      </h3>
                      <span className="text-[11px] text-slate-400 font-medium ml-2 flex-shrink-0">
                        {formatChatDate(chat.last_message_at)}
                      </span>
                    </div>

                    <div className="flex justify-between items-center">
                      <p className="text-xs text-slate-500 truncate pr-2 flex items-center gap-1">
                        {chat.last_message_from_me && (
                          <CheckCheck className="w-3.5 h-3.5 text-slate-400 flex-shrink-0 inline" />
                        )}
                        <span className="truncate">{chat.last_message_preview || 'No messages yet'}</span>
                      </p>

                      {chat.unread_count > 0 && (
                        <div className="min-w-[20px] h-5 bg-[#25d366] text-white text-[11px] font-bold rounded-full flex items-center justify-center px-1.5 shadow-sm">
                          {chat.unread_count}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* RIGHT COLUMN: MAIN CHAT PANE */}
      {/* ----------------------------------------------------------------- */}
      <div className="flex-1 flex flex-col bg-[#efeae2] relative min-w-0">
        
        {selectedChat ? (
          <>
            {/* Authentic Chat Header */}
            <div className="h-16 px-4 bg-[#f0f2f5] border-b border-[#e9edef] flex items-center justify-between z-10 shadow-sm">
              <div className="flex items-center gap-3 min-w-0">
                <ContactAvatar chat={selectedChat} size="sm" avatarVersion={avatarVersion} />

                <div className="min-w-0">
                  <h2 className="font-semibold text-slate-800 text-sm truncate">
                    {getContactDisplayName(selectedChat)}
                  </h2>
                  <p className="text-xs text-slate-500 truncate">
                    {getContactSubtext(selectedChat)}
                  </p>
                </div>
              </div>

              {/* Chat Actions */}
              <div className="flex items-center gap-3 text-slate-600">
                <button
                  onClick={handleSyncHistory}
                  className="p-2 rounded-full hover:bg-slate-200 transition"
                  title="Sync older messages from WhatsApp"
                >
                  <RefreshCw className="w-4 h-4" />
                </button>

                <button
                  onClick={() => setShowMsgSearch(!showMsgSearch)}
                  className="p-2 rounded-full hover:bg-slate-200 transition"
                  title="Search in conversation"
                >
                  <Search className="w-4 h-4" />
                </button>

                <button
                  onClick={() => setShowProfilePanel(!showProfilePanel)}
                  className="p-2 rounded-full hover:bg-slate-200 transition"
                  title="Contact Information"
                >
                  <User className="w-4 h-4" />
                </button>

                <button
                  onClick={handleDeleteChat}
                  className="p-2 rounded-full hover:bg-red-100 text-red-500 transition"
                  title="Delete Chat"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* In-Chat Search Bar */}
            {showMsgSearch && (
              <div className="px-4 py-2 bg-white border-b border-[#e9edef] flex items-center gap-2 shadow-inner">
                <Search className="w-4 h-4 text-slate-400" />
                <input
                  type="text"
                  autoFocus
                  placeholder="Search in this chat..."
                  value={msgSearchQuery}
                  onChange={(e) => setMsgSearchQuery(e.target.value)}
                  className="w-full bg-transparent border-none text-sm focus:outline-none"
                />
                <button
                  onClick={() => { setShowMsgSearch(false); setMsgSearchQuery(''); }}
                  className="text-xs font-semibold text-slate-500 hover:text-slate-700"
                >
                  Done
                </button>
              </div>
            )}

            {/* Message Thread (WhatsApp Wallpaper Area) */}
            <div className="flex-1 overflow-y-auto px-4 md:px-12 py-4 space-y-2">
              {loadingMessages ? (
                <div className="flex justify-center p-8">
                  <RefreshCw className="w-6 h-6 animate-spin text-emerald-600" />
                </div>
              ) : messages.length === 0 ? (
                <div className="flex flex-col items-center justify-center p-12 text-slate-500">
                  <div className="bg-white/80 backdrop-blur px-4 py-2 rounded-xl text-xs shadow-sm">
                    🔒 Messages are end-to-end synchronized. Start your conversation below.
                  </div>
                </div>
              ) : (
                messages
                  .filter(msg => {
                    if (!msgSearchQuery) return true;
                    const text = (msg.full_body || msg.body_preview || '').toLowerCase();
                    return text.includes(msgSearchQuery.toLowerCase());
                  })
                  .map(msg => {
                    const isMe = msg.direction === 'OUTBOUND';
                    const proxySrc = buildMediaSrc(msg);
                    const mime = msg.media_mime_type || '';

                    return (
                      <div key={msg.id} className={`flex ${isMe ? 'justify-end' : 'justify-start'} group mb-1`}>
                        <div
                          className={`max-w-[75%] md:max-w-[65%] rounded-2xl px-3 py-2 shadow-sm relative ${
                            isMe ? 'bg-[#d9fdd3] text-slate-900 rounded-tr-none' : 'bg-white text-slate-900 rounded-tl-none'
                          }`}
                        >
                          {/* Media Display */}
                          {msg.has_media && proxySrc && (
                            <div className="mb-1.5 rounded-xl overflow-hidden">
                              {mime.startsWith('image/') ? (
                                <div
                                  className="relative cursor-pointer group/img overflow-hidden rounded-xl bg-slate-100"
                                  onClick={() => setLightboxMedia({ type: 'image', src: proxySrc, caption: msg.full_body })}
                                >
                                  <img
                                    src={proxySrc}
                                    alt="WhatsApp Photo"
                                    className="max-w-full max-h-[340px] w-auto h-auto object-cover rounded-xl transition duration-200 group-hover/img:scale-[1.02]"
                                    loading="lazy"
                                  />
                                  <div className="absolute inset-0 bg-black/20 opacity-0 group-hover/img:opacity-100 transition flex items-center justify-center text-white">
                                    <Maximize2 className="w-6 h-6 drop-shadow" />
                                  </div>
                                </div>
                              ) : mime.startsWith('video/') ? (
                                <div className="rounded-xl overflow-hidden bg-black max-w-full">
                                  <video
                                    src={proxySrc}
                                    controls
                                    className="max-w-full max-h-[340px] rounded-xl"
                                    preload="metadata"
                                  />
                                </div>
                              ) : mime.startsWith('audio/') ? (
                                <WhatsAppAudioPlayer src={proxySrc} isMe={isMe} />
                              ) : (
                                <div className="flex items-center gap-3 p-3 bg-slate-50 border border-slate-200 rounded-xl">
                                  <div className="w-10 h-10 rounded-lg bg-emerald-100 text-emerald-700 flex items-center justify-center flex-shrink-0">
                                    <FileText className="w-5 h-5" />
                                  </div>
                                  <div className="flex-1 min-w-0">
                                    <p className="text-xs font-semibold text-slate-800 truncate">
                                      {msg.full_body || 'Attachment'}
                                    </p>
                                    <p className="text-[10px] text-slate-400 uppercase">{mime.split('/')[1] || 'FILE'}</p>
                                  </div>
                                  <a
                                    href={proxySrc}
                                    download
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="p-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 transition"
                                  >
                                    <Download className="w-4 h-4" />
                                  </a>
                                </div>
                              )}
                            </div>
                          )}

                          {/* Message Text Body */}
                          {msg.full_body || msg.body_preview ? (
                            <p className="text-sm whitespace-pre-wrap break-words leading-relaxed">
                              {msg.full_body || msg.body_preview}
                            </p>
                          ) : msg.has_media ? null : (
                            <p className="text-sm italic text-slate-400">Unsupported message type</p>
                          )}

                          {/* Footer with Timestamp and Status Ticks */}
                          <div className="flex items-center justify-end gap-1 mt-1 select-none">
                            <span className="text-[10px] text-slate-500 font-medium">
                              {formatMessageTime(msg.created_at || msg.sent_at)}
                            </span>

                            {isMe && (
                              <span className="ml-0.5">
                                {msg.status === 'READ' ? (
                                  <CheckCheck className="w-3.5 h-3.5 text-[#53bdeb]" />
                                ) : msg.status === 'DELIVERED' ? (
                                  <CheckCheck className="w-3.5 h-3.5 text-slate-400" />
                                ) : msg.status === 'SENT' ? (
                                  <Check className="w-3.5 h-3.5 text-slate-400" />
                                ) : (
                                  <Clock className="w-3 h-3 text-slate-400" />
                                )}
                              </span>
                            )}
                          </div>

                          {/* Delete on hover for own messages */}
                          {isMe && (
                            <button
                              onClick={() => handleDeleteMessage(msg.id)}
                              className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-white border border-slate-200 text-slate-400 hover:text-red-500 flex items-center justify-center opacity-0 group-hover:opacity-100 transition shadow"
                              title="Delete message"
                            >
                              <X className="w-3 h-3" />
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input Toolbar */}
            <div className="relative bg-[#f0f2f5] px-4 py-2.5 flex flex-col z-20">
              
              {/* Emoji Drawer */}
              {showEmojiPicker && (
                <div className="absolute bottom-16 left-4 z-50 bg-white border border-slate-200 rounded-2xl shadow-2xl p-4 w-80">
                  <div className="flex justify-between items-center mb-2 pb-1 border-b border-slate-100">
                    <span className="text-xs font-bold text-slate-500">Emojis</span>
                    <button onClick={() => setShowEmojiPicker(false)} className="text-slate-400 hover:text-slate-600">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="grid grid-cols-8 gap-1.5 max-h-48 overflow-y-auto">
                    {[
                      '😀','😂','😊','😍','🥰','😘','😎','🤔','😅','😭',
                      '😱','🥳','🤗','😏','😒','🙄','😤','🤩','🥺','😔',
                      '👍','👎','❤️','🔥','✅','🎉','👏','🙏','💯','⭐',
                      '😴','🤤','😋','🤪','🤓','😷','🤒','🤢','😈','👻',
                      '🌹','🌺','🌸','🌼','🌻','🌞','🌈','⚡','💧','🎵'
                    ].map(em => (
                      <button
                        key={em}
                        type="button"
                        onClick={() => { setMessage(prev => prev + em); setShowEmojiPicker(false); }}
                        className="text-xl p-1 hover:bg-slate-100 rounded-lg transition"
                      >
                        {em}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Attachment Popover Menu */}
              {showAttachMenu && (
                <div className="absolute bottom-16 left-14 z-50 bg-white rounded-2xl shadow-xl border border-slate-200 p-2 flex flex-col gap-1 w-48 text-sm">
                  <label className="flex items-center gap-3 px-3 py-2 rounded-xl hover:bg-slate-50 cursor-pointer text-slate-700">
                    <div className="w-8 h-8 rounded-full bg-purple-100 text-purple-600 flex items-center justify-center">
                      <ImageIcon className="w-4 h-4" />
                    </div>
                    <span>Photos & Videos</span>
                    <input
                      type="file"
                      accept="image/*,video/*"
                      className="hidden"
                      onChange={handleFileSelect}
                    />
                  </label>

                  <label className="flex items-center gap-3 px-3 py-2 rounded-xl hover:bg-slate-50 cursor-pointer text-slate-700">
                    <div className="w-8 h-8 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center">
                      <FileText className="w-4 h-4" />
                    </div>
                    <span>Document</span>
                    <input
                      type="file"
                      accept=".pdf,.doc,.docx,.xls,.xlsx,.zip"
                      className="hidden"
                      onChange={handleFileSelect}
                    />
                  </label>

                  <label className="flex items-center gap-3 px-3 py-2 rounded-xl hover:bg-slate-50 cursor-pointer text-slate-700">
                    <div className="w-8 h-8 rounded-full bg-orange-100 text-orange-600 flex items-center justify-center">
                      <Mic className="w-4 h-4" />
                    </div>
                    <span>Audio File</span>
                    <input
                      type="file"
                      accept="audio/*"
                      className="hidden"
                      onChange={handleFileSelect}
                    />
                  </label>
                </div>
              )}

              {/* Attachment Preview Card */}
              {attachPreview && (
                <div className="mb-2 p-3 bg-white rounded-2xl border border-slate-200 shadow-md flex items-center gap-3">
                  {attachPreview.mime.startsWith('image/') ? (
                    <img src={attachPreview.url} alt="Preview" className="w-16 h-16 object-cover rounded-xl" />
                  ) : attachPreview.mime.startsWith('audio/') ? (
                    <div className="w-16 h-16 rounded-xl bg-emerald-50 text-emerald-600 flex items-center justify-center">
                      <Mic className="w-7 h-7" />
                    </div>
                  ) : (
                    <div className="w-16 h-16 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center">
                      <FileText className="w-7 h-7" />
                    </div>
                  )}

                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold text-slate-800 truncate">{attachPreview.name}</p>
                    <p className="text-[10px] text-slate-400">{(attachPreview.size / 1024).toFixed(1)} KB</p>
                    <input
                      type="text"
                      placeholder="Add a caption..."
                      value={message}
                      onChange={e => setMessage(e.target.value)}
                      className="mt-1 w-full bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500"
                    />
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setAttachPreview(null)}
                      className="p-1.5 text-slate-400 hover:text-red-500"
                      title="Cancel"
                    >
                      <X className="w-5 h-5" />
                    </button>
                    <button
                      onClick={handleSendMedia}
                      disabled={isSendingMedia}
                      className="bg-[#00a884] hover:bg-emerald-700 text-white text-xs font-bold px-4 py-2 rounded-xl flex items-center gap-1.5 shadow transition disabled:opacity-50"
                    >
                      {isSendingMedia ? <RefreshCw className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                      Send
                    </button>
                  </div>
                </div>
              )}

              {/* Main Input Row */}
              <div className="flex items-center gap-2">
                
                {/* Voice Note Recording Status Active */}
                {isRecording ? (
                  <div className="flex-1 flex items-center justify-between bg-white rounded-2xl px-4 py-2 border border-red-200 shadow-sm animate-pulse">
                    <div className="flex items-center gap-3">
                      <span className="w-3 h-3 rounded-full bg-red-500 animate-ping" />
                      <span className="text-sm font-semibold text-red-600">Recording Audio...</span>
                      <span className="text-xs font-mono text-slate-500">{recordingSeconds}s</span>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={cancelRecording}
                        className="p-2 rounded-full hover:bg-red-50 text-red-500 transition"
                        title="Cancel Recording"
                      >
                        <Trash2 className="w-5 h-5" />
                      </button>
                      <button
                        onClick={stopRecording}
                        className="bg-emerald-600 hover:bg-emerald-700 text-white p-2 rounded-full shadow transition"
                        title="Finish & Review Voice Note"
                      >
                        <Square className="w-4 h-4 fill-current" />
                      </button>
                    </div>
                  </div>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={() => { setShowEmojiPicker(prev => !prev); setShowAttachMenu(false); }}
                      className="p-2 text-slate-500 hover:text-slate-700 rounded-full hover:bg-slate-200 transition"
                    >
                      <Smile className="w-6 h-6" />
                    </button>

                    <button
                      type="button"
                      onClick={() => { setShowAttachMenu(prev => !prev); setShowEmojiPicker(false); }}
                      className="p-2 text-slate-500 hover:text-slate-700 rounded-full hover:bg-slate-200 transition"
                    >
                      <Paperclip className="w-6 h-6" />
                    </button>

                    <input
                      type="text"
                      placeholder="Type a message"
                      value={message}
                      onChange={e => setMessage(e.target.value)}
                      onKeyDown={e => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          if (attachPreview) {
                            handleSendMedia();
                          } else {
                            handleSendMessage();
                          }
                        }
                      }}
                      className="flex-1 bg-white rounded-2xl px-4 py-2.5 text-sm focus:outline-none border-none shadow-sm placeholder:text-slate-400"
                    />

                    {message.trim() || attachPreview ? (
                      <button
                        type="button"
                        onClick={attachPreview ? handleSendMedia : handleSendMessage}
                        className="w-10 h-10 bg-[#00a884] hover:bg-emerald-700 text-white rounded-full flex items-center justify-center transition shadow-md flex-shrink-0"
                      >
                        <Send className="w-5 h-5 ml-0.5" />
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={startRecording}
                        className="w-10 h-10 bg-slate-200 hover:bg-emerald-100 hover:text-emerald-700 text-slate-600 rounded-full flex items-center justify-center transition flex-shrink-0"
                        title="Record Voice Note"
                      >
                        <Mic className="w-5 h-5" />
                      </button>
                    )}
                  </>
                )}
              </div>
            </div>
          </>
        ) : (
          /* Empty State when no conversation is selected */
          <div className="flex-1 flex flex-col items-center justify-center p-8 text-center bg-[#f0f2f5] border-b-[6px] border-[#00a884]">
            <div className="w-64 h-64 mb-6 rounded-full bg-white flex items-center justify-center shadow-inner border border-slate-200">
              <Phone className="w-24 h-24 text-slate-300" />
            </div>
            <h2 className="text-2xl font-light text-slate-700 mb-2">WhatsApp Web</h2>
            <p className="text-sm text-slate-500 max-w-md mb-6 leading-relaxed">
              Send and receive WhatsApp messages directly synchronized with your CRM leads. Select a conversation from the left or start a new chat.
            </p>
            <button
              onClick={() => { setShowNewChatModal(true); fetchKeyPeople(); }}
              className="bg-[#00a884] hover:bg-emerald-700 text-white text-sm font-semibold px-6 py-2.5 rounded-full shadow transition flex items-center gap-2"
            >
              <Plus className="w-4 h-4" /> Start New Chat
            </button>
          </div>
        )}
      </div>

      {/* ----------------------------------------------------------------- */}
      {/* CONTACT PROFILE SLIDEOUT PANEL */}
      {/* ----------------------------------------------------------------- */}
      {selectedChat && showProfilePanel && (
        <div className="w-80 border-l border-[#e9edef] bg-white flex flex-col flex-shrink-0 overflow-y-auto z-20">
          <div className="h-16 px-4 bg-[#f0f2f5] border-b border-[#e9edef] flex justify-between items-center">
            <span className="font-semibold text-slate-800 text-sm">Contact Info</span>
            <button onClick={() => setShowProfilePanel(false)} className="text-slate-400 hover:text-slate-600">
              <X className="w-5 h-5" />
            </button>
          </div>

          <div className="p-6 flex flex-col items-center border-b border-slate-100 relative">
            <div className="relative group">
              <ContactAvatar chat={selectedChat} size="lg" avatarVersion={avatarVersion} />
              <button
                onClick={() => avatarFileInputRef.current?.click()}
                disabled={uploadingAvatar}
                title="Change contact profile picture"
                className="absolute bottom-0 right-0 p-2 bg-[#00a884] hover:bg-emerald-700 text-white rounded-full shadow-lg transition transform hover:scale-110 z-20 flex items-center justify-center cursor-pointer"
              >
                <Camera className="w-4 h-4" />
              </button>
              <input
                ref={avatarFileInputRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                onChange={handleAvatarUpload}
                className="hidden"
              />
            </div>
            {!isEditingName ? (
              <div className="flex items-center justify-center gap-1.5 mt-3 max-w-full px-2">
                <h3 className="text-base font-bold text-slate-800 text-center truncate">
                  {getContactDisplayName(selectedChat)}
                </h3>
                <button
                  type="button"
                  onClick={() => {
                    setEditNameValue(selectedChat.whatsapp_name || selectedChat.contact_name || '');
                    setIsEditingName(true);
                  }}
                  className="p-1 rounded-full text-slate-400 hover:text-emerald-600 hover:bg-slate-100 transition flex-shrink-0"
                  title="Rename contact"
                >
                  <Edit2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ) : (
              <div className="mt-3 w-full px-3 flex flex-col gap-1.5">
                <div className="flex items-center gap-1">
                  <input
                    type="text"
                    value={editNameValue}
                    onChange={(e) => setEditNameValue(e.target.value)}
                    placeholder="Enter contact name"
                    className="flex-1 bg-white border border-emerald-500 rounded-lg px-2.5 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500 text-slate-800"
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleSaveContactName();
                      if (e.key === 'Escape') setIsEditingName(false);
                    }}
                  />
                  <button
                    type="button"
                    onClick={handleSaveContactName}
                    disabled={savingName}
                    className="p-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg transition disabled:opacity-50"
                    title="Save"
                  >
                    <Check className="w-3.5 h-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsEditingName(false)}
                    className="p-1.5 bg-slate-200 hover:bg-slate-300 text-slate-600 rounded-lg transition"
                    title="Cancel"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
                <span className="text-[10px] text-slate-400 text-center">Press Enter to save or Esc to cancel</span>
              </div>
            )}

            {/* Phone Number Display / Edit */}
            {!isEditingPhone ? (
              <div className="flex items-center justify-center gap-1.5 mt-1 text-xs text-slate-600 font-mono">
                <Phone className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />
                <span>{selectedChat.phone_number || selectedChat.prospect_phone || (formatPhone(selectedChat.chat_id) || 'No phone set')}</span>
                <button
                  type="button"
                  onClick={() => {
                    setEditPhoneValue(selectedChat.phone_number || selectedChat.prospect_phone || formatPhone(selectedChat.chat_id) || '');
                    setIsEditingPhone(true);
                  }}
                  className="p-1 rounded-full text-slate-400 hover:text-emerald-600 hover:bg-slate-100 transition"
                  title="Edit phone number"
                >
                  <Edit2 className="w-3 h-3" />
                </button>
              </div>
            ) : (
              <div className="mt-2 w-full px-3 flex flex-col gap-1.5">
                <div className="flex items-center gap-1">
                  <input
                    type="text"
                    value={editPhoneValue}
                    onChange={(e) => setEditPhoneValue(e.target.value)}
                    placeholder="e.g. +919003619221"
                    className="flex-1 bg-white border border-emerald-500 rounded-lg px-2.5 py-1 text-xs focus:outline-none focus:ring-1 focus:ring-emerald-500 text-slate-800 font-mono"
                    autoFocus
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') handleSaveContactPhone();
                      if (e.key === 'Escape') setIsEditingPhone(false);
                    }}
                  />
                  <button
                    type="button"
                    onClick={handleSaveContactPhone}
                    disabled={savingPhone}
                    className="p-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg transition disabled:opacity-50"
                    title="Save"
                  >
                    <Check className="w-3.5 h-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setIsEditingPhone(false)}
                    className="p-1.5 bg-slate-200 hover:bg-slate-300 text-slate-600 rounded-lg transition"
                    title="Cancel"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
                <span className="text-[10px] text-slate-400 text-center">Enter phone with country code (e.g. +91...)</span>
              </div>
            )}

            {uploadingAvatar && (
              <p className="text-[11px] text-emerald-600 mt-1 animate-pulse">Uploading photo...</p>
            )}
          </div>

          <div className="p-4 space-y-4 text-xs">
            {/* CRM Link Card */}
            <div className="bg-slate-50 rounded-xl p-3 border border-slate-200/80">
              <div className="flex items-center justify-between mb-2">
                <span className="font-semibold text-slate-500 uppercase tracking-wider text-[10px]">
                  CRM Contact Link
                </span>
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold ${
                  selectedChat.is_matched ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'
                }`}>
                  {selectedChat.is_matched ? '✓ Linked to CRM' : 'Unmatched'}
                </span>
              </div>

              {selectedChat.is_matched ? (
                <div className="space-y-2">
                  <div>
                    <span className="text-[10px] text-slate-400 block">Company</span>
                    <p className="text-slate-900 font-bold text-sm flex items-center gap-1.5">
                      <Building className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />
                      <span>{selectedChat.prospect_name || wahaContact?.company || 'Unknown Company'}</span>
                    </p>
                  </div>

                  {selectedChat.contact_name && (
                    <div>
                      <span className="text-[10px] text-slate-400 block">Key Person</span>
                      <p className="text-slate-800 font-medium text-xs flex items-center gap-1.5">
                        <User className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                        <span>{selectedChat.contact_name}</span>
                      </p>
                    </div>
                  )}

                  {(selectedChat.contact_designation || wahaContact?.designation) && (
                    <div>
                      <span className="text-[10px] text-slate-400 block">Designation</span>
                      <p className="text-slate-700 text-xs flex items-center gap-1.5">
                        <Briefcase className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                        <span>{selectedChat.contact_designation || wahaContact?.designation}</span>
                      </p>
                    </div>
                  )}

                  {(selectedChat.contact_email || wahaContact?.official_email) && (
                    <div>
                      <span className="text-[10px] text-slate-400 block">Email</span>
                      <p className="text-slate-700 text-xs flex items-center gap-1.5 font-mono">
                        <Mail className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />
                        <span>{selectedChat.contact_email || wahaContact?.official_email}</span>
                      </p>
                    </div>
                  )}

                  <div className="pt-2 border-t border-slate-200 flex gap-2">
                    <button
                      onClick={() => { setShowLinkCRMModal(true); handleSearchCRM(); }}
                      className="flex-1 bg-white hover:bg-slate-100 text-slate-700 font-semibold py-1.5 px-2 rounded-lg border border-slate-300 transition text-[11px] flex items-center justify-center gap-1 cursor-pointer"
                    >
                      <LinkIcon className="w-3 h-3 text-slate-500" /> Change Link
                    </button>
                    <button
                      onClick={() => handleLinkToCRM(null)}
                      className="bg-white hover:bg-rose-50 text-rose-600 hover:text-rose-700 font-semibold py-1.5 px-2 rounded-lg border border-rose-200 transition text-[11px] flex items-center justify-center gap-1 cursor-pointer"
                      title="Unlink from CRM"
                    >
                      <Unlink className="w-3 h-3" /> Unlink
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  <p className="text-slate-600 text-xs leading-relaxed">
                    This WhatsApp chat is not yet linked to any Key Person or Lead in your CRM database.
                  </p>
                  <button
                    onClick={() => { setShowLinkCRMModal(true); handleSearchCRM(); }}
                    className="w-full bg-[#00a884] hover:bg-emerald-700 text-white font-semibold py-2 px-3 rounded-xl shadow-sm transition text-xs flex items-center justify-center gap-1.5 cursor-pointer"
                  >
                    <LinkIcon className="w-3.5 h-3.5" /> Link to CRM Contact
                  </button>
                </div>
              )}
            </div>

            {/* Chat ID details */}
            <div>
              <span className="font-semibold text-slate-400 uppercase tracking-wider block mb-1">Chat ID</span>
              <p className="text-slate-600 font-mono break-all bg-slate-50 p-2 rounded-lg border border-slate-200 text-[11px]">
                {selectedChat.chat_id}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* FULLSCREEN LIGHTBOX MODAL */}
      {/* ----------------------------------------------------------------- */}
      {lightboxMedia && (
        <div className="fixed inset-0 z-50 bg-black/90 backdrop-blur-md flex flex-col justify-between p-4 animate-in fade-in duration-200">
          <div className="flex justify-between items-center text-white px-4 py-2">
            <span className="text-sm font-semibold">{lightboxMedia.caption || 'Photo'}</span>
            <div className="flex items-center gap-3">
              <a
                href={lightboxMedia.src}
                download
                target="_blank"
                rel="noopener noreferrer"
                className="p-2 rounded-full hover:bg-white/10 transition"
                title="Download"
              >
                <Download className="w-5 h-5 text-white" />
              </a>
              <button
                onClick={() => setLightboxMedia(null)}
                className="p-2 rounded-full hover:bg-white/10 transition"
                title="Close"
              >
                <X className="w-6 h-6 text-white" />
              </button>
            </div>
          </div>

          <div className="flex-1 flex items-center justify-center p-4">
            <img
              src={lightboxMedia.src}
              alt="Full size media"
              className="max-h-[85vh] max-w-[90vw] object-contain rounded-xl shadow-2xl"
            />
          </div>

          {lightboxMedia.caption && (
            <div className="text-center text-white text-sm bg-black/40 py-2 rounded-xl max-w-xl mx-auto">
              {lightboxMedia.caption}
            </div>
          )}
        </div>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* NEW CHAT MODAL */}
      {/* ----------------------------------------------------------------- */}
      {showNewChatModal && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full overflow-hidden border border-slate-200 animate-in zoom-in-95 duration-150">
            <div className="h-14 px-5 bg-[#00a884] text-white flex items-center justify-between">
              <h3 className="font-bold text-base">New WhatsApp Chat</h3>
              <button onClick={() => setShowNewChatModal(false)} className="text-white/80 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                  Start with Phone Number (with Country Code)
                </label>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newChatPhone}
                    onChange={e => setNewChatPhone(e.target.value)}
                    placeholder="e.g. 919003619221"
                    className="flex-1 border border-slate-300 rounded-xl px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-500 font-mono"
                  />
                  <button
                    onClick={() => {
                      if (newChatPhone.trim()) {
                        handleStartNewChat(newChatPhone, newChatPhone, 'Direct WhatsApp');
                        setNewChatPhone('');
                      }
                    }}
                    className="bg-[#00a884] hover:bg-emerald-700 text-white text-xs font-semibold px-4 py-2 rounded-xl transition"
                  >
                    Start Chat
                  </button>
                </div>
              </div>

              <div className="pt-2 border-t border-slate-100">
                <span className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">
                  Or select CRM Key Person:
                </span>

                <div className="max-h-60 overflow-y-auto divide-y divide-slate-100 border border-slate-200 rounded-xl">
                  {loadingKeyPeople ? (
                    <div className="p-4 text-center text-xs text-slate-400">Loading contacts...</div>
                  ) : keyPeople.length === 0 ? (
                    <div className="p-4 text-center text-xs text-slate-400">No CRM contacts found with phone numbers.</div>
                  ) : (
                    keyPeople.filter(kp => kp.phone_number).map(kp => (
                      <div
                        key={kp.id}
                        onClick={() => handleStartNewChat(kp.phone_number, kp.contact_name, kp.prospect_name, kp.id)}
                        className="p-3 hover:bg-slate-50 cursor-pointer flex items-center justify-between transition"
                      >
                        <div>
                          <p className="text-xs font-bold text-slate-800">{kp.contact_name}</p>
                          <p className="text-[11px] text-slate-500">{kp.prospect_name || 'CRM Lead'}</p>
                        </div>
                        <span className="text-xs font-mono text-emerald-600 font-semibold">{kp.phone_number}</span>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ----------------------------------------------------------------- */}
      {/* LINK CRM CONTACT MODAL */}
      {/* ----------------------------------------------------------------- */}
      {showLinkCRMModal && selectedChat && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full overflow-hidden border border-slate-200 animate-in zoom-in-95 duration-150 flex flex-col max-h-[85vh]">
            <div className="h-14 px-5 bg-[#00a884] text-white flex items-center justify-between flex-shrink-0">
              <div>
                <h3 className="font-bold text-base flex items-center gap-2">
                  <LinkIcon className="w-4 h-4" /> Link to CRM Contact
                </h3>
                <p className="text-[11px] text-emerald-100 font-mono">
                  {selectedChat.chat_id}
                </p>
              </div>
              <button
                onClick={() => setShowLinkCRMModal(false)}
                className="text-white/80 hover:text-white p-1 rounded-lg hover:bg-white/10 transition cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-4 border-b border-slate-100 flex-shrink-0">
              <div className="relative flex items-center bg-[#f0f2f5] rounded-xl px-3 py-2 focus-within:ring-2 focus-within:ring-[#00a884]/40">
                <Search className="w-4 h-4 text-slate-400 mr-2 flex-shrink-0" />
                <input
                  type="text"
                  value={crmSearchQuery}
                  onChange={e => {
                    setCrmSearchQuery(e.target.value);
                    handleSearchCRM(e.target.value);
                  }}
                  placeholder="Search by contact name, company, email, or phone..."
                  className="w-full bg-transparent text-xs text-slate-800 placeholder-slate-400 focus:outline-none"
                  autoFocus
                />
                {crmSearchQuery && (
                  <button
                    onClick={() => {
                      setCrmSearchQuery('');
                      handleSearchCRM('');
                    }}
                    className="text-slate-400 hover:text-slate-600 p-0.5 cursor-pointer"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-4 space-y-2">
              {loadingCrmSearch ? (
                <div className="py-8 text-center text-xs text-slate-400 animate-pulse">
                  Searching CRM contacts...
                </div>
              ) : crmSearchResults.length === 0 ? (
                <div className="py-8 text-center text-xs text-slate-400">
                  No matching CRM contacts found. Try a different search term.
                </div>
              ) : (
                crmSearchResults.map(contact => {
                  const isCurrent = selectedChat.prospect_contact === contact.id;
                  return (
                    <div
                      key={contact.id}
                      className={`p-3 rounded-xl border transition flex items-center justify-between gap-3 ${
                        isCurrent
                          ? 'border-emerald-500 bg-emerald-50/50'
                          : 'border-slate-200 hover:border-emerald-300 hover:bg-slate-50'
                      }`}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2 mb-0.5">
                          <p className="font-bold text-slate-900 text-xs truncate">
                            {contact.contact_name}
                          </p>
                          {contact.designation && (
                            <span className="text-[10px] text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded truncate">
                              {contact.designation}
                            </span>
                          )}
                        </div>

                        <p className="text-[11px] text-slate-600 font-medium flex items-center gap-1.5 truncate">
                          <Building className="w-3 h-3 text-slate-400 flex-shrink-0" />
                          <span className="truncate">{contact.company_name || 'No Company'}</span>
                        </p>

                        <div className="flex items-center gap-3 text-[10px] text-slate-400 font-mono mt-1">
                          {contact.phone_number && (
                            <span className="flex items-center gap-1 text-emerald-700">
                              <Phone className="w-2.5 h-2.5" /> {contact.phone_number}
                            </span>
                          )}
                          {contact.official_email && (
                            <span className="flex items-center gap-1 truncate">
                              <Mail className="w-2.5 h-2.5" /> {contact.official_email}
                            </span>
                          )}
                        </div>
                      </div>

                      <div>
                        {isCurrent ? (
                          <span className="px-3 py-1.5 bg-emerald-100 text-emerald-800 rounded-lg text-xs font-semibold flex items-center gap-1">
                            <Check className="w-3.5 h-3.5" /> Linked
                          </span>
                        ) : (
                          <button
                            onClick={() => handleLinkToCRM(contact.id)}
                            className="bg-[#00a884] hover:bg-emerald-700 text-white text-xs font-semibold px-3.5 py-1.5 rounded-lg shadow transition flex items-center gap-1 cursor-pointer"
                          >
                            <LinkIcon className="w-3 h-3" /> Link
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            <div className="p-3 bg-slate-50 border-t border-slate-200 flex justify-between items-center text-xs text-slate-500 flex-shrink-0">
              <span>{crmSearchResults.length} contacts available</span>
              {selectedChat.is_matched && (
                <button
                  onClick={() => handleLinkToCRM(null)}
                  className="text-rose-600 hover:text-rose-700 font-medium hover:underline text-xs cursor-pointer"
                >
                  Unlink current CRM contact
                </button>
              )}
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
