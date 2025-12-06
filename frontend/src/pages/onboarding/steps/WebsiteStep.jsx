import React, { useState, useEffect, useRef } from "react";
import { Button } from "@/components/ui/button";
import { ExternalLink, Loader2, CheckCircle2, Globe } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { makeApi } from "@/lib/apiClient";

export default function WebsiteStep({ wizard }) {
  const {
    token,
    targetPodcastId,
    setTargetPodcastId,
    formData,
    coverCropperRef,
    formatKey,
    setWebsiteUrl,
    websiteUrl: wizardWebsiteUrl,
    ensurePodcastExists,
    designVibe,
    colorPreference,
    additionalNotes,
  } = wizard;
  const [generating, setGenerating] = useState(false);
  const [websiteUrl, setWebsiteUrlLocal] = useState(wizardWebsiteUrl);
  const [error, setError] = useState(null);
  const { toast } = useToast();

  // Track if we've already initiated creation/generation to prevent duplicates
  const hasInitiatedRef = useRef(false);
  const isProcessingRef = useRef(false);

  // Update local state when wizard state changes
  useEffect(() => {
    if (wizardWebsiteUrl) {
      setWebsiteUrlLocal(wizardWebsiteUrl);
    }
  }, [wizardWebsiteUrl]);

  // Auto-generate website when component mounts - ONLY ONCE
  useEffect(() => {
    console.log("[WebsiteStep] Auto-generate effect triggered", {
      hasInitiated: hasInitiatedRef.current,
      isProcessing: isProcessingRef.current,
      targetPodcastId,
      websiteUrl,
      wizardWebsiteUrl,
      generating,
      error,
      hasFormData: !!(formData.podcastName && formData.podcastDescription),
    });

    // Prevent duplicate calls
    if (hasInitiatedRef.current || isProcessingRef.current) {
      console.log("[WebsiteStep] Skipping - already initiated or processing");
      return;
    }

    // If we already have a website URL, don't do anything
    if (websiteUrl || wizardWebsiteUrl) {
      console.log("[WebsiteStep] Website already exists, skipping");
      hasInitiatedRef.current = true;
      return;
    }

    // If we're already generating, don't start again
    if (generating) {
      console.log("[WebsiteStep] Already generating, skipping");
      return;
    }

    // If there's an error, don't auto-retry
    if (error) {
      console.log("[WebsiteStep] Error present, skipping auto-retry");
      return;
    }

    // Case 1: We have a podcast ID but no website - generate website
    if (targetPodcastId && !websiteUrl && !wizardWebsiteUrl) {
      console.log("[WebsiteStep] Case 1: Has podcast ID, generating website");
      hasInitiatedRef.current = true;
      isProcessingRef.current = true;
      handleGenerateWebsite().finally(() => {
        isProcessingRef.current = false;
      });
      return;
    }

    // Case 2: No podcast ID - try to find existing podcast first, then create if needed
    if (!targetPodcastId) {
      console.log("[WebsiteStep] Case 2: No podcast ID, finding or creating podcast");
      hasInitiatedRef.current = true;
      isProcessingRef.current = true;
      findOrCreatePodcast().finally(() => {
        isProcessingRef.current = false;
      });
      return;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [targetPodcastId, formData.podcastName, formData.podcastDescription, ensurePodcastExists]); // Also depend on formData to trigger when it becomes available

  const findOrCreatePodcast = async () => {
    if (!token) return;

    // Prevent duplicate calls
    if (isProcessingRef.current) {
      console.log("[WebsiteStep] Already processing podcast creation, skipping duplicate call");
      return;
    }

    isProcessingRef.current = true;
    setGenerating(true);
    setError(null);

    try {
      if (typeof ensurePodcastExists === "function") {
        const ensured = await ensurePodcastExists();
        if (!ensured || !ensured.id) {
          throw new Error("We couldn't create your podcast yet. Please complete the earlier steps and try again.");
        }
        if (ensured.id && ensured.id !== targetPodcastId) {
          setTargetPodcastId?.(ensured.id);
        }
        await handleGenerateWebsite(ensured.id);
        return;
      }

      const api = makeApi(token);

      // FIRST: Always check if a podcast already exists
      // This is critical for users resuming onboarding
      try {
        console.log("[WebsiteStep] Checking for existing podcasts before creation...");
        const podcasts = await api.get("/api/podcasts/");
        const items = Array.isArray(podcasts) ? podcasts : podcasts?.items || [];

        if (items.length > 0) {
          // Try to find podcast by name match first (if formData has name)
          let existingPodcast = null;
          if (formData.podcastName) {
            const nameClean = (formData.podcastName || "").trim().toLowerCase();
            existingPodcast = items.find(p =>
              p.name && p.name.trim().toLowerCase() === nameClean
            );

            if (existingPodcast) {
              console.log("[WebsiteStep] Found existing podcast by name match:", existingPodcast.id, existingPodcast.name);
            }
          }

          // Use matching podcast or first one
          existingPodcast = existingPodcast || items[0];
          console.log("[WebsiteStep] Using existing podcast:", existingPodcast.id, existingPodcast.name);
          setTargetPodcastId(existingPodcast.id);
          setGenerating(false);
          // Generate website for existing podcast
          await handleGenerateWebsite(existingPodcast.id);
          return;
        } else {
          console.log("[WebsiteStep] No existing podcasts found - will create new one");
        }
      } catch (err) {
        console.warn("[WebsiteStep] Failed to check for existing podcasts:", err);
        // If it's a 404, that's fine - no podcasts exist yet
        // If it's another error, log it but continue to create new podcast
        if (err?.status !== 404) {
          console.error("[WebsiteStep] Unexpected error checking podcasts:", err);
        }
      }

      // No existing podcast found - only create if we have form data
      if (!formData.podcastName) {
        setError("No podcast found. Please go back and complete the previous steps to create a podcast.");
        setGenerating(false);
        return;
      }

      const nameClean = (formData.podcastName || "").trim();
      const descClean = (formData.podcastDescription || "").trim();

      if (!nameClean || nameClean.length < 4) {
        throw new Error("Podcast name must be at least 4 characters.");
      }
      if (!descClean) {
        throw new Error("Podcast description is required.");
      }

      const podcastPayload = new FormData();
      podcastPayload.append("name", nameClean);
      podcastPayload.append("description", descClean);
      if (formatKey) {
        podcastPayload.append("format", formatKey);
      }
      if (formData.coverArt) {
        try {
          const blob = await coverCropperRef.current?.getProcessedBlob?.();
          if (blob) {
            const file = new File([blob], "cover.jpg", { type: "image/jpeg" });
            podcastPayload.append("cover_image", file);
          } else {
            podcastPayload.append("cover_image", formData.coverArt);
          }
        } catch (error) {
          console.warn("[Onboarding] Failed to process cover crop", error);
          podcastPayload.append("cover_image", formData.coverArt);
        }
      }

      let createdPodcast;
      try {
        createdPodcast = await api.raw("/api/podcasts/", {
          method: "POST",
          body: podcastPayload,
        });
      } catch (rawError) {
        // Handle error response from raw() method
        if (rawError?.status === 405) {
          throw new Error("Method not allowed. The podcast creation endpoint may not be available. Please try refreshing the page.");
        }
        if (rawError?.status >= 400) {
          const errorMsg = rawError?.detail || rawError?.message || rawError?.error || `Server error (${rawError.status})`;
          throw new Error(errorMsg);
        }
        throw rawError;
      }

      if (!createdPodcast || !createdPodcast.id) {
        throw new Error("Failed to create the podcast show. No ID returned.");
      }

      setTargetPodcastId(createdPodcast.id);
      toast({ title: "Great!", description: "Your podcast show has been created." });

      // Register this podcast as part of the current onboarding session so
      // Start Over can nuke only this run's data.
      try {
        await api.post("/api/onboarding/sessions", { podcast_id: createdPodcast.id });
      } catch (err) {
        console.warn("[WebsiteStep] Failed to register onboarding session", err);
      }

      // Now generate website
      await handleGenerateWebsite(createdPodcast.id);
    } catch (err) {
      console.error("[Onboarding] Failed to create podcast:", err);
      const errorMessage = err?.response?.data?.detail || err?.message || "Failed to create podcast. Please try again.";
      setError(errorMessage);
      setGenerating(false);
      hasInitiatedRef.current = false; // Allow retry on error
    } finally {
      isProcessingRef.current = false;
    }
  };

  const handleGenerateWebsite = async (podcastId = targetPodcastId) => {
    // Use the passed podcastId parameter, not targetPodcastId
    const effectivePodcastId = podcastId || targetPodcastId;

    if (!effectivePodcastId || !token) {
      setError("Podcast not found. Please go back and complete previous steps.");
      setGenerating(false);
      isProcessingRef.current = false;
      return;
    }

    // Prevent duplicate calls
    if (isProcessingRef.current && !podcastId) {
      console.log("[Onboarding] Already processing website generation, skipping duplicate call");
      return;
    }

    isProcessingRef.current = true;
    setGenerating(true);
    setError(null);

    try {
      const api = makeApi(token);
      const response = await api.post(`/api/podcasts/${effectivePodcastId}/website`, {
        design_vibe: designVibe,
        color_preference: colorPreference,
        additional_notes: additionalNotes,
        host_bio: (formData.hostBio || "").trim() || undefined,
      });

      if (response?.default_domain) {
        const url = response.default_domain;
        setWebsiteUrlLocal(url);
        if (setWebsiteUrl) {
          setWebsiteUrl(url);
        }
        toast({
          title: "Website created!",
          description: "Your podcast website is ready. You can edit it later in Website Builder.",
        });
      } else {
        throw new Error("Website created but URL not returned");
      }
    } catch (err) {
      console.error("[Onboarding] Failed to generate website:", err);
      setError(err?.message || "Failed to generate website. You can create it later in Website Builder.");
      toast({
        variant: "destructive",
        title: "Website generation failed",
        description: "You can create your website later in the Website Builder.",
      });
      hasInitiatedRef.current = false; // Allow retry on error
    } finally {
      setGenerating(false);
      isProcessingRef.current = false;
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted-foreground">
        We're creating a simple website for your podcast so people can find and listen to your show.
        You can customize it later in Website Builder.
      </p>

      {generating && (
        <div className="flex items-center gap-3 p-4 border rounded-lg bg-muted/50">
          <Loader2 className="h-5 w-5 animate-spin text-primary" />
          <div>
            <p className="text-sm font-medium">Generating your website...</p>
            <p className="text-xs text-muted-foreground">This usually takes 1–2 minutes</p>
          </div>
        </div>
      )}

      {error && (
        <div className="p-4 border border-yellow-500/50 bg-yellow-500/10 rounded-lg">
          <p className="text-sm text-yellow-900 dark:text-yellow-100">{error}</p>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              hasInitiatedRef.current = false; // Reset to allow retry
              handleGenerateWebsite();
            }}
            className="mt-2"
          >
            Try Again
          </Button>
        </div>
      )}

      {websiteUrl && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 p-4 border rounded-lg bg-green-50 dark:bg-green-950">
            <CheckCircle2 className="h-5 w-5 text-green-600" />
            <div className="flex-1">
              <p className="text-sm font-medium text-green-900 dark:text-green-100">
                Website created successfully!
              </p>
              <p className="text-xs text-green-700 dark:text-green-300 mt-1">
                Your podcast website is live at:
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 p-3 border rounded-lg bg-card">
            <Globe className="h-4 w-4 text-muted-foreground" />
            <code className="flex-1 text-sm font-mono break-all">{websiteUrl}</code>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                const canonical = websiteUrl.startsWith('http') ? websiteUrl : `https://${websiteUrl}`;
                const sub = (websiteUrl || '').replace(/^https?:\/\//, '').replace(/\.donecast\.com$/,'');
                const subdomain = sub.includes('.donecast.com') ? sub.split('.donecast.com')[0] : (sub || '').split('.')[0];
                const previewUrl = subdomain ? `https://donecast.com/?subdomain=${encodeURIComponent(subdomain)}` : canonical;
                window.open(previewUrl, "_blank");
              }}
            >
              <ExternalLink className="h-4 w-4 mr-2" />
              Open
            </Button>
          </div>
          <div className="text-xs text-muted-foreground">
            Final URL: <code className="font-mono">{websiteUrl}</code> (may take up to 24 hours to propagate). The Open button uses the immediate preview: <code className="font-mono">https://donecast.com/?subdomain=your-subdomain</code>.
          </div>
          <p className="text-xs text-muted-foreground">
            You can customize your website later in Website Builder. For now, you have a URL to share with listeners.
          </p>
        </div>
      )}

      {!generating && !websiteUrl && !error && (
        <Button
          type="button"
          onClick={async () => {
            hasInitiatedRef.current = false; // Reset to allow manual trigger
            // If no targetPodcastId, try to find or create podcast first
            if (!targetPodcastId) {
              await findOrCreatePodcast();
            } else {
              await handleGenerateWebsite();
            }
          }}
          disabled={generating}
        >
          Generate Website
        </Button>
      )}
    </div>
  );
}

