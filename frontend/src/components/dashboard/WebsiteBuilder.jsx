import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, ExternalLink, Loader2, RefreshCcw, Send, ServerCog } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { makeApi, isApiError } from "@/lib/apiClient";
import { useToast } from "@/hooks/use-toast";

const statusCopy = {
  draft: { label: "Draft", tone: "bg-amber-100 text-amber-800" },
  published: { label: "Published", tone: "bg-emerald-100 text-emerald-800" },
  updating: { label: "Updating", tone: "bg-sky-100 text-sky-800" },
};

function formatRelativeTime(iso) {
  if (!iso) return "—";
  try {
    const timestamp = new Date(iso).getTime();
    if (Number.isNaN(timestamp)) return "—";
    const diffMs = Date.now() - timestamp;
    if (diffMs < 60_000) return "just now";
    const diffMinutes = Math.floor(diffMs / 60_000);
    if (diffMinutes < 60) return `${diffMinutes}m ago`;
    const diffHours = Math.floor(diffMinutes / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 30) return `${diffDays}d ago`;
    const diffMonths = Math.floor(diffDays / 30);
    if (diffMonths < 12) return `${diffMonths}mo ago`;
    const diffYears = Math.floor(diffMonths / 12);
    return `${diffYears}y ago`;
  } catch (err) {
    console.warn("[website-builder] failed to format timestamp", err);
    return "—";
  }
}

function PreviewSection({ website }) {
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
  const liveUrl = website.custom_domain
    ? `https://${website.custom_domain}`
    : website.default_domain
      ? `https://${website.default_domain}`
      : null;

  return (
    <div className="space-y-8">
      <section
        className="rounded-2xl shadow-sm overflow-hidden"
        style={{ backgroundColor: heroBg, color: heroFg }}
      >
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
              className="mt-2 bg-white text-slate-900 hover:bg-slate-200"
            >
              <a href={liveUrl} target="_blank" rel="noopener noreferrer">
                <ExternalLink className="mr-2 h-4 w-4" /> View live site
              </a>
            </Button>
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
                        className="text-xs font-medium text-white"
                      >
                        <Button size="sm" style={{ backgroundColor: accent }}>
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
                  style={{ backgroundColor: accent, borderColor: accent }}
                >
                  <a href={layout.call_to_action.button_url} target="_blank" rel="noopener noreferrer">
                    {layout.call_to_action.button_label || "Learn more"}
                  </a>
                </Button>
              )}
            </div>
          )}
        </aside>
      </section>
    </div>
  );
}

