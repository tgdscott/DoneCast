import React from "react";
import { Play, Mic, Square, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import VoiceRecorder from "@/components/onboarding/VoiceRecorder.jsx";
import VoicePicker from "@/components/VoicePicker.jsx";
import { formatMediaDisplayName } from "../utils/mediaDisplay.js";
import { makeApi } from "@/lib/apiClient";

export default function IntroOutroStep({ wizard }) {
  const {
    introMode,
    setIntroMode,
    introOptions,
    setIntroOptions,
    selectedIntroId,
    setSelectedIntroId,
    introAsset,
    setIntroAsset,
    introPreviewing,
    toggleIntroPreview,
    introScript,
    setIntroScript,
    introFile,
    setIntroFile,
    outroMode,
    setOutroMode,
    outroOptions,
    setOutroOptions,
    selectedOutroId,
    setSelectedOutroId,
    outroAsset,
    setOutroAsset,
    outroPreviewing,
    toggleOutroPreview,
    outroScript,
    setOutroScript,
    outroFile,
    setOutroFile,
    token,
    largeText,
    firstName,
    refreshUser,
    toast,
    voices,
    voicesLoading,
    voicesError,
    selectedVoiceId,
    formData,
    setSelectedVoiceId,
    introVoiceId,
    setIntroVoiceId,
    outroVoiceId,
    setOutroVoiceId,
    previewSelectedVoice,
    canPreviewSelectedVoice,
    voicePreviewing,
    generateOrUploadTTS,
  } = wizard;

  const [showIntroVoicePicker, setShowIntroVoicePicker] = React.useState(false);
  const [showOutroVoicePicker, setShowOutroVoicePicker] = React.useState(false);
  const [introVoiceName, setIntroVoiceName] = React.useState(null);
  const [outroVoiceName, setOutroVoiceName] = React.useState(null);
  const [introPlaying, setIntroPlaying] = React.useState(false);
  const [outroPlaying, setOutroPlaying] = React.useState(false);
  const introAudioRef = React.useRef(null);
  const outroAudioRef = React.useRef(null);
  const [aiAssistBusy, setAiAssistBusy] = React.useState(false);

  const showName = React.useMemo(() => {
    const trimmed = (formData?.podcastName || "").trim();
    return trimmed || "your show";
  }, [formData?.podcastName]);

  const hostNameDisplay = React.useMemo(() => (firstName || "").trim(), [firstName]);

  const descriptionSnippet = React.useMemo(() => {
    const raw = (formData?.podcastDescription || "").trim();
    if (!raw) return "";
    const match = raw.match(/[^.!?]+[.!?]?/);
    const sentence = (match ? match[0] : raw).trim();
    if (sentence.length > 180) {
      return `${sentence.slice(0, 177)}...`;
    }
    return sentence;
  }, [formData?.podcastDescription]);

  const introSuggestion = React.useMemo(() => {
    let copy;
    if (descriptionSnippet) {
      const withPeriod = descriptionSnippet.endsWith(".") ? descriptionSnippet : `${descriptionSnippet}.`;
      const hostPart = hostNameDisplay ? `I'm ${hostNameDisplay}, ` : "";
      copy = `Welcome to ${showName}. ${withPeriod} ${hostPart}and I'm glad you're here. Let's jump in.`;
    } else {
      const hostPart = hostNameDisplay ? `I'm ${hostNameDisplay}, ` : "";
      copy = `Welcome to ${showName}. ${hostPart}let's jump in.`;
    }
    return copy.replace(/\s{2,}/g, " ").trim();
  }, [descriptionSnippet, showName, hostNameDisplay]);

  const outroSuggestion = React.useMemo(() => {
    const hostPart = hostNameDisplay ? `I'm ${hostNameDisplay}, ` : "";
    const copy = `Thanks for listening to ${showName}. ${hostPart}follow or share the show so more listeners can find it. I'll see you next time.`;
    return copy.replace(/\s{2,}/g, " ").trim();
  }, [showName, hostNameDisplay]);

  const introVoiceLabel = introVoiceName || (introVoiceId && introVoiceId !== "default" ? "Custom ElevenLabs voice" : "Default AI voice");
  const outroVoiceLabel = outroVoiceName || (outroVoiceId && outroVoiceId !== "default" ? "Custom ElevenLabs voice" : "Default AI voice");

  const registerGeneratedAsset = React.useCallback(
    (kind, asset) => {
      if (!asset) return;
      const key = String(asset.id || asset.filename || "");
      if (!key) return;
      if (kind === "intro") {
        setIntroAsset(asset);
        setIntroMode("existing");
        setSelectedIntroId(key);
        setIntroOptions((previous) => {
          const exists = previous.some((item) => String(item.id || item.filename) === key);
          return exists ? previous : [asset, ...previous];
        });
      } else {
        setOutroAsset(asset);
        setOutroMode("existing");
        setSelectedOutroId(key);
        setOutroOptions((previous) => {
          const exists = previous.some((item) => String(item.id || item.filename) === key);
          return exists ? previous : [asset, ...previous];
        });
      }
    },
    [
      setIntroAsset,
      setIntroMode,
      setSelectedIntroId,
      setIntroOptions,
      setOutroAsset,
      setOutroMode,
      setSelectedOutroId,
      setOutroOptions,
    ]
  );

  const handleApplySuggestions = React.useCallback(() => {
    setIntroScript(introSuggestion);
    setOutroScript(outroSuggestion);
    try {
      toast?.({
        title: "Scripts ready",
        description: "Feel free to tweak the text before generating audio.",
      });
    } catch (_) { }
  }, [introSuggestion, outroSuggestion, setIntroScript, setOutroScript, toast]);

  const handleGenerateWithAI = React.useCallback(async () => {
    setAiAssistBusy(true);
    try {
      setIntroScript(introSuggestion);
      setOutroScript(outroSuggestion);
      const introResult = await generateOrUploadTTS("intro", "tts", introSuggestion, null, null);
      const outroResult = await generateOrUploadTTS("outro", "tts", outroSuggestion, null, null);
      let createdAny = false;
      if (introResult) {
        registerGeneratedAsset("intro", introResult);
        createdAny = true;
      }
      if (outroResult) {
        registerGeneratedAsset("outro", outroResult);
        createdAny = true;
      }
      if (createdAny) {
        toast?.({
          title: "Intro & outro ready",
          description: "Preview the new AI voice lines below.",
        });
      }
    } finally {
      setAiAssistBusy(false);
    }
  }, [
    generateOrUploadTTS,
    introSuggestion,
    outroSuggestion,
    registerGeneratedAsset,
    toast,
    setIntroScript,
    setOutroScript,
  ]);

  // Resolve intro voice name when introVoiceId changes
  React.useEffect(() => {
    if (!introVoiceId || introVoiceId === 'default') {
      setIntroVoiceName(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const api = makeApi(token);
        const v = await api.get(`/api/elevenlabs/voice/${encodeURIComponent(introVoiceId)}/resolve`);
        const dn = v?.common_name || v?.name || null;
        if (!cancelled) setIntroVoiceName(dn);
      } catch (_) { /* ignore */ }
    })();
    return () => { cancelled = true; };
  }, [introVoiceId, token]);

  // Resolve outro voice name when outroVoiceId changes
  React.useEffect(() => {
    if (!outroVoiceId || outroVoiceId === 'default') {
      setOutroVoiceName(null);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const api = makeApi(token);
        const v = await api.get(`/api/elevenlabs/voice/${encodeURIComponent(outroVoiceId)}/resolve`);
        const dn = v?.common_name || v?.name || null;
        if (!cancelled) setOutroVoiceName(dn);
      } catch (_) { /* ignore */ }
    })();
    return () => { cancelled = true; };
  }, [outroVoiceId, token]);

  const handleIntroPlayPause = () => {
    if (!introAsset) return;
    const audioUrl = `/api/media/preview?id=${introAsset.id || introAsset.filename}`;
    if (introPlaying && introAudioRef.current) {
      introAudioRef.current.pause();
      introAudioRef.current = null;
      setIntroPlaying(false);
    } else {
      if (introAudioRef.current) introAudioRef.current.pause();
      const audio = new Audio(audioUrl);
      audio.addEventListener('ended', () => {
        setIntroPlaying(false);
        introAudioRef.current = null;
      });
      audio.play();
      introAudioRef.current = audio;
      setIntroPlaying(true);
    }
  };

  const handleOutroPlayPause = () => {
    if (!outroAsset) return;
    const audioUrl = `/api/media/preview?id=${outroAsset.id || outroAsset.filename}`;
    if (outroPlaying && outroAudioRef.current) {
      outroAudioRef.current.pause();
      outroAudioRef.current = null;
      setOutroPlaying(false);
    } else {
      if (outroAudioRef.current) outroAudioRef.current.pause();
      const audio = new Audio(audioUrl);
      audio.addEventListener('ended', () => {
        setOutroPlaying(false);
        outroAudioRef.current = null;
      });
      audio.play();
      outroAudioRef.current = audio;
      setOutroPlaying(true);
    }
  };

  return (
    <div className="space-y-6">
      <Card className="border-primary/20 bg-muted/40 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="h-4 w-4 text-primary" />
            Let DoneCast draft it for you
          </CardTitle>
          <p className="text-sm text-muted-foreground">
            We use your show name, description, and selected voices to propose short intros and outros.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Suggested intro
              </Label>
              <Textarea
                value={introSuggestion}
                readOnly
                className="mt-1 min-h-[90px] resize-none bg-background/70"
              />
            </div>
            <div>
              <Label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Suggested outro
              </Label>
              <Textarea
                value={outroSuggestion}
                readOnly
                className="mt-1 min-h-[90px] resize-none bg-background/70"
              />
            </div>
          </div>
          <div className="flex flex-col gap-4 pt-1 md:flex-row md:items-center md:gap-6">
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={handleApplySuggestions}>
                Use these scripts
              </Button>
              <Button size="sm" onClick={handleGenerateWithAI} disabled={aiAssistBusy}>
                {aiAssistBusy ? "Generating..." : "Generate intro & outro audio"}
              </Button>
            </div>
            <div className="flex flex-col gap-2 text-xs text-muted-foreground md:flex-row md:items-center md:gap-4">
              <div className="flex items-center gap-1">
                <span className="font-semibold text-foreground">Intro voice:</span>
                <span>{introVoiceLabel}</span>
                <Button
                  variant="link"
                  size="sm"
                  className="h-auto px-1"
                  onClick={() => setShowIntroVoicePicker(true)}
                >
                  Change
                </Button>
              </div>
              <div className="flex items-center gap-1">
                <span className="font-semibold text-foreground">Outro voice:</span>
                <span>{outroVoiceLabel}</span>
                <Button
                  variant="link"
                  size="sm"
                  className="h-auto px-1"
                  onClick={() => setShowOutroVoicePicker(true)}
                >
                  Change
                </Button>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Intro Card - Segmented like Template Editor */}
      <Card className="shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Intro</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label className="text-sm font-medium text-gray-600 mb-2 block">Audio Source</Label>
            <Select value={introMode} onValueChange={setIntroMode}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">No Intro</SelectItem>
                {introOptions.length > 0 && (
                  <SelectItem value="existing">Use Current Intro</SelectItem>
                )}
                <SelectItem value="record">
                  <span className="flex items-center gap-2">
                    <Mic className="h-4 w-4" />
                    Record Now
                    <span className="ml-1 px-1.5 py-0.5 bg-green-100 text-green-800 text-xs rounded font-medium">
                      Easy!
                    </span>
                  </span>
                </SelectItem>
                <SelectItem value="tts">Generate with AI Voice</SelectItem>
                <SelectItem value="upload">Upload a File</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {introMode === "existing" && (
            <div>
              <Label className="text-sm font-medium text-gray-600 mb-2 block">Audio File</Label>
              <div className="flex items-center gap-2">
                <Select
                  value={selectedIntroId || ''}
                  onValueChange={(value) => {
                    setSelectedIntroId(value);
                    const found = introOptions.find((item) => String(item.id || item.filename) === value) || null;
                    setIntroAsset(found);
                  }}
                >
                  <SelectTrigger className="flex-1">
                    <SelectValue placeholder="Select an intro file..." />
                  </SelectTrigger>
                  <SelectContent>
                    {introOptions.map((item) => {
                      const key = String(item?.id || item?.filename || "unknown");
                      const displayName = formatMediaDisplayName(item, true) || "Intro";
                      return (
                        <SelectItem key={key} value={key}>
                          {displayName}
                        </SelectItem>
                      );
                    })}
                  </SelectContent>
                </Select>
                {introAsset && (
                  <Button
                    type="button"
                    variant={introPlaying ? "default" : "outline"}
                    size="icon"
                    onClick={handleIntroPlayPause}
                    title={introPlaying ? "Stop audio" : "Preview audio"}
                  >
                    {introPlaying ? <Square className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                  </Button>
                )}
              </div>
            </div>
          )}

          {introMode === "record" && (
            <VoiceRecorder
              type="intro"
              token={token}
              maxDuration={60}
              largeText={largeText}
              userFirstName={firstName}
              refreshUser={refreshUser}
              onRecordingComplete={(mediaItem) => {
                setIntroAsset(mediaItem);
                setIntroOptions((previous) => {
                  const exists = previous.some(
                    (item) => (item.id || item.filename) === (mediaItem.id || mediaItem.filename)
                  );
                  return exists ? previous : [...previous, mediaItem];
                });
                setSelectedIntroId(String(mediaItem.id || mediaItem.filename));
                setIntroMode("existing");
                toast({
                  title: "Perfect!",
                  description: "Your intro has been recorded. Preview it below!",
                });
              }}
            />
          )}

          {introMode === "tts" && (
            <div className="space-y-3">
              <div>
                <Label className="text-sm font-medium text-gray-600 mb-2 block">Script</Label>
                <Textarea
                  value={introScript}
                  onChange={(event) => setIntroScript(event.target.value)}
                  placeholder="Write your intro script here (e.g., 'Welcome to my podcast!')"
                  rows={3}
                />
              </div>
              <div>
                <Label className="text-sm font-medium text-gray-600 mb-2 block">Voice</Label>
                <div className="flex items-center gap-3">
                  <div className="flex-1">
                    <div className="text-sm text-gray-800 border rounded-md px-3 py-2 bg-gray-50">
                      {introVoiceName || introVoiceId || 'Not set'}
                    </div>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowIntroVoicePicker(true)}
                  >
                    Choose voice
                  </Button>
                </div>
              </div>
            </div>
          )}

          {introMode === "upload" && (
            <div>
              <Label className="text-sm font-medium text-gray-600 mb-2 block">Upload Audio File</Label>
              <Input
                type="file"
                accept="audio/*"
                onChange={(event) => setIntroFile(event.target.files?.[0] || null)}
              />
            </div>
          )}

          {introMode === "none" && (
            <p className="text-sm text-muted-foreground">
              No intro will be added to your episodes.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Outro Card - Segmented like Template Editor */}
      <Card className="shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Outro</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label className="text-sm font-medium text-gray-600 mb-2 block">Audio Source</Label>
            <Select value={outroMode} onValueChange={setOutroMode}>
              <SelectTrigger className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">No Outro</SelectItem>
                {outroOptions.length > 0 && (
                  <SelectItem value="existing">Use Current Outro</SelectItem>
                )}
                <SelectItem value="record">
                  <span className="flex items-center gap-2">
                    <Mic className="h-4 w-4" />
                    Record Now
                    <span className="ml-1 px-1.5 py-0.5 bg-green-100 text-green-800 text-xs rounded font-medium">
                      Easy!
                    </span>
                  </span>
                </SelectItem>
                <SelectItem value="tts">Generate with AI Voice</SelectItem>
                <SelectItem value="upload">Upload a File</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {outroMode === "existing" && (
            <div>
              <Label className="text-sm font-medium text-gray-600 mb-2 block">Audio File</Label>
              <div className="flex items-center gap-2">
                <Select
                  value={selectedOutroId || ''}
                  onValueChange={(value) => {
                    setSelectedOutroId(value);
                    const found = outroOptions.find((item) => String(item.id || item.filename) === value) || null;
                    setOutroAsset(found);
                  }}
                >
                  <SelectTrigger className="flex-1">
                    <SelectValue placeholder="Select an outro file..." />
                  </SelectTrigger>
                  <SelectContent>
                    {outroOptions.map((item) => {
                      const key = String(item?.id || item?.filename || "unknown");
                      const displayName = formatMediaDisplayName(item, true) || "Outro";
                      return (
                        <SelectItem key={key} value={key}>
                          {displayName}
                        </SelectItem>
                      );
                    })}
                  </SelectContent>
                </Select>
                {outroAsset && (
                  <Button
                    type="button"
                    variant={outroPlaying ? "default" : "outline"}
                    size="icon"
                    onClick={handleOutroPlayPause}
                    title={outroPlaying ? "Stop audio" : "Preview audio"}
                  >
                    {outroPlaying ? <Square className="w-4 h-4" /> : <Play className="w-4 h-4" />}
                  </Button>
                )}
              </div>
            </div>
          )}

          {outroMode === "record" && (
            <VoiceRecorder
              type="outro"
              token={token}
              maxDuration={60}
              largeText={largeText}
              userFirstName={firstName}
              refreshUser={refreshUser}
              onRecordingComplete={(mediaItem) => {
                setOutroAsset(mediaItem);
                setOutroOptions((previous) => {
                  const exists = previous.some(
                    (item) => (item.id || item.filename) === (mediaItem.id || mediaItem.filename)
                  );
                  return exists ? previous : [...previous, mediaItem];
                });
                setSelectedOutroId(String(mediaItem.id || mediaItem.filename));
                setOutroMode("existing");
                toast({
                  title: "Perfect!",
                  description: "Your outro has been recorded. Preview it below!",
                });
              }}
            />
          )}

          {outroMode === "tts" && (
            <div className="space-y-3">
              <div>
                <Label className="text-sm font-medium text-gray-600 mb-2 block">Script</Label>
                <Textarea
                  value={outroScript}
                  onChange={(event) => setOutroScript(event.target.value)}
                  placeholder="Write your outro script here (e.g., 'Thank you for listening!')"
                  rows={3}
                />
              </div>
              <div>
                <Label className="text-sm font-medium text-gray-600 mb-2 block">Voice</Label>
                <div className="flex items-center gap-3">
                  <div className="flex-1">
                    <div className="text-sm text-gray-800 border rounded-md px-3 py-2 bg-gray-50">
                      {outroVoiceName || outroVoiceId || 'Not set'}
                    </div>
                  </div>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowOutroVoicePicker(true)}
                  >
                    Choose voice
                  </Button>
                </div>
              </div>
            </div>
          )}

          {outroMode === "upload" && (
            <div>
              <Label className="text-sm font-medium text-gray-600 mb-2 block">Upload Audio File</Label>
              <Input
                type="file"
                accept="audio/*"
                onChange={(event) => setOutroFile(event.target.files?.[0] || null)}
              />
            </div>
          )}

          {outroMode === "none" && (
            <p className="text-sm text-muted-foreground">
              No outro will be added to your episodes.
            </p>
          )}
        </CardContent>
      </Card>

      {/* Voice Pickers */}
      {showIntroVoicePicker && (
        <VoicePicker
          value={introVoiceId && introVoiceId !== 'default' ? introVoiceId : null}
          onChange={(id) => {
            setIntroVoiceId(id || 'default');
            setShowIntroVoicePicker(false);
          }}
          onSelect={(item) => {
            setIntroVoiceName(item?.common_name || item?.name || null);
          }}
          onClose={() => setShowIntroVoicePicker(false)}
          token={token}
        />
      )}

      {showOutroVoicePicker && (
        <VoicePicker
          value={outroVoiceId && outroVoiceId !== 'default' ? outroVoiceId : null}
          onChange={(id) => {
            setOutroVoiceId(id || 'default');
            setShowOutroVoicePicker(false);
          }}
          onSelect={(item) => {
            setOutroVoiceName(item?.common_name || item?.name || null);
          }}
          onClose={() => setShowOutroVoicePicker(false)}
          token={token}
        />
      )}
    </div>
  );
}
