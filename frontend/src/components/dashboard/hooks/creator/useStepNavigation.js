import { useState, useMemo, useCallback, useEffect } from 'react';
import { makeApi } from '@/lib/apiClient';

/**
 * Manages podcast creation wizard step navigation and template selection
 * 
 * @param {Object} options
 * @param {string} options.token - Auth token for API calls
 * @param {number} options.initialStep - Starting step number (default: 1)
 * @param {string} options.creatorMode - 'standard' | 'preuploaded' (affects Step 2 title/icon)
 * @returns {Object} Navigation state and handlers
 */
export default function useStepNavigation({ token, initialStep = 1, creatorMode = 'standard' }) {
  // State
  const [currentStep, setCurrentStep] = useState(initialStep);
  const [selectedTemplate, setSelectedTemplate] = useState(null);

  // Steps configuration (changes based on creator mode)
  const steps = useMemo(() => {
    const stepTwoTitle = creatorMode === 'preuploaded' ? 'Select Main Content' : 'Upload Audio';
    const stepTwoIcon = creatorMode === 'preuploaded' ? 'Library' : 'Mic';

    return [
      { number: 1, title: 'Select Template', icon: 'BookText' },
      { number: 2, title: stepTwoTitle, icon: stepTwoIcon },
      { number: 3, title: 'Customize Segments', icon: 'Wand2' },
      { number: 4, title: 'Cover Art', icon: 'FileImage' },
      { number: 5, title: 'Details & Schedule', icon: 'Settings' },
      { number: 6, title: 'Assemble', icon: 'Globe' },
    ];
  }, [creatorMode]);

  // Progress percentage for progress bar
  const progressPercentage = useMemo(
    () => ((currentStep - 1) / (steps.length - 1)) * 100,
    [currentStep, steps.length]
  );

  // Normalizer used when any code calls setSelectedTemplate directly.
  // Ensures the template always exposes a safe `segments` array and
  // preserves seeded TTS voice defaults.
  const normalizeTemplate = useCallback((tpl) => {
    // Always return a safe template object. If tpl is falsy, return a
    // minimal template with a single content segment so the UI remains
    // usable and doesn't receive an object with undefined fields.
    const merged = { ...(tpl || {}) };
    let rawSegments = merged?.segments;
    if (!Array.isArray(rawSegments) && typeof merged?.segments === 'string') {
      try { rawSegments = JSON.parse(merged.segments); } catch { rawSegments = []; }
    }
    if ((!Array.isArray(rawSegments) || rawSegments.length === 0) && merged?.segments_json) {
      try {
        const parsed = typeof merged.segments_json === 'string' ? JSON.parse(merged.segments_json) : merged.segments_json;
        if (Array.isArray(parsed)) rawSegments = parsed;
      } catch {}
    }
  if (!Array.isArray(rawSegments)) rawSegments = [];
    const safeSegments = rawSegments.map((s) => {
      const seg = { ...(s || {}) };
      if (!seg.source || typeof seg.source !== 'object') seg.source = { source_type: 'content' };
      if (!seg.source.source_type && seg.source.type) {
        seg.source.source_type = seg.source.type;
        delete seg.source.type;
      }
      if (seg.source.source_type === 'tts') {
        if (!seg.source.text_prompt && seg.source.script) seg.source.text_prompt = seg.source.script;
      }
      return seg;
    });
    const segments = safeSegments.length ? safeSegments : [{ segment_type: 'content', source: { source_type: 'content' } }];
    const templateDefaultVoiceId = segments.find(s => s?.source?.source_type === 'tts' && s?.source?.voice_id)?.source?.voice_id || merged?.default_elevenlabs_voice_id || null;
    const seeded = segments.map((s) => {
      if (s?.source?.source_type === 'tts') {
        return { ...s, source: { ...s.source, voice_id: s.source.voice_id || templateDefaultVoiceId || s.source.voice_id } };
      }
      return s;
    });
    return { ...merged, segments: seeded };
  }, []);

  // Wrapped setter that accepts either a value or an updater function, like React's setState.
  const setNormalizedSelectedTemplate = useCallback((next) => {
    if (typeof next === 'function') {
      setSelectedTemplate((prev) => {
        const computed = next(prev);
        return normalizeTemplate(computed);
      });
    } else {
      setSelectedTemplate(normalizeTemplate(next));
    }
  }, [normalizeTemplate]);

  // Template selection handler - fetches full template and advances to Step 2
  const handleTemplateSelect = useCallback(
    async (template) => {
      try {
        const api = makeApi(token);
        const full = await api.get(`/api/templates/${template.id}`);

        // Default AI settings
        const aiDefaults = {
          auto_fill_ai: true,
          title_instructions: '',
          notes_instructions: '',
          tags_instructions: '',
          tags_always_include: [],
          auto_generate_tags: true,
        };
    // Debug logging during fetch is done later as a top-level effect so we can
    // capture all updates to `selectedTemplate` in one place.

        // Merge template with full data and AI defaults
        const merged = {
          ...template,
          ...full,
          ai_settings: { ...aiDefaults, ...(full?.ai_settings || template?.ai_settings || {}) }
        };

        // Normalization: ensure segments is a usable array and each segment has
        // a predictable `source.source_type` value. This guards against
        // historical templates, serialization differences, or partial data.
        let rawSegments = merged?.segments;
        // Some backends might still return segments as a JSON string under
        // `segments` or `segments_json`. Try to handle those cases safely.
        if (!Array.isArray(rawSegments) && typeof merged?.segments === 'string') {
          try {
            rawSegments = JSON.parse(merged.segments);
          } catch (_) {
            rawSegments = [];
          }
        }
        if ((!Array.isArray(rawSegments) || rawSegments.length === 0) && merged?.segments_json) {
          try {
            const parsed = typeof merged.segments_json === 'string' ? JSON.parse(merged.segments_json) : merged.segments_json;
            if (Array.isArray(parsed)) rawSegments = parsed;
          } catch (_) {
            // leave rawSegments as-is
          }
        }

        if (!Array.isArray(rawSegments)) rawSegments = [];

        const safeSegments = rawSegments.map((s) => {
          const seg = { ...(s || {}) };
          // Ensure source object exists
          if (!seg.source || typeof seg.source !== 'object') seg.source = { source_type: 'content' };
          // Normalize alternative field names -> frontend expects source.source_type
          if (!seg.source.source_type && seg.source.type) {
            seg.source.source_type = seg.source.type;
            delete seg.source.type;
          }
          // Back-compat: older TTS templates may use `script` instead of `text_prompt`
          if (seg.source.source_type === 'tts') {
            if (!seg.source.text_prompt && seg.source.script) seg.source.text_prompt = seg.source.script;
            if (!seg.source.voice_id && merged.default_elevenlabs_voice_id) seg.source.voice_id = merged.default_elevenlabs_voice_id;
          }
          return seg;
        });

        // If we ended up with no segments, create a single content segment fallback
        const segments = safeSegments.length ? safeSegments : [{ segment_type: 'content', source: { source_type: 'content' } }];

        // Find a template-level default voice (if any) from TTS segments
        const templateDefaultVoiceId = segments.find(
          s => s?.source?.source_type === 'tts' && s?.source?.voice_id
        )?.source?.voice_id || merged?.default_elevenlabs_voice_id || null;

        const seeded = segments.map((s) => {
          if (s?.source?.source_type === 'tts') {
            return {
              ...s,
              source: {
                ...s.source,
                voice_id: s.source.voice_id || templateDefaultVoiceId || s.source.voice_id
              }
            };
          }
          return s;
        });

        // Helpful debug log so users can see what the backend returned for the template
        // (this is safe: it will log to the browser console only and will not expose
        // internal IDs to other systems). Remove once we've confirmed the root cause.
        try { console.debug('[useStepNavigation] fetched template:', { templateId: template?.id, merged, segments: seeded }); } catch (_) {}

  setNormalizedSelectedTemplate({ ...merged, segments: seeded });
      } catch (err) {
        // Fallback: use basic template with AI defaults
        const aiDefaults = {
          auto_fill_ai: true,
          title_instructions: '',
          notes_instructions: '',
          tags_instructions: '',
          tags_always_include: [],
          auto_generate_tags: true,
        };
        // Also surface error to console so the user can see why fetch failed
        try { console.warn('[useStepNavigation] failed to fetch full template, falling back to provided template', err); } catch (_) {}
        setNormalizedSelectedTemplate(prev => ({
          ...(template || prev),
          segments: (template && Array.isArray(template.segments) && template.segments.length)
            ? template.segments
            : [{ segment_type: 'content', source: { source_type: 'content' } }],
          ai_settings: { ...aiDefaults, ...((template || {}).ai_settings || {}) }
        }));
      }

      // Advance to Step 2 (upload/select audio)
      setCurrentStep(2);
    },
    [token]
  );

    

  // Debug: log whenever selectedTemplate changes so we can trace accidental overwrites
  useEffect(() => {
    try {
      const id = selectedTemplate?.id || null;
      const name = selectedTemplate?.name || null;
      const segs = Array.isArray(selectedTemplate?.segments) ? selectedTemplate.segments.length : 0;
      const stack = (new Error()).stack?.split('\n').slice(2,6).join('\n');
      console.debug('[useStepNavigation] selectedTemplate changed', { id, name, segs, stack });
    } catch (_) {}
  }, [selectedTemplate]);

  return {
    // State
    currentStep,
    selectedTemplate,
    steps,
    progressPercentage,
    
    // Setters
    setCurrentStep,
    setSelectedTemplate: setNormalizedSelectedTemplate,
    
    // Handlers
    handleTemplateSelect,
  };
}
