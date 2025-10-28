import { useState, useEffect, useRef, useCallback } from 'react';
import { toast } from '@/hooks/use-toast';
import { makeApi } from '@/lib/apiClient';

/**
 * Manages episode publishing workflow
 * Handles publish modes (now, draft, schedule), visibility, auto-publish, and validation
 * 
 * @param {Object} options
 * @param {string} options.token - Auth token for API calls
 * @param {Object} options.selectedTemplate - Currently selected podcast template
 * @param {Object} options.assembledEpisode - Assembled episode object
 * @param {boolean} options.assemblyComplete - Whether assembly is complete
 * @param {Function} options.setStatusMessage - Callback to set status message
 * @param {Function} options.setError - Callback to set error message
 * @param {Function} options.setCurrentStep - Callback to set current wizard step
 * @param {boolean} options.testMode - Whether in test mode (auto-sets draft)
 * @returns {Object} Publishing state and handlers
 */
export default function usePublishing({
  token,
  selectedTemplate,
  assembledEpisode,
  assemblyComplete,
  setStatusMessage,
  setError,
  setCurrentStep,
  testMode,
}) {
  // Publishing state
  const [isPublishing, setIsPublishing] = useState(false);
  const [publishMode, setPublishMode] = useState('draft'); // 'now', 'draft', 'schedule'
  const [publishVisibility, setPublishVisibility] = useState('public'); // 'public', 'unpublished'
  const [scheduleDate, setScheduleDate] = useState('');
  const [scheduleTime, setScheduleTime] = useState('');
  const [autoPublishPending, setAutoPublishPending] = useState(false);
  
  // Track last auto-published episode to prevent duplicate publishing
  const [lastAutoPublishedEpisodeId, setLastAutoPublishedEpisodeId] = useState(null);
  const publishingTriggeredRef = useRef(false);
  
  // Track whether user had stored publish preferences
  const hadStoredPublishRef = useRef(false);

  // Initialize publish settings from localStorage
  useEffect(() => {
    try {
      const storedMode = localStorage.getItem('ppp_publish_mode');
      if (storedMode && ['now', 'draft', 'schedule'].includes(storedMode)) {
        setPublishMode(storedMode);
      }
      hadStoredPublishRef.current = !!storedMode;
      
      const storedVis = localStorage.getItem('ppp_publish_visibility');
      if (storedVis && ['public', 'unpublished'].includes(storedVis)) {
        setPublishVisibility(storedVis);
      }
      
      const storedSchedule = localStorage.getItem('ppp_schedule_datetime');
      let base;
      if (storedSchedule) {
        const d = new Date(storedSchedule);
        if (!isNaN(d.getTime()) && d.getTime() > Date.now() + 10 * 60000) {
          base = d;
        }
      }
      if (!base) {
        base = new Date(Date.now() + 60 * 60000);
        const mins = base.getMinutes();
        const rounded = Math.ceil(mins / 5) * 5;
        if (rounded >= 60) {
          base.setHours(base.getHours() + 1);
          base.setMinutes(0);
        } else {
          base.setMinutes(rounded);
        }
        base.setSeconds(0, 0);
      }
      const yyyy = base.getFullYear();
      const mm = String(base.getMonth() + 1).padStart(2, '0');
      const dd = String(base.getDate()).padStart(2, '0');
      const hh = String(base.getHours()).padStart(2, '0');
      const mi = String(base.getMinutes()).padStart(2, '0');
      setScheduleDate(`${yyyy}-${mm}-${dd}`);
      setScheduleTime(`${hh}:${mi}`);
    } catch {}
  }, []);

  // Set default publish mode based on test mode (if no stored preference)
  useEffect(() => {
    if (!hadStoredPublishRef.current) {
      setPublishMode(testMode ? 'draft' : 'now');
    }
  }, [testMode]);

  // Persist publish settings to localStorage
  useEffect(() => {
    try {
      localStorage.setItem('ppp_publish_mode', publishMode);
    } catch {}
  }, [publishMode]);

  useEffect(() => {
    try {
      localStorage.setItem('ppp_publish_visibility', publishVisibility);
    } catch {}
  }, [publishVisibility]);

  useEffect(() => {
    try {
      if (scheduleDate && scheduleTime) {
        const iso = new Date(`${scheduleDate}T${scheduleTime}:00`).toISOString();
        localStorage.setItem('ppp_schedule_datetime', iso);
      }
    } catch {}
  }, [scheduleDate, scheduleTime]);

  // Internal publish handler (shared by manual and auto-publish)
  const handlePublishInternal = useCallback(
    async ({ scheduleEnabled, publish_at, publish_at_local }) => {
      let showId = null;
      if (selectedTemplate && selectedTemplate.podcast_id) {
        showId = selectedTemplate.podcast_id;
      }
      if (!showId) {
        toast({
          variant: 'destructive',
          title: 'Missing show',
          description: 'Template needs a show association.',
        });
        return;
      }
      
      const effectiveState = scheduleEnabled ? 'unpublished' : publishVisibility;
      const payload = { publish_state: effectiveState };
      if (publish_at) {
        payload.publish_at = publish_at;
        if (publish_at_local) payload.publish_at_local = publish_at_local;
      }
      
      try {
        const api = makeApi(token);
        await api.post(`/api/episodes/${assembledEpisode.id}/publish`, payload);
        const msg = scheduleEnabled
          ? 'Episode scheduled successfully.'
          : 'Episode published successfully.';
        toast({ title: 'Publish', description: msg });
        setStatusMessage(msg);
        
        try {
          if (assembledEpisode?.id) setLastAutoPublishedEpisodeId(assembledEpisode.id);
        } catch {}
        
        try {
          const pubData = await api.get(`/api/episodes/${assembledEpisode.id}/publish/status`);
          if (pubData.last_error) {
            toast({
              variant: 'destructive',
              title: 'Publish downstream error',
              description: pubData.last_error,
            });
          }
        } catch {}
      } catch (e) {
        toast({
          variant: 'destructive',
          title: 'Publish failed',
          description: e.message || String(e),
        });
      }
    },
    [token, selectedTemplate, assembledEpisode, publishVisibility, setStatusMessage]
  );

  // Manual publish handler (user clicks "Publish" button)
  const handlePublish = useCallback(
    async () => {
      if (!assembledEpisode) {
        setError('Assembled episode required.');
        return;
      }
      
      let showId = null;
      if (selectedTemplate && selectedTemplate.podcast_id) {
        showId = selectedTemplate.podcast_id;
      }
      if (!showId) {
        setError('Template is not linked to a show (podcast). Update template to include its show.');
        toast({
          variant: 'destructive',
          title: 'Missing show',
          description: 'Template needs a show association.',
        });
        return;
      }
      
      setIsPublishing(true);
      setStatusMessage('Publishing your episode...');
      setError('');
      
      const scheduleEnabled = publishMode === 'schedule';
      let publish_at = null;
      let publish_at_local = null;
      
      if (scheduleEnabled && scheduleDate && scheduleTime) {
        try {
          const local = new Date(`${scheduleDate}T${scheduleTime}:00`);
          if (!isNaN(local.getTime()) && local.getTime() > Date.now() + 60 * 1000) {
            publish_at = new Date(local.getTime()).toISOString();
            publish_at_local = `${scheduleDate} ${scheduleTime}`;
          } else {
            toast({
              variant: 'destructive',
              title: 'Invalid schedule time',
              description: 'Pick a future date/time (>= 1 minute ahead).',
            });
            setIsPublishing(false);
            return;
          }
        } catch (e) {
          toast({
            variant: 'destructive',
            title: 'Invalid schedule time',
            description: 'Unable to parse date/time.',
          });
          setIsPublishing(false);
          return;
        }
      }

      try {
        const effectiveState = scheduleEnabled ? 'unpublished' : publishVisibility;
        const payload = {
          publish_state: effectiveState,
        };
        if (publish_at) {
          payload.publish_at = publish_at;
          if (publish_at_local) payload.publish_at_local = publish_at_local;
        }
        
        const api = makeApi(token);
        let result = await api.post(`/api/episodes/${assembledEpisode.id}/publish`, payload);
        if (!result || typeof result !== 'object') result = {};
        
        const scheduled = !!publish_at;
        const wasPrivate = effectiveState === 'unpublished' && !scheduled;
        const msg = result.message || (scheduled
          ? 'Episode scheduled for future publish.'
          : wasPrivate ? 'Episode uploaded privately.' : 'Episode published publicly.');
        
        setStatusMessage(msg);
        toast({ title: 'Success!', description: msg });
        
        try {
          if (assembledEpisode?.id) setLastAutoPublishedEpisodeId(assembledEpisode.id);
        } catch {}
        
        setCurrentStep(6);
      } catch (err) {
        const friendly = err && err.message
          ? err.message
          : (typeof err === 'string' ? err : 'Publish failed');
        setError(friendly);
        setStatusMessage('');
        toast({ variant: 'destructive', title: 'Error', description: friendly });
      } finally {
        setIsPublishing(false);
      }
    },
    [
      assembledEpisode,
      selectedTemplate,
      publishMode,
      publishVisibility,
      scheduleDate,
      scheduleTime,
      token,
      setError,
      setStatusMessage,
      setCurrentStep,
    ]
  );

  // Auto-publish effect (triggers when assembly completes)
  const assembledEpisodeId = assembledEpisode?.id;
  
  useEffect(() => {
    if (!assemblyComplete || !autoPublishPending || !assembledEpisode) return;
    
    // Guard 1: Check if publishing already triggered for this episode
    if (publishingTriggeredRef.current && assembledEpisode?.id === lastAutoPublishedEpisodeId) {
      setAutoPublishPending(false);
      return;
    }
    
    // Guard 2: Legacy check
    if (lastAutoPublishedEpisodeId && assembledEpisode.id === lastAutoPublishedEpisodeId) {
      setAutoPublishPending(false);
      return;
    }
    
    if (publishMode === 'draft') {
      setAutoPublishPending(false);
      setStatusMessage('Draft created (processing complete).');
      publishingTriggeredRef.current = false; // Reset for next episode
      return;
    }
    
    // Set flag IMMEDIATELY before async operation to prevent race conditions
    publishingTriggeredRef.current = true;
    
    // Capture schedule values at the moment autopublish triggers (don't re-trigger on date/time changes)
    const capturedPublishMode = publishMode;
    const capturedScheduleDate = scheduleDate;
    const capturedScheduleTime = scheduleTime;
    
    let scheduleEnabled = capturedPublishMode === 'schedule';
    let publish_at = null;
    let publish_at_local = null;
    
    if (scheduleEnabled) {
      const dt = new Date(`${capturedScheduleDate}T${capturedScheduleTime}:00`);
      if (!isNaN(dt.getTime()) && dt.getTime() > Date.now() + 9 * 60000) {
        publish_at = dt.toISOString().replace(/\.\d{3}Z$/, 'Z');
        publish_at_local = `${capturedScheduleDate} ${capturedScheduleTime}`;
      } else {
        toast({
          variant: 'destructive',
          title: 'Schedule invalid',
          description: 'Falling back to draft.',
        });
        setAutoPublishPending(false);
        return;
      }
    }
    
    (async () => {
      setIsPublishing(true);
      try {
        await handlePublishInternal({ scheduleEnabled, publish_at, publish_at_local });
      } finally {
        setIsPublishing(false);
        setAutoPublishPending(false);
      }
    })();
    // CRITICAL: Only trigger when assembly completes and autopublish flag is set
    // Use assembledEpisodeId (string) instead of assembledEpisode (object) to prevent re-triggers on object changes
    // Do NOT include scheduleDate/scheduleTime as dependencies or we'll publish multiple times!
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assemblyComplete, autoPublishPending, assembledEpisodeId]);

  return {
    // State
    isPublishing,
    publishMode,
    setPublishMode,
    publishVisibility,
    setPublishVisibility,
    scheduleDate,
    setScheduleDate,
    scheduleTime,
    setScheduleTime,
    autoPublishPending,
    setAutoPublishPending,
    lastAutoPublishedEpisodeId,
    
    // Handlers
    handlePublish,
  };
}
