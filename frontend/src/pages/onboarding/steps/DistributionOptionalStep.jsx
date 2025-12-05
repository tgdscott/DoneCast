import React, { useState, useEffect, useMemo, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { ExternalLink, CheckCircle2, Loader2, Copy, Check } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { makeApi } from "@/lib/apiClient";
import { copyTextToClipboard } from "@/lib/clipboard";
import { ConfettiBurst } from "../components/ConfettiBurst.jsx";

const OPTIONAL_PLATFORMS = [
  // Keep Amazon first, then iHeart as requested
  "amazon_music",
  "iheart",
  // Remaining popular directories
  "castbox",
  "deezer",
  "podcast_addict",
  "podchaser",
];

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

export default function DistributionOptionalStep({ wizard }) {
  const {
    token,
    targetPodcastId,
    setTargetPodcastId,
    rssFeedUrl,
    setRssFeedUrl,
    ensurePodcastExists,
  } = wizard;
  const [loading, setLoading] = useState(false);
  const [checklist, setChecklist] = useState(null);
  const [hasPublishedEpisodes, setHasPublishedEpisodes] = useState(false);
  const [copied, setCopied] = useState(false);
  const [completingPlatform, setCompletingPlatform] = useState(null);
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
      const copiedSuccessfully = await copyTextToClipboard(resolvedFeedUrl);
      if (copiedSuccessfully) {
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
      if (!token) return;
      if (!targetPodcastId) {
        if (typeof ensurePodcastExists === "function") {
          const podcast = await ensurePodcastExists();
          if (cancelled) return;
          if (podcast?.id) {
            setTargetPodcastId?.(podcast.id);
            return;
          }
        }
        return;
      }
      await loadChecklist();
    };

    bootstrap();
    return () => {
      cancelled = true;
    };
  }, [targetPodcastId, token, ensurePodcastExists, setTargetPodcastId]);

  const loadChecklist = async () => {
    if (!targetPodcastId || !token) return;
    
    setLoading(true);
    try {
      const api = makeApi(token);
      const data = await api.get(`/api/podcasts/${targetPodcastId}/distribution/checklist`);
      setChecklist(data);
      setHasPublishedEpisodes(data?.has_published_episodes || false);
      
      // Update RSS feed URL in wizard context
      if (data.rss_feed_url && setRssFeedUrl) {
        setRssFeedUrl(data.rss_feed_url);
      }
    } catch (err) {
      console.error("[Onboarding] Failed to load distribution checklist:", err);
      toast({
        variant: "destructive",
        title: "Failed to load platforms",
        description: "You can add these later in Settings → Distribution.",
      });
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
      
      toast({ title: "Status updated" });
      loadChecklist(); // Refresh to get updated status
    } catch (err) {
      toast({
        variant: "destructive",
        title: "Failed to update status",
        description: err?.message || "Please try again.",
      });
      throw err;
    }
  };

  const triggerConfetti = useCallback(() => {
    setConfettiBursts((prev) => [...prev, Date.now()]);
  }, []);

  const handleConfettiComplete = useCallback((burstId) => {
    setConfettiBursts((prev) => prev.filter((id) => id !== burstId));
  }, []);

  const handlePlatformCompleted = async (platformKey) => {
    setCompletingPlatform(platformKey);
    try {
      await updateStatus(platformKey, "completed");
      triggerConfetti();
    } catch (err) {
      // Errors already surfaced via toast in updateStatus
    } finally {
      setCompletingPlatform(null);
    }
  };

  const handleLaunchPlatform = async (platformLabel, actionUrl) => {
    if (!actionUrl) {
      return;
    }
    await copyRssFeed({
      successDescription: `Copied! Opening ${platformLabel || "this platform"} in a new tab.`,
    });
    window.open(actionUrl, "_blank", "noopener");
  };

  const optionalItems = checklist?.items?.filter(item => 
    OPTIONAL_PLATFORMS.includes(item.key)
  ) || [];

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        <span className="ml-2 text-sm text-muted-foreground">Loading platforms...</span>
      </div>
    );
  }

  return (
    <div className="relative space-y-4">
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
          Other large platforms we recommend you are on as well
        </p>
        <p className="text-xs text-muted-foreground">
          These platforms help you reach more listeners. You can add them now with one click, or skip and add them later.
        </p>
      </div>

      {!hasPublishedEpisodes && (
        <div className="p-3 border border-yellow-500/50 bg-yellow-500/10 rounded-lg">
          <p className="text-xs text-yellow-900 dark:text-yellow-100">
            You'll need to publish your first episode before submitting to these platforms. 
            You can add them later in Settings → Distribution.
          </p>
        </div>
      )}

      {resolvedFeedUrl && (
        <div className="p-4 border rounded-lg bg-muted/30 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="flex-1 min-w-0">
              <label className="text-xs font-medium text-muted-foreground mb-1 block">
                Your RSS Feed URL
              </label>
              <code className="flex-1 text-sm font-mono break-all bg-background px-2 py-1.5 rounded border block">
                {resolvedFeedUrl}
              </code>
            </div>
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
      )}

      <div className="grid gap-3">
        {optionalItems.map((item) => {
          const isCompleted = item.status === "completed";
          const feedUrl = resolvedFeedUrl;
          const actionUrl = item.action_url_template && feedUrl
            ? item.action_url_template.replace("{rss_feed_encoded}", encodeURIComponent(feedUrl))
            : item.action_url;
          const actionLabel = item.action_label || `Open ${item.name}`;
          const ctaLabel = `Copy RSS & ${actionLabel}`;
          const isCompleting = completingPlatform === item.key;

          return (
            <div
              key={item.key}
              className={`p-4 border rounded-lg transition-colors ${
                isCompleted
                  ? "border-green-500 bg-green-50 dark:bg-green-950"
                  : "hover:border-primary/50"
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold">{item.name}</h3>
                    {isCompleted && (
                      <CheckCircle2 className="h-4 w-4 text-green-600" />
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground mt-1">{item.summary}</p>
                  {item.automation_notes && (
                    <p className="text-xs text-muted-foreground mt-1">{item.automation_notes}</p>
                  )}
                </div>
              </div>

              {feedUrl && actionUrl && (
                <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={!hasPublishedEpisodes || !feedUrl}
                    onClick={() => handleLaunchPlatform(item.name, actionUrl)}
                  >
                    <ExternalLink className="h-4 w-4 mr-2" />
                    {ctaLabel}
                  </Button>
                  {isCompleted ? (
                    <span className="text-sm font-semibold text-emerald-600 flex items-center gap-2">
                      🎉 Completed 🎉
                    </span>
                  ) : (
                    <Button
                      type="button"
                      size="sm"
                      className="bg-emerald-600 hover:bg-emerald-700 text-white"
                      onClick={() => handlePlatformCompleted(item.key)}
                      disabled={isCompleting}
                    >
                      {isCompleting ? (
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

              {!hasPublishedEpisodes && (
                <p className="text-xs text-muted-foreground mt-2">
                  Publish your first episode to enable one-click submission
                </p>
              )}
            </div>
          );
        })}
      </div>

      {optionalItems.length === 0 && (
        <p className="text-sm text-muted-foreground text-center py-4">
          No additional platforms available at this time.
        </p>
      )}

      <p className="text-xs text-muted-foreground pt-2 border-t">
        You can add or remove these platforms anytime in Settings → Distribution.
      </p>
    </div>
  );
}

