import ProtectedRoute from "./components/common/ProtectedRoute.jsx";
import React, { useEffect, useState } from 'react';
import { useAuth } from './AuthContext.jsx'; 
import { makeApi } from '@/lib/apiClient';
import PodcastPlusDashboard from '@/components/dashboard.jsx'; // The regular user dashboard
import Onboarding from '@/pages/Onboarding.jsx';
import AdminDashboard from '@/components/admin-dashboard.jsx'; // The new admin dashboard
import { useToast } from '@/hooks/use-toast';
import { Button } from '@/components/ui/button';
import { AlertTriangle } from 'lucide-react';
import LandingPage from '@/components/landing-page.jsx';
import Settings from '@/components/dashboard/Settings.jsx'; // Import the Settings component
import ClosedAlphaGate from '@/components/ClosedAlphaGate.jsx';
import { Toaster } from '@/components/ui/toaster.jsx';
import MetaHead from '@/components/MetaHead.jsx';
import TermsGate from '@/components/common/TermsGate.jsx';
import AppAB from '@/ab/AppAB.jsx';
import { useLayout } from '@/layout/LayoutContext.jsx';
import BuildInfo from '@/components/admin/BuildInfo.jsx';
import { initBugReportCapture } from '@/lib/bugReportCapture.js'; // NEW: Bug reporting
import { WarmupLoader } from '@/components/WarmupLoader.jsx';
import { useWarmup } from '@/contexts/WarmupContext.jsx';

// --- IMPORTANT ---
// Admin is determined by backend role; no hard-coded emails.
const isAdmin = (user) => !!(user && (user.is_admin || user.role === 'admin'));

