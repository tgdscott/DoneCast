import React, { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  Info,
  ChevronLeft,
  ChevronRight,
  CheckCircle2,
  HandHeart,
  FileText,
  Image as ImageIcon,
  Globe,
  Sparkles,
  User,
  GitBranch,
  Repeat,
  CalendarDays,
  Lightbulb,
  ClipboardList,
  HelpCircle,
  LogOut,
  RotateCcw,
} from "lucide-react";
import ComfortControls from "./ComfortControls.jsx";
import OnboardingSidebar from "./OnboardingSidebar.jsx";
import { useAuth } from "@/AuthContext.jsx";

/**
 * @typedef {{ id: string; title: string; description?: string; render: () => React.ReactNode; validate?: () => boolean | Promise<boolean>; tip?: string; }} OnboardingStep
 * @typedef {{ largeText: boolean; highContrast: boolean }} OnboardingPrefs
 * @param {{ steps: OnboardingStep[]; index: number; setIndex: (n:number)=>void; onComplete?: ()=>void; prefs: OnboardingPrefs }} props
 */

// Lightweight fade/slide wrapper (≤200ms) with no external deps
function FadeSlide({ children, keyProp }) {
  const [show, setShow] = useState(true);
  useMemo(() => { setShow(false); const t = setTimeout(() => setShow(true), 0); return () => clearTimeout(t); }, [keyProp]);
  return (
    <div
      key={keyProp}
      className={
        "transition-all duration-200 ease-out will-change-transform " +
        (show ? "opacity-100 translate-y-0" : "opacity-0 translate-y-2")
      }
    >
      {children}
    </div>
  );
}

