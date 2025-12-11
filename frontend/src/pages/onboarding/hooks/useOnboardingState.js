
import { useState, useRef, useEffect, useMemo } from "react";
import { NO_MUSIC_OPTION } from "@/components/onboarding/OnboardingWizard.jsx";
import {
    useOnboardingPersistence,
    getStoredStepIndex,
    getStoredFormData,
    getStoredPodcastId,
    getStoredWebsiteUrl
} from "./useOnboardingPersistence";

export const useOnboardingState = (user) => {
    const { saveStep, saveForm, savePodcastId, saveWebsiteUrl } = useOnboardingPersistence();

    // -- Initialization Helpers --
    const initialStepData = useMemo(() => {
        if (!user?.email) return { value: 0, restored: false };
        const stored = getStoredStepIndex(user.email);
        return { value: stored, restored: true };
    }, [user?.email]);

    const [fromManager] = useState(() => {
        try {
            return new URLSearchParams(window.location.search).get("from") === "manager";
        } catch {
            return false;
        }
    });

    // -- Core State --
    const [stepIndex, setStepIndex] = useState(initialStepData.value);
    const restoredStepRef = useRef(initialStepData.restored);
    const lastUserEmailRef = useRef(user?.email);

    // User change reset logic
    useEffect(() => {
        const previousEmail = lastUserEmailRef.current;
        if (user?.email && previousEmail && previousEmail !== user.email) {
            // User changed - clear old user's step (handled in persistence, but we reset local state here)
            // Actually persistence hook has clean function, but here we just reset state
            setStepIndex(0);
        }
        if (user?.email !== previousEmail) {
            restoredStepRef.current = false;
        }
        lastUserEmailRef.current = user?.email;
    }, [user?.email]);

    // Restore step index on mount/user change
    useEffect(() => {
        if (!user?.email || restoredStepRef.current) return;
        const storedIndex = getStoredStepIndex(user.email);
        restoredStepRef.current = true;
        setStepIndex((current) => (storedIndex !== current ? storedIndex : current));
    }, [user?.email]);

    // Persist step index
    const stepSaveTimer = useRef(null);
    useEffect(() => {
        if (stepSaveTimer.current) clearTimeout(stepSaveTimer.current);
        stepSaveTimer.current = setTimeout(() => {
            saveStep(user?.email, stepIndex);
        }, 350);
        return () => {
            if (stepSaveTimer.current) clearTimeout(stepSaveTimer.current);
        };
    }, [stepIndex, user?.email, saveStep]);

    // -- Form Data State --
    const [formData, setFormData] = useState(() => getStoredFormData(user?.email));

    // Persist form data
    useEffect(() => {
        const timer = setTimeout(() => {
            saveForm(user?.email, formData);
        }, 500);
        return () => clearTimeout(timer);
    }, [formData, user?.email, saveForm]);

    const handleChange = (event) => {
        const { id, value, files } = event.target;
        setFormData((prev) => ({ ...prev, [id]: files ? files[0] : value }));
    };

    // -- General Fields --
    const [path, setPath] = useState("new");
    const [saving, setSaving] = useState(false);

    // -- Podcast & Website State --
    const [targetPodcastId, setTargetPodcastId] = useState(() => getStoredPodcastId(user?.email));
    useEffect(() => savePodcastId(user?.email, targetPodcastId), [targetPodcastId, user?.email, savePodcastId]);

    const [websiteUrl, setWebsiteUrl] = useState(() => getStoredWebsiteUrl(user?.email));
    useEffect(() => saveWebsiteUrl(user?.email, websiteUrl), [websiteUrl, user?.email, saveWebsiteUrl]);

    // -- Feature State --
    // Audio/Music
    const [musicAssets, setMusicAssets] = useState([NO_MUSIC_OPTION]);
    const [musicLoading, setMusicLoading] = useState(false);
    const [musicChoice, setMusicChoice] = useState("none");
    const [musicPreviewing, setMusicPreviewing] = useState(null);
    const audioRef = useRef(null);

    // Intro/Outro
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
    const [ioAudioRef] = useState(() => ({ current: null })); // Using state for ref stability/mocking if needed, but useRef is fine
    const ioAudioRefActual = useRef(null); // Actually let's stick to useRef pattern
    const [introPreviewing, setIntroPreviewing] = useState(false);
    const [outroPreviewing, setOutroPreviewing] = useState(false);
    const [needsTtsReview, setNeedsTtsReview] = useState(false);
    const [ttsGeneratedIntro, setTtsGeneratedIntro] = useState(null);
    const [ttsGeneratedOutro, setTtsGeneratedOutro] = useState(null);
    const [renameIntro, setRenameIntro] = useState("");
    const [renameOutro, setRenameOutro] = useState("");

    // Voices
    const [voices, setVoices] = useState([]);
    const [voicesLoading, setVoicesLoading] = useState(false);
    const [voicesError, setVoicesError] = useState("");
    const [selectedVoiceId, setSelectedVoiceId] = useState("default");
    const [introVoiceId, setIntroVoiceId] = useState("default");
    const [outroVoiceId, setOutroVoiceId] = useState("default");
    const voiceAudioRef = useRef(null);
    const [voicePreviewing, setVoicePreviewing] = useState(false);

    // Design
    const [designVibe, setDesignVibe] = useState("Clean & Minimal");
    const [colorPreference, setColorPreference] = useState("");
    const [additionalNotes, setAdditionalNotes] = useState("");

    // Publish Plan
    const [freqUnit, setFreqUnit] = useState("week");
    const [freqCount, setFreqCount] = useState(1);
    const [cadenceError, setCadenceError] = useState("");
    const [selectedWeekdays, setSelectedWeekdays] = useState([]);
    const [selectedDates, setSelectedDates] = useState([]);
    const [notSureSchedule, setNotSureSchedule] = useState(false);

    // User Profile
    const [firstName, setFirstName] = useState("");
    const [lastName, setLastName] = useState("");
    const [nameError, setNameError] = useState("");

    // Import Flow
    const [formatKey, setFormatKey] = useState("solo");
    const [rssUrl, setRssUrl] = useState("");
    const [importResult, setImportResult] = useState(null);
    const [resumeAfterImport, setResumeAfterImport] = useState(false);
    const [importLoading, setImportLoading] = useState(false);
    const [showSkipNotice, setShowSkipNotice] = useState(false);
    const [importJumpedToStep6, setImportJumpedToStep6] = useState(false);

    // RSS Status
    const [rssFeedUrl, setRssFeedUrl] = useState("");
    const [rssStatus, setRssStatus] = useState({ state: "idle", lastChecked: 0, error: null });
    const [showRssWaiting, setShowRssWaiting] = useState(false);
    const [distributionReady, setDistributionReady] = useState(false);

    // Cover Art
    const [skipCoverNow, setSkipCoverNow] = useState(false);
    const coverArtInputRef = useRef(null);
    const coverCropperRef = useRef(null);
    const [coverCrop, setCoverCrop] = useState(null);
    const [coverMode, setCoverMode] = useState("crop");

    // Misc
    const [firstTimeUser, setFirstTimeUser] = useState(false);
    const [hasExistingPodcast, setHasExistingPodcast] = useState(false);

    return {
        fromManager,
        stepIndex, setStepIndex,
        formData, setFormData, handleChange,
        path, setPath,
        saving, setSaving,
        targetPodcastId, setTargetPodcastId,
        websiteUrl, setWebsiteUrl,

        // Music
        musicAssets, setMusicAssets,
        musicLoading, setMusicLoading,
        musicChoice, setMusicChoice,
        musicPreviewing, setMusicPreviewing,
        audioRef,

        // Intro/Outro
        introMode, setIntroMode,
        outroMode, setOutroMode,
        introScript, setIntroScript,
        outroScript, setOutroScript,
        introFile, setIntroFile,
        outroFile, setOutroFile,
        introAsset, setIntroAsset,
        outroAsset, setOutroAsset,
        introOptions, setIntroOptions,
        outroOptions, setOutroOptions,
        selectedIntroId, setSelectedIntroId,
        selectedOutroId, setSelectedOutroId,
        ioAudioRef: ioAudioRefActual,
        introPreviewing, setIntroPreviewing,
        outroPreviewing, setOutroPreviewing,
        needsTtsReview, setNeedsTtsReview,
        ttsGeneratedIntro, setTtsGeneratedIntro,
        ttsGeneratedOutro, setTtsGeneratedOutro,
        renameIntro, setRenameIntro,
        renameOutro, setRenameOutro,

        // Voices
        voices, setVoices,
        voicesLoading, setVoicesLoading,
        voicesError, setVoicesError,
        selectedVoiceId, setSelectedVoiceId,
        introVoiceId, setIntroVoiceId,
        outroVoiceId, setOutroVoiceId,
        voiceAudioRef,
        voicePreviewing, setVoicePreviewing,

        // Design
        designVibe, setDesignVibe,
        colorPreference, setColorPreference,
        additionalNotes, setAdditionalNotes,

        // Publish Plan
        freqUnit, setFreqUnit,
        freqCount, setFreqCount,
        cadenceError, setCadenceError,
        selectedWeekdays, setSelectedWeekdays,
        selectedDates, setSelectedDates,
        notSureSchedule, setNotSureSchedule,

        // User Profile
        firstName, setFirstName,
        lastName, setLastName,
        nameError, setNameError,

        // Import Flow
        formatKey, setFormatKey,
        rssUrl, setRssUrl,
        importResult, setImportResult,
        resumeAfterImport, setResumeAfterImport,
        importLoading, setImportLoading,
        showSkipNotice, setShowSkipNotice,
        importJumpedToStep6, setImportJumpedToStep6,

        // RSS Status
        rssFeedUrl, setRssFeedUrl,
        rssStatus, setRssStatus,
        showRssWaiting, setShowRssWaiting,
        distributionReady, setDistributionReady,

        // Cover Art
        skipCoverNow, setSkipCoverNow,
        coverArtInputRef,
        coverCropperRef,
        coverCrop, setCoverCrop,
        coverMode, setCoverMode,

        // Misc
        firstTimeUser, setFirstTimeUser,
        hasExistingPodcast, setHasExistingPodcast
    };
};
