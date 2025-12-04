/**
 * Website Preview Component
 * Displays a preview of the website layout
 */

import { ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ensureReadablePair } from "@/components/website/theme/colorAccessibility";

export default function WebsitePreview({ website }) {
  if (!website) {
    return (
      <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-6 text-center text-sm text-slate-600">
        Generate a site to see a live preview. The layout renders here exactly how visitors will experience it.
      </div>
    );
  }

  const layout = website.layout || {};
  const theme = layout.theme || {};
  const heroBg = theme.primary_color || "#0f172a";
  const heroFg = theme.secondary_color || "#ffffff";
  const accent = theme.accent_color || "#2563eb";
  const heroColors = ensureReadablePair({
    background: heroBg,
    text: heroFg,
    fallbackText: "#ffffff",
  });
  const accentButtonColors = ensureReadablePair({
    background: accent,
    text: "#ffffff",
    fallbackText: "#0f172a",
  });
  const accentOnLight = ensureReadablePair({
    background: "#ffffff",
    text: accent,
    fallbackText: "#2563eb",
  }).text;
  const heroImage = layout.hero_image_url;
  const liveUrl = website.custom_domain
    ? `https://${website.custom_domain}`
    : website.default_domain
      ? `https://${website.default_domain}`
      : null;

  return (
    <div className="space-y-8">
      <section
        className="rounded-2xl shadow-sm overflow-hidden"
        style={{ 
          backgroundColor: heroColors.background || heroBg, 
          color: heroColors.text || heroFg,
        }}
      >
        <div className="grid gap-8 md:grid-cols-[minmax(0,1fr)_minmax(0,0.75fr)]">
          <div className="p-8 md:p-12 space-y-4">
            <div className="text-xs uppercase tracking-[0.3em] opacity-80">Podcast Plus Plus</div>
            <h2 className="text-3xl md:text-5xl font-semibold leading-tight">{layout.hero_title || "Your podcast"}</h2>
            {layout.hero_subtitle && (
              <p className="text-base md:text-lg max-w-2xl opacity-90">{layout.hero_subtitle}</p>
            )}
            {liveUrl && (
              <Button
                asChild
                size="sm"
                className="mt-2"
                style={{
                  backgroundColor: accentButtonColors.background || accent,
                  color: accentButtonColors.text,
                }}
              >
                <a href={liveUrl} target="_blank" rel="noopener noreferrer">
                  <ExternalLink className="mr-2 h-4 w-4" /> View live site
                </a>
              </Button>
            )}
          </div>
          {heroImage && (
            <div className="relative flex items-center justify-center bg-slate-900/10 p-6 md:p-8">
              <div className="relative aspect-square w-full max-w-xs overflow-hidden rounded-xl border border-white/10 shadow-lg">
                <img
                  src={heroImage}
                  alt="Podcast cover art"
                  className="h-full w-full object-cover"
                />
              </div>
            </div>
          )}
        </div>
      </section>

      <section className="grid gap-6 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="space-y-6">
          <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
            <h3 className="text-xl font-semibold text-slate-900">{layout.about?.heading || "About the show"}</h3>
            <p className="mt-2 text-sm leading-6 text-slate-600 whitespace-pre-line">{layout.about?.body || "Tell listeners why your show matters."}</p>
          </div>

          {Array.isArray(layout.episodes) && layout.episodes.length > 0 && (
            <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
              <div className="border-b border-slate-100 px-6 py-4">
                <h3 className="text-lg font-semibold text-slate-900">Episodes</h3>
                <p className="text-xs text-slate-500">Listeners can play episodes right from your site.</p>
              </div>
              <div className="divide-y divide-slate-100">
                {layout.episodes.map((episode, idx) => (
                  <div key={episode.episode_id || idx} className="px-6 py-4 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                    <div>
                      <div className="text-sm font-semibold text-slate-900">{episode.title || "Episode"}</div>
                      {episode.description && (
                        <p className="text-xs text-slate-500 max-w-2xl">{episode.description}</p>
                      )}
                    </div>
                    {episode.cta_url && (
                      <a
                        href={episode.cta_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs font-medium"
                      >
                        <Button
                          size="sm"
                          style={{
                            backgroundColor: accentButtonColors.background || accent,
                            color: accentButtonColors.text,
                          }}
                        >
                          {episode.cta_label || "Play"}
                        </Button>
                      </a>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {Array.isArray(layout.additional_sections) && layout.additional_sections.length > 0 && (
            <div className="space-y-4">
              {layout.additional_sections.map((section, idx) => (
                <div key={idx} className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
                  <h4 className="text-lg font-semibold text-slate-900">{section.heading || "Section"}</h4>
                  {section.body && <p className="mt-2 text-sm leading-6 text-slate-600 whitespace-pre-line">{section.body}</p>}
                </div>
              ))}
            </div>
          )}
        </div>

        <aside className="space-y-6">
          {Array.isArray(layout.hosts) && layout.hosts.length > 0 && (
            <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="text-lg font-semibold text-slate-900">Hosts</h3>
              <ul className="mt-3 space-y-3">
                {layout.hosts.map((host, idx) => (
                  <li key={idx} className="border border-slate-100 rounded-md px-3 py-2">
                    <div className="text-sm font-medium text-slate-900">{host.name || "Host"}</div>
                    {host.bio && <div className="text-xs text-slate-500">{host.bio}</div>}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {layout.call_to_action && (
            <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="text-lg font-semibold text-slate-900">{layout.call_to_action.heading || "Stay in touch"}</h3>
              {layout.call_to_action.body && <p className="mt-2 text-sm text-slate-600">{layout.call_to_action.body}</p>}
              {layout.call_to_action.button_url && (
                <Button
                  asChild
                  className="mt-4"
                  style={{
                    backgroundColor: accentButtonColors.background || accent,
                    borderColor: accentButtonColors.background || accent,
                    color: accentButtonColors.text,
                  }}
                >
                  <a href={layout.call_to_action.button_url} target="_blank" rel="noopener noreferrer">
                    {layout.call_to_action.button_label || "Learn more"}
                  </a>
                </Button>
              )}
            </div>
          )}

          {Array.isArray(layout.section_suggestions) && layout.section_suggestions.length > 0 && (
            <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-6 shadow-sm">
              <h3 className="text-lg font-semibold text-slate-900">Section ideas</h3>
              <p className="mt-1 text-xs text-slate-500">
                Toggle your favorites in the builder. Items marked "recommended" are preloaded on the draft.
              </p>
              <ul className="mt-4 space-y-3">
                {layout.section_suggestions.map((suggestion, idx) => (
                  <li key={idx} className="rounded-md border border-slate-200 bg-white p-3">
                    <div className="flex items-center justify-between text-sm font-medium text-slate-900">
                      <span>{suggestion.label || suggestion.type || "Section"}</span>
                      {suggestion.include_by_default && (
                        <span className="text-xs font-semibold uppercase tracking-wide" style={{ color: accentOnLight }}>
                          Recommended
                        </span>
                      )}
                    </div>
                    {suggestion.description && (
                      <p className="mt-1 text-xs text-slate-500">{suggestion.description}</p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>
      </section>
    </div>
  );
}


