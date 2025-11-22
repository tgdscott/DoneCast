import React, { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { ExternalLink, CheckCircle2, Loader2 } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { makeApi } from "@/lib/apiClient";

const OPTIONAL_PLATFORMS = [
  "amazon_music",
  "castbox",
  "deezer",
  "podcast_addict",
  "podchaser",
];

export default function DistributionOptionalStep({ wizard }) {
  const { token, targetPodcastId, rssFeedUrl, setRssFeedUrl } = wizard;
  const [loading, setLoading] = useState(false);
  const [checklist, setChecklist] = useState(null);
  const [selectedPlatforms, setSelectedPlatforms] = useState(new Set());
  const [hasPublishedEpisodes, setHasPublishedEpisodes] = useState(false);
  const { toast } = useToast();

  useEffect(() => {
    if (targetPodcastId && token) {
      loadChecklist();
    }
  }, [targetPodcastId, token]);

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
      
      if (newStatus === "completed") {
        setSelectedPlatforms(prev => new Set([...prev, platformKey]));
      } else {
        setSelectedPlatforms(prev => {
          const next = new Set(prev);
          next.delete(platformKey);
          return next;
        });
      }
      
      toast({ title: "Status updated" });
      loadChecklist(); // Refresh to get updated status
    } catch (err) {
      toast({
        variant: "destructive",
        title: "Failed to update status",
        description: err?.message || "Please try again.",
      });
    }
  };

  const togglePlatform = (platformKey) => {
    const currentStatus = checklist?.items?.find(item => item.key === platformKey)?.status || "not_started";
    const newStatus = currentStatus === "completed" ? "not_started" : "in_progress";
    updateStatus(platformKey, newStatus);
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
    <div className="space-y-4">
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

      <div className="grid gap-3">
        {optionalItems.map((item) => {
          const isCompleted = item.status === "completed";
          const feedUrl = rssFeedUrl || checklist?.rss_feed_url || "";
          const actionUrl = item.action_url_template 
            ? item.action_url_template.replace("{rss_feed_encoded}", encodeURIComponent(feedUrl))
            : item.action_url;

          return (
            <div
              key={item.key}
              className={`p-4 border rounded-lg cursor-pointer transition-colors ${
                isCompleted
                  ? "border-green-500 bg-green-50 dark:bg-green-950"
                  : "hover:border-primary/50"
              }`}
              onClick={() => !isCompleted && hasPublishedEpisodes && togglePlatform(item.key)}
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
                {isCompleted && (
                  <span className="text-xs text-green-700 dark:text-green-300 font-medium">
                    Added
                  </span>
                )}
              </div>

              {(rssFeedUrl || checklist?.rss_feed_url) && actionUrl && !isCompleted && (
                <div className="mt-3 flex items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={(e) => {
                      e.stopPropagation();
                      window.open(actionUrl, "_blank");
                      togglePlatform(item.key);
                    }}
                  >
                    <ExternalLink className="h-4 w-4 mr-2" />
                    {item.action_label || "Add"}
                  </Button>
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

