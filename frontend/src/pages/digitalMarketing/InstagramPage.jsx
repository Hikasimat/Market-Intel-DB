import React, { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { toast } from 'react-toastify';
import { 
  ExternalLink, 
  Plus, 
  Trash2, 
  RefreshCw, 
  CheckCircle2, 
  AlertCircle, 
  Info, 
  Image as ImageIcon,
  Heart,
  MessageCircle,
  Eye,
  X,
  Send,
  HelpCircle
} from 'lucide-react';
import api from '../../services/api';
import { InstagramIcon, FacebookIcon } from '../../components/common/SocialIcons';

const InstagramPage = () => {
  const [loading, setLoading] = useState(true);
  const [statusData, setStatusData] = useState(null);
  const [fbStatus, setFbStatus] = useState(null);
  const [postsData, setPostsData] = useState({ database_posts: [], live_posts: [] });
  const [isPublishModalOpen, setIsPublishModalOpen] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [formData, setFormData] = useState({ image_url: '', caption: '', publish_live: true });
  const [targetPlatforms, setTargetPlatforms] = useState({ instagram: true, facebook: true });
  const [selectedFile, setSelectedFile] = useState(null);
  const [filePreview, setFilePreview] = useState('');
  const [uploadMode, setUploadMode] = useState('file'); // 'file' or 'url'
  const [deletingId, setDeletingId] = useState(null);
  const [disconnecting, setDisconnecting] = useState(false);

  // Live Post Comments & Exact Engagement State
  const [activePostFilter, setActivePostFilter] = useState('ALL'); // 'ALL' | 'LIVE' | 'WORKSPACE'
  const [selectedPostForComments, setSelectedPostForComments] = useState(null);
  const [commentsList, setCommentsList] = useState([]);
  const [loadingComments, setLoadingComments] = useState(false);
  const [commentReplyText, setCommentReplyText] = useState('');
  const [submittingComment, setSubmittingComment] = useState(false);
  const [replyingToComment, setReplyingToComment] = useState(null);

  const handleOpenComments = async (post) => {
    setSelectedPostForComments(post);
    setLoadingComments(true);
    setCommentsList([]);
    setCommentReplyText('');
    setReplyingToComment(null);
    try {
      const res = await api.get(`/digital-marketing/posts/INSTAGRAM/${post.id}/comments/`);
      setCommentsList(res.data.comments || []);
    } catch (err) {
      toast.error('Failed to load post comments.');
    } finally {
      setLoadingComments(false);
    }
  };

  const handleSendCommentReply = async (e) => {
    e?.preventDefault();
    if (!commentReplyText.trim() || !selectedPostForComments) return;
    setSubmittingComment(true);
    try {
      const targetCommentId = replyingToComment ? replyingToComment.id : selectedPostForComments.id;
      const res = await api.post(`/digital-marketing/posts/INSTAGRAM/${selectedPostForComments.id}/comments/`, {
        comment_id: targetCommentId,
        message: commentReplyText.trim()
      });
      toast.success(res.data.detail || 'Reply published live to Instagram!');
      setCommentReplyText('');
      setReplyingToComment(null);
      // Refresh comments
      const updated = await api.get(`/digital-marketing/posts/INSTAGRAM/${selectedPostForComments.id}/comments/`);
      setCommentsList(updated.data.comments || []);
      // Also refresh posts to update comment counters
      fetchPosts();
    } catch (err) {
      const msg = err.response?.data?.error || 'Failed to submit comment reply.';
      toast.error(msg);
    } finally {
      setSubmittingComment(false);
    }
  };

  const location = useLocation();
  const oauthProcessedRef = useRef(false);

  const fetchStatus = async () => {
    try {
      const res = await api.get('/digital-marketing/instagram/status/');
      setStatusData(res.data);
    } catch (err) {
      toast.error('Failed to load Instagram status.');
    }
  };

  const fetchPosts = async () => {
    try {
      const res = await api.get('/digital-marketing/instagram/posts/');
      setPostsData(res.data);
    } catch (err) {
      console.warn('Failed to fetch Instagram posts.', err);
    }
  };

  const fetchFbStatus = async () => {
    try {
      const res = await api.get('/digital-marketing/facebook/status/');
      setFbStatus(res.data);
    } catch (e) {
      // optional
    }
  };

  const loadData = async () => {
    setLoading(true);
    await Promise.all([fetchStatus(), fetchPosts(), fetchFbStatus()]);
    setLoading(false);
  };

  useEffect(() => {
    loadData();
  }, []);

  // Handle incoming OAuth callback query params if user was redirected back to frontend
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
          const res = await api.post('/digital-marketing/instagram/callback/', { code, state });
          toast.success(res.data.detail || 'Instagram account connected successfully.');
          loadData();
        } catch (err) {
          toast.error(err.response?.data?.error || 'Failed to complete Instagram connection.');
          loadData();
        }
      };
      processOAuth();
    }
  }, [location.search]);

  const handleConnect = async () => {
    try {
      const redirectUri = `${window.location.origin}/digital-marketing/instagram`;
      const res = await api.get('/digital-marketing/instagram/auth-url/', {
        params: { redirect_uri: redirectUri }
      });
      if (res.data?.url) {
        window.location.href = res.data.url;
      }
    } catch (err) {
      const msg = err.response?.data?.error || 'Failed to start Instagram authorization. Please verify Meta App credentials.';
      toast.error(msg);
    }
  };

  const handleDisconnect = async () => {
    if (!window.confirm('Are you sure you want to disconnect this Instagram account?')) return;
    setDisconnecting(true);
    try {
      await api.post('/digital-marketing/instagram/disconnect/');
      toast.success('Instagram account disconnected.');
      loadData();
    } catch (err) {
      toast.error('Failed to disconnect Instagram account.');
    } finally {
      setDisconnecting(false);
    }
  };

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedFile(file);
      const objUrl = URL.createObjectURL(file);
      setFilePreview(objUrl);
    }
  };

  const handleClearFile = () => {
    setSelectedFile(null);
    if (filePreview) URL.revokeObjectURL(filePreview);
    setFilePreview('');
  };

  const handlePublish = async (e) => {
    e.preventDefault();
    if (!selectedFile && !formData.image_url && !formData.caption) {
      toast.error('Please choose an image file, enter an image URL, or add a caption.');
      return;
    }

    if (!targetPlatforms.instagram && !targetPlatforms.facebook) {
      toast.error('Please select at least one destination platform (Instagram or Facebook).');
      return;
    }

    const shouldPublishLive = isConnected && Boolean(formData.publish_live);
    if (shouldPublishLive && targetPlatforms.instagram && !selectedFile && !formData.image_url) {
      toast.error('Direct Instagram live publishing requires an image file or an image URL.');
      return;
    }

    setPublishing(true);
    try {
      const data = new FormData();
      if (selectedFile) {
        data.append('image_file', selectedFile);
      }
      if (formData.image_url) {
        data.append('image_url', formData.image_url);
      }
      data.append('publish_live', shouldPublishLive ? 'true' : 'false');
      data.append('caption', formData.caption || '');

      const platformsList = [];
      if (targetPlatforms.instagram) platformsList.push('INSTAGRAM');
      if (targetPlatforms.facebook) platformsList.push('FACEBOOK');
      data.append('platforms', platformsList.join(','));

      const res = await api.post('/digital-marketing/posts/universal/', data, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      toast.success(res.data.detail || 'Post published successfully!');
      setIsPublishModalOpen(false);
      handleClearFile();
      setFormData({ image_url: '', caption: '', publish_live: true });
      fetchPosts();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Universal upload failed.');
    } finally {
      setPublishing(false);
    }
  };

  const handleDeletePost = async (postId) => {
    if (!window.confirm('Are you sure you want to delete this post?')) return;
    setDeletingId(postId);
    try {
      await api.delete(`/digital-marketing/posts/${postId}/`);
      toast.success('Post removed from workspace.');
      fetchPosts();
    } catch (err) {
      toast.error('Failed to delete post.');
    } finally {
      setDeletingId(null);
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
          <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-amber-500 via-pink-500 to-purple-600 text-white flex items-center justify-center shadow-md shadow-pink-500/20">
            <InstagramIcon className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-2">
              Instagram Professional
            </h1>
            <p className="text-sm text-slate-500">
              Official Instagram Graph API integration and workspace post management.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              setFormData(prev => ({ ...prev, publish_live: isConnected }));
              setIsPublishModalOpen(true);
            }}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-pink-600 to-purple-600 hover:from-pink-700 hover:to-purple-700 shadow-sm transition"
          >
            <Plus className="w-4 h-4" />
            Upload Post
          </button>

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

      {/* Configuration Warning if Meta App credentials are missing */}
      {!isConfigured && statusData?.config_error && (
        <div className="p-5 bg-amber-50 border border-amber-200 rounded-2xl text-amber-900 shadow-sm space-y-3">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="font-bold text-sm text-amber-900">Meta Developer Configuration Required</h4>
              <p className="text-xs text-amber-800 mt-1">
                {statusData.config_error}
              </p>
            </div>
          </div>
          <div className="text-xs bg-white/60 p-3 rounded-xl border border-amber-200 space-y-1">
            <div className="font-bold text-amber-900">Required Environment Variables:</div>
            <code className="block font-mono text-[11px] text-slate-700">META_APP_ID=&lt;your-facebook-app-id&gt;</code>
            <code className="block font-mono text-[11px] text-slate-700">META_APP_SECRET=&lt;your-facebook-app-secret&gt;</code>
            <code className="block font-mono text-[11px] text-slate-700">META_REDIRECT_URI=http://localhost:5173/digital-marketing/instagram</code>
          </div>
        </div>
      )}

      {/* Account Connection Status Panel */}
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
              <div className="w-16 h-16 rounded-2xl bg-pink-50 text-pink-500 flex items-center justify-center border border-pink-100">
                <InstagramIcon className="w-8 h-8" />
              </div>
            )}

            <div>
              <div className="flex items-center gap-2.5">
                <h3 className="text-lg font-bold text-slate-900">
                  {isConnected ? (account?.account_name || account?.account_username) : 'No Instagram Account Connected'}
                </h3>
                <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold ${
                  isConnected ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'
                }`}>
                  {isConnected ? 'Authorized & Active' : 'Disconnected'}
                </span>
              </div>

              {isConnected ? (
                <div className="mt-2 text-xs text-slate-500 space-y-0.5">
                  <div>Username: <strong className="text-slate-800">@{account?.account_username}</strong></div>
                  <div>Account ID: <code className="text-slate-600 font-mono">{account?.account_id}</code></div>
                  {account?.metadata?.page_name && (
                    <div>Linked Facebook Page: <strong className="text-slate-700">{account.metadata.page_name}</strong></div>
                  )}
                </div>
              ) : (
                <p className="text-xs text-slate-500 mt-1 max-w-xl">
                  You can upload and organize posts directly in your Market Intel DB feed right now. Connecting to Meta is optional and only needed when you want to publish live to an official Instagram account.
                </p>
              )}
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3 self-start md:self-center">
            {isConnected ? (
              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => {
                    setFormData(prev => ({ ...prev, publish_live: true }));
                    setIsPublishModalOpen(true);
                  }}
                  className="inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-pink-600 to-purple-600 hover:from-pink-700 hover:to-purple-700 text-white rounded-xl text-xs font-bold transition shadow-sm"
                >
                  <Plus className="w-4 h-4" />
                  Upload & Publish
                </button>
                <button
                  onClick={handleDisconnect}
                  disabled={disconnecting}
                  className="inline-flex items-center gap-2 px-4 py-2 border border-red-200 text-red-600 hover:bg-red-50 rounded-xl text-xs font-bold transition shadow-sm disabled:opacity-50"
                >
                  <Trash2 className="w-4 h-4" />
                  {disconnecting ? 'Disconnecting...' : 'Disconnect Account'}
                </button>
              </div>
            ) : (
              <div className="flex flex-wrap items-center gap-3">
                <button
                  onClick={() => {
                    setFormData(prev => ({ ...prev, publish_live: false }));
                    setIsPublishModalOpen(true);
                  }}
                  className="inline-flex items-center gap-2 px-4 py-2.5 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-bold transition shadow-sm"
                >
                  <Plus className="w-4 h-4" />
                  Upload Normal Post
                </button>
                <button
                  onClick={handleConnect}
                  disabled={!isConfigured}
                  className="inline-flex items-center gap-2 px-4 py-2.5 bg-gradient-to-r from-pink-600 to-purple-600 hover:from-pink-700 hover:to-purple-700 text-white rounded-xl text-xs font-bold transition shadow-md shadow-pink-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <InstagramIcon className="w-4 h-4" />
                  Connect Live Instagram
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Connected Metrics Bar */}
        {isConnected && (
          <div className="mt-6 pt-6 border-t border-slate-100 grid grid-cols-2 sm:grid-cols-4 gap-4 text-center">
            <div className="p-3 bg-slate-50 rounded-xl">
              <div className="text-xs text-slate-400 font-medium">Followers</div>
              <div className="text-xl font-bold text-slate-900 mt-0.5">
                {(account?.metadata?.followers_count || 0).toLocaleString()}
              </div>
            </div>
            <div className="p-3 bg-slate-50 rounded-xl">
              <div className="text-xs text-slate-400 font-medium">Following</div>
              <div className="text-xl font-bold text-slate-900 mt-0.5">
                {(account?.metadata?.follows_count || 0).toLocaleString()}
              </div>
            </div>
            <div className="p-3 bg-slate-50 rounded-xl">
              <div className="text-xs text-slate-400 font-medium">Media Posts</div>
              <div className="text-xl font-bold text-slate-900 mt-0.5">
                {(account?.metadata?.media_count || 0).toLocaleString()}
              </div>
            </div>
            <div className="p-3 bg-slate-50 rounded-xl">
              <div className="text-xs text-slate-400 font-medium">Account Type</div>
              <div className="text-sm font-bold text-slate-900 mt-1">
                Professional (Business)
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Technical Prerequisites & Permission Details */}
      <div className="bg-slate-100/60 rounded-2xl border border-slate-200 p-5 text-xs text-slate-600 space-y-2">
        <div className="flex items-center gap-2 font-bold text-slate-800 text-sm">
          <HelpCircle className="w-4 h-4 text-pink-600" />
          Supported Capabilities & Official Permissions
        </div>
        <ul className="list-disc list-inside space-y-1 text-slate-500 pl-1">
          <li><strong>Supported:</strong> Live post engagement, exact likes counter, public post comments viewer and replies, photo publishing.</li>
          <li><strong>Required Scopes:</strong> <code>instagram_basic</code>, <code>instagram_content_publish</code>, <code>instagram_manage_insights</code>, <code>pages_show_list</code>.</li>
          <li><strong>Privacy Note:</strong> In accordance with Meta official privacy policies, exact follower counts and commenters' usernames are provided for free; individual follower profiles are protected.</li>
        </ul>
      </div>

      {/* Instagram Posts & Insights Feed */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-2">
            <ImageIcon className="w-5 h-5 text-pink-600" />
            <h3 className="font-bold text-slate-900 text-base">Posts & Exact Engagement</h3>
          </div>

          {/* Filter Tabs */}
          <div className="flex items-center rounded-xl bg-slate-100 p-1 text-xs font-bold">
            <button
              onClick={() => setActivePostFilter('ALL')}
              className={`px-3 py-1.5 rounded-lg transition ${activePostFilter === 'ALL' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}
            >
              All ({(postsData.live_posts?.length || 0) + (postsData.database_posts?.length || 0)})
            </button>
            <button
              onClick={() => setActivePostFilter('LIVE')}
              className={`px-3 py-1.5 rounded-lg transition ${activePostFilter === 'LIVE' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}
            >
              Live Meta Posts ({postsData.live_posts?.length || 0})
            </button>
            <button
              onClick={() => setActivePostFilter('WORKSPACE')}
              className={`px-3 py-1.5 rounded-lg transition ${activePostFilter === 'WORKSPACE' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}
            >
              Workspace ({postsData.database_posts?.length || 0})
            </button>
          </div>
        </div>

        {(() => {
          const liveList = (postsData.live_posts || []).map(p => ({
            id: p.id,
            caption: p.caption,
            media_url: p.media_url || p.thumbnail_url,
            permalink: p.permalink,
            published_at: p.timestamp,
            likes_count: p.like_count ?? 0,
            comments_count: p.comments_count ?? 0,
            is_live: true,
          }));

          const dbList = (postsData.database_posts || []).map(p => ({
            id: p.id,
            external_post_id: p.external_post_id,
            caption: p.caption,
            media_url: p.media_display_url || p.media_url,
            published_at: p.published_at,
            likes_count: p.metrics?.likes ?? 0,
            comments_count: p.metrics?.comments ?? 0,
            status: p.status,
            is_live: Boolean(p.external_post_id && (p.status === 'PUBLISHED' || !p.status)),
          }));

          const seenIds = new Set();
          const merged = [];
          for (const l of liveList) {
            seenIds.add(l.id);
            merged.push(l);
          }
          for (const d of dbList) {
            if (!d.external_post_id || !seenIds.has(d.external_post_id)) {
              if (d.external_post_id) seenIds.add(d.external_post_id);
              merged.push(d);
            }
          }

          let combined = [];
          if (activePostFilter === 'LIVE') combined = merged.filter(p => p.is_live);
          else if (activePostFilter === 'WORKSPACE') combined = merged.filter(p => !p.is_live);
          else combined = merged;

          if (combined.length === 0) {
            return (
              <div className="py-12 text-center text-slate-400 text-sm">
                <InstagramIcon className="w-12 h-12 text-slate-200 mx-auto mb-3" />
                <p className="font-bold text-slate-700 text-base">No posts found for this view</p>
                <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                  Upload an image to your workspace or publish live to Instagram to see your engagement counters.
                </p>
                <button
                  onClick={() => {
                    setFormData(prev => ({ ...prev, publish_live: isConnected }));
                    setIsPublishModalOpen(true);
                  }}
                  className="mt-4 inline-flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-pink-600 to-purple-600 text-white rounded-xl text-xs font-bold hover:from-pink-700 hover:to-purple-700 transition shadow-md shadow-pink-500/20"
                >
                  <Plus className="w-4 h-4" />
                  Upload Post
                </button>
              </div>
            );
          }

          return (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {combined.map((post) => (
                <div key={post.id} className="border border-slate-200 rounded-2xl overflow-hidden flex flex-col justify-between hover:shadow-md transition bg-white group">
                  <div>
                    {post.media_url ? (
                      <div className="relative">
                        <img
                          src={post.media_url}
                          alt={post.caption || 'Instagram Post'}
                          className="w-full h-48 object-cover bg-slate-100"
                          onError={(e) => { e.target.style.display = 'none'; }}
                        />
                        <div className="absolute top-2 left-2">
                          {post.is_live ? (
                            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[10px] font-bold bg-slate-900/80 backdrop-blur-sm text-white border border-white/20 shadow-sm">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
                              Live on Instagram
                            </span>
                          ) : (
                            <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-slate-900/80 backdrop-blur-sm text-white">
                              Workspace Draft
                            </span>
                          )}
                        </div>
                        {post.permalink && (
                          <a
                            href={post.permalink}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="absolute top-2 right-2 p-1.5 rounded-lg bg-slate-900/80 backdrop-blur-sm text-white hover:bg-pink-600 transition"
                            title="Open on Instagram"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                          </a>
                        )}
                      </div>
                    ) : (
                      <div className="w-full h-40 bg-slate-100 flex items-center justify-center text-slate-400">
                        <ImageIcon className="w-8 h-8" />
                      </div>
                    )}

                    <div className="p-4">
                      <p className="text-xs text-slate-800 line-clamp-3">
                        {post.caption || <span className="text-slate-400 italic">No caption provided</span>}
                      </p>
                      <div className="mt-3 text-[11px] text-slate-400">
                        {post.published_at ? new Date(post.published_at).toLocaleString() : 'Just now'}
                      </div>
                    </div>
                  </div>

                  <div className="p-4 bg-slate-50 border-t border-slate-100 flex items-center justify-between text-xs text-slate-600">
                    <div className="flex items-center gap-3">
                      <span className="flex items-center gap-1 font-bold text-rose-600" title="Exact Likes">
                        <Heart className="w-4 h-4 fill-rose-500 text-rose-500" />
                        {post.likes_count.toLocaleString()}
                      </span>

                      <button
                        onClick={() => handleOpenComments(post)}
                        className="flex items-center gap-1 font-bold text-blue-600 hover:text-blue-800 transition"
                        title="View comments"
                      >
                        <MessageCircle className="w-4 h-4" />
                        {post.comments_count.toLocaleString()}
                      </button>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleOpenComments(post)}
                        className="px-2.5 py-1 text-[11px] font-bold rounded-lg bg-white border border-slate-200 text-slate-700 hover:border-pink-300 hover:text-pink-600 transition shadow-xs"
                      >
                        Comments ({post.comments_count})
                      </button>
                      {!post.is_live && (
                        <button
                          onClick={() => handleDeletePost(post.id)}
                          disabled={deletingId === post.id}
                          className="text-slate-400 hover:text-rose-600 p-1 rounded transition"
                          title="Delete post"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          );
        })()}
      </div>

      {/* Publish / Normal Upload Modal */}
      {isPublishModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg overflow-hidden border border-slate-200 animate-in fade-in zoom-in-95 duration-150">
            <div className="p-5 border-b border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <InstagramIcon className="w-5 h-5 text-pink-600" />
                <h3 className="font-bold text-slate-900">
                  {isConnected ? 'Create / Upload Instagram Post' : 'Upload Normal Post'}
                </h3>
              </div>
              <button
                onClick={() => setIsPublishModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handlePublish} className="p-5 space-y-4">
              {/* Upload Mode Tabs */}
              <div className="flex rounded-xl bg-slate-100 p-1 text-xs font-bold">
                <button
                  type="button"
                  onClick={() => setUploadMode('file')}
                  className={`flex-1 py-1.5 rounded-lg transition ${uploadMode === 'file' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}
                >
                  Upload Image File
                </button>
                <button
                  type="button"
                  onClick={() => setUploadMode('url')}
                  className={`flex-1 py-1.5 rounded-lg transition ${uploadMode === 'url' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}
                >
                  Image URL
                </button>
              </div>

              {uploadMode === 'file' ? (
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1.5">
                    Select Image File from Device
                  </label>
                  {filePreview ? (
                    <div className="relative rounded-xl overflow-hidden border border-slate-200 bg-slate-50">
                      <img src={filePreview} alt="Preview" className="w-full h-44 object-cover" />
                      <button
                        type="button"
                        onClick={handleClearFile}
                        className="absolute top-2 right-2 bg-slate-900/80 text-white p-1.5 rounded-lg hover:bg-rose-600 transition"
                        title="Remove image"
                      >
                        <X className="w-4 h-4" />
                      </button>
                    </div>
                  ) : (
                    <label className="border-2 border-dashed border-slate-200 hover:border-pink-500 rounded-2xl p-6 flex flex-col items-center justify-center cursor-pointer bg-slate-50 hover:bg-pink-50/30 transition">
                      <ImageIcon className="w-8 h-8 text-slate-400 mb-2" />
                      <span className="text-xs font-bold text-slate-700">Click to choose image</span>
                      <span className="text-[10px] text-slate-400 mt-0.5">JPG, PNG, WEBP, GIF</span>
                      <input
                        type="file"
                        accept="image/*"
                        onChange={handleFileChange}
                        className="hidden"
                      />
                    </label>
                  )}
                </div>
              ) : (
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">
                    Public Image URL
                  </label>
                  <input
                    type="url"
                    placeholder="https://example.com/assets/campaign-banner.jpg"
                    value={formData.image_url}
                    onChange={(e) => setFormData(prev => ({ ...prev, image_url: e.target.value }))}
                    className="w-full text-xs px-3.5 py-2.5 rounded-xl border border-slate-200 focus:outline-none focus:border-pink-500 focus:ring-2 focus:ring-pink-100"
                  />
                </div>
              )}

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Caption & Hashtags
                </label>
                <textarea
                  rows="3"
                  maxLength="2200"
                  placeholder="Write your post caption or notes... #marketintel"
                  value={formData.caption}
                  onChange={(e) => setFormData(prev => ({ ...prev, caption: e.target.value }))}
                  className="w-full text-xs px-3.5 py-2.5 rounded-xl border border-slate-200 focus:outline-none focus:border-pink-500 focus:ring-2 focus:ring-pink-100"
                />
                <div className="text-right text-[10px] text-slate-400 mt-1">
                  {formData.caption.length} / 2200 characters
                </div>
              </div>

              {/* Target Platforms: Universal Cross-Posting */}
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1.5 flex items-center justify-between">
                  <span>Publish Destinations</span>
                  {targetPlatforms.instagram && targetPlatforms.facebook && (
                    <span className="text-[10px] font-bold text-purple-700 bg-purple-50 px-2 py-0.5 rounded-full border border-purple-200">
                      ⚡ Universal Post Active
                    </span>
                  )}
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  <label className={`flex items-center gap-2.5 p-3 rounded-xl border cursor-pointer transition ${targetPlatforms.instagram ? 'bg-pink-50/70 border-pink-300' : 'bg-slate-50 border-slate-200 opacity-60'}`}>
                    <input
                      type="checkbox"
                      checked={targetPlatforms.instagram}
                      onChange={(e) => setTargetPlatforms(prev => ({ ...prev, instagram: e.target.checked }))}
                      className="rounded text-pink-600 focus:ring-pink-500 w-4 h-4"
                    />
                    <div className="flex items-center gap-2">
                      <InstagramIcon className="w-4 h-4 text-pink-600 shrink-0" />
                      <div className="text-left">
                        <div className="text-xs font-bold text-slate-900">Instagram</div>
                        <div className="text-[10px] text-slate-500 truncate max-w-[120px]">
                          {account?.account_username ? `@${account.account_username}` : 'Instagram Account'}
                        </div>
                      </div>
                    </div>
                  </label>

                  <label className={`flex items-center gap-2.5 p-3 rounded-xl border cursor-pointer transition ${targetPlatforms.facebook ? 'bg-blue-50/70 border-blue-300' : 'bg-slate-50 border-slate-200 opacity-60'}`}>
                    <input
                      type="checkbox"
                      checked={targetPlatforms.facebook}
                      onChange={(e) => setTargetPlatforms(prev => ({ ...prev, facebook: e.target.checked }))}
                      className="rounded text-blue-600 focus:ring-blue-500 w-4 h-4"
                    />
                    <div className="flex items-center gap-2">
                      <FacebookIcon className="w-4 h-4 text-blue-600 shrink-0" />
                      <div className="text-left">
                        <div className="text-xs font-bold text-slate-900">Facebook Page</div>
                        <div className="text-[10px] text-slate-500 truncate max-w-[120px]">
                          {fbStatus?.pages?.[0]?.account_name || 'Market Intel DB'}
                        </div>
                      </div>
                    </div>
                  </label>
                </div>
              </div>

              {/* Status Info / Publish Live Option */}
              {isConnected ? (
                <div className="space-y-2">
                  <label className="flex items-start gap-3 cursor-pointer bg-slate-50 p-3.5 rounded-xl border border-slate-200 hover:bg-slate-100/60 transition">
                    <input
                      type="checkbox"
                      checked={formData.publish_live}
                      onChange={(e) => setFormData(prev => ({ ...prev, publish_live: e.target.checked }))}
                      className="mt-0.5 rounded text-pink-600 focus:ring-pink-500 w-4 h-4"
                    />
                    <div className="flex-1">
                      <div className="text-xs font-bold text-slate-900 flex items-center gap-1.5">
                        Publish live via Meta Graph API
                      </div>
                      <div className="text-[10px] text-slate-500 mt-0.5 leading-relaxed">
                        {targetPlatforms.instagram && targetPlatforms.facebook
                          ? 'This post will be broadcast live to both your Instagram account and Facebook Page simultaneously.'
                          : targetPlatforms.facebook
                            ? 'This post will be published live to your official Facebook Page.'
                            : 'This post will be published live to your official Instagram account.'}
                      </div>
                    </div>
                  </label>
                  {!formData.publish_live && (
                    <div className="text-[10px] text-slate-500 px-1">
                      Unchecked: Post will be saved only to your local Market Intel DB workspace feed.
                    </div>
                  )}
                </div>
              ) : (
                <div className="bg-slate-50 border border-slate-200 p-3 rounded-xl text-[11px] text-slate-600">
                  <span className="font-bold text-slate-800">Normal Post Mode:</span> This post will be uploaded and stored directly in your Market Intel DB feed. Connect Instagram above to publish live.
                </div>
              )}

              <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setIsPublishModalOpen(false)}
                  className="px-4 py-2 rounded-xl text-xs font-bold text-slate-600 hover:bg-slate-100 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={publishing}
                  className="inline-flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-pink-600 via-purple-600 to-blue-600 hover:opacity-90 transition shadow-sm disabled:opacity-50"
                >
                  <Send className="w-3.5 h-3.5" />
                  {publishing
                    ? 'Publishing live...'
                    : targetPlatforms.instagram && targetPlatforms.facebook
                      ? '🚀 Publish to Instagram & Facebook'
                      : targetPlatforms.facebook
                        ? 'Publish to Facebook'
                        : 'Publish to Instagram'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Comments & Discussion Modal */}
      {selectedPostForComments && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg overflow-hidden border border-slate-200 flex flex-col max-h-[85vh] animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="p-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-pink-100 text-pink-600 flex items-center justify-center">
                  <MessageCircle className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-sm text-slate-900">Post Comments & Engagement</h3>
                  <div className="flex items-center gap-3 text-[11px] text-slate-500 mt-0.5">
                    <span className="flex items-center gap-1 font-semibold text-rose-600">
                      <Heart className="w-3 h-3 fill-rose-500 text-rose-500" />
                      {selectedPostForComments.likes_count ?? 0} Likes
                    </span>
                    <span>•</span>
                    <span className="font-semibold text-slate-700">
                      {commentsList.length} Comments
                    </span>
                  </div>
                </div>
              </div>
              <button
                onClick={() => {
                  setSelectedPostForComments(null);
                  setReplyingToComment(null);
                }}
                className="text-slate-400 hover:text-slate-600 p-1.5 rounded-lg hover:bg-slate-100 transition"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Post Caption Snippet */}
            {selectedPostForComments.caption && (
              <div className="p-3 bg-slate-50 border-b border-slate-100 text-xs text-slate-600 flex items-start gap-2.5">
                <span className="font-bold text-slate-900 shrink-0">Caption:</span>
                <p className="line-clamp-2 italic text-slate-700">"{selectedPostForComments.caption}"</p>
              </div>
            )}

            {/* Comments List */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3.5 divide-y divide-slate-100">
              {loadingComments ? (
                <div className="py-12 text-center text-slate-400 text-xs flex flex-col items-center gap-2">
                  <RefreshCw className="w-5 h-5 animate-spin text-pink-600" />
                  Loading comments from Instagram...
                </div>
              ) : commentsList.length === 0 ? (
                <div className="py-12 text-center text-slate-400 text-xs space-y-2">
                  <MessageCircle className="w-8 h-8 text-slate-300 mx-auto" />
                  <p className="font-bold text-slate-700">No comments on this post yet</p>
                  <p className="text-[11px] text-slate-400">
                    Write a comment below to start the conversation!
                  </p>
                </div>
              ) : (
                commentsList.map((c) => (
                  <div key={c.id} className="pt-3 first:pt-0 space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-start gap-2.5">
                        <div className="w-7 h-7 rounded-full bg-gradient-to-tr from-pink-500 to-purple-600 text-white font-bold text-xs flex items-center justify-center shrink-0">
                          {(c.username || c.name || 'U').charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-bold text-xs text-slate-900">
                              {c.name && c.name !== c.username ? c.name : (c.username ? `@${c.username}` : 'Instagram User')}
                            </span>
                            {c.name && c.username && c.name !== c.username && (
                              <span className="text-[11px] text-slate-500 font-medium">
                                (@{c.username})
                              </span>
                            )}
                            <span className="text-[10px] text-slate-400">
                              • {c.timestamp ? new Date(c.timestamp).toLocaleDateString() : ''}
                            </span>
                          </div>
                          <p className="text-xs text-slate-700 mt-1 whitespace-pre-wrap leading-relaxed">
                            {c.text}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        {c.like_count > 0 && (
                          <span className="flex items-center gap-1 text-[10px] text-rose-600 font-bold">
                            <Heart className="w-3 h-3 fill-rose-500" /> {c.like_count}
                          </span>
                        )}
                        <button
                          onClick={() => {
                            setReplyingToComment(c);
                            setCommentReplyText(c.username ? `@${c.username} ` : '');
                          }}
                          className="text-[11px] font-bold text-pink-600 hover:text-pink-800 transition"
                        >
                          Reply
                        </button>
                      </div>
                    </div>

                    {/* Nested Replies */}
                    {c.replies?.length > 0 && (
                      <div className="ml-9 pl-3 border-l-2 border-slate-100 space-y-2 mt-2">
                        {c.replies.map((r) => (
                          <div key={r.id} className="text-xs">
                            <div className="flex items-center gap-1.5 font-bold text-slate-900 text-[11px]">
                              <span>{r.name && r.name !== r.username ? `${r.name} (@${r.username})` : `@${r.username || 'user'}`}</span>
                              <span className="text-[9px] text-slate-400 font-normal">
                                • {r.timestamp ? new Date(r.timestamp).toLocaleDateString() : ''}
                              </span>
                            </div>
                            <p className="text-slate-600 text-[11px] mt-0.5">{r.text}</p>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>

            {/* Reply / Comment Composer */}
            <form onSubmit={handleSendCommentReply} className="p-3 border-t border-slate-100 bg-slate-50/50 space-y-2">
              {replyingToComment && (
                <div className="flex items-center justify-between text-[11px] text-pink-700 bg-pink-50 px-2.5 py-1 rounded-lg">
                  <span>Replying to <strong>{replyingToComment.name || `@${replyingToComment.username}`}</strong></span>
                  <button
                    type="button"
                    onClick={() => {
                      setReplyingToComment(null);
                      setCommentReplyText('');
                    }}
                    className="font-bold hover:underline"
                  >
                    Cancel
                  </button>
                </div>
              )}
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  placeholder={replyingToComment ? `Write a reply to ${replyingToComment.username ? `@${replyingToComment.username}` : 'user'}...` : "Write a public comment on this post..."}
                  value={commentReplyText}
                  onChange={(e) => setCommentReplyText(e.target.value)}
                  className="flex-1 text-xs px-3.5 py-2 rounded-xl border border-slate-200 focus:outline-none focus:border-pink-500 bg-white"
                />
                <button
                  type="submit"
                  disabled={submittingComment || !commentReplyText.trim()}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-gradient-to-r from-pink-600 to-purple-600 text-white font-bold text-xs hover:from-pink-700 hover:to-purple-700 transition shadow-sm disabled:opacity-50"
                >
                  <Send className={`w-3.5 h-3.5 ${submittingComment ? 'animate-spin' : ''}`} />
                  {replyingToComment ? 'Reply' : 'Comment'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default InstagramPage;
