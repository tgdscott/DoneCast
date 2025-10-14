"use client"

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  Headphones,
  Plus,
  Edit,
  Trash2,
  Share2,
  Play,
  Download,
  Users,
  LogOut,
  Bell,
  Search,
  Target,
  Zap,
  FileText,
  Music,
  BarChart3,
  Loader2,
  Podcast,
  ArrowLeft,
  Rss,
  AlertTriangle,
  Settings as SettingsIcon,
  DollarSign,
  Globe2,
} from "lucide-react";
import { useState, useEffect, useMemo, useCallback, useRef } from "react";

import { makeApi, coerceArray } from "@/lib/apiClient";
import { useAuth } from "@/AuthContext";
import { useToast } from "@/hooks/use-toast";
import Logo from "@/components/Logo.jsx";
import Joyride, { STATUS } from "react-joyride";
import { useResolvedTimezone } from "@/hooks/useResolvedTimezone";
import { formatInTimezone } from "@/lib/timezone";

import TemplateEditor from "@/components/dashboard/TemplateEditor";
import PodcastCreator from "@/components/dashboard/PodcastCreator";
import EpisodeStartOptions from "@/components/dashboard/EpisodeStartOptions";
import PreUploadManager from "@/components/dashboard/PreUploadManager";
import MediaLibrary from "@/components/dashboard/MediaLibrary";
import EpisodeHistory from "@/components/dashboard/EpisodeHistory";
import PodcastManager from "@/components/dashboard/PodcastManager";
import PodcastAnalytics from "@/components/dashboard/PodcastAnalytics";
import RssImporter from "@/components/dashboard/RssImporter";
import DevTools from "@/components/dashboard/DevTools";
import TemplateWizard from "@/components/dashboard/TemplateWizard";
import Settings from "@/components/dashboard/Settings";
import TemplateManager from "@/components/dashboard/TemplateManager";
import BillingPage from "@/components/dashboard/BillingPage";
import Recorder from "@/components/quicktools/Recorder";
import WebsiteBuilder from "@/components/dashboard/WebsiteBuilder.jsx";
import AIAssistant from "@/components/assistant/AIAssistant";

const isAdmin = (u) => !!(u && (u.is_admin || u.role === 'admin'));
const DASHBOARD_TOUR_STORAGE_KEY = 'ppp_dashboard_tour_completed';

function formatRelative(iso) {
  if(!iso) return '—';
  try {
    const d = new Date(iso);
    const diffMs = Date.now() - d.getTime();
    const sec = Math.floor(diffMs/1000);
    if(sec < 60) return 'just now';
    const min = Math.floor(sec/60);
    if(min < 60) return `${min}m ago`;
    const hr = Math.floor(min/60);
    if(hr < 24) return `${hr}h ago`;
    const day = Math.floor(hr/24);
    if(day < 30) return `${day}d ago`;
    const mo = Math.floor(day/30);
    if(mo < 12) return `${mo}mo ago`;
    const yr = Math.floor(mo/12);
    return `${yr}y ago`;
  } catch { return '—'; }
}

function formatAssemblyStatus(status) {
  if(!status) return '—';
  switch(status) {
    case 'success': return 'Success';
    case 'error': return 'Error';
    case 'pending': return 'In Progress';
    default: return status.charAt(0).toUpperCase()+status.slice(1);
  }
}

function formatShort(iso, timezone) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    return formatInTimezone(
      d,
      sameDay
        ? { hour: '2-digit', minute: '2-digit' }
        : { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' },
      timezone
    );
  } catch {
    return '';
  }
}

