import { useEffect, useRef, useState, useMemo, forwardRef, useImperativeHandle } from 'react';
import WaveSurfer from 'wavesurfer.js';
import Regions from 'wavesurfer.js/plugins/regions';
import Timeline from 'wavesurfer.js/plugins/timeline';

// Props:
// - audioUrl: string (required)
// - initialCuts: [{start_ms,end_ms}]
// - onCutsChange: (cuts) => void
// - height?: number
// - zoomWindows?: number[] in seconds
const WaveformEditor = ({ audioUrl, initialCuts = [], onCutsChange, height = 120, zoomWindows = [15, 30, 60, 120], onDuration }, ref) => {
  const containerRef = useRef(null);
  const wsRef = useRef(null);
  const regionsRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [durationMs, setDurationMs] = useState(null);
  const [activeZoom, setActiveZoom] = useState(60);
  const [selectedRegionId, setSelectedRegionId] = useState(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [timeInput, setTimeInput] = useState('0:00');

  // Build wavesurfer
  useEffect(() => {
    if (!containerRef.current || !audioUrl) return;
    const regions = Regions.create();
    const timeline = Timeline.create({
      height: 18,
      style: { color: '#6b7280', fontSize: '10px' },
      formatTimeCallback: (sec) => {
        if (!isFinite(sec)) return '0:00';
        const s = Math.max(0, Math.floor(sec));
        const m = Math.floor(s / 60);
        const r = s % 60;
        return `${m}:${String(r).padStart(2,'0')}`;
      },
    });
    const ws = WaveSurfer.create({
      container: containerRef.current,
      url: audioUrl,
      height,
      waveColor: '#68a0ff',
      progressColor: '#1e40af',
      cursorColor: '#111827',
      normalize: true,
      plugins: [regions, timeline],
    });
    wsRef.current = ws;
    regionsRef.current = regions;

    const onReady = () => {
      setReady(true);
  const durMs = Math.round(ws.getDuration() * 1000);
  setDurationMs(durMs);
  try { onDuration?.(durMs); } catch {}
      // seed existing regions
      if (Array.isArray(initialCuts)) {
        for (const c of initialCuts) {
          const start = Math.max(0, (c.start_ms || 0) / 1000);
          const end = Math.max(start + 0.02, (c.end_ms || 0) / 1000);
          regions.addRegion({ start, end, color: 'rgba(239,68,68,0.25)' });
        }
      }
      // Apply initial zoom
      applyZoomWindow(activeZoom);
    };
    const onError = (e) => { console.warn('WaveSurfer error', e); };
  const onRegionUpdate = (r) => { setSelectedRegionId(r?.id || null); emitCuts(); };
  const onRegionCreated = (r) => { setSelectedRegionId(r?.id || null); emitCuts(); };
  const onRegionRemoved = () => { setSelectedRegionId(null); emitCuts(); };
    const onRegionClicked = (r) => { setSelectedRegionId(r?.id || null); };
    const onTimeUpdate = (t) => {
      setCurrentTime(t);
      setTimeInput(formatTime(t));
    };

  ws.on('ready', onReady);
    ws.on('error', onError);
  ws.on('timeupdate', onTimeUpdate);
    regions.on('region-updated', onRegionUpdate);
    regions.on('region-created', onRegionCreated);
    regions.on('region-removed', onRegionRemoved);
  regions.on('region-clicked', onRegionClicked);

    return () => {
      try { regions.unAll(); } catch {}
      try { ws.destroy(); } catch {}
      wsRef.current = null;
      regionsRef.current = null;
      setReady(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [audioUrl]);

  const getAllRegions = () => {
    const regions = regionsRef.current;
    if (!regions) return [];
    if (typeof regions.getRegions === 'function') return regions.getRegions();
    return Object.values(regions.list || {});
  };

  const emitCuts = () => {
    if (!regionsRef.current) return;
    const regs = getAllRegions();
    const cuts = regs
      .map(r => ({ start_ms: Math.round(r.start * 1000), end_ms: Math.round(r.end * 1000) }))
      .filter(c => c.end_ms > c.start_ms + 20)
      .sort((a,b)=> a.start_ms - b.start_ms);
    onCutsChange?.(cuts);
  };

  useImperativeHandle(ref, () => ({
    getCuts: () => {
      const regs = getAllRegions();
      return regs
        .map(r => ({ start_ms: Math.round(r.start * 1000), end_ms: Math.round(r.end * 1000) }))
        .filter(c => c.end_ms > c.start_ms + 20)
        .sort((a,b)=> a.start_ms - b.start_ms);
    }
  }), []);

  // Keyboard delete on focused container
  useEffect(() => {
    const onKey = (e) => {
      if (e.key !== 'Delete') return;
      const regs = regionsRef.current; if (!regs) return;
      // remove the last created region as a simple heuristic
      const ids = Object.keys(regs.list || {});
      const lastId = ids[ids.length - 1];
      if (lastId) { regs.removeRegion(lastId); emitCuts(); }
    };
    const el = containerRef.current;
    if (!el) return;
    el.tabIndex = 0; // make focusable
    el.addEventListener('keydown', onKey);
    return () => { try { el.removeEventListener('keydown', onKey); } catch {} };
  }, []);

  const addSelection = () => {
    const ws = wsRef.current; const regions = regionsRef.current;
    if (!ws || !regions) return;
    const cur = ws.getCurrentTime();
    const dur = ws.getDuration();
    const start = cur;
    const end = Math.min(dur, cur + 2);
    regions.addRegion({ start, end, color: 'rgba(239,68,68,0.25)' });
  };

  // Removed per user request (numeric remove is sufficient)

  const applyZoomWindow = (seconds) => {
    const ws = wsRef.current;
    if (!ws) return;
    setActiveZoom(seconds);
    try {
      // Use pxPerSec API in v7: bigger = more zoom
      const containerWidth = containerRef.current?.clientWidth || 800;
      const pxPerSec = Math.max(20, Math.round(containerWidth / seconds));
      ws.zoom(pxPerSec);
    } catch {}
  };

  const deleteAll = () => {
    const regions = regionsRef.current; if (!regions) return;
    try {
  const regs = getAllRegions();
  for (const r of regs) { try { r.remove(); } catch {} }
    } catch {}
    emitCuts();
  };

  const formatTime = (t) => {
    if (!isFinite(t)) return '0:00:00';
    const total = Math.max(0, Math.floor(t));
    const hh = Math.floor(total / 3600);
    const rem = total % 3600;
    const mm = Math.floor(rem / 60);
    const ss = rem % 60;
    return `${hh}:${String(mm).padStart(2,'0')}:${String(ss).padStart(2,'0')}`;
  };

  const parseTime = (str) => {
    if (!str) return 0;
    const trimmed = String(str).trim();
    if (/^\d+(?:\.\d+)?$/.test(trimmed)) return parseFloat(trimmed); // seconds
    // hh:mm:ss(.ms) or mm:ss(.ms)
    let m = /^(\d+):(\d{2}):(\d{2})(?:\.(\d{1,3}))?$/.exec(trimmed);
    if (m) {
      const hh = parseInt(m[1],10);
      const mm = parseInt(m[2],10);
      const ss = parseInt(m[3],10);
      const ms = m[4] ? parseInt(m[4].padEnd(3,'0'),10) : 0;
      return hh*3600 + mm*60 + ss + (ms/1000);
    }
    m = /^(\d+):(\d{2})(?:\.(\d{1,3}))?$/.exec(trimmed);
    if (m) {
      const mm = parseInt(m[1],10);
      const ss = parseInt(m[2],10);
      const ms = m[3] ? parseInt(m[3].padEnd(3,'0'),10) : 0;
      return mm*60 + ss + (ms/1000);
    }
    return 0;
  };

  const jumpToTime = () => {
    const ws = wsRef.current; if (!ws) return;
    const t = parseTime(timeInput);
    const clamped = Math.max(0, Math.min(ws.getDuration() || 0, t));
    try { ws.setTime(clamped); } catch {}
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <button className="text-xs px-2 py-1 border rounded" onClick={()=>wsRef.current?.playPause()}>{wsRef.current?.isPlaying() ? 'Pause' : 'Play'}</button>
  <button className="text-xs px-2 py-1 border rounded" onClick={addSelection}>+ Cut Selection</button>
  <button className="text-xs px-2 py-1 border rounded" onClick={deleteAll}>Clear all cuts</button>
        <div className="ml-2 text-xs text-gray-600">Zoom:</div>
        {zoomWindows.map(z => (
          <button key={z} className={`text-xs px-2 py-1 border rounded ${activeZoom===z?'bg-gray-800 text-white':''}`} onClick={()=>applyZoomWindow(z)}>{z}s</button>
        ))}
        <div className="ml-auto flex items-center gap-1 text-xs text-gray-700">
          <span>Time:</span>
          <input
            className="w-20 border rounded px-1 py-[2px] text-xs"
            value={timeInput}
            onChange={e=>setTimeInput(e.target.value)}
            onBlur={jumpToTime}
            onKeyDown={(e)=>{ if(e.key==='Enter'){ e.preventDefault(); jumpToTime(); } }}
            title="hh:mm:ss, mm:ss, or seconds"
          />
          <span className="ml-2 text-gray-500">{ready ? (durationMs ? `${Math.round(durationMs/1000)}s` : '') : 'Loading…'}</span>
        </div>
      </div>
      <div ref={containerRef} className="w-full select-none" />
      <div className="text-[11px] text-gray-500">Tip: Drag edges to adjust a region. Click to select, Delete key to remove.</div>
    </div>
  );
};

export default forwardRef(WaveformEditor);
