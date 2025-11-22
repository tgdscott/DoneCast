import { useState, useCallback, useMemo } from 'react';
import { makeApi, isApiError } from '@/lib/apiClient';
import { useToast } from '@/hooks/use-toast';

/**
 * Hook for managing website pages
 * @param {string} token - Authentication token
 * @param {string} podcastId - Podcast ID
 * @returns {Object} Pages state and operations
 */
export function useWebsitePages(token, podcastId) {
  const { toast } = useToast();
  const api = useMemo(() => makeApi(token), [token]);
  
  const [pages, setPages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const loadPages = useCallback(async () => {
    if (!podcastId) return;
    
    setLoading(true);
    setError(null);
    try {
      const data = await api.get(`/api/podcasts/${podcastId}/website/pages`);
      setPages(data || []);
      return data;
    } catch (err) {
      if (err && err.status === 404) {
        setPages([]);
        return [];
      } else {
        console.error("[useWebsitePages] Failed to load pages", err);
        const message = isApiError(err) 
          ? (err.detail || err.message || err.error || "Unable to load pages") 
          : "Unable to load pages";
        setError(message);
        throw err;
      }
    } finally {
      setLoading(false);
    }
  }, [api, podcastId]);

  const createPage = useCallback(async (title, slug, isHome = false) => {
    if (!podcastId) return null;
    
    try {
      const data = await api.post(`/api/podcasts/${podcastId}/website/pages`, {
        title,
        slug,
        is_home: isHome,
      });
      await loadPages();
      toast({
        title: "Page created",
        description: `"${title}" has been added to your website.`,
      });
      return data;
    } catch (err) {
      console.error("Failed to create page", err);
      const message = isApiError(err)
        ? (err.detail || err.error || "Unable to create page")
        : "Unable to create page";
      setError(message);
      toast({
        title: "Failed to create page",
        description: message,
        variant: "destructive"
      });
      throw err;
    }
  }, [api, podcastId, loadPages, toast]);

  const updatePage = useCallback(async (pageId, updates) => {
    if (!podcastId) return null;
    
    try {
      const data = await api.patch(`/api/podcasts/${podcastId}/website/pages/${pageId}`, updates);
      await loadPages();
      toast({
        title: "Page updated",
        description: "Page changes have been saved.",
      });
      return data;
    } catch (err) {
      console.error("Failed to update page", err);
      const message = isApiError(err)
        ? (err.detail || err.error || "Unable to update page")
        : "Unable to update page";
      setError(message);
      toast({
        title: "Failed to update page",
        description: message,
        variant: "destructive"
      });
      throw err;
    }
  }, [api, podcastId, loadPages, toast]);

  const deletePage = useCallback(async (pageId) => {
    if (!podcastId) return;
    
    try {
      await api.delete(`/api/podcasts/${podcastId}/website/pages/${pageId}`);
      await loadPages();
      toast({
        title: "Page deleted",
        description: "Page has been removed from your website.",
      });
    } catch (err) {
      console.error("Failed to delete page", err);
      const message = isApiError(err)
        ? (err.detail || err.error || "Unable to delete page")
        : "Unable to delete page";
      setError(message);
      toast({
        title: "Failed to delete page",
        description: message,
        variant: "destructive"
      });
      throw err;
    }
  }, [api, podcastId, loadPages, toast]);

  // Get navigation items (pages sorted by order, excluding home page)
  const navigationItems = useMemo(() => {
    return pages
      .filter(page => !page.is_home)
      .sort((a, b) => a.order - b.order)
      .map(page => ({
        title: page.title,
        slug: page.slug,
        id: page.id,
      }));
  }, [pages]);

  // Get home page
  const homePage = useMemo(() => {
    return pages.find(page => page.is_home) || null;
  }, [pages]);

  return {
    pages,
    loading,
    error,
    setError,
    loadPages,
    createPage,
    updatePage,
    deletePage,
    navigationItems,
    homePage,
  };
}




