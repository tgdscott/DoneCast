import { useState, useRef, useCallback, useEffect } from 'react';
import { toast } from '@/hooks/use-toast';
import { makeApi } from '@/lib/apiClient';

/**
 * Manages episode assembly workflow and job status polling
 * 
 * @param {Object} options
 * @param {string} options.token - Auth token for API calls
 * @param {Object} options.selectedTemplate - Currently selected podcast template
 * @param {string} options.uploadedFilename - Uploaded audio filename
 * @param {Object} options.episodeDetails - Episode metadata (title, description, etc.)
 * @param {Object} options.ttsValues - TTS prompt values
 * @param {Array} options.flubberCutsMs - Flubber cut timestamps
 * @param {Object} options.intents - User intents (flubber, intern, sfx)
 * @param {Function} options.setError - Error message setter
 * @param {Function} options.setStatusMessage - Status message setter
 * @param {Function} options.setCurrentStep - Step navigation setter
 * @param {Function} options.refreshUsage - Refresh usage/quota callback
 * @param {number} options.audioDurationSec - Audio duration for quota checks
 * @param {boolean} options.transcriptReady - Whether a transcript exists for the main audio
 * @param {Object} options.minutesPrecheck - Minutes quota precheck result
 * @param {boolean} options.minutesPrecheckPending - Whether precheck is in progress
 * @param {Function} options.setMinutesDialog - Minutes dialog setter
 * @param {boolean} options.quotaExceeded - Whether episode quota exceeded
 * @param {string} options.publishMode - Publish mode ('now', 'draft', 'schedule')
 * @param {string} options.scheduleDate - Scheduled publish date
 * @param {string} options.scheduleTime - Scheduled publish time
 * @param {Function} options.handleUploadProcessedCoverAndPreview - Cover upload handler
 * @param {boolean} options.useAdvancedAudio - Whether to use advanced audio processing
 * @returns {Object} Assembly state and handlers
 */
