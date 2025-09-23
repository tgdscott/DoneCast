import React, { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { ArrowLeft, Mic, Square, Loader2, CheckCircle } from "lucide-react";
import { makeApi } from "@/lib/apiClient";
import { useToast } from "@/hooks/use-toast";

export default function Recorder({ onBack, token, onFinish, onSaved }) {
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [hasPreview, setHasPreview] = useState(false);
  const [elapsed, setElapsed] = useState(0); // seconds
  const [supportError, setSupportError] = useState("");
  const [devices, setDevices] = useState([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState("");
  const [mimeType, setMimeType] = useState("");
  const [isMicChecking, setIsMicChecking] = useState(false);
  const [levelPct, setLevelPct] = useState(0); // 0..1
  const [recordingName, setRecordingName] = useState("");
  const [audioUrl, setAudioUrl] = useState("");
  const [audioBlob, setAudioBlob] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [serverFilename, setServerFilename] = useState("");
  const [serverStem, setServerStem] = useState("");
  const [transcriptReady, setTranscriptReady] = useState(false);
  const [showTimeoutNotice, setShowTimeoutNotice] = useState(false);
  // Display-only name for UX (friendly name + extension), hides server's internal filename
  const [savedDisplayName, setSavedDisplayName] = useState("");
  // Senior-friendly helpers
  const [isCountingDown, setIsCountingDown] = useState(false);
  const [countdown, setCountdown] = useState(0);

  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const rafRef = useRef(null);
  const audioCtxRef = useRef(null);
  const analyserRef = useRef(null);
  const sourceRef = useRef(null);
  const isRecordingRef = useRef(false);
  const isPausedRef = useRef(false);
  const { toast } = useToast();
  const pollIntervalRef = useRef(null);
  const pollAbortRef = useRef(null);
  const pollStartRef = useRef(0);
  const countdownTimerRef = useRef(null);
  const wakeLockRef = useRef(null);
  const audioRef = useRef(null);
  const [maxUploadMb, setMaxUploadMb] = useState(500);
  const MAX_UPLOAD_BYTES = useMemo(() => maxUploadMb * 1024 * 1024, [maxUploadMb]);

  const isMobile = useMemo(() => {
    try { return /Mobi|Android|iPhone|iPad|iPod/i.test(navigator.userAgent || ''); } catch { return false; }
  }, []);

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

  const formatTime = (s) => {
    const m = Math.floor(s / 60)
      .toString()
      .padStart(2, "0");
    const r = Math.floor(s % 60)
      .toString()
      .padStart(2, "0");
    return `${m}:${r}`;
  };

  const pickMimeType = () => {
    if (window.MediaRecorder) {
      if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
        return "audio/webm;codecs=opus";
      }
      if (MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported("audio/mp4;codecs=aac")) {
        return "audio/mp4;codecs=aac"; // Safari/iOS
      }
    }
    return "";
  };

  // Re-encode a recording Blob to PCM WAV to normalize timestamps and avoid per-chunk glitches.
  // Returns a Blob of type audio/wav. Throws if decode fails.
  const reencodeToWav = async (blob) => {
    const arrayBuffer = await blob.arrayBuffer();
    const AC = window.AudioContext || window.webkitAudioContext;
    if (!AC) throw new Error("No AudioContext available");
    const ctx = new AC();
    try {
      const audioBuffer = await ctx.decodeAudioData(arrayBuffer);
      const numChannels = Math.min(2, Math.max(1, audioBuffer.numberOfChannels || 1));
      const sampleRate = audioBuffer.sampleRate;
      const length = audioBuffer.length;
      // Prepare interleaved PCM16
      const channelData = [];
      for (let ch = 0; ch < numChannels; ch++) {
        channelData[ch] = audioBuffer.getChannelData(ch);
      }
      const bytesPerSample = 2;
      const blockAlign = numChannels * bytesPerSample;
      const byteRate = sampleRate * blockAlign;
      const dataSize = length * blockAlign;
      const buffer = new ArrayBuffer(44 + dataSize);
      const view = new DataView(buffer);

      // Write WAV header
      let offset = 0;
      // RIFF identifier 'RIFF'
      view.setUint32(offset, 0x52494646, false); offset += 4;
      // file length minus RIFF and size fields
      view.setUint32(offset, 36 + dataSize, true); offset += 4;
      // RIFF type 'WAVE'
      view.setUint32(offset, 0x57415645, false); offset += 4;
      // format chunk identifier 'fmt '
      view.setUint32(offset, 0x666d7420, false); offset += 4;
      // format chunk length
      view.setUint32(offset, 16, true); offset += 4;
      // audio format (1 = PCM)
      view.setUint16(offset, 1, true); offset += 2;
      // number of channels
      view.setUint16(offset, numChannels, true); offset += 2;
      // sample rate
      view.setUint32(offset, sampleRate, true); offset += 4;
      // byte rate (sample rate * block align)
      view.setUint32(offset, byteRate, true); offset += 4;
      // block align (channel count * bytes per sample)
      view.setUint16(offset, blockAlign, true); offset += 2;
      // bits per sample
      view.setUint16(offset, 16, true); offset += 2;
      // data chunk identifier 'data'
      view.setUint32(offset, 0x64617461, false); offset += 4;
      // data chunk length
      view.setUint32(offset, dataSize, true); offset += 4;

      // PCM samples
      const writeSample = (v) => {
        // Clamp to [-1,1] then scale to 16-bit PCM
        const s = Math.max(-1, Math.min(1, v));
        view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
        offset += 2;
      };

      if (numChannels === 1) {
        const input = channelData[0];
        for (let i = 0; i < length; i++) writeSample(input[i]);
      } else {
        const left = channelData[0];
        const right = channelData[1];
        for (let i = 0; i < length; i++) { writeSample(left[i]); writeSample(right[i]); }
      }

      return new Blob([buffer], { type: "audio/wav" });
    } finally {
      try { await ctx.close(); } catch {}
    }
  };

  const formatDateName = () => {
    const d = new Date();
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, "0");
    const dd = String(d.getDate()).padStart(2, "0");
    const HH = String(d.getHours()).padStart(2, "0");
    const MM = String(d.getMinutes()).padStart(2, "0");
    return `My Recording ${yyyy}-${mm}-${dd} ${HH}${MM}`;
  };

  const extractStemFromFilename = (filename) => {
    if (!filename) return "";
    const idx = filename.lastIndexOf(".");
    return idx > 0 ? filename.slice(0, idx) : filename;
  };

  const stopStream = () => {
    try {
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
      }
    } catch {}
    streamRef.current = null;
  };

  const stopAudioGraph = () => {
    try {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
      if (audioCtxRef.current) audioCtxRef.current.close();
    } catch {}
    audioCtxRef.current = null;
    analyserRef.current = null;
    sourceRef.current = null;
  };

  const buildAudioGraph = (stream) => {
    try {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 2048;
      source.connect(analyser);
      audioCtxRef.current = ctx;
      analyserRef.current = analyser;
      sourceRef.current = source;

      const data = new Uint8Array(analyser.fftSize);
      const loop = () => {
        analyser.getByteTimeDomainData(data);
        // Compute simple peak level 0..1
        let peak = 0;
        for (let i = 0; i < data.length; i++) {
          const v = Math.abs(data[i] - 128) / 128; // center at 0
          if (v > peak) peak = v;
        }
        setLevelPct(Math.min(1, peak));
        rafRef.current = requestAnimationFrame(loop);
      };
      rafRef.current = requestAnimationFrame(loop);
    } catch (e) {
      // Meter optional; ignore failures
    }
  };

  const ensurePermissionAndDevices = async () => {
    // Request minimal audio to unlock enumerateDevices
    try {
      const constraints = { audio: true };
      const s = await navigator.mediaDevices.getUserMedia(constraints);
      try {
        const devs = await navigator.mediaDevices.enumerateDevices();
        // Only include devices with a non-empty deviceId; some browsers obfuscate until permission is granted
        const inputs = devs.filter((d) => d.kind === "audioinput" && d.deviceId);
        setDevices(inputs);
        if (!selectedDeviceId && inputs[0]?.deviceId) setSelectedDeviceId(inputs[0].deviceId);
      } finally {
        try { s.getTracks().forEach((t) => t.stop()); } catch {}
      }
    } catch (e) {
      const name = e?.name || "";
      if (name === "NotAllowedError" || name === "SecurityError" || name === "PermissionDeniedError") {
        setSupportError("Microphone access was blocked. Please allow microphone permission in your browser, then try again. Tip: Click the mic/camera icon in the address bar to grant access.");
      } else if (name === "NotFoundError") {
        setSupportError("No microphone was found. Plug in or enable a microphone and try again.");
      } else {
        setSupportError("Could not access microphone.");
      }
      throw e;
    }
  };

  const startStream = async (deviceId) => {
    // Be resilient: some devices reject certain constraints; try a few fallbacks
    const attempts = [];
    const withDev = deviceId ? { exact: deviceId } : undefined;
    attempts.push({ audio: { deviceId: withDev, channelCount: 1, noiseSuppression: { ideal: true }, echoCancellation: { ideal: true } } });
    attempts.push({ audio: { deviceId: withDev, channelCount: 1 } });
    attempts.push({ audio: { deviceId: withDev } });
    attempts.push({ audio: true });

    let lastErr;
    for (const c of attempts) {
      try {
        const s = await navigator.mediaDevices.getUserMedia(c);
        streamRef.current = s;
        buildAudioGraph(s);
        return s;
      } catch (e) {
        lastErr = e;
        // Continue to next fallback
      }
    }
    throw lastErr || new Error('getUserMedia failed');
  };

  const startRecording = async () => {
    setSupportError("");
    setAudioUrl((prev) => {
      if (prev) URL.revokeObjectURL(prev);
      return "";
    });
    setAudioBlob(null);
    setHasPreview(false);
    setElapsed(0);
  // Reset any existing chunks to avoid concatenating from a previous session
  chunksRef.current = [];
  // Ensure preview audio is paused so it won't play while recording (prevents echo)
  try { if (audioRef.current) { audioRef.current.pause(); audioRef.current.currentTime = 0; } } catch {}
    setIsPaused(false);
    isPausedRef.current = false;

    const m = pickMimeType();
    if (!m) {
      setSupportError("Recording not supported in this browser.");
      return;
    }
    setMimeType(m);

    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        setSupportError("Recording not supported in this browser.");
        return;
      }
      // Start stream with current device
      const s = await startStream(selectedDeviceId);

      const rec = new MediaRecorder(s, { mimeType: m });
      chunksRef.current = [];
  let lastChunkAt = 0;
  rec.ondataavailable = (e) => {
        const now = Date.now();
        // Only accept non-empty chunks while the session is active; debounce to avoid quick duplicates
        if (!e?.data || e.data.size === 0) return;
        if (now - lastChunkAt < 50) return; // guard against immediate duplicate events
        lastChunkAt = now;
        chunksRef.current.push(e.data);
      };
      rec.onpause = () => {
        setIsPaused(true);
        isPausedRef.current = true;
      };
      rec.onresume = () => {
        setIsPaused(false);
        isPausedRef.current = false;
      };
      rec.onstop = () => {
        // Allow any final ondataavailable to land before assembling
        Promise.resolve().then(async () => {
          try {
            const parts = chunksRef.current || [];
            const rawBlob = new Blob(parts, { type: m });
            // Re-encode to WAV to normalize and remove any duplicated 1s chunk artifacts
            let finalBlob = rawBlob;
            try {
              finalBlob = await reencodeToWav(rawBlob);
              setMimeType("audio/wav");
            } catch (err) {
              // Fallback to original if re-encode fails
              finalBlob = rawBlob;
            }
            setAudioBlob(finalBlob);
            const url = URL.createObjectURL(finalBlob);
            setAudioUrl(url);
            setHasPreview(true);
          } catch {}
        });
      };
  mediaRecorderRef.current = rec;
  // Start without a timeSlice so data is emitted on stop (and occasionally on pause/resume).
  // This avoids per-second chunk artifacts some browsers exhibit when concatenating.
  rec.start();
      setIsRecording(true);
      isRecordingRef.current = true;
      // Timer
      if (timerRef.current) { try { clearInterval(timerRef.current); } catch {} }
      timerRef.current = setInterval(() => {
        if (isRecordingRef.current && !isPausedRef.current) {
          setElapsed((e) => e + 1);
        }
      }, 1000);
      // Try to keep the screen awake during recording (ignore errors)
      try {
        if (navigator.wakeLock?.request) {
          wakeLockRef.current = await navigator.wakeLock.request('screen');
        }
      } catch {}
    } catch (e) {
      console.error(e);
      const name = e?.name || "";
      if (name === "NotAllowedError" || name === "SecurityError" || name === "PermissionDeniedError") {
        setSupportError("Microphone permission denied. Allow access in your browser and try again.");
      } else if (name === "NotFoundError") {
        setSupportError("No microphone detected.");
      } else {
        setSupportError("Could not access microphone.");
      }
      stopStream();
      stopAudioGraph();
    }
  };

  const stopRecording = () => {
    try {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== "inactive") {
  mediaRecorderRef.current.stop();
      }
    } catch {}
    setIsRecording(false);
  isRecordingRef.current = false;
  setIsPaused(false);
  isPausedRef.current = false;
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
  // Stop any preview playback immediately to avoid overlapping sound
  try { if (audioRef.current) audioRef.current.pause(); } catch {}
    stopAudioGraph();
    stopStream();
  // Release wake lock if held
  try { if (wakeLockRef.current?.release) { wakeLockRef.current.release(); } } catch {}
  wakeLockRef.current = null;
  };

  const startCountdown = () => {
    if (isRecording || isCountingDown) return;
    setCountdown(3);
    setIsCountingDown(true);
    if (countdownTimerRef.current) { try { clearInterval(countdownTimerRef.current); } catch {} }
    countdownTimerRef.current = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          try { clearInterval(countdownTimerRef.current); } catch {}
          countdownTimerRef.current = null;
          setIsCountingDown(false);
          startRecording();
          return 0;
        }
        return c - 1;
      });
    }, 1000);
  };

  const startResumeCountdown = () => {
    if (!isPaused || isCountingDown) return;
    setCountdown(3);
    setIsCountingDown(true);
    if (countdownTimerRef.current) { try { clearInterval(countdownTimerRef.current); } catch {} }
    countdownTimerRef.current = setInterval(() => {
      setCountdown((c) => {
        if (c <= 1) {
          try { clearInterval(countdownTimerRef.current); } catch {}
          countdownTimerRef.current = null;
          setIsCountingDown(false);
          try { mediaRecorderRef.current?.resume?.(); } catch {}
          return 0;
        }
        return c - 1;
      });
    }, 1000);
  };

  const cancelCountdown = () => {
    try { if (countdownTimerRef.current) clearInterval(countdownTimerRef.current); } catch {}
    countdownTimerRef.current = null;
    setIsCountingDown(false);
    setCountdown(0);
  };

  const handleRecordToggle = () => {
    // Three-state button: Record (initial) -> Pause -> Resume (with 3s countdown)
    if (!isRecording) {
      if (isCountingDown) { cancelCountdown(); return; }
      startCountdown();
      return;
    }
    // If currently recording and not paused, pause immediately
    if (!isPaused) {
      try { mediaRecorderRef.current?.pause?.(); } catch {}
      return;
    }
    // If paused, resume with countdown
    startResumeCountdown();
  };

  const handleStop = () => {
    if (isPaused) {
      stopRecording();
    }
  };

  const handleMicCheck = async () => {
    if (isRecording || isMicChecking) return;
    setIsMicChecking(true);
    try {
      // Ensure we can see devices; if permission was revoked mid-session, prompt again
      if (!devices || devices.length === 0) {
        try { await ensurePermissionAndDevices(); } catch {}
      }
      const s = await startStream(selectedDeviceId);
      // Show meter for ~3s
      await new Promise((res) => setTimeout(res, 3000));
      stopAudioGraph();
      s.getTracks().forEach((t) => t.stop());
    } catch (e) {
      const name = e?.name || '';
      if (name === 'NotAllowedError' || name === 'SecurityError' || name === 'PermissionDeniedError') {
        setSupportError('Microphone permission is blocked. Allow access in your browser and try again.');
      } else if (name === 'NotFoundError' || name === 'OverconstrainedError') {
        setSupportError('Could not start mic check for the selected device. Try another microphone or unplug/replug it.');
      } else {
        setSupportError('Could not start mic check.');
      }
    } finally {
      setIsMicChecking(false);
    }
  };

  const ensureExt = (name, ext) => {
    if (!name) return `untitled${ext}`;
    const lower = name.toLowerCase();
    return lower.endsWith(ext) ? name : `${name}${ext}`;
  };

  const handleSave = async () => {
    if (!audioBlob || isSaving) return;
    if (audioBlob.size > MAX_UPLOAD_BYTES) {
      toast({ variant: "destructive", title: "Too large", description: "Recording too long to upload (over 500 MB)." });
      return;
    }
    if (serverFilename) {
      // Already uploaded; keep UI idempotent
      return;
    }
    try {
      setIsSaving(true);
  // Determine final name
  const baseName = (recordingName && recordingName.trim()) ? recordingName.trim() : formatDateName();
  let ext = ".webm";
  if (mimeType.includes("wav")) ext = ".wav";
  else if (mimeType.includes("webm")) ext = ".webm";
  else if (mimeType.includes("mp4") || mimeType.includes("aac")) ext = ".m4a";
      const filenameWithExt = ensureExt(baseName, ext);
  // Save display name immediately for UI; we keep server filename internally
  setSavedDisplayName(filenameWithExt);
      // Build File from Blob so server receives a filename with extension
      const file = new File([audioBlob], filenameWithExt, { type: mimeType || audioBlob.type || "audio/webm" });
      const form = new FormData();
      form.append("files", file);
      form.append("friendly_names", JSON.stringify([baseName]));
      const api = makeApi(token);
  const res = await api.raw("/api/media/upload/main_content", { method: "POST", body: form });
  const arr = Array.isArray(res) ? res : (res && res.data ? res.data : null);
  const first = Array.isArray(arr) ? arr[0] : null;
      const stored = first && (first.filename || first.name || first.stored_name);
      if (!stored) throw new Error("Upload response missing filename");
      setServerFilename(stored);
      setServerStem(extractStemFromFilename(stored));
      // Surface success toast
      toast({ title: "Saved", description: "Saved. Transcription has started." });
  // Notify host app (A/B upload screen, etc.) so it can surface the new media immediately
  try { window.dispatchEvent(new CustomEvent('ppp:media-uploaded', { detail: first })); } catch {}
  try { if (typeof onSaved === 'function') onSaved(first); } catch {}
    } catch (e) {
      const msg = (e && (e.detail || e.message)) || "Upload failed";
      toast({ variant: "destructive", title: "Upload error", description: msg });
    } finally {
      setIsSaving(false);
    }
  };

  // Populate devices after permission when component mounts (lazy: on first record or mic check).
  useEffect(() => {
    // Try to enumerate if permission already granted
    (async () => {
      try {
        // Proactively surface denied state if Permissions API exists
        if (navigator.permissions?.query) {
          try {
            const status = await navigator.permissions.query({ name: "microphone" });
            if (status?.state === "denied") {
              setSupportError("Microphone access is blocked. Enable it in your browser site settings, then press Record.");
            }
          } catch {}
        }
  const devs = await navigator.mediaDevices.enumerateDevices();
  // Filter out entries lacking a stable deviceId (common pre-permission)
  const inputs = devs.filter((d) => d.kind === "audioinput" && d.deviceId);
        if (inputs.length) {
          setDevices(inputs);
          // Respect previously selected device if available
          let saved = '';
          try { saved = localStorage.getItem('ppp_mic_device_id') || ''; } catch {}
          if (saved && inputs.find(d => d.deviceId === saved)) {
            setSelectedDeviceId(saved);
          } else if (!selectedDeviceId) {
            setSelectedDeviceId(inputs[0].deviceId);
          }
        }
      } catch {}
    })();
    return () => {
      // Cleanup on unmount
      try { if (timerRef.current) clearInterval(timerRef.current); } catch {}
      try { if (countdownTimerRef.current) clearInterval(countdownTimerRef.current); } catch {}
      stopAudioGraph();
      stopStream();
      if (audioUrl) URL.revokeObjectURL(audioUrl);
      try { if (pollIntervalRef.current) clearInterval(pollIntervalRef.current); } catch {}
      try { if (pollAbortRef.current) pollAbortRef.current.abort(); } catch {}
      try { if (wakeLockRef.current?.release) { wakeLockRef.current.release(); } } catch {}
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Start polling transcript readiness once we have a stored filename/stem
  useEffect(() => {
    // Reset readiness states when stem changes
    setTranscriptReady(false);
    setShowTimeoutNotice(false);
    if (!serverStem) {
      // Clear any existing polling
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
      // Abort any in-flight
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
        // Ignore transient errors; continue polling
      }
      const elapsedMs = Date.now() - pollStartRef.current;
      if (elapsedMs >= TEN_MIN_MS) setShowTimeoutNotice(true);
    };

    // Kick off immediately, then every 5s
    check();
    pollIntervalRef.current = setInterval(check, 5000);

    return () => {
      try { if (pollIntervalRef.current) clearInterval(pollIntervalRef.current); } catch {}
      pollIntervalRef.current = null;
      try { if (pollAbortRef.current) pollAbortRef.current.abort(); } catch {}
      pollAbortRef.current = null;
    };
  }, [serverStem, token]);

  // Keyboard shortcuts: R to start/stop; Space to play/pause preview (when not typing)
  useEffect(() => {
    const isEditable = (el) => {
      if (!el) return false;
      const tn = el.tagName?.toLowerCase();
      return el.isContentEditable || tn === 'input' || tn === 'textarea' || tn === 'select';
    };
    const onKey = (e) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      const key = e.key || e.code;
      if (key === 'r' || key === 'R') {
        if (isEditable(e.target)) return;
        e.preventDefault();
        handleRecordToggle();
      } else if (key === ' ' || key === 'Spacebar' || key === 'Space') {
        if (hasPreview && audioRef.current && !isEditable(e.target)) {
          e.preventDefault();
          const a = audioRef.current;
          if (a.paused) a.play().catch(()=>{}); else a.pause();
        }
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [hasPreview, handleRecordToggle]);

  const onChangeDevice = async (value) => {
    setSelectedDeviceId(value);
  try { localStorage.setItem('ppp_mic_device_id', value || ''); } catch {}
    // If we already have permission and not recording, pre-warm a silent stream for meter readiness
    if (!isRecording) {
      try {
        stopAudioGraph();
        stopStream();
        const s = await startStream(value);
        // Don't keep it forever; just build graph to show signal then stop after brief delay
        setTimeout(() => {
          stopAudioGraph();
          try { s.getTracks().forEach((t) => t.stop()); } catch {}
        }, 500);
      } catch {}
    } else {
      // Restart stream during recording (simple approach: stop recording)
      stopRecording();
      // Optionally auto-restart with new device
  startCountdown();
    }
  };

  return (
    <div className="space-y-6">
      {/* Top bar */}
      <div className="flex items-center gap-3">
  <Button variant="ghost" onClick={onBack} className="px-2 focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-primary" aria-label="Go back to dashboard">
          <ArrowLeft className="w-4 h-4 mr-2" /> Back
        </Button>
        <div>
          <h1 className="text-2xl font-semibold">Record an Episode</h1>
          <p className="text-sm text-muted-foreground">Capture audio directly in your browser and save it to your library.</p>
        </div>
      </div>

      <Card className="shadow-sm">
        <CardHeader className="pb-2">
          <CardTitle className="text-lg">Recorder</CardTitle>
          <CardDescription>Large controls and clear status for easy use.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {supportError && (
            <div className="text-sm bg-red-50 border border-red-200 text-red-700 rounded p-3">
              {supportError}
            </div>
          )}
          {/* Center controls */}
          <div className="flex flex-col items-center gap-5">
            <div className="flex items-center gap-4">
              <Button
                onClick={handleRecordToggle}
                aria-label={!isRecording ? (isCountingDown ? 'Cancel countdown' : 'Start recording') : (isPaused ? 'Resume recording' : 'Pause recording')}
                className={`rounded-full w-28 h-28 text-lg font-semibold shadow ${!isRecording ? (isCountingDown ? 'bg-amber-600 hover:bg-amber-500' : 'bg-green-600 hover:bg-green-500') : (isPaused ? 'bg-green-600 hover:bg-green-500' : 'bg-amber-600 hover:bg-amber-500')} text-white focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-primary`}
              >
                {!isRecording ? (
                  <span className="flex items-center gap-2"><Mic className="w-5 h-5" /> {isCountingDown ? `Starting in ${countdown}…` : 'Record'}</span>
                ) : (
                  <span className="flex items-center gap-2">{isPaused ? <><Mic className="w-5 h-5" /> {isCountingDown ? `Resuming in ${countdown}…` : 'Resume'}</> : <>Pause</>}</span>
                )}
              </Button>
              <Button variant="outline" disabled={!isPaused} onClick={handleStop} aria-label="Stop recording (available when paused)" className="h-10">
                <Square className="w-4 h-4 mr-2" /> Stop
              </Button>
            </div>

            {/* Digital timer */}
            <div className="text-5xl font-mono tracking-wider" aria-live="polite">{formatTime(elapsed)}</div>

            {/* Mobile keep-awake hint */}
            {isRecording && isMobile && (
              <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2" role="status">
                Keep your screen on while recording. We’ll try to prevent sleep.
              </div>
            )}

            {/* Input level meter */}
            <div className="w-full max-w-md">
              <div className="text-xs text-muted-foreground mb-1">Input level</div>
              <div className="h-3 rounded-full bg-muted relative overflow-hidden">
                <div className="absolute left-0 top-0 h-3 bg-emerald-500 transition-[width] duration-75" style={{ width: `${Math.round(levelPct*100)}%` }} />
              </div>
            </div>
          </div>

          {/* Microphone select + mic check */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 items-end max-w-3xl mx-auto w-full">
            <div className="md:col-span-2">
              <Label htmlFor="micSelect">Microphone</Label>
              {devices.filter(d => d.deviceId).length === 0 && (
                <p className="text-xs text-muted-foreground mt-1">Select your microphone and click Allow in your browser when prompted. The list stays disabled until access is granted.</p>
              )}
              <Select value={selectedDeviceId} onValueChange={onChangeDevice} onOpenChange={(open)=>{ if(open && devices.filter(d=>d.deviceId).length===0) ensurePermissionAndDevices().catch(()=>{}); }} aria-label="Select microphone">
                <SelectTrigger id="micSelect" className="mt-1 focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-primary">
                  <SelectValue placeholder={devices.filter(d=>d.deviceId).length? 'Select microphone' : 'Select microphone (allow access first)'} />
                </SelectTrigger>
                <SelectContent>
                  {devices.filter(d=>d.deviceId).length === 0 ? (
                    <SelectItem value="no-devices" disabled>No microphones found</SelectItem>
                  ) : (
                    devices.filter(d=>d.deviceId).map((d) => (
                      <SelectItem key={d.deviceId} value={d.deviceId}>{d.label || 'Microphone'}</SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
            </div>
            <div className="flex md:justify-end">
              <Button variant="outline" className="w-full md:w-auto focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-primary" aria-label="Run mic check" disabled={isRecording || isMicChecking} onClick={async ()=>{
                if (devices.length===0) {
                  try { await ensurePermissionAndDevices(); } catch {}
                }
                handleMicCheck();
              }}>Mic check (3s)</Button>
            </div>
          </div>

          {/* Preview & save area (shown after stop) */}
          {hasPreview && (
            <div className="mt-2 space-y-4 max-w-3xl mx-auto w-full">
              <div className="p-4 border rounded-lg bg-card">
                <audio controls className="w-full focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary" src={audioUrl || undefined} ref={audioRef} aria-label="Recording preview" />
              </div>
              <div className="grid md:grid-cols-3 gap-4 items-end">
                <div className="md:col-span-2">
                  <Label htmlFor="recName">Name this recording</Label>
                  <Input id="recName" className="mt-1 focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-primary" placeholder="e.g., Interview with Jamie (raw)" value={recordingName} onChange={(e)=>setRecordingName(e.target.value)} />
                </div>
                <div className="flex gap-2 md:justify-end">
                  <Button
                    className="flex-1 md:flex-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-primary"
                    aria-label="Save to My Library"
                    disabled={!audioBlob || isSaving || (audioBlob && audioBlob.size > MAX_UPLOAD_BYTES) || !!serverFilename}
                    onClick={handleSave}
                  >
                    {isSaving ? (
                      <span className="inline-flex items-center gap-2"><Loader2 className="h-4 w-4 animate-spin" /> Saving…</span>
                    ) : (!!serverFilename ? 'Saved' : 'Save to My Library')}
                  </Button>
                  <Button variant="outline" className="flex-1 md:flex-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-primary" aria-label="Discard recording" disabled={isSaving} onClick={()=>{ setHasPreview(false); setAudioBlob(null); setAudioUrl((u)=>{ if(u) URL.revokeObjectURL(u); return ""; }); setRecordingName(""); }}>Discard</Button>
                </div>
              </div>
              {audioBlob && audioBlob.size > MAX_UPLOAD_BYTES && (
                <div className="text-sm bg-red-50 border border-red-200 text-red-700 rounded p-3">
                  Recording too long to upload (over 500 MB). Please record a shorter segment.
                </div>
              )}
              {serverFilename && (
                <div className="p-4 border rounded-lg bg-muted/30">
                  <div className="flex items-center justify-between gap-3 flex-wrap">
                    <div>
                      <div className="text-sm text-muted-foreground">Queued for processing</div>
                      <div className="text-sm font-medium mt-1">{savedDisplayName || serverFilename}</div>
                      <div className="text-xs text-muted-foreground mt-0.5">
                        Size: {audioBlob ? (audioBlob.size / (1024*1024)).toFixed(2) : '0.00'} MB
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      {transcriptReady ? (
                        <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-emerald-100 text-emerald-800 border border-emerald-200">
                          <CheckCircle className="h-4 w-4 mr-1" aria-hidden /> Ready
                        </span>
                      ) : (
                        <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-medium bg-amber-100 text-amber-800 border border-amber-200">
                          <Loader2 className="h-4 w-4 mr-1 animate-spin" aria-hidden /> Processing…
                        </span>
                      )}
                      {transcriptReady && (
                        <Button
                          className="bg-primary text-primary-foreground hover:bg-primary/90 focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-primary"
                          aria-label="Finish episode"
                          onClick={() => {
                            // Prefer prop callback handoff; fallback to localStorage + event for backward-compat
                            if (typeof onFinish === 'function') {
                              onFinish({ filename: serverFilename, hint: serverStem, transcriptReady: true, startStep: 5 });
                              return;
                            }
                            try {
                              if (serverFilename) localStorage.setItem('ppp_uploaded_filename', serverFilename);
                              if (serverStem) localStorage.setItem('ppp_uploaded_hint', serverStem);
                              localStorage.setItem('ppp_start_step', '5');
                              localStorage.setItem('ppp_transcript_ready', '1');
                            } catch {}
                            try {
                              window.dispatchEvent(new CustomEvent('ppp:navigate-view', { detail: 'createEpisode' }));
                            } catch {}
                          }}
                        >
                          Finish Episode
                        </Button>
                      )}
                    </div>
                  </div>
                  {showTimeoutNotice && !transcriptReady && (
                    <div className="text-xs text-muted-foreground mt-3">Still processing; you can leave this page — we’ll keep working.</div>
                  )}
                </div>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
