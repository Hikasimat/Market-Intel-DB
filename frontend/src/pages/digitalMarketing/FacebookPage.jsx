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
  ExternalLink
} from 'lucide-react';
import api from '../../services/api';
import { FacebookIcon } from '../../components/common/SocialIcons';

const FacebookPage = () => {
  const [loading, setLoading] = useState(true);
  const [statusData, setStatusData] = useState(null);
  const [postsData, setPostsData] = useState({ database_posts: [], live_posts: [] });
  const [isPublishModalOpen, setIsPublishModalOpen] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [formData, setFormData] = useState({ message: '', link: '', page_id: '', publish_live: true });
  const [selectedFile, setSelectedFile] = useState(null);
  const [filePreview, setFilePreview] = useState('');
  const [deletingId, setDeletingId] = useState(null);
  const [disconnecting, setDisconnecting] = useState(false);

  const location = useLocation();
  const oauthProcessedRef = useRef(false);

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

  const loadData = async () => {
    setLoading(true);
    await Promise.all([fetchStatus(), fetchPosts()]);
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
      const res = await api.get('/digital-marketing/facebook/auth-url/');
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
    setPublishing(true);
    try {
      const data = new FormData();
      if (selectedFile) data.append('image_file', selectedFile);
      if (formData.message) data.append('message', formData.message);
      if (formData.link) data.append('link', formData.link);
      if (formData.page_id) data.append('page_id', formData.page_id);
      data.append('publish_live', isConnected && formData.publish_live ? 'true' : 'false');

      const res = await api.post('/digital-marketing/facebook/posts/', data, {
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
              Official Meta Graph API integration and workspace post management.
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
            <code className="block font-mono text-[11px] text-slate-700">META_REDIRECT_URI=http://localhost:5173/digital-marketing/facebook</code>
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
                      {page.metadata?.category || 'Business Page'} · <strong className="text-slate-700">{(page.metadata?.fan_count || 0).toLocaleString()}</strong> fans
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
          <li><strong>Supported:</strong> Publishing feed messages, link attachments, and retrieving reaction/comment insights.</li>
          <li><strong>API Permissions:</strong> <code>pages_show_list</code>, <code>pages_read_engagement</code>, <code>pages_manage_posts</code>.</li>
          <li><strong>Policy Note:</strong> Personal profiles are excluded by Meta Graph API policy. Management is strictly scoped to authorized business/brand Pages.</li>
        </ul>
      </div>

      {/* Recent Posts & Engagement Insights */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <Share2 className="w-5 h-5 text-blue-600" />
            <h3 className="font-bold text-slate-900 text-base">Page Posts & Engagement Insights</h3>
          </div>
          <span className="text-xs text-slate-400">
            {postsData.live_posts?.length > 0 ? 'Live from Facebook Graph API' : 'Published records'}
          </span>
        </div>

        {postsData.database_posts?.length === 0 && postsData.live_posts?.length === 0 ? (
          <div className="py-12 text-center text-slate-400 text-sm">
            <FacebookIcon className="w-12 h-12 text-slate-200 mx-auto mb-3" />
            No posts recorded for authorized Facebook Pages. Click "Upload Post" above to create or upload a post.
          </div>
        ) : (
          <div className="space-y-4">
            {postsData.database_posts.map((post) => (
              <div key={post.id} className="p-4 border border-slate-200 rounded-xl bg-white hover:border-slate-300 transition flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                <div className="flex items-start gap-4 max-w-xl">
                  {(post.media_display_url || (post.media_type === 'IMAGE' && post.media_url)) && (
                    <img
                      src={post.media_display_url || post.media_url}
                      alt="Attachment"
                      className="w-20 h-20 rounded-xl object-cover bg-slate-100 flex-shrink-0 border border-slate-200"
                      onError={(e) => { e.target.style.display = 'none'; }}
                    />
                  )}
                  <div className="space-y-1">
                    <p className="text-sm text-slate-800 font-medium">{post.caption || <span className="text-slate-400 italic">No text content</span>}</p>
                    {post.media_url && post.media_type !== 'IMAGE' && (
                      <a
                        href={post.media_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-blue-600 hover:underline flex items-center gap-1"
                      >
                        <Globe className="w-3.5 h-3.5" />
                        {post.media_url}
                      </a>
                    )}
                    <div className="text-[11px] text-slate-400">
                      Published: {post.published_at ? new Date(post.published_at).toLocaleString() : 'Just now'}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-3 self-start sm:self-auto">
                  <div className="flex items-center gap-4 text-xs font-bold text-slate-600 bg-slate-50 px-4 py-2 rounded-xl">
                    <span className="flex items-center gap-1.5" title="Reactions">
                      <ThumbsUp className="w-4 h-4 text-blue-600" />
                      {post.metrics?.reactions_count || 0}
                    </span>
                    <span className="flex items-center gap-1.5" title="Comments">
                      <MessageCircle className="w-4 h-4 text-emerald-600" />
                      {post.metrics?.comments_count || 0}
                    </span>
                    <span className="flex items-center gap-1.5" title="Shares">
                      <Share2 className="w-4 h-4 text-indigo-600" />
                      {post.metrics?.shares_count || 0}
                    </span>
                  </div>

                  <button
                    onClick={() => handleDeletePost(post.id)}
                    disabled={deletingId === post.id}
                    className="p-2 text-slate-400 hover:text-rose-600 rounded-lg hover:bg-slate-100 transition"
                    title="Delete post"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
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

              {/* Live vs Normal Post Mode */}
              {isConnected ? (
                <label className="flex items-center gap-2 cursor-pointer bg-blue-50/60 p-3 rounded-xl border border-blue-100">
                  <input
                    type="checkbox"
                    checked={formData.publish_live}
                    onChange={(e) => setFormData(prev => ({ ...prev, publish_live: e.target.checked }))}
                    className="rounded text-blue-600 focus:ring-blue-500"
                  />
                  <span className="text-xs font-bold text-blue-900">
                    Publish live to connected Facebook Page
                  </span>
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
                  className="inline-flex items-center gap-2 px-5 py-2 rounded-xl text-xs font-bold text-white bg-blue-600 hover:bg-blue-700 transition shadow-sm disabled:opacity-50"
                >
                  <Send className="w-3.5 h-3.5" />
                  {publishing ? 'Uploading...' : 'Upload Post'}
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
