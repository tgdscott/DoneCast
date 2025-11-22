import React from "react";
import { useAuth } from "@/AuthContext.jsx";
import OnboardingWrapper from "@/components/onboarding/OnboardingWrapper.jsx";
import { useToast } from "@/hooks/use-toast";
import { useComfort } from "@/ComfortContext.jsx";
import useOnboardingWizard from "./onboarding/hooks/useOnboardingWizard.jsx";

export default function Onboarding() {
  const { token, user, refreshUser } = useAuth();
  const { toast } = useToast();
  const comfort = useComfort();

  const {
    steps,
    stepIndex,
    setStepIndex,
    handleFinish,
    handleExitDiscard,
    handleBack,
    handleStartOver,
    nextDisabled,
    hideNext,
    hideBack,
    showExitDiscard,
    hasExistingPodcast,
    greetingName,
    prefs,
    path,
  } = useOnboardingWizard({ token, user, refreshUser, toast, comfort });

  return (
    <OnboardingWrapper
      steps={steps}
      index={stepIndex}
      setIndex={setStepIndex}
      onComplete={handleFinish}
      prefs={prefs}
      greetingName={greetingName}
      nextDisabled={nextDisabled}
      hideNext={hideNext}
      hideBack={hideBack}
      showExitDiscard={showExitDiscard}
      onExitDiscard={handleExitDiscard}
      hasExistingPodcast={hasExistingPodcast}
      handleStartOver={handleStartOver}
      onBack={handleBack}
      path={path}
    />
  );
}
