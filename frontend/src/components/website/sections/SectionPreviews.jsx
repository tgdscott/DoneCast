/**
 * Section preview components for the website builder.
 * Each section renders a preview of how it will look on the published site.
 */

import { ExternalLink, Mail, Radio, Rss, Users, Quote, DollarSign, Calendar, Heart, Sparkles, ChevronLeft, ChevronRight, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useState, useEffect } from "react";
import { ensureReadablePair, normalizeHexColor } from "@/components/website/theme/colorAccessibility";

// Basic markdown/emphasis cleanup to keep AI copy from rendering stray asterisks/underscores
const sanitizeCopy = (text) => {
  if (typeof text !== "string") return text;
  return text.replace(/[\*_`]+/g, "").replace(/\s{2,}/g, " ").trim();
};

// Helper to get icon component by name
export function getSectionIcon(iconName) {
  const icons = {
    Sparkles,
    Info: () => <span className="text-sm">ℹ️</span>,
    Radio,
    Rss,
    Users,
    Mail,
    Quote,
    DollarSign,
    Calendar,
    Heart,
    Newspaper: () => <span className="text-sm">📰</span>,
    Award: () => <span className="text-sm">🏆</span>,
    BookOpen: () => <span className="text-sm">📚</span>,
    HelpCircle: () => <span className="text-sm">❓</span>,
    MessageSquare: () => <span className="text-sm">💬</span>,
    FileText: () => <span className="text-sm">📄</span>,
    Share2: () => <span className="text-sm">🔗</span>,
    Film: () => <span className="text-sm">🎬</span>,
  };
  
  const IconComponent = icons[iconName];
  return IconComponent ? <IconComponent className="h-5 w-5" /> : <Sparkles className="h-5 w-5" />;
}

/**
 * Hero Section Preview
 */
export function HeroSectionPreview({ config, enabled, podcast }) {
  const {
    title,
    subtitle,
    cta_text = "Listen Now",
    cta_url,
    background_color,
    text_color,
    show_cover_art = true,
    variant,
  } = config || {};
  
  // Use config title or fall back to podcast title
  const displayTitle = sanitizeCopy(title || podcast?.title || "Your Podcast Name");
  const displaySubtitle = sanitizeCopy(subtitle || podcast?.description || "A captivating tagline that hooks listeners");
  const coverUrl = podcast?.cover_url;
  
  // Debug logging for cover image (dev only)
  useEffect(() => {
    if (import.meta.env.DEV) {
      console.log('[HeroSection] ===== COVER IMAGE DEBUG =====');
      console.log('[HeroSection] Cover URL (raw):', coverUrl);
      console.log('[HeroSection] Cover URL (type):', typeof coverUrl);
      console.log('[HeroSection] Cover URL (truthy?):', !!coverUrl);
      console.log('[HeroSection] Show cover art:', show_cover_art);
      console.log('[HeroSection] Show cover art (type):', typeof show_cover_art);
      console.log('[HeroSection] Podcast object:', JSON.stringify(podcast || {}));
      console.log('[HeroSection] Should show image?', (show_cover_art !== false) && coverUrl);
      console.log('[HeroSection] ============================');
    }
  }, [coverUrl, show_cover_art, podcast]);

  // Use CSS variables from AI theme if available, otherwise use config values
  const bgColor = background_color || "#1e293b";
  const txtColor = text_color || "#ffffff";
  const heroClass = variant ? `hero ${variant}` : "hero";
  
  // Check if we should use CSS variables (when background_color is a CSS variable)
  const useCSSVars = background_color && background_color.startsWith('var(');
  const heroColors = ensureReadablePair({
    background: bgColor,
    text: txtColor,
    fallbackText: "#ffffff",
  });
  const buttonColors = ensureReadablePair({
    background: heroColors.text,
    text: heroColors.background,
    fallbackText: heroColors.background,
  });

  return (
    <div
      className={`w-full relative overflow-hidden ${heroClass}`}
      style={useCSSVars ? {
        opacity: enabled ? 1 : 0.6,
        color: heroColors.text || txtColor,
        backgroundColor: "var(--hero-bg, var(--bg, transparent))",
      } : {
        backgroundColor: heroColors.background || bgColor,
        color: heroColors.text || txtColor,
        opacity: enabled ? 1 : 0.6,
      }}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
        <div className="grid md:grid-cols-2 gap-8 items-center">
          {/* Cover image on the left - ALWAYS show if coverUrl exists and show_cover_art is not explicitly false */}
          {(() => {
            // Force check - be very explicit
            const hasCoverUrl = coverUrl && typeof coverUrl === 'string' && coverUrl.trim().length > 0;
            const shouldShowCover = show_cover_art !== false;
            const shouldShow = hasCoverUrl && shouldShowCover;
            
            if (import.meta.env.DEV) {
              console.log('[HeroSection] Render check:', {
                hasCoverUrl,
                coverUrlValue: coverUrl,
                shouldShowCover,
                show_cover_art,
                finalShouldShow: shouldShow
              });
              
              if (!shouldShow) {
                console.warn('[HeroSection] ⚠️ Cover image NOT rendering:', {
                  reason: !hasCoverUrl ? 'NO_COVER_URL' : 'SHOW_COVER_ART_FALSE',
                  coverUrl: coverUrl || 'MISSING',
                  show_cover_art
                });
              }
            }
            
            return shouldShow ? (
              <div className="flex justify-center md:justify-start order-1 md:order-1">
                <img
                  src={coverUrl}
                  alt={displayTitle}
                  className="w-64 h-64 md:w-80 md:h-80 rounded-2xl shadow-2xl object-cover"
                  style={{ border: '2px solid #10b981' }} // Green border to confirm it's rendering
                  onError={(e) => {
                    if (import.meta.env.DEV) {
                      console.error('[HeroSection] ❌ IMAGE LOAD ERROR:', {
                        src: coverUrl,
                        error: e.target.error,
                        naturalWidth: e.target.naturalWidth,
                        naturalHeight: e.target.naturalHeight
                      });
                    }
                    e.target.style.border = '4px solid red';
                  }}
                  onLoad={(e) => {
                    if (import.meta.env.DEV) {
                      console.log('[HeroSection] ✅ IMAGE LOADED SUCCESSFULLY:', {
                        src: coverUrl,
                        naturalWidth: e.target.naturalWidth,
                        naturalHeight: e.target.naturalHeight
                      });
                    }
                  }}
                />
              </div>
            ) : (
              <div className="flex justify-center md:justify-start order-1 md:order-1 p-4 border-2 border-yellow-500">
                <p className="text-xs text-yellow-700">
                  No cover image: coverUrl={coverUrl ? 'EXISTS' : 'MISSING'}, show_cover_art={String(show_cover_art)}
                </p>
              </div>
            );
          })()}
          {/* Don't show debug message - just leave space empty if no cover */}
          
          {/* Title and content on the right */}
          <div className="space-y-6 order-2 md:order-2">
            <h1 className="text-4xl md:text-5xl font-bold leading-tight hero-title">{displayTitle}</h1>
            {displaySubtitle && <p className="text-lg md:text-xl opacity-90">{displaySubtitle}</p>}
            {cta_text && cta_url && (
              <div className="pt-4">
                <Button 
                  size="lg" 
                  className={variant === "marquee-style" ? "btn ticket-style" : ""}
                  style={{ 
                    color: buttonColors.text || bgColor,
                    backgroundColor: buttonColors.background || txtColor,
                  }}
                  asChild
                >
                  <a href={cta_url}>{cta_text}</a>
                </Button>
              </div>
            )}
          </div>
          
          {/* Theater bulbs decoration if marquee style */}
          {variant === "marquee-style" && (
            <div className="bulb-row absolute bottom-4 left-1/2 -translate-x-1/2 w-full">
              {[...Array(12)].map((_, i) => (
                <div key={i} className="bulb" />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * About Section Preview
 */
export function AboutSectionPreview({ config, enabled, podcast }) {
  const {
    heading,
    body,
  } = config || {};
  
  // Use config or fall back to podcast data
  const displayHeading = sanitizeCopy(heading || `About ${podcast?.title || 'the Show'}`);
  const displayBody = sanitizeCopy(body || podcast?.description || "Tell listeners what your podcast is about and why they should tune in.");

  return (
    <div
      className="w-full bg-white py-12"
      style={{ opacity: enabled ? 1 : 0.6 }}
    >
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
        <h2 className="text-3xl font-bold text-slate-900 mb-6">{displayHeading}</h2>
        <div className="text-lg text-slate-600 leading-relaxed whitespace-pre-wrap">
          {displayBody}
        </div>
      </div>
    </div>
  );
}

/**
 * Latest Episodes Section Preview
 */
export function LatestEpisodesSectionPreview({ config, enabled, podcast, episodes = [] }) {
  const {
    heading = "Latest Episodes",
    count = 6,
    layout = "cards", // Default to cards, not list
    show_descriptions = true,
    show_dates = true,
  } = config || {};

  // Pagination state - persist across re-renders
  const [currentPage, setCurrentPage] = useState(1);
  const episodesPerPage = count || 6;
  const totalPages = Math.ceil((episodes?.length || 0) / episodesPerPage);
  
  // Calculate which episodes to show (must be before useEffect that uses them)
  const startIndex = (currentPage - 1) * episodesPerPage;
  const endIndex = startIndex + episodesPerPage;
  const displayEpisodes = (episodes?.length > 0) ? episodes.slice(startIndex, endIndex) : [];
  
  // Debug logging (dev only)
  useEffect(() => {
    if (import.meta.env.DEV) {
      const totalEpisodes = episodes?.length || 0;
      const shouldShowPagination = totalEpisodes > episodesPerPage;
      console.log('[LatestEpisodes] ===== EPISODE DEBUG =====');
      console.log('[LatestEpisodes] Total episodes received:', totalEpisodes);
      console.log('[LatestEpisodes] Episodes per page:', episodesPerPage);
      console.log('[LatestEpisodes] Total pages:', totalPages);
      console.log('[LatestEpisodes] Current page:', currentPage);
      console.log('[LatestEpisodes] Display episodes count:', displayEpisodes.length);
      console.log('[LatestEpisodes] Start index:', startIndex, 'End index:', endIndex);
      console.log('[LatestEpisodes] Should show pagination?', shouldShowPagination, `(${totalEpisodes} > ${episodesPerPage})`);
      if (totalEpisodes > 0) {
        console.log('[LatestEpisodes] First episode:', episodes[0]?.title, episodes[0]?.publish_date);
        console.log('[LatestEpisodes] Last episode:', episodes[totalEpisodes - 1]?.title, episodes[totalEpisodes - 1]?.publish_date);
        if (totalEpisodes >= 200) {
          console.log('[LatestEpisodes] ✅ Episode 200 exists:', episodes[199]?.title);
        }
        if (totalEpisodes >= 204) {
          console.log('[LatestEpisodes] ✅ Episode 204 exists:', episodes[203]?.title);
        }
      }
      console.log('[LatestEpisodes] ========================');
    }
  }, [episodes?.length, episodesPerPage, totalPages, currentPage, startIndex, endIndex, displayEpisodes.length, episodes]);
  
  // Reset to page 1 only if current page is invalid (e.g., episodes list shrunk)
  useEffect(() => {
    if (totalPages > 0 && currentPage > totalPages) {
      setCurrentPage(1);
    }
  }, [totalPages, currentPage]);
  
  // Format date helper
  const formatDate = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
  };
  
  const handlePreviousPage = () => {
    setCurrentPage(prev => {
      if (prev > 1) {
        // Scroll to top of section
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return prev - 1;
      }
      return prev;
    });
  };
  
  const handleNextPage = () => {
    setCurrentPage(prev => {
      if (prev < totalPages) {
        // Scroll to top of section
        window.scrollTo({ top: 0, behavior: 'smooth' });
        return prev + 1;
      }
      return prev;
    });
  };

  if (displayEpisodes.length === 0) {
    // Placeholder when no episodes
    return (
      <div
        className="rounded-lg border border-slate-200 bg-white"
        style={{ opacity: enabled ? 1 : 0.6 }}
      >
        <div className="border-b border-slate-100 px-6 py-4">
          <h3 className="text-lg font-semibold text-slate-900">{heading}</h3>
          <p className="text-xs text-slate-500">Showing your {count} most recent episodes</p>
        </div>
        <div className="divide-y divide-slate-100">
          <div className="px-6 py-4 flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold text-slate-900">Sample Episode</div>
              {show_descriptions && (
                <p className="text-xs text-slate-500">Your latest published episode will appear here with a play button.</p>
              )}
            </div>
            <Button size="sm" variant="outline" disabled>
              <Radio className="mr-2 h-3 w-3" /> Play
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // Format duration helper
  const formatDuration = (seconds) => {
    if (!seconds) return '';
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;
    if (hours > 0) {
      return `${hours}h ${minutes}m ${secs > 0 ? secs + 's' : ''}`;
    }
    return `${minutes}m ${secs > 0 ? secs + 's' : ''}`;
  };

  // Real episodes rendering - Simplified Spreaker-style
  if (layout === "list") {
    // Simple list layout: title, play button, runtime, add to queue
    return (
      <div
        className="w-full bg-white py-12"
        style={{ opacity: enabled ? 1 : 0.6 }}
      >
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8">
          <h2 className="text-3xl font-bold text-slate-900 mb-8">{heading}</h2>
          <div className="space-y-3">
            {displayEpisodes.map((episode) => (
              <div
                key={episode.id}
                className="flex items-center justify-between gap-4 p-4 rounded-lg hover:bg-slate-50 transition-colors border border-slate-100"
              >
                <div className="flex-1 min-w-0">
                  <h3 className="text-base font-semibold text-slate-900 mb-1 truncate">
                    {episode.title}
                  </h3>
                  {show_dates && episode.publish_date && (
                    <p className="text-xs text-slate-500">
                      {formatDate(episode.publish_date)}
                    </p>
                  )}
                </div>
                
                <div className="flex items-center gap-3">
                  {/* Play Button */}
                  {episode.audio_url ? (
                    <Button
                      size="sm"
                      variant="default"
                      className="bg-slate-900 hover:bg-slate-800 text-white"
                      onClick={() => {
                        // Trigger play in persistent player
                        // Add episode to queue first, then play
                        window.dispatchEvent(new CustomEvent('add-to-queue', {
                          detail: { episode }
                        }));
                        window.dispatchEvent(new CustomEvent('play-episode', {
                          detail: { episode }
                        }));
                      }}
                    >
                      <Radio className="mr-1.5 h-3.5 w-3.5" />
                      Play
                    </Button>
                  ) : (
                    <Button size="sm" variant="outline" disabled>
                      <Radio className="mr-1.5 h-3.5 w-3.5" />
                      Play
                    </Button>
                  )}
                  
                  {/* Runtime */}
                  {episode.duration_seconds && (
                    <span className="text-xs text-slate-500 min-w-[60px] text-right">
                      {formatDuration(episode.duration_seconds)}
                    </span>
                  )}
                  
                  {/* Add to Queue */}
                  {episode.audio_url && (
                    <Button
                      size="sm"
                      variant="ghost"
                      className="text-slate-600 hover:text-slate-900"
                      onClick={() => {
                        window.dispatchEvent(new CustomEvent('add-to-queue', {
                          detail: { episode }
                        }));
                      }}
                      title="Add to queue"
                    >
                      <Plus className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </div>
            ))}
          </div>
          
          {/* Pagination Controls - Show if we have more episodes than per page */}
          {episodes && Array.isArray(episodes) && episodes.length > episodesPerPage && (
            <div className="flex items-center justify-center gap-4 mt-8">
              <Button
                variant="outline"
                size="sm"
                onClick={handlePreviousPage}
                disabled={currentPage === 1}
              >
                <ChevronLeft className="h-4 w-4 mr-1" />
                Previous
              </Button>
              
              <span className="text-sm text-slate-600">
                Page {currentPage} of {totalPages}
              </span>
              
              <Button
                variant="outline"
                size="sm"
                onClick={handleNextPage}
                disabled={currentPage === totalPages}
              >
                Next
                <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </div>
          )}
        </div>
      </div>
    );
  }

  // Cards/Grid layout (default) - keep existing card-based rendering
  return (
    <div
      className="w-full bg-white py-12"
      style={{ opacity: enabled ? 1 : 0.6 }}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <h2 className="text-3xl font-bold text-slate-900 mb-8">{heading}</h2>
        <div className="space-y-6">
          {displayEpisodes.map((episode) => (
            <div
              key={episode.id}
              className="border border-slate-200 rounded-lg p-6 hover:border-slate-300 transition-colors"
            >
              <div className="flex gap-4">
                {/* Episode Cover */}
                {episode.cover_url && (
                  <div className="flex-shrink-0">
                    <img
                      src={episode.cover_url}
                      alt={episode.title}
                      className="w-24 h-24 rounded-md object-cover"
                      onError={(e) => {
                        e.target.style.display = 'none';
                      }}
                    />
                  </div>
                )}
                
                {/* Episode Info */}
                <div className="flex-1 min-w-0">
                  <h3 className="text-xl font-semibold text-slate-900 mb-2">
                    {episode.title}
                  </h3>
                  
                  {show_dates && episode.publish_date && (
                    <p className="text-sm text-slate-500 mb-2">
                      {formatDate(episode.publish_date)}
                    </p>
                  )}
                  
                  {show_descriptions && episode.description && (
                    <p className="text-sm text-slate-600 line-clamp-3 mb-4">
                      {episode.description}
                    </p>
                  )}
                  
                  {/* Play Button - triggers persistent player */}
                  {episode.audio_url ? (
                    <Button 
                      size="sm" 
                      variant="default"
                      className="mt-4 bg-purple-600 hover:bg-purple-700 text-white"
                      onClick={() => {
                        if (import.meta.env.DEV) {
                          console.log('[LatestEpisodes] Play button clicked for episode:', episode.title);
                          console.log('[LatestEpisodes] Episode audio_url:', episode.audio_url);
                        }
                        if (!episode.audio_url) {
                          if (import.meta.env.DEV) {
                            console.warn('[LatestEpisodes] Episode has no audio_url!');
                          }
                          alert('This episode does not have an audio file available.');
                          return;
                        }
                        // Trigger play in persistent player
                        window.dispatchEvent(new CustomEvent('add-to-queue', {
                          detail: { episode }
                        }));
                        window.dispatchEvent(new CustomEvent('play-episode', {
                          detail: { episode }
                        }));
                      }}
                    >
                      <Radio className="mr-2 h-3 w-3" />
                      Play Episode
                    </Button>
                  ) : (
                    <Button size="sm" variant="outline" disabled className="mt-4">
                      <Radio className="mr-2 h-3 w-3" /> Audio unavailable
                    </Button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
        
        {/* Pagination Controls */}
        {(episodes?.length || 0) > episodesPerPage && (
          <div className="flex items-center justify-center gap-4 mt-8">
            <Button
              variant="outline"
              size="sm"
              onClick={handlePreviousPage}
              disabled={currentPage === 1}
            >
              <ChevronLeft className="h-4 w-4 mr-1" />
              Previous
            </Button>
            
            <span className="text-sm text-slate-600">
              Page {currentPage} of {totalPages}
            </span>
            
            <Button
              variant="outline"
              size="sm"
              onClick={handleNextPage}
              disabled={currentPage === totalPages}
            >
              Next
              <ChevronRight className="h-4 w-4 ml-1" />
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Subscribe Section Preview
 */
export function SubscribeSectionPreview({ config, enabled, podcast }) {
  const {
    heading = "Subscribe & Listen",
    layout = "icons",
    apple_podcasts_url,
    spotify_url,
    google_podcasts_url,
    youtube_url,
    show_rss = true,
  } = config || {};
  
  // Use config URLs or fall back to podcast RSS and server-provided feed URL
  const rss_url = config?.rss_url || podcast?.rss_url || podcast?.rss_feed_url;

  const hasAnyPlatform = !!(
    apple_podcasts_url ||
    spotify_url ||
    google_podcasts_url ||
    youtube_url ||
    (show_rss && rss_url)
  );

  const renderButton = (label, url, icon = null) => {
    if (!url) {
      return (
        <Button size="lg" variant="outline" disabled title={`${label} link not set yet`}>
          {icon}
          {label}
        </Button>
      );
    }
    return (
      <Button size="lg" variant="outline" asChild>
        <a href={url} target="_blank" rel="noopener noreferrer">
          {icon}
          {label}
        </a>
      </Button>
    );
  };

  return (
    <div
      className="w-full bg-slate-50 py-12"
      style={{ opacity: enabled ? 1 : 0.6 }}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <h2 className="text-3xl font-bold text-slate-900 mb-4">{heading}</h2>
        <p className="text-slate-600 mb-8">Listen on your favorite podcast platform</p>
        
        <div className="flex gap-4 flex-wrap justify-center">
          {renderButton("Apple Podcasts", apple_podcasts_url)}
          {renderButton("Spotify", spotify_url)}
          {renderButton("Google Podcasts", google_podcasts_url)}
          {renderButton("YouTube", youtube_url)}
          {show_rss && renderButton("RSS Feed", rss_url, <Rss className="mr-2 h-4 w-4" />)}
        </div>

        {!hasAnyPlatform && (
          <p className="mt-4 text-xs text-slate-500">Add your links in Website Builder to make these buttons live.</p>
        )}
      </div>
    </div>
  );
}

/**
 * Newsletter Section Preview
 */
export function NewsletterSectionPreview({ config, enabled }) {
  const {
    heading = "Stay in the Loop",
    description = "Get episode updates and exclusive content.",
    button_text = "Subscribe",
  } = config || {};

  return (
    <div
      className="rounded-lg border border-slate-200 bg-white p-6"
      style={{ opacity: enabled ? 1 : 0.6 }}
    >
      <div className="flex items-start gap-3">
        <Mail className="h-5 w-5 text-slate-400 mt-1" />
        <div className="flex-1">
          <h3 className="text-lg font-semibold text-slate-900">{heading}</h3>
          {description && <p className="mt-1 text-sm text-slate-600">{description}</p>}
          <div className="mt-3 flex gap-2">
            <input
              type="email"
              placeholder="you@example.com"
              className="flex-1 px-3 py-2 border border-slate-200 rounded text-sm"
              disabled
            />
            <Button size="sm">{button_text}</Button>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * Testimonials Section Preview
 */
export function TestimonialsSectionPreview({ config, enabled }) {
  const {
    heading = "What Listeners Are Saying",
  } = config || {};

  return (
    <div
      className="rounded-lg border border-slate-200 bg-white p-6"
      style={{ opacity: enabled ? 1 : 0.6 }}
    >
      <h3 className="text-lg font-semibold text-slate-900 mb-4">{heading}</h3>
      <div className="space-y-3">
        {[1, 2].map((i) => (
          <div key={i} className="border border-slate-100 rounded-md p-3">
            <Quote className="h-4 w-4 text-slate-400 mb-2" />
            <p className="text-sm text-slate-600 italic">
              "This podcast changed my perspective..."
            </p>
            <p className="text-xs text-slate-500 mt-2">— Listener {i}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * Header Section Preview
 */
export function HeaderSectionPreview({ config, enabled, podcast, pages = [] }) {
  const {
    show_logo = true,
    logo_url,
    logo_text,
    show_navigation = true,
    show_player = false,
    background_color = "#ffffff",
    text_color = "#1e293b",
    height = "normal",
    show_shadow = true,
  } = config || {};

  const headerColors = ensureReadablePair({
    background: background_color,
    text: text_color,
    fallbackText: "#1e293b",
  });
  
  // Use config logo_text or fall back to podcast title
  const displayLogoText = logo_text || podcast?.title || "Podcast Name";
  
  // Priority: config.logo_url > podcast.cover_url
  const logoImageUrl = logo_url || podcast?.cover_url;
  
  // Auto-populate navigation from pages (sorted by order)
  const navigationItems = pages
    .filter(page => !page.is_home)
    .sort((a, b) => (a.order || 0) - (b.order || 0))
    .map(page => ({
      title: page.title,
      slug: page.slug,
      href: `/${page.slug}`,
    }));

  const heightClasses = {
    compact: "py-2",
    normal: "py-4",
    tall: "py-6",
  };

  return (
    <div
      className={`w-full ${show_shadow ? "shadow-sm" : ""}`}
      style={{ 
        backgroundColor: headerColors.background || background_color, 
        color: headerColors.text || text_color,
        opacity: enabled ? 1 : 0.6 
      }}
    >
      <div className={`max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 ${heightClasses[height]} flex items-center justify-between`}>
        {/* Logo */}
        {show_logo && (
          <div className="flex items-center gap-3">
            {logoImageUrl ? (
              <img
                src={logoImageUrl}
                alt={displayLogoText}
                className="w-10 h-10 rounded-lg object-cover"
                onError={(e) => {
                  e.target.style.display = 'none';
                }}
              />
            ) : (
              <div className="w-10 h-10 rounded-lg bg-slate-200 flex items-center justify-center text-xl">
                🎙️
              </div>
            )}
            <a href="/" className="font-bold text-lg hover:opacity-80 transition-opacity">{displayLogoText}</a>
          </div>
        )}

        {/* Navigation - Auto-populated from pages */}
        {show_navigation && (
          <nav className="hidden md:flex gap-6 text-sm font-medium">
            {navigationItems.length > 0 ? (
              navigationItems.map((item) => (
                <a 
                  key={item.slug} 
                  href={item.href} 
                  className="opacity-70 hover:opacity-100 cursor-pointer transition-opacity"
                >
                  {item.title}
                </a>
              ))
            ) : (
              // Default navigation if no pages exist (single-page site) - scroll to sections
              <>
                <a 
                  href="#hero" 
                  onClick={(e) => {
                    e.preventDefault();
                    const heroSection = document.querySelector('[data-section-id="hero"]') || document.querySelector('.hero');
                    if (heroSection) {
                      heroSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    } else {
                      window.scrollTo({ top: 0, behavior: 'smooth' });
                    }
                  }}
                  className="opacity-70 hover:opacity-100 cursor-pointer transition-opacity"
                >
                  Home
                </a>
                <a 
                  href="#latest-episodes" 
                  onClick={(e) => {
                    e.preventDefault();
                    const episodesSection = document.querySelector('[data-section-id="latest-episodes"]') || document.querySelector('[data-section-id="episodes"]');
                    if (episodesSection) {
                      episodesSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }
                  }}
                  className="opacity-70 hover:opacity-100 cursor-pointer transition-opacity"
                >
                  Episodes
                </a>
                <a 
                  href="#about" 
                  onClick={(e) => {
                    e.preventDefault();
                    const aboutSection = document.querySelector('[data-section-id="about"]');
                    if (aboutSection) {
                      aboutSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }
                  }}
                  className="opacity-70 hover:opacity-100 cursor-pointer transition-opacity"
                >
                  About
                </a>
              </>
            )}
          </nav>
        )}

        {/* Player */}
        {show_player && (
          <div className="flex items-center gap-2 text-xs">
            <Button size="sm" variant="ghost" className="h-7 w-7 p-0">
              ▶
            </Button>
            <span className="opacity-70">Now Playing</span>
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Footer Section Preview
 */
export function FooterSectionPreview({ config, enabled, podcast }) {
  const {
    show_social_links = true,
    show_subscribe_links = true,
    show_legal_links = false,
    copyright_text,
    background_color = "#1e293b",
    text_color = "#94a3b8",
    layout = "columns",
    social_links = {},
  } = config || {};

  const footerColors = ensureReadablePair({
    background: background_color,
    text: text_color,
    fallbackText: "#94a3b8",
  });

  const footerDividerColor = (() => {
    const normalized = normalizeHexColor(footerColors.text || text_color);
    return normalized ? `${normalized}40` : undefined;
  })();
  
  // Use config copyright or generate from podcast title
  const displayCopyright = copyright_text || `© ${new Date().getFullYear()} ${podcast?.title || 'Your Podcast'}. All rights reserved.`;

  const socialPlatforms = [
    { key: "x", label: "X", icon: "X", url: social_links.x },
    { key: "instagram", label: "Instagram", icon: "IG", url: social_links.instagram },
    { key: "youtube", label: "YouTube", icon: "YT", url: social_links.youtube },
    { key: "facebook", label: "Facebook", icon: "FB", url: social_links.facebook },
    { key: "tiktok", label: "TikTok", icon: "TT", url: social_links.tiktok },
    { key: "linkedin", label: "LinkedIn", icon: "IN", url: social_links.linkedin },
  ];

  const rssUrl = podcast?.rss_url || podcast?.rss_feed_url;

  const renderSocialIcon = (platform) => {
    const hasUrl = !!platform.url;
    const commonClasses = "w-10 h-10 rounded-full flex items-center justify-center border border-white/15 bg-white/5 text-xs font-semibold";
    if (!hasUrl) {
      return (
        <button
          key={platform.key}
          className={`${commonClasses} opacity-60 cursor-not-allowed`}
          type="button"
          title={`${platform.label} link not set yet`}
          aria-disabled
        >
          {platform.icon}
        </button>
      );
    }
    return (
      <a
        key={platform.key}
        href={platform.url}
        target="_blank"
        rel="noopener noreferrer"
        className={`${commonClasses} hover:opacity-100 transition-opacity`}
        title={platform.label}
      >
        {platform.icon}
      </a>
    );
  };

  return (
    <div
      className="w-full"
      style={{ 
        backgroundColor: footerColors.background || background_color, 
        color: footerColors.text || text_color,
        opacity: enabled ? 1 : 0.6 
      }}
    >
      <div className={`max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 ${layout === "centered" ? "text-center" : ""}`}>
        {layout === "columns" ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 text-sm">
            {/* Social Links */}
            {show_social_links && (
              <div>
                <h4 className="font-semibold mb-3">Follow Us</h4>
                <div className="flex gap-3 flex-wrap" aria-label="Social links">
                  {socialPlatforms.map(renderSocialIcon)}
                </div>
                <p className="text-xs opacity-70 mt-2">Add your handles in Website Builder to activate.</p>
              </div>
            )}

            {/* Subscribe Links */}
            {show_subscribe_links && (
              <div>
                <h4 className="font-semibold mb-3">Subscribe</h4>
                <div className="space-y-2 text-sm">
                  {rssUrl ? (
                    <a href={rssUrl} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 opacity-90 hover:opacity-100 transition-opacity">
                      <Rss className="h-4 w-4" /> RSS Feed
                    </a>
                  ) : (
                    <span className="opacity-70 text-xs">Add your RSS feed to enable this link.</span>
                  )}
                </div>
              </div>
            )}

            {/* Legal - hidden by default (user-managed) */}
            {show_legal_links && (
              <div>
                <h4 className="font-semibold mb-3">Legal</h4>
                <div className="space-y-2">
                  <div className="opacity-80 hover:opacity-100 transition-opacity cursor-pointer">Privacy Policy</div>
                  <div className="opacity-80 hover:opacity-100 transition-opacity cursor-pointer">Terms of Service</div>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-6 text-sm">
            {show_social_links && (
              <div className="flex gap-3 justify-center flex-wrap" aria-label="Social links">
                {socialPlatforms.map(renderSocialIcon)}
              </div>
            )}
            {show_subscribe_links && (
              <div className="flex gap-6 justify-center flex-wrap">
                {rssUrl ? (
                  <a href={rssUrl} target="_blank" rel="noopener noreferrer" className="flex items-center gap-2 opacity-90 hover:opacity-100 transition-opacity">
                    <Rss className="h-4 w-4" /> RSS
                  </a>
                ) : (
                  <span className="opacity-70 text-xs">Add your RSS feed to enable subscribe links.</span>
                )}
              </div>
            )}
          </div>
        )}

        {/* Copyright */}
        <div
          className="mt-8 pt-6 border-t border-slate-700 text-xs text-center"
          style={footerDividerColor ? { borderColor: footerDividerColor } : undefined}
        >
          {displayCopyright}
        </div>
        
        {/* DoneCast Branding */}
        <div className="mt-4 text-xs text-center opacity-70">
          Powered by{' '}
          <a 
            href="https://donecast.com" 
            target="_blank" 
            rel="noopener noreferrer"
            className="underline"
          >
            DoneCast
          </a>
        </div>
      </div>
    </div>
  );
}

/**
 * Generic Section Preview (for sections without custom components)
 */
export function GenericSectionPreview({ sectionDef, config, enabled }) {
  const Icon = getSectionIcon(sectionDef?.icon);
  const heading = config?.heading || sectionDef?.label || "Section";
  const description = config?.description || sectionDef?.description || "";

  return (
    <div
      className="rounded-lg border border-slate-200 bg-white p-6"
      style={{ opacity: enabled ? 1 : 0.6 }}
    >
      <div className="flex items-start gap-3">
        <div className="text-slate-400 mt-1">{Icon}</div>
        <div>
          <h3 className="text-lg font-semibold text-slate-900">{heading}</h3>
          {description && <p className="mt-1 text-sm text-slate-600">{description}</p>}
        </div>
      </div>
    </div>
  );
}

/**
 * Get the appropriate preview component for a section
 */
export function getSectionPreviewComponent(sectionId) {
  const previewComponents = {
    header: HeaderSectionPreview,
    footer: FooterSectionPreview,
    hero: HeroSectionPreview,
    about: AboutSectionPreview,
    "latest-episodes": LatestEpisodesSectionPreview,
    subscribe: SubscribeSectionPreview,
    newsletter: NewsletterSectionPreview,
    testimonials: TestimonialsSectionPreview,
  };

  return previewComponents[sectionId] || GenericSectionPreview;
}
