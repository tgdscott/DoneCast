import React from 'react';
import { ArrowLeft, ArrowUp, ArrowDown, Lightbulb, AlertTriangle, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '../../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '../../ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '../../ui/alert-dialog';
import { Label } from '../../ui/label';
import { Textarea } from '../../ui/textarea';
import { formatDisplayName, isUuidLike } from '@/lib/displayNames';

const SEGMENT_PLACEHOLDER = 'Audio segment';

export default function StepCustomizeSegments({
  selectedTemplate,
  mediaLibrary,
  mainSegments = [],
  uploadedAudioLabel,
  ttsValues,
  onTtsChange,
  onBack,
  onNext,
  onOpenVoicePicker,
  voiceNameById,
  voicesLoading,
  segmentsDirty = false,
  isBundlingSegments = false,
  bundleError = null,
  onReorderSegments = () => { },
  onComposeSegments = () => { },
}) {
  React.useEffect(() => {
    try {
      console.debug('[StepCustomizeSegments] selectedTemplate at render:', {
        id: selectedTemplate?.id,
        name: selectedTemplate?.name,
        segmentsLength: Array.isArray(selectedTemplate?.segments) ? selectedTemplate.segments.length : 0,
        rawSegments: selectedTemplate?.segments,
      });
    } catch (_) { }
  }, [selectedTemplate]);

  const [isGuideOpen, setIsGuideOpen] = React.useState(false);
  const [showValidation, setShowValidation] = React.useState(false);
  const [showBlankWarning, setShowBlankWarning] = React.useState(false);

  const bundleBlocking = Boolean(segmentsDirty || isBundlingSegments || bundleError);

  const computeSegmentKey = React.useCallback((segment, index) => {
    if (segment?.id !== undefined && segment?.id !== null) return segment.id;
    if (segment?.source?.prompt_id !== undefined && segment?.source?.prompt_id !== null) {
      return segment.source.prompt_id;
    }
    if (segment?.slug) return segment.slug;
    if (segment?.name) return segment.name;
    return `segment-${index}`;
  }, []);

  const ttsSegmentsWithKey = React.useMemo(() => {
    const segments = Array.isArray(selectedTemplate?.segments) && selectedTemplate.segments.length
      ? selectedTemplate.segments
      : [{ segment_type: 'content', source: { source_type: 'content' } }];
    return segments
      .map((segment, index) => ({ segment, index, key: computeSegmentKey(segment, index) }))
      .filter(({ segment }) => segment?.source?.source_type === 'tts');
  }, [selectedTemplate?.segments, computeSegmentKey]);

  const missingSegmentKeys = React.useMemo(() => {
    // TTS segments are OPTIONAL - users don't need to fill them if they don't want them
    // Return empty array so nothing is "missing" - allow continuation regardless
    return [];
  }, [ttsSegmentsWithKey, ttsValues]);

  const missingKeysSet = React.useMemo(() => new Set(missingSegmentKeys), [missingSegmentKeys]);
  // Allow continue if: (1) no TTS segments exist, OR (2) all TTS segments have scripts
  const canContinue = ttsSegmentsWithKey.length === 0 || missingSegmentKeys.length === 0;

  const renderSegmentContent = React.useCallback(
    (segment, { fieldId, isMissing, promptKey }) => {
      if (segment.segment_type === 'content') {
        const contentLabel = (uploadedAudioLabel && uploadedAudioLabel.trim()) || 'Segments not ready yet';
        return (
          <div className="mt-2 bg-blue-50 p-3 rounded-md">
            <p className="text-gray-700 font-semibold">{contentLabel}</p>
            {contentLabel === 'Segments not ready yet' && (
              <p className="text-xs text-gray-500 mt-1">
                Go back to Step 2 to upload or re-order your main content segments.
              </p>
            )}
          </div>
        );
      }

      if (segment.source.source_type === 'tts') {
        const voiceId = segment?.source?.voice_id || '';
        const resolvedFriendly = voiceNameById[voiceId];
        const providedLabel = segment?.source?.voice_name || segment?.source?.voice_label;

        const baseVoiceLabel =
          (!voiceId || voiceId === 'default')
            ? 'Default voice'
            : resolvedFriendly && !isUuidLike(resolvedFriendly)
              ? resolvedFriendly
              : providedLabel && !isUuidLike(providedLabel)
                ? providedLabel
                : 'AI Voice'; // Generic fallback while resolving - NEVER show raw UUID
        const isResolvingVoice = Boolean(
          voicesLoading &&
          voiceId &&
          voiceId !== 'default' &&
          !resolvedFriendly &&
          (!providedLabel || isUuidLike(providedLabel))
        );
        const voiceTitle =
          resolvedFriendly && !isUuidLike(resolvedFriendly)
            ? resolvedFriendly
            : providedLabel && !isUuidLike(providedLabel)
              ? providedLabel
              : voiceId && voiceId !== 'default'
                ? formatDisplayName(voiceId, { fallback: '' }) || undefined
                : undefined;
        const value = ttsValues?.[promptKey] || '';
        const errorMessageId = isMissing ? `${fieldId}-error` : undefined;
        return (
          <div className="mt-4">
            <div className="mt-2 flex items-center justify-between">
              <span className="text-xs text-gray-500" title={voiceTitle}>
                Voice: {baseVoiceLabel}
                {isResolvingVoice ? '…' : ''}
              </span>
              <Button size="sm" variant="outline" onClick={() => onOpenVoicePicker(segment.id || promptKey)}>
                Change voice
              </Button>
            </div>
            <Label htmlFor={fieldId} className="text-sm font-medium text-gray-700 mb-2 block">
              {segment.source.text_prompt || 'AI voice script'} <span className="text-gray-400 font-normal">(optional)</span>
            </Label>
            <Textarea
              id={fieldId}
              placeholder="Leave blank to skip this segment, or enter text to include it..."
              className={cn(
                'min-h-[100px] resize-none text-base bg-white',
                isMissing && 'border-red-500 focus-visible:ring-red-500'
              )}
              value={value}
              aria-invalid={isMissing}
              aria-describedby={errorMessageId}
              onChange={(event) => onTtsChange(promptKey, event.target.value)}
            />
            {isMissing ? (
              <p id={errorMessageId} className="mt-2 text-sm text-red-600">
                Please provide the script for this AI segment before continuing.
              </p>
            ) : null}
          </div>
        );
      }

      if (segment.source.source_type === 'static') {
        const mediaItem = mediaLibrary.find((item) => item.filename.endsWith(segment.source.filename));
        const friendlyName =
          mediaItem
            ? formatDisplayName(mediaItem, { fallback: 'Audio clip' }) || 'Audio clip'
            : formatDisplayName(segment.source.filename, { fallback: 'Audio clip' }) || 'Audio clip';
        return <p className="text-gray-600 mt-2">{friendlyName}</p>;
      }

      return <p className="text-red-500 mt-2">Unknown segment source type</p>;
    },
    [
      mediaLibrary,
      onOpenVoicePicker,
      onTtsChange,
      ttsValues,
      uploadedAudioLabel,
      voiceNameById,
      voicesLoading,
    ]
  );

  const handleContinue = React.useCallback(
    (event) => {
      if (bundleBlocking) {
        event?.preventDefault?.();
        event?.stopPropagation?.();
        return;
      }

      // Check for empty TTS segments
      // We want to warn the user if they're leaving AI scripts blank, as they might expect generation
      const blankSegments = ttsSegmentsWithKey.filter(({ key }) => {
        const val = ttsValues?.[key];
        return !val || !val.trim();
      });

      if (blankSegments.length > 0) {
        setShowBlankWarning(true);
        return;
      }

      onNext();
    },
    [bundleBlocking, onNext, ttsSegmentsWithKey, ttsValues]
  );

  React.useEffect(() => {
    if (canContinue) {
      setShowValidation(false);
    }
  }, [canContinue]);

  return (
    <div className="space-y-8">
      <CardHeader className="text-center">
        <CardTitle style={{ color: '#2C3E50' }}>Step 3: Customize Your Episode</CardTitle>
        <p className="text-md text-gray-500 pt-2">Review the structure and fill in the required text for any AI-generated segments.</p>
      </CardHeader>

      <Card className="border border-slate-200 bg-white">
        <CardHeader className="pb-3">
          <CardTitle className="text-lg text-slate-900">Main content order</CardTitle>
          <p className="text-sm text-slate-500">Intro and outro stay in place—reorder only affects your uploaded segments.</p>
        </CardHeader>
        <CardContent className="space-y-3">
          {Array.isArray(mainSegments) && mainSegments.length ? (
            mainSegments.map((segment, index) => (
              <div
                key={segment.id || segment.mediaItemId || index}
                className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between"
              >
                <div>
                  <p className="font-semibold text-slate-900">
                    {index + 1}. {formatDisplayName(segment.friendlyName || segment.filename, { fallback: SEGMENT_PLACEHOLDER })}
                  </p>
                  <p className="text-xs text-slate-500">{segment.processingMode === 'advanced' ? 'Advanced mastering' : 'Standard pipeline'}</p>
                </div>
                <div className="flex items-center gap-2 self-start sm:self-auto">
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => onReorderSegments(index, index - 1)}
                    disabled={index === 0}
                  >
                    <ArrowUp className="h-4 w-4" aria-hidden="true" />
                    <span className="sr-only">Move up</span>
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => onReorderSegments(index, index + 1)}
                    disabled={index === mainSegments.length - 1}
                  >
                    <ArrowDown className="h-4 w-4" aria-hidden="true" />
                    <span className="sr-only">Move down</span>
                  </Button>
                </div>
              </div>
            ))
          ) : (
            <p className="text-sm text-slate-500 text-center py-2">No uploaded segments yet.</p>
          )}

          {isBundlingSegments && (
            <div className="rounded-md border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800 flex items-center gap-3">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              <span>Rebuilding your master audio…</span>
            </div>
          )}
          {!isBundlingSegments && segmentsDirty && (
            <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              Segment order changed. We’ll merge the new order automatically—please wait.
            </div>
          )}
          {bundleError && (
            <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700 flex items-center justify-between gap-3">
              <span>{bundleError}</span>
              <Button size="sm" variant="outline" onClick={onComposeSegments} disabled={isBundlingSegments}>
                Retry merge
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <Dialog open={isGuideOpen} onOpenChange={setIsGuideOpen}>
          <DialogTrigger asChild>
            <Button
              variant="outline"
              size="sm"
              data-tour-id="episode-segment-guide"
              className="flex items-center gap-2"
            >
              <Lightbulb className="h-4 w-4 text-amber-500" aria-hidden="true" />
              Segment tips
            </Button>
          </DialogTrigger>
          <DialogContent className="max-w-2xl">
            <DialogHeader className="text-left">
              <DialogTitle className="flex items-center gap-2 text-slate-900">
                <Lightbulb className="h-5 w-5 text-amber-500" aria-hidden="true" />
                How these segments play out
              </DialogTitle>
            </DialogHeader>
            <div className="py-4 text-slate-700">
              Tips coming soon
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <Card className="border-0 shadow-lg bg-white">
        <CardContent className="p-6 space-y-4">
          {/* Always render an effective segments list. If selectedTemplate is missing
              or its segments array is empty (server-side issue), fall back to a
              single content segment so the UI remains usable. */}
          {
            (Array.isArray(selectedTemplate?.segments) && selectedTemplate.segments.length
              ? selectedTemplate.segments
              : [{ segment_type: 'content', source: { source_type: 'content' } }]
            ).map((segment, index) => {
              const promptKey = computeSegmentKey(segment, index);
              const fieldId = segment?.id !== undefined && segment?.id !== null ? String(segment.id) : String(promptKey);
              const isMissing = showValidation && missingKeysSet.has(promptKey);
              const reactKey = promptKey ?? `segment-${index}`;

              return (
                <div key={reactKey} className="p-4 rounded-md bg-gray-50 border border-gray-200">
                  <h4 className="font-semibold text-lg text-gray-800 capitalize">
                    {segment.segment_type.replace('_', ' ')}
                  </h4>
                  {renderSegmentContent(segment, { fieldId, isMissing, promptKey })}
                </div>
              );
            })
          }
        </CardContent>
      </Card>

      <div className="flex justify-between pt-8">
        <Button onClick={onBack} variant="outline" size="lg">
          <ArrowLeft className="w-5 h-5 mr-2" />Back to Upload
        </Button>
        <div className="flex flex-col items-end gap-2">
          {bundleBlocking && (
            <p className="text-sm text-slate-500">
              Wait for your segments to finish merging before continuing.
            </p>
          )}
          {!bundleBlocking && !canContinue && (
            <p className={cn('text-sm', showValidation ? 'text-red-600' : 'text-slate-500')}>
              {showValidation
                ? 'Complete the required scripts before continuing.'
                : 'Add text for each AI voice segment to enable Continue.'}
            </p>
          )}
          <Button
            type="button"
            onClick={handleContinue}
            size="lg"
            disabled={!canContinue || bundleBlocking}
            aria-disabled={!canContinue || bundleBlocking}
            className={cn(
              'px-8 py-3 text-lg font-semibold text-white transition-colors',
              (!canContinue || bundleBlocking) && 'cursor-not-allowed opacity-80'
            )}
            style={{ backgroundColor: (!canContinue || bundleBlocking) ? '#94a3b8' : '#2C3E50' }}
          >
            Continue to Details
            <ArrowLeft className="w-5 h-5 ml-2 rotate-180" />
          </Button>
        </div>
      </div>

      <AlertDialog open={showBlankWarning} onOpenChange={setShowBlankWarning}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Empty Voice Scripts?</AlertDialogTitle>
            <AlertDialogDescription>
              You have {ttsSegmentsWithKey.filter(({ key }) => !ttsValues?.[key]?.trim()).length} AI voice segment(s) with no text. These segments will be skipped in the final audio.
              <br /><br />
              Are you sure you want to continue?
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Go back</AlertDialogCancel>
            <AlertDialogAction onClick={onNext}>Continue anyway</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
