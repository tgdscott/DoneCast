import React, { useEffect, useRef, useState } from 'react';
import { WaveSurfer, RegionsPlugin } from '@/vendor/wavesurfer.js';

/**
 * Waveform
 * Props:
 * - src: audio URL
 * - height?: number
 * - start?: number (seconds) optional initial start marker
 * - end?: number (seconds) optional initial end marker
 * - onReady?: (ws) => void
 * - onMarkersChange?: ({start, end})
 * - onCut?: (currentTimeSecRelative: number) => void // called when Cut is pressed with current playhead (relative to snippet)
 * - cutButtonLabel?: string // custom label for the cut button (default: "End of Request")
 */
export default function Waveform({ src, height = 96, start, end, onReady, onMarkersChange, onCut, markerEnd, cutButtonLabel = "End of Request" }) {
  const containerRef = useRef(null);
  const wsRef = useRef(null);
  const regionsRef = useRef(null);
  const [durationSec, setDurationSec] = useState(null);
  const [isPlaying, setIsPlaying] = useState(false);

  useEffect(() => {
    if (!containerRef.current) return;
    
    // Detect if mobile for touch optimizations
    const isMobile = window.innerWidth < 768;
    
    const ws = WaveSurfer.create({
      container: containerRef.current,
      waveColor: '#9CA3AF',
      progressColor: '#1F2937',
      cursorColor: '#111827',
      height,
      normalize: true,
      backend: 'webaudio',
      // Mobile optimizations
      interact: true,
      hideScrollbar: isMobile,
      minPxPerSec: isMobile ? 50 : 100, // Larger waveform segments for easier touch
    });
    const regions = ws.registerPlugin(RegionsPlugin.create());
    wsRef.current = ws;
    regionsRef.current = regions;

    ws.on('ready', () => {
      if (typeof onReady === 'function') onReady(ws);
      try { setDurationSec(ws.getDuration()); } catch {}
      
      // Prevent zoom on double-tap (mobile)
      if (containerRef.current) {
        const preventZoom = (e) => {
          if (e.touches && e.touches.length > 1) {
            e.preventDefault();
          }
        };
        containerRef.current.addEventListener('touchstart', preventZoom, { passive: false });
      }
      
      // initialize region if provided
      if (typeof start === 'number') {
        const s = Math.max(0, start);
        const e = typeof end === 'number' && end > s ? end : s + 0.2;
        regions.clear();
        regions.addRegion({
          id: 'cut',
          start: s,
          end: e,
          color: 'rgba(239, 68, 68, 0.25)', // red with alpha
          drag: true,
          resize: true,
        });
      }
    });

    ws.on('play', () => setIsPlaying(true));
    ws.on('pause', () => setIsPlaying(false));
    ws.on('finish', () => setIsPlaying(false));

    regions.on('region-updated', (region) => {
      if (region.id === 'cut' && typeof onMarkersChange === 'function') {
        onMarkersChange({ start: region.start, end: region.end });
      }
    });
    regions.on('region-created', (region) => {
      if (region.id === 'cut' && typeof onMarkersChange === 'function') {
        onMarkersChange({ start: region.start, end: region.end });
      }
    });
    regions.on('region-removed', (region) => {
      if (region.id === 'cut' && typeof onMarkersChange === 'function') {
        onMarkersChange({ start: undefined, end: undefined });
      }
    });

    try { ws.load(src); } catch {}
    return () => {
      try { ws.destroy(); } catch {}
      wsRef.current = null;
      regionsRef.current = null;
      setDurationSec(null);
      setIsPlaying(false);
    };
  }, [src, height]);

  // reflect external start/end changes after init
  useEffect(() => {
    const regions = regionsRef.current;
    const ws = wsRef.current;
    if (!ws || !regions) return;
    const existing = regions.getRegions().find(r => r.id === 'cut');
    if (typeof start === 'number') {
      const s = Math.max(0, start);
      const e = typeof end === 'number' && end > s ? end : s + 0.2;
      if (existing) {
        existing.setOptions({ start: s, end: e });
      } else {
        regions.addRegion({ id: 'cut', start: s, end: e, color: 'rgba(239, 68, 68, 0.25)', drag: true, resize: true });
      }
    } else if (existing) {
      existing.remove();
    }
  }, [start, end]);

  const handlePlayPause = () => {
    const ws = wsRef.current;
    if (!ws) return;
    try { ws.playPause(); } catch {}
  };

  const handleCut = () => {
    if (typeof onCut !== 'function') return;
    const ws = wsRef.current;
    if (!ws) return;
    let t = 0;
    try { t = ws.getCurrentTime() || 0; } catch {}
    onCut(t);
  };

  return (
    <div className="w-full">
      <div className="relative">
        <div ref={containerRef} />
        {typeof markerEnd === 'number' && durationSec && durationSec > 0 && (
          <div
            style={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              width: '2px',
              backgroundColor: 'rgba(239,68,68,0.9)',
              left: `${Math.max(0, Math.min(1, markerEnd / durationSec)) * 100}%`,
              pointerEvents: 'none',
            }}
          />
        )}
      </div>
      <div className="mt-2 flex items-center gap-2 flex-wrap">
        <button
          type="button"
          onClick={handlePlayPause}
          className="touch-target px-3 py-2 text-sm rounded border bg-white hover:bg-gray-50"
        >
          {isPlaying ? 'Pause' : 'Play'}
        </button>
        {typeof onCut === 'function' && (
          <button
            type="button"
            onClick={handleCut}
            className="touch-target px-3 py-2 text-sm rounded border bg-red-50 text-red-700 hover:bg-red-100"
          >
            {cutButtonLabel}
          </button>
        )}
      </div>
    </div>
  );
}
