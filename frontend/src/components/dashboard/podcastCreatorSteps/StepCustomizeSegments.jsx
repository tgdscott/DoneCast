import React from 'react';
import { ArrowLeft, Lightbulb, ListChecks } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '../../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from '../../ui/dialog';
import { Label } from '../../ui/label';
import { Textarea } from '../../ui/textarea';
import { formatDisplayName, isUuidLike } from '@/lib/displayNames';

export default function StepCustomizeSegments({
  selectedTemplate,
  mediaLibrary,
  uploadedFile,
  uploadedAudioLabel,
  ttsValues,
  onTtsChange,
  onBack,
  onNext,
  onOpenVoicePicker,
  voiceNameById,
  voicesLoading,
}) {
  const [isGuideOpen, setIsGuideOpen] = React.useState(false);
  const [showValidation, setShowValidation] = React.useState(false);

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
    if (!Array.isArray(selectedTemplate?.segments)) return [];
    return selectedTemplate.segments
      .map((segment, index) => ({ segment, index, key: computeSegmentKey(segment, index) }))
      .filter(({ segment }) => segment?.source?.source_type === 'tts');
  }, [selectedTemplate?.segments, computeSegmentKey]);

  const missingSegmentKeys = React.useMemo(() => {
    if (!ttsSegmentsWithKey.length) return [];
    return ttsSegmentsWithKey
      .filter(({ key }) => {
        const value = ttsValues?.[key];
        return !(typeof value === 'string' && value.trim());
      })
      .map(({ key }) => key);
  }, [ttsSegmentsWithKey, ttsValues]);

  const missingKeysSet = React.useMemo(() => new Set(missingSegmentKeys), [missingSegmentKeys]);
  const canContinue = missingSegmentKeys.length === 0;

  const renderSegmentContent = React.useCallback(
    (segment, { fieldId, isMissing, promptKey }) => {
      if (segment.segment_type === 'content') {
        const contentLabel = uploadedAudioLabel || uploadedFile?.name || 'Audio not selected yet';
        return (
          <div className="mt-2 bg-blue-50 p-3 rounded-md">
            <p className="text-gray-700 font-semibold">{contentLabel}</p>
          </div>
        );
      }

      if (segment.source.source_type === 'tts') {
        const voiceId = segment?.source?.voice_id || '';
        const resolvedFriendly = voiceNameById[voiceId];
        const providedLabel = segment?.source?.voice_name || segment?.source?.voice_label || segment?.source?.name;
        const baseVoiceLabel =
          (!voiceId || voiceId === 'default')
            ? 'Default voice'
            : resolvedFriendly && !isUuidLike(resolvedFriendly)
            ? resolvedFriendly
            : providedLabel && !isUuidLike(providedLabel)
            ? providedLabel
            : formatDisplayName(voiceId, { fallback: 'Custom voice' }) || 'Custom voice';
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
              <Button size="sm" variant="outline" onClick={() => onOpenVoicePicker(segment.id)}>
                Change voice
              </Button>
            </div>
            <Label htmlFor={fieldId} className="text-sm font-medium text-gray-700 mb-2 block">
              {segment.source.text_prompt || 'AI voice script'}
            </Label>
            <Textarea
              id={fieldId}
              placeholder="Enter text to be converted to speech..."
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
      uploadedFile,
      voiceNameById,
      voicesLoading,
    ]
  );

  const handleContinue = React.useCallback(
    (event) => {
      if (!canContinue) {
        event?.preventDefault?.();
        event?.stopPropagation?.();
        setShowValidation(true);
        const firstMissingKey = missingSegmentKeys[0];
        if (firstMissingKey !== undefined && typeof window !== 'undefined') {
          const fieldId = String(firstMissingKey);
          window.requestAnimationFrame?.(() => {
            const el = document.getElementById(fieldId);
            if (el) {
              el.scrollIntoView({ behavior: 'smooth', block: 'center' });
              if (typeof el.focus === 'function') {
                try {
                  el.focus({ preventScroll: true });
                } catch (_) {
                  el.focus();
                }
              }
            }
          });
        }
        return;
      }

      onNext();
    },
    [canContinue, missingSegmentKeys, onNext]
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
              <DialogDescription>
                Each block below becomes a chapter in your final episode. Tweak the script, switch voices, or swap in uploaded clips—changes are saved immediately.
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-3 text-sm text-slate-700">
              <ul className="space-y-2">
                <li className="flex items-start gap-2">
                  <ListChecks className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" aria-hidden="true" />
                  <span><strong>Content</strong> anchors your uploaded audio. Intro/outro and ad slots wrap around it automatically.</span>
                </li>
                <li className="flex items-start gap-2">
                  <ListChecks className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" aria-hidden="true" />
                  <span><strong>TTS segments</strong> use the template’s default voice—edit the script here or tap “Change voice” for a different tone.</span>
                </li>
                <li className="flex items-start gap-2">
                  <ListChecks className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" aria-hidden="true" />
                  <span><strong>Static clips</strong> pull from your media library. Upload new stingers or music in the Template step if you need variety.</span>
                </li>
              </ul>
              <p className="text-xs text-slate-500">
                Pro tip: want to reuse this structure later? Save these updates back to the template once you love the flow.
              </p>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      <Card className="border-0 shadow-lg bg-white">
        <CardContent className="p-6 space-y-4">
          {selectedTemplate && selectedTemplate.segments ? (
            selectedTemplate.segments.map((segment, index) => {
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
          ) : (
            <div className="text-center py-12">
              <p className="text-lg text-gray-600">This template has no segments to display.</p>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="flex justify-between pt-8">
        <Button onClick={onBack} variant="outline" size="lg">
          <ArrowLeft className="w-5 h-5 mr-2" />Back to Upload
        </Button>
        <div className="flex flex-col items-end gap-2">
          {!canContinue && (
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
            aria-disabled={!canContinue}
            className={cn(
              'px-8 py-3 text-lg font-semibold text-white transition-colors',
              !canContinue && 'cursor-not-allowed opacity-80'
            )}
            style={{ backgroundColor: canContinue ? '#2C3E50' : '#94a3b8' }}
          >
            Continue to Details
            <ArrowLeft className="w-5 h-5 ml-2 rotate-180" />
          </Button>
        </div>
      </div>
    </div>
  );
}