export default function App() {
    const { isAuthenticated, token, login, logout, user, refreshUser, hydrated, maintenanceInfo } = useAuth();
    const [isLoading, setIsLoading] = useState(true);
    const [postCheckout, setPostCheckout] = useState(false);
    const [postCheckoutStartedAt, setPostCheckoutStartedAt] = useState(null);
    const { toast } = useToast();
    const [adminCheck, setAdminCheck] = useState({ checked: false, allowed: false });
    // Podcast existence check always declared so hooks order stable
    const [podcastCheck, setPodcastCheck] = React.useState({ loading: true, count: 0, fetched: false, error: false });
    // Onboarding completion check - ensures user completed all 13 steps before dashboard access
    const [onboardingCheck, setOnboardingCheck] = React.useState({ loading: true, completed: false, fetched: false, error: false });
    const { layoutKey } = useLayout();

    // Initialize global bug report capture system (runs once at app start)
    useEffect(() => {
        initBugReportCapture();
    }, []);

    // Prevent back button from navigating away from the app (but allow internal navigation)
    useEffect(() => {
        if (!isAuthenticated || !hydrated) return;

        // Track when we first entered the authenticated app
        // Store this in sessionStorage so it persists across page reloads
        const APP_ENTRY_KEY = 'ppp_app_entry_url';
        let appEntryUrl = sessionStorage.getItem(APP_ENTRY_KEY);
        
        if (!appEntryUrl) {
            // First time entering the app - mark this as the entry point
            appEntryUrl = window.location.href;
            sessionStorage.setItem(APP_ENTRY_KEY, appEntryUrl);
            // Mark current state as being in the app
            window.history.replaceState({ inApp: true }, '', window.location.href);
        } else {
            // Already have an entry point - just mark current state
            if (!window.history.state?.inApp) {
                window.history.replaceState({ inApp: true }, '', window.location.href);
            }
        }

        const handlePopState = (event) => {
            const currentPath = window.location.pathname;
            const currentUrl = window.location.href;
            
            // Check if we're still in the app (internal routes)
            const isAppRoute = currentPath.startsWith('/app') || 
                              currentPath.startsWith('/dashboard') || 
                              currentPath.startsWith('/admin') ||
                              (currentPath === '/' && isAuthenticated);
            
            // If we're still in the app, allow the navigation (let React Router and dashboard handle it)
            if (isAppRoute) {
                // Check if this is a dashboard internal navigation (has dashboardView state)
                if (event.state?.dashboardView) {
                    // This is handled by dashboard's own popstate handler, don't interfere
                    return;
                }
                // If we're in an app route but don't have dashboardView, dashboard handler will fix it
                // Just ensure we mark inApp flag
                const currentState = window.history.state || {};
                if (!currentState.inApp) {
                    // Preserve dashboardView if it exists, otherwise let dashboard handler add it
                    window.history.replaceState({ ...currentState, inApp: true }, '', currentUrl);
                }
                return; // Allow normal navigation - dashboard handler will restore view if needed
            }
            
            // If we're navigating outside the app, redirect back to entry point
            // This prevents going back to external sites (like Google, etc.)
            const entryUrl = new URL(appEntryUrl);
            const targetPath = entryUrl.pathname || '/app';
            
            // Check if we're on the same domain - if so, use history API to avoid reload
            const currentHost = window.location.hostname;
            const entryHost = entryUrl.hostname;
            
            if (currentHost === entryHost || currentHost === 'localhost' || currentHost === '127.0.0.1') {
                // Same domain - use history API to navigate without reload
                window.history.pushState({ inApp: true, dashboardView: 'dashboard' }, '', targetPath);
                // Use a small timeout to let React Router process, then trigger navigation if needed
                setTimeout(() => {
                    // If we're still not on the right path, force it (shouldn't happen but safety net)
                    if (window.location.pathname !== targetPath) {
                        window.location.pathname = targetPath;
                    }
                }, 0);
            } else {
                // Different domain - must use full navigation to prevent leaving
                window.location.pathname = targetPath;
            }
        };

        // Use capture phase to run before React Router's handler
        window.addEventListener('popstate', handlePopState, true);
        return () => {
            window.removeEventListener('popstate', handlePopState, true);
        };
    }, [isAuthenticated, hydrated]);

    // Handle navigation messages from popped-out AI Assistant window
    useEffect(() => {
        const handleMessage = (event) => {
            // Verify origin for security
            if (event.origin !== window.location.origin) return;
            
            // Handle navigate message from AI Assistant popup
            if (event.data?.type === 'navigate' && event.data?.path) {
                window.location.href = event.data.path;
            }
        };

        window.addEventListener('message', handleMessage);
        return () => window.removeEventListener('message', handleMessage);
    }, []);

    useEffect(() => {
        const processAuth = async () => {
            const hash = window.location.hash;
            if (hash) {
                const params = new URLSearchParams(hash.substring(1));
                const urlToken = params.get('access_token');
                if (urlToken) {
                    login(urlToken);
                    window.location.hash = '';
                }
            }
            
            // Handle magic link token from email (query parameter)
            const searchParams = new URLSearchParams(window.location.search);
            const magicToken = searchParams.get('token');
            if (magicToken && !isAuthenticated) {
                try {
                    // Exchange magic link token for access token
                    const response = await fetch('/api/auth/magic-link', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ token: magicToken }),
                        credentials: 'include',
                    });
                    
                    if (response.ok) {
                        const data = await response.json();
                        if (data.access_token) {
                            login(data.access_token);
                            // Remove token from URL without reloading
                            const newUrl = new URL(window.location.href);
                            newUrl.searchParams.delete('token');
                            window.history.replaceState({}, '', newUrl.toString());
                        }
                    } else {
                        if (import.meta.env.DEV) console.warn('[App] Magic link token exchange failed:', response.status);
                        // Remove invalid token from URL
                        const newUrl = new URL(window.location.href);
                        newUrl.searchParams.delete('token');
                        window.history.replaceState({}, '', newUrl.toString());
                    }
                } catch (err) {
                    console.error('[App] Error exchanging magic link token:', err);
                    // Remove token from URL on error
                    const newUrl = new URL(window.location.href);
                    newUrl.searchParams.delete('token');
                    window.history.replaceState({}, '', newUrl.toString());
                }
            }
            
            // Detect checkout=success early (may arrive before AuthContext refresh completes)
            if (searchParams.get('checkout') === 'success') {
                setPostCheckout(true);
                setPostCheckoutStartedAt(Date.now());
                try { localStorage.setItem('ppp_post_checkout','1'); } catch {}
                // Clean query (keep path) after flag so reloads don't re-trigger
                // Defer query param cleanup so BillingPage can detect checkout=success and show toasts.
                // We'll let BillingPage clear it after processing.
                // try { window.history.replaceState(null,'', window.location.pathname); } catch {}
            }
            setIsLoading(false);
        };
        processAuth();
    }, [token, login, isAuthenticated]);

    // If we have postCheckout flag but not authenticated yet, poll user refresh a few times
    useEffect(() => {
        if (!postCheckout) return;
        if (isAuthenticated) return; // normal flow will proceed
    // Immediately try a forced refresh once (in case timing missed)
    refreshUser({ force: true });
        let attempts = 0;
        const id = setInterval(() => {
            attempts += 1;
            refreshUser({ force: true });
            if (attempts > 8) clearInterval(id); // ~8 attempts * 750ms ~ 6s
        }, 750);
        return () => clearInterval(id);
    }, [postCheckout, isAuthenticated, refreshUser]);
    // Fetch podcasts once after auth to decide onboarding vs dashboard (must be before any returns)
    useEffect(() => {
        if(!isAuthenticated || podcastCheck.fetched || !hydrated) return;
        let cancelled = false;
        (async () => {
            try {
                const api = makeApi(token);
                const data = await api.get('/api/podcasts/');
                if(!cancelled) {
                    const items = Array.isArray(data) ? data : (data.items || []);
                    setPodcastCheck({ loading:false, count: items.length, fetched: true, error: false });
                }
            } catch (err) {
                // If API call fails, don't assume user has no podcasts - they might have existing podcasts
                // Set error flag so we don't redirect to onboarding on API failures
                if(!cancelled) {
                    console.error('[App] Failed to fetch podcasts for onboarding check:', err);
                    setPodcastCheck({ loading:false, count: 0, fetched: true, error: true });
                }
            }
        })();
        return () => { cancelled = true; };
    }, [isAuthenticated, token, podcastCheck.fetched, hydrated]);

    // Check onboarding completion status - CRITICAL: Users MUST complete all 13 steps before dashboard access
    useEffect(() => {
        if(!isAuthenticated || onboardingCheck.fetched || !hydrated || !user) return;
        let cancelled = false;
        (async () => {
            try {
                const api = makeApi(token);
                const status = await api.get('/api/assistant/onboarding/status');
                if(!cancelled) {
                    setOnboardingCheck({ 
                        loading: false, 
                        completed: status.completed || false, 
                        fetched: true, 
                        error: false 
                    });
                }
            } catch (err) {
                // If API call fails, assume onboarding not complete (safer default)
                if(!cancelled) {
                    console.error('[App] Failed to check onboarding status:', err);
                    setOnboardingCheck({ loading: false, completed: false, fetched: true, error: true });
                }
            }
        })();
        return () => { cancelled = true; };
    }, [isAuthenticated, token, onboardingCheck.fetched, hydrated, user]);

    // Admin preflight: verify backend allows /api/admin/* before rendering AdminDashboard
    useEffect(() => {
        let cancelled = false;
        (async () => {
            setAdminCheck(prev => ({...prev, checked: false, allowed: false}));
            if (!isAuthenticated || !hydrated || !user || !isAdmin(user)) { setAdminCheck({ checked: true, allowed: false }); return; }
            try {
                const api = makeApi(token);
                await api.get('/api/admin/summary');
                if (!cancelled) setAdminCheck({ checked: true, allowed: true });
            } catch (e) {
                if (!cancelled) {
                    setAdminCheck({ checked: true, allowed: false });
                    // If backend denies, inform and fall back
                    toast({ title: 'Admin access denied', description: 'Falling back to dashboard.' });
                }
            }
        })();
        return () => { cancelled = true; };
    }, [isAuthenticated, token, user, hydrated]);

    // Global error handler for AI Assistant
    useEffect(() => {
        const handleError = (event) => {
            // Dispatch custom event that AIAssistant listens for
            window.dispatchEvent(new CustomEvent('ppp:error-occurred', {
                detail: {
                    message: event.message || 'An error occurred',
                    stack: event.error?.stack,
                    filename: event.filename,
                    lineno: event.lineno,
                    colno: event.colno,
                    timestamp: Date.now(),
                    type: 'uncaught'
                }
            }));
        };

        const handleUnhandledRejection = (event) => {
            // Also catch unhandled promise rejections
            window.dispatchEvent(new CustomEvent('ppp:error-occurred', {
                detail: {
                    message: event.reason?.message || 'Unhandled promise rejection',
                    stack: event.reason?.stack,
                    timestamp: Date.now(),
                    type: 'unhandled-rejection'
                }
            }));
        };

        window.addEventListener('error', handleError);
        window.addEventListener('unhandledrejection', handleUnhandledRejection);

        return () => {
            window.removeEventListener('error', handleError);
            window.removeEventListener('unhandledrejection', handleUnhandledRejection);
        };
    }, []);

    // --- Render decisions (after all hooks declared) ---
    const path = window.location.pathname;
    if (!hydrated) return <div className="flex items-center justify-center h-screen">Loading...</div>;
    if (maintenanceInfo) {
        const message = maintenanceInfo.message || maintenanceInfo.detail?.message || maintenanceInfo.detail?.detail || 'We are performing scheduled maintenance and will be back soon.';
        return (
            <div className="min-h-screen w-full flex flex-col items-center justify-center bg-slate-950 text-white px-6 text-center space-y-6">
                <AlertTriangle className="w-14 h-14 text-amber-400" />
                <div className="text-3xl font-semibold">We'll be right back</div>
                <p className="max-w-md text-sm text-slate-200">{message}</p>
                <div className="flex flex-wrap items-center justify-center gap-3">
                    <Button size="sm" onClick={() => refreshUser({ force: true })}>Try Again</Button>
                    <Button size="sm" variant="outline" className="text-white border-white/40 hover:bg-white/10" onClick={logout}>Sign Out</Button>
                </div>
                <p className="text-xs text-slate-400 max-w-sm">Admins can still sign in to toggle maintenance mode off.</p>
            </div>
        );
    }
    // If account is inactive, always show the closed alpha gate regardless of route
    if (user && user.is_active === false) {
        return <ClosedAlphaGate />;
    }
    if (path === '/dashboard/settings') return <Settings token={token} />;
    // If no token at all, immediately show landing (don't force user to wait for loading spinner)
    if (postCheckout && !isAuthenticated) {
        // If we already have a token, optimistic render dashboard root to allow normal flows
        if (token) {
            return layoutKey === 'ab' ? <AppAB token={token} /> : <PodcastPlusDashboard />; // will internally hit APIs; if 401 occurs AuthContext will reset
        }
        const elapsed = postCheckoutStartedAt ? Date.now() - postCheckoutStartedAt : 0;
        return <div className="flex flex-col items-center justify-center h-screen space-y-4">
            <div className="text-xl font-semibold">Finalizing your purchase...</div>
            <div className="text-gray-500 text-sm">This will update automatically.</div>
            {elapsed > 8000 && <>
                <div className="text-xs text-red-500">Still working... you can manually sign back in if this persists.</div>
                <button onClick={()=>{ try { window.location.href='/?login=1'; } catch{} }} className="text-xs text-blue-600 underline">Open sign-in modal</button>
            </>}
        </div>;
    }
    if (!isAuthenticated && !token) return <LandingPage />;
    if (isLoading) return <div className="flex items-center justify-center h-screen">Loading...</div>;
    if (!isAuthenticated) return <LandingPage />;
    
    // CRITICAL: Wait for AuthContext to hydrate before making routing decisions
    // This prevents race conditions where we render based on stale/null user data
    // (e.g., after email verification when user is freshly logged in)
    if (isAuthenticated && !hydrated) {
        return <div className="flex items-center justify-center h-screen">Preparing your account...</div>;
    }
    
    if (user) {
        // If the account is inactive, show the closed alpha gate page
        if (user.is_active === false) {
            return <ClosedAlphaGate />;
        }
        if (podcastCheck.loading) return <div className="flex items-center justify-center h-screen">Preparing your workspace...</div>;
        
        // CRITICAL: Wait for podcast check AND onboarding check to complete before making routing decisions
        // This prevents false positives when API calls are still in progress or have failed
        if (!podcastCheck.fetched || !onboardingCheck.fetched) {
            return <div className="flex items-center justify-center h-screen">Preparing your workspace...</div>;
        }
        
        // CRITICAL: Check onboarding FIRST before anything else (including ToS)
        // This ensures new users who just verified their email go through onboarding
        const params = new URLSearchParams(window.location.search);
        const onboardingParam = params.get('onboarding');
        const forceOnboarding = onboardingParam === '1';
        const skipOnboarding = onboardingParam === '0' || params.get('skip_onboarding') === '1';
        const justVerified = params.get('verified') === '1';
        
        // Skip onboarding for admin users - they should have direct access to dashboard/admin panel
        const userIsAdmin = isAdmin(user);
        
        // CRITICAL: Users MUST complete all 13 onboarding steps before accessing dashboard
        // This checks backend status: has podcast, has template, AND terms accepted
        // EXCEPTION: Admin users skip onboarding regardless of completion status
        // IMPORTANT: Only redirect if we've successfully fetched onboarding status
        // If API call failed (error: true), don't redirect - assume user might have completed onboarding
        // CRITICAL: If forceOnboarding is set (e.g., from reset), always show onboarding regardless of completion status
        if (
            (onboardingCheck.fetched && 
            !onboardingCheck.error && 
            !onboardingCheck.completed && 
            !skipOnboarding && 
            !userIsAdmin) ||
            (forceOnboarding && !skipOnboarding && !userIsAdmin)
        ) {
            if (import.meta.env.DEV) {
                console.log('[App] Redirecting to onboarding - user has not completed all 13 steps or forced onboarding');
            }
            return <Onboarding />;
        }
        
        // CRITICAL: Users with ZERO podcasts MUST complete onboarding - no escape routes
        // This ensures every user creates at least one podcast before accessing dashboard
        // EXCEPTION: Admin users skip onboarding regardless of podcast count
        // IMPORTANT: Only redirect if we've successfully fetched podcasts AND count is 0
        // This prevents redirecting users with existing podcasts due to API errors
        // If API call failed (error: true), don't redirect - assume user might have podcasts
        if (podcastCheck.fetched && !podcastCheck.error && podcastCheck.count === 0 && !skipOnboarding && !userIsAdmin) {
            return <Onboarding />;
        }
        
        // Honor a persisted completion flag so users who chose to skip aren't forced back into onboarding
        let completedFlag = false;
        try { completedFlag = localStorage.getItem('ppp.onboarding.completed') === '1'; } catch {}
        
        // Users with podcasts OR just verified their email OR explicitly requested onboarding
        // should go through onboarding BEFORE seeing ToS or dashboard
        // EXCEPTION: Admin users skip onboarding regardless of verification status
        if (!skipOnboarding && !completedFlag && !userIsAdmin && (forceOnboarding || justVerified)) {
            return <Onboarding />;
        }
        
        // CRITICAL: Terms acceptance check - MUST happen AFTER onboarding check
        // Terms are the LAST step (step 13) of onboarding, so users must complete onboarding first
        // If Terms require acceptance, gate here AFTER onboarding check
        // CRITICAL: Only check if user data is hydrated (fresh from backend)
        // This prevents showing gate with stale data after user accepts terms
        const requiredVersion = user?.terms_version_required;
        const acceptedVersion = user?.terms_version_accepted;
        
        // Debug logging to track Terms bypass issues (dev only to avoid console spam)
        if (import.meta.env.DEV && requiredVersion) {
            console.log('[TermsGate Check]', {
                email: user?.email,
                requiredVersion,
                acceptedVersion,
                match: requiredVersion === acceptedVersion,
                shouldShowGate: !!(requiredVersion && requiredVersion !== acceptedVersion),
                hydrated: hydrated
            });
        }
        
        // CRITICAL: Block access if terms not accepted (strict comparison)
        // Only enforce if:
        // 1. User data is hydrated (fresh from backend)
        // 2. requiredVersion is set AND is a non-empty string
        // 3. requiredVersion differs from acceptedVersion
        // This prevents:
        // - Blocking users when TERMS_VERSION isn't configured (requiredVersion is null/empty)
        // - Showing gate with stale data before refresh completes
        // - Pestering users who already accepted terms
        if (
            hydrated && // Only check with fresh data
            requiredVersion && 
            typeof requiredVersion === 'string' && 
            requiredVersion.trim() !== '' && 
            requiredVersion !== acceptedVersion
        ) {
            if (import.meta.env.DEV) {
                console.warn('[TermsGate] Blocking user - terms acceptance required:', {
                    email: user?.email,
                    required: requiredVersion,
                    accepted: acceptedVersion
                });
            }
            return <TermsGate />;
        }
        
        // Admin gating: SUPERADMINS start on admin dashboard, regular admins start on user dashboard
        // CRITICAL: Allow opt-in/opt-out via ?admin=1 (force admin view) or ?view=user (force user view)
        const urlParams = new URLSearchParams(window.location.search);
        const forceAdminView = urlParams.get('admin') === '1';
        const forceUserView = urlParams.get('admin') === '0' || urlParams.get('view') === 'user';
        
        const isSuperAdmin = user?.role === 'superadmin';
        const isRegularAdmin = user?.role === 'admin' || (user?.is_admin && !isSuperAdmin);
        
        // Superadmins: Default to admin dashboard (unless ?view=user)
        if (isSuperAdmin && !forceUserView) {
            if (!adminCheck.checked) return <div className="flex items-center justify-center h-screen">Checking admin access...</div>;
            if (adminCheck.allowed) return <AdminDashboard />;
            // If not allowed, fall through to regular dashboard
        }
        
        // Regular admins: Default to user dashboard (unless ?admin=1)
        if (isRegularAdmin && forceAdminView) {
            if (!adminCheck.checked) return <div className="flex items-center justify-center h-screen">Checking admin access...</div>;
            if (adminCheck.allowed) return <AdminDashboard />;
            // If not allowed, fall through to regular dashboard
        }
        
        return layoutKey === 'ab' ? <AppAB token={token} /> : <PodcastPlusDashboard />;
    }
        return <div className="flex items-center justify-center h-screen">Loading...</div>;
}

// Wrap export to always include single Toaster instance
export function AppWithToasterWrapper() {
    const { isWarmingUp } = useWarmup();
    return <>
    <MetaHead />
        <App />
        <BuildInfo />
        <WarmupLoader isVisible={isWarmingUp} />
        <Toaster />
    </>;
}
