import { useState, useEffect, useCallback, useMemo } from 'react';
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

  // Compute active segment based on voicePickerTargetId
  const activeSegment = useMemo(() => {
    if (!voicePickerTargetId || !selectedTemplate?.segments) return null;
    
    // Try to find segment by id first
    let segment = selectedTemplate.segments.find(s => s.id === voicePickerTargetId);
    
    // If not found by id, try matching by other identifiers
    if (!segment) {
      segment = selectedTemplate.segments.find(s => {
        // Try matching by prompt_id if it exists
        if (s?.source?.prompt_id === voicePickerTargetId) return true;
        // Try matching by slug
        if (s?.slug === voicePickerTargetId) return true;
        // Try matching by name
        if (s?.name === voicePickerTargetId) return true;
        return false;
      });
    }
    
    // If still not found and targetId is a computed fallback (e.g., "segment-0"), try index matching
    if (!segment && typeof voicePickerTargetId === 'string' && voicePickerTargetId.startsWith('segment-')) {
      const indexMatch = voicePickerTargetId.match(/^segment-(\d+)$/);
      if (indexMatch) {
        const index = parseInt(indexMatch[1], 10);
        if (!isNaN(index) && index >= 0 && index < selectedTemplate.segments.length) {
          segment = selectedTemplate.segments[index];
        }
      }
    }
    
    // Only return TTS segments
    if (segment?.source?.source_type === 'tts') {
      return segment;
    }
    
    return null;
  }, [voicePickerTargetId, selectedTemplate?.segments]);

  // TTS value change handler
  const handleTtsChange = useCallback(
    (promptId, value) => {
      setTtsValues(prev => ({ ...prev, [promptId]: value }));
    },
    []
  );

  // Helper function to match a segment by voicePickerTargetId (same logic as activeSegment)
  // Note: Index-based matching for computed keys is handled in handleVoiceChange using the segments array
  const matchesSegment = useCallback((segment, targetId, segmentIndex = null, allSegments = null) => {
    if (!segment || !targetId) return false;
    // Try matching by id first
    if (segment.id === targetId) return true;
    // Try matching by prompt_id if it exists
    if (segment?.source?.prompt_id === targetId) return true;
    // Try matching by slug
    if (segment?.slug === targetId) return true;
    // Try matching by name
    if (segment?.name === targetId) return true;
    // Try index-based matching for computed fallback keys (e.g., "segment-0")
    if (typeof targetId === 'string' && targetId.startsWith('segment-') && segmentIndex !== null) {
      const indexMatch = targetId.match(/^segment-(\d+)$/);
      if (indexMatch) {
        const targetIndex = parseInt(indexMatch[1], 10);
        if (!isNaN(targetIndex) && targetIndex === segmentIndex) return true;
      }
    }
    return false;
  }, []);

  // Voice selection handler
  const handleVoiceChange = useCallback(
    (voice_id, voiceItem = null) => {
      if (!voicePickerTargetId) return;
      
      setSelectedTemplate(prev => {
        if (!prev?.segments) return prev;
        
        const nextSegs = prev.segments.map((s, index) => {
          if (matchesSegment(s, voicePickerTargetId, index, prev.segments) && s?.source?.source_type === 'tts') {
            const updatedSource = { ...s.source, voice_id };
            // If full voice object provided, store the display name
            if (voiceItem) {
              const displayName = voiceItem.common_name || voiceItem.name || null;
              if (displayName) {
                updatedSource.voice_name = displayName;
              }
            }
            return { ...s, source: updatedSource };
          }
          return s;
        });
        
        return { ...prev, segments: nextSegs };
      });
    },
    [voicePickerTargetId, setSelectedTemplate, matchesSegment]
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
    activeSegment,
    
    // Voice resolution state
    voiceNameById,
    setVoiceNameById,
    voicesLoading,
    
    // Handlers
    handleTtsChange,
    handleVoiceChange,
  };
}
