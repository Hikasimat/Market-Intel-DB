import React, { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { toast } from 'react-toastify';
import { 
  Plus, 
  Trash2, 
  RefreshCw, 
  AlertCircle, 
  Send,
  X,
  Repeat2,
  Heart,
  MessageSquare,
  BarChart2,
  HelpCircle,
  ExternalLink,
  ShieldCheck,
  CheckCircle2
} from 'lucide-react';
import api from '../../services/api';
import { TwitterXIcon } from '../../components/common/SocialIcons';

const TwitterPage = () => {
  const [loading, setLoading] = useState(true);
  const [statusData, setStatusData] = useState(null);
  const [tweetsData, setTweetsData] = useState({ database_tweets: [], live_tweets: [] });
  const [isTweetModalOpen, setIsTweetModalOpen] = useState(false);
  const [tweeting, setTweeting] = useState(false);
  const [tweetText, setTweetText] = useState('');
  const [publishLive, setPublishLive] = useState(true);
  const [disconnecting, setDisconnecting] = useState(false);

  const location = useLocation();
  const oauthProcessedRef = useRef(false);

  const fetchStatus = async () => {
    try {
      const res = await api.get('/digital-marketing/twitter/status/');
      setStatusData(res.data);
    } catch (err) {
      toast.error('Failed to load Twitter/X status.');
    }
  };

  const fetchTweets = async () => {
    try {
      const res = await api.get('/digital-marketing/twitter/tweets/');
      setTweetsData(res.data);
    } catch (err) {
      console.warn('Failed to fetch tweets.', err);
    }
  };

  const loadData = async () => {
    setLoading(true);
    await Promise.all([fetchStatus(), fetchTweets()]);
    setLoading(false);
  };

  useEffect(() => {
    loadData();
  }, []);

  // Handle incoming OAuth 2.0 PKCE callback query params
  useEffect(() => {
    const params = new URLSearchParams(location.search);
    const code = params.get('code');
    const state = params.get('state');

    if (code && state && !oauthProcessedRef.current) {
      oauthProcessedRef.current = true;
      window.history.replaceState({}, document.title, window.location.pathname);
      const processOAuth = async () => {
        setLoading(true);
        try {
          const res = await api.post('/digital-marketing/twitter/callback/', { code, state });
          toast.success(res.data.detail || 'Twitter/X account connected successfully.');
          loadData();
        } catch (err) {
          toast.error(err.response?.data?.error || 'Failed to complete Twitter/X authorization.');
          loadData();
        }
      };
      processOAuth();
    }
  }, [location.search]);

  const handleConnect = async () => {
    try {
      const redirectUri = `${window.location.origin}/digital-marketing/twitter`;
      const res = await api.get('/digital-marketing/twitter/auth-url/', {
        params: { redirect_uri: redirectUri }
      });
      if (res.data?.url) {
        window.location.href = res.data.url;
      }
    } catch (err) {
      const msg = err.response?.data?.error || 'Failed to start Twitter authorization. Please check client credentials.';
      toast.error(msg);
    }
  };

  const handleDisconnect = async () => {
    if (!window.confirm('Are you sure you want to disconnect this Twitter/X account?')) return;
    setDisconnecting(true);
    try {
      await api.post('/digital-marketing/twitter/disconnect/');
      toast.success('Twitter/X account disconnected.');
      loadData();
    } catch (err) {
      toast.error('Failed to disconnect Twitter/X account.');
    } finally {
      setDisconnecting(false);
    }
  };

  const handlePostTweet = async (e) => {
    e.preventDefault();
    if (!tweetText.trim()) {
      toast.error('Tweet text cannot be empty.');
      return;
    }
    if (tweetText.length > 280) {
      toast.error('Tweet exceeds maximum 280 characters.');
      return;
    }

    setTweeting(true);
    try {
      const res = await api.post('/digital-marketing/twitter/tweets/', { 
        text: tweetText,
        publish_live: publishLive 
      });
      toast.success(res.data.detail || 'Tweet saved successfully!');
      setIsTweetModalOpen(false);
      setTweetText('');
      fetchTweets();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to post tweet.');
    } finally {
      setTweeting(false);
    }
  };

  const isConnected = statusData?.is_connected;
  const isConfigured = statusData?.is_configured;
  const account = statusData?.account;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-slate-900 text-white flex items-center justify-center shadow-md shadow-slate-900/20">
            <TwitterXIcon className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-2">
              Twitter / X Integration
            </h1>
            <p className="text-sm text-slate-500">
              Official X API v2 integration with OAuth 2.0 PKCE authentication.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {isConnected && (
            <button
              onClick={() => setIsTweetModalOpen(true)}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold text-white bg-slate-900 hover:bg-slate-800 shadow-sm transition"
            >
              <Plus className="w-4 h-4" />
              Post Tweet
            </button>
          )}

          <button
            onClick={loadData}
            disabled={loading}
            className="inline-flex items-center gap-2 px-4 py-2 border border-slate-200 rounded-xl text-xs font-bold text-slate-700 bg-white hover:bg-slate-50 transition shadow-sm disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Configuration Warning if Twitter credentials are missing */}
      {!isConfigured && statusData?.config_error && (
        <div className="p-5 bg-amber-50 border border-amber-200 rounded-2xl text-amber-900 shadow-sm space-y-3">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="font-bold text-sm text-amber-900">X Developer Credentials Required</h4>
              <p className="text-xs text-amber-800 mt-1">
                {statusData.config_error}
              </p>
            </div>
          </div>
          <div className="text-xs bg-white/60 p-3 rounded-xl border border-amber-200 space-y-1">
            <div className="font-bold text-amber-900">Required Environment Variables:</div>
            <code className="block font-mono text-[11px] text-slate-700">TWITTER_CLIENT_ID=&lt;your-oauth2-client-id&gt;</code>
            <code className="block font-mono text-[11px] text-slate-700">TWITTER_CLIENT_SECRET=&lt;your-oauth2-client-secret&gt;</code>
            <code className="block font-mono text-[11px] text-slate-700">TWITTER_REDIRECT_URI=http://localhost:5173/digital-marketing/twitter</code>
          </div>
        </div>
      )}

      {/* Account Status Card */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="flex items-start gap-4">
            {isConnected && account?.profile_picture_url ? (
              <img
                src={account.profile_picture_url}
                alt={account.account_username}
                className="w-16 h-16 rounded-2xl object-cover border border-slate-200 shadow-sm"
              />
            ) : (
              <div className="w-16 h-16 rounded-2xl bg-slate-100 text-slate-800 flex items-center justify-center border border-slate-200">
                <TwitterXIcon className="w-8 h-8" />
              </div>
            )}

            <div>
              <div className="flex items-center gap-2.5">
                <h3 className="text-lg font-bold text-slate-900">
                  {isConnected ? (account?.account_name || `@${account?.account_username}`) : 'No X Account Connected'}
                </h3>
                <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold ${
                  isConnected ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'
                }`}>
                  {isConnected ? 'Connected & Verified' : 'Disconnected'}
                </span>
              </div>

              {isConnected ? (
                <div className="mt-2 text-xs text-slate-500 space-y-0.5">
                  <div>Handle: <strong className="text-slate-900">@{account?.account_username}</strong></div>
                  <div>Account ID: <code className="text-slate-600 font-mono">{account?.account_id}</code></div>
                  {account?.metadata?.description && (
                    <p className="text-slate-600 mt-1 max-w-lg italic">"{account.metadata.description}"</p>
                  )}
                </div>
              ) : (
                <p className="text-xs text-slate-500 mt-1 max-w-xl">
                  Connect via official X API v2 OAuth 2.0 PKCE to publish tweets, monitor public engagement metrics, and track impressions.
                </p>
              )}
            </div>
          </div>

          <div className="flex items-center gap-3 self-end md:self-center">
            {isConnected ? (
              <button
                onClick={handleDisconnect}
                disabled={disconnecting}
                className="inline-flex items-center gap-2 px-4 py-2 border border-red-200 text-red-600 hover:bg-red-50 rounded-xl text-xs font-bold transition shadow-sm disabled:opacity-50"
              >
                <Trash2 className="w-4 h-4" />
                {disconnecting ? 'Disconnecting...' : 'Disconnect Account'}
              </button>
            ) : (
              <button
                onClick={handleConnect}
                disabled={!isConfigured}
                className="inline-flex items-center gap-2 px-5 py-2.5 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-bold transition shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <TwitterXIcon className="w-4 h-4" />
                Connect X Account (OAuth 2.0)
              </button>
            )}
          </div>
        </div>

        {/* Public Metrics Strip */}
        {isConnected && (
          <div className="mt-6 pt-6 border-t border-slate-100 grid grid-cols-3 gap-4 text-center">
            <div className="p-3 bg-slate-50 rounded-xl">
              <div className="text-xs text-slate-400 font-medium">Followers</div>
              <div className="text-xl font-bold text-slate-900 mt-0.5">
                {(account?.metadata?.followers_count || 0).toLocaleString()}
              </div>
            </div>
            <div className="p-3 bg-slate-50 rounded-xl">
              <div className="text-xs text-slate-400 font-medium">Following</div>
              <div className="text-xl font-bold text-slate-900 mt-0.5">
                {(account?.metadata?.following_count || 0).toLocaleString()}
              </div>
            </div>
            <div className="p-3 bg-slate-50 rounded-xl">
              <div className="text-xs text-slate-400 font-medium">Lifetime Tweets</div>
              <div className="text-xl font-bold text-slate-900 mt-0.5">
                {(account?.metadata?.tweet_count || 0).toLocaleString()}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Official API Guidelines & Access Tier Notes */}
      <div className="bg-slate-100/60 rounded-2xl border border-slate-200 p-5 text-xs text-slate-600 space-y-2">
        <div className="flex items-center gap-2 font-bold text-slate-800 text-sm">
          <HelpCircle className="w-4 h-4 text-slate-900" />
          Official X API v2 Tier & Rate Limit Architecture
        </div>
        <ul className="list-disc list-inside space-y-1 text-slate-500 pl-1">
          <li><strong>Official Endpoints:</strong> Uses official <code>POST /2/tweets</code> and <code>GET /2/users/me</code>. Scraping or unofficial automation is strictly avoided.</li>
          <li><strong>Access Tiers:</strong> Free tier permits up to 1,500 Tweets/month. Basic tier ($100/mo) permits 50,000 Tweets/month. Rate limit responses (HTTP 429) are gracefully handled.</li>
          <li><strong>Security:</strong> OAuth 2.0 PKCE state tokens protect against CSRF. Encrypted tokens are managed server-side and never exposed to the browser.</li>
        </ul>
      </div>

      {/* Tweets & Performance Insights */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <TwitterXIcon className="w-5 h-5 text-slate-900" />
            <h3 className="font-bold text-slate-900 text-base">Recent Tweets & Public Metrics</h3>
          </div>
          <span className="text-xs text-slate-400">
            {tweetsData.live_tweets?.length > 0 ? 'Live from X API v2' : 'Published records'}
          </span>
        </div>

        {tweetsData.database_tweets?.length === 0 && tweetsData.live_tweets?.length === 0 ? (
          <div className="py-12 text-center text-slate-400 text-sm">
            <TwitterXIcon className="w-12 h-12 text-slate-200 mx-auto mb-3" />
            No tweets published yet. Click "Post Tweet" to post official content.
          </div>
        ) : (
          <div className="space-y-4">
            {tweetsData.database_tweets.map((tweet) => (
              <div key={tweet.id} className="p-4 border border-slate-200 rounded-xl bg-white hover:border-slate-300 transition flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="space-y-1 max-w-xl">
                  <p className="text-sm text-slate-800 whitespace-pre-wrap">{tweet.caption}</p>
                  <div className="text-[11px] text-slate-400 flex items-center gap-2">
                    <span>Published: {tweet.published_at ? new Date(tweet.published_at).toLocaleString() : 'Just now'}</span>
                    {tweet.external_post_id && (
                      <span className="font-mono text-slate-400">ID: {tweet.external_post_id}</span>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-4 text-xs font-bold text-slate-600 bg-slate-50 px-4 py-2 rounded-xl self-start sm:self-auto">
                  <span className="flex items-center gap-1.5" title="Likes">
                    <Heart className="w-3.5 h-3.5 text-rose-500" />
                    {tweet.metrics?.like_count || 0}
                  </span>
                  <span className="flex items-center gap-1.5" title="Retweets">
                    <Repeat2 className="w-3.5 h-3.5 text-emerald-600" />
                    {tweet.metrics?.retweet_count || 0}
                  </span>
                  <span className="flex items-center gap-1.5" title="Replies">
                    <MessageSquare className="w-3.5 h-3.5 text-blue-500" />
                    {tweet.metrics?.reply_count || 0}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Post Tweet Modal */}
      {isTweetModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg overflow-hidden border border-slate-200 animate-in fade-in zoom-in-95 duration-150">
            <div className="p-5 border-b border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <TwitterXIcon className="w-5 h-5 text-slate-900" />
                <h3 className="font-bold text-slate-900">Post Tweet to X</h3>
              </div>
              <button onClick={() => setIsTweetModalOpen(false)} className="text-slate-400 hover:text-slate-600 p-1">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handlePostTweet} className="p-5 space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Tweet Content <span className="text-rose-500">*</span>
                </label>
                <textarea
                  rows="4"
                  maxLength="280"
                  required
                  placeholder="What is happening?! (Max 280 characters)"
                  value={tweetText}
                  onChange={(e) => setTweetText(e.target.value)}
                  className="w-full text-xs px-3.5 py-2.5 rounded-xl border border-slate-200 focus:outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-100"
                />
                <div className="flex items-center justify-between text-[11px] text-slate-400 mt-1">
                  <span>Standard 280 character limit</span>
                  <span className={`font-bold ${280 - tweetText.length < 20 ? 'text-rose-500' : 'text-slate-500'}`}>
                    {280 - tweetText.length} left
                  </span>
                </div>
              </div>

              <div className="flex items-start gap-2.5 p-3 rounded-xl bg-slate-50 border border-slate-200">
                <input
                  type="checkbox"
                  id="publishLiveTwitter"
                  checked={publishLive}
                  onChange={(e) => setPublishLive(e.target.checked)}
                  className="mt-0.5 w-4 h-4 text-slate-900 rounded border-slate-300 focus:ring-slate-900 cursor-pointer"
                />
                <label htmlFor="publishLiveTwitter" className="text-xs text-slate-700 cursor-pointer">
                  <span className="font-bold text-slate-900">
                    Publish live to connected X account {account?.account_username ? `(@${account.account_username})` : ''}
                  </span>
                  <p className="text-[11px] text-slate-500 mt-0.5">
                    Requires API credits on X Developer Portal. Uncheck to save directly to your workspace feed.
                  </p>
                </label>
              </div>

              <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setIsTweetModalOpen(false)}
                  className="px-4 py-2 rounded-xl text-xs font-bold text-slate-600 hover:bg-slate-100 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={tweeting || !tweetText.trim()}
                  className="inline-flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-bold text-white bg-slate-900 hover:bg-slate-800 transition shadow-sm disabled:opacity-50"
                >
                  <Send className="w-3.5 h-3.5" />
                  {tweeting ? 'Posting...' : 'Post Tweet'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default TwitterPage;
