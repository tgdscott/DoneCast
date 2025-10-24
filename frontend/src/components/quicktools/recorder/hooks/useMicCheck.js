import { useState, useRef, useCallback } from 'react';
import { playBeep } from '../utils/audioUtils';
import { analyzeMicCheckLevels } from '../utils/audioAnalysis';

/**
 * Hook for managing mic check orchestration with intelligent analysis
 * @param {Object} params - Hook parameters
 * @param {Object} params.audioGraph - Audio graph controls (audioCtxRef, gainNodeRef, inputGain, updateGain, buildAudioGraph, stopAudioGraph)
 * @param {Object} params.deviceSelection - Device selection controls (selectedDeviceId, devices, ensurePermissionAndDevices)
 * @param {Function} params.startStream - Function to start media stream
 * @param {Function} params.stopStream - Function to stop media stream
 * @param {Function} params.onError - Error callback
 * @returns {Object} Mic check state and controls
 */
export const useMicCheck = ({
  audioGraph,
  deviceSelection,
  startStream,
  stopStream,
  onError
}) => {
  const [isMicChecking, setIsMicChecking] = useState(false);
  const [micCheckCountdown, setMicCheckCountdown] = useState(0);
  const [micCheckPlayback, setMicCheckPlayback] = useState(false);
  const [micCheckCompleted, setMicCheckCompleted] = useState(false);
  const [micCheckAnalysis, setMicCheckAnalysis] = useState(null);
  
  const micCheckTimerRef = useRef(null);
  const micCheckAudioRef = useRef(null);
  // CRITICAL: Use the peakLevelsRef from audioGraph (shared ref), not a local one
  const peakLevelsRef = audioGraph.peakLevelsRef;

  /**
   * Run mic check with countdown, recording, playback, and analysis
   */
  const handleMicCheck = useCallback(async () => {
    if (isMicChecking) return;
    setIsMicChecking(true);
    setMicCheckPlayback(false);
    setMicCheckAnalysis(null); // Clear previous analysis
    
    try {
      // Clean up any existing audio graph before starting
      audioGraph.stopAudioGraph();
      stopStream();
      
      // Ensure we can see devices; if permission was revoked mid-session, prompt again
      if (!deviceSelection.devices || deviceSelection.devices.length === 0) {
        try {
          await deviceSelection.ensurePermissionAndDevices();
        } catch {}
      }
      
      // 3-2-1 countdown with beeps BEFORE starting mic check
      for (let i = 3; i > 0; i--) {
        setMicCheckCountdown(i);
        playBeep(800, 150); // Beep sound
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      
      const s = await startStream(deviceSelection.selectedDeviceId);
      
      // Small delay to let audio graph initialize
      await new Promise(resolve => setTimeout(resolve, 100));
      
      // Reset peak tracking for this mic check
      peakLevelsRef.current = [];
      
      // Start recording FIRST, then do countdown
      const dest = audioGraph.audioCtxRef.current?.createMediaStreamDestination?.();
      if (dest && audioGraph.gainNodeRef.current) {
        // Connect gain node to destination for recording (it's already connected to analyser for meter)
        audioGraph.gainNodeRef.current.connect(dest);
        const rec = new MediaRecorder(dest.stream);
        const chunks = [];
        
        rec.ondataavailable = (e) => {
          if (e.data?.size) chunks.push(e.data);
        };
        rec.start();
        
        // Countdown from 5 to 0 during recording (5 seconds total)
        for (let i = 5; i > 0; i--) {
          setMicCheckCountdown(-i); // Negative numbers indicate recording countdown
          await new Promise(resolve => setTimeout(resolve, 1000));
        }
        setMicCheckCountdown(0); // Recording complete
        
        // Stop recording after countdown finishes
        try {
          rec.stop();
        } catch {}
        
        // Wait for the recording to be fully processed
        const recordedChunks = await new Promise((resolve) => {
          rec.onstop = () => resolve(chunks);
          // Fallback timeout in case onstop doesn't fire
          setTimeout(() => resolve(chunks), 500);
        });
        
        // Playback the full recording
        setMicCheckPlayback(true);
        const blob = new Blob(recordedChunks, { type: 'audio/webm' });
        const url = URL.createObjectURL(blob);
        const a = new Audio(url);
        micCheckAudioRef.current = a;
        
        // Wait for playback to complete
        await new Promise((resolve) => {
          a.onended = () => {
            try {
              URL.revokeObjectURL(url);
            } catch {}
            resolve();
          };
          a.onerror = () => {
            try {
              URL.revokeObjectURL(url);
            } catch {}
            resolve();
          };
          a.play().catch(() => resolve());
        });
        
        // Analyze the recorded levels
        console.log(`[MicCheck] Collected ${peakLevelsRef.current.length} peak level samples`);
        
        if (peakLevelsRef.current.length > 0) {
          const analysis = analyzeMicCheckLevels(peakLevelsRef.current, audioGraph.inputGain);
          console.log('[MicCheck] Analysis result:', analysis);
          setMicCheckAnalysis(analysis);
          
          // Auto-adjust gain if suggested
          if (analysis.suggestedGain !== audioGraph.inputGain && !analysis.requireRedo) {
            audioGraph.updateGain(analysis.suggestedGain);
          }
          
          // If redo required, don't mark as completed
          if (!analysis.requireRedo) {
            console.log('[MicCheck] Mic check PASSED - marking as completed');
            setMicCheckCompleted(true);
          } else {
            console.log('[MicCheck] Mic check FAILED - requireRedo is true');
          }
        } else {
          // No data collected - this is a FAILURE, not success!
          console.log('[MicCheck] CRITICAL: No peak levels collected - mic check FAILED');
          setMicCheckAnalysis({
            status: 'silent',
            message: '🔇 No audio detected',
            suggestion: 'No audio was recorded during the mic check.\n\n• Check that your microphone is plugged in\n• Make sure the microphone isn\'t muted in Windows\n• Try a different microphone\n• Speak during the mic check countdown',
            requireRedo: true,
            suggestedGain: audioGraph.inputGain,
            stats: { avg: 0, max: 0, min: 0 }
          });
          // Do NOT mark as completed - force user to retry
        }
      }
      
      audioGraph.stopAudioGraph();
      s.getTracks().forEach((t) => t.stop());
    } catch (e) {
      console.error('[MicCheck] Error:', e);
      const name = e?.name || '';
      if (name === 'NotAllowedError' || name === 'SecurityError' || name === 'PermissionDeniedError') {
        onError?.('Microphone permission is blocked. Allow access in your browser and try again.');
      } else if (name === 'NotFoundError' || name === 'OverconstrainedError') {
        onError?.('Could not start mic check for the selected device. Try another microphone or unplug/replug it.');
      } else {
        onError?.('Could not start mic check.');
      }
    } finally {
      setIsMicChecking(false);
      setMicCheckCountdown(0);
      setMicCheckPlayback(false);
      micCheckAudioRef.current = null;
    }
  }, [isMicChecking, audioGraph, deviceSelection, startStream, stopStream, onError]);

  /**
   * Clear analysis results and continue
   */
  const clearAnalysis = useCallback(() => {
    setMicCheckAnalysis(null);
  }, []);

  /**
   * Reset mic check state
   */
  const resetMicCheck = useCallback(() => {
    setMicCheckCompleted(false);
    setMicCheckAnalysis(null);
    setMicCheckCountdown(0);
    setMicCheckPlayback(false);
    peakLevelsRef.current = [];
  }, []);

  /**
   * Mark mic check as completed (for session restoration)
   */
  const markMicCheckCompleted = useCallback(() => {
    setMicCheckCompleted(true);
    setMicCheckAnalysis(null);
  }, []);

  return {
    // State
    isMicChecking,
    micCheckCountdown,
    micCheckPlayback,
    micCheckCompleted,
    micCheckAnalysis,
    // Refs
    peakLevelsRef,
    // Functions
    handleMicCheck,
    clearAnalysis,
    resetMicCheck,
    markMicCheckCompleted,
  };
};
