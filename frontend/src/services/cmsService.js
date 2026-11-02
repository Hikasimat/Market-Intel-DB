/**
 * Native Market Intel CMS Service
 * Connects the Market Intel frontend directly to the internal Market Intel CMS endpoints.
 * Integrates:
 * 1. CMS Pages & XML Sitemaps
 * 2. Google Analytics (Page ID config, tracking snippets, detailed stats & live real-time hits)
 * 3. Google Search Console (Domain registration & verification, sitemaps, live URL inspection)
 * 4. Bing Webmaster Tools (API config, IndexNow live HTTP submission, sitemaps)
 * 5. Google Ads (Account config, campaigns, ad groups, keywords, budget updates & audit logs)
 */

import api from './api';

const wrapApi = async (promise) => {
  try {
    const res = await promise;
    return { ok: true, data: res.data, status: res.status };
  } catch (err) {
    const errorMsg =
      err.response?.data?.error ||
      err.response?.data?.detail ||
      err.response?.data?.message ||
      err.message ||
      'An unexpected error occurred';
    return { ok: false, error: errorMsg, status: err.response?.status, data: err.response?.data };
  }
};

const cmsService = {
  // ── CMS Overview ─────────────────────────────────────────────────────────────
  getOverview() {
    return wrapApi(api.get('/digital-marketing/cms/overview/'));
  },

  // ── CMS Website Pages ────────────────────────────────────────────────────────
  getPages(params = {}) {
    return wrapApi(api.get('/digital-marketing/cms/pages/', { params }));
  },

  createPage(payload) {
    return wrapApi(api.post('/digital-marketing/cms/pages/', payload));
  },

  updatePage(id, payload) {
    return wrapApi(api.put(`/digital-marketing/cms/pages/${id}/`, payload));
  },

  deletePage(id) {
    return wrapApi(api.delete(`/digital-marketing/cms/pages/${id}/`));
  },

  getSitemapXml() {
    return wrapApi(api.get('/digital-marketing/cms/sitemap.xml', { responseType: 'text' }));
  },

  // ── 1. Google Analytics (Essential Features & Real-Time) ─────────────────────
  getAnalyticsConfig(pageId = '') {
    const params = pageId ? { page_id: pageId } : {};
    return wrapApi(api.get('/digital-marketing/cms/analytics/config/', { params }));
  },

  updateAnalyticsConfig(payload) {
    return wrapApi(api.post('/digital-marketing/cms/analytics/config/', payload));
  },

  getAnalyticsDashboard(range = '30d') {
    return wrapApi(api.get('/digital-marketing/cms/analytics/dashboard/', { params: { range } }));
  },

  getRealtimeAnalytics() {
    return wrapApi(api.get('/digital-marketing/cms/analytics/realtime/'));
  },

  sendAnalyticsHit(payload) {
    return wrapApi(api.post('/digital-marketing/cms/analytics/collect/', payload));
  },

  recordAnalyticsStat(payload) {
    return wrapApi(api.post('/digital-marketing/cms/analytics/dashboard/', payload));
  },

  // ── 2. Google Search Console ─────────────────────────────────────────────────
  getSearchConsoleDashboard() {
    return wrapApi(api.get('/digital-marketing/cms/search-console/dashboard/'));
  },

  registerSearchConsoleDomain(payload) {
    return wrapApi(api.post('/digital-marketing/cms/search-console/domains/', payload));
  },

  verifySearchConsoleDomain(id, method = 'DNS_TXT') {
    return wrapApi(api.post(`/digital-marketing/cms/search-console/domains/${id}/verify/`, { method }));
  },

  deleteSearchConsoleDomain(id) {
    return wrapApi(api.delete(`/digital-marketing/cms/search-console/domains/${id}/`));
  },

  submitSearchConsoleSitemap(payload) {
    return wrapApi(api.post('/digital-marketing/cms/search-console/sitemaps/', payload));
  },

  inspectSearchConsoleUrl(payload) {
    return wrapApi(api.post('/digital-marketing/cms/search-console/indexing/', { action: 'INSPECT', ...payload }));
  },

  submitSearchConsoleIndexing(payload) {
    return wrapApi(api.post('/digital-marketing/cms/search-console/indexing/', { action: 'SUBMIT', ...payload }));
  },

  // ── 3. Bing Webmaster Tools & IndexNow ───────────────────────────────────────
  getBingDashboard() {
    return wrapApi(api.get('/digital-marketing/cms/bing/dashboard/'));
  },

  updateBingConfig(payload) {
    return wrapApi(api.post('/digital-marketing/cms/bing/config/', payload));
  },

  submitBingUrls(payload) {
    return wrapApi(api.post('/digital-marketing/cms/bing/indexing/', payload));
  },

  submitBingSitemap(payload) {
    return wrapApi(api.post('/digital-marketing/cms/bing/sitemaps/', payload));
  },

  // ── 4. Google Ads ────────────────────────────────────────────────────────────
  getGoogleAdsDashboard() {
    return wrapApi(api.get('/digital-marketing/cms/google-ads/dashboard/'));
  },

  updateGoogleAdsConfig(payload) {
    return wrapApi(api.post('/digital-marketing/cms/google-ads/config/', payload));
  },

  createGoogleAdsCampaign(payload) {
    return wrapApi(api.post('/digital-marketing/cms/google-ads/campaigns/', payload));
  },

  updateGoogleAdsCampaign(id, payload) {
    return wrapApi(api.put(`/digital-marketing/cms/google-ads/campaigns/${id}/`, payload));
  },

  deleteGoogleAdsCampaign(id) {
    return wrapApi(api.delete(`/digital-marketing/cms/google-ads/campaigns/${id}/`));
  },

  createGoogleAdsAdGroup(payload) {
    return wrapApi(api.post('/digital-marketing/cms/google-ads/ad-groups/', payload));
  },

  updateGoogleAdsAdGroup(id, payload) {
    return wrapApi(api.put(`/digital-marketing/cms/google-ads/ad-groups/${id}/`, payload));
  },

  deleteGoogleAdsAdGroup(id) {
    return wrapApi(api.delete(`/digital-marketing/cms/google-ads/ad-groups/${id}/`));
  },

  createGoogleAdsKeyword(payload) {
    return wrapApi(api.post('/digital-marketing/cms/google-ads/keywords/', payload));
  },

  updateGoogleAdsKeyword(id, payload) {
    return wrapApi(api.put(`/digital-marketing/cms/google-ads/keywords/${id}/`, payload));
  },

  deleteGoogleAdsKeyword(id) {
    return wrapApi(api.delete(`/digital-marketing/cms/google-ads/keywords/${id}/`));
  },

  // ── Google Products OAuth Connection ─────────────────────────────────────────
  getGoogleConnectUrl() {
    return wrapApi(api.get('/digital-marketing/cms/google/auth-url/'));
  },

  getGoogleConnectionStatus() {
    return wrapApi(api.get('/digital-marketing/cms/google/status/'));
  },
};

export default cmsService;
