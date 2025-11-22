/**
 * Custom hook for website builder API operations
 * Clean, simple implementation with proper error handling
 */

import { useState, useCallback, useMemo } from "react";
import { useToast } from "@/hooks/use-toast";
import { makeApi, isApiError } from "@/lib/apiClient";

/**
 * Extract error message from API error
 */
function extractErrorMessage(err) {
  if (!err) return "An unknown error occurred";
  
  if (isApiError(err)) {
    if (typeof err.detail === 'string') return err.detail;
    if (err.detail && typeof err.detail === 'object') {
      return err.detail.message || err.detail.detail || err.detail.error || "An error occurred";
    }
    if (typeof err.error === 'string') return err.error;
    if (err.error && typeof err.error === 'object') {
      return err.error.message || String(err.error);
    }
    if (typeof err.message === 'string') return err.message;
  }
  
  if (err && typeof err === 'object') {
    return err.message || String(err);
  }
  
  return String(err);
}

/**
 * Hook for managing website data and operations
 */
export function useWebsiteBuilder(token, podcastId) {
  const { toast } = useToast();
  const api = useMemo(() => makeApi(token), [token]);
  
  const [website, setWebsite] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const loadWebsite = useCallback(async () => {
    if (!podcastId) {
      setWebsite(null);
      setError(null);
      return null;
    }
    
    setLoading(true);
    setError(null);
    try {
      const data = await api.get(`/api/podcasts/${podcastId}/website`);
      setWebsite(data);
      return data;
    } catch (err) {
      if (err && err.status === 404) {
        setWebsite(null);
        setError(null);
        return null;
      }
      const message = extractErrorMessage(err);
      setError(message);
      throw err;
    } finally {
      setLoading(false);
    }
  }, [api, podcastId]);

  const generateWebsite = useCallback(async () => {
    if (!podcastId) return null;
    
    setError(null);
    try {
      const data = await api.post(`/api/podcasts/${podcastId}/website`);
      setWebsite(data);
      toast({ 
        title: "Website generated", 
        description: "Your website has been created successfully." 
      });
      return data;
    } catch (err) {
      const message = extractErrorMessage(err);
      setError(message);
      toast({
        title: "Failed to generate website",
        description: message,
        variant: "destructive"
      });
      throw err;
    }
  }, [api, podcastId, toast]);

  const resetWebsite = useCallback(async () => {
    if (!podcastId) return null;
    
    setError(null);
    try {
      const data = await api.post(`/api/podcasts/${podcastId}/website/reset`, {
        confirmation_phrase: "here comes the boom"
      });
      setWebsite(data);
      toast({
        title: "Website reset",
        description: "Your website has been reset to default settings."
      });
      return data;
    } catch (err) {
      const message = extractErrorMessage(err);
      setError(message);
      toast({
        title: "Failed to reset website",
        description: message,
        variant: "destructive"
      });
      throw err;
    }
  }, [api, podcastId, toast]);

  return {
    website,
    loading,
    error,
    setError,
    loadWebsite,
    generateWebsite,
    resetWebsite,
  };
}

/**
 * Hook for managing website publishing operations
 */
export function useWebsitePublishing(token, podcastId, onWebsiteUpdated) {
  const { toast } = useToast();
  const api = useMemo(() => makeApi(token), [token]);
  
  const [publishing, setPublishing] = useState(false);
  const [publishStatus, setPublishStatus] = useState(null);

  const publish = useCallback(async (isPublished) => {
    if (!podcastId) return;
    
    setPublishing(true);
    try {
      if (isPublished) {
        // Unpublish
        await api.post(`/api/podcasts/${podcastId}/website/unpublish`);
        toast({
          title: "Website unpublished",
          description: "Your website is now in draft mode. Click 'Publish Website' to republish it."
        });
      } else {
        // Publish
        const result = await api.post(`/api/podcasts/${podcastId}/website/publish`, {
          auto_provision_domain: true
        });
        
        setPublishStatus(result);
        
        if (result.ssl_status === 'provisioning') {
          toast({
            title: "🎉 Publishing website...",
            description: `Your website will be live at ${result.domain} in about 10-15 minutes while we provision your SSL certificate.`,
            duration: 10000
          });
        } else if (result.ssl_status === 'active') {
          toast({
            title: "🚀 Website is live!",
            description: `Your website is now accessible at ${result.domain}`
          });
        } else {
          toast({
            title: "✅ Website published",
            description: `Your website is now live at ${result.domain || 'your subdomain'}`
          });
        }
      }
      
      // Always refresh website data after publish/unpublish to get updated status
      if (onWebsiteUpdated) {
        await onWebsiteUpdated();
      }
    } catch (err) {
      const message = extractErrorMessage(err);
      toast({
        title: isPublished ? "Failed to unpublish" : "Failed to publish",
        description: message,
        variant: "destructive"
      });
      throw err;
    } finally {
      setPublishing(false);
    }
  }, [api, podcastId, toast, onWebsiteUpdated]);

  return {
    publishing,
    publishStatus,
    publish,
  };
}

/**
 * Hook for managing custom domain operations
 */
