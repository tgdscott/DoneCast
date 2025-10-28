import { useState, useEffect, useMemo, useRef, useCallback } from "react";
import { makeApi } from "@/lib/apiClient";
import { toast } from "@/hooks/use-toast";
import { useAuth } from "@/AuthContext.jsx";
import { Loader2, ArrowLeft, Save } from "lucide-react";
import { Button } from "@/components/ui/button";

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
import { AI_DEFAULT } from "./constants";

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
          api.get('/api/music-assets/global'),
        ]);

        if (mediaData.status === 'fulfilled') {
          setMediaFiles(Array.isArray(mediaData.value) ? mediaData.value : []);
        }
        
        if (podcastsData.status === 'fulfilled') {
          setPodcasts(Array.isArray(podcastsData.value) ? podcastsData.value : []);
        }
        
        if (globalMusicData.status === 'fulfilled') {
          setGlobalMusicAssets(Array.isArray(globalMusicData.value) ? globalMusicData.value : []);
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

  // Check page completion
  useEffect(() => {
    if (!template) return;
    
    const completed = new Set();
    
    // Basics page: has name and podcast_id
    if (template.name && template.podcast_id) {
      completed.add('basics');
    }
    
    // Schedule page: always optional, mark complete if visited
    // (We'll track this via user interaction)
    
    // AI page: always optional, mark complete if has settings
    if (template.ai_settings && Object.keys(template.ai_settings).length > 0) {
      completed.add('ai');
    }
    
    // Structure page: has at least intro, content, outro
    if (template.segments && template.segments.length >= 3) {
      completed.add('structure');
    }
    
    // Music page: always optional
    if (template.background_music_rules && template.background_music_rules.length > 0) {
      completed.add('music');
    }
    
    // Advanced page: always optional
    
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
  }, [template, podcasts, token, isNewTemplate, templateId, onTemplateSaved]);

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

  // Render current page
  const renderPage = () => {
    if (!template) return null;

    const pageProps = {
      template,
      setTemplate,
      mediaFiles,
      podcasts,
      globalMusicAssets,
      token,
      onNavigate: handleNavigate,
      currentPage,
      isNewTemplate,
      onScheduleDirtyChange: setScheduleDirty,
      authUser,
    };

    switch (currentPage) {
      case 'basics':
        return <TemplateBasicsPage {...pageProps} />;
      case 'schedule':
        return <TemplateSchedulePage {...pageProps} />;
      case 'ai':
        return <TemplateAIPage {...pageProps} />;
      case 'structure':
        return <TemplateStructurePage {...pageProps} />;
      case 'music':
        return <TemplateMusicPage {...pageProps} />;
      case 'advanced':
        return <TemplateAdvancedPage {...pageProps} />;
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
          onNavigate={handleNavigate}
          onSave={handleSave}
          isSaving={isSaving}
          isDirty={isDirty}
        />

        {/* Content Area */}
        <main className="flex-1 min-w-0">
          {renderPage()}
        </main>
      </div>
    </div>
  );
}
