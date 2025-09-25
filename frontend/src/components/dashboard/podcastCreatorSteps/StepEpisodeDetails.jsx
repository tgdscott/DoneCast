import React from 'react';
import { Button } from '../../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';
import { Input } from '../../ui/input';
import { Label } from '../../ui/label';
import { Textarea } from '../../ui/textarea';
import { ArrowLeft, Loader2, Wand2, Lightbulb, ListChecks } from 'lucide-react';

export default function StepEpisodeDetails({
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
  onSuggestDescription,
  onPublishModeChange,
  onPublishVisibilityChange,
  onScheduleDateChange,
  onScheduleTimeChange,
}) {
  return (
    <div className="space-y-8">
      <CardHeader className="text-center">
        <CardTitle style={{ color: '#2C3E50' }}>Step 5: Episode Details &amp; Scheduling</CardTitle>
      </CardHeader>
      <Card className="border border-slate-200 bg-slate-50" data-tour-id="episode-details-guide">
        <CardHeader className="flex flex-col gap-1 pb-2 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="text-base flex items-center gap-2 text-slate-800">
            <Lightbulb className="h-4 w-4 text-amber-500" aria-hidden="true" />
            Final quick check
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm text-slate-700">
          <p>
            We already drafted these details from your recording. Give them a glance and adjust anything you want before you
            assemble or publish.
          </p>
          <ul className="space-y-2">
            <li className="flex items-start gap-2">
              <ListChecks className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" aria-hidden="true" />
              <span><strong>Title &amp; description</strong>: happy with what you see? Great. Want a new take? Tap the AI buttons for an instant rewrite.</span>
            </li>
            <li className="flex items-start gap-2">
              <ListChecks className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" aria-hidden="true" />
              <span><strong>Episode numbers &amp; explicit flag</strong>: confirm they match what your host expects.</span>
            </li>
            <li className="flex items-start gap-2">
              <ListChecks className="mt-0.5 h-4 w-4 flex-shrink-0 text-primary" aria-hidden="true" />
              <span><strong>Scheduling</strong>: choose “Schedule” to pick your local date and time—we handle the background math.</span>
            </li>
          </ul>
          <p className="text-xs text-slate-500">Tags are optional. Add them if your host uses them, otherwise feel free to leave them blank.</p>
        </CardContent>
      </Card>
      <Card className="border-0 shadow-lg bg-white">
        <CardContent className="p-6 space-y-6">
          <div className="grid md:grid-cols-2 gap-6">
            <div className="col-span-2 md:col-span-1">
              <Label htmlFor="title">Episode Title *</Label>
              <Input
                id="title"
                placeholder="e.g., The Future of AI"
                value={episodeDetails.title}
                onChange={(event) => onDetailsChange('title', event.target.value)}
              />
              <div className="mt-2 flex gap-2">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={onSuggestTitle}
                  disabled={!transcriptReady || isAssembling || isPublishing || isAiTitleBusy}
                >
                  <Wand2 className="w-4 h-4 mr-1" /> AI Suggest Title
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
            <div className="flex items-center pt-6 gap-2">
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
            <div className="mt-2 flex gap-2">
              <Button
                type="button"
                variant="secondary"
                onClick={onSuggestDescription}
                disabled={!transcriptReady || isAssembling || isPublishing || isAiDescBusy}
              >
                <Wand2 className="w-4 h-4 mr-1" /> AI Suggest Description
              </Button>
              {!transcriptReady && (
                <span className="text-xs text-gray-500 flex items-center gap-1">
                  <Loader2 className="w-3 h-3 animate-spin" /> Waiting for transcript…
                </span>
              )}
            </div>
          </div>

          <div>
            <Label htmlFor="tags">Tags (comma separated, max 20)</Label>
            <Textarea
              id="tags"
              placeholder="tag1, tag2"
              className="min-h-[64px]"
              value={episodeDetails.tags || ''}
              onChange={(event) => onDetailsChange('tags', event.target.value)}
            />
            <p className="text-xs text-gray-500 mt-1">Each tag ≤30 chars. Enforced on publish.</p>
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
        <div className="flex flex-col items-end">
          <Button
            onClick={onAssemble}
            disabled={!canProceed || isAssembling}
            size="lg"
            className="px-8 py-3 text-lg font-semibold text-white disabled:opacity-70"
            style={{ backgroundColor: '#2C3E50' }}
          >
            {isAssembling ? 'Assembling...' : 'Save and continue'}
            <ArrowLeft className="w-5 h-5 ml-2 rotate-180" />
          </Button>
          {!canProceed && (
            <div className="text-xs text-red-600 mt-2 max-w-sm text-right">
              {blockingQuota
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
