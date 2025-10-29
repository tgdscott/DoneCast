import React from "react";
import { Play, Pause, Mic } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import VoiceRecorder from "@/components/onboarding/VoiceRecorder.jsx";
import { formatMediaDisplayName } from "../utils/mediaDisplay.js";

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
    previewSelectedVoice,
    canPreviewSelectedVoice,
    voicePreviewing,
  } = wizard;

  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <div className="font-medium">Intro</div>
        <div className="flex items-center gap-2">
          <Select value={introMode} onValueChange={setIntroMode}>
            <SelectTrigger className="w-[280px]">
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
          <div className="flex items-center gap-2">
            <button
              type="button"
              aria-label={introPreviewing ? "Pause preview" : "Play preview"}
              onClick={() => toggleIntroPreview("intro")}
              className={`inline-flex items-center justify-center h-8 w-8 rounded border ${
                introPreviewing
                  ? "bg-blue-600 text-white border-blue-600"
                  : "bg-white text-foreground border-muted-foreground/30"
              }`}
              title="Preview"
            >
              {introPreviewing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </button>
            <select
              className="border rounded p-2 w-full min-w-0 sm:min-w-[220px]"
              value={selectedIntroId}
              onChange={(event) => {
                const value = event.target.value;
                setSelectedIntroId(value);
                const found =
                  introOptions.find((item) => String(item.id || item.filename) === value) || null;
                setIntroAsset(found);
              }}
            >
              {introOptions.map((item) => {
                const key = String(item?.id || item?.filename || "unknown");
                const base =
                  item?.friendly_name ||
                  item?.display_name ||
                  item?.original_name ||
                  item?.filename ||
                  "Intro";
                return (
                  <option key={key} value={key}>
                    {formatMediaDisplayName(base, true)}
                  </option>
                );
              })}
            </select>
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
        {introMode === "tts" ? (
          <Textarea
            value={introScript}
            onChange={(event) => setIntroScript(event.target.value)}
            placeholder="Write your intro script here (e.g., 'Welcome to my podcast!')"
          />
        ) : introMode === "upload" ? (
          <Input
            type="file"
            accept="audio/*"
            onChange={(event) => setIntroFile(event.target.files?.[0] || null)}
          />
        ) : null}
      </div>

      <div className="space-y-2">
        <div className="font-medium">Outro</div>
        <div className="flex items-center gap-2">
          <Select value={outroMode} onValueChange={setOutroMode}>
            <SelectTrigger className="w-[280px]">
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
          <div className="flex items-center gap-2">
            <button
              type="button"
              aria-label={outroPreviewing ? "Pause preview" : "Play preview"}
              onClick={() => toggleOutroPreview("outro")}
              className={`inline-flex items-center justify-center h-8 w-8 rounded border ${
                outroPreviewing
                  ? "bg-blue-600 text-white border-blue-600"
                  : "bg-white text-foreground border-muted-foreground/30"
              }`}
              title="Preview"
            >
              {outroPreviewing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
            </button>
            <select
              className="border rounded p-2 w-full min-w-0 sm:min-w-[220px]"
              value={selectedOutroId}
              onChange={(event) => {
                const value = event.target.value;
                setSelectedOutroId(value);
                const found =
                  outroOptions.find((item) => String(item.id || item.filename) === value) || null;
                setOutroAsset(found);
              }}
            >
              {outroOptions.map((item) => {
                const key = String(item?.id || item?.filename || "unknown");
                const base =
                  item?.friendly_name ||
                  item?.display_name ||
                  item?.original_name ||
                  item?.filename ||
                  "Outro";
                return (
                  <option key={key} value={key}>
                    {formatMediaDisplayName(base, true)}
                  </option>
                );
              })}
            </select>
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
        {outroMode === "tts" ? (
          <Textarea
            value={outroScript}
            onChange={(event) => setOutroScript(event.target.value)}
            placeholder="Write your outro script here (e.g., 'Thank you for listening!')"
          />
        ) : outroMode === "upload" ? (
          <Input
            type="file"
            accept="audio/*"
            onChange={(event) => setOutroFile(event.target.files?.[0] || null)}
          />
        ) : null}
      </div>

      {(introMode === "tts" || outroMode === "tts") && (
        <div className="space-y-2">
          <div className="space-y-1">
            <Label>Voice</Label>
            <div className="flex items-center gap-2">
              <select
                className="border rounded p-2 w-full min-w-0 sm:min-w-[220px]"
                value={selectedVoiceId}
                onChange={(event) => setSelectedVoiceId(event.target.value)}
                disabled={voicesLoading || (voices?.length || 0) === 0}
              >
                <option value="default">Default</option>
                {voices.map((voice) => {
                  const id = voice.voice_id || voice.id || voice.name;
                  const label = voice.name || voice.label || id;
                  return (
                    <option key={id} value={id}>
                      {label}
                    </option>
                  );
                })}
              </select>
              <Button
                type="button"
                variant="outline"
                onClick={previewSelectedVoice}
                disabled={voicesLoading || !canPreviewSelectedVoice}
              >
                {voicePreviewing ? <Pause className="w-4 h-4 mr-2" /> : <Play className="w-4 h-4 mr-2" />}
                Preview
              </Button>
            </div>
          </div>
          {voicesLoading && <div className="text-xs text-muted-foreground">Loading voices…</div>}
          {voicesError && <div className="text-xs text-yellow-700">{voicesError}</div>}
        </div>
      )}
      <p className="text-xs text-muted-foreground">
        We’ll create simple defaults if you leave the scripts unchanged.
      </p>
    </div>
  );
}
