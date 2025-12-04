import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getSectionPreviewComponent } from '../components/website/sections/SectionPreviews';
import PersistentPlayer from '../components/website/PersistentPlayer';

export default function PublicWebsite() {
  const [websiteData, setWebsiteData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    async function loadWebsite() {
      try {
        // Get subdomain from query param (for dev mode) or hostname (for production)
        const searchParams = new URL(window.location.href).searchParams;
        const previewSubdomain = searchParams.get('subdomain'); // For dev preview mode

        let subdomain = null;

        // Allow subdomain via query param (production or dev)
        if (previewSubdomain) {
          subdomain = previewSubdomain;
          if (import.meta.env.DEV) console.log('[PublicWebsite] Using subdomain from query param:', subdomain);
        } else {
          // Extract subdomain from hostname (production mode)
          const hostname = window.location.hostname;
          if (import.meta.env.DEV) console.log('[PublicWebsite] Current hostname:', hostname);

          // Parse subdomain (e.g., "cinema-irl" from "cinema-irl.donecast.com")
          const parts = hostname.split('.');

          // Check if this is a subdomain request (not the root domain)
          if (parts.length < 3) {
            if (import.meta.env.DEV) console.log('[PublicWebsite] Not a subdomain, redirecting to dashboard');
            navigate('/dashboard');
            return;
          }

          subdomain = parts[0];
          if (import.meta.env.DEV) console.log('[PublicWebsite] Detected subdomain:', subdomain);

          // Check for reserved subdomains that shouldn't serve websites
          const reserved = ['www', 'api', 'admin', 'app', 'dev', 'test', 'staging'];
          if (reserved.includes(subdomain)) {
            if (import.meta.env.DEV) console.log('[PublicWebsite] Reserved subdomain, redirecting');
            navigate('/dashboard');
            return;
          }
        }

        if (!subdomain) {
          if (import.meta.env.DEV) console.log('[PublicWebsite] No subdomain found');
          navigate('/dashboard');
          return;
        }

        // Fetch website data from API
        let apiBase = import.meta.env.VITE_API_BASE ||
          (window.location.hostname === 'localhost' ? 'http://127.0.0.1:8000' : '');

        // Fix for double /api/api issue
        if (apiBase && apiBase.endsWith('/api')) {
          apiBase = apiBase.slice(0, -4);
        }
        if (apiBase && apiBase.endsWith('/')) {
          apiBase = apiBase.slice(0, -1);
        }

        // In dev mode with query param, always use preview endpoint
        // In production, try published first, then preview
        let response;
        if (import.meta.env.DEV && searchParams.get('subdomain')) {
          if (import.meta.env.DEV) console.log('[PublicWebsite] Dev mode: using preview endpoint');
          response = await fetch(`${apiBase}/api/sites/${subdomain}/preview`);
        } else {
          // Try published endpoint first
          response = await fetch(`${apiBase}/api/sites/${subdomain}`);

          // If not published, try preview endpoint (shows draft websites)
          if (!response.ok && response.status === 404) {
            if (import.meta.env.DEV) console.log('[PublicWebsite] Published website not found, trying preview...');
            response = await fetch(`${apiBase}/api/sites/${subdomain}/preview`);
          }
        }

        if (!response.ok) {
          if (response.status === 404) {
            const errorData = await response.json();
            throw new Error(errorData.error?.message || 'Website not found');
          }
          throw new Error(`Failed to load website: ${response.status}`);
        }

        const data = await response.json();

        // Debug logging (dev only)
        if (import.meta.env.DEV) {
          const episodeCount = data.episodes?.length || 0;
          console.log('========================================');
          console.log('[PublicWebsite] EPISODE COUNT:', episodeCount);
          console.log('[PublicWebsite] Episode 200 exists?', episodeCount >= 200);
          console.log('[PublicWebsite] Episode 204 exists?', episodeCount >= 204);
          if (episodeCount > 0) {
            console.log('[PublicWebsite] First episode:', data.episodes[0]?.title);
            console.log('[PublicWebsite] Last episode:', data.episodes[episodeCount - 1]?.title);
          }
          console.log('[PublicWebsite] Podcast cover_url:', data.podcast_cover_url);
          console.log('[PublicWebsite] Sections:', data.sections?.map(s => s.id) || []);
          console.log('========================================');
        }
        setWebsiteData(data);

      } catch (err) {
        // Always log errors, but keep them minimal in production
        if (import.meta.env.DEV) {
          console.error('[PublicWebsite] Error loading website:', err);
        } else {
          console.error('[PublicWebsite] Error loading website');
        }
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }

    loadWebsite();
  }, [navigate]); // Only depend on navigate, URL changes will trigger reload

  // Inject custom CSS when website data is loaded
  useEffect(() => {
    if (websiteData?.global_css) {
      // Remove any existing custom style tag
      const existingStyle = document.getElementById('podcast-website-custom-css');
      if (existingStyle) {
        existingStyle.remove();
      }

      // Create and inject new style tag
      const styleTag = document.createElement('style');
      styleTag.id = 'podcast-website-custom-css';
      styleTag.textContent = websiteData.global_css;
      // Insert at the end of head to ensure it overrides other styles
      // If Tailwind is loaded, insert after it
      const tailwindLink = document.querySelector('link[href*="tailwind"]');
      if (tailwindLink && tailwindLink.nextSibling) {
        document.head.insertBefore(styleTag, tailwindLink.nextSibling);
      } else {
        document.head.appendChild(styleTag);
      }

      if (import.meta.env.DEV) {
        console.log('[PublicWebsite] Injected custom CSS, length:', websiteData.global_css.length);
        console.log('[PublicWebsite] CSS preview:', websiteData.global_css.substring(0, 500));

        // Debug: Check if CSS variables are defined
        const rootStyles = window.getComputedStyle(document.documentElement);
        console.log('[PublicWebsite] CSS Variables:', {
          '--primary': rootStyles.getPropertyValue('--primary'),
          '--bg': rootStyles.getPropertyValue('--bg'),
          '--text': rootStyles.getPropertyValue('--text'),
        });
      }

      // Cleanup on unmount
      return () => {
        const tag = document.getElementById('podcast-website-custom-css');
        if (tag) {
          tag.remove();
        }
      };
    } else {
      if (import.meta.env.DEV) console.warn('[PublicWebsite] No global_css found in website data');
    }
  }, [websiteData]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600"></div>
          <p className="mt-4 text-slate-600">Loading website...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 px-4">
        <div className="text-center max-w-md">
          <div className="text-6xl mb-4">🤷</div>
          <h1 className="text-2xl font-bold text-slate-900 mb-2">Website Not Found</h1>
          <p className="text-slate-600 mb-6">{error}</p>
          <button
            onClick={() => window.location.href = 'https://donecast.com'}
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-purple-600 hover:bg-purple-700"
          >
            Go to DoneCast
          </button>
        </div>
      </div>
    );
  }

  if (!websiteData) {
    return null;
  }

  // Separate header, footer, and content sections
  const headerSection = websiteData.sections.find(s => s.id === 'header');
  const footerSection = websiteData.sections.find(s => s.id === 'footer');
  const contentSections = websiteData.sections.filter(s => s.id !== 'header' && s.id !== 'footer');

  return (
    <div className="min-h-screen flex flex-col" style={{ background: 'var(--bg, white)', color: 'var(--text, #1e293b)' }}>
      {/* Sticky Header */}
      {headerSection && (
        <div className="sticky top-0 z-50">
          {(() => {
            const HeaderComponent = getSectionPreviewComponent('header');
            return <HeaderComponent
              config={headerSection.config}
              enabled={headerSection.enabled}
              podcast={{
                id: websiteData.podcast_id,
                title: websiteData.podcast_title,
                description: websiteData.podcast_description,
                cover_url: websiteData.podcast_cover_url,
                rss_url: websiteData.podcast_rss_feed_url,
              }}
              pages={websiteData.pages || []}
            />;
          })()}
        </div>
      )}

      {/* Main Content Sections */}
      <main className="flex-1 pb-20">
        {contentSections.map((section) => {
          const SectionComponent = getSectionPreviewComponent(section.id);

          if (!SectionComponent) {
            if (import.meta.env.DEV) console.warn(`[PublicWebsite] No component found for section ID: ${section.id}`);
            return null;
          }

          // Pass episode data to sections that need it
          const sectionProps = {
            key: section.id,
            config: section.config,
            enabled: section.enabled,
            podcast: {
              id: websiteData.podcast_id,
              title: websiteData.podcast_title,
              description: websiteData.podcast_description,
              cover_url: websiteData.podcast_cover_url, // This MUST be passed for hero section
              rss_url: websiteData.podcast_rss_feed_url,
            },
          };

          // Debug logging for hero section (dev only)
          if (import.meta.env.DEV && section.id === 'hero') {
            console.log('[PublicWebsite] Hero section config:', section.config);
            console.log('[PublicWebsite] Podcast cover_url being passed:', websiteData.podcast_cover_url);
            console.log('[PublicWebsite] Podcast object:', sectionProps.podcast);
          }

          // Add episodes for sections that display them
          if (section.id === 'latest-episodes' || section.id === 'episodes') {
            // Add podcast_title to each episode for the player
            const episodesWithPodcast = (websiteData.episodes || []).map(ep => ({
              ...ep,
              podcast_title: websiteData.podcast_title
            }));
            sectionProps.episodes = episodesWithPodcast;
            if (import.meta.env.DEV) console.log(`[PublicWebsite] ${section.id} section - episodes count:`, episodesWithPodcast.length);
          }

          return (
            <div data-section-id={section.id} key={section.id}>
              <SectionComponent {...sectionProps} />
            </div>
          );
        })}
      </main>

      {/* Persistent Audio Player - Always visible at bottom */}
      <div style={{ position: 'relative', zIndex: 1 }}>
        <PersistentPlayer />
      </div>

      {/* Footer Section */}
      {footerSection ? (
        (() => {
          const FooterComponent = getSectionPreviewComponent('footer');
          return <FooterComponent
            config={footerSection.config}
            enabled={footerSection.enabled}
            podcast={{
              id: websiteData.podcast_id,
              title: websiteData.podcast_title,
              description: websiteData.podcast_description,
              cover_url: websiteData.podcast_cover_url,
              rss_url: websiteData.podcast_rss_feed_url,
            }}
          />;
        })()
      ) : (
        /* Default DoneCast branding footer */
        <footer className="bg-slate-900 text-white py-8">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
            <p className="text-sm text-slate-400">
              Powered by{' '}
              <a
                href="https://donecast.com"
                target="_blank"
                rel="noopener noreferrer"
                className="text-purple-400 hover:text-purple-300 transition-colors"
              >
                DoneCast
              </a>
            </p>
          </div>
        </footer>
      )}
    </div>
  );
}
