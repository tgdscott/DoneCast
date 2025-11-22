import React, { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { ExternalLink, AlertCircle, CheckCircle2, Loader2, Copy, Check } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { makeApi } from "@/lib/apiClient";

export default function DistributionRequiredStep({ wizard }) {
  const { token, targetPodcastId, rssFeedUrl, setRssFeedUrl } = wizard;
  const [loading, setLoading] = useState(false);
  const [checklist, setChecklist] = useState(null);
  const [appleStatus, setAppleStatus] = useState("not_started");
  const [spotifyStatus, setSpotifyStatus] = useState("not_started");
  const [skipped, setSkipped] = useState(false);
  const [hasPublishedEpisodes, setHasPublishedEpisodes] = useState(false);
  const [copied, setCopied] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    if (targetPodcastId && token) {
      loadChecklist();
    } else if (!targetPodcastId && token) {
      // Try to find existing podcast (even without formData, in case podcast was created earlier)
      findExistingPodcast();
    }
  }, [targetPodcastId, token]);

  const findExistingPodcast = async () => {
    if (!token) return;
    try {
      const api = makeApi(token);
      const data = await api.get("/api/podcasts/");
      const podcasts = Array.isArray(data) ? data : data?.items || [];
      if (podcasts.length > 0 && wizard?.setTargetPodcastId) {
        // Try to match by name if we have formData
        const nameClean = wizard?.formData?.podcastName?.trim().toLowerCase();
        let selectedPodcast = podcasts[0];
        
        if (nameClean) {
          const matching = podcasts.find(p => 
            p.name && p.name.trim().toLowerCase() === nameClean
          );
          if (matching) {
            selectedPodcast = matching;
          }
        }
        
        wizard.setTargetPodcastId(selectedPodcast.id);
        console.log("[Onboarding] Found existing podcast:", selectedPodcast.id);
      } else if (podcasts.length === 0) {
        console.warn("[Onboarding] No podcasts found - user may need to create one first");
      }
    } catch (err) {
      console.error("[Onboarding] Failed to load podcasts:", err);
      // If it's a 404, the endpoint might not exist or user has no podcasts
      // Don't show error to user, just log it
      if (err?.status === 404) {
        console.warn("[Onboarding] Podcasts endpoint returned 404 - endpoint may not be available");
      }
    }
  };

  const loadChecklist = async () => {
    if (!targetPodcastId || !token) {
      // If no targetPodcastId, try to find one first
      if (!targetPodcastId && token) {
        await findExistingPodcast();
        // Wait a moment for state to update, then retry if we found one
        setTimeout(() => {
          if (wizard?.targetPodcastId) {
            loadChecklist();
          }
        }, 100);
      }
      return;
    }
    
    setLoading(true);
    try {
      const api = makeApi(token);
      const data = await api.get(`/api/podcasts/${targetPodcastId}/distribution/checklist`);
      
      const apple = data.items?.find(item => item.key === "apple_podcasts");
      const spotify = data.items?.find(item => item.key === "spotify");
      
      setChecklist(data);
      setAppleStatus(apple?.status || "not_started");
      setSpotifyStatus(spotify?.status || "not_started");
      setHasPublishedEpisodes(data?.has_published_episodes || false);
      
      // Update RSS feed URL in wizard context
      if (data.rss_feed_url && setRssFeedUrl) {
        setRssFeedUrl(data.rss_feed_url);
      }
    } catch (err) {
      console.error("[Onboarding] Failed to load distribution checklist:", err);
      // If it's a 404, the podcast might not exist - try finding it again
      if (err?.status === 404 && token) {
        console.log("[Onboarding] Checklist returned 404, trying to find podcast again...");
        await findExistingPodcast();
      }
    } finally {
      setLoading(false);
    }
  };

  const updateStatus = async (platformKey, newStatus) => {
    if (!targetPodcastId || !token) return;
    
    try {
      const api = makeApi(token);
      await api.put(
        `/api/podcasts/${targetPodcastId}/distribution/checklist/${platformKey}`,
        { status: newStatus }
      );
      
      if (platformKey === "apple_podcasts") {
        setAppleStatus(newStatus);
      } else if (platformKey === "spotify") {
        setSpotifyStatus(newStatus);
      }
      
      toast({ title: "Status updated" });
    } catch (err) {
      toast({
        variant: "destructive",
        title: "Failed to update status",
        description: err?.message || "Please try again.",
      });
    }
  };

  const appleItem = checklist?.items?.find(item => item.key === "apple_podcasts");
  const spotifyItem = checklist?.items?.find(item => item.key === "spotify");

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        <span className="ml-2 text-sm text-muted-foreground">Loading distribution options...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <p className="text-sm font-medium">
          We want to set you up for success, and these are the two largest podcasting platforms that you need to be on.
        </p>
        <p className="text-xs text-muted-foreground">
          Submitting to these platforms helps listeners find your podcast. We strongly recommend submitting now, 
          but you can skip and do it later if needed.
        </p>
      </div>

      {!hasPublishedEpisodes && (
        <div className="p-4 border border-yellow-500/50 bg-yellow-500/10 rounded-lg">
          <div className="flex items-start gap-2">
            <AlertCircle className="h-5 w-5 text-yellow-600 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium text-yellow-900 dark:text-yellow-100">
                RSS feed not ready yet
              </p>
              <p className="text-xs text-yellow-700 dark:text-yellow-300 mt-1">
                You'll need to publish your first episode before submitting to these platforms. 
                Apple Podcasts and Spotify require at least one published episode with audio. 
                You can complete this step later in Settings → Distribution.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* RSS Feed Display */}
      {(rssFeedUrl || checklist?.rss_feed_url) && (
        <div className="p-4 border rounded-lg bg-muted/30 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="flex-1 min-w-0">
              <label className="text-xs font-medium text-muted-foreground mb-1 block">
                Your RSS Feed URL
              </label>
              <div className="flex items-center gap-2">
                <code className="flex-1 text-sm font-mono break-all bg-background px-2 py-1.5 rounded border">
                  {rssFeedUrl || checklist?.rss_feed_url}
                </code>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={async () => {
                    const feedUrl = rssFeedUrl || checklist?.rss_feed_url || "";
                    try {
                      await navigator.clipboard.writeText(feedUrl);
                      setCopied(true);
                      toast({
                        title: "Copied!",
                        description: "RSS feed URL copied to clipboard",
                      });
                      setTimeout(() => setCopied(false), 2000);
                    } catch (err) {
                      // Fallback for older browsers
                      const textArea = document.createElement("textarea");
                      textArea.value = feedUrl;
                      document.body.appendChild(textArea);
                      textArea.select();
                      try {
                        document.execCommand("copy");
                        setCopied(true);
                        toast({
                          title: "Copied!",
                          description: "RSS feed URL copied to clipboard",
                        });
                        setTimeout(() => setCopied(false), 2000);
                      } catch (fallbackErr) {
                        toast({
                          variant: "destructive",
                          title: "Failed to copy",
                          description: "Please copy the URL manually",
                        });
                      }
                      document.body.removeChild(textArea);
                    }
                  }}
                  className="shrink-0"
                >
                  {copied ? (
                    <>
                      <Check className="h-4 w-4 mr-2" />
                      Copied
                    </>
                  ) : (
                    <>
                      <Copy className="h-4 w-4 mr-2" />
                      Copy
                    </>
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="space-y-4">
        {/* Apple Podcasts */}
        {appleItem && (
          <div className="p-4 border rounded-lg space-y-3">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <h3 className="font-semibold flex items-center gap-2">
                  {appleItem.name}
                  {appleStatus === "completed" && (
                    <CheckCircle2 className="h-4 w-4 text-green-600" />
                  )}
                </h3>
                <p className="text-sm text-muted-foreground mt-1">{appleItem.summary}</p>
                {appleItem.automation_notes && (
                  <p className="text-xs text-muted-foreground mt-1">{appleItem.automation_notes}</p>
                )}
              </div>
            </div>
            
            {(rssFeedUrl || checklist?.rss_feed_url) && appleItem.action_url && (
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => window.open(appleItem.action_url, "_blank")}
                  disabled={!hasPublishedEpisodes}
                  asChild
                >
                  <a href={appleItem.action_url} target="_blank" rel="noreferrer">
                    <ExternalLink className="h-4 w-4 mr-2" />
                    {appleItem.action_label || "Open Podcasts Connect"}
                  </a>
                </Button>
                <div className="flex items-center gap-2">
                  <select
                    className="text-xs border rounded px-2 py-1"
                    value={appleStatus}
                    onChange={(e) => updateStatus("apple_podcasts", e.target.value)}
                  >
                    <option value="not_started">Not started</option>
                    <option value="in_progress">In progress</option>
                    <option value="completed">Completed</option>
                  </select>
                </div>
              </div>
            )}

            {hasPublishedEpisodes && (rssFeedUrl || checklist?.rss_feed_url) && appleItem.instructions && (
              <details className="text-xs text-muted-foreground">
                <summary className="cursor-pointer hover:text-foreground">Show instructions</summary>
                <ol className="list-decimal list-inside mt-2 space-y-1 pl-2">
                  {appleItem.instructions.map((step, idx) => (
                    <li key={idx}>{step.replace("{rss_feed_url}", rssFeedUrl || checklist?.rss_feed_url || "")}</li>
                  ))}
                </ol>
              </details>
            )}
          </div>
        )}

        {/* Spotify */}
        {spotifyItem && (
          <div className="p-4 border rounded-lg space-y-3">
            <div className="flex items-start justify-between">
              <div className="flex-1">
                <h3 className="font-semibold flex items-center gap-2">
                  {spotifyItem.name}
                  {spotifyStatus === "completed" && (
                    <CheckCircle2 className="h-4 w-4 text-green-600" />
                  )}
                </h3>
                <p className="text-sm text-muted-foreground mt-1">{spotifyItem.summary}</p>
                {spotifyItem.automation_notes && (
                  <p className="text-xs text-muted-foreground mt-1">{spotifyItem.automation_notes}</p>
                )}
              </div>
            </div>
            
            {(rssFeedUrl || checklist?.rss_feed_url) && spotifyItem.action_url && (
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    const feed = rssFeedUrl || checklist?.rss_feed_url || "";
                    const encodedFeed = encodeURIComponent(feed);
                    const url = spotifyItem.action_url_template?.replace("{rss_feed_encoded}", encodedFeed) || spotifyItem.action_url;
                    window.open(url, "_blank");
                  }}
                  disabled={!hasPublishedEpisodes}
                >
                  <ExternalLink className="h-4 w-4 mr-2" />
                  {spotifyItem.action_label || "Submit to Spotify"}
                </Button>
                <div className="flex items-center gap-2">
                  <select
                    className="text-xs border rounded px-2 py-1"
                    value={spotifyStatus}
                    onChange={(e) => updateStatus("spotify", e.target.value)}
                  >
                    <option value="not_started">Not started</option>
                    <option value="in_progress">In progress</option>
                    <option value="completed">Completed</option>
                  </select>
                </div>
              </div>
            )}

            {hasPublishedEpisodes && (rssFeedUrl || checklist?.rss_feed_url) && spotifyItem.instructions && (
              <details className="text-xs text-muted-foreground">
                <summary className="cursor-pointer hover:text-foreground">Show instructions</summary>
                <ol className="list-decimal list-inside mt-2 space-y-1 pl-2">
                  {spotifyItem.instructions.map((step, idx) => (
                    <li key={idx}>{step.replace("{rss_feed_url}", rssFeedUrl || checklist?.rss_feed_url || "")}</li>
                  ))}
                </ol>
              </details>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 pt-2 border-t">
        <input
          id="skipDistribution"
          type="checkbox"
          checked={skipped}
          onChange={(e) => setSkipped(e.target.checked)}
        />
        <label htmlFor="skipDistribution" className="text-sm text-muted-foreground cursor-pointer">
          I'll submit to these platforms later (not recommended)
        </label>
      </div>
    </div>
  );
}

