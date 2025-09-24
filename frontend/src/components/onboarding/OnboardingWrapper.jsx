import React, { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import {
  Info,
  HelpCircle,
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
} from "lucide-react";
import ComfortControls from "./ComfortControls.jsx";

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

export default function OnboardingWrapper({ steps, index, setIndex, onComplete, prefs, greetingName, nextDisabled = false, hideNext = false, hideBack = false, showExitDiscard = false, onExitDiscard }) {
  const step = steps[index];
  const total = steps.length;
  const pct = Math.round(((index + 1) / total) * 100);
  const isLast = index === total - 1;
  const contentRef = useRef(null);
  const headingRef = useRef(null);

  const AUTOSAVE_IDLE_MS = 15000; // milliseconds of inactivity before showing the saved cue
  const AUTOSAVE_DISPLAY_MS = 2000; // how long the saved cue remains visible

  // Debounced autosave cue
  const [savedVisible, setSavedVisible] = useState(false);
  const [liveMsg, setLiveMsg] = useState("");
  const saveTimer = useRef(null);
  const hideTimer = useRef(null);

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
    if (index > 0) setIndex(index - 1);
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
      spreaker: Globe,
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
            <h1 className="text-xl md:text-2xl font-semibold">
              New Podcast Setup
            </h1>
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
      <main className="container mx-auto px-4 py-8 grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Step content (2 cols) */}
        <section className="md:col-span-2 space-y-6">
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
                disabled={index === 0}
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

        {/* Right rail (1 col) */}
        <aside className="space-y-4">
          <Card>
            <CardHeader className="flex flex-row items-center gap-2 pb-2">
              <Info className="h-5 w-5 text-primary" />
              <CardTitle className="text-base">Helpful tip</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">
                {step?.tip || "Short and sweet: you can change this later in Settings."}
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="flex flex-row items-center gap-2 pb-2">
              <HelpCircle className="h-5 w-5 text-primary" />
              <CardTitle className="text-base">Need a hand?</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground mb-3">
                We're here to help. Browse quick guides or reach out.
              </p>
              <div className="flex gap-2">
                <Button variant="outline" className="rounded-[var(--radius)] h-11 min-h-[44px] px-5" asChild>
                  <a href="/help" target="_blank" rel="noreferrer">Guides</a>
                </Button>
                <Button className="rounded-[var(--radius)] h-11 min-h-[44px] px-5 text-white" asChild>
                  <a href="mailto:support@example.com">Contact</a>
                </Button>
              </div>
            </CardContent>
          </Card>
        </aside>
      </main>
    </div>
  );
}

export { OnboardingWrapper };
