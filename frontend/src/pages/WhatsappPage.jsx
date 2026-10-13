import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useSelector } from 'react-redux';
import { Search, MoreVertical, Paperclip, Smile, Send, Phone, Video, RefreshCw, Plus, Trash2, X, ChevronDown } from 'lucide-react';
import api from '../services/api';

const API_BASE = api.defaults.baseURL;
const HOST_URL = API_BASE.endsWith('/api') ? API_BASE.slice(0, -4) : API_BASE;

export default function WhatsappPage() {
  const { user, accessToken: reduxAccessToken } = useSelector((state) => state.auth);

  // Session management
  const [sessions, setSessions] = useState([]);
  const [selectedSession, setSelectedSession] = useState(null);
  const [showSessionDropdown, setShowSessionDropdown] = useState(false);

  // Conversations
  const [chats, setChats] = useState([]);
  const [selectedChat, setSelectedChat] = useState(null);
  const [messages, setMessages] = useState([]);
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [toastMessage, setToastMessage] = useState(null);
  const [showEmojiPicker, setShowEmojiPicker] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [showMsgSearch, setShowMsgSearch] = useState(false);
  const [showProfilePanel, setShowProfilePanel] = useState(false);
  const [wahaContact, setWahaContact] = useState(null);
  const [msgSearchQuery, setMsgSearchQuery] = useState('');
  const [attachPreview, setAttachPreview] = useState(null);
  const [isSendingMedia, setIsSendingMedia] = useState(false);

  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);

  // -------------------------------------------------------------------
  // Session management
  // -------------------------------------------------------------------

  const fetchSessions = useCallback(async () => {
    try {
      const res = await api.get('/whatsapp/session/list/');
      setSessions(res.data);
      // Auto-select first READY session, or just first session.
      if (!selectedSession && res.data.length > 0) {
        const ready = res.data.find(s => s.status === 'READY') || res.data[0];
        setSelectedSession(ready);
      }
    } catch (err) {
      console.error('Failed to fetch sessions:', err);
    }
  }, [selectedSession]);

  useEffect(() => {
    fetchSessions();
  }, []);



  // -------------------------------------------------------------------
  // Contact info (now authenticated via api)
  // -------------------------------------------------------------------

  useEffect(() => {
    if (selectedChat) {
      setWahaContact(null);
      api.get(`/whatsapp/contact-info/${selectedChat.chat_id}/`)
        .then(r => {
          if (r.data?.phoneNumber) setWahaContact(r.data);
        }).catch(err => console.error('Contact info error:', err));
    }
  }, [selectedChat]);

  // -------------------------------------------------------------------
  // Conversations and messages
  // -------------------------------------------------------------------

  useEffect(() => {
    if (selectedSession) {
      setChats([]);
      setSelectedChat(null);
      fetchConversations(false, selectedSession.id);
    }
  }, [selectedSession?.id]);

  useEffect(() => {
    if (selectedChat) {
      fetchMessages(selectedChat.id);
    }
  }, [selectedChat?.id]);

  const handleSyncHistory = async () => {
    if (!selectedChat) return;
    try {
      setToastMessage({ text: 'Syncing history...', type: 'info' });
      const response = await api.post(`/whatsapp/conversations/${selectedChat.id}/sync/`);
      setToastMessage({ text: response.data.detail || 'Sync complete.', type: 'success' });
      setTimeout(() => setToastMessage(null), 3000);
      fetchMessages(selectedChat.id);
    } catch (error) {
      console.error('Failed to sync history:', error);
      setToastMessage({ text: error.response?.data?.detail || 'Failed to sync history', type: 'error' });
      setTimeout(() => setToastMessage(null), 4000);
    }
  };

  // Polling for real-time updates
  useEffect(() => {
    const intervalId = setInterval(() => {
      if (selectedSession) fetchConversations(true, selectedSession.id);
      if (selectedChat) fetchMessages(selectedChat.id, true);
    }, 5000);
    return () => clearInterval(intervalId);
  }, [selectedChat?.id, selectedSession?.id]);

  // Scroll to bottom when messages update
  useEffect(() => {
    if (messages.length > 0) {
      setTimeout(scrollToBottom, 50);
    }
  }, [messages.length, selectedChat?.id]);

  const fetchConversations = async (isPolling = false, sessionId = null) => {
    try {
      const params = {};
      if (sessionId) params.session_id = sessionId;
      const response = await api.get('/whatsapp/conversations/', { params });
      setChats(response.data);
    } catch (error) {
      console.error('Failed to fetch conversations:', error);
    } finally {
      if (!isPolling) setLoading(false);
    }
  };

  const fetchMessages = async (conversationId, isPolling = false) => {
    if (!isPolling) setLoadingMessages(true);
    try {
      const response = await api.get(`/whatsapp/conversations/${conversationId}/messages/`);
      const sorted = response.data.messages.reverse();
      setMessages(sorted);
      if (!isPolling) setTimeout(scrollToBottom, 150);
    } catch (error) {
      console.error('Failed to fetch messages:', error);
    } finally {
      if (!isPolling) setLoadingMessages(false);
    }
  };

  const handleSendMessage = async () => {
    if (!message.trim() || !selectedChat) return;
    const body = message.trim();
    setMessage('');
    try {
      const response = await api.post('/whatsapp/send/', {
        prospect_contact_id: selectedChat.prospect_contact || null,
        chat_id: selectedChat.chat_id,
        message_body: body
      });
      setMessages(prev => [...prev, response.data]);
      setTimeout(scrollToBottom, 100);
      setChats(prevChats => prevChats.map(c =>
        c.id === selectedChat.id
          ? { ...c, last_message_preview: body, last_message_at: new Date().toISOString() }
          : c
      ));
    } catch (error) {
      console.error('Failed to send message:', error);
      const errMsg = error.response?.data?.detail || 'Failed to send message';
      showToast(typeof errMsg === 'string' ? errMsg : 'An error occurred while sending the message.', 'error');
    }
  };

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

  const handleMarkRead = async () => {
    if (!selectedChat) return;
    try {
      await api.post(`/whatsapp/conversations/${selectedChat.id}/read/`);
      setChats(prev => prev.map(c =>
        c.id === selectedChat.id ? { ...c, unread_count: 0 } : c
      ));
    } catch (err) {
      // Non-critical; continue.
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'auto' });
  };

  const showToast = (text, type = 'info') => {
    setToastMessage({ text, type });
    setTimeout(() => setToastMessage(null), type === 'error' ? 5000 : 3000);
  };

  const handleEmojiClick = (emoji) => {
    setMessage(prev => prev + emoji);
    setShowEmojiPicker(false);
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    setAttachPreview({ file, url, mime: file.type });
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

      showToast('Media sent!', 'success');
    } catch (err) {
      showToast(err.response?.data?.detail || 'Failed to send media', 'error');
    } finally {
      setIsSendingMedia(false);
    }
  };

  // Common emoji set
  const EMOJIS = [
    '😀','😂','😊','😍','🥰','😘','😎','🤔','😅','😭',
    '😱','🥳','🤗','😏','😒','🙄','😤','🤩','🥺','😔',
    '👍','👎','❤️','🔥','✅','🎉','👏','🙏','💯','⭐',
    '😴','🤤','😋','🤪','🤓','😷','🤒','🤢','😈','👻',
    '🌹','🌺','🌸','🌼','🌻','🌞','🌈','⚡','💧','🎵',
  ];

  const formatTime = (dateString) => {
    if (!dateString) return '';
    return new Date(dateString).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  const formatPhoneFromChatId = (chatId) => {
    if (!chatId) return '';
    if (chatId.includes('@c.us') || chatId.includes('@s.whatsapp.net')) {
      return '+' + chatId.split('@')[0];
    }
    if (chatId.includes('@g.us')) {
      return 'Group Chat';
    }
    return ''; // Do not display raw LIDs in the UI
  };

  const buildMediaSrc = useCallback((msg) => {
    const raw = msg.media_url || msg.media_file || '';
    if (!raw) return '';
    if (raw.startsWith('/media/') || raw.startsWith('http://localhost') || raw.startsWith('http://host.docker')) {
      return `${API_BASE}/whatsapp/media-proxy/?url=${encodeURIComponent(raw)}&message_id=${msg.id}`;
    }
    if (raw.startsWith('/')) return HOST_URL + raw;
    return raw;
  }, []);

  // Message status icon.
  const MessageStatus = ({ msg }) => {
    if (msg.direction !== 'OUTBOUND') return null;
    const s = msg.status;
    if (s === 'READ') return <span className="text-[10px] text-blue-500 ml-1">✓✓</span>;
    if (s === 'DELIVERED') return <span className="text-[10px] text-slate-500 ml-1">✓✓</span>;
    if (s === 'SENT') return <span className="text-[10px] text-slate-400 ml-1">✓</span>;
    if (s === 'FAILED') return <span className="text-[10px] text-red-500 ml-1">✗</span>;
    return <span className="text-[10px] text-slate-300 ml-1">⏳</span>;
  };

  const filteredChats = chats.filter(chat => {
    if (!searchQuery) return true;
    const name = (chat.contact_name || '').toLowerCase();
    const phone = formatPhoneFromChatId(chat.chat_id);
    return name.includes(searchQuery.toLowerCase()) || phone.includes(searchQuery);
  });

  return (
    <div className="flex h-[calc(100vh-4rem)] bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden relative">
      {/* Toast Notification */}
      {toastMessage && (
        <div className={`absolute top-4 right-4 z-50 p-4 rounded shadow-md flex items-center justify-between min-w-[300px] transition-all duration-300 border-l-4 ${
          toastMessage.type === 'error' ? 'bg-red-50 border-red-500' :
          toastMessage.type === 'success' ? 'bg-green-50 border-green-500' :
          'bg-blue-50 border-blue-500'
        }`}>
          <div className="flex items-center">
            <div className="py-1">
              {toastMessage.type === 'error' ? (
                <svg className="fill-current h-6 w-6 text-red-500 mr-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><path d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-11v4a1 1 0 11-2 0V7a1 1 0 112 0zm-1 8a1.5 1.5 0 110-3 1.5 1.5 0 010 3z"/></svg>
              ) : toastMessage.type === 'success' ? (
                <svg className="fill-current h-6 w-6 text-green-500 mr-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><path d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z"/></svg>
              ) : (
                <svg className="fill-current h-6 w-6 text-blue-500 mr-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><path d="M10 18a8 8 0 100-16 8 8 0 000 16zm1-11v4a1 1 0 11-2 0V7a1 1 0 112 0zm-1 8a1.5 1.5 0 110-3 1.5 1.5 0 010 3z"/></svg>
              )}
            </div>
            <div>
              <p className={`font-semibold ${toastMessage.type === 'error' ? 'text-red-700' : toastMessage.type === 'success' ? 'text-green-700' : 'text-blue-700'}`}>
                {toastMessage.type === 'error' ? 'Error' : toastMessage.type === 'success' ? 'Success' : 'Info'}
              </p>
              <p className={`text-sm ${toastMessage.type === 'error' ? 'text-red-600' : toastMessage.type === 'success' ? 'text-green-600' : 'text-blue-600'}`}>{toastMessage.text}</p>
            </div>
          </div>
          <button onClick={() => setToastMessage(null)} className={`${toastMessage.type === 'error' ? 'text-red-500 hover:text-red-700' : toastMessage.type === 'success' ? 'text-green-500 hover:text-green-700' : 'text-blue-500 hover:text-blue-700'} ml-4`}>
            <svg className="h-4 w-4 fill-current" role="button" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><title>Close</title><path d="M14.348 14.849a1.2 1.2 0 0 1-1.697 0L10 11.819l-2.651 3.029a1.2 1.2 0 1 1-1.697-1.697l2.758-3.15-2.759-3.152a1.2 1.2 0 1 1 1.697-1.697L10 8.183l2.651-3.031a1.2 1.2 0 1 1 1.697 1.697l-2.758 3.152 2.758 3.15a1.2 1.2 0 0 1 0 1.698z"/></svg>
          </button>
        </div>
      )}

      {/* Sidebar */}
      <div className="w-1/3 flex-shrink-0 border-r border-slate-200 flex flex-col bg-slate-50">
        {/* Session Selector Header */}
        <div className="p-3 bg-slate-100 border-b border-slate-200">
          {/* Session Dropdown */}
          <div className="relative mb-2">
            <button
              onClick={() => setShowSessionDropdown(p => !p)}
              className="w-full flex items-center justify-between px-3 py-2 bg-white border border-slate-200 rounded-lg text-sm hover:border-blue-400 transition"
            >
              <div className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full ${
                  selectedSession?.status === 'READY' ? 'bg-green-500' :
                  selectedSession?.status === 'QR_REQUIRED' ? 'bg-yellow-500' :
                  selectedSession?.status === 'STARTING' ? 'bg-blue-400 animate-pulse' :
                  'bg-slate-300'
                }`} />
                <span className="font-medium text-slate-700 truncate">
                  {selectedSession ? selectedSession.session_name : 'No session selected'}
                </span>
                {selectedSession?.phone_number && (
                  <span className="text-xs text-slate-400">({selectedSession.phone_number})</span>
                )}
              </div>
              <ChevronDown className="w-4 h-4 text-slate-400 flex-shrink-0" />
            </button>

            {showSessionDropdown && (
              <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded-lg shadow-lg z-30 max-h-48 overflow-y-auto">
                {sessions.length === 0 && (
                  <div className="px-3 py-4 text-center text-sm text-slate-500">No sessions yet.</div>
                )}
                {sessions.map(s => (
                  <button
                    key={s.id}
                    onClick={() => { setSelectedSession(s); setShowSessionDropdown(false); }}
                    className={`w-full flex items-center gap-2 px-3 py-2 text-sm hover:bg-slate-50 transition text-left ${selectedSession?.id === s.id ? 'bg-blue-50 text-blue-700' : 'text-slate-700'}`}
                  >
                    <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
                      s.status === 'READY' ? 'bg-green-500' :
                      s.status === 'QR_REQUIRED' ? 'bg-yellow-500' :
                      s.status === 'STARTING' ? 'bg-blue-400' :
                      'bg-slate-300'
                    }`} />
                    <span className="font-medium truncate">{s.session_name}</span>
                    <span className="text-xs text-slate-400 ml-auto">{s.status}</span>
                  </button>
                ))}

              </div>
            )}
          </div>


          {/* Search + controls */}
          <div className="flex gap-2 items-center mt-2">
            <div className="relative flex-1">
              <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                placeholder="Search conversations"
                className="w-full bg-white border border-slate-200 rounded-lg pl-9 pr-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
              />
            </div>
            <RefreshCw
              className={`w-4 h-4 cursor-pointer text-slate-500 hover:text-slate-700 ${loading ? 'animate-spin' : ''}`}
              onClick={() => fetchConversations(false, selectedSession?.id)}
            />
          </div>
        </div>

        {/* Conversation list */}
        <div className="flex-1 overflow-y-auto">
          {!selectedSession ? (
            <div className="p-8 text-center text-slate-500">
              <Phone className="w-12 h-12 mx-auto mb-3 text-slate-300" />
              <p className="font-medium">No session selected</p>
              <p className="text-xs mt-1 text-slate-400">Register or select a WhatsApp session above to get started.</p>
            </div>
          ) : loading && chats.length === 0 ? (
            <div className="p-8 text-center text-slate-400">Loading conversations...</div>
          ) : filteredChats.length === 0 ? (
            <div className="p-8 text-center text-slate-400">No conversations found.</div>
          ) : (
            filteredChats.map(chat => (
              <div
                key={chat.id}
                onClick={() => { setSelectedChat(chat); handleMarkRead(); }}
                className={`flex items-center gap-3 p-3 cursor-pointer hover:bg-slate-100 transition ${selectedChat?.id === chat.id ? 'bg-slate-100' : ''}`}
              >
                <div className="w-12 h-12 rounded-full bg-blue-100 flex-shrink-0 flex items-center justify-center text-blue-600 font-bold overflow-hidden relative">
                  <img
                    src={`${API_BASE}/whatsapp/profile-pic/${chat.chat_id}/`}
                    className="w-full h-full object-cover absolute inset-0 z-10"
                    onError={(e) => e.target.style.display = 'none'}
                    alt=""
                  />
                  <span className="relative z-0">{(chat.contact_name || chat.whatsapp_name || '#').charAt(0).toUpperCase()}</span>
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex justify-between items-baseline mb-1">
                    <h3 className="font-semibold text-slate-800 truncate">
                      {chat.contact_name || chat.whatsapp_name || 'Unknown Contact'}
                      {(chat.prospect_phone || formatPhoneFromChatId(chat.chat_id)) && (
                        <span className="font-normal text-slate-500 text-sm ml-1">
                          ({chat.prospect_phone || formatPhoneFromChatId(chat.chat_id)})
                        </span>
                      )}
                    </h3>
                    <span className="text-xs text-slate-500">{formatTime(chat.last_message_at)}</span>
                  </div>
                  <div className="flex justify-between items-baseline">
                    <p className="text-sm text-slate-500 truncate">{chat.last_message_preview || 'No messages yet'}</p>
                    {chat.unread_count > 0 && (
                      <div className="w-5 h-5 bg-green-500 rounded-full flex items-center justify-center text-[10px] font-bold text-white flex-shrink-0">
                        {chat.unread_count}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col bg-[#efeae2] min-w-0">
        {selectedChat ? (
          <>
            {/* Chat Header */}
            <div className="p-4 bg-white border-b border-slate-200 flex justify-between items-center z-10 shadow-sm">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 font-bold overflow-hidden relative">
                  <img
                    src={`${API_BASE}/whatsapp/profile-pic/${selectedChat.chat_id}/`}
                    className="w-full h-full object-cover absolute inset-0 z-10"
                    onError={(e) => e.target.style.display = 'none'}
                    alt=""
                  />
                  <span className="relative z-0">{(selectedChat.contact_name || selectedChat.whatsapp_name || (wahaContact && wahaContact.pushname) || '#').charAt(0).toUpperCase()}</span>
                </div>
                <div>
                  <h2 className="font-semibold text-slate-800">
                    {selectedChat.contact_name || selectedChat.whatsapp_name || (wahaContact && wahaContact.pushname) || "Unknown Contact"}
                  </h2>
                  <p className="text-xs text-slate-500 font-medium">{selectedChat.prospect_name || (wahaContact && wahaContact.company) || 'Unknown Company'}</p>
                </div>
              </div>
              <div className="flex gap-3 text-slate-500 items-center">
                <RefreshCw className="w-4 h-4 cursor-pointer hover:text-slate-700" onClick={handleSyncHistory} title="Sync message history" />
                <Search className="w-5 h-5 cursor-pointer hover:text-slate-700" onClick={() => setShowMsgSearch(!showMsgSearch)} />
                <button
                  onClick={() => setShowProfilePanel(!showProfilePanel)}
                  className="text-slate-500 hover:text-slate-700 font-semibold text-sm bg-slate-100 hover:bg-slate-200 px-3 py-1.5 rounded-full transition-colors"
                >
                  View Profile
                </button>
                <button
                  onClick={handleDeleteChat}
                  className="text-red-400 hover:text-red-600 transition"
                  title="Delete conversation"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Message Search Bar */}
            {showMsgSearch && (
              <div className="px-4 py-2 border-b bg-slate-50 flex items-center gap-2">
                <Search className="w-4 h-4 text-slate-400" />
                <input
                  type="text"
                  autoFocus
                  placeholder="Search messages..."
                  value={msgSearchQuery}
                  onChange={(e) => setMsgSearchQuery(e.target.value)}
                  className="w-full bg-transparent border-none text-sm focus:outline-none"
                />
                <button onClick={() => { setShowMsgSearch(false); setMsgSearchQuery(''); }} className="text-slate-400 hover:text-slate-600 text-sm">Cancel</button>
              </div>
            )}

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {loadingMessages ? (
                <div className="flex justify-center p-4"><RefreshCw className="w-6 h-6 animate-spin text-slate-400" /></div>
              ) : messages.length === 0 ? (
                <div className="flex justify-center p-8 text-slate-500">No messages yet. Send the first message!</div>
              ) : (
                messages.filter(msg => {
                  if (!msgSearchQuery) return true;
                  const text = (msg.full_body || msg.body_preview || '').toLowerCase();
                  return text.includes(msgSearchQuery.toLowerCase());
                }).map(msg => {
                  const isMe = msg.direction === 'OUTBOUND';
                  const proxySrc = buildMediaSrc(msg);
                  const _mime = msg.media_mime_type || '';
                  return (
                    <div key={msg.id} className={`flex ${isMe ? 'justify-end' : 'justify-start'}`}>
                      <div className={`max-w-[70%] rounded-lg p-3 ${isMe ? 'bg-[#d9fdd3] text-slate-800 rounded-tr-none' : 'bg-white text-slate-800 rounded-tl-none'} shadow-sm relative group`}>
                        {msg.has_media && proxySrc && (
                          <div className="mb-2 group/media relative">
                            {_mime.startsWith('image/') ? (
                              <div className="relative inline-block">
                                <img src={proxySrc} alt="Media" className="max-w-full rounded-md" style={{ maxHeight: '300px' }} onError={e => { e.target.style.display='none'; }} />
                                <a href={proxySrc} target="_blank" rel="noopener noreferrer" download className="absolute top-2 right-2 bg-black/50 text-white p-1.5 rounded-full opacity-0 group-hover/media:opacity-100 transition-opacity">
                                  <Paperclip className="w-4 h-4" />
                                </a>
                              </div>
                            ) : _mime.startsWith('video/') ? (
                              <div className="relative inline-block">
                                <video src={proxySrc} controls className="max-w-full rounded-md" style={{ maxHeight: '300px' }} />
                              </div>
                            ) : _mime.startsWith('audio/') ? (
                              <audio src={proxySrc} controls className="max-w-full" />
                            ) : (
                              <a href={proxySrc} target="_blank" rel="noopener noreferrer" download className="text-blue-600 hover:underline flex items-center gap-1 text-sm bg-slate-100 p-2 rounded">
                                <Paperclip className="w-4 h-4" /> Download / View File
                              </a>
                            )}
                          </div>
                        )}
                        {msg.full_body || msg.body_preview ? (
                          <p className="text-sm whitespace-pre-wrap break-words">{msg.full_body || msg.body_preview}</p>
                        ) : msg.has_media ? null : (
                          <p className="text-sm whitespace-pre-wrap break-words italic text-slate-500">(Unsupported Message Type)</p>
                        )}
                        <div className="flex items-center justify-end gap-1 mt-1">
                          <span className="text-[10px] text-slate-500">{formatTime(msg.created_at)}</span>
                          <MessageStatus msg={msg} />
                        </div>
                        {/* Delete button (visible on hover for own messages) */}
                        {isMe && (
                          <button
                            onClick={() => handleDeleteMessage(msg.id)}
                            className="absolute -top-2 -right-2 bg-white border border-slate-200 text-slate-400 hover:text-red-500 hover:border-red-300 rounded-full p-0.5 opacity-0 group-hover:opacity-100 transition-opacity shadow-sm"
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

            {/* Input Area */}
            <div className="relative">
              {/* Emoji Picker */}
              {showEmojiPicker && (
                <div className="absolute bottom-16 left-2 z-50 bg-white border border-slate-200 rounded-xl shadow-xl p-3 w-72">
                  <div className="grid grid-cols-10 gap-1 max-h-40 overflow-y-auto">
                    {EMOJIS.map(emoji => (
                      <button key={emoji} onClick={() => handleEmojiClick(emoji)} className="text-xl hover:bg-slate-100 rounded p-0.5 transition">
                        {emoji}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Attach Preview */}
              {attachPreview && (
                <div className="absolute bottom-16 left-0 right-0 bg-white border-t border-slate-200 p-3 flex items-center gap-3 shadow-md">
                  {attachPreview.mime.startsWith('image/') ? (
                    <img src={attachPreview.url} alt="Preview" className="h-20 w-20 object-cover rounded-lg border" />
                  ) : (
                    <div className="h-20 w-20 bg-slate-100 rounded-lg border flex flex-col items-center justify-center text-xs text-slate-600 p-1 text-center">
                      <Paperclip className="w-6 h-6 mb-1" />
                      <span className="truncate w-full text-center">{attachPreview.file.name}</span>
                    </div>
                  )}
                  <div className="flex-1">
                    <p className="text-xs text-slate-500">{attachPreview.file.name}</p>
                    <p className="text-xs text-slate-400">{(attachPreview.file.size / 1024).toFixed(1)} KB</p>
                    <input
                      type="text"
                      placeholder="Add a caption..."
                      value={message}
                      onChange={e => setMessage(e.target.value)}
                      className="mt-1 w-full border border-slate-200 rounded px-2 py-1 text-sm focus:outline-none"
                    />
                  </div>
                  <div className="flex flex-col gap-2">
                    <button onClick={() => { setAttachPreview(null); setMessage(''); }} className="text-xs text-red-500 hover:text-red-700">Remove</button>
                    <button onClick={handleSendMedia} disabled={isSendingMedia} className="bg-green-500 text-white text-xs px-3 py-1.5 rounded-lg hover:bg-green-600 disabled:opacity-50">
                      {isSendingMedia ? 'Sending...' : 'Send'}
                    </button>
                  </div>
                </div>
              )}

              {/* Hidden file input */}
              <input ref={fileInputRef} type="file" accept="image/*,video/*,audio/*,.pdf,.doc,.docx,.xls,.xlsx" className="hidden" onChange={handleFileSelect} />

              <div className="p-3 bg-slate-100 flex items-center gap-3">
                <button onClick={() => setShowEmojiPicker(p => !p)} className="text-slate-500 hover:text-slate-700 transition">
                  <Smile className="w-6 h-6" />
                </button>
                <button onClick={() => fileInputRef.current?.click()} className="text-slate-500 hover:text-slate-700 transition">
                  <Paperclip className="w-6 h-6" />
                </button>
                <input
                  type="text"
                  placeholder="Type a message"
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  onKeyDown={handleKeyPress}
                  onFocus={() => setShowEmojiPicker(false)}
                  className="flex-1 bg-white border-none rounded-lg px-4 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-green-500 shadow-sm"
                />
                {message.trim() && !attachPreview ? (
                  <div onClick={handleSendMessage} className="w-10 h-10 bg-green-500 rounded-full flex items-center justify-center cursor-pointer hover:bg-green-600 transition shadow-sm">
                    <Send className="w-5 h-5 text-white ml-1" />
                  </div>
                ) : null}
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-center p-8 text-slate-500">
            <div className="w-64 h-64 mb-6 opacity-30 rounded-full border-4 border-dashed border-slate-400 flex items-center justify-center bg-slate-100">
              <Phone className="w-24 h-24 text-slate-500" />
            </div>
            <h2 className="text-2xl font-light text-slate-700 mb-2">WhatsApp Web</h2>
            <p className="text-sm max-w-md">
              {selectedSession
                ? 'Select a conversation to start messaging.'
                : 'Register or select a WhatsApp session from the sidebar to get started.'}
            </p>
          </div>
        )}
      </div>

      {/* Contact Profile Panel */}
      {selectedChat && showProfilePanel && (
        <div className="w-80 border-l border-slate-200 bg-white flex flex-col flex-shrink-0 overflow-y-auto">
          <div className="p-4 border-b border-slate-200 flex justify-between items-center bg-slate-50">
            <h2 className="font-semibold text-slate-800">{selectedChat.contact_name || selectedChat.whatsapp_name || (wahaContact && wahaContact.pushname) || "Unknown Contact"}</h2>
            <button onClick={() => setShowProfilePanel(false)} className="text-slate-400 hover:text-slate-600 text-xl font-bold">&times;</button>
          </div>

          <div className="p-6 flex flex-col items-center border-b border-slate-100">
            <div className="w-32 h-32 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center font-bold text-4xl mb-4 overflow-hidden relative shadow-sm">
              <img src={`${API_BASE}/whatsapp/profile-pic/${selectedChat.chat_id}/`} className="w-full h-full object-cover relative z-10" onError={(e) => e.target.style.display = 'none'} alt="" />
              <span className="absolute inset-0 flex items-center justify-center">{(selectedChat.contact_name || selectedChat.whatsapp_name || (wahaContact && wahaContact.pushname) || '#').charAt(0).toUpperCase()}</span>
            </div>
            <h3 className="text-xl font-bold text-slate-800 text-center">{selectedChat.contact_name || selectedChat.whatsapp_name || (wahaContact && wahaContact.pushname) || "Unknown Contact"}</h3>
            <p className="text-slate-500 text-sm mt-1 font-mono">
              {selectedChat.prospect_phone || formatPhoneFromChatId(selectedChat.chat_id) || (wahaContact && wahaContact.phoneNumber ? formatPhoneFromChatId(wahaContact.phoneNumber) : 'Unknown Number')}
            </p>
          </div>

          <div className="p-4 space-y-4">
            <div>
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Session</label>
              <p className="text-slate-800 mt-1 text-sm">{selectedSession?.session_name || '–'}</p>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Company</label>
              <p className="text-slate-800 mt-1">{selectedChat.prospect_name || (wahaContact && wahaContact.company) || 'Not linked to CRM'}</p>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Chat ID</label>
              <p className="text-slate-800 mt-1 text-sm break-all">{selectedChat.chat_id}</p>
            </div>
            <div>
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Matched Lead</label>
              <p className="mt-1">
                {selectedChat.is_matched ? (
                  <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">Yes (CRM Synced)</span>
                ) : (
                  <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-800">Unmatched</span>
                )}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
