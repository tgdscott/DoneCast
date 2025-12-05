import React, { useState, useEffect, useMemo, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { ExternalLink, AlertCircle, CheckCircle2, Loader2, Copy, Check } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { makeApi } from "@/lib/apiClient";
import { copyTextToClipboard } from "@/lib/clipboard";
import { ConfettiBurst } from "../components/ConfettiBurst.jsx";

const CONFETTI_COLORS = [
  "#FF6B6B",
  "#4ECDC4",
  "#45B7D1",
  "#FFA07A",
  "#98D8C8",
  "#F7DC6F",
  "#BB8FCE",
  "#85C1E2",
];

export default function DistributionRequiredStep({ wizard }) {
  const {
    token,
    targetPodcastId,
    setTargetPodcastId,
    rssFeedUrl,
    setRssFeedUrl,
    ensurePodcastExists,
    rssStatus,
    refreshRssMetadata,
    showRssWaiting,
    setShowRssWaiting,
    setDistributionReady,
  } = wizard;
  const [loading, setLoading] = useState(false);
  const [checklist, setChecklist] = useState(null);
  const [appleStatus, setAppleStatus] = useState("not_started");
  const [spotifyStatus, setSpotifyStatus] = useState("not_started");
  const [skipped, setSkipped] = useState(false);
  const [hasPublishedEpisodes, setHasPublishedEpisodes] = useState(false);
  const [copied, setCopied] = useState(false);
  const [refreshingRss, setRefreshingRss] = useState(false);
  const [appleCompleting, setAppleCompleting] = useState(false);
  const [spotifyCompleting, setSpotifyCompleting] = useState(false);
  const [confettiBursts, setConfettiBursts] = useState([]);
  const { toast } = useToast();
  const checklistFeed = checklist?.rss_feed_url || "";
  const resolvedFeedUrl = useMemo(() => rssFeedUrl || checklistFeed || "", [rssFeedUrl, checklistFeed]);

  const copyRssFeed = useCallback(
    async ({ successDescription } = {}) => {
      if (!resolvedFeedUrl) {
        toast({
          variant: "destructive",
          title: "RSS feed unavailable",
          description: "We couldn't find your DoneCast RSS feed yet. Please refresh and try again.",
        });
        return false;
      }

      const copied = await copyTextToClipboard(resolvedFeedUrl);
      if (copied) {
        if (successDescription) {
          toast({ title: "Copied!", description: successDescription });
        }
        return true;
      }

      toast({
        variant: "destructive",
        title: "Copy failed",
        description: "Please copy the RSS feed manually.",
      });
      return false;
    },
    [resolvedFeedUrl, toast]
  );

  useEffect(() => {
    let cancelled = false;

    const bootstrap = async () => {
      if (!token) {
        return;
      }

      if (!targetPodcastId) {
        if (typeof ensurePodcastExists === "function") {
          const podcast = await ensurePodcastExists();
          if (cancelled) return;
          if (podcast?.id) {
            setTargetPodcastId?.(podcast.id);
            return;
          }
        }
        await findExistingPodcast();
        return;
      }

      await loadChecklist();
    };

    bootstrap();

    return () => {
      cancelled = true;
    };
  }, [targetPodcastId, token, ensurePodcastExists, setTargetPodcastId]);

  useEffect(() => {
    if (!token || !targetPodcastId || rssFeedUrl) {
      return;
    }
    refreshRssMetadata?.().catch((err) => {
      if (err) {
        console.warn("[Onboarding] RSS refresh failed in distribution step:", err);
      }
    });
  }, [token, targetPodcastId, rssFeedUrl, refreshRssMetadata]);

  const findExistingPodcast = async () => {
    if (!token) return;
    try {
      const api = makeApi(token);
      const data = await api.get("/api/podcasts/");
      const podcasts = Array.isArray(data) ? data : data?.items || [];
      if (podcasts.length > 0 && setTargetPodcastId) {
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
        
        setTargetPodcastId(selectedPodcast.id);
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
      throw err;
    }
  };

  const waitingForRss = !targetPodcastId || !resolvedFeedUrl;

  useEffect(() => {
    if (!setShowRssWaiting) {
      return;
    }
    setShowRssWaiting(waitingForRss);
  }, [waitingForRss, setShowRssWaiting]);

  useEffect(() => {
    if (!setDistributionReady) {
      return;
    }
    const ready = skipped || (appleStatus === "completed" && spotifyStatus === "completed");
    setDistributionReady(ready);
  }, [skipped, appleStatus, spotifyStatus, setDistributionReady]);

  useEffect(() => {
    if (!resolvedFeedUrl || rssFeedUrl === resolvedFeedUrl || !setRssFeedUrl) {
      return;
    }
    setRssFeedUrl(resolvedFeedUrl);
  }, [resolvedFeedUrl, rssFeedUrl, setRssFeedUrl]);

  const handleManualRefresh = async () => {
    if (!refreshRssMetadata || refreshingRss) {
      return;
    }
    setRefreshingRss(true);
    try {
      await refreshRssMetadata();
    } catch (err) {
      const description = err?.message || err?.detail || "Please try again.";
      toast({
        variant: "destructive",
        title: "Still preparing your feed",
        description,
      });
    } finally {
      setRefreshingRss(false);
    }
  };

  const triggerConfetti = () => {
    setConfettiBursts((prev) => [...prev, Date.now()]);
  };

  const handleConfettiComplete = (burstId) => {
    setConfettiBursts((prev) => prev.filter((id) => id !== burstId));
  };

  const handlePlatformCompleted = async (platformKey) => {
    const setLoading = platformKey === "apple_podcasts" ? setAppleCompleting : setSpotifyCompleting;
    setLoading(true);
    try {
      await updateStatus(platformKey, "completed");
      triggerConfetti();
    } catch (err) {
      // Errors already surfaced via toast in updateStatus
    } finally {
      setLoading(false);
    }
  };

  const appleItem = checklist?.items?.find(item => item.key === "apple_podcasts");
  const spotifyItem = checklist?.items?.find(item => item.key === "spotify");

  if (waitingForRss || showRssWaiting) {
    const statusLabel = rssStatus?.state === "error"
      ? "We hit a snag while generating your RSS feed."
      : "We’re generating your DoneCast RSS feed so Apple and Spotify can see it.";

    return (
      <div className="flex flex-col items-center justify-center text-center py-12 space-y-4">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        <div className="space-y-2">
          <p className="text-sm font-medium">{statusLabel}</p>
          <p className="text-xs text-muted-foreground max-w-md">
            This usually takes under a minute. Stay on this step and we’ll unlock the submission checklist the moment your feed is ready.
          </p>
        </div>
        <div className="flex flex-col items-center gap-2">
          <Button type="button" size="sm" disabled={refreshingRss} onClick={handleManualRefresh}>
            {refreshingRss ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                Refreshing
              </>
            ) : (
              <>Refresh status</>
            )}
          </Button>
          {rssStatus?.error && (
            <p className="text-xs text-destructive max-w-xs">{rssStatus.error}</p>
          )}
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        <span className="ml-2 text-sm text-muted-foreground">Loading distribution options...</span>
      </div>
    );
  }

  return (
    <div className="relative space-y-6">
      {confettiBursts.map((burstId) => (
        <ConfettiBurst
          key={burstId}
          burstId={burstId}
          onComplete={handleConfettiComplete}
          colors={CONFETTI_COLORS}
        />
      ))}
      <div className="space-y-2">
        <p className="text-sm font-medium">
          Apple Podcasts and Spotify are the two largest podcast platforms.
        </p>
        <div className="rounded-md border border-amber-300 bg-amber-50 text-amber-900 p-3 text-xs">
          Skipping Apple or Spotify will dramatically reduce your potential audience.
          We strongly recommend completing both. You can still publish without them.
        </div>
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
      {resolvedFeedUrl && (
        <div className="p-4 border rounded-lg bg-muted/30 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="flex-1 min-w-0">
              <label className="text-xs font-medium text-muted-foreground mb-1 block">
                Your RSS Feed URL
              </label>
              <div className="flex items-center gap-2">
                <code className="flex-1 text-sm font-mono break-all bg-background px-2 py-1.5 rounded border">
                  {resolvedFeedUrl}
                </code>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={async () => {
                    const success = await copyRssFeed({
                      successDescription: "RSS feed URL copied to clipboard",
                    });
                    if (success) {
                      setCopied(true);
                      setTimeout(() => setCopied(false), 2000);
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
            
            {resolvedFeedUrl && appleItem.action_url && (
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!hasPublishedEpisodes}
                  onClick={async () => {
                    await copyRssFeed({
                      successDescription: "Copied! Opening Podcasts Connect in a new tab.",
                    });
                    window.open(appleItem.action_url, "_blank", "noopener");
                  }}
                >
                  <ExternalLink className="h-4 w-4 mr-2" />
                  {`Copy RSS & ${appleItem.action_label || "Open Podcasts Connect"}`}
                </Button>
                {appleStatus === "completed" ? (
                  <span className="text-sm font-semibold text-emerald-600 flex items-center gap-2">
                    🎉 Completed 🎉
                  </span>
                ) : (
                  <Button
                    type="button"
                    size="sm"
                    className="bg-emerald-600 hover:bg-emerald-700 text-white"
                    onClick={() => handlePlatformCompleted("apple_podcasts")}
                    disabled={appleCompleting}
                  >
                    {appleCompleting ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                        Saving...
                      </>
                    ) : (
                      "I added it!"
                    )}
                  </Button>
                )}
              </div>
            )}

            {hasPublishedEpisodes && resolvedFeedUrl && appleItem.instructions && (
              <details className="text-xs text-muted-foreground">
                <summary className="cursor-pointer hover:text-foreground">Show instructions</summary>
                <ol className="list-decimal list-inside mt-2 space-y-1 pl-2">
                  {appleItem.instructions.map((step, idx) => (
                    <li key={idx}>{step.replace("{rss_feed_url}", resolvedFeedUrl)}</li>
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
            
            {resolvedFeedUrl && spotifyItem.action_url && (
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={async () => {
                    const feed = resolvedFeedUrl;
                    const url = spotifyItem.action_url_template
                      ? spotifyItem.action_url_template.replace("{rss_feed_encoded}", encodeURIComponent(feed))
                      : spotifyItem.action_url;
                    await copyRssFeed({
                      successDescription: "Copied! Opening Spotify for Creators in a new tab.",
                    });
                    window.open(url, "_blank", "noopener");
                  }}
                  disabled={!hasPublishedEpisodes}
                >
                  <ExternalLink className="h-4 w-4 mr-2" />
                  {`Copy RSS & ${spotifyItem.action_label || "Submit to Spotify"}`}
                </Button>
                {spotifyStatus === "completed" ? (
                  <span className="text-sm font-semibold text-emerald-600 flex items-center gap-2">
                    🎉 Completed 🎉
                  </span>
                ) : (
                  <Button
                    type="button"
                    size="sm"
                    className="bg-emerald-600 hover:bg-emerald-700 text-white"
                    onClick={() => handlePlatformCompleted("spotify")}
                    disabled={spotifyCompleting}
                  >
                    {spotifyCompleting ? (
                      <>
                        <Loader2 className="h-4 w-4 animate-spin mr-2" />
                        Saving...
                      </>
                    ) : (
                      "I added it!"
                    )}
                  </Button>
                )}
              </div>
            )}

            {hasPublishedEpisodes && resolvedFeedUrl && spotifyItem.instructions && (
              <details className="text-xs text-muted-foreground">
                <summary className="cursor-pointer hover:text-foreground">Show instructions</summary>
                <ol className="list-decimal list-inside mt-2 space-y-1 pl-2">
                  {spotifyItem.instructions.map((step, idx) => (
                    <li key={idx}>{step.replace("{rss_feed_url}", resolvedFeedUrl)}</li>
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