export function useWebsiteDomain(token, podcastId, onWebsiteUpdated, customDomain = null) {
  const { toast } = useToast();
  const api = useMemo(() => makeApi(token), [token]);
  
  const [savingDomain, setSavingDomain] = useState(false);
  const [domainDraft, setDomainDraft] = useState(customDomain || "");

  const saveDomain = useCallback(async (domain) => {
    if (!podcastId) return;
    
    setSavingDomain(true);
    try {
      const payload = { custom_domain: domain?.trim() ? domain.trim() : null };
      const data = await api.patch(`/api/podcasts/${podcastId}/website/domain`, payload);
      
      if (onWebsiteUpdated) {
        await onWebsiteUpdated();
      }
      
      toast({
        title: "Domain updated",
        description: data.custom_domain 
          ? `Live at ${data.custom_domain}` 
          : "Using the default domain."
      });
      return data;
    } catch (err) {
      const message = extractErrorMessage(err);
      toast({
        title: "Error",
        description: message,
        variant: "destructive"
      });
      throw err;
    } finally {
      setSavingDomain(false);
    }
  }, [api, podcastId, toast, onWebsiteUpdated]);

  return {
    domainDraft,
    setDomainDraft,
    savingDomain,
    saveDomain,
  };
}

/**
 * Hook for managing AI chat operations
 */
export function useWebsiteChat(token, podcastId, onWebsiteUpdated) {
  const { toast } = useToast();
  const api = useMemo(() => makeApi(token), [token]);
  
  const [chatting, setChatting] = useState(false);
  const [chatMessage, setChatMessage] = useState("");

  const sendChatMessage = useCallback(async (message) => {
    if (!podcastId || !message?.trim()) return null;
    
    setChatting(true);
    try {
      const data = await api.post(`/api/podcasts/${podcastId}/website/chat`, {
        message: message.trim()
      });
      
      if (onWebsiteUpdated) {
        await onWebsiteUpdated();
      }
      
      setChatMessage("");
      toast({
        title: "Update applied",
        description: "The AI builder adjusted your layout."
      });
      return data;
    } catch (err) {
      const message = extractErrorMessage(err);
      toast({
        title: "Error",
        description: message,
        variant: "destructive"
      });
      throw err;
    } finally {
      setChatting(false);
    }
  }, [api, podcastId, toast, onWebsiteUpdated]);

  return {
    chatting,
    chatMessage,
    setChatMessage,
    sendChatMessage,
  };
}

/**
 * Hook for managing CSS operations
 */
export function useWebsiteCSS(token, podcastId, onWebsiteUpdated) {
  const { toast } = useToast();
  const api = useMemo(() => makeApi(token), [token]);
  
  const [cssEditorLoading, setCSSEditorLoading] = useState(false);

  const saveCSS = useCallback(async (css) => {
    if (!podcastId) return;
    
    setCSSEditorLoading(true);
    try {
      await api.patch(`/api/podcasts/${podcastId}/website/css`, { css });
      
      if (onWebsiteUpdated) {
        await onWebsiteUpdated();
      }
      
      toast({
        title: "CSS updated",
        description: "Your custom styles have been saved."
      });
    } catch (err) {
      const message = extractErrorMessage(err);
      toast({
        title: "Failed to update CSS",
        description: message,
        variant: "destructive"
      });
      throw err;
    } finally {
      setCSSEditorLoading(false);
    }
  }, [api, podcastId, toast, onWebsiteUpdated]);

  const generateAICSS = useCallback(async (prompt) => {
    if (!podcastId || !prompt?.trim()) return;
    
    setCSSEditorLoading(true);
    try {
      const result = await api.patch(`/api/podcasts/${podcastId}/website/css`, {
        css: "",
        ai_prompt: prompt
      });
      
      if (onWebsiteUpdated) {
        await onWebsiteUpdated();
      }
      
      toast({
        title: "CSS generated",
        description: "AI has created custom styles for your website."
      });
      return result;
    } catch (err) {
      const message = extractErrorMessage(err);
      toast({
        title: "Failed to generate CSS",
        description: message,
        variant: "destructive"
      });
      throw err;
    } finally {
      setCSSEditorLoading(false);
    }
  }, [api, podcastId, toast, onWebsiteUpdated]);

  return {
    cssEditorLoading,
    saveCSS,
    generateAICSS,
  };
}

/**
 * Hook for managing AI theme generation
 */
export function useWebsiteAITheme(token, podcastId, onWebsiteUpdated) {
  const { toast } = useToast();
  const api = useMemo(() => makeApi(token), [token]);
  
  const [generatingTheme, setGeneratingTheme] = useState(false);

  const generateAITheme = useCallback(async () => {
    if (!podcastId) return;
    
    setGeneratingTheme(true);
    try {
      const result = await api.post(`/api/podcasts/${podcastId}/website/generate-ai-theme`);
      
      if (onWebsiteUpdated) {
        await onWebsiteUpdated();
      }
      
      toast({
        title: "AI Theme Generated!",
        description: result.description || "Your website now has a custom themed design."
      });
      return result;
    } catch (err) {
      const message = extractErrorMessage(err);
      toast({
        title: "Failed to generate theme",
        description: message,
        variant: "destructive"
      });
      throw err;
    } finally {
      setGeneratingTheme(false);
    }
  }, [api, podcastId, toast, onWebsiteUpdated]);

  return {
    generatingTheme,
    generateAITheme,
  };
}
