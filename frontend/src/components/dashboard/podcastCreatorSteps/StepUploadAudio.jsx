import React from 'react';
import { Button } from '../../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';
import { Switch } from '../../ui/switch';
import { Loader2, Mic, Upload, ArrowLeft, AlertTriangle, Trash2 } from 'lucide-react';
import { formatDisplayName } from '@/lib/displayNames';
import { formatProgressDetail } from '@/lib/uploadProgress';

const SEGMENT_PLACEHOLDER = 'Audio segment';

export default function StepUploadAudio({
  mainSegments = [],
  uploadedFilename,
  isUploading,
  isBundling = false,
  bundleError = null,
  segmentsDirty = false,
  uploadProgress = null,
  uploadStats = null,
  onFileChange,
  onSegmentRemove = () => {},
  onSegmentProcessingChange = () => {},
  composeSegments = async () => {},
  fileInputRef,
  onBack,
  onNext = () => {},
  onEditAutomations,
  onIntentSubmit,
  pendingIntentLabels = [],
  intents = {},
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
  useAdvancedAudio = false,
  onAdvancedAudioToggle = () => {},
  isAdvancedAudioSaving = false,
}) {
  const audioDurationSec = audioDurationSecProp;
  const hasSegments = Array.isArray(mainSegments) && mainSegments.length > 0;
  const hasMergedAudio = Boolean(uploadedFilename);
  const hasPendingIntents = Array.isArray(pendingIntentLabels) && pendingIntentLabels.length > 0;
  const pendingLabelText = hasPendingIntents ? pendingIntentLabels.join(', ') : '';
  const processingModes = React.useMemo(() => new Set(mainSegments.map(seg => seg.processingMode)), [mainSegments]);
  const showProcessingWarning = processingModes.size > 1;

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
    return minutesFromSeconds(totalSeconds) ?? minutesFromSeconds(mainSeconds) ?? minutesFromSeconds(effectiveAudioSeconds);
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
    requiredMinutesVal != null ? `${requiredMinutesVal} minute${requiredMinutesVal === 1 ? '' : 's'}` : null;
  const remainingMinutesText =
    remainingMinutesDisplay != null ? `${remainingMinutesDisplay} minute${remainingMinutesDisplay === 1 ? '' : 's'}` : null;

  const blockingMessage = minutesBlockingMessage || 'Not enough processing minutes remain to create this episode.';
  const showPrecheckCard = hasMergedAudio && (minutesPrecheckPending || minutesPrecheck || minutesPrecheckError);

  const continueDisabled =
    isUploading ||
    !hasSegments ||
    !hasMergedAudio ||
    isBundling ||
    segmentsDirty ||
    minutesPrecheckPending ||
    minutesBlocking ||
    Boolean(bundleError);

  const queueFilesSequentially = async (fileList) => {
    const files = Array.from(fileList || []);
    for (const file of files) {
      // eslint-disable-next-line no-await-in-loop
      await onFileChange(file);
    }
  };

  const handleFileInput = async (event) => {
    const files = event.target.files;
    if (files?.length) {
      await queueFilesSequentially(files);
      event.target.value = '';
    }
  };

  const handleDrop = async (event) => {
    event.preventDefault();
    const files = event.dataTransfer?.files;
    if (files?.length) {
      await queueFilesSequentially(files);
    }
  };

  const handleContinue = async () => {
    if (!hasSegments) return;
    if (!hasMergedAudio || segmentsDirty) {
      try {
        await composeSegments();
      } catch {
        return;
      }
    }
    if (hasPendingIntents && typeof onEditAutomations === 'function') {
      onEditAutomations();
      return;
    }
    if (typeof onIntentSubmit === 'function') {
      const result = await onIntentSubmit(intents);
      if (result === false || result === true) return;
    }
    onNext();
  };

  return (
    <div className="space-y-8">
      <CardHeader className="text-center">
        <CardTitle style={{ color: '#2C3E50' }}>
          {wasRecorded ? 'Step 2: Your Recording' : 'Step 2: Add Main Content Segments'}
        </CardTitle>
        <p className="text-sm text-slate-500 mt-2">Upload each segment separately so we can stitch and process them in the right order.</p>
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
        <CardContent className="p-8">
          <div
            className="border-2 border-dashed rounded-xl p-10 text-center"
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
          >
            <Mic className="w-16 h-16 mx-auto text-gray-400" />
            <div className="mt-6 space-y-4">
              <p className="text-2xl font-semibold text-gray-700">Drag audio files here to add segments</p>
              <p className="text-gray-500 text-sm">Upload as many recordings as you need—we’ll combine them for you.</p>
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
                    <Upload className="w-5 h-5 mr-2" /> Choose Audio Files
                  </>
                )}
              </Button>
              <p className="text-xs text-slate-500">You can also drop multiple files at once.</p>
            </div>
            <input ref={fileInputRef} type="file" accept="audio/*" multiple onChange={handleFileInput} className="hidden" />
          </div>
        </CardContent>
      </Card>

      {uploadedFilename && episodeStatus && ['processed', 'published', 'scheduled'].includes(String(episodeStatus).toLowerCase()) && (
        <div className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          This episode has already been processed. You can safely delete the previous master if you need to reclaim storage.
        </div>
      )}

      <Card className="border border-slate-200 bg-white">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg text-slate-900">Segment queue</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {hasSegments ? (
            mainSegments.map((segment, index) => (
              <div
                key={segment.id || segment.mediaItemId || index}
                className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="text-left">
                  <p className="font-semibold text-slate-900">
                    {index + 1}. {formatDisplayName(segment.friendlyName || segment.filename, { fallback: SEGMENT_PLACEHOLDER })}
                  </p>
                  <p className="text-xs text-slate-500">
                    {segment.processingMode === 'advanced' ? 'Advanced mastering' : 'Standard pipeline'}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-600">Advanced</span>
                    <Switch
                      checked={segment.processingMode === 'advanced'}
                      onCheckedChange={(checked) => onSegmentProcessingChange(segment.id, checked ? 'advanced' : 'standard')}
                      disabled={isBundling}
                      aria-label="Toggle advanced processing"
                    />
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => onSegmentRemove(segment.id)}
                    disabled={isBundling}
                    className="text-slate-500 hover:text-red-600"
                  >
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                    <span className="sr-only">Remove</span>
                  </Button>
                </div>
              </div>
            ))
          ) : (
            <p className="text-sm text-slate-500 text-center py-4">No segments added yet.</p>
          )}
        </CardContent>
      </Card>

      {hasSegments && (
        <Card className="border border-slate-200 bg-white">
          <CardHeader className="pb-3">
            <CardTitle className="text-lg text-slate-900">Default processing for new uploads</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center justify-between gap-4 flex-col sm:flex-row sm:items-center">
              <div className="space-y-1">
                <p className="text-sm font-medium text-slate-900">Use Advanced Audio Processing</p>
                <p className="text-xs text-slate-600">
                  This sets the default pipeline for future segments. You can still override each segment above.
                </p>
                {isAdvancedAudioSaving && (
                  <p className="text-xs text-slate-500">Saving your preference…</p>
                )}
              </div>
              <Switch
                id="advanced-audio-toggle"
                checked={useAdvancedAudio}
                onCheckedChange={(checked) => onAdvancedAudioToggle(Boolean(checked))}
                disabled={isAdvancedAudioSaving}
              />
            </div>
          </CardContent>
        </Card>
      )}

      {showProcessingWarning && (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          Mixed processing detected. Segments mastered with different pipelines may sound inconsistent.
        </div>
      )}

      {isBundling && (
        <div className="rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800 flex items-center gap-3">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          <span>Combining segments into a single master file…</span>
        </div>
      )}

      {!isBundling && segmentsDirty && (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
          Segment changes detected. We’ll rebuild the master file automatically—hang tight.
        </div>
      )}

      {bundleError && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700 flex items-center justify-between gap-3">
          <span>{bundleError}</span>
          <Button size="sm" variant="outline" onClick={() => composeSegments()} disabled={isBundling}>
            Retry merge
          </Button>
        </div>
      )}

      {hasMergedAudio && (
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
        {hasSegments && (
          <div className="flex w-full flex-col gap-3 sm:w-auto sm:flex-row sm:items-center sm:justify-end">
            <div className="flex justify-end gap-2">
              <Button
                onClick={handleContinue}
                size="lg"
                className="text-white"
                style={{ backgroundColor: '#2C3E50' }}
                disabled={continueDisabled}
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

