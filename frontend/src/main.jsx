import "./shims/react-global.js";
import React from 'react'
import './sentry.js'; // side-effect import for Sentry (no-op if DSN missing)
import ReactDOM from 'react-dom/client'
import App, { AppWithToasterWrapper } from './App.jsx'
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
import NotFound from '@/pages/NotFound.jsx';
import ErrorPage from '@/pages/Error.jsx';
import ABPreview from '@/pages/ABPreview.jsx';
import OnboardingDemo from '@/pages/OnboardingDemo.jsx';
import Onboarding from '@/pages/Onboarding.jsx';
import PrivacyPolicy from '@/pages/PrivacyPolicy.jsx';
import TermsOfUse from '@/pages/TermsOfUse.jsx';
import Verify from '@/pages/Verify.jsx';
import Pricing from '@/pages/Pricing.jsx';
import { AuthProvider } from './AuthContext.jsx';
import { BrandProvider } from './brand/BrandContext.jsx';
import { ComfortProvider } from './ComfortContext.jsx';
import { LayoutProvider } from './layout/LayoutContext.jsx';
import './index.css' // <-- This line imports all the styles
import { assetUrl } from './lib/apiClient';

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
  if(!sessionStorage.getItem('ppp_tab_id')) {
    sessionStorage.setItem('ppp_tab_id', Math.random().toString(36).slice(2));
  }
  if (window.location.hash && window.location.hash.includes('access_token=')) {
    const params = new URLSearchParams(window.location.hash.substring(1));
    const accessToken = params.get('access_token');
    if (accessToken) {
      // Persist for subsequent tabs
      localStorage.setItem('authToken', accessToken);
      // Clean up visible hash (do not trigger a full reload)
      try { window.history.replaceState(null, '', window.location.pathname + window.location.search); } catch(_) {}
      // Dispatch a custom event so AuthProvider (already reading from localStorage) can optionally react.
      window.dispatchEvent(new CustomEvent('ppp-token-captured', { detail: { token: accessToken }}));
    }
  }
} catch(err) {
  // eslint-disable-next-line no-console
  console.warn('[auth] token capture failed', err);
}

const router = createBrowserRouter([
  { path: '/', element: <AppWithToasterWrapper />, errorElement: <ErrorPage /> },
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
  { path: '/verify', element: <Verify /> },
  { path: '/pricing', element: <Pricing /> },
  { path: '/subscriptions', element: <Pricing /> },
  // Fallback 404 for any unknown route
  { path: '*', element: <NotFound /> },
]);

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <AuthProvider>
      <BrandProvider>
        <LayoutProvider>
          <ComfortProvider>
            <RouterProvider router={router} />
          </ComfortProvider>
        </LayoutProvider>
      </BrandProvider>
    </AuthProvider>
  </React.StrictMode>,
)

