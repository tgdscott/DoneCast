import { useState, useEffect, useCallback } from 'react';
import { makeApi } from '@/lib/apiClient';
import { fetchVoices as fetchElevenVoices } from '@/api/elevenlabs';

/**
 * Manages TTS (Text-to-Speech) and voice configuration
 * Handles voice picker state, voice name resolution, and TTS prompt values
 * 
 * @param {Object} options
 * @param {string} options.token - Auth token for API calls
 * @param {number} options.currentStep - Current wizard step
 * @param {Object} options.selectedTemplate - Currently selected podcast template
 * @param {Function} options.setSelectedTemplate - Template setter (for voice changes)
 * @returns {Object} Voice configuration state and handlers
 */
export default function useVoiceConfiguration({
  token,
  currentStep,
  selectedTemplate,
  setSelectedTemplate,
}) {
  // TTS prompt values (user input for TTS segments)
  const [ttsValues, setTtsValues] = useState({});
  
  // Voice picker state
  const [showVoicePicker, setShowVoicePicker] = useState(false);
  const [voicePickerTargetId, setVoicePickerTargetId] = useState(null);
  
  // Voice name resolution (voice_id -> display name)
  const [voiceNameById, setVoiceNameById] = useState({});
  const [voicesLoading, setVoicesLoading] = useState(false);

  // TTS value change handler
  const handleTtsChange = useCallback(
    (promptId, value) => {
      setTtsValues(prev => ({ ...prev, [promptId]: value }));
    },
    []
  );

  // Voice selection handler
  const handleVoiceChange = useCallback(
    (voice_id) => {
      if (!voicePickerTargetId) return;
      
      setSelectedTemplate(prev => {
        if (!prev?.segments) return prev;
        
        const nextSegs = prev.segments.map(s => {
          if (s.id === voicePickerTargetId && s?.source?.source_type === 'tts') {
            return { ...s, source: { ...s.source, voice_id } };
          }
          return s;
        });
        
        return { ...prev, segments: nextSegs };
      });
    },
    [voicePickerTargetId, setSelectedTemplate]
  );

  // Voice name resolution effect (fetch display names for voice IDs)
  useEffect(() => {
    if (currentStep !== 3) return;
    
    // Collect all voice IDs from template segments
    const ids = new Set();
    try {
      (selectedTemplate?.segments || []).forEach(s => {
        if (s?.source?.source_type === 'tts' && s?.source?.voice_id) {
          const vid = String(s.source.voice_id);
          if (vid && vid.toLowerCase() !== 'default') ids.add(vid);
        }
      });
    } catch {}
    
    if (!ids.size) return;
    
    // Check if we already have all names
    let haveAll = true;
    for (const id of ids) {
      if (!voiceNameById[id]) {
        haveAll = false;
        break;
      }
    }
    if (haveAll) return;
    
    // Fetch missing voice names
    let cancelled = false;
    (async () => {
      try {
        setVoicesLoading(true);
        
        // Fetch from ElevenLabs
        const res = await fetchElevenVoices('', 1, 200);
        const map = {};
        for (const v of (res?.items || [])) {
          const dn = v.common_name || v.name || '';
          if (dn) map[v.voice_id] = dn;
        }
        
        if (!cancelled) setVoiceNameById(prev => ({ ...prev, ...map }));
        
        // Resolve unknown voices via backend
        const unknown = Array.from(ids).filter(
          id => id && id.toLowerCase() !== 'default' && !map[id]
        );
        
        if (unknown.length) {
          const api = makeApi(token);
          for (const id of unknown) {
            try {
              const v = await api.get(`/api/elevenlabs/voice/${encodeURIComponent(id)}/resolve`);
              const dn = v?.common_name || v?.name || '';
              if (dn && !cancelled) {
                setVoiceNameById(prev => ({ ...prev, [id]: dn }));
              }
            } catch (_) {}
          }
        }
      } catch {
      } finally {
        if (!cancelled) setVoicesLoading(false);
      }
    })();
    
    return () => {
      cancelled = true;
    };
  }, [currentStep, selectedTemplate?.id, token, voiceNameById]);

  return {
    // TTS state
    ttsValues,
    setTtsValues,
    
    // Voice picker state
    showVoicePicker,
    setShowVoicePicker,
    voicePickerTargetId,
    setVoicePickerTargetId,
    
    // Voice resolution state
    voiceNameById,
    setVoiceNameById,
    voicesLoading,
    
    // Handlers
    handleTtsChange,
    handleVoiceChange,
  };
}
