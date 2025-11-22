import React from 'react';
import usePodcastCreator from './hooks/usePodcastCreator';
import StepTemplateSelection from './podcastCreatorSteps/StepTemplateSelection';
import StepUploadAudio from './podcastCreatorSteps/StepUploadAudio';
import StepSelectPreprocessed from './podcastCreatorSteps/StepSelectPreprocessed';
import StepCustomizeSegments from './podcastCreatorSteps/StepCustomizeSegments';
import StepCoverArt from './podcastCreatorSteps/StepCoverArt';
import StepEpisodeDetails from './podcastCreatorSteps/StepEpisodeDetails';
import StepAssemble from './podcastCreatorSteps/StepAssemble';
import PodcastCreatorScaffold from './podcastCreator/PodcastCreatorScaffold';
import FlubberScanOverlay from './podcastCreator/FlubberScanOverlay';
import FlubberRetryModal from './podcastCreator/FlubberRetryModal';
import FlubberCommandReviewText from './podcastCreator/FlubberCommandReviewText';
import InternCommandReviewText from './podcastCreator/InternCommandReviewText';
import IntentQuestions from './IntentQuestions';
import VoicePicker from '@/components/VoicePicker';
import CreditPurchaseModal from './CreditPurchaseModal';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useToast } from '@/hooks/use-toast';
import { makeApi } from '@/lib/apiClient';
import { useResolvedTimezone } from '@/hooks/useResolvedTimezone';
import { formatInTimezone } from '@/lib/timezone';
import { formatDisplayName, isUuidLike } from '@/lib/displayNames';

