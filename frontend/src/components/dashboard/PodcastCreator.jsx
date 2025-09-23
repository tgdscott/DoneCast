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
    handleRecurringApply,
    activeSegment,
    showVoicePicker,
    handleVoiceChange,
    setPublishMode,
    setPublishVisibility,
    setScheduleDate,
    setScheduleTime,
    setShowIntentQuestions,
  } = controller;

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
            isUploading={isUploading}
            onFileChange={handleFileChange}
            fileInputRef={fileInputRef}
            onBack={() => setCurrentStep(1)}
            onNext={() => setCurrentStep(3)}
            onEditAutomations={() => setShowIntentQuestions(true)}
            onIntentChange={handleIntentAnswerChange}
            onIntentSubmit={handleIntentSubmit}
            canProceed={!!uploadedFile && intentsComplete && !isUploading}
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
              if (episodeDetails.coverArt && coverNeedsUpload) {
                await handleUploadProcessedCover();
              }
              setCurrentStep(5);
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
        minutesRemaining={minutesRemaining}
        token={token}
        templates={templates}
        onRecurringApply={handleRecurringApply}
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
          hide={{
            flubber: false,
            intern: !(capabilities.has_elevenlabs || capabilities.has_google_tts),
            sfx: !capabilities.has_any_sfx_triggers,
          }}
        />
      )}

      <FlubberRetryModal
        open={flubberNotFound}
        fuzzyThreshold={fuzzyThreshold}
        onThresholdChange={setFuzzyThreshold}
        onRetry={retryFlubberSearch}
        onSkip={skipFlubberRetry}
      />

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

