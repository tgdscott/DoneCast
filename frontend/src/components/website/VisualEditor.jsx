/**
 * Visual Editor - Main drag-and-drop website builder interface
 * Combines section palette, canvas, and configuration
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { ArrowLeft, Loader2, Palette, RotateCcw, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import SectionPalette from "./SectionPalette";
import SectionCanvas from "./SectionCanvas";
import SectionConfigModal from "./SectionConfigModal";
import CSSEditorDialog from "@/components/dashboard/CSSEditorDialog";
import ResetConfirmDialog from "@/components/dashboard/ResetConfirmDialog";
import { useAvailableSections, useWebsiteSections, useWebsiteGeneration } from "@/hooks/useVisualEditor";
import { useWebsiteBuilder, useWebsiteCSS } from "@/hooks/useWebsiteBuilder";

export default function VisualEditor({ token, podcast, onBack }) {
  // Debug: Track renders
  const renderCountRef = useRef(0);
  renderCountRef.current += 1;
  if (renderCountRef.current <= 10 || renderCountRef.current % 10 === 0) {
    console.log(`[VisualEditor] Render #${renderCountRef.current}`, {
      podcastId: podcast?.id,
      podcastName: podcast?.name,
      timestamp: Date.now()
    });
  }
  
  // UI state
  const [editingSection, setEditingSection] = useState(null);
  const [showCSSEditor, setShowCSSEditor] = useState(false);
  const [showResetDialog, setShowResetDialog] = useState(false);
  const [refining, setRefining] = useState(false);

  // Load available sections
  const { availableSections, availableSectionDefs, loading: sectionsLoading } = useAvailableSections(token);

  // Load website data - only initialize hook once podcast is stable
  const podcastIdRef = useRef(podcast.id);
  if (podcastIdRef.current !== podcast.id) {
    podcastIdRef.current = podcast.id;
  }
  
  const {
    website,
    loading: websiteLoading,
    loadWebsite,
    resetWebsite,
  } = useWebsiteBuilder(token, podcastIdRef.current);
  
  // Track if we've done initial load to prevent loops
  const initialLoadDoneRef = useRef(false);
  
  // Debug: Log when loadWebsite changes
  const loadWebsiteRefPrev = useRef(loadWebsite);
  useEffect(() => {
    if (loadWebsiteRefPrev.current !== loadWebsite) {
      console.log('[VisualEditor] loadWebsite function changed', {
        podcastId: podcast.id,
        prev: loadWebsiteRefPrev.current?.toString().substring(0, 50),
        new: loadWebsite?.toString().substring(0, 50)
      });
      loadWebsiteRefPrev.current = loadWebsite;
    }
  }, [loadWebsite, podcast.id]);

  // Load and manage sections
  const {
    sections,
    sectionsConfig,
    sectionsEnabled,
    loading: sectionsDataLoading,
    loadSections,
    reorderSections,
    toggleSection,
    saveSectionConfig,
    addSection,
    deleteSection,
    refineSection: refineSectionWithAI,
  } = useWebsiteSections(token, podcast.id, availableSections);

  // Use refs to avoid recreating callbacks when loadWebsite/loadSections change
  const loadWebsiteRef = useRef(loadWebsite);
  const loadSectionsRef = useRef(loadSections);
  
  useEffect(() => {
    loadWebsiteRef.current = loadWebsite;
  }, [loadWebsite]);
  
  useEffect(() => {
    loadSectionsRef.current = loadSections;
  }, [loadSections]);
  
  // Create stable callbacks for updates
  const handleWebsiteAndSectionsUpdate = useCallback(async () => {
    await loadWebsiteRef.current();
    await loadSectionsRef.current();
  }, []); // Empty deps - uses refs

  const handleWebsiteUpdate = useCallback(async () => {
    await loadWebsiteRef.current();
  }, []); // Empty deps - uses ref

  // Website generation operations
  const {
    generating,
    regenerating,
    regeneratingTheme,
    generateWebsite,
    regenerateWebsite,
    regenerateTheme,
  } = useWebsiteGeneration(token, podcast.id, handleWebsiteAndSectionsUpdate);

  // CSS operations
  const {
    cssEditorLoading,
    saveCSS,
    generateAICSS,
  } = useWebsiteCSS(token, podcast.id, handleWebsiteUpdate);

  // Track if we've loaded sections to prevent loops
  const sectionsLoadedRef = useRef(false);
  const lastWebsiteIdRef = useRef(null);
  const lastPodcastIdRef = useRef(null);
  
  // Reset refs when podcast changes
  useEffect(() => {
    if (lastPodcastIdRef.current !== podcast.id) {
      console.log('[VisualEditor] Podcast ID changed', {
        from: lastPodcastIdRef.current,
        to: podcast.id
      });
      lastPodcastIdRef.current = podcast.id;
      initialLoadDoneRef.current = false;
      sectionsLoadedRef.current = false;
      lastWebsiteIdRef.current = null;
    }
  }, [podcast.id]);
  
  // Initial load (only once when sections are available and website is loaded)
  useEffect(() => {
    const websiteId = website?.id;
    if (availableSections.length > 0 && website && 
        (!sectionsLoadedRef.current || lastWebsiteIdRef.current !== websiteId)) {
      console.log('[VisualEditor] Loading sections', {
        websiteId,
        sectionsCount: availableSections.length,
        wasLoaded: sectionsLoadedRef.current,
        lastWebsiteId: lastWebsiteIdRef.current
      });
      sectionsLoadedRef.current = true;
      lastWebsiteIdRef.current = websiteId;
      loadSectionsRef.current().catch(err => {
        console.error('[VisualEditor] Failed to load sections', err);
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [availableSections.length, website?.id]); // Only depend on website ID, not entire object

  // Handlers
  const handleReorder = async (newSections) => {
    await reorderSections(newSections);
  };

  const handleToggleSection = async (sectionId, enabled) => {
    await toggleSection(sectionId, enabled);
  };

  const handleSaveConfig = async (sectionId, config) => {
    setEditingSection(null);
    await saveSectionConfig(sectionId, config);
  };

  const handleRefineSection = async (sectionId, instruction) => {
    setRefining(true);
    try {
      await refineSectionWithAI(sectionId, instruction);
    } finally {
      setRefining(false);
    }
  };

  const handleGenerateWebsite = async () => {
    await generateWebsite();
    await loadWebsite();
    await loadSections();
  };

  const handleRegenerateWebsite = async () => {
    await regenerateWebsite();
  };

  const handleRegenerateTheme = async () => {
    await regenerateTheme();
  };

  const handleAddSection = async (section) => {
    await addSection(section);
  };

  const handleDeleteSection = async (sectionId) => {
    await deleteSection(sectionId);
  };

  const handleCSSsave = async (css) => {
    await saveCSS(css);
    setShowCSSEditor(false);
  };

  const handleAIGenerateCSS = async (prompt) => {
    await generateAICSS(prompt);
  };

  const handleReset = async () => {
    try {
      await resetWebsite();
      setShowResetDialog(false);
      await loadWebsite();
      await loadSections();
    } catch (err) {
      // Error already handled in hook
    }
  };

  const loading = websiteLoading || sectionsLoading || sectionsDataLoading;

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[600px]">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="sm" onClick={onBack}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Button>
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">
              Website Builder
            </h1>
            <p className="text-sm text-slate-600">
              {podcast.name}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Only show functional buttons */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowCSSEditor(true)}
            disabled={loading || !website}
          >
            <Palette className="mr-2 h-4 w-4" />
            Customize CSS
          </Button>
          
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowResetDialog(true)}
            disabled={loading || !website}
            className="text-red-600 hover:text-red-700 hover:bg-red-50"
          >
            <RotateCcw className="mr-2 h-4 w-4" />
            Reset
          </Button>
          
          {/* Live Site Button - always shows when domain exists */}
          {website?.default_domain && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => window.open(`https://${website.default_domain}`, "_blank")}
            >
              View Live Site
            </Button>
          )}
        </div>
      </div>
      
      {/* Warning banner about preview vs live site */}
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 flex items-start gap-2">
        <div className="text-amber-600 mt-0.5">
          <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
            <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
          </svg>
        </div>
        <div className="flex-1">
          <p className="text-sm font-medium text-amber-800">
            Preview Mode
          </p>
          <p className="text-xs text-amber-700 mt-0.5">
            This is a simplified preview for editing. The live site will look different and include all features like the audio player and full styling.
          </p>
        </div>
      </div>
      
      {/* Theme Description Display */}
      {website && sectionsConfig && sectionsConfig["_theme_metadata"] && (
        <div className="bg-gradient-to-r from-purple-50 to-pink-50 border border-purple-200 rounded-lg p-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2">
                <Sparkles className="h-4 w-4 text-purple-600" />
                <h3 className="text-sm font-semibold text-purple-900">AI Theme Description</h3>
              </div>
              <p className="text-sm text-purple-800">
                {sectionsConfig["_theme_metadata"].description || "No theme description available."}
              </p>
              {sectionsConfig["_theme_metadata"].visual_motifs && sectionsConfig["_theme_metadata"].visual_motifs.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {sectionsConfig["_theme_metadata"].visual_motifs.map((motif, idx) => (
                    <span key={idx} className="text-xs px-2 py-0.5 bg-purple-100 text-purple-700 rounded">
                      {motif}
                    </span>
                  ))}
                </div>
              )}
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleRegenerateTheme}
                disabled={regeneratingTheme || loading}
                className="text-purple-700 border-purple-300 hover:bg-purple-100"
                title="Generate a new AI theme (doesn't change structure)"
              >
                {regeneratingTheme ? (
                  <>
                    <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                    Regenerating...
                  </>
                ) : (
                  <>
                    <Sparkles className="mr-1.5 h-3.5 w-3.5" />
                    New Theme
                  </>
                )}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  // Open section config for _theme_metadata to edit
                  setEditingSection("_theme_metadata");
                }}
                className="text-purple-700 hover:text-purple-900 hover:bg-purple-100"
              >
                Edit
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Main editor area */}
      <div className="grid grid-cols-[320px_1fr] gap-6">
        {/* Left sidebar - Section palette */}
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between mb-2">
              <div>
                <CardTitle className="text-lg">Available Sections</CardTitle>
                <CardDescription className="text-xs">
                  Add sections to build your website
                </CardDescription>
              </div>
              {website && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowCSSEditor(true)}
                  disabled={loading}
                  className="h-8"
                  title="Edit custom CSS styles"
                >
                  <Palette className="h-4 w-4" />
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent>
            <SectionPalette
              availableSections={availableSections}
              onAddSection={handleAddSection}
              existingSectionIds={existingSectionIds}
              loading={false}
            />
          </CardContent>
        </Card>

        {/* Right side - Canvas */}
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle className="text-lg">Your Website</CardTitle>
                  <CardDescription className="text-xs">
                    Drag to reorder • Click settings to configure • Toggle eye to show/hide
                  </CardDescription>
                </div>
                <div className="flex gap-2">
                  {!website && (
                    <Button
                      size="sm"
                      onClick={handleGenerateWebsite}
                      disabled={generating}
                      className="bg-purple-600 hover:bg-purple-700"
                    >
                      {generating ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Generating...
                        </>
                      ) : (
                        <>
                          <Sparkles className="mr-2 h-4 w-4" />
                          Generate Website
                        </>
                      )}
                    </Button>
                  )}
                  {website && (
                    <Button
                      size="sm"
                      onClick={handleRegenerateWebsite}
                      disabled={regenerating || loading}
                      className="bg-purple-600 hover:bg-purple-700"
                      title="Regenerate entire website with AI: updates layout, colors from cover art, and latest episodes. This may overwrite your customizations."
                    >
                      {regenerating ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Regenerating...
                        </>
                      ) : (
                        <>
                          <Sparkles className="mr-2 h-4 w-4" />
                          Regenerate with AI
                        </>
                      )}
                    </Button>
                  )}
                  {!website && (
                    <Button
                      size="sm"
                      onClick={handleGenerateWebsite}
                      disabled={generating}
                      className="bg-purple-600 hover:bg-purple-700"
                    >
                      {generating ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Generating...
                        </>
                      ) : (
                        <>
                          <Sparkles className="mr-2 h-4 w-4" />
                          Generate Website
                        </>
                      )}
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => loadWebsite()}
                    disabled={loading}
                    title="Reload website data from server (useful if you made changes elsewhere)"
                  >
                    {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Refresh"}
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {!website ? (
                <div className="text-center py-12 px-4">
                  <Sparkles className="h-12 w-12 mx-auto text-purple-400 mb-4" />
                  <h3 className="text-lg font-semibold text-slate-900 mb-2">
                    No Website Yet
                  </h3>
                  <p className="text-sm text-slate-600 mb-6 max-w-md mx-auto">
                    Click "Generate Website" to create a beautiful website for {podcast.name}. 
                    AI will automatically extract colors from your cover art, add your latest episodes, 
                    and create a professional layout.
                  </p>
                  <Button
                    size="lg"
                    onClick={handleGenerateWebsite}
                    disabled={generating}
                    className="bg-purple-600 hover:bg-purple-700"
                  >
                    {generating ? (
                      <>
                        <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                        Generating Your Website...
                      </>
                    ) : (
                      <>
                        <Sparkles className="mr-2 h-5 w-5" />
                        Generate Website with AI
                      </>
                    )}
                  </Button>
                </div>
              ) : (
                <SectionCanvas
                  sections={sections}
                  sectionsConfig={sectionsConfig}
                  sectionsEnabled={sectionsEnabled}
                  availableSectionDefs={availableSectionDefs}
                  onReorder={handleReorder}
                  onToggleSection={handleToggleSection}
                  onEditSection={(sectionId) => setEditingSection(sectionId)}
                  onDeleteSection={handleDeleteSection}
                  podcast={{
                    id: podcast.id,
                    title: podcast.name,
                    description: podcast.description,
                    cover_url: website?.cover_url || podcast.cover_url,
                    rss_url: podcast.rss_feed_url,
                  }}
                  episodes={website?.episodes || []}
                />
              )}
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Section config modal */}
      {editingSection && (
        <SectionConfigModal
          open={!!editingSection}
          onClose={() => setEditingSection(null)}
          section={{ id: editingSection }}
          sectionDef={availableSectionDefs[editingSection]}
          config={sectionsConfig[editingSection] || {}}
          onSave={(config) => handleSaveConfig(editingSection, config)}
          onRefine={handleRefineSection}
          refining={refining}
        />
      )}

      {/* CSS Editor Dialog */}
      <CSSEditorDialog
        isOpen={showCSSEditor}
        onClose={() => setShowCSSEditor(false)}
        currentCSS={website?.global_css || ""}
        onSave={handleCSSsave}
        onAIGenerate={handleAIGenerateCSS}
        isLoading={cssEditorLoading}
      />

      {/* Reset Confirmation Dialog */}
      <ResetConfirmDialog
        isOpen={showResetDialog}
        onClose={() => setShowResetDialog(false)}
        onConfirm={handleReset}
        isLoading={loading}
      />
    </div>
  );
}
