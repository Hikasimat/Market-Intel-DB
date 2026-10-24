import React, { useState, useEffect, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { toast } from 'react-toastify';
import { 
  Plus, 
  Trash2, 
  RefreshCw, 
  AlertCircle, 
  ThumbsUp,
  MessageCircle,
  Share2,
  Send,
  X,
  Building,
  Users,
  HelpCircle,
  Globe,
  ExternalLink,
  Image as ImageIcon,
  Heart
} from 'lucide-react';
import api from '../../services/api';
import { FacebookIcon, InstagramIcon } from '../../components/common/SocialIcons';

const FacebookPage = () => {
  const [loading, setLoading] = useState(true);
  const [statusData, setStatusData] = useState(null);
  const [igStatus, setIgStatus] = useState(null);
  const [postsData, setPostsData] = useState({ database_posts: [], live_posts: [] });
  const [isPublishModalOpen, setIsPublishModalOpen] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [formData, setFormData] = useState({ message: '', link: '', page_id: '', publish_live: true });
  const [targetPlatforms, setTargetPlatforms] = useState({ facebook: true, instagram: true });
  const [selectedFile, setSelectedFile] = useState(null);
  const [filePreview, setFilePreview] = useState('');
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

  const location = useLocation();
  const oauthProcessedRef = useRef(false);

  const handleOpenComments = async (post) => {
    setSelectedPostForComments(post);
    setLoadingComments(true);
    setCommentsList([]);
    setCommentReplyText('');
    setReplyingToComment(null);

    const targetPostId = post.external_post_id || post.id;
    if (!targetPostId) {
      setLoadingComments(false);
      return;
    }

    try {
      const res = await api.get(`/digital-marketing/posts/FACEBOOK/${targetPostId}/comments/`);
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
    const targetPostId = selectedPostForComments.external_post_id || selectedPostForComments.id;

    if (!targetPostId) {
      toast.error('Cannot reply to comments on a workspace draft that has not been published to Facebook.');
      return;
    }

    setSubmittingComment(true);
    try {
      const targetCommentId = replyingToComment ? replyingToComment.id : targetPostId;
      const res = await api.post(`/digital-marketing/posts/FACEBOOK/${targetPostId}/comments/`, {
        comment_id: targetCommentId,
        message: commentReplyText.trim()
      });
      toast.success(res.data.detail || 'Reply published live to Facebook!');
      setCommentReplyText('');
      setReplyingToComment(null);
      // Refresh comments
      const updated = await api.get(`/digital-marketing/posts/FACEBOOK/${targetPostId}/comments/`);
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

  const fetchStatus = async () => {
    try {
      const res = await api.get('/digital-marketing/facebook/status/');
      setStatusData(res.data);
      if (res.data?.pages?.length > 0 && !formData.page_id) {
        setFormData(prev => ({ ...prev, page_id: res.data.pages[0].account_id }));
      }
    } catch (err) {
      toast.error('Failed to load Facebook Pages status.');
    }
  };

  const fetchPosts = async () => {
    try {
      const res = await api.get('/digital-marketing/facebook/posts/');
      setPostsData(res.data);
    } catch (err) {
      console.warn('Failed to fetch Facebook posts.', err);
    }
  };

  const fetchIgStatus = async () => {
    try {
      const res = await api.get('/digital-marketing/instagram/status/');
      setIgStatus(res.data);
    } catch (e) {
      // optional
    }
  };

  const loadData = async () => {
    setLoading(true);
    await Promise.all([fetchStatus(), fetchPosts(), fetchIgStatus()]);
    setLoading(false);
  };

  useEffect(() => {
    loadData();
  }, []);

  // Handle incoming OAuth callback query params
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
          const res = await api.post('/digital-marketing/facebook/callback/', { code, state });
          toast.success(res.data.detail || 'Facebook Pages authorized successfully.');
          loadData();
        } catch (err) {
          toast.error(err.response?.data?.error || 'Failed to complete Facebook authorization.');
          loadData();
        }
      };
      processOAuth();
    }
  }, [location.search]);

  const handleConnect = async () => {
    try {
      const redirectUri = `${window.location.origin}/digital-marketing/facebook`;
      const res = await api.get('/digital-marketing/facebook/auth-url/', {
        params: { redirect_uri: redirectUri }
      });
      if (res.data?.url) {
        window.location.href = res.data.url;
      }
    } catch (err) {
      const msg = err.response?.data?.error || 'Failed to start Facebook authorization.';
      toast.error(msg);
    }
  };

  const handleDisconnect = async (pageId = null) => {
    if (!window.confirm('Disconnect this Facebook Page from Market Intel DB?')) return;
    setDisconnecting(true);
    try {
      await api.post('/digital-marketing/facebook/disconnect/', { page_id: pageId });
      toast.success('Facebook Page disconnected.');
      loadData();
    } catch (err) {
      toast.error('Failed to disconnect Facebook Page.');
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
    if (!formData.message.trim() && !selectedFile && !formData.link) {
      toast.error('Please enter a message, link, or attach an image.');
      return;
    }

    if (!targetPlatforms.facebook && !targetPlatforms.instagram) {
      toast.error('Please select at least one destination platform (Facebook or Instagram).');
      return;
    }

    setPublishing(true);
    try {
      const data = new FormData();
      if (selectedFile) data.append('image_file', selectedFile);
      if (formData.message) data.append('caption', formData.message);
      if (formData.link) data.append('link', formData.link);
      data.append('publish_live', isConnected && formData.publish_live ? 'true' : 'false');

      const platformsList = [];
      if (targetPlatforms.facebook) platformsList.push('FACEBOOK');
      if (targetPlatforms.instagram) platformsList.push('INSTAGRAM');
      data.append('platforms', platformsList.join(','));

      const res = await api.post('/digital-marketing/posts/universal/', data, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      toast.success(res.data.detail || 'Post uploaded successfully!');
      setIsPublishModalOpen(false);
      handleClearFile();
      setFormData(prev => ({ ...prev, message: '', link: '', publish_live: true }));
      fetchPosts();
    } catch (err) {
      toast.error(err.response?.data?.error || 'Failed to upload post.');
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
  const pages = statusData?.pages || [];

  const totalFollowers = pages.reduce((acc, p) => acc + (p.metadata?.followers_count || p.metadata?.fan_count || 0), 0);
  const totalFans = pages.reduce((acc, p) => acc + (p.metadata?.fan_count || 0), 0);

  // Live posts directly from Facebook Graph API
  const liveList = (postsData.live_posts || []).map(p => ({
    id: p.id,
    external_post_id: p.id,
    caption: p.message,
    media_url: p.media_url || '',
    permalink: p.permalink_url || `https://facebook.com/${p.id}`,
    published_at: p.created_time,
    likes_count: p.reactions_count ?? 0,
    comments_count: p.comments_count ?? 0,
    shares_count: p.shares_count ?? 0,
    is_live: true,
  }));

  // Posts from database (including published posts and drafts)
  const dbList = (postsData.database_posts || []).map(p => {
    const isLive = Boolean(p.external_post_id && (p.status === 'PUBLISHED' || !p.status));
    return {
      id: p.id,
      external_post_id: p.external_post_id,
      caption: p.caption,
      media_url: p.media_display_url || p.media_url,
      media_type: p.media_type,
      permalink: p.external_post_id ? `https://facebook.com/${p.external_post_id}` : '',
      published_at: p.published_at,
      likes_count: p.metrics?.reactions_count ?? p.metrics?.likes ?? 0,
      comments_count: p.metrics?.comments_count ?? p.metrics?.comments ?? 0,
      shares_count: p.metrics?.shares_count ?? 0,
      status: p.status,
      is_live: isLive,
    };
  });

  // Deduplicate and merge: database posts + Graph API posts
  const seenIds = new Set();
  const mergedPosts = [];

  for (const dbPost of dbList) {
    if (dbPost.external_post_id) {
      seenIds.add(dbPost.external_post_id);
      const liveMatch = liveList.find(lp => lp.id === dbPost.external_post_id);
      if (liveMatch) {
        dbPost.likes_count = liveMatch.likes_count || dbPost.likes_count;
        dbPost.comments_count = liveMatch.comments_count || dbPost.comments_count;
        dbPost.shares_count = liveMatch.shares_count || dbPost.shares_count;
        if (liveMatch.permalink) dbPost.permalink = liveMatch.permalink;
        if (!dbPost.media_url && liveMatch.media_url) dbPost.media_url = liveMatch.media_url;
      }
    }
    mergedPosts.push(dbPost);
  }

  for (const livePost of liveList) {
    if (!seenIds.has(livePost.id)) {
      seenIds.add(livePost.id);
      mergedPosts.push(livePost);
    }
  }

  const livePostsCount = mergedPosts.filter(p => p.is_live).length;
  const workspaceDraftsCount = mergedPosts.filter(p => !p.is_live).length;
  const totalPostsCount = mergedPosts.length;

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-blue-600 text-white flex items-center justify-center shadow-md shadow-blue-500/20">
            <FacebookIcon className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-2">
              Facebook Pages
            </h1>
            <p className="text-sm text-slate-500">
              Official Meta Graph API integration, real-time post engagement, and comments.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              setFormData(prev => ({ ...prev, publish_live: isConnected }));
              setIsPublishModalOpen(true);
            }}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold text-white bg-blue-600 hover:bg-blue-700 shadow-sm transition"
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

      {/* Meta App Configuration Warning if missing */}
      {!isConfigured && statusData?.config_error && (
        <div className="p-5 bg-amber-50 border border-amber-200 rounded-2xl text-amber-900 shadow-sm space-y-3">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
            <div>
              <h4 className="font-bold text-sm text-amber-900">Meta App Configuration Required</h4>
              <p className="text-xs text-amber-800 mt-1">
                {statusData.config_error}
              </p>
            </div>
          </div>
          <div className="text-xs bg-white/60 p-3 rounded-xl border border-amber-200 space-y-1">
            <div className="font-bold text-amber-900">Required Environment Variables:</div>
            <code className="block font-mono text-[11px] text-slate-700">META_APP_ID=&lt;your-facebook-app-id&gt;</code>
            <code className="block font-mono text-[11px] text-slate-700">META_APP_SECRET=&lt;your-facebook-app-secret&gt;</code>
            <code className="block font-mono text-[11px] text-slate-700">META_FACEBOOK_REDIRECT_URI={typeof window !== 'undefined' ? `${window.location.origin}/digital-marketing/facebook` : 'https://marketinteldbapp.hikasimat.com/digital-marketing/facebook'}</code>
          </div>
        </div>
      )}

      {/* Connected Pages Overview */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div>
            <h3 className="text-base font-bold text-slate-900">Authorized Facebook Pages</h3>
            <p className="text-xs text-slate-500 mt-0.5">
              {isConnected ? `${pages.length} Facebook Page(s) authorized with page management permissions.` : 'No Facebook Pages currently connected.'}
            </p>
          </div>

          {!isConnected && (
            <button
              onClick={handleConnect}
              disabled={!isConfigured}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-xl text-xs font-bold transition shadow-md shadow-blue-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <FacebookIcon className="w-4 h-4" />
              Authorize Facebook Pages
            </button>
          )}
        </div>

        {isConnected ? (
          <div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {pages.map((page) => (
                <div key={page.id} className="p-4 border border-slate-200 rounded-xl bg-slate-50/50 flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3">
                    {page.profile_picture_url ? (
                      <img src={page.profile_picture_url} alt={page.account_name} className="w-12 h-12 rounded-xl object-cover border border-slate-200" />
                    ) : (
                      <div className="w-12 h-12 rounded-xl bg-blue-100 text-blue-700 flex items-center justify-center font-bold">
                        <Building className="w-6 h-6" />
                      </div>
                    )}
                    <div>
                      <h4 className="text-sm font-bold text-slate-900">{page.account_name}</h4>
                      <div className="text-xs text-slate-500 mt-0.5">
                        {page.metadata?.category || 'Business Page'} · <strong className="text-slate-700">{(page.metadata?.followers_count || page.metadata?.fan_count || 0).toLocaleString()}</strong> followers
                      </div>
                      <code className="text-[10px] text-slate-400 font-mono">ID: {page.account_id}</code>
                    </div>
                  </div>

                  <button
                    onClick={() => handleDisconnect(page.account_id)}
                    disabled={disconnecting}
                    className="p-2 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition"
                    title="Disconnect this Page"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>

            {/* Live Facebook Engagement & Audience Metrics Bar */}
            <div className="mt-6 pt-6 border-t border-slate-100 grid grid-cols-2 sm:grid-cols-4 gap-4 text-center">
              <div className="p-3 bg-slate-50 rounded-xl">
                <div className="text-xs text-slate-400 font-medium">Page Followers</div>
                <div className="text-xl font-bold text-slate-900 mt-0.5">
                  {totalFollowers.toLocaleString()}
                </div>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl">
                <div className="text-xs text-slate-400 font-medium">Page Likes (Fans)</div>
                <div className="text-xl font-bold text-slate-900 mt-0.5">
                  {totalFans.toLocaleString()}
                </div>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl">
                <div className="text-xs text-slate-400 font-medium">Total Posts</div>
                <div className="text-xl font-bold text-slate-900 mt-0.5">
                  {totalPostsCount.toLocaleString()}
                </div>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl">
                <div className="text-xs text-slate-400 font-medium">Integration Mode</div>
                <div className="text-sm font-bold text-emerald-700 mt-1 flex items-center justify-center gap-1">
                  <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                  Meta Graph API
                </div>
              </div>
            </div>
          </div>
        ) : (
          <div className="p-8 border border-dashed border-slate-200 rounded-xl text-center text-slate-400 text-xs">
            Connect your Facebook account to grant Page-level publishing and analytics permissions.
          </div>
        )}
      </div>

      {/* Permission Boundaries & Policy */}
      <div className="bg-slate-100/60 rounded-2xl border border-slate-200 p-5 text-xs text-slate-600 space-y-2">
        <div className="flex items-center gap-2 font-bold text-slate-800 text-sm">
          <HelpCircle className="w-4 h-4 text-blue-600" />
          Facebook Platform Capabilities & Permissions
        </div>
        <ul className="list-disc list-inside space-y-1 text-slate-500 pl-1">
          <li><strong>Supported:</strong> Publishing feed messages, image attachments, exact likes/reactions counters, comments viewer, and direct replies.</li>
          <li><strong>API Permissions:</strong> <code>pages_show_list</code>, <code>pages_read_engagement</code>, <code>pages_manage_posts</code>, <code>business_management</code>.</li>
          <li><strong>Policy Note:</strong> Meta Graph API scopes management strictly to authorized business Pages. Follower counts and post commenters are available for free.</li>
        </ul>
      </div>

      {/* Facebook Posts & Engagement Insights Feed */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-6">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="flex items-center gap-2">
            <Share2 className="w-5 h-5 text-blue-600" />
            <h3 className="font-bold text-slate-900 text-base">Page Posts & Exact Engagement</h3>
          </div>

          {/* Filter Tabs */}
          <div className="flex items-center rounded-xl bg-slate-100 p-1 text-xs font-bold">
            <button
              onClick={() => setActivePostFilter('ALL')}
              className={`px-3 py-1.5 rounded-lg transition ${activePostFilter === 'ALL' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}
            >
              All ({totalPostsCount})
            </button>
            <button
              onClick={() => setActivePostFilter('LIVE')}
              className={`px-3 py-1.5 rounded-lg transition ${activePostFilter === 'LIVE' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}
            >
              Live Facebook Posts ({livePostsCount})
            </button>
            <button
              onClick={() => setActivePostFilter('WORKSPACE')}
              className={`px-3 py-1.5 rounded-lg transition ${activePostFilter === 'WORKSPACE' ? 'bg-white text-slate-900 shadow-sm' : 'text-slate-500 hover:text-slate-800'}`}
            >
              Workspace ({workspaceDraftsCount})
            </button>
          </div>
        </div>

        {(() => {
          let combined = [];
          if (activePostFilter === 'LIVE') combined = mergedPosts.filter(p => p.is_live);
          else if (activePostFilter === 'WORKSPACE') combined = mergedPosts.filter(p => !p.is_live);
          else combined = mergedPosts;

          if (combined.length === 0) {
            return (
              <div className="py-12 text-center text-slate-400 text-sm">
                <FacebookIcon className="w-12 h-12 text-slate-200 mx-auto mb-3" />
                <p className="font-bold text-slate-700 text-base">No posts found for this view</p>
                <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                  Click "Upload Post" above to publish to your Facebook Page or save to your workspace.
                </p>
                <button
                  onClick={() => {
                    setFormData(prev => ({ ...prev, publish_live: isConnected }));
                    setIsPublishModalOpen(true);
                  }}
                  className="mt-4 inline-flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white rounded-xl text-xs font-bold hover:bg-blue-700 transition shadow-md shadow-blue-500/20"
                >
                  <Plus className="w-4 h-4" />
                  Upload Post
                </button>
              </div>
            );
          }

          return (
            <div className="space-y-4">
              {combined.map((post) => (
                <div key={post.id} className="p-4 border border-slate-200 rounded-2xl bg-white hover:border-slate-300 transition flex flex-col sm:flex-row sm:items-center justify-between gap-4 group">
                  <div className="flex items-start gap-4 max-w-xl">
                    {post.media_url ? (
                      <img
                        src={post.media_url}
                        alt="Attachment"
                        className="w-20 h-20 rounded-xl object-cover bg-slate-100 flex-shrink-0 border border-slate-200"
                        onError={(e) => { e.target.style.display = 'none'; }}
                      />
                    ) : (
                      <div className="w-12 h-12 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center flex-shrink-0">
                        <FacebookIcon className="w-6 h-6" />
                      </div>
                    )}

                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        {post.is_live ? (
                          <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold bg-blue-50 text-blue-700 border border-blue-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-blue-600 animate-pulse"></span>
                            Live on Facebook
                          </span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-slate-100 text-slate-600">
                            Workspace Draft
                          </span>
                        )}
                        {post.permalink && (
                          <a
                            href={post.permalink}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-blue-600 hover:underline inline-flex items-center gap-1 font-semibold"
                          >
                            <ExternalLink className="w-3 h-3" />
                            View on Facebook
                          </a>
                        )}
                      </div>

                      <p className="text-sm text-slate-800 font-medium line-clamp-3">
                        {post.caption || <span className="text-slate-400 italic">No text content</span>}
                      </p>

                      <div className="text-[11px] text-slate-400">
                        Published: {post.published_at ? new Date(post.published_at).toLocaleString() : 'Just now'}
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 self-start sm:self-auto">
                    <div className="flex items-center gap-3 text-xs font-bold text-slate-600 bg-slate-50 px-3.5 py-2 rounded-xl border border-slate-100">
                      <span className="flex items-center gap-1.5 text-blue-600" title="Exact Reactions / Likes">
                        <ThumbsUp className="w-4 h-4 fill-blue-50 text-blue-600" />
                        {post.likes_count.toLocaleString()}
                      </span>
                      <button
                        onClick={() => handleOpenComments(post)}
                        className="flex items-center gap-1.5 text-emerald-600 hover:text-emerald-800 transition cursor-pointer"
                        title="View Comments & Replies"
                      >
                        <MessageCircle className="w-4 h-4" />
                        {post.comments_count.toLocaleString()}
                      </button>
                      <span className="flex items-center gap-1.5 text-indigo-600" title="Shares">
                        <Share2 className="w-4 h-4" />
                        {post.shares_count.toLocaleString()}
                      </span>
                    </div>

                    <button
                      onClick={() => handleOpenComments(post)}
                      className="px-3 py-1.5 text-xs font-bold rounded-xl bg-blue-50 text-blue-700 hover:bg-blue-100 transition border border-blue-200/60"
                    >
                      Comments ({post.comments_count})
                    </button>

                    {!post.is_live && (
                      <button
                        onClick={() => handleDeletePost(post.id)}
                        disabled={deletingId === post.id}
                        className="p-2 text-slate-400 hover:text-rose-600 rounded-lg hover:bg-slate-100 transition"
                        title="Delete post"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          );
        })()}
      </div>

      {/* Upload Post Modal */}
      {isPublishModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg overflow-hidden border border-slate-200 animate-in fade-in zoom-in-95 duration-150">
            <div className="p-5 border-b border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <FacebookIcon className="w-5 h-5 text-blue-600" />
                <h3 className="font-bold text-slate-900">
                  {isConnected ? 'Create / Upload Facebook Post' : 'Upload Normal Post'}
                </h3>
              </div>
              <button onClick={() => setIsPublishModalOpen(false)} className="text-slate-400 hover:text-slate-600 p-1">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handlePublish} className="p-5 space-y-4">
              {isConnected && pages.length > 1 && (
                <div>
                  <label className="block text-xs font-bold text-slate-700 mb-1">Target Page</label>
                  <select
                    value={formData.page_id}
                    onChange={(e) => setFormData(prev => ({ ...prev, page_id: e.target.value }))}
                    className="w-full text-xs px-3.5 py-2.5 rounded-xl border border-slate-200 focus:outline-none focus:border-blue-500"
                  >
                    {pages.map(p => (
                      <option key={p.account_id} value={p.account_id}>{p.account_name}</option>
                    ))}
                  </select>
                </div>
              )}

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Post Content / Status
                </label>
                <textarea
                  rows="3"
                  placeholder="Share updates, announcements, or product notes..."
                  value={formData.message}
                  onChange={(e) => setFormData(prev => ({ ...prev, message: e.target.value }))}
                  className="w-full text-xs px-3.5 py-2.5 rounded-xl border border-slate-200 focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100"
                />
              </div>

              {/* Optional Image Attachment */}
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1.5">
                  Image Attachment (Optional)
                </label>
                {filePreview ? (
                  <div className="relative rounded-xl overflow-hidden border border-slate-200 bg-slate-50">
                    <img src={filePreview} alt="Preview" className="w-full h-40 object-cover" />
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
                  <label className="border-2 border-dashed border-slate-200 hover:border-blue-500 rounded-xl p-4 flex items-center justify-center gap-2 cursor-pointer bg-slate-50 hover:bg-blue-50/20 transition">
                    <span className="text-xs font-bold text-slate-600">+ Choose Image to Attach</span>
                    <input
                      type="file"
                      accept="image/*"
                      onChange={handleFileChange}
                      className="hidden"
                    />
                  </label>
                )}
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1">
                  Link URL (Optional)
                </label>
                <input
                  type="url"
                  placeholder="https://example.com/blog/market-report"
                  value={formData.link}
                  onChange={(e) => setFormData(prev => ({ ...prev, link: e.target.value }))}
                  className="w-full text-xs px-3.5 py-2.5 rounded-xl border border-slate-200 focus:outline-none focus:border-blue-500"
                />
              </div>

              {/* Target Platforms: Universal Cross-Posting */}
              <div>
                <label className="block text-xs font-bold text-slate-700 mb-1.5 flex items-center justify-between">
                  <span>Publish Destinations</span>
                  {targetPlatforms.facebook && targetPlatforms.instagram && (
                    <span className="text-[10px] font-bold text-blue-700 bg-blue-50 px-2 py-0.5 rounded-full border border-blue-200">
                      ⚡ Universal Post Active
                    </span>
                  )}
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
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
                          {pages?.[0]?.account_name || 'Market Intel DB'}
                        </div>
                      </div>
                    </div>
                  </label>

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
                          {igStatus?.account?.account_username ? `@${igStatus.account.account_username}` : 'Instagram Account'}
                        </div>
                      </div>
                    </div>
                  </label>
                </div>
              </div>

              {/* Live vs Normal Post Mode */}
              {isConnected ? (
                <label className="flex items-start gap-3 cursor-pointer bg-slate-50 p-3.5 rounded-xl border border-slate-200 hover:bg-slate-100/60 transition">
                  <input
                    type="checkbox"
                    checked={formData.publish_live}
                    onChange={(e) => setFormData(prev => ({ ...prev, publish_live: e.target.checked }))}
                    className="mt-0.5 rounded text-blue-600 focus:ring-blue-500 w-4 h-4"
                  />
                  <div className="flex-1">
                    <div className="text-xs font-bold text-slate-900 flex items-center gap-1.5">
                      Publish live via Meta Graph API
                    </div>
                    <div className="text-[10px] text-slate-500 mt-0.5 leading-relaxed">
                      {targetPlatforms.facebook && targetPlatforms.instagram
                        ? 'This post will be broadcast live to both your Facebook Page and Instagram account simultaneously.'
                        : targetPlatforms.facebook
                          ? 'This post will be published live to your official Facebook Page.'
                          : 'This post will be published live to your official Instagram account.'}
                    </div>
                  </div>
                </label>
              ) : (
                <div className="bg-slate-50 border border-slate-200 p-3 rounded-xl text-[11px] text-slate-600">
                  <span className="font-bold text-slate-800">Normal Post Mode:</span> This post will be stored and organized directly in your Market Intel DB feed.
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
                  className="inline-flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-bold text-white bg-gradient-to-r from-blue-600 via-indigo-600 to-purple-600 hover:opacity-90 transition shadow-sm disabled:opacity-50"
                >
                  <Send className="w-3.5 h-3.5" />
                  {publishing
                    ? 'Publishing live...'
                    : targetPlatforms.facebook && targetPlatforms.instagram
                      ? '🚀 Publish to Facebook & Instagram'
                      : targetPlatforms.facebook
                        ? 'Publish to Facebook'
                        : 'Publish to Instagram'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Facebook Comments & Discussion Modal */}
      {selectedPostForComments && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-lg overflow-hidden border border-slate-200 flex flex-col max-h-[85vh] animate-in fade-in zoom-in-95 duration-150">
            {/* Modal Header */}
            <div className="p-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-blue-100 text-blue-600 flex items-center justify-center">
                  <MessageCircle className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-sm text-slate-900">Post Comments & Engagement</h3>
                  <div className="flex items-center gap-3 text-[11px] text-slate-500 mt-0.5">
                    <span className="flex items-center gap-1 font-semibold text-blue-600">
                      <ThumbsUp className="w-3 h-3 fill-blue-100 text-blue-600" />
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
                <span className="font-bold text-slate-900 shrink-0">Status:</span>
                <p className="line-clamp-2 italic text-slate-700">"{selectedPostForComments.caption}"</p>
              </div>
            )}


            {/* Comments List */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3.5 divide-y divide-slate-100">
              {loadingComments ? (
                <div className="py-12 text-center text-slate-400 text-xs flex flex-col items-center gap-2">
                  <RefreshCw className="w-5 h-5 animate-spin text-blue-600" />
                  Loading comments from Facebook...
                </div>
              ) : commentsList.length === 0 ? (
                <div className="py-12 text-center text-slate-400 text-xs space-y-3">
                  <MessageCircle className="w-8 h-8 text-slate-300 mx-auto" />
                  <div>
                    <p className="font-bold text-slate-700 text-sm">No comments loaded from API</p>
                    <p className="text-[11px] text-slate-500 mt-1 max-w-xs mx-auto">
                      Meta limits public comment reading to apps with Meta App Review. You can view all live comments and conversations directly on Facebook.
                    </p>
                  </div>
                  {selectedPostForComments.permalink && (
                    <a
                      href={selectedPostForComments.permalink}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 px-4 py-2 bg-blue-50 text-blue-700 hover:bg-blue-100 rounded-xl text-xs font-bold transition border border-blue-200"
                    >
                      <ExternalLink className="w-3.5 h-3.5" />
                      View Comments on Facebook
                    </a>
                  )}
                </div>
              ) : (
                commentsList.map((c) => (
                  <div key={c.id} className="pt-3 first:pt-0 space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-start gap-2.5">
                        <div className="w-7 h-7 rounded-full bg-blue-600 text-white font-bold text-xs flex items-center justify-center shrink-0">
                          {(c.name || c.username || 'F').charAt(0).toUpperCase()}
                        </div>
                        <div>
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="font-bold text-xs text-slate-900">
                              {c.name || c.username || 'Facebook User'}
                            </span>
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
                          <span className="flex items-center gap-1 text-[10px] text-blue-600 font-bold">
                            <ThumbsUp className="w-3 h-3 fill-blue-50" /> {c.like_count}
                          </span>
                        )}
                        <button
                          onClick={() => {
                            setReplyingToComment(c);
                            setCommentReplyText(`@${c.name || c.username} `);
                          }}
                          className="text-[11px] font-bold text-blue-600 hover:text-blue-800 transition"
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
                              <span>{r.name || r.username || 'User'}</span>
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

            {/* Reply Composer */}
            <form onSubmit={handleSendCommentReply} className="p-3 border-t border-slate-100 bg-slate-50/50 space-y-2">
              {replyingToComment && (
                <div className="flex items-center justify-between text-[11px] text-blue-700 bg-blue-50 px-2.5 py-1 rounded-lg">
                  <span>Replying to <strong>{replyingToComment.username}</strong></span>
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
                  placeholder={replyingToComment ? `Write a reply to ${replyingToComment.username}...` : "Write a public comment/reply..."}
                  value={commentReplyText}
                  onChange={(e) => setCommentReplyText(e.target.value)}
                  className="flex-1 text-xs px-3.5 py-2 rounded-xl border border-slate-200 focus:outline-none focus:border-blue-500 bg-white"
                />
                <button
                  type="submit"
                  disabled={submittingComment || !commentReplyText.trim()}
                  className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-blue-600 text-white font-bold text-xs hover:bg-blue-700 transition shadow-sm disabled:opacity-50"
                >
                  <Send className={`w-3.5 h-3.5 ${submittingComment ? 'animate-spin' : ''}`} />
                  Reply
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default FacebookPage;
