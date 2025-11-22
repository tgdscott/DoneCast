/**
 * Visual Editor - Main drag-and-drop website builder interface
 * Clean, simple implementation
 */

import { useState, useEffect, useCallback, useMemo } from "react";
import { ArrowLeft, Loader2, Palette, RotateCcw, Sparkles, Eye, ExternalLink, CheckCircle2, Settings, ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import SectionPalette from "./SectionPalette";
import SectionCanvas from "./SectionCanvas";
import SectionConfigModal from "./SectionConfigModal";
import PageManager from "./PageManager";
import CSSEditorDialog from "@/components/dashboard/CSSEditorDialog";
import ResetConfirmDialog from "@/components/dashboard/ResetConfirmDialog";
import LocalWebsitePreview from "./LocalWebsitePreview";
import { useAvailableSections, useWebsiteSections, useWebsiteGeneration } from "@/hooks/useVisualEditor";
import { useWebsiteBuilder, useWebsiteCSS, useWebsitePublishing, useWebsiteAITheme } from "@/hooks/useWebsiteBuilder";

export default function VisualEditor({ token, podcast, onBack }) {
  // Check if podcast has required info for website generation
  const podcastIsReady = useMemo(() => {
    if (!podcast) return false;
    const hasName = podcast.name && podcast.name.trim().length > 0;
    const hasDescription = podcast.description && podcast.description.trim().length > 0;
    const hasCover = !!(podcast.cover_url || podcast.cover_path || podcast.remote_cover_url);
    return hasName && hasDescription && hasCover;
  }, [podcast]);
  
  // UI state
  const [editingSection, setEditingSection] = useState(null);
  const [showCSSEditor, setShowCSSEditor] = useState(false);
  const [showResetDialog, setShowResetDialog] = useState(false);
  const [autoGenerating, setAutoGenerating] = useState(false);
  const [showLocalPreview, setShowLocalPreview] = useState(false);
  const [previewEpisodes, setPreviewEpisodes] = useState([]);
  const [loadingEpisodes, setLoadingEpisodes] = useState(false);
  const [showCustomizeOptions, setShowCustomizeOptions] = useState(false);

  // Load available sections
  const { availableSections, availableSectionDefs, loading: sectionsLoading } = useAvailableSections(token);

  // Load website data
  const {
    website,
    loading: websiteLoading,
    loadWebsite,
    resetWebsite,
  } = useWebsiteBuilder(token, podcast?.id);

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
  } = useWebsiteSections(token, podcast?.id, availableSections);

  // Website generation operations
  const {
    generating,
    regenerating,
    regeneratingTheme,
    generateWebsite,
    regenerateWebsite,
    regenerateTheme,
  } = useWebsiteGeneration(token, podcast?.id, async () => {
    await loadWebsite();
    await loadSections();
  });

  // CSS operations
  const {
    cssEditorLoading,
    saveCSS,
    generateAICSS,
  } = useWebsiteCSS(token, podcast?.id, async () => {
    await loadWebsite();
  });

  // Publishing operations
  const handleWebsiteUpdate = useCallback(async () => {
    await loadWebsite();
    await loadSections();
  }, [loadWebsite, loadSections]);

  const {
    publishing,
    publish,
  } = useWebsitePublishing(token, podcast?.id, handleWebsiteUpdate);

  // AI Theme generation
  const {
    generatingTheme,
    generateAITheme,
  } = useWebsiteAITheme(token, podcast?.id, handleWebsiteUpdate);

  // Auto-generate website if podcast is ready and no website exists
  useEffect(() => {
    if (!podcast?.id || !podcastIsReady) return;
    if (websiteLoading || autoGenerating || website) return; // Don't generate if website already exists
    
    let cancelled = false;
    
    const checkAndGenerate = async () => {
      if (cancelled) return;
      
      try {
        const loadedWebsite = await loadWebsite();
        if (cancelled) return;
        
        if (!loadedWebsite) {
          setAutoGenerating(true);
          await generateWebsite();
          if (!cancelled) {
            await loadWebsite();
          }
        }
      } catch (err) {
        if (cancelled) return;
        
        // If 404, that means no website exists - try to auto-generate
        if (err?.status === 404) {
          setAutoGenerating(true);
          try {
            await generateWebsite();
            if (!cancelled) {
              await loadWebsite();
            }
          } catch (genErr) {
            console.error('Failed to auto-generate website', genErr);
          } finally {
            if (!cancelled) {
              setAutoGenerating(false);
            }
          }
        }
      } finally {
        if (!cancelled) {
          setAutoGenerating(false);
        }
      }
    };
    
    checkAndGenerate();
    
    return () => {
      cancelled = true;
    };
  }, [podcast?.id, podcastIsReady]); // Only run when podcast changes

  // Load sections when website is available
  useEffect(() => {
    if (website?.id && availableSections.length > 0) {
      loadSections().catch(err => {
        console.error('Failed to load sections', err);
      });
    }
  }, [website?.id, availableSections.length]);

  // Handlers
  const handleReorder = useCallback(async (newSections) => {
    await reorderSections(newSections);
  }, [reorderSections]);

  const handleToggleSection = useCallback(async (sectionId, enabled) => {
    await toggleSection(sectionId, enabled);
  }, [toggleSection]);

  const handleSaveConfig = useCallback(async (sectionId, config) => {
    setEditingSection(null);
    await saveSectionConfig(sectionId, config);
  }, [saveSectionConfig]);

  const handleGenerateWebsite = useCallback(async () => {
    await generateWebsite();
    await loadWebsite();
    await loadSections();
  }, [generateWebsite, loadWebsite, loadSections]);

  const handleRegenerateWebsite = useCallback(async () => {
    try {
      await regenerateWebsite();
      await loadWebsite();
      await loadSections();
    } catch (err) {
      console.error('Failed to regenerate website', err);
    }
  }, [regenerateWebsite, loadWebsite, loadSections]);

  const handleRegenerateTheme = useCallback(async () => {
    await regenerateTheme();
  }, [regenerateTheme]);

  const handleAddSection = useCallback(async (section) => {
    await addSection(section);
  }, [addSection]);

  const handleDeleteSection = useCallback(async (sectionId) => {
    await deleteSection(sectionId);
  }, [deleteSection]);

  const handleCSSsave = useCallback(async (css) => {
    await saveCSS(css);
    setShowCSSEditor(false);
  }, [saveCSS]);

  const handleAIGenerateCSS = useCallback(async (prompt) => {
    await generateAICSS(prompt);
  }, [generateAICSS]);

  const handleReset = useCallback(async () => {
    try {
      await resetWebsite();
      setShowResetDialog(false);
      await loadWebsite();
      await loadSections();
    } catch (err) {
      // Error already handled in hook
    }
  }, [resetWebsite, loadWebsite, loadSections]);

  const loading = websiteLoading || sectionsLoading || sectionsDataLoading || autoGenerating;

  // Create array of existing section IDs for SectionPalette
  const existingSectionIds = useMemo(() => {
    return sections.map(s => s.id);
  }, [sections]);

  // Show gating message if podcast is not ready
  if (!podcastIsReady) {
    const missingItems = [];
    if (!podcast.name || !podcast.name.trim()) missingItems.push('podcast name');
    if (!podcast.description || !podcast.description.trim()) missingItems.push('description');
    if (!podcast.cover_url && !podcast.cover_path && !podcast.remote_cover_url) missingItems.push('cover image');
    
    return (
      <div className="space-y-6">
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
                {podcast.name || 'Untitled Podcast'}
              </p>
            </div>
          </div>
        </div>
        
        <Card className="border-2 border-amber-200 bg-amber-50">
          <CardContent className="pt-6">
            <div className="text-center py-8">
              <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-amber-100 mb-4">
                <svg className="w-8 h-8 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <h3 className="text-xl font-semibold text-slate-900 mb-2">
                Complete Your Podcast Information
              </h3>
              <p className="text-slate-600 mb-4 max-w-md mx-auto">
                To generate a website, your podcast needs:
              </p>
              <ul className="text-left inline-block text-slate-700 mb-6 space-y-2">
                <li className={podcast.name && podcast.name.trim() ? 'text-green-600' : 'text-red-600'}>
                  {podcast.name && podcast.name.trim() ? '✓' : '✗'} Podcast name {podcast.name && podcast.name.trim() ? '(complete)' : '(missing)'}
                </li>
                <li className={podcast.description && podcast.description.trim() ? 'text-green-600' : 'text-red-600'}>
                  {podcast.description && podcast.description.trim() ? '✓' : '✗'} Description {podcast.description && podcast.description.trim() ? '(complete)' : '(missing)'}
                </li>
                <li className={podcast.cover_url || podcast.cover_path || podcast.remote_cover_url ? 'text-green-600' : 'text-red-600'}>
                  {podcast.cover_url || podcast.cover_path || podcast.remote_cover_url ? '✓' : '✗'} Cover image {podcast.cover_url || podcast.cover_path || podcast.remote_cover_url ? '(complete)' : '(missing)'}
                </li>
              </ul>
              <p className="text-sm text-slate-500">
                Please add the missing information in your podcast settings, then return here to generate your website.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (loading || autoGenerating) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[600px] space-y-4">
        <Loader2 className="h-8 w-8 animate-spin text-slate-400" />
        {autoGenerating && (
          <p className="text-sm text-slate-600">Generating your website...</p>
        )}
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

        {/* Simplified header - only show customize button */}
        {website && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowCustomizeOptions(!showCustomizeOptions)}
          >
            <Settings className="mr-2 h-4 w-4" />
            {showCustomizeOptions ? 'Hide Options' : 'Customize'}
          </Button>
        )}
      </div>
      
      {/* PRIMARY ACTION: Publish/Update Website */}
      {website && (
        <Card className={`border-2 ${website.status === 'published' ? 'bg-green-50 border-green-300' : 'bg-gradient-to-r from-purple-50 to-blue-50 border-purple-300'}`}>
          <CardContent className="pt-6 pb-6">
            <div className="flex items-center justify-between gap-6">
              <div className="flex-1">
                {website.status === 'published' ? (
                  <>
                    <div className="flex items-center gap-3 mb-2">
                      <CheckCircle2 className="h-6 w-6 text-green-600" />
                      <h3 className="text-xl font-semibold text-green-900">
                        Your Website is Live! 🎉
                      </h3>
                    </div>
                    <p className="text-sm text-green-800 mb-3">
                      Your website is live and accessible to visitors. Make changes below, preview them, then click "Update Website" to publish your changes.
                    </p>
                    {website.default_domain && (
                      <a 
                        href={`https://${website.default_domain}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-2 text-sm font-medium text-green-700 hover:text-green-800 underline"
                      >
                        <ExternalLink className="h-4 w-4" />
                        View live site: {website.default_domain}
                      </a>
                    )}
                  </>
                ) : (
                  <>
                    <h3 className="text-xl font-semibold text-slate-900 mb-2">
                      Ready to Publish Your Website?
                    </h3>
                    <p className="text-sm text-slate-700 mb-4">
                      Your website is ready to go live! Preview it first to make sure everything looks good, then click "Publish Website" to make it public.
                    </p>
                  </>
                )}
              </div>
              <div className="flex flex-col gap-3">
                {/* Preview button - always available */}
                {sections && sections.length > 0 && (
                  <Button
                    size="lg"
                    variant="outline"
                    onClick={async () => {
                      setLoadingEpisodes(true);
                      try {
                        const apiBase = import.meta.env.VITE_API_BASE || 
                                       (window.location.hostname === 'localhost' ? 'http://127.0.0.1:8000' : '');
                        
                        let episodes = [];
                        try {
                          const previewResponse = await fetch(`${apiBase}/api/sites/${website.subdomain}/preview`, {
                            headers: { 'Authorization': `Bearer ${token}` },
                          });
                          if (previewResponse.ok) {
                            const previewData = await previewResponse.json();
                            episodes = previewData.episodes || [];
                          }
                        } catch (previewErr) {
                          console.warn('[LocalPreview] Preview endpoint failed:', previewErr);
                        }
                        
                        if (episodes.length === 0) {
                          const episodesResponse = await fetch(`${apiBase}/api/episodes/?limit=20000`, {
                            headers: { 'Authorization': `Bearer ${token}` },
                          });
                          if (episodesResponse.ok) {
                            const episodesData = await episodesResponse.json();
                            const allEpisodes = episodesData.items || episodesData || [];
                            episodes = allEpisodes
                              .filter(ep => String(ep.podcast_id || ep.podcast?.id) === String(podcast.id))
                              .map(ep => ({
                                id: String(ep.id),
                                title: ep.title || 'Untitled Episode',
                                description: ep.description || ep.show_notes || '',
                                audio_url: ep.final_audio_url || ep.audio_url || null,
                                cover_url: ep.cover_url || null,
                                publish_date: ep.publish_at || ep.publish_date || null,
                                duration_seconds: ep.duration_ms ? Math.floor(ep.duration_ms / 1000) : ep.duration_seconds || null,
                              }));
                          }
                        }
                        
                        setPreviewEpisodes(episodes);
                      } catch (err) {
                        console.error('[LocalPreview] Failed to fetch episodes:', err);
                        setPreviewEpisodes([]);
                      } finally {
                        setLoadingEpisodes(false);
                        setShowLocalPreview(true);
                      }
                    }}
                    disabled={loadingEpisodes}
                    className="h-12 px-6 text-base border-purple-300 text-purple-700 hover:bg-purple-50"
                  >
                    <Eye className="mr-2 h-5 w-5" />
                    {loadingEpisodes ? 'Loading...' : 'Preview Changes'}
                  </Button>
                )}
                
                {/* Publish/Update button */}
                <Button
                  size="lg"
                  onClick={async () => {
                    // Always publish/update - never unpublish from primary button
                    await publish(false);
                  }}
                  disabled={publishing || loading}
                  className="bg-purple-600 hover:bg-purple-700 text-white h-12 px-8 text-base font-semibold shadow-lg"
                >
                  {publishing ? (
                    <>
                      <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                      {website.status === 'published' ? 'Updating...' : 'Publishing...'}
                    </>
                  ) : website.status === 'published' ? (
                    <>
                      <ExternalLink className="mr-2 h-5 w-5" />
                      Update Website
                    </>
                  ) : (
                    <>
                      <ExternalLink className="mr-2 h-5 w-5" />
                      Publish Website
                    </>
                  )}
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* COLLAPSIBLE CUSTOMIZE SECTION */}
      {website && (
        <Card className="border border-slate-200">
          <CardHeader 
            className="cursor-pointer hover:bg-slate-50 transition-colors"
            onClick={() => setShowCustomizeOptions(!showCustomizeOptions)}
          >
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-base">Advanced Options</CardTitle>
                <CardDescription className="text-xs mt-1">
                  Change theme, edit CSS, regenerate website, or unpublish
                </CardDescription>
              </div>
              {showCustomizeOptions ? (
                <ChevronUp className="h-5 w-5 text-slate-400" />
              ) : (
                <ChevronDown className="h-5 w-5 text-slate-400" />
              )}
            </div>
          </CardHeader>
          {showCustomizeOptions && (
            <CardContent className="pt-0">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {/* Generate New Theme */}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleRegenerateTheme}
                  disabled={regeneratingTheme || loading}
                  className="h-auto py-3 flex flex-col items-center gap-2"
                >
                  <Sparkles className="h-5 w-5" />
                  <span className="text-xs">New Theme</span>
                </Button>

                {/* Customize CSS */}
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowCSSEditor(true)}
                  disabled={loading}
                  className="h-auto py-3 flex flex-col items-center gap-2"
                >
                  <Palette className="h-5 w-5" />
                  <span className="text-xs">Edit CSS</span>
                </Button>

                {/* Regenerate Website */}
                {website && (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleRegenerateWebsite}
                    disabled={regenerating || loading}
                    className="h-auto py-3 flex flex-col items-center gap-2"
                  >
                    <Sparkles className="h-5 w-5" />
                    <span className="text-xs">Regenerate</span>
                  </Button>
                )}

                {/* Unpublish - only show if published */}
                {website.status === 'published' ? (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={async () => {
                      if (confirm('Are you sure you want to unpublish your website? It will no longer be accessible to visitors, but you can republish it anytime.')) {
                        await publish(true);
                      }
                    }}
                    disabled={publishing || loading}
                    className="h-auto py-3 flex flex-col items-center gap-2 text-amber-600 border-amber-300 hover:bg-amber-50"
                  >
                    <RotateCcw className="h-5 w-5" />
                    <span className="text-xs">Unpublish</span>
                  </Button>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowResetDialog(true)}
                    disabled={loading}
                    className="h-auto py-3 flex flex-col items-center gap-2 text-red-600 border-red-300 hover:bg-red-50"
                  >
                    <RotateCcw className="h-5 w-5" />
                    <span className="text-xs">Reset</span>
                  </Button>
                )}
              </div>
            </CardContent>
          )}
        </Card>
      )}

      {/* Theme Description Display - Only show if customize section is open */}
      {website && showCustomizeOptions && sectionsConfig && sectionsConfig["_theme_metadata"] && (
        <Card className="border border-purple-200 bg-gradient-to-r from-purple-50 to-pink-50">
          <CardContent className="pt-4">
            <div className="flex items-start gap-3">
              <Sparkles className="h-5 w-5 text-purple-600 mt-0.5" />
              <div className="flex-1">
                <h4 className="text-sm font-semibold text-purple-900 mb-1">Current Theme</h4>
                <p className="text-sm text-purple-800 mb-2">
                  {sectionsConfig["_theme_metadata"].description || "No theme description available."}
                </p>
                {sectionsConfig["_theme_metadata"].visual_motifs && sectionsConfig["_theme_metadata"].visual_motifs.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {sectionsConfig["_theme_metadata"].visual_motifs.map((motif, idx) => (
                      <span key={idx} className="text-xs px-2 py-0.5 bg-purple-100 text-purple-700 rounded">
                        {motif}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Main editor area */}
      <div className="grid grid-cols-[320px_1fr] gap-6">
        {/* Left sidebar - Page manager and Section palette */}
        <div className="space-y-4">
          {/* Page Manager */}
          {website && (
            <PageManager token={token} podcastId={podcast.id} website={website} />
          )}
          
          {/* Section Palette */}
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
        </div>

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
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => loadWebsite()}
                    disabled={loading}
                    title="Reload website data from server"
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

      {/* Local Preview Modal */}
      {showLocalPreview && website && (
        <LocalWebsitePreview
          website={website}
          sections={sections}
          sectionsConfig={sectionsConfig}
          sectionsEnabled={sectionsEnabled}
          podcast={podcast}
          episodes={previewEpisodes}
          token={token}
          onClose={() => setShowLocalPreview(false)}
        />
      )}
    </div>
  );
}