export default function PodcastCreator({
  onBack,
  token,
  templates = [],
  podcasts,
  initialStep,
  testInject,
  preselectedMainFilename,
  preselectedTranscriptReady,
  creatorMode = 'standard',
  wasRecorded = false,
  preuploadedItems = [],
  preuploadedLoading = false,
  onRefreshPreuploaded = () => {},
  preselectedStartStep,
  onRequestUpload,
  userTimezone = null,
  onViewHistory = null,
}) {
  const resolvedTimezone = useResolvedTimezone(userTimezone);
  const controller = usePodcastCreator({
    token,
    templates,
    initialStep,
    testInject,
    preselectedMainFilename,
    preselectedTranscriptReady,
    creatorMode,
    wasRecorded,
    preselectedStartStep,
  });

  const {
    currentStep,
    setCurrentStep,
    steps,
    progressPercentage,
    selectedTemplate,
    handleTemplateSelect,
    uploadedFilename,
    wasRecorded: wasRecordedFromHook,
    selectedPreupload,
    isUploading,
    uploadProgress,
    handleFileChange,
    mainSegments,
    segmentsDirty,
    isBundling,
    bundleError,
    removeSegment,
    updateSegmentProcessingMode,
    reorderSegments,
    composeSegments,
    handlePreuploadedSelect,
    fileInputRef,
    uploadStats,
    mediaLibrary,
    ttsValues,
    handleTtsChange,
    setShowVoicePicker,
    setVoicePickerTargetId,
    voiceNameById,
    voicesLoading,
    coverArtInputRef,
    coverCropperRef,
    coverNeedsUpload,
    handleCoverFileSelected,
    handleUploadProcessedCover,
    episodeDetails,
    updateCoverCrop,
    setCoverMode,
    clearCover,
    isUploadingCover,
    handleDetailsChange,
    transcriptReady,
    isAssembling,
    isPublishing,
    isAiTitleBusy,
    isAiDescBusy,
    publishMode,
    publishVisibility,
    scheduleDate,
    scheduleTime,
    canProceedToStep5,
    blockingQuota,
    missingTitle,
    missingEpisodeNumber,
    handleAISuggestTitle,
    handleAIRefineTitle,
    handleAISuggestDescription,
    handleAIRefineDescription,
    handleAssemble,
    handleCancelAssembly,
    assemblyComplete,
    processingEstimate,
    assembledEpisode,
    statusMessage,
    showFlubberScan,
    setShowFlubberScan,
    showFlubberReview,
    flubberContexts,
    showInternReview,
    internReviewContexts,
    internResponses,
    handleFlubberConfirm,
    handleFlubberCancel,
    handleInternComplete,
    handleInternCancel,
    showIntentQuestions,
    handleIntentSubmit,
    intents,
    intentDetections,
    intentDetectionReady,
    handleIntentAnswerChange,
    intentVisibility,
    capabilities,
    intentsComplete,
    pendingIntentLabels,
    flubberNotFound,
    fuzzyThreshold,
    setFuzzyThreshold,
    retryFlubberSearch,
    skipFlubberRetry,
    usage,
    minutesNearCap,
    minutesRemaining,
    audioDurationSec,
    minutesPrecheck,
    minutesPrecheckPending,
    minutesPrecheckError,
    minutesBlocking,
    minutesRequiredPrecheck,
    minutesRemainingPrecheck,
    minutesDialog,
    setMinutesDialog,
    activeSegment,
    retryMinutesPrecheck,
    showVoicePicker,
    handleVoiceChange,
    processInternCommand,
    setPublishMode,
    setPublishVisibility,
    setScheduleDate,
    setScheduleTime,
    setShowIntentQuestions,
    cancelBuild,
    buildActive,
    resolveInternVoiceId,
    useAdvancedAudio,
    handleAdvancedAudioToggle,
    isSavingAdvancedAudio,
  } = controller;

  // Auto-fill title/description/tags when user reaches Step 5 and conditions met
  const autoFillTriggeredRef = React.useRef({ templateId: null, transcriptPath: null });
  React.useEffect(() => {
    // Only trigger on Step 5 entry
    if (currentStep !== 5) return;
    if (!selectedTemplate) return;
    // Respect template AI opt-out
    const shouldAuto = selectedTemplate?.ai_settings?.auto_fill_ai !== false;
    if (!shouldAuto) return;
    // Must have a ready transcript to auto-fill
    if (!transcriptReady) return;

    const tplId = selectedTemplate?.id || null;
    const transcriptPath = controller?.transcriptPath || null;
    // Only run once per template + transcript combination
    if (autoFillTriggeredRef.current.templateId === tplId && autoFillTriggeredRef.current.transcriptPath === transcriptPath) return;
    autoFillTriggeredRef.current = { templateId: tplId, transcriptPath };

    (async () => {
      try {
        if (typeof controller.handleAISuggestTitle === 'function') {
          await controller.handleAISuggestTitle();
        }
        if (typeof controller.handleAISuggestDescription === 'function') {
          await controller.handleAISuggestDescription();
        }
        if (typeof controller.suggestTags === 'function') {
          try {
            const tags = await controller.suggestTags();
            if (Array.isArray(tags) && tags.length && typeof handleDetailsChange === 'function') {
              handleDetailsChange('tags', tags.join(', '));
              // Mark tags as AI-generated
              if (typeof controller.setAiGeneratedFields === 'function') {
                controller.setAiGeneratedFields(prev => ({ ...prev, tags: true }));
              }
            }
          } catch (_) {}
        }
      } catch (e) {
        console.warn('[PodcastCreator] autofill failed', e);
      }
    })();
  }, [currentStep, selectedTemplate, transcriptReady, controller, handleDetailsChange]);

  const { toast } = useToast();

  // Auto-select and advance if there's only ONE valid active template
  const autoAdvanceRef = React.useRef(false);
  React.useEffect(() => {
    if (creatorMode === 'preuploaded' && !autoAdvanceRef.current && currentStep === 1) {
      const activeTemplates = templates.filter(t => t.is_active !== false);
      if (activeTemplates.length === 1 && !selectedTemplate) {
        // Automatically select the only template and advance
        handleTemplateSelect(activeTemplates[0]);
        autoAdvanceRef.current = true;
      }
    }
  }, [creatorMode, currentStep, templates, selectedTemplate, handleTemplateSelect]);

  const selectedPreuploadItem = React.useMemo(
    () => {
      if (!selectedPreupload) return null;
      return preuploadedItems.find((item) => item.filename === selectedPreupload) || null;
    },
    [preuploadedItems, selectedPreupload]
  );

  const uploadedAudioLabel = React.useMemo(() => {
    if (Array.isArray(mainSegments) && mainSegments.length > 0) {
      if (mainSegments.length === 1) {
        const segment = mainSegments[0];
        return formatDisplayName(segment.friendlyName || segment.filename, { fallback: segment.friendlyName || 'Audio segment' });
      }
      return `${mainSegments.length} segments`;
    }
    if (selectedPreuploadItem) {
      return formatDisplayName(selectedPreuploadItem, { fallback: '' });
    }
    if (uploadedFilename) {
      return formatDisplayName(uploadedFilename, { fallback: '' });
    }
    return '';
  }, [mainSegments, selectedPreuploadItem, uploadedFilename]);

  const handleDeletePreuploaded = React.useCallback(async (item) => {
    if (!item || !item.id) return;
    if (typeof window !== 'undefined') {
      const confirmed = window.confirm('Delete this upload?');
      if (!confirmed) return;
    }

    try {
      const api = makeApi(token);
      await api.del(`/api/media/${item.id}`);
      const deletedName = formatDisplayName(item, { fallback: 'audio file' }) || 'audio file';
      toast({
        title: 'Upload deleted',
        description: `${deletedName} was removed from your library.`,
      });

      try {
        if (selectedPreupload && item.filename === selectedPreupload) {
          handlePreuploadedSelect(null);
        }
      } catch (_) {}

      try {
        await onRefreshPreuploaded();
      } catch (_) {}
    } catch (err) {
      let description = err?.message || 'Unable to delete upload.';
      const detail = err?.detail;
      if (typeof detail === 'string') description = detail;
      else if (detail && typeof detail === 'object' && typeof detail.detail === 'string') description = detail.detail;
      toast({ variant: 'destructive', title: 'Delete failed', description });
    }
  }, [token, toast, selectedPreupload, handlePreuploadedSelect, onRefreshPreuploaded]);

  const intentDetectionCounts = {
    flubber: Number((intentDetections?.flubber?.count) ?? 0),
    intern: Number((intentDetections?.intern?.count) ?? 0),
    sfx: Number((intentDetections?.sfx?.count) ?? 0),
  };

  const internVoiceId = typeof resolveInternVoiceId === 'function' ? resolveInternVoiceId() : null;
  const internVoiceName = React.useMemo(() => {
    if (!internVoiceId) return null;
    if (internVoiceId === 'default') return 'Default voice';
    const mapped = voiceNameById?.[internVoiceId];
    if (mapped && !isUuidLike(mapped)) return mapped;
    // Check if it's the ElevenLabs George voice (most common default)
    if (internVoiceId === '19B4gjtpL5m876wS3Dfg') return 'George (ElevenLabs)';
    return formatDisplayName(internVoiceId, { fallback: 'AI Voice' }) || 'AI Voice';
  }, [internVoiceId, voiceNameById]);

  const baseIntentHide = {
    flubber: false,
    intern: !(capabilities.has_elevenlabs || capabilities.has_google_tts),
    sfx: !capabilities.has_any_sfx_triggers,
  };

  const effectiveIntentHide = intentDetectionReady
    ? {
        flubber: baseIntentHide.flubber || intentDetectionCounts.flubber === 0,
        intern: baseIntentHide.intern || intentDetectionCounts.intern === 0,
        sfx: baseIntentHide.sfx || intentDetectionCounts.sfx === 0,
      }
    : baseIntentHide;

  const formatDuration = (seconds) => {
    if (!seconds || !isFinite(seconds) || seconds <= 0) return null;
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    const parts = [];
    if (mins > 0) parts.push(`${mins} min${mins === 1 ? '' : 's'}`);
    parts.push(`${secs} sec${secs === 1 ? '' : 's'}`);
    return parts.join(' ');
  };

  const minutesBlockingMessage = minutesPrecheck?.detail?.message
    || (minutesBlocking ? 'Not enough processing minutes remain to create this episode.' : '');

  const minutesDialogDuration = minutesDialog?.durationSeconds != null
    ? formatDuration(minutesDialog.durationSeconds)
    : (minutesDialog?.requiredMinutes ? formatDuration(minutesDialog.requiredMinutes * 60) : null);
  const minutesDialogRemaining = typeof minutesDialog?.remainingMinutes === 'number'
    ? formatDuration(Math.max(0, minutesDialog.remainingMinutes) * 60)
    : null;
  const minutesDialogRenewal = minutesDialog?.renewalDate
    ? (() => {
        try {
          return formatInTimezone(minutesDialog.renewalDate, { month: 'long', day: 'numeric', year: 'numeric' }, resolvedTimezone);
        } catch {
          return minutesDialog.renewalDate;
        }
      })()
    : null;

  const closeMinutesDialog = () => setMinutesDialog(null);
  
  // Wrap onBack with confirmation if user has made progress past step 3
  const handleBackToDashboard = () => {
    // Check if user has progressed past step 3 (after uploading/selecting audio)
    // AND has entered any metadata (title, description, tags)
    const hasMetadata = !!(
      episodeDetails?.title?.trim() ||
      episodeDetails?.description?.trim() ||
      episodeDetails?.tags?.trim()
    );
    
    if (currentStep > 3 && hasMetadata) {
      const confirmed = window.confirm(
        'Your episode details will be saved and restored if you return to edit this audio file. Continue to dashboard?'
      );
      if (!confirmed) return;
    }
    
    // Call original onBack
    if (typeof onBack === 'function') {
      onBack();
    }
  };
  const goToUpgrade = () => {
    try { localStorage.setItem('ppp_billing_intent', 'upgrade'); } catch {}
    window.dispatchEvent(new Event('ppp:navigate-billing'));
    closeMinutesDialog();
  };
  const goToBuyMinutes = () => {
    try { localStorage.setItem('ppp_billing_intent', 'purchase-minutes'); } catch {}
    window.dispatchEvent(new Event('ppp:navigate-billing'));
    closeMinutesDialog();
  };

  const stepContent = (() => {
    switch (currentStep) {
      case 1:
        return (
          <StepTemplateSelection
            templates={templates}
            onTemplateSelect={handleTemplateSelect}
          />
        );
      case 2:
        if (creatorMode === 'preuploaded') {
          return (
            <StepSelectPreprocessed
              items={preuploadedItems}
              loading={preuploadedLoading}
              selectedFilename={selectedPreupload || uploadedFilename}
              onSelect={handlePreuploadedSelect}
              onBack={() => setCurrentStep(1)}
              onNext={() => setCurrentStep(3)}
              onRefresh={onRefreshPreuploaded}
              onUpload={onRequestUpload}
              intents={intents}
              pendingIntentLabels={pendingIntentLabels}
              onIntentSubmit={handleIntentSubmit}
              onEditAutomations={() => setShowIntentQuestions(true)}
              onDeleteItem={handleDeletePreuploaded}
              minutesPrecheck={minutesPrecheck}
              minutesPrecheckPending={minutesPrecheckPending}
              minutesPrecheckError={minutesPrecheckError}
              minutesBlocking={minutesBlocking}
              minutesBlockingMessage={minutesBlockingMessage}
              minutesRequired={minutesRequiredPrecheck}
              minutesRemaining={minutesRemainingPrecheck}
              formatDuration={formatDuration}
              audioDurationSec={audioDurationSec}
              userTimezone={resolvedTimezone}
            />
          );
        }
        return (
          <StepUploadAudio
            mainSegments={mainSegments}
            uploadedFilename={uploadedFilename}
            isUploading={isUploading}
            isBundling={isBundling}
            bundleError={bundleError}
            segmentsDirty={segmentsDirty}
            uploadProgress={uploadProgress}
            uploadStats={uploadStats}
            onFileChange={(file, overrides) => handleFileChange(file, { processingMode: useAdvancedAudio ? 'advanced' : 'standard', ...(overrides || {}) })}
            onSegmentRemove={removeSegment}
            onSegmentProcessingChange={updateSegmentProcessingMode}
            composeSegments={composeSegments}
            fileInputRef={fileInputRef}
            onBack={() => setCurrentStep(1)}
            onNext={() => setCurrentStep(3)}
            onEditAutomations={() => setShowIntentQuestions(true)}
            onIntentChange={handleIntentAnswerChange}
            onIntentSubmit={handleIntentSubmit}
            pendingIntentLabels={pendingIntentLabels}
            intents={intents}
            intentVisibility={intentVisibility}
            minutesPrecheck={minutesPrecheck}
            minutesPrecheckPending={minutesPrecheckPending}
            minutesPrecheckError={minutesPrecheckError}
            minutesBlocking={minutesBlocking}
            minutesBlockingMessage={minutesBlockingMessage}
            minutesRequired={minutesRequiredPrecheck}
            minutesRemaining={minutesRemainingPrecheck}
            formatDuration={formatDuration}
            audioDurationSec={audioDurationSec}
            episodeStatus={assembledEpisode?.status}
            wasRecorded={wasRecordedFromHook}
            useAdvancedAudio={useAdvancedAudio}
            onAdvancedAudioToggle={handleAdvancedAudioToggle}
            isAdvancedAudioSaving={isSavingAdvancedAudio}
          />
        );
      case 3:
        return (
          <StepCustomizeSegments
            selectedTemplate={selectedTemplate}
            mediaLibrary={mediaLibrary}
            mainSegments={mainSegments}
            segmentsDirty={segmentsDirty}
            isBundlingSegments={isBundling}
            bundleError={bundleError}
            uploadedAudioLabel={uploadedAudioLabel}
            ttsValues={ttsValues}
            onTtsChange={handleTtsChange}
            onBack={() => setCurrentStep(2)}
            onNext={() => setCurrentStep(4)}
            onReorderSegments={reorderSegments}
            onComposeSegments={composeSegments}
            onOpenVoicePicker={(segmentId) => {
              setVoicePickerTargetId(segmentId);
              setShowVoicePicker(true);
            }}
            voiceNameById={voiceNameById}
            voicesLoading={voicesLoading}
          />
        );
      case 4:
        return (
          <StepCoverArt
            episodeDetails={episodeDetails}
            coverArtInputRef={coverArtInputRef}
            coverCropperRef={coverCropperRef}
            coverNeedsUpload={coverNeedsUpload}
            isUploadingCover={isUploadingCover}
            onCoverFileSelected={handleCoverFileSelected}
            onCoverCropChange={updateCoverCrop}
            onCoverModeChange={setCoverMode}
            onRemoveCover={clearCover}
            onBack={() => setCurrentStep(3)}
            onSkip={() => setCurrentStep(5)}
            onContinue={async () => {
              try {
                if (episodeDetails.coverArt && coverNeedsUpload) {
                  await handleUploadProcessedCover();
                }
              } catch (e) {
                // Error toast is handled inside handleUploadProcessedCover; proceed anyway
              } finally {
                setCurrentStep(5);
              }
            }}
          />
        );
      case 5:
        return (
          <StepEpisodeDetails
            episodeDetails={episodeDetails}
            transcriptReady={transcriptReady}
            isAssembling={isAssembling}
            isPublishing={isPublishing}
            isAiTitleBusy={isAiTitleBusy}
            isAiDescBusy={isAiDescBusy}
            publishMode={publishMode}
            publishVisibility={publishVisibility}
            scheduleDate={scheduleDate}
            scheduleTime={scheduleTime}
            canProceed={canProceedToStep5}
            blockingQuota={blockingQuota}
            missingTitle={missingTitle}
            missingEpisodeNumber={missingEpisodeNumber}
            onBack={() => setCurrentStep(4)}
            onAssemble={handleAssemble}
            onDetailsChange={handleDetailsChange}
            onSuggestTitle={handleAISuggestTitle}
            onRefineTitle={handleAIRefineTitle}
            onSuggestDescription={handleAISuggestDescription}
            onRefineDescription={handleAIRefineDescription}
            onPublishModeChange={setPublishMode}
            onPublishVisibilityChange={setPublishVisibility}
            onScheduleDateChange={setScheduleDate}
            onScheduleTimeChange={setScheduleTime}
            minutesPrecheck={minutesPrecheck}
            minutesPrecheckPending={minutesPrecheckPending}
            minutesPrecheckError={minutesPrecheckError}
            minutesBlocking={minutesBlocking}
            minutesBlockingMessage={minutesBlockingMessage}
            minutesRequired={minutesRequiredPrecheck}
            minutesRemaining={minutesRemainingPrecheck}
            formatDuration={formatDuration}
            audioDurationSec={audioDurationSec}
            onRetryPrecheck={retryMinutesPrecheck}
            aiGeneratedFields={controller.aiGeneratedFields}
          />
        );
      case 6:
        return (
          <StepAssemble
            assemblyComplete={assemblyComplete}
            processingEstimate={processingEstimate}
            publishMode={publishMode}
            assembledEpisode={assembledEpisode || {}}
            statusMessage={statusMessage}
            onBack={onBack}
            onCancel={() => {
              if (handleCancelAssembly) {
                handleCancelAssembly();
                setCurrentStep(5); // Go back to Episode Details step
              }
            }}
            onViewHistory={onViewHistory}
          />
        );
      default:
        return <div>Invalid Step</div>;
    }
  })();

  return (
    <>
      <PodcastCreatorScaffold
        onBack={handleBackToDashboard}
        selectedTemplate={selectedTemplate}
        steps={steps}
        currentStep={currentStep}
        progressPercentage={progressPercentage}
        isUploading={isUploading}
        uploadProgress={uploadProgress}
        usage={usage}
        minutesNearCap={minutesNearCap}
        buildActive={buildActive}
        minutesRemaining={minutesRemaining}
        onCancelBuild={cancelBuild}
      >
        {stepContent}
      </PodcastCreatorScaffold>

      <FlubberScanOverlay
        open={showFlubberScan}
        onSkip={() => {
          setShowFlubberScan(false);
          setCurrentStep(3);
        }}
      />

      {showFlubberReview && (
        <FlubberCommandReviewText
          contexts={flubberContexts || []}
          open={showFlubberReview}
          onConfirm={handleFlubberConfirm}
          onCancel={handleFlubberCancel}
        />
      )}

      {showInternReview && (
        <InternCommandReviewText
          open={showInternReview}
          contexts={internReviewContexts || []}
          onComplete={handleInternComplete}
          onCancel={handleInternCancel}
          onProcess={processInternCommand}
          voiceName={internVoiceName}
          initialResults={internResponses}
        />
      )}

      {showIntentQuestions && (
        <IntentQuestions
          open={showIntentQuestions}
          onSubmit={handleIntentSubmit}
          onCancel={() => {
            setShowIntentQuestions(false);
            setCurrentStep(3);
          }}
          initialAnswers={intents}
          hide={effectiveIntentHide}
          detectedIntents={intentDetections}
        />
      )}

      <FlubberRetryModal
        open={flubberNotFound}
        fuzzyThreshold={fuzzyThreshold}
        onThresholdChange={setFuzzyThreshold}
        onRetry={retryFlubberSearch}
        onSkip={skipFlubberRetry}
      />

      <CreditPurchaseModal
        open={controller.showCreditPurchase || false}
        onOpenChange={(open) => {
          if (controller.setShowCreditPurchase) {
            controller.setShowCreditPurchase(open);
          }
        }}
        token={token}
        planKey={controller.creditPurchaseData?.planKey}
        requiredCredits={controller.creditPurchaseData?.requiredCredits}
        onSuccess={() => {
          // Refresh usage after successful purchase
          if (controller.quota?.refreshUsage) {
            controller.quota.refreshUsage();
          }
          if (controller.setShowCreditPurchase) {
            controller.setShowCreditPurchase(false);
          }
        }}
      />

      <Dialog open={!!minutesDialog} onOpenChange={(open) => { if (!open) closeMinutesDialog(); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Not enough processing minutes</DialogTitle>
            <DialogDescription>
              {minutesDialog?.message || 'This episode cannot be created because it exceeds your remaining processing minutes.'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 text-sm">
            {minutesDialogDuration && (
              <p>
                This episode is <strong>{minutesDialogDuration}</strong> long.
              </p>
            )}
            {minutesDialogRemaining && (
              <p>
                Your plan has <strong>{minutesDialogRemaining}</strong> remaining
                {minutesDialogRenewal ? ` until ${minutesDialogRenewal}` : ''}.
              </p>
            )}
            {!minutesDialogDuration && minutesDialog?.requiredMinutes && (
              <p>
                Estimated processing time: <strong>{minutesDialog.requiredMinutes} minute{minutesDialog.requiredMinutes === 1 ? '' : 's'}</strong>.
              </p>
            )}
          </div>
          <DialogFooter className="flex flex-col space-y-2 sm:flex-row sm:space-y-0 sm:space-x-2 sm:justify-end">
            <Button variant="outline" onClick={goToUpgrade} className="w-full sm:w-auto">
              Upgrade Plan
            </Button>
            <Button variant="outline" onClick={goToBuyMinutes} className="w-full sm:w-auto">
              Buy Minutes
            </Button>
            <Button variant="ghost" onClick={closeMinutesDialog} className="w-full sm:w-auto">
              Cancel
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {showVoicePicker && activeSegment && (
        <VoicePicker
          value={activeSegment?.source?.voice_id || null}
          onChange={(id) => handleVoiceChange(id)}
          onSelect={(voiceItem) => handleVoiceChange(voiceItem.voice_id, voiceItem)}
          onClose={() => {
            setShowVoicePicker(false);
            setVoicePickerTargetId(null);
          }}
          token={token}
        />
      )}
    </>
  );
}
