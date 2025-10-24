import React from 'react';
import { Button } from "@/components/ui/button";
import { Mic, Square } from "lucide-react";
import { formatTime } from '../utils/audioUtils';

/**
 * Recording control buttons (Record/Pause/Resume, Stop, Mic Check)
 * @param {Object} props - Component props
 * @param {boolean} props.isRecording - Whether currently recording
 * @param {boolean} props.isPaused - Whether recording is paused
 * @param {boolean} props.isCountingDown - Whether countdown is active
 * @param {number} props.countdown - Countdown value
 * @param {number} props.elapsed - Elapsed recording time in seconds
 * @param {Function} props.onRecordToggle - Record/pause/resume callback
 * @param {Function} props.onStop - Stop callback
 * @param {Function} props.onMicCheck - Mic check callback
 * @param {boolean} props.micCheckCompleted - Whether mic check has been completed
 * @param {boolean} props.isMicChecking - Whether mic check is in progress
 * @param {boolean} props.hasPreview - Whether preview is available
 */
export const RecorderControls = ({
  isRecording,
  isPaused,
  isCountingDown,
  countdown,
  elapsed,
  onRecordToggle,
  onStop,
  onMicCheck,
  micCheckCompleted,
  isMicChecking,
  hasPreview = false
}) => {
  return (
    <>
      {/* Help banner - only shown when not recording */}
      {!hasPreview && !isRecording && (
        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 text-sm">
          <div className="flex items-start gap-3">
            <span className="text-2xl">🎙️</span>
            <div className="flex-1">
              <p className="font-medium text-blue-900 mb-2">Quick Start Guide</p>
              <ol className="list-decimal list-inside space-y-1 text-blue-800">
                <li><strong>Click Record</strong> - Green button starts recording after 3-second countdown</li>
                <li><strong>Pause anytime</strong> - Click the button again to pause, click again to resume</li>
                <li><strong>Stop when paused</strong> - Pause first, then click Stop to finish</li>
                <li><strong>Preview & Save</strong> - Listen to your recording, then save to your library</li>
              </ol>
              {micCheckCompleted && (
                <p className="mt-2 text-xs text-blue-700">
                  💡 Hover over any ⓘ icon for detailed help • 
                  <button 
                    onClick={onMicCheck} 
                    className="ml-1 underline hover:text-blue-900"
                  >
                    Run mic check again
                  </button>
                </p>
              )}
            </div>
          </div>
        </div>
      )}
      
      {/* Center controls with circular button */}
      <div className="flex flex-col items-center gap-5">
        <div className="flex items-center gap-4">
          <Button
            onClick={onRecordToggle}
            aria-label={!isRecording ? (isCountingDown ? 'Cancel countdown' : 'Start recording') : (isPaused ? 'Resume recording' : 'Pause recording')}
            className={`rounded-full w-28 h-28 text-lg font-semibold shadow ${!isRecording ? (isCountingDown ? 'bg-amber-600 hover:bg-amber-500' : 'bg-green-600 hover:bg-green-500') : (isPaused ? 'bg-green-600 hover:bg-green-500' : 'bg-amber-600 hover:bg-amber-500')} text-white`}
          >
            {!isRecording ? (
              <span className="flex flex-col items-center leading-tight">
                <Mic className="w-5 h-5 mb-1" />
                <span>{isCountingDown ? `Starting in ${countdown}…` : 'Record'}</span>
              </span>
            ) : (
              <span className="flex flex-col items-center leading-tight">
                {isPaused ? (
                  <>
                    <Mic className="w-5 h-5 mb-1" />
                    <span>{isCountingDown ? `Resuming in ${countdown}…` : 'Resume'}</span>
                  </>
                ) : (
                  <span>Pause</span>
                )}
              </span>
            )}
          </Button>
          <Button 
            variant="outline" 
            disabled={!isPaused || isCountingDown} 
            onClick={onStop} 
            aria-label="Stop recording (available when paused)"
            className="h-10"
          >
            <Square className="w-4 h-4 mr-2" /> Stop
          </Button>
        </div>

        {/* Digital timer */}
        <div className="text-5xl font-mono tracking-wider" aria-live="polite">{formatTime(elapsed)}</div>
      </div>
    </>
  );
};
