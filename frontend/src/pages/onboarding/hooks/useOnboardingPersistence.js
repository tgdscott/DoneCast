
import { useCallback } from "react";

export const STORAGE_KEYS = {
    STEP: (email) => `ppp.onboarding.step.${email}`,
    FORM: (email) => `ppp.onboarding.form.${email}`,
    PID: (email) => `ppp.onboarding.pid.${email}`,
    WEB: (email) => `ppp.onboarding.web.${email}`,
    LEGACY_STEP: "ppp.onboarding.step",
};

export const getStoredStepIndex = (email) => {
    if (!email) return 0;
    try {
        const raw = localStorage.getItem(STORAGE_KEYS.STEP(email));
        const parsed = raw != null ? parseInt(raw, 10) : 0;
        const idx = Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
        if (idx > 0) {
            console.log(`[Onboarding] Restored stepIndex ${idx} for user ${email}`);
        }
        return idx;
    } catch (error) {
        console.warn("[Onboarding] Failed to restore stepIndex:", error);
        return 0;
    }
};

export const getStoredFormData = (email) => {
    const defaults = {
        podcastName: "",
        podcastDescription: "",
        coverArt: null,
        elevenlabsApiKey: "",
        hostBio: "",
    };
    if (!email) return defaults;
    try {
        const saved = localStorage.getItem(STORAGE_KEYS.FORM(email));
        if (saved) {
            const parsed = JSON.parse(saved);
            return { ...defaults, ...parsed, coverArt: null };
        }
    } catch (e) {
        console.warn("[Onboarding] Failed to restore form data", e);
    }
    return defaults;
};

export const getStoredPodcastId = (email) => {
    if (!email) return null;
    try {
        return localStorage.getItem(STORAGE_KEYS.PID(email)) || null;
    } catch {
        return null;
    }
};

export const getStoredWebsiteUrl = (email) => {
    if (!email) return "";
    try {
        return localStorage.getItem(STORAGE_KEYS.WEB(email)) || "";
    } catch {
        return "";
    }
};

export const clearOnboardingState = (email) => {
    try {
        localStorage.removeItem(STORAGE_KEYS.LEGACY_STEP);
        if (email) {
            localStorage.removeItem(STORAGE_KEYS.STEP(email));
            localStorage.removeItem(STORAGE_KEYS.FORM(email));
            localStorage.removeItem(STORAGE_KEYS.PID(email));
            localStorage.removeItem(STORAGE_KEYS.WEB(email));
        }
    } catch (error) {
        console.warn("[Onboarding] Failed to clear stored state", error);
    }
};

export const useOnboardingPersistence = () => {
    // Logic mostly moved to helper functions for cleaner use in initialization
    // But we can expose savers here if we want a hook interface

    const saveStep = useCallback((email, stepIndex) => {
        if (!email) return;
        try {
            localStorage.setItem(STORAGE_KEYS.STEP(email), String(stepIndex));
        } catch (error) {
            console.warn("[Onboarding] Failed to save step", error);
        }
    }, []);

    const saveForm = useCallback((email, formData) => {
        if (!email) return;
        try {
            const toSave = {
                podcastName: formData.podcastName,
                podcastDescription: formData.podcastDescription,
                elevenlabsApiKey: formData.elevenlabsApiKey,
                hostBio: formData.hostBio,
            };
            localStorage.setItem(STORAGE_KEYS.FORM(email), JSON.stringify(toSave));
        } catch (e) {
            console.warn("[Onboarding] Failed to save form", e);
        }
    }, []);

    const savePodcastId = useCallback((email, pid) => {
        if (!email) return;
        if (pid) {
            localStorage.setItem(STORAGE_KEYS.PID(email), pid);
        } else {
            localStorage.removeItem(STORAGE_KEYS.PID(email));
        }
    }, []);

    const saveWebsiteUrl = useCallback((email, url) => {
        if (!email) return;
        if (url) {
            localStorage.setItem(STORAGE_KEYS.WEB(email), url);
        } else {
            localStorage.removeItem(STORAGE_KEYS.WEB(email));
        }
    }, []);

    return {
        saveStep,
        saveForm,
        savePodcastId,
        saveWebsiteUrl,
        clearOnboardingState
    };
};
