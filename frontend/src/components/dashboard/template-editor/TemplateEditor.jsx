import { useState, useEffect, useMemo, useRef, useCallback } from "react";
import { makeApi } from "@/lib/apiClient";
import { toast } from "@/hooks/use-toast";
import { useAuth } from "@/AuthContext.jsx";
import { Loader2, ArrowLeft, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { createTTS } from "@/api/media";
import VoicePicker from "@/components/VoicePicker";

// Layout components
import TemplateEditorSidebar, { PAGES } from "./layout/TemplateEditorSidebar";

// Page components
import TemplateBasicsPage from "./pages/TemplateBasicsPage";
import TemplateSchedulePage from "./pages/TemplateSchedulePage";
import TemplateAIPage from "./pages/TemplateAIPage";
import TemplateStructurePage from "./pages/TemplateStructurePage";
import TemplateMusicPage from "./pages/TemplateMusicPage";
import TemplateAdvancedPage from "./pages/TemplateAdvancedPage";

// Constants
import { AI_DEFAULT, DEFAULT_VOLUME_LEVEL, volumeLevelToDb } from "./constants";

/**
 * Template Editor with Sidebar Navigation
 * Refactored October 19, 2024 - Guide-style navigation pattern
 */
export default function TemplateEditor({ templateId, onBack, token, onTemplateSaved }) {
  const { user: authUser } = useAuth();
  
  // Core state
  const [template, setTemplate] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(null);
  
  // Reference data
  const [mediaFiles, setMediaFiles] = useState([]);
  const [podcasts, setPodcasts] = useState([]);
  const [globalMusicAssets, setGlobalMusicAssets] = useState([]);
  
  // Navigation state
  const [currentPage, setCurrentPage] = useState('basics');
  const [completedPages, setCompletedPages] = useState(new Set());
  
  // Dirty tracking
  const [baselineTemplate, setBaselineTemplate] = useState(null);
  const [scheduleDirty, setScheduleDirty] = useState(false);
  const skipExitPromptRef = useRef(false);
  
  // Voice & TTS state
  const [voiceId, setVoiceId] = useState(null);
  const [showVoicePicker, setShowVoicePicker] = useState(false);
  const [voiceName, setVoiceName] = useState(null);
  const [internVoiceId, setInternVoiceId] = useState(null);
  const [showInternVoicePicker, setShowInternVoicePicker] = useState(false);
  const [internVoiceName, setInternVoiceName] = useState(null);
  const [ttsOpen, setTtsOpen] = useState(false);
  const [ttsTargetSegment, setTtsTargetSegment] = useState(null);
  const [ttsScript, setTtsScript] = useState("");
  const [ttsVoiceId, setTtsVoiceId] = useState(null);
  const [ttsSpeakingRate, setTtsSpeakingRate] = useState(1.0);
  const [ttsFriendlyName, setTtsFriendlyName] = useState("");
  const [ttsVoices, setTtsVoices] = useState([]);
  const [ttsLoading, setTtsLoading] = useState(false);
  const [createdFromTTS, setCreatedFromTTS] = useState({});
  
  // Music upload state
  const [musicUploadIndex, setMusicUploadIndex] = useState(null);
  const [isUploadingMusic, setIsUploadingMusic] = useState(false);
  const musicUploadInputRef = useRef(null);
  const musicUploadIndexRef = useRef(null);
  
  const isNewTemplate = templateId === 'new';

  // Dirty calculation
  const templateDirty = useMemo(() => {
    if (!template || !baselineTemplate) return false;
    try {
      return JSON.stringify(template) !== JSON.stringify(baselineTemplate);
    } catch {
      return true;
    }
  }, [template, baselineTemplate]);

  const isDirty = templateDirty || scheduleDirty;

  // Prevent accidental navigation away
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!isDirty) return;
    const handler = (event) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [isDirty]);

  // Set baseline on template change
  useEffect(() => {
    if (!template) return;
    setBaselineTemplate((prev) => {
      if (prev) return prev;
      try {
        return JSON.parse(JSON.stringify(template));
      } catch {
        return prev;
      }
    });
  }, [template]);

  // Load initial data
  useEffect(() => {
    const fetchInitialData = async () => {
      setBaselineTemplate(null);
      setIsLoading(true);
      try {
        const api = makeApi(token);
        const [mediaData, podcastsData, templateData, globalMusicData] = await Promise.allSettled([
          api.get('/api/media/'),
          api.get('/api/podcasts/'),
          isNewTemplate ? Promise.resolve(null) : api.get(`/api/templates/${templateId}`),
          api.get('/api/music/assets?scope=global'),
        ]);

        if (mediaData.status === 'fulfilled') {
          setMediaFiles(Array.isArray(mediaData.value) ? mediaData.value : []);
        }
        
        if (podcastsData.status === 'fulfilled') {
          setPodcasts(Array.isArray(podcastsData.value) ? podcastsData.value : []);
        }
        
        if (globalMusicData.status === 'fulfilled') {
          const assets = globalMusicData.value?.assets || globalMusicData.value || [];
          setGlobalMusicAssets(Array.isArray(assets) ? assets : []);
        }

        if (isNewTemplate) {
          setTemplate({
            name: 'New Template',
            podcast_id: '',
            is_active: true,
            segments: [
              { id: crypto.randomUUID(), segment_type: 'intro', source: { source_type: 'static', filename: '' } },
              { id: crypto.randomUUID(), segment_type: 'content', source: { source_type: 'static', filename: '' } },
              { id: crypto.randomUUID(), segment_type: 'outro', source: { source_type: 'static', filename: '' } },
            ],
            background_music_rules: [],
            timing: { content_start_offset_s: 0, outro_start_offset_s: 0 },
            ai_settings: AI_DEFAULT,
          });
        } else if (templateData.status === 'fulfilled') {
          setTemplate(templateData.value || null);
        }
        
        setError(null);
      } catch (err) {
        setError(err?.message || String(err));
      } finally {
        setIsLoading(false);
      }
    };

    fetchInitialData();
  }, [templateId, token, isNewTemplate]);

  // Memoized filtered media lists
  const introFiles = useMemo(() => mediaFiles.filter(mf => mf.category === 'intro'), [mediaFiles]);
  const outroFiles = useMemo(() => mediaFiles.filter(mf => mf.category === 'outro'), [mediaFiles]);
  const musicFiles = useMemo(() => mediaFiles.filter(mf => mf.category === 'music'), [mediaFiles]);
  const commercialFiles = useMemo(() => mediaFiles.filter(mf => mf.category === 'commercial'), [mediaFiles]);
  
  // Check if there's a content segment
  const hasContentSegment = useMemo(() => {
    return template?.segments?.some(s => s.segment_type === 'content') || false;
  }, [template?.segments]);

  // Media uploaded callback
  const onMediaUploaded = useCallback((newFile) => {
    if (!newFile) return;
    setMediaFiles(prev => {
      const filtered = Array.isArray(prev) ? prev.filter(f => f?.filename !== newFile.filename) : [];
      return [...filtered, newFile];
    });
  }, []);

  // Initialize voice IDs and names from template when loaded
  useEffect(() => {
    const loadVoiceNames = async () => {
      if (!template) return;
      
      const api = makeApi(token);
      
      // Load ElevenLabs voice
      if (template.default_elevenlabs_voice_id) {
        setVoiceId(template.default_elevenlabs_voice_id);
        try {
          const voiceData = await api.get(`/api/elevenlabs/voice/${template.default_elevenlabs_voice_id}/resolve`);
          setVoiceName(voiceData.common_name || voiceData.name || null);
        } catch (err) {
          console.warn('Failed to load voice name:', err);
          setVoiceName(null);
        }
      }
      
      // Load Intern voice - check multiple possible locations
      const internId = template.default_intern_voice_id || 
                      template.ai_settings?.intern_voice_id ||
                      template.automation_settings?.intern_voice_id;
      if (internId) {
        setInternVoiceId(internId);
        try {
          const voiceData = await api.get(`/api/elevenlabs/voice/${internId}/resolve`);
          setInternVoiceName(voiceData.common_name || voiceData.name || null);
        } catch (err) {
          console.warn('Failed to load intern voice name:', err);
          setInternVoiceName(null);
        }
      }
    };
    
    loadVoiceNames();
  }, [template?.id, token]); // Only run when template ID changes (initial load or switching templates)

  // Check page completion
  useEffect(() => {
    if (!template) {
      setCompletedPages(new Set());
      return;
    }
    
    const completed = new Set();
    
    // Basics page: has name and podcast_id
    if (template.name && template.podcast_id) {
      completed.add('basics');
    }
    
    // Schedule page: always optional, considered complete if template is saved
    if (template.id) {
      completed.add('schedule');
    }
    
    // AI page: always optional, mark complete if has settings or is saved
    if (template.id || (template.ai_settings && Object.keys(template.ai_settings).length > 0)) {
      completed.add('ai');
    }
    
    // Structure page: has at least intro, content, outro
    if (template.segments && template.segments.length >= 3) {
      const hasIntro = template.segments.some(s => s.segment_type === 'intro');
      const hasContent = template.segments.some(s => s.segment_type === 'content');
      const hasOutro = template.segments.some(s => s.segment_type === 'outro');
      if (hasIntro && hasContent && hasOutro) {
        completed.add('structure');
      }
    }
    
    // Music page: always optional, complete if template saved or has music
    if (template.id || (template.background_music_rules && template.background_music_rules.length > 0)) {
      completed.add('music');
    }
    
    // Advanced page: always optional, complete if template saved
    if (template.id) {
      completed.add('advanced');
    }
    
    setCompletedPages(completed);
  }, [template]);

  // Save handler
  const handleSave = useCallback(async () => {
    if (!template) return;
    if (!template.podcast_id || podcasts.length === 0) {
      toast({
        title: "Action needed",
        description: "A show is required for this template. Please select one.",
        variant: "destructive",
      });
      setCurrentPage('basics');
      return;
    }

    setIsSaving(true);
    try {
      const api = makeApi(token);
      const payload = { ...template };
      
      // Save voice settings
      payload.default_elevenlabs_voice_id = voiceId || null;
      payload.default_intern_voice_id = internVoiceId || null;
      // Also save in ai_settings for redundancy
      if (!payload.ai_settings) {
        payload.ai_settings = {};
      }
      payload.ai_settings.intern_voice_id = internVoiceId || null;
      
      // Clean up segments
      if (Array.isArray(payload.segments)) {
        payload.segments = payload.segments.map(seg => {
          if (seg.segment_type !== 'content') {
            const st = seg?.source?.source_type;
            if (st === 'static') {
              const filename = seg?.source?.filename || '';
              return { ...seg, source: { source_type: 'static', filename } };
            }
            if (st === 'tts') {
              return {
                ...seg,
                source: {
                  source_type: 'tts',
                  script: seg.source.script || '',
                  voice_id: seg.source.voice_id || null,
                  speaking_rate: seg.source.speaking_rate || 1.0,
                },
              };
            }
          }
          return seg;
        });
      }

      let savedTemplate;
      if (isNewTemplate) {
        savedTemplate = await api.post('/api/templates/', payload);
      } else {
        savedTemplate = await api.put(`/api/templates/${templateId}`, payload);
      }

      setTemplate(savedTemplate);
      setBaselineTemplate(JSON.parse(JSON.stringify(savedTemplate)));
      
      toast({
        title: "Success!",
        description: "Template saved successfully.",
      });

      if (onTemplateSaved) onTemplateSaved(savedTemplate);
    } catch (err) {
      toast({
        title: "Error",
        description: err?.message || 'Failed to save template',
        variant: "destructive",
      });
    } finally {
      setIsSaving(false);
    }
  }, [template, podcasts, token, isNewTemplate, templateId, onTemplateSaved, voiceId, internVoiceId]);

  // Back handler with dirty check
  const handleBackClick = useCallback(() => {
    if (isDirty && !skipExitPromptRef.current) {
      if (!window.confirm('You have unsaved changes. Are you sure you want to leave?')) {
        return;
      }
    }
    skipExitPromptRef.current = false;
    onBack();
  }, [isDirty, onBack]);

  // Navigation handler
  const handleNavigate = useCallback((pageId) => {
    setCurrentPage(pageId);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, []);

  // Template change handler
  const handleTemplateChange = useCallback((field, value) => {
    setTemplate(prev => prev ? { ...prev, [field]: value } : null);
  }, []);

  // Timing handlers
  const handleTimingChange = useCallback((field, valueInSeconds) => {
    setTemplate(prev => {
      if (!prev) return prev;
      const newTiming = { ...prev.timing, [field]: valueInSeconds };
      return { ...prev, timing: newTiming };
    });
  }, []);

  // Background music handlers
  const handleBackgroundMusicChange = useCallback((index, field, value) => {
    setTemplate(prev => {
      if (!prev) return prev;
      const newRules = [...(prev.background_music_rules || [])];
      if (newRules[index]) {
        newRules[index] = { ...newRules[index], [field]: value };
      }
      return { ...prev, background_music_rules: newRules };
    });
  }, []);

  const handleAddBackgroundMusicRule = useCallback(() => {
    const newRule = {
      id: crypto.randomUUID(),
      apply_to_segments: ['content'],
      music_filename: '',
      start_offset_s: 0,
      end_offset_s: 0,
      fade_in_s: 2,
      fade_out_s: 3,
      volume_db: Number(volumeLevelToDb(DEFAULT_VOLUME_LEVEL).toFixed(1)),
    };
    setTemplate(prev => {
      if (!prev) return prev;
      return { ...prev, background_music_rules: [...(prev.background_music_rules || []), newRule] };
    });
  }, []);

  const handleRemoveBackgroundMusicRule = useCallback((index) => {
    setTemplate(prev => {
      if (!prev) return prev;
      const newRules = [...(prev.background_music_rules || [])];
      newRules.splice(index, 1);
      return { ...prev, background_music_rules: newRules };
    });
  }, []);

  const handleSetMusicVolumeLevel = useCallback((index, level) => {
    const numeric = typeof level === 'number' ? level : parseFloat(level);
    const fallback = DEFAULT_VOLUME_LEVEL;
    const clamped = Math.max(1, Math.min(11, Number.isFinite(numeric) ? numeric : fallback));
    const dbValue = Number(volumeLevelToDb(clamped).toFixed(1));
    handleBackgroundMusicChange(index, 'volume_db', dbValue);
  }, [handleBackgroundMusicChange]);

  // Music upload handlers
  const handleStartMusicUpload = useCallback((index) => {
    if (isUploadingMusic) return;
    setMusicUploadIndex(index);
    musicUploadIndexRef.current = index;
    try {
      if (musicUploadInputRef.current) {
        musicUploadInputRef.current.click();
      }
    } catch (_) {
      /* no-op */
    }
  }, [isUploadingMusic]);

  const handleMusicFileSelected = async (event) => {
    const file = event?.target?.files?.[0];
    const targetIndex = musicUploadIndexRef.current;
    if (!file || targetIndex == null) {
      if (event?.target) event.target.value = '';
      setMusicUploadIndex(null);
      musicUploadIndexRef.current = null;
      return;
    }

    setIsUploadingMusic(true);
    try {
      const api = makeApi(token);
      const fd = new FormData();
      fd.append('files', file);
      const data = await api.raw('/api/media/upload/music', { method: 'POST', body: fd });
      const uploadedItem = Array.isArray(data) ? data[0] : data;
      if (!uploadedItem?.filename) {
        throw new Error('Upload succeeded but no file was returned.');
      }
      const uploaded = {
        id: uploadedItem.id || crypto.randomUUID(),
        filename: uploadedItem.filename,
        friendly_name: uploadedItem.friendly_name || undefined,
        category: uploadedItem.category || 'music',
        content_type: uploadedItem.content_type || 'audio/mpeg',
      };
      onMediaUploaded(uploaded);
      handleBackgroundMusicChange(targetIndex, 'music_filename', uploaded.filename);
      toast({ title: 'Music uploaded', description: 'Your track is now available in the template.' });
    } catch (e) {
      const message = e?.message || 'Could not upload music.';
      toast({ variant: 'destructive', title: 'Upload failed', description: message });
    } finally {
      setIsUploadingMusic(false);
      setMusicUploadIndex(null);
      musicUploadIndexRef.current = null;
      if (event?.target) {
        try { event.target.value = ''; } catch (_) {}
      }
    }
  };

  // Segment handlers
  const handleAddSegment = useCallback((type) => {
    setTemplate(prev => {
      if (!prev) return prev;
      const newSegment = {
        id: crypto.randomUUID(),
        segment_type: type,
        source: { source_type: 'static', filename: '' },
      };
      const segments = [...(prev.segments || [])];
      const contentIndex = segments.findIndex(s => s.segment_type === 'content');
      
      if (type === 'intro') {
        segments.splice(contentIndex !== -1 ? contentIndex : 0, 0, newSegment);
      } else if (type === 'outro') {
        segments.push(newSegment);
      } else { // commercials
        segments.splice(contentIndex !== -1 ? contentIndex + 1 : segments.length, 0, newSegment);
      }
      return { ...prev, segments };
    });
  }, []);

  const handleDeleteSegment = useCallback((segmentId) => {
    setTemplate(prev => {
      if (!prev) return prev;
      return { ...prev, segments: (prev.segments || []).filter(seg => seg.id !== segmentId) };
    });
  }, []);

  const handleSourceChange = useCallback((segmentId, newSource) => {
    setTemplate(prev => {
      if (!prev) return prev;
      const segments = (prev.segments || []).map(seg => {
        if (seg.id === segmentId) {
          return { ...seg, source: newSource };
        }
        return seg;
      });
      return { ...prev, segments };
    });
  }, []);

  const handleDragEnd = useCallback((result) => {
    if (!result.destination) return;

    setTemplate(prev => {
      if (!prev) return prev;
      const items = Array.from(prev.segments || []);
      const [reorderedItem] = items.splice(result.source.index, 1);
      items.splice(result.destination.index, 0, reorderedItem);

      // Enforce structure rules
      const contentIndex = items.findIndex(item => item.segment_type === 'content');
      const firstOutroIndex = items.findIndex(item => item.segment_type === 'outro');

      if (contentIndex !== -1) {
        // Rule: Intros must be before content
        if (reorderedItem.segment_type === 'intro' && result.destination.index > contentIndex) return prev;
        // Rule: Content cannot be dragged before an intro
        if (reorderedItem.segment_type === 'content' && items.some((item, index) => item.segment_type === 'intro' && index > result.destination.index)) return prev;
      }
      if (firstOutroIndex !== -1) {
        // Rule: Outros must be after content
        if (reorderedItem.segment_type === 'outro' && contentIndex !== -1 && result.destination.index < contentIndex) return prev;
        // Rule: Content cannot be dragged after an outro
        if (reorderedItem.segment_type === 'content' && result.destination.index > firstOutroIndex) return prev;
      }

      return { ...prev, segments: items };
    });
  }, []);

  // TTS/Voice handlers
  const handleOpenTTS = useCallback((segment) => {
    setTtsTargetSegment(segment);
    setTtsScript(segment?.source?.script || "");
    setTtsVoiceId(segment?.source?.voice_id || voiceId || null);
    setTtsSpeakingRate(segment?.source?.speaking_rate || 1.0);
    setTtsFriendlyName("");
    setTtsOpen(true);
  }, [voiceId]);

  const handleChooseVoice = useCallback(() => {
    setShowVoicePicker(true);
  }, []);

  const handleChooseInternVoice = useCallback(() => {
    setShowInternVoicePicker(true);
  }, []);

  // Render current page
  const renderPage = () => {
    if (!template) return null;

    // Common props for all pages
    const commonProps = {
      onNext: () => {
        const currentIndex = PAGES.findIndex(p => p.id === currentPage);
        if (currentIndex < PAGES.length - 1) {
          handleNavigate(PAGES[currentIndex + 1].id);
        }
      },
      onBack: () => {
        const currentIndex = PAGES.findIndex(p => p.id === currentPage);
        if (currentIndex > 0) {
          handleNavigate(PAGES[currentIndex - 1].id);
        }
      },
    };

    switch (currentPage) {
      case 'basics':
        return (
          <TemplateBasicsPage
            template={template}
            podcasts={podcasts}
            onTemplateChange={handleTemplateChange}
            {...commonProps}
          />
        );
      case 'schedule':
        return (
          <TemplateSchedulePage
            token={token}
            templateId={templateId}
            userTimezone={authUser?.timezone}
            isNewTemplate={!template?.id}
            onDirtyChange={setScheduleDirty}
            {...commonProps}
          />
        );
      case 'ai':
        return (
          <TemplateAIPage
            aiSettings={template.ai_settings || AI_DEFAULT}
            defaultSettings={AI_DEFAULT}
            onChange={(newSettings) => handleTemplateChange('ai_settings', newSettings)}
            {...commonProps}
          />
        );
      case 'structure':
        return (
          <TemplateStructurePage
            segments={template.segments || []}
            hasContentSegment={hasContentSegment}
            addSegment={handleAddSegment}
            onSourceChange={handleSourceChange}
            deleteSegment={handleDeleteSegment}
            introFiles={introFiles}
            outroFiles={outroFiles}
            commercialFiles={commercialFiles}
            onDragEnd={handleDragEnd}
            onOpenTTS={handleOpenTTS}
            createdFromTTS={createdFromTTS}
            templateVoiceId={voiceId}
            token={token}
            onMediaUploaded={onMediaUploaded}
            {...commonProps}
          />
        );
      case 'music':
        return (
          <TemplateMusicPage
            template={template}
            onTimingChange={handleTimingChange}
            backgroundMusicRules={template.background_music_rules || []}
            onBackgroundMusicChange={handleBackgroundMusicChange}
            onAddBackgroundMusicRule={handleAddBackgroundMusicRule}
            onRemoveBackgroundMusicRule={handleRemoveBackgroundMusicRule}
            musicFiles={musicFiles}
            onStartMusicUpload={handleStartMusicUpload}
            musicUploadIndex={musicUploadIndex}
            isUploadingMusic={isUploadingMusic}
            musicUploadInputRef={musicUploadInputRef}
            onMusicFileSelected={handleMusicFileSelected}
            onSetMusicVolumeLevel={handleSetMusicVolumeLevel}
            voiceName={voiceName}
            onChooseVoice={handleChooseVoice}
            internVoiceDisplay={internVoiceName || "Default"}
            onChooseInternVoice={handleChooseInternVoice}
            globalMusicAssets={globalMusicAssets}
            {...commonProps}
          />
        );
      case 'advanced':
        return (
          <TemplateAdvancedPage
            template={template}
            onTemplateChange={handleTemplateChange}
            voiceName={voiceName}
            onChooseVoice={handleChooseVoice}
            internVoiceDisplay={internVoiceName || "Default"}
            onChooseInternVoice={handleChooseInternVoice}
            {...commonProps}
          />
        );
      default:
        return <div>Unknown page: {currentPage}</div>;
    }
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="flex justify-center items-center min-h-screen">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="p-6">
        <div className="bg-red-50 border border-red-200 rounded-lg p-4">
          <p className="text-red-800 font-medium">Error loading template</p>
          <p className="text-red-600 text-sm mt-1">{error}</p>
          <Button onClick={handleBackClick} variant="outline" className="mt-4">
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back to Dashboard
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 sticky top-0 z-40">
        <div className="px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Button onClick={handleBackClick} variant="ghost" size="sm">
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back
            </Button>
            <h1 className="text-xl font-bold text-gray-800">
              {template?.name || 'Template Editor'}
            </h1>
          </div>
          <div className="flex items-center gap-3">
            {isDirty && !isSaving && (
              <span className="text-xs text-amber-600 font-medium">Unsaved changes</span>
            )}
            <Button
              onClick={handleSave}
              disabled={isSaving}
              className="bg-blue-600 hover:bg-blue-700 text-white"
            >
              {isSaving ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Saving...
                </>
              ) : (
                <>
                  <Save className="w-4 h-4 mr-2" />
                  Save Template
                </>
              )}
            </Button>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex gap-6 p-6 max-w-7xl mx-auto">
        {/* Sidebar */}
        <TemplateEditorSidebar
          currentPage={currentPage}
          completedPages={completedPages}
          onPageChange={handleNavigate}
          onSave={handleSave}
          isSaving={isSaving}
          isDirty={isDirty}
        />

        {/* Content Area */}
        <main className="flex-1 min-w-0">
          {renderPage()}
        </main>
      </div>

      {/* Voice Picker Dialogs */}
      {showVoicePicker && (
        <VoicePicker
          value={voiceId || null}
          onChange={(id) => setVoiceId(id)}
          onSelect={(item) => setVoiceName(item?.common_name || item?.name || null)}
          onClose={() => setShowVoicePicker(false)}
          token={token}
        />
      )}
      {showInternVoicePicker && (
        <VoicePicker
          value={internVoiceId || null}
          onChange={(id) => {
            setInternVoiceId(id);
            if (!id) setInternVoiceName(null);
          }}
          onSelect={(item) => setInternVoiceName(item?.common_name || item?.name || null)}
          onClose={() => setShowInternVoicePicker(false)}
          token={token}
        />
      )}
    </div>
  );
}
