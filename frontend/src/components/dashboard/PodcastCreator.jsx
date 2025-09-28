import React from 'react';
import usePodcastCreator from './hooks/usePodcastCreator';
import StepTemplateSelection from './podcastCreatorSteps/StepTemplateSelection';
import StepUploadAudio from './podcastCreatorSteps/StepUploadAudio';
import StepCustomizeSegments from './podcastCreatorSteps/StepCustomizeSegments';
import StepCoverArt from './podcastCreatorSteps/StepCoverArt';
import StepEpisodeDetails from './podcastCreatorSteps/StepEpisodeDetails';
import StepAssemble from './podcastCreatorSteps/StepAssemble';
import PodcastCreatorScaffold from './podcastCreator/PodcastCreatorScaffold';
import FlubberScanOverlay from './podcastCreator/FlubberScanOverlay';
import FlubberRetryModal from './podcastCreator/FlubberRetryModal';
import FlubberQuickReview from './FlubberQuickReview';
import IntentQuestions from './IntentQuestions';
import VoicePicker from '@/components/VoicePicker';
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

export default function PodcastCreator({
  onBack,
  token,
  templates = [],
  podcasts,
  initialStep,
  testInject,
  preselectedMainFilename,
  preselectedTranscriptReady,
}) {
  const controller = usePodcastCreator({
    token,
    templates,
    initialStep,
    testInject,
    preselectedMainFilename,
    preselectedTranscriptReady,
  });

  const {
    currentStep,
    setCurrentStep,
    steps,
    progressPercentage,
    selectedTemplate,
    handleTemplateSelect,
    uploadedFile,
    uploadedFilename,
    isUploading,
    handleFileChange,
    fileInputRef,
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
    handleAISuggestDescription,
    handleAssemble,
    assemblyComplete,
    processingEstimate,
    assembledEpisode,
    statusMessage,
    showFlubberScan,
    setShowFlubberScan,
    showFlubberReview,
    flubberContexts,
    handleFlubberConfirm,
    handleFlubberCancel,
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
    minutesDialog,
    setMinutesDialog,
    activeSegment,
    showVoicePicker,
    handleVoiceChange,
    setPublishMode,
    setPublishVisibility,
    setScheduleDate,
    setScheduleTime,
    setShowIntentQuestions,
    cancelBuild,
    buildActive,
  } = controller;

  const intentDetectionCounts = {
    flubber: Number((intentDetections?.flubber?.count) ?? 0),
    intern: Number((intentDetections?.intern?.count) ?? 0),
    sfx: Number((intentDetections?.sfx?.count) ?? 0),
  };

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

  const minutesDialogDuration = minutesDialog?.durationSeconds != null
    ? formatDuration(minutesDialog.durationSeconds)
    : (minutesDialog?.requiredMinutes ? formatDuration(minutesDialog.requiredMinutes * 60) : null);
  const minutesDialogRemaining = typeof minutesDialog?.remainingMinutes === 'number'
    ? formatDuration(Math.max(0, minutesDialog.remainingMinutes) * 60)
    : null;
  const minutesDialogRenewal = minutesDialog?.renewalDate
    ? (() => {
        try {
          return new Date(minutesDialog.renewalDate).toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' });
        } catch {
          return minutesDialog.renewalDate;
        }
      })()
    : null;

  const closeMinutesDialog = () => setMinutesDialog(null);
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
        return (
          <StepUploadAudio
            uploadedFile={uploadedFile}
            uploadedFilename={uploadedFilename}
            isUploading={isUploading}
            onFileChange={handleFileChange}
            fileInputRef={fileInputRef}
            onBack={() => setCurrentStep(1)}
            onNext={() => setCurrentStep(3)}
            onEditAutomations={() => setShowIntentQuestions(true)}
            onIntentChange={handleIntentAnswerChange}
            onIntentSubmit={handleIntentSubmit}
            canProceed={!!(uploadedFile || uploadedFilename) && intentsComplete && !isUploading}
            pendingIntentLabels={pendingIntentLabels}
            intents={intents}
            intentVisibility={intentVisibility}
          />
        );
      case 3:
        return (
          <StepCustomizeSegments
            selectedTemplate={selectedTemplate}
            mediaLibrary={mediaLibrary}
            uploadedFile={uploadedFile}
            ttsValues={ttsValues}
            onTtsChange={handleTtsChange}
            onBack={() => setCurrentStep(2)}
            onNext={() => setCurrentStep(4)}
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
            onSuggestDescription={handleAISuggestDescription}
            onPublishModeChange={setPublishMode}
            onPublishVisibilityChange={setPublishVisibility}
            onScheduleDateChange={setScheduleDate}
            onScheduleTimeChange={setScheduleTime}
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
          />
        );
      default:
        return <div>Invalid Step</div>;
    }
  })();

  return (
    <>
      <PodcastCreatorScaffold
        onBack={onBack}
        selectedTemplate={selectedTemplate}
        steps={steps}
        currentStep={currentStep}
        progressPercentage={progressPercentage}
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
        <FlubberQuickReview
          contexts={flubberContexts || []}
          open={showFlubberReview}
          onConfirm={handleFlubberConfirm}
          onCancel={handleFlubberCancel}
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

      <Dialog open={!!minutesDialog} onOpenChange={(open) => { if (!open) closeMinutesDialog(); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Not enough processing minutes</DialogTitle>
            <DialogDescription>
              {minutesDialog?.message || 'This episode cannot be assembled because it exceeds your remaining processing minutes.'}
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
          onClose={() => {
            setShowVoicePicker(false);
            setVoicePickerTargetId(null);
          }}
        />
      )}
    </>
  );
}

