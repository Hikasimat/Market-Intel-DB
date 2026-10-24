import React, { useState, useEffect, useRef } from 'react';
import { toast } from 'react-toastify';
import {
  MessageSquare,
  Search,
  RefreshCw,
  Send,
  Check,
  CheckCheck,
  Clock,
  AlertCircle,
  ExternalLink,
  ChevronRight,
  ShieldCheck,
  Image as ImageIcon,
  User,
  Inbox,
  Filter,
} from 'lucide-react';
import api from '../../services/api';
import { InstagramIcon, FacebookIcon } from '../../components/common/SocialIcons';

const SocialMessagesPage = () => {
  const [conversations, setConversations] = useState([]);
  const [selectedThread, setSelectedThread] = useState(null);
  const [messages, setMessages] = useState([]);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [sending, setSending] = useState(false);
  const [replyText, setReplyText] = useState('');
  const [platformFilter, setPlatformFilter] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [connections, setConnections] = useState({ instagram: false, facebook: false });

  const messagesEndRef = useRef(null);

  const fetchConversations = async (silent = false) => {
    if (!silent) setLoadingList(true);
    try {
      const params = {};
      if (platformFilter !== 'ALL') params.platform = platformFilter;
      if (searchQuery.trim()) params.search = searchQuery.trim();

      const res = await api.get('/digital-marketing/conversations/', { params });
      setConversations(res.data.conversations || []);
      setConnections(res.data.connections || { instagram: false, facebook: false });

      // If the currently selected thread is still in the list, keep it updated
      if (selectedThread) {
        const updated = (res.data.conversations || []).find((c) => c.id === selectedThread.id);
        if (updated) setSelectedThread(updated);
      }
    } catch (err) {
      if (!silent) toast.error('Failed to load conversations.');
    } finally {
      if (!silent) setLoadingList(false);
    }
  };

  const prevMsgCountRef = useRef(0);

  const fetchMessages = async (threadId, markRead = true, isBackground = false) => {
    if (!isBackground) setLoadingMessages(true);
    try {
      const res = await api.get(`/digital-marketing/conversations/${threadId}/messages/`);
      const newMsgs = res.data.messages || [];

      setMessages((prev) => {
        if (
          prev.length === newMsgs.length &&
          prev.length > 0 &&
          prev[prev.length - 1].id === newMsgs[newMsgs.length - 1].id
        ) {
          return prev;
        }
        return newMsgs;
      });

      if (res.data.thread) setSelectedThread(res.data.thread);
      if (markRead) {
        // update local unread counter on the thread
        setConversations((prev) =>
          prev.map((c) => (c.id === threadId ? { ...c, unread_count: 0 } : c))
        );
      }
    } catch (err) {
      if (!isBackground) toast.error('Failed to load thread messages.');
    } finally {
      if (!isBackground) setLoadingMessages(false);
    }
  };

  const handleSync = async () => {
    setSyncing(true);
    try {
      const res = await api.post('/digital-marketing/conversations/sync/');
      toast.success(res.data.detail || 'Synced conversations successfully.');
      await fetchConversations(true);
      if (selectedThread) {
        await fetchMessages(selectedThread.id, false, false);
      }
    } catch (err) {
      const msg = err.response?.data?.detail || err.response?.data?.error || 'Failed to sync conversations with Meta.';
      toast.error(msg);
    } finally {
      setSyncing(false);
    }
  };

  const handleSendMessage = async (e) => {
    e?.preventDefault();
    if (!replyText.trim() || !selectedThread) return;

    setSending(true);
    try {
      const res = await api.post(`/digital-marketing/conversations/${selectedThread.id}/messages/`, {
        text: replyText.trim(),
      });
      setReplyText('');
      setMessages((prev) => [...prev, res.data.message]);
      fetchConversations(true);
    } catch (err) {
      const msg = err.response?.data?.error || 'Failed to send message.';
      toast.error(msg);
    } finally {
      setSending(false);
    }
  };

  useEffect(() => {
    fetchConversations();
  }, [platformFilter, searchQuery]);

  useEffect(() => {
    if (selectedThread) {
      prevMsgCountRef.current = 0;
      fetchMessages(selectedThread.id, true, false);
    }
  }, [selectedThread?.id]);

  useEffect(() => {
    if (messages.length > prevMsgCountRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
    prevMsgCountRef.current = messages.length;
  }, [messages.length]);

  const selectedThreadRef = useRef(selectedThread);
  useEffect(() => {
    selectedThreadRef.current = selectedThread;
  }, [selectedThread]);

  const isSyncingMetaRef = useRef(false);

  // 24/7 Live Active Inbox: Silently polls Meta Graph API directly in the background
  const silentSyncWithMeta = async () => {
    if (isSyncingMetaRef.current) return;
    isSyncingMetaRef.current = true;
    try {
      await api.post('/digital-marketing/conversations/sync/');
      await fetchConversations(true);
      if (selectedThreadRef.current) {
        await fetchMessages(selectedThreadRef.current.id, false, true);
      }
    } catch (e) {
      // Completely silent for background polling
    } finally {
      isSyncingMetaRef.current = false;
    }
  };

  // Run initial sync on page load and continuously sync every 6 seconds
  useEffect(() => {
    silentSyncWithMeta();
    const interval = setInterval(() => {
      silentSyncWithMeta();
    }, 6000);
    return () => clearInterval(interval);
  }, []);

  const formatTime = (isoString) => {
    if (!isoString) return '';
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    const diffHours = Math.floor(diffMins / 60);

    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

  const totalUnread = conversations.reduce((acc, c) => acc + (c.unread_count || 0), 0);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-blue-600 to-indigo-600 text-white flex items-center justify-center shadow-md shadow-blue-500/20">
            <MessageSquare className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-black text-slate-900 tracking-tight">
                Social Messaging
              </h1>
              {totalUnread > 0 && (
                <span className="px-2.5 py-0.5 rounded-full text-xs font-bold bg-rose-500 text-white animate-pulse">
                  {totalUnread} new
                </span>
              )}
            </div>
            <p className="text-sm text-slate-500">
              Unified inbox for Instagram Direct Messages & Facebook Messenger.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden sm:inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-emerald-50 text-emerald-700 border border-emerald-200 text-xs font-semibold">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
            24/7 Live Inbox Active
          </div>
          <button
            onClick={handleSync}
            disabled={syncing}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-slate-200 bg-white text-xs font-bold text-slate-700 hover:bg-slate-50 hover:border-slate-300 transition shadow-sm disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${syncing ? 'animate-spin text-blue-600' : ''}`} />
            {syncing ? 'Syncing...' : 'Sync Messages'}
          </button>
        </div>
      </div>

      {/* Main Two-Panel Chat Container */}
      <div className="bg-white rounded-3xl border border-slate-200 shadow-sm overflow-hidden h-[720px] flex flex-col md:flex-row">
        {/* Left Column: Conversations List */}
        <div className="w-full md:w-80 lg:w-96 border-r border-slate-200 flex flex-col shrink-0 bg-slate-50/50">
          {/* Search & Platform Filter */}
          <div className="p-4 border-b border-slate-200 space-y-3 bg-white">
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
              <input
                type="text"
                placeholder="Search conversations..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-2 text-xs rounded-xl border border-slate-200 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
              />
            </div>

            {/* Platform Filter Tabs */}
            <div className="flex items-center gap-1.5 p-1 bg-slate-100 rounded-xl">
              <button
                onClick={() => setPlatformFilter('ALL')}
                className={`flex-1 py-1.5 text-xs font-bold rounded-lg transition ${
                  platformFilter === 'ALL'
                    ? 'bg-white text-slate-900 shadow-sm'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                All
              </button>
              <button
                onClick={() => setPlatformFilter('INSTAGRAM')}
                className={`flex-1 py-1.5 text-xs font-bold rounded-lg flex items-center justify-center gap-1.5 transition ${
                  platformFilter === 'INSTAGRAM'
                    ? 'bg-white text-slate-900 shadow-sm'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                <InstagramIcon className="w-3.5 h-3.5" />
                Instagram
              </button>
              <button
                onClick={() => setPlatformFilter('FACEBOOK')}
                className={`flex-1 py-1.5 text-xs font-bold rounded-lg flex items-center justify-center gap-1.5 transition ${
                  platformFilter === 'FACEBOOK'
                    ? 'bg-white text-slate-900 shadow-sm'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                <FacebookIcon className="w-3.5 h-3.5 text-blue-600" />
                Facebook
              </button>
            </div>
          </div>

          {/* Conversations Scrollable List */}
          <div className="flex-1 overflow-y-auto divide-y divide-slate-100">
            {loadingList ? (
              <div className="p-8 text-center text-xs text-slate-400">Loading conversations...</div>
            ) : conversations.length === 0 ? (
              <div className="p-8 text-center space-y-3">
                <div className="w-12 h-12 rounded-2xl bg-slate-100 text-slate-400 flex items-center justify-center mx-auto">
                  <Inbox className="w-6 h-6" />
                </div>
                <div>
                  <p className="text-xs font-bold text-slate-700">No conversations yet</p>
                  <p className="text-[11px] text-slate-400 mt-1 max-w-[200px] mx-auto">
                    Click "Sync Messages" above or connect your Instagram / Facebook Page.
                  </p>
                </div>
              </div>
            ) : (
              conversations.map((thread) => {
                const isSelected = selectedThread?.id === thread.id;
                const isInstagram = thread.platform === 'INSTAGRAM';

                return (
                  <button
                    key={thread.id}
                    onClick={() => setSelectedThread(thread)}
                    className={`w-full text-left p-4 transition flex items-start gap-3 relative ${
                      isSelected ? 'bg-blue-50/70 border-r-2 border-blue-600' : 'hover:bg-white'
                    }`}
                  >
                    {/* Contact Avatar + Platform Badge */}
                    <div className="relative shrink-0">
                      {thread.participant_avatar_url ? (
                        <img
                          src={thread.participant_avatar_url}
                          alt={thread.participant_name}
                          className="w-11 h-11 rounded-full object-cover border border-slate-200"
                        />
                      ) : (
                        <div
                          className={`w-11 h-11 rounded-full flex items-center justify-center text-white font-bold text-sm ${
                            isInstagram
                              ? 'bg-gradient-to-tr from-amber-500 via-rose-500 to-purple-600'
                              : 'bg-blue-600'
                          }`}
                        >
                          {thread.participant_name.charAt(0).toUpperCase()}
                        </div>
                      )}
                      <div
                        className={`absolute -bottom-1 -right-1 w-5 h-5 rounded-full flex items-center justify-center shadow-sm text-white ${
                          isInstagram
                            ? 'bg-gradient-to-tr from-amber-500 via-rose-500 to-purple-600'
                            : 'bg-blue-600'
                        }`}
                      >
                        {isInstagram ? (
                          <InstagramIcon className="w-3 h-3" />
                        ) : (
                          <FacebookIcon className="w-3 h-3" />
                        )}
                      </div>
                    </div>

                    {/* Content preview */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-1 mb-1">
                        <span className="font-bold text-xs text-slate-900 truncate">
                          {thread.participant_name}
                        </span>
                        <span className="text-[10px] text-slate-400 shrink-0">
                          {formatTime(thread.last_message_at)}
                        </span>
                      </div>

                      <p
                        className={`text-xs truncate ${
                          thread.unread_count > 0 ? 'font-bold text-slate-900' : 'text-slate-500'
                        }`}
                      >
                        {thread.last_message_text || 'Active conversation'}
                      </p>

                      <div className="flex items-center justify-between mt-1">
                        <span className="text-[10px] text-slate-400">
                          via {thread.account_username || thread.account_name}
                        </span>
                        {thread.unread_count > 0 && (
                          <span className="w-5 h-5 rounded-full bg-blue-600 text-white text-[10px] font-bold flex items-center justify-center">
                            {thread.unread_count}
                          </span>
                        )}
                      </div>
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* Right Column: Chat Thread & Reply Composer */}
        <div className="flex-1 flex flex-col bg-white">
          {selectedThread ? (
            <>
              {/* Active Thread Header */}
              <div className="p-4 border-b border-slate-200 flex items-center justify-between bg-white shrink-0">
                <div className="flex items-center gap-3">
                  <div className="relative">
                    {selectedThread.participant_avatar_url ? (
                      <img
                        src={selectedThread.participant_avatar_url}
                        alt={selectedThread.participant_name}
                        className="w-10 h-10 rounded-full object-cover"
                      />
                    ) : (
                      <div className="w-10 h-10 rounded-full bg-slate-900 text-white font-bold flex items-center justify-center text-sm">
                        {selectedThread.participant_name.charAt(0).toUpperCase()}
                      </div>
                    )}
                    <span
                      className={`absolute -bottom-1 -right-1 w-4 h-4 rounded-full flex items-center justify-center text-white ${
                        selectedThread.platform === 'INSTAGRAM' ? 'bg-rose-500' : 'bg-blue-600'
                      }`}
                    >
                      {selectedThread.platform === 'INSTAGRAM' ? (
                        <InstagramIcon className="w-2.5 h-2.5" />
                      ) : (
                        <FacebookIcon className="w-2.5 h-2.5" />
                      )}
                    </span>
                  </div>

                  <div>
                    <h3 className="font-bold text-sm text-slate-900">
                      {selectedThread.participant_name}
                    </h3>
                    <p className="text-[11px] text-slate-500">
                      {selectedThread.platform === 'INSTAGRAM' ? 'Instagram Direct' : 'Facebook Messenger'} • Connected to {selectedThread.account_name}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                    <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                    Webhook Active • Ready to Reply
                  </span>
                </div>
              </div>

              {/* Messages Body */}
              <div className="flex-1 overflow-y-auto p-6 space-y-4 bg-slate-50/30">
                {loadingMessages ? (
                  <div className="text-center py-10 text-xs text-slate-400">Loading messages...</div>
                ) : messages.length === 0 ? (
                  <div className="text-center py-16 space-y-2">
                    <MessageSquare className="w-8 h-8 text-slate-300 mx-auto" />
                    <p className="text-xs font-bold text-slate-600">No messages in this thread yet</p>
                    <p className="text-[11px] text-slate-400">
                      Send a message below to start the conversation.
                    </p>
                  </div>
                ) : (
                  messages.map((msg) => {
                    const isBusiness = msg.sender_type === 'BUSINESS';

                    return (
                      <div
                        key={msg.id}
                        className={`flex flex-col ${isBusiness ? 'items-end' : 'items-start'}`}
                      >
                        <div
                          className={`max-w-[70%] rounded-2xl px-4 py-2.5 shadow-sm text-xs space-y-1.5 ${
                            isBusiness
                              ? 'bg-blue-600 text-white rounded-br-sm'
                              : 'bg-white text-slate-800 border border-slate-200/80 rounded-bl-sm'
                          }`}
                        >
                          {msg.media_url && (
                            <img
                              src={msg.media_url}
                              alt="Attachment"
                              className="rounded-xl max-h-60 object-cover w-full"
                            />
                          )}
                          {msg.text && <p className="leading-relaxed whitespace-pre-wrap">{msg.text}</p>}
                        </div>

                        <div className="flex items-center gap-1 mt-1 text-[10px] text-slate-400 px-1">
                          <span>{new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                          {isBusiness && (
                            <CheckCheck className="w-3 h-3 text-blue-500" />
                          )}
                        </div>
                      </div>
                    );
                  })
                )}
                <div ref={messagesEndRef} />
              </div>

              {/* Reply Input Composer */}
              <div className="p-4 border-t border-slate-200 bg-white">
                <form onSubmit={handleSendMessage} className="space-y-2">
                  <div className="relative">
                    <textarea
                      rows="3"
                      value={replyText}
                      onChange={(e) => setReplyText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault();
                          handleSendMessage();
                        }
                      }}
                      placeholder={`Reply to ${selectedThread.participant_name} on ${
                        selectedThread.platform === 'INSTAGRAM' ? 'Instagram' : 'Facebook'
                      }... (Press Enter to send)`}
                      className="w-full text-xs p-3 pr-20 rounded-xl border border-slate-200 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 resize-none"
                    />
                    <button
                      type="submit"
                      disabled={sending || !replyText.trim()}
                      className="absolute right-2.5 bottom-3.5 inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-bold text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 transition shadow-sm"
                    >
                      <Send className="w-3 h-3" />
                      {sending ? 'Sending...' : 'Send'}
                    </button>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-400 px-1">
                    <span>Press Enter to send, Shift + Enter for new line</span>
                    <span>100% Free via official Meta Send API</span>
                  </div>
                </form>
              </div>
            </>
          ) : (
            /* Empty selection state */
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center space-y-4">
              <div className="w-16 h-16 rounded-3xl bg-blue-50 text-blue-600 flex items-center justify-center shadow-inner">
                <MessageSquare className="w-8 h-8" />
              </div>
              <div className="max-w-sm">
                <h3 className="font-bold text-slate-900 text-sm">Select a Conversation</h3>
                <p className="text-xs text-slate-500 mt-1">
                  Choose an Instagram Direct or Facebook Messenger thread on the left to read history and send real-time replies.
                </p>
              </div>
              <div className="flex items-center gap-2 text-xs font-semibold text-slate-500 bg-slate-50 px-4 py-2 rounded-xl border border-slate-200/60">
                <ShieldCheck className="w-4 h-4 text-emerald-600" />
                <span>Encrypted credentials & Official Meta Graph API</span>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default SocialMessagesPage;
