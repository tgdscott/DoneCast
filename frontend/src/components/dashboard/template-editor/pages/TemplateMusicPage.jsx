import MusicTimingSection from "../MusicTimingSection";
import TemplatePageWrapper from "../layout/TemplatePageWrapper";

const TemplateMusicPage = ({
  template,
  onTimingChange,
  backgroundMusicRules,
  onBackgroundMusicChange,
  onAddBackgroundMusicRule,
  onRemoveBackgroundMusicRule,
  musicFiles,
  onStartMusicUpload,
  musicUploadIndex,
  isUploadingMusic,
  musicUploadInputRef,
  onMusicFileSelected,
  onSetMusicVolumeLevel,
  voiceName,
  onChooseVoice,
  internVoiceDisplay,
  onChooseInternVoice,
  globalMusicAssets,
  onNext,
  onBack,
}) => {
  return (
    <TemplatePageWrapper
      title="Music & Timing"
      description="Fine-tune segment overlaps, add background music, and control fades (optional)"
      onNext={onNext}
      onBack={onBack}
      hasNext={true}
      hasPrevious={true}
    >
      <MusicTimingSection
        isOpen={true} // Always open on this page
        onToggle={() => {}} // No toggle on dedicated page
        template={template}
        onTimingChange={onTimingChange}
        backgroundMusicRules={backgroundMusicRules}
        onBackgroundMusicChange={onBackgroundMusicChange}
        onAddBackgroundMusicRule={onAddBackgroundMusicRule}
        onRemoveBackgroundMusicRule={onRemoveBackgroundMusicRule}
        musicFiles={musicFiles}
        onStartMusicUpload={onStartMusicUpload}
        musicUploadIndex={musicUploadIndex}
        isUploadingMusic={isUploadingMusic}
        musicUploadInputRef={musicUploadInputRef}
        onMusicFileSelected={onMusicFileSelected}
        onSetMusicVolumeLevel={onSetMusicVolumeLevel}
        voiceName={voiceName}
        onChooseVoice={onChooseVoice}
        internVoiceDisplay={internVoiceDisplay}
        onChooseInternVoice={onChooseInternVoice}
        globalMusicAssets={globalMusicAssets}
      />
    </TemplatePageWrapper>
  );
};

export default TemplateMusicPage;
