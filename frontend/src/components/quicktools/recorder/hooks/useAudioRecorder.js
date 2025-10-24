import { useState, useRef, useCallback, useEffect } from 'react';
import { reencodeToWav, pickMimeType, playBeep } from '../utils/audioUtils';

/**
 * Hook for managing audio recording with MediaRecorder
 * @param {Object} params - Hook parameters
 * @param {Function} params.buildAudioGraph - Function to build audio graph with stream
 * @param {Function} params.stopAudioGraph - Function to stop audio graph
 * @param {Function} params.toast - Toast notification function
 * @returns {Object} Recording state and controls
 */
export const useAudioRecorder = ({ buildAudioGraph, stopAudioGraph, toast }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [hasPreview, setHasPreview] = useState(false);
  const [elapsed, setElapsed] = useState(0); // seconds
  const [audioUrl, setAudioUrl] = useState("");
  const [audioBlob, setAudioBlob] = useState(null);
  const [mimeType, setMimeType] = useState("");
  const [isCountingDown, setIsCountingDown] = useState(false);
  const [countdown, setCountdown] = useState(0);

  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const discardOnStopRef = useRef(false);
  const timerRef = useRef(null);
  const isRecordingRef = useRef(false);
  const isPausedRef = useRef(false);
  const countdownTimerRef = useRef(null);
  const wakeLockRef = useRef(null);

  /**
   * Stop and cleanup media stream
   */
  const stopStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => {
        try {
          t.stop();
        } catch {}
      });
      streamRef.current = null;
    }
  }, []);

  /**
   * Start media stream with fallback constraints
   * @param {string} deviceId - Device ID to use
   */
  const startStream = useCallback(async (deviceId) => {
    // Be resilient: some devices reject certain constraints; try a few fallbacks
    const attempts = [];
    const withDev = deviceId ? { exact: deviceId } : undefined;
    attempts.push({ audio: { deviceId: withDev, channelCount: 1, noiseSuppression: { ideal: true }, echoCancellation: { ideal: true } } });
    attempts.push({ audio: { deviceId: withDev, channelCount: 1 } });
    attempts.push({ audio: { deviceId: withDev } });
    attempts.push({ audio: true });

    let lastErr;
    for (const c of attempts) {
      try {
        const s = await navigator.mediaDevices.getUserMedia(c);
        streamRef.current = s;
        buildAudioGraph(s);
        return s;
      } catch (e) {
        lastErr = e;
        // Continue to next fallback
      }
    }
    throw lastErr || new Error('getUserMedia failed');
  }, [buildAudioGraph]);

  /**
   * Start recording
   * @param {string} deviceId - Device ID to use
   * @param {Function} onError - Error callback
   */
  const startRecording = useCallback(async (deviceId, onError) => {
    setAudioUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return "";
    });
    setAudioBlob(null);
    setHasPreview(false);
    setElapsed(0);
    chunksRef.current = [];
    setIsPaused(false);
    isPausedRef.current = false;

    const m = pickMimeType();
    if (!m) {
      onError?.("Recording not supported in this browser.");
      return;
    }
    setMimeType(m);

    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        onError?.("Recording not supported in this browser.");
        return;
      }
      // Start stream with current device
      const s = await startStream(deviceId);

      const rec = new MediaRecorder(s, { mimeType: m });
      chunksRef.current = [];
      let lastChunkAt = 0;
      rec.ondataavailable = (e) => {
        const now = Date.now();
        // Only accept non-empty chunks while the session is active; debounce to avoid quick duplicates
        if (!e?.data || e.data.size === 0) return;
        if (now - lastChunkAt < 50) return; // guard against immediate duplicate events
        lastChunkAt = now;
        chunksRef.current.push(e.data);
      };
      rec.onpause = () => {
        setIsPaused(true);
        isPausedRef.current = true;
      };
      rec.onresume = () => {
        setIsPaused(false);
        isPausedRef.current = false;
      };
      rec.onstop = () => {
        // Allow any final ondataavailable to land before assembling
        Promise.resolve().then(async () => {
          try {
            if (discardOnStopRef.current) {
              // Discard short take
              chunksRef.current = [];
              discardOnStopRef.current = false;
              setHasPreview(false);
              setAudioBlob(null);
              setAudioUrl((u) => {
                if (u) URL.revokeObjectURL(u);
                return "";
              });
              setElapsed(0);
              toast?.({ title: 'Discarded', description: 'Short take discarded (<30s).' });
              return;
            }
            const parts = chunksRef.current || [];
            const rawBlob = new Blob(parts, { type: m });
            // Re-encode to WAV to normalize and remove any duplicated 1s chunk artifacts
            let finalBlob = rawBlob;
            try {
              finalBlob = await reencodeToWav(rawBlob);
              setMimeType("audio/wav");
            } catch (err) {
              // Fallback to original if re-encode fails
              finalBlob = rawBlob;
            }
            setAudioBlob(finalBlob);
            const url = URL.createObjectURL(finalBlob);
            setAudioUrl(url);
            setHasPreview(true);
          } catch {}
        });
      };
      mediaRecorderRef.current = rec;
      rec.start();
      setIsRecording(true);
      isRecordingRef.current = true;
      // Timer
      if (timerRef.current) {
        try {
          clearInterval(timerRef.current);
        } catch {}
      }
      timerRef.current = setInterval(() => {
        if (isRecordingRef.current && !isPausedRef.current) {
          setElapsed((e) => e + 1);
        }
      }, 1000);
      // Try to keep the screen awake during recording (ignore errors)
      try {
        if (navigator.wakeLock?.request) {
          wakeLockRef.current = await navigator.wakeLock.request('screen');
        }
      } catch {}
    } catch (e) {
      console.error('[AudioRecorder] Start recording error:', e);
      const name = e?.name || "";
      if (name === "NotAllowedError" || name === "SecurityError" || name === "PermissionDeniedError") {
        onError?.("Microphone permission denied. Allow access in your browser and try again.");
      } else if (name === "NotFoundError") {
        onError?.("No microphone detected.");
      } else {
        onError?.("Could not access microphone.");
      }
      stopStream();
      stopAudioGraph();
    }
  }, [startStream, buildAudioGraph, stopAudioGraph, toast, stopStream]);

  /**
   * Stop recording
   */
  const stopRecording = useCallback(() => {
    try {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
        mediaRecorderRef.current.stop();
      }
    } catch {}
    setIsRecording(false);
    isRecordingRef.current = false;
    setIsPaused(false);
    isPausedRef.current = false;
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
    stopAudioGraph();
    stopStream();
    // Release wake lock if held
    try {
      if (wakeLockRef.current?.release) {
        wakeLockRef.current.release();
      }
    } catch {}
    wakeLockRef.current = null;
  }, [stopAudioGraph, stopStream]);

  /**
   * Start countdown before recording
   */
  const startCountdown = useCallback((callback) => {
    if (isRecordingRef.current || isCountingDown) return;
    setCountdown(3);
    setIsCountingDown(true);
    playBeep(800, 150); // Initial beep for 3
    if (countdownTimerRef.current) {
      try {
        clearInterval(countdownTimerRef.current);
      } catch {}
    }
    countdownTimerRef.current = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          try {
            clearInterval(countdownTimerRef.current);
          } catch {}
          countdownTimerRef.current = null;
          setIsCountingDown(false);
          callback?.();
          return 0;
        }
        playBeep(800, 150); // Beep for each countdown number
        return c - 1;
      });
    }, 1000);
  }, [isCountingDown]);

  /**
   * Start countdown before resuming
   */
  const startResumeCountdown = useCallback(() => {
    if (!isPausedRef.current || isCountingDown) return;
    setCountdown(3);
    setIsCountingDown(true);
    playBeep(800, 150); // Initial beep for 3
    if (countdownTimerRef.current) {
      try {
        clearInterval(countdownTimerRef.current);
      } catch {}
    }
    countdownTimerRef.current = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          try {
            clearInterval(countdownTimerRef.current);
          } catch {}
          countdownTimerRef.current = null;
          setIsCountingDown(false);
          try {
            mediaRecorderRef.current?.resume?.();
          } catch {}
          return 0;
        }
        playBeep(800, 150); // Beep for each countdown number
        return c - 1;
      });
    }, 1000);
  }, [isCountingDown]);

  /**
   * Cancel countdown
   */
  const cancelCountdown = useCallback(() => {
    try {
      if (countdownTimerRef.current) clearInterval(countdownTimerRef.current);
    } catch {}
    countdownTimerRef.current = null;
    setIsCountingDown(false);
    setCountdown(0);
  }, []);

  /**
   * Handle record/pause/resume toggle
   */
  const handleRecordToggle = useCallback((deviceId, onError) => {
    // Three-state button: Record (initial) -> Pause -> Resume (with 3s countdown)
    if (!isRecordingRef.current) {
      if (isCountingDown) {
        cancelCountdown();
        return;
      }
      startCountdown(() => startRecording(deviceId, onError));
      return;
    }
    // If currently recording and not paused, pause immediately
    if (!isPausedRef.current) {
      try {
        mediaRecorderRef.current?.pause?.();
      } catch {}
      return;
    }
    // If paused, resume with countdown
    startResumeCountdown();
  }, [isCountingDown, cancelCountdown, startCountdown, startRecording, startResumeCountdown]);

  /**
   * Handle stop with discard check for short recordings
   */
  const handleStop = useCallback(() => {
    if (isPausedRef.current) {
      // If less than 30 seconds captured, warn that stopping will discard
      if (elapsed < 30) {
        const ok = window.confirm('You have recorded less than 30 seconds. Stopping now will discard this take. Do you want to stop and discard?');
        if (!ok) return;
        discardOnStopRef.current = true;
      }
      stopRecording();
    }
  }, [elapsed, stopRecording]);

  /**
   * Pause recording immediately
   */
  const pauseRecording = useCallback(() => {
    try {
      mediaRecorderRef.current?.pause?.();
    } catch {}
  }, []);

  /**
   * Reset to initial state
   */
  const reset = useCallback(() => {
    stopRecording();
    setAudioUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return "";
    });
    setAudioBlob(null);
    setHasPreview(false);
    setElapsed(0);
    chunksRef.current = [];
  }, [stopRecording]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cancelCountdown();
      stopRecording();
      if (audioUrl) {
        URL.revokeObjectURL(audioUrl);
      }
    };
  }, [audioUrl, cancelCountdown, stopRecording]);

  return {
    // State
    isRecording,
    isPaused,
    hasPreview,
    elapsed,
    audioUrl,
    audioBlob,
    mimeType,
    isCountingDown,
    countdown,
    // Refs for direct access
    streamRef,
    // Functions
    startRecording,
    stopRecording,
    pauseRecording,
    handleRecordToggle,
    handleStop,
    startCountdown,
    cancelCountdown,
    reset,
  };
};
