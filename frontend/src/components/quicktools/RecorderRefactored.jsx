import React, { useState, useEffect, useRef, useMemo } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import { useAuth } from "@/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { makeApi } from "@/lib/apiClient";
import { uploadMediaDirect } from "@/lib/directUpload";

// Hooks
import { useDeviceSelection } from "./recorder/hooks/useDeviceSelection";
import { useAudioGraph } from "./recorder/hooks/useAudioGraph";
import { useAudioRecorder } from "./recorder/hooks/useAudioRecorder";
import { useMicCheck } from "./recorder/hooks/useMicCheck";

// Components
import { DeviceSelector } from "./recorder/components/DeviceSelector";
import { MicCheckOverlay } from "./recorder/components/MicCheckOverlay";
import { RecorderControls } from "./recorder/components/RecorderControls";
import { LevelMeter } from "./recorder/components/LevelMeter";
import { RecordingPreview } from "./recorder/components/RecordingPreview";

// Utils
import { ensureExt, formatDateName, extractStemFromFilename, isMobileDevice } from "./recorder/utils/audioUtils";

/**
 * Main Recorder component - browser-based podcast recording
 * @param {Object} props - Component props
 * @param {Function} props.onBack - Back navigation callback
 * @param {string} props.token - Auth token
 * @param {Function} props.onFinish - Finish callback
 * @param {Function} props.onSaved - Save callback
 * @param {string} [props.source="A"] - Source identifier
 */
