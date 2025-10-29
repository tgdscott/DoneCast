export function toggleMusicPreview({
  asset,
  audioRef,
  musicPreviewing,
  setMusicPreviewing,
  stopAfterSeconds = 20,
}) {
  if (!asset || asset.id === "none") return;
  const url = asset.preview_url || asset.url || asset.filename;
  if (!url) return;
  if (musicPreviewing === asset.id) {
    try {
      audioRef.current?.pause();
    } catch (error) {
      console.warn("[Onboarding] Failed to pause current music preview", error);
    }
    audioRef.current = null;
    setMusicPreviewing(null);
    return;
  }
  try {
    if (audioRef.current) {
      try {
        audioRef.current.pause();
      } catch (error) {
        console.warn("[Onboarding] Failed to pause existing music preview", error);
      }
    }
    const audio = new Audio(url);
    audioRef.current = audio;
    setMusicPreviewing(asset.id);
    const onTick = () => {
      if (!audio || Number.isNaN(audio.currentTime)) return;
      if (audio.currentTime >= stopAfterSeconds) {
        audio.pause();
        setMusicPreviewing(null);
        audio.removeEventListener("timeupdate", onTick);
      }
    };
    audio.addEventListener("timeupdate", onTick);
    audio.onended = () => {
      setMusicPreviewing(null);
      try {
        audio.removeEventListener("timeupdate", onTick);
      } catch (_) {}
    };
    audio.play().catch(() => {
      setMusicPreviewing(null);
      try {
        audio.removeEventListener("timeupdate", onTick);
      } catch (_) {}
    });
  } catch (error) {
    console.warn("[Onboarding] Music preview failed", error);
    setMusicPreviewing(null);
  }
}
