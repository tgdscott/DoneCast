import React, { useState, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { AlertTriangle, CheckCircle2, Loader2, RefreshCcw, Sparkles } from 'lucide-react';

const formatTimestamp = (seconds) => {
  if (!Number.isFinite(seconds) || seconds < 0) return '0:00';
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, '0')}`;
};

export default function InternCommandReviewText({
  open,
  contexts = [],
  onComplete,
  onCancel,
  onProcess,
  voiceName,
  initialResults = [],
  maxRegenerations = 2,
}) {
  const [endPositions, setEndPositions] = useState({});
  const [responses, setResponses] = useState({});
  const [processingId, setProcessingId] = useState(null);
  const [errors, setErrors] = useState({});
  const [regenCount, setRegenCount] = useState({});

  // Initialize from contexts
  const normalized = useMemo(() => {
    return contexts.map((ctx, index) => {
      const raw = ctx || {};
      return {
        raw,
        id: raw.command_id ?? raw.intern_index ?? `intern-${index}`,
        index,
        startS: Number(raw.start_s || 0),
        defaultEndS: Number(raw.default_end_s || 0),
        maxEndS: Number(raw.max_end_s || 0),
        promptText: (raw.prompt_text || '').trim(),
        words: Array.isArray(raw.words) ? raw.words : [],
        voiceId: raw.voice_id,
      };
    });
  }, [contexts]);

  // Calculate prompt text based on end position
  const calculatePromptText = (ctx, endS) => {
    if (!Array.isArray(ctx.words) || ctx.words.length === 0) {
      return ctx.promptText;
    }
    const tokens = [];
    for (const w of ctx.words) {
      if (w.start >= endS) break;
      tokens.push(w.word);
    }
    return tokens.join(' ').trim() || ctx.promptText;
  };

  const handleWordClick = (ctx, wordTimestamp) => {
    // Set end position to this word's timestamp
    setEndPositions((prev) => ({
      ...prev,
      [ctx.id]: wordTimestamp,
    }));
  };

  const handleGenerate = async (ctx, { regenerate = false } = {}) => {
    if (typeof onProcess !== 'function') return;
    
    const endS = endPositions[ctx.id] || ctx.defaultEndS;
    const startS = ctx.startS;
    
    setProcessingId(ctx.id);
    setErrors((prev) => ({ ...prev, [ctx.id]: null }));
    
    try {
      const result = await onProcess({
        context: ctx.raw,
        startSeconds: startS,
        endSeconds: endS,
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
      const endS = endPositions[ctx.id] || ctx.defaultEndS;
      const text = (responses[ctx.id]?.text || '').trim();
      const voiceId = responses[ctx.id]?.raw?.voice_id || ctx.voiceId;
      
      return {
        command_id: responses[ctx.id]?.commandId ?? ctx.raw?.command_id ?? ctx.id,
        start_s: ctx.startS,
        end_s: endS,
        response_text: text,
        voice_id: voiceId,
        audio_url: responses[ctx.id]?.audioUrl || null,
        prompt_text: calculatePromptText(ctx, endS),
        regenerate_count: regenCount[ctx.id] || 0,
      };
    });
    
    onComplete(results);
  };

  if (!open) return null;

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
                Read the transcript and click where each command ends, then generate the intern's response.
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
            const currentEndS = endPositions[ctx.id] || ctx.defaultEndS;
            const promptText = calculatePromptText(ctx, currentEndS);
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
                      Starts at {formatTimestamp(ctx.startS)} – click a word to mark where it ends
                    </div>
                  </div>
                  <Badge 
                    variant={pending ? 'outline' : 'default'} 
                    className={pending ? 'border-amber-300 text-amber-600 bg-amber-50' : 'bg-emerald-500 text-white'}
                  >
                    {pending ? 'Pending' : 'Ready'}
                  </Badge>
                </div>

                <div className="space-y-2">
                  <div className="bg-green-50 border border-green-200 rounded-md p-3 mb-3">
                    <div className="text-xs font-semibold text-green-900 mb-1 flex items-center gap-2">
                      <AlertTriangle className="h-3 w-3" />
                      What to do: Click the LAST WORD of what the intern should respond to
                    </div>
                    <div className="text-xs text-green-700">
                      <span className="inline-block bg-green-100 px-1 rounded">Light green words</span> = What the AI will use to generate a response
                      <br />
                      <span className="inline-block bg-green-200 px-1 rounded font-semibold">Dark green word</span> = The last word you selected (click a different word to change)
                      <br />
                      <span className="inline-block text-slate-400 px-1">Gray words</span> = After your selection (not included)
                    </div>
                  </div>
                  
                  <div className="text-xs font-semibold text-slate-700 flex items-center justify-between">
                    <span>Transcript - Click any word to mark it as the END of the intern's context</span>
                    <span className="text-slate-500">
                      Selected end: {formatTimestamp(currentEndS)}
                    </span>
                  </div>
                  
                  <div className="text-sm text-slate-700 bg-slate-50 border-2 border-green-300 rounded-md p-3 leading-relaxed">
                    {ctx.words.map((word, idx) => {
                      const isSelected = word.start <= currentEndS && word.end > currentEndS;
                      const isBeforeEnd = word.start < currentEndS;
                      
                      return (
                        <span
                          key={idx}
                          onClick={() => handleWordClick(ctx, word.end)}
                          className={`
                            inline-block cursor-pointer px-0.5 transition-colors
                            ${isSelected ? 'bg-green-200 text-green-900 font-semibold border-b-2 border-green-400' : ''}
                            ${isBeforeEnd && !isSelected ? 'bg-green-50 hover:bg-green-100' : ''}
                            ${!isBeforeEnd ? 'text-slate-400 hover:bg-slate-100' : ''}
                          `}
                        >
                          {word.word}
                        </span>
                      );
                    })}
                  </div>
                </div>

                <div className="space-y-2">
                  <div className="text-xs font-semibold text-slate-700">Prompt (what the AI will receive)</div>
                  <div className="text-xs text-slate-600 bg-slate-100 border border-slate-200 rounded-md p-3 whitespace-pre-wrap">
                    {promptText || '—'}
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

                {response && response.text && (
                  <div className="space-y-2">
                    <div className="text-xs font-semibold text-slate-700">Intern response (edit if needed)</div>
                    <Textarea
                      value={response.text}
                      onChange={(e) => handleResponseChange(ctx, e.target.value)}
                      className="min-h-[80px] text-sm"
                      placeholder="Edit the intern's response..."
                    />
                  </div>
                )}
              </div>
            );
          })}
        </CardContent>

        <div className="border-t p-4 bg-white flex items-center justify-between gap-4">
          <Button variant="outline" onClick={onCancel} disabled={processingId !== null}>
            Cancel
          </Button>
          
          <div className="flex items-center gap-2">
            {voiceName && (
              <span className="text-xs text-slate-500">Voice: {voiceName}</span>
            )}
            <Button 
              onClick={handleSubmit} 
              disabled={processingId !== null || normalized.some((ctx) => !responses[ctx.id]?.text)}
            >
              Continue with {normalized.length} command{normalized.length !== 1 ? 's' : ''}
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
