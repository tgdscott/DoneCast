import React, { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";

const LINE_SEQUENCE = [
  {
    id: "hero",
    type: "hero",
    delay: 0,
  },
  {
    id: "line-a",
    copy: "We make podcasting easy for everyone",
    delay: 900,
  },
  {
    id: "line-b",
    copy: "Whether you're an experienced pro or someone just starting out, we've got you",
    delay: 1900,
  },
  {
    id: "line-c",
    copy: "You won't need fancy tech to record with us",
    delay: 2900,
  },
  {
    id: "line-d",
    copy: "Of course it's better if you do, but if you have a desktop microphone, a webcam, or even just a phone, that will work.",
    delay: 3900,
  },
  {
    id: "line-e",
    copy: "To get you going, we have a one-time step process. Click continue to begin.",
    delay: 5000,
  },
  {
    id: "cta",
    type: "cta",
    delay: 6100,
  },
];

export default function WelcomeStep({ onContinue, prefs }) {
  const [visible, setVisible] = useState({});

  useEffect(() => {
    const timers = LINE_SEQUENCE.map((line) =>
      setTimeout(() => {
        setVisible((prev) => ({ ...prev, [line.id]: true }));
      }, line.delay)
    );
    return () => {
      timers.forEach(clearTimeout);
    };
  }, []);

  const textClass = useMemo(() => (prefs?.largeText ? "text-lg md:text-xl" : "text-base md:text-lg"), [prefs?.largeText]);

  return (
    <div className="relative z-10 mx-auto flex w-full max-w-4xl flex-col items-center gap-6 text-center">
      <div
        className={`transition-all duration-700 ease-out ${
          visible.hero ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
        }`}
      >
        <img
          src="/assets/branding/logo-horizontal.png"
          alt="DoneCast"
          className="mx-auto h-14 w-auto select-none"
          draggable={false}
        />
        <p className="mt-6 text-3xl font-semibold tracking-tight text-balance md:text-4xl">
          Welcome to DoneCast
        </p>
      </div>

      {LINE_SEQUENCE.filter((line) => line.copy).map((line) => (
        <p
          key={line.id}
          className={`max-w-3xl text-balance ${textClass} transition-all duration-700 ease-out ${
            visible[line.id] ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
          }`}
        >
          {line.copy}
        </p>
      ))}

      <div
        className={`transition-all duration-700 ease-out ${
          visible.cta ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
        }`}
      >
        <Button
          size="lg"
          onClick={onContinue}
          disabled={!visible.cta}
          className="min-w-[200px] rounded-full px-8 text-base font-semibold"
        >
          Continue
        </Button>
      </div>
    </div>
  );
}
