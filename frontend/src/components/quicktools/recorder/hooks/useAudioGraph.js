import { useState, useRef, useCallback, useEffect } from 'react';

/**
 * Hook for managing Web Audio API graph (analyser, gain, level metering)
 * @param {Object} options - Configuration options
 * @param {React.RefObject} [options.peakLevelsRef] - Optional ref to track peak levels for analysis
 * @returns {Object} Audio graph state and controls
 */
export const useAudioGraph = ({ peakLevelsRef } = {}) => {
  const [levelPct, setLevelPct] = useState(0); // 0..1
  const [levelColor, setLevelColor] = useState('#ef4444'); // Color based on smoothed zones
  const [inputGain, setInputGain] = useState(() => {
    // Load saved gain from localStorage
    try {
      const saved = localStorage.getItem('ppp_mic_gain');
      if (saved) {
        const parsed = parseFloat(saved);
        if (isFinite(parsed) && parsed >= 0.1 && parsed <= 2.0) {
          return parsed;
        }
      }
    } catch {}
    return 1.0;
  });

  const audioCtxRef = useRef(null);
  const analyserRef = useRef(null);
  const sourceRef = useRef(null);
  const gainNodeRef = useRef(null);
  const rafRef = useRef(null);

  /**
   * Build audio graph: source → gain → analyser
   * @param {MediaStream} stream - Audio stream
   */
  const buildAudioGraph = useCallback((stream) => {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const source = ctx.createMediaStreamSource(stream);
      const gainNode = ctx.createGain();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 2048;
      
      // Connect: source -> gain -> analyser
      source.connect(gainNode);
      gainNode.connect(analyser);
      gainNode.gain.value = inputGain;
      
      audioCtxRef.current = ctx;
      analyserRef.current = analyser;
      sourceRef.current = source;
      gainNodeRef.current = gainNode;

      const data = new Uint8Array(analyser.fftSize);
      let smoothedLevel = 0; // Smoothed level for display
      const smoothingFactor = 0.15; // Lower = smoother (range 0-1)
      let frameCount = 0; // Only update color every N frames
      
      const loop = () => {
        if (!analyserRef.current) {
          return; // Stop if analyser is gone
        }
        
        analyser.getByteTimeDomainData(data);
        
        // Compute simple peak level 0..1
        let peak = 0;
        for (let i = 0; i < data.length; i++) {
          const v = Math.abs(data[i] - 128) / 128; // center at 0
          if (v > peak) peak = v;
        }
        
        // Track raw peak levels during mic check for analysis (every 10th frame to avoid too many samples)
        if (frameCount % 10 === 0 && peakLevelsRef?.current) {
          peakLevelsRef.current.push(peak);
        }
        
        // Smooth but responsive meter movement with exponential averaging
        // Use faster attack (rise) and slower decay (fall) for natural feel
        const attackSpeed = 0.75;  // Rise quickly to peaks (slightly faster for better responsiveness)
        const decaySpeed = 0.20;   // Fall gradually (slower decay for smoother movement)
        
        if (peak > smoothedLevel) {
          // Attack: jump up quickly when audio gets louder
          smoothedLevel = smoothedLevel + (peak - smoothedLevel) * attackSpeed;
        } else {
          // Decay: fall slowly when audio gets quieter
          smoothedLevel = smoothedLevel + (peak - smoothedLevel) * decaySpeed;
        }
        
        // Apply 1.25x multiplier to make levels more visible while keeping under 1.0
        // This helps users see activity better without distorting the meter
        const displayLevel = Math.min(1.0, smoothedLevel * 1.25);
        setLevelPct(displayLevel);
        
        // SIMPLIFIED COLOR: Binary green/gray (NO rainbow mode)
        // Green when audio detected, gray when silent
        const newColor = smoothedLevel > 0.08 ? '#22c55e' : '#374151'; // green-500 : gray-700
        setLevelColor(newColor);
        
        frameCount++;
        
        rafRef.current = requestAnimationFrame(loop);
      };
      
      rafRef.current = requestAnimationFrame(loop);
      console.log('[AudioGraph] Audio graph built successfully');
    } catch (e) {
      console.error('[AudioGraph] Failed to build audio graph:', e);
    }
  }, [inputGain, peakLevelsRef]);

  /**
   * Stop and cleanup audio graph
   */
  const stopAudioGraph = useCallback(() => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (sourceRef.current) {
      try {
        sourceRef.current.disconnect();
      } catch {}
      sourceRef.current = null;
    }
    if (analyserRef.current) {
      analyserRef.current = null;
    }
    if (gainNodeRef.current) {
      try {
        gainNodeRef.current.disconnect();
      } catch {}
      gainNodeRef.current = null;
    }
    if (audioCtxRef.current) {
      try {
        audioCtxRef.current.close();
      } catch {}
      audioCtxRef.current = null;
    }
    setLevelPct(0);
    console.log('[AudioGraph] Audio graph stopped and cleaned up');
  }, []);

  /**
   * Update gain in real-time
   * @param {number} newGain - New gain value (0.1 to 2.0)
   */
  const updateGain = useCallback((newGain) => {
    const clamped = Math.max(0.1, Math.min(2.0, newGain));
    setInputGain(clamped);
    if (gainNodeRef.current) {
      gainNodeRef.current.gain.value = clamped;
    }
    try {
      localStorage.setItem('ppp_mic_gain', String(clamped));
    } catch {}
    console.log('[AudioGraph] Gain updated to:', clamped);
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopAudioGraph();
    };
  }, [stopAudioGraph]);

  return {
    levelPct,
    levelColor,
    inputGain,
    buildAudioGraph,
    stopAudioGraph,
    updateGain,
    // Expose refs for advanced use (like mic check)
    audioCtxRef,
    analyserRef,
    sourceRef,
    gainNodeRef,
    peakLevelsRef, // CRITICAL: Expose the peakLevelsRef so mic check can read from it
  };
};
