import React, { useState, useEffect } from 'react';
import { Loader2 } from 'lucide-react';

const WARMUP_MESSAGES = [
  "Warming the engine up",
  "Letting the cat out of the bag",
  "Doing vocal warm-ups",
  "Stirring the pot",
  "Cranking up the volume",
  "Preparing the stage",
  "Tuning the instruments",
  "Rolling out the red carpet",
  "Firing up the engines",
  "Getting the band together",
  "Waking up the servers",
  "Brewing some coffee",
  "Stretching our legs",
  "Checking the mic",
  "Adjusting the spotlight",
  "Warming up the vocals",
  "Loading the magic",
  "Spinning up something special",
  "Rustling up some bytes",
  "Preparing for takeoff",
];

export function WarmupLoader({ isVisible }) {
  const [currentMessage, setCurrentMessage] = useState(WARMUP_MESSAGES[0]);

  useEffect(() => {
    if (!isVisible) {
      setCurrentMessage(WARMUP_MESSAGES[0]);
      return;
    }

    // Select a random message every 2.5 seconds
    const interval = setInterval(() => {
      const randomIndex = Math.floor(Math.random() * WARMUP_MESSAGES.length);
      setCurrentMessage(WARMUP_MESSAGES[randomIndex]);
    }, 2500);

    return () => clearInterval(interval);
  }, [isVisible]);

  if (!isVisible) return null;

  return (
    <div 
      className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/50 backdrop-blur-sm"
      style={{ zIndex: 9999 }}
    >
      <div className="bg-white dark:bg-slate-900 rounded-lg shadow-2xl p-8 max-w-sm w-full mx-4 border border-slate-200 dark:border-slate-700">
        <div className="flex flex-col items-center justify-center space-y-4">
          <img
            src="/assets/branding/favicon.png"
            alt="DoneCast icon"
            className="h-10 w-10 animate-pulse"
            aria-hidden="true"
            loading="eager"
          />
          <div className="text-center space-y-2">
            <p className="text-sm font-medium text-slate-900 dark:text-slate-100 animate-pulse">
              {currentMessage}
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-400">
              This usually takes just a moment...
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

