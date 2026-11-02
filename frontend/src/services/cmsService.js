/**
 * Headless CMS Service Adapter
 * Connects Market Intel DB DM role to the multi-tenant Headless CMS backend
 * Gateway: Production Gateway https://cms.hikasimat.com
 */

import { store } from '../app/store';
import api from './api';
import { tokenRefreshed } from '../features/auth/authSlice';

const CMS_GATEWAY_STORAGE_KEY = 'cms_dynamic_gateway_url';
const DEFAULT_CMS_FALLBACK = 'https://cms.hikasimat.com';

let gatewayListeners = [];

export const getCmsBaseUrl = () => {
  // 1. Dynamic user-configured URL from localStorage (highest priority)
  if (typeof localStorage !== 'undefined') {
    const stored = localStorage.getItem(CMS_GATEWAY_STORAGE_KEY);
    if (stored && stored.trim()) {
      const clean = stored.trim().replace(/\/+$/, '');
      if (clean.includes('trycloudflare.com')) {
        localStorage.removeItem(CMS_GATEWAY_STORAGE_KEY);
      } else {
        return clean;
      }
    }
  }
  // 2. Environment variable from Vite (.env / .env.local)
  const envUrl = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_CMS_API_URL) || '';
  if (envUrl && envUrl.trim() && !envUrl.includes('trycloudflare.com')) {
    return envUrl.trim().replace(/\/+$/, '');
  }
  // 3. Default fallback
  return DEFAULT_CMS_FALLBACK;
};

export const setCmsBaseUrl = (newUrl) => {
  if (!newUrl) return;
  const clean = newUrl.trim().replace(/\/+$/, '');
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem(CMS_GATEWAY_STORAGE_KEY, clean);
  }
  // Reset session tokens for new gateway target
  clearStoredCmsTokens();
  gatewayListeners.forEach((l) => l(clean));
};

export const resetCmsBaseUrlToDefault = () => {
  if (typeof localStorage !== 'undefined') {
    localStorage.removeItem(CMS_GATEWAY_STORAGE_KEY);
  }
  clearStoredCmsTokens();
  const def = getCmsBaseUrl();
  gatewayListeners.forEach((l) => l(def));
  return def;
};

export const testGatewayUrl = async (candidateUrl) => {
  if (!candidateUrl || !candidateUrl.trim()) {
    return { ok: false, error: 'URL cannot be empty' };
  }
  const clean = candidateUrl.trim().replace(/\/+$/, '');
  const startTime = performance.now();
  try {
    const res = await fetch(`${clean}/health/live`, {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });
    const latency = Math.round(performance.now() - startTime);
    if (res.ok) {
      return { ok: true, latency, status: res.status };
    }
    return { ok: false, latency, status: res.status, error: `HTTP ${res.status}` };
  } catch (err) {
    const latency = Math.round(performance.now() - startTime);
    return { ok: false, latency, error: err.message || 'Connection failed' };
  }
};

export const subscribeGatewayChange = (listener) => {
  gatewayListeners.push(listener);
  return () => {
    gatewayListeners = gatewayListeners.filter((l) => l !== listener);
  };
};

// Internal activity log subscribers for live Activity Inspector drawer
let activityListeners = [];
let activityLogs = [];

export const subscribeActivityLog = (listener) => {
  activityListeners.push(listener);
  return () => {
    activityListeners = activityListeners.filter((l) => l !== listener);
  };
};

export const getActivityLogs = () => [...activityLogs];

export const clearActivityLogs = () => {
  activityLogs = [];
  activityListeners.forEach((l) => l(activityLogs));
};

const notifyActivity = (logEntry) => {
  activityLogs = [logEntry, ...activityLogs].slice(0, 100);
  activityListeners.forEach((l) => l(activityLogs));
};

// Token storage key
const CMS_TOKEN_KEY = 'cms_jwt_access_token';
const CMS_REFRESH_KEY = 'cms_jwt_refresh_token';

