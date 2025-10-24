/**
 * Visual Editor - Main drag-and-drop website builder interface
 * Combines section palette, canvas, and configuration
 */

import { useState, useEffect, useCallback, useMemo } from "react";
import { ArrowLeft, Save, Loader2, Eye, Plus, Palette, RotateCcw, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { useToast } from "@/hooks/use-toast";
import { makeApi, isApiError } from "@/lib/apiClient";
import SectionPalette from "./SectionPalette";
import SectionCanvas from "./SectionCanvas";
import SectionConfigModal from "./SectionConfigModal";
import CSSEditorDialog from "@/components/dashboard/CSSEditorDialog";
import ResetConfirmDialog from "@/components/dashboard/ResetConfirmDialog";

export default function VisualEditor({ token, podcast, onBack }) {
  const { toast } = useToast();
  const api = useMemo(() => makeApi(token), [token]);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [refining, setRefining] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  
  // Section library (available sections from API)
  const [availableSections, setAvailableSections] = useState([]);
  const [availableSectionDefs, setAvailableSectionDefs] = useState({});
  
  // Website state
  const [website, setWebsite] = useState(null);
  const [sections, setSections] = useState([]); // Ordered array of {id}
  const [sectionsConfig, setSectionsConfig] = useState({});
  const [sectionsEnabled, setSectionsEnabled] = useState({});
  
  // UI state
  const [editingSection, setEditingSection] = useState(null);
  const [viewMode, setViewMode] = useState("editor"); // "editor" | "preview"
  const [showCSSEditor, setShowCSSEditor] = useState(false);
  const [cssEditorLoading, setCSSEditorLoading] = useState(false);
  const [showResetDialog, setShowResetDialog] = useState(false);

  // Load available sections from API
  const loadAvailableSections = useCallback(async () => {
    try {
      const data = await api.get("/api/website-sections");
      setAvailableSections(data);
      
      // Create lookup map
      const defsMap = {};
      data.forEach((section) => {
        defsMap[section.id] = section;
      });
      setAvailableSectionDefs(defsMap);
    } catch (err) {
      console.error("Failed to load sections", err);
      toast({
        title: "Error",
        description: "Failed to load available sections",
        variant: "destructive",
      });
    }
  }, [api, toast]);

  // Load website and its section configuration
  const loadWebsite = useCallback(async () => {
    setLoading(true);
    try {
      // Load website data
      const websiteData = await api.get(`/api/podcasts/${podcast.id}/website`);
      setWebsite(websiteData);

      // Load section configuration
      const sectionsData = await api.get(`/api/podcasts/${podcast.id}/website/sections`);
      
      const order = sectionsData.sections_order || [];
      const config = sectionsData.sections_config || {};
      const enabled = sectionsData.sections_enabled || {};

      setSections(order.map((id) => ({ id })));
      setSectionsConfig(config);
      setSectionsEnabled(enabled);
    } catch (err) {
      if (err?.status === 404) {
        // No website yet - initialize with defaults
        const defaultSections = availableSections
          .filter((s) => s.default_enabled)
          .map((s) => ({ id: s.id }));
        
        setSections(defaultSections);
        
        const defaultEnabled = {};
        defaultSections.forEach((s) => {
          defaultEnabled[s.id] = true;
        });
        setSectionsEnabled(defaultEnabled);
      } else {
        console.error("Failed to load website", err);
        toast({
          title: "Error",
          description: "Failed to load website configuration",
          variant: "destructive",
        });
      }
    } finally {
      setLoading(false);
    }
  }, [api, podcast.id, availableSections, toast]);

  // Initial load
  useEffect(() => {
    loadAvailableSections();
  }, [loadAvailableSections]);

  useEffect(() => {
    if (availableSections.length > 0) {
      loadWebsite();
    }
  }, [availableSections, loadWebsite]);

  // Save section order
  const handleReorder = async (newSections) => {
    setSections(newSections);
    
    // Optimistic update, save in background
    try {
      await api.patch(`/api/podcasts/${podcast.id}/website/sections/order`, {
        section_ids: newSections.map((s) => s.id),
      });
    } catch (err) {
      console.error("Failed to save order", err);
      toast({
        title: "Error",
        description: "Failed to save section order",
        variant: "destructive",
      });
      // Reload to get server state
      loadWebsite();
    }
  };

  // Toggle section visibility
  const handleToggleSection = async (sectionId, enabled) => {
    console.log(`[VisualEditor] Toggling section ${sectionId} to ${enabled}`);
    
    // Optimistic update
    setSectionsEnabled((prev) => {
      const newState = {
        ...prev,
        [sectionId]: enabled,
      };
      console.log(`[VisualEditor] Updated sectionsEnabled state:`, newState);
      return newState;
    });

    try {
      const response = await api.patch(`/api/podcasts/${podcast.id}/website/sections/${sectionId}/toggle`, {
        enabled,
      });
      console.log(`[VisualEditor] Toggle API response:`, response);
      
      toast({
        title: "Success",
        description: `Section ${enabled ? 'shown' : 'hidden'}`,
      });
    } catch (err) {
      console.error("[VisualEditor] Failed to toggle section", err);
      const errorMsg = err?.response?.data?.detail || err?.message || "Unknown error";
      toast({
        title: "Error",
        description: `Failed to update section visibility: ${errorMsg}`,
        variant: "destructive",
      });
      // Revert
      setSectionsEnabled((prev) => ({
        ...prev,
        [sectionId]: !enabled,
      }));
    }
  };

  // Save section configuration
  const handleSaveConfig = async (sectionId, config) => {
    // Optimistic update
    setSectionsConfig((prev) => ({
      ...prev,
      [sectionId]: config,
    }));
    
    setEditingSection(null);

    try {
      await api.patch(`/api/podcasts/${podcast.id}/website/sections/${sectionId}/config`, {
        config,
      });
      
      toast({
        title: "Saved",
        description: "Section configuration updated",
      });
    } catch (err) {
      console.error("Failed to save config", err);
      toast({
        title: "Error",
        description: "Failed to save section configuration",
        variant: "destructive",
      });
      // Reload to get server state
      loadWebsite();
    }
  };

  // AI refinement for a section
  const handleRefineSection = async (sectionId, instruction) => {
    setRefining(true);
    try {
      const response = await api.post(
        `/api/podcasts/${podcast.id}/website/sections/${sectionId}/refine`,
        { instruction }
      );
      
      // Update with AI-generated config
      setSectionsConfig((prev) => ({
        ...prev,
        [sectionId]: response.config,
      }));
      
      toast({
        title: "Refined",
        description: "AI has improved your section content",
      });
    } catch (err) {
      console.error("Failed to refine section", err);
      
      // Check for 501 (not implemented yet)
      if (err?.status === 501) {
        toast({
          title: "Coming Soon",
          description: "AI section refinement is being implemented",
          variant: "default",
        });
      } else {
        toast({
          title: "Error",
          description: "Failed to refine section with AI",
          variant: "destructive",
        });
      }
    } finally {
      setRefining(false);
    }
  };

  // Generate website for the first time
  const handleGenerateWebsite = async () => {
    setGenerating(true);
    try {
      const websiteData = await api.post(`/api/podcasts/${podcast.id}/website`);
      setWebsite(websiteData);
      
      // Reload to get the full website configuration
      await loadWebsite();
      
      toast({
        title: "Website Generated!",
        description: "Your podcast website has been created with AI",
      });
    } catch (err) {
      console.error("Failed to generate website", err);
      const message = isApiError(err) 
        ? (err.detail || err.message || err.error || "Unable to generate website") 
        : "Unable to generate website";
      toast({
        title: "Error",
        description: message,
        variant: "destructive",
      });
    } finally {
      setGenerating(false);
    }
  };

  // Regenerate existing website with fresh data
  const handleRegenerateWebsite = async () => {
    setRegenerating(true);
    try {
      // POST to same endpoint - backend will update existing website
      const websiteData = await api.post(`/api/podcasts/${podcast.id}/website`);
      setWebsite(websiteData);
      
      // Reload to get the full updated configuration
      await loadWebsite();
      
      toast({
        title: "Website Regenerated!",
        description: "Your website has been refreshed with latest episodes and colors",
      });
    } catch (err) {
      console.error("Failed to regenerate website", err);
      const message = isApiError(err) 
        ? (err.detail || err.message || err.error || "Unable to regenerate website") 
        : "Unable to regenerate website";
      toast({
        title: "Error",
        description: message,
        variant: "destructive",
      });
    } finally {
      setRegenerating(false);
    }
  };

  // Add section from palette
  const handleAddSection = (section) => {
    const newSection = { id: section.id };
    setSections((prev) => [...prev, newSection]);
    setSectionsEnabled((prev) => ({
      ...prev,
      [section.id]: true,
    }));

    // Initialize with defaults
    const defaultConfig = {};
    [...section.required_fields, ...section.optional_fields].forEach((field) => {
      if (field.default !== undefined) {
        defaultConfig[field.name] = field.default;
      }
    });
    
    if (Object.keys(defaultConfig).length > 0) {
      setSectionsConfig((prev) => ({
        ...prev,
        [section.id]: defaultConfig,
      }));
    }

    // Save to server
    handleReorder([...sections, newSection]);
    handleToggleSection(section.id, true);

    toast({
      title: "Section added",
      description: `${section.label} has been added to your website`,
    });
  };

  // Delete section
  const handleDeleteSection = (sectionId) => {
    setSections((prev) => prev.filter((s) => s.id !== sectionId));
    handleReorder(sections.filter((s) => s.id !== sectionId));
    
    toast({
      title: "Section removed",
      description: "Section has been removed from your website",
    });
  };

  const existingSectionIds = sections.map((s) => s.id);

  // CSS Editor handlers
  const handleCSSsave = async (css) => {
    if (!podcast?.id) return;
    setCSSEditorLoading(true);
    try {
      await api.patch(`/api/podcasts/${podcast.id}/website/css`, { css });
      await loadWebsite();
      setShowCSSEditor(false);
      toast({ 
        title: "CSS updated", 
        description: "Your custom styles have been saved." 
      });
    } catch (err) {
      console.error("Failed to update CSS", err);
      toast({ 
        title: "Failed to update CSS", 
        description: isApiError(err) ? (err.detail || err.error || "Unable to save CSS") : "Unable to save CSS",
        variant: "destructive"
      });
    } finally {
      setCSSEditorLoading(false);
    }
  };

  const handleAIGenerateCSS = async (prompt) => {
    if (!podcast?.id || !prompt.trim()) return;
    setCSSEditorLoading(true);
    try {
      const result = await api.patch(`/api/podcasts/${podcast.id}/website/css`, { 
        css: "", 
        ai_prompt: prompt 
      });
      await loadWebsite();
      toast({ 
        title: "CSS generated", 
        description: "AI has created custom styles for your website." 
      });
      // Update the website state with new CSS
      if (website) {
        setWebsite({...website, global_css: result.css});
      }
    } catch (err) {
      console.error("Failed to generate CSS", err);
      toast({ 
        title: "Failed to generate CSS", 
        description: isApiError(err) ? (err.detail || err.error || "Unable to generate CSS") : "Unable to generate CSS",
        variant: "destructive"
      });
    } finally {
      setCSSEditorLoading(false);
    }
  };

  // Reset handler
  const handleReset = async () => {
    if (!podcast?.id) return;
    setLoading(true);
    try {
      const data = await api.post(`/api/podcasts/${podcast.id}/website/reset`, { 
        confirmation_phrase: "here comes the boom" 
      });
      setWebsite(data);
      setShowResetDialog(false);
      // Reload sections after reset
      await loadWebsite();
      toast({ 
        title: "Website reset", 
        description: "Your website has been reset to default settings." 
      });
    } catch (err) {
      console.error("Failed to reset website", err);
      toast({ 
        title: "Failed to reset website", 
        description: isApiError(err) ? (err.detail || err.error || "Unable to reset") : "Unable to reset",
        variant: "destructive"
      });
    } finally {
      setLoading(false);
    }
  };

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
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowCSSEditor(true)}
            disabled={loading}
          >
            <Palette className="mr-2 h-4 w-4" />
            Customize CSS
          </Button>
          
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowResetDialog(true)}
            disabled={loading}
            className="text-red-600 hover:text-red-700 hover:bg-red-50"
          >
            <RotateCcw className="mr-2 h-4 w-4" />
            Reset
          </Button>
          
          <Button
            variant={viewMode === "preview" ? "default" : "outline"}
            size="sm"
            onClick={() => setViewMode(viewMode === "preview" ? "editor" : "preview")}
          >
            <Eye className="mr-2 h-4 w-4" />
            {viewMode === "preview" ? "Edit" : "Preview"}
          </Button>
          
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

      {/* Main editor area */}
      <div className="grid grid-cols-[320px_1fr] gap-6">
        {/* Left sidebar - Section palette */}
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Available Sections</CardTitle>
            <CardDescription className="text-xs">
              Add sections to build your website
            </CardDescription>
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
                      title="Regenerate website with latest episodes and colors"
                    >
                      {regenerating ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                          Regenerating...
                        </>
                      ) : (
                        <>
                          <Sparkles className="mr-2 h-4 w-4" />
                          Regenerate
                        </>
                      )}
                    </Button>
                  )}
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => loadWebsite()}
                    disabled={loading}
                    title="Reload current website data from server"
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