export default function useEpisodeAssembly({
  token,
  selectedTemplate,
  uploadedFilename,
  transcriptReady = false,
  episodeDetails,
  ttsValues,
  flubberCutsMs,
  intents,
  setError,
  setStatusMessage,
  setCurrentStep,
  refreshUsage,
  audioDurationSec,
  minutesPrecheck,
  minutesPrecheckPending,
  setMinutesDialog,
  quotaExceeded,
  publishMode,
  scheduleDate,
  scheduleTime,
  handleUploadProcessedCoverAndPreview,
  useAdvancedAudio = false,
  usage = null, // Add usage prop for credit checking
  onShowCreditPurchase = null, // Callback to show credit purchase modal
  enableTimeoutToast = true, // Control whether to show long-running assembly toast
}) {
  // Assembly state
  const [isAssembling, setIsAssembling] = useState(false);
  const [assemblyComplete, setAssemblyComplete] = useState(false);
  const [assembledEpisode, setAssembledEpisode] = useState(null);
  const [expectedEpisodeId, setExpectedEpisodeId] = useState(null);
  const [jobId, setJobId] = useState(null);
  const [assemblyStartTime, setAssemblyStartTime] = useState(null);
  
  // Publishing state (managed here because it's tied to assembly completion)
  const [autoPublishPending, setAutoPublishPending] = useState(false);
  
  // Polling control
  const pollingIntervalRef = useRef(null);
  
  // Helper to normalize tags
  const normalizeTags = (rawTags) => {
    if (Array.isArray(rawTags)) return rawTags;
    if (typeof rawTags === 'string') {
      const trimmed = rawTags.trim();
      if (!trimmed) return [];
      return trimmed.split(/[,\n]+/).map(s => s.trim()).filter(Boolean);
    }
    return [];
  };

  // Main assembly handler
  const handleAssemble = useCallback(
    async () => {
      console.log('[ASSEMBLE] handleAssemble called with publishMode:', publishMode);
      
      // Guard: Minutes precheck pending
      if (minutesPrecheckPending) {
        setError('Checking processing minutes… please wait.');
        return;
      }

      // Guard: Check credits first (new system)
      if (usage && typeof usage.credits_balance === 'number') {
        // Estimate credits needed for assembly
        // Assembly: 3 credits/sec, Processing: 1 credit/sec
        const estimatedCredits = audioDurationSec ? (audioDurationSec * 4) : 0; // Rough estimate: 4 credits/sec total
        
        if (usage.credits_balance < estimatedCredits) {
          // Show credit purchase modal instead of blocking
          if (onShowCreditPurchase) {
            onShowCreditPurchase({
              requiredCredits: estimatedCredits,
              availableCredits: usage.credits_balance,
              planKey: usage.plan_key || 'pro',
            });
            setStatusMessage('');
            setError('');
            return;
          } else {
            // Fallback: show error but don't block (allow user to try)
            setError(`Insufficient credits. You have ${usage.credits_balance.toFixed(0)} credits, but need approximately ${estimatedCredits.toFixed(0)} credits for this episode.`);
            return;
          }
        }
      }

      // Guard: Minutes quota check failed (legacy system - keep for backward compatibility)
      if (minutesPrecheck && minutesPrecheck.allowed === false) {
        const detail = minutesPrecheck.detail || {};
        const required = Number(detail.minutes_required) || null;
        const remaining = (() => {
          const candidate = detail.minutes_remaining;
          const num = Number(candidate);
          return Number.isFinite(num) ? num : null;
        })();
        const renewal = detail.renewal_date || detail.renewalDate || null;
        const durationSeconds = (() => {
          const total = Number(minutesPrecheck.total_seconds);
          if (Number.isFinite(total) && total > 0) return total;
          const main = Number(minutesPrecheck.main_seconds);
          if (Number.isFinite(main) && main > 0) return main;
          return audioDurationSec && audioDurationSec > 0 ? audioDurationSec : null;
        })();

        // For minutes system, also try to show credit purchase if available
        if (onShowCreditPurchase && usage && typeof usage.credits_balance === 'number') {
          const estimatedCredits = durationSeconds ? (durationSeconds * 4) : (required ? (required * 60 * 4) : 0);
          if (usage.credits_balance < estimatedCredits) {
            onShowCreditPurchase({
              requiredCredits: estimatedCredits,
              availableCredits: usage.credits_balance,
              planKey: usage.plan_key || 'pro',
            });
            setStatusMessage('');
            setError('');
            return;
          }
        }

        setMinutesDialog({
          requiredMinutes: required,
          remainingMinutes: remaining,
          renewalDate: renewal,
          message: detail.message || 'Not enough processing minutes remain to assemble this episode.',
          durationSeconds: durationSeconds || null,
        });
        setStatusMessage('');
        setError('');
        return;
      }

      // Guard: Episode quota exceeded
      if (quotaExceeded) {
        setError('Monthly episode quota reached. Upgrade your plan to continue.');
        window.dispatchEvent(new Event('ppp:navigate-billing'));
        return;
      }

      // Guard: Required fields
      if (!uploadedFilename || !selectedTemplate || !episodeDetails.title) {
        setError('A template, title, and audio file are required.');
        return;
      }

      // Auto-fix missing season
      if (!episodeDetails.season || !String(episodeDetails.season).trim()) {
        episodeDetails.season = '1';
      }

      // Guard: Schedule validation
      if (publishMode === 'schedule') {
        if (!scheduleDate || !scheduleTime) {
          setError('Pick date & time for scheduling');
          return;
        }
        const dt = new Date(`${scheduleDate}T${scheduleTime}:00`);
        if (isNaN(dt.getTime()) || dt.getTime() < Date.now() + 10 * 60000) {
          setError('Scheduled time must be at least 10 minutes in the future.');
          return;
        }
      }

      // Upload cover if needed
      if (episodeDetails.coverArt && !episodeDetails.cover_image_path) {
        try {
          setStatusMessage('Processing cover before assembly...');
          await handleUploadProcessedCoverAndPreview();
        } catch (err) {
          setError('Cover processing failed; you can retry or remove the cover.');
          return;
        }
      }

      // Reset state for new assembly
      setAssemblyComplete(false);
      setAssembledEpisode(null);
      setAutoPublishPending(false);
      setExpectedEpisodeId(null);
      setIsAssembling(true);
      setAssemblyStartTime(Date.now());
      setStatusMessage('Assembling your episode...');
      setError('');
      setCurrentStep(6);

      try {
        const api = makeApi(token);
        
        // Sanitize episode details
        const sanitizedDetails = {
          title: episodeDetails.title,
          description: episodeDetails.description,
          season: episodeDetails.season,
          episodeNumber: episodeDetails.episodeNumber,
          cover_image_path: episodeDetails.cover_image_path || null,
          explicit: episodeDetails.is_explicit || false,
          tags: normalizeTags(episodeDetails.tags),
        };

        let result;
        try {
          console.log('[ASSEMBLE] Sending payload with intents:', {
            intern_overrides_count: intents?.intern_overrides?.length || 0,
            intern_overrides_sample: intents?.intern_overrides?.slice(0, 2).map(o => ({
              command_id: o.command_id,
              has_audio_url: !!o.audio_url,
              has_voice_id: !!o.voice_id,
              text_length: o.response_text?.length || 0,
            })),
          });

          result = await api.post('/api/episodes/assemble', {
            template_id: selectedTemplate.id,
            main_content_filename: uploadedFilename,
            output_filename: episodeDetails.title.toLowerCase().replace(/\s+/g, '-'),
            tts_values: ttsValues,
            episode_details: {
              ...sanitizedDetails,
              guest_intros: episodeDetails.guests ? episodeDetails.guests.map(g => ({
                name: g.name,
                gcs_path: g.gcs_path
              })) : []
            },
            flubber_cuts_ms: Array.isArray(flubberCutsMs) && flubberCutsMs.length ? flubberCutsMs : null,
            intents: intents,
            use_auphonic: useAdvancedAudio,
          });
        } catch (e) {
          // Handle 402 (quota/minutes exceeded) specially
          if (e && e.status === 402) {
            const detail = (e.detail && typeof e.detail === 'object') ? e.detail : {};
            
            if (detail.code === 'INSUFFICIENT_MINUTES') {
              const required = Number(detail.minutes_required) || 0;
              const remaining = Number(detail.minutes_remaining);
              const renewal = detail.renewal_date || detail.renewalDate || null;
              const secondsEstimate = (audioDurationSec && audioDurationSec > 0)
                ? audioDurationSec
                : (required > 0 ? required * 60 : null);

              setMinutesDialog({
                requiredMinutes: required,
                remainingMinutes: Number.isFinite(remaining) ? Math.max(0, remaining) : null,
                renewalDate: renewal,
                message: detail.message || e.message || 'Not enough processing minutes remain.',
                durationSeconds: secondsEstimate,
              });
              setStatusMessage('');
              setIsAssembling(false);
              setError('');
              try {
                await refreshUsage();
              } catch {}
              return;
            }

            // Episode quota exceeded
            const msg = 'Monthly episode quota reached. Upgrade your plan to continue.';
            setError(msg);
            setStatusMessage('');
            toast({ variant: 'destructive', title: 'Quota Reached', description: msg });
            setIsAssembling(false);
            window.dispatchEvent(new Event('ppp:navigate-billing'));
            return;
          }
          throw e;
        }

        // Store job ID and episode ID for polling
        if (result.episode_id) setExpectedEpisodeId(result.episode_id);
        setJobId(result.job_id);
        setAutoPublishPending(true);
        setStatusMessage(`Episode assembly has been queued. Job ID: ${result.job_id}`);
      } catch (err) {
        setError(err.message || err?.detail?.message || 'Assembly failed');
        setStatusMessage('');
        setIsAssembling(false);
      }
    },
    [
      token,
      selectedTemplate,
      uploadedFilename,
      episodeDetails,
      ttsValues,
      flubberCutsMs,
      intents,
      minutesPrecheck,
      minutesPrecheckPending,
      quotaExceeded,
      publishMode,
      scheduleDate,
      scheduleTime,
      audioDurationSec,
      setError,
      setStatusMessage,
      setCurrentStep,
      setMinutesDialog,
      refreshUsage,
      handleUploadProcessedCoverAndPreview,
      useAdvancedAudio,
    ]
  );

  // Cancel assembly handler
  const handleCancelAssembly = useCallback(() => {
    console.log('[ASSEMBLE] User cancelled assembly');
    
    // Stop polling
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
      pollingIntervalRef.current = null;
    }
    
    // Reset assembly state
    setIsAssembling(false);
    setJobId(null);
    setAssemblyStartTime(null);
    setAutoPublishPending(false);
    setStatusMessage('');
    setError('');
    
    // Note: We don't delete the episode or cancel the backend job
    // The job will complete in background and user can find it in history
    toast({
      title: 'Assembly Cancelled',
      description: 'Stopped monitoring. The episode may still complete in the background.',
    });
  }, [setError, setStatusMessage]);

  // Job status polling effect
  useEffect(() => {
    if (!jobId) return;

    const api = makeApi(token);
    const TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes
    const POLL_INTERVAL_MS = 5000; // 5 seconds
    
    const pollStatus = async () => {
      try {
        // Check for timeout
        if (assemblyStartTime && (Date.now() - assemblyStartTime) > TIMEOUT_MS) {
          if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current);
            pollingIntervalRef.current = null;
          }
          setIsAssembling(false);

          // Optional UX: long-running assembly warning. Useful during
          // metadata/AI steps, but can be noisy on Step 6 summary.
          if (enableTimeoutToast) {
            setError(
              'Assembly is taking longer than expected. This may indicate a service issue. ' +
              'You can safely leave - we\'ll notify you when it completes, or check Episode History later.'
            );
            toast({
              variant: 'destructive',
              title: 'Assembly Timeout',
              description: 'Taking longer than expected. Check Episode History later or contact support.',
            });
          }
          return;
        }

        const data = await api.get(`/api/episodes/status/${jobId}`);
        setStatusMessage(data.status);

        if (data.status === 'processed' || data.status === 'error') {
          if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current);
            pollingIntervalRef.current = null;
          }
          setIsAssembling(false);

          if (data.status === 'processed') {
            // Guard: Episode ID mismatch (race condition protection)
            if (data.episode && expectedEpisodeId && data.episode.id && data.episode.id !== expectedEpisodeId) {
              setIsAssembling(true);
              setTimeout(() => {
                setJobId(j => j);
              }, 750);
              return;
            }

            setAssemblyComplete(true);
            setAssembledEpisode(data.episode);

            // Clear persisted draft data on successful assembly
            if (uploadedFilename) {
              try {
                const draftKey = `ppp_episode_draft_${uploadedFilename}`;
                localStorage.removeItem(draftKey);
                console.log('[Assembly] Cleared draft data for:', uploadedFilename);
              } catch (err) {
                console.warn('[Assembly] Failed to clear draft data:', err);
              }
            }

            // Show success toast
            if (publishMode === 'schedule') {
              toast({ title: 'Scheduled', description: 'Episode assembled & ready to schedule.' });
            } else if (publishMode === 'draft') {
              toast({ title: 'Draft Ready', description: 'Episode assembled (draft).' });
            }
          } else {
            const errorMsg = data.error || 'An error occurred during processing.';
            setError(errorMsg);
            toast({
              variant: 'destructive',
              title: 'Assembly Error',
              description: errorMsg,
            });
          }
        }
      } catch (err) {
        // Handle network errors gracefully
        const is503 = err?.status === 503 || err?.message?.includes('503');
        const isNetworkError = !err?.status || err?.message?.includes('fetch') || err?.message?.includes('network');
        
        if (is503 || isNetworkError) {
          console.warn('[ASSEMBLE] Network/503 error during polling:', err);
          setStatusMessage('Connection issue detected - retrying...');
          // Don't stop polling on transient errors, let timeout handle it
        } else {
          // Fatal error - stop polling
          if (pollingIntervalRef.current) {
            clearInterval(pollingIntervalRef.current);
            pollingIntervalRef.current = null;
          }
          setIsAssembling(false);
          const errorMsg = err?.message || 'Failed to check assembly status.';
          setError(errorMsg);
          toast({
            variant: 'destructive',
            title: 'Status Check Failed',
            description: errorMsg,
          });
        }
      }
    };

    // Start polling
    pollingIntervalRef.current = setInterval(pollStatus, POLL_INTERVAL_MS);
    pollStatus(); // Initial poll

    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
        pollingIntervalRef.current = null;
      }
    };
  }, [jobId, token, expectedEpisodeId, publishMode, assemblyStartTime, setError, setStatusMessage, uploadedFilename]);

  // Validation for Step 5 (Episode Details)
  const missingTitle = !episodeDetails?.title || episodeDetails.title.trim() === '';
  const missingEpisodeNumber = !episodeDetails?.episodeNumber || episodeDetails.episodeNumber.toString().trim() === '';
  const blockingQuota = quotaExceeded;
  // Require a ready transcript before allowing the user to proceed to Step 5
  const canProceedToStep5 = !missingTitle && !missingEpisodeNumber && !blockingQuota && !!transcriptReady;

  return {
    // State
    isAssembling,
    assemblyComplete,
    assembledEpisode,
    expectedEpisodeId,
    jobId,
    autoPublishPending,

    // Validation
    canProceedToStep5,
    blockingQuota,
    missingTitle,
    missingEpisodeNumber,

    // Setters (for external control)
    setIsAssembling,
    setAssemblyComplete,
    setAssembledEpisode,
    setExpectedEpisodeId,
    setJobId,
    setAutoPublishPending,

    // Handlers
    handleAssemble,
    handleCancelAssembly,
  };
}
