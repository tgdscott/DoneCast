import React from 'react';
import { Button } from "@/components/ui/button";
import { Loader2 } from "lucide-react";

/**
 * Full-screen mic check overlay - SIMPLIFIED
 * Shows countdown, then results screen
 * @param {Object} props - Component props
 * @param {boolean} props.isVisible - Whether the overlay is visible
 * @param {number} props.countdown - Countdown value (positive for pre-check, negative for recording)
 * @param {boolean} props.isPlayback - Whether playback is happening
 * @param {Object} props.analysis - Analysis results
 * @param {Function} props.onContinue - Continue callback
 * @param {Function} props.onRetry - Retry callback
 */
export const MicCheckOverlay = ({
  isVisible,
  countdown,
  isPlayback,
  analysis,
  onContinue,
  onRetry
}) => {
  if (!isVisible) return null;

  return (
    <div className="min-h-[600px] flex flex-col items-center justify-center space-y-8">
      {/* RESULTS SCREEN - Show after mic check completes */}
      {analysis && (
        <div className={`rounded-2xl p-12 text-center max-w-2xl mx-auto shadow-2xl ${
          analysis.status === 'good' 
            ? 'bg-green-50 border-4 border-green-500' 
            : analysis.requireRedo 
            ? 'bg-red-50 border-4 border-red-500' 
            : 'bg-yellow-50 border-4 border-yellow-500'
        }`}>
          {/* Big checkmark or warning with animation */}
          <div className={`text-9xl mb-6 ${
            analysis.status === 'good' ? 'text-green-600 animate-bounce' : 'text-red-600'
          }`}>
            {analysis.status === 'good' ? '✓' : '⚠️'}
          </div>
          
          {/* Main message - BIGGER and BOLDER for success */}
          <h2 className={`font-bold mb-6 ${
            analysis.status === 'good' 
              ? 'text-5xl text-green-900' 
              : 'text-4xl text-red-900'
          }`}>
            {analysis.status === 'good' ? '🎉 Perfect! You\'re Ready to Record!' : 'Mic Check Failed'}
          </h2>
          
          {/* Detailed message */}
          <p className={`text-2xl mb-6 font-semibold ${
            analysis.status === 'good' ? 'text-green-800' : 'text-red-800'
          }`}>
            {analysis.message}
          </p>
          
          {/* Suggestion with better formatting */}
          {analysis.suggestion && (
            <div className={`text-base mb-8 max-w-lg mx-auto p-6 rounded-lg ${
              analysis.status === 'good' 
                ? 'bg-white text-gray-700 border border-green-200' 
                : 'bg-white text-gray-800 border border-red-200'
            }`}>
              <p className="whitespace-pre-line text-left leading-relaxed">
                {analysis.suggestion}
              </p>
            </div>
          )}
          
          {/* Action button - VERY prominent */}
          {analysis.requireRedo ? (
            <div className="space-y-4">
              <Button 
                onClick={onRetry}
                size="lg"
                className="text-xl px-12 py-8 bg-red-600 hover:bg-red-700 text-white font-bold shadow-lg"
              >
                🔄 Try Mic Check Again
              </Button>
              <p className="text-sm text-gray-600">
                Don't worry! Mic checks often need a couple tries to get the settings right.
              </p>
            </div>
          ) : (
            <Button 
              onClick={onContinue}
              size="lg"
              className="text-2xl px-16 py-10 bg-green-600 hover:bg-green-700 text-white font-bold shadow-2xl animate-pulse"
            >
              ▶️ Start Recording Now!
            </Button>
          )}
        </div>
      )}
      
      {/* COUNTDOWN/RECORDING UI - Show before results */}
      {!analysis && (
        <div className="bg-blue-50 border-4 border-blue-400 rounded-2xl p-12 text-center max-w-2xl mx-auto shadow-lg" aria-live="polite">
          {countdown > 0 ? (
            // Pre-countdown (3-2-1 before recording starts)
            <>
              <div className="text-3xl font-bold text-blue-900 mb-4">
                Get Ready...
              </div>
              <div className="text-8xl font-mono font-bold text-blue-600 mb-6">
                {countdown}
              </div>
              <p className="text-xl text-blue-700">
                Starting mic check in {countdown}...<br />
                <span className="text-base">🔊 Listen for the beeps!</span>
              </p>
            </>
          ) : countdown < 0 ? (
            // Recording countdown (5-4-3-2-1 during recording)
            <>
              <div className="text-3xl font-bold text-red-900 mb-4">
                🎤 Recording
              </div>
              <div className="text-8xl font-mono font-bold text-red-600 mb-6">
                {Math.abs(countdown)}
              </div>
              <p className="text-xl text-red-700">
                Speak normally at your regular volume
              </p>
            </>
          ) : isPlayback ? (
            // Playback phase
            <>
              <div className="text-3xl font-bold text-green-900 mb-4">
                🔊 Playing Back
              </div>
              <Loader2 className="w-16 h-16 animate-spin mx-auto text-green-600 my-8" />
              <p className="text-xl text-green-700">
                Listen to verify your audio
              </p>
            </>
          ) : (
            // Default recording state
            <>
              <div className="text-3xl font-bold text-blue-900 mb-4">
                🎤 Recording
              </div>
              <div className="text-6xl font-mono font-bold text-red-600 mb-6 animate-pulse">
                ● REC
              </div>
              <p className="text-xl text-blue-700">
                Speak normally at your regular volume
              </p>
            </>
          )}
        </div>
      )}
    </div>
  );
};
