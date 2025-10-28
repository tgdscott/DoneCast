import { useState, useCallback, useRef } from 'react';
import { toast } from '@/hooks/use-toast';
import { makeApi } from '@/lib/apiClient';

/**
 * Manages AI-powered features (Flubber and Intern workflows)
 * Flubber: Detects and removes spoken retakes ("flubber" keyword)
 * Intern: Processes spoken commands for inserting pre-recorded segments
 * 
 * @param {Object} options
 * @param {string} options.token - Auth token for API calls
 * @param {string} options.uploadedFilename - Uploaded audio filename
 * @param {string} options.selectedPreupload - Selected pre-uploaded file
 * @param {Object} options.selectedTemplate - Currently selected podcast template
 * @param {Function} options.setStatusMessage - Callback to set status message
 * @param {Function} options.setCurrentStep - Callback to set current wizard step
 * @param {Function} options.resolveInternVoiceId - Callback to resolve intern voice ID
 * @param {boolean} options.requireIntern - Whether intern is required
 * @param {boolean} options.requireSfx - Whether sound effects are required
 * @param {Object} options.internPrefetch - Prefetched intern data
 * @returns {Object} AI features state and handlers
 */
export default function useAIFeatures({
  token,
  uploadedFilename,
  selectedPreupload,
  selectedTemplate,
  setStatusMessage,
  setCurrentStep,
  resolveInternVoiceId,
  requireIntern,
  requireSfx,
  internPrefetch,
}) {
  // Flubber state
  const [flubberContexts, setFlubberContexts] = useState([]);
  const [flubberCutsMs, setFlubberCutsMs] = useState([]);
  const [showFlubberReview, setShowFlubberReview] = useState(false);
  const [showFlubberScan, setShowFlubberScan] = useState(false);
  const [flubberNotFound, setFlubberNotFound] = useState(false);

  // Intern state
  const [internResponses, setInternResponses] = useState([]);
  const [internPendingContexts, setInternPendingContexts] = useState(null);
  const [internReviewContexts, setInternReviewContexts] = useState([]);
  const [showInternReview, setShowInternReview] = useState(false);

  // Intent state (flubber/intern/sfx detection)
  const [intents, setIntents] = useState({ flubber: null, intern: null, sfx: null, intern_overrides: [] });
  const [intentDetections, setIntentDetections] = useState({ flubber: null, intern: null, sfx: null });
  const [intentDetectionReady, setIntentDetectionReady] = useState(false);
  const [showIntentQuestions, setShowIntentQuestions] = useState(false);
  const intentsPromptedRef = useRef(false);

  // Reset all AI features state
  const resetAIFeatures = useCallback(() => {
    setIntents({ flubber: null, intern: null, sfx: null, intern_overrides: [] });
    setInternResponses([]);
    setInternPendingContexts(null);
    setInternReviewContexts([]);
    setShowInternReview(false);
    setIntentDetections({ flubber: null, intern: null, sfx: null });
    setIntentDetectionReady(false);
    setShowIntentQuestions(false);
    intentsPromptedRef.current = false;
    setFlubberContexts([]);
    setFlubberCutsMs([]);
    setShowFlubberReview(false);
    setShowFlubberScan(false);
    setFlubberNotFound(false);
  }, []);

  // Queue intern review (may defer if flubber is showing)
  const queueInternReview = useCallback((contexts) => {
    if (!Array.isArray(contexts) || contexts.length === 0) return false;
    if (showFlubberReview) {
      setInternPendingContexts(contexts);
    } else {
      setInternPendingContexts(null);
      setInternReviewContexts(contexts);
      setShowInternReview(true);
    }
    return true;
  }, [showFlubberReview]);

  // Proceed to next step after flubber review
  const proceedAfterFlubber = useCallback(() => {
    if (internPendingContexts && internPendingContexts.length) {
      setInternReviewContexts(internPendingContexts);
      setInternPendingContexts(null);
      setShowInternReview(true);
    } else {
      setCurrentStep(3);
    }
  }, [internPendingContexts, setCurrentStep]);

  // Flubber handlers
  const handleFlubberConfirm = useCallback((cuts) => {
    setFlubberCutsMs(cuts || []);
    setShowFlubberReview(false);
    proceedAfterFlubber();
  }, [proceedAfterFlubber]);

  const handleFlubberCancel = useCallback(() => {
    setFlubberCutsMs([]);
    setShowFlubberReview(false);
    proceedAfterFlubber();
  }, [proceedAfterFlubber]);

  const retryFlubberSearch = useCallback(async () => {
    setFlubberNotFound(false);
    setStatusMessage('Re-scanning for flubber...');
    setShowFlubberScan(true);
    
    const api = makeApi(token);
    const payload = { filename: uploadedFilename, intents: { flubber: 'yes' } };
    let contexts = [];
    
    try {
      for (let attempt = 0; attempt < 20; attempt++) {
        try {
          const data = await api.post('/api/flubber/prepare-by-file', payload);
          contexts = Array.isArray(data?.contexts) ? data.contexts : [];
          break;
        } catch (e) {
          if (e && e.status === 425) {
            await new Promise((r) => setTimeout(r, 1000));
            continue;
          }
          break;
        }
      }
    } catch (_) {
    } finally {
      setShowFlubberScan(false);
      setStatusMessage('');
    }

    if (contexts.length > 0) {
      setFlubberContexts(contexts);
      setShowFlubberReview(true);
    } else {
      setFlubberNotFound(true);
    }
  }, [token, uploadedFilename, setStatusMessage]);

  const skipFlubberRetry = useCallback(() => {
    setFlubberNotFound(false);
    proceedAfterFlubber();
  }, [proceedAfterFlubber]);

  // Intern handlers
  const handleInternComplete = useCallback(async (results) => {
    const safe = Array.isArray(results) ? results : [];
    
    // Generate TTS for each response that doesn't already have audio
    setStatusMessage('Generating intern voice responses...');
    const api = makeApi(token);
    const enriched = [];
    
    for (const result of safe) {
      if (!result.audio_url && result.response_text) {
        try {
          const ttsPayload = {
            text: result.response_text,
            voice_id: result.voice_id || resolveInternVoiceId() || undefined,
            category: 'intern',
            provider: 'elevenlabs',
            speaking_rate: 1.0,
            confirm_charge: false,
          };
          console.log('[INTERN_TTS] Generating TTS:', { 
            text_length: result.response_text.length, 
            voice_id: ttsPayload.voice_id,
            command_id: result.command_id 
          });
          const ttsResult = await api.post('/api/media/tts', ttsPayload);
          console.log('[INTERN_TTS] TTS generated:', { 
            filename: ttsResult?.filename,
            command_id: result.command_id 
          });
          // MediaItem.filename contains the GCS URL after upload
          enriched.push({
            ...result,
            audio_url: ttsResult?.filename || null,
          });
        } catch (err) {
          console.error('[INTERN_TTS] Failed to generate TTS for intern response:', err);
          // Still push the result even if TTS fails - backend will generate as fallback
          enriched.push(result);
        }
      } else {
        if (!result.response_text) {
          console.warn('[INTERN_TTS] Skipping TTS - no response text:', result.command_id);
        } else if (result.audio_url) {
          console.log('[INTERN_TTS] Using existing audio URL:', result.command_id);
        }
        enriched.push(result);
      }
    }
    
    setStatusMessage('');
    console.log('[INTERN_COMPLETE] Final enriched results:', enriched.map(r => ({ 
      command_id: r.command_id, 
      has_audio_url: !!r.audio_url,
      has_voice_id: !!r.voice_id,
      text_length: r.response_text?.length || 0
    })));
    setInternResponses(enriched);
    setIntents((prev) => ({ ...prev, intern_overrides: enriched }));
    setShowInternReview(false);
    setInternReviewContexts([]);
    setInternPendingContexts(null);
    setCurrentStep(3);
  }, [token, resolveInternVoiceId, setStatusMessage, setCurrentStep]);

  const handleInternCancel = useCallback(() => {
    setInternResponses([]);
    setIntents((prev) => ({ ...prev, intern_overrides: [] }));
    setShowInternReview(false);
    setInternReviewContexts([]);
    setInternPendingContexts(null);
    setCurrentStep(3);
  }, [setCurrentStep]);

  const processInternCommand = useCallback(
    async ({ context, startSeconds, endSeconds, regenerate = false, overrideText = null }) => {
      const filename = uploadedFilename || selectedPreupload;
      if (!filename) throw new Error('No audio selected for intern processing.');
      if (typeof endSeconds !== 'number' || !isFinite(endSeconds)) {
        throw new Error('Select an end point for the intern command.');
      }
      
      const api = makeApi(token);
      const payload = {
        filename,
        end_s: endSeconds,
      };
      
      if (selectedTemplate?.id) {
        payload.template_id = selectedTemplate.id;
        // Let backend resolve voice from template
      } else {
        // Only include voice_id if no template (fallback)
        payload.voice_id = resolveInternVoiceId() || undefined;
      }
      
      const commandId = context?.command_id ?? context?.intern_index ?? context?.id ?? context?.index ?? (typeof context?.__index === 'number' ? context.__index : null);
      if (commandId != null) payload.command_id = commandId;
      
      const start = typeof startSeconds === 'number' && isFinite(startSeconds)
        ? startSeconds
        : (typeof context?.start_s === 'number' ? context.start_s : null);
      if (start != null) payload.start_s = start;
      if (overrideText != null) payload.override_text = overrideText;
      if (regenerate) payload.regenerate = true;
      
      const res = await api.post('/api/intern/execute', payload);
      return res || {};
    },
    [uploadedFilename, selectedPreupload, token, resolveInternVoiceId, selectedTemplate],
  );

  // Normalize intent value
  const normalizeIntentValue = useCallback((val) => {
    if (val === 'yes' || val === 'no' || val === 'unknown') return val;
    if (val === true || val === 1) return 'yes';
    if (val === false || val === 0) return 'no';
    return null;
  }, []);

  // Handle intent submission (flubber/intern/sfx questions)
  const handleIntentSubmit = useCallback(async (answers = intents) => {
    const normalized = {
      flubber: normalizeIntentValue(answers?.flubber ?? intents.flubber) ?? 'no',
      intern: requireIntern ? (normalizeIntentValue(answers?.intern ?? intents.intern) ?? 'no') : 'no',
      sfx: requireSfx ? (normalizeIntentValue(answers?.sfx ?? intents.sfx) ?? 'no') : 'no',
    };

    setIntents((prev) => {
      const next = { ...prev, ...normalized };
      if (normalized.intern !== 'yes') {
        next.intern_overrides = [];
      }
      return next;
    });
    
    if (normalized.intern !== 'yes') {
      setInternResponses([]);
      setInternPendingContexts(null);
      setInternReviewContexts([]);
      setShowInternReview(false);
    }
    
    intentsPromptedRef.current = true;
    setShowIntentQuestions(false);

    let paused = false;

    // Flubber scanning
    const shouldScanFlubber = uploadedFilename && (normalized.flubber === 'yes' || normalized.flubber === 'unknown');
    if (shouldScanFlubber) {
      setStatusMessage('Scanning for retakes (flubber)...');
      setShowFlubberScan(true);
      const api = makeApi(token);
      const payload = { filename: uploadedFilename, intents: { flubber: normalized.flubber } };
      let contexts = [];
      
      try {
        for (let attempt = 0; attempt < 20; attempt++) {
          try {
            const data = await api.post('/api/flubber/prepare-by-file', payload);
            contexts = Array.isArray(data?.contexts) ? data.contexts : [];
            break;
          } catch (e) {
            if (e && e.status === 425) {
              await new Promise((r) => setTimeout(r, 1000));
              continue;
            }
            break;
          }
        }
      } catch (_) {
      } finally {
        setShowFlubberScan(false);
        setStatusMessage('');
      }

      if (contexts.length > 0) {
        setFlubberContexts(contexts);
        setShowFlubberReview(true);
        paused = true;
      } else if (normalized.flubber === 'yes') {
        setFlubberNotFound(true);
        paused = true;
      }
    }

    // Intern processing
    const shouldProcessIntern = normalized.intern === 'yes' && requireIntern && (uploadedFilename || selectedPreupload);
    if (shouldProcessIntern) {
      const sourceFilename = uploadedFilename || selectedPreupload;
      const prefetched =
        internPrefetch && internPrefetch.status === 'ready' && internPrefetch.filename === sourceFilename
          ? internPrefetch.contexts
          : null;
      const usePrefetched = Array.isArray(prefetched) && prefetched.length > 0;
      
      if (usePrefetched) {
        if (queueInternReview(prefetched)) {
          paused = true;
        }
      } else {
        try {
          setStatusMessage('Preparing intern commands...');
          const api = makeApi(token);
          const payload = { filename: sourceFilename };
          
          if (selectedTemplate?.id) {
            payload.template_id = selectedTemplate.id;
            // Let backend resolve voice from template
          } else {
            // Only include voice_id if no template (fallback)
            const voiceId = resolveInternVoiceId();
            if (voiceId) payload.voice_id = voiceId;
          }
          
          const data = await api.post('/api/intern/prepare-by-file', payload);
          const contexts = Array.isArray(data?.contexts)
            ? data.contexts
            : Array.isArray(data?.commands)
              ? data.commands
              : [];
          
          if (queueInternReview(contexts)) {
            paused = true;
          }
        } catch (err) {
          const description = err?.detail?.message || err?.message || 'Unable to prepare intern commands right now.';
          toast({ variant: 'destructive', title: 'Intern review unavailable', description });
        } finally {
          setStatusMessage('');
        }
      }
    }

    if (!paused) {
      setCurrentStep(3);
    }
  }, [
    intents,
    requireIntern,
    requireSfx,
    uploadedFilename,
    selectedPreupload,
    token,
    selectedTemplate,
    resolveInternVoiceId,
    internPrefetch,
    setStatusMessage,
    setCurrentStep,
    normalizeIntentValue,
    queueInternReview,
  ]);

  return {
    // Flubber state
    flubberContexts,
    setFlubberContexts,
    flubberCutsMs,
    setFlubberCutsMs,
    showFlubberReview,
    setShowFlubberReview,
    showFlubberScan,
    setShowFlubberScan,
    flubberNotFound,
    setFlubberNotFound,
    
    // Intern state
    internResponses,
    setInternResponses,
    internPendingContexts,
    setInternPendingContexts,
    internReviewContexts,
    setInternReviewContexts,
    showInternReview,
    setShowInternReview,
    
    // Intent state
    intents,
    setIntents,
    intentDetections,
    setIntentDetections,
    intentDetectionReady,
    setIntentDetectionReady,
    showIntentQuestions,
    setShowIntentQuestions,
    intentsPromptedRef,
    
    // Handlers
    resetAIFeatures,
    handleFlubberConfirm,
    handleFlubberCancel,
    retryFlubberSearch,
    skipFlubberRetry,
    handleInternComplete,
    handleInternCancel,
    processInternCommand,
    handleIntentSubmit,
    normalizeIntentValue,
  };
}
