/**
 * Custom hooks for Visual Editor operations
 * Extracts business logic from VisualEditor component
 */

import { useState, useCallback, useMemo, useEffect, useRef } from "react";
import { useToast } from "@/hooks/use-toast";
import { makeApi, isApiError } from "@/lib/apiClient";
import { useWebsiteBuilder, useWebsiteCSS } from "./useWebsiteBuilder";

/**
 * Hook for managing available sections from the API
 * @param {string} token - Authentication token
 * @returns {Object} Available sections and definitions
 */
export function useAvailableSections(token) {
  const { toast } = useToast();
  const api = useMemo(() => makeApi(token), [token]);
  
  const [availableSections, setAvailableSections] = useState([]);
  const [availableSectionDefs, setAvailableSectionDefs] = useState({});
  const [loading, setLoading] = useState(true);

  const loadAvailableSections = useCallback(async () => {
    setLoading(true);
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
    } finally {
      setLoading(false);
    }
  }, [api, toast]);

  useEffect(() => {
    loadAvailableSections();
  }, [loadAvailableSections]);

  return {
    availableSections,
    availableSectionDefs,
    loading,
    reload: loadAvailableSections,
  };
}

/**
 * Hook for managing website sections (order, config, enabled state)
 * @param {string} token - Authentication token
 * @param {string} podcastId - Podcast ID
 * @param {Array} availableSections - Available sections from API
 * @returns {Object} Section state and operations
 */
