export function getVoiceById(voices, vid) {
  if (!vid || vid === "default") return null;
  const canon = (v) => v?.voice_id || v?.id || v?.name;
  return voices.find((v) => canon(v) === vid) || null;
}

export function toggleVoicePreview({
  voicePreviewing,
  setVoicePreviewing,
  voiceAudioRef,
  voices,
  selectedVoiceId,
}) {
  try {
    if (voicePreviewing && voiceAudioRef.current) {
      voiceAudioRef.current.pause();
      setVoicePreviewing(false);
      return;
    }
    const voice = getVoiceById(voices, selectedVoiceId);
    const url = voice?.preview_url || voice?.sample_url;
    if (!url) return;
    if (voiceAudioRef.current) {
      try {
        voiceAudioRef.current.pause();
      } catch (error) {
        console.warn("[Onboarding] Failed to pause existing voice preview", error);
      }
    }
    const audio = new Audio(url);
    voiceAudioRef.current = audio;
    setVoicePreviewing(true);
    audio.onended = () => {
      setVoicePreviewing(false);
    };
    audio.play().catch(() => setVoicePreviewing(false));
  } catch (error) {
    console.warn("[Onboarding] Voice preview failed", error);
    setVoicePreviewing(false);
  }
}
