import { useEffect, useMemo, useState } from "react";
import { ArrowLeft, Globe2, Loader2, MessageCircle, RefreshCcw, Wand2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";
import { makeApi } from "@/lib/apiClient";

const CUSTOM_DOMAIN_ALLOWED_TIERS = new Set(["pro", "business", "team", "agency", "enterprise"]);

function SectionHeading({ title, description }) {
  return (
    <div className="space-y-1">
      <h3 className="text-sm font-semibold text-slate-800">{title}</h3>
      {description ? (
        <p className="text-xs text-slate-500">{description}</p>
      ) : null}
    </div>
  );
}

function SitePreview({ website }) {
  if (!website) return null;
  const layout = website.layout || {};
  return (
    <Card className="border border-slate-200 shadow-sm">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Latest layout</CardTitle>
        <CardDescription>Snapshot of the structure the AI most recently produced.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div>
          <SectionHeading title="Hero" />
          <p className="font-semibold text-slate-900">{layout.hero_title || "—"}</p>
          <p className="text-slate-600">{layout.hero_subtitle || "No subtitle yet."}</p>
        </div>
        <div>
          <SectionHeading title={layout?.about?.heading || "About"} />
          <p className="text-slate-600 whitespace-pre-line">
            {(layout?.about?.body || "Use the chat to ask the builder for an intro section.").trim()}
          </p>
        </div>
        {Array.isArray(layout.hosts) && layout.hosts.length > 0 && (
          <div>
            <SectionHeading title="Hosts" />
            <ul className="grid gap-2">
              {layout.hosts.map((host, idx) => (
                <li key={`${host.name || idx}`} className="rounded border border-slate-200 p-3">
                  <p className="text-sm font-semibold text-slate-900">{host.name || "Host"}</p>
                  {host.bio ? <p className="text-xs text-slate-600">{host.bio}</p> : null}
                </li>
              ))}
            </ul>
          </div>
        )}
        {Array.isArray(layout.episodes) && layout.episodes.length > 0 && (
          <div className="space-y-2">
            <SectionHeading title="Featured episodes" />
            <ul className="grid gap-2">
              {layout.episodes.map((episode) => (
                <li key={episode.episode_id} className="rounded border border-slate-200 p-3">
                  <p className="text-sm font-semibold text-slate-900">{episode.title}</p>
                  {episode.description ? (
                    <p className="text-xs text-slate-600">{episode.description}</p>
                  ) : null}
                  {episode.cta_label ? (
                    <div className="mt-2 text-xs text-slate-500">
                      CTA: <span className="font-medium text-slate-700">{episode.cta_label}</span>
                      {episode.cta_url ? ` → ${episode.cta_url}` : ""}
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          </div>
        )}
        {layout?.call_to_action?.heading && (
          <div>
            <SectionHeading title="Call to action" />
            <p className="text-sm font-semibold text-slate-900">{layout.call_to_action.heading}</p>
            <p className="text-xs text-slate-600">{layout.call_to_action.body}</p>
            <p className="text-xs text-slate-500 mt-1">
              Button: <span className="font-medium text-slate-700">{layout.call_to_action.button_label}</span>{" "}
              {layout.call_to_action.button_url ? `→ ${layout.call_to_action.button_url}` : null}
            </p>
          </div>
        )}
        {Array.isArray(layout.additional_sections) && layout.additional_sections.length > 0 && (
          <div className="space-y-2">
            <SectionHeading title="Additional sections" />
            <ul className="grid gap-2">
              {layout.additional_sections.map((section, idx) => (
                <li key={`${section.heading || section.type || idx}`} className="rounded border border-slate-200 p-3">
                  <p className="text-sm font-semibold text-slate-900">
                    {section.heading || section.type || "Section"}
                  </p>
                  {section.body ? <p className="text-xs text-slate-600">{section.body}</p> : null}
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function WebsiteBuilder({ token, podcasts, onBack, user }) {
  const { toast } = useToast();
  const api = useMemo(() => makeApi(token), [token]);
  const [selectedPodcastId, setSelectedPodcastId] = useState(null);
  const [website, setWebsite] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isChatting, setIsChatting] = useState(false);
  const [chatMessage, setChatMessage] = useState("");
  const [customDomain, setCustomDomain] = useState("");
  const [isSavingDomain, setIsSavingDomain] = useState(false);
  const [loadError, setLoadError] = useState(null);

  const normalizedTier = (user?.tier || "").toLowerCase();
  const canUseCustomDomain = CUSTOM_DOMAIN_ALLOWED_TIERS.has(normalizedTier);

  useEffect(() => {
    if (!selectedPodcastId && podcasts && podcasts.length > 0) {
      setSelectedPodcastId(podcasts[0].id);
    }
  }, [podcasts, selectedPodcastId]);

  const fetchWebsite = async (podcastId) => {
    if (!podcastId) return;
    setIsLoading(true);
    setLoadError(null);
    try {
      const data = await api.get(`/api/podcasts/${podcastId}/website`);
      setWebsite(data);
      setCustomDomain(data.custom_domain || "");
    } catch (err) {
      if (err?.status === 404) {
        setWebsite(null);
        setCustomDomain("");
      } else {
        console.error("Failed to load website", err);
        setLoadError(err?.detail || err?.message || "Unable to load website.");
        toast({
          title: "Failed to load website",
          description: err?.detail || err?.message || "Try again in a few minutes.",
          variant: "destructive",
        });
      }
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (selectedPodcastId) {
      fetchWebsite(selectedPodcastId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedPodcastId]);

  const handleGenerate = async () => {
    if (!selectedPodcastId) return;
    setIsGenerating(true);
    try {
      const data = await api.post(`/api/podcasts/${selectedPodcastId}/website`);
      setWebsite(data);
      setCustomDomain(data.custom_domain || "");
      toast({
        title: "Website generated",
        description: "The AI builder refreshed your site layout.",
      });
    } catch (err) {
      console.error("Failed to generate website", err);
      toast({
        title: "Generation failed",
        description: err?.detail || err?.message || "Gemini was unable to build the site.",
        variant: "destructive",
      });
    } finally {
      setIsGenerating(false);
    }
  };

  const handleChat = async () => {
    if (!selectedPodcastId || !chatMessage.trim()) return;
    setIsChatting(true);
    try {
      const data = await api.post(`/api/podcasts/${selectedPodcastId}/website/chat`, {
        message: chatMessage.trim(),
      });
      setWebsite(data);
      setCustomDomain(data.custom_domain || "");
      setChatMessage("");
      toast({
        title: "Update applied",
        description: "The builder incorporated your request.",
      });
    } catch (err) {
      console.error("Chat update failed", err);
      toast({
        title: "Update failed",
        description: err?.detail || err?.message || "The builder could not apply that request.",
        variant: "destructive",
      });
    } finally {
      setIsChatting(false);
    }
  };

  const handleDomainSave = async () => {
    if (!selectedPodcastId) return;
    setIsSavingDomain(true);
    try {
      const payload = { custom_domain: customDomain.trim() || null };
      const data = await api.patch(`/api/podcasts/${selectedPodcastId}/website/domain`, payload);
      setWebsite(data);
      setCustomDomain(data.custom_domain || "");
      toast({
        title: "Domain settings saved",
        description: data.custom_domain
          ? `Custom domain updated to ${data.custom_domain}.`
          : "Custom domain removed.",
      });
    } catch (err) {
      console.error("Failed to save domain", err);
      toast({
        title: "Domain update failed",
        description: err?.detail || err?.message || "Check the domain and try again.",
        variant: "destructive",
      });
    } finally {
      setIsSavingDomain(false);
    }
  };

  const selectedPodcast = podcasts?.find((pod) => pod.id === selectedPodcastId) || null;
  const defaultUrl = website?.default_domain ? `https://${website.default_domain}` : null;
  const customUrl = website?.custom_domain ? `https://${website.custom_domain}` : null;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={onBack} className="-ml-2">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back to dashboard
        </Button>
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Podcast website builder</h1>
          <p className="text-sm text-slate-600">
            Generate an AI-crafted landing page for your show and iterate by chatting with the builder.
          </p>
        </div>
      </div>

      <Card className="border border-slate-200 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Pick a podcast</CardTitle>
          <CardDescription>Select the show you want to build a site for.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {podcasts && podcasts.length > 0 ? (
            <Select value={selectedPodcastId || ""} onValueChange={setSelectedPodcastId}>
              <SelectTrigger className="w-full md:w-80">
                <SelectValue placeholder="Choose a podcast" />
              </SelectTrigger>
              <SelectContent>
                {podcasts.map((podcast) => (
                  <SelectItem value={podcast.id} key={podcast.id}>
                    {podcast.name || podcast.title || "Untitled podcast"}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <p className="text-sm text-slate-600">
              You don&apos;t have any podcasts yet. Create one from the dashboard to get started.
            </p>
          )}
          {loadError ? (
            <p className="text-xs text-red-600">{loadError}</p>
          ) : null}
        </CardContent>
      </Card>

      {selectedPodcast ? (
        <div className="grid lg:grid-cols-[2fr_1fr] gap-6">
          <div className="space-y-6">
            <Card className="border border-slate-200 shadow-sm">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">AI generation</CardTitle>
                <CardDescription>
                  We&apos;ll analyze {selectedPodcast.name || "your podcast"} and its recent episodes to produce a full landing page.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex flex-wrap items-center gap-3">
                  <Button onClick={handleGenerate} disabled={isGenerating || isLoading}>
                    {isGenerating ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <Wand2 className="mr-2 h-4 w-4" />
                    )}
                    {website ? "Refresh layout" : "Generate website"}
                  </Button>
                  <Button
                    variant="outline"
                    asChild
                    disabled={!website}
                  >
                    <a
                      href={customUrl || defaultUrl || "#"}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <Globe2 className="mr-2 h-4 w-4" />
                      {website?.custom_domain ? "Open custom domain" : "Open live site"}
                    </a>
                  </Button>
                  {website?.prompt_log_path ? (
                    <a
                      className="text-xs text-slate-500 hover:text-slate-700"
                      href={`https://console.cloud.google.com/storage/browser/_details/${website.prompt_log_path}`}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      View prompt log in Cloud Storage
                    </a>
                  ) : null}
                </div>
                {website ? (
                  <div className="grid gap-4 rounded border border-slate-200 bg-slate-50 p-4 text-sm">
                    <div className="flex flex-col">
                      <span className="text-xs uppercase tracking-wide text-slate-500">Status</span>
                      <span className="font-medium text-slate-800 capitalize">{website.status}</span>
                    </div>
                    <div className="flex flex-col">
                      <span className="text-xs uppercase tracking-wide text-slate-500">Default domain</span>
                      <a
                        className="font-medium text-blue-600 hover:underline"
                        href={defaultUrl || "#"}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {website.default_domain}
                      </a>
                    </div>
                    {website.custom_domain ? (
                      <div className="flex flex-col">
                        <span className="text-xs uppercase tracking-wide text-slate-500">Custom domain</span>
                        <a
                          className="font-medium text-blue-600 hover:underline"
                          href={customUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          {website.custom_domain}
                        </a>
                      </div>
                    ) : null}
                    {website.last_generated_at ? (
                      <div className="flex flex-col">
                        <span className="text-xs uppercase tracking-wide text-slate-500">Last generated</span>
                        <span className="font-medium text-slate-800">
                          {new Date(website.last_generated_at).toLocaleString()}
                        </span>
                      </div>
                    ) : null}
                  </div>
                ) : (
                  <p className="text-sm text-slate-600">
                    No site yet. Click <strong>Generate website</strong> to spin up your first draft.
                  </p>
                )}
              </CardContent>
            </Card>

            <Card className="border border-slate-200 shadow-sm">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Chat with the builder</CardTitle>
                <CardDescription>
                  Ask for copy tweaks, new sections, or design adjustments. The builder will regenerate the layout to match.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <Label htmlFor="builder-message" className="text-xs text-slate-500 uppercase tracking-wide">
                  Instruction
                </Label>
                <Textarea
                  id="builder-message"
                  value={chatMessage}
                  onChange={(event) => setChatMessage(event.target.value)}
                  placeholder="Example: Add a testimonials section with three quotes from superfans."
                  rows={4}
                  disabled={isChatting || isLoading || !website}
                />
                <div className="flex justify-end">
                  <Button onClick={handleChat} disabled={isChatting || !chatMessage.trim() || !website}>
                    {isChatting ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <MessageCircle className="mr-2 h-4 w-4" />
                    )}
                    Send to builder
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="space-y-6">
            {canUseCustomDomain ? (
              <Card className="border border-slate-200 shadow-sm">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base">Custom domain</CardTitle>
                  <CardDescription>
                    Point your own domain at our builder. Leave blank and save to remove.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <Label htmlFor="custom-domain" className="text-xs uppercase tracking-wide text-slate-500">
                    Domain (example: podcast.example.com)
                  </Label>
                  <Input
                    id="custom-domain"
                    value={customDomain}
                    onChange={(event) => setCustomDomain(event.target.value)}
                    placeholder="podcast.example.com"
                    disabled={isSavingDomain || !website}
                  />
                  <Button onClick={handleDomainSave} disabled={isSavingDomain || !website}>
                    {isSavingDomain ? (
                      <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                      <RefreshCcw className="mr-2 h-4 w-4" />
                    )}
                    Save domain
                  </Button>
                  {!website ? (
                    <p className="text-xs text-slate-500">
                      Generate your site before connecting a custom domain.
                    </p>
                  ) : null}
                </CardContent>
              </Card>
            ) : (
              <Card className="border border-dashed border-amber-300 bg-amber-50/50">
                <CardHeader className="pb-3">
                  <CardTitle className="text-base text-amber-900">Custom domains unlock on Pro</CardTitle>
                  <CardDescription className="text-amber-800">
                    Upgrade to Pro to map your own URL. You can still publish to our default domain today.
                  </CardDescription>
                </CardHeader>
              </Card>
            )}

            <SitePreview website={website} />
          </div>
        </div>
      ) : null}

      {isLoading ? (
        <div className="flex items-center gap-2 text-sm text-slate-600">
          <Loader2 className="h-4 w-4 animate-spin" /> Fetching website details…
        </div>
      ) : null}
    </div>
  );
}
