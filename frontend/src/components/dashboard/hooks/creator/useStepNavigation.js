import { useState, useMemo, useCallback } from 'react';
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
        
        // Merge template with full data and AI defaults
        const merged = {
          ...template,
          ...full,
          ai_settings: { ...aiDefaults, ...(full?.ai_settings || template?.ai_settings || {}) }
        };
        
        // Seed TTS segments with default voice if available
        const segments = Array.isArray(merged.segments) ? [...merged.segments] : [];
        const templateDefaultVoiceId = segments.find(
          s => s?.source?.source_type === 'tts' && s?.source?.voice_id
        )?.source?.voice_id || null;
        
        const seeded = segments.map(s => {
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
        
        setSelectedTemplate({ ...merged, segments: seeded });
      } catch {
        // Fallback: use basic template with AI defaults
        const aiDefaults = {
          auto_fill_ai: true,
          title_instructions: '',
          notes_instructions: '',
          tags_instructions: '',
          tags_always_include: [],
          auto_generate_tags: true,
        };
        setSelectedTemplate(prev => ({
          ...(template || prev),
          ai_settings: { ...aiDefaults, ...((template || {}).ai_settings || {}) }
        }));
      }
      
      // Advance to Step 2 (upload/select audio)
      setCurrentStep(2);
    },
    [token]
  );

  return {
    // State
    currentStep,
    selectedTemplate,
    steps,
    progressPercentage,
    
    // Setters
    setCurrentStep,
    setSelectedTemplate,
    
    // Handlers
    handleTemplateSelect,
  };
}
