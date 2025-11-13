/**
 * Custom hook for website builder API operations
 * Extracts all API calls and state management from WebsiteBuilder component
 */

import { useState, useCallback, useMemo, useEffect, useRef } from "react";
import { useToast } from "@/hooks/use-toast";
import { makeApi, isApiError } from "@/lib/apiClient";

/**
 * Hook for managing website data and operations
 * @param {string} token - Authentication token
 * @param {string} podcastId - Selected podcast ID
 * @returns {Object} Website state and operations
 */
export function useWebsiteBuilder(token, podcastId) {
  const { toast } = useToast();
  const api = useMemo(() => makeApi(token), [token]);
  
  const [website, setWebsite] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const loadingRef = useRef(false); // Prevent concurrent loads
  
  // Debug: Track hook calls
  const hookCallCountRef = useRef(0);
  hookCallCountRef.current += 1;
  if (hookCallCountRef.current <= 5 || hookCallCountRef.current % 10 === 0) {
    console.log(`[useWebsiteBuilder] Hook call #${hookCallCountRef.current}`, {
      podcastId,
      hasWebsite: !!website,
      websiteId: website?.id,
      loading,
      timestamp: Date.now()
    });
  }

  const loadWebsite = useCallback(async () => {
    if (!podcastId) {
      setWebsite(null);
      return;
    }
    
    // Prevent concurrent loads
    if (loadingRef.current) {
      console.log('[useWebsiteBuilder] Skipping load - already loading', { podcastId });
      return;
    }
    
    console.log('[useWebsiteBuilder] Starting loadWebsite', { podcastId, timestamp: Date.now() });
    loadingRef.current = true;
    setLoading(true);
    setError(null);
    try {
      const data = await api.get(`/api/podcasts/${podcastId}/website`);
      console.log('[useWebsiteBuilder] Loaded website', { podcastId, websiteId: data?.id });
      setWebsite(data);
      return data;
    } catch (err) {
      if (err && err.status === 404) {
        console.log('[useWebsiteBuilder] Website not found (404)', { podcastId });
        setWebsite(null);
        return null;
      } else {
        console.error("[useWebsiteBuilder] Failed to load website", err);
        const message = isApiError(err) 
          ? (err.detail || err.message || err.error || "Unable to load site") 
          : "Unable to load site";
        setError(message);
        throw err;
      }
    } finally {
      setLoading(false);
      loadingRef.current = false;
      console.log('[useWebsiteBuilder] Finished loadWebsite', { podcastId, timestamp: Date.now() });
    }
  }, [api, podcastId]);

  const generateWebsite = useCallback(async () => {
    if (!podcastId) return null;
    
    setError(null);
    try {
      const data = await api.post(`/api/podcasts/${podcastId}/website`);
      setWebsite(data);
      toast({ 
        title: "Website drafted", 
        description: "The AI builder prepared a fresh layout." 
      });
      return data;
    } catch (err) {
      console.error("Failed to generate website", err);
      const message = isApiError(err) 
        ? (err.detail || err.message || err.error || "Unable to generate site") 
        : "Unable to generate site";
      setError(message);
      throw err;
    }
  }, [api, podcastId, toast]);

  const resetWebsite = useCallback(async () => {
    if (!podcastId) return null;
    
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
      console.error("Failed to reset website", err);
      const message = isApiError(err)
        ? (err.detail || err.error || "Unable to reset")
        : "Unable to reset";
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
 * @param {string} token - Authentication token
 * @param {string} podcastId - Selected podcast ID
 * @param {Function} onWebsiteUpdated - Callback when website is updated
 * @returns {Object} Publishing state and operations
 */
export function useWebsitePublishing(token, podcastId, onWebsiteUpdated) {
  const { toast } = useToast();
  const api = useMemo(() => makeApi(token), [token]);
  
  const [publishing, setPublishing] = useState(false);
  const [publishStatus, setPublishStatus] = useState(null);
  
  // Use ref to avoid recreating callbacks when onWebsiteUpdated changes
  const onWebsiteUpdatedRef = useRef(onWebsiteUpdated);
  useEffect(() => {
    onWebsiteUpdatedRef.current = onWebsiteUpdated;
  }, [onWebsiteUpdated]);

  const publish = useCallback(async (isPublished) => {
    if (!podcastId) return;
    
    setPublishing(true);
    try {
      if (isPublished) {
        // Unpublish
        await api.post(`/api/podcasts/${podcastId}/website/unpublish`);
        toast({
          title: "Website unpublished",
          description: "Your website is now in draft mode."
        });
      } else {
        // Publish with automatic domain provisioning
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
          
          // Start polling for SSL readiness
          pollDomainStatus();
        } else if (result.ssl_status === 'active') {
          toast({
            title: "🚀 Website is live!",
            description: `Your website is now accessible at ${result.domain}`
          });
        }
      }
      
      // Reload website to get updated status
      if (onWebsiteUpdatedRef.current) {
        await onWebsiteUpdatedRef.current();
      }
    } catch (err) {
      console.error("Failed to publish/unpublish website", err);
      const message = isApiError(err)
        ? (err.detail || err.message || err.error || "Unable to publish site")
        : "Unable to publish site";
      toast({
        title: "Error",
        description: message,
        variant: "destructive"
      });
      throw err;
    } finally {
      setPublishing(false);
    }
  }, [api, podcastId, toast]); // Removed onWebsiteUpdated from deps

  const pollDomainStatus = useCallback(async () => {
    if (!podcastId) return;
    
    const checkStatus = async () => {
      try {
        const status = await api.get(`/api/podcasts/${podcastId}/website/domain-status`);
        
        if (status.is_ready) {
          toast({
            title: "✅ Your website is now live!",
            description: `Visit ${status.domain} to see it in action.`,
            duration: 10000
          });
          if (onWebsiteUpdatedRef.current) {
            await onWebsiteUpdatedRef.current();
          }
          return true; // Stop polling
        }
        return false; // Continue polling
      } catch (err) {
        console.error("Failed to check domain status", err);
        return true; // Stop polling on error
      }
    };
    
    // Poll every 30 seconds for up to 20 minutes
    const maxAttempts = 40;
    let attempts = 0;
    
    const intervalId = setInterval(async () => {
      attempts++;
      const shouldStop = await checkStatus();
      
      if (shouldStop || attempts >= maxAttempts) {
        clearInterval(intervalId);
      }
    }, 30000); // 30 seconds
  }, [api, podcastId, toast]); // Removed onWebsiteUpdated from deps

  return {
    publishing,
    publishStatus,
    publish,
  };
}

/**
 * Hook for managing custom domain operations
 * @param {string} token - Authentication token
 * @param {string} podcastId - Selected podcast ID
 * @param {Function} onWebsiteUpdated - Callback when website is updated
 * @param {string} customDomain - Current custom domain value (optional, for initializing domain draft)
 * @returns {Object} Domain state and operations
 */
export function useWebsiteDomain(token, podcastId, onWebsiteUpdated, customDomain = null) {
  const { toast } = useToast();
  const api = useMemo(() => makeApi(token), [token]);
  
  const [savingDomain, setSavingDomain] = useState(false);
  const [domainDraft, setDomainDraft] = useState(customDomain || "");
  
  // Use ref to avoid recreating callbacks when onWebsiteUpdated changes
  const onWebsiteUpdatedRef = useRef(onWebsiteUpdated);
  useEffect(() => {
    onWebsiteUpdatedRef.current = onWebsiteUpdated;
  }, [onWebsiteUpdated]);
  
  // Update domain draft when custom_domain changes
  useEffect(() => {
    const newDomain = customDomain || "";
    if (domainDraft !== newDomain) {
      setDomainDraft(newDomain);
    }
  }, [customDomain, domainDraft]);

  const saveDomain = useCallback(async (domain) => {
    if (!podcastId) return;
    
    setSavingDomain(true);
    try {
      const payload = { custom_domain: domain?.trim() ? domain.trim() : null };
      const data = await api.patch(`/api/podcasts/${podcastId}/website/domain`, payload);
      
      if (onWebsiteUpdatedRef.current) {
        await onWebsiteUpdatedRef.current();
      }
      
      toast({
        title: "Domain updated",
        description: data.custom_domain 
          ? `Live at ${data.custom_domain}` 
          : "Using the default domain."
      });
      return data;
    } catch (err) {
      console.error("Failed to update domain", err);
      const message = isApiError(err)
        ? (err.detail || err.message || err.error || "Unable to update domain")
        : "Unable to update domain";
      toast({
        title: "Error",
        description: message,
        variant: "destructive"
      });
      throw err;
    } finally {
      setSavingDomain(false);
    }
  }, [api, podcastId, toast]); // Removed onWebsiteUpdated from deps

  return {
    domainDraft,
    setDomainDraft,
    savingDomain,
    saveDomain,
  };
}

/**
 * Hook for managing AI chat operations
 * @param {string} token - Authentication token
 * @param {string} podcastId - Selected podcast ID
 * @param {Function} onWebsiteUpdated - Callback when website is updated
 * @returns {Object} Chat state and operations
 */
export function useWebsiteChat(token, podcastId, onWebsiteUpdated) {
  const { toast } = useToast();
  const api = useMemo(() => makeApi(token), [token]);
  
  const [chatting, setChatting] = useState(false);
  const [chatMessage, setChatMessage] = useState("");
  
  // Use ref to avoid recreating callbacks when onWebsiteUpdated changes
  const onWebsiteUpdatedRef = useRef(onWebsiteUpdated);
  useEffect(() => {
    onWebsiteUpdatedRef.current = onWebsiteUpdated;
  }, [onWebsiteUpdated]);

  const sendChatMessage = useCallback(async (message) => {
    if (!podcastId || !message?.trim()) return null;
    
    setChatting(true);
    try {
      const data = await api.post(`/api/podcasts/${podcastId}/website/chat`, {
        message: message.trim()
      });
      
      if (onWebsiteUpdatedRef.current) {
        await onWebsiteUpdatedRef.current();
      }
      
      setChatMessage("");
      toast({
        title: "Update applied",
        description: "The AI builder adjusted your layout."
      });
      return data;
    } catch (err) {
      console.error("Failed to apply update", err);
      const message = isApiError(err)
        ? (err.detail || err.message || err.error || "Unable to update site")
        : "Unable to update site";
      toast({
        title: "Error",
        description: message,
        variant: "destructive"
      });
      throw err;
    } finally {
      setChatting(false);
    }
  }, [api, podcastId, toast]); // Removed onWebsiteUpdated from deps

  return {
    chatting,
    chatMessage,
    setChatMessage,
    sendChatMessage,
  };
}

/**
 * Hook for managing CSS operations
 * @param {string} token - Authentication token
 * @param {string} podcastId - Selected podcast ID
 * @param {Function} onWebsiteUpdated - Callback when website is updated
 * @returns {Object} CSS state and operations
 */
export function useWebsiteCSS(token, podcastId, onWebsiteUpdated) {
  const { toast } = useToast();
  const api = useMemo(() => makeApi(token), [token]);
  
  const [cssEditorLoading, setCSSEditorLoading] = useState(false);
  
  // Use ref to avoid recreating callbacks when onWebsiteUpdated changes
  const onWebsiteUpdatedRef = useRef(onWebsiteUpdated);
  useEffect(() => {
    onWebsiteUpdatedRef.current = onWebsiteUpdated;
  }, [onWebsiteUpdated]);

  const saveCSS = useCallback(async (css) => {
    if (!podcastId) return;
    
    setCSSEditorLoading(true);
    try {
      await api.patch(`/api/podcasts/${podcastId}/website/css`, { css });
      
      if (onWebsiteUpdatedRef.current) {
        await onWebsiteUpdatedRef.current();
      }
      
      toast({
        title: "CSS updated",
        description: "Your custom styles have been saved."
      });
    } catch (err) {
      console.error("Failed to update CSS", err);
      toast({
        title: "Failed to update CSS",
        description: isApiError(err)
          ? (err.detail || err.error || "Unable to save CSS")
          : "Unable to save CSS",
        variant: "destructive"
      });
      throw err;
    } finally {
      setCSSEditorLoading(false);
    }
  }, [api, podcastId, toast]); // Removed onWebsiteUpdated from deps

  const generateAICSS = useCallback(async (prompt) => {
    if (!podcastId || !prompt?.trim()) return;
    
    setCSSEditorLoading(true);
    try {
      const result = await api.patch(`/api/podcasts/${podcastId}/website/css`, {
        css: "",
        ai_prompt: prompt
      });
      
      if (onWebsiteUpdatedRef.current) {
        await onWebsiteUpdatedRef.current();
      }
      
      toast({
        title: "CSS generated",
        description: "AI has created custom styles for your website."
      });
      return result;
    } catch (err) {
      console.error("Failed to generate CSS", err);
      toast({
        title: "Failed to generate CSS",
        description: isApiError(err)
          ? (err.detail || err.error || "Unable to generate CSS")
          : "Unable to generate CSS",
        variant: "destructive"
      });
      throw err;
    } finally {
      setCSSEditorLoading(false);
    }
  }, [api, podcastId, toast]); // Removed onWebsiteUpdated from deps

  return {
    cssEditorLoading,
    saveCSS,
    generateAICSS,
  };
}

/**
 * Hook for managing AI theme generation
 * @param {string} token - Authentication token
 * @param {string} podcastId - Selected podcast ID
 * @param {Function} onWebsiteUpdated - Callback when website is updated
 * @returns {Object} Theme generation state and operations
 */
export function useWebsiteAITheme(token, podcastId, onWebsiteUpdated) {
  const { toast } = useToast();
  const api = useMemo(() => makeApi(token), [token]);
  
  const [generatingTheme, setGeneratingTheme] = useState(false);
  
  // Use ref to avoid recreating callbacks when onWebsiteUpdated changes
  const onWebsiteUpdatedRef = useRef(onWebsiteUpdated);
  useEffect(() => {
    onWebsiteUpdatedRef.current = onWebsiteUpdated;
  }, [onWebsiteUpdated]);

  const generateAITheme = useCallback(async () => {
    if (!podcastId) return;
    
    setGeneratingTheme(true);
    try {
      const result = await api.post(`/api/podcasts/${podcastId}/website/generate-ai-theme`);
      
      if (onWebsiteUpdatedRef.current) {
        await onWebsiteUpdatedRef.current();
      }
      
      toast({
        title: "AI Theme Generated!",
        description: result.description || "Your website now has a custom themed design."
      });
      return result;
    } catch (err) {
      console.error("Failed to generate AI theme", err);
      let message = "Unable to generate theme";
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
        title: "Failed to generate theme",
        description: message,
        variant: "destructive"
      });
      throw err;
    } finally {
      setGeneratingTheme(false);
    }
  }, [api, podcastId, toast]); // Removed onWebsiteUpdated from deps

  return {
    generatingTheme,
    generateAITheme,
  };
}