export default function Recorder({ onBack, token, onFinish, onSaved, source = "A" }) {
  const { user: authUser } = useAuth();
  const { toast } = useToast();
  
  // Config
  const [maxUploadMb, setMaxUploadMb] = useState(500);
  const MAX_UPLOAD_BYTES = useMemo(() => maxUploadMb * 1024 * 1024, [maxUploadMb]);
  const isMobile = useMemo(() => isMobileDevice(), []);

  // Recording state
  const [recordingName, setRecordingName] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [serverFilename, setServerFilename] = useState("");
  const [serverStem, setServerStem] = useState("");
  const [savedDisplayName, setSavedDisplayName] = useState("");
  const [transcriptReady, setTranscriptReady] = useState(false);
  const [showTimeoutNotice, setShowTimeoutNotice] = useState(false);

  // Polling refs
  const pollIntervalRef = useRef(null);
  const pollAbortRef = useRef(null);
  const pollStartRef = useRef(0);

  // Device selection
  const deviceSelection = useDeviceSelection();

  // Audio graph (level metering + gain control)
  const peakLevelsRef = useRef([]);
  const audioGraph = useAudioGraph({ peakLevelsRef });

  // Audio recorder
  const recorder = useAudioRecorder({
    buildAudioGraph: audioGraph.buildAudioGraph,
    stopAudioGraph: audioGraph.stopAudioGraph,
    toast
  });

  // Helper: Start stream with fallback constraints
  const startStream = async (deviceId) => {
    const withDev = deviceId ? { exact: deviceId } : undefined;
    const attempts = [
      { audio: { deviceId: withDev, channelCount: 1, noiseSuppression: { ideal: true }, echoCancellation: { ideal: true } } },
      { audio: { deviceId: withDev, channelCount: 1 } },
      { audio: { deviceId: withDev } },
      { audio: true }
    ];

    let lastErr;
    for (const c of attempts) {
      try {
        const s = await navigator.mediaDevices.getUserMedia(c);
        audioGraph.buildAudioGraph(s);
        return s;
      } catch (e) {
        lastErr = e;
      }
    }
    throw lastErr || new Error('getUserMedia failed');
  };

  // Helper: Stop stream
  const stopStream = () => {
    if (recorder.streamRef.current) {
      recorder.streamRef.current.getTracks().forEach((t) => {
        try {
          t.stop();
        } catch {}
      });
      recorder.streamRef.current = null;
    }
  };

  // Mic check
  const micCheck = useMicCheck({
    audioGraph, // Now includes all refs
    deviceSelection,
    startStream,
    stopStream,
    onError: (msg) => toast({ variant: "destructive", title: "Error", description: msg })
  });

  // Fetch max upload config
  useEffect(() => {
    let canceled = false;
    (async () => {
      try {
        const res = await fetch('/api/public/config');
        const data = await res.json().catch(() => ({}));
        const n = parseInt(String(data?.max_upload_mb || '500'), 10);
        if (!canceled && isFinite(n) && !isNaN(n)) {
          const clamped = Math.min(Math.max(n, 10), 2048);
          setMaxUploadMb(clamped);
        }
      } catch {}
    })();
    return () => { canceled = true; };
  }, []);

  // Initialize devices on mount
  useEffect(() => {
    let mounted = true;
    
    (async () => {
      try {
        if (!mounted) return;
        console.log('[Recorder] Checking permissions...');
        
        // Check if permission already granted
        if (navigator.permissions?.query) {
          try {
            const status = await navigator.permissions.query({ name: "microphone" });
            if (status?.state === "granted" && mounted) {
              await deviceSelection.ensurePermissionAndDevices();
            }
          } catch (e) {
            // Permissions API not supported
          }
        }
      } catch (e) {
        console.error('[Recorder] Init error:', e);
      }
    })();
    
    return () => {
      mounted = false;
      // Cleanup
      audioGraph.stopAudioGraph();
      if (recorder.audioUrl) {
        URL.revokeObjectURL(recorder.audioUrl);
      }
      try { if (pollIntervalRef.current) clearInterval(pollIntervalRef.current); } catch {}
      try { if (pollAbortRef.current) pollAbortRef.current.abort(); } catch {}
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Poll transcript readiness
  useEffect(() => {
    setTranscriptReady(false);
    setShowTimeoutNotice(false);
    if (!serverStem) {
      try { if (pollIntervalRef.current) clearInterval(pollIntervalRef.current); } catch {}
      try { if (pollAbortRef.current) pollAbortRef.current.abort(); } catch {}
      pollIntervalRef.current = null;
      pollAbortRef.current = null;
      return;
    }

    const api = makeApi(token);
    const TEN_MIN_MS = 10 * 60 * 1000;
    pollStartRef.current = Date.now();

    const check = async () => {
      try { if (pollAbortRef.current) pollAbortRef.current.abort(); } catch {}
      const controller = new AbortController();
      pollAbortRef.current = controller;
      try {
        const res = await api.get(`/api/ai/transcript-ready?hint=${encodeURIComponent(serverStem)}`, { signal: controller.signal });
        const ready = (res && (res.ready === true || res.status === 'ready' || res === true));
        if (ready) {
          setTranscriptReady(true);
          try { if (pollIntervalRef.current) clearInterval(pollIntervalRef.current); } catch {}
          pollIntervalRef.current = null;
        }
      } catch (e) {
        // Ignore errors
      }
      const elapsedMs = Date.now() - pollStartRef.current;
      if (elapsedMs >= TEN_MIN_MS) setShowTimeoutNotice(true);
    };

    check();
    pollIntervalRef.current = setInterval(check, 5000);

    return () => {
      try { if (pollIntervalRef.current) clearInterval(pollIntervalRef.current); } catch {}
      try { if (pollAbortRef.current) pollAbortRef.current.abort(); } catch {}
    };
  }, [serverStem, token]);

  // Keyboard shortcut: Space to start/stop
  useEffect(() => {
    const isEditable = (el) => {
      if (!el) return false;
      const tn = el.tagName?.toLowerCase();
      return el.isContentEditable || tn === 'input' || tn === 'textarea' || tn === 'select';
    };
    const onKey = (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (isEditable(e.target)) return;
      
      const key = e.key || e.code;
      if (key === ' ' || key === 'Spacebar' || key === 'Space') {
        e.preventDefault();
        recorder.handleRecordToggle(deviceSelection.selectedDeviceId, (msg) => {
          deviceSelection.setSupportError?.(msg) || toast({ variant: "destructive", title: "Error", description: msg });
        });
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [recorder, deviceSelection, toast]);

  // Handle save
  const handleSave = async () => {
    if (!recorder.audioBlob || isSaving) return;
    if (recorder.audioBlob.size > MAX_UPLOAD_BYTES) {
      toast({ variant: "destructive", title: "Too large", description: `Recording too long to upload (over ${maxUploadMb} MB).` });
      return;
    }
    if (serverFilename) return; // Already uploaded

    try {
      setIsSaving(true);
      const baseName = (recordingName && recordingName.trim()) ? recordingName.trim() : formatDateName();
      let ext = ".webm";
      if (recorder.mimeType.includes("wav")) ext = ".wav";
      else if (recorder.mimeType.includes("webm")) ext = ".webm";
      else if (recorder.mimeType.includes("mp4") || recorder.mimeType.includes("aac")) ext = ".m4a";
      const filenameWithExt = ensureExt(baseName, ext);
      setSavedDisplayName(filenameWithExt);

      const file = new File([recorder.audioBlob], filenameWithExt, { type: recorder.mimeType || recorder.audioBlob.type || "audio/webm" });
      const userEmail = authUser?.email || '';
      
      const uploaded = await uploadMediaDirect({
        category: 'main_content',
        file,
        friendlyName: baseName,
        token,
        notifyWhenReady: !!userEmail,
        notifyEmail: userEmail || undefined,
      });
      
      const first = Array.isArray(uploaded) ? uploaded[0] : null;
      const stored = first && (first.filename || first.name || first.stored_name);
      if (!stored) throw new Error("Upload response missing filename");
      setServerFilename(stored);
      setServerStem(extractStemFromFilename(stored));
      
      const emailMsg = userEmail ? ` We'll email you at ${userEmail} when it's ready.` : '';
      toast({ title: "Recording Saved!", description: `Transcription started.${emailMsg}` });
      
      try { window.dispatchEvent(new CustomEvent('ppp:media-uploaded', { detail: first })); } catch {}
      try { if (typeof onSaved === 'function') onSaved(first); } catch {}
    } catch (e) {
      const msg = (e && (e.detail || e.message)) || "Upload failed";
      toast({ variant: "destructive", title: "Upload error", description: msg });
    } finally {
      setIsSaving(false);
    }
  };

  // Device change handler
  const onChangeDevice = async (value) => {
    if (recorder.isRecording) {
      toast({ variant: "destructive", title: "Cannot change device", description: "Stop recording first" });
      return;
    }
    deviceSelection.handleDeviceChange(value);
    // Restart stream if we had one
    if (recorder.streamRef.current) {
      audioGraph.stopAudioGraph();
      if (recorder.streamRef.current) {
        recorder.streamRef.current.getTracks().forEach((t) => t.stop());
      }
    }
  };

  return (
    <Card className="w-full">
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-2xl">Record Audio</CardTitle>
            <CardDescription className="mt-2">
              Record podcast audio directly in your browser
            </CardDescription>
          </div>
          {onBack && (
            <Button variant="ghost" onClick={onBack}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back
            </Button>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-6">
        {/* Mic check full-screen overlay when active OR showing analysis results */}
        {(micCheck.isMicChecking || micCheck.micCheckAnalysis) ? (
          <MicCheckOverlay
            isVisible={true}
            countdown={micCheck.micCheckCountdown}
            isPlayback={micCheck.micCheckPlayback}
            analysis={micCheck.micCheckAnalysis}
            levelPct={audioGraph.levelPct}
            levelColor={audioGraph.levelColor}
            inputGain={audioGraph.inputGain}
            onGainChange={audioGraph.updateGain}
            onContinue={micCheck.clearAnalysis}
            onRetry={micCheck.handleMicCheck}
          />
        ) : !micCheck.micCheckCompleted && !recorder.hasPreview ? (
          /* Show prominent mic check button before first use */
          <div className="min-h-[600px] flex flex-col items-center justify-center space-y-8">
            <div className="text-center space-y-6">
              <div className="text-4xl font-bold text-foreground">
                🎙️ First Time Recording?
              </div>
              <p className="text-xl text-muted-foreground max-w-2xl">
                Let's do a quick mic check to make sure your audio levels are perfect.
                It only takes 5 seconds!
              </p>
              <Button
                onClick={micCheck.handleMicCheck}
                size="lg"
                className="text-xl px-12 py-8"
                disabled={micCheck.isMicChecking}
              >
                Start Mic Check
              </Button>
            </div>
          </div>
        ) : recorder.hasPreview ? (
          /* Recording preview and save */
          <RecordingPreview
            audioUrl={recorder.audioUrl}
            audioBlob={recorder.audioBlob}
            recordingName={recordingName}
            onNameChange={setRecordingName}
            onSave={handleSave}
            isSaving={isSaving}
            savedDisplayName={savedDisplayName}
            transcriptReady={transcriptReady}
            showTimeoutNotice={showTimeoutNotice}
            maxUploadMb={maxUploadMb}
            onFinish={onFinish}
          />
        ) : (
          /* Main recording interface */
          <>
            {/* Device selector */}
            <DeviceSelector
              devices={deviceSelection.devices}
              selectedDeviceId={deviceSelection.selectedDeviceId}
              onDeviceChange={onChangeDevice}
              disabled={recorder.isRecording}
            />

            {/* Error display */}
            {deviceSelection.supportError && (
              <div className="bg-red-50 border border-red-300 rounded-lg p-4">
                <p className="text-red-800">{deviceSelection.supportError}</p>
              </div>
            )}

            {/* Recording controls */}
            <RecorderControls
              isRecording={recorder.isRecording}
              isPaused={recorder.isPaused}
              isCountingDown={recorder.isCountingDown}
              countdown={recorder.countdown}
              elapsed={recorder.elapsed}
              onRecordToggle={() => recorder.handleRecordToggle(deviceSelection.selectedDeviceId, (msg) => {
                deviceSelection.setSupportError?.(msg) || toast({ variant: "destructive", title: "Error", description: msg });
              })}
              onStop={recorder.handleStop}
              onMicCheck={micCheck.handleMicCheck}
              micCheckCompleted={micCheck.micCheckCompleted}
              isMicChecking={micCheck.isMicChecking}
            />

            {/* Level meter - show during recording */}
            {(recorder.isRecording || recorder.isPaused) && (
              <LevelMeter
                levelPct={audioGraph.levelPct}
                levelColor={audioGraph.levelColor}
                inputGain={audioGraph.inputGain}
                onGainChange={audioGraph.updateGain}
                showGainControl={false}
              />
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
