/**
 * Local Website Preview Component
 * Renders the website locally using the same components as PublicWebsite
 * Fetches data from the preview endpoint to ensure it matches the published site exactly
 * 
 * This allows testing website changes locally without publishing
 */

import { useEffect, useState } from 'react';
import { getSectionPreviewComponent } from './sections/SectionPreviews';
import PersistentPlayer from './PersistentPlayer';

export default function LocalWebsitePreview({ 
  website, 
  sections, 
  sectionsConfig, 
  sectionsEnabled, 
  podcast, 
  episodes = [],
  onClose,
  token
}) {
  const [previewData, setPreviewData] = useState(null);
  const [loadingPreview, setLoadingPreview] = useState(true);

  // Fetch preview data from API to ensure it matches published site exactly
  useEffect(() => {
    if (!website?.subdomain) return;

    const fetchPreviewData = async () => {
      try {
        const apiBase = import.meta.env.VITE_API_BASE || 
                       (window.location.hostname === 'localhost' ? 'http://127.0.0.1:8000' : '');
        
        const response = await fetch(`${apiBase}/api/sites/${website.subdomain}/preview`, {
          headers: { 'Authorization': `Bearer ${token}` },
        });
        
        if (response.ok) {
          const data = await response.json();
          setPreviewData(data);
          console.log('[LocalPreview] Loaded preview data from API, CSS length:', data.global_css?.length || 0);
        } else {
          console.error('[LocalPreview] Failed to fetch preview data:', response.status);
          // Fallback to using editor state if API fails
          setPreviewData(null);
        }
      } catch (err) {
        console.error('[LocalPreview] Error fetching preview data:', err);
        // Fallback to using editor state if API fails
        setPreviewData(null);
      } finally {
        setLoadingPreview(false);
      }
    };

    fetchPreviewData();
  }, [website?.subdomain, token]);

  // Inject global CSS from preview data (or fallback to website object)
  useEffect(() => {
    const cssToInject = previewData?.global_css || website?.global_css;
    
    if (cssToInject) {
      // Remove any existing style tag we added
      const existingStyle = document.getElementById('local-website-preview-css');
      if (existingStyle) {
        existingStyle.remove();
      }
      
      // Add the CSS
      const style = document.createElement('style');
      style.id = 'local-website-preview-css';
      style.textContent = cssToInject;
      // Insert at end of head to ensure it overrides other styles
      document.head.appendChild(style);
      
      console.log('[LocalPreview] Injected CSS, length:', cssToInject.length);
      console.log('[LocalPreview] CSS source:', previewData ? 'API preview endpoint' : 'Editor state');
      console.log('[LocalPreview] CSS preview:', cssToInject.substring(0, 300));
      
      return () => {
        const styleTag = document.getElementById('local-website-preview-css');
        if (styleTag) {
          styleTag.remove();
        }
      };
    } else {
      console.warn('[LocalPreview] No global_css found');
    }
  }, [previewData?.global_css, website?.global_css]);

  if (loadingPreview) {
    return (
      <div className="fixed inset-0 bg-white z-[10000] flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-purple-600 mb-4"></div>
          <p className="text-slate-600">Loading preview...</p>
        </div>
      </div>
    );
  }

  // Use preview data if available, otherwise fallback to editor state
  const dataToUse = previewData || {
    sections: sections?.map(s => ({
      id: s.id,
      label: s.id,
      category: '',
      icon: '',
      description: '',
      config: sectionsConfig[s.id] || {},
      enabled: sectionsEnabled[s.id] !== false,
    })) || [],
    episodes: episodes || [],
    podcast_title: podcast?.name,
    podcast_description: podcast?.description,
    podcast_cover_url: podcast?.cover_url || podcast?.cover_path || podcast?.remote_cover_url,
  };

  if (!dataToUse.sections || dataToUse.sections.length === 0) {
    return (
      <div className="fixed inset-0 bg-white z-[10000] flex items-center justify-center">
        <div className="text-center">
          <p className="text-slate-600 mb-4">No website data available for preview</p>
          {onClose && (
            <button
              onClick={onClose}
              className="px-4 py-2 bg-slate-900 text-white rounded-lg hover:bg-slate-800"
            >
              Close Preview
            </button>
          )}
        </div>
      </div>
    );
  }

  // Build content sections from preview data
  const contentSections = dataToUse.sections
    .filter(section => section.enabled !== false)
    .map(section => ({
      id: section.id,
      config: section.config || {},
      enabled: section.enabled !== false,
    }));

  // Find header and footer sections
  const headerSection = contentSections.find(s => s.id === 'header');
  const footerSection = contentSections.find(s => s.id === 'footer');
  const otherSections = contentSections.filter(s => s.id !== 'header' && s.id !== 'footer');

  // Prepare podcast data from preview data or fallback
  const podcastData = {
    id: podcast?.id,
    title: dataToUse.podcast_title || podcast?.name || podcast?.title,
    description: dataToUse.podcast_description || podcast?.description,
    cover_url: dataToUse.podcast_cover_url || podcast?.cover_url || podcast?.cover_path || podcast?.remote_cover_url,
    rss_url: dataToUse.podcast_rss_feed_url || podcast?.rss_url,
  };

  // Use episodes from preview data (they're already formatted correctly)
  const episodesWithPodcast = (dataToUse.episodes || episodes || []).map(ep => ({
    ...ep,
    podcast_title: podcastData.title,
  }));

  return (
    <div className="fixed inset-0 bg-white z-[10000] overflow-auto" style={{ background: 'var(--bg, white)', color: 'var(--text, #1e293b)' }}>
      {/* Preview Header Bar */}
      <div className="sticky top-0 z-[10001] bg-slate-900 text-white px-4 py-2 flex items-center justify-between border-b border-slate-700">
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
          <span className="text-sm font-medium">Local Preview Mode</span>
          <span className="text-xs text-slate-400">(Testing locally - not published)</span>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded text-sm font-medium transition-colors"
          >
            Close Preview
          </button>
        )}
      </div>

      {/* Website Content */}
      <div className="min-h-screen flex flex-col">
        {/* Sticky Header */}
        {headerSection && (
          <div className="sticky top-[41px] z-50">
            {(() => {
              const HeaderComponent = getSectionPreviewComponent('header');
              return <HeaderComponent 
                config={headerSection.config} 
                enabled={headerSection.enabled} 
                podcast={podcastData}
                pages={previewData?.pages || website?.pages || []}
              />
            })()}
          </div>
        )}

        {/* Main Content Sections */}
        <main className="flex-1" style={{ paddingBottom: '80px' }}>
          {otherSections.map((section) => {
            const SectionComponent = getSectionPreviewComponent(section.id);
            
            if (!SectionComponent) {
              console.warn(`[LocalPreview] No component found for section ID: ${section.id}`);
              return null;
            }
            
            // Pass episode data to sections that need it
            const sectionProps = {
              key: section.id,
              config: section.config,
              enabled: section.enabled,
              podcast: podcastData,
            };
            
            // Add episodes for sections that display them
            if (section.id === 'latest-episodes' || section.id === 'episodes') {
              sectionProps.episodes = episodesWithPodcast;
              console.log(`[LocalPreview] ${section.id} section - episodes count:`, episodesWithPodcast.length);
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
        {footerSection && (
          <div>
            {(() => {
              const FooterComponent = getSectionPreviewComponent('footer');
              return <FooterComponent 
                config={footerSection.config} 
                enabled={footerSection.enabled} 
                podcast={podcastData}
              />
            })()}
          </div>
        )}
      </div>
    </div>
  );
}

