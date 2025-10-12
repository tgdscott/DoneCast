import React, { useEffect, useMemo, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import Waveform from '@/components/media/Waveform';
import { AlertTriangle, CheckCircle2, Loader2, RefreshCcw, Sparkles } from 'lucide-react';

const clamp = (value, min, max) => {
  if (!Number.isFinite(value)) return min;
  return Math.min(Math.max(value, min), max);
};

const formatTimestamp = (seconds) => {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

const findInitialResult = (ctx, results) => {
  if (!Array.isArray(results)) return null;
  const keys = [
    ctx?.raw?.command_id,
    ctx?.raw?.intern_index,
    ctx?.raw?.id,
    ctx?.id,
    ctx?.index,
  ].filter((key) => key !== undefined && key !== null);
  return results.find((item) => {
    const candidate = item?.command_id ?? item?.context_id ?? item?.id;
    return keys.some((key) => key === candidate);
  }) || null;
};

export default function InternCommandReview({
  open,
  contexts = [],
  onComplete,
  onCancel,
  onProcess,
  voiceName,
  initialResults = [],
  maxRegenerations = 2,
}) {
  const normalized = useMemo(() => {
    return contexts.map((ctx, index) => {
      const raw = ctx || {};
      const startAbs = Number(raw.start_s ?? raw.absolute_start_s ?? raw.command_start_s ?? raw.trigger_time_s ?? raw.time_s ?? 0);
      const snippetStart = Number(raw.snippet_start_s ?? raw.window_start_s ?? startAbs);
      const snippetEnd = Number.isFinite(raw.snippet_end_s) ? Number(raw.snippet_end_s) : snippetStart + Math.min(30, Number(raw.duration_s ?? 30));
      const maxDuration = Number.isFinite(raw.max_duration_s) ? Number(raw.max_duration_s) : 30;
      const maxAbs = Math.max(snippetStart + 0.5, Math.min(snippetStart + Math.max(3, Math.min(maxDuration, 30)), snippetEnd + Math.min(8, maxDuration)));
      const defaultEndCandidate = Number(raw.default_end_s ?? raw.suggested_end_s ?? snippetEnd);
      const prompt = (raw.prompt_text ?? raw.transcript ?? raw.transcript_preview ?? raw.text ?? '').trim();
      const startRelative = Math.max(0, startAbs - snippetStart);
      const maxRelative = Math.max(startRelative + 0.5, Math.min(maxAbs - snippetStart, 30));
      let defaultEndRelative = clamp(defaultEndCandidate - snippetStart, startRelative + 0.5, maxRelative);
      if (!Number.isFinite(defaultEndRelative)) {
        defaultEndRelative = Math.min(maxRelative, startRelative + 6);
      }
      const audioUrl = raw.audio_url || raw.snippet_url || raw.url || null;
      const words = Array.isArray(raw.words) ? raw.words : [];
      return {
        raw,
        id: raw.command_id ?? raw.intern_index ?? raw.id ?? `intern-${index}`,
        index,
        audioUrl,
        prompt,
        label: raw.label || raw.display_label || null,
        startAbs,
        snippetStart,
        startRelative,
        defaultEndRelative,
        maxRelative,
        words,
      };
    });
  }, [contexts]);

  const [markerMap, setMarkerMap] = useState({});
  const [responses, setResponses] = useState({});
  const [processingId, setProcessingId] = useState(null);
  const [errors, setErrors] = useState({});
  const [regenCount, setRegenCount] = useState({});

  const calculatePromptText = (ctx, endRelative) => {
    if (!Array.isArray(ctx.words) || ctx.words.length === 0) {
      return ctx.prompt;
    }
    const endAbs = ctx.snippetStart + endRelative;
    const tokens = [];
    for (const w of ctx.words) {
      if (w.start >= endAbs) break;
      tokens.push(w.word);
    }
    return tokens.join(' ').trim() || ctx.prompt;
  };

  useEffect(() => {
    if (!open) return;
    const nextMarkers = {};
    const nextResponses = {};
    const nextRegens = {};
    normalized.forEach((ctx) => {
      const existing = findInitialResult(ctx, initialResults);
      let endRelative = ctx.defaultEndRelative;
      if (existing && Number.isFinite(existing.end_s)) {
        endRelative = clamp(existing.end_s - ctx.snippetStart, ctx.startRelative + 0.5, ctx.maxRelative);
      }
      nextMarkers[ctx.id] = { start: ctx.startRelative, end: endRelative };
      if (existing && typeof existing.response_text === 'string') {
        nextResponses[ctx.id] = {
          text: existing.response_text,
          audioUrl: existing.audio_url || null,
          commandId: existing.command_id ?? ctx.raw?.command_id ?? ctx.id,
          raw: existing,
        };
        if (Number.isFinite(existing.regenerate_count)) {
          nextRegens[ctx.id] = existing.regenerate_count;
        }
      }
    });
    setMarkerMap(nextMarkers);
    setResponses(nextResponses);
    setRegenCount(nextRegens);
    setErrors({});
    setProcessingId(null);
  }, [open, normalized, initialResults]);

  if (!open) return null;

  const pendingContexts = normalized.filter((ctx) => !responses[ctx.id] || !(responses[ctx.id].text || '').trim());
  const allComplete = normalized.length === 0 || pendingContexts.length === 0;

  const handleMarkersChange = (ctx, next) => {
    setMarkerMap((prev) => {
      const current = { ...(prev || {}) };
      const base = current[ctx.id] || { start: ctx.startRelative, end: ctx.defaultEndRelative };
      const nextStart = typeof next.start === 'number' ? clamp(next.start, 0, ctx.maxRelative - 0.25) : base.start;
      const minEnd = nextStart + 0.25;
      const proposedEnd = typeof next.end === 'number' ? next.end : base.end;
      const nextEnd = clamp(proposedEnd, minEnd, ctx.maxRelative);
      current[ctx.id] = { start: clamp(nextStart, ctx.startRelative, ctx.maxRelative - 0.1), end: nextEnd };
      return current;
    });
  };

  const handleCut = (ctx, relativeNowSec) => {
    if (!Number.isFinite(relativeNowSec)) return;
    setMarkerMap((prev) => {
      const current = { ...(prev || {}) };
      const base = current[ctx.id] || { start: ctx.startRelative, end: ctx.defaultEndRelative };
      const minEnd = base.start + 0.25;
      current[ctx.id] = {
        start: base.start,
        end: clamp(relativeNowSec, minEnd, ctx.maxRelative),
      };
      return current;
    });
  };

  const handleGenerate = async (ctx, { regenerate = false } = {}) => {
    if (typeof onProcess !== 'function') return;
    const marker = markerMap[ctx.id] || { start: ctx.startRelative, end: ctx.defaultEndRelative };
    const endAbs = ctx.snippetStart + clamp(marker.end, ctx.startRelative + 0.25, ctx.maxRelative);
    const startAbs = ctx.startAbs;
    setProcessingId(ctx.id);
    setErrors((prev) => ({ ...prev, [ctx.id]: null }));
    try {
      const result = await onProcess({
        context: ctx.raw,
        startSeconds: startAbs,
        endSeconds: endAbs,
        regenerate,
      });
      const text = (result?.response_text ?? result?.text ?? '').trim();
      setResponses((prev) => ({
        ...prev,
        [ctx.id]: {
          text,
          audioUrl: result?.audio_url || null,
          commandId: result?.command_id ?? ctx.raw?.command_id ?? ctx.id,
          raw: result,
        },
      }));
      setRegenCount((prev) => {
        const current = prev?.[ctx.id] || 0;
        return {
          ...prev,
          [ctx.id]: regenerate ? current + 1 : current,
        };
      });
    } catch (error) {
      const message = error?.detail?.message || error?.message || 'Intern processing failed.';
      setErrors((prev) => ({ ...prev, [ctx.id]: message }));
    } finally {
      setProcessingId(null);
    }
  };

  const handleResponseChange = (ctx, value) => {
    setResponses((prev) => ({
      ...prev,
      [ctx.id]: {
        ...(prev?.[ctx.id] || { commandId: ctx.raw?.command_id ?? ctx.id, audioUrl: null, raw: null }),
        text: value,
      },
    }));
  };

  const handleSubmit = () => {
    if (typeof onComplete !== 'function') return;
    const results = normalized.map((ctx) => {
      const marker = markerMap[ctx.id] || { start: ctx.startRelative, end: ctx.defaultEndRelative };
      const endAbs = ctx.snippetStart + clamp(marker.end, ctx.startRelative + 0.25, ctx.maxRelative);
      const text = (responses[ctx.id]?.text || '').trim();
      const voiceId = responses[ctx.id]?.raw?.voice_id || ctx.raw?.voice_id;
      return {
        command_id: responses[ctx.id]?.commandId ?? ctx.raw?.command_id ?? ctx.id,
        start_s: ctx.startAbs,
        end_s: endAbs,
        response_text: text,
        voice_id: voiceId,
        audio_url: responses[ctx.id]?.audioUrl || null,
        prompt_text: calculatePromptText(ctx, marker.end),
        regenerate_count: regenCount[ctx.id] || 0,
      };
    });
    onComplete(results);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <Card className="w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col shadow-xl">
        <CardHeader className="border-b">
          <div className="flex items-start justify-between gap-4">
            <div className="space-y-1">
              <CardTitle className="text-lg font-semibold text-slate-900 flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-amber-500" />
                Review Intern Commands
              </CardTitle>
              <p className="text-sm text-slate-600">
                Mark where each spoken command ends, then generate or edit the intern's response.
                {voiceName ? ` Responses will use the "${voiceName}" voice.` : " Responses use your template's intern voice."}
              </p>
            </div>
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <Badge variant="outline" className="border-slate-200">
                Commands: {normalized.length}
              </Badge>
              {maxRegenerations > 0 && (
                <Badge variant="outline" className="border-slate-200">
                  Regens allowed: {maxRegenerations}
                </Badge>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex-1 overflow-y-auto space-y-4 p-6 bg-slate-50">
          {normalized.length === 0 && (
            <div className="text-sm text-slate-600 bg-white border border-slate-200 rounded-md p-6 text-center">
              No intern commands detected.
            </div>
          )}
          {normalized.map((ctx) => {
            const marker = markerMap[ctx.id] || { start: ctx.startRelative, end: ctx.defaultEndRelative };
            const response = responses[ctx.id];
            const pending = !response || !(response.text || '').trim();
            const regenUsed = regenCount[ctx.id] || 0;
            const canRegenerate = typeof onProcess === 'function' && regenUsed < maxRegenerations;
            const isProcessing = processingId === ctx.id;
            return (
              <div key={ctx.id} className="bg-white rounded-lg border border-slate-200 shadow-sm p-5 space-y-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="text-sm font-semibold text-slate-800">
                      Command {ctx.index + 1}
                    </div>
                    <div className="text-xs text-slate-500">
                      Detected at {formatTimestamp(ctx.startAbs)} – mark where it ends.
                    </div>
                  </div>
                  <Badge variant={pending ? 'outline' : 'default'} className={pending ? 'border-amber-300 text-amber-600 bg-amber-50' : 'bg-emerald-500 text-white'}>
                    {pending ? 'Pending' : 'Ready'}
                  </Badge>
                </div>

                {ctx.audioUrl ? (
                  <Waveform
                    src={ctx.audioUrl}
                    height={90}
                    start={marker.start}
                    end={marker.end}
                    markerEnd={marker.end}
                    onMarkersChange={(next) => handleMarkersChange(ctx, next)}
                    onCut={(value) => handleCut(ctx, value)}
                  />
                ) : (
                  <div className="text-xs text-slate-600 bg-slate-100 border border-slate-200 rounded-md p-3 flex items-center gap-2">
                    <AlertTriangle className="h-4 w-4 text-amber-500" />
                    Audio preview unavailable for this command.
                  </div>
                )}

                <div className="space-y-2">
                  <div className="text-xs font-semibold text-slate-700">Prompt snippet</div>
                  <div className="text-xs text-slate-600 bg-slate-100 border border-slate-200 rounded-md p-3 whitespace-pre-wrap">
                    {calculatePromptText(ctx, marker.end) || '—'}
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    size="sm"
                    onClick={() => handleGenerate(ctx, { regenerate: false })}
                    disabled={isProcessing || typeof onProcess !== 'function'}
                  >
                    {isProcessing ? (
                      <>
                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                        Processing
                      </>
                    ) : (
                      <>
                        <Sparkles className="h-4 w-4 mr-2" />
                        Generate response
                      </>
                    )}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleGenerate(ctx, { regenerate: true })}
                    disabled={isProcessing || !response || !response.text || !canRegenerate}
                  >
                    <RefreshCcw className="h-4 w-4 mr-2" />
                    Regenerate{maxRegenerations ? ` (${maxRegenerations - regenUsed} left)` : ''}
                  </Button>
                  {!pending && (
                    <span className="flex items-center text-xs text-emerald-600 gap-1">
                      <CheckCircle2 className="h-4 w-4" /> Ready
                    </span>
                  )}
                </div>

                {errors[ctx.id] && (
                  <div className="text-xs text-red-600 bg-red-50 border border-red-200 rounded-md p-2">
                    {errors[ctx.id]}
                  </div>
                )}

                <div className="space-y-2">
                  <div className="text-xs font-semibold text-slate-700">Intern response</div>
                  <Textarea
                    rows={4}
                    value={response?.text || ''}
                    onChange={(event) => handleResponseChange(ctx, event.target.value)}
                    placeholder="Generated response will appear here. You can edit before continuing."
                  />
                  {response?.audioUrl && (
                    <audio controls className="w-full">
                      <source src={response.audioUrl} />
                    </audio>
                  )}
                </div>
              </div>
            );
          })}
        </CardContent>
        <div className="border-t bg-white px-6 py-4 flex items-center justify-between">
          <div className="text-xs text-slate-500">
            {voiceName ? `Intern voice: ${voiceName}` : 'Intern voice: template default'}
            {pendingContexts.length > 0 && (
              <span className="ml-2 text-amber-600">{pendingContexts.length} response{pendingContexts.length === 1 ? '' : 's'} still need attention.</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={onCancel}>
              Cancel
            </Button>
            <Button size="sm" onClick={handleSubmit} disabled={!allComplete}>
              Continue
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
