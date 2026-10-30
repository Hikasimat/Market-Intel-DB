/**
 * Headless CMS Service Adapter
 * Connects Market Intel DB DM role to the multi-tenant Headless CMS backend
 * Gateway: Cloudflare Tunnel https://symbols-andrews-pix-anytime.trycloudflare.com
 */

const CMS_GATEWAY_STORAGE_KEY = 'cms_dynamic_gateway_url';
const DEFAULT_CMS_FALLBACK = 'http://localhost:8001';

let gatewayListeners = [];

export const getCmsBaseUrl = () => {
  // 1. Dynamic user-configured URL from localStorage (highest priority)
  if (typeof localStorage !== 'undefined') {
    const stored = localStorage.getItem(CMS_GATEWAY_STORAGE_KEY);
    if (stored && stored.trim()) {
      const clean = stored.trim().replace(/\/+$/, '');
      if (clean.includes('symbols-andrews-pix-anytime')) {
        localStorage.removeItem(CMS_GATEWAY_STORAGE_KEY);
      } else {
        return clean;
      }
    }
  }
  // 2. Environment variable from Vite (.env / .env.local)
  const envUrl = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_CMS_API_URL) || '';
  if (envUrl && envUrl.trim()) {
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
  return localStorage.getItem(CMS_TOKEN_KEY) || '';
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
      errorMsg =
        (typeof parsedData === 'object' && (parsedData?.error?.message || parsedData?.detail || parsedData?.message)) ||
        `Request failed with status ${status}`;
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
 * Auto-authenticate using Market Intel DB DM credentials
 */
export async function autoLoginCms(email = 'meynix.official@gmail.com', password = 'AdminPassword123!') {
  const base = getCmsBaseUrl();
  try {
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
};

export default cmsService;
