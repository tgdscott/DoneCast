import React, { useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@/AuthContext.jsx";
import OnboardingWrapper from "@/components/onboarding/OnboardingWrapper.jsx";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CheckCircle, Play, Pause, Mic } from "lucide-react";
import { useToast } from "@/hooks/use-toast";
import { useComfort } from '@/ComfortContext.jsx';
import { makeApi, buildApiUrl } from '@/lib/apiClient';
import { FORMATS, NO_MUSIC_OPTION } from "@/components/onboarding/OnboardingWizard.jsx";
import CoverCropper from "@/components/dashboard/CoverCropper.jsx";
import { useResolvedTimezone } from '@/hooks/useResolvedTimezone';
import { formatInTimezone } from '@/lib/timezone';
import AIAssistant from "@/components/assistant/AIAssistant.jsx";
import VoiceRecorder from "@/components/onboarding/VoiceRecorder.jsx";

export default function Onboarding() {
  const { token, user, refreshUser } = useAuth();
  const { toast } = useToast();
  const resolvedTimezone = useResolvedTimezone(user?.timezone);
  const STEP_KEY = 'ppp.onboarding.step';
  // Detect if launched from Podcast Manager and whether to reset saved step
  const [fromManager] = useState(() => {
    try { return new URLSearchParams(window.location.search).get('from') === 'manager'; } catch { return false; }
  });
  // Restore step index on mount from localStorage
  const [stepIndex, setStepIndex] = useState(() => {
    try {
      const raw = localStorage.getItem(STEP_KEY);
      const n = raw != null ? parseInt(raw, 10) : 0;
      return Number.isFinite(n) && n >= 0 ? n : 0;
    } catch {
      return 0;
    }
  });
  
  // Auth check - redirect to login if no token
  useEffect(() => {
    if (!token && !user) {
      console.warn('[Onboarding] No authentication token found, redirecting to login');
      window.location.href = '/?login=1';
    }
  }, [token, user]);
  const stepSaveTimer = useRef(null);
  const importResumeTimerRef = useRef(null);
  const { largeText, setLargeText, highContrast, setHighContrast } = useComfort();

  // Path selection: 'new' | 'import'
  const [path, setPath] = useState('new');

  // Local state mirrors NewUserWizard.jsx
  const [formData, setFormData] = useState({
    podcastName: '',
    podcastDescription: '',
    coverArt: null,
    elevenlabsApiKey: '',
  });
  const [saving, setSaving] = useState(false);

  // Additional state for richer flow
  const [formatKey, setFormatKey] = useState('solo');
  const [publishDay, setPublishDay] = useState('Monday');
  const [rssUrl, setRssUrl] = useState('');
  const [importResult, setImportResult] = useState(null);
  const [resumeAfterImport, setResumeAfterImport] = useState(false);
  const [importLoading, setImportLoading] = useState(false);
  // Interop flags for import -> new flow jump
  const [showSkipNotice, setShowSkipNotice] = useState(false);
  const [importJumpedToStep6, setImportJumpedToStep6] = useState(false);

  // Music assets
  const [musicAssets, setMusicAssets] = useState([NO_MUSIC_OPTION]);
  const [musicLoading, setMusicLoading] = useState(false);
  const [musicChoice, setMusicChoice] = useState('none');
  const [musicPreviewing, setMusicPreviewing] = useState(null); // asset id
  const audioRef = useRef(null);
  // Dedicated audio ref for intro/outro previews
  const ioAudioRef = useRef(null);
  const [introPreviewing, setIntroPreviewing] = useState(false);
  const [outroPreviewing, setOutroPreviewing] = useState(false);
  // New scheduling states
  const [freqUnit, setFreqUnit] = useState(''); // no default; enforce selection
  const [freqCount, setFreqCount] = useState(1);
  const [cadenceError, setCadenceError] = useState('');
  const [selectedWeekdays, setSelectedWeekdays] = useState([]); // e.g., ['Monday','Wednesday']
  const [selectedDates, setSelectedDates] = useState([]); // e.g., ['2025-09-10','2025-09-24']
  const [notSureSchedule, setNotSureSchedule] = useState(false);
  // Name capture (Step 1)
  const [firstName, setFirstName] = useState(() => (user?.first_name || ''));
  const [lastName, setLastName] = useState(() => (user?.last_name || ''));
  const [nameError, setNameError] = useState('');

  // Cover step: allow skipping
  const [skipCoverNow, setSkipCoverNow] = useState(false);
  const coverArtInputRef = useRef(null);
  const coverCropperRef = useRef(null);
  const [coverCrop, setCoverCrop] = useState(null);
  const [coverMode, setCoverMode] = useState('crop');

  // Intro/Outro step state
  const [introMode, setIntroMode] = useState('tts'); // 'existing' | 'tts' | 'upload'
  const [outroMode, setOutroMode] = useState('tts'); // 'existing' | 'tts' | 'upload'
  const [introScript, setIntroScript] = useState('Welcome to my podcast!');
  const [outroScript, setOutroScript] = useState('Thank you for listening and see you next time!');
  const [introFile, setIntroFile] = useState(null);
  const [outroFile, setOutroFile] = useState(null);
  const [introAsset, setIntroAsset] = useState(null); // { filename, id, ... }
  const [outroAsset, setOutroAsset] = useState(null);
  // Saved media options
  const [introOptions, setIntroOptions] = useState([]); // MediaItem[] where category === 'intro'
  const [outroOptions, setOutroOptions] = useState([]);
  const [selectedIntroId, setSelectedIntroId] = useState('');
  const [selectedOutroId, setSelectedOutroId] = useState('');
  // Voice selection and preview for TTS
  const [voices, setVoices] = useState([]);
  const [voicesLoading, setVoicesLoading] = useState(false);
  const [voicesError, setVoicesError] = useState('');
  const [selectedVoiceId, setSelectedVoiceId] = useState('default');
  const voiceAudioRef = useRef(null);
  const [voicePreviewing, setVoicePreviewing] = useState(false);

  // TTS review step state
  const [needsTtsReview, setNeedsTtsReview] = useState(false);
  const [ttsGeneratedIntro, setTtsGeneratedIntro] = useState(null);
  const [ttsGeneratedOutro, setTtsGeneratedOutro] = useState(null);
  const [renameIntro, setRenameIntro] = useState("");
  const [renameOutro, setRenameOutro] = useState("");
  const [firstTimeUser, setFirstTimeUser] = useState(false);

  // Helper: format media display names (strip hex/uuid prefixes, ext; prettify; clamp at ~25 alphanumerics to end of word)
  const formatMediaDisplayName = (raw, clamp = true) => {
    try {
      let s = String(raw || "");
      // if full object passed
      if (typeof raw === 'object' && raw) {
        s = raw.display_name || raw.original_name || raw.filename || raw.name || raw.id || "";
      }
      // strip path
      s = s.split(/[\\/]/).pop();
      // drop extension
      s = s.replace(/\.[a-z0-9]{2,4}$/i, "");
      // drop leading hex/uuid-like tokens followed by _ or -
      s = s.replace(/^(?:[a-f0-9]{8,}|[a-f0-9-]{8,})[_-]+/i, "");
      // replace separators with spaces
      s = s.replace(/[._-]+/g, " ");
      // trim and normalize spaces
      s = s.trim().replace(/\s+/g, " ");
      // lowercase then capitalize first letter (sentence case)
      s = s.toLowerCase();
      if (s.length) s = s[0].toUpperCase() + s.slice(1);

      if (!clamp) return s;

      // Clamp to last complete word at/over 25 alphanumerics
      let count = 0, end = s.length;
      for (let i = 0; i < s.length; i++) {
        if (/[a-z0-9]/i.test(s[i])) count++;
        if (count >= 25) {
          // move to end of current word
          let j = i + 1;
          while (j < s.length && /[a-z0-9]/i.test(s[j])) j++;
          end = j;
          break;
        }
      }
      const clamped = s.slice(0, end);
      return end < s.length ? `${clamped}…` : clamped;
    } catch {
      return String(raw || "");
    }
  };

  // Helper: find a voice by id across possible schemas
  const getVoiceById = (vid) => {
    if (!vid || vid === 'default') return null;
    const canon = (v) => v?.voice_id || v?.id || v?.name;
    return voices.find(v => canon(v) === vid) || null;
  };

  const previewSelectedVoice = () => {
    try {
      if (voicePreviewing && voiceAudioRef.current) {
        voiceAudioRef.current.pause();
        setVoicePreviewing(false);
        return;
      }
      const v = getVoiceById(selectedVoiceId);
      const url = v?.preview_url || v?.sample_url;
      if (!url) return;
      if (voiceAudioRef.current) { try { voiceAudioRef.current.pause(); } catch {} }
      const a = new Audio(url);
      voiceAudioRef.current = a;
      setVoicePreviewing(true);
      a.onended = () => { setVoicePreviewing(false); };
      a.play().catch(() => setVoicePreviewing(false));
    } catch {
      setVoicePreviewing(false);
    }
  };

  const importFlowSteps = useMemo(() => ([
    { id: 'rss', title: 'Import from RSS' },
    { id: 'confirm', title: 'Confirm import' },
    { id: 'importing', title: 'Importing...' },
    { id: 'analyze', title: 'Analyzing' },
    { id: 'assets', title: 'Assets' },
    { id: 'importSuccess', title: 'Import complete!' },
  ]), []);

  const newFlowSteps = useMemo(() => {
    const nameStep = {
      id: 'yourName',
      title: 'What can we call you?',
      validate: async () => {
        const fn = (firstName || '').trim();
        const ln = (lastName || '').trim();
        if (!fn) { setNameError('First name is required'); return false; }
        setNameError('');
        try {
          const api = makeApi(token);
          await api.patch('/api/auth/users/me/prefs', { first_name: fn, last_name: ln || undefined });
          try { refreshUser?.({ force: true }); } catch {}
        } catch (_) { /* non-fatal */ }
        return true;
      },
      render: () => (
        <div className="grid gap-4">
          <div className="grid grid-cols-4 items-center gap-4">
            <Label htmlFor="firstName" className="text-right">First name<span className="text-red-600">*</span></Label>
            <Input id="firstName" value={firstName} onChange={(e)=>setFirstName(e.target.value)} className="col-span-3" placeholder="e.g., Alex" />
          </div>
          <div className="grid grid-cols-4 items-center gap-4">
            <Label htmlFor="lastName" className="text-right">Last name</Label>
            <Input id="lastName" value={lastName} onChange={(e)=>setLastName(e.target.value)} className="col-span-3" placeholder="(Optional)" />
          </div>
          {nameError && <p className="text-sm text-red-600">{nameError}</p>}
        </div>
      ),
    };

    const choosePathStep = {
      id: 'choosePath',
      title: 'Do you have an existing podcast?',
    };

    const newSteps = [
      nameStep,
      choosePathStep,
      { id: 'showDetails', title: 'About your show' },
      { id: 'format', title: 'Format' },
      { id: 'coverArt', title: 'Podcast Cover Art (optional)' },
      // Optional interstitial: show a one-off page when jumping here after import
      ...(showSkipNotice ? [{ id: 'skipNotice', title: 'Skipping ahead', description: "We imported your show. We'll jump to Step 6 so you can finish setup." }] : []),
      { id: 'introOutro', title: 'Intro & Outro' },
      { id: 'music', title: 'Music (optional)' },
      { id: 'publishCadence', title: 'How often will you publish?' },
      { id: 'publishSchedule', title: 'Publishing days' },
      { id: 'finish', title: 'All done!' },
    ];

    // If we launched from Podcast Manager, the user's name is already known; remove that step
    let filtered = fromManager ? newSteps.filter((s) => s.id !== 'yourName') : newSteps;

    const includeSchedule = (freqUnit !== 'day' && freqUnit !== 'year');
    return includeSchedule ? filtered : filtered.filter((s) => s.id !== 'publishSchedule');
  }, [firstName, lastName, nameError, freqUnit, path, token, refreshUser, fromManager, showSkipNotice]);

  const wizardSteps = useMemo(() => (
    path === 'import' ? importFlowSteps : newFlowSteps
  ), [path, importFlowSteps, newFlowSteps]);

  const introOutroIndex = useMemo(() => {
    const idx = newFlowSteps.findIndex((s) => s.id === 'introOutro');
    return idx >= 0 ? idx : 0;
  }, [newFlowSteps]);

  const stepId = wizardSteps[stepIndex]?.id;
  // Detect if user already has any podcast; if so, show Exit & Discard
  const [hasExistingPodcast, setHasExistingPodcast] = useState(false);
  useEffect(() => {
    (async () => {
      try {
        const data = await makeApi(token).get('/api/podcasts/');
        const items = Array.isArray(data) ? data : (data?.items || []);
        setHasExistingPodcast(items.length > 0);
      } catch (_) { setHasExistingPodcast(false); }
    })();
  }, [token]);

  // If a query param requests a specific step (e.g., step=2), respect it on first mount
  const bootstrappedRef = useRef(false);
  useEffect(() => {
    if (bootstrappedRef.current) return;
    bootstrappedRef.current = true;
    try {
      const url = new URL(window.location.href);
      const fromManager = url.searchParams.get('from') === 'manager';
      const shouldReset = url.searchParams.get('reset') === '1' || url.searchParams.get('reset') === 'true';
      if (shouldReset) {
        try { localStorage.removeItem(STEP_KEY); } catch {}
      }
      const stepParam = url.searchParams.get('step');
      const n = stepParam != null ? parseInt(stepParam, 10) : NaN;
      if (Number.isFinite(n) && n >= 1) {
        // 1-based in the URL; clamp to available steps
        const clamped = Math.min(Math.max(1, n), wizardSteps.length) - 1;
        setStepIndex(clamped);
        // If jumping to step 2 (choosePath), we already have their name. Ensure path remains 'new'.
      } else if (fromManager) {
        // Launching from Podcast Manager: skip step 1 (yourName). Start at choosePath if present, else first step.
        const idx = wizardSteps.findIndex((s) => s.id === 'choosePath');
        setStepIndex(idx >= 0 ? idx : 0);
      }
    } catch {}
  }, [wizardSteps.length]);

  // Clamp restored step to bounds if env flags change shape
  useEffect(() => {
    const maxIndex = Math.max(0, wizardSteps.length - 1);
    if (stepIndex > maxIndex) setStepIndex(maxIndex);
  }, [wizardSteps.length]);

  // Debounce persist of current step index (≈350ms)
  useEffect(() => {
    if (stepSaveTimer.current) clearTimeout(stepSaveTimer.current);
    stepSaveTimer.current = setTimeout(() => {
      try { localStorage.setItem(STEP_KEY, String(stepIndex)); } catch {}
    }, 350);
    return () => { if (stepSaveTimer.current) clearTimeout(stepSaveTimer.current); };
  }, [stepIndex]);

  // Listen for AI-generated cover images from Mike Czech
  useEffect(() => {
    const handleAiGeneratedCover = (event) => {
      const file = event.detail?.file;
      if (file && file instanceof File) {
        // Update formData with the AI-generated cover
        setFormData(prev => ({ ...prev, coverArt: file }));
        setCoverCrop(null); // Reset crop for new image
        
        // Auto-advance to cover art step if not already there
        if (stepId !== 'coverArt') {
          const coverStepIndex = wizardSteps.findIndex(s => s.id === 'coverArt');
          if (coverStepIndex >= 0) {
            setStepIndex(coverStepIndex);
          }
        }
      }
    };
    
    window.addEventListener('ai-generated-cover', handleAiGeneratedCover);
    return () => window.removeEventListener('ai-generated-cover', handleAiGeneratedCover);
  }, [stepId, wizardSteps]);

  // When on the music step, fetch assets once (global music only)
  useEffect(() => {
    if (stepId === 'music' && musicAssets.length <= 1 && !musicLoading) {
      setMusicLoading(true);
      (async () => {
        try {
          const api = makeApi(token);
          // Fetch global music only for onboarding
          const data = await api.get('/api/music/assets?scope=global');
          const assets = Array.isArray(data?.assets) ? data.assets : [];
          setMusicAssets([NO_MUSIC_OPTION, ...assets]);
        } catch (_) {
          setMusicAssets([NO_MUSIC_OPTION]);
        } finally {
          setMusicLoading(false);
        }
      })();
    }
    // cleanup preview when leaving music step
    if (stepId !== 'music' && audioRef.current) {
      try { audioRef.current.pause(); } catch {}
      audioRef.current = null;
      setMusicPreviewing(null);
    }
  }, [stepId, musicAssets.length, musicLoading]);

  // Load voices and saved intro/outro media when entering intro/outro step
  useEffect(() => {
    if (stepId === 'introOutro' && !voicesLoading && voices.length === 0) {
      setVoicesLoading(true); setVoicesError('');
      (async()=>{
        try {
          const data = await makeApi(token).get('/api/elevenlabs/voices?size=12');
          const items = (data && (data.items || data.voices)) || [];
          setVoices(items);
          if (items.length > 0 && (!selectedVoiceId || selectedVoiceId === 'default')) {
            const first = items[0];
            setSelectedVoiceId(first.voice_id || first.id || first.name || 'default');
          }
        } catch (e) {
          setVoicesError('Voice list unavailable; using a default voice.');
        } finally {
          setVoicesLoading(false);
        }
      })();
    }
    // Load user's saved intro/outro items
    if (stepId === 'introOutro' && introOptions.length === 0 && outroOptions.length === 0) {
      (async () => {
        try {
          const media = await makeApi(token).get('/api/media/');
          const asArray = Array.isArray(media) ? media : (media?.items || []);
          const intros = asArray.filter(m => (m?.category || '').toLowerCase() === 'intro');
          const outros = asArray.filter(m => (m?.category || '').toLowerCase() === 'outro');
          setIntroOptions(intros);
          setOutroOptions(outros);
          // Default to first existing if available
          if (intros.length > 0) {
            const first = intros[0];
            setSelectedIntroId(String(first.id || first.filename));
            setIntroAsset(first);
            setIntroMode(prev => (prev === 'tts' || prev === 'upload') ? 'existing' : prev);
          }
          if (outros.length > 0) {
            const first = outros[0];
            setSelectedOutroId(String(first.id || first.filename));
            setOutroAsset(first);
            setOutroMode(prev => (prev === 'tts' || prev === 'upload') ? 'existing' : prev);
          }
        } catch (_) { /* ignore */ }
      })();
    }
    if (stepId !== 'introOutro' && voiceAudioRef.current) {
      try { voiceAudioRef.current.pause(); } catch {}
      setVoicePreviewing(false);
    }
    if (stepId !== 'introOutro' && ioAudioRef.current) {
      try { ioAudioRef.current.pause(); } catch {}
      setIntroPreviewing(false);
      setOutroPreviewing(false);
    }
  }, [stepId, voicesLoading, voices.length, selectedVoiceId, token, introOptions.length, outroOptions.length]);

  // Detect brand new user (no podcasts and no intro/outro items) to disable the 60s free rule
  useEffect(() => {
    if (stepId !== 'introOutro') return;
    (async () => {
      try {
        const podcasts = await makeApi(token).get('/api/podcasts/');
        const pItems = Array.isArray(podcasts) ? podcasts : (podcasts?.items || []);
        const media = await makeApi(token).get('/api/media/');
        const mItems = Array.isArray(media) ? media : (media?.items || []);
        const hasIntro = mItems.some(m => (m?.category || '').toLowerCase() === 'intro');
        const hasOutro = mItems.some(m => (m?.category || '').toLowerCase() === 'outro');
        setFirstTimeUser((pItems.length === 0) && !hasIntro && !hasOutro);
      } catch {
        setFirstTimeUser(false);
      }
    })();
  }, [stepId, token]);

  const toggleIoPreview = (kind) => {
    try {
      let asset = null;
      if (needsTtsReview) {
        asset = (kind === 'intro') ? (ttsGeneratedIntro || introAsset) : (ttsGeneratedOutro || outroAsset);
      } else {
        asset = kind === 'intro'
          ? (introOptions.find(x => String(x.id || x.filename) === selectedIntroId) || introAsset || null)
          : (outroOptions.find(x => String(x.id || x.filename) === selectedOutroId) || outroAsset || null);
      }
      if (!asset) return;

      // Resolve preview URL exactly like MediaLibrary does (which works!)
      const resolvePreviewUrl = async () => {
        if (!asset?.id) {
          console.error('[Onboarding] Cannot resolve preview URL - asset has no ID:', asset);
          return null;
        }
        try {
          const api = makeApi(token);
          const res = await api.get(`/api/media/preview?id=${encodeURIComponent(asset.id)}&resolve=true`);
          const url = res?.path || res?.url;
          if (!url) {
            console.error('[Onboarding] Preview endpoint returned no URL for ID:', asset.id, 'Response:', res);
          }
          return url || null;
        } catch (err) {
          console.error('[Onboarding] Failed to resolve preview URL for ID:', asset.id, 'Error:', err);
          toast?.({ variant: 'destructive', title: 'Preview failed', description: err?.message || 'Could not resolve preview URL' });
          return null;
        }
      };

      const run = async () => {
        let url = await resolvePreviewUrl();
        if (!url) { toast?.({ title: 'No audio', description: 'Could not determine preview URL', variant: 'destructive' }); return; }
        // Normalize relative paths (so vite proxy / same-origin cookies work)
        if (!/^https?:\/\//i.test(url)) url = buildApiUrl(url.startsWith('/') ? url : `/${url}`);

        const isPlaying = kind === 'intro' ? introPreviewing : outroPreviewing;
        if (isPlaying && ioAudioRef.current) {
          try { ioAudioRef.current.pause(); } catch {}
          ioAudioRef.current = null;
          setIntroPreviewing(false); setOutroPreviewing(false);
          return;
        }
        // Stop any current
        if (ioAudioRef.current) { try { ioAudioRef.current.pause(); } catch {} }
        const a = new Audio(url);
        // Only set crossOrigin when the media is served by our API origin, which responds with CORS headers.
        // For third-party or signed GCS URLs without CORS headers, leaving crossOrigin unset avoids load failures.
        try {
          const apiBase = buildApiUrl('/')
            .replace(/\/+$|^https?:\/\/|\/$/g, '') // strip protocol and trailing slash
            .replace(/^[^/]*\/\//, '');
          const apiHost = apiBase.includes('//') ? new URL(apiBase).host : apiBase;
          const mediaHost = new URL(url, window.location.origin).host;
          if (apiHost && mediaHost && apiHost === mediaHost) {
            a.crossOrigin = 'anonymous';
          }
        } catch {}
        ioAudioRef.current = a;
        setIntroPreviewing(kind === 'intro');
        setOutroPreviewing(kind === 'outro');
        a.onended = () => { setIntroPreviewing(false); setOutroPreviewing(false); };
        a.onerror = () => { setIntroPreviewing(false); setOutroPreviewing(false); toast?.({ title: 'Playback failed', description: 'Could not play audio preview', variant: 'destructive' }); };
        a.play().catch(err => {
          setIntroPreviewing(false); setOutroPreviewing(false);
          toast?.({ title: 'Playback blocked', description: err?.message || 'User gesture or CORS issue', variant: 'destructive' });
        });
      };
      run();
    } catch {
      setIntroPreviewing(false); setOutroPreviewing(false);
    }
  };

  const togglePreview = (asset) => {
    if (!asset || asset.id === 'none') return;
    const url = asset.preview_url || asset.url || asset.filename;
    if (!url) return;
    // stop current
    if (musicPreviewing === asset.id) {
      try { audioRef.current?.pause(); } catch {}
      audioRef.current = null;
      setMusicPreviewing(null);
      return;
    }
    try {
      if (audioRef.current) { try { audioRef.current.pause(); } catch {} }
      const a = new Audio(url);
      audioRef.current = a;
      setMusicPreviewing(asset.id);
      const stopAt = 20; // seconds
      const onTick = () => {
        if (!a || isNaN(a.currentTime)) return;
        if (a.currentTime >= stopAt) {
          a.pause();
          setMusicPreviewing(null);
          a.removeEventListener('timeupdate', onTick);
        }
      };
      a.addEventListener('timeupdate', onTick);
      a.onended = () => { setMusicPreviewing(null); try { a.removeEventListener('timeupdate', onTick);} catch {} };
      a.play().catch(() => { setMusicPreviewing(null); });
    } catch {
      setMusicPreviewing(null);
    }
  };

  const handleChange = (e) => {
    const { id, value, files } = e.target;
    setFormData((prev) => ({ ...prev, [id]: files ? files[0] : value }));
  };



  // Exit & Discard
  const handleExitDiscard = () => {
    if (!hasExistingPodcast) return;
    // Confirm only if user reached Intro & Outro or later
    const idxIntro = newFlowSteps.findIndex((s) => s.id === 'introOutro');
    const atOrBeyondIntro = idxIntro >= 0 && stepIndex >= idxIntro;
    if (atOrBeyondIntro) {
      const ok = window.confirm('Exit and discard your onboarding changes?');
      if (!ok) return;
    }
    try { localStorage.removeItem('ppp.onboarding.step'); } catch {}
    try { window.location.replace('/?onboarding=0'); } catch {}
  };

  async function generateOrUploadTTS(kind, mode, script, file, recordedAsset) {
    // kind: 'intro' | 'outro'
    // mode: 'tts' | 'upload' | 'record' | 'existing'
    try {
      // Check for authentication token before making any API calls
      if (!token) {
        const errorMsg = 'Your session has expired. Please refresh the page (F5 or Ctrl+R) and sign in again.';
        toast({ 
          title: 'Session Expired', 
          description: errorMsg, 
          variant: 'destructive' 
        });
        throw new Error(errorMsg);
      }
      
      if (mode === 'record') {
        // Recording already uploaded via VoiceRecorder component
        return recordedAsset || null;
      }
      if (mode === 'upload') {
        if (!file) return null;
        const fd = new FormData();
        fd.append('files', file);
        const data = await makeApi(token).raw(`/api/media/upload/${kind}`, { method: 'POST', body: fd });
        if (Array.isArray(data) && data.length > 0) return data[0];
        return null;
      } else {
        const body = { text: (script || '').trim() || (kind==='intro' ? 'Welcome to my podcast!' : 'Thank you for listening and see you next time!'), category: kind };
        if (selectedVoiceId && selectedVoiceId !== 'default') body.voice_id = selectedVoiceId;
        if (firstTimeUser) body.free_override = true;
        const item = await makeApi(token).post('/api/media/tts', body);
        console.log('[Onboarding] TTS response for', kind, ':', item);
        console.log('[Onboarding] TTS response keys:', item ? Object.keys(item) : 'null');
        console.log('[Onboarding] TTS response id:', item?.id, 'filename:', item?.filename, 'category:', item?.category);
        if (!item?.id) {
          console.error('[Onboarding] TTS response missing ID! Full object:', JSON.stringify(item, null, 2));
        }
        return item || null;
      }
    } catch (e) {
      // Enhanced error handling with specific messages for auth failures
      const status = e?.status;
      let errorMsg = e?.message || String(e);
      
      if (status === 401) {
        errorMsg = 'Your session has expired. Please refresh the page (F5 or Ctrl+R) and sign in again.';
      } else if (status === 403) {
        errorMsg = 'Permission denied. You may not have access to this feature.';
      } else if (status === 429) {
        errorMsg = e?.detail?.message || 'Too many requests. Please wait a moment and try again.';
      }
      
      try { 
        toast({ 
          title: `Could not prepare ${kind}`, 
          description: errorMsg, 
          variant: 'destructive' 
        }); 
      } catch {}
      return null;
    }
  }

  async function handleFinish() {
    try {
      setSaving(true);
      // Determine whether to create a new podcast or use an existing one
      let targetPodcast = null;
      let existingShows = [];
      try {
        const data = await makeApi(token).get('/api/podcasts/');
        existingShows = Array.isArray(data) ? data : (data?.items || []);
      } catch (_) { existingShows = []; }
      if (formData.elevenlabsApiKey) {
        try {
          await makeApi(token).put('/api/users/me/elevenlabs-key', { api_key: formData.elevenlabsApiKey });
        } catch {}
      }
      if (path === 'new' && existingShows.length === 0) {
        // Validate podcast name and description before attempting to create
        const nameClean = (formData.podcastName || '').trim();
        const descClean = (formData.podcastDescription || '').trim();
        if (!nameClean || nameClean.length < 4) {
          throw new Error('Podcast name must be at least 4 characters.');
        }
        if (!descClean) {
          throw new Error('Podcast description is required.');
        }
        
        const podcastPayload = new FormData();
        podcastPayload.append('name', nameClean);
        podcastPayload.append('description', descClean);
        if (formData.coverArt) {
          try {
            const blob = await coverCropperRef.current?.getProcessedBlob?.();
            if (blob) {
              const file = new File([blob], 'cover.jpg', { type: 'image/jpeg' });
              podcastPayload.append('cover_image', file);
            } else {
              podcastPayload.append('cover_image', formData.coverArt);
            }
          } catch {
            podcastPayload.append('cover_image', formData.coverArt);
          }
        }
        const createdPodcast = await makeApi(token).raw('/api/podcasts/', { method: 'POST', body: podcastPayload });
        if (!createdPodcast || !createdPodcast.id) {
          let detail = '';
          try { detail = (createdPodcast && createdPodcast.detail) ? createdPodcast.detail : JSON.stringify(createdPodcast || {}); } catch {}
          throw new Error(detail || 'Failed to create the podcast show.');
        }
        targetPodcast = createdPodcast;
        try { toast({ title: 'Great!', description: 'Your new podcast show has been created.' }); } catch {}

        // Create a default template "My First Template" with intro/outro segments and background music rules
        try {
          console.log('[Onboarding] Creating template with:', {
            introAsset,
            outroAsset,
            introFilename: introAsset?.filename,
            outroFilename: outroAsset?.filename
          });
          const segments = [];
          if (introAsset?.filename) {
            console.log('[Onboarding] Adding intro segment with filename:', introAsset.filename);
            segments.push({ segment_type: 'intro', source: { source_type: 'static', filename: introAsset.filename } });
          } else {
            console.warn('[Onboarding] NO intro added to template - introAsset:', introAsset);
          }
          // Always include a content segment placeholder using TTS (empty script) for broad compatibility
          segments.push({ segment_type: 'content', source: { source_type: 'tts', script: '', voice_id: (selectedVoiceId && selectedVoiceId !== 'default') ? selectedVoiceId : 'default' } });
          if (outroAsset?.filename) {
            console.log('[Onboarding] Adding outro segment with filename:', outroAsset.filename);
            segments.push({ segment_type: 'outro', source: { source_type: 'static', filename: outroAsset.filename } });
          } else {
            console.warn('[Onboarding] NO outro added to template - outroAsset:', outroAsset);
          }
          // Compose background music rules if a track was chosen
          const musicRules = [];
          const selectedMusic = (musicAssets || []).find(a => a.id === musicChoice && a.id !== 'none');
          if (selectedMusic && selectedMusic.id) {
            musicRules.push({
              music_asset_id: selectedMusic.id,
              apply_to_segments: ['intro'],
              start_offset_s: 0,
              end_offset_s: 1,
              fade_in_s: 1.5,
              fade_out_s: 2.0,
              volume_db: -4,
            });
            musicRules.push({
              music_asset_id: selectedMusic.id,
              apply_to_segments: ['outro'],
              start_offset_s: -10,
              end_offset_s: 0,
              fade_in_s: 3.0,
              fade_out_s: 1.0,
              volume_db: -4,
            });
          }

          // Choose target podcast id: newly created or last existing
          const chosen = targetPodcast || (existingShows.length > 0 ? existingShows[existingShows.length - 1] : null);
          const templatePayload = {
            name: 'My First Template',
            podcast_id: chosen?.id,
            segments,
            background_music_rules: musicRules,
            timing: { content_start_offset_s: 0, outro_start_offset_s: 0 },
            is_active: true,
            default_elevenlabs_voice_id: (selectedVoiceId && selectedVoiceId !== 'default') ? selectedVoiceId : null,
          };
          try { await makeApi(token).post('/api/templates/', templatePayload); } catch (e) {
            // Non-fatal: user can still proceed; backend prevents last-template deletes
            try { toast({ title: 'Template not saved', description: e?.message || 'We could not save your default template.', variant: 'destructive' }); } catch {}
          }
        } catch (_) {}
      } else {
        // Import or manager path: create a default template for the most recent existing show
        const chosen = existingShows.length > 0 ? existingShows[existingShows.length - 1] : null;
        if (chosen) {
          try {
            const segments = [];
            if (introAsset?.filename) segments.push({ segment_type: 'intro', source: { source_type: 'static', filename: introAsset.filename } });
            segments.push({ segment_type: 'content', source: { source_type: 'tts', script: '', voice_id: (selectedVoiceId && selectedVoiceId !== 'default') ? selectedVoiceId : 'default' } });
            if (outroAsset?.filename) segments.push({ segment_type: 'outro', source: { source_type: 'static', filename: outroAsset.filename } });
            const templatePayload = { name: 'My First Template', podcast_id: chosen.id, segments, background_music_rules: [], timing: { content_start_offset_s: 0, outro_start_offset_s: 0 }, is_active: true, default_elevenlabs_voice_id: (selectedVoiceId && selectedVoiceId !== 'default') ? selectedVoiceId : null };
            await makeApi(token).post('/api/templates/', templatePayload);
          } catch (e) {
            try { toast({ title: 'Template not saved', description: e?.message || 'We could not save your default template.', variant: 'destructive' }); } catch {}
          }
        }
        try { toast({ title: 'All done!', description: 'Your show has been imported.' }); } catch {}
      }
      // Mark onboarding complete and avoid reopening wizard if podcast count hasn't propagated yet
      try {
        localStorage.removeItem('ppp.onboarding.step');
        localStorage.setItem('ppp.onboarding.completed', '1');
      } catch {}
      // Redirect with flag to skip onboarding rerender
      try { window.location.replace('/?onboarding=0'); } catch {}
    } catch (error) {
      try { toast({ title: 'An Error Occurred', description: error.message, variant: 'destructive' }); } catch {}
    } finally {
      setSaving(false);
    }
  }

  // Map each stepId to a render function
  const steps = wizardSteps.map((s, i) => ({
    id: s.id,
    title: s.title,
    description: s.description,
    tip: (
      s.id === 'yourName' ? "We'll use this to personalize your dashboard." :
  s.id === 'choosePath' ? 'If you have an existing podcast, import it here.' :
      s.id === 'showDetails' ? 'Short and clear works best.' :
  s.id === 'format' ? 'This is for your reference.' :
  s.id === 'coverArt' ? 'No artwork yet? You can skip this for now.' :
  s.id === 'introOutro' ? 'Start with our default scripts or upload your own audio.' :
  s.id === 'music' ? 'This is background music for your intro and outro. It can be changed or removed at any time.' :
  s.id === 'publishCadence' ? 'We ask to help keep you on track for publishing consistently' :
  s.id === 'publishSchedule' ? 'Consistency is more important than volume for a successful podcast' :
      s.id === 'rss' ? 'Paste your feed URL.' :
      s.id === 'analyze' ? "We'll bring over what we can, and you can tidy later." :
      s.id === 'assets' ? "We'll bring over what we can, and you can tidy later." :
      s.id === 'finish' ? "There's a short tour next if you'd like it." : ''
    ),
    render: () => {
      switch (s.id) {
        case 'yourName':
          // If launched from Podcast Manager, skip rendering this step and auto-advance
          if ((new URLSearchParams(window.location.search).get('from') === 'manager')) {
            return (
              <div className="text-sm text-muted-foreground">Skipping…</div>
            );
          }
          return (
            <div className="grid gap-4">
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="firstName" className="text-right">First name<span className="text-red-600">*</span></Label>
                <Input id="firstName" value={firstName} onChange={(e)=>setFirstName(e.target.value)} className="col-span-3" placeholder="e.g., Alex" />
              </div>
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="lastName" className="text-right">Last name</Label>
                <Input id="lastName" value={lastName} onChange={(e)=>setLastName(e.target.value)} className="col-span-3" placeholder="(Optional)" />
              </div>
              {nameError && <p className="text-sm text-red-600">{nameError}</p>}
            </div>
          );
  case 'choosePath':
          return (
            <div className="space-y-4">
              <div className="flex gap-3">
                <Button
                  variant={path === 'new' ? 'default' : 'outline'}
                  onClick={() => { setPath('new'); setStepIndex(i + 1); }}
                >Start new</Button>
                <Button
                  variant={path === 'import' ? 'default' : 'outline'}
                  onClick={() => { setPath('import'); setStepIndex(0); }}
                >Import existing</Button>
              </div>
              <p className="text-sm text-muted-foreground">Don't worry about breaking anything, and we're going to save as you go.</p>
            </div>
          );
        case 'showDetails':
          return (
            <div className="grid gap-4">
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="podcastName" className="text-right">Name<span className="text-red-600">*</span></Label>
                <div className="col-span-3">
                  <Input id="podcastName" value={formData.podcastName} onChange={handleChange} placeholder="e.g., 'The Morning Cup'" />
                  {((formData.podcastName||'').trim().length > 0 && (formData.podcastName||'').trim().length < 4) && (
                    <p className="text-xs text-red-600 mt-1">Name must be at least 4 characters</p>
                  )}
                </div>
              </div>
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="podcastDescription" className="text-right">Description<span className="text-red-600">*</span></Label>
                <Textarea id="podcastDescription" value={formData.podcastDescription} onChange={handleChange} className="col-span-3" placeholder="e.g., 'A daily podcast about the latest tech news.'" />
              </div>
            </div>
          );
        case 'format':
          return (
            <div className="space-y-3">
              <div className="grid gap-3">
                {FORMATS.map(f => (
                  <label key={f.key} className={`border rounded p-3 cursor-pointer flex gap-3 ${formatKey===f.key? 'border-blue-600 ring-1 ring-blue-400':'hover:border-gray-400'}`}>
                    <input type="radio" name="format" className="mt-1" value={f.key} checked={formatKey===f.key} onChange={() => setFormatKey(f.key)} />
                    <span><span className="font-medium">{f.label}</span><br/><span className="text-xs text-muted-foreground">{f.desc}</span></span>
                  </label>
                ))}
              </div>
            </div>
          );
        case 'coverArt':
          return (
            <div className="space-y-4">
              {!formData.coverArt && (
                <div className="space-y-2">
                  <Label htmlFor="coverArt" className="">Image</Label>
                  <div>
                    <Input
                      ref={coverArtInputRef}
                      id="coverArt"
                      type="file"
                      onChange={handleChange}
                      accept="image/png, image/jpeg,image/jpg"
                    />
                    <p className="text-xs text-muted-foreground mt-2">You can resize and position your image below.</p>
                  </div>
                  <div className="flex items-center gap-2 mt-2">
                    <input id="skipCoverNow" type="checkbox" checked={skipCoverNow} onChange={(e)=> setSkipCoverNow(e.target.checked)} />
                    <Label htmlFor="skipCoverNow">Skip this for now</Label>
                  </div>
                </div>
              )}
              {formData.coverArt && (
                <div className="space-y-3">
                  <div className="grid grid-cols-4 items-start gap-4">
                    <Label className="text-right">Adjust</Label>
                    <div className="col-span-3">
                      <CoverCropper
                        ref={coverCropperRef}
                        sourceFile={formData.coverArt}
                        existingUrl={null}
                        value={coverCrop}
                        onChange={(s)=> setCoverCrop(s)}
                        onModeChange={(m)=> setCoverMode(m)}
                      />
                      <div className="flex gap-2 mt-2">
                        <Button
                          type="button"
                          variant="outline"
                          onClick={()=>{ setFormData(prev=>({...prev, coverArt:null})); setCoverCrop(null); }}
                        >
                          Remove
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        case 'introOutro':
          return (
            <div className="space-y-6">
              <div className="space-y-2">
                <div className="font-medium">Intro</div>
                <div className="flex items-center gap-2">
                  <Select value={introMode} onValueChange={(value) => setIntroMode(value)}>
                    <SelectTrigger className="w-[280px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {introOptions.length > 0 && (
                        <SelectItem value="existing">
                          Use Current Intro
                        </SelectItem>
                      )}
                      <SelectItem value="record">
                        <span className="flex items-center gap-2">
                          <Mic className="h-4 w-4" />
                          Record Now
                          <span className="ml-1 px-1.5 py-0.5 bg-green-100 text-green-800 text-xs rounded font-medium">Easy!</span>
                        </span>
                      </SelectItem>
                      <SelectItem value="tts">Generate with AI Voice</SelectItem>
                      <SelectItem value="upload">Upload a File</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {introMode==='existing' && (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      aria-label={introPreviewing? 'Pause preview':'Play preview'}
                      onClick={()=>toggleIoPreview('intro')}
                      className={`inline-flex items-center justify-center h-8 w-8 rounded border ${introPreviewing? 'bg-blue-600 text-white border-blue-600':'bg-white text-foreground border-muted-foreground/30'}`}
                      title="Preview"
                    >
                      {introPreviewing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                    </button>
                    <select
                      className="border rounded p-2 min-w-[220px]"
                      value={selectedIntroId}
                      onChange={(e)=>{
                        const v = e.target.value;
                        setSelectedIntroId(v);
                        const found = introOptions.find(x => String(x.id || x.filename) === v) || null;
                        setIntroAsset(found);
                      }}
                    >
                      {introOptions.map((itm)=>{
                        const key = String(itm?.id || itm?.filename || 'unknown');
                        const base = itm?.friendly_name || itm?.display_name || itm?.original_name || itm?.filename || 'Intro';
                        return <option key={key} value={key}>{formatMediaDisplayName(base, true)}</option>;
                      })}
                    </select>
                  </div>
                )}
                {introMode==='record' && (
                  <VoiceRecorder
                    type="intro"
                    token={token}
                    maxDuration={60}
                    largeText={largeText}
                    userFirstName={firstName}
                    refreshUser={refreshUser}
                    onRecordingComplete={(mediaItem) => {
                      setIntroAsset(mediaItem);
                      // Add to intro options if not already there
                      setIntroOptions(prev => {
                        const exists = prev.some(x => (x.id || x.filename) === (mediaItem.id || mediaItem.filename));
                        return exists ? prev : [...prev, mediaItem];
                      });
                      setSelectedIntroId(String(mediaItem.id || mediaItem.filename));
                      // Switch to "existing" mode to show preview
                      setIntroMode('existing');
                      toast({ 
                        title: "Perfect!", 
                        description: "Your intro has been recorded. Preview it below!" 
                      });
                    }}
                  />
                )}
                {introMode==='tts' ? (
                  <Textarea value={introScript} onChange={(e)=> setIntroScript(e.target.value)} placeholder="Welcome to my podcast!" />
                ) : (
                  introMode==='upload' ? <Input type="file" accept="audio/*" onChange={(e)=> setIntroFile(e.target.files?.[0] || null)} /> : null
                )}
                {/* Prepared helper removed per request */}
              </div>
              <div className="space-y-2">
                <div className="font-medium">Outro</div>
                <div className="flex items-center gap-2">
                  <Select value={outroMode} onValueChange={(value) => setOutroMode(value)}>
                    <SelectTrigger className="w-[280px]">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {outroOptions.length > 0 && (
                        <SelectItem value="existing">
                          Use Current Outro
                        </SelectItem>
                      )}
                      <SelectItem value="record">
                        <span className="flex items-center gap-2">
                          <Mic className="h-4 w-4" />
                          Record Now
                          <span className="ml-1 px-1.5 py-0.5 bg-green-100 text-green-800 text-xs rounded font-medium">Easy!</span>
                        </span>
                      </SelectItem>
                      <SelectItem value="tts">Generate with AI Voice</SelectItem>
                      <SelectItem value="upload">Upload a File</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                {outroMode==='existing' && (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      aria-label={outroPreviewing? 'Pause preview':'Play preview'}
                      onClick={()=>toggleIoPreview('outro')}
                      className={`inline-flex items-center justify-center h-8 w-8 rounded border ${outroPreviewing? 'bg-blue-600 text-white border-blue-600':'bg-white text-foreground border-muted-foreground/30'}`}
                      title="Preview"
                    >
                      {outroPreviewing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                    </button>
                    <select
                      className="border rounded p-2 min-w-[220px]"
                      value={selectedOutroId}
                      onChange={(e)=>{
                        const v = e.target.value;
                        setSelectedOutroId(v);
                        const found = outroOptions.find(x => String(x.id || x.filename) === v) || null;
                        setOutroAsset(found);
                      }}
                    >
                      {outroOptions.map((itm)=>{
                        const key = String(itm?.id || itm?.filename || 'unknown');
                        const base = itm?.friendly_name || itm?.display_name || itm?.original_name || itm?.filename || 'Outro';
                        return <option key={key} value={key}>{formatMediaDisplayName(base, true)}</option>;
                      })}
                    </select>
                  </div>
                )}
                {outroMode==='record' && (
                  <VoiceRecorder
                    type="outro"
                    token={token}
                    maxDuration={60}
                    largeText={largeText}
                    userFirstName={firstName}
                    refreshUser={refreshUser}
                    onRecordingComplete={(mediaItem) => {
                      setOutroAsset(mediaItem);
                      // Add to outro options if not already there
                      setOutroOptions(prev => {
                        const exists = prev.some(x => (x.id || x.filename) === (mediaItem.id || mediaItem.filename));
                        return exists ? prev : [...prev, mediaItem];
                      });
                      setSelectedOutroId(String(mediaItem.id || mediaItem.filename));
                      // Switch to "existing" mode to show preview
                      setOutroMode('existing');
                      toast({ 
                        title: "Perfect!", 
                        description: "Your outro has been recorded. Preview it below!" 
                      });
                    }}
                  />
                )}
                {outroMode==='tts' ? (
                  <Textarea value={outroScript} onChange={(e)=> setOutroScript(e.target.value)} placeholder="Thank you for listening and see you next time!" />
                ) : (
                  outroMode==='upload' ? <Input type="file" accept="audio/*" onChange={(e)=> setOutroFile(e.target.files?.[0] || null)} /> : null
                )}
                {/* Prepared helper removed per request */}
              </div>
              {(introMode === 'tts' || outroMode === 'tts') && (
                <div className="space-y-2">
                  <div className="space-y-1">
                    <Label className="">Voice</Label>
                    <div className="flex items-center gap-2">
                      <select className="border rounded p-2 min-w-[220px]" value={selectedVoiceId} onChange={(e)=> setSelectedVoiceId(e.target.value)} disabled={voicesLoading || (voices?.length||0)===0}>
                        <option value="default">Default</option>
                        {voices.map((v)=>{
                          const id = v.voice_id || v.id || v.name;
                          const label = v.name || v.label || id;
                          return <option key={id} value={id}>{label}</option>;
                        })}
                      </select>
                      <Button type="button" variant="outline" onClick={previewSelectedVoice} disabled={voicesLoading || !getVoiceById(selectedVoiceId)?.preview_url}>
                        {voicePreviewing ? <Pause className="w-4 h-4 mr-2"/> : <Play className="w-4 h-4 mr-2"/>}
                        Preview
                      </Button>
                    </div>
                  </div>
                  {voicesLoading && <div className="text-xs text-muted-foreground">Loading voices…</div>}
                  {voicesError && <div className="text-xs text-yellow-700">{voicesError}</div>}
                </div>
              )}
              <p className="text-xs text-muted-foreground">We’ll create simple defaults if you leave the scripts unchanged.</p>
            </div>
          );
        case 'music':
          return (
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                {musicLoading ? 'Loading music...' : 'Pick a track or choose "No Music".'}
              </div>
              <div className="grid gap-2">
                {musicAssets.map(a => {
                  const canPreview = !!(a && a.id !== 'none' && (a.preview_url || a.url || a.filename));
                  const isActive = musicChoice === a.id;
                  const isPreviewing = musicPreviewing === a.id;
                  return (
                    <div key={a.id} className={`flex items-center gap-3 p-2 rounded border ${isActive? 'border-blue-600 bg-blue-50':'bg-card hover:border-muted-foreground/30'}`}>
                      <button
                        type="button"
                        aria-label={isPreviewing? 'Pause preview':'Play preview'}
                        disabled={!canPreview}
                        onClick={() => canPreview && togglePreview(a)}
                        className={`inline-flex items-center justify-center h-8 w-8 rounded border ${isPreviewing? 'bg-blue-600 text-white border-blue-600':'bg-white text-foreground border-muted-foreground/30'} disabled:opacity-50`}
                        title={canPreview? 'Preview 20s':'Preview not available'}
                      >
                        {isPreviewing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                      </button>
                      <label className="flex items-center gap-3 flex-1 cursor-pointer">
                        <input type="radio" name="music" value={a.id} checked={isActive} onChange={() => setMusicChoice(a.id)} />
                        <div className="flex-1">
                          <div className="text-sm font-medium">{a.display_name}</div>
                          {a.mood_tags && a.mood_tags.length > 0 && (
                            <div className="text-xs text-muted-foreground">{a.mood_tags.slice(0,3).join(', ')}</div>
                          )}
                        </div>
                      </label>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        
        case 'publishDay':
          return null;
        case 'publishCadence':
          return (
            <div className="space-y-4">
              <div className="flex items-center gap-2">
                <span className="text-sm">I want to publish</span>
                <Input type="number" min={1} value={freqCount} onChange={(e)=> setFreqCount(Math.max(1, parseInt(e.target.value||'1',10) || 1))} className="w-20" />
                <span className="text-sm">time(s) every</span>
                <select className="border rounded p-2" value={freqUnit} onChange={(e)=> setFreqUnit(e.target.value)}>
                  <option value="" disabled>select...</option>
                  <option value="day">day</option>
                  <option value="week">week</option>
                  <option value="bi-weekly">bi-weekly</option>
                  <option value="month">month</option>
                  <option value="year">year</option>
                </select>
              </div>
              {cadenceError && <p className="text-sm text-red-600">{cadenceError}</p>}
              <p className="text-xs text-muted-foreground">We'll tailor the next step based on this.</p>
            </div>
          );
        case 'publishSchedule':
          if (freqUnit === 'week') {
            const WEEKDAYS = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"];
            const toggleDay = (d) => setSelectedWeekdays((prev)=> prev.includes(d) ? prev.filter(x=>x!==d) : [...prev, d]);
            return (
              <div className="space-y-2">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                  {WEEKDAYS.map(d => (
                    <button type="button" key={d} onClick={()=>toggleDay(d)} className={`border rounded p-2 text-center ${selectedWeekdays.includes(d)?'border-blue-600 ring-1 ring-blue-400':'hover:border-gray-400'}`}>{d}</button>
                  ))}
                </div>
                <div className="flex items-center gap-2 mt-2">
                  <input id="notSureSchedule" type="checkbox" checked={notSureSchedule} onChange={(e)=> setNotSureSchedule(e.target.checked)} />
                  <Label htmlFor="notSureSchedule">I'm not sure yet</Label>
                </div>
                {/* Helper text removed per spec */}
              </div>
            );
          }
          // bi-weekly or month: calendar picker that hides past days and carries over end-of-month into next month if only same-week days remain
          const today = (() => { const t = new Date(); return new Date(t.getFullYear(), t.getMonth(), t.getDate()); })();
          const startOfThisMonth = new Date(today.getFullYear(), today.getMonth(), 1);
          const startOfNextMonth = new Date(today.getFullYear(), today.getMonth()+1, 1);
          const endOfThisMonth = new Date(today.getFullYear(), today.getMonth()+1, 0);
          const nextMonthWeekStart = (() => {
            // Sunday start of the week that contains the first of next month
            const d = new Date(startOfNextMonth);
            const dow = d.getDay(); // 0=Sun..6=Sat
            const start = new Date(d);
            start.setDate(d.getDate() - dow);
            return start;
          })();
          const nextMonthWeekEnd = new Date(nextMonthWeekStart.getFullYear(), nextMonthWeekStart.getMonth(), nextMonthWeekStart.getDate()+6);

          // Collect remaining days in current month (>= today)
          const remainingThisMonthDates = (() => {
            const arr = [];
            for (let d = today.getDate(); d <= endOfThisMonth.getDate(); d++) {
              arr.push(new Date(today.getFullYear(), today.getMonth(), d));
            }
            return arr;
          })();
          // If all remaining days fall within the same week as next month's 1st, drop current month and carry them over
          const dropCurrentMonth = remainingThisMonthDates.length > 0 && remainingThisMonthDates.every(dt => dt >= nextMonthWeekStart && dt <= nextMonthWeekEnd);
          const months = dropCurrentMonth ? [startOfNextMonth] : [startOfThisMonth, startOfNextMonth];

          const daysInMonth = (y,m)=> new Date(y, m+1, 0).getDate();
          const pad = (n)=> String(n).padStart(2,'0');
          const toISO = (d)=> `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}`;
          const toggleDate = (iso)=> setSelectedDates((prev)=> prev.includes(iso) ? prev.filter(x=>x!==iso) : [...prev, iso]);
          // Sunday-first calendar headers
          const HEADERS = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"];
          return (
            <div className="space-y-4">
              {months.map((m, idx)=>{
                const year = m.getFullYear();
                const month = m.getMonth();
                const isNextMonth = (month === startOfNextMonth.getMonth() && year === startOfNextMonth.getFullYear());
                const total = daysInMonth(year, month);
                const first = new Date(year, month, 1);
                const jsFirst = first.getDay(); // 0=Sun..6=Sat (Sunday-first)
                const cells = [];

                // Leading cells for alignment. If we're only showing next month and dropping current month,
                // fill the leading cells with carryover days from previous month that are >= today.
                if (isNextMonth && dropCurrentMonth) {
                  for (let i = 0; i < jsFirst; i++) {
                    const prevDate = new Date(year, month, 1 - (jsFirst - i)); // dates from previous month
                    if (prevDate >= today && prevDate >= nextMonthWeekStart && prevDate <= nextMonthWeekEnd) {
                      const iso = toISO(prevDate);
                      cells.push({ key: iso, iso, day: prevDate.getDate(), carry: true });
                    } else {
                      cells.push({ key: `b-${i}`, blank: true });
                    }
                  }
                } else {
                  for (let i = 0; i < jsFirst; i++) cells.push({ key: `b-${i}`, blank: true });
                }

                // Current month days
                for (let d=1; d<=total; d++) {
                  const dateObj = new Date(year, month, d);
                  // Hide past days for the current (visible) month that includes today
                  if (dateObj < today) {
                    // Only blank out past days in the month that contains today; future months are all in the future
                    const isThisMonth = (month === today.getMonth() && year === today.getFullYear());
                    if (isThisMonth) { cells.push({ key: `p-${d}`, blank: true }); continue; }
                  }
                  const iso = toISO(dateObj);
                  cells.push({ key: iso, iso, day: d });
                }

                // Pad trailing blanks to complete the last week row
                while (cells.length % 7 !== 0) cells.push({ key: `t-${cells.length}`, blank: true });
                return (
                  <div key={idx} className="space-y-2">
                    <div className="font-medium text-sm">{formatInTimezone(m, { month:'long', year:'numeric' }, resolvedTimezone)}</div>
                    <div className="grid grid-cols-7 gap-1 text-[11px] text-muted-foreground">
                      {HEADERS.map(h => <div key={h} className="py-1 text-center">{h}</div>)}
                    </div>
                    <div className="grid grid-cols-7 gap-1">
                      {cells.map(cell => {
                        if (cell.blank) return <div key={cell.key} className="p-2" />;
                        const active = selectedDates.includes(cell.iso);
                        return (
                          <button
                            type="button"
                            key={cell.key}
                            onClick={()=>toggleDate(cell.iso)}
                            className={`border rounded p-2 text-center text-xs ${active?'border-blue-600 ring-1 ring-blue-400':'hover:border-gray-400'}`}
                          >
                            {cell.day}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
              <div className="flex items-center gap-2 mt-2">
                <input id="notSureSchedule2" type="checkbox" checked={notSureSchedule} onChange={(e)=> setNotSureSchedule(e.target.checked)} />
                <Label htmlFor="notSureSchedule2">I'm not sure yet</Label>
              </div>
              {/* Helper text removed per spec */}
            </div>
          );
        case 'finish':
          const nameOk = (formData.podcastName || '').trim().length >= 4;
          const descOk = (formData.podcastDescription || '').trim().length > 0;
          const missingData = path === 'new' && (!nameOk || !descOk);
          return (
            <div className="space-y-2">
              <h3 className="text-lg font-semibold">Finish</h3>
              {missingData ? (
                <div className="space-y-2">
                  <p className="text-sm text-destructive">We're missing some required information:</p>
                  <ul className="text-sm text-muted-foreground list-disc list-inside">
                    {!nameOk && <li>Podcast name (at least 4 characters)</li>}
                    {!descOk && <li>Podcast description</li>}
                  </ul>
                  <p className="text-sm text-muted-foreground">Please go back and fill in these details.</p>
                </div>
              ) : (
                <>
                  <p className="text-sm text-muted-foreground">Nice work. You can publish now or explore your dashboard.</p>
                  {saving && <div className="text-xs text-muted-foreground">Working...</div>}
                </>
              )}
            </div>
          );
        // Import flow renders
        case 'rss':
          return (
            <div className="grid gap-4">
              <div className="grid grid-cols-4 items-center gap-4">
                <Label htmlFor="rssUrl" className="text-right">RSS URL</Label>
                <Input id="rssUrl" value={rssUrl} onChange={(e)=> setRssUrl(e.target.value)} className="col-span-3" placeholder="https://example.com/feed.xml" />
              </div>
            </div>
          );
        case 'confirm':
          return (
            <div className="space-y-3">
              <p className="text-sm">We'll import episodes and assets from:</p>
              <div className="p-3 rounded border bg-accent/30 text-sm break-all">{rssUrl || '-'}</div>
              <p className="text-xs text-muted-foreground">Click Continue to start the import.</p>
            </div>
          );
        case 'importing':
          return (<div className="text-sm">Importing... This may take a moment.</div>);
        case 'analyze':
          return (<div className="text-sm">Analyzing your feed and extracting settings...</div>);
        case 'assets':
          return (<div className="text-sm">Pulling cover art and audio assets...</div>);
        case 'importSuccess':
          return (
            <div className="space-y-2">
              <h3 className="text-lg font-semibold">Imported</h3>
              <p className="text-sm text-muted-foreground">Your show is in Podcast Plus Plus. We&apos;ll continue the setup from step 6 so you can fine-tune everything.</p>
            </div>
          );
        default:
          return null;
      }
    },
  // Keep validations lenient: prefer step-provided validate, then intercept where needed
  validate: s.validate ? s.validate : s.id === 'publishCadence' ? async () => {
      if (!freqUnit) {
        setCadenceError('Please choose a frequency.');
        return false;
      }
      if (freqUnit === 'bi-weekly' && Number(freqCount) !== 1) {
        setCadenceError('For bi-weekly, X must be 1.');
        return false;
      }
      setCadenceError('');
      return true;
    } : s.id === 'publishSchedule' ? async () => {
      if (notSureSchedule) return true;
      if (freqUnit === 'week' && selectedWeekdays.length === 0) return false;
      if ((freqUnit === 'bi-weekly' || freqUnit === 'month') && selectedDates.length === 0) return false;
      return true;
    } : s.id === 'confirm' && path === 'import' ? async () => {
      const trimmed = (rssUrl || '').trim();
      if (!trimmed) {
        toast({ variant: 'destructive', title: 'RSS feed required', description: 'Please enter your feed URL before continuing.' });
        return false;
      }
      setImportLoading(true);
      try {
        const api = makeApi(token);
        const data = await api.post('/api/import/rss', { rss_url: trimmed });
        setImportResult(data);
        setRssUrl(trimmed);
        const importedName = data?.podcast_name || data?.title || data?.name || '';
        const importedDescription = data?.description || data?.summary || '';
        setFormData((prev) => ({
          ...prev,
          podcastName: importedName || prev.podcastName || '',
          podcastDescription: importedDescription || prev.podcastDescription || '',
        }));
        setSkipCoverNow(true);
        setResumeAfterImport(true);
        return true;
      } catch (err) {
        const message = err?.detail || err?.message || 'Failed to import RSS feed.';
        toast({ variant: 'destructive', title: 'Import failed', description: message });
        setImportResult(null);
        setResumeAfterImport(false);
        return false;
      } finally {
        setImportLoading(false);
      }
    } : s.id === 'showDetails' ? async () => {
      const nameLen = (formData.podcastName || '').trim().length;
      const nameOk = nameLen >= 4;
      const descOk = (formData.podcastDescription || '').trim().length > 0;
      return nameOk && descOk;
    } : s.id === 'coverArt' ? async () => {
      // Require cover or explicit skip
      if (formData.coverArt || skipCoverNow) return true;
      return false;
    } : s.id === 'introOutro' ? async () => {
      // Prepare assets as needed
      let createdIntro = null;
      let createdOutro = null;
      // If upload mode is chosen, enforce selecting a file
      if (introMode === 'upload' && !introFile) return false;
      if (outroMode === 'upload' && !outroFile) return false;
      // If record mode is chosen, ensure recording was completed
      if (introMode === 'record' && !introAsset) return false;
      if (outroMode === 'record' && !outroAsset) return false;
      
      // Handle intro generation/upload
      // Generate/upload if mode is not 'existing' OR if mode is 'tts'/'upload' and user wants to regenerate
      if (introMode === 'tts' || introMode === 'upload' || introMode === 'record') {
        const ia = await generateOrUploadTTS('intro', introMode, introScript, introFile, introAsset);
        if (ia) { 
          console.log('[Onboarding] Intro created:', ia);
          setIntroAsset(ia); 
          createdIntro = ia;
          // Add to intro options if not already there
          setIntroOptions(prev => {
            const exists = prev.some(x => (x.id || x.filename) === (ia.id || ia.filename));
            return exists ? prev : [...prev, ia];
          });
          setSelectedIntroId(String(ia.id || ia.filename));
          // Switch to "existing" mode for preview
          setIntroMode('existing');
        } else {
          console.error('[Onboarding] Failed to create intro');
          toast({ 
            title: "Intro creation failed", 
            description: "Please try again or choose a different option.",
            variant: "destructive"
          });
          return false;
        }
      }
      
      // Handle outro generation/upload
      // Generate/upload if mode is not 'existing' OR if mode is 'tts'/'upload' and user wants to regenerate
      if (outroMode === 'tts' || outroMode === 'upload' || outroMode === 'record') {
        console.log('[Onboarding] Generating outro with mode:', outroMode);
        const oa = await generateOrUploadTTS('outro', outroMode, outroScript, outroFile, outroAsset);
        if (oa) { 
          console.log('[Onboarding] Outro created successfully:', oa);
          console.log('[Onboarding] Outro has id?', !!oa.id, 'filename?', !!oa.filename);
          setOutroAsset(oa); 
          createdOutro = oa;
          // Add to outro options if not already there
          setOutroOptions(prev => {
            const exists = prev.some(x => (x.id || x.filename) === (oa.id || oa.filename));
            console.log('[Onboarding] Adding outro to options. Already exists?', exists);
            return exists ? prev : [...prev, oa];
          });
          const selectedId = String(oa.id || oa.filename);
          console.log('[Onboarding] Setting selectedOutroId to:', selectedId);
          setSelectedOutroId(selectedId);
          // Switch to "existing" mode for preview
          setOutroMode('existing');
        } else {
          console.error('[Onboarding] Failed to create outro - generateOrUploadTTS returned null/undefined');
          toast({ 
            title: "Outro creation failed", 
            description: "Please try again or choose a different option.",
            variant: "destructive"
          });
          return false;
        }
      }
      
      // Show success toast if anything was created
      if (createdIntro || createdOutro) {
        const parts = [];
        if (createdIntro) parts.push('intro');
        if (createdOutro) parts.push('outro');
        toast({ 
          title: "Success!", 
          description: `Your ${parts.join(' and ')} ${parts.length === 1 ? 'has' : 'have'} been created. Preview below!` 
        });
        // Don't navigate away - stay on this step to allow preview
        return false;
      }
      
      // If in 'existing' mode, validate that assets are selected
      if (introMode === 'existing' && !introAsset) {
        toast({ 
          title: "Intro required", 
          description: "Please select an intro or choose a different option.",
          variant: "destructive"
        });
        return false;
      }
      if (outroMode === 'existing' && !outroAsset) {
        toast({ 
          title: "Outro required", 
          description: "Please select an outro or choose a different option.",
          variant: "destructive"
        });
        return false;
      }
      
      return true;
    } : undefined,
  }));

  // Auto-advance simple import progress steps
  useEffect(() => {
    let t;
    if (path === 'import') {
      if (stepId === 'importing') {
        t = setTimeout(() => setStepIndex((n) => Math.min(n + 1, wizardSteps.length - 1)), 1000);
      } else if (stepId === 'analyze') {
        t = setTimeout(() => setStepIndex((n) => Math.min(n + 1, wizardSteps.length - 1)), 800);
      } else if (stepId === 'assets') {
        t = setTimeout(() => setStepIndex((n) => Math.min(n + 1, wizardSteps.length - 1)), 800);
      }
    }
    return () => { if (t) clearTimeout(t); };
  }, [path, stepId, wizardSteps.length]);

  useEffect(() => {
    const shouldResume = resumeAfterImport && path === 'import' && stepId === 'importSuccess';
    if (shouldResume && !importResumeTimerRef.current) {
      const targetIndex = introOutroIndex >= 0 ? introOutroIndex : 0; // base index becomes skipNotice when enabled
      importResumeTimerRef.current = window.setTimeout(() => {
        importResumeTimerRef.current = null;
        setResumeAfterImport(false);
        setPath('new');
        setShowSkipNotice(true);
        setImportJumpedToStep6(true);
        setStepIndex(targetIndex); // points at skipNotice if enabled
        const importedName = importResult?.podcast_name || importResult?.title || importResult?.name || formData.podcastName || 'your show';
        toast({ title: 'Import complete', description: `We pulled in ${importedName}. Continue with the rest of the setup.` });
      }, 600);
    } else if (!shouldResume && importResumeTimerRef.current) {
      clearTimeout(importResumeTimerRef.current);
      importResumeTimerRef.current = null;
    }

    return () => {
      if (importResumeTimerRef.current) {
        clearTimeout(importResumeTimerRef.current);
        importResumeTimerRef.current = null;
      }
    };
  }, [resumeAfterImport, path, stepId, introOutroIndex, importResult, formData.podcastName, toast, setStepIndex, setPath, setResumeAfterImport]);

  // Compute gating for Next/Finish and hide rules
  const { nextDisabled, hideNext } = useMemo(() => {
    let disabled = false;
    let hide = false;
    switch (stepId) {
      case 'skipNotice': {
        // Allow immediate continue; also auto-advance via effect below
        disabled = false;
        break;
      }
      case 'choosePath':
        // Special UX: hide Continue; use Start new / Import existing buttons
        hide = true;
        break;
      case 'confirm': {
        if (path === 'import') {
          disabled = importLoading;
        }
        break;
      }
      case 'yourName': {
        disabled = !(firstName || '').trim();
        break;
      }
      case 'showDetails': {
        const nameOk = (formData.podcastName || '').trim().length >= 4;
        const descOk = (formData.podcastDescription || '').trim().length > 0;
        disabled = !(nameOk && descOk);
        break;
      }
      case 'coverArt': {
        disabled = !(formData.coverArt || skipCoverNow);
        break;
      }
      case 'publishCadence': {
        disabled = !freqUnit || (freqUnit === 'bi-weekly' && Number(freqCount) !== 1);
        break;
      }
      case 'publishSchedule': {
        if (!notSureSchedule) {
          if (freqUnit === 'week') disabled = selectedWeekdays.length === 0; else if (freqUnit === 'bi-weekly' || freqUnit === 'month') disabled = selectedDates.length === 0;
        }
        break;
      }
      case 'introOutro': {
        // Only block continue if user is in TTS/upload/record mode but hasn't completed the action
        // If they have existing intro/outro selected, they're good to go
        if (introMode === 'tts' && !introScript.trim()) {
          disabled = true;
        } else if (introMode === 'upload' && !introFile) {
          disabled = true;
        } else if (introMode === 'record' && !introAsset) {
          disabled = true;
        } else if (outroMode === 'tts' && !outroScript.trim()) {
          disabled = true;
        } else if (outroMode === 'upload' && !outroFile) {
          disabled = true;
        } else if (outroMode === 'record' && !outroAsset) {
          disabled = true;
        }
        // If mode is 'existing', no validation needed - they already have intro/outro
        break;
      }
      case 'finish': {
        // On the finish step, validate that we have required data if creating a new podcast
        // This is a safety check in case the user somehow bypassed earlier validation
        if (path === 'new') {
          const nameOk = (formData.podcastName || '').trim().length >= 4;
          const descOk = (formData.podcastDescription || '').trim().length > 0;
          disabled = !(nameOk && descOk);
        }
        break;
      }
      default:
        break;
    }
    return { nextDisabled: !!disabled, hideNext: !!hide };
  }, [stepId, path, importLoading, firstName, formData.podcastName, formData.podcastDescription, formData.coverArt, skipCoverNow, freqUnit, freqCount, notSureSchedule, selectedWeekdays.length, selectedDates.length, introMode, outroMode, introScript, outroScript, introFile, outroFile, introAsset, outroAsset]);

  // Auto-advance the skip notice after a short delay
  useEffect(() => {
    if (stepId !== 'skipNotice') return;
    const t = setTimeout(() => {
      setStepIndex((n) => Math.min(n + 1, wizardSteps.length - 1));
    }, 900);
    return () => clearTimeout(t);
  }, [stepId, wizardSteps.length, setStepIndex]);

  return (
    <>
      <OnboardingWrapper
        steps={steps}
        index={stepIndex}
        setIndex={setStepIndex}
        onComplete={handleFinish}
        prefs={{ largeText, setLargeText, highContrast, setHighContrast }}
        greetingName={firstName?.trim() || ''}
        nextDisabled={nextDisabled}
        hideNext={hideNext}
        hideBack={importJumpedToStep6 && stepId === 'introOutro'}
        showExitDiscard={hasExistingPodcast}
        onExitDiscard={handleExitDiscard}
      />
      <AIAssistant 
        token={token} 
        user={user}
        onboardingMode={true}
        currentStep={stepId}
        currentStepData={{
          path,
          formData,
          firstName,
          lastName,
          formatKey,
          musicChoice,
          freqUnit,
          freqCount,
          selectedWeekdays,
          selectedDates,
          notSureSchedule,
        }}
      />
    </>
  );
}

