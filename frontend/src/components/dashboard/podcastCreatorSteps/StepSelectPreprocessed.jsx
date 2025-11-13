import React, { useMemo, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../../ui/card';
import { Badge } from '../../ui/badge';
import { Button } from '../../ui/button';
import { formatDisplayName } from '@/lib/displayNames';

import { AlertTriangle, FileAudio, Loader2, RefreshCcw, Sparkles, Trash2 } from 'lucide-react';

const formatDate = (iso, timezone = null) => {
  if (!iso) return '—';
  try {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return iso;

    const baseOptions = { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' };
    if (timezone) {
      return new Intl.DateTimeFormat(undefined, { ...baseOptions, timeZone: timezone, timeZoneName: 'short' }).format(date);
    }

    return new Intl.DateTimeFormat(undefined, baseOptions).format(date);
  } catch {
    return iso;
  }
};

const formatExpirationDate = (expiresAt) => {
  if (!expiresAt) return null;
  try {
    // Parse the ISO date string (stored in UTC)
    const date = new Date(expiresAt);
    if (Number.isNaN(date.getTime())) return null;
    
    // The expiration date represents when cleanup will happen (2am PT)
    // We want to show the day BEFORE that date
    // Since the date is stored in UTC, we need to convert to PT first
    // PT is UTC-8 (PST) or UTC-7 (PDT)
    // For simplicity, we'll subtract 1 day from the UTC date
    // This works because the expiration is already aligned to 2am PT boundary
    
    // Create a new date and subtract 1 day
    const expirationDate = new Date(date);
    expirationDate.setUTCDate(expirationDate.getUTCDate() - 1);
    
    // Format as M/D (e.g., 8/12) using UTC date to avoid timezone issues
    const month = expirationDate.getUTCMonth() + 1; // getUTCMonth() returns 0-11
    const day = expirationDate.getUTCDate();
    return {
      formatted: `${month}/${day}`,
      date: expirationDate, // Keep the date object for comparison
      expiresAt: date // Keep original expiration for comparison
    };
  } catch {
    return null;
  }
};

const isExpiringSoon = (expiresAt) => {
  if (!expiresAt) return false;
  try {
    const expirationDate = new Date(expiresAt);
    if (Number.isNaN(expirationDate.getTime())) return false;
    
    const now = new Date();
    const daysUntilExpiration = Math.ceil((expirationDate - now) / (1000 * 60 * 60 * 24));
    
    // Return true if expiration is within 3 days
    return daysUntilExpiration <= 3;
  } catch {
    return false;
  }
};

const formatItemDuration = (seconds) => {
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
  minutesPrecheck = null,
  minutesPrecheckPending = false,
  minutesPrecheckError = null,
  minutesBlocking = false,
  minutesBlockingMessage = '',
  minutesRequired = null,
  minutesRemaining = null,
  formatDuration = () => null,
  audioDurationSec: audioDurationSecProp = null,
  userTimezone = null,
}) {
  const audioDurationSec = audioDurationSecProp;
  const hasPendingIntents = Array.isArray(pendingIntentLabels) && pendingIntentLabels.length > 0;

  const resolvedTimezone = useMemo(() => {
    const validateTimezone = (tz) => {
      if (!tz || typeof tz !== 'string') return null;
      const trimmed = tz.trim();
      if (!trimmed) return null;
      try {
        // Attempt to format with the timezone to ensure it is valid
        new Intl.DateTimeFormat(undefined, { timeZone: trimmed }).format(new Date());
        return trimmed;
      } catch {
        return null;
      }
    };

    const candidate = validateTimezone(userTimezone);
    if (candidate) return candidate;

    try {
      const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
      return validateTimezone(detected);
    } catch {
      return null;
    }
  }, [userTimezone]);

  const formatUploadedAt = useCallback((iso) => formatDate(iso, resolvedTimezone), [resolvedTimezone]);

  const selected = useMemo(
    () => items.find((item) => item.filename === selectedFilename) || null,
    [items, selectedFilename]
  );

  const selectedDisplayName = selected
    ? formatDisplayName(selected, { fallback: 'your upload' }) || 'your upload'
    : 'your upload';

  const counts = selected?.intents || {};
  const flubberCount = Number((counts?.flubber?.count) ?? 0);
  const internCount = Number((counts?.intern?.count) ?? 0);
  const sfxCount = Number((counts?.sfx?.count) ?? 0);
  const hasDetectedAutomations = flubberCount > 0 || internCount > 0 || sfxCount > 0;

  const handleContinue = async () => {
    // If intern/flubber detected, submit intents as "yes" and go to review
    if (hasDetectedAutomations && typeof onIntentSubmit === 'function') {
      // Build intent answers with "yes" for each detected automation
      const intentAnswers = {
        flubber: flubberCount > 0 ? 'yes' : 'no',
        intern: internCount > 0 ? 'yes' : 'no',
        sfx: sfxCount > 0 ? 'yes' : 'no',
      };
      
      // Submit intents - this will trigger the review flow
      await onIntentSubmit(intentAnswers);
      return;
    }
    // Otherwise just proceed to next step
    if (typeof onNext === 'function') onNext();
  };

  const canContinue = !!selected;

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
  const selectedDurationSeconds = toPositiveSeconds(selected?.duration_seconds);
  const effectiveAudioSeconds = toPositiveSeconds(audioDurationSec) ?? selectedDurationSeconds ?? null;

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
  const showPrecheckCard = !!selected && (minutesPrecheckPending || minutesPrecheck || minutesPrecheckError);
  const blockingMessage = minutesBlockingMessage || 'Not enough processing minutes remain to create this episode.';

  return (
    <div className="space-y-6">
      <CardHeader className="flex flex-col gap-3 text-center sm:text-left sm:flex-row sm:items-center sm:justify-between">
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
              <div className="py-10 px-6 text-center text-sm text-slate-600 space-y-4">
                <p className="text-base font-medium text-slate-700">No processed uploads yet</p>
                <p>
                  Upload audio so we can work our magic. Once it’s processed you’ll find it here, ready with transcripts and automations.
                </p>
                {typeof onUpload === 'function' && (
                  <Button onClick={onUpload}>
                    <Upload className="w-4 h-4 mr-2" /> Upload audio
                  </Button>
                )}
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
                  const displayName = formatDisplayName(item, { fallback: 'Audio file' }) || 'Audio file';
                  return (
                    <div
                      key={item.id || item.filename}
                      role="button"
                      tabIndex={ready ? 0 : -1}
                      aria-disabled={!ready}
                      className={`text-left p-4 transition border-r border-b border-slate-200 focus:outline-none focus-visible:ring relative ${
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
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="font-medium text-slate-800">{displayName}</span>
                              {ready ? (
                                <Badge variant={isSelected ? 'default' : 'outline'} className="bg-emerald-100 text-emerald-700 border-emerald-200">
                                  Ready
                                </Badge>
                              ) : (
                                <Badge variant="outline" className="bg-amber-100 text-amber-700 border-amber-200">
                                  Processing
                                </Badge>
                              )}
                              {item.used_in_episode_id && (
                                <Badge variant="outline" className="bg-blue-50 text-blue-700 border-blue-300">
                                  ✓ Already Used
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
                                aria-label={`Delete ${displayName}`}
                              >
                                <Trash2 className="h-4 w-4" />
                              </button>
                            )}
                          </div>
                          <div className="text-xs text-slate-500">
                            Uploaded {formatUploadedAt(item.created_at)} · Duration {formatItemDuration(item.duration_seconds)}
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
                                Sound Effects: {sfx}
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
                      {/* Expiration date in bottom right corner - always show */}
                      {(() => {
                        // Try to format from expires_at first
                        let expirationData = formatExpirationDate(item.expires_at);
                        let expirationDateStr = null;
                        let isSoon = false;
                        
                        if (expirationData) {
                          expirationDateStr = expirationData.formatted;
                          isSoon = isExpiringSoon(item.expires_at);
                        } else if (item.created_at) {
                          // If no expires_at, calculate from created_at as fallback
                          try {
                            const createdDate = new Date(item.created_at);
                            if (!Number.isNaN(createdDate.getTime())) {
                              // Default: 14 days from created_at (fallback for old files)
                              const defaultExpiration = new Date(createdDate);
                              defaultExpiration.setUTCDate(defaultExpiration.getUTCDate() + 13); // 14 days - 1 day for display
                              const month = defaultExpiration.getUTCMonth() + 1;
                              const day = defaultExpiration.getUTCDate();
                              expirationDateStr = `${month}/${day}`;
                              
                              // Check if this fallback date is within 3 days
                              const now = new Date();
                              const daysUntilExpiration = Math.ceil((defaultExpiration - now) / (1000 * 60 * 60 * 24));
                              isSoon = daysUntilExpiration <= 3;
                            }
                          } catch {
                            // If calculation fails, don't show expiration
                            expirationDateStr = null;
                          }
                        }
                        
                        return expirationDateStr ? (
                          <div className={`absolute bottom-2 right-2 text-xs ${isSoon ? 'text-red-600 font-semibold' : 'text-slate-500'}`}>
                            Expires {expirationDateStr}
                          </div>
                        ) : null;
                      })()}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

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

      {/* REMOVED: Automation confirmation box - users who use intern/flubber know what they're doing.


          Automations (flubber, intern, sfx) will process automatically when they hit Continue.


          No extra clicks, no extra questions - just hit Continue and they'll process in order. */}

      <div className="flex justify-between pt-4 items-start">
        <Button variant="ghost" onClick={onBack}>
          Back
        </Button>
        <div className="flex flex-col items-end gap-1">
          <Button
            onClick={handleContinue}
            disabled={!canContinue || loading || minutesPrecheckPending || minutesBlocking}
          >
            Continue
          </Button>
          {minutesPrecheckPending && (
            <span className="text-xs text-slate-600">Waiting for processing minutes check…</span>
          )}
          {minutesBlocking && !minutesPrecheckPending && (
            <span className="text-xs text-red-600">{blockingMessage}</span>
          )}
        </div>
      </div>
    </div>
  );
}
