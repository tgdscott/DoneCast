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
    nextDisabled,
    hideNext,
    hideBack,
    showExitDiscard,
    greetingName,
    prefs,
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
    />
  );
}
