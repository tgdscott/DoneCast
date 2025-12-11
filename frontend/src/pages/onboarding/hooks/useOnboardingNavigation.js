
import { useMemo, useRef, useCallback } from "react";
import { makeApi } from "@/lib/apiClient";

export const useOnboardingNavigation = ({
    token,
    refreshUser,
    state,
    toast,
    fromManager
}) => {
    const {
        path, stepIndex, setStepIndex,
        firstName, lastName, setNameError,
        showSkipNotice, freqUnit,
        handleChange
    } = state;

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
        setNameError,
        freqUnit, // used in dependency of original code, likely for re-render triggers?
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

    const stepId = wizardSteps[stepIndex]?.id;

    // Indices helpers
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

    // Navigation handlers would go here if we extract validation logic completely.
    // For now, validation is stuck inside step definitions (name validation).
    // Ideally, `handleNext` calls `step.validate()`.

    return {
        wizardSteps,
        stepId,
        introOutroIndex,
        publishPlanIndex,
        distributionRequiredIndex
    };
};
