import React, { useState, useEffect, useCallback } from 'react';
import { toast } from 'react-toastify';
import {
  Globe,
  FileText,
  Search,
  BarChart3,
  ShieldCheck,
  Activity,
  Plus,
  RefreshCw,
  ExternalLink,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  Send,
  Trash2,
  Copy,
  ChevronRight,
  Database,
  Layers,
  ArrowUpRight,
  Code,
  Terminal,
  Check,
  Sparkles,
  MousePointerClick,
  Users,
  Eye,
  Sliders,
  X
} from 'lucide-react';
import {
  cmsService,
  getCmsBaseUrl,
  setCmsBaseUrl,
  resetCmsBaseUrlToDefault,
  testGatewayUrl,
  subscribeGatewayChange,
  subscribeActivityLog,
  clearActivityLogs,
  getStoredCmsToken,
} from '../../services/cmsService';

const CmsPage = () => {
  // Navigation & Active View
  const [activeTab, setActiveTab] = useState('articles'); // 'articles' | 'inspector' | 'seo' | 'analytics' | 'consent'
  const [isInspectorOpen, setIsInspectorOpen] = useState(false);
  const [activityLogs, setActivityLogs] = useState([]);

  // Gateway & System Health (Fully Dynamic URL & Instant Switcher)
  const [currentGatewayUrl, setCurrentGatewayUrl] = useState(getCmsBaseUrl());
  const [isGatewayModalOpen, setIsGatewayModalOpen] = useState(false);
  const [gatewayInput, setGatewayInput] = useState('');
  const [gatewayTesting, setGatewayTesting] = useState(false);
  const [gatewayTestResult, setGatewayTestResult] = useState(null);
  const [backendHealth, setBackendHealth] = useState({ live: false, ready: false, checking: true });
  const [userEmail, setUserEmail] = useState('meynix.official@gmail.com');

  // Tenancy Data
  const [workspaces, setWorkspaces] = useState([]);
  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState('');
  const [sites, setSites] = useState([]);
  const [selectedSiteId, setSelectedSiteId] = useState('');
  const [loadingTenancy, setLoadingTenancy] = useState(false);

  // Modal: Create Site
  const [isCreateSiteOpen, setIsCreateSiteOpen] = useState(false);
  const [newSiteName, setNewSiteName] = useState('');
  const [newSiteSlug, setNewSiteSlug] = useState('');
  const [newSiteLocale, setNewSiteLocale] = useState('en-US');
  const [creatingSite, setCreatingSite] = useState(false);

  // Tab 1: Articles
  const [articles, setArticles] = useState([]);
  const [loadingArticles, setLoadingArticles] = useState(false);
  const [isCreateArticleOpen, setIsCreateArticleOpen] = useState(false);
  const [newArtTitle, setNewArtTitle] = useState('');
  const [newArtSlug, setNewArtSlug] = useState('');
  const [newArtBody, setNewArtBody] = useState('# New Post\n\nWrite your article content here in Markdown...');
  const [newArtExcerpt, setNewArtExcerpt] = useState('');
  const [creatingArticle, setCreatingArticle] = useState(false);
  const [articleFilter, setArticleFilter] = useState('ALL'); // 'ALL' | 'PUBLISHED' | 'DRAFT'
  const [articleSearch, setArticleSearch] = useState('');
  const [publicDeliveryData, setPublicDeliveryData] = useState(null);
  const [showPublicDelivery, setShowPublicDelivery] = useState(false);
  const [loadingPublicDelivery, setLoadingPublicDelivery] = useState(false);

  // Tab 2: 7-Step Pipeline Inspector
  const [inspectedArticle, setInspectedArticle] = useState(null);
  const [pipelineData, setPipelineData] = useState(null);
  const [loadingPipeline, setLoadingPipeline] = useState(false);

  // Tab 3: SEO & Indexing
  const [seoPreviewType, setSeoPreviewType] = useState('sitemap'); // 'sitemap' | 'robots'
  const [seoPreviewText, setSeoPreviewText] = useState('');
  const [loadingSeoPreview, setLoadingSeoPreview] = useState(false);
  const [indexingProvider, setIndexingProvider] = useState('GOOGLE');
  const [indexingUrl, setIndexingUrl] = useState('');
  const [submittingIndexing, setSubmittingIndexing] = useState(false);
  const [indexingLogs, setIndexingLogs] = useState([]);
  const [loadingIndexingLogs, setLoadingIndexingLogs] = useState(false);
  const [indexNowKey, setIndexNowKey] = useState('');

  // Tab 4: Privacy Analytics
  const [analyticsOverview, setAnalyticsOverview] = useState(null);
  const [analyticsConfig, setAnalyticsConfig] = useState(null);
  const [loadingAnalyticsConfig, setLoadingAnalyticsConfig] = useState(false);
  const [togglingIngestion, setTogglingIngestion] = useState(false);
  const [loadingAnalytics, setLoadingAnalytics] = useState(false);
  const [simulatingEvent, setSimulatingEvent] = useState(false);
  const [ga4ReportData, setGa4ReportData] = useState(null);
  const [loadingGa4Report, setLoadingGa4Report] = useState(false);

  // Tab 5: Consent Management
  const [consentVisitorId, setConsentVisitorId] = useState('visitor-dm-session-901');
  const [consentJurisdiction, setConsentJurisdiction] = useState('EU_GDPR');
  const [consentResult, setConsentResult] = useState(null);
  const [recordingConsent, setRecordingConsent] = useState(false);

  // Subscribe to realtime Activity Inspector logs
  useEffect(() => {
    const unsubscribe = subscribeActivityLog((logs) => {
      setActivityLogs(logs);
    });
    return unsubscribe;
  }, []);

  // Compute clean display hostname for toolbar indicator & alert badges
  const displayHost = React.useMemo(() => {
    try {
      const u = new URL(currentGatewayUrl);
      return u.host;
    } catch {
      return currentGatewayUrl.replace(/^https?:\/\//, '').split('/')[0] || currentGatewayUrl;
    }
  }, [currentGatewayUrl]);

  // Subscribe to dynamic gateway URL changes
  useEffect(() => {
    const unsubscribe = subscribeGatewayChange((newUrl) => {
      setCurrentGatewayUrl(newUrl);
    });
    return unsubscribe;
  }, []);

  // Check health and load workspaces on mount or whenever active gateway URL changes
  useEffect(() => {
    checkSystemHealth();
    initTenancy();
  }, [currentGatewayUrl]);

  const handleSaveGateway = (urlToSave) => {
    const target = (urlToSave || gatewayInput).trim();
    if (!target) {
      toast.error('Gateway URL cannot be empty');
      return;
    }
    setCmsBaseUrl(target);
    setCurrentGatewayUrl(target);
    setIsGatewayModalOpen(false);
    setGatewayTestResult(null);
    toast.success(`Connected to CMS Gateway: ${target}`);
  };

  const handleTestGateway = async (candidate) => {
    const testUrl = (candidate || gatewayInput).trim();
    if (!testUrl) {
      toast.error('Please enter a URL to test');
      return;
    }
    setGatewayTesting(true);
    setGatewayTestResult(null);
    const res = await testGatewayUrl(testUrl);
    setGatewayTesting(false);
    setGatewayTestResult(res);
  };

  const handleResetGateway = () => {
    const def = resetCmsBaseUrlToDefault();
    setCurrentGatewayUrl(def);
    setGatewayInput(def);
    setGatewayTestResult(null);
    setIsGatewayModalOpen(false);
    toast.info(`Gateway reset to default: ${def}`);
  };

  const checkSystemHealth = async () => {
    setBackendHealth((prev) => ({ ...prev, checking: true }));
    try {
      const liveRes = await cmsService.checkLive();
      const readyRes = await cmsService.checkReady();
      setBackendHealth({
        live: liveRes.ok,
        ready: readyRes.ok,
        checking: false,
      });
    } catch {
      setBackendHealth({ live: false, ready: false, checking: false });
    }
  };

  const initTenancy = async () => {
    setLoadingTenancy(true);
    try {
      // Verify or refresh current user session
      const meRes = await cmsService.getCurrentUser();
      if (meRes.ok && meRes.data?.email) {
        setUserEmail(meRes.data.email);
      }

      // Load workspaces
      const wsRes = await cmsService.getWorkspaces();
      const wsList = Array.isArray(wsRes.data)
        ? wsRes.data
        : wsRes.data?.results || [];

      setWorkspaces(wsList);
      if (wsList.length > 0) {
        const initialWsId = wsList[0].id;
        setSelectedWorkspaceId(initialWsId);
        await loadSitesForWorkspace(initialWsId);
      }
    } catch (err) {
      toast.error('Could not initialize CMS tenant workspace: ' + err.message);
    } finally {
      setLoadingTenancy(false);
    }
  };

  const loadSitesForWorkspace = async (wId) => {
    if (!wId) return;
    try {
      const sitesRes = await cmsService.getSites(wId);
      const siteList = Array.isArray(sitesRes.data)
        ? sitesRes.data
        : sitesRes.data?.results || [];

      setSites(siteList);
      if (siteList.length > 0) {
        const initialSite = siteList[0];
        setSelectedSiteId(initialSite.id);
        await loadArticlesForSite(wId, initialSite.id, siteList);
      } else {
        setSelectedSiteId('');
        setArticles([]);
      }
    } catch (err) {
      console.warn('Failed to load sites:', err);
    }
  };

  const loadArticlesForSite = async (wId, sId, siteListOverride = null) => {
    if (!wId || !sId) return;
    setLoadingArticles(true);
    try {
      const artRes = await cmsService.getArticles(wId, sId);
      const artList = Array.isArray(artRes.data)
        ? artRes.data
        : artRes.data?.results || [];
      setArticles(artList);

      // Auto-populate indexing URL with the latest published article (or first article) instead of sample-post
      const availableSites = siteListOverride || sites;
      const activeSiteObj = availableSites.find((s) => s.id === sId);
      const siteSlug = activeSiteObj?.slug || 'site';
      const published = artList.filter((a) => a.status === 'PUBLISHED');
      if (published.length > 0) {
        setIndexingUrl(`https://${siteSlug}.hikasimat.com/articles/${published[0].slug}`);
      } else if (artList.length > 0) {
        setIndexingUrl(`https://${siteSlug}.hikasimat.com/articles/${artList[0].slug}`);
      } else {
        setIndexingUrl(`https://${siteSlug}.hikasimat.com/`);
      }
    } catch (err) {
      console.warn('Failed to load articles:', err);
    } finally {
      setLoadingArticles(false);
    }
  };

  // Re-load when workspace changes
  const handleWorkspaceChange = async (wId) => {
    setSelectedWorkspaceId(wId);
    await loadSitesForWorkspace(wId);
  };

  // Re-load when site changes
  const handleSiteChange = async (sId) => {
    setSelectedSiteId(sId);
    const siteObj = sites.find((s) => s.id === sId);
    await loadArticlesForSite(selectedWorkspaceId, sId, sites);
    if (activeTab === 'analytics') {
      loadAnalytics();
    }
    if (activeTab === 'seo') {
      loadSeoPreview(seoPreviewType, siteObj);
    }
  };

  // Create Site
  const handleCreateSite = async (e) => {
    e.preventDefault();
    if (!newSiteName.trim()) {
      toast.error('Please enter a valid publication site name.');
      return;
    }
    const cleanSlug =
      newSiteSlug.trim() ||
      newSiteName
        .toLowerCase()
        .replace(/^https?:\/\//i, '')
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-|-$/g, '');

    setCreatingSite(true);
    try {
      const res = await cmsService.createSite(selectedWorkspaceId, {
        name: newSiteName.trim(),
        slug: cleanSlug,
        default_locale: newSiteLocale || 'en-US',
      });

      if (res.ok) {
        toast.success(`Publication site "${newSiteName}" created successfully!`);
        setIsCreateSiteOpen(false);
        setNewSiteName('');
        setNewSiteSlug('');
        await loadSitesForWorkspace(selectedWorkspaceId);
      } else {
        toast.error('Failed to create site: ' + (res.error || 'Server error'));
      }
    } catch (err) {
      toast.error('Site creation error: ' + err.message);
    } finally {
      setCreatingSite(false);
    }
  };

  // Create Article
  const handleCreateArticle = async (e) => {
    e.preventDefault();
    if (!newArtTitle.trim()) {
      toast.error('Article title is required.');
      return;
    }
    const cleanSlug =
      newArtSlug.trim() ||
      newArtTitle
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-|-$/g, '');

    setCreatingArticle(true);
    try {
      const res = await cmsService.createArticle(selectedWorkspaceId, selectedSiteId, {
        title: newArtTitle.trim(),
        slug: cleanSlug,
        body: newArtBody,
        excerpt: newArtExcerpt,
        status: 'DRAFT',
      });

      if (res.ok) {
        toast.success(`Draft article "${newArtTitle}" created!`);
        setIsCreateArticleOpen(false);
        setNewArtTitle('');
        setNewArtSlug('');
        setNewArtExcerpt('');
        await loadArticlesForSite(selectedWorkspaceId, selectedSiteId);
        // Automatically open pipeline inspector on new article
        if (res.data?.id) {
          inspectPipeline(res.data);
        }
      } else {
        toast.error('Failed to create article: ' + (res.error || 'Validation error'));
      }
    } catch (err) {
      toast.error('Error creating article: ' + err.message);
    } finally {
      setCreatingArticle(false);
    }
  };

  // Publish Article
  const handlePublishArticle = async (article) => {
    try {
      const res = await cmsService.publishArticle(selectedWorkspaceId, selectedSiteId, article.id);
      if (res.ok) {
        toast.success(`Article "${article.title}" published live!`);
        await loadArticlesForSite(selectedWorkspaceId, selectedSiteId);
        inspectPipeline(article);
      } else {
        toast.error('Failed to publish: ' + (res.error || 'Server error'));
      }
    } catch (err) {
      toast.error('Error publishing article: ' + err.message);
    }
  };

  // Delete Article
  const handleDeleteArticle = async (article) => {
    if (!window.confirm(`Are you sure you want to delete "${article.title}"?`)) return;
    try {
      const res = await cmsService.deleteArticle(selectedWorkspaceId, selectedSiteId, article.id);
      if (res.ok) {
        toast.success('Article deleted successfully.');
        await loadArticlesForSite(selectedWorkspaceId, selectedSiteId);
        if (inspectedArticle?.id === article.id) {
          setInspectedArticle(null);
          setPipelineData(null);
        }
      } else {
        toast.error('Delete failed: ' + (res.error || 'Server error'));
      }
    } catch (err) {
      toast.error('Error deleting article: ' + err.message);
    }
  };

  // Inspect Pipeline Flow
  const inspectPipeline = async (article) => {
    setInspectedArticle(article);
    setActiveTab('inspector');
    setLoadingPipeline(true);
    try {
      const res = await cmsService.getArticlePipelineFlow(
        selectedWorkspaceId,
        selectedSiteId,
        article.id
      );
      if (res.ok) {
        setPipelineData(res.data);
      } else {
        toast.error('Failed to fetch pipeline diagnostics: ' + (res.error || ''));
      }
    } catch (err) {
      toast.error('Error fetching pipeline: ' + err.message);
    } finally {
      setLoadingPipeline(false);
    }
  };

  // Public Delivery Comparison
  const fetchPublicDelivery = async () => {
    const siteObj = sites.find((s) => s.id === selectedSiteId);
    if (!siteObj) return;
    setLoadingPublicDelivery(true);
    setShowPublicDelivery(true);
    try {
      const res = await cmsService.getPublicArticles(siteObj.slug);
      setPublicDeliveryData(res.data);
    } catch (err) {
      toast.error('Failed to fetch public delivery: ' + err.message);
    } finally {
      setLoadingPublicDelivery(false);
    }
  };

  // SEO Preview (Sitemap / Robots)
  const loadSeoPreview = async (type = 'sitemap', siteOverride = null) => {
    const siteObj = siteOverride || sites.find((s) => s.id === selectedSiteId);
    if (!siteObj) return;
    setSeoPreviewType(type);
    setLoadingSeoPreview(true);
    try {
      const res =
        type === 'sitemap'
          ? await cmsService.getPublicSitemap(siteObj.slug)
          : await cmsService.getPublicRobots(siteObj.slug);

      setSeoPreviewText(typeof res.data === 'string' ? res.data : JSON.stringify(res.data, null, 2));
    } catch (err) {
      setSeoPreviewText('Error loading preview: ' + err.message);
    } finally {
      setLoadingSeoPreview(false);
    }
  };

  // IndexNow & Providers Logs
  const loadIndexingLogs = async () => {
    if (!selectedWorkspaceId || !selectedSiteId) return;
    setLoadingIndexingLogs(true);
    try {
      const logsRes = await cmsService.getIndexingLogs(selectedWorkspaceId, selectedSiteId);
      const logsList = Array.isArray(logsRes.data)
        ? logsRes.data
        : logsRes.data?.results || [];
      setIndexingLogs(logsList);

      const keyRes = await cmsService.getIndexNowKey(selectedWorkspaceId, selectedSiteId);
      if (keyRes.ok && keyRes.data?.key) {
        setIndexNowKey(keyRes.data.key);
      }
    } catch (err) {
      console.warn('Indexing logs error:', err);
    } finally {
      setLoadingIndexingLogs(false);
    }
  };

  // Submit URL for Indexing
  const handleSubmitIndexing = async (e) => {
    e.preventDefault();
    if (!indexingUrl.trim()) {
      toast.error('Please enter a URL to submit.');
      return;
    }
    setSubmittingIndexing(true);
    try {
      const res = await cmsService.submitUrlForIndexing(selectedWorkspaceId, selectedSiteId, {
        provider: indexingProvider,
        urls: [indexingUrl.trim()],
      });
      if (res.ok) {
        toast.success(`URL submitted to ${indexingProvider} successfully!`);
        await loadIndexingLogs();
      } else {
        toast.error('Submission failed: ' + (res.error || 'Server error'));
      }
    } catch (err) {
      toast.error('Error submitting URL: ' + err.message);
    } finally {
      setSubmittingIndexing(false);
    }
  };

  // Privacy Analytics
  const loadAnalyticsConfig = async () => {
    if (!selectedWorkspaceId || !selectedSiteId) return;
    setLoadingAnalyticsConfig(true);
    try {
      const res = await cmsService.getAnalyticsConfig(selectedWorkspaceId, selectedSiteId);
      if (res.ok) {
        setAnalyticsConfig(res.data);
      }
    } catch (err) {
      console.warn('Analytics config error:', err);
    } finally {
      setLoadingAnalyticsConfig(false);
    }
  };

  const handleToggleFirstParty = async (enable) => {
    if (!selectedWorkspaceId || !selectedSiteId) return;
    setTogglingIngestion(true);
    try {
      const res = await cmsService.updateAnalyticsConfig(selectedWorkspaceId, selectedSiteId, {
        is_first_party_enabled: enable,
      });
      if (res.ok) {
        setAnalyticsConfig(res.data);
        toast.success(
          enable
            ? 'First-party event ingestion enabled!'
            : 'First-party event ingestion disabled.'
        );
      } else {
        toast.error('Failed to update config: ' + (res.error || 'Server error'));
      }
    } catch (err) {
      toast.error('Error updating config: ' + err.message);
    } finally {
      setTogglingIngestion(false);
    }
  };

  const loadAnalytics = async () => {
    if (!selectedWorkspaceId || !selectedSiteId) return;
    setLoadingAnalytics(true);
    try {
      const res = await cmsService.getAnalyticsOverview(selectedWorkspaceId, selectedSiteId);
      if (res.ok) {
        setAnalyticsOverview(res.data);
      }
      await loadAnalyticsConfig();
    } catch (err) {
      console.warn('Analytics overview error:', err);
    } finally {
      setLoadingAnalytics(false);
    }
  };

  const handleSimulateEvent = async (eventType, path) => {
    const siteObj = sites.find((s) => s.id === selectedSiteId);
    if (!siteObj) return;

    // Auto-enable first party ingestion if disabled
    if (analyticsConfig && !analyticsConfig.is_first_party_enabled) {
      await handleToggleFirstParty(true);
    }

    setSimulatingEvent(true);
    const visitorId = `vis-${Math.random().toString(36).substring(2, 9)}`;
    const sessionId = `ses-${Math.random().toString(36).substring(2, 9)}`;

    // Strictly adhere to CMS allowlisted properties (ANA-4)
    let properties = {};
    if (eventType === 'page_view') {
      properties = { path, referrer: 'https://google.com', title: 'Headless Reader Post' };
    } else if (eventType === 'cta_click') {
      properties = {
        path,
        cta_id: 'btn-signup-now',
        cta_text: 'Get Started',
        target_url: `https://${siteObj.slug}.hikasimat.com${path}`,
      };
    } else if (eventType === 'form_submit') {
      properties = { path, form_id: 'lead-newsletter-form', form_name: 'Lead Newsletter Signup' };
    }

    try {
      const res = await cmsService.ingestPublicEvent(siteObj.slug, {
        event_type: eventType,
        visitor_id: visitorId,
        session_id: sessionId,
        path,
        consent_granted: true,
        properties,
      });

      if (res.ok) {
        toast.success(`Event recorded: ${eventType} on ${path}`);
        await loadAnalytics();
      } else {
        const errMsg =
          (res.data && Array.isArray(res.data) && res.data[0]) ||
          (typeof res.data === 'object' && (res.data?.detail || res.data?.error?.message)) ||
          res.error ||
          'Validation failed for one or more fields.';
        toast.error(`Event ingestion failed: ${errMsg}`);
      }
    } catch (err) {
      toast.error('Simulation error: ' + err.message);
    } finally {
      setSimulatingEvent(false);
    }
  };

  const fetchGa4LiveReport = async () => {
    if (!selectedWorkspaceId || !selectedSiteId) return;
    setLoadingGa4Report(true);
    const now = new Date();
    const today = now.toISOString().split('T')[0];
    const past = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0];

    try {
      const res = await cmsService.getGA4Report(selectedWorkspaceId, selectedSiteId, {
        start_date: past,
        end_date: today,
      });
      if (res.ok) {
        setGa4ReportData(res.data);
        toast.success('GA4 Live Report refreshed!');
      } else {
        const errorDetail =
          (res.data && Array.isArray(res.data) && res.data[0]) ||
          (typeof res.data === 'object' && (res.data?.detail || res.data?.error?.message)) ||
          res.error ||
          'GA4 connection not configured for this site.';
        toast.info(errorDetail);
        setGa4ReportData({
          status: 'NOT_CONNECTED',
          message: errorDetail,
          recommendation: 'Configure GA4 OAuth connection in site settings to stream Google Analytics 4 reports.',
        });
      }
    } catch (err) {
      toast.error('GA4 report error: ' + err.message);
    } finally {
      setLoadingGa4Report(false);
    }
  };

  // Consent Operations
  const handleRecordConsent = async (analyticsChoice, marketingChoice) => {
    const siteObj = sites.find((s) => s.id === selectedSiteId);
    if (!siteObj) return;
    setRecordingConsent(true);
    try {
      const isFullOptIn = analyticsChoice && marketingChoice;
      // GDPR Art. 7 requires 'necessary' cookies to always be active and explicit
      const res = await cmsService.recordVisitorConsent(siteObj.slug, {
        visitor_id: consentVisitorId || 'visitor-dm-session-901',
        categories: {
          necessary: true,
          analytics: Boolean(analyticsChoice),
          marketing: Boolean(marketingChoice),
          preferences: Boolean(analyticsChoice || marketingChoice),
        },
        consent_type: isFullOptIn ? 'EXPLICIT_OPT_IN' : 'OPT_OUT',
      });

      if (res.ok) {
        setConsentResult({
          timestamp: new Date().toLocaleTimeString(),
          analytics: analyticsChoice,
          marketing: marketingChoice,
          data: res.data,
        });
        toast.success('Visitor consent recorded with GDPR Art. 7 compliance!');
      } else {
        const errMsg =
          (res.data && Array.isArray(res.data) && res.data[0]) ||
          (typeof res.data === 'object' && (res.data?.detail || res.data?.error?.message)) ||
          res.error ||
          'Failed to record consent.';
        toast.error('Consent recording error: ' + errMsg);
      }
    } catch (err) {
      toast.error('Consent record error: ' + err.message);
    } finally {
      setRecordingConsent(false);
    }
  };

  // Switch tabs handler
  const handleTabSwitch = (tab) => {
    setActiveTab(tab);
    if (tab === 'seo') {
      loadSeoPreview(seoPreviewType);
      loadIndexingLogs();
    } else if (tab === 'analytics') {
      loadAnalytics();
    }
  };

  const activeSite = sites.find((s) => s.id === selectedSiteId);

  // Filtered articles
  const filteredArticles = articles.filter((art) => {
    const matchesFilter =
      articleFilter === 'ALL' ||
      (articleFilter === 'PUBLISHED' && art.status === 'PUBLISHED') ||
      (articleFilter === 'DRAFT' && art.status === 'DRAFT');

    const matchesSearch =
      !articleSearch ||
      art.title?.toLowerCase().includes(articleSearch.toLowerCase()) ||
      art.slug?.toLowerCase().includes(articleSearch.toLowerCase());

    return matchesFilter && matchesSearch;
  });

  // Resolve human-readable page title and badge for analytics telemetry paths
  const resolvePageDetails = (path) => {
    if (!path) return { title: 'Unknown Page', badge: 'Unknown', path: '/' };

    if (path === '/' || path === '') {
      return { title: 'Homepage', badge: 'Root', path };
    }
    if (path === '/blog' || path === '/articles') {
      return { title: 'Articles Feed Index', badge: 'Index', path };
    }
    if (path === '/pricing') {
      return { title: 'Pricing & Plans', badge: 'Static', path };
    }
    if (path === '/contact') {
      return { title: 'Contact Us', badge: 'Static', path };
    }

    // Match /articles/{slug} or /blog/{slug}
    const match = path.match(/^\/(?:articles|blog)\/([^/?#]+)/);
    if (match) {
      const slug = match[1];
      const matchedArt = articles.find(
        (a) => a.slug === slug || a.slug.toLowerCase() === slug.toLowerCase()
      );
      if (matchedArt) {
        return {
          title: matchedArt.title,
          badge: matchedArt.status === 'PUBLISHED' ? 'Article' : 'Draft',
          path,
        };
      }
      // Clean fallback from slug
      const formattedTitle = slug
        .replace(/[-_]+/g, ' ')
        .replace(/\b\w/g, (c) => c.toUpperCase());
      return {
        title: formattedTitle,
        badge: 'Article',
        path,
      };
    }

    // Generic formatting for any other path (e.g. /about-us -> About Us)
    const clean = path
      .replace(/^\//, '')
      .replace(/[-_/]+/g, ' ')
      .replace(/\b\w/g, (c) => c.toUpperCase());
    return {
      title: clean || path,
      badge: 'Page',
      path,
    };
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-16">
      {/* ── TOP HEADER / WORKSPACE & SITE TOOLBAR ──────────────────────── */}
      <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-600 flex items-center justify-center text-white shadow-md shadow-blue-500/20">
              <Globe className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-black text-slate-900 tracking-tight">Headless CMS Suite</h1>
                <span className="px-2 py-0.5 text-[11px] font-bold bg-blue-50 text-blue-700 border border-blue-200 rounded-full">
                  DM Role
                </span>
              </div>
              <p className="text-xs text-slate-500 mt-0.5">
                Multi-tenant content authoring, technical SEO automation, search indexing & privacy analytics
              </p>
            </div>
          </div>

          {/* Quick Selectors & Live Gateway Status */}
          <div className="flex flex-wrap items-center gap-2.5">
            {/* Dynamic Gateway Selector & Live Status Pill */}
            <button
              type="button"
              onClick={() => {
                setGatewayInput(currentGatewayUrl);
                setGatewayTestResult(null);
                setIsGatewayModalOpen(true);
              }}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold border transition cursor-pointer shadow-2xs hover:shadow-xs ${
                backendHealth.live
                  ? 'bg-emerald-50 text-emerald-800 border-emerald-200 hover:bg-emerald-100/80'
                  : 'bg-rose-50 text-rose-800 border-rose-200 hover:bg-rose-100/80'
              }`}
              title={`Gateway: ${currentGatewayUrl} (Click to configure or change URL)`}
            >
              <span
                className={`w-2 h-2 rounded-full ${
                  backendHealth.checking
                    ? 'bg-amber-400 animate-ping'
                    : backendHealth.live
                    ? 'bg-emerald-500 animate-pulse'
                    : 'bg-rose-500'
                }`}
              />
              <span className="truncate max-w-[190px] font-mono text-[11px]">
                {displayHost}
              </span>
              <Sliders className="w-3.5 h-3.5 opacity-60 hover:opacity-100 text-slate-600" />
            </button>

            {/* Workspace Switcher */}
            <select
              value={selectedWorkspaceId}
              onChange={(e) => handleWorkspaceChange(e.target.value)}
              disabled={loadingTenancy || workspaces.length === 0}
              className="px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {workspaces.map((w) => (
                <option key={w.id} value={w.id}>
                  🏢 {w.name}
                </option>
              ))}
            </select>

            {/* Site Switcher */}
            <select
              value={selectedSiteId}
              onChange={(e) => handleSiteChange(e.target.value)}
              disabled={loadingTenancy || sites.length === 0}
              className="px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-semibold text-slate-800 focus:outline-none focus:ring-2 focus:ring-blue-500 max-w-[200px]"
            >
              {sites.map((s) => (
                <option key={s.id} value={s.id}>
                  🌐 {s.name} ({s.slug})
                </option>
              ))}
            </select>

            {/* New Site Button */}
            <button
              onClick={() => setIsCreateSiteOpen(true)}
              className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold transition shadow-xs"
            >
              <Plus className="w-3.5 h-3.5" />
              New Site
            </button>

            {/* Realtime API Inspector Drawer Toggle */}
            <button
              onClick={() => setIsInspectorOpen(!isInspectorOpen)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-bold transition border ${
                isInspectorOpen
                  ? 'bg-slate-900 text-white border-slate-900'
                  : 'bg-slate-100 hover:bg-slate-200 text-slate-700 border-slate-200'
              }`}
            >
              <Terminal className="w-3.5 h-3.5 text-blue-500" />
              Inspector
              {activityLogs.length > 0 && (
                <span className="w-4 h-4 text-[10px] rounded-full bg-blue-600 text-white flex items-center justify-center font-bold">
                  {activityLogs.length > 99 ? '99+' : activityLogs.length}
                </span>
              )}
            </button>
          </div>
        </div>

        {/* User Session Bar */}
        <div className="mt-4 pt-3 border-t border-slate-100 flex flex-wrap items-center justify-between text-xs text-slate-500 gap-2">
          <div className="flex items-center gap-2">
            <span className="text-slate-400">Authenticated Session:</span>
            <span className="font-semibold text-slate-700 bg-slate-100 px-2 py-0.5 rounded">
              {userEmail}
            </span>
            <span className="text-slate-400">|</span>
            <span className="text-slate-400">Active Site Domain:</span>
            <span className="font-mono text-slate-700">
              {activeSite?.slug ? `${activeSite.slug}.hikasimat.com` : 'No site active'}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={checkSystemHealth}
              className="text-blue-600 hover:text-blue-800 font-semibold flex items-center gap-1"
            >
              <RefreshCw className={`w-3 h-3 ${backendHealth.checking ? 'animate-spin' : ''}`} />
              Re-probe Health
            </button>
          </div>
        </div>
      </div>

      {/* ── GATEWAY OFFLINE ALERT BANNER ─────────────────────────────────── */}
      {!backendHealth.live && !backendHealth.checking && (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-3 text-amber-950 shadow-xs animate-in fade-in duration-200">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-amber-100 flex items-center justify-center text-amber-700 shrink-0">
              <AlertTriangle className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs font-bold text-amber-950 flex items-center gap-1.5">
                <span>CMS Gateway Unreachable</span>
                <span className="font-mono text-[11px] font-normal text-amber-800 bg-amber-100/70 px-1.5 py-0.5 rounded">
                  {displayHost}
                </span>
              </p>
              <p className="text-[11px] text-amber-800 mt-0.5">
                The endpoint did not respond to health probes. If your Cloudflare Tunnel restarted, update the gateway URL or switch to local server.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => handleSaveGateway('http://localhost:8001')}
              className="px-3 py-1.5 text-xs font-bold bg-white hover:bg-amber-100 text-amber-900 border border-amber-300 rounded-lg transition shadow-2xs flex items-center gap-1 cursor-pointer"
            >
              ⚡ Switch to localhost:8001
            </button>
            <button
              type="button"
              onClick={() => {
                setGatewayInput(currentGatewayUrl);
                setGatewayTestResult(null);
                setIsGatewayModalOpen(true);
              }}
              className="px-3 py-1.5 text-xs font-bold bg-amber-600 hover:bg-amber-700 text-white rounded-lg transition shadow-xs flex items-center gap-1 cursor-pointer"
            >
              <Sliders className="w-3.5 h-3.5" />
              Configure Gateway
            </button>
            <button
              type="button"
              onClick={checkSystemHealth}
              disabled={backendHealth.checking}
              className="p-1.5 text-amber-700 hover:text-amber-950 rounded-lg hover:bg-amber-100 transition cursor-pointer"
              title="Retry connection"
            >
              <RefreshCw className={`w-4 h-4 ${backendHealth.checking ? 'animate-spin' : ''}`} />
            </button>
          </div>
        </div>
      )}

      {/* ── MODAL: CONFIGURE GATEWAY URL ───────────────────────────────── */}
      {isGatewayModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-lg w-full p-6 animate-in fade-in zoom-in-95 duration-150 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 flex items-center justify-center">
                  <Sliders className="w-4 h-4" />
                </div>
                <div>
                  <h2 className="text-base font-bold text-slate-900">Configure Headless CMS Gateway</h2>
                  <p className="text-[11px] text-slate-500">Update API gateway dynamically without restarting servers</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsGatewayModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Current Active Info */}
            <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between text-xs">
              <div>
                <span className="text-slate-400 text-[10px] uppercase font-bold block">Current Active URL</span>
                <span className="font-mono font-semibold text-slate-800 break-all">{currentGatewayUrl}</span>
              </div>
              <span
                className={`px-2 py-0.5 rounded-full text-[10px] font-bold shrink-0 ${
                  backendHealth.live
                    ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                    : 'bg-rose-50 text-rose-700 border border-rose-200'
                }`}
              >
                {backendHealth.live ? '● Connected' : '○ Offline'}
              </span>
            </div>

            {/* Target URL Input */}
            <div className="space-y-1.5">
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
                CMS Gateway URL (Local or Cloudflare Tunnel)
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={gatewayInput}
                  onChange={(e) => {
                    setGatewayInput(e.target.value);
                    setGatewayTestResult(null);
                  }}
                  placeholder="https://your-tunnel.trycloudflare.com or http://localhost:8001"
                  className="flex-1 px-3 py-2 border border-slate-300 rounded-lg text-xs font-mono focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
                <button
                  type="button"
                  onClick={() => handleTestGateway()}
                  disabled={gatewayTesting || !gatewayInput.trim()}
                  className="px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-bold transition flex items-center gap-1 shrink-0 disabled:opacity-50 cursor-pointer"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${gatewayTesting ? 'animate-spin' : ''}`} />
                  Test
                </button>
              </div>
              <p className="text-[11px] text-slate-500">
                Supports full URLs including protocol: <code>http://localhost:8001</code> or <code>https://...trycloudflare.com</code>
              </p>
            </div>

            {/* Test Connection Probe Feedback */}
            {gatewayTestResult && (
              <div
                className={`p-3 rounded-xl border text-xs font-mono flex items-center justify-between ${
                  gatewayTestResult.ok
                    ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                    : 'bg-rose-50 text-rose-800 border-rose-200'
                }`}
              >
                <div className="flex items-center gap-2">
                  {gatewayTestResult.ok ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                  ) : (
                    <XCircle className="w-4 h-4 text-rose-600 shrink-0" />
                  )}
                  <span>
                    {gatewayTestResult.ok
                      ? `Probe Successful! Live status 200 OK (${gatewayTestResult.latency}ms)`
                      : `Probe Failed: ${gatewayTestResult.error}`}
                  </span>
                </div>
              </div>
            )}

            {/* Quick Presets */}
            <div className="space-y-2">
              <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block">
                Quick Presets
              </span>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                <button
                  type="button"
                  onClick={() => {
                    setGatewayInput('http://localhost:8001');
                    handleTestGateway('http://localhost:8001');
                  }}
                  className="p-2.5 rounded-lg border border-slate-200 hover:border-blue-400 bg-slate-50/60 hover:bg-blue-50/50 text-left transition group cursor-pointer"
                >
                  <div className="font-bold text-slate-800 group-hover:text-blue-700 flex items-center gap-1">
                    ⚡ Local CMS (Port 8001)
                  </div>
                  <div className="text-[11px] font-mono text-slate-500 truncate">http://localhost:8001</div>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    const detected = 'https://angels-outlined-pick-similar.trycloudflare.com';
                    setGatewayInput(detected);
                    handleTestGateway(detected);
                  }}
                  className="p-2.5 rounded-lg border border-slate-200 hover:border-blue-400 bg-slate-50/60 hover:bg-blue-50/50 text-left transition group cursor-pointer"
                >
                  <div className="font-bold text-slate-800 group-hover:text-blue-700 flex items-center gap-1">
                    🌐 Active Tunnel
                  </div>
                  <div className="text-[11px] font-mono text-slate-500 truncate">angels-outlined-pick-similar...</div>
                </button>
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-between pt-3 border-t border-slate-100">
              <button
                type="button"
                onClick={handleResetGateway}
                className="text-xs text-slate-500 hover:text-slate-800 underline cursor-pointer"
              >
                Reset to default
              </button>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setIsGatewayModalOpen(false)}
                  className="px-4 py-2 text-xs font-bold text-slate-600 hover:bg-slate-100 rounded-lg transition cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => handleSaveGateway()}
                  disabled={!gatewayInput.trim()}
                  className="px-4 py-2 text-xs font-bold bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition shadow-xs flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                >
                  <Check className="w-3.5 h-3.5" />
                  Save & Connect
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── MODAL: CREATE NEW SITE ────────────────────────────────────── */}
      {isCreateSiteOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-md w-full p-6 animate-in fade-in zoom-in-95 duration-150">
            <div className="flex items-center justify-between mb-4 pb-2 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Globe className="w-5 h-5 text-blue-600" />
                <h2 className="text-base font-bold text-slate-900">Register New Publication Site</h2>
              </div>
              <button
                onClick={() => setIsCreateSiteOpen(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateSite} className="space-y-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                  Site Name / URL
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. AI Innovations Today or https://ai-innovations.com"
                  value={newSiteName}
                  onChange={(e) => {
                    setNewSiteName(e.target.value);
                    if (!newSiteSlug) {
                      setNewSiteSlug(
                        e.target.value
                          .toLowerCase()
                          .replace(/^https?:\/\//i, '')
                          .replace(/[^a-z0-9]+/g, '-')
                          .replace(/^-|-$/g, '')
                      );
                    }
                  }}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                  Canonical Slug
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. ai-innovations-today"
                  value={newSiteSlug}
                  onChange={(e) => setNewSiteSlug(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                  Default Locale
                </label>
                <input
                  type="text"
                  value={newSiteLocale}
                  onChange={(e) => setNewSiteLocale(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsCreateSiteOpen(false)}
                  className="px-4 py-2 border border-slate-200 text-slate-600 rounded-lg text-xs font-bold hover:bg-slate-50 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creatingSite}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold transition flex items-center gap-1.5"
                >
                  {creatingSite && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                  Register Site
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── MAIN TAB NAVIGATION ───────────────────────────────────────── */}
      <div className="border-b border-slate-200">
        <nav className="flex space-x-2 sm:space-x-4 overflow-x-auto pb-1">
          {[
            { id: 'articles', label: 'Articles & Content', icon: FileText, count: articles.length },
            {
              id: 'inspector',
              label: 'Publishing Pipeline',
              icon: Activity,
              highlight: inspectedArticle ? 'Active' : null,
            },
            { id: 'seo', label: 'Technical SEO & Indexing', icon: Search },
            { id: 'analytics', label: 'Privacy Analytics & GA4', icon: BarChart3 },
            { id: 'consent', label: 'Consent Manager (GDPR)', icon: ShieldCheck },
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => handleTabSwitch(tab.id)}
                className={`flex items-center gap-2 py-3 px-3.5 rounded-t-xl text-xs font-bold border-b-2 whitespace-nowrap transition-all ${
                  isActive
                    ? 'border-blue-600 text-blue-600 bg-blue-50/50'
                    : 'border-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                }`}
              >
                <Icon className={`w-4 h-4 ${isActive ? 'text-blue-600' : 'text-slate-400'}`} />
                {tab.label}
                {typeof tab.count === 'number' && (
                  <span
                    className={`ml-1 px-1.5 py-0.2 rounded-full text-[10px] font-bold ${
                      isActive ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600'
                    }`}
                  >
                    {tab.count}
                  </span>
                )}
                {tab.highlight && (
                  <span className="w-2 h-2 rounded-full bg-indigo-500 animate-ping" />
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* ─────────────────────────────────────────────────────────────── */}
      {/* TAB 1: ARTICLES & CONTENT PUBLISHING */}
      {/* ─────────────────────────────────────────────────────────────── */}
      {activeTab === 'articles' && (
        <div className="space-y-6">
          {/* Action Toolbar */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div className="flex items-center gap-2 flex-1 max-w-md">
              <div className="relative flex-1">
                <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
                <input
                  type="text"
                  placeholder="Filter articles by title or slug..."
                  value={articleSearch}
                  onChange={(e) => setArticleSearch(e.target.value)}
                  className="w-full pl-9 pr-3 py-1.5 bg-white border border-slate-200 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>
              <select
                value={articleFilter}
                onChange={(e) => setArticleFilter(e.target.value)}
                className="px-2.5 py-1.5 bg-white border border-slate-200 rounded-lg text-xs font-semibold text-slate-700 focus:outline-none"
              >
                <option value="ALL">All Statuses</option>
                <option value="PUBLISHED">Published Live Only</option>
                <option value="DRAFT">Drafts Only</option>
              </select>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={fetchPublicDelivery}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-bold transition"
              >
                <Code className="w-3.5 h-3.5 text-indigo-500" />
                Compare Public Delivery API
              </button>
              <button
                onClick={() => setIsCreateArticleOpen(!isCreateArticleOpen)}
                className="flex items-center gap-1.5 px-3.5 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold transition shadow-xs"
              >
                <Plus className="w-3.5 h-3.5" />
                Create Draft Article
              </button>
            </div>
          </div>

          {/* Collapsible: Create Article Card */}
          {isCreateArticleOpen && (
            <div className="bg-white border border-blue-200 rounded-2xl p-6 shadow-md animate-in fade-in duration-150">
              <div className="flex items-center justify-between mb-4 pb-2 border-b border-slate-100">
                <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                  <FileText className="w-4 h-4 text-blue-600" />
                  Author New Article for "{activeSite?.name || 'Selected Site'}"
                </h3>
                <button
                  onClick={() => setIsCreateArticleOpen(false)}
                  className="text-slate-400 hover:text-slate-600"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <form onSubmit={handleCreateArticle} className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                      Article Title *
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Next-Gen AI Agents in Enterprise Software"
                      value={newArtTitle}
                      onChange={(e) => {
                        setNewArtTitle(e.target.value);
                        if (!newArtSlug) {
                          setNewArtSlug(
                            e.target.value
                              .toLowerCase()
                              .replace(/[^a-z0-9]+/g, '-')
                              .replace(/^-|-$/g, '')
                          );
                        }
                      }}
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                      Slug *
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. next-gen-ai-agents"
                      value={newArtSlug}
                      onChange={(e) => setNewArtSlug(e.target.value)}
                      className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm font-mono focus:ring-2 focus:ring-blue-500 focus:outline-none"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                    Short Excerpt / Meta Description
                  </label>
                  <input
                    type="text"
                    placeholder="Brief description for search snippet and article cards..."
                    value={newArtExcerpt}
                    onChange={(e) => setNewArtExcerpt(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  />
                </div>

                <div>
                  <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                    Body Content (Markdown or HTML)
                  </label>
                  <textarea
                    rows={6}
                    value={newArtBody}
                    onChange={(e) => setNewArtBody(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs font-mono focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  />
                </div>

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setIsCreateArticleOpen(false)}
                    className="px-4 py-2 border border-slate-200 text-slate-600 rounded-lg text-xs font-bold hover:bg-slate-50 transition"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={creatingArticle}
                    className="px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold transition flex items-center gap-1.5 shadow-xs"
                  >
                    {creatingArticle && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                    Save Draft & Inspect Flow
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* Public Delivery API Comparison Modal / View */}
          {showPublicDelivery && (
            <div className="bg-slate-900 text-slate-100 rounded-2xl p-5 border border-slate-800 shadow-xl space-y-3">
              <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                    Live Public Delivery API Output: <code>/api/v1/public/sites/{activeSite?.slug}/articles/</code>
                  </h4>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={fetchPublicDelivery}
                    className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1 font-semibold"
                  >
                    <RefreshCw className={`w-3 h-3 ${loadingPublicDelivery ? 'animate-spin' : ''}`} />
                    Refresh Feed
                  </button>
                  <button
                    onClick={() => setShowPublicDelivery(false)}
                    className="text-slate-400 hover:text-white p-1"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>
              <pre className="text-[11px] font-mono p-3 bg-slate-950 rounded-lg max-h-56 overflow-y-auto text-emerald-400 border border-slate-800">
                {publicDeliveryData
                  ? JSON.stringify(publicDeliveryData, null, 2)
                  : loadingPublicDelivery
                  ? 'Fetching live public feed...'
                  : 'No public articles published yet.'}
              </pre>
            </div>
          )}

          {/* Articles Table Card */}
          <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-xs">
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-slate-900">Articles in Active Publication Site</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Drafts remain isolated in your workspace. Published articles are immediately delivered to the public API and search indexers.
                </p>
              </div>
              <button
                onClick={() => loadArticlesForSite(selectedWorkspaceId, selectedSiteId)}
                className="text-xs text-blue-600 hover:text-blue-700 font-semibold flex items-center gap-1"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loadingArticles ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-100 uppercase tracking-wider">
                    <th className="py-3 px-6">Title</th>
                    <th className="py-3 px-6">Slug</th>
                    <th className="py-3 px-6">Status</th>
                    <th className="py-3 px-6">Author & Versions</th>
                    <th className="py-3 px-6 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {loadingArticles ? (
                    <tr>
                      <td colSpan={5} className="py-8 text-center text-slate-400">
                        <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-blue-600" />
                        Loading publication articles...
                      </td>
                    </tr>
                  ) : filteredArticles.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-8 text-center text-slate-400">
                        No articles match the filter. Click "Create Draft Article" above to start authoring!
                      </td>
                    </tr>
                  ) : (
                    filteredArticles.map((art) => {
                      const isPublished = art.status === 'PUBLISHED';
                      return (
                        <tr key={art.id} className="hover:bg-slate-50/80 transition-colors">
                          <td className="py-3.5 px-6 font-bold text-slate-900 max-w-xs truncate">
                            {art.title}
                          </td>
                          <td className="py-3.5 px-6 font-mono text-slate-500">
                            {art.slug}
                          </td>
                          <td className="py-3.5 px-6">
                            <span
                              className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full font-bold text-[10px] border ${
                                isPublished
                                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                                  : 'bg-amber-50 text-amber-700 border-amber-200'
                              }`}
                            >
                              <span
                                className={`w-1.5 h-1.5 rounded-full ${
                                  isPublished ? 'bg-emerald-500' : 'bg-amber-500'
                                }`}
                              />
                              {isPublished ? 'LIVE PUBLISHED' : 'DRAFT (Private)'}
                            </span>
                          </td>
                          <td className="py-3.5 px-6 text-slate-500">
                            <div>{art.author?.email || 'admin@cms.local'}</div>
                            <div className="text-[10px] text-slate-400">
                              Revisions: {art.versions_count || 1}
                            </div>
                          </td>
                          <td className="py-3.5 px-6 text-right space-x-2">
                            <button
                              onClick={() => handlePublishArticle(art)}
                              className={`px-3 py-1 rounded-lg text-xs font-bold transition ${
                                isPublished
                                  ? 'bg-slate-100 hover:bg-slate-200 text-slate-700'
                                  : 'bg-emerald-600 hover:bg-emerald-700 text-white shadow-xs'
                              }`}
                            >
                              {isPublished ? 'Re-Publish' : '🚀 Publish'}
                            </button>

                            <button
                              onClick={() => inspectPipeline(art)}
                              className="px-3 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 rounded-lg text-xs font-bold transition inline-flex items-center gap-1"
                            >
                              <Activity className="w-3 h-3" />
                              Inspect Flow
                            </button>

                            <button
                              onClick={() => handleDeleteArticle(art)}
                              className="p-1 text-slate-400 hover:text-rose-600 rounded-md transition"
                              title="Delete Article"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────── */}
      {/* TAB 2: 7-STEP ARTICLE PUBLISHING PIPELINE INSPECTOR */}
      {/* ─────────────────────────────────────────────────────────────── */}
      {activeTab === 'inspector' && (
        <div className="space-y-6">
          <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs">
            <div className="flex flex-col md:flex-row md:items-center justify-between pb-4 border-b border-slate-100 gap-4">
              <div>
                <div className="flex items-center gap-2">
                  <Activity className="w-5 h-5 text-indigo-600" />
                  <h3 className="text-base font-bold text-slate-900">
                    Article Publishing Pipeline Flow Inspector
                  </h3>
                  {pipelineData && (
                    <span
                      className={`px-2.5 py-0.5 rounded-full text-xs font-bold border ${
                        pipelineData.overall_status === 'SUCCESS'
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                          : pipelineData.overall_status === 'WARNING'
                          ? 'bg-amber-50 text-amber-700 border-amber-200'
                          : 'bg-rose-50 text-rose-700 border-rose-200'
                      }`}
                    >
                      {pipelineData.overall_status === 'SUCCESS'
                        ? '✔ ALL SYSTEMS HEALTHY (SUCCESS)'
                        : pipelineData.overall_status === 'WARNING'
                        ? '⚠ WARNING / IN-FLIGHT'
                        : '✖ PIPELINE ERRORS'}
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-500 mt-1">
                  Verifies end-to-end publishing health across schema integrity, versioning, site domain, delivery feed, dynamic XML sitemaps, search engine indexing, and audit trail.
                </p>
              </div>

              <div className="flex items-center gap-2">
                {inspectedArticle && (
                  <button
                    onClick={() => inspectPipeline(inspectedArticle)}
                    disabled={loadingPipeline}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 rounded-lg text-xs font-bold transition"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 ${loadingPipeline ? 'animate-spin' : ''}`} />
                    Re-check Pipeline
                  </button>
                )}
                <button
                  onClick={() => setActiveTab('articles')}
                  className="px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-bold transition"
                >
                  Back to Articles
                </button>
              </div>
            </div>

            {/* Article Context Meta */}
            {inspectedArticle ? (
              <div className="mt-4 p-3 bg-slate-50 rounded-xl border border-slate-200/60 flex flex-wrap items-center justify-between text-xs gap-2">
                <div>
                  <span className="text-slate-400 mr-1">Target Article:</span>
                  <strong className="text-slate-900 font-bold mr-3">{inspectedArticle.title}</strong>
                  <span className="font-mono text-slate-500 mr-3">({inspectedArticle.slug})</span>
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                      inspectedArticle.status === 'PUBLISHED'
                        ? 'bg-emerald-100 text-emerald-800'
                        : 'bg-amber-100 text-amber-800'
                    }`}
                  >
                    {inspectedArticle.status}
                  </span>
                </div>
                <div className="text-slate-500 font-mono text-[11px]">
                  ID: {inspectedArticle.id}
                </div>
              </div>
            ) : (
              <div className="mt-6 text-center py-10 bg-slate-50 rounded-xl border border-dashed border-slate-200 text-slate-500 text-xs">
                <FileText className="w-8 h-8 text-slate-400 mx-auto mb-2" />
                Select an article from the "Articles & Content" tab and click "Inspect Flow" to analyze its 7-step pipeline.
              </div>
            )}

            {/* Step Progression List */}
            {loadingPipeline ? (
              <div className="py-12 text-center text-slate-400">
                <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-600" />
                Analyzing 7-step pipeline diagnostics...
              </div>
            ) : pipelineData?.steps ? (
              <div className="mt-6 space-y-3.5">
                {pipelineData.steps.map((step, idx) => {
                  const isPassed = step.status === 'PASSED';
                  const isPending = step.status === 'PENDING' || step.status === 'WARNING';
                  const isFailed = step.status === 'FAILED';

                  return (
                    <div
                      key={step.step || idx}
                      className={`p-4 rounded-xl border transition ${
                        isFailed
                          ? 'bg-rose-50/60 border-rose-200'
                          : isPassed
                          ? 'bg-slate-50/80 border-slate-200 hover:border-slate-300'
                          : 'bg-amber-50/60 border-amber-200'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <div className="flex items-center gap-2">
                          <span className="w-6 h-6 rounded-full bg-slate-200/80 text-slate-700 font-bold text-xs flex items-center justify-center">
                            {idx + 1}
                          </span>
                          <h4 className="text-sm font-bold text-slate-900">{step.title}</h4>
                        </div>
                        <span
                          className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${
                            isPassed
                              ? 'bg-emerald-100 text-emerald-800 border-emerald-300'
                              : isPending
                              ? 'bg-amber-100 text-amber-800 border-amber-300'
                              : isFailed
                              ? 'bg-rose-100 text-rose-800 border-rose-300'
                              : 'bg-slate-200 text-slate-700 border-slate-300'
                          }`}
                        >
                          {step.status}
                        </span>
                      </div>

                      <p className="text-xs text-slate-600 ml-8">{step.details}</p>

                      {/* Error details callout */}
                      {step.error && (
                        <div className="mt-2.5 ml-8 p-3 rounded-lg bg-rose-100/80 border border-rose-300 text-rose-800 text-xs font-mono">
                          <strong>Error:</strong> {step.error}
                        </div>
                      )}

                      {/* Search Indexing Submission Logs table */}
                      {step.logs && step.logs.length > 0 && (
                        <div className="mt-3 ml-8 border border-slate-200 rounded-lg overflow-hidden bg-white">
                          <table className="w-full text-left text-[11px]">
                            <thead className="bg-slate-100 text-slate-600 font-semibold uppercase">
                              <tr>
                                <th className="p-2">Provider</th>
                                <th className="p-2">Status</th>
                                <th className="p-2">HTTP</th>
                                <th className="p-2">Response / Result</th>
                                <th className="p-2">Timestamp</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                              {step.logs.map((log, lIdx) => (
                                <tr key={lIdx}>
                                  <td className="p-2 font-bold">{log.provider}</td>
                                  <td className="p-2">
                                    <span
                                      className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                        log.status === 'SUCCESS' || log.status === 'SUBMITTED'
                                          ? 'bg-emerald-100 text-emerald-800'
                                          : 'bg-rose-100 text-rose-800'
                                      }`}
                                    >
                                      {log.status}
                                    </span>
                                  </td>
                                  <td className="p-2 font-mono">{log.response_code || 'N/A'}</td>
                                  <td className="p-2 font-mono text-slate-500 max-w-xs truncate">
                                    {log.response_body || 'None'}
                                  </td>
                                  <td className="p-2 text-slate-400">
                                    {new Date(log.created_at).toLocaleTimeString()}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}

                      {/* Audit Events */}
                      {step.events && step.events.length > 0 && (
                        <div className="mt-2 ml-8 space-y-1 text-[11px] text-slate-500">
                          {step.events.map((evt, eIdx) => (
                            <div key={eIdx} className="flex items-center gap-1.5">
                              <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                              <span>
                                <strong>{evt.action}</strong> by <code>{evt.actor}</code> at{' '}
                                {new Date(evt.timestamp).toLocaleTimeString()}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : null}
          </div>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────── */}
      {/* TAB 3: TECHNICAL SEO & SEARCH ENGINE INDEXING */}
      {/* ─────────────────────────────────────────────────────────────── */}
      {activeTab === 'seo' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Realtime Submission Tool */}
            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-4">
              <div className="flex items-center gap-2 pb-2 border-b border-slate-100">
                <Send className="w-5 h-5 text-blue-600" />
                <h3 className="text-sm font-bold text-slate-900">
                  Real-time Search Engine Indexing (Google & Bing)
                </h3>
              </div>
              <p className="text-xs text-slate-500">
                Submit newly created or updated URLs directly to search crawlers via Google Indexing API and IndexNow Protocol.
              </p>

              <form onSubmit={handleSubmitIndexing} className="space-y-3.5">
                <div>
                  <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                    Indexing Provider
                  </label>
                  <select
                    value={indexingProvider}
                    onChange={(e) => setIndexingProvider(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs font-semibold focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  >
                    <option value="GOOGLE">Google Search Console (Indexing API)</option>
                    <option value="BING">Bing Webmaster (IndexNow)</option>
                    <option value="INDEXNOW">IndexNow Open Protocol</option>
                  </select>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider">
                      Target URL to Index
                    </label>
                    {articles.length > 0 && (
                      <span className="text-[11px] text-blue-600 font-medium">
                        {articles.filter((a) => a.status === 'PUBLISHED').length} Published Article(s)
                      </span>
                    )}
                  </div>

                  {/* Quick Select from Published Articles */}
                  {articles.length > 0 && (
                    <div className="mb-2">
                      <select
                        onChange={(e) => {
                          if (e.target.value) {
                            setIndexingUrl(e.target.value);
                          }
                        }}
                        className="w-full px-3 py-1.5 border border-slate-200 bg-slate-50 hover:bg-slate-100 rounded-lg text-xs font-medium text-slate-700 focus:ring-2 focus:ring-blue-500 focus:outline-none"
                      >
                        <option value="">⚡ Quick Select a Published Article to Index...</option>
                        {articles.map((art) => {
                          const siteSlug = activeSite?.slug || 'site';
                          const artUrl = `https://${siteSlug}.hikasimat.com/articles/${art.slug}`;
                          return (
                            <option key={art.id} value={artUrl}>
                              {art.title} ({art.status}) — /articles/{art.slug}
                            </option>
                          );
                        })}
                      </select>
                    </div>
                  )}

                  <input
                    type="url"
                    required
                    value={indexingUrl}
                    onChange={(e) => setIndexingUrl(e.target.value)}
                    placeholder="https://example.com/articles/my-post"
                    className="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs font-mono focus:ring-2 focus:ring-blue-500 focus:outline-none"
                  />
                  <p className="mt-1 text-[11px] text-slate-500">
                    Directly notifies search engines (Google Indexing API / Bing IndexNow) to immediately crawl and index this specific live URL, skipping the normal sitemap crawl delay.
                  </p>
                </div>

                <div className="flex items-center justify-between pt-1">
                  {indexNowKey && (
                    <span className="text-[11px] font-mono text-slate-500">
                      Key: <code>{indexNowKey.substring(0, 12)}...</code>
                    </span>
                  )}
                  <button
                    type="submit"
                    disabled={submittingIndexing}
                    className="ml-auto px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold transition flex items-center gap-1.5 shadow-xs"
                  >
                    {submittingIndexing && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                    Submit for Indexing
                  </button>
                </div>
              </form>
            </div>

            {/* Dynamic XML Sitemap & Robots Preview */}
            <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-4">
              <div className="flex items-center justify-between pb-2 border-b border-slate-100">
                <div className="flex items-center gap-2">
                  <Search className="w-5 h-5 text-indigo-600" />
                  <h3 className="text-sm font-bold text-slate-900">Dynamic SEO Feeds</h3>
                </div>
                <div className="flex items-center gap-1 bg-slate-100 p-1 rounded-lg">
                  <button
                    onClick={() => loadSeoPreview('sitemap')}
                    className={`px-2.5 py-1 rounded text-xs font-bold transition ${
                      seoPreviewType === 'sitemap' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600'
                    }`}
                  >
                    Sitemap.xml
                  </button>
                  <button
                    onClick={() => loadSeoPreview('robots')}
                    className={`px-2.5 py-1 rounded text-xs font-bold transition ${
                      seoPreviewType === 'robots' ? 'bg-white text-slate-900 shadow-xs' : 'text-slate-600'
                    }`}
                  >
                    Robots.txt
                  </button>
                </div>
              </div>

              <div className="relative">
                <pre className="text-[11px] font-mono p-3 bg-slate-900 text-indigo-300 rounded-xl max-h-52 overflow-y-auto border border-slate-800">
                  {loadingSeoPreview ? 'Loading feed...' : seoPreviewText || 'Click a preview button above.'}
                </pre>
                {activeSite && (
                  <div className="mt-3 space-y-2.5">
                    <div className="flex items-center justify-between">
                      <span className="text-xs text-slate-500 font-medium">
                        Live Public Feed Endpoint:
                      </span>
                      <button
                        type="button"
                        onClick={() => {
                          const url = `${getCmsBaseUrl()}/api/v1/public/sites/${activeSite.slug}/${
                            seoPreviewType === 'sitemap' ? 'sitemap.xml' : 'robots.txt'
                          }`;
                          navigator.clipboard.writeText(url);
                          toast.success('Live URL copied to clipboard!');
                        }}
                        className="text-xs text-blue-600 hover:text-blue-800 flex items-center gap-1 font-bold bg-blue-50 hover:bg-blue-100 px-2.5 py-1 rounded-lg transition"
                      >
                        <Copy className="w-3.5 h-3.5" />
                        Copy Live Feed URL
                      </button>
                    </div>

                    {/* Step-by-step submission instructions */}
                    <div className="p-3 bg-slate-50 rounded-xl border border-slate-200 text-xs space-y-1.5 text-slate-600">
                      <div className="font-bold text-slate-800 flex items-center gap-1.5">
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                        Where to submit or paste this copied URL:
                      </div>
                      <ul className="list-disc pl-4 space-y-1 text-[11px]">
                        <li>
                          <strong>Google Search Console:</strong> Go to <em>search.google.com/search-console</em> → Select your verified property → Click <strong>Sitemaps</strong> in the left sidebar → Paste this URL and click <strong>Submit</strong>.
                        </li>
                        <li>
                          <strong>Bing Webmaster Tools:</strong> Go to <em>bing.com/webmasters</em> → Select site → <strong>Sitemaps</strong> → <strong>Submit Sitemap</strong>.
                        </li>
                        <li>
                          <strong>Frontend Blog Website:</strong> In your public website's <code>robots.txt</code> file, add the line:
                          <br />
                          <code className="text-blue-700 bg-white px-1.5 py-0.5 rounded border border-slate-200 block mt-0.5 overflow-x-auto">
                            Sitemap: {getCmsBaseUrl()}/api/v1/public/sites/{activeSite.slug}/sitemap.xml
                          </code>
                        </li>
                      </ul>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Submission Audit Logs */}
          <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-xs">
            <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-slate-900">Recent Search Engine Submission History</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Audit trail of indexing requests dispatched to Google Search Console and Bing.
                </p>
              </div>
              <button
                onClick={loadIndexingLogs}
                className="text-xs text-blue-600 hover:text-blue-700 font-semibold flex items-center gap-1"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loadingIndexingLogs ? 'animate-spin' : ''}`} />
                Refresh Logs
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-100 uppercase tracking-wider">
                    <th className="py-2.5 px-6">Provider</th>
                    <th className="py-2.5 px-6">Status</th>
                    <th className="py-2.5 px-6">HTTP Status</th>
                    <th className="py-2.5 px-6">Response Details</th>
                    <th className="py-2.5 px-6">Dispatched At</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {indexingLogs.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-6 text-center text-slate-400">
                        No submissions recorded for this publication site yet.
                      </td>
                    </tr>
                  ) : (
                    indexingLogs.map((log) => (
                      <tr key={log.id} className="hover:bg-slate-50">
                        <td className="py-2.5 px-6 font-bold text-slate-800">{log.provider}</td>
                        <td className="py-2.5 px-6">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              log.status === 'SUCCESS' || log.status === 'SUBMITTED'
                                ? 'bg-emerald-100 text-emerald-800'
                                : 'bg-rose-100 text-rose-800'
                            }`}
                          >
                            {log.status}
                          </span>
                        </td>
                        <td className="py-2.5 px-6 font-mono text-slate-600">
                          {log.response_code || '200 OK'}
                        </td>
                        <td className="py-2.5 px-6 font-mono text-slate-500 max-w-sm truncate">
                          {log.response_body || 'Acknowledged'}
                        </td>
                        <td className="py-2.5 px-6 text-slate-400">
                          {new Date(log.created_at).toLocaleString()}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────── */}
      {/* TAB 4: PRIVACY ANALYTICS & GA4 */}
      {/* ─────────────────────────────────────────────────────────────── */}
      {activeTab === 'analytics' && (
        <div className="space-y-6">
          {/* Active Publication Site Scope Banner */}
          <div className="p-4 bg-gradient-to-r from-blue-50/90 to-indigo-50/90 border border-blue-200/80 rounded-2xl flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-blue-950 shadow-2xs">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-blue-600 text-white flex items-center justify-center shrink-0 shadow-sm shadow-blue-500/20">
                <Globe className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-bold text-sm text-slate-900">
                    Live Telemetry for Publication Site: {activeSite?.name || 'Selected Site'}
                  </span>
                  <code className="text-[11px] bg-white px-2 py-0.5 rounded border border-blue-200 text-blue-700 font-bold">
                    {activeSite?.slug || 'slug'}.hikasimat.com
                  </code>
                </div>
                <p className="text-[11px] text-slate-600 mt-0.5">
                  Metrics below are generated by public visitors (and tests) on this website's public delivery endpoint. This is <em>not</em> internal Market Intel DB platform telemetry.
                </p>
              </div>
            </div>
            <button
              onClick={loadAnalytics}
              className="text-xs text-blue-700 hover:text-blue-900 font-bold flex items-center gap-1.5 px-3 py-1.5 bg-white hover:bg-blue-50 rounded-lg border border-blue-200 transition shrink-0 cursor-pointer shadow-2xs"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingAnalytics ? 'animate-spin' : ''}`} />
              Refresh Metrics
            </button>
          </div>

          {/* Top KPI Metric Cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {[
              {
                label: 'Total Events',
                value: analyticsOverview?.summary?.total_events ?? 0,
                icon: Activity,
                color: 'text-blue-600',
                bg: 'bg-blue-50',
              },
              {
                label: 'Unique Visitors',
                value: analyticsOverview?.summary?.unique_visitors ?? 0,
                icon: Users,
                color: 'text-indigo-600',
                bg: 'bg-indigo-50',
              },
              {
                label: 'Page Views',
                value: analyticsOverview?.summary?.page_views ?? 0,
                icon: Eye,
                color: 'text-emerald-600',
                bg: 'bg-emerald-50',
              },
              {
                label: 'CTA / Form Clicks',
                value:
                  (analyticsOverview?.summary?.cta_clicks ?? 0) +
                  (analyticsOverview?.summary?.form_submits ?? 0),
                icon: MousePointerClick,
                color: 'text-amber-600',
                bg: 'bg-amber-50',
              },
            ].map((kpi, idx) => {
              const Icon = kpi.icon;
              return (
                <div key={idx} className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs">
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
                      {kpi.label}
                    </span>
                    <div className={`p-2 rounded-xl ${kpi.bg} ${kpi.color}`}>
                      <Icon className="w-4 h-4" />
                    </div>
                  </div>
                  <div className="text-2xl font-black text-slate-900 tracking-tight">
                    {loadingAnalytics ? '...' : kpi.value}
                  </div>
                </div>
              );
            })}
          </div>

          {/* First-Party Telemetry Status & Toggle */}
          <div className="bg-white border border-slate-200 rounded-2xl p-5 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div
                className={`w-10 h-10 rounded-xl flex items-center justify-center font-bold text-sm ${
                  analyticsConfig?.is_first_party_enabled
                    ? 'bg-emerald-50 text-emerald-600'
                    : 'bg-amber-50 text-amber-600'
                }`}
              >
                <ShieldCheck className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h4 className="text-sm font-bold text-slate-900">First-Party Telemetry Ingestion</h4>
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                      analyticsConfig?.is_first_party_enabled
                        ? 'bg-emerald-100 text-emerald-800'
                        : 'bg-amber-100 text-amber-800'
                    }`}
                  >
                    {analyticsConfig?.is_first_party_enabled ? 'Active / Enabled' : 'Disabled'}
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-0.5">
                  Privacy-preserving zero-PII telemetry pipeline (GDPR compliant pseudonymous hashes, retention {analyticsConfig?.retention_days || 90} days).
                </p>
              </div>
            </div>

            <button
              type="button"
              disabled={togglingIngestion}
              onClick={() => handleToggleFirstParty(!analyticsConfig?.is_first_party_enabled)}
              className={`px-4 py-2 rounded-lg text-xs font-bold transition flex items-center gap-1.5 cursor-pointer shadow-xs shrink-0 ${
                analyticsConfig?.is_first_party_enabled
                  ? 'bg-slate-100 hover:bg-slate-200 text-slate-700'
                  : 'bg-emerald-600 hover:bg-emerald-700 text-white'
              }`}
            >
              {togglingIngestion && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
              {analyticsConfig?.is_first_party_enabled ? 'Disable Ingestion' : 'Enable Ingestion'}
            </button>
          </div>

          {/* Event Ingestion Simulator Card */}
          <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-amber-500" />
                <h3 className="text-sm font-bold text-slate-900">
                  Simulate First-Party Inbound Telemetry
                </h3>
              </div>
              <button
                onClick={loadAnalytics}
                className="text-xs text-blue-600 hover:text-blue-700 font-semibold flex items-center gap-1"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loadingAnalytics ? 'animate-spin' : ''}`} />
                Refresh Metrics
              </button>
            </div>
            <p className="text-xs text-slate-500">
              Fire anonymous telemetry pings through the public event endpoint (zero IP storage, pseudonymous session hashes).
            </p>

            <div className="flex flex-wrap gap-2.5">
              <button
                onClick={() => handleSimulateEvent('page_view', '/blog/post-1')}
                disabled={simulatingEvent}
                className="px-3.5 py-2 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg text-xs font-bold transition flex items-center gap-1.5"
              >
                <Eye className="w-3.5 h-3.5 text-blue-600" />
                Simulate Page View (/blog/post-1)
              </button>
              <button
                onClick={() => handleSimulateEvent('cta_click', '/pricing')}
                disabled={simulatingEvent}
                className="px-3.5 py-2 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg text-xs font-bold transition flex items-center gap-1.5"
              >
                <MousePointerClick className="w-3.5 h-3.5 text-indigo-600" />
                Simulate CTA Click (/pricing)
              </button>
              <button
                onClick={() => handleSimulateEvent('form_submit', '/contact')}
                disabled={simulatingEvent}
                className="px-3.5 py-2 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg text-xs font-bold transition flex items-center gap-1.5"
              >
                <Send className="w-3.5 h-3.5 text-emerald-600" />
                Simulate Form Submit (/contact)
              </button>
            </div>
          </div>

          {/* Top Paths & Device Breakdown */}
          {analyticsOverview && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Top Visited Pages & Articles */}
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs">
                <div className="flex items-center justify-between mb-3">
                  <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                    Top Visited Pages & Articles
                  </h4>
                  <span className="text-[11px] text-slate-400 font-medium">
                    Resolved from Articles & Route Paths
                  </span>
                </div>
                <div className="space-y-2.5">
                  {analyticsOverview.top_paths?.length > 0 ? (
                    analyticsOverview.top_paths.map((p, idx) => {
                      const details = resolvePageDetails(p.path);
                      return (
                        <div
                          key={idx}
                          className="flex items-center justify-between p-2.5 bg-slate-50 hover:bg-slate-100/70 rounded-xl transition border border-slate-100/80"
                        >
                          <div className="min-w-0 pr-3">
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-xs text-slate-900 truncate">
                                {details.title}
                              </span>
                              <span
                                className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                  details.badge === 'Article'
                                    ? 'bg-blue-100 text-blue-800'
                                    : details.badge === 'Static'
                                    ? 'bg-indigo-100 text-indigo-800'
                                    : details.badge === 'Index'
                                    ? 'bg-emerald-100 text-emerald-800'
                                    : 'bg-slate-200 text-slate-700'
                                }`}
                              >
                                {details.badge}
                              </span>
                            </div>
                            <div className="text-[11px] font-mono text-slate-400 truncate mt-0.5">
                              {p.path}
                            </div>
                          </div>
                          <span className="font-bold text-xs text-blue-600 bg-blue-50 border border-blue-100 px-2.5 py-1 rounded-lg shrink-0">
                            {p.views} {p.views === 1 ? 'view' : 'views'}
                          </span>
                        </div>
                      );
                    })
                  ) : (
                    <div className="text-xs text-slate-400 py-4 text-center">
                      No path events recorded yet.
                    </div>
                  )}
                </div>
              </div>

              {/* Device Breakdown */}
              <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs">
                <h4 className="text-xs font-bold text-slate-700 uppercase tracking-wider mb-3">
                  Device Category Breakdown
                </h4>
                <div className="grid grid-cols-3 gap-3 text-center">
                  {['DESKTOP', 'TABLET', 'MOBILE'].map((device) => {
                    const count = analyticsOverview.device_breakdown?.[device] || 0;
                    return (
                      <div key={device} className="p-4 bg-slate-50 rounded-xl border border-slate-100">
                        <div className="text-xs font-bold text-slate-500 uppercase">{device}</div>
                        <div className="text-xl font-black text-slate-900 mt-1">{count}</div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* Google Analytics 4 (GA4) Card */}
          <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <BarChart3 className="w-5 h-5 text-indigo-600" />
                <h3 className="text-sm font-bold text-slate-900">Google Analytics 4 (GA4) Integration</h3>
              </div>
              <button
                onClick={fetchGa4LiveReport}
                disabled={loadingGa4Report}
                className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-bold transition flex items-center gap-1.5 shadow-xs"
              >
                {loadingGa4Report && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                Fetch GA4 Live Report
              </button>
            </div>
            <p className="text-xs text-slate-500">
              Server-side GA4 reporting with automatic OAuth refresh and aggregated reporting queries.
            </p>

            {ga4ReportData && (
              <pre className="text-[11px] font-mono p-3 bg-slate-900 text-indigo-300 rounded-xl max-h-56 overflow-y-auto border border-slate-800">
                {JSON.stringify(ga4ReportData, null, 2)}
              </pre>
            )}
          </div>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────── */}
      {/* TAB 5: CONSENT MANAGER (GDPR / CCPA) */}
      {/* ─────────────────────────────────────────────────────────────── */}
      {activeTab === 'consent' && (
        <div className="space-y-6">
          <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-xs space-y-4">
            <div className="flex items-center gap-2 pb-2 border-b border-slate-100">
              <ShieldCheck className="w-5 h-5 text-emerald-600" />
              <h3 className="text-sm font-bold text-slate-900">
                GDPR Art. 7 & Google Consent Mode (GCM v2) Manager
              </h3>
            </div>
            <p className="text-xs text-slate-500">
              Enforce verifiable audit records, dynamic consent versioning, and right-to-withdraw across global jurisdictions.
            </p>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                  Simulated Visitor Pseudonym
                </label>
                <input
                  type="text"
                  value={consentVisitorId}
                  onChange={(e) => setConsentVisitorId(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs font-mono focus:ring-2 focus:ring-blue-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                  Jurisdiction Mode
                </label>
                <select
                  value={consentJurisdiction}
                  onChange={(e) => setConsentJurisdiction(e.target.value)}
                  className="w-full px-3 py-2 border border-slate-300 rounded-lg text-xs font-semibold focus:ring-2 focus:ring-blue-500 focus:outline-none"
                >
                  <option value="EU_GDPR">EU (GDPR Strict Opt-In)</option>
                  <option value="US_CCPA">US (CCPA Opt-Out)</option>
                  <option value="GLOBAL">Global / Default</option>
                </select>
              </div>
            </div>

            <div className="flex flex-wrap gap-2.5 pt-2">
              <button
                onClick={() => handleRecordConsent(true, true)}
                disabled={recordingConsent}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold transition flex items-center gap-1.5 shadow-xs"
              >
                <Check className="w-3.5 h-3.5" />
                Grant All (Analytics + Ads)
              </button>
              <button
                onClick={() => handleRecordConsent(true, false)}
                disabled={recordingConsent}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg text-xs font-bold transition flex items-center gap-1.5"
              >
                <BarChart3 className="w-3.5 h-3.5 text-blue-600" />
                Analytics Only
              </button>
              <button
                onClick={() => handleRecordConsent(false, false)}
                disabled={recordingConsent}
                className="px-4 py-2 bg-rose-50 hover:bg-rose-100 text-rose-700 border border-rose-200 rounded-lg text-xs font-bold transition flex items-center gap-1.5"
              >
                <XCircle className="w-3.5 h-3.5" />
                Reject Non-Essential
              </button>
            </div>

            {consentResult && (
              <div className="mt-4 p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs font-mono space-y-2">
                <div className="flex items-center justify-between text-slate-500">
                  <span>Timestamp: {consentResult.timestamp}</span>
                  <span className="text-emerald-700 font-bold bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                    Consent Audit Record Persisted
                  </span>
                </div>
                <pre className="text-[11px] bg-white p-3 rounded border border-slate-200 overflow-x-auto text-slate-800">
                  {JSON.stringify(consentResult.data, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────── */}
      {/* SLIDE-OUT REALTIME API INSPECTOR DRAWER */}
      {/* ─────────────────────────────────────────────────────────────── */}
      {isInspectorOpen && (
        <aside className="fixed top-0 right-0 h-full w-full max-w-lg bg-slate-900 text-slate-100 z-50 shadow-2xl border-l border-slate-800 flex flex-col animate-in slide-in-from-right duration-200">
          <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-950">
            <div className="flex items-center gap-2">
              <Terminal className="w-4 h-4 text-blue-400" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-200">
                Live CMS Gateway Telemetry
              </h3>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={clearActivityLogs}
                className="text-xs text-slate-400 hover:text-white px-2 py-1 rounded bg-slate-800/80"
              >
                Clear
              </button>
              <button
                onClick={() => setIsInspectorOpen(false)}
                className="text-slate-400 hover:text-white p-1 rounded"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {activityLogs.length === 0 ? (
              <div className="text-center py-16 text-slate-500 text-xs">
                No requests captured yet. Perform actions in the CMS suite to stream real-time API logs.
              </div>
            ) : (
              activityLogs.map((log) => {
                const isSuccess = log.status >= 200 && log.status < 300;
                return (
                  <div
                    key={log.id}
                    className="p-3 rounded-xl bg-slate-950/80 border border-slate-800 text-xs font-mono space-y-1.5"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                            log.method === 'GET'
                              ? 'bg-blue-900/60 text-blue-300'
                              : log.method === 'POST'
                              ? 'bg-emerald-900/60 text-emerald-300'
                              : log.method === 'PATCH'
                              ? 'bg-amber-900/60 text-amber-300'
                              : 'bg-rose-900/60 text-rose-300'
                          }`}
                        >
                          {log.method}
                        </span>
                        <span className="text-slate-300 truncate max-w-[220px]" title={log.path}>
                          {log.path}
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5 text-[11px]">
                        <span
                          className={`font-bold ${isSuccess ? 'text-emerald-400' : 'text-rose-400'}`}
                        >
                          {log.status}
                        </span>
                        <span className="text-slate-500">{log.latency}ms</span>
                      </div>
                    </div>

                    {log.responseData && (
                      <pre className="text-[10px] p-2 bg-black/40 rounded text-slate-400 max-h-36 overflow-y-auto">
                        {typeof log.responseData === 'object'
                          ? JSON.stringify(log.responseData, null, 2)
                          : log.responseData}
                      </pre>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </aside>
      )}
    </div>
  );
};

export default CmsPage;
