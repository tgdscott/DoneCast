import React from 'react';
import { Button } from '../../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { Textarea } from '../../ui/textarea';
import { ArrowLeft, Loader2, Wand2, Lightbulb, ListChecks, AlertTriangle, RefreshCw } from 'lucide-react';
import { TagInput } from '../AudioCleanupSettings';
import GuestSelector from './GuestSelector';

export default function StepEpisodeDetails({
  token,
  podcastId,
  episodeDetails,
  transcriptReady,
  isAssembling,
  isPublishing,
  isAiTitleBusy,
  isAiDescBusy,
  publishMode,
  publishVisibility,
  scheduleDate,
  scheduleTime,
  canProceed,
  blockingQuota,
  missingTitle,
  missingEpisodeNumber,
  onBack,
  onAssemble,
  onDetailsChange,
  onSuggestTitle,
  onRefineTitle,
  onSuggestDescription,
  onRefineDescription,
  onPublishModeChange,
  onPublishVisibilityChange,
  onScheduleDateChange,
  onScheduleTimeChange,
  minutesPrecheck = null,
  minutesPrecheckPending = false,
  minutesPrecheckError = null,
  minutesBlocking = false,
  minutesBlockingMessage = '',
  minutesRequired = null,
  minutesRemaining = null,
  formatDuration = () => null,
  audioDurationSec: audioDurationSecProp = null,
  onRetryPrecheck = null,
  aiGeneratedFields = { title: false, description: false, tags: false },
}) {
  const audioDurationSec = audioDurationSecProp;
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
  const showPrecheckNotice = minutesPrecheckPending || minutesPrecheck || minutesPrecheckError;
  const blockingMessage = minutesBlockingMessage || 'Not enough processing minutes remain to assemble this episode.';

  return (
    <div className="space-y-8">
      <CardHeader className="text-center">
        <CardTitle style={{ color: '#2C3E50' }}>Step 5: Episode Details &amp; Scheduling</CardTitle>
      </CardHeader>
      <Card className="border border-slate-200 bg-slate-50" data-tour-id="episode-details-guide">
        <CardHeader className="flex flex-col gap-1 pb-2 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="text-base flex items-center gap-2 text-slate-800">
            <Lightbulb className="h-4 w-4 text-amber-500" aria-hidden="true" />
            Publishing checklist
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-slate-700">
          <p>
            This is the last stop before you assemble or publish. Use it as a quick final review so you never miss a required
            field.
          </p>
          <ul className="space-y-2">
            <li className="flex items-start gap-2">
              <ListChecks className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" aria-hidden="true" />
              <span><strong>Title &amp; description</strong>: keep keywords up front. Try the AI helpers for a punchy first draft.</span>
            </li>
            <li className="flex items-start gap-2">
              <ListChecks className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" aria-hidden="true" />
              <span><strong>Numbering &amp; tags</strong>: confirm season/episode numbers and add 3–5 tags so auto-generated show notes stay relevant.</span>
            </li>
            <li className="flex items-start gap-2">
              <ListChecks className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" aria-hidden="true" />
              <span><strong>Scheduling</strong>: choosing “Schedule” opens the calendar—pick a local date/time and we’ll convert it to UTC for you.</span>
            </li>
          </ul>
          <p className="text-xs text-slate-500">
            Need to brainstorm? The{' '}
            <a
              href="https://www.podcastplusplus.com/guide"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-600 hover:text-blue-800 underline"
            >
              front-page guide
            </a>
            {' '}has examples for titles, calls-to-action, and launch checklists.
          </p>
        </CardContent>
      </Card>
      {/* CRITICAL ERROR: Transcript not ready - MUST be visible! */}
      {!transcriptReady && (
        <div className="rounded-md border border-red-400 bg-red-50 p-4 text-sm text-red-800">
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold text-red-900">❌ Transcript Not Ready - Assembly Blocked</span>
            <AlertTriangle className="h-5 w-5 text-red-600" aria-hidden="true" />
          </div>
          <div className="mt-3 space-y-2">
            <p className="font-medium">Your audio file is still being transcribed. You cannot proceed until this completes.</p>
            <p><strong>What's a transcript?</strong> We convert your audio to text so we can apply voice cleaning, remove filler words, and enable AI features.</p>
            <p><strong>Why is it not ready?</strong> Transcription usually takes 10-60 seconds after upload, depending on file length. If it's been longer, check for errors in the Bug Reports page.</p>
            <p className="text-xs mt-2 text-red-700">If you just uploaded this file, please wait a moment and refresh the page. If the problem persists after 2-3 minutes, contact support.</p>
          </div>
        </div>
      )}

      {showPrecheckNotice && (
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
      <Card className="border-0 shadow-lg bg-white">
        <CardContent className="p-6 space-y-6">
          <p className="text-[13px] text-slate-500">It may take a few seconds for the AI fields to autofill.</p>
          <div className="grid md:grid-cols-2 gap-6">
            <div className="col-span-2 md:col-span-1">
              <Label htmlFor="title">Episode Title *</Label>
              <Input
                id="title"
                placeholder="e.g., The Future of AI"
                value={episodeDetails.title}
                onChange={(event) => onDetailsChange('title', event.target.value)}
              />
              {aiGeneratedFields.title && (
                <p className="text-xs text-slate-500 mt-1">AI-suggested — click to edit or replace.</p>
              )}
              <div className="mt-2 flex gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={onSuggestTitle}
                  disabled={!transcriptReady || isAssembling || isPublishing || isAiTitleBusy}
                >
                  <Wand2 className="w-4 h-4 mr-1" /> Suggest Title
                </Button>
                {!transcriptReady && (
                  <span className="text-xs text-gray-500 flex items-center gap-1">
                    <Loader2 className="w-3 h-3 animate-spin" /> Waiting for transcript…
                  </span>
                )}
              </div>
            </div>
          </div>

          <div className="grid md:grid-cols-3 gap-6">
            <div>
              <Label htmlFor="season">Season Number *</Label>
              <Input
                id="season"
                type="number"
                placeholder="e.g., 1"
                value={episodeDetails.season}
                onChange={(event) => onDetailsChange('season', event.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="episodeNumber">Episode Number *</Label>
              <Input
                id="episodeNumber"
                type="number"
                placeholder="e.g., 12"
                value={episodeDetails.episodeNumber}
                onChange={(event) => onDetailsChange('episodeNumber', event.target.value)}
              />
            </div>
            <div className="flex flex-col pt-6 gap-2">
              <div className="flex items-center gap-2">
                <input
                  id="explicitFlag"
                  type="checkbox"
                  checked={!!episodeDetails.is_explicit}
                  onChange={(event) => onDetailsChange('is_explicit', event.target.checked)}
                />
                <Label htmlFor="explicitFlag" className="cursor-pointer">
                  Explicit
                </Label>
              </div>
              <p className="text-xs text-gray-500 ml-6">
                Enable this option if your recording contains explicit content. This information is also exported to your RSS / iTunes feeds.
              </p>
            </div>
          </div>

          <div>
            <Label htmlFor="description">Episode Description</Label>
            <Textarea
              id="description"
              placeholder="Describe what this episode is about..."
              className="min-h-[120px]"
              value={episodeDetails.description}
              onChange={(event) => onDetailsChange('description', event.target.value)}
            />
            {aiGeneratedFields.description && (
              <p className="text-xs text-slate-500 mt-1">AI-suggested — click to edit or replace.</p>
            )}
            <div className="mt-2 flex gap-2">
              <Button
                type="button"
                variant="secondary"
                onClick={onSuggestDescription}
                disabled={!transcriptReady || isAssembling || isPublishing || isAiDescBusy}
              >
                <Wand2 className="w-4 h-4 mr-1" /> Suggest New Description
              </Button>
              {episodeDetails.description && episodeDetails.description.trim() && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={onRefineDescription}
                  disabled={!transcriptReady || isAssembling || isPublishing || isAiDescBusy}
                >
                  <RefreshCw className="w-4 h-4 mr-1" /> Refine Current
                </Button>
              )}
              {!transcriptReady && (
                <span className="text-xs text-gray-500 flex items-center gap-1">
                  <Loader2 className="w-3 h-3 animate-spin" /> Waiting for transcript…
                </span>
              )}
            </div>
          </div>

          <div>
            <Label htmlFor="tags">Tags (max 20)</Label>
            <TagInput
              values={episodeDetails.tags ? episodeDetails.tags.split(',').map(t => t.trim()).filter(Boolean) : []}
              onChange={(tagsArray) => {
                onDetailsChange('tags', tagsArray.join(', '));
              }}
              placeholder="Type a tag and press Enter"
            />
            {aiGeneratedFields.tags && (
              <p className="text-xs text-slate-500 mt-1">AI-suggested — click to edit or replace.</p>
            )}
            <p className="text-xs text-gray-500 mt-1">Each tag ≤30 chars. Enforced on publish.</p>
          </div>

          {/* Guest Selector */}
          <div className="pt-2">
            <GuestSelector
              token={token}
              podcastId={podcastId}
              initialGuests={episodeDetails.guests || []}
              onGuestsChange={(guests) => onDetailsChange('guests', guests)}
            />
          </div>

          <div className="space-y-3 pt-4 border-t">
            <Label className="font-medium">Publish Options</Label>
            <div className="flex flex-col gap-2 text-sm">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="pubmode"
                  value="now"
                  checked={publishMode === 'now'}
                  onChange={() => onPublishModeChange('now')}
                />
                Publish Immediately (after assembly)
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="pubmode"
                  value="draft"
                  checked={publishMode === 'draft'}
                  onChange={() => onPublishModeChange('draft')}
                />
                Save as Draft (no publish)
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="radio"
                  name="pubmode"
                  value="schedule"
                  checked={publishMode === 'schedule'}
                  onChange={() => onPublishModeChange('schedule')}
                />
                Schedule Publish
              </label>
            </div>

            {publishMode === 'schedule' && (
              <div className="grid grid-cols-2 gap-4 text-sm mt-2">
                <div>
                  <label htmlFor="schedule-date" className="text-xs font-medium mb-1 block">
                    Date
                  </label>
                  <input
                    id="schedule-date"
                    aria-label="Schedule date"
                    type="date"
                    className="border rounded p-2 w-full"
                    value={scheduleDate}
                    onChange={(event) => onScheduleDateChange(event.target.value)}
                  />
                </div>
                <div>
                  <label htmlFor="schedule-time" className="text-xs font-medium mb-1 block">
                    Time
                  </label>
                  <input
                    id="schedule-time"
                    aria-label="Schedule time"
                    type="time"
                    step={300}
                    className="border rounded p-2 w-full"
                    value={scheduleTime}
                    onChange={(event) => onScheduleTimeChange(event.target.value)}
                  />
                </div>
                <div className="col-span-2 text-xs text-gray-500">
                  Must be ≥10 minutes in the future. Converted to UTC automatically.
                </div>
              </div>
            )}

            {publishMode === 'now' && (
              <div className="mt-2">
                <span className="text-xs font-medium">Visibility:</span>
                <div className="flex gap-4 mt-1 text-sm">
                  <label className="flex items-center gap-1">
                    <input
                      type="radio"
                      name="vis"
                      value="public"
                      checked={publishVisibility === 'public'}
                      onChange={() => onPublishVisibilityChange('public')}
                    />
                    Public
                  </label>
                  <label className="flex items-center gap-1">
                    <input
                      type="radio"
                      name="vis"
                      value="unpublished"
                      checked={publishVisibility === 'unpublished'}
                      onChange={() => onPublishVisibilityChange('unpublished')}
                    />
                    Private
                  </label>
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-between pt-8">
        <Button onClick={onBack} variant="outline" size="lg">
          <ArrowLeft className="w-5 h-5 mr-2" />Back
        </Button>
        <div className="flex flex-col items-end gap-2">
          <div className="flex gap-2">
            {(minutesBlocking || blockingQuota) && onRetryPrecheck && (
              <Button
                onClick={onRetryPrecheck}
                disabled={minutesPrecheckPending}
                variant="outline"
                size="lg"
                className="px-4"
                title="Refresh quota check (if you just upgraded your plan)"
              >
                <RefreshCw className={`w-5 h-5 ${minutesPrecheckPending ? 'animate-spin' : ''}`} />
              </Button>
            )}
            <Button
              onClick={onAssemble}
              disabled={!canProceed || isAssembling || minutesPrecheckPending || minutesBlocking}
              size="lg"
              className="px-8 py-3 text-lg font-semibold text-white disabled:opacity-70"
              style={{ backgroundColor: '#2C3E50' }}
            >
              {isAssembling ? 'Assembling...' : 'Save and continue'}
              <ArrowLeft className="w-5 h-5 ml-2 rotate-180" />
            </Button>
          </div>
          {(minutesPrecheckPending || !canProceed) && (
            <div className={`text-xs max-w-sm text-right ${minutesBlocking ? 'text-red-600' : minutesPrecheckPending ? 'text-slate-600' : 'text-red-600'}`}>
              {minutesPrecheckPending
                ? 'Waiting for processing minutes check…'
                : minutesBlocking
                  ? blockingMessage
                  : blockingQuota
                    ? 'Quota exceeded – upgrade or wait for reset.'
                    : missingTitle
                      ? 'Enter a title to continue.'
                      : missingEpisodeNumber
                        ? 'Enter an episode number to continue.'
                        : ''}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
