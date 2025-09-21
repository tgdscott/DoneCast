import ProtectedRoute from "./components/common/ProtectedRoute.jsx";
import PodcastPublisherTool from "./components/dashboard/PodcastPublisherTool";
import React, { useEffect, useState } from 'react';
import { useAuth } from './AuthContext.jsx'; 
import { makeApi } from '@/lib/apiClient';
import PodcastPlusDashboard from '@/components/dashboard.jsx'; // The regular user dashboard
import OnboardingWizard from '@/components/onboarding/OnboardingWizard.jsx';
import Onboarding from '@/pages/Onboarding.jsx';
import AdminDashboard from '@/components/admin-dashboard.jsx'; // The new admin dashboard
import { useToast } from '@/hooks/use-toast';
import LandingPage from '@/components/landing-page.jsx';
import Settings from '@/components/dashboard/Settings.jsx'; // Import the Settings component
import ClosedAlphaGate from '@/components/ClosedAlphaGate.jsx';
import { Toaster } from '@/components/ui/toaster.jsx';
import MetaHead from '@/components/MetaHead.jsx';
import TermsGate from '@/components/common/TermsGate.jsx';

// --- IMPORTANT ---
// Admin is determined by backend role; no hard-coded emails.
const isAdmin = (user) => !!(user && (user.is_admin || user.role === 'admin'));

export default function App() {
    const { isAuthenticated, token, login, logout, user, refreshUser, hydrated } = useAuth(); 
    const [isLoading, setIsLoading] = useState(true);
    const [postCheckout, setPostCheckout] = useState(false);
    const [postCheckoutStartedAt, setPostCheckoutStartedAt] = useState(null);
    const { toast } = useToast();
    const [adminCheck, setAdminCheck] = useState({ checked: false, allowed: false });
    // Podcast existence check always declared so hooks order stable
    const [podcastCheck, setPodcastCheck] = React.useState({ loading: true, count: 0, fetched: false });

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
            // Detect checkout=success early (may arrive before AuthContext refresh completes)
            const searchParams = new URLSearchParams(window.location.search);
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
    }, [token, login]);

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
                    setPodcastCheck({ loading:false, count: items.length, fetched: true });
                }
            } catch { if(!cancelled) setPodcastCheck({ loading:false, count:0, fetched: true }); }
        })();
        return () => { cancelled = true; };
    }, [isAuthenticated, token, podcastCheck.fetched, hydrated]);

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

    // --- Render decisions (after all hooks declared) ---
    const path = window.location.pathname;
    if (!hydrated) return <div className="flex items-center justify-center h-screen">Loading...</div>;
    // If account is inactive, always show the closed alpha gate regardless of route
    if (user && user.is_active === false) {
        return <ClosedAlphaGate />;
    }
    if (path === '/dashboard/settings') return <Settings token={token} />;
    // If no token at all, immediately show landing (don't force user to wait for loading spinner)
    if (postCheckout && !isAuthenticated) {
        // If we already have a token, optimistic render dashboard root to allow normal flows
        if (token) {
            return <PodcastPlusDashboard />; // will internally hit APIs; if 401 occurs AuthContext will reset
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
    if (user) {
        // If the account is inactive, show the closed alpha gate page
        if (user.is_active === false) {
            return <ClosedAlphaGate />;
        }
        if (podcastCheck.loading) return <div className="flex items-center justify-center h-screen">Preparing your workspace...</div>;
        // Only show onboarding wizard if explicitly requested via query param and no podcasts exist
        const params = new URLSearchParams(window.location.search);
        const onboardingParam = params.get('onboarding');
        const forceOnboarding = onboardingParam === '1';
        const skipOnboarding = onboardingParam === '0' || params.get('skip_onboarding') === '1';
        const rawFullpage = import.meta.env?.VITE_ONBOARDING_FULLPAGE ?? import.meta.env?.ONBOARDING_FULLPAGE;
        const FULLPAGE = rawFullpage === undefined ? true : String(rawFullpage).toLowerCase() === 'true';
        if (!skipOnboarding) {
            if (FULLPAGE && (podcastCheck.count === 0 || forceOnboarding)) {
                return <Onboarding />;
            }
            if (!FULLPAGE && (podcastCheck.count === 0 || forceOnboarding)) {
                return <OnboardingWizard />;
            }
        }
        // If Terms require acceptance, gate here before dashboard/admin
        const requiredVersion = user?.terms_version_required;
        const acceptedVersion = user?.terms_version_accepted;
        if (requiredVersion && requiredVersion !== acceptedVersion) {
            return <TermsGate />;
        }
        // Admin gating: render Admin only after user is loaded and if checks pass
        if (isAdmin(user)) {
            if (!adminCheck.checked) return <div className="flex items-center justify-center h-screen">Checking admin access...</div>;
            if (adminCheck.allowed) return <AdminDashboard />;
            // If not allowed, fall through to regular dashboard
        }
        return <PodcastPlusDashboard />;
    }
        return <div className="flex items-center justify-center h-screen">Loading...</div>;
}

// Wrap export to always include single Toaster instance
export function AppWithToasterWrapper() {
    return <>
    <MetaHead />
        <App />
        <Toaster />
    </>;
}