export default function PodcastPlusDashboard() {
  const { token, logout, user: authUser } = useAuth();
  const { toast } = useToast();
  const resolvedTimezone = useResolvedTimezone(authUser?.timezone);
  const [user, setUser] = useState(null); // local alias for convenience
  const [templates, setTemplates] = useState([]);
  const [podcasts, setPodcasts] = useState([]);
  const [stats, setStats] = useState(null);
  const [statsError, setStatsError] = useState(null);
  const [notifications, setNotifications] = useState([]);
  const [showNotifPanel, setShowNotifPanel] = useState(false);
  const [currentView, setCurrentView] = useState(() => {
    try { if(localStorage.getItem('ppp_post_checkout')==='1') return 'billing'; } catch {}
    return 'dashboard';
  });
  const [selectedTemplateId, setSelectedTemplateId] = useState(null);
  const [selectedPodcastId, setSelectedPodcastId] = useState(null);
  const [preselectedMainFilename, setPreselectedMainFilename] = useState(null);
  const [preselectedTranscriptReady, setPreselectedTranscriptReady] = useState(false);
  const [shouldRunTour, setShouldRunTour] = useState(false);
  const [creatorMode, setCreatorMode] = useState('standard');
  const [preuploadItems, setPreuploadItems] = useState([]);
  const [preuploadLoading, setPreuploadLoading] = useState(false);
  const [preuploadError, setPreuploadError] = useState(null);
  const preuploadFetchedOnceRef = useRef(false);
  const previousPreuploadContextRef = useRef({ view: currentView, mode: creatorMode });

  const resetPreuploadFetchedFlag = useCallback(() => {
    preuploadFetchedOnceRef.current = false;
  }, []);

  const proEligibleTiers = useMemo(() => new Set(['pro', 'enterprise', 'business', 'team', 'agency']), []);
  const normalizedTier = (user?.tier || '').toLowerCase();
  const canManageCustomDomain = proEligibleTiers.has(normalizedTier);

  const tourSteps = useMemo(() => [
    {
      target: '[data-tour-id="dashboard-new-episode"]',
      title: 'New Episode Button',
      content: 'This is where the magic happens. Hit this button to start making your episode either from a show you\'ve already recorded, or one you want to record now.',
      disableBeacon: true,
    },
    {
      target: '[data-tour-id="dashboard-quicktool-podcasts"]',
      title: 'Podcasts',
      content: 'If you want to change anything about the structure of your show, like the name, cover, or description, that\'s here.',
    },
    {
      target: '[data-tour-id="dashboard-quicktool-templates"]',
      title: 'Templates',
      content: 'This is the blueprint for your show - the stuff that happens every episode. We made one for you already, but you can edit it or make others.',
    },
    {
      target: '[data-tour-id="dashboard-quicktool-media"]',
      title: 'Media',
      content: 'Any sound files that you use for your show are uploaded and stored here.',
    },
    {
      target: '[data-tour-id="dashboard-quicktool-episodes"]',
      title: 'Episodes',
      content: 'All the details about your individual episodes here so you can edit them as you need to.',
    },
    {
      target: '[data-tour-id="dashboard-quicktool-subscription"]',
      title: 'Subscription',
      content: 'This is where you can choose and edit your plan here so you get the perfect one for you.',
    },
    {
      target: '[data-tour-id="dashboard-quicktool-settings"]',
      title: 'Settings',
      content: 'If it doesn\'t fit in one of the categories above, look for it here.',
    },
  ], []);

  const refreshPreuploads = useCallback(async () => {
    if (!token) return [];
    setPreuploadLoading(true);
    try {
      const api = makeApi(token);
      const data = await api.get('/api/media/main-content');
      if (Array.isArray(data)) {
        setPreuploadItems(data);
      } else {
        setPreuploadItems([]);
      }
      setPreuploadError(null);
      return data;
    } catch (err) {
      const status = err?.status;
      let msg = 'Failed to load your uploaded main-content audio.';
      if (status === 401) {
        msg = 'Your session expired. Please sign in again to load your uploads.';
      } else if (status === 403) {
        msg = 'You are not allowed to view uploads for this account.';
      } else if (status === 404) {
        // In some setups this route might be gated; treat as empty rather than fatal
        msg = 'No uploads found yet.';
      } else if (typeof err?.message === 'string') {
        const em = err.message.toLowerCase();
        if (em.includes('failed to fetch') || em.includes('network') || em.includes('cors')) {
          msg = 'Network issue loading your uploads. Check your connection or try again.';
        }
      }
      setPreuploadError(msg);
      setPreuploadItems([]);
      return [];
    } finally {
      setPreuploadLoading(false);
      preuploadFetchedOnceRef.current = true;
    }
  }, [token]);

  const requestPreuploadRefresh = useCallback(async () => {
    resetPreuploadFetchedFlag();
    return refreshPreuploads();
  }, [resetPreuploadFetchedFlag, refreshPreuploads]);

  const handleTourCallback = (data) => {
    const { status } = data;
    if ([STATUS.FINISHED, STATUS.SKIPPED].includes(status)) {
      try { localStorage.setItem(DASHBOARD_TOUR_STORAGE_KEY, '1'); } catch {}
      setShouldRunTour(false);
    }
  };

  const fetchData = async () => {
    if (!token) return;
    try {
      setStatsError(null);
      const api = makeApi(token);
      // Use allSettled so that missing optional endpoints (404) don't cause
      // the whole fetch to reject and force a logout. Only treat 401 as fatal.
      const results = await Promise.allSettled([
        api.get('/api/templates/'),
        api.get('/api/podcasts/'),
        api.get('/api/dashboard/stats'),
      ]);

      const [templatesRes, podcastsRes, statsRes] = results;

      // Templates
      if (templatesRes.status === 'fulfilled') {
        const templatesList = coerceArray(templatesRes.value);
        setTemplates(templatesList);
      } else {
        const reason = templatesRes.reason || {};
        if (reason.status === 401) {
          // Authorization failure -> force logout
          console.warn('Templates fetch unauthorized, logging out', reason);
          logout();
          return;
        }
        console.warn('Failed to load templates (non-fatal):', reason);
        setTemplates([]);
      }

      // Podcasts
      if (podcastsRes.status === 'fulfilled') {
        const podcastList = coerceArray(podcastsRes.value);
        setPodcasts(podcastList);
      } else {
        const reason = podcastsRes.reason || {};
        if (reason.status === 401) {
          console.warn('Podcasts fetch unauthorized, logging out', reason);
          logout();
          return;
        }
        console.warn('Failed to load podcasts (non-fatal):', reason);
        setPodcasts([]);
      }

      // Stats (optional)
      if (statsRes.status === 'fulfilled') {
        setStats(statsRes.value);
      } else {
        const reason = statsRes.reason || {};
        if (reason.status === 401) {
          console.warn('Stats fetch unauthorized; continuing without stats', reason);
          setStatsError('You are not authorized to view stats.');
          setStats(null);
        } else {
          // Non-fatal: show a gentle UI message
          console.warn('Failed to load stats (non-fatal):', reason);
          setStatsError('Failed to load stats.');
          setStats(null);
        }
      }
    } catch (err) {
      // Unexpected error: don't immediately force logout unless it's a 401
      console.error("Unexpected error fetching dashboard data:", err);
      if (err && err.status === 401) {
        logout();
      } else {
        setStatsError('Failed to load dashboard data.');
      }
    }
  };

  // Initial load + token change: fetch other data (user already fetched by AuthContext)
  useEffect(() => { if (token) { fetchData(); } }, [token, logout]);
  useEffect(() => {
    if (!token) return;
    if (currentView === 'episodeStart' || currentView === 'preuploadUpload') {
      requestPreuploadRefresh();
    }
  }, [token, currentView, requestPreuploadRefresh]);
  useEffect(() => {
    if (!token) return;
    if (
      currentView === 'createEpisode' &&
      creatorMode === 'preuploaded' &&
      !preuploadLoading &&
      preuploadItems.length === 0 &&
      !preuploadFetchedOnceRef.current
    ) {
      refreshPreuploads();
    }
  }, [token, currentView, creatorMode, preuploadLoading, preuploadItems.length, refreshPreuploads]);

  useEffect(() => {
    const previous = previousPreuploadContextRef.current;
    const wasInPreupload =
      previous.view === 'createEpisode' && previous.mode === 'preuploaded';
    const isInPreupload =
      currentView === 'createEpisode' && creatorMode === 'preuploaded';

    if (wasInPreupload && !isInPreupload) {
      resetPreuploadFetchedFlag();
    }

    previousPreuploadContextRef.current = { view: currentView, mode: creatorMode };
  }, [currentView, creatorMode, resetPreuploadFetchedFlag]);
  // When navigating back to the Dashboard view, refresh data so cards reflect latest state
  useEffect(() => {
    if (token && currentView === 'dashboard') {
      fetchData();
    }
  }, [token, currentView]);
  // Fetch notifications
  useEffect(() => {
    if(!token) return;
    let cancelled = false;
    const load = async () => {
      try {
        const api = makeApi(token);
        const r = await api.get('/api/notifications/');
        if(!cancelled && Array.isArray(r)) {
          setNotifications(curr => {
            const map = new Map((curr||[]).map(n=>[n.id,n]));
            const merged = r.map(n => {
              const existing = map.get(n.id);
              if(existing && existing.read_at) return { ...n, read_at: existing.read_at };
              return n;
            });
            for(const n of (curr||[])) if(!merged.find(m=>m.id===n.id)) merged.push(n);
            return merged.sort((a,b)=> new Date(b.created_at||0) - new Date(a.created_at||0));
          });
        }
      } catch {}
    };
    load();
  }, [token]);
  // BroadcastChannel listener for checkout success -> refetch notifications
  useEffect(() => {
    let bc;
    try {
  bc = new BroadcastChannel('ppp_billing');
      bc.onmessage = (e) => {
        if(e?.data?.type === 'checkout_success') {
          // Refresh notifications & maybe toast
          (async ()=>{
            try {
              const api = makeApi(token);
              const d = await api.get('/api/notifications/');
              setNotifications(curr=>{
            const map = new Map((curr||[]).map(n=>[n.id,n]));
                const merged = (Array.isArray(d)? d: []).map(n=>{ const ex = map.get(n.id); if(ex && ex.read_at) return { ...n, read_at: ex.read_at }; return n; });
                for(const n of (curr||[])) if(!merged.find(m=>m.id===n.id)) merged.push(n);
                return merged.sort((a,b)=> new Date(b.created_at||0) - new Date(a.created_at||0));
              });
            } catch {}
          })();
        } else if(e?.data?.type === 'subscription_updated') {
          // Refetch subscription in case Billing page not mounted & show toast if not already billing view
          if(currentView !== 'billing') {
            toast({ title:'Subscription Updated', description:`Plan changed to ${e.data.payload?.plan_key}`, duration:5000 });
          }
        }
      };
    } catch {}
    const storageHandler = (ev) => {
      if(ev.key === 'ppp_last_checkout') {
        (async ()=>{
          try {
            const api = makeApi(token);
            const d = await api.get('/api/notifications/');
            setNotifications(curr=>{
              const map = new Map((curr||[]).map(n=>[n.id,n]));
              const merged = (Array.isArray(d)? d: []).map(n=>{ const ex = map.get(n.id); if(ex && ex.read_at) return { ...n, read_at: ex.read_at }; return n; });
              for(const n of (curr||[])) if(!merged.find(m=>m.id===n.id)) merged.push(n);
              return merged.sort((a,b)=> new Date(b.created_at||0) - new Date(a.created_at||0));
            });
          } catch {}
        })();
      }
    };
    window.addEventListener('storage', storageHandler);
    return () => { try { bc && bc.close(); } catch{} window.removeEventListener('storage', storageHandler); };
  }, [token, currentView, toast]);
  // Sync local user with auth context
  useEffect(() => { setUser(authUser); }, [authUser]);
  // Clear post-checkout flag once we've mounted and possibly navigated
  useEffect(() => { if(currentView==='billing') { try { localStorage.removeItem('ppp_post_checkout'); } catch {} } }, [currentView]);

  const handleEditTemplate = (templateId) => {
    setSelectedTemplateId(templateId);
    setCurrentView('editTemplate');
  };

  const handleBackToDashboard = () => {
    setSelectedTemplateId(null);
    setCreatorMode('standard');
    setCurrentView('dashboard');
    // Ensure counts (podcasts/templates/stats) are fresh when returning
    try { fetchData(); } catch {}
  };
  
  const handleBackToTemplateManager = () => {
      setSelectedTemplateId(null);
      setCurrentView('templateManager');
  }

  const handleDeleteTemplate = async (templateId) => {
    if (!window.confirm("Are you sure you want to delete this template? This cannot be undone.")) return;
  try {
    const api = makeApi(token);
    await api.del(`/api/templates/${templateId}`);
    toast({ title: "All done!", description: "Template deleted." });
    fetchData(); 
  } catch (err) {
    const msg = (err && err.message) || '';
    if (msg.toLowerCase().includes('at least one template')){
      toast({ title: "Action needed", description: "Create another template before deleting your last one.", variant: "destructive" });
    } else {
      toast({ title: "Error", description: msg || 'Delete failed', variant: "destructive" });
    }
  }
  };

  const renderCurrentView = () => {
    switch (currentView) {
      case 'recorder':
        return (
          <Recorder
            onBack={handleBackToDashboard}
            token={token}
            onFinish={({ filename, hint, transcriptReady }) => {
              try {
                setPreselectedMainFilename(filename || hint || null);
                setPreselectedTranscriptReady(!!transcriptReady);
              } catch {}
              setCreatorMode('standard');
              setCurrentView('createEpisode');
            }}
          />
        );
      case 'episodeStart': {
        const hasReadyAudio = preuploadItems.some((item) => item?.transcript_ready);
        return (
          <EpisodeStartOptions
            loading={preuploadLoading}
            hasReadyAudio={hasReadyAudio}
            errorMessage={preuploadError || ''}
            onRetry={() => {
              try {
                requestPreuploadRefresh();
              } catch {}
            }}
            onBack={handleBackToDashboard}
            onChooseRecord={() => {
              setCreatorMode('standard');
              setCurrentView('recorder');
            }}
            onChooseLibrary={async () => {
              setCreatorMode('preuploaded');
              setPreselectedMainFilename(null);
              setPreselectedTranscriptReady(false);
              resetPreuploadFetchedFlag();
              if (!preuploadLoading && preuploadItems.length === 0) {
                try { await requestPreuploadRefresh(); } catch {}
              }
              setCurrentView('createEpisode');
            }}
          />
        );
      }
      case 'preuploadUpload':
        return (
          <PreUploadManager
            token={token}
            onBack={() => setCurrentView('episodeStart')}
            onDone={handleBackToDashboard}
            defaultEmail={user?.email || ''}
            onUploaded={requestPreuploadRefresh}
          />
        );
      case 'templateManager':
        return <TemplateManager onBack={handleBackToDashboard} token={token} setCurrentView={setCurrentView} />;
      case 'editTemplate':
        return <TemplateEditor templateId={selectedTemplateId} onBack={handleBackToTemplateManager} token={token} onTemplateSaved={fetchData} />;
      case 'createEpisode':
        return (
          <PodcastCreator
            onBack={handleBackToDashboard}
            token={token}
            templates={templates}
            podcasts={podcasts}
            preselectedMainFilename={preselectedMainFilename}
            preselectedTranscriptReady={preselectedTranscriptReady}
            creatorMode={creatorMode}
            preuploadedItems={preuploadItems}
            preuploadedLoading={preuploadLoading}
            onRefreshPreuploaded={requestPreuploadRefresh}
            preselectedStartStep={creatorMode === 'preuploaded' ? 1 : undefined}
            onRequestUpload={() => {
              setCreatorMode('standard');
              setCurrentView('preuploadUpload');
            }}
            userTimezone={resolvedTimezone}
          />
        );
      case 'mediaLibrary':
        return <MediaLibrary onBack={handleBackToDashboard} token={token} />;
      case 'episodeHistory':
        return <EpisodeHistory onBack={handleBackToDashboard} token={token} />;
      case 'websiteBuilder':
        return (
          <WebsiteBuilder
            token={token}
            podcasts={podcasts}
            onBack={handleBackToDashboard}
            allowCustomDomain={canManageCustomDomain}
          />
        );
      case 'podcastManager':
        return <PodcastManager 
          onBack={handleBackToDashboard} 
          token={token} 
          podcasts={podcasts} 
          setPodcasts={setPodcasts}
          onViewAnalytics={(podcastId) => {
            setSelectedPodcastId(podcastId);
            setCurrentView('analytics');
          }}
        />;
      case 'rssImporter':
        return <RssImporter onBack={handleBackToDashboard} token={token} />;
      case 'devTools':
        return isAdmin(authUser)
          ? <DevTools token={token} />
          : <div className="p-6 text-sm text-red-600">Not authorized.</div>;
      case 'settings':
        return <Settings token={token} />;
      case 'templateWizard':
        return <TemplateWizard user={user} token={token} onBack={() => setCurrentView('templateManager')} onTemplateCreated={() => { fetchData(); setCurrentView('templateManager'); }} />;
      case 'billing':
        return <BillingPage token={token} onBack={() => setCurrentView('dashboard')} />;
      case 'analytics':
        return (
          <PodcastAnalytics 
            podcastId={selectedPodcastId} 
            token={token} 
            onBack={handleBackToDashboard}
          />
        );
      case 'dashboard':
      default: {
        const canCreateEpisode = podcasts.length > 0 && templates.length > 0;
        return (
          <div className="space-y-8">
            {/* Hero / Greeting */}
            <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
              <div>
                <h1 className="text-3xl md:text-4xl font-bold tracking-tight" style={{ color: '#2C3E50' }}>
                  Welcome back
                  {user ? `, ${user.first_name || (user.email ? user.email.split('@')[0] : 'friend')}` : ''}!
                </h1>
                <p className="text-sm md:text-base text-gray-600 mt-1">Quick launch your next episode or jump into a tool.</p>
              </div>
              {/* Layout experiment toggled from the admin dashboard */}
            </div>
            {statsError && (
              <div className="bg-red-100 border border-red-300 text-red-700 rounded p-3 mb-4 text-sm">
                {statsError}
              </div>
            )}
            <div className="grid lg:grid-cols-3 gap-6">
              <div className="lg:col-span-2 space-y-6">
                {/* Create Episode Card */}
                <Card className="shadow-sm border border-gray-200">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-lg">Create Episode</CardTitle>
                    <CardDescription>Create a new episode from your shows & templates.</CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                    <div className="flex items-center gap-6 text-sm">
                      <div className="text-center">
                        <div className="text-[11px] tracking-wide text-gray-500">Shows</div>
                        <div className="font-semibold text-gray-800 mt-0.5">{podcasts.length}</div>
                      </div>
                      <div className="text-center">
                        <div className="text-[11px] tracking-wide text-gray-500">Episodes</div>
                        <div className="font-semibold text-gray-800 mt-0.5">{stats?.total_episodes ?? '–'}</div>
                      </div>
                    </div>
                      <div className="flex flex-col sm:flex-row gap-3 w-full md:w-auto">
                        {canCreateEpisode && (
                          <Button
                            className="flex-1 md:flex-none"
                            title="Start a new episode"
                            data-tour-id="dashboard-new-episode"
                            onClick={() => {
                              setCreatorMode('standard');
                              setPreselectedMainFilename(null);
                              setPreselectedTranscriptReady(false);
                              setCurrentView('episodeStart');
                              requestPreuploadRefresh();
                            }}
                          >
                            <Plus className="w-4 h-4 mr-2" />
                            Start New Episode
                          </Button>
                        )}
                    </div>
                  </CardContent>
                </Card>
                {/* Recent Activity & Listening Metrics */}
                <Card className="shadow-sm border border-gray-200">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-lg">Recent Activity</CardTitle>
                    <CardDescription>Production pace and listening at a glance.</CardDescription>
                  </CardHeader>
                  <CardContent className="text-sm text-gray-700 space-y-4">
                    <div className="grid md:grid-cols-2 gap-3">
                      <div className="p-3 rounded border bg-white flex flex-col gap-1">
                        <span className="text-[11px] tracking-wide text-gray-500">Episodes published in last 30 days</span>
                        <span className="text-lg font-semibold">{stats?.episodes_last_30d ?? '–'}</span>
                      </div>
                      <div className="p-3 rounded border bg-white flex flex-col gap-1">
                        <span className="text-[11px] tracking-wide text-gray-500">Episodes scheduled</span>
                        <span className="text-lg font-semibold">{typeof stats?.upcoming_scheduled === 'number' ? stats.upcoming_scheduled : '–'}</span>
                      </div>
                      <div className="p-3 rounded border bg-white flex flex-col gap-1">
                        <span className="text-[11px] tracking-wide text-gray-500">Last episode published</span>
                        <span className="text-sm font-medium">{formatRelative(stats?.last_published_at)}</span>
                      </div>
                      <div className="p-3 rounded border bg-white flex flex-col gap-1">
                        <span className="text-[11px] tracking-wide text-gray-500">Last assembly result</span>
                        <span className={`text-sm font-medium ${stats?.last_assembly_status==='error'?'text-red-600': stats?.last_assembly_status==='success'?'text-green-600': stats?.last_assembly_status==='pending'?'text-amber-600':'text-gray-600'}`}>{formatAssemblyStatus(stats?.last_assembly_status)}</span>
                      </div>
                    </div>
          {(typeof stats?.plays_last_30d === 'number' || typeof stats?.show_total_plays === 'number' || (Array.isArray(stats?.recent_episode_plays) && stats.recent_episode_plays.length > 0)) && (
                      <div className="space-y-3">
                        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Listening</div>
                        <div className="grid md:grid-cols-2 gap-3">
              {typeof stats?.plays_last_30d === 'number' && (
                            <div className="p-3 rounded border bg-white flex flex-col gap-1">
                <span className="text-[11px] tracking-wide text-gray-500">Plays Last 30 Days</span>
                <span className="text-lg font-semibold">{stats.plays_last_30d}</span>
                            </div>
                          )}
                          {Array.isArray(stats?.recent_episode_plays) && stats.recent_episode_plays.slice(0,4).map(ep => (
                            <div key={ep.episode_id} className="p-3 rounded border bg-white flex flex-col gap-1">
                              <span className="text-[11px] tracking-wide text-gray-500 truncate" title={ep.title}>{ep.title}</span>
                              <span className="text-lg font-semibold">{ep.plays_total ?? '—'}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                    <p className="text-[11px] text-gray-400">Plays update periodically; detailed windows (24h / 7d / 30d) coming soon.</p>
                  </CardContent>
                </Card>
              </div>
              {/* Quick Tools */}
              <div className="space-y-6">
        <Card className="shadow-sm border border-gray-200">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-lg">Quick Tools</CardTitle>
                    <CardDescription className="text-xs">Jump directly into a management area.</CardDescription>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-2 gap-3">
          <Button onClick={() => setCurrentView('podcastManager')} variant="outline" className="justify-start text-sm h-10" data-tour-id="dashboard-quicktool-podcasts"><Podcast className="w-4 h-4 mr-2" />Podcasts</Button>
                      <Button onClick={() => setCurrentView('templateManager')} variant="outline" className="justify-start text-sm h-10" data-tour-id="dashboard-quicktool-templates"><FileText className="w-4 h-4 mr-2" />Templates</Button>
                      <Button onClick={() => setCurrentView('mediaLibrary')} variant="outline" className="justify-start text-sm h-10" data-tour-id="dashboard-quicktool-media"><Music className="w-4 h-4 mr-2" />Media</Button>
          <Button onClick={() => setCurrentView('episodeHistory')} variant="outline" className="justify-start text-sm h-10" data-tour-id="dashboard-quicktool-episodes"><BarChart3 className="w-4 h-4 mr-2" />Episodes</Button>
          <Button 
            onClick={() => {
              if (podcasts.length > 0) {
                setSelectedPodcastId(podcasts[0].id);
                setCurrentView('analytics');
              }
            }} 
            variant="outline" 
            className="justify-start text-sm h-10" 
            data-tour-id="dashboard-quicktool-analytics"
            disabled={podcasts.length === 0}
          >
            <BarChart3 className="w-4 h-4 mr-2" />Analytics
          </Button>
          {/* Import moved under Podcasts */}
          <Button onClick={() => setCurrentView('billing')} variant="outline" className="justify-start text-sm h-10" data-tour-id="dashboard-quicktool-subscription"><DollarSign className="w-4 h-4 mr-2" />Subscription</Button>
                      <Button onClick={() => setCurrentView('settings')} variant="outline" className="justify-start text-sm h-10" data-tour-id="dashboard-quicktool-settings"><SettingsIcon className="w-4 h-4 mr-2" />Settings</Button>
                      <Button
                        onClick={() => setCurrentView('websiteBuilder')}
                        variant="outline"
                        className="justify-start text-sm h-10 text-slate-400 border-slate-200 bg-slate-50 hover:bg-slate-100"
                      >
                        <Globe2 className="w-4 h-4 mr-2" />
                        <span className="flex items-center w-full">
                          <span>Website Builder</span>
                          <span className="ml-auto text-xs font-medium uppercase tracking-wide text-slate-400">Coming Soon</span>
                        </span>
                      </Button>
                      {isAdmin(authUser) && (
                        <Button onClick={() => setCurrentView('devTools')} variant="destructive" className="justify-start text-sm h-10"><AlertTriangle className="w-4 h-4 mr-2" />Dev</Button>
                      )}
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>
          </div>
        );
      }
    }
  };
  
  useEffect(() => {
    const toBilling = () => setCurrentView('billing');
    window.addEventListener('ppp:navigate-billing', toBilling);
    const toView = (e) => {
      try {
        const v = e?.detail;
        if (typeof v === 'string') setCurrentView(v);
      } catch {}
    };
    window.addEventListener('ppp:navigate-view', toView);
    return () => {
      window.removeEventListener('ppp:navigate-billing', toBilling);
      window.removeEventListener('ppp:navigate-view', toView);
    };
  }, []);

  useEffect(() => {
    if (shouldRunTour) return;
    if (currentView !== 'dashboard') {
      setShouldRunTour(false);
      return;
    }

    let cancelled = false;
    const timer = setTimeout(() => {
      if (cancelled) return;
      try {
        if (localStorage.getItem(DASHBOARD_TOUR_STORAGE_KEY) === '1') {
          return;
        }
      } catch {
        return;
      }

      const firstTarget = document.querySelector('[data-tour-id="dashboard-new-episode"]');
      if (firstTarget) {
        setShouldRunTour(true);
      }
    }, 600);

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [currentView, podcasts, templates, shouldRunTour]);

  return (
    <div className="min-h-screen bg-gray-50">
      <Joyride
        steps={tourSteps}
        run={shouldRunTour}
        continuous
        showSkipButton
        callback={handleTourCallback}
        disableOverlayClose
        scrollToFirstStep
        styles={{ options: { zIndex: 10000 } }}
        spotlightClicks
      />
      <nav className="border-b border-gray-200 px-4 py-4 bg-white shadow-sm">
        <div className="container mx-auto max-w-7xl flex justify-between items-center">
      <Logo size={28} lockup />
          <div className="flex items-center space-x-4">
            <div className="relative">
              <Button variant="ghost" size="sm" className="relative" onClick={()=>setShowNotifPanel(v=>!v)}>
                <Bell className="w-5 h-5" />
                {notifications.filter(n=>!n.read_at).length > 0 && (
                  <Badge className="absolute -top-1 -right-1 h-5 w-5 rounded-full p-0 flex items-center justify-center bg-red-500 text-white text-xs">{notifications.filter(n=>!n.read_at).length}</Badge>
                )}
              </Button>
              {showNotifPanel && (
                <div className="absolute right-0 mt-2 w-80 bg-white border border-gray-200 rounded shadow-lg z-50 max-h-96 overflow-auto">
                  <div className="p-3 font-semibold border-b flex items-center justify-between">
                    <span>Notifications</span>
                    {notifications.some(n=>!n.read_at) && (
                      <button
                        className="text-xs text-blue-600 hover:underline"
                        onClick={async ()=>{
                          try {
                            const api = makeApi(token);
                            await api.post('/api/notifications/read-all');
                            setNotifications(curr=>curr.map(n=> n.read_at ? n : { ...n, read_at: new Date().toISOString() }));
                          } catch {}
                        }}
                      >Mark all read</button>
                    )}
                  </div>
                  {notifications.length === 0 && <div className="p-3 text-sm text-gray-500">No notifications</div>}
                  {notifications.map(n => (
                    <div key={n.id} className="p-3 text-sm border-b last:border-b-0 flex flex-col gap-1">
                      <div className="flex items-center justify-between">
                        <div className="font-medium mr-2 truncate">{n.title}</div>
                        <div className="text-[11px] text-gray-500 whitespace-nowrap">{formatShort(n.created_at, resolvedTimezone)}</div>
                      </div>
                      {n.body && <div className="text-gray-600 text-xs">{n.body}</div>}
                      {!n.read_at && <button className="text-xs text-blue-600 self-start" onClick={async ()=>{ try { const api = makeApi(token); await api.post(`/api/notifications/${n.id}/read`); setNotifications(curr=>curr.map(x=>x.id===n.id?{...x,read_at:new Date().toISOString()}:x)); } catch{} }}>Mark read</button>}
                    </div>
                  ))}
                </div>) }
            </div>
            <div className="flex items-center space-x-3">
              {user?.picture ? (
                <Avatar className="h-8 w-8">
                  <AvatarImage src={user.picture} />
                  <AvatarFallback>{user?.email ? user.email.substring(0, 2).toUpperCase() : '…'}</AvatarFallback>
                </Avatar>
              ) : null}
              <span className="hidden md:block text-sm font-medium" style={{ color: "#2C3E50" }}>{user ? user.email : 'Loading...'}</span>
            </div>
            <Button onClick={logout} variant="ghost" size="sm" className="text-gray-600 hover:text-gray-800"><LogOut className="w-4 h-4 mr-1" /><span className="hidden md:inline">Logout</span></Button>
          </div>
        </div>
      </nav>
      <main className="container mx-auto max-w-7xl px-4 py-6">
        {renderCurrentView()}
      </main>
      
      {/* AI Assistant - Always available in bottom-right corner */}
      <AIAssistant token={token} user={user} />
    </div>
  );
}

