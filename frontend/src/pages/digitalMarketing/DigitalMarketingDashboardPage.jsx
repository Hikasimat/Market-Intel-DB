import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'react-toastify';
import { 
  LayoutDashboard, 
  BarChart2, 
  TrendingUp, 
  CheckCircle2, 
  AlertCircle, 
  ArrowRight, 
  Share2, 
  Calendar,
  Layers,
  Sparkles,
  ExternalLink,
  RefreshCw,
  Globe
} from 'lucide-react';
import api from '../../services/api';
import { InstagramIcon, FacebookIcon, TwitterXIcon } from '../../components/common/SocialIcons';

const DigitalMarketingDashboardPage = () => {
  const [loading, setLoading] = useState(true);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const fetchDashboardData = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get('/digital-marketing/dashboard/');
      setData(res.data);
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to load marketing dashboard data.';
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const platforms = data?.platforms || {};
  const recentPosts = data?.recent_posts || [];
  const insights = data?.aggregated_insights || { paid_overview: {}, platforms: {}, organic_overview: {} };

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="p-2 bg-blue-100 text-blue-700 rounded-xl">
              <LayoutDashboard className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl font-black text-slate-900 tracking-tight">
                Digital Marketing Workspace
              </h1>
              <p className="text-sm text-slate-500 mt-0.5">
                Manage professional social channels, official content publishing, and advertising insights.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Link
            to="/digital-marketing/instagram"
            className="inline-flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-pink-600 via-purple-600 to-blue-600 hover:opacity-90 text-white rounded-xl text-xs font-bold transition shadow-sm"
          >
            <Sparkles className="w-4 h-4" />
            Universal Post (IG + FB)
          </Link>

          <button
            onClick={fetchDashboardData}
            disabled={loading}
            className="inline-flex items-center gap-2 px-4 py-2 border border-slate-200 rounded-xl text-xs font-bold text-slate-700 bg-white hover:bg-slate-50 transition shadow-sm disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-red-700 text-sm flex items-center gap-3">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Platform Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-5">
        {/* Instagram Card */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm hover:border-slate-300 transition-all flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="w-10 h-10 rounded-xl bg-pink-50 text-pink-600 flex items-center justify-center">
                <InstagramIcon className="w-5 h-5" />
              </div>
              <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold ${
                platforms.instagram?.is_connected
                  ? 'bg-emerald-100 text-emerald-800'
                  : 'bg-slate-100 text-slate-600'
              }`}>
                {platforms.instagram?.is_connected ? 'Connected' : 'Not Connected'}
              </span>
            </div>
            <h3 className="text-base font-bold text-slate-900">Instagram</h3>
            <p className="text-xs text-slate-500 mt-1 line-clamp-1">
              {platforms.instagram?.is_connected 
                ? `@${platforms.instagram.account_username || 'Professional Account'}`
                : 'Instagram Professional (Business / Creator)'}
            </p>
            <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
              <span>Followers</span>
              <span className="font-bold text-slate-800">
                {platforms.instagram?.followers_count?.toLocaleString() || '0'}
              </span>
            </div>
          </div>
          <Link
            to="/digital-marketing/instagram"
            className="mt-4 inline-flex items-center justify-between w-full text-xs font-bold text-pink-600 hover:text-pink-700 pt-2 border-t border-slate-50"
          >
            <span>Open Instagram Module</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>

        {/* Facebook Card */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm hover:border-slate-300 transition-all flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center">
                <FacebookIcon className="w-5 h-5" />
              </div>
              <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold ${
                platforms.facebook?.is_connected
                  ? 'bg-emerald-100 text-emerald-800'
                  : 'bg-slate-100 text-slate-600'
              }`}>
                {platforms.facebook?.is_connected ? 'Connected' : 'Not Connected'}
              </span>
            </div>
            <h3 className="text-base font-bold text-slate-900">Facebook</h3>
            <p className="text-xs text-slate-500 mt-1 line-clamp-1">
              {platforms.facebook?.is_connected 
                ? platforms.facebook.account_name || 'Authorized Page'
                : 'Facebook Pages & Management'}
            </p>
            <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
              <span>Page Likes</span>
              <span className="font-bold text-slate-800">
                {platforms.facebook?.fan_count?.toLocaleString() || '0'}
              </span>
            </div>
          </div>
          <Link
            to="/digital-marketing/facebook"
            className="mt-4 inline-flex items-center justify-between w-full text-xs font-bold text-blue-600 hover:text-blue-700 pt-2 border-t border-slate-50"
          >
            <span>Open Facebook Module</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>

        {/* Twitter / X Card */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm hover:border-slate-300 transition-all flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="w-10 h-10 rounded-xl bg-slate-900 text-white flex items-center justify-center">
                <TwitterXIcon className="w-4 h-4" />
              </div>
              <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold ${
                platforms.twitter?.is_connected
                  ? 'bg-emerald-100 text-emerald-800'
                  : 'bg-slate-100 text-slate-600'
              }`}>
                {platforms.twitter?.is_connected ? 'Connected' : 'Not Connected'}
              </span>
            </div>
            <h3 className="text-base font-bold text-slate-900">Twitter / X</h3>
            <p className="text-xs text-slate-500 mt-1 line-clamp-1">
              {platforms.twitter?.is_connected 
                ? `@${platforms.twitter.account_username}`
                : 'Official X API v2 Publishing'}
            </p>
            <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
              <span>Followers</span>
              <span className="font-bold text-slate-800">
                {platforms.twitter?.followers_count?.toLocaleString() || '0'}
              </span>
            </div>
          </div>
          <Link
            to="/digital-marketing/twitter"
            className="mt-4 inline-flex items-center justify-between w-full text-xs font-bold text-slate-900 hover:text-slate-700 pt-2 border-t border-slate-50"
          >
            <span>Open Twitter / X Module</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>

        {/* Ads & Insights Card */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm hover:border-slate-300 transition-all flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="w-10 h-10 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center">
                <BarChart2 className="w-5 h-5" />
              </div>
              <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-indigo-100 text-indigo-800">
                Reporting
              </span>
            </div>
            <h3 className="text-base font-bold text-slate-900">Ads & Insights</h3>
            <p className="text-xs text-slate-500 mt-1">
              Meta Ads & X Ads Performance
            </p>
            <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
              <span>Active Campaigns</span>
              <span className="font-bold text-slate-800">
                {insights.paid_overview?.active_campaigns_count || '0'}
              </span>
            </div>
          </div>
          <Link
            to="/digital-marketing/ads-insights"
            className="mt-4 inline-flex items-center justify-between w-full text-xs font-bold text-indigo-600 hover:text-indigo-700 pt-2 border-t border-slate-50"
          >
            <span>Open Ads & Insights</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>

        {/* Headless CMS Card */}
        <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm hover:border-slate-300 transition-all flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 text-white flex items-center justify-center shadow-xs">
                <Globe className="w-5 h-5" />
              </div>
              <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800">
                Live Gateway
              </span>
            </div>
            <h3 className="text-base font-bold text-slate-900">Headless CMS</h3>
            <p className="text-xs text-slate-500 mt-1">
              Multi-Tenant Blogs & SEO Suite
            </p>
            <div className="mt-4 pt-3 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
              <span>Cloudflare Tunnel</span>
              <span className="font-bold text-emerald-600">
                Active 🟢
              </span>
            </div>
          </div>
          <Link
            to="/digital-marketing/cms"
            className="mt-4 inline-flex items-center justify-between w-full text-xs font-bold text-blue-600 hover:text-blue-700 pt-2 border-t border-slate-50"
          >
            <span>Open CMS Suite</span>
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>

      {/* Summary KPI Strip */}
      <div className="bg-gradient-to-r from-blue-600 to-indigo-700 rounded-2xl p-6 text-white shadow-md">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-blue-200" />
            <h2 className="text-lg font-bold">Cross-Platform Activity Summary</h2>
          </div>
          <span className="text-xs bg-white/20 px-3 py-1 rounded-full font-medium text-white">
            Official Developer API Engine
          </span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
            <div className="text-xs text-blue-200 font-medium">Organic Publications</div>
            <div className="text-2xl font-black mt-1">
              {insights.organic_overview?.total_posts || 0}
            </div>
            <div className="text-[11px] text-blue-100/70 mt-1">Across all connected feeds</div>
          </div>

          <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
            <div className="text-xs text-blue-200 font-medium">Total Organic Engagement</div>
            <div className="text-2xl font-black mt-1">
              {(insights.organic_overview?.total_engagement || 0).toLocaleString()}
            </div>
            <div className="text-[11px] text-blue-100/70 mt-1">Reactions, replies, shares</div>
          </div>

          <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
            <div className="text-xs text-blue-200 font-medium">Paid Ad Spend</div>
            <div className="text-2xl font-black mt-1">
              ${parseFloat(insights.paid_overview?.total_spend || '0').toFixed(2)}
            </div>
            <div className="text-[11px] text-blue-100/70 mt-1">Meta Ads & X Ads (read-only)</div>
          </div>

          <div className="bg-white/10 rounded-xl p-4 backdrop-blur-sm border border-white/10">
            <div className="text-xs text-blue-200 font-medium">Paid Impressions</div>
            <div className="text-2xl font-black mt-1">
              {(insights.paid_overview?.total_impressions || 0).toLocaleString()}
            </div>
            <div className="text-[11px] text-blue-100/70 mt-1">
              CTR: {insights.paid_overview?.avg_ctr || '0.000'}%
            </div>
          </div>
        </div>
      </div>

      {/* Recent Activity Table */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-5 border-b border-slate-100 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Share2 className="w-5 h-5 text-indigo-600" />
            <h3 className="font-bold text-slate-900">Recent Social Activity</h3>
          </div>
          <span className="text-xs text-slate-400">Chronological feed of recorded content</span>
        </div>

        {recentPosts.length === 0 ? (
          <div className="py-12 text-center text-slate-500 text-sm">
            <Layers className="w-10 h-10 text-slate-300 mx-auto mb-2" />
            No social content published yet. Connect a channel above to begin publishing.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-100 text-sm">
              <thead className="bg-slate-50 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                <tr>
                  <th className="px-6 py-3 text-left">Platform</th>
                  <th className="px-6 py-3 text-left">Content</th>
                  <th className="px-6 py-3 text-left">Status</th>
                  <th className="px-6 py-3 text-left">Engagement</th>
                  <th className="px-6 py-3 text-right">Published</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {recentPosts.map((post) => (
                  <tr key={post.id} className="hover:bg-slate-50 transition">
                    <td className="px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-2">
                        {post.platform === 'INSTAGRAM' && (
                          <div className="w-7 h-7 rounded-lg bg-pink-100 text-pink-600 flex items-center justify-center">
                            <InstagramIcon className="w-3.5 h-3.5" />
                          </div>
                        )}
                        {post.platform === 'FACEBOOK' && (
                          <div className="w-7 h-7 rounded-lg bg-blue-100 text-blue-600 flex items-center justify-center">
                            <FacebookIcon className="w-3.5 h-3.5" />
                          </div>
                        )}
                        {post.platform === 'TWITTER' && (
                          <div className="w-7 h-7 rounded-lg bg-slate-900 text-white flex items-center justify-center">
                            <TwitterXIcon className="w-3 h-3" />
                          </div>
                        )}
                        <span className="font-bold text-xs text-slate-800">{post.platform}</span>
                      </div>
                    </td>
                    <td className="px-6 py-4 max-w-xs truncate text-slate-700">
                      {post.caption || <span className="text-slate-400 italic">No text</span>}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                        post.status === 'PUBLISHED' 
                          ? 'bg-emerald-100 text-emerald-800' 
                          : post.status === 'DRAFT'
                          ? 'bg-slate-100 text-slate-700'
                          : 'bg-rose-100 text-rose-800'
                      }`}>
                        {post.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-xs text-slate-600">
                      {post.metrics ? (
                        <span>
                          {post.metrics.likes || post.metrics.like_count || post.metrics.reactions_count || 0} Likes · {post.metrics.comments || post.metrics.comments_count || post.metrics.reply_count || 0} Comments
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-xs text-slate-500">
                      {post.published_at ? new Date(post.published_at).toLocaleDateString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default DigitalMarketingDashboardPage;
