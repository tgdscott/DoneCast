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
  AlertCircle,
  Settings as SettingsIcon,
  DollarSign,
  Globe2,
  Menu,
  X,
  BookOpen,
  Mic,
  Library,
  Shield,
} from "lucide-react";
import { useState, useEffect, useMemo, useCallback, useRef, lazy, Suspense } from "react";

import { makeApi, coerceArray } from "@/lib/apiClient";
import { useAuth } from "@/AuthContext";
import { useToast } from "@/hooks/use-toast";
import Logo from "@/components/Logo.jsx";
import Joyride, { STATUS } from "react-joyride";
import { useResolvedTimezone } from "@/hooks/useResolvedTimezone";
import { formatInTimezone } from "@/lib/timezone";

// Eager load components needed for dashboard view
import EpisodeStartOptions from "@/components/dashboard/EpisodeStartOptions";
import AIAssistant from "@/components/assistant/AIAssistant";

// Lazy load heavy components for better mobile performance
const TemplateEditor = lazy(() => import("@/components/dashboard/TemplateEditor"));
const PodcastCreator = lazy(() => import("@/components/dashboard/PodcastCreator"));
const PreUploadManager = lazy(() => import("@/components/dashboard/PreUploadManager"));
const MediaLibrary = lazy(() => import("@/components/dashboard/MediaLibrary"));
const EpisodeHistory = lazy(() => import("@/components/dashboard/EpisodeHistory"));
const PodcastManager = lazy(() => import("@/components/dashboard/PodcastManager"));
const PodcastAnalytics = lazy(() => import("@/components/dashboard/PodcastAnalytics"));
const RssImporter = lazy(() => import("@/components/dashboard/RssImporter"));
const TemplateWizard = lazy(() => import("@/components/dashboard/TemplateWizard"));
const Settings = lazy(() => import("@/components/dashboard/Settings"));
const TemplateManager = lazy(() => import("@/components/dashboard/TemplateManager"));
const BillingPage = lazy(() => import("@/components/dashboard/BillingPage"));
const Recorder = lazy(() => import("@/components/quicktools/Recorder"));
const VisualEditor = lazy(() => import("@/components/website/VisualEditor.jsx"));

// Loading fallback component
const ComponentLoader = () => (
  <div className="flex items-center justify-center min-h-[400px]">
    <Loader2 className="w-8 h-8 animate-spin text-primary" />
  </div>
);

