import React, { useState, useEffect } from 'react';
import { toast } from 'react-toastify';
import { 
  BarChart2, 
  TrendingUp, 
  DollarSign, 
  MousePointerClick, 
  Eye, 
  Target, 
  Calendar, 
  RefreshCw, 
  AlertCircle, 
  Layers,
  Sparkles,
  Info,
  Shield,
  HelpCircle,
  Filter
} from 'lucide-react';
import api from '../../services/api';
import { FacebookIcon, InstagramIcon, TwitterXIcon } from '../../components/common/SocialIcons';

const AdsInsightsPage = () => {
  const [loading, setLoading] = useState(true);
  const [overview, setOverview] = useState(null);
  const [campaigns, setCampaigns] = useState([]);
  const [selectedPlatform, setSelectedPlatform] = useState('ALL'); // ALL, META_ADS, TWITTER_ADS
  const [dateRange, setDateRange] = useState('30d'); // 7d, 30d, 90d

  const fetchAdsData = async () => {
    setLoading(true);
    try {
      const [overviewRes, campaignsRes] = await Promise.all([
        api.get('/digital-marketing/ads/overview/'),
        api.get('/digital-marketing/ads/campaigns/', {
          params: selectedPlatform !== 'ALL' ? { platform: selectedPlatform } : {}
        })
      ]);
      setOverview(overviewRes.data);
      setCampaigns(campaignsRes.data.campaigns || []);
    } catch (err) {
      toast.error('Failed to load advertising insights.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAdsData();
  }, [selectedPlatform]);

  const paid = overview?.paid_overview || {};
  const platforms = overview?.platforms || {};
  const organic = overview?.organic_overview || {};

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-12 h-12 rounded-2xl bg-indigo-600 text-white flex items-center justify-center shadow-md shadow-indigo-500/20">
            <BarChart2 className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-2">
              Ads & Cross-Platform Insights
            </h1>
            <p className="text-sm text-slate-500">
              Aggregated reporting for Meta Ads (Facebook & Instagram), X Ads, and Organic social performance.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {/* Date range filter */}
          <div className="flex items-center bg-white border border-slate-200 rounded-xl p-1 text-xs font-bold text-slate-700 shadow-sm">
            <button
              onClick={() => setDateRange('7d')}
              className={`px-3 py-1.5 rounded-lg transition ${dateRange === '7d' ? 'bg-indigo-600 text-white' : 'hover:bg-slate-50'}`}
            >
              7 Days
            </button>
            <button
              onClick={() => setDateRange('30d')}
              className={`px-3 py-1.5 rounded-lg transition ${dateRange === '30d' ? 'bg-indigo-600 text-white' : 'hover:bg-slate-50'}`}
            >
              30 Days
            </button>
            <button
              onClick={() => setDateRange('90d')}
              className={`px-3 py-1.5 rounded-lg transition ${dateRange === '90d' ? 'bg-indigo-600 text-white' : 'hover:bg-slate-50'}`}
            >
              Quarter
            </button>
          </div>

          <button
            onClick={fetchAdsData}
            disabled={loading}
            className="inline-flex items-center gap-2 px-4 py-2 border border-slate-200 rounded-xl text-xs font-bold text-slate-700 bg-white hover:bg-slate-50 transition shadow-sm disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Strict Security Policy Notice */}
      <div className="bg-slate-900 text-white rounded-2xl p-5 shadow-sm flex items-start gap-3">
        <Shield className="w-5 h-5 text-indigo-400 flex-shrink-0 mt-0.5" />
        <div className="text-xs space-y-1">
          <div className="font-bold text-white text-sm">Protected Read-Only Analytics Workspace</div>
          <p className="text-slate-300">
            This module provides analytical reporting across official advertising APIs. 
            In compliance with security boundaries, <strong>autonomous ad expenditure, campaign budgeting, and credit card charges are strictly disabled</strong>.
            All metrics reflect official API responses without fabrication.
          </p>
        </div>
      </div>

      {/* SECTION 1: PAID ADVERTISING KPI OVERVIEW */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
            <DollarSign className="w-4 h-4 text-emerald-600" />
            Paid Advertising Performance
          </h2>
          <span className="text-xs font-medium text-slate-400">Aggregated Meta Ads & X Ads</span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
            <div className="text-xs text-slate-400 font-medium">Total Spend</div>
            <div className="text-xl font-bold text-slate-900 mt-1">
              ${parseFloat(paid.total_spend || '0').toFixed(2)}
            </div>
            <div className="text-[10px] text-slate-400 mt-1">Authorized ad accounts</div>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
            <div className="text-xs text-slate-400 font-medium">Impressions</div>
            <div className="text-xl font-bold text-slate-900 mt-1">
              {(paid.total_impressions || 0).toLocaleString()}
            </div>
            <div className="text-[10px] text-slate-400 mt-1">Cross-platform views</div>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
            <div className="text-xs text-slate-400 font-medium">Total Clicks</div>
            <div className="text-xl font-bold text-slate-900 mt-1">
              {(paid.total_clicks || 0).toLocaleString()}
            </div>
            <div className="text-[10px] text-slate-400 mt-1">Ad link clicks</div>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
            <div className="text-xs text-slate-400 font-medium">Average CPC</div>
            <div className="text-xl font-bold text-slate-900 mt-1">
              ${paid.avg_cpc || '0.0000'}
            </div>
            <div className="text-[10px] text-slate-400 mt-1">Cost per link click</div>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
            <div className="text-xs text-slate-400 font-medium">Click-Through (CTR)</div>
            <div className="text-xl font-bold text-slate-900 mt-1">
              {paid.avg_ctr || '0.000'}%
            </div>
            <div className="text-[10px] text-slate-400 mt-1">Clicks ÷ Impressions</div>
          </div>

          <div className="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
            <div className="text-xs text-slate-400 font-medium">Conversions</div>
            <div className="text-xl font-bold text-slate-900 mt-1">
              {(paid.total_conversions || 0).toLocaleString()}
            </div>
            <div className="text-[10px] text-slate-400 mt-1">Pixel & post events</div>
          </div>
        </div>
      </div>

      {/* SECTION 2: ADVERTISING PLATFORM SEPARATION (META ADS vs X ADS) */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Meta Ads Box */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center">
                <FacebookIcon className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-bold text-slate-900 text-sm">Meta Marketing API (Ads)</h3>
                <p className="text-[11px] text-slate-500">Facebook & Instagram Sponsored Campaigns</p>
              </div>
            </div>

            <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold ${
              platforms.meta_ads?.is_connected ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'
            }`}>
              {platforms.meta_ads?.is_connected ? 'Connected' : 'Not Connected'}
            </span>
          </div>

          {platforms.meta_ads?.is_connected ? (
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="p-3 bg-slate-50 rounded-xl">
                <div className="text-[11px] text-slate-400 font-medium">Spend</div>
                <div className="text-base font-bold text-slate-800 mt-0.5">${platforms.meta_ads?.spend}</div>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl">
                <div className="text-[11px] text-slate-400 font-medium">Impressions</div>
                <div className="text-base font-bold text-slate-800 mt-0.5">{(platforms.meta_ads?.impressions || 0).toLocaleString()}</div>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl">
                <div className="text-[11px] text-slate-400 font-medium">Clicks</div>
                <div className="text-base font-bold text-slate-800 mt-0.5">{(platforms.meta_ads?.clicks || 0).toLocaleString()}</div>
              </div>
            </div>
          ) : (
            <div className="p-4 bg-slate-50 rounded-xl border border-dashed border-slate-200 text-xs text-slate-500 space-y-1">
              <p>Meta Ad Account not linked. Connect Facebook Page & Ad Account with <code>ads_read</code> permission to view sponsored campaigns.</p>
            </div>
          )}
        </div>

        {/* X Ads Box */}
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-slate-900 text-white flex items-center justify-center">
                <TwitterXIcon className="w-4 h-4" />
              </div>
              <div>
                <h3 className="font-bold text-slate-900 text-sm">X Ads API</h3>
                <p className="text-[11px] text-slate-500">Twitter / X Promoted Campaigns</p>
              </div>
            </div>

            <span className={`px-2.5 py-0.5 rounded-full text-xs font-bold ${
              platforms.x_ads?.is_connected ? 'bg-emerald-100 text-emerald-800' : 'bg-slate-100 text-slate-600'
            }`}>
              {platforms.x_ads?.is_connected ? 'Connected' : 'Not Connected'}
            </span>
          </div>

          {platforms.x_ads?.is_connected ? (
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="p-3 bg-slate-50 rounded-xl">
                <div className="text-[11px] text-slate-400 font-medium">Spend</div>
                <div className="text-base font-bold text-slate-800 mt-0.5">${platforms.x_ads?.spend}</div>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl">
                <div className="text-[11px] text-slate-400 font-medium">Impressions</div>
                <div className="text-base font-bold text-slate-800 mt-0.5">{(platforms.x_ads?.impressions || 0).toLocaleString()}</div>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl">
                <div className="text-[11px] text-slate-400 font-medium">Clicks</div>
                <div className="text-base font-bold text-slate-800 mt-0.5">{(platforms.x_ads?.clicks || 0).toLocaleString()}</div>
              </div>
            </div>
          ) : (
            <div className="p-4 bg-slate-50 rounded-xl border border-dashed border-slate-200 text-xs text-slate-500 space-y-1">
              <p>X Ads API access requires an authorized X Ads Account. Unconnected or missing Ads API product permissions keep operations safely disabled.</p>
            </div>
          )}
        </div>
      </div>

      {/* SECTION 3: ORGANIC SOCIAL INSIGHTS (SEPARATED FROM PAID ADS) */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <TrendingUp className="w-5 h-5 text-indigo-600" />
            <h3 className="font-bold text-slate-900 text-base">Organic Social Insights</h3>
          </div>
          <span className="text-xs bg-slate-100 text-slate-600 px-3 py-1 rounded-full font-bold">
            Unpaid Distribution & Reach
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 text-center">
          <div className="p-4 bg-slate-50 rounded-xl border border-slate-100">
            <div className="text-xs text-slate-400 font-medium">Total Organic Posts</div>
            <div className="text-2xl font-bold text-slate-900 mt-1">{organic.total_posts || 0}</div>
          </div>
          <div className="p-4 bg-pink-50/50 rounded-xl border border-pink-100">
            <div className="text-xs text-pink-600 font-medium">Instagram Feed Posts</div>
            <div className="text-2xl font-bold text-slate-900 mt-1">{organic.instagram_posts || 0}</div>
          </div>
          <div className="p-4 bg-blue-50/50 rounded-xl border border-blue-100">
            <div className="text-xs text-blue-600 font-medium">Facebook Page Posts</div>
            <div className="text-2xl font-bold text-slate-900 mt-1">{organic.facebook_posts || 0}</div>
          </div>
          <div className="p-4 bg-slate-100/50 rounded-xl border border-slate-200">
            <div className="text-xs text-slate-700 font-medium">Twitter / X Tweets</div>
            <div className="text-2xl font-bold text-slate-900 mt-1">{organic.twitter_posts || 0}</div>
          </div>
        </div>
      </div>

      {/* SECTION 4: CAMPAIGN BREAKDOWN TABLE */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-5 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h3 className="font-bold text-slate-900 text-base">Advertising Campaigns & Delivery Status</h3>
            <p className="text-xs text-slate-500 mt-0.5">Reported via official platform advertising APIs</p>
          </div>

          {/* Platform filter tabs */}
          <div className="flex items-center gap-2 bg-slate-100 p-1 rounded-xl text-xs font-bold text-slate-600">
            <button
              onClick={() => setSelectedPlatform('ALL')}
              className={`px-3 py-1.5 rounded-lg transition ${selectedPlatform === 'ALL' ? 'bg-white text-slate-900 shadow-sm' : ''}`}
            >
              All Providers
            </button>
            <button
              onClick={() => setSelectedPlatform('META_ADS')}
              className={`px-3 py-1.5 rounded-lg transition ${selectedPlatform === 'META_ADS' ? 'bg-white text-blue-600 shadow-sm' : ''}`}
            >
              Meta Ads
            </button>
            <button
              onClick={() => setSelectedPlatform('TWITTER_ADS')}
              className={`px-3 py-1.5 rounded-lg transition ${selectedPlatform === 'TWITTER_ADS' ? 'bg-white text-slate-900 shadow-sm' : ''}`}
            >
              X Ads
            </button>
          </div>
        </div>

        {campaigns.length === 0 ? (
          <div className="py-12 text-center text-slate-400 text-sm">
            <Layers className="w-10 h-10 text-slate-200 mx-auto mb-2" />
            No advertising campaigns detected on authorized ad accounts for this period.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-100 text-sm">
              <thead className="bg-slate-50 text-xs font-semibold text-slate-500 uppercase tracking-wider">
                <tr>
                  <th className="px-6 py-3 text-left">Platform</th>
                  <th className="px-6 py-3 text-left">Campaign Name</th>
                  <th className="px-6 py-3 text-left">Status</th>
                  <th className="px-6 py-3 text-right">Spend</th>
                  <th className="px-6 py-3 text-right">Impressions</th>
                  <th className="px-6 py-3 text-right">Clicks</th>
                  <th className="px-6 py-3 text-right">CPC</th>
                  <th className="px-6 py-3 text-right">CTR</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {campaigns.map((camp) => (
                  <tr key={camp.id} className="hover:bg-slate-50 transition">
                    <td className="px-6 py-4 whitespace-nowrap text-xs font-bold">
                      {camp.platform === 'META_ADS' ? (
                        <span className="text-blue-600 flex items-center gap-1.5">
                          <FacebookIcon className="w-4 h-4" /> Meta Ads
                        </span>
                      ) : (
                        <span className="text-slate-900 flex items-center gap-1.5">
                          <TwitterXIcon className="w-3.5 h-3.5" /> X Ads
                        </span>
                      )}
                    </td>
                    <td className="px-6 py-4 font-medium text-slate-900 text-xs">
                      {camp.name}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap">
                      <span className={`px-2 py-0.5 rounded text-[11px] font-bold ${
                        camp.status === 'ACTIVE'
                          ? 'bg-emerald-100 text-emerald-800'
                          : 'bg-slate-100 text-slate-600'
                      }`}>
                        {camp.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-xs font-bold text-slate-900">
                      ${parseFloat(camp.spend || '0').toFixed(2)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-xs text-slate-600">
                      {(camp.impressions || 0).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-xs text-slate-600">
                      {(camp.clicks || 0).toLocaleString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-xs text-slate-600">
                      ${camp.cpc || '0.00'}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-right text-xs text-slate-600">
                      {camp.ctr || '0.0'}%
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

export default AdsInsightsPage;
