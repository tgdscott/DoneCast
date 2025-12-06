import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import PublishPlanStep from "../steps/PublishPlanStep.jsx";
import DesignStep from "../steps/DesignStep.jsx";
import WebsiteStep from "../steps/WebsiteStep.jsx";
import DistributionRequiredStep from "../steps/DistributionRequiredStep.jsx";
import DistributionOptionalStep from "../steps/DistributionOptionalStep.jsx";
import FinishStep from "../steps/FinishStep.jsx";
import ImportRssStep from "../steps/ImportRssStep.jsx";
import ConfirmImportStep from "../steps/ConfirmImportStep.jsx";
import ImportingStep from "../steps/ImportingStep.jsx";
import ImportAnalyzeStep from "../steps/ImportAnalyzeStep.jsx";
import ImportAssetsStep from "../steps/ImportAssetsStep.jsx";
import ImportSuccessStep from "../steps/ImportSuccessStep.jsx";
import WelcomeStep from "../steps/WelcomeStep.jsx";

const DISTRIBUTION_BOOTSTRAP_STEPS = new Set([
  "music",
  "publishPlan",
  "distributionRequired",
  "distributionOptional",
  "design",
  "website",
  "finish",
]);

export default function useOnboardingWizard({
  token,
  user,
  refreshUser,
  toast,
  comfort,
  showConfirm,
}) {
  const resolvedTimezone = useResolvedTimezone(user?.timezone);
  const { largeText, setLargeText, highContrast, setHighContrast } = comfort;

  const getStoredStepIndex = useCallback((email) => {
    if (!email) return 0;
    try {
      const key = `ppp.onboarding.step.${email}`;
      const raw = localStorage.getItem(key);
      const parsed = raw != null ? parseInt(raw, 10) : 0;
      const idx = Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
      if (idx > 0) {
        console.log(`[Onboarding] Restored stepIndex ${idx} for user ${email} from localStorage`);
      }
      return idx;
    } catch (error) {
      console.warn("[Onboarding] Failed to restore stepIndex from localStorage:", error);
      return 0;
    }
  }, []);

  const initialStepData = (() => {
    if (!user?.email) {
      return { value: 0, restored: false };
    }
    return { value: getStoredStepIndex(user.email), restored: true };
  })();

  const [fromManager] = useState(() => {
    try {
      return new URLSearchParams(window.location.search).get("from") === "manager";
    } catch {
      return false;
    }
  });

  const [stepIndex, setStepIndex] = useState(initialStepData.value);
  const restoredStepRef = useRef(initialStepData.restored);

  // Clear step when user changes (prevents cross-user contamination)
  const lastUserEmailRef = useRef(user?.email);
  useEffect(() => {
    const previousEmail = lastUserEmailRef.current;
    if (user?.email && previousEmail && previousEmail !== user.email) {
      // User changed - clear old user's step
      try {
        const oldKey = `ppp.onboarding.step.${previousEmail}`;
        localStorage.removeItem(oldKey);
        console.log(`[Onboarding] Cleared step for previous user: ${previousEmail}`);
      } catch (error) {
        console.warn("[Onboarding] Failed to clear previous user's step", error);
      }
      // Reset to step 0 for new user
      setStepIndex(0);
    }
    if (user?.email !== previousEmail) {
      restoredStepRef.current = false;
    }
    lastUserEmailRef.current = user?.email;
  }, [user?.email, setStepIndex]);

  useEffect(() => {
    if (!user?.email || restoredStepRef.current) {
      return;
    }
    const storedIndex = getStoredStepIndex(user.email);
    restoredStepRef.current = true;
    setStepIndex((current) => (storedIndex !== current ? storedIndex : current));
  }, [user?.email, getStoredStepIndex]);

  const stepSaveTimer = useRef(null);
  const importResumeTimerRef = useRef(null);

  const [path, setPath] = useState("new");
  const [formData, setFormData] = useState(() => {
    const defaults = {
      podcastName: "",
      podcastDescription: "",
      coverArt: null,
      elevenlabsApiKey: "",
      hostBio: "",
    };
    if (!user?.email) return defaults;
    try {
      const saved = localStorage.getItem(`ppp.onboarding.form.${user.email}`);
      if (saved) {
        const parsed = JSON.parse(saved);
        return { ...defaults, ...parsed, coverArt: null }; // Cannot restore File objects
      }
    } catch (e) {
      console.warn("[Onboarding] Failed to restore form data", e);
    }
    return defaults;
  });

  // Persist formData
  useEffect(() => {
    if (!user?.email) return;
    const timer = setTimeout(() => {
      try {
        const toSave = {
          podcastName: formData.podcastName,
          podcastDescription: formData.podcastDescription,
          elevenlabsApiKey: formData.elevenlabsApiKey,
          hostBio: formData.hostBio,
        };
        localStorage.setItem(`ppp.onboarding.form.${user.email}`, JSON.stringify(toSave));
      } catch (e) {
        console.warn("[Onboarding] Failed to save form data", e);
      }
    }, 500);
    return () => clearTimeout(timer);
  }, [formData, user?.email]);

  const [saving, setSaving] = useState(false);
  const [formatKey, setFormatKey] = useState("solo");
  const [rssUrl, setRssUrl] = useState("");
  const [importResult, setImportResult] = useState(null);
  const [resumeAfterImport, setResumeAfterImport] = useState(false);
  const [importLoading, setImportLoading] = useState(false);
  const [showSkipNotice, setShowSkipNotice] = useState(false);
  const [importJumpedToStep6, setImportJumpedToStep6] = useState(false);

  const [targetPodcastId, setTargetPodcastId] = useState(() => {
    if (!user?.email) return null;
    try {
      return localStorage.getItem(`ppp.onboarding.pid.${user.email}`) || null;
    } catch { return null; }
  });

  useEffect(() => {
    if (!user?.email) return;
    if (targetPodcastId) {
      localStorage.setItem(`ppp.onboarding.pid.${user.email}`, targetPodcastId);
    } else {
      localStorage.removeItem(`ppp.onboarding.pid.${user.email}`);
    }
  }, [targetPodcastId, user?.email]);

  const lastPodcastInfoRef = useRef(null);
  const ensurePodcastPromiseRef = useRef(null);
  const rssBootstrapRequestedRef = useRef(false);

  const [rssFeedUrl, setRssFeedUrl] = useState("");
  const [rssStatus, setRssStatus] = useState({ state: "idle", lastChecked: 0, error: null });
  const [showRssWaiting, setShowRssWaiting] = useState(false);
  const [distributionReady, setDistributionReady] = useState(false);
  const [websiteUrl, setWebsiteUrl] = useState(() => {
    if (!user?.email) return "";
    try {
      return localStorage.getItem(`ppp.onboarding.web.${user.email}`) || "";
    } catch { return ""; }
  });

  useEffect(() => {
    if (!user?.email) return;
    if (websiteUrl) {
      localStorage.setItem(`ppp.onboarding.web.${user.email}`, websiteUrl);
    } else {
      localStorage.removeItem(`ppp.onboarding.web.${user.email}`);
    }
  }, [websiteUrl, user?.email]);

  // Design preferences
  const [designVibe, setDesignVibe] = useState("Clean & Minimal");
  const [colorPreference, setColorPreference] = useState("");
  const [additionalNotes, setAdditionalNotes] = useState("");

  const [musicAssets, setMusicAssets] = useState([NO_MUSIC_OPTION]);
  const [musicLoading, setMusicLoading] = useState(false);
  const [musicChoice, setMusicChoice] = useState("none");
  const [musicPreviewing, setMusicPreviewing] = useState(null);
  const audioRef = useRef(null);
  const ioAudioRef = useRef(null);
  const [introPreviewing, setIntroPreviewing] = useState(false);
  const [outroPreviewing, setOutroPreviewing] = useState(false);

  const [freqUnit, setFreqUnit] = useState("week");
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
  const [introScript, setIntroScript] = useState("");
  const [outroScript, setOutroScript] = useState("");
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
  const [selectedVoiceId, setSelectedVoiceId] = useState("default"); // Fallback/default voice
  const [introVoiceId, setIntroVoiceId] = useState("default"); // Intro-specific voice
  const [outroVoiceId, setOutroVoiceId] = useState("default"); // Outro-specific voice
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
      { id: "design", title: "Website Style" },
      { id: "importSuccess", title: "Import complete!" },
    ],
    []
  );

  const newFlowSteps = useMemo(() => {
    const welcomeStep = {
      id: "welcome",
      title: "Welcome to DoneCast",
      description: "We make podcasting easy. This is a one-time setup to tailor DoneCast to your show.",
    };
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
      welcomeStep,
      nameStep,
      choosePathStep,
      { id: "showDetails", title: "About your show" },
      { id: "format", title: "Format" },
      { id: "coverArt", title: "Podcast Cover Art" },
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
      { id: "publishPlan", title: "Publishing plan" },
      { id: "distributionRequired", title: "Distribute to Apple & Spotify" },
      { id: "distributionOptional", title: "Other platforms" },
      { id: "design", title: "Website Style" },
      { id: "website", title: "Create your website" },
      { id: "finish", title: "All done!" },
    ];

    const filtered = fromManager ? baseSteps.filter((step) => step.id !== "yourName") : baseSteps;
    return filtered;
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

  const publishPlanIndex = useMemo(() => {
    const idx = newFlowSteps.findIndex((step) => step.id === "publishPlan");
    return idx >= 0 ? idx : 0;
  }, [newFlowSteps]);

  const distributionRequiredIndex = useMemo(() => {
    const idx = newFlowSteps.findIndex((step) => step.id === "distributionRequired");
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
          // Remove both user-specific and legacy global key
          if (user?.email) {
            localStorage.removeItem(`ppp.onboarding.step.${user.email}`);
          }
          localStorage.removeItem("ppp.onboarding.step"); // Legacy global key
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
        // Save step with user-specific key
        if (user?.email) {
          const userStepKey = `ppp.onboarding.step.${user.email}`;
          localStorage.setItem(userStepKey, String(stepIndex));
        }
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
      } catch (_) { }
      audioRef.current = null;
      setMusicPreviewing(null);
    }
  }, [stepId, musicAssets.length, musicLoading, token]);

  useEffect(() => {
    // Preload voices early to reduce delay at Intro/Outro
    if (!voicesLoading && voices.length === 0) {
      setVoicesLoading(true);
      setVoicesError("");
      (async () => {
        try {
          const data = await makeApi(token).get("/api/elevenlabs/voices?size=20");
          const items = (data && (data.items || data.voices)) || [];
          setVoices(items);
          if (items.length > 0) {
            const first = items[0];
            const defaultVoiceId = first.voice_id || first.id || first.name || "default";
            // Initialize all voice IDs if they're still at default
            if (!selectedVoiceId || selectedVoiceId === "default") {
              setSelectedVoiceId(defaultVoiceId);
            }
            if (!introVoiceId || introVoiceId === "default") {
              setIntroVoiceId(defaultVoiceId);
            }
            if (!outroVoiceId || outroVoiceId === "default") {
              setOutroVoiceId(defaultVoiceId);
            }
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
      } catch (_) { }
      setVoicePreviewing(false);
    }
    if (stepId !== "introOutro" && ioAudioRef.current) {
      try {
        ioAudioRef.current.pause();
      } catch (_) { }
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
    async (asset) => {
      await toggleMusicPreviewHelper({
        asset,
        audioRef,
        musicPreviewing,
        setMusicPreviewing,
        token,
        makeApi,
        buildApiUrl,
      });
    },
    [musicPreviewing, token, makeApi, buildApiUrl]
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

  const handleExitDiscard = useCallback(async () => {
    // Use branded confirm dialog instead of window.confirm
    const showConfirmSafe = showConfirm;
    if (!hasExistingPodcast) return;
    const idxIntro = newFlowSteps.findIndex((s) => s.id === "introOutro");
    const atOrBeyondIntro = idxIntro >= 0 && stepIndex >= idxIntro;
    if (atOrBeyondIntro) {
      let ok = true;
      if (showConfirmSafe) {
        ok = await showConfirmSafe({
          title: "Exit and discard changes?",
          description: "Your onboarding progress will be cleared.",
          confirmText: "Discard & Exit",
          cancelText: "Stay",
          variant: "destructive",
        });
      } else {
        ok = typeof window !== "undefined" ? window.confirm("Exit and discard your onboarding changes?") : true;
      }
      if (!ok) return;
    }
    try {
      localStorage.removeItem("ppp.onboarding.step");
      if (user?.email) {
        localStorage.removeItem(`ppp.onboarding.step.${user.email}`);
        localStorage.removeItem(`ppp.onboarding.form.${user.email}`);
        localStorage.removeItem(`ppp.onboarding.pid.${user.email}`);
        localStorage.removeItem(`ppp.onboarding.web.${user.email}`);
      }
    } catch (error) {
      console.warn("[Onboarding] Failed to clear stored step", error);
    }
    try {
      // Use href instead of replace to force full page reload and clear ALL state
      // The discard=1 param helps us identify this was an intentional discard
      window.location.href = "/?onboarding=0&discard=1";
    } catch (error) {
      console.warn("[Onboarding] Failed to redirect", error);
    }
  }, [hasExistingPodcast, newFlowSteps, stepIndex, user?.email]);

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
        // Use segment-specific voice if available, otherwise fall back to selectedVoiceId
        const voiceToUse = kind === "intro"
          ? (introVoiceId && introVoiceId !== "default" ? introVoiceId : selectedVoiceId)
          : (outroVoiceId && outroVoiceId !== "default" ? outroVoiceId : selectedVoiceId);
        if (voiceToUse && voiceToUse !== "default") body.voice_id = voiceToUse;
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
        } catch (_) { }
        return null;
      }
    },
    [token, toast, selectedVoiceId, introVoiceId, outroVoiceId, firstTimeUser]
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

      if (currentAsset && currentAsset.filename) {
        return currentAsset;
      }

      if (mode === "existing" && selectedId) {
        const existing = options.find((item) => String(item.id || item.filename) === selectedId);
        if (existing) {
          if (isIntro) {
            setIntroAsset(existing);
          } else {
            setOutroAsset(existing);
          }
          return existing;
        }
        return null;
      }

      if (mode === "record") {
        return currentAsset;
      }

      const asset = await generateOrUploadTTS(kind, mode, script, file, currentAsset);
      if (!asset) {
        return null;
      }

      const key = String(asset.id || asset.filename || "");
      if (isIntro) {
        setIntroAsset(asset);
        if (key) {
          setSelectedIntroId(key);
          setIntroOptions((previous) => {
            const exists = previous.some((item) => String(item.id || item.filename) === key);
            return exists ? previous : [...previous, asset];
          });
        }
      } else {
        setOutroAsset(asset);
        if (key) {
          setSelectedOutroId(key);
          setOutroOptions((previous) => {
            const exists = previous.some((item) => String(item.id || item.filename) === key);
            return exists ? previous : [...previous, asset];
          });
        }
      }

      return asset;
    },
    [
      introMode,
      outroMode,
      introScript,
      outroScript,
      introFile,
      outroFile,
      introAsset,
      outroAsset,
      introOptions,
      outroOptions,
      selectedIntroId,
      selectedOutroId,
      generateOrUploadTTS,
    ]
  );

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
  }, [formData.podcastName, formData.podcastDescription, formData.coverArt, formatKey]);

  const ensurePodcastExists = useCallback(async () => {
    if (!token) {
      return null;
    }

    if (ensurePodcastPromiseRef.current) {
      return ensurePodcastPromiseRef.current;
    }

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
        const feed =
          selected.rss_feed_url ||
          selected.rss_url_locked ||
          selected.rss_url ||
          selected.feed_url ||
          selected.rssFeedUrl;
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
    }, [token, targetPodcastId, formData.podcastName, path, preparePodcastPayload, setTargetPodcastId, setRssFeedUrl, toast]);

  const refreshRssMetadata = useCallback(async () => {
    if (!token) {
      return null;
    }

    setRssStatus((prev) => {
      if (prev.state === "ready") {
        return prev;
      }
      return { state: "checking", lastChecked: Date.now(), error: null };
    });

    try {
      let podcastId = targetPodcastId;
      if (!podcastId) {
        const ensured = await ensurePodcastExists();
        podcastId = ensured?.id || null;
      }

      if (!podcastId) {
        throw new Error("Podcast not created yet");
      }

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
  }, [token, targetPodcastId, ensurePodcastExists, setRssFeedUrl, setShowRssWaiting]);

  useEffect(() => {
    if (rssStatus.state !== "pending") {
      return undefined;
    }

    const timer = setTimeout(() => {
      refreshRssMetadata().catch((err) => {
        console.warn("[Onboarding] RSS auto-refresh failed:", err);
      });
    }, 4000);

    return () => clearTimeout(timer);
  }, [rssStatus.state, refreshRssMetadata]);

  useEffect(() => {
    if (path !== "new") {
      return;
    }
    if (!token) {
      return;
    }
    if (stepIndex < introOutroIndex) {
      return;
    }
    if (rssStatus.state === "ready") {
      return;
    }
    if (rssBootstrapRequestedRef.current) {
      return;
    }

    rssBootstrapRequestedRef.current = true;
    refreshRssMetadata().catch((err) => {
      rssBootstrapRequestedRef.current = false;
      console.warn("[Onboarding] RSS bootstrap failed:", err);
    });
  }, [path, token, stepIndex, introOutroIndex, rssStatus.state, refreshRssMetadata]);

  useEffect(() => {
    if (path !== "new") {
      return;
    }
    if (!stepId || !DISTRIBUTION_BOOTSTRAP_STEPS.has(stepId)) {
      return;
    }

    let cancelled = false;
    ensurePodcastExists()?.catch((err) => {
      if (!cancelled && err) {
        console.warn("[Onboarding] ensurePodcastExists failed:", err);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [stepId, ensurePodcastExists, path]);

  const handleFinish = useCallback(async () => {
    try {
      setSaving(true);
      let targetPodcast = null;
      let existingShows = [];
      try {
        const data = await makeApi(token).get("/api/podcasts/");
        existingShows = Array.isArray(data) ? data : data?.items || [];
        console.log(`[Onboarding.handleFinish] Found ${existingShows.length} existing podcast(s)`);

        // If we have a targetPodcastId, find it in the list
        if (targetPodcastId && existingShows.length > 0) {
          targetPodcast = existingShows.find(p => p.id === targetPodcastId) || null;
          if (targetPodcast) {
            console.log(`[Onboarding.handleFinish] Found target podcast by ID: ${targetPodcast.id} (${targetPodcast.name})`);
          } else {
            console.warn(`[Onboarding.handleFinish] targetPodcastId ${targetPodcastId} not found in existing shows`);
          }
        }

        // Also try to match by name if we don't have a targetPodcast yet
        if (!targetPodcast && existingShows.length > 0 && formData.podcastName) {
          const nameClean = (formData.podcastName || "").trim().toLowerCase();
          targetPodcast = existingShows.find(p =>
            p.name && p.name.trim().toLowerCase() === nameClean
          ) || null;
          if (targetPodcast) {
            console.log(`[Onboarding.handleFinish] Found podcast by name match: ${targetPodcast.id} (${targetPodcast.name})`);
            // Update targetPodcastId to match
            setTargetPodcastId(targetPodcast.id);
          }
        }
      } catch (error) {
        console.warn("[Onboarding.handleFinish] Failed to load podcasts:", error);
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
      // Check if podcast was already created (e.g., in website step)
      // Use targetPodcast OR any existing shows OR targetPodcastId
      // Also check by name to catch cases where targetPodcastId wasn't set properly
      const nameClean = formData.podcastName ? (formData.podcastName || "").trim().toLowerCase() : "";
      const hasMatchingPodcast = existingShows.length > 0 && nameClean
        ? existingShows.some(p => p.name && p.name.trim().toLowerCase() === nameClean)
        : false;
      const podcastAlreadyCreated = targetPodcast || targetPodcastId || hasMatchingPodcast || existingShows.length > 0;

      try {
        await ensureSegmentAsset("intro");
        await ensureSegmentAsset("outro");
      } catch (error) {
        console.warn("[Onboarding] Failed to ensure intro/outro assets", error);
      }

      if (podcastAlreadyCreated) {
        const reason = targetPodcast ? 'targetPodcast' : targetPodcastId ? 'targetPodcastId' : hasMatchingPodcast ? 'name match' : 'any existing';
        console.log(`[Onboarding.handleFinish] Podcast already exists (${reason}) - skipping creation. Using: ${targetPodcast?.id || targetPodcastId || 'first available'}`);
      }

      if (path === "new" && !podcastAlreadyCreated) {
        console.log("[Onboarding.handleFinish] No podcast found - creating new one...");
        const podcastPayload = await preparePodcastPayload();
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
          } catch (_) { }
          throw new Error(detail || "Failed to create the podcast show.");
        }
        targetPodcast = createdPodcast;
        setTargetPodcastId(createdPodcast.id);
        try {
          toast({ title: "Great!", description: "Your new podcast show has been created." });
        } catch (_) { }
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
          // Use existing podcast if it was created earlier, otherwise use the one we just created
          // Priority: targetPodcast (found by ID/name) > targetPodcastId match > newly created > first available
          let chosen = null;
          if (targetPodcast) {
            chosen = targetPodcast;
            console.log(`[Onboarding.handleFinish] Using targetPodcast: ${chosen.id} (${chosen.name})`);
          } else if (targetPodcastId) {
            chosen = existingShows.find(p => p.id === targetPodcastId) || null;
            if (chosen) {
              console.log(`[Onboarding.handleFinish] Using podcast found by targetPodcastId: ${chosen.id} (${chosen.name})`);
            }
          }
          if (!chosen && targetPodcast) {
            chosen = targetPodcast;
          }
          if (!chosen && existingShows.length > 0) {
            // Use most recently created (last in array, or match by name)
            const nameMatch = formData.podcastName
              ? existingShows.find(p => p.name && p.name.trim().toLowerCase() === (formData.podcastName || "").trim().toLowerCase())
              : null;
            chosen = nameMatch || existingShows[existingShows.length - 1];
            console.log(`[Onboarding.handleFinish] Using ${nameMatch ? 'name-matched' : 'most recent'} podcast: ${chosen.id} (${chosen.name})`);
          }
          // Fallback to newly created podcast if nothing else found
          if (!chosen && targetPodcast) {
            chosen = targetPodcast; // This should be the newly created one
            console.log(`[Onboarding.handleFinish] Using newly created podcast: ${chosen.id} (${chosen.name})`);
          }
          if (!chosen) {
            console.error("[Onboarding.handleFinish] No podcast available - this should not happen!");
            throw new Error("No podcast available to create template for.");
          }
          const templatePayload = {
            name: "My First Template",
            podcast_id: chosen.id,
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
        // Podcast already exists - use it
        let chosen = null;
        if (targetPodcast) {
          chosen = targetPodcast;
          console.log(`[Onboarding.handleFinish] Using existing targetPodcast: ${chosen.id} (${chosen.name})`);
        } else if (targetPodcastId) {
          chosen = existingShows.find(p => p.id === targetPodcastId) || null;
          if (chosen) {
            console.log(`[Onboarding.handleFinish] Using existing podcast by targetPodcastId: ${chosen.id} (${chosen.name})`);
          }
        }
        if (!chosen && existingShows.length > 0) {
          // Match by name first, then use most recent
          const nameMatch = formData.podcastName
            ? existingShows.find(p => p.name && p.name.trim().toLowerCase() === (formData.podcastName || "").trim().toLowerCase())
            : null;
          chosen = nameMatch || existingShows[existingShows.length - 1];
          console.log(`[Onboarding.handleFinish] Using ${nameMatch ? 'name-matched' : 'most recent'} existing podcast: ${chosen.id} (${chosen.name})`);
        }
        if (!chosen) {
          console.error("[Onboarding.handleFinish] No existing podcast found but podcastAlreadyCreated was true!");
          throw new Error("No podcast available to create template for.");
        }
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
        } catch (_) { }
      }
      try {
        localStorage.removeItem("ppp.onboarding.step");
        if (user?.email) {
          localStorage.removeItem(`ppp.onboarding.step.${user.email}`);
          localStorage.removeItem(`ppp.onboarding.form.${user.email}`);
          localStorage.removeItem(`ppp.onboarding.pid.${user.email}`);
          localStorage.removeItem(`ppp.onboarding.web.${user.email}`);
        }
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
      } catch (_) { }
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
    preparePodcastPayload,
    ensureSegmentAsset,
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
        disabled = !formData.coverArt; // Make cover art required
        break;
      case "publishPlan":
        disabled = !freqUnit || (freqUnit === "bi-weekly" && Number(freqCount) !== 1);
        break;
      // schedule selection is part of publishPlan; no separate gating case
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
      case "distributionRequired":
        disabled = !distributionReady;
        break;
      default:
        break;
    }
    return { nextDisabled: !!disabled, hideNext: !!hide };
  }, [
    stepId,
    path,
    distributionReady,
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
      welcome: WelcomeStep,
      yourName: YourNameStep,
      choosePath: ChoosePathStep,
      showDetails: ShowDetailsStep,
      format: FormatStep,
      coverArt: CoverArtStep,
      skipNotice: SkipNoticeStep,
      introOutro: IntroOutroStep,
      music: MusicStep,
      publishPlan: PublishPlanStep,
      website: WebsiteStep,
      distributionRequired: DistributionRequiredStep,
      distributionOptional: DistributionOptionalStep,
      finish: FinishStep,
      rss: ImportRssStep,
      confirm: ConfirmImportStep,
      importing: ImportingStep,
      analyze: ImportAnalyzeStep,
      assets: ImportAssetsStep,
      design: DesignStep,
      importSuccess: ImportSuccessStep,
    }),
    []
  );

  // Generate cover art with AI
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

      console.log("[Onboarding] Generate cover response:", {
        hasImage: !!response.image,
        imageType: typeof response.image,
        imageLength: response.image?.length,
        imagePreview: response.image?.substring(0, 100),
      });

      if (!response.image) {
        console.error("[Onboarding] No image in response:", response);
        throw new Error("No image returned from server");
      }

      // Check if response is an error object
      if (response.error || response.detail) {
        throw new Error(response.detail || response.error || "Failed to generate cover art");
      }

      // Convert base64 data URL to File object
      // Handle both formats: "data:image/png;base64,{data}" or just "{data}"
      let base64Data = response.image;
      let mimeType = "image/png";

      // Check if it's a data URL format
      if (base64Data.includes(",")) {
        const parts = base64Data.split(",");
        base64Data = parts[1];
        // Extract mime type from data URL prefix if available
        const prefix = parts[0];
        const mimeMatch = prefix.match(/data:([^;]+)/);
        if (mimeMatch) {
          mimeType = mimeMatch[1];
        }
      } else if (base64Data.startsWith("data:")) {
        // Data URL without comma separator (malformed but handle it)
        const match = base64Data.match(/data:([^,]+),(.+)/);
        if (match) {
          mimeType = match[1].split(";")[0];
          base64Data = match[2];
        } else {
          throw new Error("Invalid image data format from server");
        }
      }
      // If no data: prefix, assume it's already base64 data

      // Clean up base64 string (remove whitespace, newlines, etc.)
      base64Data = base64Data.trim().replace(/\s/g, "");

      // Validate base64 format
      if (!/^[A-Za-z0-9+/=]+$/.test(base64Data)) {
        console.error("[Onboarding] Invalid base64 data:", base64Data.substring(0, 100));
        throw new Error("Invalid image data format: not valid base64");
      }

      try {
        const binaryString = atob(base64Data);
        const bytes = new Uint8Array(binaryString.length);
        for (let i = 0; i < binaryString.length; i++) {
          bytes[i] = binaryString.charCodeAt(i);
        }
        const blob = new Blob([bytes], { type: mimeType });
        const file = new File([blob], "ai-generated-cover.png", { type: mimeType });

        return file;
      } catch (decodeError) {
        console.error("[Onboarding] Base64 decode error:", decodeError);
        console.error("[Onboarding] Base64 data preview:", base64Data.substring(0, 200));
        throw new Error(`Failed to decode image data: ${decodeError.message}`);
      }
    } catch (error) {
      console.error("[Onboarding] Failed to generate cover art:", error);
      throw error;
    }
  }, [token, formData.podcastName, formData.podcastDescription]);

  // Reset function to clear all onboarding state and start over
  const handleStartOver = useCallback(async () => {
    const confirmed = window.confirm(
      "Are you sure you want to start over? This will clear all your progress and you'll need to start from the beginning."
    );
    if (!confirmed) return;

    try {
      if (token) {
        try {
          await makeApi(token).post("/api/onboarding/reset");
        } catch (resetError) {
          console.warn("[Onboarding] Failed to reset server-side onboarding session", resetError);
        }
      }
      // Clear all localStorage keys related to onboarding
      // Remove user-specific step key
      if (user?.email) {
        localStorage.removeItem(`ppp.onboarding.step.${user.email}`);
        localStorage.removeItem(`ppp.onboarding.form.${user.email}`);
        localStorage.removeItem(`ppp.onboarding.pid.${user.email}`);
        localStorage.removeItem(`ppp.onboarding.web.${user.email}`);
      }
      // Also remove legacy global key for cleanup
      localStorage.removeItem("ppp.onboarding.step");
      localStorage.removeItem("ppp.onboarding.completed");

      // Clear any other onboarding-related localStorage keys
      const keysToRemove = [];
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && key.startsWith("ppp.onboarding.")) {
          keysToRemove.push(key);
        }
      }
      keysToRemove.forEach(key => localStorage.removeItem(key));

      // Stop any audio previews
      try {
        if (audioRef.current) {
          audioRef.current.pause();
          audioRef.current.src = "";
        }
        if (ioAudioRef.current) {
          ioAudioRef.current.pause();
          ioAudioRef.current.src = "";
        }
        if (voiceAudioRef.current) {
          voiceAudioRef.current.pause();
          voiceAudioRef.current.src = "";
        }
      } catch (e) {
        // Ignore audio cleanup errors
      }

      // Reset step index to 0 to restart from beginning
      setStepIndex(0);

      // Reload the page with reset parameter AND force onboarding mode
      // This ensures user restarts onboarding even if they already have a podcast
      const url = new URL(window.location.href);
      url.searchParams.set("reset", "1");
      url.searchParams.set("onboarding", "1"); // Force onboarding mode
      url.searchParams.delete("skip_onboarding"); // Remove any skip flags
      window.location.href = url.toString();
    } catch (error) {
      console.error("[Onboarding] Failed to reset wizard:", error);
      // Fallback: just reload with reset param
      window.location.href = window.location.pathname + "?reset=1";
    }
  }, []);

  const wizardContext = {
    token,
    refreshUser,
    toast,
    path,
    setPath,
    formData,
    setFormData,
    handleStartOver,
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
    introVoiceId,
    setIntroVoiceId,
    outroVoiceId,
    setOutroVoiceId,
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
    generateCoverArt,
    targetPodcastId,
    setTargetPodcastId,
    rssFeedUrl,
    setRssFeedUrl,
    rssStatus,
    refreshRssMetadata,
    showRssWaiting,
    setShowRssWaiting,
    distributionReady,
    setDistributionReady,
    websiteUrl,
    setWebsiteUrl,
    designVibe,
    setDesignVibe,
    colorPreference,
    setColorPreference,
    additionalNotes,
    setAdditionalNotes,
    ensurePodcastExists,
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
                ? "Short and clear works best. Host bio is required (50+ chars) to power your site."
              : step.id === "format"
                ? "This is for your reference."
                : step.id === "coverArt"
                  ? "No artwork yet? You can skip this for now."
                  : step.id === "introOutro"
                    ? "Start with our default scripts or upload your own audio."
                    : step.id === "music"
                      ? 'Background music fades in during intros and fades out during outros. It does not play during your main content segments. All timing and volume can be adjusted later in the Template Editor.'
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
        ? (extraProps = {}) => <Component wizard={wizardContext} stepIndex={index} {...extraProps} />
        : () => null,
      validate:
        step.validate && typeof step.validate === "function"
          ? step.validate
          : step.id === "showDetails"
            ? async () => {
              const bio = (formData.hostBio || "").trim();
              if (!bio || bio.length < 50) {
                toast({
                  variant: "destructive",
                  title: "Host bio required",
                  description: "Add at least 50 characters about yourself to continue.",
                });
                return false;
              }
              return true;
            }
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

  // Custom back handler that switches back to choosePath when at first import step
  const handleBack = useCallback(() => {
    // If we're at the first step of import flow (rss step), go back to choosePath
    if (path === "import" && stepIndex === 0 && stepId === "rss") {
      const choosePathIndex = newFlowSteps.findIndex((s) => s.id === "choosePath");
      if (choosePathIndex >= 0) {
        setPath("new");
        setStepIndex(choosePathIndex);
        return;
      }
    }
    // Otherwise, normal back navigation
    if (stepIndex > 0) {
      setStepIndex(stepIndex - 1);
    }
  }, [path, stepIndex, stepId, newFlowSteps]);

  return {
    steps,
    stepIndex,
    setStepIndex,
    handleFinish,
    handleExitDiscard,
    handleBack,
    handleStartOver,
    nextDisabled,
    hideBack: importJumpedToStep6 && stepId === "introOutro",
    showExitDiscard: hasExistingPodcast,
    hasExistingPodcast,
    greetingName: firstName?.trim() || "",
    prefs: { largeText, setLargeText, highContrast, setHighContrast },
    path, // Expose path so OnboardingWrapper can detect import flow
  };
}
