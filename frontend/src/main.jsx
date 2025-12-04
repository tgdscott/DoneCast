import "./shims/react-global.js";
import React, { Suspense } from 'react'
import { Loader2 } from 'lucide-react';
import './sentry.js'; // side-effect import for Sentry (no-op if DSN missing)
import ReactDOM from 'react-dom/client'

// Lazy load pages to improve initial bundle size
const AppWithToasterWrapper = React.lazy(() => import('./App.jsx').then(module => ({ default: module.AppWithToasterWrapper })));
const NotFound = React.lazy(() => import('@/pages/NotFound.jsx'));
const ErrorPage = React.lazy(() => import('@/pages/Error.jsx'));
const ABPreview = React.lazy(() => import('@/pages/ABPreview.jsx'));
const OnboardingDemo = React.lazy(() => import('@/pages/OnboardingDemo.jsx'));
const Onboarding = React.lazy(() => import('@/pages/Onboarding.jsx'));
const PrivacyPolicy = React.lazy(() => import('@/pages/PrivacyPolicy.jsx'));
const TermsOfUse = React.lazy(() => import('@/pages/TermsOfUse.jsx'));
const Legal = React.lazy(() => import('@/pages/Legal.jsx'));
const Verify = React.lazy(() => import('@/pages/Verify.jsx'));
const EmailVerification = React.lazy(() => import('@/pages/EmailVerification.jsx'));
const ResetPassword = React.lazy(() => import('@/pages/ResetPassword.jsx'));
const Pricing = React.lazy(() => import('@/pages/Pricing.jsx'));
const PublicPricing = React.lazy(() => import('@/pages/PublicPricing.jsx'));
const PodcastWebsiteBuilder = React.lazy(() => import('@/pages/PodcastWebsiteBuilder.jsx'));
const NewLanding = React.lazy(() => import('@/pages/NewLanding.jsx'));
const Signup = React.lazy(() => import('@/pages/Signup.jsx'));
const InDevelopment = React.lazy(() => import('@/pages/InDevelopment.jsx'));
const Contact = React.lazy(() => import('@/pages/Contact.jsx'));
const Guides = React.lazy(() => import('@/pages/Guides.jsx'));
const FAQ = React.lazy(() => import('@/pages/FAQ.jsx'));
const Features = React.lazy(() => import('@/pages/Features.jsx'));
const About = React.lazy(() => import('@/pages/About.jsx'));
const PublicWebsite = React.lazy(() => import('@/pages/PublicWebsite.jsx'));
const AIAssistantPopup = React.lazy(() => import('@/components/assistant/AIAssistantPopup.jsx'));
import { AuthProvider } from './AuthContext.jsx';
import { BrandProvider } from './brand/BrandContext.jsx';
import { ComfortProvider } from './ComfortContext.jsx';
import { LayoutProvider } from './layout/LayoutContext.jsx';
import { WarmupProvider } from './contexts/WarmupContext.jsx';
import { PostHogProvider } from 'posthog-js/react';
import './index.css' // <-- This line imports all the styles
import { assetUrl } from './lib/apiClient';
import { createBrowserRouter, RouterProvider, useSearchParams } from 'react-router-dom';

// Simple loading spinner for Suspense fallback
const PageLoader = () => (
  <div className="flex items-center justify-center h-screen w-full bg-white dark:bg-slate-950">
    <Loader2 className="h-8 w-8 animate-spin text-blue-600" />
  </div>
);

// Always show DEV background when running on localhost:5173 or 127.0.0.1:5173
try {
  if (
    typeof document !== 'undefined' &&
    (
      import.meta?.env?.DEV ||
      (window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost') && window.location.port === '5173'
    )
  ) {
    document.documentElement.classList.add('env-dev');
  }
} catch { }

// Runtime safeguard: some code (or older bundles) may call fetch('/api/...') expecting
// the API to be on a separate origin. If VITE_API_BASE is configured we should ensure
// these relative calls get routed to the API host rather than the SPA origin which
// would otherwise respond with index.html. We do this by wrapping window.fetch once.
try {
  if (typeof window !== 'undefined' && window.fetch) {
    const originalFetch = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      try {
        // Normalize input to a string path when possible
        const urlStr = typeof input === 'string' ? input : (input && input.url) || '';
        if (urlStr && (urlStr.startsWith('/api/') || urlStr === '/api' || urlStr.startsWith('/api?') || urlStr.startsWith('/api/'))) {
          const newUrl = assetUrl(urlStr);
          // If original input was a Request, clone it with the new URL
          if (input instanceof Request) {
            input = new Request(newUrl, input);
          } else {
            input = newUrl;
          }
        }
      } catch (e) {
        // If anything goes wrong, fall back to original behavior
      }
      return originalFetch(input, init);
    };
  }
} catch (err) {
  // ignore; this is a best-effort runtime shim
}

