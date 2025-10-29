export async function toggleIntroOutroPreview({
  kind,
  asset,
  token,
  makeApi,
  buildApiUrl,
  ioAudioRef,
  isIntroPreviewing,
  isOutroPreviewing,
  setIntroPreviewing,
  setOutroPreviewing,
  toast,
}) {
  if (!asset) return;

  const resolvePreviewUrl = async () => {
    if (!asset?.id) {
      console.error("[Onboarding] Cannot resolve preview URL - asset has no ID", asset);
      return null;
    }
    try {
      const api = makeApi(token);
      const response = await api.get(
        `/api/media/preview?id=${encodeURIComponent(asset.id)}&resolve=true`
      );
      const url = response?.path || response?.url;
      if (!url) {
        console.error("[Onboarding] Preview endpoint returned no URL", {
          id: asset.id,
          response,
        });
      }
      return url || null;
    } catch (error) {
      console.error("[Onboarding] Failed to resolve preview URL", {
        id: asset.id,
        error,
      });
      toast?.({
        variant: "destructive",
        title: "Preview failed",
        description: error?.message || "Could not resolve preview URL",
      });
      return null;
    }
  };

  const url = await resolvePreviewUrl();
  if (!url) {
    toast?.({
      title: "No audio",
      description: "Could not determine preview URL",
      variant: "destructive",
    });
    return;
  }

  let resolvedUrl = url;
  if (!/^https?:\/\//i.test(resolvedUrl)) {
    resolvedUrl = buildApiUrl(resolvedUrl.startsWith("/") ? resolvedUrl : `/${resolvedUrl}`);
  }

  const isIntro = kind === "intro";
  const isOutro = kind === "outro";
  const alreadyPlaying = (isIntro && isIntroPreviewing) || (isOutro && isOutroPreviewing);

  if (alreadyPlaying && ioAudioRef.current) {
    try {
      ioAudioRef.current.pause();
    } catch (_) {}
    ioAudioRef.current = null;
    setIntroPreviewing(false);
    setOutroPreviewing(false);
    return;
  }

  if (ioAudioRef.current) {
    try {
      ioAudioRef.current.pause();
    } catch (_) {}
  }

  const audio = new Audio(resolvedUrl);
  try {
    const apiBase = buildApiUrl("/")
      .replace(/\/+$/g, "")
      .replace(/^https?:\/\//, "");
    const apiHost = apiBase.includes("//") ? new URL(apiBase).host : apiBase;
    const mediaHost = new URL(resolvedUrl, window.location.origin).host;
    if (apiHost && mediaHost && apiHost === mediaHost) {
      audio.crossOrigin = "anonymous";
    }
  } catch (_) {}

  ioAudioRef.current = audio;
  setIntroPreviewing(isIntro);
  setOutroPreviewing(isOutro);

  audio.onended = () => {
    setIntroPreviewing(false);
    setOutroPreviewing(false);
  };
  audio.onerror = () => {
    setIntroPreviewing(false);
    setOutroPreviewing(false);
    toast?.({
      title: "Playback failed",
      description: "Could not play audio preview",
      variant: "destructive",
    });
  };

  audio
    .play()
    .catch((error) => {
      setIntroPreviewing(false);
      setOutroPreviewing(false);
      toast?.({
        title: "Playback blocked",
        description: error?.message || "User gesture or CORS issue",
        variant: "destructive",
      });
    });
}
