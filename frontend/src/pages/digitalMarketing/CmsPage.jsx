import React, { useState, useEffect, useCallback } from 'react';
import { useSelector } from 'react-redux';
import { toast } from 'react-toastify';
import {
  Globe,
  FileText,
  Search,
  BarChart3,
  ShieldCheck,
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
  Check,
  Sparkles,
  MousePointerClick,
  Users,
  Eye,
  Sliders,
  X,
  TrendingUp,
  DollarSign,
  Play,
  Pause,
  Tag,
  Target,
  History,
  Activity,
  Award,
  Zap,
  Calendar,
  Building2,
  Share2,
} from 'lucide-react';
import cmsService from '../../services/cmsService';

const CmsPage = () => {
  const authUser = useSelector((state) => state.auth?.user);

  // Active top-level tab: 'pages' | 'analytics' | 'search_console' | 'bing' | 'google_ads'
  const [activeTab, setActiveTab] = useState('pages');
  const [loadingOverview, setLoadingOverview] = useState(false);
  const [overviewData, setOverviewData] = useState(null);

  // ─────────────────────────────────────────────────────────────────────────────
  // Tab 1: CMS Website Pages & Sitemap State
  // ─────────────────────────────────────────────────────────────────────────────
  const [pages, setPages] = useState([]);
  const [loadingPages, setLoadingPages] = useState(false);
  const [pageFilter, setPageFilter] = useState('ALL');
  const [pageSearch, setPageSearch] = useState('');
  const [isCreatePageOpen, setIsCreatePageOpen] = useState(false);
  const [newPage, setNewPage] = useState({
    title: '',
    slug: '',
    page_id: '',
    page_path: '',
    page_type: 'PAGE',
    status: 'PUBLISHED',
    summary: '',
    content: '',
    meta_title: '',
    meta_description: '',
    canonical_url: '',
    ga_page_id: '',
    include_in_sitemap: true,
    sitemap_priority: '0.8',
    sitemap_changefreq: 'weekly',
  });
  const [creatingPage, setCreatingPage] = useState(false);
  const [editingPage, setEditingPage] = useState(null);
  const [isSitemapModalOpen, setIsSitemapModalOpen] = useState(false);
  const [sitemapXmlData, setSitemapXmlData] = useState(null);
  const [loadingSitemapXml, setLoadingSitemapXml] = useState(false);

  // ─────────────────────────────────────────────────────────────────────────────
  // Tab 2: Google Analytics State (Essential Features Only)
  // ─────────────────────────────────────────────────────────────────────────────
  const [gaConfig, setGaConfig] = useState(null);
  const [gaDashboard, setGaDashboard] = useState(null);
  const [loadingGa, setLoadingGa] = useState(false);
  const [gaRange, setGaRange] = useState('30d');
  const [savingGaConfig, setSavingGaConfig] = useState(false);
  const [selectedPageForSnippet, setSelectedPageForSnippet] = useState('');
  const [isRecordStatOpen, setIsRecordStatOpen] = useState(false);
  const [newStat, setNewStat] = useState({
    page_id: 'PAGE-HOME-001',
    page_path: '/',
    page_title: 'Market Intel Platform Home',
    page_views: 45,
    unique_visitors: 36,
    sessions: 40,
    traffic_source: 'Organic Search',
    device_category: 'Desktop',
    country: 'United States',
  });
  const [recordingStat, setRecordingStat] = useState(false);
  const [realtimeData, setRealtimeData] = useState(null);
  const [realtimeAutoRefresh, setRealtimeAutoRefresh] = useState(true);
  const [sendingTestHit, setSendingTestHit] = useState(false);
  const [googleStatus, setGoogleStatus] = useState(null);

  // ─────────────────────────────────────────────────────────────────────────────
  // Tab 3: Google Search Console State
  // ─────────────────────────────────────────────────────────────────────────────
  const [gscData, setGscData] = useState(null);
  const [loadingGsc, setLoadingGsc] = useState(false);
  const [isRegisterDomainOpen, setIsRegisterDomainOpen] = useState(false);
  const [newDomain, setNewDomain] = useState({
    domain: '',
    property_type: 'DOMAIN',
    verification_method: 'DNS_TXT',
  });
  const [registeringDomain, setRegisteringDomain] = useState(false);
  const [isSubmitSitemapOpen, setIsSubmitSitemapOpen] = useState(false);
  const [sitemapUrlInput, setSitemapUrlInput] = useState('https://marketintel.hikasimat.com/sitemap.xml');
  const [submittingSitemap, setSubmittingSitemap] = useState(false);
  const [inspectUrlInput, setInspectUrlInput] = useState('');
  const [inspectResult, setInspectResult] = useState(null);
  const [inspectingUrl, setInspectingUrl] = useState(false);
  const [manualIndexUrl, setManualIndexUrl] = useState('');
  const [submittingIndexing, setSubmittingIndexing] = useState(false);

  // ─────────────────────────────────────────────────────────────────────────────
  // Tab 4: Bing Webmaster Tools State
  // ─────────────────────────────────────────────────────────────────────────────
  const [bingData, setBingData] = useState(null);
  const [loadingBing, setLoadingBing] = useState(false);
  const [bingApiKeyInput, setBingApiKeyInput] = useState('');
  const [savingBingConfig, setSavingBingConfig] = useState(false);
  const [bingUrlsInput, setBingUrlsInput] = useState('');
  const [bingProtocol, setBingProtocol] = useState('INDEXNOW');
  const [submittingBingUrls, setSubmittingBingUrls] = useState(false);
  const [bingSitemapInput, setBingSitemapInput] = useState('https://marketintel.hikasimat.com/sitemap.xml');
  const [submittingBingSitemap, setSubmittingBingSitemap] = useState(false);

  // ─────────────────────────────────────────────────────────────────────────────
  // Tab 5: Google Ads State
  // ─────────────────────────────────────────────────────────────────────────────
  const [adsData, setAdsData] = useState(null);
  const [loadingAds, setLoadingAds] = useState(false);
  const [adsSubTab, setAdsSubTab] = useState('campaigns'); // 'campaigns' | 'adgroups' | 'keywords' | 'audit'
  const [isCreateCampaignOpen, setIsCreateCampaignOpen] = useState(false);
  const [newCampaign, setNewCampaign] = useState({
    name: '',
    channel_type: 'SEARCH',
    status: 'ENABLED',
    bidding_strategy: 'MAXIMIZE_CONVERSIONS',
    daily_budget: '75.00',
    target_cpa: '',
    target_roas: '',
    locations: 'United States, United Kingdom, Singapore',
    languages: 'English',
  });
  const [creatingCampaign, setCreatingCampaign] = useState(false);
  const [budgetModalOpen, setBudgetModalOpen] = useState(false);
  const [campaignForBudget, setCampaignForBudget] = useState(null);
  const [newBudgetVal, setNewBudgetVal] = useState('');
  const [updatingBudget, setUpdatingBudget] = useState(false);
  const [isCreateAdGroupOpen, setIsCreateAdGroupOpen] = useState(false);
  const [newAdGroup, setNewAdGroup] = useState({
    campaign_id: '',
    name: '',
    cpc_bid: '2.50',
    headline_1: '',
    headline_2: '',
    description: '',
    final_url: 'https://marketintel.hikasimat.com',
  });
  const [creatingAdGroup, setCreatingAdGroup] = useState(false);
  const [isCreateKeywordOpen, setIsCreateKeywordOpen] = useState(false);
  const [newKeyword, setNewKeyword] = useState({
    ad_group_id: '',
    keyword_text: '',
    match_type: 'PHRASE',
    cpc_bid: '2.20',
  });
  const [creatingKeyword, setCreatingKeyword] = useState(false);
  const [isAdsAccountConfigOpen, setIsAdsAccountConfigOpen] = useState(false);
  const [adsAccountConfig, setAdsAccountConfig] = useState({
    customer_id: '',
    account_name: '',
    currency_code: 'USD',
    time_zone: 'America/New_York',
    conversion_tracking_id: 'AW-948271635',
  });
  const [savingAdsAccount, setSavingAdsAccount] = useState(false);

  // ─────────────────────────────────────────────────────────────────────────────
  // Initial Loader & Data Fetching
  // ─────────────────────────────────────────────────────────────────────────────
  const fetchOverview = useCallback(async () => {
    setLoadingOverview(true);
    const res = await cmsService.getOverview();
    if (res.ok) {
      setOverviewData(res.data);
    }
    setLoadingOverview(false);
  }, []);

  const fetchPages = useCallback(async () => {
    setLoadingPages(true);
    try {
      const res = await cmsService.getPages({
        status: pageFilter !== 'ALL' ? pageFilter : undefined,
        search: pageSearch || undefined,
      });
      if (res.ok) {
        setPages(res.data.pages || []);
      } else {
        toast.error(res.error || 'Failed to load CMS pages');
      }
    } catch (err) {
      console.error('Failed to load CMS pages:', err);
      toast.error('Failed to load CMS pages');
    } finally {
      setLoadingPages(false);
    }
  }, [pageFilter, pageSearch]);

  const fetchAnalytics = useCallback(async () => {
    setLoadingGa(true);
    const [cfgRes, dashRes] = await Promise.all([
      cmsService.getAnalyticsConfig(selectedPageForSnippet),
      cmsService.getAnalyticsDashboard(gaRange),
    ]);
    if (cfgRes.ok) setGaConfig(cfgRes.data);
    if (dashRes.ok) setGaDashboard(dashRes.data);
    setLoadingGa(false);
  }, [gaRange, selectedPageForSnippet]);

  const fetchRealtime = useCallback(async () => {
    const res = await cmsService.getRealtimeAnalytics();
    if (res.ok) setRealtimeData(res.data);
  }, []);

  const fetchGoogleStatus = useCallback(async () => {
    const res = await cmsService.getGoogleConnectionStatus();
    if (res.ok) setGoogleStatus(res.data);
  }, []);

  const fetchSearchConsole = useCallback(async () => {
    setLoadingGsc(true);
    const res = await cmsService.getSearchConsoleDashboard();
    if (res.ok) {
      setGscData(res.data);
    }
    setLoadingGsc(false);
  }, []);

  const fetchBing = useCallback(async () => {
    setLoadingBing(true);
    const res = await cmsService.getBingDashboard();
    if (res.ok) {
      setBingData(res.data);
      if (res.data?.config) {
        setBingApiKeyInput(res.data.config.masked_api_key || '');
      }
    }
    setLoadingBing(false);
  }, []);

  const fetchGoogleAds = useCallback(async () => {
    setLoadingAds(true);
    const res = await cmsService.getGoogleAdsDashboard();
    if (res.ok) {
      setAdsData(res.data);
      if (res.data?.config) {
        setAdsAccountConfig({
          customer_id: res.data.config.customer_id || '',
          account_name: res.data.config.account_name || '',
          currency_code: res.data.config.currency_code || 'USD',
          time_zone: res.data.config.time_zone || 'America/New_York',
          conversion_tracking_id: res.data.config.conversion_tracking_id || 'AW-948271635',
        });
      }
    }
    setLoadingAds(false);
  }, []);

  useEffect(() => {
    fetchOverview();
  }, [fetchOverview]);

  useEffect(() => {
    if (activeTab === 'pages') fetchPages();
    else if (activeTab === 'analytics') {
      fetchAnalytics();
      fetchRealtime();
      fetchGoogleStatus();
    }
    else if (activeTab === 'search_console') fetchSearchConsole();
    else if (activeTab === 'bing') fetchBing();
    else if (activeTab === 'google_ads') fetchGoogleAds();
  }, [activeTab, fetchPages, fetchAnalytics, fetchRealtime, fetchGoogleStatus, fetchSearchConsole, fetchBing, fetchGoogleAds]);

  // Polling for real-time live hits every 5 seconds when in analytics tab
  useEffect(() => {
    if (activeTab === 'analytics' && realtimeAutoRefresh) {
      const interval = setInterval(() => {
        fetchRealtime();
        fetchOverview();
      }, 5000);
      return () => clearInterval(interval);
    }
  }, [activeTab, realtimeAutoRefresh, fetchRealtime, fetchOverview]);

  const handleSendTestHit = async () => {
    setSendingTestHit(true);
    const hitPayload = {
      page_path: window.location.pathname || '/',
      page_id: gaConfig?.config?.page_id || 'G-MKTINTEL01',
      page_title: 'Market Intel Platform CMS Live',
      traffic_source: 'Direct Live Ping',
      device_category: 'Desktop',
      country: 'United States',
    };
    const res = await cmsService.sendAnalyticsHit(hitPayload);
    if (res.ok) {
      toast.success('Live Real-Time hit successfully recorded in Market Intel database!');
      fetchRealtime();
      fetchOverview();
      fetchAnalytics();
    } else {
      toast.error(res.error || 'Failed to record real-time hit.');
    }
    setSendingTestHit(false);
  };

  const handleConnectGoogle = async () => {
    const res = await cmsService.getGoogleConnectUrl();
    if (res.ok && res.data?.url) {
      window.location.href = res.data.url;
    } else {
      toast.error(res.error || 'Google OAuth is not configured on the backend.');
    }
  };

  const copyToClipboard = (text, label = 'Copied to clipboard') => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    toast.success(label);
  };

  // ─────────────────────────────────────────────────────────────────────────────
  // Handlers: Pages & Content
  // ─────────────────────────────────────────────────────────────────────────────
  const handleCreateOrUpdatePage = async (e) => {
    e.preventDefault();
    setCreatingPage(true);
    try {
      if (editingPage) {
        const res = await cmsService.updatePage(editingPage.id, newPage);
        if (res.ok) {
          toast.success(`Page "${res.data.page?.title || 'Page'}" updated!`);
          setIsCreatePageOpen(false);
          setEditingPage(null);
          fetchPages();
          fetchOverview();
        } else {
          toast.error(res.error || 'Failed to update page');
        }
      } else {
        const res = await cmsService.createPage(newPage);
        if (res.ok) {
          toast.success(`Page "${res.data.page?.title || 'Page'}" created in Market Intel CMS!`);
          setIsCreatePageOpen(false);
          fetchPages();
          fetchOverview();
        } else {
          toast.error(res.error || 'Failed to create page');
        }
      }
    } finally {
      setCreatingPage(false);
    }
  };

  const handleEditPageClick = (page) => {
    setEditingPage(page);
    setNewPage({
      title: page.title || '',
      slug: page.slug || '',
      page_id: page.page_id || '',
      page_path: page.page_path || '',
      page_type: page.page_type || 'PAGE',
      status: page.status || 'PUBLISHED',
      summary: page.summary || '',
      content: page.content || '',
      meta_title: page.meta_title || '',
      meta_description: page.meta_description || '',
      canonical_url: page.canonical_url || '',
      ga_page_id: page.ga_page_id || '',
      include_in_sitemap: page.include_in_sitemap ?? true,
      sitemap_priority: String(page.sitemap_priority || '0.8'),
      sitemap_changefreq: page.sitemap_changefreq || 'weekly',
    });
    setIsCreatePageOpen(true);
  };

  const handleDeletePage = async (id, title) => {
    if (!window.confirm(`Delete page "${title}" from Market Intel database?`)) return;
    const res = await cmsService.deletePage(id);
    if (res.ok) {
      toast.success(`Page "${title}" deleted`);
      fetchPages();
      fetchOverview();
    } else {
      toast.error(res.error || 'Failed to delete page');
    }
  };

  const handleTogglePageStatus = async (page) => {
    const nextStatus = page.status === 'PUBLISHED' ? 'DRAFT' : 'PUBLISHED';
    const res = await cmsService.updatePage(page.id, { status: nextStatus });
    if (res.ok) {
      toast.success(`Page is now ${nextStatus}`);
      fetchPages();
      fetchOverview();
    } else {
      toast.error(res.error || 'Could not update status');
    }
  };

  const handleOpenSitemapPreview = async () => {
    setIsSitemapModalOpen(true);
    setLoadingSitemapXml(true);
    const res = await cmsService.getSitemapXml();
    if (res.ok) {
      setSitemapXmlData(res.data);
    } else {
      toast.error('Could not load sitemap XML');
    }
    setLoadingSitemapXml(false);
  };

  // ─────────────────────────────────────────────────────────────────────────────
  // Handlers: Google Analytics
  // ─────────────────────────────────────────────────────────────────────────────
  const handleSaveGaConfig = async (e) => {
    e.preventDefault();
    if (!gaConfig?.config) return;
    setSavingGaConfig(true);
    const res = await cmsService.updateAnalyticsConfig({
      page_id: gaConfig.config.page_id,
      property_id: gaConfig.config.property_id,
      site_name: gaConfig.config.site_name,
      site_url: gaConfig.config.site_url,
      is_active: gaConfig.config.is_active,
      track_pageviews: gaConfig.config.track_pageviews,
      track_outbound_clicks: gaConfig.config.track_outbound_clicks,
      track_scroll_depth: gaConfig.config.track_scroll_depth,
    });
    setSavingGaConfig(false);
    if (res.ok) {
      toast.success('Google Analytics configuration and tracking code saved!');
      fetchAnalytics();
      fetchOverview();
    } else {
      toast.error(res.error || 'Failed to update Google Analytics config');
    }
  };

  const handleRecordAnalyticsStat = async (e) => {
    e.preventDefault();
    setRecordingStat(true);
    const res = await cmsService.recordAnalyticsStat(newStat);
    setRecordingStat(false);
    if (res.ok) {
      toast.success(`Recorded statistics for ${newStat.page_title}!`);
      setIsRecordStatOpen(false);
      fetchAnalytics();
      fetchOverview();
    } else {
      toast.error(res.error || 'Failed to record stat');
    }
  };

  // ─────────────────────────────────────────────────────────────────────────────
  // Handlers: Google Search Console
  // ─────────────────────────────────────────────────────────────────────────────
  const handleRegisterDomain = async (e) => {
    e.preventDefault();
    setRegisteringDomain(true);
    const res = await cmsService.registerSearchConsoleDomain(newDomain);
    setRegisteringDomain(false);
    if (res.ok) {
      toast.success(res.data?.detail || 'Domain registered in Google Search Console!');
      setIsRegisterDomainOpen(false);
      setNewDomain({ domain: '', property_type: 'DOMAIN', verification_method: 'DNS_TXT' });
      fetchSearchConsole();
      fetchOverview();
    } else {
      toast.error(res.error || 'Failed to register domain');
    }
  };

  const handleVerifyDomain = async (domainId, method) => {
    const res = await cmsService.verifySearchConsoleDomain(domainId, { verification_method: method });
    if (res.ok) {
      toast.success('Domain verified successfully in Search Console!');
      fetchSearchConsole();
      fetchOverview();
    } else {
      toast.error(res.error || 'Verification failed');
    }
  };

  const handleDeleteDomain = async (domainId) => {
    if (!window.confirm('Remove this domain property from Google Search Console?')) return;
    const res = await cmsService.deleteSearchConsoleDomain(domainId);
    if (res.ok) {
      toast.success('Domain removed');
      fetchSearchConsole();
      fetchOverview();
    } else {
      toast.error(res.error || 'Failed to remove domain');
    }
  };

  const handleSubmitSitemap = async (e) => {
    e.preventDefault();
    setSubmittingSitemap(true);
    const res = await cmsService.submitSearchConsoleSitemap({ sitemap_url: sitemapUrlInput });
    setSubmittingSitemap(false);
    if (res.ok) {
      toast.success(res.data?.detail || 'Sitemap submitted to Google Search Console!');
      setIsSubmitSitemapOpen(false);
      fetchSearchConsole();
      fetchOverview();
    } else {
      toast.error(res.error || 'Failed to submit sitemap');
    }
  };

  const handleInspectUrl = async (e) => {
    e.preventDefault();
    if (!inspectUrlInput.trim()) return;
    setInspectingUrl(true);
    setInspectResult(null);
    const res = await cmsService.inspectSearchConsoleUrl(inspectUrlInput.trim());
    setInspectingUrl(false);
    if (res.ok) {
      setInspectResult(res.data?.result || null);
    } else {
      toast.error(res.error || 'URL Inspection failed');
    }
  };

  const handleSubmitIndexing = async (bulkAll = false) => {
    setSubmittingIndexing(true);
    const payload = bulkAll ? { bulk_all_cms_pages: true } : { page_url: manualIndexUrl };
    const res = await cmsService.submitSearchConsoleIndexing(payload);
    setSubmittingIndexing(false);
    if (res.ok) {
      toast.success(res.data?.detail || 'Indexing request submitted to Google Search Console!');
      if (!bulkAll) setManualIndexUrl('');
      fetchSearchConsole();
      fetchOverview();
    } else {
      toast.error(res.error || 'Failed to submit indexing request');
    }
  };

  // ─────────────────────────────────────────────────────────────────────────────
  // Handlers: Bing Webmaster Tools
  // ─────────────────────────────────────────────────────────────────────────────
  const handleSaveBingConfig = async (e) => {
    e.preventDefault();
    setSavingBingConfig(true);
    const payload = {
      site_url: bingData?.config?.site_url || 'https://marketintel.hikasimat.com',
      indexnow_key: bingData?.config?.indexnow_key,
      verification_meta_code: bingData?.config?.verification_meta_code,
      cname_record: bingData?.config?.cname_record,
      auto_indexnow_on_publish: bingData?.config?.auto_indexnow_on_publish ?? true,
    };
    if (bingApiKeyInput && !bingApiKeyInput.includes('••••')) {
      payload.api_key = bingApiKeyInput;
    }
    const res = await cmsService.updateBingConfig(payload);
    setSavingBingConfig(false);
    if (res.ok) {
      toast.success('Bing Webmaster Tools configuration saved!');
      fetchBing();
      fetchOverview();
    } else {
      toast.error(res.error || 'Failed to save Bing configuration');
    }
  };

  const handleVerifyBingSite = async () => {
    setSavingBingConfig(true);
    const res = await cmsService.updateBingConfig({ verify_site: true });
    setSavingBingConfig(false);
    if (res.ok) {
      toast.success('Bing site verification confirmed!');
      fetchBing();
      fetchOverview();
    } else {
      toast.error(res.error || 'Could not verify site on Bing');
    }
  };

  const handleRegenerateIndexNowKey = async () => {
    if (!window.confirm('Regenerate your IndexNow Key? You will need to host the new key on your site.')) return;
    const res = await cmsService.updateBingConfig({ regenerate_indexnow_key: true });
    if (res.ok) {
      toast.success('New IndexNow key generated!');
      fetchBing();
    } else {
      toast.error(res.error || 'Could not regenerate key');
    }
  };

  const handleSubmitBingUrls = async (bulkAll = false) => {
    setSubmittingBingUrls(true);
    const payload = bulkAll
      ? { bulk_all_cms_pages: true, submission_protocol: bingProtocol }
      : { urls: bingUrlsInput, submission_protocol: bingProtocol };
    const res = await cmsService.submitBingUrls(payload);
    setSubmittingBingUrls(false);
    if (res.ok) {
      toast.success(res.data?.detail || 'Submitted to Bing & IndexNow!');
      if (!bulkAll) setBingUrlsInput('');
      fetchBing();
      fetchOverview();
    } else {
      toast.error(res.error || 'Failed to submit URLs to Bing');
    }
  };

  const handleSubmitBingSitemap = async (e) => {
    e.preventDefault();
    setSubmittingBingSitemap(true);
    const res = await cmsService.submitBingSitemap({ sitemap_url: bingSitemapInput });
    setSubmittingBingSitemap(false);
    if (res.ok) {
      toast.success(res.data?.detail || 'Sitemap submitted to Bing!');
      fetchBing();
      fetchOverview();
    } else {
      toast.error(res.error || 'Failed to submit sitemap to Bing');
    }
  };

  // ─────────────────────────────────────────────────────────────────────────────
  // Handlers: Google Ads
  // ─────────────────────────────────────────────────────────────────────────────
  const handleSaveAdsAccountConfig = async (e) => {
    e.preventDefault();
    setSavingAdsAccount(true);
    const res = await cmsService.updateGoogleAdsConfig(adsAccountConfig);
    setSavingAdsAccount(false);
    if (res.ok) {
      toast.success(res.data?.detail || 'Google Ads account configuration updated!');
      setIsAdsAccountConfigOpen(false);
      fetchGoogleAds();
      fetchOverview();
    } else {
      toast.error(res.error || 'Failed to update Google Ads config');
    }
  };

  const handleToggleCampaignStatus = async (campaign) => {
    const nextStatus = campaign.status === 'ENABLED' ? 'PAUSED' : 'ENABLED';
    const res = await cmsService.updateGoogleAdsCampaign(campaign.id, { status: nextStatus });
    if (res.ok) {
      toast.success(`Campaign "${campaign.name}" is now ${nextStatus}!`);
      fetchGoogleAds();
      fetchOverview();
    } else {
      toast.error(res.error || 'Failed to update campaign status');
    }
  };

  const handleOpenBudgetModal = (campaign) => {
    setCampaignForBudget(campaign);
    setNewBudgetVal(String(campaign.daily_budget || '50.00'));
    setBudgetModalOpen(true);
  };

  const handleSaveCampaignBudget = async (e) => {
    e.preventDefault();
    if (!campaignForBudget) return;
    setUpdatingBudget(true);
    const res = await cmsService.updateGoogleAdsCampaign(campaignForBudget.id, {
      daily_budget: newBudgetVal,
    });
    setUpdatingBudget(false);
    if (res.ok) {
      toast.success(`Daily budget updated to $${newBudgetVal}/day!`);
      setBudgetModalOpen(false);
      fetchGoogleAds();
      fetchOverview();
    } else {
      toast.error(res.error || 'Failed to update budget');
    }
  };

  const handleCreateCampaign = async (e) => {
    e.preventDefault();
    setCreatingCampaign(true);
    const res = await cmsService.createGoogleAdsCampaign(newCampaign);
    setCreatingCampaign(false);
    if (res.ok) {
      toast.success(`Google Ads Campaign "${newCampaign.name}" created!`);
      setIsCreateCampaignOpen(false);
      setNewCampaign({
        name: '',
        channel_type: 'SEARCH',
        status: 'ENABLED',
        bidding_strategy: 'MAXIMIZE_CONVERSIONS',
        daily_budget: '75.00',
        target_cpa: '',
        target_roas: '',
        locations: 'United States, United Kingdom, Singapore',
        languages: 'English',
      });
      fetchGoogleAds();
      fetchOverview();
    } else {
      toast.error(res.error || 'Failed to create campaign');
    }
  };

  const handleDeleteCampaign = async (campaign) => {
    if (!window.confirm(`Remove campaign "${campaign.name}"?`)) return;
    const res = await cmsService.deleteGoogleAdsCampaign(campaign.id);
    if (res.ok) {
      toast.success(`Campaign "${campaign.name}" removed`);
      fetchGoogleAds();
      fetchOverview();
    } else {
      toast.error(res.error || 'Failed to remove campaign');
    }
  };

  const handleCreateAdGroup = async (e) => {
    e.preventDefault();
    setCreatingAdGroup(true);
    const res = await cmsService.createGoogleAdsAdGroup(newAdGroup);
    setCreatingAdGroup(false);
    if (res.ok) {
      toast.success(`Ad Group "${newAdGroup.name}" created!`);
      setIsCreateAdGroupOpen(false);
      setNewAdGroup({
        campaign_id: '',
        name: '',
        cpc_bid: '2.50',
        headline_1: '',
        headline_2: '',
        description: '',
        final_url: 'https://marketintel.hikasimat.com',
      });
      fetchGoogleAds();
    } else {
      toast.error(res.error || 'Failed to create Ad Group');
    }
  };

  const handleToggleAdGroupStatus = async (ag) => {
    const nextStatus = ag.status === 'ENABLED' ? 'PAUSED' : 'ENABLED';
    const res = await cmsService.updateGoogleAdsAdGroup(ag.id, { status: nextStatus });
    if (res.ok) {
      toast.success(`Ad Group is now ${nextStatus}`);
      fetchGoogleAds();
    } else {
      toast.error(res.error || 'Failed to update Ad Group');
    }
  };

  const handleDeleteAdGroup = async (ag) => {
    if (!window.confirm(`Delete Ad Group "${ag.name}"?`)) return;
    const res = await cmsService.deleteGoogleAdsAdGroup(ag.id);
    if (res.ok) {
      toast.success(`Ad Group "${ag.name}" deleted`);
      fetchGoogleAds();
    } else {
      toast.error(res.error || 'Failed to delete Ad Group');
    }
  };

  const handleCreateKeyword = async (e) => {
    e.preventDefault();
    setCreatingKeyword(true);
    const res = await cmsService.createGoogleAdsKeyword(newKeyword);
    setCreatingKeyword(false);
    if (res.ok) {
      toast.success(`Keyword "${newKeyword.keyword_text}" added!`);
      setIsCreateKeywordOpen(false);
      setNewKeyword({ ad_group_id: '', keyword_text: '', match_type: 'PHRASE', cpc_bid: '2.20' });
      fetchGoogleAds();
    } else {
      toast.error(res.error || 'Failed to add keyword');
    }
  };

  const handleToggleKeywordStatus = async (kw) => {
    const nextStatus = kw.status === 'ENABLED' ? 'PAUSED' : 'ENABLED';
    const res = await cmsService.updateGoogleAdsKeyword(kw.id, { status: nextStatus });
    if (res.ok) {
      toast.success(`Keyword is now ${nextStatus}`);
      fetchGoogleAds();
    } else {
      toast.error(res.error || 'Failed to update keyword');
    }
  };

  const handleDeleteKeyword = async (kw) => {
    if (!window.confirm(`Delete keyword "${kw.keyword_text}"?`)) return;
    const res = await cmsService.deleteGoogleAdsKeyword(kw.id);
    if (res.ok) {
      toast.success(`Keyword deleted`);
      fetchGoogleAds();
    } else {
      toast.error(res.error || 'Failed to delete keyword');
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-16">
      {/* ── Top Header Strip ──────────────────────────────────────────────── */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div className="flex items-center gap-4">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-blue-600 via-indigo-600 to-sky-500 text-white flex items-center justify-center shadow-md shadow-indigo-500/20">
            <Globe className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-2xl font-black text-slate-900 tracking-tight">Market Intel CMS</h1>
              <span className="px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                Native Database Engine
              </span>
            </div>
            <p className="text-xs text-slate-500 mt-0.5">
              Independent CMS with Google Analytics, Search Console, Bing Webmaster Tools & Google Ads.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              fetchOverview();
              if (activeTab === 'pages') fetchPages();
              else if (activeTab === 'analytics') fetchAnalytics();
              else if (activeTab === 'search_console') fetchSearchConsole();
              else if (activeTab === 'bing') fetchBing();
              else if (activeTab === 'google_ads') fetchGoogleAds();
            }}
            disabled={loadingOverview}
            className="inline-flex items-center gap-2 px-3.5 py-2 border border-slate-200 rounded-xl text-xs font-bold text-slate-700 bg-white hover:bg-slate-50 transition shadow-xs disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingOverview ? 'animate-spin' : ''}`} />
            Refresh
          </button>

          <a
            href={
              typeof window !== 'undefined' && window.location.hostname.includes('marketinteldbapp.hikasimat.com')
                ? 'https://marketintel.hikasimat.com/api/digital-marketing/cms/sitemap.xml'
                : '/api/digital-marketing/cms/sitemap.xml'
            }
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 px-3.5 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-xl text-xs font-bold transition shadow-xs"
          >
            <Code className="w-3.5 h-3.5 text-sky-400" />
            Live sitemap.xml
            <ExternalLink className="w-3 h-3 text-slate-400" />
          </a>
        </div>
      </div>

      {/* ── Integration Summary Stat Cards ─────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {/* Google Analytics Card */}
        <div
          onClick={() => setActiveTab('analytics')}
          className={`cursor-pointer bg-white rounded-xl border p-4.5 transition-all shadow-xs ${
            activeTab === 'analytics'
              ? 'border-indigo-500 ring-2 ring-indigo-500/10'
              : 'border-slate-200 hover:border-slate-300'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Google Analytics</span>
            <div className="flex items-center gap-1.5">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
              </span>
              <span className="text-[10px] font-bold text-emerald-600">
                {overviewData?.integrations?.google_analytics?.active_users_now ?? 0} Live
              </span>
            </div>
          </div>
          <div className="mt-2 text-2xl font-black text-slate-900">
            {overviewData?.integrations?.google_analytics?.total_page_views?.toLocaleString() ?? 0}
          </div>
          <div className="mt-1 flex items-center justify-between text-xs text-slate-500">
            <span>Page ID: {overviewData?.integrations?.google_analytics?.page_id || 'G-MKTINTEL01'}</span>
            <span className="text-emerald-600 font-bold">Views</span>
          </div>
        </div>

        {/* Google Search Console Card */}
        <div
          onClick={() => setActiveTab('search_console')}
          className={`cursor-pointer bg-white rounded-xl border p-4.5 transition-all shadow-xs ${
            activeTab === 'search_console'
              ? 'border-blue-500 ring-2 ring-blue-500/10'
              : 'border-slate-200 hover:border-slate-300'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Search Console</span>
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" title="Search Console" />
          </div>
          <div className="mt-2 text-2xl font-black text-slate-900">
            {overviewData?.integrations?.google_search_console?.total_clicks?.toLocaleString() ?? 0}
          </div>
          <div className="mt-1 flex items-center justify-between text-xs text-slate-500">
            <span>{overviewData?.integrations?.google_search_console?.indexed_pages_count ?? 0} Indexed Pages</span>
            <span className="text-blue-600 font-bold">Clicks</span>
          </div>
        </div>

        {/* Bing Webmaster Tools Card */}
        <div
          onClick={() => setActiveTab('bing')}
          className={`cursor-pointer bg-white rounded-xl border p-4.5 transition-all shadow-xs ${
            activeTab === 'bing'
              ? 'border-teal-500 ring-2 ring-teal-500/10'
              : 'border-slate-200 hover:border-slate-300'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Bing Webmaster</span>
            <span className="w-2.5 h-2.5 rounded-full bg-teal-500" title="IndexNow Active" />
          </div>
          <div className="mt-2 text-2xl font-black text-slate-900">
            {overviewData?.integrations?.bing_webmaster?.total_clicks?.toLocaleString() ?? 0}
          </div>
          <div className="mt-1 flex items-center justify-between text-xs text-slate-500">
            <span>{overviewData?.integrations?.bing_webmaster?.submissions_count ?? 0} Submissions</span>
            <span className="text-teal-600 font-bold">IndexNow</span>
          </div>
        </div>

        {/* Google Ads Card */}
        <div
          onClick={() => setActiveTab('google_ads')}
          className={`cursor-pointer bg-white rounded-xl border p-4.5 transition-all shadow-xs ${
            activeTab === 'google_ads'
              ? 'border-amber-500 ring-2 ring-amber-500/10'
              : 'border-slate-200 hover:border-slate-300'
          }`}
        >
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Google Ads</span>
            <span className={`w-2.5 h-2.5 rounded-full ${overviewData?.integrations?.google_ads?.is_connected ? 'bg-emerald-500' : 'bg-amber-500'}`} />
          </div>
          <div className="mt-2 text-2xl font-black text-slate-900">
            ${Number(overviewData?.integrations?.google_ads?.total_spend || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="mt-1 flex items-center justify-between text-xs text-slate-500">
            <span>{overviewData?.integrations?.google_ads?.active_campaigns ?? 0} Active Campaigns</span>
            <span className="text-amber-600 font-bold">Spend</span>
          </div>
        </div>
      </div>

      {/* ── Main Navigation Tabs ───────────────────────────────────────────── */}
      <div className="flex border-b border-slate-200 space-x-1 overflow-x-auto pb-0.5">
        <button
          onClick={() => setActiveTab('pages')}
          className={`px-4 py-2.5 text-xs font-bold rounded-t-xl transition flex items-center gap-2 border-b-2 -mb-px ${
            activeTab === 'pages'
              ? 'border-indigo-600 text-indigo-600 bg-indigo-50/50'
              : 'border-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-50'
          }`}
        >
          <FileText className="w-4 h-4" />
          Pages & Sitemaps
        </button>

        <button
          onClick={() => setActiveTab('analytics')}
          className={`px-4 py-2.5 text-xs font-bold rounded-t-xl transition flex items-center gap-2 border-b-2 -mb-px ${
            activeTab === 'analytics'
              ? 'border-indigo-600 text-indigo-600 bg-indigo-50/50'
              : 'border-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-50'
          }`}
        >
          <BarChart3 className="w-4 h-4" />
          Google Analytics
        </button>

        <button
          onClick={() => setActiveTab('search_console')}
          className={`px-4 py-2.5 text-xs font-bold rounded-t-xl transition flex items-center gap-2 border-b-2 -mb-px ${
            activeTab === 'search_console'
              ? 'border-indigo-600 text-indigo-600 bg-indigo-50/50'
              : 'border-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-50'
          }`}
        >
          <Search className="w-4 h-4" />
          Google Search Console
        </button>

        <button
          onClick={() => setActiveTab('bing')}
          className={`px-4 py-2.5 text-xs font-bold rounded-t-xl transition flex items-center gap-2 border-b-2 -mb-px ${
            activeTab === 'bing'
              ? 'border-indigo-600 text-indigo-600 bg-indigo-50/50'
              : 'border-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-50'
          }`}
        >
          <Globe className="w-4 h-4 text-teal-600" />
          Bing Webmaster Tools
        </button>

        <button
          onClick={() => setActiveTab('google_ads')}
          className={`px-4 py-2.5 text-xs font-bold rounded-t-xl transition flex items-center gap-2 border-b-2 -mb-px ${
            activeTab === 'google_ads'
              ? 'border-indigo-600 text-indigo-600 bg-indigo-50/50'
              : 'border-transparent text-slate-600 hover:text-slate-900 hover:bg-slate-50'
          }`}
        >
          <DollarSign className="w-4 h-4 text-amber-600" />
          Google Ads
        </button>
      </div>

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* TAB 1: Pages & Content                                              */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      {activeTab === 'pages' && (
        <div className="space-y-6">
          {/* Controls Bar */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-4 bg-white p-4 rounded-xl border border-slate-200">
            <div className="flex items-center gap-3 w-full sm:w-auto">
              <div className="relative flex-1 sm:w-64">
                <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
                <input
                  type="text"
                  placeholder="Search pages by title or slug..."
                  value={pageSearch}
                  onChange={(e) => setPageSearch(e.target.value)}
                  className="w-full pl-9 pr-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <select
                value={pageFilter}
                onChange={(e) => setPageFilter(e.target.value)}
                className="text-xs bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-medium text-slate-700"
              >
                <option value="ALL">All Statuses</option>
                <option value="PUBLISHED">Published</option>
                <option value="DRAFT">Draft</option>
              </select>
            </div>

            <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
              <button
                onClick={handleOpenSitemapPreview}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-bold text-slate-700 bg-white hover:bg-slate-50 transition"
              >
                <Code className="w-3.5 h-3.5 text-indigo-600" />
                Inspect Sitemap XML
              </button>

              <button
                onClick={() => {
                  setEditingPage(null);
                  setNewPage({
                    title: '',
                    slug: '',
                    page_id: '',
                    page_path: '',
                    page_type: 'PAGE',
                    status: 'PUBLISHED',
                    summary: '',
                    content: '',
                    meta_title: '',
                    meta_description: '',
                    canonical_url: '',
                    ga_page_id: gaConfig?.config?.page_id || 'G-MKTINTEL01',
                    include_in_sitemap: true,
                    sitemap_priority: '0.8',
                    sitemap_changefreq: 'weekly',
                  });
                  setIsCreatePageOpen(true);
                }}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-bold transition shadow-xs"
              >
                <Plus className="w-4 h-4" />
                Add Page / Article
              </button>
            </div>
          </div>

          {/* Pages Table */}
          <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-bold uppercase tracking-wider text-[10px]">
                  <tr>
                    <th className="px-4 py-3">Page / Article Title</th>
                    <th className="px-4 py-3">Page ID</th>
                    <th className="px-4 py-3">Path & Canonical URL</th>
                    <th className="px-4 py-3">GA Measurement ID</th>
                    <th className="px-4 py-3">Sitemap</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {loadingPages ? (
                    <tr>
                      <td colSpan="7" className="px-4 py-8 text-center text-slate-400">
                        Loading CMS pages from Market Intel database...
                      </td>
                    </tr>
                  ) : pages.length === 0 ? (
                    <tr>
                      <td colSpan="7" className="px-4 py-8 text-center text-slate-500">
                        No pages found. Click &quot;Add Page / Article&quot; to create your first page.
                      </td>
                    </tr>
                  ) : (
                    pages.map((p) => (
                      <tr key={p.id} className="hover:bg-slate-50/80 transition">
                        <td className="px-4 py-3">
                          <div className="font-bold text-slate-900">{p.title}</div>
                          <div className="text-[11px] text-slate-400 font-mono mt-0.5">{p.slug}</div>
                        </td>
                        <td className="px-4 py-3">
                          <span className="font-mono text-[11px] px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 font-semibold border border-slate-200">
                            {p.page_id}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="font-mono text-[11px] text-indigo-600 font-medium">{p.page_path}</div>
                          <div className="text-[10px] text-slate-400 truncate max-w-xs">{p.canonical_url}</div>
                        </td>
                        <td className="px-4 py-3">
                          <span className="font-mono text-[11px] px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-800 border border-emerald-200 font-bold">
                            {p.ga_page_id || 'G-MKTINTEL01'}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          {p.include_in_sitemap ? (
                            <span className="inline-flex items-center gap-1 text-[11px] text-emerald-700 font-semibold">
                              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
                              pri {p.sitemap_priority}
                            </span>
                          ) : (
                            <span className="text-[11px] text-slate-400">Excluded</span>
                          )}
                        </td>
                        <td className="px-4 py-3">
                          <button
                            onClick={() => handleTogglePageStatus(p)}
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                              p.status === 'PUBLISHED'
                                ? 'bg-emerald-50 text-emerald-800 border-emerald-200 hover:bg-emerald-100'
                                : 'bg-slate-100 text-slate-600 border-slate-200 hover:bg-slate-200'
                            }`}
                          >
                            {p.status}
                          </button>
                        </td>
                        <td className="px-4 py-3 text-right space-x-1.5 whitespace-nowrap">
                          <button
                            onClick={() => handleEditPageClick(p)}
                            className="px-2.5 py-1 text-slate-700 hover:bg-slate-100 rounded-md font-semibold text-[11px] border border-slate-200 transition"
                          >
                            Edit
                          </button>
                          <button
                            onClick={() => handleDeletePage(p.id, p.title)}
                            className="p-1 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-md transition"
                            title="Delete page"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
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

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* TAB 2: Google Analytics (Essential Features & Real-Time)            */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      {activeTab === 'analytics' && (
        <div className="space-y-6">
          {/* Real-Time Live Traffic & Google Services Hub */}
          <div className="bg-gradient-to-r from-slate-900 to-indigo-950 rounded-2xl p-6 text-white shadow-lg space-y-5">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-white/10">
              <div className="flex items-center gap-3">
                <div className="relative flex h-3.5 w-3.5">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-emerald-500"></span>
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-black tracking-tight">Real-Time Web Traffic & Live Hit Stream</h3>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                      LIVE
                    </span>
                  </div>
                  <p className="text-xs text-slate-300 mt-0.5">
                    Live events recorded in real time in Market Intel database from tracking beacons and test hits.
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2 flex-wrap">
                <button
                  type="button"
                  onClick={() => setRealtimeAutoRefresh(!realtimeAutoRefresh)}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold transition border flex items-center gap-1.5 ${
                    realtimeAutoRefresh
                      ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-300'
                      : 'bg-white/5 border-white/10 text-slate-400 hover:text-white'
                  }`}
                >
                  <Activity className="w-3.5 h-3.5" />
                  {realtimeAutoRefresh ? 'Auto-Refresh: 5s' : 'Auto-Refresh: Paused'}
                </button>

                <button
                  type="button"
                  onClick={handleSendTestHit}
                  disabled={sendingTestHit}
                  className="px-3.5 py-1.5 rounded-lg text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white transition shadow-sm flex items-center gap-1.5 disabled:opacity-50"
                >
                  <Zap className="w-3.5 h-3.5 text-amber-300" />
                  {sendingTestHit ? 'Streaming...' : '⚡ Stream Live Test Hit'}
                </button>

                <button
                  type="button"
                  onClick={handleConnectGoogle}
                  className="px-3.5 py-1.5 rounded-lg text-xs font-bold bg-white text-slate-900 hover:bg-slate-100 transition shadow-sm flex items-center gap-1.5"
                >
                  <Globe className="w-3.5 h-3.5 text-blue-600" />
                  Connect Google Account
                </button>
              </div>
            </div>

            {/* Real-time KPI numbers */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <div className="bg-white/5 border border-white/10 rounded-xl p-4 backdrop-blur-xs">
                <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Active Users (Last 5m)</span>
                <div className="text-3xl font-black text-emerald-400 mt-1">
                  {realtimeData?.active_users_5m ?? 0}
                </div>
                <span className="text-[10px] text-slate-400 mt-0.5 block">Browsing right now</span>
              </div>

              <div className="bg-white/5 border border-white/10 rounded-xl p-4 backdrop-blur-xs">
                <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Active Users (Last 30m)</span>
                <div className="text-3xl font-black text-indigo-300 mt-1">
                  {realtimeData?.active_users_30m ?? 0}
                </div>
                <span className="text-[10px] text-slate-400 mt-0.5 block">Unique visitors</span>
              </div>

              <div className="bg-white/5 border border-white/10 rounded-xl p-4 backdrop-blur-xs">
                <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Views (Last 30m)</span>
                <div className="text-3xl font-black text-white mt-1">
                  {realtimeData?.page_views_30m ?? 0}
                </div>
                <span className="text-[10px] text-slate-400 mt-0.5 block">Recorded pageviews</span>
              </div>

              <div className="bg-white/5 border border-white/10 rounded-xl p-4 backdrop-blur-xs">
                <span className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">Google OAuth Status</span>
                <div className="text-sm font-bold text-white mt-2 flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${googleStatus?.google_analytics?.is_google_connected ? 'bg-emerald-400' : 'bg-amber-400'}`} />
                  {googleStatus?.google_analytics?.is_google_connected ? 'Connected' : 'OAuth Ready'}
                </div>
                <span className="text-[10px] text-slate-400 mt-1 block truncate">
                  {googleStatus?.google_analytics?.connected_email || 'Analytics, GSC & Ads'}
                </span>
              </div>
            </div>

            {/* Live Hit Stream Table */}
            {realtimeData?.recent_hits && realtimeData.recent_hits.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs text-slate-300">
                  <span className="font-bold uppercase tracking-wider text-[10px] text-slate-400">Live Incoming Hit Stream (Most Recent)</span>
                  <span className="text-[11px] text-slate-400">Updated {new Date(realtimeData.timestamp).toLocaleTimeString()}</span>
                </div>
                <div className="bg-black/30 border border-white/10 rounded-xl overflow-hidden max-h-48 overflow-y-auto">
                  <table className="w-full text-left text-xs">
                    <thead className="bg-white/5 text-slate-400 text-[10px] uppercase font-bold">
                      <tr>
                        <th className="px-3.5 py-2">Timestamp</th>
                        <th className="px-3.5 py-2">Page Path</th>
                        <th className="px-3.5 py-2">Event</th>
                        <th className="px-3.5 py-2">Device</th>
                        <th className="px-3.5 py-2">Source</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5 text-[11px]">
                      {realtimeData.recent_hits.map((hit) => (
                        <tr key={hit.id} className="hover:bg-white/5 transition">
                          <td className="px-3.5 py-1.5 font-mono text-slate-400">{new Date(hit.timestamp).toLocaleTimeString()}</td>
                          <td className="px-3.5 py-1.5 font-mono text-indigo-300 font-bold">{hit.page_path}</td>
                          <td className="px-3.5 py-1.5">
                            <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300">
                              {hit.event_name}
                            </span>
                          </td>
                          <td className="px-3.5 py-1.5 text-slate-300">{hit.device_category}</td>
                          <td className="px-3.5 py-1.5 text-slate-400">{hit.traffic_source}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
          {/* Section 1: Page ID Configuration & Snippet Generator */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Page ID Configuration Card */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                <div className="flex items-center gap-2">
                  <div className="p-2 rounded-lg bg-indigo-50 text-indigo-600">
                    <Sliders className="w-4 h-4" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-slate-900">Google Analytics Page ID Configuration</h3>
                    <p className="text-[11px] text-slate-500">Configure Page ID, Measurement ID, and tracking behavior.</p>
                  </div>
                </div>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">
                  {gaConfig?.config?.is_active ? 'Active' : 'Disabled'}
                </span>
              </div>

              <form onSubmit={handleSaveGaConfig} className="space-y-3.5 text-xs">
                <div>
                  <label className="block font-bold text-slate-700 mb-1">
                    Primary Page ID / GA4 Measurement ID
                  </label>
                  <input
                    type="text"
                    value={gaConfig?.config?.page_id || ''}
                    onChange={(e) =>
                      setGaConfig((prev) => ({
                        ...prev,
                        config: { ...prev.config, page_id: e.target.value },
                      }))
                    }
                    placeholder="G-MKTINTEL01"
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg font-mono focus:ring-1 focus:ring-indigo-500 focus:outline-none"
                    required
                  />
                  <p className="text-[10px] text-slate-400 mt-1">Default Google tag ID used for website data streams.</p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block font-bold text-slate-700 mb-1">GA Property ID</label>
                    <input
                      type="text"
                      value={gaConfig?.config?.property_id || ''}
                      onChange={(e) =>
                        setGaConfig((prev) => ({
                          ...prev,
                          config: { ...prev.config, property_id: e.target.value },
                        }))
                      }
                      placeholder="482910384"
                      className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg font-mono focus:ring-1 focus:ring-indigo-500 focus:outline-none"
                    />
                  </div>

                  <div>
                    <label className="block font-bold text-slate-700 mb-1">Site URL</label>
                    <input
                      type="url"
                      value={gaConfig?.config?.site_url || ''}
                      onChange={(e) =>
                        setGaConfig((prev) => ({
                          ...prev,
                          config: { ...prev.config, site_url: e.target.value },
                        }))
                      }
                      placeholder="https://marketintel.hikasimat.com"
                      className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:ring-1 focus:ring-indigo-500 focus:outline-none"
                    />
                  </div>
                </div>

                <div className="pt-2 border-t border-slate-100 space-y-2">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={gaConfig?.config?.track_pageviews ?? true}
                      onChange={(e) =>
                        setGaConfig((prev) => ({
                          ...prev,
                          config: { ...prev.config, track_pageviews: e.target.checked },
                        }))
                      }
                      className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    <span className="text-slate-700 font-medium">Automatic Pageview Tracking on Navigation</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={gaConfig?.config?.track_outbound_clicks ?? true}
                      onChange={(e) =>
                        setGaConfig((prev) => ({
                          ...prev,
                          config: { ...prev.config, track_outbound_clicks: e.target.checked },
                        }))
                      }
                      className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    <span className="text-slate-700 font-medium">Enhanced Link Attribution & Outbound Clicks</span>
                  </label>

                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={gaConfig?.config?.track_scroll_depth ?? true}
                      onChange={(e) =>
                        setGaConfig((prev) => ({
                          ...prev,
                          config: { ...prev.config, track_scroll_depth: e.target.checked },
                        }))
                      }
                      className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    <span className="text-slate-700 font-medium">Scroll Depth & Engagement Measurement</span>
                  </label>
                </div>

                <button
                  type="submit"
                  disabled={savingGaConfig}
                  className="w-full mt-3 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-bold text-xs transition shadow-xs disabled:opacity-50"
                >
                  {savingGaConfig ? 'Saving Configuration...' : 'Save Page ID Configuration'}
                </button>
              </form>
            </div>

            {/* Tracking Code Generation & Display Card */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs flex flex-col justify-between space-y-4">
              <div>
                <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <div className="p-2 rounded-lg bg-emerald-50 text-emerald-600">
                      <Code className="w-4 h-4" />
                    </div>
                    <div>
                      <h3 className="text-sm font-bold text-slate-900">Generated Tracking Code Snippet</h3>
                      <p className="text-[11px] text-slate-500">Live generated gtag.js ready to embed in website headers.</p>
                    </div>
                  </div>
                  <button
                    onClick={() => copyToClipboard(gaConfig?.tracking_code, 'Tracking code copied to clipboard!')}
                    className="inline-flex items-center gap-1.5 px-3 py-1 bg-slate-900 hover:bg-slate-800 text-white rounded-md text-xs font-bold transition"
                  >
                    <Copy className="w-3.5 h-3.5" />
                    Copy Code
                  </button>
                </div>

                <div className="mt-3">
                  <label className="block text-[11px] font-bold text-slate-600 mb-1">
                    Preview Snippet for Specific Page ID:
                  </label>
                  <select
                    value={selectedPageForSnippet}
                    onChange={(e) => setSelectedPageForSnippet(e.target.value)}
                    className="w-full text-xs bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-slate-700 font-medium focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="">Default Primary Page ID ({gaConfig?.config?.page_id || 'G-MKTINTEL01'})</option>
                    {(gaConfig?.pages || []).map((p) => (
                      <option key={p.id} value={p.ga_page_id || p.page_id}>
                        {p.title} — {p.page_id} ({p.ga_page_id || gaConfig?.config?.page_id})
                      </option>
                    ))}
                  </select>
                </div>

                <div className="mt-3 relative bg-slate-950 text-slate-200 font-mono text-[11px] p-3.5 rounded-lg border border-slate-800 overflow-x-auto max-h-56">
                  <pre className="whitespace-pre">{gaConfig?.tracking_code || 'Loading tracking code snippet...'}</pre>
                </div>
              </div>

              <div className="p-3 bg-indigo-50/70 border border-indigo-100 rounded-lg text-indigo-900 text-xs">
                <span className="font-bold">Deployment Notice:</span> Add this snippet immediately after the opening{' '}
                <code className="bg-indigo-100 px-1 py-0.5 rounded text-indigo-800">&lt;head&gt;</code> tag on every page.
              </div>
            </div>
          </div>

          {/* Section 2: Analytics Dashboard with Detailed Website Statistics */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
              <div>
                <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
                  <BarChart3 className="w-5 h-5 text-indigo-600" />
                  Website Analytics Statistics Dashboard
                </h3>
                <p className="text-xs text-slate-500">
                  Detailed traffic, engagement, pageviews, and bounce rate metrics from the Market Intel database.
                </p>
              </div>

              <div className="flex items-center gap-2">
                <div className="inline-flex rounded-lg border border-slate-200 p-0.5 bg-slate-50 text-xs font-bold text-slate-700">
                  <button
                    onClick={() => setGaRange('7d')}
                    className={`px-3 py-1 rounded-md transition ${gaRange === '7d' ? 'bg-white shadow-xs text-indigo-600' : 'hover:text-slate-900'}`}
                  >
                    7 Days
                  </button>
                  <button
                    onClick={() => setGaRange('30d')}
                    className={`px-3 py-1 rounded-md transition ${gaRange === '30d' ? 'bg-white shadow-xs text-indigo-600' : 'hover:text-slate-900'}`}
                  >
                    30 Days
                  </button>
                  <button
                    onClick={() => setGaRange('90d')}
                    className={`px-3 py-1 rounded-md transition ${gaRange === '90d' ? 'bg-white shadow-xs text-indigo-600' : 'hover:text-slate-900'}`}
                  >
                    Quarter
                  </button>
                </div>

                <button
                  onClick={() => setIsRecordStatOpen(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-xs font-bold transition"
                >
                  <Plus className="w-3.5 h-3.5" />
                  Record Stat
                </button>
              </div>
            </div>

            {/* KPI Cards Strip */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80">
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Total Page Views</span>
                <div className="text-2xl font-black text-slate-900 mt-1">
                  {gaDashboard?.summary?.total_page_views?.toLocaleString() || '0'}
                </div>
                <span className="text-[11px] text-emerald-600 font-semibold mt-0.5 block">+12.4% vs previous period</span>
              </div>

              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80">
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Unique Visitors</span>
                <div className="text-2xl font-black text-slate-900 mt-1">
                  {gaDashboard?.summary?.unique_visitors?.toLocaleString() || '0'}
                </div>
                <span className="text-[11px] text-slate-500 font-medium mt-0.5 block">Total distinct users</span>
              </div>

              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80">
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Avg Session Duration</span>
                <div className="text-2xl font-black text-slate-900 mt-1">
                  {Math.floor((gaDashboard?.summary?.avg_duration_seconds || 0) / 60)}m {(gaDashboard?.summary?.avg_duration_seconds || 0) % 60}s
                </div>
                <span className="text-[11px] text-slate-500 font-medium mt-0.5 block">
                  Engagement rate: {gaDashboard?.summary?.engagement_rate ?? 0}%
                </span>
              </div>

              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200/80">
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Bounce Rate</span>
                <div className="text-2xl font-black text-slate-900 mt-1">
                  {gaDashboard?.summary?.bounce_rate ?? 0}%
                </div>
                <span className="text-[11px] text-emerald-600 font-semibold mt-0.5 block">Recorded metric</span>
              </div>
            </div>

            {/* Detailed Page Statistics Table */}
            <div>
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2.5">
                Detailed Website Statistics per Page ID & Path
              </h4>
              <div className="border border-slate-200 rounded-xl overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-bold uppercase tracking-wider text-[10px]">
                    <tr>
                      <th className="px-4 py-2.5">Page Title & Path</th>
                      <th className="px-4 py-2.5">Page ID</th>
                      <th className="px-4 py-2.5 text-right">Views</th>
                      <th className="px-4 py-2.5 text-right">Visitors</th>
                      <th className="px-4 py-2.5 text-right">Sessions</th>
                      <th className="px-4 py-2.5 text-right">Avg Time</th>
                      <th className="px-4 py-2.5 text-right">Bounce Rate</th>
                      <th className="px-4 py-2.5 text-right">Conversions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {(gaDashboard?.page_statistics || []).map((row, idx) => (
                      <tr key={idx} className="hover:bg-slate-50/70 transition">
                        <td className="px-4 py-2.5">
                          <div className="font-bold text-slate-900">{row.page_title}</div>
                          <div className="text-[11px] text-indigo-600 font-mono">{row.page_path}</div>
                        </td>
                        <td className="px-4 py-2.5">
                          <span className="font-mono text-[11px] px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 font-bold">
                            {row.page_id}
                          </span>
                        </td>
                        <td className="px-4 py-2.5 text-right font-bold text-slate-900">
                          {row.page_views?.toLocaleString()}
                        </td>
                        <td className="px-4 py-2.5 text-right text-slate-600">
                          {row.unique_visitors?.toLocaleString()}
                        </td>
                        <td className="px-4 py-2.5 text-right text-slate-600">
                          {row.sessions?.toLocaleString()}
                        </td>
                        <td className="px-4 py-2.5 text-right text-slate-600">
                          {Math.floor((row.avg_duration_seconds || 0) / 60)}m {(row.avg_duration_seconds || 0) % 60}s
                        </td>
                        <td className="px-4 py-2.5 text-right text-slate-600 font-medium">
                          {row.bounce_rate}%
                        </td>
                        <td className="px-4 py-2.5 text-right font-bold text-emerald-600">
                          {row.conversions || 0}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Traffic Sources & Device Distribution Strip */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
              <div className="p-4 rounded-xl border border-slate-200">
                <h5 className="text-xs font-bold text-slate-800 mb-2">Traffic Sources</h5>
                <div className="space-y-1.5 text-xs">
                  {(gaDashboard?.traffic_sources || []).map((src, i) => (
                    <div key={i} className="flex items-center justify-between py-1 border-b border-slate-50 last:border-0">
                      <span className="text-slate-600">{src.traffic_source}</span>
                      <span className="font-bold text-slate-900">{src.sessions?.toLocaleString()}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="p-4 rounded-xl border border-slate-200">
                <h5 className="text-xs font-bold text-slate-800 mb-2">Device Categories</h5>
                <div className="space-y-1.5 text-xs">
                  {(gaDashboard?.devices || []).map((dev, i) => (
                    <div key={i} className="flex items-center justify-between py-1 border-b border-slate-50 last:border-0">
                      <span className="text-slate-600">{dev.device_category}</span>
                      <span className="font-bold text-slate-900">{dev.sessions?.toLocaleString()}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="p-4 rounded-xl border border-slate-200">
                <h5 className="text-xs font-bold text-slate-800 mb-2">Top Countries</h5>
                <div className="space-y-1.5 text-xs">
                  {(gaDashboard?.countries || []).map((c, i) => (
                    <div key={i} className="flex items-center justify-between py-1 border-b border-slate-50 last:border-0">
                      <span className="text-slate-600">{c.country}</span>
                      <span className="font-bold text-slate-900">{c.page_views?.toLocaleString()}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* TAB 3: Google Search Console                                        */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      {activeTab === 'search_console' && (
        <div className="space-y-6">
          {/* Performance Overview Strip */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-lg bg-blue-50 text-blue-600">
                  <Search className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">Google Search Console Performance Dashboard</h3>
                  <p className="text-[11px] text-slate-500">Live search performance, clicks, impressions, CTR, and indexing state.</p>
                </div>
              </div>
              <button
                onClick={() => handleSubmitIndexing(true)}
                disabled={submittingIndexing}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold transition shadow-xs"
              >
                <Zap className="w-3.5 h-3.5" />
                {submittingIndexing ? 'Submitting Indexing...' : 'Bulk Index All CMS Pages'}
              </button>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Total Clicks</span>
                <div className="text-2xl font-black text-blue-600 mt-1">
                  {gscData?.summary?.total_clicks?.toLocaleString() ?? 0}
                </div>
                <span className="text-[11px] text-slate-500">Organic Google Search</span>
              </div>

              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Total Impressions</span>
                <div className="text-2xl font-black text-slate-900 mt-1">
                  {gscData?.summary?.total_impressions?.toLocaleString() ?? 0}
                </div>
                <span className="text-[11px] text-slate-500">Search results appearances</span>
              </div>

              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Average CTR</span>
                <div className="text-2xl font-black text-slate-900 mt-1">
                  {gscData?.summary?.avg_ctr ?? 0}%
                </div>
                <span className="text-[11px] text-emerald-600 font-semibold">Search intent</span>
              </div>

              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Average Position</span>
                <div className="text-2xl font-black text-slate-900 mt-1">
                  {gscData?.summary?.avg_position ?? 0}
                </div>
                <span className="text-[11px] text-slate-500">SERP average</span>
              </div>
            </div>
          </div>

          {/* URL Inspection & Indexing Request Box */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Live URL Inspection Card */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-4">
              <div className="flex items-center gap-2 pb-3 border-b border-slate-100">
                <Search className="w-4 h-4 text-indigo-600" />
                <h3 className="text-sm font-bold text-slate-900">URL Inspection & Coverage</h3>
              </div>

              <form onSubmit={handleInspectUrl} className="flex gap-2">
                <input
                  type="text"
                  placeholder="https://marketintel.hikasimat.com/solutions/prospect-database"
                  value={inspectUrlInput}
                  onChange={(e) => setInspectUrlInput(e.target.value)}
                  className="flex-1 px-3 py-1.5 text-xs bg-slate-50 border border-slate-200 rounded-lg focus:ring-1 focus:ring-indigo-500 focus:outline-none"
                  required
                />
                <button
                  type="submit"
                  disabled={inspectingUrl}
                  className="px-3.5 py-1.5 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-xs font-bold transition disabled:opacity-50"
                >
                  {inspectingUrl ? 'Inspecting...' : 'Inspect URL'}
                </button>
              </form>

              {inspectResult ? (
                <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-700">Presence on Google:</span>
                    <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800">
                      {inspectResult.indexing_state}
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-600">
                    <span className="font-semibold">Coverage:</span> {inspectResult.coverage_status}
                  </div>
                  <div className="text-[11px] text-slate-600 flex items-center justify-between">
                    <span>Mobile Usability: <strong className="text-emerald-700">{inspectResult.mobile_usability}</strong></span>
                    <span>Crawl Allowed: <strong className="text-emerald-700">{inspectResult.crawl_allowed ? 'Yes' : 'No'}</strong></span>
                  </div>
                  <button
                    onClick={() => {
                      setManualIndexUrl(inspectResult.page_url);
                      handleSubmitIndexing(false);
                    }}
                    className="w-full mt-2 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-md font-bold text-[11px] transition"
                  >
                    Request Indexing for This URL
                  </button>
                </div>
              ) : (
                <p className="text-[11px] text-slate-400">
                  Enter any website URL above to inspect Google Index status, mobile usability, and canonicalization.
                </p>
              )}
            </div>

            {/* Quick Submit Indexing Card */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-4">
              <div className="flex items-center gap-2 pb-3 border-b border-slate-100">
                <Send className="w-4 h-4 text-blue-600" />
                <h3 className="text-sm font-bold text-slate-900">Submit Single Indexing Request</h3>
              </div>

              <div className="space-y-3 text-xs">
                <div>
                  <label className="block font-bold text-slate-700 mb-1">Page URL to Submit to Google Index</label>
                  <input
                    type="text"
                    placeholder="https://marketintel.hikasimat.com/insights/2026-apac-corporate-ma-report"
                    value={manualIndexUrl}
                    onChange={(e) => setManualIndexUrl(e.target.value)}
                    className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg focus:ring-1 focus:ring-blue-500 focus:outline-none"
                  />
                </div>

                <button
                  onClick={() => handleSubmitIndexing(false)}
                  disabled={submittingIndexing || !manualIndexUrl.trim()}
                  className="w-full py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-bold text-xs transition disabled:opacity-50"
                >
                  {submittingIndexing ? 'Submitting to Google...' : 'Submit Indexing Request'}
                </button>
              </div>
            </div>
          </div>

          {/* Domain Registration & Verification Section */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                  <ShieldCheck className="w-4 h-4 text-emerald-600" />
                  Domain Registration & Verification
                </h3>
                <p className="text-[11px] text-slate-500">Manage Search Console domain properties and DNS / HTML verification tokens.</p>
              </div>
              <button
                onClick={() => setIsRegisterDomainOpen(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold transition shadow-xs"
              >
                <Plus className="w-3.5 h-3.5" />
                Register Domain
              </button>
            </div>

            <div className="border border-slate-200 rounded-xl overflow-hidden">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-bold uppercase tracking-wider text-[10px]">
                  <tr>
                    <th className="px-4 py-2.5">Domain Property</th>
                    <th className="px-4 py-2.5">Verification Method</th>
                    <th className="px-4 py-2.5">Verification Token / Record</th>
                    <th className="px-4 py-2.5">Status</th>
                    <th className="px-4 py-2.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(gscData?.domains || []).map((dom) => (
                    <tr key={dom.id} className="hover:bg-slate-50/70 transition">
                      <td className="px-4 py-2.5">
                        <div className="font-bold text-slate-900">{dom.domain}</div>
                        <div className="text-[10px] text-slate-400">{dom.property_type}</div>
                      </td>
                      <td className="px-4 py-2.5 text-slate-700 font-medium">
                        {dom.verification_method}
                      </td>
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2">
                          <code className="text-[10px] bg-slate-100 px-2 py-0.5 rounded font-mono text-slate-700 truncate max-w-xs">
                            {dom.dns_txt_record}
                          </code>
                          <button
                            onClick={() => copyToClipboard(dom.dns_txt_record, 'DNS TXT Record copied!')}
                            className="p-1 text-slate-400 hover:text-slate-700"
                            title="Copy DNS Record"
                          >
                            <Copy className="w-3 h-3" />
                          </button>
                        </div>
                      </td>
                      <td className="px-4 py-2.5">
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                            dom.is_verified
                              ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                              : 'bg-amber-50 text-amber-800 border-amber-200'
                          }`}
                        >
                          {dom.is_verified ? 'Verified Owner' : 'Pending Verification'}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right space-x-1.5">
                        {!dom.is_verified && (
                          <button
                            onClick={() => handleVerifyDomain(dom.id, dom.verification_method)}
                            className="px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-[11px] font-bold"
                          >
                            Verify
                          </button>
                        )}
                        <button
                          onClick={() => handleDeleteDomain(dom.id)}
                          className="p-1 text-slate-400 hover:text-red-600 rounded"
                          title="Delete domain"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Page Sitemap Management Section */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                  <Layers className="w-4 h-4 text-blue-600" />
                  Page Sitemap Management
                </h3>
                <p className="text-[11px] text-slate-500">Submitted XML sitemaps, crawl status, and discovered URLs.</p>
              </div>
              <button
                onClick={() => setIsSubmitSitemapOpen(true)}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-xs font-bold transition shadow-xs"
              >
                <Plus className="w-3.5 h-3.5" />
                Submit Sitemap
              </button>
            </div>

            <div className="border border-slate-200 rounded-xl overflow-hidden">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-bold uppercase tracking-wider text-[10px]">
                  <tr>
                    <th className="px-4 py-2.5">Sitemap URL</th>
                    <th className="px-4 py-2.5">Type</th>
                    <th className="px-4 py-2.5 text-right">Discovered Pages</th>
                    <th className="px-4 py-2.5 text-right">Indexed</th>
                    <th className="px-4 py-2.5">Status</th>
                    <th className="px-4 py-2.5">Last Crawled</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(gscData?.sitemaps || []).map((sm) => (
                    <tr key={sm.id} className="hover:bg-slate-50/70 transition">
                      <td className="px-4 py-2.5 font-mono text-[11px] text-blue-600 font-medium">
                        {sm.sitemap_url}
                      </td>
                      <td className="px-4 py-2.5 text-slate-600">{sm.sitemap_type}</td>
                      <td className="px-4 py-2.5 text-right font-bold text-slate-800">
                        {sm.discovered_pages_count}
                      </td>
                      <td className="px-4 py-2.5 text-right font-bold text-emerald-600">
                        {sm.indexed_pages_count}
                      </td>
                      <td className="px-4 py-2.5">
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-800 border border-emerald-200">
                          {sm.status}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-slate-400 text-[10px]">
                        {sm.last_crawled_at ? new Date(sm.last_crawled_at).toLocaleDateString() : 'Recent'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Top Search Queries Table */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-4">
            <h3 className="text-sm font-bold text-slate-900">Top Organic Search Queries on Google</h3>
            <div className="border border-slate-200 rounded-xl overflow-hidden">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-bold uppercase tracking-wider text-[10px]">
                  <tr>
                    <th className="px-4 py-2.5">Top Query</th>
                    <th className="px-4 py-2.5 text-right">Clicks</th>
                    <th className="px-4 py-2.5 text-right">Impressions</th>
                    <th className="px-4 py-2.5 text-right">CTR</th>
                    <th className="px-4 py-2.5 text-right">Position</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(gscData?.top_queries || []).map((q, idx) => (
                    <tr key={idx} className="hover:bg-slate-50/70 transition">
                      <td className="px-4 py-2.5 font-bold text-slate-900">{q.query}</td>
                      <td className="px-4 py-2.5 text-right font-bold text-blue-600">{q.clicks?.toLocaleString()}</td>
                      <td className="px-4 py-2.5 text-right text-slate-600">{q.impressions?.toLocaleString()}</td>
                      <td className="px-4 py-2.5 text-right text-slate-600 font-medium">{q.ctr}%</td>
                      <td className="px-4 py-2.5 text-right font-bold text-slate-800">{q.position}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* TAB 4: Bing Webmaster Tools                                         */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      {activeTab === 'bing' && (
        <div className="space-y-6">
          {/* Performance Summary Cards */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-lg bg-teal-50 text-teal-600">
                  <Globe className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">Bing Webmaster Tools & IndexNow Suite</h3>
                  <p className="text-[11px] text-slate-500">Live search performance, IndexNow ping submissions, and crawl metrics.</p>
                </div>
              </div>
              <button
                onClick={() => handleSubmitBingUrls(true)}
                disabled={submittingBingUrls}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-xs font-bold transition shadow-xs"
              >
                <Zap className="w-3.5 h-3.5" />
                {submittingBingUrls ? 'Submitting to IndexNow...' : 'Index All Published Pages via IndexNow'}
              </button>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Bing Clicks</span>
                <div className="text-2xl font-black text-teal-600 mt-1">
                  {bingData?.summary?.total_clicks?.toLocaleString() ?? 0}
                </div>
                <span className="text-[11px] text-slate-500">Organic Bing Search</span>
              </div>

              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Bing Impressions</span>
                <div className="text-2xl font-black text-slate-900 mt-1">
                  {bingData?.summary?.total_impressions?.toLocaleString() ?? 0}
                </div>
                <span className="text-[11px] text-slate-500">Search appearances</span>
              </div>

              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Crawled Pages</span>
                <div className="text-2xl font-black text-slate-900 mt-1">
                  {bingData?.summary?.crawled_pages ?? 0}
                </div>
                <span className="text-[11px] text-emerald-600 font-semibold">Crawl errors: {bingData?.summary?.crawl_errors ?? 0}</span>
              </div>

              <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">IndexNow Daily Quota</span>
                <div className="text-2xl font-black text-slate-900 mt-1">
                  {bingData?.summary?.daily_quota_remaining?.toLocaleString() ?? '10,000'}
                </div>
                <span className="text-[11px] text-slate-500">URLs remaining today</span>
              </div>
            </div>
          </div>

          {/* Configuration & IndexNow Box */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Bing Configuration Card */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                <h3 className="text-sm font-bold text-slate-900">Bing Webmaster Site Configuration</h3>
                <span
                  className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                    bingData?.config?.is_verified
                      ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                      : 'bg-amber-50 text-amber-800 border-amber-200'
                  }`}
                >
                  {bingData?.config?.is_verified ? 'Site Verified' : 'Pending Verification'}
                </span>
              </div>

              <form onSubmit={handleSaveBingConfig} className="space-y-3.5 text-xs">
                <div>
                  <label className="block font-bold text-slate-700 mb-1">Site URL</label>
                  <input
                    type="url"
                    value={bingData?.config?.site_url || 'https://marketintel.hikasimat.com'}
                    onChange={(e) =>
                      setBingData((prev) => ({
                        ...prev,
                        config: { ...prev.config, site_url: e.target.value },
                      }))
                    }
                    className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg focus:ring-1 focus:ring-teal-500 focus:outline-none"
                    required
                  />
                </div>

                <div>
                  <label className="block font-bold text-slate-700 mb-1">Bing Webmaster API Key</label>
                  <input
                    type="text"
                    value={bingApiKeyInput}
                    onChange={(e) => setBingApiKeyInput(e.target.value)}
                    placeholder="Enter or paste Bing Webmaster API key..."
                    className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-mono focus:ring-1 focus:ring-teal-500 focus:outline-none"
                  />
                  <p className="text-[10px] text-slate-400 mt-1">Encrypted with Fernet in Market Intel database at rest.</p>
                </div>

                <div>
                  <label className="block font-bold text-slate-700 mb-1">Verification Meta Tag</label>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      readOnly
                      value={bingData?.config?.meta_tag_snippet || '<meta name="msvalidate.01" ... />'}
                      className="w-full px-3 py-1.5 bg-slate-100 border border-slate-200 rounded-lg font-mono text-[11px] text-slate-700"
                    />
                    <button
                      type="button"
                      onClick={() => copyToClipboard(bingData?.config?.meta_tag_snippet, 'Bing Meta tag copied!')}
                      className="p-1.5 text-slate-500 hover:text-slate-800 border border-slate-200 rounded-lg"
                      title="Copy meta tag"
                    >
                      <Copy className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                <div className="flex items-center gap-2 pt-2">
                  <button
                    type="submit"
                    disabled={savingBingConfig}
                    className="flex-1 py-2 bg-teal-600 hover:bg-teal-700 text-white rounded-lg font-bold text-xs transition disabled:opacity-50"
                  >
                    {savingBingConfig ? 'Saving...' : 'Save Bing Configuration'}
                  </button>

                  {!bingData?.config?.is_verified && (
                    <button
                      type="button"
                      onClick={handleVerifyBingSite}
                      className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-bold text-xs transition"
                    >
                      Verify Site
                    </button>
                  )}
                </div>
              </form>
            </div>

            {/* IndexNow Key & Quick Submission Card */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                <h3 className="text-sm font-bold text-slate-900">IndexNow Protocol Configuration</h3>
                <button
                  onClick={handleRegenerateIndexNowKey}
                  className="text-xs text-teal-600 hover:text-teal-700 font-bold"
                >
                  Regenerate Key
                </button>
              </div>

              <div className="space-y-3 text-xs">
                <div>
                  <label className="block font-bold text-slate-700 mb-1">Active IndexNow Key</label>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      readOnly
                      value={bingData?.config?.indexnow_key || ''}
                      className="w-full px-3 py-1.5 bg-slate-100 border border-slate-200 rounded-lg font-mono text-slate-800 text-[11px]"
                    />
                    <button
                      type="button"
                      onClick={() => copyToClipboard(bingData?.config?.indexnow_key, 'IndexNow key copied!')}
                      className="p-1.5 text-slate-500 hover:text-slate-800 border border-slate-200 rounded-lg"
                    >
                      <Copy className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                <div>
                  <label className="block font-bold text-slate-700 mb-1">Submit URLs to Bing IndexNow</label>
                  <textarea
                    rows="3"
                    placeholder="https://marketintel.hikasimat.com/pricing&#10;https://marketintel.hikasimat.com/solutions/prospect-database"
                    value={bingUrlsInput}
                    onChange={(e) => setBingUrlsInput(e.target.value)}
                    className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-mono text-xs focus:ring-1 focus:ring-teal-500 focus:outline-none"
                  />
                  <p className="text-[10px] text-slate-400 mt-0.5">Separate multiple URLs by commas or new lines.</p>
                </div>

                <div className="flex items-center gap-3">
                  <select
                    value={bingProtocol}
                    onChange={(e) => setBingProtocol(e.target.value)}
                    className="text-xs bg-slate-50 border border-slate-200 rounded-lg px-2.5 py-1.5 text-slate-700 font-medium"
                  >
                    <option value="INDEXNOW">IndexNow Instant Ping</option>
                    <option value="BING_API">Bing Webmaster URL Submission API</option>
                  </select>

                  <button
                    onClick={() => handleSubmitBingUrls(false)}
                    disabled={submittingBingUrls || !bingUrlsInput.trim()}
                    className="flex-1 py-1.5 bg-teal-600 hover:bg-teal-700 text-white rounded-lg font-bold text-xs transition disabled:opacity-50"
                  >
                    {submittingBingUrls ? 'Submitting...' : 'Submit URLs'}
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Bing Sitemaps & Submission History Strip */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Bing Sitemaps Card */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                <h3 className="text-sm font-bold text-slate-900">Bing Sitemaps</h3>
              </div>

              <form onSubmit={handleSubmitBingSitemap} className="flex gap-2 text-xs">
                <input
                  type="url"
                  value={bingSitemapInput}
                  onChange={(e) => setBingSitemapInput(e.target.value)}
                  placeholder="https://marketintel.hikasimat.com/sitemap.xml"
                  className="flex-1 px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg focus:ring-1 focus:ring-teal-500 focus:outline-none"
                  required
                />
                <button
                  type="submit"
                  disabled={submittingBingSitemap}
                  className="px-3 py-1.5 bg-teal-600 hover:bg-teal-700 text-white rounded-lg font-bold transition disabled:opacity-50"
                >
                  Submit
                </button>
              </form>

              <div className="border border-slate-200 rounded-lg overflow-hidden">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-bold uppercase tracking-wider text-[10px]">
                    <tr>
                      <th className="px-3 py-2">Sitemap URL</th>
                      <th className="px-3 py-2 text-right">Discovered</th>
                      <th className="px-3 py-2 text-right">Indexed</th>
                      <th className="px-3 py-2">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {(bingData?.sitemaps || []).map((sm) => (
                      <tr key={sm.id}>
                        <td className="px-3 py-2 font-mono text-[11px] text-teal-600 truncate max-w-xs">{sm.sitemap_url}</td>
                        <td className="px-3 py-2 text-right font-bold text-slate-800">{sm.urls_discovered}</td>
                        <td className="px-3 py-2 text-right font-bold text-emerald-600">{sm.urls_indexed}</td>
                        <td className="px-3 py-2">
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-800">
                            {sm.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Recent URL Submissions Log */}
            <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-4">
              <h3 className="text-sm font-bold text-slate-900 pb-3 border-b border-slate-100">
                Recent URL Indexing Submissions Log
              </h3>
              <div className="border border-slate-200 rounded-lg overflow-hidden max-h-56 overflow-y-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-bold uppercase tracking-wider text-[10px] sticky top-0">
                    <tr>
                      <th className="px-3 py-2">Submitted Page URL</th>
                      <th className="px-3 py-2">Protocol</th>
                      <th className="px-3 py-2">Status</th>
                      <th className="px-3 py-2 text-right">Code</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {(bingData?.submissions || []).map((sub) => (
                      <tr key={sub.id}>
                        <td className="px-3 py-2 font-mono text-[11px] text-slate-700 truncate max-w-xs">{sub.page_url}</td>
                        <td className="px-3 py-2 text-[10px] text-slate-500">{sub.submission_protocol}</td>
                        <td className="px-3 py-2">
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-teal-50 text-teal-800">
                            {sub.status}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-right font-mono font-bold text-emerald-600">{sub.http_status_code}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* TAB 5: Google Ads                                                   */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      {activeTab === 'google_ads' && (
        <div className="space-y-6">
          {/* Header & KPI Summary */}
          <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-lg bg-amber-50 text-amber-600">
                  <DollarSign className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">Market Intel Google Ads Management</h3>
                  <p className="text-[11px] text-slate-500">
                    Account: {adsData?.config?.account_name} ({adsData?.config?.customer_id}) — Currency: {adsData?.config?.currency_code}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setIsAdsAccountConfigOpen(true)}
                  className="px-3 py-1.5 border border-slate-200 rounded-lg text-xs font-bold text-slate-700 hover:bg-slate-50 transition"
                >
                  Account Settings
                </button>
                <button
                  onClick={() => setIsCreateCampaignOpen(true)}
                  className="inline-flex items-center gap-1.5 px-3.5 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-bold transition shadow-xs"
                >
                  <Plus className="w-4 h-4" />
                  Create Campaign
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Total Spend</span>
                <div className="text-xl font-black text-slate-900 mt-1">
                  ${Number(adsData?.summary?.total_spend || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </div>
                <span className="text-[10px] text-slate-500">Budget: ${adsData?.summary?.total_daily_budget}/day</span>
              </div>

              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Clicks & Impressions</span>
                <div className="text-xl font-black text-amber-600 mt-1">
                  {adsData?.summary?.total_clicks?.toLocaleString()}
                </div>
                <span className="text-[10px] text-slate-500">{adsData?.summary?.total_impressions?.toLocaleString()} imps</span>
              </div>

              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Avg CTR</span>
                <div className="text-xl font-black text-slate-900 mt-1">
                  {adsData?.summary?.avg_ctr}%
                </div>
                <span className="text-[10px] text-slate-500">Avg CPC: ${adsData?.summary?.avg_cpc}</span>
              </div>

              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Conversions</span>
                <div className="text-xl font-black text-emerald-600 mt-1">
                  {adsData?.summary?.total_conversions}
                </div>
                <span className="text-[10px] text-slate-500">Value: ${adsData?.summary?.total_conversion_value?.toLocaleString()}</span>
              </div>

              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Cost / Conversion (CPA)</span>
                <div className="text-xl font-black text-slate-900 mt-1">
                  ${adsData?.summary?.avg_cpa}
                </div>
                <span className="text-[10px] text-emerald-600 font-semibold">Target achieved</span>
              </div>

              <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">ROAS (Return on Ad Spend)</span>
                <div className="text-xl font-black text-indigo-600 mt-1">
                  {adsData?.summary?.roas}x
                </div>
                <span className="text-[10px] text-slate-500">Gross revenue ratio</span>
              </div>
            </div>
          </div>

          {/* Sub Navigation */}
          <div className="flex border-b border-slate-200 space-x-1 text-xs font-bold">
            <button
              onClick={() => setAdsSubTab('campaigns')}
              className={`px-3 py-2 rounded-t-lg transition border-b-2 -mb-px ${
                adsSubTab === 'campaigns'
                  ? 'border-amber-600 text-amber-700 bg-amber-50/50'
                  : 'border-transparent text-slate-600 hover:text-slate-900'
              }`}
            >
              Campaigns ({adsData?.campaigns?.length || 0})
            </button>
            <button
              onClick={() => setAdsSubTab('adgroups')}
              className={`px-3 py-2 rounded-t-lg transition border-b-2 -mb-px ${
                adsSubTab === 'adgroups'
                  ? 'border-amber-600 text-amber-700 bg-amber-50/50'
                  : 'border-transparent text-slate-600 hover:text-slate-900'
              }`}
            >
              Ad Groups ({adsData?.ad_groups?.length || 0})
            </button>
            <button
              onClick={() => setAdsSubTab('keywords')}
              className={`px-3 py-2 rounded-t-lg transition border-b-2 -mb-px ${
                adsSubTab === 'keywords'
                  ? 'border-amber-600 text-amber-700 bg-amber-50/50'
                  : 'border-transparent text-slate-600 hover:text-slate-900'
              }`}
            >
              Keywords ({adsData?.keywords?.length || 0})
            </button>
            <button
              onClick={() => setAdsSubTab('audit')}
              className={`px-3 py-2 rounded-t-lg transition border-b-2 -mb-px ${
                adsSubTab === 'audit'
                  ? 'border-amber-600 text-amber-700 bg-amber-50/50'
                  : 'border-transparent text-slate-600 hover:text-slate-900'
              }`}
            >
              Audit Logs ({adsData?.audit_logs?.length || 0})
            </button>
          </div>

          {/* Sub-tab 1: Campaigns Table */}
          {adsSubTab === 'campaigns' && (
            <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-bold uppercase tracking-wider text-[10px]">
                  <tr>
                    <th className="px-4 py-3">Campaign Name</th>
                    <th className="px-4 py-3">Channel</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3 text-right">Daily Budget</th>
                    <th className="px-4 py-3 text-right">Spend</th>
                    <th className="px-4 py-3 text-right">Clicks</th>
                    <th className="px-4 py-3 text-right">CTR</th>
                    <th className="px-4 py-3 text-right">Conversions</th>
                    <th className="px-4 py-3 text-right">ROAS</th>
                    <th className="px-4 py-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(!adsData?.campaigns || adsData.campaigns.length === 0) ? (
                    <tr>
                      <td colSpan="10" className="px-4 py-8 text-center text-slate-500">
                        No Google Ads campaigns found in database. Click &quot;+ Create Campaign&quot; to launch your first real campaign.
                      </td>
                    </tr>
                  ) : (
                    adsData.campaigns.map((c) => (
                    <tr key={c.id} className="hover:bg-slate-50/70 transition">
                      <td className="px-4 py-3">
                        <div className="font-bold text-slate-900">{c.name}</div>
                        <div className="text-[10px] text-slate-400 font-mono">ID: {c.external_campaign_id} • {c.bidding_strategy}</div>
                      </td>
                      <td className="px-4 py-3">
                        <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-700 border border-slate-200">
                          {c.channel_type}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <button
                          onClick={() => handleToggleCampaignStatus(c)}
                          className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-bold border transition ${
                            c.status === 'ENABLED'
                              ? 'bg-emerald-50 text-emerald-800 border-emerald-200 hover:bg-emerald-100'
                              : 'bg-amber-50 text-amber-800 border-amber-200 hover:bg-amber-100'
                          }`}
                        >
                          {c.status === 'ENABLED' ? <Play className="w-2.5 h-2.5 fill-current" /> : <Pause className="w-2.5 h-2.5 fill-current" />}
                          {c.status}
                        </button>
                      </td>
                      <td className="px-4 py-3 text-right font-bold text-slate-900">
                        ${Number(c.daily_budget).toFixed(2)}/day
                      </td>
                      <td className="px-4 py-3 text-right font-bold text-slate-900">
                        ${Number(c.cost).toLocaleString(undefined, { minimumFractionDigits: 2 })}
                      </td>
                      <td className="px-4 py-3 text-right text-slate-600">{c.clicks?.toLocaleString()}</td>
                      <td className="px-4 py-3 text-right text-slate-600">{c.ctr}%</td>
                      <td className="px-4 py-3 text-right font-bold text-emerald-600">{c.conversions}</td>
                      <td className="px-4 py-3 text-right font-bold text-indigo-600">{c.roas}x</td>
                      <td className="px-4 py-3 text-right space-x-1.5 whitespace-nowrap">
                        <button
                          onClick={() => handleOpenBudgetModal(c)}
                          className="px-2.5 py-1 text-slate-700 hover:bg-slate-100 border border-slate-200 rounded text-[11px] font-bold transition"
                        >
                          Budget
                        </button>
                        <button
                          onClick={() => handleDeleteCampaign(c)}
                          className="p-1 text-slate-400 hover:text-red-600 rounded"
                          title="Remove campaign"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  )))}
                </tbody>
              </table>
            </div>
          )}

          {/* Sub-tab 2: Ad Groups Table */}
          {adsSubTab === 'adgroups' && (
            <div className="space-y-4">
              <div className="flex justify-end">
                <button
                  onClick={() => setIsCreateAdGroupOpen(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-bold transition shadow-xs"
                >
                  <Plus className="w-3.5 h-3.5" />
                  Add Ad Group
                </button>
              </div>

              <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-bold uppercase tracking-wider text-[10px]">
                    <tr>
                      <th className="px-4 py-3">Ad Group Name</th>
                      <th className="px-4 py-3">Campaign</th>
                      <th className="px-4 py-3 text-right">Default CPC Bid</th>
                      <th className="px-4 py-3 text-right">Clicks</th>
                      <th className="px-4 py-3 text-right">Cost</th>
                      <th className="px-4 py-3 text-right">Conversions</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {(!adsData?.ad_groups || adsData.ad_groups.length === 0) ? (
                      <tr>
                        <td colSpan="8" className="px-4 py-8 text-center text-slate-500">
                          No ad groups found in database. Click &quot;+ Add Ad Group&quot; to organize your ads.
                        </td>
                      </tr>
                    ) : (
                      adsData.ad_groups.map((ag) => (
                      <tr key={ag.id} className="hover:bg-slate-50/70 transition">
                        <td className="px-4 py-3 font-bold text-slate-900">{ag.name}</td>
                        <td className="px-4 py-3 text-slate-600">{ag.campaign_name}</td>
                        <td className="px-4 py-3 text-right font-bold text-slate-800">${Number(ag.cpc_bid).toFixed(2)}</td>
                        <td className="px-4 py-3 text-right text-slate-600">{ag.clicks?.toLocaleString()}</td>
                        <td className="px-4 py-3 text-right font-bold text-slate-900">${Number(ag.cost).toFixed(2)}</td>
                        <td className="px-4 py-3 text-right font-bold text-emerald-600">{ag.conversions}</td>
                        <td className="px-4 py-3">
                          <button
                            onClick={() => handleToggleAdGroupStatus(ag)}
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                              ag.status === 'ENABLED'
                                ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                                : 'bg-slate-100 text-slate-600 border-slate-200'
                            }`}
                          >
                            {ag.status}
                          </button>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button
                            onClick={() => handleDeleteAdGroup(ag)}
                            className="p-1 text-slate-400 hover:text-red-600 rounded"
                            title="Delete ad group"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    )))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Sub-tab 3: Keywords Table */}
          {adsSubTab === 'keywords' && (
            <div className="space-y-4">
              <div className="flex justify-end">
                <button
                  onClick={() => setIsCreateKeywordOpen(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-bold transition shadow-xs"
                >
                  <Plus className="w-3.5 h-3.5" />
                  Add Keyword
                </button>
              </div>

              <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-bold uppercase tracking-wider text-[10px]">
                    <tr>
                      <th className="px-4 py-3">Keyword</th>
                      <th className="px-4 py-3">Match Type</th>
                      <th className="px-4 py-3">Ad Group / Campaign</th>
                      <th className="px-4 py-3 text-right">Quality Score</th>
                      <th className="px-4 py-3 text-right">Max CPC</th>
                      <th className="px-4 py-3 text-right">Clicks</th>
                      <th className="px-4 py-3 text-right">Conversions</th>
                      <th className="px-4 py-3">Status</th>
                      <th className="px-4 py-3 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {(!adsData?.keywords || adsData.keywords.length === 0) ? (
                      <tr>
                        <td colSpan="9" className="px-4 py-8 text-center text-slate-500">
                          No keywords found in database. Click &quot;+ Add Keyword&quot; to target high-intent search terms.
                        </td>
                      </tr>
                    ) : (
                      adsData.keywords.map((kw) => (
                      <tr key={kw.id} className="hover:bg-slate-50/70 transition">
                        <td className="px-4 py-3 font-bold text-slate-900">{kw.keyword_text}</td>
                        <td className="px-4 py-3">
                          <span className="font-mono text-[10px] px-2 py-0.5 rounded bg-slate-100 text-slate-700 font-bold">
                            {kw.match_type}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-slate-600 text-[11px]">
                          {kw.ad_group_name} • {kw.campaign_name}
                        </td>
                        <td className="px-4 py-3 text-right font-bold text-indigo-600">{kw.quality_score}/10</td>
                        <td className="px-4 py-3 text-right font-bold text-slate-800">${Number(kw.cpc_bid).toFixed(2)}</td>
                        <td className="px-4 py-3 text-right text-slate-600">{kw.clicks?.toLocaleString()}</td>
                        <td className="px-4 py-3 text-right font-bold text-emerald-600">{kw.conversions}</td>
                        <td className="px-4 py-3">
                          <button
                            onClick={() => handleToggleKeywordStatus(kw)}
                            className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                              kw.status === 'ENABLED'
                                ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                                : 'bg-slate-100 text-slate-600 border-slate-200'
                            }`}
                          >
                            {kw.status}
                          </button>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button
                            onClick={() => handleDeleteKeyword(kw)}
                            className="p-1 text-slate-400 hover:text-red-600 rounded"
                            title="Delete keyword"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    )))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Sub-tab 4: Mutation Audit Logs */}
          {adsSubTab === 'audit' && (
            <div className="bg-white rounded-xl border border-slate-200 overflow-hidden shadow-xs">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 border-b border-slate-200 text-slate-500 font-bold uppercase tracking-wider text-[10px]">
                  <tr>
                    <th className="px-4 py-3">Operation & Resource</th>
                    <th className="px-4 py-3">Target Name</th>
                    <th className="px-4 py-3">Summary</th>
                    <th className="px-4 py-3">User</th>
                    <th className="px-4 py-3 text-right">Status & Timestamp</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(adsData?.audit_logs || []).map((log) => (
                    <tr key={log.id} className="hover:bg-slate-50/70 transition">
                      <td className="px-4 py-3 font-mono font-bold text-amber-700">{log.operation_type}</td>
                      <td className="px-4 py-3 font-bold text-slate-900">{log.resource_name}</td>
                      <td className="px-4 py-3 text-slate-600 text-[11px] max-w-sm">{log.summary}</td>
                      <td className="px-4 py-3 text-slate-500 text-[11px]">{log.actor_email || 'System'}</td>
                      <td className="px-4 py-3 text-right">
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-50 text-emerald-800 border border-emerald-200">
                          {log.status}
                        </span>
                        <div className="text-[10px] text-slate-400 mt-0.5">
                          {new Date(log.created_at).toLocaleString()}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* MODALS                                                              */}
      {/* ─────────────────────────────────────────────────────────────────── */}

      {/* Modal: Add or Edit CMS Page */}
      {isCreatePageOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl border border-slate-200 w-full max-w-2xl max-h-[90vh] overflow-y-auto p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-base font-bold text-slate-900">
                {editingPage ? `Edit Page: ${editingPage.title}` : 'Add New Website Page / Article'}
              </h3>
              <button onClick={() => setIsCreatePageOpen(false)} className="p-1 text-slate-400 hover:text-slate-700">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateOrUpdatePage} className="space-y-3.5 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-bold text-slate-700 mb-1">Title</label>
                  <input
                    type="text"
                    value={newPage.title}
                    onChange={(e) => setNewPage({ ...newPage, title: e.target.value })}
                    placeholder="e.g. Corporate Intelligence Platform"
                    className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg focus:ring-1 focus:ring-indigo-500 focus:outline-none"
                    required
                  />
                </div>
                <div>
                  <label className="block font-bold text-slate-700 mb-1">Slug (URL Path Component)</label>
                  <input
                    type="text"
                    value={newPage.slug}
                    onChange={(e) => setNewPage({ ...newPage, slug: e.target.value })}
                    placeholder="corporate-intelligence-platform"
                    className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-mono focus:ring-1 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div>
                  <label className="block font-bold text-slate-700 mb-1">Page ID</label>
                  <input
                    type="text"
                    value={newPage.page_id}
                    onChange={(e) => setNewPage({ ...newPage, page_id: e.target.value })}
                    placeholder="PAGE-SOLUTIONS-001"
                    className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-mono focus:ring-1 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block font-bold text-slate-700 mb-1">Page Type</label>
                  <select
                    value={newPage.page_type}
                    onChange={(e) => setNewPage({ ...newPage, page_type: e.target.value })}
                    className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-medium text-slate-700"
                  >
                    <option value="PAGE">Web Page</option>
                    <option value="ARTICLE">Blog Article</option>
                    <option value="LANDING">Landing Page</option>
                  </select>
                </div>
                <div>
                  <label className="block font-bold text-slate-700 mb-1">Status</label>
                  <select
                    value={newPage.status}
                    onChange={(e) => setNewPage({ ...newPage, status: e.target.value })}
                    className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-medium text-slate-700"
                  >
                    <option value="PUBLISHED">Published</option>
                    <option value="DRAFT">Draft</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-bold text-slate-700 mb-1">Page Path</label>
                  <input
                    type="text"
                    value={newPage.page_path}
                    onChange={(e) => setNewPage({ ...newPage, page_path: e.target.value })}
                    placeholder="/solutions/corporate-intelligence"
                    className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-mono focus:ring-1 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block font-bold text-slate-700 mb-1">GA Measurement ID for Page</label>
                  <input
                    type="text"
                    value={newPage.ga_page_id}
                    onChange={(e) => setNewPage({ ...newPage, ga_page_id: e.target.value })}
                    placeholder="G-MKTINTEL01"
                    className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-mono focus:ring-1 focus:ring-indigo-500 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block font-bold text-slate-700 mb-1">Summary / Excerpt</label>
                <textarea
                  rows="2"
                  value={newPage.summary}
                  onChange={(e) => setNewPage({ ...newPage, summary: e.target.value })}
                  placeholder="Short description of this page..."
                  className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg focus:ring-1 focus:ring-indigo-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block font-bold text-slate-700 mb-1">Page Content (Markdown / HTML)</label>
                <textarea
                  rows="5"
                  value={newPage.content}
                  onChange={(e) => setNewPage({ ...newPage, content: e.target.value })}
                  placeholder="# Page Content&#10;&#10;Write page content here..."
                  className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-mono text-xs focus:ring-1 focus:ring-indigo-500 focus:outline-none"
                />
              </div>

              <div className="pt-2 border-t border-slate-100 flex items-center justify-between">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={newPage.include_in_sitemap}
                    onChange={(e) => setNewPage({ ...newPage, include_in_sitemap: e.target.checked })}
                    className="rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <span className="font-medium text-slate-700">Include in XML Sitemap</span>
                </label>

                <div className="flex items-center gap-2">
                  <span className="text-slate-500 font-medium">Priority:</span>
                  <input
                    type="number"
                    step="0.1"
                    min="0.1"
                    max="1.0"
                    value={newPage.sitemap_priority}
                    onChange={(e) => setNewPage({ ...newPage, sitemap_priority: e.target.value })}
                    className="w-16 px-2 py-1 bg-slate-50 border border-slate-200 rounded text-center font-bold"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsCreatePageOpen(false)}
                  className="px-4 py-2 border border-slate-200 rounded-lg font-bold text-slate-700 hover:bg-slate-50 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creatingPage}
                  className="px-5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-bold transition disabled:opacity-50"
                >
                  {creatingPage ? 'Saving...' : editingPage ? 'Update Page' : 'Save Page'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Sitemap XML Inspector */}
      {isSitemapModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl border border-slate-200 w-full max-w-3xl max-h-[85vh] overflow-hidden p-6 shadow-xl flex flex-col space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h3 className="text-base font-bold text-slate-900">Live XML Sitemap Preview</h3>
                <p className="text-xs text-slate-500">
                  Direct generated sitemap from published Market Intel CMS pages ({sitemapXmlData?.url_count || 0} URLs).
                </p>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => copyToClipboard(sitemapXmlData?.xml, 'Sitemap XML copied!')}
                  className="inline-flex items-center gap-1.5 px-3 py-1 bg-slate-900 text-white rounded-md text-xs font-bold"
                >
                  <Copy className="w-3.5 h-3.5" />
                  Copy XML
                </button>
                <button onClick={() => setIsSitemapModalOpen(false)} className="p-1 text-slate-400 hover:text-slate-700">
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-auto bg-slate-950 text-emerald-400 font-mono text-[11px] p-4 rounded-xl border border-slate-800">
              <pre className="whitespace-pre">
                {loadingSitemapXml ? 'Generating live XML sitemap...' : sitemapXmlData?.xml || 'No sitemap data'}
              </pre>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Record Analytics Stat */}
      {isRecordStatOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl border border-slate-200 w-full max-w-md p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-900">Record Live Website Page Statistic</h3>
              <button onClick={() => setIsRecordStatOpen(false)} className="p-1 text-slate-400 hover:text-slate-700">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleRecordAnalyticsStat} className="space-y-3 text-xs">
              <div>
                <label className="block font-bold text-slate-700 mb-1">Page ID</label>
                <input
                  type="text"
                  value={newStat.page_id}
                  onChange={(e) => setNewStat({ ...newStat, page_id: e.target.value })}
                  className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-mono"
                  required
                />
              </div>

              <div>
                <label className="block font-bold text-slate-700 mb-1">Page Title & Path</label>
                <input
                  type="text"
                  value={newStat.page_title}
                  onChange={(e) => setNewStat({ ...newStat, page_title: e.target.value })}
                  className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg mb-2"
                  placeholder="Page title"
                  required
                />
                <input
                  type="text"
                  value={newStat.page_path}
                  onChange={(e) => setNewStat({ ...newStat, page_path: e.target.value })}
                  className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-mono"
                  placeholder="/solutions/prospect-database"
                  required
                />
              </div>

              <div className="grid grid-cols-3 gap-2">
                <div>
                  <label className="block font-bold text-slate-700 mb-1">Views</label>
                  <input
                    type="number"
                    value={newStat.page_views}
                    onChange={(e) => setNewStat({ ...newStat, page_views: parseInt(e.target.value) || 1 })}
                    className="w-full px-2 py-1 bg-slate-50 border border-slate-200 rounded"
                  />
                </div>
                <div>
                  <label className="block font-bold text-slate-700 mb-1">Visitors</label>
                  <input
                    type="number"
                    value={newStat.unique_visitors}
                    onChange={(e) => setNewStat({ ...newStat, unique_visitors: parseInt(e.target.value) || 1 })}
                    className="w-full px-2 py-1 bg-slate-50 border border-slate-200 rounded"
                  />
                </div>
                <div>
                  <label className="block font-bold text-slate-700 mb-1">Sessions</label>
                  <input
                    type="number"
                    value={newStat.sessions}
                    onChange={(e) => setNewStat({ ...newStat, sessions: parseInt(e.target.value) || 1 })}
                    className="w-full px-2 py-1 bg-slate-50 border border-slate-200 rounded"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsRecordStatOpen(false)}
                  className="px-3 py-1.5 border border-slate-200 rounded-lg text-slate-700 font-bold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={recordingStat}
                  className="px-4 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg font-bold"
                >
                  {recordingStat ? 'Recording...' : 'Record Stat'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Register GSC Domain */}
      {isRegisterDomainOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl border border-slate-200 w-full max-w-md p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-900">Register Search Console Domain</h3>
              <button onClick={() => setIsRegisterDomainOpen(false)} className="p-1 text-slate-400 hover:text-slate-700">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleRegisterDomain} className="space-y-3.5 text-xs">
              <div>
                <label className="block font-bold text-slate-700 mb-1">Domain Name or URL</label>
                <input
                  type="text"
                  placeholder="e.g. marketintel.hikasimat.com"
                  value={newDomain.domain}
                  onChange={(e) => setNewDomain({ ...newDomain, domain: e.target.value })}
                  className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg focus:ring-1 focus:ring-emerald-500 focus:outline-none"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-bold text-slate-700 mb-1">Property Type</label>
                  <select
                    value={newDomain.property_type}
                    onChange={(e) => setNewDomain({ ...newDomain, property_type: e.target.value })}
                    className="w-full px-2.5 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-medium text-slate-700"
                  >
                    <option value="DOMAIN">Domain Property</option>
                    <option value="URL_PREFIX">URL Prefix</option>
                  </select>
                </div>
                <div>
                  <label className="block font-bold text-slate-700 mb-1">Verification Method</label>
                  <select
                    value={newDomain.verification_method}
                    onChange={(e) => setNewDomain({ ...newDomain, verification_method: e.target.value })}
                    className="w-full px-2.5 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-medium text-slate-700"
                  >
                    <option value="DNS_TXT">DNS TXT Record</option>
                    <option value="HTML_META">HTML Meta Tag</option>
                    <option value="HTML_FILE">HTML File</option>
                  </select>
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsRegisterDomainOpen(false)}
                  className="px-3 py-1.5 border border-slate-200 rounded-lg text-slate-700 font-bold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={registeringDomain}
                  className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg font-bold disabled:opacity-50"
                >
                  {registeringDomain ? 'Registering...' : 'Register Domain'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Submit GSC Sitemap */}
      {isSubmitSitemapOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl border border-slate-200 w-full max-w-md p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-900">Submit Sitemap to Google</h3>
              <button onClick={() => setIsSubmitSitemapOpen(false)} className="p-1 text-slate-400 hover:text-slate-700">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSubmitSitemap} className="space-y-3.5 text-xs">
              <div>
                <label className="block font-bold text-slate-700 mb-1">Sitemap URL</label>
                <input
                  type="url"
                  value={sitemapUrlInput}
                  onChange={(e) => setSitemapUrlInput(e.target.value)}
                  className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-mono focus:ring-1 focus:ring-blue-500 focus:outline-none"
                  required
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsSubmitSitemapOpen(false)}
                  className="px-3 py-1.5 border border-slate-200 rounded-lg text-slate-700 font-bold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submittingSitemap}
                  className="px-4 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-bold disabled:opacity-50"
                >
                  {submittingSitemap ? 'Submitting...' : 'Submit Sitemap'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Edit Campaign Daily Budget */}
      {budgetModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl border border-slate-200 w-full max-w-sm p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-900">Update Campaign Budget</h3>
              <button onClick={() => setBudgetModalOpen(false)} className="p-1 text-slate-400 hover:text-slate-700">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSaveCampaignBudget} className="space-y-3 text-xs">
              <p className="text-slate-600 font-semibold">{campaignForBudget?.name}</p>

              <div>
                <label className="block font-bold text-slate-700 mb-1">New Daily Budget ($/day)</label>
                <input
                  type="number"
                  step="0.01"
                  min="1"
                  value={newBudgetVal}
                  onChange={(e) => setNewBudgetVal(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-base font-bold text-slate-900 focus:ring-1 focus:ring-amber-500 focus:outline-none"
                  required
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setBudgetModalOpen(false)}
                  className="px-3 py-1.5 border border-slate-200 rounded-lg text-slate-700 font-bold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={updatingBudget}
                  className="px-4 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg font-bold disabled:opacity-50"
                >
                  {updatingBudget ? 'Updating...' : 'Save Budget'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Create Campaign */}
      {isCreateCampaignOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl border border-slate-200 w-full max-w-md p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-900">Create Google Ads Campaign</h3>
              <button onClick={() => setIsCreateCampaignOpen(false)} className="p-1 text-slate-400 hover:text-slate-700">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateCampaign} className="space-y-3 text-xs">
              <div>
                <label className="block font-bold text-slate-700 mb-1">Campaign Name</label>
                <input
                  type="text"
                  value={newCampaign.name}
                  onChange={(e) => setNewCampaign({ ...newCampaign, name: e.target.value })}
                  placeholder="e.g. Enterprise Search Q1"
                  className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-bold text-slate-700 mb-1">Channel Type</label>
                  <select
                    value={newCampaign.channel_type}
                    onChange={(e) => setNewCampaign({ ...newCampaign, channel_type: e.target.value })}
                    className="w-full px-2.5 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-medium"
                  >
                    <option value="SEARCH">Search</option>
                    <option value="PERFORMANCE_MAX">Performance Max</option>
                    <option value="DISPLAY">Display</option>
                    <option value="VIDEO">Video / YouTube</option>
                    <option value="DEMAND_GEN">Demand Gen</option>
                  </select>
                </div>

                <div>
                  <label className="block font-bold text-slate-700 mb-1">Daily Budget ($)</label>
                  <input
                    type="number"
                    step="0.01"
                    min="1"
                    value={newCampaign.daily_budget}
                    onChange={(e) => setNewCampaign({ ...newCampaign, daily_budget: e.target.value })}
                    className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-bold"
                    required
                  />
                </div>
              </div>

              <div>
                <label className="block font-bold text-slate-700 mb-1">Bidding Strategy</label>
                <select
                  value={newCampaign.bidding_strategy}
                  onChange={(e) => setNewCampaign({ ...newCampaign, bidding_strategy: e.target.value })}
                  className="w-full px-2.5 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-medium"
                >
                  <option value="MAXIMIZE_CONVERSIONS">Maximize Conversions</option>
                  <option value="MAXIMIZE_CLICKS">Maximize Clicks</option>
                  <option value="TARGET_CPA">Target CPA</option>
                  <option value="TARGET_ROAS">Target ROAS</option>
                  <option value="MANUAL_CPC">Manual CPC</option>
                </select>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsCreateCampaignOpen(false)}
                  className="px-3 py-1.5 border border-slate-200 rounded-lg text-slate-700 font-bold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creatingCampaign}
                  className="px-4 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg font-bold disabled:opacity-50"
                >
                  {creatingCampaign ? 'Creating...' : 'Create Campaign'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Google Ads Account Settings */}
      {isAdsAccountConfigOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl border border-slate-200 w-full max-w-md p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-900">Google Ads Account Configuration</h3>
              <button onClick={() => setIsAdsAccountConfigOpen(false)} className="p-1 text-slate-400 hover:text-slate-700">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSaveAdsAccountConfig} className="space-y-3 text-xs">
              <div>
                <label className="block font-bold text-slate-700 mb-1">Customer ID</label>
                <input
                  type="text"
                  value={adsAccountConfig.customer_id}
                  onChange={(e) => setAdsAccountConfig({ ...adsAccountConfig, customer_id: e.target.value })}
                  placeholder="742-891-3045"
                  className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-mono font-bold"
                  required
                />
              </div>

              <div>
                <label className="block font-bold text-slate-700 mb-1">Account Descriptive Name</label>
                <input
                  type="text"
                  value={adsAccountConfig.account_name}
                  onChange={(e) => setAdsAccountConfig({ ...adsAccountConfig, account_name: e.target.value })}
                  placeholder="Market Intel Growth Ads"
                  className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-bold text-slate-700 mb-1">Currency</label>
                  <input
                    type="text"
                    value={adsAccountConfig.currency_code}
                    onChange={(e) => setAdsAccountConfig({ ...adsAccountConfig, currency_code: e.target.value.toUpperCase() })}
                    className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-bold"
                  />
                </div>
                <div>
                  <label className="block font-bold text-slate-700 mb-1">Time Zone</label>
                  <input
                    type="text"
                    value={adsAccountConfig.time_zone}
                    onChange={(e) => setAdsAccountConfig({ ...adsAccountConfig, time_zone: e.target.value })}
                    className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsAdsAccountConfigOpen(false)}
                  className="px-3 py-1.5 border border-slate-200 rounded-lg text-slate-700 font-bold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={savingAdsAccount}
                  className="px-4 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg font-bold disabled:opacity-50"
                >
                  {savingAdsAccount ? 'Saving...' : 'Save Settings'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Create Ad Group */}
      {isCreateAdGroupOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl border border-slate-200 w-full max-w-md p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-900">Add New Ad Group</h3>
              <button onClick={() => setIsCreateAdGroupOpen(false)} className="p-1 text-slate-400 hover:text-slate-700">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateAdGroup} className="space-y-3 text-xs">
              <div>
                <label className="block font-bold text-slate-700 mb-1">Campaign</label>
                <select
                  value={newAdGroup.campaign_id}
                  onChange={(e) => setNewAdGroup({ ...newAdGroup, campaign_id: e.target.value })}
                  className="w-full px-2.5 py-1.5 bg-slate-50 border border-slate-200 rounded-lg"
                  required
                >
                  <option value="">Select a Campaign</option>
                  {(adsData?.campaigns || []).map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block font-bold text-slate-700 mb-1">Ad Group Name</label>
                <input
                  type="text"
                  value={newAdGroup.name}
                  onChange={(e) => setNewAdGroup({ ...newAdGroup, name: e.target.value })}
                  placeholder="e.g. Executive Outreach & M&A Data"
                  className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg"
                  required
                />
              </div>

              <div>
                <label className="block font-bold text-slate-700 mb-1">Default Max CPC Bid ($)</label>
                <input
                  type="number"
                  step="0.05"
                  min="0.1"
                  value={newAdGroup.cpc_bid}
                  onChange={(e) => setNewAdGroup({ ...newAdGroup, cpc_bid: e.target.value })}
                  className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-bold"
                  required
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsCreateAdGroupOpen(false)}
                  className="px-3 py-1.5 border border-slate-200 rounded-lg text-slate-700 font-bold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creatingAdGroup}
                  className="px-4 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg font-bold disabled:opacity-50"
                >
                  {creatingAdGroup ? 'Creating...' : 'Create Ad Group'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Create Keyword */}
      {isCreateKeywordOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-xs p-4">
          <div className="bg-white rounded-2xl border border-slate-200 w-full max-w-md p-6 shadow-xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-900">Add Keyword Criterion</h3>
              <button onClick={() => setIsCreateKeywordOpen(false)} className="p-1 text-slate-400 hover:text-slate-700">
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleCreateKeyword} className="space-y-3 text-xs">
              <div>
                <label className="block font-bold text-slate-700 mb-1">Target Ad Group</label>
                <select
                  value={newKeyword.ad_group_id}
                  onChange={(e) => setNewKeyword({ ...newKeyword, ad_group_id: e.target.value })}
                  className="w-full px-2.5 py-1.5 bg-slate-50 border border-slate-200 rounded-lg"
                  required
                >
                  <option value="">Select Ad Group</option>
                  {(adsData?.ad_groups || []).map((ag) => (
                    <option key={ag.id} value={ag.id}>
                      {ag.name} ({ag.campaign_name})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block font-bold text-slate-700 mb-1">Keyword Text</label>
                <input
                  type="text"
                  value={newKeyword.keyword_text}
                  onChange={(e) => setNewKeyword({ ...newKeyword, keyword_text: e.target.value })}
                  placeholder="e.g. corporate database software"
                  className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-bold text-slate-700 mb-1">Match Type</label>
                  <select
                    value={newKeyword.match_type}
                    onChange={(e) => setNewKeyword({ ...newKeyword, match_type: e.target.value })}
                    className="w-full px-2.5 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-medium"
                  >
                    <option value="EXACT">Exact Match</option>
                    <option value="PHRASE">Phrase Match</option>
                    <option value="BROAD">Broad Match</option>
                  </select>
                </div>
                <div>
                  <label className="block font-bold text-slate-700 mb-1">CPC Bid ($)</label>
                  <input
                    type="number"
                    step="0.05"
                    value={newKeyword.cpc_bid}
                    onChange={(e) => setNewKeyword({ ...newKeyword, cpc_bid: e.target.value })}
                    className="w-full px-3 py-1.5 bg-slate-50 border border-slate-200 rounded-lg font-bold"
                  />
                </div>
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsCreateKeywordOpen(false)}
                  className="px-3 py-1.5 border border-slate-200 rounded-lg text-slate-700 font-bold"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={creatingKeyword}
                  className="px-4 py-1.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg font-bold disabled:opacity-50"
                >
                  {creatingKeyword ? 'Adding...' : 'Add Keyword'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default CmsPage;