export default function OnboardingWrapper({ steps, index, setIndex, onComplete, prefs, greetingName, nextDisabled = false, hideNext = false, hideBack = false, showExitDiscard = false, onExitDiscard, hasExistingPodcast = false, onBack, path = "new", handleStartOver }) {
  const { token, user, logout } = useAuth();
  const step = steps[index];
  const total = steps.length;
  const pct = Math.round(((index + 1) / total) * 100);
  const isLast = index === total - 1;
  const contentRef = useRef(null);
  const headingRef = useRef(null);
  const popupWindowRef = useRef(null);
  
  // Check if we're at the first import step (rss step) - allow back button even at index 0
  const isFirstImportStep = path === "import" && step?.id === "rss" && index === 0;

  // Open Mike's popup window for assistance
  const openMikePopup = () => {
    // Check if popup is already open
    if (popupWindowRef.current && !popupWindowRef.current.closed) {
      popupWindowRef.current.focus();
      return;
    }
    
    // Open new popup window
    const width = 600;
    const height = 700;
    const left = Math.max(0, (window.screen.width - width) / 2);
    const top = Math.max(0, (window.screen.height - height) / 2);
    
    const popup = window.open(
      '/mike',
      'MikeCzech',
      `width=${width},height=${height},left=${left},top=${top},resizable=yes,scrollbars=no,status=no,toolbar=no,menubar=no,location=no,alwaysRaised=yes`
    );
    
    if (popup) {
      popupWindowRef.current = popup;
      
      // Listen for popup ready message
      const handlePopupReady = (event) => {
        if (event.origin !== window.location.origin) return;
        if (event.data?.type === 'mike-popup-ready' && popup && !popup.closed) {
          // Send initialization data to popup
          popup.postMessage({
            type: 'mike-popup-init',
            token,
            user,
          }, window.location.origin);
        }
      };
      
      window.addEventListener('message', handlePopupReady);
      
      // Clean up when popup closes
      const checkClosed = setInterval(() => {
        if (popup.closed) {
          clearInterval(checkClosed);
          popupWindowRef.current = null;
          window.removeEventListener('message', handlePopupReady);
        }
      }, 500);
    } else {
      // Popup blocked - could show a toast or message
      console.warn('Popup blocked - please allow popups to use Mike');
    }
  };

  const AUTOSAVE_IDLE_MS = 15000; // milliseconds of inactivity before showing the saved cue
  const AUTOSAVE_DISPLAY_MS = 2000; // how long the saved cue remains visible

  // Debounced autosave cue
  const [savedVisible, setSavedVisible] = useState(false);
  const [liveMsg, setLiveMsg] = useState("");
  const saveTimer = useRef(null);
  const hideTimer = useRef(null);

  // Track completed steps (steps that have been successfully moved past)
  // A step is completed if we've moved past it (not including current step)
  const completedSteps = useMemo(() => {
    const completed = new Set();
    // All steps before the current one are considered completed
    for (let i = 0; i < index; i++) {
      completed.add(i);
    }
    return completed;
  }, [index]);

  // Map step icons for sidebar
  const stepIconMap = useMemo(() => {
    const map = {
      welcome: HandHeart,
      showDetails: FileText,
      format: FileText,
      coverArt: ImageIcon,
      introOutro: Sparkles,
      music: Sparkles,
      elevenlabs: Sparkles,
      publishDay: CheckCircle2,
      finish: CheckCircle2,
      rss: Globe,
      analyze: FileText,
      assets: ImageIcon,
      yourName: User,
      choosePath: GitBranch,
      publishCadence: Repeat,
      publishSchedule: CalendarDays,
      ttsReview: Sparkles,
      skipNotice: Info,
      confirm: CheckCircle2,
      importing: Repeat,
      importSuccess: CheckCircle2,
    };
    return map;
  }, []);

  // Prepare steps with icons for sidebar
  const stepsWithIcons = useMemo(() => {
    return steps.map((step) => ({
      ...step,
      icon: stepIconMap[step.id] || null,
    }));
  }, [steps, stepIconMap]);

  function handleSidebarStepClick(stepIndex) {
    // Only allow navigation to completed steps (including current)
    if (completedSteps.has(stepIndex)) {
      setIndex(stepIndex);
    }
  }

  const baseText = prefs.largeText ? "text-[18px] md:text-[18px]" : "text-[15px] md:text-[16px]";
  const hc = prefs.highContrast ? "bg-white text-black [&_.btn]:!bg-black [&_.btn]:!text-white [&_.btn-outline]:!border-black [&_.btn-outline]:!text-black [&_a]:underline" : "";

  async function handleNext() {
    if (step?.validate) {
      try {
        const ok = await step.validate();
        if (!ok) return;
      } catch (_) {
        return;
      }
    }
    if (isLast) {
      onComplete?.();
    } else {
      setIndex(index + 1);
    }
  }

  function handleBack() {
    // Use custom back handler if provided, otherwise use default
    if (onBack) {
      onBack();
    } else {
      if (index > 0) setIndex(index - 1);
    }
  }

  // Map step ids to small icons
  const StepIcon = useMemo(() => {
    const map = {
      welcome: HandHeart,
      showDetails: FileText,
      format: FileText,
      coverArt: ImageIcon,
      introOutro: Sparkles,
      music: Sparkles,
      elevenlabs: Sparkles,
      publishDay: CheckCircle2,
      finish: CheckCircle2,
      rss: Globe,
      analyze: FileText,
      assets: ImageIcon,
      // Added explicit icons for steps lacking one
      yourName: User,
      choosePath: GitBranch,
      publishCadence: Repeat,
      publishSchedule: CalendarDays,
      ttsReview: Sparkles,
    };
    return step?.id && map[step.id] ? map[step.id] : null;
  }, [step?.id]);

  const guideScripts = useMemo(() => ({
    welcome: {
      headline: "What to expect",
      summary: "You'll answer a few quick questions so we can pre-fill your show settings and connect the tools you already use.",
      steps: [
        "Have your show name, a short description, and any cover art handy.",
        "If you're importing, keep the RSS URL nearby.",
      ],
    },
    yourName: {
      headline: "Why we ask",
      summary: "We personalize reminders and drafts using your first name only.",
      steps: [
        "Use the name you'd like to appear in emails and episode copy.",
      ],
    },
    showDetails: {
      headline: "Describe your show",
      summary: "A clear name and description help us draft intros, titles, and marketing copy that sound like you.",
      steps: [
        "Aim for a 4+ character name that's easy to search.",
        "Mention your audience and value proposition in the description.",
        "You can tweak these later inside Show Settings.",
      ],
    },
    format: {
      headline: "Pick a starting format",
      summary: "Formats determine which segments we auto-generate (intro, interview cues, outro, etc.).",
      steps: [
        "Choose the option that best matches your recurring structure—it's easy to adjust per episode.",
        "Need something custom? Select the closest match and refine the template in the next step.",
      ],
    },
    introOutro: {
      headline: "Plan your openings",
      summary: "Decide whether you want AI narration, an uploaded intro, or both.",
      steps: [
        "Upload any must-use clips so we can stitch them into every episode.",
        "Prefer AI voiceovers? You'll preview voices in the ElevenLabs step.",
      ],
    },
    music: {
      headline: "Choose background music",
      summary: "Select background music that will fade in during intros and fade out during outros. This won't play during your main content segments.",
      steps: [
        "By default, music only plays during intro and outro segments—not during your main content.",
        "You can adjust timing, volume, and which segments use music later in the Template Editor.",
        "Pick a track from the library or choose 'No Music' if you prefer to skip this for now.",
      ],
    },
    elevenlabs: {
      headline: "Preview voices",
      summary: "Test a few AI voices and lock in the tone you want for narration or ad reads.",
      steps: [
        "Click preview to hear an example line.",
        "Use the notes field to tell us about pronunciation or pacing preferences.",
      ],
    },
    publishCadence: {
      headline: "Set your cadence",
      summary: "We use this to schedule reminders and auto-build episode timelines.",
      steps: [
        "Weekly cadence works best for most shows. Bi-weekly means every 2 weeks.",
        "Not sure yet? Pick your best guess—you can change it any time.",
      ],
    },
    website: {
      headline: "Create your website",
      summary: "We're generating a simple website for your podcast so people can find and listen to your show.",
      steps: [
        "Your website will be created automatically with your podcast name, description, and cover art.",
        "You can customize it later in Website Builder, but for now you'll have a URL to share.",
      ],
    },
    distributionRequired: {
      headline: "Distribute to Apple & Spotify",
      summary: "These are the two largest podcasting platforms. We strongly recommend submitting now.",
      steps: [
        "Apple Podcasts is required for Siri and the iOS Podcasts app.",
        "Spotify reaches Android, desktop, and smart speaker listeners.",
        "You can skip and do this later, but submitting now helps listeners find your podcast sooner.",
      ],
    },
    distributionOptional: {
      headline: "Other platforms",
      summary: "Additional platforms help you reach more listeners.",
      steps: [
        "Add these platforms with one click if you want broader distribution.",
        "You can always add or remove platforms later in Settings → Distribution.",
      ],
    },
    publishSchedule: {
      headline: "Pick preferred days",
      summary: "Scheduling helps us plan drafts, reminders, and auto-publishing windows.",
      steps: [
        "Select the days you usually publish.",
        "If you mark “I’m not sure,” we’ll pause scheduling nudges for now.",
      ],
    },
    rss: {
      headline: "Importing via RSS",
      summary: "Drop your RSS feed URL and we'll pull recent episodes to learn your style.",
      steps: [
        "You can find the RSS link in Spotify for Podcasters, Apple Podcasts Connect, or your current host dashboard.",
        "We'll never publish to that feed—this is read-only for setup.",
      ],
    },
    confirm: {
      headline: "Review & finish",
      summary: "Double-check the summary and continue—we'll start generating your workspace immediately.",
      steps: [
        "You can revisit any step later from Settings.",
      ],
    },
  }), []);

  const activeGuide = step?.id ? guideScripts[step.id] : null;
  const StepGlyph = activeGuide?.icon || StepIcon;

  // Keyboard handling: Enter advances; Backspace won't navigate; Esc does nothing
  useEffect(() => {
    const handler = (e) => {
      const tgt = e.target;
      const tag = (tgt?.tagName || "").toLowerCase();
      const isEditable = tgt?.isContentEditable || tag === "input" || tag === "textarea" || tag === "select";

      if (e.key === "Backspace") {
        // Prevent browser back when not actively editing text
        if (!isEditable) {
          e.preventDefault();
          e.stopPropagation();
        }
        return;
      }

      if (e.key === "Escape") {
        // Never discard progress
        e.preventDefault();
        e.stopPropagation();
        return;
      }

      if (e.key === "Enter" && !e.shiftKey && !e.ctrlKey && !e.metaKey && !e.altKey) {
        // Do not capture Enter for multiline inputs
        if (tag !== "textarea") {
          e.preventDefault();
          e.stopPropagation();
          // Advance if valid
          handleNext();
        }
      }
    };
    window.addEventListener("keydown", handler, { capture: true });
    return () => window.removeEventListener("keydown", handler, { capture: true });
  }, [handleNext]);

  // Move focus to step heading on step change
  useEffect(() => {
    const h = headingRef.current;
    if (h) {
      // Defer to allow DOM update
      const t = setTimeout(() => {
        try { h.focus(); } catch {}
      }, 0);
      return () => clearTimeout(t);
    }
  }, [step?.id]);

  // Input listener for autosave cue
  useEffect(() => {
    const el = contentRef.current;
    if (!el) return;
    const onInput = () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
      if (hideTimer.current) clearTimeout(hideTimer.current);
      setSavedVisible(false);
      // Idle window before showing the saved cue
      saveTimer.current = setTimeout(() => {
        setSavedVisible(true);
        setLiveMsg("Saved");
        // Briefly show, then hide and clear live region text
        hideTimer.current = setTimeout(() => {
          setSavedVisible(false);
          setLiveMsg("");
        }, AUTOSAVE_DISPLAY_MS);
      }, AUTOSAVE_IDLE_MS);
    };
    el.addEventListener("input", onInput, true);
    return () => {
      el.removeEventListener("input", onInput, true);
      if (saveTimer.current) clearTimeout(saveTimer.current);
      if (hideTimer.current) clearTimeout(hideTimer.current);
    };
  }, [step?.id]);

  return (
    <div className={`min-h-screen bg-background ${baseText} ${hc}`}>
      {/* Top header without percent complete per spec */}
      <header className="border-b bg-card/40 backdrop-blur-sm">
        <div className="container mx-auto px-4 py-6">
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <h1 className="text-xl md:text-2xl font-semibold">
                New Podcast Setup
              </h1>
              <Button
                variant="ghost"
                size="sm"
                onClick={logout}
                className="text-muted-foreground hover:text-foreground"
                aria-label="Logout"
              >
                <LogOut className="h-4 w-4 mr-2" />
                <span className="hidden sm:inline">Logout</span>
              </Button>
            </div>
            <div className="flex items-center justify-end gap-3">
              <ComfortControls
                largeText={prefs.largeText}
                setLargeText={prefs.setLargeText ?? (()=>{})}
                highContrast={prefs.highContrast}
                setHighContrast={prefs.setHighContrast ?? (()=>{})}
              />
            </div>
          </div>
        </div>
      </header>

      {/* Main content grid */}
      <main className="container mx-auto px-4 py-8 grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Sidebar navigation (left) */}
        <div className="lg:col-span-3">
          <OnboardingSidebar
            steps={stepsWithIcons}
            currentIndex={index}
            completedSteps={completedSteps}
            onStepClick={handleSidebarStepClick}
          />
        </div>

        {/* Step content (middle) */}
        <section className="lg:col-span-6 space-y-6">
          <div className="space-y-2">
            {/* Optional greeting on Step 2 when name is known */}
            {greetingName && (index === 1) && (
              <div className="text-lg md:text-xl font-semibold" aria-live="polite">
                {`Hi ${greetingName}.  It's great to meet you.`}
              </div>
            )}
            {/* Live region announcing step transitions and transient Saved cue */}
            <div
              className="sr-only"
              role="status"
              aria-live="polite"
              aria-atomic="true"
            >
              {`Step ${index + 1}: ${step?.title || ''}${liveMsg ? ` - ${liveMsg}` : ''}`}
            </div>
            {/* Screen-reader progress list with aria-current */}
            <nav className="sr-only" aria-label="Step Progress">
              <ol>
                {steps.map((s, i) => (
                  <li key={s.id} aria-current={i === index ? "step" : undefined}>{`Step ${i + 1}: ${s.title}`}</li>
                ))}
              </ol>
            </nav>
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                {StepIcon ? (
                  <StepIcon className="h-5 w-5 text-muted-foreground" aria-hidden="true" />
                ) : (
                  <span className="inline-block h-5 w-5" aria-hidden="true" />
                )}
                <h2
                  ref={headingRef}
                  tabIndex={-1}
                  className="text-lg md:text-xl font-medium flex items-center gap-2"
                >
                  {`Step ${index + 1}: ${step?.title || ''}`}
                  {/* Visible Saved cue (aria-hidden) */}
                  {savedVisible && (
                    <span className="inline-flex items-center gap-1 text-xs text-muted-foreground" aria-hidden="true">
                      <CheckCircle2 className="h-3.5 w-3.5" /> Saved
                    </span>
                  )}
                </h2>
              </div>
            </div>
            {step?.description && (
              <p className="text-muted-foreground">{step.description}</p>
            )}
          </div>

          <FadeSlide keyProp={step?.id}>
            <div ref={contentRef} className="rounded-[var(--radius)] border bg-card p-4 md:p-6">
              {step?.render()}
            </div>
          </FadeSlide>

          <div className="flex items-center justify-between pt-2">
            {!hideBack && (
              <Button
                variant="outline"
                onClick={handleBack}
                disabled={index === 0 && !isFirstImportStep}
                className="rounded-[var(--radius)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring h-11 min-h-[44px] px-5 btn-outline text-foreground"
              >
                <ChevronLeft className="mr-2 h-4 w-4" /> Back
              </Button>
            )}

            <div className="flex items-center gap-2">
              {isLast && !hideNext && (
                <span className="text-xs text-muted-foreground hidden md:inline-flex items-center gap-1">
                  <CheckCircle2 className="h-4 w-4" /> You're all set after this
                </span>
              )}
              {!hideNext && (
                <Button
                  onClick={handleNext}
                  disabled={!!nextDisabled}
                  className="rounded-[var(--radius)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring h-11 min-h-[44px] px-5 btn text-white disabled:opacity-60"
                >
                  {isLast ? (
                    <>
                      Finish <ChevronRight className="ml-2 h-4 w-4" />
                    </>
                  ) : (
                    <>
                      Continue <ChevronRight className="ml-2 h-4 w-4" />
                    </>
                  )}
                </Button>
              )}
            </div>
          </div>

          {/* Exit & Discard at bottom-right near the right rail */}
          {showExitDiscard && (
            <div className="flex justify-end mt-3">
              <button
                type="button"
                onClick={() => onExitDiscard?.()}
                className="inline-flex items-center rounded-full border border-red-600 text-red-600 px-3 py-1 text-xs bg-white hover:bg-red-50"
              >
                Exit and Discard
              </button>
            </div>
          )}
        </section>

        {/* Right rail (help cards) */}
        <aside className="lg:col-span-3 space-y-4">
          {activeGuide && (
            <Card data-tour-id="onboarding-dynamic-guide">
              <CardHeader className="flex flex-row items-center gap-2 pb-2">
                {(StepGlyph || Lightbulb) && (
                  <div className="rounded-full bg-primary/10 p-2 text-primary">
                    {StepGlyph ? <StepGlyph className="h-5 w-5" aria-hidden="true" /> : <Lightbulb className="h-5 w-5" aria-hidden="true" />}
                  </div>
                )}
                <CardTitle className="text-base">{activeGuide.headline}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-sm text-muted-foreground">{activeGuide.summary}</p>
                {Array.isArray(activeGuide.steps) && activeGuide.steps.length > 0 && (
                  <ul className="space-y-2 rounded-md border border-dashed border-muted-foreground/40 bg-muted/40 p-3 text-sm">
                    {activeGuide.steps.map((tipLine, idx) => (
                      <li key={idx} className="flex items-start gap-2">
                        <ClipboardList className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" aria-hidden="true" />
                        <span>{tipLine}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader className="flex flex-row items-center gap-2 pb-2">
              <Info className="h-5 w-5 text-primary" />
              <CardTitle className="text-base">Helpful tip</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                {step?.tip || activeGuide?.summary || "Short and sweet: you can change this later in Settings."}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center gap-2 pb-2">
              <HelpCircle className="h-5 w-5 text-primary" />
              <CardTitle className="text-base">Need a hand?</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-col gap-2">
                <Button 
                  className="rounded-[var(--radius)] h-11 min-h-[44px] px-5 text-white w-full" 
                  onClick={openMikePopup}
                >
                  Contact Us
                </Button>
                {hasExistingPodcast && (
                  <Button
                    variant="secondary"
                    className="rounded-[var(--radius)] h-11 min-h-[44px] px-5 w-full"
                    onClick={() => {
                      const ok = window.confirm(
                        "You can skip this for now, but you will either have to complete this later or enter in everything manually to create podcast episodes."
                      );
                      if (ok) {
                        try { localStorage.setItem('ppp.onboarding.completed', '1'); } catch {}
                        try { localStorage.removeItem('ppp.onboarding.step'); } catch {}
                        // Add onboarding=0 so App.jsx gating does not relaunch the wizard when user has 0 podcasts
                        try { window.location.assign('/dashboard?onboarding=0'); } catch {}
                      }
                    }}
                  >
                    Skip for now
                  </Button>
                )}
              </div>
            </CardContent>
          </Card>

          {/* Start Over Button */}
          {handleStartOver && (
            <Card className="border-red-200 bg-red-50/50">
              <CardHeader className="flex flex-row items-center gap-2 pb-2">
                <RotateCcw className="h-5 w-5 text-red-600" />
                <CardTitle className="text-base text-red-900">Start Over</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-red-700 mb-3">
                  Clear all progress and start the wizard from the beginning.
                </p>
                <Button
                  variant="destructive"
                  className="rounded-[var(--radius)] h-11 min-h-[44px] px-5 w-full"
                  onClick={handleStartOver}
                >
                  <RotateCcw className="h-4 w-4 mr-2" />
                  Start Over
                </Button>
              </CardContent>
            </Card>
          )}
        </aside>
      </main>
    </div>
  );
}

export { OnboardingWrapper };
