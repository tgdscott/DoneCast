import { useState, useCallback, useEffect, useRef } from 'react';
import { makeApi } from '@/lib/apiClient';

export default function useAIOrchestration({
  token,
  uploadedFilename,
  selectedPreupload,
  selectedTemplate,
  transcriptReady,
  expectedEpisodeId,
  setTranscriptReady,
  setTranscriptPath,
  resolveInternVoiceId,
  capabilities,
}) {
  const [internPrefetch, setInternPrefetch] = useState({ status: 'idle', filename: null, contexts: [], log: null, error: null });
  const [intentDetections, setIntentDetections] = useState({ flubber: null, intern: null, sfx: null });
  const [intentDetectionReady, setIntentDetectionReady] = useState(false);
  const [intents, setIntents] = useState({ flubber: null, intern: null, sfx: null, intern_overrides: [] });

  useEffect(() => {
    setInternPrefetch({ status: 'idle', filename: null, contexts: [], log: null, error: null });
  }, [uploadedFilename, selectedPreupload]);

  useEffect(() => {
    if (!transcriptReady) return;
    if (!uploadedFilename && !expectedEpisodeId) return;

    let canceled = false;
    const api = makeApi(token);
    setIntentDetectionReady(false);
    setIntentDetections({ flubber: null, intern: null, sfx: null });

    const params = [];
    if (expectedEpisodeId) params.push(`episode_id=${encodeURIComponent(expectedEpisodeId)}`);
    if (uploadedFilename) params.push(`hint=${encodeURIComponent(uploadedFilename)}`);
    const url = `/api/ai/intent-hints${params.length ? `?${params.join('&')}` : ''}`;

    const fetchHints = async (attempt = 0) => {
      try {
        const res = await api.get(url);
        if (canceled) return;
        const hints = (res && res.intents) ? res.intents : {};
        setIntentDetections(hints);
        const flubberCount = Number((hints?.flubber?.count) ?? 0);
        const internCount = Number((hints?.intern?.count) ?? 0);
        const sfxCount = Number((hints?.sfx?.count) ?? 0);
        setIntents(prev => {
          const next = { ...prev };
          let changed = false;
          if (prev.flubber === null && flubberCount === 0) { next.flubber = 'no'; changed = true; }
          if (prev.intern === null && internCount === 0) { next.intern = 'no'; changed = true; }
          if (prev.sfx === null && sfxCount === 0) { next.sfx = 'no'; changed = true; }
          return changed ? next : prev;
        });
        setIntentDetectionReady(true);
      } catch (err) {
        if (canceled) return;
        const status = err && typeof err === 'object' ? err.status : null;
        if (status && [404, 409, 425].includes(status) && attempt < 5) {
          setTimeout(() => { if (!canceled) fetchHints(attempt + 1); }, 750);
          return;
        }
        setIntentDetections(null);
        setIntentDetectionReady(true);
      }
    };

    fetchHints();

    return () => { canceled = true; };
  }, [transcriptReady, uploadedFilename, expectedEpisodeId, token]);

  useEffect(() => {
    if (!capabilities.has_elevenlabs && !capabilities.has_google_tts) return;
    if (!transcriptReady) return;
    if (!intentDetectionReady) return;
    const sourceFilename = uploadedFilename || selectedPreupload;
    if (!sourceFilename) return;
    if (Number((intentDetections?.intern?.count) ?? 0) <= 0) return;

    let shouldFetch = false;
    setInternPrefetch((prev) => {
      if (prev && prev.filename === sourceFilename) {
        if (prev.status === 'ready' || prev.status === 'loading') {
          return prev;
        }
      }
      shouldFetch = true;
      return { status: 'loading', filename: sourceFilename, contexts: [], log: null, error: null };
    });
    if (!shouldFetch) return;

    let canceled = false;
    const api = makeApi(token);
    const payload = { filename: sourceFilename };
    if (selectedTemplate?.id) {
      payload.template_id = selectedTemplate.id;
    } else {
      try {
        const voiceId = resolveInternVoiceId();
        if (voiceId) payload.voice_id = voiceId;
      } catch (_) {}
    }

    (async () => {
      try {
        const data = await api.post('/api/intern/prepare-by-file', payload);
        if (canceled) return;
        const contexts = Array.isArray(data?.contexts) ? data.contexts : [];
        setInternPrefetch({
          status: 'ready',
          filename: sourceFilename,
          contexts,
          log: data?.log || null,
          error: null,
        });
      } catch (error) {
        if (canceled) return;
        setInternPrefetch((prev) => {
          if (prev && prev.filename === sourceFilename) {
            return { status: 'error', filename: sourceFilename, contexts: [], log: null, error };
          }
          return prev;
        });
      }
    })();

    return () => {
      canceled = true;
    };
  }, [
    capabilities.has_elevenlabs,
    capabilities.has_google_tts,
    transcriptReady,
    intentDetectionReady,
    intentDetections,
    uploadedFilename,
    selectedPreupload,
    token,
    resolveInternVoiceId,
    selectedTemplate?.id,
  ]);

  return {
    internPrefetch,
    intentDetections,
    intentDetectionReady,
    intents,
    setIntents,
    setIntentDetections,
    setIntentDetectionReady,
  };
}