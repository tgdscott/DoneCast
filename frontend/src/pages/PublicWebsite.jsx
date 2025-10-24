import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { getSectionPreviewComponent } from '../components/website/sections/SectionPreviews';

export default function PublicWebsite() {
  const [websiteData, setWebsiteData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const navigate = useNavigate();

  useEffect(() => {
    async function loadWebsite() {
      try {
        // Extract subdomain from hostname
        const hostname = window.location.hostname;
        console.log('[PublicWebsite] Current hostname:', hostname);
        
        // Parse subdomain (e.g., "cinema-irl" from "cinema-irl.podcastplusplus.com")
        const parts = hostname.split('.');
        
        // Check if this is a subdomain request (not the root domain)
        if (parts.length < 3) {
          console.log('[PublicWebsite] Not a subdomain, redirecting to dashboard');
          navigate('/dashboard');
          return;
        }
        
        const subdomain = parts[0];
        console.log('[PublicWebsite] Detected subdomain:', subdomain);
        
        // Check for reserved subdomains that shouldn't serve websites
        const reserved = ['www', 'api', 'admin', 'app', 'dev', 'test', 'staging'];
        if (reserved.includes(subdomain)) {
          console.log('[PublicWebsite] Reserved subdomain, redirecting');
          navigate('/dashboard');
          return;
        }
        
        // Fetch website data from API
        const apiBase = import.meta.env.VITE_API_BASE || 
                       (window.location.hostname === 'localhost' ? 'http://127.0.0.1:8000' : '');
        
        // Try published endpoint first
        let response = await fetch(`${apiBase}/api/sites/${subdomain}`);
        
        // If not published, try preview endpoint (shows draft websites)
        if (!response.ok && response.status === 404) {
          console.log('[PublicWebsite] Published website not found, trying preview...');
          response = await fetch(`${apiBase}/api/sites/${subdomain}/preview`);
        }
        
        if (!response.ok) {
          if (response.status === 404) {
            const errorData = await response.json();
            throw new Error(errorData.error?.message || 'Website not found');
          }
          throw new Error(`Failed to load website: ${response.status}`);
        }
        
        const data = await response.json();
        console.log('[PublicWebsite] Loaded website data:', data);
        setWebsiteData(data);
        
      } catch (err) {
        console.error('[PublicWebsite] Error loading website:', err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    
    loadWebsite();
  }, [navigate]);

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
      document.head.appendChild(styleTag);

      console.log('[PublicWebsite] Injected custom CSS');

      // Cleanup on unmount
      return () => {
        const tag = document.getElementById('podcast-website-custom-css');
        if (tag) {
          tag.remove();
        }
      };
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
            onClick={() => window.location.href = 'https://podcastplusplus.com'}
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-purple-600 hover:bg-purple-700"
          >
            Go to Podcast Plus Plus
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
    <div className="min-h-screen bg-white flex flex-col">
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
            />;
          })()}
        </div>
      )}

      {/* Main Content Sections */}
      <main className="flex-1">
        {contentSections.map((section) => {
          const SectionComponent = getSectionPreviewComponent(section.id);
          
          if (!SectionComponent) {
            console.warn(`[PublicWebsite] No component found for section ID: ${section.id}`);
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
              cover_url: websiteData.podcast_cover_url,
              rss_url: websiteData.podcast_rss_feed_url,
            },
          };
          
          // Add episodes for sections that display them
          if (section.id === 'latest-episodes' || section.id === 'episodes') {
            sectionProps.episodes = websiteData.episodes || [];
          }
          
          return <SectionComponent {...sectionProps} />;
        })}
      </main>
      
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
        /* Default Podcast Plus Plus branding footer */
        <footer className="bg-slate-900 text-white py-8">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
            <p className="text-sm text-slate-400">
              Powered by{' '}
              <a 
                href="https://podcastplusplus.com" 
                target="_blank" 
                rel="noopener noreferrer"
                className="text-purple-400 hover:text-purple-300 transition-colors"
              >
                Podcast Plus Plus
              </a>
            </p>
          </div>
        </footer>
      )}
    </div>
  );
}
