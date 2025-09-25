import React, { useMemo } from 'react';

/**
 * EpisodeStructureSummary
 * Read-only visualization of the planned episode segments (intro, main, outros, ads).
 * Expects an array of segments with shape: { id, label, start, end, type }
 */
export default function EpisodeStructureSummary({ segments, totalSeconds }) {
  const duration = Math.max(1, totalSeconds || 1);
  const ordered = Array.isArray(segments) ? [...segments].sort((a,b)=>a.start-b.start) : [];

  const pretty = (s) => {
    const m = Math.floor(s/60); const r = Math.round(s % 60);
    return `${m}:${r.toString().padStart(2,'0')}`;
  };

  const color = (t) => {
    switch(t){
      case 'intro': return 'bg-indigo-500';
      case 'outro': return 'bg-slate-500';
      case 'ad': return 'bg-amber-500';
      case 'main': return 'bg-blue-500';
      default: return 'bg-gray-400';
    }
  };

  const totalLabel = useMemo(()=> pretty(duration), [duration]);

  return (
    <div className="rounded-lg border bg-white shadow-sm p-5">
      <h3 className="text-sm font-semibold mb-3 text-slate-700">Episode Structure</h3>
      {ordered.length === 0 && (
        <p className="text-xs text-slate-500">No segments configured.</p>
      )}
      {ordered.length > 0 && (
        <>
          <div className="w-full h-4 rounded overflow-hidden flex ring-1 ring-slate-200 mb-2">
            {ordered.map(seg => {
              const len = Math.max(0, (seg.end - seg.start));
              const pct = (len / duration) * 100;
              return (
                <div key={seg.id} style={{ width: pct + '%' }} className={`relative group ${color(seg.type)}`}>
                  <span className="absolute inset-0 flex items-center justify-center text-[10px] font-medium text-white opacity-0 group-hover:opacity-100 transition-opacity px-1 truncate">
                    {seg.label || seg.type}
                  </span>
                </div>
              );
            })}
          </div>
          <div className="flex justify-between text-[10px] font-mono text-slate-500 mb-3">
            <span>0:00</span>
            <span>{totalLabel}</span>
          </div>
          <ul className="space-y-1 max-h-44 overflow-auto pr-1">
            {ordered.map(seg => {
              const len = Math.max(0, seg.end - seg.start);
              const pct = ((len / duration) * 100).toFixed(1);
              return (
                <li key={seg.id} className="flex items-center justify-between text-[11px] bg-slate-50/70 hover:bg-slate-100 rounded px-2 py-1 border border-slate-200">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className={`inline-block h-2 w-2 rounded-sm ${color(seg.type)}`} />
                    <span className="font-medium truncate max-w-[110px]" title={seg.label || seg.type}>{seg.label || seg.type}</span>
                    <span className="text-slate-400">({seg.type})</span>
                  </div>
                  <div className="flex items-center gap-3 text-[10px] font-mono text-slate-600">
                    <span>{pretty(seg.start)} - {pretty(seg.end)}</span>
                    <span className="text-slate-400">{pretty(len)} / {pct}%</span>
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="mt-2 text-[10px] text-slate-400">Hover bar to see labels. Adjust segments back in Step 2.</p>
        </>
      )}
    </div>
  );
}
