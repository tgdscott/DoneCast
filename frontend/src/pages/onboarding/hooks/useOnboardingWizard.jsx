import React, { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { makeApi, buildApiUrl } from "@/lib/apiClient";
import { NO_MUSIC_OPTION } from "@/components/onboarding/OnboardingWizard.jsx";
import { useResolvedTimezone } from "@/hooks/useResolvedTimezone";

import { formatMediaDisplayName } from "../utils/mediaDisplay.js";
import { getVoiceById, toggleVoicePreview } from "../utils/voicePreview.js";
import { toggleMusicPreview as toggleMusicPreviewHelper } from "../utils/musicPreview.js";
import { toggleIntroOutroPreview } from "../utils/introOutroPreview.js";

import YourNameStep from "../steps/YourNameStep.jsx";
import ChoosePathStep from "../steps/ChoosePathStep.jsx";
import ShowDetailsStep from "../steps/ShowDetailsStep.jsx";
import FormatStep from "../steps/FormatStep.jsx";
import CoverArtStep from "../steps/CoverArtStep.jsx";
import SkipNoticeStep from "../steps/SkipNoticeStep.jsx";
import IntroOutroStep from "../steps/IntroOutroStep.jsx";
import MusicStep from "../steps/MusicStep.jsx";
import PublishCadenceStep from "../steps/PublishCadenceStep.jsx";
import PublishScheduleStep from "../steps/PublishScheduleStep.jsx";
import FinishStep from "../steps/FinishStep.jsx";
import ImportRssStep from "../steps/ImportRssStep.jsx";
import ConfirmImportStep from "../steps/ConfirmImportStep.jsx";
import ImportingStep from "../steps/ImportingStep.jsx";
import ImportAnalyzeStep from "../steps/ImportAnalyzeStep.jsx";
import ImportAssetsStep from "../steps/ImportAssetsStep.jsx";
import ImportSuccessStep from "../steps/ImportSuccessStep.jsx";

export default function useOnboardingWizard({
  token,
  user,
  refreshUser,
  toast,
  comfort,
}) {
  const resolvedTimezone = useResolvedTimezone(user?.timezone);
  const { largeText, setLargeText, highContrast, setHighContrast } = comfort;
  const STEP_KEY = "ppp.onboarding.step";

  const [fromManager] = useState(() => {
    try {
      return new URLSearchParams(window.location.search).get("from") === "manager";
    } catch {
      return false;
    }
  });

  const [stepIndex, setStepIndex] = useState(() => {
    try {
      const raw = localStorage.getItem(STEP_KEY);
      const n = raw != null ? parseInt(raw, 10) : 0;
      return Number.isFinite(n) && n >= 0 ? n : 0;
    } catch {
      return 0;
    }
  });

  useEffect(() => {
    if (!token && !user) {
      console.warn("[Onboarding] No authentication token found, redirecting to login");
      window.location.href = "/?login=1";
    }
  }, [token, user]);

  const stepSaveTimer = useRef(null);
  const importResumeTimerRef = useRef(null);

  const [path, setPath] = useState("new");
  const [formData, setFormData] = useState({
    podcastName: "",
    podcastDescription: "",
    coverArt: null,
    elevenlabsApiKey: "",
  });
  const [saving, setSaving] = useState(false);
  const [formatKey, setFormatKey] = useState("solo");
  const [rssUrl, setRssUrl] = useState("");
  const [importResult, setImportResult] = useState(null);
  const [resumeAfterImport, setResumeAfterImport] = useState(false);
  const [importLoading, setImportLoading] = useState(false);
  const [showSkipNotice, setShowSkipNotice] = useState(false);
  const [importJumpedToStep6, setImportJumpedToStep6] = useState(false);

  const [musicAssets, setMusicAssets] = useState([NO_MUSIC_OPTION]);
  const [musicLoading, setMusicLoading] = useState(false);
  const [musicChoice, setMusicChoice] = useState("none");
  const [musicPreviewing, setMusicPreviewing] = useState(null);
  const audioRef = useRef(null);
  const ioAudioRef = useRef(null);
  const [introPreviewing, setIntroPreviewing] = useState(false);
  const [outroPreviewing, setOutroPreviewing] = useState(false);

  const [freqUnit, setFreqUnit] = useState("");
  const [freqCount, setFreqCount] = useState(1);
  const [cadenceError, setCadenceError] = useState("");
  const [selectedWeekdays, setSelectedWeekdays] = useState([]);
  const [selectedDates, setSelectedDates] = useState([]);
  const [notSureSchedule, setNotSureSchedule] = useState(false);

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [nameError, setNameError] = useState("");

  const [skipCoverNow, setSkipCoverNow] = useState(false);
  const coverArtInputRef = useRef(null);
  const coverCropperRef = useRef(null);
  const [coverCrop, setCoverCrop] = useState(null);
  const [coverMode, setCoverMode] = useState("crop");

  const [introMode, setIntroMode] = useState("tts");
  const [outroMode, setOutroMode] = useState("tts");
  const [introScript, setIntroScript] = useState("Welcome to my podcast!");
  const [outroScript, setOutroScript] = useState("Thank you for listening and see you next time!");
  const [introFile, setIntroFile] = useState(null);
  const [outroFile, setOutroFile] = useState(null);
  const [introAsset, setIntroAsset] = useState(null);
  const [outroAsset, setOutroAsset] = useState(null);
  const [introOptions, setIntroOptions] = useState([]);
  const [outroOptions, setOutroOptions] = useState([]);
  const [selectedIntroId, setSelectedIntroId] = useState("");
  const [selectedOutroId, setSelectedOutroId] = useState("");
  const [voices, setVoices] = useState([]);
  const [voicesLoading, setVoicesLoading] = useState(false);
  const [voicesError, setVoicesError] = useState("");
  const [selectedVoiceId, setSelectedVoiceId] = useState("default");
  const voiceAudioRef = useRef(null);
  const [voicePreviewing, setVoicePreviewing] = useState(false);

  const [needsTtsReview, setNeedsTtsReview] = useState(false);
  const [ttsGeneratedIntro, setTtsGeneratedIntro] = useState(null);
  const [ttsGeneratedOutro, setTtsGeneratedOutro] = useState(null);
  const [renameIntro, setRenameIntro] = useState("");
  const [renameOutro, setRenameOutro] = useState("");
  const [firstTimeUser, setFirstTimeUser] = useState(false);

  const stepIdRef = useRef(null);

  const importFlowSteps = useMemo(
    () => [
      { id: "rss", title: "Import from RSS" },
      { id: "confirm", title: "Confirm import" },
      { id: "importing", title: "Importing..." },
      { id: "analyze", title: "Analyzing" },
      { id: "assets", title: "Assets" },
      { id: "importSuccess", title: "Import complete!" },
    ],
    []
  );

  const newFlowSteps = useMemo(() => {
    const nameStep = {
      id: "yourName",
      title: "What can we call you?",
      validate: async () => {
        const fn = (firstName || "").trim();
        const ln = (lastName || "").trim();
        if (!fn) {
          setNameError("First name is required");
          return false;
        }
        setNameError("");
        try {
          const api = makeApi(token);
          await api.patch("/api/auth/users/me/prefs", {
            first_name: fn,
            last_name: ln || undefined,
          });
          try {
            refreshUser?.({ force: true });
          } catch (error) {
            console.warn("[Onboarding] Failed to refresh user", error);
          }
        } catch (error) {
          console.warn("[Onboarding] Failed to persist name", error);
        }
        return true;
      },
    };

    const choosePathStep = {
      id: "choosePath",
      title: "Do you have an existing podcast?",
    };

    const baseSteps = [
      nameStep,
      choosePathStep,
      { id: "showDetails", title: "About your show" },
      { id: "format", title: "Format" },
      { id: "coverArt", title: "Podcast Cover Art (optional)" },
      ...(showSkipNotice
        ? [
            {
              id: "skipNotice",
              title: "Skipping ahead",
              description: "We imported your show. We'll jump to Step 6 so you can finish setup.",
            },
          ]
        : []),
      { id: "introOutro", title: "Intro & Outro" },
      { id: "music", title: "Music (optional)" },
      { id: "publishCadence", title: "How often will you publish?" },
      { id: "publishSchedule", title: "Publishing days" },
      { id: "finish", title: "All done!" },
    ];

    const filtered = fromManager ? baseSteps.filter((step) => step.id !== "yourName") : baseSteps;
    const includeSchedule = freqUnit !== "day" && freqUnit !== "year";
    return includeSchedule ? filtered : filtered.filter((step) => step.id !== "publishSchedule");
  }, [
    firstName,
    lastName,
    nameError,
    freqUnit,
    path,
    token,
    refreshUser,
    fromManager,
    showSkipNotice,
  ]);

  const wizardSteps = useMemo(
    () => (path === "import" ? importFlowSteps : newFlowSteps),
    [path, importFlowSteps, newFlowSteps]
  );

  const introOutroIndex = useMemo(() => {
    const idx = newFlowSteps.findIndex((step) => step.id === "introOutro");
    return idx >= 0 ? idx : 0;
  }, [newFlowSteps]);

  const stepId = wizardSteps[stepIndex]?.id;
  stepIdRef.current = stepId;

  const [hasExistingPodcast, setHasExistingPodcast] = useState(false);
  useEffect(() => {
    (async () => {
      try {
        const data = await makeApi(token).get("/api/podcasts/");
        const items = Array.isArray(data) ? data : data?.items || [];
        setHasExistingPodcast(items.length > 0);
      } catch (error) {
        console.warn("[Onboarding] Failed to load podcasts", error);
        setHasExistingPodcast(false);
      }
    })();
  }, [token]);

  const bootstrappedRef = useRef(false);
  useEffect(() => {
    if (bootstrappedRef.current) return;
    bootstrappedRef.current = true;
    try {
      const url = new URL(window.location.href);
      const fromParam = url.searchParams.get("from") === "manager";
      const shouldReset =
        url.searchParams.get("reset") === "1" || url.searchParams.get("reset") === "true";
      if (shouldReset) {
        try {
          localStorage.removeItem(STEP_KEY);
        } catch (error) {
          console.warn("[Onboarding] Failed to reset stored step", error);
        }
      }
      const stepParam = url.searchParams.get("step");
      const n = stepParam != null ? parseInt(stepParam, 10) : Number.NaN;
      if (Number.isFinite(n) && n >= 1) {
        const clamped = Math.min(Math.max(1, n), wizardSteps.length) - 1;
        setStepIndex(clamped);
      } else if (fromParam) {
        const idx = wizardSteps.findIndex((s) => s.id === "choosePath");
        setStepIndex(idx >= 0 ? idx : 0);
      }
    } catch (error) {
      console.warn("[Onboarding] Failed to bootstrap step", error);
    }
  }, [wizardSteps.length]);

  useEffect(() => {
    const maxIndex = Math.max(0, wizardSteps.length - 1);
    if (stepIndex > maxIndex) setStepIndex(maxIndex);
  }, [wizardSteps.length, stepIndex]);

  useEffect(() => {
    if (stepSaveTimer.current) clearTimeout(stepSaveTimer.current);
    stepSaveTimer.current = setTimeout(() => {
      try {
        localStorage.setItem(STEP_KEY, String(stepIndex));
      } catch (error) {
        console.warn("[Onboarding] Failed to store onboarding step", error);
      }
    }, 350);
    return () => {
      if (stepSaveTimer.current) clearTimeout(stepSaveTimer.current);
    };
  }, [stepIndex]);

  useEffect(() => {
    const handleAiGeneratedCover = (event) => {
      const file = event.detail?.file;
      if (file && file instanceof File) {
        setFormData((prev) => ({ ...prev, coverArt: file }));
        setCoverCrop(null);
        if (stepIdRef.current !== "coverArt") {
          const coverStepIndex = wizardSteps.findIndex((s) => s.id === "coverArt");
          if (coverStepIndex >= 0) {
            setStepIndex(coverStepIndex);
          }
        }
      }
    };
    window.addEventListener("ai-generated-cover", handleAiGeneratedCover);
    return () => window.removeEventListener("ai-generated-cover", handleAiGeneratedCover);
  }, [wizardSteps]);

  useEffect(() => {
    if (stepId === "music" && musicAssets.length <= 1 && !musicLoading) {
      setMusicLoading(true);
      (async () => {
        try {
          const api = makeApi(token);
          const data = await api.get("/api/music/assets?scope=global");
          const assets = Array.isArray(data?.assets) ? data.assets : [];
          setMusicAssets([NO_MUSIC_OPTION, ...assets]);
        } catch (error) {
          console.warn("[Onboarding] Failed to load music assets", error);
          setMusicAssets([NO_MUSIC_OPTION]);
        } finally {
          setMusicLoading(false);
        }
      })();
    }
    if (stepId !== "music" && audioRef.current) {
      try {
        audioRef.current.pause();
      } catch (_) {}
      audioRef.current = null;
      setMusicPreviewing(null);
    }
  }, [stepId, musicAssets.length, musicLoading, token]);

  useEffect(() => {
    if (stepId === "introOutro" && !voicesLoading && voices.length === 0) {
      setVoicesLoading(true);
      setVoicesError("");
      (async () => {
        try {
          const data = await makeApi(token).get("/api/elevenlabs/voices?size=20");
          const items = (data && (data.items || data.voices)) || [];
          setVoices(items);
          if (items.length > 0 && (!selectedVoiceId || selectedVoiceId === "default")) {
            const first = items[0];
            setSelectedVoiceId(first.voice_id || first.id || first.name || "default");
          }
        } catch (error) {
          console.warn("[Onboarding] Failed to load voices", error);
          setVoicesError("Voice list unavailable; using a default voice.");
        } finally {
          setVoicesLoading(false);
        }
      })();
    }
    if (stepId === "introOutro" && introOptions.length === 0 && outroOptions.length === 0) {
      (async () => {
        try {
          const media = await makeApi(token).get("/api/media/");
          const asArray = Array.isArray(media) ? media : media?.items || [];
          const intros = asArray.filter((m) => (m?.category || "").toLowerCase() === "intro");
          const outros = asArray.filter((m) => (m?.category || "").toLowerCase() === "outro");
          setIntroOptions(intros);
          setOutroOptions(outros);
          if (intros.length > 0) {
            const firstIntro = intros[0];
            setSelectedIntroId(String(firstIntro.id || firstIntro.filename));
            setIntroAsset(firstIntro);
            setIntroMode((prev) => (prev === "tts" || prev === "upload" ? "existing" : prev));
          }
          if (outros.length > 0) {
            const firstOutro = outros[0];
            setSelectedOutroId(String(firstOutro.id || firstOutro.filename));
            setOutroAsset(firstOutro);
            setOutroMode((prev) => (prev === "tts" || prev === "upload" ? "existing" : prev));
          }
        } catch (error) {
          console.warn("[Onboarding] Failed to load intro/outro options", error);
        }
      })();
    }
    if (stepId !== "introOutro" && voiceAudioRef.current) {
      try {
        voiceAudioRef.current.pause();
      } catch (_) {}
      setVoicePreviewing(false);
    }
    if (stepId !== "introOutro" && ioAudioRef.current) {
      try {
        ioAudioRef.current.pause();
      } catch (_) {}
      setIntroPreviewing(false);
      setOutroPreviewing(false);
    }
  }, [
    stepId,
    voicesLoading,
    voices.length,
    selectedVoiceId,
    token,
    introOptions.length,
    outroOptions.length,
  ]);

  useEffect(() => {
    if (stepId !== "introOutro") return;
    (async () => {
      try {
        const podcasts = await makeApi(token).get("/api/podcasts/");
        const pItems = Array.isArray(podcasts) ? podcasts : podcasts?.items || [];
        const media = await makeApi(token).get("/api/media/");
        const mItems = Array.isArray(media) ? media : media?.items || [];
        const hasIntro = mItems.some((m) => (m?.category || "").toLowerCase() === "intro");
        const hasOutro = mItems.some((m) => (m?.category || "").toLowerCase() === "outro");
        setFirstTimeUser(pItems.length === 0 && !hasIntro && !hasOutro);
      } catch (error) {
        console.warn("[Onboarding] Failed to determine first-time user status", error);
        setFirstTimeUser(false);
      }
    })();
  }, [stepId, token]);

  const handleIntroOutroPreview = useCallback(
    async (kind) => {
      let asset = null;
      if (needsTtsReview) {
        asset = kind === "intro" ? ttsGeneratedIntro || introAsset : ttsGeneratedOutro || outroAsset;
      } else {
        asset =
          kind === "intro"
            ? introOptions.find((x) => String(x.id || x.filename) === selectedIntroId) || introAsset || null
            : outroOptions.find((x) => String(x.id || x.filename) === selectedOutroId) || outroAsset || null;
      }
      await toggleIntroOutroPreview({
        kind,
        asset,
        token,
        makeApi,
        buildApiUrl,
        ioAudioRef,
        isIntroPreviewing: introPreviewing,
        isOutroPreviewing: outroPreviewing,
        setIntroPreviewing,
        setOutroPreviewing,
        toast,
      });
    },
    [
      needsTtsReview,
      ttsGeneratedIntro,
      introAsset,
      ttsGeneratedOutro,
      outroAsset,
      introOptions,
      selectedIntroId,
      outroOptions,
      selectedOutroId,
      token,
      introPreviewing,
      outroPreviewing,
      toast,
    ]
  );

  const toggleMusicPreview = useCallback(
    (asset) => {
      toggleMusicPreviewHelper({
        asset,
        audioRef,
        musicPreviewing,
        setMusicPreviewing,
      });
    },
    [musicPreviewing]
  );

  const previewSelectedVoice = useCallback(() => {
    toggleVoicePreview({
      voicePreviewing,
      setVoicePreviewing,
      voiceAudioRef,
      voices,
      selectedVoiceId,
    });
  }, [voicePreviewing, voices, selectedVoiceId]);

  const canPreviewSelectedVoice = useMemo(() => {
    const voice = getVoiceById(voices, selectedVoiceId);
    return !!(voice && (voice.preview_url || voice.sample_url));
  }, [voices, selectedVoiceId]);

  const handleChange = useCallback((event) => {
    const { id, value, files } = event.target;
    setFormData((prev) => ({ ...prev, [id]: files ? files[0] : value }));
  }, []);

  const handleExitDiscard = useCallback(() => {
    if (!hasExistingPodcast) return;
    const idxIntro = newFlowSteps.findIndex((s) => s.id === "introOutro");
    const atOrBeyondIntro = idxIntro >= 0 && stepIndex >= idxIntro;
    if (atOrBeyondIntro) {
      const ok = window.confirm("Exit and discard your onboarding changes?");
      if (!ok) return;
    }
    try {
      localStorage.removeItem("ppp.onboarding.step");
    } catch (error) {
      console.warn("[Onboarding] Failed to clear stored step", error);
    }
    try {
      window.location.replace("/?onboarding=0");
    } catch (error) {
      console.warn("[Onboarding] Failed to redirect", error);
    }
  }, [hasExistingPodcast, newFlowSteps, stepIndex]);

  const generateOrUploadTTS = useCallback(
    async (kind, mode, script, file, recordedAsset) => {
      try {
        if (!token) {
          const errorMsg =
            "Your session has expired. Please refresh the page (F5 or Ctrl+R) and sign in again.";
          toast({
            title: "Session Expired",
            description: errorMsg,
            variant: "destructive",
          });
          throw new Error(errorMsg);
        }
        if (mode === "record") {
          return recordedAsset || null;
        }
        if (mode === "upload") {
          if (!file) return null;
          const fd = new FormData();
          fd.append("files", file);
          const data = await makeApi(token).raw(`/api/media/upload/${kind}`, {
            method: "POST",
            body: fd,
          });
          if (Array.isArray(data) && data.length > 0) return data[0];
          return null;
        }
        const body = {
          text:
            (script || "").trim() ||
            (kind === "intro"
              ? "Welcome to my podcast!"
              : "Thank you for listening and see you next time!"),
          category: kind,
        };
        if (selectedVoiceId && selectedVoiceId !== "default") body.voice_id = selectedVoiceId;
        if (firstTimeUser) body.free_override = true;
        const item = await makeApi(token).post("/api/media/tts", body);
        return item || null;
      } catch (error) {
        const status = error?.status;
        let errorMsg = error?.message || String(error);
        if (status === 401) {
          errorMsg = "Your session has expired. Please refresh the page (F5 or Ctrl+R) and sign in again.";
        } else if (status === 403) {
          errorMsg = "Permission denied. You may not have access to this feature.";
        } else if (status === 429) {
          errorMsg = error?.detail?.message || "Too many requests. Please wait a moment and try again.";
        }
        try {
          toast({
            title: `Could not prepare ${kind}`,
            description: errorMsg,
            variant: "destructive",
          });
        } catch (_) {}
        return null;
      }
    },
    [token, toast, selectedVoiceId, firstTimeUser]
  );

  const handleFinish = useCallback(async () => {
    try {
      setSaving(true);
      let targetPodcast = null;
      let existingShows = [];
      try {
        const data = await makeApi(token).get("/api/podcasts/");
        existingShows = Array.isArray(data) ? data : data?.items || [];
      } catch (error) {
        console.warn("[Onboarding] Failed to load podcasts", error);
        existingShows = [];
      }
      if (formData.elevenlabsApiKey) {
        try {
          await makeApi(token).put("/api/users/me/elevenlabs-key", {
            api_key: formData.elevenlabsApiKey,
          });
        } catch (error) {
          console.warn("[Onboarding] Failed to save ElevenLabs key", error);
        }
      }
      if (path === "new" && existingShows.length === 0) {
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
        const createdPodcast = await makeApi(token).raw("/api/podcasts/", {
          method: "POST",
          body: podcastPayload,
        });
        if (!createdPodcast || !createdPodcast.id) {
          let detail = "";
          try {
            detail =
              createdPodcast && createdPodcast.detail
                ? createdPodcast.detail
                : JSON.stringify(createdPodcast || {});
          } catch (_) {}
          throw new Error(detail || "Failed to create the podcast show.");
        }
        targetPodcast = createdPodcast;
        try {
          toast({ title: "Great!", description: "Your new podcast show has been created." });
        } catch (_) {}
        try {
          const segments = [];
          if (introAsset?.filename) {
            segments.push({
              segment_type: "intro",
              source: { source_type: "static", filename: introAsset.filename },
            });
          }
          segments.push({
            segment_type: "content",
            source: {
              source_type: "tts",
              script: "",
              voice_id: selectedVoiceId && selectedVoiceId !== "default" ? selectedVoiceId : "default",
            },
          });
          if (outroAsset?.filename) {
            segments.push({
              segment_type: "outro",
              source: { source_type: "static", filename: outroAsset.filename },
            });
          }
          const musicRules = [];
          const selectedMusic = (musicAssets || []).find((a) => a.id === musicChoice && a.id !== "none");
          if (selectedMusic && selectedMusic.id) {
            musicRules.push({
              music_asset_id: selectedMusic.id,
              apply_to_segments: ["intro"],
              start_offset_s: 0,
              end_offset_s: 1,
              fade_in_s: 1.5,
              fade_out_s: 2.0,
              volume_db: -1.4,
            });
            musicRules.push({
              music_asset_id: selectedMusic.id,
              apply_to_segments: ["outro"],
              start_offset_s: -10,
              end_offset_s: 0,
              fade_in_s: 3.0,
              fade_out_s: 1.0,
              volume_db: -1.4,
            });
          }
          const chosen = targetPodcast || (existingShows.length > 0 ? existingShows[existingShows.length - 1] : null);
          const templatePayload = {
            name: "My First Template",
            podcast_id: chosen?.id,
            segments,
            background_music_rules: musicRules,
            timing: { content_start_offset_s: 0, outro_start_offset_s: 0 },
            is_active: true,
            default_elevenlabs_voice_id:
              selectedVoiceId && selectedVoiceId !== "default" ? selectedVoiceId : null,
          };
          try {
            await makeApi(token).post("/api/templates/", templatePayload);
          } catch (error) {
            console.warn("[Onboarding] Failed to create default template", error);
            toast({
              title: "Template not saved",
              description: error?.message || "We could not save your default template.",
              variant: "destructive",
            });
          }
        } catch (error) {
          console.warn("[Onboarding] Failed to set up template", error);
        }
      } else {
        const chosen = existingShows.length > 0 ? existingShows[existingShows.length - 1] : null;
        if (chosen) {
          try {
            const segments = [];
            if (introAsset?.filename) {
              segments.push({
                segment_type: "intro",
                source: { source_type: "static", filename: introAsset.filename },
              });
            }
            segments.push({
              segment_type: "content",
              source: {
                source_type: "tts",
                script: "",
                voice_id: selectedVoiceId && selectedVoiceId !== "default" ? selectedVoiceId : "default",
              },
            });
            if (outroAsset?.filename) {
              segments.push({
                segment_type: "outro",
                source: { source_type: "static", filename: outroAsset.filename },
              });
            }
            const templatePayload = {
              name: "My First Template",
              podcast_id: chosen.id,
              segments,
              background_music_rules: [],
              timing: { content_start_offset_s: 0, outro_start_offset_s: 0 },
              is_active: true,
              default_elevenlabs_voice_id:
                selectedVoiceId && selectedVoiceId !== "default" ? selectedVoiceId : null,
            };
            await makeApi(token).post("/api/templates/", templatePayload);
          } catch (error) {
            console.warn("[Onboarding] Failed to save template for existing show", error);
            toast({
              title: "Template not saved",
              description: error?.message || "We could not save your default template.",
              variant: "destructive",
            });
          }
        }
        try {
          toast({ title: "All done!", description: "Your show has been imported." });
        } catch (_) {}
      }
      try {
        localStorage.removeItem("ppp.onboarding.step");
        localStorage.setItem("ppp.onboarding.completed", "1");
      } catch (error) {
        console.warn("[Onboarding] Failed to persist completion flag", error);
      }
      try {
        window.location.replace("/?onboarding=0");
      } catch (error) {
        console.warn("[Onboarding] Failed to redirect after finish", error);
      }
    } catch (error) {
      try {
        toast({ title: "An Error Occurred", description: error.message, variant: "destructive" });
      } catch (_) {}
    } finally {
      setSaving(false);
    }
  }, [
    token,
    toast,
    formData,
    coverCropperRef,
    introAsset,
    outroAsset,
    selectedVoiceId,
    musicAssets,
    musicChoice,
    path,
  ]);

  useEffect(() => {
    let timer;
    if (path === "import") {
      if (stepId === "importing") {
        timer = setTimeout(
          () => setStepIndex((n) => Math.min(n + 1, wizardSteps.length - 1)),
          1000
        );
      } else if (stepId === "analyze" || stepId === "assets") {
        timer = setTimeout(
          () => setStepIndex((n) => Math.min(n + 1, wizardSteps.length - 1)),
          800
        );
      }
    }
    return () => {
      if (timer) clearTimeout(timer);
    };
  }, [path, stepId, wizardSteps.length]);

  useEffect(() => {
    const shouldResume = resumeAfterImport && path === "import" && stepId === "importSuccess";
    if (shouldResume && !importResumeTimerRef.current) {
      const targetIndex = introOutroIndex >= 0 ? introOutroIndex : 0;
      importResumeTimerRef.current = window.setTimeout(() => {
        importResumeTimerRef.current = null;
        setResumeAfterImport(false);
        setPath("new");
        setShowSkipNotice(true);
        setImportJumpedToStep6(true);
        setStepIndex(targetIndex);
        const importedName =
          importResult?.podcast_name ||
          importResult?.title ||
          importResult?.name ||
          formData.podcastName ||
          "your show";
        toast({
          title: "Import complete",
          description: `We pulled in ${importedName}. Continue with the rest of the setup.`,
        });
      }, 600);
    } else if (!shouldResume && importResumeTimerRef.current) {
      clearTimeout(importResumeTimerRef.current);
      importResumeTimerRef.current = null;
    }
    return () => {
      if (importResumeTimerRef.current) {
        clearTimeout(importResumeTimerRef.current);
        importResumeTimerRef.current = null;
      }
    };
  }, [
    resumeAfterImport,
    path,
    stepId,
    introOutroIndex,
    importResult,
    formData.podcastName,
    toast,
  ]);

  const { nextDisabled, hideNext } = useMemo(() => {
    let disabled = false;
    let hide = false;
    switch (stepId) {
      case "skipNotice":
        disabled = false;
        break;
      case "choosePath":
        hide = true;
        break;
      case "confirm":
        if (path === "import") {
          disabled = importLoading;
        }
        break;
      case "yourName":
        disabled = !(firstName || "").trim();
        break;
      case "showDetails": {
        const nameOk = (formData.podcastName || "").trim().length >= 4;
        const descOk = (formData.podcastDescription || "").trim().length > 0;
        disabled = !(nameOk && descOk);
        break;
      }
      case "coverArt":
        disabled = !(formData.coverArt || skipCoverNow);
        break;
      case "publishCadence":
        disabled = !freqUnit || (freqUnit === "bi-weekly" && Number(freqCount) !== 1);
        break;
      case "publishSchedule":
        if (!notSureSchedule) {
          if (freqUnit === "week") disabled = selectedWeekdays.length === 0;
          else if (freqUnit === "bi-weekly" || freqUnit === "month")
            disabled = selectedDates.length === 0;
        }
        break;
      case "introOutro": {
        const hasIntroAsset =
          introAsset ||
          ttsGeneratedIntro ||
          (introMode === "existing" && introOptions.length > 0);
        const hasOutroAsset =
          outroAsset ||
          ttsGeneratedOutro ||
          (outroMode === "existing" && outroOptions.length > 0);
        if (introMode === "tts" && !introScript.trim() && !hasIntroAsset) {
          disabled = true;
        } else if (introMode === "upload" && !introFile && !hasIntroAsset) {
          disabled = true;
        } else if (introMode === "record" && !hasIntroAsset) {
          disabled = true;
        }
        if (outroMode === "tts" && !outroScript.trim() && !hasOutroAsset) {
          disabled = true;
        } else if (outroMode === "upload" && !outroFile && !hasOutroAsset) {
          disabled = true;
        } else if (outroMode === "record" && !hasOutroAsset) {
          disabled = true;
        }
        break;
      }
      case "finish":
        if (path === "new") {
          const nameOk = (formData.podcastName || "").trim().length >= 4;
          const descOk = (formData.podcastDescription || "").trim().length > 0;
          disabled = !(nameOk && descOk);
        }
        break;
      default:
        break;
    }
    return { nextDisabled: !!disabled, hideNext: !!hide };
  }, [
    stepId,
    path,
    importLoading,
    firstName,
    formData.podcastName,
    formData.podcastDescription,
    formData.coverArt,
    skipCoverNow,
    freqUnit,
    freqCount,
    notSureSchedule,
    selectedWeekdays.length,
    selectedDates.length,
    introMode,
    outroMode,
    introScript,
    outroScript,
    introFile,
    outroFile,
    introAsset,
    outroAsset,
    ttsGeneratedIntro,
    ttsGeneratedOutro,
    introOptions.length,
    outroOptions.length,
  ]);

  useEffect(() => {
    if (stepId !== "skipNotice") return;
    const timer = setTimeout(() => {
      setStepIndex((n) => Math.min(n + 1, wizardSteps.length - 1));
    }, 900);
    return () => clearTimeout(timer);
  }, [stepId, wizardSteps.length]);

  const stepComponents = useMemo(
    () => ({
      yourName: YourNameStep,
      choosePath: ChoosePathStep,
      showDetails: ShowDetailsStep,
      format: FormatStep,
      coverArt: CoverArtStep,
      skipNotice: SkipNoticeStep,
      introOutro: IntroOutroStep,
      music: MusicStep,
      publishCadence: PublishCadenceStep,
      publishSchedule: PublishScheduleStep,
      finish: FinishStep,
      rss: ImportRssStep,
      confirm: ConfirmImportStep,
      importing: ImportingStep,
      analyze: ImportAnalyzeStep,
      assets: ImportAssetsStep,
      importSuccess: ImportSuccessStep,
    }),
    []
  );

  const wizardContext = {
    token,
    refreshUser,
    toast,
    path,
    setPath,
    formData,
    setFormData,
    saving,
    setSaving,
    formatKey,
    setFormatKey,
    rssUrl,
    setRssUrl,
    importResult,
    setImportResult,
    resumeAfterImport,
    setResumeAfterImport,
    importLoading,
    setImportLoading,
    showSkipNotice,
    setShowSkipNotice,
    importJumpedToStep6,
    setImportJumpedToStep6,
    musicAssets,
    setMusicAssets,
    musicLoading,
    setMusicLoading,
    musicChoice,
    setMusicChoice,
    musicPreviewing,
    setMusicPreviewing,
    audioRef,
    ioAudioRef,
    introPreviewing,
    setIntroPreviewing,
    outroPreviewing,
    setOutroPreviewing,
    freqUnit,
    setFreqUnit,
    freqCount,
    setFreqCount,
    cadenceError,
    setCadenceError,
    selectedWeekdays,
    setSelectedWeekdays,
    selectedDates,
    setSelectedDates,
    notSureSchedule,
    setNotSureSchedule,
    firstName,
    setFirstName,
    lastName,
    setLastName,
    nameError,
    setNameError,
    skipCoverNow,
    setSkipCoverNow,
    coverArtInputRef,
    coverCropperRef,
    coverCrop,
    setCoverCrop,
    coverMode,
    setCoverMode,
    introMode,
    setIntroMode,
    introOptions,
    setIntroOptions,
    selectedIntroId,
    setSelectedIntroId,
    introAsset,
    setIntroAsset,
    introScript,
    setIntroScript,
    introFile,
    setIntroFile,
    outroMode,
    setOutroMode,
    outroOptions,
    setOutroOptions,
    selectedOutroId,
    setSelectedOutroId,
    outroAsset,
    setOutroAsset,
    outroScript,
    setOutroScript,
    outroFile,
    setOutroFile,
    voices,
    voicesLoading,
    voicesError,
    selectedVoiceId,
    setSelectedVoiceId,
    voicePreviewing,
    setVoicePreviewing,
    needsTtsReview,
    setNeedsTtsReview,
    ttsGeneratedIntro,
    setTtsGeneratedIntro,
    ttsGeneratedOutro,
    setTtsGeneratedOutro,
    renameIntro,
    setRenameIntro,
    renameOutro,
    setRenameOutro,
    firstTimeUser,
    largeText,
    setLargeText,
    highContrast,
    setHighContrast,
    resolvedTimezone,
    setStepIndex,
    handleChange,
    toggleIntroPreview: handleIntroOutroPreview,
    toggleOutroPreview: handleIntroOutroPreview,
    toggleMusicPreview,
    previewSelectedVoice,
    canPreviewSelectedVoice,
    getVoiceById: (vid) => getVoiceById(voices, vid),
    formatMediaDisplayName,
    generateOrUploadTTS,
  };

  const steps = wizardSteps.map((step, index) => {
    const Component = stepComponents[step.id];
    return {
      id: step.id,
      title: step.title,
      description: step.description,
      tip:
        step.id === "yourName"
          ? "We'll use this to personalize your dashboard."
          : step.id === "choosePath"
          ? "If you have an existing podcast, import it here."
          : step.id === "showDetails"
          ? "Short and clear works best."
          : step.id === "format"
          ? "This is for your reference."
          : step.id === "coverArt"
          ? "No artwork yet? You can skip this for now."
          : step.id === "introOutro"
          ? "Start with our default scripts or upload your own audio."
          : step.id === "music"
          ? 'This is background music for your intro and outro. It can be changed or removed at any time.'
          : step.id === "publishCadence"
          ? "We ask to help keep you on track for publishing consistently"
          : step.id === "publishSchedule"
          ? "Consistency is more important than volume for a successful podcast"
          : step.id === "rss"
          ? "Paste your feed URL."
          : step.id === "analyze"
          ? "We'll bring over what we can, and you can tidy later."
          : step.id === "assets"
          ? "We'll bring over what we can, and you can tidy later."
          : step.id === "finish"
          ? "There's a short tour next if you'd like it."
          : "",
      render: Component
        ? () => <Component wizard={wizardContext} stepIndex={index} />
        : () => null,
      validate:
        step.validate && typeof step.validate === "function"
          ? step.validate
          : step.id === "publishCadence"
          ? async () => {
              if (!freqUnit) {
                setCadenceError("Please choose a frequency.");
                return false;
              }
              if (freqUnit === "bi-weekly" && Number(freqCount) !== 1) {
                setCadenceError("For bi-weekly, X must be 1.");
                return false;
              }
              setCadenceError("");
              return true;
            }
          : step.id === "publishSchedule"
          ? async () => {
              if (notSureSchedule) return true;
              if (freqUnit === "week" && selectedWeekdays.length === 0) return false;
              if ((freqUnit === "bi-weekly" || freqUnit === "month") && selectedDates.length === 0)
                return false;
              return true;
            }
          : step.id === "confirm" && path === "import"
          ? async () => {
              const trimmed = (rssUrl || "").trim();
              if (!trimmed) {
                toast({
                  variant: "destructive",
                  title: "RSS feed required",
                  description: "Please enter your feed URL before continuing.",
                });
                return false;
              }
              setImportLoading(true);
              try {
                const api = makeApi(token);
                const data = await api.post("/api/import/rss", { rss_url: trimmed });
                setImportResult(data);
                setRssUrl(trimmed);
                const importedName = data?.podcast_name || data?.title || data?.name || "";
                const importedDescription = data?.description || data?.summary || "";
                setFormData((prev) => ({
                  ...prev,
                  podcastName: importedName || prev.podcastName || "",
                  podcastDescription: importedDescription || prev.podcastDescription || "",
                }));
                setSkipCoverNow(true);
                setImportLoading(false);
                setResumeAfterImport(true);
                return true;
              } catch (error) {
                console.error("[Onboarding] Import failed", error);
                toast({
                  variant: "destructive",
                  title: "Import failed",
                  description: error?.message || "We couldn't import that feed.",
                });
                setImportLoading(false);
                return false;
              }
            }
          : undefined,
    };
  });

  return {
    steps,
    stepIndex,
    setStepIndex,
    handleFinish,
    handleExitDiscard,
    nextDisabled,
    hideNext,
    hideBack: importJumpedToStep6 && stepId === "introOutro",
    showExitDiscard: hasExistingPodcast,
    greetingName: firstName?.trim() || "",
    prefs: { largeText, setLargeText, highContrast, setHighContrast },
  };
}
