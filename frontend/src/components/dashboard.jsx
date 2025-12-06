"use client"

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
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
  Home,
} from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import React, { useState, useEffect, useMemo, useCallback, useRef, lazy, Suspense } from "react";

import { makeApi, coerceArray } from "@/lib/apiClient";
import { useAuth } from "@/AuthContext";
import { useToast } from "@/hooks/use-toast";
import Logo from "@/components/Logo.jsx";
import Joyride, { STATUS } from "react-joyride";
import { useResolvedTimezone } from "@/hooks/useResolvedTimezone";
import { formatInTimezone } from "@/lib/timezone";
import CustomTourTooltip from "@/components/dashboard/CustomTourTooltip";
import DashboardSidebar from "@/components/dashboard/DashboardSidebar.jsx";

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
  <div className="space-y-6 p-6">
    <div className="space-y-2">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-4 w-96" />
    </div>
    <div className="grid gap-4">
      <Skeleton className="h-32 w-full" />
      <Skeleton className="h-32 w-full" />
    </div>
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
      if (import.meta.env.DEV) console.warn('[LazyLoad] Chunk load error detected, will auto-reload');
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
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    const diffMs = Date.now() - d.getTime();
    const sec = Math.floor(diffMs / 1000);
    if (sec < 60) return 'just now';
    const min = Math.floor(sec / 60);
    if (min < 60) return `${min}m ago`;
    const hr = Math.floor(min / 60);
    if (hr < 24) return `${hr}h ago`;
    const day = Math.floor(hr / 24);
    if (day < 30) return `${day}d ago`;
    const mo = Math.floor(day / 30);
    if (mo < 12) return `${mo}mo ago`;
    const yr = Math.floor(mo / 12);
    return `${yr}y ago`;
  } catch { return '—'; }
}

