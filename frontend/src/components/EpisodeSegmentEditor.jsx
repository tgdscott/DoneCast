import React, { useCallback } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Plus, Scissors, Trash2 } from 'lucide-react';

/**
 * EpisodeSegmentEditor
 * Lightweight initial pass at structuring an episode into labeled segments (Intro, Main, Outro, etc.).
 * This is intentionally simple (no waveform yet) but provides:
 *  - Visual horizontal bar showing relative segment lengths
 *  - Inline rename of segment labels
 *  - Add Ad Break (splits the largest main segment)
 *  - Split (halves selected segment if long enough)
 *  - Remove non-core segments (e.g., ad breaks) while keeping continuous coverage
 *
 * Expected segment object: { id, label, start, end, type }
 * Types: intro | main | outro | ad | custom
 */
export default function EpisodeSegmentEditor({ totalSeconds, segments, onChange }) {
  const duration = Math.max(1, totalSeconds || 1);

  const updateSegment = (id, patch) => {
    onChange(segments.map(s => s.id === id ? { ...s, ...patch } : s));
  };

  const formatTime = (secs) => {
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m}:${s.toString().padStart(2,'0')}`;
  };

  const addAdBreak = () => {
    // Find largest main segment to split
    const mainSeg = [...segments].filter(s => s.type === 'main').sort((a,b) => (b.end-b.start)-(a.end-a.start))[0];
    if (!mainSeg) return;
    const segLen = mainSeg.end - mainSeg.start;
    if (segLen < 120) return; // need at least 2 min to carve reasonable ad break
    const adLen = Math.min(60, Math.max(30, Math.round(segLen * 0.08))); // 30-60s typical
    const midpoint = mainSeg.start + segLen/2;
    const adStart = Math.round(midpoint - adLen/2);
    const adEnd = adStart + adLen;
    // Construct new sequence: main (before), ad, main (after)
    const before = { ...mainSeg, end: adStart };
    const ad = { id: crypto.randomUUID(), label: 'Ad Break', start: adStart, end: adEnd, type: 'ad' };
    const after = { ...mainSeg, id: crypto.randomUUID(), start: adEnd };
    const next = segments.flatMap(s => s.id === mainSeg.id ? [before, ad, after] : [s]);
    onChange(next);
  };

  const splitSegment = (seg) => {
    const len = seg.end - seg.start;
    if (len < 60) return; // too short to split
    const mid = Math.round(seg.start + len/2);
    const first = { ...seg, end: mid };
    const second = { ...seg, id: crypto.randomUUID(), start: mid };
    onChange(segments.flatMap(s => s.id === seg.id ? [first, second] : [s]));
  };

  const removeSegment = (seg) => {
    if (['intro','outro','main'].includes(seg.type)) return; // preserve core
    // Merge space into adjacent segment with most overlap potential (prefer main)
    const idx = segments.findIndex(s => s.id === seg.id);
    const prev = segments[idx-1];
    const next = segments[idx+1];
    let mergedSegments = [...segments];
    mergedSegments.splice(idx,1);
    if (prev && next && prev.type === next.type) {
      // combine prev + next if same type by extending prev
      const combined = { ...prev, end: next.end };
      mergedSegments = [
        ...segments.slice(0, idx-1),
        combined,
        ...segments.slice(idx+2)
      ].filter(Boolean);
    }
    onChange(mergedSegments);
  };

  const colorClass = useCallback((type) => {
    switch(type) {
      case 'intro': return 'bg-indigo-500';
      case 'outro': return 'bg-slate-500';
      case 'ad': return 'bg-amber-500';
      case 'main': return 'bg-blue-500';
      default: return 'bg-gray-400';
    }
  }, []);

  return (
    <Card className="border-0 shadow-lg bg-white">
      <CardHeader>
        <CardTitle className="flex items-center justify-between" style={{ color: '#2C3E50' }}>
          <span>Episode Sections</span>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" className="bg-transparent" onClick={addAdBreak} disabled={!segments.some(s=>s.type==='main')}>
              <Plus className="w-4 h-4 mr-1" /> Ad Break
            </Button>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-5">
        {/* Visual bar */}
        <div className="w-full h-5 rounded overflow-hidden flex ring-1 ring-gray-200">
          {segments.map(s => {
            const pct = ((s.end - s.start)/duration)*100;
            return <div key={s.id} style={{ width: pct+'%' }} className={`relative ${colorClass(s.type)} group`}> 
              <span className="absolute inset-0 flex items-center justify-center text-[10px] text-white font-medium opacity-0 group-hover:opacity-100 transition-opacity">
                {s.label}
              </span>
            </div>;
          })}
        </div>
        <div className="text-[11px] text-gray-500 flex justify-between font-mono">
          <span>0:00</span>
          <span>{formatTime(duration)}</span>
        </div>

        {/* Segment list */}
        <div className="space-y-3">
          {segments.map(seg => (
            <div key={seg.id} className="border rounded-lg p-3 bg-gray-50 flex flex-col gap-2">
              <div className="flex items-center gap-3">
                <Input
                  value={seg.label}
                  onChange={e => updateSegment(seg.id, { label: e.target.value })}
                  className="text-sm"
                />
                <div className="text-[11px] text-gray-600 font-mono whitespace-nowrap">
                  {formatTime(seg.start)} - {formatTime(seg.end)} ({formatTime(seg.end - seg.start)})
                </div>
              </div>
              <div className="flex gap-2">
                {seg.type !== 'ad' && (seg.end - seg.start) >= 120 && (
                  <Button variant="outline" size="xs" className="h-7 px-2 bg-transparent" onClick={() => splitSegment(seg)}>
                    <Scissors className="w-3 h-3 mr-1" /> Split
                  </Button>
                )}
                {seg.type === 'ad' && (
                  <Button variant="outline" size="xs" className="h-7 px-2 bg-transparent" onClick={() => removeSegment(seg)}>
                    <Trash2 className="w-3 h-3 mr-1" /> Remove
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
        <div className="text-[10px] text-gray-400">
          This structural model is a draft (no waveform yet). Later we can auto-detect segments from silence, music beds, or chapter markers.
        </div>
      </CardContent>
    </Card>
  );
}
