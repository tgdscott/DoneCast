import React, { useRef, useEffect, useState } from 'react';
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { CheckCircle, Download, Loader2, RotateCcw, X } from "lucide-react";
import { formatDateName } from '../utils/audioUtils';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";

/**
 * Recording preview with playback, naming, and save controls
 * @param {Object} props - Component props
 * @param {string} props.audioUrl - Audio blob URL
 * @param {Blob} props.audioBlob - Audio blob
 * @param {string} props.recordingName - Current recording name
 * @param {Function} props.onNameChange - Name change callback
 * @param {Function} props.onSave - Save callback
 * @param {boolean} props.isSaving - Whether save is in progress
 * @param {string} props.savedDisplayName - Display name after save
 * @param {boolean} props.transcriptReady - Whether transcript is ready
 * @param {boolean} props.showTimeoutNotice - Whether to show timeout notice
 * @param {number} props.maxUploadMb - Maximum upload size in MB
 * @param {Function} props.onFinish - Finish callback
 * @param {Function} props.onStartOver - Start over callback (discard & record again)
 * @param {Function} props.onDiscard - Discard & return to dashboard callback
 * @param {boolean} props.useAdvancedAudio - Whether advanced audio processing is enabled
 * @param {Function} props.onAdvancedAudioToggle - Toggle handler for advanced audio processing
 * @param {boolean} props.isAdvancedAudioSaving - Whether preference is being saved
 */
export const RecordingPreview = ({
  audioUrl,
  audioBlob,
  recordingName,
  onNameChange,
  onSave,
  isSaving,
  savedDisplayName,
  transcriptReady,
  showTimeoutNotice,
  maxUploadMb,
  onFinish,
  onStartOver,
  onDiscard,
  useAdvancedAudio,
  onAdvancedAudioToggle,
  isAdvancedAudioSaving,
}) => {
  const audioRef = useRef(null);

  // Pause audio when component unmounts
  useEffect(() => {
    return () => {
      try {
        if (audioRef.current) {
          audioRef.current.pause();
        }
      } catch {}
    };
  }, []);

  const isTooBig = audioBlob && audioBlob.size > (maxUploadMb * 1024 * 1024);

  return (
    <div className="space-y-6">
      {/* Audio Player */}
      <div className="space-y-2">
        <Label className="text-base font-medium">Preview Your Recording</Label>
        {audioUrl && (
          <audio
            ref={audioRef}
            src={audioUrl}
            controls
            className="w-full"
            preload="metadata"
          />
        )}
      </div>

      {/* File Size Warning */}
      {isTooBig && (
        <div className="bg-red-50 border border-red-300 rounded-lg p-4">
          <p className="text-red-800 font-medium">
            Recording is too large to upload (over {maxUploadMb} MB).
          </p>
          <p className="text-red-700 text-sm mt-1">
            Consider recording shorter segments or using a lower quality setting.
          </p>
        </div>
      )}

      {/* Naming */}
      <div className="space-y-2">
        <Label htmlFor="recording-name" className="text-base font-medium">
          Recording Name (optional)
        </Label>
        <Input
          id="recording-name"
          type="text"
          value={recordingName}
          onChange={(e) => onNameChange(e.target.value)}
          placeholder={formatDateName()}
          disabled={isSaving || !!savedDisplayName}
        />
        <p className="text-xs text-muted-foreground">
          Leave blank to use timestamp
        </p>
      </div>

      {/* Advanced audio toggle */}
      <div className="flex flex-col gap-2 rounded-lg border border-slate-200 p-4 bg-slate-50">
        <div className="flex items-center justify-between gap-4">
          <div className="space-y-1">
            <Label htmlFor="recorder-advanced-audio" className="text-base font-medium">
              Use Advanced Audio Processing
            </Label>
            <p className="text-xs text-muted-foreground">
              If you aren't using specific podcasting equipment. this is highly recommended to make it sound like you are.
            </p>
            {isAdvancedAudioSaving && (
              <p className="text-xs text-slate-500">Saving your preference…</p>
            )}
          </div>
          <Switch
            id="recorder-advanced-audio"
            checked={!!useAdvancedAudio}
            onCheckedChange={(checked) => onAdvancedAudioToggle?.(Boolean(checked))}
            disabled={isAdvancedAudioSaving}
          />
        </div>
      </div>

      {/* Save/Status */}
      <div className="space-y-4">
        {!savedDisplayName ? (
          <>
            <Button
              onClick={onSave}
              disabled={isSaving || isTooBig}
              size="lg"
              className="w-full text-lg py-6"
            >
              {isSaving ? (
                <>
                  <Loader2 className="w-5 h-5 mr-2 animate-spin" />
                  Uploading & Starting Transcription...
                </>
              ) : (
                <>
                  <Download className="w-5 h-5 mr-2" />
                  Save Recording
                </>
              )}
            </Button>
            
            {/* Action buttons row */}
            <div className="grid grid-cols-2 gap-3">
              {/* Start Over button with confirmation */}
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button
                    variant="outline"
                    disabled={isSaving}
                    className="w-full"
                  >
                    <RotateCcw className="w-4 h-4 mr-2" />
                    Start Over
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Start Over?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This will discard your current recording and let you record again (without running the mic check).
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction onClick={onStartOver}>
                      Start Over
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
              
              {/* Discard & Return button with confirmation */}
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button
                    variant="outline"
                    disabled={isSaving}
                    className="w-full text-red-600 hover:text-red-700 hover:bg-red-50"
                  >
                    <X className="w-4 h-4 mr-2" />
                    Discard
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Discard Recording?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This will permanently delete your recording and return you to the dashboard. This action cannot be undone.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction 
                      onClick={onDiscard}
                      className="bg-red-600 hover:bg-red-700"
                    >
                      Discard Recording
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            </div>
          </>
        ) : (
          <div className="bg-green-50 border border-green-300 rounded-lg p-6 space-y-4">
            <div className="flex items-center justify-center text-green-800">
              <CheckCircle className="w-6 h-6 mr-2" />
              <span className="text-lg font-medium">Recording Saved!</span>
            </div>
            
            {/* Transcription Status */}
            {transcriptReady ? (
              <p className="text-center text-green-700 font-medium text-base">
                ✅ Transcript is ready!
              </p>
            ) : (
              <div className="space-y-3">
                <p className="text-center text-green-700 text-base">
                  We're transcribing your audio now.
                </p>
                <p className="text-center text-green-700 text-base font-medium">
                  We'll let you know when it's ready!
                </p>
                {showTimeoutNotice && (
                  <p className="text-center text-yellow-700 text-sm">
                    This is taking longer than expected. The transcript will be ready soon.
                  </p>
                )}
              </div>
            )}
            
            {/* Finish Button */}
            {onFinish && (
              <Button
                onClick={onFinish}
                className="w-full mt-4"
              >
                Back to Dashboard
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
