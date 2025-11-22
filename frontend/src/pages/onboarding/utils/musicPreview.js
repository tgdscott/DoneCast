export async function toggleMusicPreview({
  asset,
  audioRef,
  musicPreviewing,
  setMusicPreviewing,
  stopAfterSeconds = 20,
  token,
  makeApi,
  buildApiUrl,
}) {
  if (!asset || asset.id === "none") return;
  
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

  // Prefer preview_url from backend (already processed), fall back to API endpoint
  let url = asset.preview_url || asset.url || asset.filename;
  
  // If no URL, construct API endpoint
  if (!url && asset.id && asset.id !== "none") {
    url = `/api/music/assets/${asset.id}/preview`;
  }
  
  if (!url) {
    console.warn("[Onboarding] No preview URL available for music asset", asset);
    return;
  }

  // Build absolute URL if needed (required for Audio element)
  let resolvedUrl = url;
  if (!/^https?:\/\//i.test(resolvedUrl)) {
    if (buildApiUrl) {
      resolvedUrl = buildApiUrl(url.startsWith("/") ? url : `/${url}`);
    } else {
      // Fallback: construct URL from current origin
      resolvedUrl = `${window.location.origin}${url.startsWith("/") ? url : `/${url}`}`;
    }
  }

  try {
    if (audioRef.current) {
      try {
        audioRef.current.pause();
      } catch (error) {
        console.warn("[Onboarding] Failed to pause existing music preview", error);
      }
    }
    const audio = new Audio(resolvedUrl);
    // Set crossOrigin for CORS support when using API endpoints
    if (resolvedUrl.includes("/api/") || resolvedUrl.includes(window.location.host)) {
      audio.crossOrigin = "anonymous";
    }
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
    audio.onerror = (e) => {
      console.warn("[Onboarding] Music preview playback error", e, { url: resolvedUrl });
      setMusicPreviewing(null);
      try {
        audio.removeEventListener("timeupdate", onTick);
      } catch (_) {}
    };
    audio.play().catch((error) => {
      console.warn("[Onboarding] Music preview play failed", error, { url: resolvedUrl });
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
