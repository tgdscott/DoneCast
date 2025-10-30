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
  const { user: authUser } = useAuth();
  
  const [error, setError] = useState('');
  const [statusMessage, setStatusMessage] = useState('');
  const [capabilities, setCapabilities] = useState({ has_elevenlabs: false, has_google_tts: false, has_any_sfx_triggers: false });
  const [testMode, setTestMode] = useState(false);
  const [useAuphonic, setUseAuphonic] = useState(false);

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
    selectedTemplate: stepNav.selectedTemplate,
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

  const scheduling = useScheduling({
    token,
    selectedTemplate: stepNav.selectedTemplate,
    setPublishMode: () => {},
    setScheduleDate: () => {},
    setScheduleTime: () => {},
  });

  const quota = useQuota({
    token,
    selectedTemplate: stepNav.selectedTemplate,
    uploadedFilename: fileUpload.uploadedFilename,
    audioDurationSec: fileUpload.audioDurationSec,
  });

  const publishing = usePublishing({
    token,
    selectedTemplate: stepNav.selectedTemplate,
    assembledEpisode: null,
    assemblyComplete: false,
    setStatusMessage,
    setError,
    setCurrentStep: stepNav.setCurrentStep,
    testMode,
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

  const assembly = useEpisodeAssembly({
    token,
    selectedTemplate: stepNav.selectedTemplate,
    uploadedFilename: fileUpload.uploadedFilename,
    episodeDetails: metadata.episodeDetails,
    ttsValues: voiceConfig.ttsValues,
    flubberCutsMs: aiFeatures.flubberCutsMs,
    intents: aiOrchestration.intents,
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
    useAuphonic,
  });

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

  return {
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
    useAuphonic,
    setUseAuphonic,
    capabilities,
  };
}