export const getStoredCmsToken = () => {
  if (typeof localStorage !== 'undefined') {
    const localToken = localStorage.getItem(CMS_TOKEN_KEY);
    if (localToken && localToken.trim()) return localToken.trim();
  }
  return '';
};

export const setStoredCmsTokens = (access, refresh) => {
  if (access) localStorage.setItem(CMS_TOKEN_KEY, access);
  if (refresh) localStorage.setItem(CMS_REFRESH_KEY, refresh);
};

export const clearStoredCmsTokens = () => {
  localStorage.removeItem(CMS_TOKEN_KEY);
  localStorage.removeItem(CMS_REFRESH_KEY);
};

/**
 * Core API Request Dispatcher with Telemetry Logging & Transparent Auto-Recovery
 */
export async function cmsFetch(endpoint, options = {}, requireAuth = true) {
  const base = getCmsBaseUrl();
  const cleanPath = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  const fullUrl = `${base}${cleanPath}`;
  const method = (options.method || 'GET').toUpperCase();
  const startTime = performance.now();

  const headers = {
    ...(options.body || ['POST', 'PUT', 'PATCH'].includes(method) ? { 'Content-Type': 'application/json' } : {}),
    ...(options.headers || {}),
  };

  let token = getStoredCmsToken();

  // If auth is required and no token exists, attempt auto-login
  if (requireAuth && !token) {
    const loginOk = await autoLoginCms();
    if (loginOk) {
      token = getStoredCmsToken();
    }
  }

  if (requireAuth && token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const fetchOptions = {
    method,
    headers,
  };

  if (options.body && method !== 'GET' && method !== 'HEAD') {
    fetchOptions.body = typeof options.body === 'string' ? options.body : JSON.stringify(options.body);
  }

  let response;
  let parsedData = null;
  let errorMsg = null;
  let status = 0;

  try {
    response = await fetch(fullUrl, fetchOptions);
    status = response.status;
    const rawText = await response.text();

    try {
      parsedData = JSON.parse(rawText);
    } catch {
      parsedData = rawText;
    }

    // Handle 401 Unauthorized with token refresh or re-login once
    if (status === 401 && requireAuth && !options._isRetry) {
      const reloginOk = await autoLoginCms();
      if (reloginOk) {
        return cmsFetch(endpoint, { ...options, _isRetry: true }, requireAuth);
      }
    }

    if (!response.ok) {
      if (typeof parsedData === 'object' && parsedData !== null) {
        if (parsedData.error?.message) {
          errorMsg = parsedData.error.message;
          if (parsedData.error.details) {
            const detailStr = typeof parsedData.error.details === 'object'
              ? Object.entries(parsedData.error.details)
                  .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
                  .join('; ')
              : String(parsedData.error.details);
            if (detailStr) errorMsg += ` (${detailStr})`;
          }
        } else if (parsedData.detail) {
          errorMsg = parsedData.detail;
        } else if (parsedData.message) {
          errorMsg = parsedData.message;
        } else {
          // DRF validation errors like {"urls": ["..."]} or {"non_field_errors": ["..."]}
          const fieldErrors = Object.entries(parsedData)
            .map(([field, errs]) => `${field}: ${Array.isArray(errs) ? errs.join(', ') : errs}`)
            .join(' | ');
          errorMsg = fieldErrors || `Request failed with status ${status}`;
        }
      } else {
        errorMsg = `Request failed with status ${status}`;
      }
    }
  } catch (err) {
    status = 500;
    errorMsg = err.message || 'Network / connection error';
    parsedData = { error: { message: errorMsg } };
  }

  const latency = Math.round(performance.now() - startTime);

  // Dispatch Telemetry Entry to Inspector
  notifyActivity({
    id: `log-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`,
    timestamp: new Date().toISOString(),
    method,
    path: cleanPath,
    fullUrl,
    status,
    latency,
    requestBody: options.body || null,
    responseData: parsedData,
    ok: status >= 200 && status < 300,
    error: errorMsg,
  });

  return {
    ok: status >= 200 && status < 300,
    status,
    data: parsedData,
    error: errorMsg,
  };
}

/**
 * Auto-authenticate using Market Intel DB DM credentials or federated token
 */
let autoLoginPromise = null;

export async function autoLoginCms(email = null, password = null) {
  if (autoLoginPromise) return autoLoginPromise;
  autoLoginPromise = _executeAutoLogin(email, password).finally(() => {
    autoLoginPromise = null;
  });
  return autoLoginPromise;
}

async function _executeAutoLogin(email = null, password = null) {
  const base = getCmsBaseUrl();
  try {
    // 0. Rotate CMS access token if refresh token exists in localStorage
    if (typeof localStorage !== 'undefined') {
      const storedRefresh = localStorage.getItem(CMS_REFRESH_KEY);
      if (storedRefresh) {
        try {
          const refRes = await fetch(`${base}/api/v1/auth/refresh/`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh: storedRefresh }),
          });
          if (refRes.ok) {
            const refTokens = await refRes.json();
            if (refTokens.access) {
              setStoredCmsTokens(refTokens.access, refTokens.refresh || storedRefresh);
              return true;
            }
          }
        } catch (refErr) {
          console.warn('CMS refresh token rotation failed:', refErr);
        }
      }
    }

    // 1. Obtain active Market Intel DB token (from Redux or by refreshing active session cookie)
    let activeToken = null;
    try {
      activeToken = store?.getState?.()?.auth?.accessToken;
    } catch {
      // Ignore store error
    }

    // If Redux has no access token, refresh it via Market Intel DB axios api instance
    if (!activeToken) {
      try {
        const miRefRes = await api.post('/auth/refresh/', {});
        if (miRefRes.data?.access) {
          activeToken = miRefRes.data.access;
          try {
            store.dispatch(tokenRefreshed({ access: activeToken }));
          } catch {}
        }
      } catch (miErr) {
        // If refresh failed, fallback to direct fetch
        try {
          const miFetch = await fetch('/api/auth/refresh/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({}),
          });
          if (miFetch.ok) {
            const data = await miFetch.json();
            if (data.access) {
              activeToken = data.access;
              try { store.dispatch(tokenRefreshed({ access: activeToken })); } catch {}
            }
          }
        } catch {}
      }
    }

    // 2. If active Market Intel token is available, exchange it with CMS
    if (activeToken) {
      try {
        const exRes = await fetch(`${base}/api/v1/auth/marketintel/exchange/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: activeToken }),
        });
        if (exRes.ok) {
          const tokens = await exRes.json();
          if (tokens.access) {
            setStoredCmsTokens(tokens.access, tokens.refresh);
            return true;
          }
        }
      } catch (exErr) {
        console.warn('Market Intel token exchange attempt error:', exErr);
      }

      // Try direct token login
      try {
        const loginTokenRes = await fetch(`${base}/api/v1/auth/login/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token: activeToken }),
        });
        if (loginTokenRes.ok) {
          const tokens = await loginTokenRes.json();
          if (tokens.access) {
            setStoredCmsTokens(tokens.access, tokens.refresh);
            return true;
          }
        }
      } catch (ltErr) {
        console.warn('Direct token login error:', ltErr);
      }
    }

    // 3. Optional fallback for explicit credentials (when provided by caller)
    if (email && password) {
      const res = await fetch(`${base}/api/v1/auth/login/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });
      if (res.ok) {
        const tokens = await res.json();
        if (tokens.access) {
          setStoredCmsTokens(tokens.access, tokens.refresh);
          return true;
        }
      }
    }

    return false;
  } catch (e) {
    console.warn('Auto-login to CMS failed:', e);
    return false;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// EXPORTED CMS SERVICE API METHODS
// ─────────────────────────────────────────────────────────────────────────────

export const cmsService = {
  // Probes & Status
  async checkLive() {
    return cmsFetch('/health/live', { method: 'GET' }, false);
  },
  async checkReady() {
    return cmsFetch('/health/ready', { method: 'GET' }, false);
  },

  // Auth & Session
  async login(email, password) {
    const res = await cmsFetch('/api/v1/auth/login/', { method: 'POST', body: { email, password } }, false);
    if (res.ok && res.data?.access) {
      setStoredCmsTokens(res.data.access, res.data.refresh);
    }
    return res;
  },
  async getCurrentUser() {
    return cmsFetch('/api/v1/auth/me/', { method: 'GET' }, true);
  },
  logout() {
    clearStoredCmsTokens();
  },

  // Multi-Tenancy: Workspaces
  async getWorkspaces() {
    return cmsFetch('/api/v1/workspaces/', { method: 'GET' }, true);
  },
  async createWorkspace(name, slug) {
    return cmsFetch('/api/v1/workspaces/', { method: 'POST', body: { name, slug } }, true);
  },

  // Multi-Tenancy: Sites & Domains
  async getSites(workspaceId) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/sites/`, { method: 'GET' }, true);
  },
  async createSite(workspaceId, { name, slug, default_locale = 'en-US' }) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/sites/`, {
      method: 'POST',
      body: { name, slug, default_locale },
    }, true);
  },
  async getDomains(workspaceId, siteId) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/sites/${siteId}/domains/`, { method: 'GET' }, true);
  },
  async createDomain(workspaceId, siteId, { hostname, is_primary = false }) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/sites/${siteId}/domains/`, {
      method: 'POST',
      body: { hostname, is_primary },
    }, true);
  },
  async verifyDomain(workspaceId, siteId, domainId, simulateSuccess = true) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/sites/${siteId}/domains/${domainId}/verify/`, {
      method: 'POST',
      body: { simulate_success: simulateSuccess },
    }, true);
  },
  async deleteDomain(workspaceId, siteId, domainId) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/sites/${siteId}/domains/${domainId}/`, {
      method: 'DELETE',
    }, true);
  },

  // Content & Articles
  async getArticles(workspaceId, siteId) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/sites/${siteId}/articles/`, { method: 'GET' }, true);
  },
  async createArticle(workspaceId, siteId, { title, slug, body, excerpt = '', content_type = 'POST', status = 'DRAFT' }) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/sites/${siteId}/articles/`, {
      method: 'POST',
      body: { title, slug, body, excerpt, content_type, status },
    }, true);
  },
  async updateArticle(workspaceId, siteId, articleId, data) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/sites/${siteId}/articles/${articleId}/`, {
      method: 'PATCH',
      body: data,
    }, true);
  },
  async deleteArticle(workspaceId, siteId, articleId) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/sites/${siteId}/articles/${articleId}/`, {
      method: 'DELETE',
    }, true);
  },
  async publishArticle(workspaceId, siteId, articleId) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/sites/${siteId}/articles/${articleId}/publish/`, {
      method: 'POST',
    }, true);
  },

  // 7-Step Article Publishing Pipeline Inspector
  async getArticlePipelineFlow(workspaceId, siteId, articleId) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/sites/${siteId}/articles/${articleId}/pipeline-flow/`, {
      method: 'GET',
    }, true);
  },

  // Public Delivery Endpoints (Client / Reader / Preview)
  async getPublicArticles(siteSlug) {
    return cmsFetch(`/api/v1/public/sites/${siteSlug}/articles/`, { method: 'GET' }, false);
  },
  async getPublicArticle(siteSlug, articleSlug) {
    return cmsFetch(`/api/v1/public/sites/${siteSlug}/articles/${articleSlug}/`, { method: 'GET' }, false);
  },
  async getPublicSitemap(siteSlug) {
    return cmsFetch(`/api/v1/public/sites/${siteSlug}/sitemap.xml`, { method: 'GET' }, false);
  },
  async getPublicRobots(siteSlug) {
    return cmsFetch(`/api/v1/public/sites/${siteSlug}/robots.txt`, { method: 'GET' }, false);
  },

  // Technical SEO & Search Integrations (Google & Bing)
  async getSearchProviders(workspaceId, siteId) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/sites/${siteId}/integrations/connections/`, { method: 'GET' }, true);
  },
  async getIndexNowKey(workspaceId, siteId) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/sites/${siteId}/integrations/indexnow/`, { method: 'GET' }, true);
  },
  async getIndexingLogs(workspaceId, siteId) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/sites/${siteId}/integrations/logs/`, { method: 'GET' }, true);
  },
  async submitUrlForIndexing(workspaceId, siteId, { provider, urls }) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/sites/${siteId}/integrations/submit/`, {
      method: 'POST',
      body: { provider, urls: Array.isArray(urls) ? urls : [urls] },
    }, true);
  },

  // Privacy-Preserving Analytics & GA4
  async ingestPublicEvent(siteSlug, { event_type, visitor_id, session_id, path, consent_granted = true, properties = {} }) {
    return cmsFetch(`/api/v1/public/sites/${siteSlug}/events/`, {
      method: 'POST',
      body: { event_type, visitor_id, session_id, path, consent_granted, properties },
    }, false);
  },
  async getAnalyticsOverview(workspaceId, siteId) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/sites/${siteId}/analytics/first-party/overview/`, { method: 'GET' }, true);
  },
  async getAnalyticsConfig(workspaceId, siteId) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/sites/${siteId}/analytics/config/`, { method: 'GET' }, true);
  },
  async updateAnalyticsConfig(workspaceId, siteId, configData) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/sites/${siteId}/analytics/config/`, {
      method: 'PATCH',
      body: configData,
    }, true);
  },
  async connectGA4(workspaceId, siteId, { property_id, measurement_id, credentials = {} }) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/sites/${siteId}/analytics/ga4/`, {
      method: 'POST',
      body: { property_id, measurement_id, credentials },
    }, true);
  },
  async getGA4Report(workspaceId, siteId, { start_date, end_date }) {
    const qs = `?start_date=${encodeURIComponent(start_date)}&end_date=${encodeURIComponent(end_date)}`;
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/sites/${siteId}/analytics/reports/ga4/${qs}`, { method: 'GET' }, true);
  },

  // Cookie & Privacy Consent Manager
  async recordVisitorConsent(siteSlug, { visitor_id, categories, consent_type = 'EXPLICIT_OPT_IN' }) {
    return cmsFetch(`/api/v1/public/sites/${siteSlug}/consent/`, {
      method: 'POST',
      body: { visitor_id, categories, consent_type },
    }, false);
  },

  // Google Ads Workspace Integration
  async getGoogleAdsConnection(workspaceId) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/google-ads/connection/`, { method: 'GET' }, true);
  },
  async authorizeGoogleAds(workspaceId, redirectUri = '') {
    const defaultUri = typeof window !== 'undefined'
      ? `${window.location.origin}/digital-marketing/cms/`
      : 'https://marketinteldbapp.hikasimat.com/digital-marketing/cms/';
    const targetUri = redirectUri || defaultUri;
    const qs = `?redirect_uri=${encodeURIComponent(targetUri)}`;
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/google-ads/authorize/${qs}`, {
      method: 'GET',
    }, true);
  },
  async exchangeGoogleAdsCode(workspaceId, code, redirectUri = '', developerToken = '') {
    const defaultUri = typeof window !== 'undefined'
      ? `${window.location.origin}/digital-marketing/cms/`
      : 'https://marketinteldbapp.hikasimat.com/digital-marketing/cms/';
    const targetUri = redirectUri || defaultUri;
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/google-ads/callback/`, {
      method: 'POST',
      body: {
        code,
        redirect_uri: targetUri,
        developer_token: developerToken || '',
      },
    }, true);
  },
  async disconnectGoogleAds(workspaceId) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/google-ads/disconnect/`, { method: 'POST' }, true);
  },
  async getGoogleAdsCustomers(workspaceId) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/google-ads/customers/`, { method: 'GET' }, true);
  },
  async selectGoogleAdsCustomer(workspaceId, payload) {
    const data = typeof payload === 'string' ? { customer_id: payload } : (payload || {});
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/google-ads/customers/select/`, {
      method: 'POST',
      body: {
        customer_id: data.customer_id,
        manager_customer_id: data.manager_customer_id || '',
        developer_token: data.developer_token || '',
      },
    }, true);
  },
  async getGoogleAdsCampaigns(workspaceId, { start_date, end_date } = {}) {
    const params = new URLSearchParams();
    if (start_date) params.append('start_date', start_date);
    if (end_date) params.append('end_date', end_date);
    const qs = params.toString() ? `?${params.toString()}` : '';
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/google-ads/campaigns/${qs}`, { method: 'GET' }, true);
  },
  async pauseGoogleAdsCampaign(workspaceId, campaignId, campaignName = '') {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/google-ads/campaigns/${campaignId}/pause/`, {
      method: 'POST',
      body: { confirm: true, campaign_name: campaignName },
    }, true);
  },
  async resumeGoogleAdsCampaign(workspaceId, campaignId, campaignName = '') {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/google-ads/campaigns/${campaignId}/resume/`, {
      method: 'POST',
      body: { confirm: true, campaign_name: campaignName },
    }, true);
  },
  async updateGoogleAdsBudget(workspaceId, campaignId, budgetArg, customerId = '', campaignName = '') {
    let budget_resource_name = '';
    let amount_micros = 0;
    let name = campaignName;

    if (typeof budgetArg === 'object' && budgetArg !== null) {
      budget_resource_name =
        budgetArg.budget_resource_name ||
        (customerId ? `customers/${customerId}/campaignBudgets/${campaignId}` : `customers/default/campaignBudgets/${campaignId}`);
      amount_micros =
        budgetArg.amount_micros ||
        Math.round(Number(budgetArg.amount || budgetArg.amount_dollars || 0) * 1000000);
      name = budgetArg.campaign_name || name;
    } else {
      const dollars = parseFloat(budgetArg) || 0;
      amount_micros = Math.round(dollars * 1000000);
      budget_resource_name = customerId
        ? `customers/${customerId}/campaignBudgets/${campaignId}`
        : `customers/default/campaignBudgets/${campaignId}`;
    }

    return cmsFetch(`/api/v1/workspaces/${workspaceId}/google-ads/campaigns/${campaignId}/budget/`, {
      method: 'POST',
      body: {
        budget_resource_name,
        amount_micros,
        campaign_id: campaignId,
        campaign_name: name,
        confirm: true,
      },
    }, true);
  },
  async getGoogleAdsAdGroups(workspaceId, { start_date, end_date } = {}) {
    const params = new URLSearchParams();
    if (start_date) params.append('start_date', start_date);
    if (end_date) params.append('end_date', end_date);
    const qs = params.toString() ? `?${params.toString()}` : '';
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/google-ads/ad-groups/${qs}`, { method: 'GET' }, true);
  },
  async getGoogleAdsKeywords(workspaceId, { start_date, end_date } = {}) {
    const params = new URLSearchParams();
    if (start_date) params.append('start_date', start_date);
    if (end_date) params.append('end_date', end_date);
    const qs = params.toString() ? `?${params.toString()}` : '';
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/google-ads/keywords/${qs}`, { method: 'GET' }, true);
  },
  async getGoogleAdsAuditLogs(workspaceId) {
    return cmsFetch(`/api/v1/workspaces/${workspaceId}/google-ads/audit-logs/`, { method: 'GET' }, true);
  },
};

export default cmsService;