// --- One-time hash fragment token capture (e.g. from Google OAuth redirect) ---
// Expected format: #access_token=...&token_type=bearer
try {
  // Stable tab id for cross-navigation (session only)
  if (!sessionStorage.getItem('ppp_tab_id')) {
    sessionStorage.setItem('ppp_tab_id', Math.random().toString(36).slice(2));
  }
  if (window.location.hash && window.location.hash.includes('access_token=')) {
    // Normalize any accidental double-hash (e.g. '##access_token=...') produced by
    // older backend redirect logic. Browsers preserve the literal sequence so we
    // strip leading '#' characters beyond the first.
    let rawHash = window.location.hash;
    while (rawHash.startsWith('##')) rawHash = rawHash.slice(1);
    const params = new URLSearchParams(rawHash.substring(1));
    const accessToken = params.get('access_token');
    if (accessToken) {
      // Persist for subsequent tabs
      localStorage.setItem('authToken', accessToken);
      // Clean up visible hash (do not trigger a full reload)
      try { window.history.replaceState(null, '', window.location.pathname + window.location.search); } catch (_) { }
      // Dispatch a custom event so AuthProvider (already reading from localStorage) can optionally react.
      window.dispatchEvent(new CustomEvent('ppp-token-captured', { detail: { token: accessToken } }));
    }
  }
} catch (err) {
  // eslint-disable-next-line no-console
  console.warn('[auth] token capture failed', err);
}

// Helper to detect if this is a subdomain request (for public websites)
const isSubdomainRequest = () => {
  if (typeof window === 'undefined') return false;

  // Check for subdomain query parameter (allow in production for preview/debugging)
  // Use simple string check to avoid any URL parsing issues
  if (window.location.search && window.location.search.includes('subdomain=')) {
    return true;
  }

  const hostname = window.location.hostname;

  // Never treat localhost or IP addresses as subdomains (unless we have query param, handled above)
  if (hostname === 'localhost' || /^\d+\.\d+\.\d+\.\d+$/.test(hostname)) {
    return false;
  }

  const parts = hostname.split('.');

  // Check if subdomain exists (more than 2 parts) and not reserved
  if (parts.length < 3) return false;
  const subdomain = parts[0];
  const reserved = ['www', 'api', 'admin', 'app', 'dev', 'test', 'staging'];
  return !reserved.includes(subdomain);
};

// Wrapper component that checks subdomain at render time (not just router creation time)
const RootRouteElement = () => {
  const [searchParams] = useSearchParams();
  const previewSubdomain = searchParams.get('subdomain');

  // Check if we are on a subdomain OR if the user is requesting a preview via query param
  if (previewSubdomain || isSubdomainRequest()) {
    return <PublicWebsite />;
  }
  return <NewLanding />;
};

const router = createBrowserRouter([
  // Public website serving (subdomains) - check FIRST before other routes
  { path: '/', element: <RootRouteElement /> },
  { path: '/app', element: <AppWithToasterWrapper />, errorElement: <ErrorPage /> },
  { path: '/app/*', element: <AppWithToasterWrapper />, errorElement: <ErrorPage /> },
  { path: '/admin', element: <AppWithToasterWrapper />, errorElement: <ErrorPage /> },
  { path: '/admin/*', element: <AppWithToasterWrapper />, errorElement: <ErrorPage /> },
  { path: '/dashboard', element: <AppWithToasterWrapper />, errorElement: <ErrorPage /> },
  { path: '/dashboard/*', element: <AppWithToasterWrapper />, errorElement: <ErrorPage /> },
  { path: '/ab', element: <ABPreview /> },
  { path: '/onboarding-demo', element: <OnboardingDemo /> },
  { path: '/onboarding', element: <Onboarding /> },
  { path: '/error', element: <ErrorPage /> },
  { path: '/privacy', element: <PrivacyPolicy /> },
  { path: '/terms', element: <TermsOfUse /> },
  { path: '/legal', element: <Legal /> },
  { path: '/verify', element: <Verify /> },
  { path: '/email-verification', element: <EmailVerification /> },
  { path: '/reset-password', element: <ResetPassword /> },
  { path: '/signup', element: <Signup /> },
  { path: '/pricing', element: <Pricing /> },
  { path: '/pricing-public', element: <PublicPricing /> },
  { path: '/subscriptions', element: <Pricing /> },
  { path: '/contact', element: <Contact /> },
  { path: '/guides', element: <Guides /> },
  { path: '/help', element: <Guides /> },
  { path: '/faq', element: <FAQ /> },
  { path: '/features', element: <Features /> },
  { path: '/about', element: <About /> },
  { path: '/docs/podcast-website-builder', element: <PodcastWebsiteBuilder /> },
  { path: '/in-development', element: <InDevelopment /> },
  { path: '/mike', element: <AIAssistantPopup /> },
  // Fallback 404 for any unknown route
  { path: '*', element: <NotFound /> },
]);

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <PostHogProvider
      apiKey={import.meta.env.VITE_POSTHOG_KEY}
      options={{
        api_host: import.meta.env.VITE_POSTHOG_HOST,
        person_profiles: 'identified_only',
        capture_pageview: true,
        capture_pageleave: true,
        loaded: (posthog) => {
          if (import.meta.env.DEV) posthog.debug();
        },
      }}
    >
      <WarmupProvider>
        <AuthProvider>
          <ComfortProvider>
            <BrandProvider>
              <LayoutProvider>
                <Suspense fallback={<PageLoader />}>
                  <RouterProvider router={router} />
                </Suspense>
              </LayoutProvider>
            </BrandProvider>
          </ComfortProvider>
        </AuthProvider>
      </WarmupProvider>
    </PostHogProvider>
  </React.StrictMode>,
)