export function useWebsiteSections(token, podcastId, availableSections = []) {
  const { toast } = useToast();
  const api = useMemo(() => makeApi(token), [token]);
  
  const [sections, setSections] = useState([]); // Ordered array of {id}
  const [sectionsConfig, setSectionsConfig] = useState({});
  const [sectionsEnabled, setSectionsEnabled] = useState({});
  const [loading, setLoading] = useState(true);

  const loadSections = useCallback(async () => {
    if (!podcastId) {
      setLoading(false);
      return;
    }
    
    setLoading(true);
    try {
      const sectionsData = await api.get(`/api/podcasts/${podcastId}/website/sections`);
      
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
        console.error("Failed to load sections", err);
        toast({
          title: "Error",
          description: "Failed to load website configuration",
          variant: "destructive",
        });
      }
    } finally {
      setLoading(false);
    }
  }, [api, podcastId, availableSections, toast]);

  const reorderSections = useCallback(async (newSections) => {
    setSections(newSections);
    
    // Optimistic update, save in background
    try {
      await api.patch(`/api/podcasts/${podcastId}/website/sections/order`, {
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
      loadSections();
    }
  }, [api, podcastId, toast, loadSections]);

  const toggleSection = useCallback(async (sectionId, enabled) => {
    // Optimistic update
    setSectionsEnabled((prev) => ({
      ...prev,
      [sectionId]: enabled,
    }));

    try {
      await api.patch(`/api/podcasts/${podcastId}/website/sections/${sectionId}/toggle`, {
        enabled,
      });
      
      toast({
        title: "Success",
        description: `Section ${enabled ? 'shown' : 'hidden'}`,
      });
    } catch (err) {
      console.error("Failed to toggle section", err);
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
  }, [api, podcastId, toast]);

  const saveSectionConfig = useCallback(async (sectionId, config) => {
    // Optimistic update
    setSectionsConfig((prev) => ({
      ...prev,
      [sectionId]: config,
    }));

    try {
      await api.patch(`/api/podcasts/${podcastId}/website/sections/${sectionId}/config`, {
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
      loadSections();
    }
  }, [api, podcastId, toast, loadSections]);

  const addSection = useCallback(async (section) => {
    const newSection = { id: section.id };
    const newSections = [...sections, newSection];
    
    setSections(newSections);
    setSectionsEnabled((prev) => ({
      ...prev,
      [section.id]: true,
    }));

    // Initialize with defaults
    const defaultConfig = {};
    [...(section.required_fields || []), ...(section.optional_fields || [])].forEach((field) => {
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
    await reorderSections(newSections);
    await toggleSection(section.id, true);

    toast({
      title: "Section added",
      description: `${section.label} has been added to your website`,
    });
  }, [sections, reorderSections, toggleSection, toast]);

  const deleteSection = useCallback(async (sectionId) => {
    const newSections = sections.filter((s) => s.id !== sectionId);
    setSections(newSections);
    await reorderSections(newSections);
    
    toast({
      title: "Section removed",
      description: "Section has been removed from your website",
    });
  }, [sections, reorderSections, toast]);

  const refineSection = useCallback(async (sectionId, instruction) => {
    try {
      const response = await api.post(
        `/api/podcasts/${podcastId}/website/sections/${sectionId}/refine`,
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
      throw err;
    }
  }, [api, podcastId, toast]);

  return {
    sections,
    sectionsConfig,
    sectionsEnabled,
    loading,
    loadSections,
    reorderSections,
    toggleSection,
    saveSectionConfig,
    addSection,
    deleteSection,
    refineSection,
    setSectionsConfig, // For direct updates when needed
  };
}

/**
 * Hook for managing website generation and regeneration
 * @param {string} token - Authentication token
 * @param {string} podcastId - Podcast ID
 * @param {Function} onWebsiteUpdated - Callback when website is updated
 * @returns {Object} Generation state and operations
 */
export function useWebsiteGeneration(token, podcastId, onWebsiteUpdated) {
  const { toast } = useToast();
  const api = useMemo(() => makeApi(token), [token]);
  
  const [generating, setGenerating] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [regeneratingTheme, setRegeneratingTheme] = useState(false);
  
  // Use ref to avoid recreating callbacks when onWebsiteUpdated changes
  const onWebsiteUpdatedRef = useRef(onWebsiteUpdated);
  useEffect(() => {
    onWebsiteUpdatedRef.current = onWebsiteUpdated;
  }, [onWebsiteUpdated]);

  const generateWebsite = useCallback(async () => {
    setGenerating(true);
    try {
      const websiteData = await api.post(`/api/podcasts/${podcastId}/website`);
      
      if (onWebsiteUpdatedRef.current) {
        await onWebsiteUpdatedRef.current();
      }
      
      toast({
        title: "Website Generated!",
        description: "Your podcast website has been created with AI",
      });
      return websiteData;
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
      throw err;
    } finally {
      setGenerating(false);
    }
  }, [api, podcastId, toast]); // Removed onWebsiteUpdated from deps

  const regenerateWebsite = useCallback(async () => {
    setRegenerating(true);
    try {
      const websiteData = await api.post(`/api/podcasts/${podcastId}/website`);
      
      if (onWebsiteUpdatedRef.current) {
        await onWebsiteUpdatedRef.current();
      }
      
      toast({
        title: "Website Regenerated!",
        description: "Your website structure has been refreshed with latest episodes and colors. Theme preserved.",
      });
      return websiteData;
    } catch (err) {
      console.error("Failed to regenerate website", err);
      let message = "Unable to regenerate website";
      if (isApiError(err)) {
        if (typeof err.detail === 'string') {
          message = err.detail;
        } else if (err.detail && typeof err.detail === 'object') {
          message = err.detail.message || err.detail.detail || err.detail.error || message;
        } else if (err.error) {
          message = typeof err.error === 'string' ? err.error : String(err.error);
        } else if (err.message) {
          message = typeof err.message === 'string' ? err.message : String(err.message);
        }
      } else if (err && typeof err === 'object') {
        message = err.message || err.toString() || message;
      }
      toast({
        title: "Error",
        description: message,
        variant: "destructive",
      });
      throw err;
    } finally {
      setRegenerating(false);
    }
  }, [api, podcastId, toast]); // Removed onWebsiteUpdated from deps

  const regenerateTheme = useCallback(async () => {
    setRegeneratingTheme(true);
    try {
      const result = await api.post(`/api/podcasts/${podcastId}/website/generate-ai-theme`);
      
      if (onWebsiteUpdatedRef.current) {
        await onWebsiteUpdatedRef.current();
      }
      
      toast({
        title: "Theme Regenerated!",
        description: result.description || "Your website theme has been updated with a new AI-generated design.",
      });
      return result;
    } catch (err) {
      console.error("Failed to regenerate theme", err);
      let message = "Unable to regenerate theme";
      if (isApiError(err)) {
        if (typeof err.detail === 'string') {
          message = err.detail;
        } else if (err.detail && typeof err.detail === 'object') {
          message = err.detail.message || err.detail.detail || err.detail.error || message;
        } else if (err.error) {
          message = typeof err.error === 'string' ? err.error : String(err.error);
        } else if (err.message) {
          message = typeof err.message === 'string' ? err.message : String(err.message);
        }
      }
      toast({
        title: "Failed to regenerate theme",
        description: message,
        variant: "destructive",
      });
      throw err;
    } finally {
      setRegeneratingTheme(false);
    }
  }, [api, podcastId, toast]); // Removed onWebsiteUpdated from deps

  return {
    generating,
    regenerating,
    regeneratingTheme,
    generateWebsite,
    regenerateWebsite,
    regenerateTheme,
  };
}