// Error boundary for lazy-loaded chunk failures
class LazyLoadErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    // Check if this is a chunk load error
    if (error?.message?.includes('Failed to fetch dynamically imported module') ||
        error?.message?.includes('Loading chunk')) {
      console.warn('[LazyLoad] Chunk load error detected, will auto-reload');
      // The Vite plugin will handle reload, but this prevents error boundary crash
    }
  }

  render() {
    if (this.state.hasError) {
      const isChunkError = this.state.error?.message?.includes('Failed to fetch') ||
                          this.state.error?.message?.includes('Loading chunk');
      
      return (
        <div className="flex flex-col items-center justify-center min-h-[400px] p-6">
          <AlertCircle className="w-12 h-12 text-orange-500 mb-4" />
          <h3 className="text-lg font-semibold mb-2">
            {isChunkError ? 'Loading Update...' : 'Something went wrong'}
          </h3>
          <p className="text-sm text-muted-foreground text-center max-w-md mb-4">
            {isChunkError 
              ? 'Podcast Plus Plus was recently updated. Refreshing to get the latest version...'
              : 'An error occurred loading this component.'}
          </p>
          {!isChunkError && (
            <Button onClick={() => window.location.reload()} variant="outline">
              Reload Page
            </Button>
          )}
        </div>
      );
    }

    return this.props.children;
  }
}

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
  const [wasRecorded, setWasRecorded] = useState(false);
  const [preuploadItems, setPreuploadItems] = useState([]);
  const [preuploadLoading, setPreuploadLoading] = useState(false);
  const [preuploadError, setPreuploadError] = useState(null);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const preuploadFetchedOnceRef = useRef(false);
  const previousPreuploadContextRef = useRef({ view: currentView, mode: creatorMode });

  // SAFETY CHECK: Detect users who bypassed TermsGate (should never happen, but defensive)
  useEffect(() => {
    if (authUser?.terms_version_required && authUser?.terms_version_required !== authUser?.terms_version_accepted) {
      console.error('[Dashboard Safety Check] User bypassed TermsGate!', {
        email: authUser.email,
        required: authUser.terms_version_required,
        accepted: authUser.terms_version_accepted,
      });
      // Force reload to trigger TermsGate check in App.jsx
      toast({
        title: 'Terms Acceptance Required',
        description: 'Please accept the Terms of Use to continue.',
        variant: 'destructive',
      });
      setTimeout(() => {
        window.location.href = '/?force_terms_check=1';
      }, 2000);
    }
  }, [authUser, toast]);

  const resetPreuploadFetchedFlag = useCallback(() => {
    preuploadFetchedOnceRef.current = false;
  }, []);

  const proEligibleTiers = useMemo(() => new Set(['pro', 'enterprise', 'business', 'team', 'agency']), []);
  const normalizedTier = (user?.tier || '').toLowerCase();
  const canManageCustomDomain = proEligibleTiers.has(normalizedTier);

  const tourSteps = useMemo(() => [
    {
      target: 'body',
      title: 'Welcome to Your Dashboard! 🎙️',
      content: 'Let\'s take a quick tour of your podcast dashboard. This will give you a general overview of the key features - not detailed instructions, just a friendly introduction to help you get oriented.',
      disableBeacon: true,
      placement: 'center',
    },
    {
      target: '[data-tour-id="dashboard-record-upload"]',
      title: 'Record or Upload Audio',
      content: 'Start here to record new audio or upload files you\'ve already created. This is your first step in creating a new episode.',
      disableBeacon: true,
    },
    {
      target: '[data-tour-id="dashboard-assemble-episode"]',
      title: 'Assemble New Episode',
      content: 'Got audio that\'s ready to go? This button appears when you have transcribed audio waiting. Click here to turn it into a polished episode.',
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
      content: 'Any other sound files except for raw episodes that you use for your show are uploaded and stored here.',
    },
    {
      target: '[data-tour-id="dashboard-quicktool-episodes"]',
      title: 'Episodes',
      content: 'All the details about your individual episodes here so you can edit them as you need to.',
    },
    {
      target: '[data-tour-id="dashboard-quicktool-analytics"]',
      title: 'Analytics',
      content: 'Track your podcast\'s performance here. See download stats, listener trends, and get insights about your audience.',
    },
    {
      target: '[data-tour-id="dashboard-quicktool-guides"]',
      title: 'Guides & Help',
      content: 'Need help or want to learn more? Access step-by-step guides, tutorials, and documentation to make the most of your podcasting experience.',
    },
    {
      target: '[data-tour-id="dashboard-quicktool-website"]',
      title: 'Website Builder',
      content: 'Create a beautiful website for your podcast! Build custom pages, showcase your episodes, and give your listeners a home on the web.',
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
      // Only show errors for auth failures (401/403)
      // Network issues, 404s, and other errors should fail silently
      // since this is just a background check for existing uploads
      if (status === 401) {
        setPreuploadError('Your session expired. Please sign in again.');
      } else if (status === 403) {
        setPreuploadError('You are not allowed to view uploads for this account.');
      } else {
        // Silently fail for all other errors (network, 404, 500, etc.)
        // User can still proceed with recording or uploading new audio
        setPreuploadError(null);
      }
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

  const handleRestartTooltips = useCallback(() => {
    // Clear the tour completion flag from localStorage
    try {
      localStorage.removeItem(DASHBOARD_TOUR_STORAGE_KEY);
    } catch (error) {
      console.error('Failed to clear tour flag:', error);
    }
    // Restart the tour
    setShouldRunTour(true);
  }, []);

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
  
  // Poll for preupload updates when on dashboard with processing files
  useEffect(() => {
    if (!token || currentView !== 'dashboard') return;
    
    // Check if we have any items that are still processing (not transcript_ready)
    const hasProcessingItems = preuploadItems.some((item) => !item?.transcript_ready);
    
    if (!hasProcessingItems || preuploadItems.length === 0) return;
    
    // Poll every 5 seconds while there are processing items
    const pollInterval = setInterval(() => {
      refreshPreuploads();
    }, 5000);
    
    return () => clearInterval(pollInterval);
  }, [token, currentView, preuploadItems, refreshPreuploads]);
  
  // Fetch notifications with polling every 10 seconds
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
    
    // Load immediately
    load();
    
    // Then poll every 10 seconds
    const interval = setInterval(load, 10000);
    
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
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
          <Suspense fallback={<ComponentLoader />}>
            <Recorder
              onBack={handleBackToDashboard}
              token={token}
              onFinish={({ filename, hint, transcriptReady }) => {
                try {
                  setPreselectedMainFilename(filename || hint || null);
                  setPreselectedTranscriptReady(!!transcriptReady);
                  setWasRecorded(true);
                } catch {}
                // Return to main dashboard after recording (not the Episode Creator)
                handleBackToDashboard();
              }}
            />
          </Suspense>
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
              setWasRecorded(false);
              setCurrentView('recorder');
            }}
            onChooseUpload={() => {
              setCreatorMode('standard');
              setWasRecorded(false);
              setCurrentView('preuploadUpload');
            }}
          />
        );
      }
      case 'preuploadUpload':
        return (
          <LazyLoadErrorBoundary>
            <Suspense fallback={<ComponentLoader />}>
              <PreUploadManager
                token={token}
                onBack={() => setCurrentView('episodeStart')}
                onDone={handleBackToDashboard}
                defaultEmail={user?.email || ''}
                onUploaded={requestPreuploadRefresh}
              />
            </Suspense>
          </LazyLoadErrorBoundary>
        );
      case 'templateManager':
        return (
          <Suspense fallback={<ComponentLoader />}>
            <TemplateManager onBack={handleBackToDashboard} token={token} setCurrentView={setCurrentView} />
          </Suspense>
        );
      case 'editTemplate':
        return (
          <Suspense fallback={<ComponentLoader />}>
            <TemplateEditor templateId={selectedTemplateId} onBack={handleBackToTemplateManager} token={token} onTemplateSaved={fetchData} />
          </Suspense>
        );
      case 'createEpisode':
        return (
          <Suspense fallback={<ComponentLoader />}>
            <PodcastCreator
              onBack={handleBackToDashboard}
              token={token}
              templates={templates}
              podcasts={podcasts}
              preselectedMainFilename={preselectedMainFilename}
              preselectedTranscriptReady={preselectedTranscriptReady}
              creatorMode={creatorMode}
              wasRecorded={wasRecorded}
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
          </Suspense>
        );
      case 'mediaLibrary':
        return (
          <Suspense fallback={<ComponentLoader />}>
            <MediaLibrary onBack={handleBackToDashboard} token={token} />
          </Suspense>
        );
      case 'episodeHistory':
        return (
          <Suspense fallback={<ComponentLoader />}>
            <EpisodeHistory onBack={handleBackToDashboard} token={token} />
          </Suspense>
        );
      case 'websiteBuilder':
        // Use VisualEditor with the first podcast as default if none selected
        const targetPodcast = podcasts?.find(p => p.id === selectedPodcastId) || podcasts?.[0];
        if (!targetPodcast) {
          return (
            <div className="p-8 text-center">
              <p className="text-slate-600">Please create a podcast first before building a website.</p>
              <Button onClick={handleBackToDashboard} className="mt-4">Back to Dashboard</Button>
            </div>
          );
        }
        return (
          <Suspense fallback={<ComponentLoader />}>
            <VisualEditor
              token={token}
              podcast={targetPodcast}
              onBack={handleBackToDashboard}
            />
          </Suspense>
        );
      case 'podcastManager':
        return (
          <Suspense fallback={<ComponentLoader />}>
            <PodcastManager 
              onBack={handleBackToDashboard} 
              token={token} 
              podcasts={podcasts} 
              setPodcasts={setPodcasts}
              onViewAnalytics={(podcastId) => {
                setSelectedPodcastId(podcastId);
                setCurrentView('analytics');
              }}
            />
          </Suspense>
        );
      case 'rssImporter':
        return (
          <Suspense fallback={<ComponentLoader />}>
            <RssImporter onBack={handleBackToDashboard} token={token} />
          </Suspense>
        );
      case 'settings':
        return (
          <Suspense fallback={<ComponentLoader />}>
            <Settings token={token} />
          </Suspense>
        );
      case 'templateWizard':
        return (
          <Suspense fallback={<ComponentLoader />}>
            <TemplateWizard user={user} token={token} onBack={() => setCurrentView('templateManager')} onTemplateCreated={() => { fetchData(); setCurrentView('templateManager'); }} />
          </Suspense>
        );
      case 'billing':
        return (
          <Suspense fallback={<ComponentLoader />}>
            <BillingPage token={token} onBack={() => setCurrentView('dashboard')} />
          </Suspense>
        );
      case 'analytics':
        return (
          <Suspense fallback={<ComponentLoader />}>
            <PodcastAnalytics 
              podcastId={selectedPodcastId} 
              token={token} 
              onBack={handleBackToDashboard}
            />
          </Suspense>
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
                <p className="text-sm md:text-base text-gray-600 mt-1">Your next masterpiece is just a couple clicks away!</p>
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
                    <div className="flex items-center gap-3 text-sm">
                      <button
                        onClick={() => setCurrentView('podcasts')}
                        className="flex flex-col items-center gap-1 px-4 py-2 rounded-full bg-gray-100 hover:bg-gray-200 transition-colors cursor-pointer"
                        title="View all shows"
                      >
                        <div className="text-[11px] tracking-wide text-gray-500">Shows</div>
                        <div className="font-semibold text-gray-800">{podcasts.length}</div>
                      </button>
                      <button
                        onClick={() => setCurrentView('episodes')}
                        className="flex flex-col items-center gap-1 px-4 py-2 rounded-full bg-gray-100 hover:bg-gray-200 transition-colors cursor-pointer"
                        title="View all episodes"
                      >
                        <div className="text-[11px] tracking-wide text-gray-500">Episodes</div>
                        <div className="font-semibold text-gray-800">{stats?.total_episodes ?? '–'}</div>
                      </button>
                    </div>
                      <div className="flex flex-col gap-2 w-full md:w-auto">
                        {canCreateEpisode && (
                          <>
                            <Button
                              className="flex-1 md:flex-none"
                              variant="default"
                              title="Record or upload new audio"
                              data-tour-id="dashboard-record-upload"
                              onClick={async () => {
                                setCreatorMode('standard');
                                setWasRecorded(false);
                                // Refresh preuploaded items before showing options
                                if (!preuploadLoading && preuploadItems.length === 0) {
                                  try { await requestPreuploadRefresh(); } catch {}
                                }
                                setCurrentView('episodeStart');
                              }}
                            >
                              <Mic className="w-4 h-4 mr-2" />
                              Record or Upload Audio
                            </Button>
                            {preuploadItems.some((item) => item?.transcript_ready) && (
                              <Button
                                className="flex-1 md:flex-none"
                                title="Assemble episode from ready audio"
                                data-tour-id="dashboard-assemble-episode"
                                onClick={async () => {
                                  setCreatorMode('preuploaded');
                                  setWasRecorded(false);
                                  setPreselectedMainFilename(null);
                                  setPreselectedTranscriptReady(false);
                                  resetPreuploadFetchedFlag();
                                  if (!preuploadLoading && preuploadItems.length === 0) {
                                    try { await requestPreuploadRefresh(); } catch {}
                                  }
                                  setCurrentView('createEpisode');
                                }}
                              >
                                <Library className="w-4 h-4 mr-2" />
                                Assemble New Episode
                              </Button>
                            )}
                          </>
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
          {(typeof stats?.plays_last_30d === 'number' || typeof stats?.plays_7d === 'number' || typeof stats?.plays_365d === 'number' || typeof stats?.plays_all_time === 'number' || typeof stats?.show_total_plays === 'number' || (Array.isArray(stats?.top_episodes) && stats.top_episodes.length > 0)) && (
                      <div className="space-y-3">
                        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Listening Stats</div>
                        
                        {/* Time Period Cards */}
                        <div className="grid md:grid-cols-2 gap-3">
              {typeof stats?.plays_7d === 'number' && (
                            <div className="p-3 rounded border bg-white flex flex-col gap-1">
                <span className="text-[11px] tracking-wide text-gray-500">Downloads Last 7 Days</span>
                <span className="text-lg font-semibold">{stats.plays_7d.toLocaleString()}</span>
                            </div>
                          )}
              {typeof stats?.plays_30d === 'number' && (
                            <div className="p-3 rounded border bg-white flex flex-col gap-1">
                <span className="text-[11px] tracking-wide text-gray-500">Downloads Last 30 Days</span>
                <span className="text-lg font-semibold">{stats.plays_30d.toLocaleString()}</span>
                            </div>
                          )}
              {typeof stats?.plays_365d === 'number' && (
                            <div className="p-3 rounded border bg-white flex flex-col gap-1">
                <span className="text-[11px] tracking-wide text-gray-500">Downloads Last Year</span>
                <span className="text-lg font-semibold">{stats.plays_365d.toLocaleString()}</span>
                            </div>
                          )}
              {typeof stats?.plays_all_time === 'number' && (
                            <div className="p-3 rounded border bg-white flex flex-col gap-1">
                <span className="text-[11px] tracking-wide text-gray-500">All-Time Downloads</span>
                <span className="text-lg font-semibold">{stats.plays_all_time.toLocaleString()}</span>
                            </div>
                          )}
                        </div>
                        
                        {/* Top Episodes Section */}
                        {Array.isArray(stats?.top_episodes) && stats.top_episodes.length > 0 && (
                          <div className="space-y-2">
                            <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mt-3">Top Episodes (All-Time)</div>
                            {stats.top_episodes.slice(0, 3).map((ep, idx) => (
                              <div key={ep.episode_id || idx} className="p-3 rounded border bg-gradient-to-r from-blue-50 to-white flex items-center justify-between">
                                <div className="flex items-center gap-2 flex-1 min-w-0">
                                  <Badge variant="outline" className="text-[10px] px-1.5 py-0.5">#{idx + 1}</Badge>
                                  <span className="text-[11px] tracking-wide text-gray-700 font-medium truncate" title={ep.title}>{ep.title}</span>
                                </div>
                                <div className="text-right ml-3">
                                  <div className="text-base font-bold text-gray-900">{ep.downloads_all_time?.toLocaleString() || 0}</div>
                                  <div className="text-[9px] text-gray-500">downloads</div>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                    <p className="text-[11px] text-gray-400">Analytics powered by OP3 (Open Podcast Prefix Project). Updates every 3 hours.</p>
                    {stats?.op3_enabled && (stats?.plays_7d === 0 && stats?.plays_30d === 0 && stats?.plays_all_time === 0) && (
                      <div className="mt-3 p-3 bg-blue-50 border border-blue-200 rounded-lg text-xs text-blue-800">
                        <p className="font-semibold mb-1">📊 Showing 0 downloads?</p>
                        <p className="mb-2">OP3 only tracks downloads from <strong>podcast apps</strong> (Apple Podcasts, Spotify, etc.). YouTube views are not included.</p>
                        <p className="text-[10px] text-blue-600">Tip: If you distribute via YouTube, consider manually tracking those views separately.</p>
                      </div>
                    )}
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
                        onClick={() => window.location.href = '/guides'}
                        variant="outline"
                        className="justify-start text-sm h-10"
                        data-tour-id="dashboard-quicktool-guides"
                      >
                        <BookOpen className="w-4 h-4 mr-2" />
                        Guides & Help
                      </Button>
                      <Button
                        onClick={() => setCurrentView('websiteBuilder')}
                        variant="outline"
                        className="justify-start text-sm h-10"
                        data-tour-id="dashboard-quicktool-website"
                      >
                        <Globe2 className="w-4 h-4 mr-2" />
                        Website Builder
                      </Button>
                      {(authUser?.role === 'admin' || authUser?.role === 'superadmin' || isAdmin(authUser)) && (
                        <Button 
                          onClick={() => window.location.href = '/dashboard?admin=1'} 
                          variant="outline" 
                          className="justify-start text-sm h-10 border-orange-300 hover:bg-orange-50"
                          data-tour-id="dashboard-quicktool-admin-panel"
                          title="Access admin panel for user management and platform settings"
                        >
                          <Shield className="w-4 h-4 mr-2 text-orange-600" />
                          Admin Panel
                        </Button>
                      )}
                      {authUser?.email === 'wordsdonewrite@gmail.com' && (
                        <Button 
                          onClick={() => window.location.href = '/admin?tab=landing'} 
                          variant="outline" 
                          className="justify-start text-sm h-10 border-blue-300 hover:bg-blue-50"
                          data-tour-id="dashboard-quicktool-landing-editor"
                          title="Edit customer testimonials and FAQs on the front page"
                        >
                          <FileText className="w-4 h-4 mr-2 text-blue-600" />
                          Edit Front Page
                        </Button>
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
        locale={{
          last: "Let's Do This!",
          skip: "Skip Tour",
        }}
      />
      <nav className="border-b border-gray-200 px-4 py-4 bg-white shadow-sm safe-top">
        <div className="container mx-auto max-w-7xl flex justify-between items-center">
          <div className="flex items-center gap-3">
            <Button
              variant="ghost"
              size="sm"
              className="lg:hidden touch-target-icon"
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              aria-label="Toggle menu"
            >
              {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </Button>
            <Logo size={28} lockup />
          </div>
          <div className="flex items-center space-x-2 sm:space-x-4">
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
                    <div 
                      key={n.id} 
                      className={`p-3 text-sm border-b last:border-b-0 flex flex-col gap-1 ${
                        n.type === 'error' ? 'bg-red-50 border-red-200' : ''
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <div className={`font-medium mr-2 truncate ${
                          n.type === 'error' ? 'text-red-700' : ''
                        }`}>{n.title}</div>
                        <div className="text-[11px] text-gray-500 whitespace-nowrap">{formatShort(n.created_at, resolvedTimezone)}</div>
                      </div>
                      {n.body && <div className={`text-xs ${
                        n.type === 'error' ? 'text-red-600' : 'text-gray-600'
                      }`}>{n.body}</div>}
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
            {(authUser?.is_admin || authUser?.role === 'admin' || authUser?.role === 'superadmin') && (
              <Button onClick={() => window.location.href = '/dashboard?admin=1'} variant="ghost" size="sm" className="text-gray-600 hover:text-gray-800">
                <SettingsIcon className="w-4 h-4 mr-1" /><span className="hidden md:inline">Admin Panel</span>
              </Button>
            )}
            <Button onClick={logout} variant="ghost" size="sm" className="text-gray-600 hover:text-gray-800"><LogOut className="w-4 h-4 mr-1" /><span className="hidden md:inline">Logout</span></Button>
          </div>
        </div>
      </nav>
      
      {/* Mobile Menu Overlay and Drawer */}
      {mobileMenuOpen && (
        <>
          <div 
            className="fixed inset-0 bg-black/50 z-40 lg:hidden"
            onClick={() => setMobileMenuOpen(false)}
          />
          <div className="fixed top-0 left-0 bottom-0 w-[280px] bg-white shadow-xl z-50 overflow-y-auto lg:hidden safe-top safe-bottom">
            <div className="p-4 border-b">
              <div className="flex items-center justify-between mb-4">
                <Logo size={24} lockup />
                <Button 
                  variant="ghost" 
                  size="sm"
                  onClick={() => setMobileMenuOpen(false)}
                  className="touch-target-icon"
                >
                  <X className="w-5 h-5" />
                </Button>
              </div>
              {user && (
                <div className="flex items-center gap-2">
                  <Avatar className="h-8 w-8">
                    <AvatarImage src={user.picture} />
                    <AvatarFallback>{user?.email ? user.email.substring(0, 2).toUpperCase() : '…'}</AvatarFallback>
                  </Avatar>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium truncate">{user.email}</p>
                  </div>
                </div>
              )}
            </div>
            <div className="p-4 space-y-2">
              {currentView !== 'dashboard' && (
                <Button 
                  onClick={() => { setCurrentView('dashboard'); setMobileMenuOpen(false); }} 
                  variant="outline" 
                  className="w-full justify-start touch-target"
                >
                  <ArrowLeft className="w-4 h-4 mr-2" />Dashboard
                </Button>
              )}
              <Button 
                onClick={() => { setCurrentView('podcastManager'); setMobileMenuOpen(false); }} 
                variant="outline" 
                className="w-full justify-start touch-target"
              >
                <Podcast className="w-4 h-4 mr-2" />Podcasts
              </Button>
              <Button 
                onClick={() => { setCurrentView('templateManager'); setMobileMenuOpen(false); }} 
                variant="outline" 
                className="w-full justify-start touch-target"
              >
                <FileText className="w-4 h-4 mr-2" />Templates
              </Button>
              <Button 
                onClick={() => { setCurrentView('mediaLibrary'); setMobileMenuOpen(false); }} 
                variant="outline" 
                className="w-full justify-start touch-target"
              >
                <Music className="w-4 h-4 mr-2" />Media
              </Button>
              <Button 
                onClick={() => { setCurrentView('episodeHistory'); setMobileMenuOpen(false); }} 
                variant="outline" 
                className="w-full justify-start touch-target"
              >
                <BarChart3 className="w-4 h-4 mr-2" />Episodes
              </Button>
              <Button 
                onClick={() => { 
                  if (podcasts.length > 0) {
                    setSelectedPodcastId(podcasts[0].id);
                    setCurrentView('analytics');
                    setMobileMenuOpen(false);
                  }
                }} 
                variant="outline" 
                className="w-full justify-start touch-target"
                disabled={podcasts.length === 0}
              >
                <BarChart3 className="w-4 h-4 mr-2" />Analytics
              </Button>
              <Button 
                onClick={() => { setCurrentView('billing'); setMobileMenuOpen(false); }} 
                variant="outline" 
                className="w-full justify-start touch-target"
              >
                <DollarSign className="w-4 h-4 mr-2" />Subscription
              </Button>
              <Button 
                onClick={() => { setCurrentView('settings'); setMobileMenuOpen(false); }} 
                variant="outline" 
                className="w-full justify-start touch-target"
              >
                <SettingsIcon className="w-4 h-4 mr-2" />Settings
              </Button>
              <Button 
                onClick={() => { window.location.href = '/guides'; }} 
                variant="outline" 
                className="w-full justify-start touch-target"
              >
                <BookOpen className="w-4 h-4 mr-2" />Guides & Help
              </Button>
              <Button 
                onClick={() => { setCurrentView('websiteBuilder'); setMobileMenuOpen(false); }} 
                variant="outline" 
                className="w-full justify-start touch-target"
              >
                <Globe2 className="w-4 h-4 mr-2" />Website Builder
              </Button>
              {(authUser?.is_admin || authUser?.role === 'admin' || authUser?.role === 'superadmin') && (
                <Button 
                  onClick={() => { window.location.href = '/dashboard?admin=1'; setMobileMenuOpen(false); }} 
                  variant="outline" 
                  className="w-full justify-start touch-target bg-purple-50 border-purple-200 text-purple-700 hover:bg-purple-100"
                >
                  <SettingsIcon className="w-4 h-4 mr-2" />Admin Panel
                </Button>
              )}
            </div>
            <div className="p-4 border-t mt-4">
              <Button 
                onClick={logout} 
                variant="ghost" 
                className="w-full justify-start touch-target text-red-600 hover:text-red-700 hover:bg-red-50"
              >
                <LogOut className="w-4 h-4 mr-2" />Logout
              </Button>
            </div>
          </div>
        </>
      )}
      
      <main className="container mx-auto max-w-7xl px-4 sm:px-6 py-6">
        {renderCurrentView()}
      </main>
      
      {/* AI Assistant - Always available in bottom-right corner */}
      <AIAssistant 
        token={token} 
        user={user} 
        currentPage={currentView}
        onRestartTooltips={currentView === 'dashboard' ? handleRestartTooltips : null}
      />
    </div>
  );
}

