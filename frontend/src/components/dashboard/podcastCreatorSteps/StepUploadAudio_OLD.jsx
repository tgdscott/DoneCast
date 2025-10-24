import React from 'react';
import { Button } from '../../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';
import { FileAudio, Loader2, Mic, Upload, ArrowLeft, Lightbulb, AlertTriangle } from 'lucide-react';
import { formatDisplayName } from '@/lib/displayNames';
import { formatBytes, formatSpeed, formatEta, formatProgressDetail } from '@/lib/uploadProgress';

// Inline intent questions were removed in favor of the floating modal.

export default function StepUploadAudio({
  uploadedFile,
  uploadedFilename,
  isUploading,
  uploadProgress = null,
  uploadStats = null,
  onFileChange,
  fileInputRef,
  onBack,
  onNext = () => {},
  onEditAutomations,
  onIntentChange,
  onIntentSubmit,
  pendingIntentLabels = [],
  intents = {},
  intentVisibility = {},
  minutesPrecheck = null,
  minutesPrecheckPending = false,
  minutesPrecheckError = null,
  minutesBlocking = false,
  minutesBlockingMessage = '',
  minutesRequired = null,
  minutesRemaining = null,
  formatDuration = () => null,
  audioDurationSec: audioDurationSecProp = null,
  episodeStatus = null,
  wasRecorded = false,
}) {
  const audioDurationSec = audioDurationSecProp;
  const handleFileInput = (event) => {
    if (event.target.files?.[0]) {
      onFileChange(event.target.files[0]);
    }
  };

  const handleDrop = (event) => {
    event.preventDefault();
    if (event.dataTransfer.files?.[0]) {
      onFileChange(event.dataTransfer.files[0]);
    }
  };

  const hasPendingIntents = Array.isArray(pendingIntentLabels) && pendingIntentLabels.length > 0;
  const pendingLabelText = hasPendingIntents ? pendingIntentLabels.join(', ') : '';

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
    onNext();
  };

  const formatDurationSafe = typeof formatDuration === 'function' ? formatDuration : () => null;
  const parseNumber = (value) => {
    if (value === null || value === undefined || value === '') return null;
    const num = Number(value);
    return Number.isFinite(num) ? num : null;
  };
  const toPositiveSeconds = (value) => {
    const num = parseNumber(value);
    return num != null && num > 0 ? num : null;
  };
  const formatSeconds = (seconds) => (seconds != null && seconds > 0 ? formatDurationSafe(seconds) : null);
  const minutesFromSeconds = (seconds) => (seconds != null && seconds > 0 ? Math.max(1, Math.ceil(seconds / 60)) : null);

  const totalSeconds = toPositiveSeconds(minutesPrecheck?.total_seconds);
  const staticSeconds = toPositiveSeconds(minutesPrecheck?.static_seconds);
  const mainSeconds = toPositiveSeconds(minutesPrecheck?.main_seconds);
  const effectiveAudioSeconds = toPositiveSeconds(audioDurationSec);

  const parsedRequiredMinutes = parseNumber(minutesRequired);
  const requiredMinutesVal = (() => {
    if (parsedRequiredMinutes != null && parsedRequiredMinutes > 0) {
      return Math.max(1, Math.ceil(parsedRequiredMinutes));
    }
    const fallbackMinutes =
      minutesFromSeconds(totalSeconds) ??
      minutesFromSeconds(mainSeconds) ??
      minutesFromSeconds(effectiveAudioSeconds);
    return fallbackMinutes;
  })();

  const remainingMinutesVal = parseNumber(minutesRemaining);
  const remainingMinutesDisplay =
    remainingMinutesVal != null && Number.isFinite(remainingMinutesVal)
      ? Math.max(0, Math.ceil(remainingMinutesVal))
      : null;

  const totalDurationText =
    formatSeconds(totalSeconds) ?? formatSeconds(mainSeconds) ?? formatSeconds(effectiveAudioSeconds);
  const staticDurationText = formatSeconds(staticSeconds);
  const audioDurationText = formatSeconds(effectiveAudioSeconds);
  const requiredMinutesText =
    requiredMinutesVal != null
      ? `${requiredMinutesVal} minute${requiredMinutesVal === 1 ? '' : 's'}`
      : null;
  const remainingMinutesText = remainingMinutesDisplay != null
    ? `${remainingMinutesDisplay} minute${remainingMinutesDisplay === 1 ? '' : 's'}`
    : null;
  const showPrecheckCard = (uploadedFile || uploadedFilename)
    && (minutesPrecheckPending || minutesPrecheck || minutesPrecheckError);
  const blockingMessage = minutesBlockingMessage || 'Not enough processing minutes remain to create this episode.';

  return (
    <div className="space-y-8">
      <CardHeader className="text-center">
        <CardTitle style={{ color: '#2C3E50' }}>
          {wasRecorded ? 'Step 2: Your Recording' : 'Step 2: Select Main Content'}
        </CardTitle>
      </CardHeader>
      {(isUploading || (typeof uploadProgress === 'number' && uploadProgress < 100)) && (
        <div className="rounded-md border border-slate-200 bg-white p-3" aria-live="polite">
          <div className="flex items-center justify-between text-sm">
            <span className="text-slate-700">Uploading audio…</span>
            <span className="text-slate-600">{Math.max(0, Math.min(100, Number(uploadProgress) || 0))}%</span>
          </div>
          <div className="mt-2 h-2 w-full rounded-full bg-slate-200 overflow-hidden">
            <div
              className="h-full bg-slate-600 transition-all duration-200"
              style={{ width: `${Math.max(5, Math.min(100, Number(uploadProgress) || 5))}%` }}
            />
          </div>
          {uploadStats && (
            <div className="mt-2 text-xs text-slate-600">
              {formatProgressDetail(uploadStats.loaded, uploadStats.total, uploadStats.bytesPerSecond, uploadStats.etaSeconds)}
            </div>
          )}
        </div>
      )}

      <Card className="border-2 border-dashed border-gray-200 bg-white">
          <CardHeader className="flex flex-col gap-1 pb-2 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="text-base flex items-center gap-2 text-slate-800">
            <Lightbulb className="h-4 w-4 text-amber-500" aria-hidden="true" />
            Audio prep checklist
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-slate-700">
          <p>
            Give the automation a strong starting point with a clean, final mix. We’ll normalize levels on upload, but the
            clearer the file the better the downstream edit.
          </p>
          <ul className="list-disc space-y-1 pl-5">
            <li>Use WAV or MP3 files under 200&nbsp;MB for the smoothest upload.</li>
            <li>Trim long silences and keep background music subtle—we re-check loudness automatically.</li>
            <li>Re-uploading? Drop the same filename and we’ll detect it so you can skip the wait.</li>
          </ul>
          <details className="rounded-lg border border-dashed border-slate-300 bg-white/80 p-3">
            <summary className="cursor-pointer text-sm font-semibold text-slate-800">How intent questions work</summary>
            <div className="mt-2 space-y-2 text-slate-600">
              <p>
                When we ask about episode intent or offers, those answers steer intro/outro copy, ad reads, and show notes.
                Update them any time before you create your episode.
              </p>
              <p>
                Skip for now if you’re unsure—we’ll remind you before publishing and you can fill them in from Automations.
              </p>
            </div>
          </details>
        </CardContent>
      </Card>
      )}

      <Card className="border-2 border-dashed border-gray-200 bg-white">
        <CardContent className="p-8">
          <div
            className="border-2 border-dashed rounded-xl p-12 text-center"
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
          >
            {(uploadedFile || uploadedFilename) ? (
              <div className="space-y-6">
                <FileAudio className="w-16 h-16 mx-auto text-green-600" />
                <p className={`text-xl font-semibold ${isUploading ? 'text-slate-600' : 'text-green-600'}`}>
                  {isUploading ? 'Uploading your audio…' : 'File Ready!'}
                </p>
                {uploadedFile && (
                  <p className="text-gray-600">
                    {formatDisplayName(uploadedFile, { fallback: uploadedFile.name || 'Audio file' })}
                  </p>
                )}
                {!uploadedFile && uploadedFilename && (
                  <>
                    <p className="text-gray-600">
                      Server file: {formatDisplayName(uploadedFilename, { fallback: 'Audio file' })}
                    </p>
                    <p className="text-xs text-muted-foreground">We found your previously uploaded audio — you can continue without re-uploading.</p>
                  </>
                )}
              </div>
            ) : (
              <div className="space-y-6">
                <Mic className="w-16 h-16 mx-auto text-gray-400" />
                <p className="text-2xl font-semibold text-gray-700">Drag your audio file here</p>
                <p className="text-gray-500">or</p>
                <Button
                  onClick={() => fileInputRef.current?.click()}
                  size="lg"
                  className="text-white"
                  style={{ backgroundColor: '#2C3E50' }}
                  disabled={isUploading}
                >
                  {isUploading ? (
                    <>
                      <Loader2 className="w-5 h-5 mr-2 animate-spin" /> Uploading...
                    </>
                  ) : (
                    <>
                      <Upload className="w-5 h-5 mr-2" /> Choose Audio File
                    </>
                  )}
                </Button>
              </div>
            )}
            {isUploading && (
              <div className="mt-6 space-y-2">
                <div className="h-2 w-full rounded-full bg-slate-200 overflow-hidden">
                  <div
                    className="h-full bg-slate-600 transition-all duration-200"
                    style={{ width: `${Math.min(100, Math.max(5, typeof uploadProgress === 'number' ? uploadProgress : 5))}%` }}
                  />
                </div>
                <p className="text-sm text-slate-600">
                  Uploading{typeof uploadProgress === 'number' ? `… ${uploadProgress}%` : '…'}
                </p>
              </div>
            )}
            <input ref={fileInputRef} type="file" accept="audio/*" onChange={handleFileInput} className="hidden" />
          </div>
          {/* Show deletion notice for processed episodes */}
          {(uploadedFile || uploadedFilename) && episodeStatus && ['processed', 'published', 'scheduled'].includes(String(episodeStatus).toLowerCase()) && (
            <div className="mt-4 rounded-md border border-red-200 bg-red-50 p-3 text-center">
              <p className="text-sm font-semibold text-red-700">
                This episode has successfully processed. You may delete this file.
              </p>
            </div>
          )}
        </CardContent>
      </Card>

      {(uploadedFile || uploadedFilename) && (
        <Card className="border border-slate-200 bg-slate-50">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg text-slate-900">Before we customize anything…</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {hasPendingIntents ? (
              <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
                We need your answer about {pendingLabelText}.
              </div>
            ) : (
              <div className="text-sm text-slate-600">
                These answers are saved automatically and you can change them later.
              </div>
            )}
            {typeof onEditAutomations === 'function' && hasPendingIntents && (
              <div className="text-right">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onEditAutomations}
                  className="text-slate-600 hover:text-slate-900"
                >
                  Answer now
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {showPrecheckCard && (
        <div
          className={`rounded-md border p-4 text-sm ${minutesBlocking ? 'border-red-300 bg-red-50 text-red-700' : 'border-slate-200 bg-slate-50 text-slate-700'}`}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold">Processing minutes check</span>
            {minutesPrecheckPending ? (
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            ) : minutesBlocking ? (
              <AlertTriangle className="h-4 w-4" aria-hidden="true" />
            ) : null}
          </div>
          <div className="mt-2 space-y-2">
            {minutesPrecheckPending && <p>Checking your remaining processing minutes…</p>}
            {!minutesPrecheckPending && minutesPrecheckError && (
              <p className="text-amber-700">{minutesPrecheckError}</p>
            )}
            {!minutesPrecheckPending && !minutesPrecheckError && (
              <>
                <p>{minutesBlocking ? blockingMessage : 'This episode fits within your available processing minutes.'}</p>
                {totalDurationText && (
                  <p>
                    Estimated length <strong>{totalDurationText}</strong>
                    {staticDurationText ? ` (template adds ${staticDurationText})` : ''}.
                  </p>
                )}
                {!totalDurationText && audioDurationText && (
                  <p>Uploaded audio length <strong>{audioDurationText}</strong>.</p>
                )}
                {requiredMinutesText && (
                  <p>Requires approximately <strong>{requiredMinutesText}</strong> of processing time.</p>
                )}
                {remainingMinutesText && (
                  <p>Your plan has <strong>{remainingMinutesText}</strong> remaining.</p>
                )}
              </>
            )}
          </div>
        </div>
      )}

      <div className="flex flex-col gap-4 pt-8 sm:flex-row sm:items-center sm:justify-between">
        <Button onClick={onBack} variant="outline" size="lg">
          <ArrowLeft className="w-5 h-5 mr-2" />Back to Templates
        </Button>
        {(uploadedFile || uploadedFilename) && (
          <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:items-center sm:justify-end">
            <div className="flex justify-end gap-2">
              <Button
                onClick={handleContinue}
                size="lg"
                className="text-white"
                style={{ backgroundColor: '#2C3E50' }}
                disabled={
                  isUploading
                  || !(uploadedFile || uploadedFilename)
                  || minutesPrecheckPending
                  || minutesBlocking
                }
              >
                Continue
              </Button>
            </div>
            {minutesPrecheckPending && (
              <p className="text-xs text-slate-600 text-right">Waiting for processing minutes check…</p>
            )}
            {minutesBlocking && !minutesPrecheckPending && (
              <p className="text-xs text-red-600 text-right">{blockingMessage}</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
