import React, { useState, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { AlertTriangle, Scissors, X } from 'lucide-react';

const formatTimestamp = (seconds) => {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

export default function FlubberCommandReviewText({
  open,
  contexts = [],
  onConfirm,
  onCancel,
}) {
  // Track which flubbers are selected and their start positions
  const [selected, setSelected] = useState(() => {
    const pre = {};
    (contexts || []).forEach((c) => {
      pre[c.flubber_index] = true;
    });
    return pre;
  });

  const [startPositions, setStartPositions] = useState({});
  const [endPositions, setEndPositions] = useState({}); // NEW: Track end positions for clicks after flubber

  // Calculate chosen flubbers sorted by time
  const chosen = useMemo(
    () => (contexts || []).filter((c) => selected[c.flubber_index]),
    [contexts, selected]
  );

  const chosenSorted = useMemo(
    () => [...chosen].sort((a, b) => (a.flubber_time_s || 0) - (b.flubber_time_s || 0)),
    [chosen]
  );

  const toggleSelection = (flubberIndex) => {
    setSelected((prev) => ({
      ...prev,
      [flubberIndex]: !prev[flubberIndex],
    }));
  };

  const handleWordClick = (ctx, wordTimestamp) => {
    const flubberTimeS = ctx.flubber_time_s || 0;
    
    // If clicked word is BEFORE flubber, set as start position
    // If clicked word is AFTER flubber, set as end position
    if (wordTimestamp < flubberTimeS) {
      setStartPositions((prev) => ({
        ...prev,
        [ctx.flubber_index]: wordTimestamp,
      }));
    } else {
      setEndPositions((prev) => ({
        ...prev,
        [ctx.flubber_index]: wordTimestamp,
      }));
    }
  };

  const handleReset = (flubberIndex) => {
    setStartPositions((prev) => {
      const newStarts = { ...prev };
      delete newStarts[flubberIndex];
      return newStarts;
    });
    setEndPositions((prev) => {
      const newEnds = { ...prev };
      delete newEnds[flubberIndex];
      return newEnds;
    });
  };

  const handleConfirm = () => {
    if (typeof onConfirm !== 'function') return;

    const cuts = chosenSorted.map((ctx) => {
      const idx = ctx.flubber_index;
      const flubberTimeS = ctx.flubber_time_s || 0;
      
      // Calculate effective start and end
      const effectiveStartS = startPositions[idx] ?? Math.max(0, flubberTimeS - 0.75);
      const defaultEndS = (ctx.flubber_end_s || flubberTimeS || 0) + 0.2;
      const effectiveEndS = endPositions[idx] ?? defaultEndS;
      
      return [Math.round(effectiveStartS * 1000), Math.round(effectiveEndS * 1000)];
    });

    onConfirm(cuts);
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <Card className="w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col shadow-xl">
        <CardHeader className="border-b">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <CardTitle className="text-lg font-semibold text-slate-900 flex items-center gap-2">
                <Scissors className="h-4 w-4 text-red-500" />
                Review Flubber Cuts
              </CardTitle>
              <p className="text-sm text-slate-600">
                Each "flubber" marks the END of a mistake. Click where the mistake STARTS.
              </p>
            </div>
            <Badge variant="outline" className="border-slate-200">
              Flubbers: {contexts.length}
            </Badge>
          </div>
        </CardHeader>

        <CardContent className="flex-1 overflow-y-auto space-y-4 p-6 bg-slate-50">
          {contexts.length === 0 && (
            <div className="text-sm text-slate-600 bg-white border border-slate-200 rounded-md p-6 text-center">
              No flubber commands detected.
            </div>
          )}

          {contexts.map((ctx, ctxIdx) => {
            const flubberIndex = ctx.flubber_index;
            const isSelected = selected[flubberIndex];
            const flubberTimeS = ctx.flubber_time_s || 0;
            
            // Calculate effective start and end
            const customStartS = startPositions[flubberIndex];
            const customEndS = endPositions[flubberIndex];
            const defaultStartS = Math.max(0, flubberTimeS - 0.75);
            const defaultEndS = (ctx.flubber_end_s || ctx.computed_end_s || flubberTimeS || 0) + 0.2;
            
            const currentStartS = customStartS ?? defaultStartS;
            const currentEndS = customEndS ?? defaultEndS;

            // Display words from snippet
            const words = ctx.words || [];
            const hasCustomCut = customStartS !== undefined || customEndS !== undefined;

            return (
              <div
                key={flubberIndex}
                className={`bg-white rounded-lg border shadow-sm p-5 space-y-4 ${
                  !isSelected ? 'border-slate-200 opacity-60' : 'border-red-300'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-slate-800">
                      Flubber {ctxIdx + 1}
                    </div>
                    <div className="text-xs text-slate-500">
                      Flubber at {formatTimestamp(flubberTimeS)} – click BEFORE or AFTER "flubber"
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {hasCustomCut && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => handleReset(flubberIndex)}
                        className="text-xs"
                      >
                        Reset
                      </Button>
                    )}
                    <Badge variant={isSelected ? 'default' : 'outline'} className={isSelected ? 'bg-red-500' : ''}>
                      {isSelected ? 'Will Cut' : 'Skipped'}
                    </Badge>
                    <Button
                      size="sm"
                      variant={isSelected ? 'outline' : 'default'}
                      onClick={() => toggleSelection(flubberIndex)}
                    >
                      {isSelected ? <X className="h-4 w-4 mr-1" /> : <Scissors className="h-4 w-4 mr-1" />}
                      {isSelected ? 'Skip' : 'Cut'}
                    </Button>
                  </div>
                </div>

                {isSelected && (
                  <>
                    <div className="bg-red-50 border border-red-200 rounded-md p-3">
                      <div className="text-xs font-semibold text-red-900 mb-1 flex items-center gap-2">
                        <AlertTriangle className="h-3 w-3" />
                        What to do: Click BEFORE "flubber" to set cut start, or AFTER "flubber" to set cut end
                      </div>
                      <div className="text-xs text-red-700">
                        <span className="inline-block bg-red-100 px-1 rounded">Light red words</span> = What will be REMOVED (cut out)
                        <br />
                        <span className="inline-block bg-red-200 px-1 rounded font-semibold">Dark red words</span> = Your custom start/end selections
                        <br />
                        <span className="inline-block text-slate-400 px-1">Gray words</span> = Before cut start (kept in episode)
                        <br />
                        <span className="inline-block text-slate-600 px-1">Darker gray words</span> = After cut end (kept in episode)
                      </div>
                    </div>

                    <div className="space-y-2">
                      <div className="text-xs font-semibold text-slate-700 flex items-center justify-between">
                        <span>Transcript - Click words to adjust cut range</span>
                        <span className="text-slate-500">
                          Cut from: {formatTimestamp(currentStartS)} to {formatTimestamp(currentEndS)}
                        </span>
                      </div>

                      <div className="text-sm text-slate-700 bg-slate-50 border-2 border-red-300 rounded-md p-3 leading-relaxed">
                        {words.map((word, idx) => {
                          const wordStart = word.start;
                          const wordEnd = word.end;
                          
                          // Determine if this word is:
                          // - Before the cut (kept) = light gray
                          // - In the cut range (removed) = red
                          // - After the cut (kept) = darker gray
                          // - Selected start/end word = dark red
                          
                          const isBeforeCut = wordEnd <= currentStartS;
                          const isAfterCut = wordStart >= currentEndS;
                          const isInCutRange = wordStart >= currentStartS && wordStart < currentEndS;
                          const isCustomStartWord = customStartS !== undefined && Math.abs(wordStart - customStartS) < 0.05;
                          const isCustomEndWord = customEndS !== undefined && Math.abs(wordStart - customEndS) < 0.05;
                          const isFlubberWord = Math.abs(wordStart - flubberTimeS) < 0.05;

                          return (
                            <span
                              key={idx}
                              onClick={() => handleWordClick(ctx, wordStart)}
                              className={`
                                inline-block cursor-pointer px-0.5 transition-colors
                                ${isCustomStartWord || isCustomEndWord ? 'bg-red-200 text-red-900 font-semibold border-b-2 border-red-400' : ''}
                                ${isFlubberWord ? 'bg-yellow-100 border border-yellow-400 font-bold' : ''}
                                ${isInCutRange && !isCustomStartWord && !isCustomEndWord && !isFlubberWord ? 'bg-red-50 hover:bg-red-100 text-red-700 line-through' : ''}
                                ${isBeforeCut && !isFlubberWord ? 'text-slate-400 hover:bg-slate-100' : ''}
                                ${isAfterCut && !isFlubberWord ? 'text-slate-600 hover:bg-slate-100' : ''}
                              `}
                            >
                              {word.word}
                            </span>
                          );
                        })}
                      </div>
                    </div>

                    <div className="text-xs text-slate-600 bg-slate-100 border border-slate-200 rounded-md p-3">
                      <span className="font-semibold">Preview:</span> Audio from {formatTimestamp(currentStartS)} to {formatTimestamp(currentEndS)} will be removed (
                      {(currentEndS - currentStartS).toFixed(1)}s cut)
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </CardContent>

        <div className="border-t p-4 bg-white flex items-center justify-between gap-4">
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>

          <Button onClick={handleConfirm} disabled={chosenSorted.length === 0}>
            <Scissors className="h-4 w-4 mr-2" />
            Cut {chosenSorted.length} flubber{chosenSorted.length !== 1 ? 's' : ''}
          </Button>
        </div>
      </Card>
    </div>
  );
}
