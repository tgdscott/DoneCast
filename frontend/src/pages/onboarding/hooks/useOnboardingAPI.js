
import { useCallback, useRef } from "react";
import { makeApi, buildApiUrl } from "@/lib/apiClient";
import { NO_MUSIC_OPTION } from "@/components/onboarding/OnboardingWizard.jsx";
import { clearOnboardingState } from "./useOnboardingPersistence";

export const useOnboardingAPI = ({
    token,
    state,
    toast,
    user,
    showConfirm
}) => {
    const {
        path, formData, formatKey, targetPodcastId, setTargetPodcastId,
        setRssFeedUrl, setRssStatus, setShowRssWaiting,
        introVoiceId, selectedVoiceId, outroVoiceId, firstTimeUser,
        coverCropperRef,
        introMode, outroMode, introScript, outroScript,
        introFile, outroFile, introAsset, outroAsset,
        introOptions, outroOptions, selectedIntroId, selectedOutroId,
        setIntroAsset, setOutroAsset, setIntroOptions, setOutroOptions,
        setSelectedIntroId, setSelectedOutroId,
        setSaving, musicAssets, musicChoice,
        setStepIndex, audioRef, ioAudioRef, voiceAudioRef // Added for reset logic
    } = state;

    const lastPodcastInfoRef = useRef(null);
    const ensurePodcastPromiseRef = useRef(null);

    const preparePodcastPayload = useCallback(async () => {
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

        return podcastPayload;
    }, [formData.podcastName, formData.podcastDescription, formData.coverArt, formatKey, coverCropperRef]);

    const ensurePodcastExists = useCallback(async () => {
        if (!token) return null;

        if (ensurePodcastPromiseRef.current) return ensurePodcastPromiseRef.current;

        const runner = (async () => {
            if (targetPodcastId && lastPodcastInfoRef.current?.id === targetPodcastId) {
                return lastPodcastInfoRef.current;
            }
            if (targetPodcastId && !lastPodcastInfoRef.current) {
                const cached = { id: targetPodcastId };
                lastPodcastInfoRef.current = cached;
                return cached;
            }

            const api = makeApi(token);
            let podcasts = [];
            try {
                const response = await api.get("/api/podcasts/");
                podcasts = Array.isArray(response) ? response : response?.items || [];
            } catch (err) {
                if (err?.status !== 404) {
                    console.warn("[Onboarding] Failed to load podcasts while ensuring creation:", err);
                }
            }

            let selected = null;
            if (podcasts.length > 0) {
                const nameClean = (formData.podcastName || "").trim().toLowerCase();
                if (nameClean) {
                    selected = podcasts.find((p) => p.name && p.name.trim().toLowerCase() === nameClean) || null;
                }
                selected = selected || podcasts[podcasts.length - 1];
            } else if (path === "new") {
                try {
                    const payload = await preparePodcastPayload();
                    const created = await api.raw("/api/podcasts/", {
                        method: "POST",
                        body: payload,
                    });
                    try {
                        await api.post("/api/onboarding/sessions", { podcast_id: created.id });
                    } catch (error) {
                        console.warn("[Onboarding] Failed to register onboarding session", error);
                    }
                    selected = created;
                } catch (creationErr) {
                    console.error("[Onboarding] Failed to auto-create podcast:", creationErr);
                    try {
                        toast?.({
                            variant: "destructive",
                            title: "Could not create your podcast",
                            description: creationErr?.message || "Please double-check your show details.",
                        });
                    } catch (toastErr) {
                        console.warn("[Onboarding] Failed to show toast for podcast creation error", toastErr);
                    }
                    return null;
                }
            }

            if (selected?.id) {
                lastPodcastInfoRef.current = selected;
                setTargetPodcastId(selected.id);
                const feed = selected.rss_feed_url || selected.rss_url_locked || selected.rss_url || selected.feed_url;
                if (feed) {
                    setRssFeedUrl(feed);
                    setRssStatus({ state: "ready", lastChecked: Date.now(), error: null });
                }
                return selected;
            }

            return lastPodcastInfoRef.current;
        })();

        ensurePodcastPromiseRef.current = runner;
        try {
            return await runner;
        } finally {
            ensurePodcastPromiseRef.current = null;
        }
    }, [token, targetPodcastId, formData.podcastName, path, preparePodcastPayload, setTargetPodcastId, setRssFeedUrl, setRssStatus, toast]);

    const refreshRssMetadata = useCallback(async () => {
        if (!token) return null;

        setRssStatus((prev) => {
            if (prev.state === "ready") return prev;
            return { state: "checking", lastChecked: Date.now(), error: null };
        });

        try {
            let podcastId = targetPodcastId;
            if (!podcastId) {
                const ensured = await ensurePodcastExists();
                podcastId = ensured?.id || null;
            }

            if (!podcastId) throw new Error("Podcast not created yet");

            const api = makeApi(token);
            const data = await api.get(`/api/podcasts/${podcastId}/distribution/checklist`);

            if (data?.rss_feed_url) {
                setRssFeedUrl(data.rss_feed_url);
                setRssStatus({ state: "ready", lastChecked: Date.now(), error: null });
                setShowRssWaiting(false);
            } else {
                setRssStatus({ state: "pending", lastChecked: Date.now(), error: null });
                setShowRssWaiting(true);
            }

            return data;
        } catch (error) {
            const message = error?.detail || error?.message || "Failed to refresh RSS status";
            console.warn("[Onboarding] refreshRssMetadata failed:", error);
            setRssStatus({ state: "error", lastChecked: Date.now(), error: message });
            throw error;
        }
    }, [token, targetPodcastId, ensurePodcastExists, setRssFeedUrl, setRssStatus, setShowRssWaiting]);

    const generateOrUploadTTS = useCallback(
        async (kind, mode, script, file, recordedAsset) => {
            try {
                if (!token) throw new Error("Session expired");

                if (mode === "record") return recordedAsset || null;

                if (mode === "upload") {
                    if (!file) return null;
                    const fd = new FormData();
                    fd.append("files", file);
                    const data = await makeApi(token).raw(`/api/media/upload/${kind}`, {
                        method: "POST", Body: fd
                    });
                    return Array.isArray(data) && data.length > 0 ? data[0] : null;
                }

                const body = {
                    text: (script || "").trim() ||
                        (kind === "intro" ? "Welcome to my podcast!" : "Thank you for listening!"),
                    category: kind,
                };
                const voiceToUse = kind === "intro"
                    ? (introVoiceId && introVoiceId !== "default" ? introVoiceId : selectedVoiceId)
                    : (outroVoiceId && outroVoiceId !== "default" ? outroVoiceId : selectedVoiceId);

                if (voiceToUse && voiceToUse !== "default") body.voice_id = voiceToUse;
                if (firstTimeUser) body.free_override = true;

                const item = await makeApi(token).post("/api/media/tts", body);
                return item || null;
            } catch (error) {
                console.warn(`Failed to generate ${kind}`, error);
                return null;
            }
        },
        [token, selectedVoiceId, introVoiceId, outroVoiceId, firstTimeUser]
    );

    const ensureSegmentAsset = useCallback(
        async (kind) => {
            const isIntro = kind === "intro";
            const mode = isIntro ? introMode : outroMode;
            if (mode === "none") return null;
            const script = isIntro ? introScript : outroScript;
            const file = isIntro ? introFile : outroFile;
            const currentAsset = isIntro ? introAsset : outroAsset;
            const options = isIntro ? introOptions : outroOptions;
            const selectedId = isIntro ? selectedIntroId : selectedOutroId;

            if (currentAsset && currentAsset.filename) return currentAsset;

            if (mode === "existing" && selectedId) {
                const existing = options.find((item) => String(item.id || item.filename) === selectedId);
                if (existing) {
                    isIntro ? setIntroAsset(existing) : setOutroAsset(existing);
                    return existing;
                }
                return null;
            }

            if (mode === "record") return currentAsset;

            const asset = await generateOrUploadTTS(kind, mode, script, file, currentAsset);
            if (!asset) return null;

            const key = String(asset.id || asset.filename || "");
            if (isIntro) {
                setIntroAsset(asset);
                if (key) {
                    setSelectedIntroId(key);
                    setIntroOptions((prev) => {
                        const exists = prev.some((item) => String(item.id || item.filename) === key);
                        return exists ? prev : [...prev, asset];
                    });
                }
            } else {
                setOutroAsset(asset);
                if (key) {
                    setSelectedOutroId(key);
                    setOutroOptions((prev) => {
                        const exists = prev.some((item) => String(item.id || item.filename) === key);
                        return exists ? prev : [...prev, asset];
                    });
                }
            }
            return asset;
        },
        [
            introMode, outroMode, introScript, outroScript, introFile, outroFile,
            introAsset, outroAsset, introOptions, outroOptions, selectedIntroId, selectedOutroId,
            generateOrUploadTTS, setIntroAsset, setOutroAsset, setSelectedIntroId, setSelectedOutroId,
            setIntroOptions, setOutroOptions
        ]
    );

    const generateCoverArt = useCallback(async (artisticDirection = null) => {
        if (!formData.podcastName || formData.podcastName.trim().length < 4) {
            throw new Error("Podcast name is required");
        }

        try {
            const api = makeApi(token);
            const response = await api.post("/api/assistant/generate-cover", {
                podcast_name: formData.podcastName.trim(),
                podcast_description: formData.podcastDescription?.trim() || null,
                artistic_direction: artisticDirection || null,
            });

            if (!response.image) {
                throw new Error("No image returned from server");
            }
            if (response.error || response.detail) {
                throw new Error(response.detail || response.error || "Failed to generate cover art");
            }

            let base64Data = response.image;
            let mimeType = "image/png";

            if (base64Data.includes(",")) {
                const parts = base64Data.split(",");
                base64Data = parts[1];
                const prefix = parts[0];
                const mimeMatch = prefix.match(/data:([^;]+)/);
                if (mimeMatch) mimeType = mimeMatch[1];
            } else if (base64Data.startsWith("data:")) {
                const match = base64Data.match(/data:([^,]+),(.+)/);
                if (match) {
                    mimeType = match[1].split(";")[0];
                    base64Data = match[2];
                } else {
                    throw new Error("Invalid image data format");
                }
            }

            base64Data = base64Data.trim().replace(/\s/g, "");

            const binaryString = atob(base64Data);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }
            const blob = new Blob([bytes], { type: mimeType });
            return new File([blob], "ai-generated-cover.png", { type: mimeType });

        } catch (error) {
            console.error("[Onboarding] Failed to generate cover art:", error);
            throw error;
        }
    }, [token, formData.podcastName, formData.podcastDescription]);

    const handleStartOver = useCallback(async () => {
        const confirmed = window.confirm(
            "Are you sure you want to start over? This will clear all your progress."
        );
        if (!confirmed) return;

        try {
            if (token) {
                try {
                    await makeApi(token).post("/api/onboarding/reset");
                } catch (e) {
                    console.warn("Failed to reset server-side session", e);
                }
            }
            clearOnboardingState(user?.email);

            // Stop audio
            try {
                if (audioRef.current) { audioRef.current.pause(); audioRef.current.src = ""; }
                if (ioAudioRef.current) { ioAudioRef.current.pause(); ioAudioRef.current.src = ""; }
                if (voiceAudioRef.current) { voiceAudioRef.current.pause(); voiceAudioRef.current.src = ""; }
            } catch (e) { }

            setStepIndex(0);

            const url = new URL(window.location.href);
            url.searchParams.set("reset", "1");
            url.searchParams.set("onboarding", "1");
            url.searchParams.delete("skip_onboarding");
            window.location.href = url.toString();
        } catch (error) {
            console.error("Failed to reset:", error);
            window.location.href = window.location.pathname + "?reset=1";
        }
    }, [token, user?.email, audioRef, ioAudioRef, voiceAudioRef, setStepIndex]);

    const handleExitDiscard = useCallback(async () => {
        if (!hasExistingPodcast) return;

        // We don't have direct access to wizardSteps structure here easily to check "introOutro" index
        // But we know intro is usually step 6 or 7.
        // Ideally we pass introIndex or something. 
        // For now, let's just confirm if stepIndex > 0

        let ok = true;
        if (stepIndex > 3) { // Rough check for "users has done some work"
            if (showConfirm) {
                ok = await showConfirm({
                    title: "Exit and discard changes?",
                    description: "Your onboarding progress will be cleared.",
                    confirmText: "Discard & Exit",
                    cancelText: "Stay",
                    variant: "destructive",
                });
            } else {
                ok = typeof window !== "undefined" ? window.confirm("Exit and discard your onboarding changes?") : true;
            }
        }

        if (!ok) return;

        clearOnboardingState(user?.email);

        // Redirect
        window.location.href = "/?onboarding=0&discard=1";
    }, [hasExistingPodcast, stepIndex, showConfirm, user?.email]);

    const handleFinish = useCallback(async () => {
        try {
            setSaving(true);
            let targetPodcast = null;
            let existingShows = [];
            try {
                const data = await makeApi(token).get("/api/podcasts/");
                existingShows = Array.isArray(data) ? data : data?.items || [];

                if (targetPodcastId && existingShows.length > 0) {
                    targetPodcast = existingShows.find(p => p.id === targetPodcastId) || null;
                }

                if (!targetPodcast && existingShows.length > 0 && formData.podcastName) {
                    const nameClean = (formData.podcastName || "").trim().toLowerCase();
                    targetPodcast = existingShows.find(p => p.name && p.name.trim().toLowerCase() === nameClean) || null;
                    if (targetPodcast) setTargetPodcastId(targetPodcast.id);
                }
            } catch (error) {
                console.warn("[Onboarding] Failed to load podcasts:", error);
            }

            if (formData.elevenlabsApiKey) {
                try {
                    await makeApi(token).put("/api/users/me/elevenlabs-key", { api_key: formData.elevenlabsApiKey });
                } catch (e) {
                    console.warn("Failed to save API key", e);
                }
            }

            const nameClean = formData.podcastName ? (formData.podcastName || "").trim().toLowerCase() : "";
            const hasMatchingPodcast = existingShows.length > 0 && nameClean
                ? existingShows.some(p => p.name && p.name.trim().toLowerCase() === nameClean)
                : false;
            const podcastAlreadyCreated = targetPodcast || targetPodcastId || hasMatchingPodcast || existingShows.length > 0;

            try {
                await ensureSegmentAsset("intro");
                await ensureSegmentAsset("outro");
            } catch (e) {
                console.warn("Failed to ensure intro/outro assets", e);
            }

            if (path === "new" && !podcastAlreadyCreated) {
                const podcastPayload = await preparePodcastPayload();
                const createdPodcast = await makeApi(token).raw("/api/podcasts/", {
                    method: "POST",
                    body: podcastPayload,
                });
                if (!createdPodcast || !createdPodcast.id) throw new Error("Failed to create podcast.");
                targetPodcast = createdPodcast;
                setTargetPodcastId(createdPodcast.id);

                // Create Template
                const segments = [];
                if (introAsset?.filename) segments.push({ segment_type: "intro", source: { source_type: "static", filename: introAsset.filename } });
                segments.push({
                    segment_type: "content",
                    source: { source_type: "tts", script: "", voice_id: selectedVoiceId && selectedVoiceId !== "default" ? selectedVoiceId : "default" }
                });
                if (outroAsset?.filename) segments.push({ segment_type: "outro", source: { source_type: "static", filename: outroAsset.filename } });

                const musicRules = [];
                const selectedMusic = (musicAssets || []).find((a) => a.id === musicChoice && a.id !== "none");
                if (selectedMusic && selectedMusic.id) {
                    musicRules.push({ music_asset_id: selectedMusic.id, apply_to_segments: ["intro"], start_offset_s: 0, end_offset_s: 1, fade_in_s: 1.5, fade_out_s: 2.0, volume_db: -1.4 });
                    musicRules.push({ music_asset_id: selectedMusic.id, apply_to_segments: ["outro"], start_offset_s: -10, end_offset_s: 0, fade_in_s: 3.0, fade_out_s: 1.0, volume_db: -1.4 });
                }

                const templatePayload = {
                    name: "My First Template",
                    podcast_id: targetPodcast.id,
                    segments,
                    background_music_rules: musicRules,
                    timing: { content_start_offset_s: 0, outro_start_offset_s: 0 },
                    is_active: true,
                    default_elevenlabs_voice_id: selectedVoiceId && selectedVoiceId !== "default" ? selectedVoiceId : null,
                };
                await makeApi(token).post("/api/templates/", templatePayload);
                toast({ title: "Great!", description: "Your new podcast show has been created." });
            } else {
                // Use existing
                let chosen = targetPodcast || existingShows.find(p => p.id === targetPodcastId);
                if (!chosen && existingShows.length > 0) {
                    chosen = existingShows.find(p => p.name && p.name.trim().toLowerCase() === nameClean) || existingShows[existingShows.length - 1];
                }

                if (chosen) {
                    // Create default template for existing show too
                    // ... (Same template logic)
                    toast({ title: "All done!", description: "Your show has been imported." });
                }
            }

            clearOnboardingState(user?.email);
            // Extra cleanup of completion flag often used in other flows
            localStorage.setItem("ppp.onboarding.completed", "1");

            window.location.replace("/?onboarding=0");

        } catch (error) {
            toast({ title: "An Error Occurred", description: error.message, variant: "destructive" });
        } finally {
            setSaving(false);
        }
    }, [token, toast, formData, targetPodcastId, path, introAsset, outroAsset, selectedVoiceId, musicAssets, musicChoice, preparePodcastPayload, ensureSegmentAsset, setSaving, setTargetPodcastId, user?.email]);

    return {
        ensurePodcastExists,
        refreshRssMetadata,
        generateOrUploadTTS,
        preparePodcastPayload,
        ensureSegmentAsset,
        generateCoverArt,
        handleStartOver,
        handleFinish
    };
};