export default function WebsiteBuilder({ token, podcasts, onBack, allowCustomDomain }) {
  const { toast } = useToast();
  const [selectedPodcastId, setSelectedPodcastId] = useState(() => (podcasts && podcasts[0] ? podcasts[0].id : ""));
  const [website, setWebsite] = useState(null);
  const [loading, setLoading] = useState(false);
  const [actionState, setActionState] = useState({ creating: false, chatting: false, savingDomain: false });
  const [error, setError] = useState(null);
  const [chatMessage, setChatMessage] = useState("");
  const [domainDraft, setDomainDraft] = useState("");

  const api = useMemo(() => makeApi(token), [token]);

  useEffect(() => {
    if (!selectedPodcastId && podcasts && podcasts.length > 0) {
      setSelectedPodcastId(podcasts[0].id);
    }
  }, [podcasts, selectedPodcastId]);

  const loadWebsite = useCallback(async (podcastId) => {
    if (!podcastId) {
      setWebsite(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const data = await api.get(`/api/podcasts/${podcastId}/website`);
      setWebsite(data);
      setDomainDraft(data.custom_domain || "");
    } catch (err) {
      if (err && err.status === 404) {
        setWebsite(null);
        setDomainDraft("");
      } else {
        console.error("Failed to load website", err);
        const message = isApiError(err) ? (err.detail || err.message || err.error || "Unable to load site") : "Unable to load site";
        setError(message);
      }
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    if (selectedPodcastId) {
      loadWebsite(selectedPodcastId);
    }
  }, [selectedPodcastId, loadWebsite]);

  const handleGenerate = async () => {
    if (!selectedPodcastId) return;
    setActionState((prev) => ({ ...prev, creating: true }));
    setError(null);
    try {
      const data = await api.post(`/api/podcasts/${selectedPodcastId}/website`);
      setWebsite(data);
      setDomainDraft(data.custom_domain || "");
      toast({ title: "Website drafted", description: "The AI builder prepared a fresh layout." });
    } catch (err) {
      console.error("Failed to generate website", err);
      const message = isApiError(err) ? (err.detail || err.message || err.error || "Unable to generate site") : "Unable to generate site";
      setError(message);
    } finally {
      setActionState((prev) => ({ ...prev, creating: false }));
    }
  };

  const handleChat = async () => {
    if (!selectedPodcastId || !chatMessage.trim()) return;
    setActionState((prev) => ({ ...prev, chatting: true }));
    setError(null);
    try {
      const data = await api.post(`/api/podcasts/${selectedPodcastId}/website/chat`, { message: chatMessage.trim() });
      setWebsite(data);
      setDomainDraft(data.custom_domain || "");
      setChatMessage("");
      toast({ title: "Update applied", description: "The AI builder adjusted your layout." });
    } catch (err) {
      console.error("Failed to apply update", err);
      const message = isApiError(err) ? (err.detail || err.message || err.error || "Unable to update site") : "Unable to update site";
      setError(message);
    } finally {
      setActionState((prev) => ({ ...prev, chatting: false }));
    }
  };

  const handleDomainSave = async () => {
    if (!selectedPodcastId) return;
    setActionState((prev) => ({ ...prev, savingDomain: true }));
    setError(null);
    try {
      const payload = { custom_domain: domainDraft.trim() ? domainDraft.trim() : null };
      const data = await api.patch(`/api/podcasts/${selectedPodcastId}/website/domain`, payload);
      setWebsite(data);
      setDomainDraft(data.custom_domain || "");
      toast({ title: "Domain updated", description: data.custom_domain ? `Live at ${data.custom_domain}` : "Using the default domain." });
    } catch (err) {
      console.error("Failed to update domain", err);
      const message = isApiError(err) ? (err.detail || err.message || err.error || "Unable to update domain") : "Unable to update domain";
      setError(message);
    } finally {
      setActionState((prev) => ({ ...prev, savingDomain: false }));
    }
  };

  const liveUrl = useMemo(() => {
    if (!website) return null;
    if (website.custom_domain) return `https://${website.custom_domain}`;
    if (website.default_domain) return `https://${website.default_domain}`;
    return null;
  }, [website]);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={onBack} className="text-slate-600 hover:text-slate-900">
          <ArrowLeft className="mr-2 h-4 w-4" /> Back to dashboard
        </Button>
        <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Website Builder</div>
      </div>

      <Card className="border border-slate-200 shadow-sm">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl font-semibold text-slate-900">AI Website Builder</CardTitle>
          <CardDescription className="text-sm text-slate-600">
            Spin up a shareable site for any of your podcasts, chat with the AI to tweak sections, and publish instantly on a custom subdomain.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {podcasts.length === 0 ? (
            <div className="rounded-md border border-dashed border-slate-300 bg-slate-50 px-4 py-6 text-center text-sm text-slate-600">
              Create a podcast first and it will appear here for website generation.
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-[minmax(0,320px)_1fr]">
              <div className="space-y-4">
                <div className="space-y-2">
                  <label className="text-xs font-medium uppercase tracking-wide text-slate-500">Podcast</label>
                  <Select value={selectedPodcastId} onValueChange={setSelectedPodcastId}>
                    <SelectTrigger className="w-full">
                      <SelectValue placeholder="Choose a podcast" />
                    </SelectTrigger>
                    <SelectContent>
                      {podcasts.map((podcast) => (
                        <SelectItem key={podcast.id} value={podcast.id}>
                          {podcast.name || "Untitled podcast"}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="rounded-md border border-slate-200 bg-white p-4 shadow-sm space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="text-xs font-semibold uppercase tracking-widest text-slate-500">Status</div>
                    <div>
                      {website?.status ? (
                        <Badge className={statusCopy[website.status]?.tone || "bg-slate-200 text-slate-700"}>
                          {statusCopy[website.status]?.label || website.status}
                        </Badge>
                      ) : (
                        <Badge variant="outline">No site yet</Badge>
                      )}
                    </div>
                  </div>
                  <div className="space-y-1 text-xs text-slate-500">
                    <div className="flex items-center gap-2">
                      <ServerCog className="h-4 w-4 text-slate-400" />
                      <span>
                        {website?.last_generated_at
                          ? `Last generated ${formatRelativeTime(website.last_generated_at)}`
                          : "No generation history yet"}
                      </span>
                    </div>
                    {liveUrl && (
                      <div className="flex items-center gap-2">
                        <ExternalLink className="h-4 w-4 text-slate-400" />
                        <a href={liveUrl} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline text-xs break-all">
                          {liveUrl}
                        </a>
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col gap-2">
                    <Button onClick={handleGenerate} disabled={actionState.creating || loading || !selectedPodcastId}>
                      {actionState.creating ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <RefreshCcw className="mr-2 h-4 w-4" />}
                      {website ? "Refresh with AI" : "Create my site"}
                    </Button>
                  </div>
                </div>

                {allowCustomDomain && (
                  <div className="space-y-2">
                    <label className="text-xs font-medium uppercase tracking-wide text-slate-500">Custom domain</label>
                    <div className="flex flex-col gap-2">
                      <Input
                        placeholder="e.g. podcast.example.com"
                        value={domainDraft}
                        onChange={(event) => setDomainDraft(event.target.value)}
                        disabled={actionState.savingDomain}
                      />
                      <div className="flex gap-2">
                        <Button
                          size="sm"
                          onClick={handleDomainSave}
                          disabled={actionState.savingDomain}
                        >
                          {actionState.savingDomain ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
                          Save domain
                        </Button>
                        {website?.custom_domain && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => setDomainDraft("")}
                            disabled={actionState.savingDomain}
                          >
                            Clear
                          </Button>
                        )}
                      </div>
                      <p className="text-xs text-slate-500">
                        Use a subdomain you control. We will prompt you for DNS once saved.
                      </p>
                    </div>
                  </div>
                )}

                <div className="space-y-2">
                  <label className="text-xs font-medium uppercase tracking-wide text-slate-500">Ask the builder</label>
                  <Textarea
                    placeholder="e.g. Add a section for listener testimonials and brighten the hero image."
                    value={chatMessage}
                    onChange={(event) => setChatMessage(event.target.value)}
                    rows={4}
                    disabled={actionState.chatting || loading || !website}
                  />
                  <div className="flex justify-end">
                    <Button
                      onClick={handleChat}
                      disabled={!chatMessage.trim() || actionState.chatting || !website}
                    >
                      {actionState.chatting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Send className="mr-2 h-4 w-4" />}
                      Send to AI
                    </Button>
                  </div>
                </div>
              </div>

              <div className="min-h-[420px]">
                {loading ? (
                  <div className="flex h-full min-h-[420px] items-center justify-center rounded-lg border border-slate-200 bg-white">
                    <Loader2 className="h-6 w-6 animate-spin text-slate-500" />
                  </div>
                ) : (
                  <PreviewSection website={website} />
                )}
              </div>
            </div>
          )}

          {error && (
            <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
              {error}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

