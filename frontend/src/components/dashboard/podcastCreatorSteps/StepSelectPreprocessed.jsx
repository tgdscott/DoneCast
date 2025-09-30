import React, { useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';
import { Badge } from '../../ui/badge';
import { Button } from '../../ui/button';
import { AlertTriangle, FileAudio, Loader2, RefreshCcw, Sparkles, Trash2 } from 'lucide-react';

const formatDate = (iso) => {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
  } catch {
    return iso;
  }
};

const formatDuration = (seconds) => {
  if (!seconds || !isFinite(seconds)) return '—';
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  if (mins <= 0) return `${secs}s`;
  if (secs <= 0) return `${mins}m`;
  return `${mins}m ${secs}s`;
};

export default function StepSelectPreprocessed({
  items = [],
  loading = false,
  selectedFilename,
  onSelect,
  onBack,
  onNext,
  onRefresh,
  intents = {},
  pendingIntentLabels = [],
  onIntentSubmit,
  onEditAutomations,
  onDeleteItem = null,
}) {
  const hasPendingIntents = Array.isArray(pendingIntentLabels) && pendingIntentLabels.length > 0;

  const selected = useMemo(
    () => items.find((item) => item.filename === selectedFilename) || null,
    [items, selectedFilename]
  );

  const counts = selected?.intents || {};
  const flubberCount = Number((counts?.flubber?.count) ?? 0);
  const internCount = Number((counts?.intern?.count) ?? 0);
  const sfxCount = Number((counts?.sfx?.count) ?? 0);

  const handleContinue = async () => {
    if (hasPendingIntents && typeof onEditAutomations === 'function') {
      onEditAutomations();
      return;
    }
    if (typeof onIntentSubmit === 'function') {
      const result = await onIntentSubmit(intents);
      if (result === false) return;
      if (result === true) return;
    }
    if (typeof onNext === 'function') onNext();
  };

  const canContinue = !!selected;

  return (
    <div className="space-y-6">
      <CardHeader className="text-center">
        <CardTitle style={{ color: '#2C3E50' }}>Step 2: Choose Your Processed Audio</CardTitle>
      </CardHeader>

      <Card className="bg-slate-50 border border-slate-200">
        <CardContent className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-sm text-slate-700">
            Pick one of your fully transcribed uploads. We’ll drop you into the editor with transcripts, intent cues, and automations ready to go.
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={onBack}>
              Back
            </Button>
            <Button variant="outline" size="sm" onClick={onRefresh} disabled={loading}>
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCcw className="w-4 h-4" />}
              <span className="ml-2">Refresh</span>
            </Button>
          </div>
        </CardContent>
      </Card>

      <Card className="border border-dashed border-slate-300">
        <CardContent className="p-0">
          <div className="divide-y divide-slate-200">
            {loading && (
              <div className="flex items-center justify-center py-10 text-sm text-slate-500">
                <Loader2 className="w-5 h-5 mr-2 animate-spin" /> Checking uploads…
              </div>
            )}
            {!loading && items.length === 0 && (
              <div className="py-10 text-center text-sm text-slate-500">
                No uploads yet. Upload audio from the previous step to see it here.
              </div>
            )}
            {!loading && items.length > 0 && (
              <div className="grid grid-cols-1 md:grid-cols-2">
                {items.map((item) => {
                  const ready = !!item?.transcript_ready;
                  const isSelected = item.filename === selectedFilename;
                  const intentsData = item.intents || {};
                  const flubber = Number((intentsData?.flubber?.count) ?? 0);
                  const intern = Number((intentsData?.intern?.count) ?? 0);
                  const sfx = Number((intentsData?.sfx?.count) ?? 0);
                  const canInteract = ready && typeof onSelect === 'function';
                  const deleteHintReady = 'Deleting a ready upload will not refund processing minutes already used.';
                  const deleteHintPending = 'Delete this upload while it is still processing? No processing minutes have been deducted yet.';
                  return (
                    <div
                      key={item.id || item.filename}
                      role="button"
                      tabIndex={ready ? 0 : -1}
                      aria-disabled={!ready}
                      className={`text-left p-4 transition border-r border-b border-slate-200 focus:outline-none focus-visible:ring ${
                        ready ? 'bg-white hover:bg-slate-50 cursor-pointer' : 'bg-slate-100 cursor-not-allowed opacity-70'
                      } ${isSelected ? 'ring-2 ring-blue-500' : ''}`}
                      onClick={() => {
                        if (!ready || !canInteract) return;
                        onSelect(item);
                      }}
                      onKeyDown={(event) => {
                        if (!ready || !canInteract) return;
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          onSelect(item);
                        }
                      }}
                    >
                      <div className="flex items-start gap-3">
                        <FileAudio className={`w-10 h-10 ${ready ? 'text-blue-500' : 'text-slate-400'}`} />
                        <div className="flex-1 space-y-1">
                          <div className="flex items-start justify-between gap-2">
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-slate-800">{item.friendly_name || item.filename}</span>
                              {ready ? (
                                <Badge variant={isSelected ? 'default' : 'outline'} className="bg-emerald-100 text-emerald-700 border-emerald-200">
                                  Ready
                                </Badge>
                              ) : (
                                <Badge variant="outline" className="bg-amber-100 text-amber-700 border-amber-200">
                                  Processing
                                </Badge>
                              )}
                            </div>
                            {typeof onDeleteItem === 'function' && (
                              <button
                                type="button"
                                className="inline-flex items-center justify-center rounded-full border border-transparent bg-slate-100 p-1 text-slate-500 hover:bg-slate-200 hover:text-slate-800 focus:outline-none focus-visible:ring"
                                onClick={(event) => {
                                  event.stopPropagation();
                                  onDeleteItem(item);
                                }}
                                onKeyDown={(event) => event.stopPropagation()}
                                title={ready ? deleteHintReady : deleteHintPending}
                                aria-label={`Delete ${item.friendly_name || item.filename}`}
                              >
                                <Trash2 className="h-4 w-4" />
                              </button>
                            )}
                          </div>
                          <div className="text-xs text-slate-500">
                            Uploaded {formatDate(item.created_at)} · Duration {formatDuration(item.duration_seconds)}
                          </div>
                          {ready && (
                            <div className="flex flex-wrap gap-2 mt-2 text-xs text-slate-600">
                              <Badge variant="outline" className="border-slate-300 text-slate-600">
                                Flubber: {flubber}
                              </Badge>
                              <Badge variant="outline" className="border-slate-300 text-slate-600">
                                Intern: {intern}
                              </Badge>
                              <Badge variant="outline" className="border-slate-300 text-slate-600">
                                SFX: {sfx}
                              </Badge>
                              {item.notify_pending && (
                                <Badge variant="outline" className="border-blue-200 text-blue-600 bg-blue-50">
                                  Notification queued
                                </Badge>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {selected && (
        <Card className="border border-slate-200">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base text-slate-800">
              <Sparkles className="w-4 h-4 text-amber-500" />
              Automations ready for {selected.friendly_name || selected.filename}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm text-slate-700">
            {flubberCount > 0 && (
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-amber-500 mt-0.5" />
                <div>
                  We found {flubberCount} flubber cue{flubberCount === 1 ? '' : 's'}. We’ll walk you through confirming those edits after this step.
                </div>
              </div>
            )}
            {internCount > 0 && (
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-blue-500 mt-0.5" />
                <div>
                  {internCount === 1 ? 'One intern command' : `${internCount} intern commands`} detected. We’ll capture the AI intern response when you configure automations.
                </div>
              </div>
            )}
            {sfxCount > 0 && (
              <div className="flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-green-500 mt-0.5" />
                <div>
                  {sfxCount} sound effect trigger{sfxCount === 1 ? '' : 's'} ready to swap with audio.
                </div>
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => typeof onEditAutomations === 'function' && onEditAutomations()}
              >
                Configure Automations
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      <div className="flex justify-between pt-4">
        <Button variant="ghost" onClick={onBack}>
          Back
        </Button>
        <Button onClick={handleContinue} disabled={!canContinue || loading}>
          Continue
        </Button>
      </div>
    </div>
  );
}