function formatAssemblyStatus(status) {
  if (!status) return '—';
  switch (status) {
    case 'success': return 'Success';
    case 'error': return 'Error';
    case 'pending': return 'In Progress';
    default: return status.charAt(0).toUpperCase() + status.slice(1);
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
    try { if (localStorage.getItem('ppp_post_checkout') === '1') return 'billing'; } catch { }
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
  const isNavigatingFromPopStateRef = useRef(false);
  const viewHistoryRef = useRef(['dashboard']); // Track view history for back button

  const navItems = useMemo(() => [
    { id: 'episodes', label: 'Episodes', view: 'episodeHistory', icon: Play, tourId: 'dashboard-nav-episodes' },
    { id: 'podcasts', label: 'Podcasts', view: 'podcastManager', icon: Podcast, tourId: 'dashboard-nav-podcasts' },
    { id: 'templates', label: 'Templates', view: 'templateManager', icon: FileText, tourId: 'dashboard-nav-templates' },
    { id: 'media', label: 'Media', view: 'mediaLibrary', icon: Music, tourId: 'dashboard-nav-media' },
    { id: 'analytics', label: 'Analytics', view: 'analytics', icon: BarChart3, tourId: 'dashboard-nav-analytics', disabled: podcasts.length === 0 },
    { id: 'subscription', label: 'Subscription', view: 'billing', icon: DollarSign, tourId: 'dashboard-nav-subscription' },
    { id: 'website', label: 'Website Builder', view: 'websiteBuilder', icon: Globe2, tourId: 'dashboard-nav-website' },
    { id: 'settings', label: 'Settings', view: 'settings', icon: SettingsIcon, tourId: 'dashboard-nav-settings' },
    { id: 'guides', label: 'Guides & Help', href: '/guides', icon: BookOpen, tourId: 'dashboard-nav-guides', section: 'support' },
  ], [podcasts.length]);

  const primaryNavItems = useMemo(() => navItems.filter((item) => item.section !== 'support'), [navItems]);
  const supportNavItems = useMemo(() => navItems.filter((item) => item.section === 'support'), [navItems]);

  // SAFETY CHECK: Detect users who bypassed TermsGate (should never happen, but defensive)
  // CRITICAL: Only check if user data is hydrated to avoid false positives
  // This prevents "pestering" users who just accepted terms but data hasn't refreshed yet
  useEffect(() => {
    // Skip check if user data isn't hydrated yet (might be stale)
    if (!authUser) return;

    const requiredVersion = authUser?.terms_version_required;
    const acceptedVersion = authUser?.terms_version_accepted;

    // Only check if requiredVersion is set and differs from accepted
    // This prevents false positives when TERMS_VERSION isn't configured
    if (
      requiredVersion &&
      typeof requiredVersion === 'string' &&
      requiredVersion.trim() !== '' &&
      requiredVersion !== acceptedVersion
    ) {
      console.error('[Dashboard Safety Check] User bypassed TermsGate!', {
        email: authUser.email,
        required: requiredVersion,
        accepted: acceptedVersion,
      });
      // Force reload to trigger TermsGate check in App.jsx
      toast({
        title: 'Terms Acceptance Required',
        description: 'Please accept the Terms of Use to continue.',
        variant: 'destructive',
      });
      // Use shorter delay and ensure we're redirecting to trigger proper check
      setTimeout(() => {
        window.location.href = '/app';
      }, 1000);
    }
  }, [authUser, toast]);

  const resetPreuploadFetchedFlag = useCallback(() => {
    preuploadFetchedOnceRef.current = false;
  }, []);

  // Store the original setter in a ref so we can wrap it
  const setCurrentViewRef = useRef(setCurrentView);
  setCurrentViewRef.current = setCurrentView;

  // Enhanced setCurrentView that tracks history for back button support
  const setCurrentViewWithHistory = useCallback((newView, skipHistory = false) => {
    if (isNavigatingFromPopStateRef.current) {
      // We're restoring from history, don't create new entry
      isNavigatingFromPopStateRef.current = false;
      setCurrentViewRef.current(newView);
      // Update viewHistoryRef to match
      if (newView === 'dashboard') {
        viewHistoryRef.current = ['dashboard'];
      } else {
        const idx = viewHistoryRef.current.indexOf(newView);
        if (idx >= 0) {
          viewHistoryRef.current = viewHistoryRef.current.slice(0, idx + 1);
        } else {
          viewHistoryRef.current.push(newView);
        }
      }
      return;
    }

    const previousView = currentView;
    setCurrentViewRef.current(newView);

    // Only create history entry if view actually changed and we're not skipping history
    if (!skipHistory && newView !== previousView) {
      // Ensure current state has dashboardView before pushing new entry
      const currentState = window.history.state || {};
      if (!currentState.dashboardView && previousView) {
        // Current state doesn't have dashboardView, fix it first
        window.history.replaceState({ dashboardView: previousView, inApp: true, ...currentState }, '', window.location.href);
      }

      if (newView === 'dashboard') {
        // Going back to dashboard - ensure dashboard is at the end of history stack
        while (viewHistoryRef.current.length > 1 && viewHistoryRef.current[viewHistoryRef.current.length - 1] !== 'dashboard') {
          viewHistoryRef.current.pop();
        }
        if (viewHistoryRef.current[viewHistoryRef.current.length - 1] !== 'dashboard') {
          viewHistoryRef.current.push('dashboard');
        }
        // Push state to browser history - always create entry when going to dashboard
        const state = { dashboardView: 'dashboard', previousView, inApp: true };
        window.history.pushState(state, '', window.location.href);
      } else {
        // Going to a new view - ensure dashboard is before it in stack
        if (viewHistoryRef.current.length === 0 || viewHistoryRef.current[viewHistoryRef.current.length - 1] !== 'dashboard') {
          viewHistoryRef.current.push('dashboard');
        }
        // Remove this view if it's already in the stack (avoid duplicates)
        const existingIdx = viewHistoryRef.current.indexOf(newView);
        if (existingIdx >= 0) {
          viewHistoryRef.current = viewHistoryRef.current.slice(0, existingIdx + 1);
        } else {
          viewHistoryRef.current.push(newView);
        }
        // Push state to browser history so back button works
        const state = { dashboardView: newView, previousView, inApp: true };
        window.history.pushState(state, '', window.location.href);
      }
    }
  }, [currentView]);

  const handleSidebarNavigate = useCallback((item) => {
    if (!item || item.disabled) return;
    if (item.href) {
      window.location.href = item.href;
      setMobileMenuOpen(false);
      return;
    }

    if (item.id === 'analytics' && podcasts.length > 0) {
      setSelectedPodcastId(podcasts[0].id);
    }

    if (item.view) {
      setCurrentViewWithHistory(item.view);
    }

    setMobileMenuOpen(false);
  }, [podcasts, setCurrentViewWithHistory, setSelectedPodcastId]);

  // Override setCurrentView to use history-aware version
  // We'll use this in the popstate handler, but for all other calls we need to replace setCurrentView
  // For now, let's update the popstate handler and key navigation points

  // Handle browser back button for internal navigation
  useEffect(() => {
    const handlePopState = (event) => {
      const currentPath = window.location.pathname;
      const isAppRoute = currentPath.startsWith('/app') ||
        currentPath.startsWith('/dashboard') ||
        currentPath.startsWith('/admin') ||
        (currentPath === '/' && authUser);

      // Always ensure we're still in an app route - if not, let App.jsx handle it
      if (!isAppRoute) {
        return; // Let App.jsx redirect back to app
      }

      // Check if this is a dashboard view navigation
      if (event.state?.dashboardView) {
        // Restore the previous view
        isNavigatingFromPopStateRef.current = true;
        const targetView = event.state.dashboardView;
        setCurrentViewRef.current(targetView);

        // Update history stack to match - find the view in our stack and trim to that point
        const idx = viewHistoryRef.current.indexOf(targetView);
        if (idx >= 0) {
          viewHistoryRef.current = viewHistoryRef.current.slice(0, idx + 1);
        } else {
          // View not in stack, rebuild it
          if (targetView === 'dashboard') {
            viewHistoryRef.current = ['dashboard'];
          } else {
            viewHistoryRef.current = ['dashboard', targetView];
          }
        }
        return;
      }

      // If no dashboard state but we're still in an app route, restore dashboard
      // This handles cases where we go back to a state before dashboard tracking started
      isNavigatingFromPopStateRef.current = true;
      setCurrentViewRef.current('dashboard');
      viewHistoryRef.current = ['dashboard'];
      // Update URL state to include dashboardView so next back press works correctly
      window.history.replaceState({ dashboardView: 'dashboard', inApp: true }, '', window.location.href);
    };

    // Use capture phase so we handle it before App.jsx
    window.addEventListener('popstate', handlePopState, true);
    return () => {
      window.removeEventListener('popstate', handlePopState, true);
    };
  }, [authUser]);

  // Initialize history state on mount and ensure it always has dashboardView
  useEffect(() => {
    // Always ensure current view is tracked in history state
    const currentState = window.history.state;
    if (!currentState || !currentState.dashboardView) {
      // Replace current state to include dashboardView - this ensures every entry has it
      window.history.replaceState({ dashboardView: currentView, inApp: true }, '', window.location.href);
    }
    // Initialize viewHistoryRef with current view
    if (viewHistoryRef.current.length === 0) {
      if (currentView === 'dashboard') {
        viewHistoryRef.current = ['dashboard'];
      } else {
        viewHistoryRef.current = ['dashboard', currentView];
      }
    }
  }, []); // Only run once on mount

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
      title: 'Create Something New',
      content: 'Start every episode by recording or uploading audio. This button kicks off the entire DoneCast workflow, so we\'ll keep it first in the tour.',
      disableBeacon: true,
    },
    {
      target: '[data-tour-id="dashboard-back-button"]',
      title: 'Dashboard Shortcut',
      content: 'Whenever you wander into another section, use this Dashboard button to snap back to your main view.',
      disableBeacon: true,
    },
    {
      target: '[data-tour-id="dashboard-nav-episodes"]',
      title: 'Episodes',
      content: 'Preview your published, scheduled, and draft episodes. During the tour we\'ll open this view so you can see it for a moment.',
    },
    {
      target: '[data-tour-id="dashboard-nav-podcasts"]',
      title: 'Podcasts',
      content: 'Manage show-level details like titles, artwork, and descriptions. Each click on the left menu opens instantly in the main area.',
    },
    {
      target: '[data-tour-id="dashboard-nav-templates"]',
      title: 'Templates',
      content: 'Your repeatable structure lives here. Adjust prompts, intro/outro settings, or create variants for special series.',
    },
    {
      target: '[data-tour-id="dashboard-nav-media"]',
      title: 'Media Library',
      content: 'Store intros, music beds, sponsor reads, and any reusable clips. No more digging through filenames elsewhere.',
    },
    {
      target: '[data-tour-id="dashboard-nav-analytics"]',
      title: 'Analytics',
      content: 'See downloads, trends, and OP3 insights without leaving DoneCast. We\'ll jump into the view so you can preview the layout.',
    },
    {
      target: '[data-tour-id="dashboard-nav-subscription"]',
      title: 'Subscription',
      content: 'Upgrade, downgrade, or review billing activity. Everything billing-related lives here now.',
    },
    {
      target: '[data-tour-id="dashboard-nav-website"]',
      title: 'Website Builder',
      content: 'Launch or tweak your DoneCast site without touching code. This opens the full visual editor.',
    },
    {
      target: '[data-tour-id="dashboard-nav-settings"]',
      title: 'Settings',
      content: 'Account-level preferences and integrations live here. If it isn\'t a podcast asset, it probably belongs in Settings.',
    },
    {
      target: '[data-tour-id="dashboard-nav-guides"]',
      title: 'Guides & Help',
      content: 'Need a walkthrough later? This link jumps directly to the DoneCast guides. We keep it visually separated so it\'s easy to spot.',
    },
  ], []);

  const jumpToView = useCallback((view) => {
    if (!view) return;
    setCurrentViewWithHistory(view, true);
  }, [setCurrentViewWithHistory]);

  const tourStepActions = useMemo(() => ({
    0: () => jumpToView('dashboard'),
    1: () => jumpToView('dashboard'),
    2: () => jumpToView('dashboard'),
    3: () => jumpToView('episodeHistory'),
    4: () => jumpToView('podcastManager'),
    5: () => jumpToView('templateManager'),
    6: () => jumpToView('mediaLibrary'),
    7: () => {
      if (podcasts.length > 0) {
        setSelectedPodcastId(podcasts[0].id);
        jumpToView('analytics');
      }
    },
    8: () => jumpToView('billing'),
    9: () => jumpToView('websiteBuilder'),
    10: () => jumpToView('settings'),
    11: () => jumpToView('dashboard'),
  }), [jumpToView, podcasts, setSelectedPodcastId]);

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
    const { status, type, index } = data;

    if (type === 'step:before' && typeof index === 'number') {
      const action = tourStepActions[index];
      if (action) {
        action();
      }
    }

    if ([STATUS.FINISHED, STATUS.SKIPPED].includes(status)) {
      try { localStorage.setItem(DASHBOARD_TOUR_STORAGE_KEY, '1'); } catch { }
      setShouldRunTour(false);
      jumpToView('dashboard');
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

  // Track if we're currently fetching to prevent concurrent calls
  const fetchingRef = useRef(false);

  const fetchData = useCallback(async () => {
    if (!token) return;

    // Prevent concurrent fetches
    if (fetchingRef.current) {
      if (import.meta.env.DEV) console.log('[Dashboard] Skipping fetchData - already fetching');
      return;
    }

    fetchingRef.current = true;
    if (import.meta.env.DEV) console.log('[Dashboard] Starting fetchData', { timestamp: Date.now() });

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
          if (import.meta.env.DEV) console.warn('Templates fetch unauthorized, logging out', reason);
          logout();
          return;
        }
        if (import.meta.env.DEV) console.warn('Failed to load templates (non-fatal):', reason);
        setTemplates([]);
      }

      // Podcasts - only update if the data actually changed to prevent re-renders
      if (podcastsRes.status === 'fulfilled') {
        const podcastList = coerceArray(podcastsRes.value);
        // Only update if the array reference or content changed
        setPodcasts(prevPodcasts => {
          const prevIds = prevPodcasts.map(p => p.id).sort().join(',');
          const newIds = podcastList.map(p => p.id).sort().join(',');
          if (prevIds === newIds && prevPodcasts.length === podcastList.length) {
            // Same podcasts, return previous to avoid re-render
            return prevPodcasts;
          }
          return podcastList;
        });
      } else {
        const reason = podcastsRes.reason || {};
        if (reason.status === 401) {
          if (import.meta.env.DEV) console.warn('Podcasts fetch unauthorized, logging out', reason);
          logout();
          return;
        }
        if (import.meta.env.DEV) console.warn('Failed to load podcasts (non-fatal):', reason);
        setPodcasts([]);
      }

      // Stats (optional)
      if (statsRes.status === 'fulfilled') {
        setStats(statsRes.value);
      } else {
        const reason = statsRes.reason || {};
        if (reason.status === 401) {
          if (import.meta.env.DEV) console.warn('Stats fetch unauthorized; continuing without stats', reason);
          setStatsError('You are not authorized to view stats.');
          setStats(null);
        } else {
          // Non-fatal: show a gentle UI message
          if (import.meta.env.DEV) console.warn('Failed to load stats (non-fatal):', reason);
          setStatsError('Unable to load statistics right now. This won\'t affect your podcast.');
          setStats(null);
        }
      }
    } catch (err) {
      // Unexpected error: don't immediately force logout unless it's a 401
      if (import.meta.env.DEV) {
        console.error("Unexpected error fetching dashboard data:", err);
      } else {
        console.error("Unexpected error fetching dashboard data");
      }
      if (err && err.status === 401) {
        logout();
      } else {
        setStatsError('Failed to load dashboard data.');
      }
    } finally {
      fetchingRef.current = false;
      if (import.meta.env.DEV) console.log('[Dashboard] Finished fetchData', { timestamp: Date.now() });
    }
  }, [token, logout]);

  // Initial load + token change: fetch other data (user already fetched by AuthContext)
  // Use ref to avoid including fetchData in deps (it's stable via useCallback)
  const fetchDataRef = useRef(fetchData);
  useEffect(() => {
    fetchDataRef.current = fetchData;
  }, [fetchData]);

  useEffect(() => {
    if (token) {
      fetchDataRef.current();
    }
  }, [token]); // Only depend on token, not fetchData
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
  }, [token, currentView, fetchData]);

  // Initial fetch of preuploaded items when dashboard loads
  useEffect(() => {
    if (token && currentView === 'dashboard' && !preuploadFetchedOnceRef.current) {
      refreshPreuploads();
    }
  }, [token, currentView, refreshPreuploads]);

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

  // Fetch notifications with adaptive polling to reduce DB load
  // - Default: 30 seconds (reduced from 10s to lower connection pressure)
  // - During upload/assembly: 60 seconds (reduce load during heavy operations)
  // - After upload: 60 seconds for 2 minutes, then back to 30s
  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    let intervalId = null;
    const UPLOAD_COOLDOWN_MS = 2 * 60 * 1000; // 2 minutes after upload
    const DEFAULT_INTERVAL = 30000; // 30 seconds
    const SLOW_INTERVAL = 60000; // 60 seconds

    // Check for recent upload activity in localStorage
    const checkRecentUpload = () => {
      try {
        const uploadTime = localStorage.getItem('ppp_last_upload_time');
        if (uploadTime) {
          const time = parseInt(uploadTime, 10);
          if (Date.now() - time < UPLOAD_COOLDOWN_MS) {
            return true;
          }
          localStorage.removeItem('ppp_last_upload_time');
        }
      } catch { }
      return false;
    };

    // Determine current polling interval based on state
    const getPollInterval = () => {
      const hasRecentUpload = checkRecentUpload();
      const isInHeavyOperation = preuploadLoading ||
        (currentView === 'createEpisode' && creatorMode !== 'preuploaded');

      if (hasRecentUpload || isInHeavyOperation) {
        return SLOW_INTERVAL;
      }
      return DEFAULT_INTERVAL;
    };

    const load = async () => {
      if (cancelled) return;
      try {
        const api = makeApi(token);
        const r = await api.get('/api/notifications/');
        if (!cancelled && Array.isArray(r)) {
          setNotifications(curr => {
            const map = new Map((curr || []).map(n => [n.id, n]));
            const merged = r.map(n => {
              const existing = map.get(n.id);
              if (existing && existing.read_at) return { ...n, read_at: existing.read_at };
              return n;
            });
            for (const n of (curr || [])) if (!merged.find(m => m.id === n.id)) merged.push(n);
            return merged.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
          });
        }
      } catch { }
    };

    // Function to restart polling with correct interval
    const restartPolling = () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
      const interval = getPollInterval();
      intervalId = setInterval(load, interval);
    };

    // Load immediately
    load();

    // Start polling with initial interval
    restartPolling();

    // Listen for upload events to adjust polling
    const handleUploadStart = () => {
      restartPolling(); // Will use SLOW_INTERVAL if in heavy operation
    };

    const handleUploadComplete = () => {
      try {
        localStorage.setItem('ppp_last_upload_time', Date.now().toString());
      } catch { }
      // Restart with slow interval (recent upload)
      restartPolling();
    };

    // Listen for custom events from upload components
    window.addEventListener('ppp:upload:start', handleUploadStart);
    window.addEventListener('ppp:upload:complete', handleUploadComplete);

    // Also restart polling when state changes
    const stateCheckInterval = setInterval(() => {
      if (!cancelled) {
        restartPolling();
      }
    }, 10000); // Check every 10s and adjust if needed

    return () => {
      cancelled = true;
      if (intervalId) clearInterval(intervalId);
      if (stateCheckInterval) clearInterval(stateCheckInterval);
      window.removeEventListener('ppp:upload:start', handleUploadStart);
      window.removeEventListener('ppp:upload:complete', handleUploadComplete);
    };
  }, [token, preuploadLoading, currentView, creatorMode]);
  // BroadcastChannel listener for checkout success -> refetch notifications
  useEffect(() => {
    let bc;
    try {
      bc = new BroadcastChannel('ppp_billing');
      bc.onmessage = (e) => {
        if (e?.data?.type === 'checkout_success') {
          // Refresh notifications & maybe toast
          (async () => {
            try {
              const api = makeApi(token);
              const d = await api.get('/api/notifications/');
              setNotifications(curr => {
                const map = new Map((curr || []).map(n => [n.id, n]));
                const merged = (Array.isArray(d) ? d : []).map(n => { const ex = map.get(n.id); if (ex && ex.read_at) return { ...n, read_at: ex.read_at }; return n; });
                for (const n of (curr || [])) if (!merged.find(m => m.id === n.id)) merged.push(n);
                return merged.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
              });
            } catch { }
          })();
        } else if (e?.data?.type === 'subscription_updated') {
          // Refetch subscription in case Billing page not mounted & show toast if not already billing view
          if (currentView !== 'billing') {
            toast({ title: 'Subscription Updated', description: `Plan changed to ${e.data.payload?.plan_key}`, duration: 5000 });
          }
        }
      };
    } catch { }
    const storageHandler = (ev) => {
      if (ev.key === 'ppp_last_checkout') {
        (async () => {
          try {
            const api = makeApi(token);
            const d = await api.get('/api/notifications/');
            setNotifications(curr => {
              const map = new Map((curr || []).map(n => [n.id, n]));
              const merged = (Array.isArray(d) ? d : []).map(n => { const ex = map.get(n.id); if (ex && ex.read_at) return { ...n, read_at: ex.read_at }; return n; });
              for (const n of (curr || [])) if (!merged.find(m => m.id === n.id)) merged.push(n);
              return merged.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0));
            });
          } catch { }
        })();
      }
    };
    window.addEventListener('storage', storageHandler);
    return () => { try { bc && bc.close(); } catch { } window.removeEventListener('storage', storageHandler); };
  }, [token, currentView, toast]);
  // Sync local user with auth context
  useEffect(() => { setUser(authUser); }, [authUser]);
  // Clear post-checkout flag once we've mounted and possibly navigated
  useEffect(() => { if (currentView === 'billing') { try { localStorage.removeItem('ppp_post_checkout'); } catch { } } }, [currentView]);

  const handleEditTemplate = (templateId) => {
    setSelectedTemplateId(templateId);
    setCurrentView('editTemplate');
  };

  const handleBackToDashboard = useCallback(() => {
    setSelectedTemplateId(null);
    setCreatorMode('standard');
    setCurrentView('dashboard');
    // Don't call fetchData here - the useEffect will handle it when currentView changes to 'dashboard'
  }, []);

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
      if (msg.toLowerCase().includes('at least one template')) {
        toast({ title: "Action needed", description: "Create another template before deleting your last one.", variant: "destructive" });
      } else {
        toast({ title: "Error", description: msg || 'Delete failed', variant: "destructive" });
      }
    }
  };

  // Memoize targetPodcast for websiteBuilder to prevent re-renders
  // Use podcast IDs string to detect actual changes, not array reference
  const podcastsIdsString = useMemo(() => {
    if (!podcasts || podcasts.length === 0) return '';
    return podcasts.map(p => p.id).sort().join(',');
  }, [podcasts]);

  // Create a stable map that only updates when podcast IDs actually change
  const podcastsMapRef = useRef(new Map());
  const lastPodcastsIdsStringRef = useRef('');

  if (podcastsIdsString !== lastPodcastsIdsStringRef.current) {
    // Podcasts actually changed, rebuild the map
    podcastsMapRef.current.clear();
    podcasts?.forEach(p => podcastsMapRef.current.set(p.id, p));
    lastPodcastsIdsStringRef.current = podcastsIdsString;
  }

  const targetPodcastForBuilder = useMemo(() => {
    if (currentView !== 'websiteBuilder') return null;
    if (!podcastsIdsString || podcastsMapRef.current.size === 0) return null;

    // Get first podcast ID from the map if no selection
    const firstPodcastId = selectedPodcastId || Array.from(podcastsMapRef.current.keys())[0];
    if (!firstPodcastId) return null;

    return podcastsMapRef.current.get(firstPodcastId) || null;
  }, [currentView, selectedPodcastId, podcastsIdsString]); // Only depend on IDs string, not array

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
                } catch { }
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
              } catch { }
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
              onViewHistory={() => setCurrentView('episodeHistory')}
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
      case 'websiteBuilder': {
        // Use memoized targetPodcast to prevent re-renders
        const targetPodcast = targetPodcastForBuilder;

        // Debug: Log when targetPodcast changes (dev only)
        if (import.meta.env.DEV && targetPodcast) {
          console.log('[Dashboard] Rendering websiteBuilder', {
            targetPodcastId: targetPodcast.id,
            targetPodcastName: targetPodcast.name,
            podcastsLength: podcasts?.length,
            selectedPodcastId,
            timestamp: Date.now()
          });
        }

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
              key={targetPodcast.id}
              token={token}
              podcast={targetPodcast}
              onBack={handleBackToDashboard}
            />
          </Suspense>
        );
      }
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
            {/* Onboarding nudge */}
            {(() => {
              let show = false;
              try {
                const completed = localStorage.getItem('ppp.onboarding.completed');
                show = !completed;
              } catch {}
              return show ? (
                <div className="rounded-lg border bg-amber-50 text-amber-900 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <div className="font-medium">Finish setting up your DoneCast onboarding</div>
                      <div className="text-sm">Complete intro/outro, distribution, and website to streamline episode creation.</div>
                    </div>
                    <a href="/onboarding" className="px-3 py-2 rounded bg-primary text-white">Resume</a>
                  </div>
                </div>
              ) : null;
            })()}
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
            <div className="space-y-6">
              {/* Create Episode Card */}
                <Card className="shadow-sm border border-gray-200">
                  <CardHeader className="pb-3">
                    <CardTitle className="text-lg">Create Episode</CardTitle>
                    <CardDescription>Create a new episode from your shows & templates.</CardDescription>
                  </CardHeader>
                  <CardContent className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
                    <div className="flex items-center gap-3 text-sm">
                      <button
                        onClick={() => setCurrentView('podcastManager')}
                        className="flex flex-col items-center gap-1 px-4 py-2 rounded-full border border-gray-300 hover:border-gray-400 hover:bg-gray-50 transition-colors cursor-pointer"
                        title="View all shows"
                      >
                        <div className="text-[11px] tracking-wide text-gray-500">Shows</div>
                        <div className="font-semibold text-gray-800">{podcasts.length}</div>
                      </button>
                      <button
                        onClick={() => setCurrentView('episodeHistory')}
                        className="flex flex-col items-center gap-1 px-4 py-2 rounded-full border border-gray-300 hover:border-gray-400 hover:bg-gray-50 transition-colors cursor-pointer"
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
                                try { await requestPreuploadRefresh(); } catch { }
                              }
                              setCurrentView('episodeStart');
                            }}
                          >
                            <Mic className="w-4 h-4 mr-2" />
                            Record or Upload Audio
                          </Button>
                          {preuploadItems.some((item) => item?.transcript_ready) && (
                            <Button
                              variant="green"
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
                                  try { await requestPreuploadRefresh(); } catch { }
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
                        <span className={`text-sm font-medium ${stats?.last_assembly_status === 'error' ? 'text-red-600' : stats?.last_assembly_status === 'success' ? 'text-green-600' : stats?.last_assembly_status === 'pending' ? 'text-amber-600' : 'text-gray-600'}`}>{formatAssemblyStatus(stats?.last_assembly_status)}</span>
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

                    {/* Recent Episodes Section */}
                    {Array.isArray(stats?.recent_episodes) && stats.recent_episodes.length > 0 && (
                      <div className="space-y-2">
                        <div className="text-xs font-semibold text-gray-500 uppercase tracking-wide mt-3">Most Recent Episodes</div>
                        {stats.recent_episodes.map((ep, idx) => (
                          <div key={ep.episode_id || idx} className="p-3 rounded border bg-white flex items-center justify-between">
                            <div className="flex items-center gap-2 flex-1 min-w-0">
                              <span className="text-[11px] tracking-wide text-gray-700 font-medium truncate" title={ep.title}>{ep.title}</span>
                            </div>
                            <div className="text-right ml-3 flex flex-col items-end">
                              <div className="text-base font-bold text-gray-900">{ep.downloads_all_time?.toLocaleString() || 0}</div>
                              <div className="text-[9px] text-gray-500">{formatRelative(ep.publish_at)}</div>
                            </div>
                          </div>
                        ))}
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
      } catch { }
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

      const firstTarget = document.querySelector('[data-tour-id="dashboard-record-upload"]');
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
    <>
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
        tooltipComponent={CustomTourTooltip}
      />
      <div className="min-h-screen bg-gray-50 flex">
        <DashboardSidebar
          navItems={navItems}
          activeView={currentView}
          onNavigate={handleSidebarNavigate}
          onLogout={logout}
        />
        <div className="flex-1 flex flex-col min-h-screen">
          <header className="border-b border-gray-200 bg-white px-4 lg:px-8 py-4 flex flex-col gap-4 md:flex-row md:items-center md:justify-between shadow-sm">
            <div className="flex items-center gap-3 flex-wrap">
              <Button
                variant="ghost"
                size="icon"
                className="lg:hidden"
                aria-label="Toggle navigation"
                onClick={() => setMobileMenuOpen((open) => !open)}
              >
                {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="text-sm"
                onClick={() => {
                  if (currentView !== 'dashboard') {
                    setCurrentViewWithHistory('dashboard');
                  }
                }}
                data-tour-id="dashboard-back-button"
              >
                <Home className="w-4 h-4 mr-2" />
                Dashboard
              </Button>
            </div>
            <div className="flex items-center gap-4">
              <div className="relative">
                <Button
                  variant="ghost"
                  size="sm"
                  className="relative"
                  onClick={() => setShowNotifPanel((v) => !v)}
                  aria-haspopup="true"
                  aria-expanded={showNotifPanel}
                >
                  <Bell className="w-5 h-5" />
                  {notifications.filter(n => !n.read_at).length > 0 && (
                    <Badge className="absolute -top-1 -right-1 h-5 w-5 rounded-full p-0 flex items-center justify-center bg-red-500 text-white text-xs">
                      {notifications.filter(n => !n.read_at).length}
                    </Badge>
                  )}
                </Button>
                {showNotifPanel && (
                  <div className="absolute right-0 mt-2 w-80 bg-white border border-gray-200 rounded shadow-lg z-50 max-h-96 overflow-auto">
                    <div className="p-3 font-semibold border-b flex items-center justify-between">
                      <span>Notifications</span>
                      {notifications.some(n => !n.read_at) && (
                        <button
                          className="text-xs text-blue-600 hover:underline"
                          onClick={async () => {
                            try {
                              const api = makeApi(token);
                              await api.post('/api/notifications/read-all');
                              setNotifications(curr => curr.map(n => n.read_at ? n : { ...n, read_at: new Date().toISOString() }));
                            } catch { }
                          }}
                        >Mark all read</button>
                      )}
                    </div>
                    {notifications.length === 0 && <div className="p-3 text-sm text-gray-500">No notifications</div>}
                    {notifications.map(n => (
                      <div
                        key={n.id}
                        className={`p-3 text-sm border-b last:border-b-0 flex flex-col gap-1 ${n.type === 'error' ? 'bg-red-50 border-red-200' : ''}`}
                      >
                        <div className="flex items-center justify-between">
                          <div className={`font-medium mr-2 truncate ${n.type === 'error' ? 'text-red-700' : ''}`}>{n.title}</div>
                          <div className="text-[11px] text-gray-500 whitespace-nowrap">{formatShort(n.created_at, resolvedTimezone)}</div>
                        </div>
                        {n.body && (
                          <div className={`text-xs ${n.type === 'error' ? 'text-red-600' : 'text-gray-600'}`}>{n.body}</div>
                        )}
                        {!n.read_at && (
                          <button
                            className="text-xs text-blue-600 self-start"
                            onClick={async () => {
                              try {
                                const api = makeApi(token);
                                await api.post(`/api/notifications/${n.id}/read`);
                                setNotifications(curr => curr.map(x => x.id === n.id ? { ...x, read_at: new Date().toISOString() } : x));
                              } catch { }
                            }}
                          >Mark read</button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <div className="flex items-center gap-3">
                {user?.picture ? (
                  <Avatar className="h-8 w-8">
                    <AvatarImage src={user.picture} />
                    <AvatarFallback>{user?.email ? user.email.substring(0, 2).toUpperCase() : '…'}</AvatarFallback>
                  </Avatar>
                ) : null}
                <span className="hidden md:block text-sm font-medium" style={{ color: "#2C3E50" }}>
                  {user ? user.email : 'Loading...'}
                </span>
              </div>
              {(authUser?.is_admin || authUser?.role === 'admin' || authUser?.role === 'superadmin') && (
                <Button onClick={() => window.location.href = '/dashboard?admin=1'} variant="ghost" size="sm" className="text-gray-600 hover:text-gray-800">
                  <SettingsIcon className="w-4 h-4 mr-1" />
                  <span className="hidden md:inline">Admin Panel</span>
                </Button>
              )}
              <Button onClick={logout} variant="ghost" size="sm" className="text-gray-600 hover:text-gray-800">
                <LogOut className="w-4 h-4 mr-1" />
                <span className="hidden md:inline">Logout</span>
              </Button>
            </div>
          </header>
          <main className="flex-1 overflow-y-auto px-4 sm:px-6 py-6">
            {renderCurrentView()}
          </main>
        </div>
        {mobileMenuOpen && (
          <>
            <div
              className="fixed inset-0 bg-black/50 z-40 lg:hidden"
              onClick={() => setMobileMenuOpen(false)}
            />
            <div className="fixed top-0 left-0 bottom-0 w-[280px] bg-white shadow-xl z-50 lg:hidden safe-top safe-bottom flex flex-col">
              <div className="p-4 border-b flex items-center justify-between">
                <Logo size={24} lockup />
                <Button variant="ghost" size="icon" onClick={() => setMobileMenuOpen(false)}>
                  <X className="w-5 h-5" />
                </Button>
              </div>
              <div className="p-4 space-y-2 overflow-y-auto flex-1">
                <Button
                  variant="outline"
                  className="w-full justify-start touch-target"
                  onClick={() => { jumpToView('dashboard'); setMobileMenuOpen(false); }}
                  data-tour-id="dashboard-back-button"
                >
                  <Home className="w-4 h-4 mr-2" />Dashboard
                </Button>
                {primaryNavItems.map((item) => (
                  <Button
                    key={item.id}
                    variant="outline"
                    className={`w-full justify-start touch-target ${item.disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
                    onClick={() => handleSidebarNavigate(item)}
                    disabled={item.disabled}
                    data-tour-id={item.tourId}
                  >
                    {item.icon && <item.icon className="w-4 h-4 mr-2" />}
                    {item.label}
                  </Button>
                ))}
                {supportNavItems.length > 0 && (
                  <div className="mt-8 pt-6 border-t border-dashed border-gray-200 space-y-2">
                    {supportNavItems.map((item) => (
                      <Button
                        key={item.id}
                        variant="outline"
                        className="w-full justify-start touch-target"
                        onClick={() => handleSidebarNavigate(item)}
                        data-tour-id={item.tourId}
                      >
                        {item.icon && <item.icon className="w-4 h-4 mr-2" />}
                        {item.label}
                      </Button>
                    ))}
                  </div>
                )}
                {(authUser?.is_admin || authUser?.role === 'admin' || authUser?.role === 'superadmin') && (
                  <Button
                    variant="outline"
                    className="w-full justify-start touch-target bg-purple-50 border-purple-200 text-purple-700 hover:bg-purple-100"
                    onClick={() => { window.location.href = '/dashboard?admin=1'; setMobileMenuOpen(false); }}
                  >
                    <SettingsIcon className="w-4 h-4 mr-2" />Admin Panel
                  </Button>
                )}
              </div>
              <div className="p-4 border-t">
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
      </div>
      <AIAssistant
        token={token}
        user={user}
        currentPage={currentView}
        onRestartTooltips={currentView === 'dashboard' ? handleRestartTooltips : null}
      />
    </>
  );
}

