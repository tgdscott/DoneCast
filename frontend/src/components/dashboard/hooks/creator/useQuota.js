import { useState, useCallback, useEffect } from 'react';
import { makeApi } from '@/lib/apiClient';

export default function useQuota({ token, selectedTemplate, uploadedFilename, audioDurationSec }) {
  const [usage, setUsage] = useState(null);
  const [minutesDialog, setMinutesDialog] = useState(null);
  const [minutesPrecheck, setMinutesPrecheck] = useState(null);
  const [minutesPrecheckPending, setMinutesPrecheckPending] = useState(false);
  const [minutesPrecheckError, setMinutesPrecheckError] = useState(null);
  const [precheckRetrigger, setPrecheckRetrigger] = useState(0);

  const refreshUsage = useCallback(async () => {
    try {
      const api = makeApi(token);
      const u = await api.get('/api/billing/usage');
      if (u) setUsage(u);
      return u;
    } catch (_) {
      return null;
    }
  }, [token]);

  useEffect(() => {
    refreshUsage();
  }, [token, refreshUsage]);

  useEffect(() => {
    if (!token || !selectedTemplate?.id || !uploadedFilename) {
      setMinutesPrecheck(null);
      setMinutesPrecheckError(null);
      setMinutesPrecheckPending(false);
      return;
    }

    let cancelled = false;
    setMinutesPrecheckPending(true);
    setMinutesPrecheckError(null);

    const api = makeApi(token);
    (async () => {
      try {
        const payload = {
          template_id: selectedTemplate.id,
          main_content_filename: uploadedFilename,
        };
        const res = await api.post('/api/episodes/precheck/minutes', payload);
        if (cancelled) return;
        setMinutesPrecheck(res || null);
        setMinutesPrecheckError(null);
      } catch (err) {
        if (cancelled) return;
        if (err && err.status === 402 && err.detail) {
          const detail = err.detail;
          const fallback = {
            allowed: false,
            detail,
            minutes_required: Number(detail.minutes_required) || null,
            minutes_remaining: Number(detail.minutes_remaining),
          };
          setMinutesPrecheck(fallback);
          setMinutesPrecheckError(null);
        } else {
          setMinutesPrecheck(null);
          setMinutesPrecheckError(err?.message || 'Unable to check minutes.');
        }
      } finally {
        if (!cancelled) setMinutesPrecheckPending(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [token, selectedTemplate?.id, uploadedFilename, precheckRetrigger]);

  const retryMinutesPrecheck = useCallback(() => {
    setPrecheckRetrigger(prev => prev + 1);
  }, []);

  const remainingEpisodes = usage?.episodes_remaining_this_month;
  const maxEpisodes = usage?.max_episodes_month;
  const nearQuota = typeof remainingEpisodes === 'number' && typeof maxEpisodes === 'number' && remainingEpisodes > 0 && remainingEpisodes <= Math.ceil(maxEpisodes * 0.1);
  const quotaExceeded = typeof remainingEpisodes === 'number' && remainingEpisodes <= 0;

  const minutesUsed = usage?.processing_minutes_used_this_month;
  const minutesCap = usage?.max_processing_minutes_month;
  const minutesRemaining = (typeof minutesCap === 'number' && typeof minutesUsed === 'number') ? (minutesCap - minutesUsed) : null;
  const minutesNearCap = (typeof minutesRemaining === 'number' && typeof minutesCap === 'number') && minutesRemaining > 0 && minutesRemaining <= Math.ceil(minutesCap * 0.1);
  const minutesExceeded = typeof minutesRemaining === 'number' && minutesRemaining <= 0;
  const minutesRemainingPrecheck = (() => {
    const candidate = minutesPrecheck?.minutes_remaining ?? minutesPrecheck?.detail?.minutes_remaining;
    const num = Number(candidate);
    if (Number.isFinite(num)) return num;
    return minutesRemaining;
  })();
  const minutesRequiredPrecheck = (() => {
    const candidate = minutesPrecheck?.minutes_required ?? minutesPrecheck?.detail?.minutes_required;
    const num = Number(candidate);
    return Number.isFinite(num) ? num : null;
  })();
  const minutesBlocking = Boolean(minutesPrecheck && minutesPrecheck.allowed === false);

  const quotaInfo = {
    remainingEpisodes,
    maxEpisodes,
    nearQuota,
    quotaExceeded,
    minutesRemaining,
    minutesRemainingPrecheck,
    minutesCap,
    minutesNearCap,
    minutesExceeded,
    minutesRequiredPrecheck,
    minutesBlocking,
    minutesPrecheckPending,
    minutesPrecheckError,
  };

  return {
    usage,
    minutesDialog,
    setMinutesDialog,
    minutesPrecheck,
    minutesPrecheckPending,
    minutesPrecheckError,
    retryMinutesPrecheck,
    quotaInfo,
    refreshUsage,
  };
}