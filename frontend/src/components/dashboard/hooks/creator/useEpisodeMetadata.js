import { useState, useRef, useCallback } from 'react';
import { toast } from '@/hooks/use-toast';
import { makeApi } from '@/lib/apiClient';

/**
 * Manages episode metadata (title, description, season, episode number, tags, cover art)
 * Includes AI-powered suggestion and refinement for title/description/tags
 * 
 * @param {Object} options
 * @param {string} options.token - Auth token for API calls
 * @param {Object} options.selectedTemplate - Currently selected podcast template
 * @param {string} options.uploadedFilename - Uploaded audio filename  
 * @param {string} options.expectedEpisodeId - Expected episode ID from assembly
 * @param {string} options.transcriptPath - Path to transcript file
 * @param {Function} options.resetTranscriptState - Callback to reset transcript state
 * @returns {Object} Metadata state and handlers
 */
export default function useEpisodeMetadata({
  token,
  selectedTemplate,
  uploadedFilename,
  expectedEpisodeId,
  transcriptPath,
  resetTranscriptState,
}) {
  // Episode metadata state
  const [episodeDetails, setEpisodeDetails] = useState({
    season: '1',
    episodeNumber: '',
    title: '',
    description: '',
    coverArt: null,
    coverArtPreview: null,
    cover_image_path: null,
    cover_crop: null,
  });

  // AI suggestion busy states
  const [isAiTitleBusy, setIsAiTitleBusy] = useState(false);
  const [isAiDescBusy, setIsAiDescBusy] = useState(false);

  // AI cache (avoid re-generating same content)
  const aiCacheRef = useRef({ title: null, notes: null, tags: null });

  // Details change handler
  const handleDetailsChange = useCallback(
    (field, value) => {
      setEpisodeDetails(prev => ({ ...prev, [field]: value }));
    },
    []
  );

  // AI Title Suggestion
  const suggestTitle = useCallback(
    async (opts = {}) => {
      const force = !!opts.force;
      const currentText = opts.currentText || null;
      
      if (!force && !currentText && aiCacheRef.current.title) {
        return aiCacheRef.current.title;
      }

      const api = makeApi(token);
      const payload = {
        episode_id: expectedEpisodeId || crypto.randomUUID(),
        podcast_id: selectedTemplate?.podcast_id,
        transcript_path: transcriptPath || null,
        hint: uploadedFilename || null,
        base_prompt: '',
        extra_instructions: selectedTemplate?.ai_settings?.title_instructions || '',
      };

      // Add current_text if refining
      if (currentText) {
        payload.current_text = currentText;
      }

      let title = '';
      try {
        const res = await api.post('/api/ai/title', payload);
        title = res?.title || '';
      } catch (e) {
        if (e && e.status === 409) {
          resetTranscriptState();
          try {
            toast({
              title: 'Transcript not ready',
              description: 'Transcript not ready yet — still processing',
              variant: 'default',
            });
          } catch {}
          return '';
        }
        try {
          if (e && e.status === 429) {
            toast({
              variant: 'destructive',
              title: 'AI Title error',
              description: 'Too many requests — please slow down and try again.',
            });
          } else {
            const code = e && e.status ? ` (${e.status})` : '';
            toast({
              variant: 'destructive',
              title: 'AI Title error',
              description: `Request failed${code}. Please try again.`,
            });
          }
        } catch {}
        return '';
      }

      // Only cache new generations, not refinements
      if (!currentText) aiCacheRef.current.title = title;
      return title;
    },
    [token, expectedEpisodeId, selectedTemplate, transcriptPath, uploadedFilename, resetTranscriptState]
  );

  // AI Description Suggestion
  const suggestNotes = useCallback(
    async (opts = {}) => {
      const force = !!opts.force;
      const currentText = opts.currentText || null;
      
      if (!force && !currentText && aiCacheRef.current.notes) {
        return aiCacheRef.current.notes;
      }

      const api = makeApi(token);
      const payload = {
        episode_id: expectedEpisodeId || crypto.randomUUID(),
        podcast_id: selectedTemplate?.podcast_id,
        transcript_path: transcriptPath || null,
        hint: uploadedFilename || null,
        base_prompt: '',
        extra_instructions: selectedTemplate?.ai_settings?.notes_instructions || '',
      };

      // Add current_text if refining
      if (currentText) {
        payload.current_text = currentText;
      }

      let desc = '';
      try {
        const res = await api.post('/api/ai/notes', payload);
        desc = res?.description || '';
      } catch (e) {
        if (e && e.status === 409) {
          resetTranscriptState();
          try {
            toast({
              title: 'Transcript not ready',
              description: 'Transcript not ready yet — still processing',
              variant: 'default',
            });
          } catch {}
          return '';
        }
        try {
          if (e && e.status === 429) {
            toast({
              variant: 'destructive',
              title: 'AI Description error',
              description: 'Too many requests — please slow down and try again.',
            });
          } else {
            const code = e && e.status ? ` (${e.status})` : '';
            toast({
              variant: 'destructive',
              title: 'AI Description error',
              description: `Request failed${code}. Please try again.`,
            });
          }
        } catch {}
        return '';
      }

      // Only cache new generations, not refinements
      if (!currentText) aiCacheRef.current.notes = desc;
      return desc;
    },
    [token, expectedEpisodeId, selectedTemplate, transcriptPath, uploadedFilename, resetTranscriptState]
  );

  // AI Tags Suggestion
  const suggestTags = useCallback(
    async () => {
      if (aiCacheRef.current.tags) return aiCacheRef.current.tags;

      const api = makeApi(token);
      const payload = {
        episode_id: expectedEpisodeId || crypto.randomUUID(),
        podcast_id: selectedTemplate?.podcast_id,
        transcript_path: transcriptPath || null,
        hint: uploadedFilename || null,
        tags_always_include: selectedTemplate?.ai_settings?.tags_always_include || [],
      };

      try {
        const res = await api.post('/api/ai/tags', payload);
        const tags = Array.isArray(res?.tags) ? res.tags : [];
        aiCacheRef.current.tags = tags;
        return tags;
      } catch (e) {
        if (e && e.status === 409) {
          resetTranscriptState();
          try {
            toast({
              title: 'Transcript not ready',
              description: 'Transcript not ready yet — still processing',
              variant: 'default',
            });
          } catch {}
          return [];
        }
        try {
          if (e && e.status === 429) {
            toast({
              variant: 'destructive',
              title: 'AI Tags error',
              description: 'Too many requests — please slow down and try again.',
            });
          } else {
            const code = e && e.status ? ` (${e.status})` : '';
            toast({
              variant: 'destructive',
              title: 'AI Tags error',
              description: `Request failed${code}. Please try again.`,
            });
          }
        } catch {}
        return [];
      }
    },
    [token, expectedEpisodeId, selectedTemplate, transcriptPath, uploadedFilename, resetTranscriptState]
  );

  // User-facing AI handlers
  const handleAISuggestTitle = useCallback(
    async () => {
      if (isAiTitleBusy) return;
      setIsAiTitleBusy(true);
      try {
        const title = await suggestTitle({ force: true });
        if (title && !/[a-f0-9]{16,}/i.test(title)) {
          handleDetailsChange('title', title);
        }
      } finally {
        setIsAiTitleBusy(false);
      }
    },
    [isAiTitleBusy, suggestTitle, handleDetailsChange]
  );

  const handleAIRefineTitle = useCallback(
    async () => {
      if (isAiTitleBusy) return;
      const currentTitle = (episodeDetails?.title || '').trim();
      if (!currentTitle) {
        try {
          toast({
            title: 'No title to refine',
            description: 'Please enter a title first, then use Refine to improve it.',
            variant: 'default',
          });
        } catch {}
        return;
      }
      setIsAiTitleBusy(true);
      try {
        const title = await suggestTitle({ force: true, currentText: currentTitle });
        if (title && !/[a-f0-9]{16,}/i.test(title)) {
          handleDetailsChange('title', title);
        }
      } finally {
        setIsAiTitleBusy(false);
      }
    },
    [isAiTitleBusy, episodeDetails, suggestTitle, handleDetailsChange]
  );

  const handleAISuggestDescription = useCallback(
    async () => {
      if (isAiDescBusy) return;
      setIsAiDescBusy(true);
      try {
        const notes = await suggestNotes({ force: true });
        const cleaned = (notes || '')
          .replace(/^(?:\*\*?)?description:?\*?\*?\s*/i, '')
          .replace(/^#+\s*description\s*/i, '')
          .trim();
        if (cleaned) handleDetailsChange('description', cleaned);
      } finally {
        setIsAiDescBusy(false);
      }
    },
    [isAiDescBusy, suggestNotes, handleDetailsChange]
  );

  const handleAIRefineDescription = useCallback(
    async () => {
      if (isAiDescBusy) return;
      const currentDesc = (episodeDetails?.description || '').trim();
      if (!currentDesc) {
        try {
          toast({
            title: 'No description to refine',
            description: 'Please enter a description first, then use Refine to improve it.',
            variant: 'default',
          });
        } catch {}
        return;
      }
      setIsAiDescBusy(true);
      try {
        const notes = await suggestNotes({ force: true, currentText: currentDesc });
        const cleaned = (notes || '')
          .replace(/^(?:\*\*?)?description:?\*?\*?\s*/i, '')
          .replace(/^#+\s*description\s*/i, '')
          .trim();
        if (cleaned) handleDetailsChange('description', cleaned);
      } finally {
        setIsAiDescBusy(false);
      }
    },
    [isAiDescBusy, episodeDetails, suggestNotes, handleDetailsChange]
  );

  return {
    // State
    episodeDetails,
    setEpisodeDetails,
    isAiTitleBusy,
    isAiDescBusy,
    aiCacheRef,
    
    // Handlers
    handleDetailsChange,
    handleAISuggestTitle,
    handleAIRefineTitle,
    handleAISuggestDescription,
    handleAIRefineDescription,
    
    // AI functions (exposed for advanced use)
    suggestTitle,
    suggestNotes,
    suggestTags,
  };
}
