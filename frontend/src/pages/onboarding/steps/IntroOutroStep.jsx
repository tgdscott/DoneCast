import React from "react";
import { Play, Pause, Mic, Upload, Square } from "lucide-react";
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
    setSelectedVoiceId,
    introVoiceId,
    setIntroVoiceId,
    outroVoiceId,
    setOutroVoiceId,
    previewSelectedVoice,
    canPreviewSelectedVoice,
    voicePreviewing,
  } = wizard;

  const [showIntroVoicePicker, setShowIntroVoicePicker] = React.useState(false);
  const [showOutroVoicePicker, setShowOutroVoicePicker] = React.useState(false);
  const [introVoiceName, setIntroVoiceName] = React.useState(null);
  const [outroVoiceName, setOutroVoiceName] = React.useState(null);
  const [introPlaying, setIntroPlaying] = React.useState(false);
  const [outroPlaying, setOutroPlaying] = React.useState(false);
  const introAudioRef = React.useRef(null);
  const outroAudioRef = React.useRef(null);

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
      <p className="text-sm text-muted-foreground">
        We've pre-filled default scripts below. You can use these as-is or customize them.
      </p>

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

      <p className="text-xs text-muted-foreground">
        We'll create simple defaults if you leave the scripts unchanged.
      </p>
    </div>
  );
}
