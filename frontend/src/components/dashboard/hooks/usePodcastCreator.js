import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from '@/hooks/use-toast';
import { makeApi } from '@/lib/apiClient';
import { fetchVoices as fetchElevenVoices } from '@/api/elevenlabs';
import { useAuth } from '@/AuthContext.jsx';

// Phase 1 extracted hooks
import useStepNavigation from './creator/useStepNavigation';
import useFileUpload from './creator/useFileUpload';
import useEpisodeAssembly from './creator/useEpisodeAssembly';

// Phase 2 & 3 extracted hooks
import useVoiceConfiguration from './creator/useVoiceConfiguration';
import useEpisodeMetadata from './creator/useEpisodeMetadata';
import usePublishing from './creator/usePublishing';
import useAIFeatures from './creator/useAIFeatures';

// Newly created hooks
import useMediaManagement from './creator/useMediaManagement';
import useAIOrchestration from './creator/useAIOrchestration';
import useScheduling from './creator/useScheduling';
import useQuota from './creator/useQuota';

export default function usePodcastCreator({
  token,
  templates,
  initialStep,
  testInject,
  preselectedMainFilename,
  preselectedTranscriptReady,
  creatorMode = 'standard',
  wasRecorded = false,
  preselectedStartStep,
}) {
  const { user: authUser, refreshUser } = useAuth();
  
  const [error, setError] = useState('');
  const [statusMessage, setStatusMessage] = useState('');
  const [capabilities, setCapabilities] = useState({ has_elevenlabs: false, has_google_tts: false, has_any_sfx_triggers: false });
  const [testMode, setTestMode] = useState(false);
  const [useAdvancedAudio, setUseAdvancedAudio] = useState(() => Boolean(authUser?.use_advanced_audio_processing));
  const [isSavingAdvancedAudio, setIsSavingAdvancedAudio] = useState(false);

  const stepNav = useStepNavigation({
    token,
    initialStep,
    creatorMode,
  });

  const fileUpload = useFileUpload({
    token,
    setError,
    setStatusMessage,
  });

  const voiceConfig = useVoiceConfiguration({
    token,
    currentStep: stepNav.currentStep,
    selectedTemplate: stepNav.selectedTemplate,
    setSelectedTemplate: stepNav.setSelectedTemplate,
  });

  const metadata = useEpisodeMetadata({
    token,
    selectedTemplate: stepNav.selectedTemplate,
    uploadedFilename: fileUpload.uploadedFilename,
    expectedEpisodeId: null,
    transcriptPath: fileUpload.transcriptPath,
    resetTranscriptState: fileUpload.resetTranscriptState,
  });
  
  const mediaManagement = useMediaManagement({
    token,
    episodeDetails: metadata.episodeDetails,
    setEpisodeDetails: metadata.setEpisodeDetails,
  });

  const aiOrchestration = useAIOrchestration({
    token,
    uploadedFilename: fileUpload.uploadedFilename,
    selectedPreupload: fileUpload.selectedPreupload,
    selectedTemplate: stepNav.selectedTemplate,
    transcriptReady: fileUpload.transcriptReady,
    expectedEpisodeId: null,
    setTranscriptReady: fileUpload.setTranscriptReady,
    setTranscriptPath: fileUpload.setTranscriptPath,
    resolveInternVoiceId: () => voiceConfig.resolveInternVoiceId(),
    capabilities,
  });

  // Publishing must be initialized before scheduling because scheduling
  // references publishing setters (setPublishMode, setScheduleDate, setScheduleTime).
  // Defining `publishing` earlier avoids the "Cannot access 'publishing' before initialization" TDZ error.
  // Note: We'll wire up assembly values (autoPublishPending, assemblyComplete, assembledEpisode) 
  // after assembly is initialized (see useEffect below)
  const [assemblyAutoPublishPending, setAssemblyAutoPublishPending] = useState(false);
  const [assemblyComplete, setAssemblyComplete] = useState(false);
  const [assembledEpisode, setAssembledEpisode] = useState(null);

  const setAutoPublishPendingBridgeRef = useRef((value) => {
    setAssemblyAutoPublishPending(value);
  });
  const setAutoPublishPendingBridge = useCallback((value) => {
    setAutoPublishPendingBridgeRef.current(value);
  }, []);

  const publishing = usePublishing({
    token,
    selectedTemplate: stepNav.selectedTemplate,
    assembledEpisode, // Wired from assembly hook below
    assemblyComplete, // Wired from assembly hook below
    autoPublishPending: assemblyAutoPublishPending, // Wired from assembly hook below
    setAutoPublishPending: setAutoPublishPendingBridge,
    setStatusMessage,
    setError,
    setCurrentStep: stepNav.setCurrentStep,
  });

  const scheduling = useScheduling({
    token,
    selectedTemplate: stepNav.selectedTemplate,
    templates,
    setSelectedTemplate: stepNav.setSelectedTemplate, // Already the normalized setter from stepNav
    setCurrentStep: stepNav.setCurrentStep,
    setPublishMode: publishing.setPublishMode,
    setScheduleDate: publishing.setScheduleDate,
    setScheduleTime: publishing.setScheduleTime,
  });

  const quota = useQuota({
    token,
    selectedTemplate: stepNav.selectedTemplate,
    uploadedFilename: fileUpload.uploadedFilename,
    audioDurationSec: fileUpload.audioDurationSec,
  });


  const aiFeatures = useAIFeatures({
    token,
    uploadedFilename: fileUpload.uploadedFilename,
    selectedPreupload: fileUpload.selectedPreupload,
    selectedTemplate: stepNav.selectedTemplate,
    setStatusMessage,
    setCurrentStep: stepNav.setCurrentStep,
    resolveInternVoiceId: () => voiceConfig.resolveInternVoiceId(),
    requireIntern: !!capabilities?.has_elevenlabs,
    requireSfx: !!capabilities?.has_any_sfx_triggers,
    internPrefetch: aiOrchestration.internPrefetch,
  });

  const [showCreditPurchase, setShowCreditPurchase] = useState(false);
  const [creditPurchaseData, setCreditPurchaseData] = useState(null);

  const assembly = useEpisodeAssembly({
    token,
    selectedTemplate: stepNav.selectedTemplate,
    uploadedFilename: fileUpload.uploadedFilename,
    episodeDetails: metadata.episodeDetails,
    ttsValues: voiceConfig.ttsValues,
    flubberCutsMs: aiFeatures.flubberCutsMs,
    intents: aiFeatures.intents, // FIXED: Use aiFeatures.intents (has intern_overrides) not aiOrchestration.intents
    setError,
    setStatusMessage,
    setCurrentStep: stepNav.setCurrentStep,
    refreshUsage: quota.refreshUsage,
    audioDurationSec: fileUpload.audioDurationSec,
    minutesPrecheck: quota.minutesPrecheck,
    minutesPrecheckPending: quota.minutesPrecheckPending,
    setMinutesDialog: quota.setMinutesDialog,
    quotaExceeded: quota.quotaInfo.quotaExceeded,
    publishMode: publishing.publishMode,
    scheduleDate: publishing.scheduleDate,
    scheduleTime: publishing.scheduleTime,
    handleUploadProcessedCoverAndPreview: mediaManagement.handleUploadProcessedCover,
    useAdvancedAudio,
    usage: quota.usage,
    onShowCreditPurchase: (data) => {
      setCreditPurchaseData(data);
      setShowCreditPurchase(true);
    },
  });

  useEffect(() => {
    const assemblySetter = assembly.setAutoPublishPending;
    setAutoPublishPendingBridgeRef.current = (value) => {
      if (typeof assemblySetter === 'function') {
        assemblySetter(value);
      }
      setAssemblyAutoPublishPending(value);
    };

    return () => {
      setAutoPublishPendingBridgeRef.current = (value) => {
        setAssemblyAutoPublishPending(value);
      };
    };
  }, [assembly.setAutoPublishPending]);

  useEffect(() => {
    setUseAdvancedAudio(Boolean(authUser?.use_advanced_audio_processing));
  }, [authUser?.use_advanced_audio_processing]);

  const handleAdvancedAudioToggle = useCallback(
    async (nextValue) => {
      const previousValue = useAdvancedAudio;
      setUseAdvancedAudio(nextValue);
      setIsSavingAdvancedAudio(true);
      try {
        const api = makeApi(token);
        await api.put('/api/users/me/audio-pipeline', { use_advanced_audio: nextValue });
        if (typeof refreshUser === 'function') {
          refreshUser({ force: true });
        }
      } catch (err) {
        setUseAdvancedAudio(previousValue);
        toast({
          variant: 'destructive',
          title: 'Could not update audio pipeline',
          description: err?.detail?.message || err?.message || 'Please try again.',
        });
      } finally {
        setIsSavingAdvancedAudio(false);
      }
    },
    [token, refreshUser, useAdvancedAudio]
  );

  // Wire assembly values to publishing hook (since assembly is initialized after publishing)
  useEffect(() => {
    console.log('[CREATOR] Syncing assembly values to publishing:', {
      autoPublishPending: assembly.autoPublishPending,
      assemblyComplete: assembly.assemblyComplete,
      assembledEpisode: assembly.assembledEpisode?.id || null,
    });
    setAssemblyAutoPublishPending(assembly.autoPublishPending);
    setAssemblyComplete(assembly.assemblyComplete);
    setAssembledEpisode(assembly.assembledEpisode);
  }, [assembly.autoPublishPending, assembly.assemblyComplete, assembly.assembledEpisode]);

  useEffect(() => {
    (async () => {
      try {
        const caps = await makeApi(token).get('/api/users/me/capabilities');
        if (caps) {
          setCapabilities({
            has_elevenlabs: !!caps.has_elevenlabs,
            has_google_tts: !!caps.has_google_tts,
            has_any_sfx_triggers: !!caps.has_any_sfx_triggers,
          });
        }
      } catch (_) {}
    })();
  }, [token]);

  // Defensive: if selectedTemplate ever appears without segments (for example
  // because a lightweight template object from a list was written into state),
  // fetch the full template and normalize it. This prevents the UI from being
  // left in a state with no segments (which previously manifested as
  // "This template has no segments to display"). We use the stepNav setter
  // which is already the normalized setter.
  useEffect(() => {
    // Re-run whenever the selectedTemplate object changes (not just its id).
    // This catches cases where some code overwrites the template with a
    // lightweight object that has the same id but lacks `segments`.
    const tpl = stepNav.selectedTemplate;
    if (!tpl || !tpl.id) return;
    const hasSegments = Array.isArray(tpl.segments) && tpl.segments.length > 0;
    if (hasSegments) return;

    console.warn('[usePodcastCreator] DEFENSIVE REFETCH: template missing segments, fetching full template', { templateId: tpl.id, currentSegments: tpl.segments });
    let cancelled = false;
    (async () => {
      try {
        const api = makeApi(token);
        const full = await api.get(`/api/templates/${tpl.id}`);
        if (cancelled) return;
        console.debug('[usePodcastCreator] DEFENSIVE REFETCH: fetched full template, restoring segments', { templateId: tpl.id, fetchedSegments: full.segments });
        // Merge existing lightweight template with full payload - the
        // stepNav setter will normalize/seed segments.
        stepNav.setSelectedTemplate({ ...tpl, ...full });
      } catch (err) {
        // Non-fatal: if fetch fails, leave the template as-is and rely on
        // existing UI fallbacks in StepCustomizeSegments.
        console.error('[usePodcastCreator] DEFENSIVE REFETCH FAILED:', err);
      }
    })();
    return () => { cancelled = true; };
  }, [stepNav.selectedTemplate, token]);

  // Calculate pendingIntentLabels - intents that have detected commands but user hasn't answered yet
  const pendingIntentLabels = useMemo(() => {
    const labels = [];
    const detections = aiOrchestration.intentDetections || {};
    const answers = aiFeatures.intents || {};
    
    // Check flubber
    if (Number((detections?.flubber?.count) ?? 0) > 0 && answers.flubber === null) {
      labels.push('flubber');
    }
    // Check intern
    if (Number((detections?.intern?.count) ?? 0) > 0 && answers.intern === null) {
      labels.push('intern');
    }
    // Check sfx
    if (Number((detections?.sfx?.count) ?? 0) > 0 && answers.sfx === null) {
      labels.push('sfx');
    }
    
    return labels;
  }, [aiOrchestration.intentDetections, aiFeatures.intents]);

  // Calculate intentsComplete - true if all detected intents have been answered
  const intentsComplete = useMemo(() => {
    return pendingIntentLabels.length === 0;
  }, [pendingIntentLabels]);

  return {
    showCreditPurchase,
    setShowCreditPurchase,
    creditPurchaseData,
    setCreditPurchaseData,
    ...stepNav,
    ...fileUpload,
    ...voiceConfig,
    ...metadata,
    ...mediaManagement,
    ...aiOrchestration,
    ...scheduling,
    ...quota,
    ...publishing,
    ...aiFeatures,
    ...assembly,
    error,
    statusMessage,
    testMode,
    useAdvancedAudio,
    handleAdvancedAudioToggle,
    isSavingAdvancedAudio,
    capabilities,
    pendingIntentLabels,
    intentsComplete,
  };
}