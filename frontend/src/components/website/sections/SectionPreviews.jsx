/**
 * Section preview components for the website builder.
 * Each section renders a preview of how it will look on the published site.
 */

import { ExternalLink, Mail, Radio, Rss, Users, Quote, DollarSign, Calendar, Heart, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

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
    background_color = "#1e293b",
    text_color = "#ffffff",
    show_cover_art = true,
  } = config || {};
  
  // Use config title or fall back to podcast title
  const displayTitle = title || podcast?.title || "Your Podcast Name";
  const displaySubtitle = subtitle || podcast?.description || "A captivating tagline that hooks listeners";
  const coverUrl = podcast?.cover_url;

  return (
    <div
      className="w-full relative overflow-hidden"
      style={{
        backgroundColor: background_color,
        color: text_color,
        opacity: enabled ? 1 : 0.6,
      }}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
        <div className="grid md:grid-cols-2 gap-8 items-center">
          <div className="space-y-6">
            <h1 className="text-4xl md:text-5xl font-bold leading-tight">{displayTitle}</h1>
            {displaySubtitle && <p className="text-lg md:text-xl opacity-90">{displaySubtitle}</p>}
            {cta_text && cta_url && (
              <div className="pt-4">
                <Button 
                  size="lg" 
                  style={{ color: background_color, backgroundColor: text_color }}
                  asChild
                >
                  <a href={cta_url}>{cta_text}</a>
                </Button>
              </div>
            )}
          </div>
          
          {show_cover_art && coverUrl && (
            <div className="flex justify-center md:justify-end">
              <img
                src={coverUrl}
                alt={displayTitle}
                className="w-64 h-64 md:w-80 md:h-80 rounded-2xl shadow-2xl object-cover"
                onError={(e) => {
                  e.target.style.display = 'none';
                }}
              />
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
  const displayHeading = heading || `About ${podcast?.title || 'the Show'}`;
  const displayBody = body || podcast?.description || "Tell listeners what your podcast is about and why they should tune in.";

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
    count = 3,
    show_descriptions = true,
    show_dates = true,
  } = config || {};

  // Use actual episodes if provided, otherwise show placeholder
  const displayEpisodes = episodes.length > 0 ? episodes.slice(0, count) : [];
  
  // Format date helper
  const formatDate = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
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
          {[1, 2].map((i) => (
            <div key={i} className="px-6 py-4 flex items-center justify-between">
              <div>
                <div className="text-sm font-semibold text-slate-900">Episode {i}</div>
                {show_descriptions && (
                  <p className="text-xs text-slate-500">Episode description...</p>
                )}
              </div>
              <Button size="sm" variant="outline">
                <Radio className="mr-2 h-3 w-3" /> Play
              </Button>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // Real episodes rendering
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
                  
                  {/* Audio Player */}
                  {episode.audio_url && (
                    <div className="mt-4">
                      <audio
                        controls
                        className="w-full max-w-md"
                        preload="none"
                        style={{ height: '40px' }}
                      >
                        <source src={episode.audio_url} type="audio/mpeg" />
                        Your browser does not support the audio element.
                      </audio>
                    </div>
                  )}
                  
                  {!episode.audio_url && (
                    <Button size="sm" variant="outline" disabled>
                      <Radio className="mr-2 h-3 w-3" /> Audio unavailable
                    </Button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
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
  
  // Use config URLs or fall back to podcast RSS
  const rss_url = config?.rss_url || podcast?.rss_url;

  return (
    <div
      className="w-full bg-slate-50 py-12"
      style={{ opacity: enabled ? 1 : 0.6 }}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center">
        <h2 className="text-3xl font-bold text-slate-900 mb-4">{heading}</h2>
        <p className="text-slate-600 mb-8">Listen on your favorite podcast platform</p>
        
        <div className="flex gap-4 flex-wrap justify-center">
          {apple_podcasts_url && (
            <Button size="lg" variant="outline" asChild>
              <a href={apple_podcasts_url} target="_blank" rel="noopener noreferrer">
                Apple Podcasts
              </a>
            </Button>
          )}
          
          {spotify_url && (
            <Button size="lg" variant="outline" asChild>
              <a href={spotify_url} target="_blank" rel="noopener noreferrer">
                Spotify
              </a>
            </Button>
          )}
          
          {google_podcasts_url && (
            <Button size="lg" variant="outline" asChild>
              <a href={google_podcasts_url} target="_blank" rel="noopener noreferrer">
                Google Podcasts
              </a>
            </Button>
          )}
          
          {youtube_url && (
            <Button size="lg" variant="outline" asChild>
              <a href={youtube_url} target="_blank" rel="noopener noreferrer">
                YouTube
              </a>
            </Button>
          )}
          
          {show_rss && rss_url && (
            <Button size="lg" variant="outline" asChild>
              <a href={rss_url} target="_blank" rel="noopener noreferrer">
                <Rss className="mr-2 h-4 w-4" /> RSS Feed
              </a>
            </Button>
          )}
          
          {/* Show placeholder buttons if no URLs configured */}
          {!apple_podcasts_url && !spotify_url && !google_podcasts_url && !youtube_url && !rss_url && (
            <>
              <Button size="lg" variant="outline" disabled>Apple Podcasts</Button>
              <Button size="lg" variant="outline" disabled>Spotify</Button>
              <Button size="lg" variant="outline" disabled>
                <Rss className="mr-2 h-4 w-4" /> RSS
              </Button>
            </>
          )}
        </div>
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
export function HeaderSectionPreview({ config, enabled, podcast }) {
  const {
    show_logo = true,
    logo_text,
    show_navigation = true,
    show_player = false,
    background_color = "#ffffff",
    text_color = "#1e293b",
    height = "normal",
    show_shadow = true,
  } = config || {};
  
  // Use config logo_text or fall back to podcast title
  const displayLogoText = logo_text || podcast?.title || "Podcast Name";

  const heightClasses = {
    compact: "py-2",
    normal: "py-4",
    tall: "py-6",
  };

  return (
    <div
      className={`w-full ${show_shadow ? "shadow-sm" : ""}`}
      style={{ 
        backgroundColor: background_color, 
        color: text_color,
        opacity: enabled ? 1 : 0.6 
      }}
    >
      <div className={`max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 ${heightClasses[height]} flex items-center justify-between`}>
        {/* Logo */}
        {show_logo && (
          <div className="flex items-center gap-3">
            {podcast?.cover_url ? (
              <img
                src={podcast.cover_url}
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
            <span className="font-bold text-lg">{displayLogoText}</span>
          </div>
        )}

        {/* Navigation */}
        {show_navigation && (
          <nav className="hidden md:flex gap-6 text-sm font-medium">
            <a href="#home" className="opacity-70 hover:opacity-100 cursor-pointer transition-opacity">Home</a>
            <a href="#episodes" className="opacity-70 hover:opacity-100 cursor-pointer transition-opacity">Episodes</a>
            <a href="#about" className="opacity-70 hover:opacity-100 cursor-pointer transition-opacity">About</a>
            <a href="#contact" className="opacity-70 hover:opacity-100 cursor-pointer transition-opacity">Contact</a>
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
    copyright_text,
    background_color = "#1e293b",
    text_color = "#94a3b8",
    layout = "columns",
  } = config || {};
  
  // Use config copyright or generate from podcast title
  const displayCopyright = copyright_text || `© ${new Date().getFullYear()} ${podcast?.title || 'Your Podcast'}. All rights reserved.`;

  return (
    <div
      className="w-full"
      style={{ 
        backgroundColor: background_color, 
        color: text_color,
        opacity: enabled ? 1 : 0.6 
      }}
    >
      <div className={`max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 ${layout === "centered" ? "text-center" : ""}`}>
        {layout === "columns" ? (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 text-sm">
            {/* Social Links */}
            {show_social_links && (
              <div>
                <h4 className="font-semibold mb-3 text-white">Follow Us</h4>
                <div className="space-y-2">
                  <div className="hover:text-white transition-colors cursor-pointer">Twitter</div>
                  <div className="hover:text-white transition-colors cursor-pointer">Instagram</div>
                  <div className="hover:text-white transition-colors cursor-pointer">YouTube</div>
                </div>
              </div>
            )}

            {/* Subscribe Links */}
            {show_subscribe_links && (
              <div>
                <h4 className="font-semibold mb-3 text-white">Subscribe</h4>
                <div className="space-y-2">
                  <div className="hover:text-white transition-colors cursor-pointer">Apple Podcasts</div>
                  <div className="hover:text-white transition-colors cursor-pointer">Spotify</div>
                  {podcast?.rss_url && (
                    <a href={podcast.rss_url} target="_blank" rel="noopener noreferrer" className="block hover:text-white transition-colors">
                      RSS Feed
                    </a>
                  )}
                </div>
              </div>
            )}

            {/* Legal */}
            <div>
              <h4 className="font-semibold mb-3 text-white">Legal</h4>
              <div className="space-y-2">
                <div className="hover:text-white transition-colors cursor-pointer">Privacy Policy</div>
                <div className="hover:text-white transition-colors cursor-pointer">Terms of Service</div>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-6 text-sm">
            {show_social_links && (
              <div className="flex gap-6 justify-center">
                {["Twitter", "Instagram", "YouTube"].map((platform) => (
                  <span key={platform} className="hover:text-white transition-colors cursor-pointer">{platform}</span>
                ))}
              </div>
            )}
            {show_subscribe_links && (
              <div className="flex gap-6 justify-center flex-wrap">
                {["Apple Podcasts", "Spotify"].map((platform) => (
                  <span key={platform} className="hover:text-white transition-colors cursor-pointer">{platform}</span>
                ))}
                {podcast?.rss_url && (
                  <a href={podcast.rss_url} target="_blank" rel="noopener noreferrer" className="hover:text-white transition-colors">
                    RSS
                  </a>
                )}
              </div>
            )}
          </div>
        )}

        {/* Copyright */}
        <div className="mt-8 pt-6 border-t border-slate-700 text-xs text-center" style={{ borderColor: text_color + '40' }}>
          {displayCopyright}
        </div>
        
        {/* Podcast Plus Plus Branding */}
        <div className="mt-4 text-xs text-center opacity-60">
          Powered by{' '}
          <a 
            href="https://podcastplusplus.com" 
            target="_blank" 
            rel="noopener noreferrer"
            className="hover:text-white transition-colors"
          >
            Podcast Plus Plus
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
