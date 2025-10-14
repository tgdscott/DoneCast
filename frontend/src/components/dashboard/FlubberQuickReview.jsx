import React, { useMemo, useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Scissors, X, ChevronLeft } from 'lucide-react';
import Waveform from '@/components/media/Waveform';

export default function FlubberQuickReview({ contexts, open, onConfirm, onCancel }) {
  const [selected, setSelected] = useState(()=>{
    const pre = {};
    (contexts||[]).forEach(c=>{ pre[c.flubber_index] = true; });
    return pre;
  });
  // Simplified UX: per-snippet Cut/Uncut. When Cut, we record startAbs at current playhead; endAbs = computed auto-end.
  const [startIdx, setStartIdx] = useState(null); // last interacted index (for subtle highlight)
  // Per-context marker overrides from waveform interactions: { [flubber_index]: { startAbs?:number, endAbs?:number } }
  const [markerOverrides, setMarkerOverrides] = useState({});
  // Track window expansion per context: { [flubber_index]: seconds_expanded }
  const [windowExpansion, setWindowExpansion] = useState({});
  // Waveform-only player now; no external <audio> refs.

  const chosen = useMemo(()=> (contexts||[]).filter(c=> selected[c.flubber_index]), [contexts, selected]);
  const chosenSorted = useMemo(()=> [...chosen].sort((a,b)=> (a.flubber_time_s||0)-(b.flubber_time_s||0)), [chosen]);

  // The audio snippet file already contains all the context (15s before flubber, 10s after)
  // The snippet plays the entire audio file. We just need to track the time ranges correctly.
  const getSnippetInfo = (ctx) => {
    const snippetStart = ctx.snippet_start_s || 0;  // earliest time in episode that the audio file contains
    const snippetEnd = ctx.snippet_end_s || 0;  // latest time in episode that the audio file contains
    const flubberTime = ctx.flubber_time_s || 0;  // when the flubber occurred in the episode
    
    // Calculate how much "before" context is available in the snippet
    const availableBeforeSeconds = flubberTime - snippetStart;
    
    return { snippetStart, snippetEnd, flubberTime, availableBeforeSeconds };
  };

  if (!open) return null;

  const computeCutsMs = () => {
    // Only include contexts marked Cut; require a startAbs; end falls back to auto end
    return chosenSorted.map(c => {
      const idx = c.flubber_index;
      const override = markerOverrides[idx] || {};
      const sAbs = typeof override.startAbs === 'number'
        ? override.startAbs
        : Math.max(0, (c.flubber_time_s || 0) - 0.75);
      const eAuto = (c.computed_end_s ?? ((c.flubber_end_s || c.flubber_time_s || 0) + 0.2));
      const eAbs = Math.max(sAbs + 0.05, typeof override.endAbs === 'number' ? override.endAbs : eAuto);
      return [Math.round(sAbs*1000), Math.round(eAbs*1000)];
    });
  };

  const canApply = chosenSorted.length >= 1;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <Card className="w-full max-w-3xl max-h-[80vh] overflow-hidden">
        <CardHeader className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">Review Retakes (Flubber)</CardTitle>
            <div className="flex gap-2">
              <Button variant="ghost" size="sm" onClick={onCancel}>Close</Button>
              <Button size="sm" disabled={!canApply} onClick={()=> onConfirm(computeCutsMs())}>
                <Scissors className="w-4 h-4 mr-1"/>Apply Selected
              </Button>
            </div>
          </div>
          <div className="flex items-center gap-4 text-xs text-gray-700">
            <div>Red line marks flubber. Review audio after the marker. Click "Expand Context" to review more before the mistake.</div>
            <span className="ml-auto">Marked: {chosenSorted.length}</span>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 overflow-y-auto">
          {(!contexts || contexts.length===0) && (
            <div className="text-xs text-gray-600">No flubber instances detected.</div>
          )}
          {(contexts||[]).map(ctx => {
            const isStart = startIdx === ctx.flubber_index;
            const { snippetStart, snippetEnd, flubberTime, availableBeforeSeconds } = getSnippetInfo(ctx);
            const expansion = windowExpansion[ctx.flubber_index] || 0;
            
            // The waveform shows the entire snippet audio file
            // The expansion doesn't change the audio, it just reminds the user how much context to review
            const canExpandMore = expansion < availableBeforeSeconds;
            
            return (
            <div key={ctx.flubber_index} className={`border rounded p-2 flex flex-col gap-2 bg-white ${isStart? 'border-green-500': ''}`}>
              <div className="flex items-center justify-between">
                <div className="text-[11px] font-mono">
                  t={Number(flubberTime).toFixed(2)}s | 
                  Snippet: [{Number(snippetStart).toFixed(1)}s – {Number(snippetEnd).toFixed(1)}s]
                  {expansion > 0 && <span className="ml-2 text-blue-600">(reviewing {expansion}s before)</span>}
                </div>
                <div className="flex items-center gap-2">
                  {!selected[ctx.flubber_index] ? (
                    <Button
                      size="xs"
                      onClick={()=>{
                        // Mark this flubber for cutting with default start position
                        const startAbs = ctx.flubber_time_s || 0;
                        const endAbs = (ctx.computed_end_s ?? ((ctx.flubber_end_s || (ctx.flubber_time_s || 0)) + 0.2));
                        setMarkerOverrides(prev => ({ ...prev, [ctx.flubber_index]: { startAbs, endAbs } }));
                        setSelected(cur => ({ ...cur, [ctx.flubber_index]: true }));
                        setStartIdx(ctx.flubber_index);
                      }}
                    >
                      <Scissors className="w-3.5 h-3.5 mr-1"/>Cut
                    </Button>
                  ) : (
                    <Button
                      size="xs"
                      variant="outline"
                      onClick={()=>{
                        setSelected(cur => ({ ...cur, [ctx.flubber_index]: false }));
                        setMarkerOverrides(prev => { const n={...prev}; delete n[ctx.flubber_index]; return n; });
                      }}
                    >
                      <X className="w-3.5 h-3.5 mr-1"/>Uncut
                    </Button>
                  )}
                </div>
              </div>
              {ctx.url ? (
                <div className="space-y-2">
                  <Waveform
                    src={ctx.url}
                    height={80}
                    cutButtonLabel="Cut"
                    start={selected[ctx.flubber_index] && markerOverrides[ctx.flubber_index]?.startAbs != null ? Math.max(0, markerOverrides[ctx.flubber_index].startAbs - snippetStart) : undefined}
                    end={selected[ctx.flubber_index] && markerOverrides[ctx.flubber_index]?.endAbs != null ? Math.max(0, markerOverrides[ctx.flubber_index].endAbs - snippetStart) : undefined}
                    markerEnd={Math.max(0, (ctx.computed_end_s ?? ((ctx.flubber_end_s || flubberTime) + 0.2)) - snippetStart)}
                    onMarkersChange={({start, end}) => {
                      // Convert from snippet-relative to episode-absolute time
                      if (typeof start === 'number') {
                        const absS = Math.max(0, snippetStart + start);
                        setStartIdx(ctx.flubber_index);
                        setMarkerOverrides(prev => ({ ...prev, [ctx.flubber_index]: { ...(prev[ctx.flubber_index]||{}), startAbs: absS } }));
                      }
                      if (typeof end === 'number') {
                        const absE = Math.max(0, snippetStart + end);
                        setMarkerOverrides(prev => ({ ...prev, [ctx.flubber_index]: { ...(prev[ctx.flubber_index]||{}), endAbs: absE } }));
                      }
                    }}
                    onCut={(relativeNowSec) => {
                      // When Cut is pressed, mark start at current playhead (snippet-relative -> episode-absolute)
                      const startAbs = Math.max(0, snippetStart + (relativeNowSec || 0));
                      const endAbs = (ctx.computed_end_s ?? ((ctx.flubber_end_s || flubberTime) + 0.2));
                      setMarkerOverrides(prev => ({ ...prev, [ctx.flubber_index]: { startAbs, endAbs } }));
                      setSelected(cur => ({ ...cur, [ctx.flubber_index]: true }));
                      setStartIdx(ctx.flubber_index);
                    }}
                  />
                  <div className="flex items-center justify-between text-[11px] text-gray-600">
                    <div>
                      Red line: {flubberTime.toFixed(2)}s | 
                      Auto end: {(ctx.computed_end_s ?? ((ctx.flubber_end_s||0) + 0.2)).toFixed(2)}s
                    </div>
                    <div className="flex gap-2">
                      <Button
                        size="xs"
                        variant="outline"
                        onClick={() => {
                          const newExpansion = Math.min(availableBeforeSeconds, (expansion || 0) + 15);
                          setWindowExpansion(prev => ({
                            ...prev,
                            [ctx.flubber_index]: newExpansion
                          }));
                        }}
                        disabled={!canExpandMore}
                        title={canExpandMore ? `Review 15s more context (${availableBeforeSeconds.toFixed(1)}s available)` : "Already reviewing full context"}
                      >
                        <ChevronLeft className="w-3 h-3 mr-1"/>Expand Context ({expansion > 0 ? `${expansion}s` : 'default'})
                      </Button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-[11px] text-gray-500">Snippet not available</div>
              )}
            </div>
          )})}
        </CardContent>
      </Card>
    </div>
  );
}
