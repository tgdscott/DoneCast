import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Textarea } from '../ui/textarea';
import { Progress } from '../ui/progress';
import { toast } from '@/hooks/use-toast';
import { ArrowLeft, Upload, FileAudio, FileUp, BookText, Wand2, FileImage, Settings, Globe, CheckCircle, Loader2, Mic } from 'lucide-react';
import RecurringScheduleManager from './RecurringScheduleManager';
import FlubberQuickReview from './FlubberQuickReview';
import IntentQuestions from './IntentQuestions';
import CoverCropper from './CoverCropper';
import { makeApi } from '@/lib/apiClient';
import VoicePicker from '@/components/VoicePicker';
import { useAuth } from '@/AuthContext.jsx';
import { fetchVoices as fetchElevenVoices } from '@/api/elevenlabs';

export default function PodcastCreator({ onBack, token, templates, podcasts, initialStep, testInject, preselectedMainFilename, preselectedTranscriptReady }) {
  const { user: authUser } = useAuth();
  const [currentStep, setCurrentStep] = useState(initialStep || 1)
  const [selectedTemplate, setSelectedTemplate] = useState(null)
  const [uploadedFile, setUploadedFile] = useState(null)
  const [uploadedFilename, setUploadedFilename] = useState(null)
  const [isUploading, setIsUploading] = useState(false)
  const [isAssembling, setIsAssembling] = useState(false)
  const [isPublishing, setIsPublishing] = useState(false)
  const [assemblyComplete, setAssemblyComplete] = useState(false)
  const [assembledEpisode, setAssembledEpisode] = useState(null)
  const [expectedEpisodeId, setExpectedEpisodeId] = useState(null)
  const [statusMessage, setStatusMessage] = useState('')
  const [error, setError] = useState('')
  const [ttsValues, setTtsValues] = useState({})
  const [mediaLibrary, setMediaLibrary] = useState([]);
  // Flubber pre-review state
  const [showFlubberReview, setShowFlubberReview] = useState(false);
  const [flubberContexts, setFlubberContexts] = useState(null);
  const [flubberCutsMs, setFlubberCutsMs] = useState(null);
  const [showIntentQuestions, setShowIntentQuestions] = useState(false);
  const [intents, setIntents] = useState({ flubber: null, intern: null, sfx: null });
  const [showFlubberScan, setShowFlubberScan] = useState(false);
  const [capabilities, setCapabilities] = useState({ has_elevenlabs:false, has_google_tts:false, has_any_sfx_triggers:false });
  const [flubberNotFound, setFlubberNotFound] = useState(false);
  const [fuzzyThreshold, setFuzzyThreshold] = useState(0.8);
  const [testMode, setTestMode] = useState(false); // retained but not required for Step 5 prefill
  // Billing usage (processing minutes remaining) for gating creation
  const [usage, setUsage] = useState(null);
  const [episodeDetails, setEpisodeDetails] = useState({
    season: '1',
    episodeNumber: '',
    title: '',
    description: '',
    coverArt: null,
    coverArtPreview: null,
    cover_image_path: null, // <<< store uploaded cover filename here
    cover_crop: null, // crop string 'x1,y1,x2,y2' (optional metadata if needed later)
  })

  // Step 5 AI helpers: disable only while fetching (no permanent locks)
  const [isAiTitleBusy, setIsAiTitleBusy] = useState(false);
  const [isAiDescBusy, setIsAiDescBusy] = useState(false);
  // Simple cache for separate AI calls
  const aiCacheRef = useRef({ title: null, notes: null, tags: null });
  // Track auto-fill per episode/template to avoid duplicate runs
  const autoFillKeyRef = useRef("");
  // Mirror transcriptReady in a ref to avoid stale closures
  const transcriptReadyRef = useRef(false);

  const [jobId, setJobId] = useState(null);
  const [spreakerShows, setSpreakerShows] = useState([]); // kept if future UI needs
  const [selectedSpreakerShow, setSelectedSpreakerShow] = useState(null); // auto-set from template
  // Publishing / scheduling selections BEFORE assembly (draft, now, schedule)
  const [publishMode, setPublishMode] = useState('draft'); // 'now' | 'draft' | 'schedule'
  const [publishVisibility, setPublishVisibility] = useState('public'); // for immediate publish (public/private)
  const [scheduleDate, setScheduleDate] = useState(""); // YYYY-MM-DD
  const [scheduleTime, setScheduleTime] = useState(""); // HH:MM
  const [autoPublishPending, setAutoPublishPending] = useState(false); // internal flag
  const [lastAutoPublishedEpisodeId, setLastAutoPublishedEpisodeId] = useState(null); // prevent duplicate or stale publishes
  // Transcript readiness for AI buttons gating
  const [transcriptReady, setTranscriptReady] = useState(false);
  // Per-episode TTS voice overrides (UI only for PR-1)
  const [showVoicePicker, setShowVoicePicker] = useState(false);
  const [voicePickerTargetId, setVoicePickerTargetId] = useState(null);
  // Map of voice_id -> friendly/common name for display in Step 3
  const [voiceNameById, setVoiceNameById] = useState({});
  const [voicesLoading, setVoicesLoading] = useState(false);

  const fileInputRef = useRef(null)
  const coverArtInputRef = useRef(null) // file chooser for cover
  const coverCropperRef = useRef(null)  // ref to cropper to export processed blob
  const [coverNeedsUpload, setCoverNeedsUpload] = useState(false); // true after selecting file until uploaded
  const [coverMode, setCoverMode] = useState('crop'); // persisted by cropper internally
  const [isUploadingCover, setIsUploadingCover] = useState(false); // track async cover upload during Continue
  // Estimated processing time (based on uploaded audio duration)
  const [audioDurationSec, setAudioDurationSec] = useState(null);

  // One-time handoff from Recorder: prefer prop-based preselection, fallback to localStorage
  useEffect(() => {
    let used = false;
    try {
      if (preselectedMainFilename && !uploadedFilename) {
        setUploadedFilename(preselectedMainFilename);
        setCurrentStep(5);
        if (preselectedTranscriptReady === true) { setTranscriptReady(true); transcriptReadyRef.current = true; }
        used = true;
      }
    } catch {}
    if (used) return;
    try {
      const handedFilename = localStorage.getItem('ppp_uploaded_filename');
      const handedHint = localStorage.getItem('ppp_uploaded_hint');
      const startStep = localStorage.getItem('ppp_start_step');
      const wasReady = localStorage.getItem('ppp_transcript_ready');
      if (!uploadedFilename) {
        if (handedFilename) setUploadedFilename(handedFilename);
        else if (handedHint) setUploadedFilename(handedHint);
      }
      if (startStep === '5') setCurrentStep(5);
      if (wasReady === '1') { setTranscriptReady(true); transcriptReadyRef.current = true; }
    } catch {}
    // Clear one-time flags so refresh doesn’t re-jump unexpectedly
    try {
      localStorage.removeItem('ppp_start_step');
      localStorage.removeItem('ppp_transcript_ready');
    } catch {}
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preselectedMainFilename]);

  // Test-only state injection to simplify rendering specific steps
  useEffect(() => {
    if (!testInject) return;
    try {
      if (testInject.selectedTemplate) setSelectedTemplate(testInject.selectedTemplate);
      if (testInject.uploadedFilename) setUploadedFilename(testInject.uploadedFilename);
      if (typeof testInject.transcriptReady === 'boolean') setTranscriptReady(!!testInject.transcriptReady);
      if (testInject.episodeDetails) setEpisodeDetails(prev => ({ ...prev, ...testInject.episodeDetails }));
    } catch {}
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [testInject]);

  // If there's exactly one active template, auto-select it on load (both procedures)
  useEffect(() => {
    if (selectedTemplate) return;
    if (!Array.isArray(templates)) return;
    const active = templates.filter(t => t?.is_active !== false);
    if (active.length === 1) {
      setSelectedTemplate(active[0]);
      if (currentStep === 1) setCurrentStep(2);
    }
  }, [templates, selectedTemplate, currentStep]);
  
  useEffect(() => {
    const api = makeApi(token);
    const fetchMedia = async () => {
      try {
        const data = await api.get('/api/media/');
        setMediaLibrary(data);
      } catch (err) {
        setError(err.message);
      }
    };
    fetchMedia();
    fetchSpreakerShows(); // Fetch Spreaker shows on mount
    // Fetch platform admin Test Mode (only attempt for admins)
    (async () => {
      try {
        const isAdmin = !!(authUser && (authUser.is_admin || authUser.role === 'admin'));
        if (!isAdmin) { setTestMode(false); return; }
        const settings = await api.get('/api/admin/settings');
        if (settings && typeof settings.test_mode !== 'undefined') {
          setTestMode(!!settings.test_mode);
        }
      } catch (_) {
        setTestMode(false);
      }
    })();
    // Fetch usage/quota (ignore errors silently so UI still works if endpoint absent)
    (async () => {
      try {
        const u = await api.get('/api/billing/usage');
        if (u) setUsage(u);
      } catch (_) { /* no-op */ }
    })();
    // Fetch lightweight capabilities for UI gating
    (async () => {
      try {
        const caps = await api.get('/api/users/me/capabilities');
        if(caps){ setCapabilities({
          has_elevenlabs: !!caps.has_elevenlabs,
          has_google_tts: !!caps.has_google_tts,
          has_any_sfx_triggers: !!caps.has_any_sfx_triggers,
        }); }
      } catch(_) { /* no-op */ }
    })();
  }, [token, authUser]);

  useEffect(() => {
    if (showIntentQuestions) return;
    if (!uploadedFile) return;
    if (isUploading) return;
    if (currentStep !== 2) return;

    const requireIntern = capabilities.has_elevenlabs || capabilities.has_google_tts;
    const requireSfx = capabilities.has_any_sfx_triggers;

    const needsFlubber = intents.flubber === null;
    const needsIntern = requireIntern && intents.intern === null;
    const needsSfx = requireSfx && intents.sfx === null;

    if (needsFlubber || needsIntern || needsSfx) {
      setShowIntentQuestions(true);
    }
  }, [
    showIntentQuestions,
    uploadedFile,
    isUploading,
    currentStep,
    intents.flubber,
    intents.intern,
    intents.sfx,
    capabilities.has_elevenlabs,
    capabilities.has_google_tts,
    capabilities.has_any_sfx_triggers,
  ]);

  // Derive audio duration from uploaded file to estimate processing time
  useEffect(() => {
    if (!uploadedFile) { setAudioDurationSec(null); return; }
    let url = null;
    const audio = new Audio();
    const onLoaded = () => {
      const d = audio && isFinite(audio.duration) ? audio.duration : null;
      setAudioDurationSec(d && d > 0 ? d : null);
      if (url) URL.revokeObjectURL(url);
    };
    const onError = () => {
      setAudioDurationSec(null);
      if (url) URL.revokeObjectURL(url);
    };
    audio.addEventListener('loadedmetadata', onLoaded);
    audio.addEventListener('error', onError);
    try {
      url = URL.createObjectURL(uploadedFile);
      audio.src = url;
      audio.load();
    } catch (_) {
      setAudioDurationSec(null);
      if (url) try { URL.revokeObjectURL(url); } catch {}
    }
    return () => {
      audio.removeEventListener('loadedmetadata', onLoaded);
      audio.removeEventListener('error', onError);
      if (url) try { URL.revokeObjectURL(url); } catch {}
    };
  }, [uploadedFile]);

  // VoicePicker: compute the active segment once per open
  const activeSegment = useMemo(() => {
    if (!showVoicePicker || !voicePickerTargetId || !selectedTemplate?.segments) return null;
    try {
      return selectedTemplate.segments.find(s => s.id === voicePickerTargetId) || null;
    } catch (_) {
      return null;
    }
  }, [showVoicePicker, voicePickerTargetId, selectedTemplate]);

  const handleVoiceChange = (voice_id) => {
    if (!voicePickerTargetId) return;
    setSelectedTemplate(prev => {
      if (!prev?.segments) return prev;
      const nextSegs = prev.segments.map(s => {
        if (s.id === voicePickerTargetId && s?.source?.source_type === 'tts') {
          return { ...s, source: { ...s.source, voice_id } };
        }
        return s;
      });
      return { ...prev, segments: nextSegs };
    });
  };

  // When on Step 3, fetch ElevenLabs voices and index by id for friendly display
  useEffect(() => {
    if (currentStep !== 3) return;
    // Collect unique TTS voice ids shown on this page
    const ids = new Set();
    try {
      (selectedTemplate?.segments || []).forEach(s => {
        if (s?.source?.source_type === 'tts' && s?.source?.voice_id) {
          const vid = String(s.source.voice_id);
          if (vid && vid.toLowerCase() !== 'default') ids.add(vid);
        }
      });
    } catch {}
    if (!ids.size) return;
    // If we already know all these ids, skip fetching
    let haveAll = true;
    for (const id of ids) { if (!voiceNameById[id]) { haveAll = false; break; } }
    if (haveAll) return;
    let cancelled = false;
    (async () => {
      try {
        setVoicesLoading(true);
        // Fetch a generous page; ElevenLabs orgs typically have < 200 voices
        const res = await fetchElevenVoices('', 1, 200);
        const map = {};
        for (const v of (res?.items || [])) {
          const dn = v.common_name || v.name || '';
          if (dn) map[v.voice_id] = dn;
        }
        if (!cancelled) setVoiceNameById(prev => ({ ...prev, ...map }));
        // Resolve any remaining unknown ids by direct backend resolve (supports BYOK/user keys)
  const unknown = Array.from(ids).filter(id => id && id.toLowerCase() !== 'default' && !map[id]);
        if (unknown.length) {
          const api = makeApi(token);
          for (const id of unknown) {
            try {
              const v = await api.get(`/api/elevenlabs/voice/${encodeURIComponent(id)}/resolve`);
              const dn = v?.common_name || v?.name || '';
              if (dn && !cancelled) {
                setVoiceNameById(prev => ({ ...prev, [id]: dn }));
              }
            } catch (_) { /* ignore */ }
          }
        }
      } catch {
        // no-op; fallback will show the id
      } finally {
        if (!cancelled) setVoicesLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [currentStep, selectedTemplate?.id, token]);

  const processingEstimate = useMemo(() => {
    if (!audioDurationSec || !isFinite(audioDurationSec) || audioDurationSec <= 0) return null;
    const mins = audioDurationSec / 60;
    const low = Math.max(0, Math.floor(mins * 0.75));
    const high = Math.max(1, Math.ceil(mins * 1.25));
    return { low, high };
  }, [audioDurationSec]);

  // Initialize defaults (schedule time, publish prefs) from localStorage with sane fallbacks.
  const hadStoredPublishRef = useRef(false);
  useEffect(() => {
    try {
      const storedMode = localStorage.getItem('ppp_publish_mode');
  if(storedMode && ['now','draft','schedule'].includes(storedMode)) setPublishMode(storedMode);
  hadStoredPublishRef.current = !!storedMode;
      const storedVis = localStorage.getItem('ppp_publish_visibility');
      if(storedVis && ['public','unpublished'].includes(storedVis)) setPublishVisibility(storedVis);
      const storedExplicit = localStorage.getItem('ppp_explicit_flag');
      if(storedExplicit === 'true') setEpisodeDetails(prev=>({ ...prev, is_explicit: true }));
  // Note: tags persistence handled separately and only when template opts-out of auto tags
      const storedSchedule = localStorage.getItem('ppp_schedule_datetime');
      let base;
      if(storedSchedule){
        const d = new Date(storedSchedule);
        // require at least 10 min in future; else recalc new
        if(!isNaN(d.getTime()) && d.getTime() > Date.now()+10*60000){
          base = d;
        }
      }
      if(!base){
        base = new Date(Date.now() + 60*60000);
        const mins = base.getMinutes();
        const rounded = Math.ceil(mins/5)*5;
        if(rounded >= 60){ base.setHours(base.getHours()+1); base.setMinutes(0);} else { base.setMinutes(rounded); }
        base.setSeconds(0,0);
      }
      const yyyy=base.getFullYear(); const mm=String(base.getMonth()+1).padStart(2,'0'); const dd=String(base.getDate()).padStart(2,'0');
      const hh=String(base.getHours()).padStart(2,'0'); const mi=String(base.getMinutes()).padStart(2,'0');
      setScheduleDate(`${yyyy}-${mm}-${dd}`); setScheduleTime(`${hh}:${mi}`);
    } catch {/* ignore */}
  }, []);

  // Apply stored tags only if the selected template explicitly opts out of auto tag generation
  useEffect(() => {
    try {
      if (selectedTemplate?.ai_settings?.auto_generate_tags === false) {
        const storedTags = localStorage.getItem('ppp_last_tags');
        if (storedTags && !episodeDetails.tags) {
          setEpisodeDetails(prev => ({ ...prev, tags: storedTags }));
        }
      }
    } catch {/* ignore */}
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTemplate]);

  // If no stored publish preference, derive sensible default from Test Mode
  useEffect(() => {
    if (!hadStoredPublishRef.current) {
      setPublishMode(testMode ? 'draft' : 'now');
    }
  }, [testMode]);

  // Persist publish preferences
  useEffect(()=>{ try { localStorage.setItem('ppp_publish_mode', publishMode); } catch {} }, [publishMode]);
  useEffect(()=>{ try { localStorage.setItem('ppp_publish_visibility', publishVisibility); } catch {} }, [publishVisibility]);
  useEffect(()=>{ try { if(scheduleDate && scheduleTime){ const iso = new Date(`${scheduleDate}T${scheduleTime}:00`).toISOString(); localStorage.setItem('ppp_schedule_datetime', iso); } } catch {} }, [scheduleDate, scheduleTime]);
  useEffect(()=>{ try { localStorage.setItem('ppp_explicit_flag', episodeDetails.is_explicit ? 'true':'false'); } catch {} }, [episodeDetails.is_explicit]);
  useEffect(() => {
    try {
      if (selectedTemplate?.ai_settings?.auto_generate_tags === false) {
        if (episodeDetails.tags) {
          localStorage.setItem('ppp_last_tags', episodeDetails.tags);
        } else {
          localStorage.removeItem('ppp_last_tags');
        }
      } else {
        // If auto tags are enabled, ensure sticky tags are cleared
        localStorage.removeItem('ppp_last_tags');
      }
    } catch {/* ignore */}
  }, [episodeDetails.tags, selectedTemplate]);

  // Auto-fill only after transcript is ready on Step 5; run once per (file|episode|template)
  useEffect(() => {
    if (currentStep !== 5 || !selectedTemplate || !transcriptReady) return;
    const key = `${uploadedFilename || ''}|${expectedEpisodeId || ''}|${selectedTemplate?.id || ''}`;
    if (autoFillKeyRef.current === key) return; // already ran for this context

    const autoFill = !!selectedTemplate?.ai_settings?.auto_fill_ai;
    const allowAutoTags = selectedTemplate?.ai_settings?.auto_generate_tags !== false;
    const pinned = selectedTemplate?.ai_settings?.tags_always_include || [];

    (async () => {
      try {
        if (autoFill && !episodeDetails.title) {
          setIsAiTitleBusy(true);
          const t = await suggestTitle();
          if (t && !/[a-f0-9]{16,}/i.test(t)) {
            handleDetailsChange('title', t);
          }
        }
      } finally { setIsAiTitleBusy(false); }

      try {
        if (autoFill && !(episodeDetails.description?.length)) {
          setIsAiDescBusy(true);
          const n = await suggestNotes();
          if (n && !/[a-f0-9]{16,}/i.test(n)) {
            handleDetailsChange('description', n);
          }
        }
      } finally { setIsAiDescBusy(false); }

      if (allowAutoTags) {
        const ai = await suggestTags();
        // merge pinned first, dedupe case-insensitive, cap 20; sort for readability; join as comma string
        const seen = new Set(); const merged = [];
        for (const t of [...pinned, ...ai]) {
          const s = String(t).trim(); if (!s) continue;
          const k = s.toLowerCase();
          if (!seen.has(k)) { seen.add(k); merged.push(s); }
          if (merged.length >= 20) break;
        }
        merged.sort((a,b)=>a.localeCompare(b));
        handleDetailsChange('tags', merged.join(', '));
      } else {
        // Opt-out: do not auto-generate or overwrite user-provided tags.
        // Leave existing tags as-is.
      }

      autoFillKeyRef.current = key; // mark done for this context
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentStep, selectedTemplate?.id, transcriptReady, uploadedFilename, expectedEpisodeId]);
  // Cover crop persistence removed

  // Keep a ref mirror of transcriptReady to avoid stale closures; reset caches on context change
  useEffect(() => { transcriptReadyRef.current = transcriptReady; }, [transcriptReady]);

  // Reset AI caches when switching to a new file/episode/template
  useEffect(() => {
    aiCacheRef.current = { title: null, notes: null, tags: null };
    autoFillKeyRef.current = "";
    // Reset transcript flag when entering Step 5 for a new context
    if (currentStep === 5) setTranscriptReady(false);
  }, [uploadedFilename, expectedEpisodeId, selectedTemplate?.id]);

  // Poll transcript readiness on Step 5 (every 5s) using filename hint even before assembly.
  // If transcriptReady flips back to false (e.g., transient 409), restart polling automatically.
  useEffect(() => {
    if (currentStep !== 5) return;
    if (!uploadedFilename && !expectedEpisodeId) return; // nothing to poll against
    if (transcriptReady) return; // already ready; no need to poll until it becomes false again

    let stopped = false;
    const api = makeApi(token);
    const tick = async () => {
      if (stopped) return;
      try {
        const params = [];
        if (expectedEpisodeId) params.push(`episode_id=${encodeURIComponent(expectedEpisodeId)}`);
        if (uploadedFilename) params.push(`hint=${encodeURIComponent(uploadedFilename)}`);
        const url = `/api/ai/transcript-ready${params.length ? `?${params.join('&')}` : ''}`;
        const r = await api.get(url);
        if (r?.ready) {
          setTranscriptReady(true);
          return; // stop polling; effect will short-circuit on next run
        }
      } catch (_) { /* ignore */ }
      if (!stopped) setTimeout(tick, 5000);
    };
    // Start with a short delay to avoid hammering right away
    const initial = setTimeout(tick, 250);
    return () => { stopped = true; clearTimeout(initial); };
  }, [currentStep, uploadedFilename, expectedEpisodeId, token, transcriptReady]);

  // Auto-select template only if there is exactly one ACTIVE template; never if 2+ exist
  useEffect(() => {
    if (selectedTemplate) return;
    if (!Array.isArray(templates)) return;
    const activeTemplates = templates.filter(t => t?.is_active !== false);
    if (activeTemplates.length === 1) {
      setSelectedTemplate(activeTemplates[0]);
      if (currentStep === 1) setCurrentStep(2); // only advance from the initial selection screen
    }
  }, [templates, selectedTemplate, currentStep]);

  // Fetch last numbering (season & episode) to auto-increment local defaults
  useEffect(() => {
    (async () => {
      try {
        const api = makeApi(token);
        const data = await api.get('/api/episodes/last/numbering');
        if(data && (data.season_number || data.episode_number)){
          setEpisodeDetails(prev => {
            if(prev.episodeNumber || prev.season !== '1') return prev; // user already edited
            const season = data.season_number ? String(data.season_number) : '1';
            const nextEp = data.episode_number ? String(Number(data.episode_number)+1) : '1';
            return { ...prev, season, episodeNumber: nextEp };
          });
        }
      } catch(_){ /* ignore */ }
    })();
  }, [token]);

  const fetchSpreakerShows = async () => { /* retained but unused */ };

  useEffect(() => {
    if (!jobId) return;
    const api = makeApi(token);
    const interval = setInterval(async () => {
      try {
        const data = await api.get(`/api/episodes/status/${jobId}`);
        setStatusMessage(data.status);

    if (data.status === 'processed' || data.status === 'error') {
          clearInterval(interval);
          setIsAssembling(false);
          if (data.status === 'processed') {
            if(data.episode && expectedEpisodeId && data.episode.id && data.episode.id !== expectedEpisodeId){
              // Wrong episode (likely fallback grabbed older). Resume polling once more.
              setIsAssembling(true);
              setTimeout(()=>{ setJobId(j=>j); }, 750);
              return;
            }
            setAssemblyComplete(true);
            setAssembledEpisode(data.episode);
            // For schedule & draft show immediate feedback; 'now' will publish via effect shortly
            if(publishMode === 'schedule'){
              toast({ title:'Scheduled', description:'Episode assembled & ready to schedule.' });
            } else if(publishMode === 'draft') {
              toast({ title: 'Draft Ready', description: 'Episode assembled (draft).' });
            }
          } else {
            setError(data.error || 'An error occurred during processing.');
            toast({ variant: 'destructive', title: 'Error', description: data.error || 'An error occurred during processing.' });
          }
        }
      } catch (err) {
        clearInterval(interval);
        setError('Failed to poll for job status.');
        setIsAssembling(false);
      }
    }, 5000); // Poll every 5 seconds

    return () => clearInterval(interval);
  }, [jobId, token]);

  // 6-step flow (Step 6 shows completion; previous standalone Done step removed)
  const steps = [
    { number: 1, title: "Select Template", icon: BookText },
    { number: 2, title: "Upload Audio", icon: FileUp },
    { number: 3, title: "Customize Segments", icon: Wand2 },
    { number: 4, title: "Cover Art", icon: FileImage },
    { number: 5, title: "Details & Schedule", icon: Settings },
    { number: 6, title: "Assemble", icon: Globe },
  ];

  const progressPercentage = ((currentStep - 1) / (steps.length - 1)) * 100;

  const handleTemplateSelect = async (template) => {
    // Ensure we have full template details, including ai_settings
    try {
      const api = makeApi(token);
      const full = await api.get(`/api/templates/${template.id}`);
      const aiDefaults = {
        auto_fill_ai: true,
        title_instructions: '',
        notes_instructions: '',
        tags_instructions: '',
        tags_always_include: [],
        auto_generate_tags: true,
      };
      const merged = { ...template, ...full, ai_settings: { ...aiDefaults, ...(full?.ai_settings || template?.ai_settings || {}) } };
      // Merge and seed TTS voice defaults if missing
      const segments = Array.isArray(merged.segments) ? [...merged.segments] : [];
      // Derive template default voice from first TTS segment with voice_id
      const templateDefaultVoiceId = segments.find(s => s?.source?.source_type === 'tts' && s?.source?.voice_id)?.source?.voice_id || null;
      const seeded = segments.map(s => {
        if (s?.source?.source_type === 'tts') {
          return { ...s, source: { ...s.source, voice_id: s.source.voice_id || templateDefaultVoiceId || s.source.voice_id } };
        }
        return s;
      });
      setSelectedTemplate({ ...merged, segments: seeded });
    } catch {
      // Fallback: apply defaults client-side if GET fails
      const aiDefaults = {
        auto_fill_ai: true,
        title_instructions: '',
        notes_instructions: '',
        tags_instructions: '',
        tags_always_include: [],
        auto_generate_tags: true,
      };
      setSelectedTemplate(prev => ({ ...(template || prev), ai_settings: { ...aiDefaults, ...((template||{}).ai_settings || {}) } }));
    }
    setCurrentStep(2)
  }

  const handleFileChange = async (file) => {
    if (!file) return
    const MB = 1024 * 1024
    if (!(file.type || '').toLowerCase().startsWith('audio/')) {
      setError('Please select an audio file.')
      return
    }
    if (file.size > 500 * MB) {
      setError('Audio exceeds 500MB limit.')
      return
    }
    setUploadedFile(file)
    setIntents({ flubber: null, intern: null, sfx: null })
    setShowIntentQuestions(false)
    setIsUploading(true)
    setStatusMessage('Uploading audio file...')
    setError('')

    const formData = new FormData()
    formData.append("files", file)
    formData.append("friendly_names", JSON.stringify([file.name]))

    try {
      const api = makeApi(token);
      const result = await api.raw('/api/media/upload/main_content', { method: 'POST', body: formData })
      const fname = result[0]?.filename
      setUploadedFilename(fname)
      setStatusMessage('Upload successful!')
      // Ask intent questions (required)
      setShowIntentQuestions(true)
    } catch (err) {
      setError(err.message)
      setStatusMessage('')
      setUploadedFile(null)
    } finally {
      setIsUploading(false)
    }
  }

  // Upload cover immediately and store server filename
  const uploadCover = async (file) => {
    const MB = 1024 * 1024
    const ct = (file?.type || '').toLowerCase()
    if (!ct.startsWith('image/')) throw new Error('Cover must be an image file.')
    if (file.size > 10 * MB) throw new Error('Cover image exceeds 10MB limit.')
    const fd = new FormData();
    fd.append("files", file);
    fd.append("friendly_names", JSON.stringify([file.name]));
    const api = makeApi(token);
    const data = await api.raw('/api/media/upload/episode_cover', { method: 'POST', body: fd });
    const uploaded = data?.[0]?.filename;
    if (!uploaded) throw new Error('Cover upload: no filename returned.');
    setEpisodeDetails(prev => ({ ...prev, cover_image_path: uploaded }));
    return uploaded;
  };

  const handleCoverFileSelected = (file) => {
    if(!file) return;
    // Reset state to allow new crop
    setEpisodeDetails(prev => ({ ...prev, coverArt: file, coverArtPreview: null, cover_image_path: null }));
    setCoverNeedsUpload(true);
  };

  const handleUploadProcessedCover = async () => {
    if(!episodeDetails.coverArt || !coverCropperRef.current) return;
    try {
      setIsUploadingCover(true);
      const blob = await coverCropperRef.current.getProcessedBlob();
      if(!blob){ throw new Error('Could not process image.'); }
      const processedFile = new File([blob], (episodeDetails.coverArt.name.replace(/\.[^.]+$/, '') + '-square.png'), { type: 'image/png' });
      await uploadCover(processedFile);
      // Build preview from processed blob
      const reader = new FileReader();
      reader.onloadend = () => {
        setEpisodeDetails(prev => ({ ...prev, coverArtPreview: reader.result }));
      };
      reader.readAsDataURL(blob);
      setCoverNeedsUpload(false);
      toast({ title: 'Cover saved', description: 'Square cover uploaded.' });
    } catch(e) {
      toast({ variant:'destructive', title:'Cover upload failed', description: e.message || String(e) });
    } finally {
      setIsUploadingCover(false);
    }
  };

  const handleTtsChange = (promptId, value) => {
    setTtsValues(prev => ({ ...prev, [promptId]: value }))
  }

  const handleDetailsChange = (field, value) => {
    setEpisodeDetails(prev => ({ ...prev, [field]: value }))
  }

  // Separate AI helpers with lightweight caching
  const suggestTitle = async (opts = {}) => {
    const force = !!opts.force;
    if (!force && aiCacheRef.current.title) return aiCacheRef.current.title;
    const api = makeApi(token);
    const payload = {
      episode_id: expectedEpisodeId || crypto.randomUUID(),
      podcast_id: selectedTemplate?.podcast_id,
      transcript_path: null,
      hint: uploadedFilename || null,
      base_prompt: "",
      extra_instructions: selectedTemplate?.ai_settings?.title_instructions || "",
    };
    let title = "";
    try {
      const res = await api.post('/api/ai/title', payload);
      title = res?.title || "";
    } catch(e) {
      if (e && e.status === 409) {
        setTranscriptReady(false);
        try { toast({ title: 'Transcript not ready', description: 'Transcript not ready yet — still processing', variant: 'default' }); } catch {}
        return "";
      }
      // Generic error (e.g., 429/500): surface a friendly toast without leaking details
      try {
        if (e && e.status === 429) {
          toast({ variant: 'destructive', title: 'AI Title error', description: 'Too many requests — please slow down and try again.' });
        } else {
          const code = e && e.status ? ` (${e.status})` : '';
          toast({ variant: 'destructive', title: 'AI Title error', description: `Request failed${code}. Please try again.` });
        }
      } catch {}
      return "";
    }
    aiCacheRef.current.title = title; // keep small cache but do not block retries
    return title;
  };

  const suggestNotes = async (opts = {}) => {
    const force = !!opts.force;
    if (!force && aiCacheRef.current.notes) return aiCacheRef.current.notes;
    const api = makeApi(token);
    const payload = {
      episode_id: expectedEpisodeId || crypto.randomUUID(),
      podcast_id: selectedTemplate?.podcast_id,
      transcript_path: null,
      hint: uploadedFilename || null,
      base_prompt: "",
      extra_instructions: selectedTemplate?.ai_settings?.notes_instructions || "",
    };
    let desc = "";
    try {
      const res = await api.post('/api/ai/notes', payload);
      desc = res?.description || "";
    } catch(e) {
      if (e && e.status === 409) {
        setTranscriptReady(false);
        try { toast({ title: 'Transcript not ready', description: 'Transcript not ready yet — still processing', variant: 'default' }); } catch {}
        return "";
      }
      // Generic error (e.g., 429/500): surface a friendly toast without leaking details
      try {
        if (e && e.status === 429) {
          toast({ variant: 'destructive', title: 'AI Description error', description: 'Too many requests — please slow down and try again.' });
        } else {
          const code = e && e.status ? ` (${e.status})` : '';
          toast({ variant: 'destructive', title: 'AI Description error', description: `Request failed${code}. Please try again.` });
        }
      } catch {}
      return "";
    }
    aiCacheRef.current.notes = desc; // cache but allow force refresh
    return desc;
  };

  const suggestTags = async () => {
    if (aiCacheRef.current.tags) return aiCacheRef.current.tags;
    const api = makeApi(token);
    const payload = {
      episode_id: expectedEpisodeId || crypto.randomUUID(),
      podcast_id: selectedTemplate?.podcast_id,
      transcript_path: null,
      hint: uploadedFilename || null,
      tags_always_include: selectedTemplate?.ai_settings?.tags_always_include || [],
    };
    const res = await api.post('/api/ai/tags', payload);
    const tags = Array.isArray(res?.tags) ? res.tags : [];
    aiCacheRef.current.tags = tags;
    return tags;
  };

  const handleAISuggestTitle = async () => {
    if (isAiTitleBusy) return;
    setIsAiTitleBusy(true);
    try {
      const title = await suggestTitle({ force: true });
      // reject junky outputs (overcautious client-side guard)
      if (title && !/[a-f0-9]{16,}/i.test(title)) {
        handleDetailsChange('title', title); // allow overwrite on retries
      }
    } finally { setIsAiTitleBusy(false); }
  };

  const handleAISuggestDescription = async () => {
    if (isAiDescBusy) return;
    setIsAiDescBusy(true);
    try {
      const notes = await suggestNotes({ force: true });
      const cleaned = (notes || '')
        .replace(/^(?:\*\*?)?description:?(\*\*)?\s*/i, '')
        .replace(/^#+\s*description\s*/i, '')
        .trim();
      if (cleaned) handleDetailsChange('description', cleaned);
    } finally { setIsAiDescBusy(false); }
  };

  const normalizeTags = (input) => {
    if(!input) return [];
    let parts = Array.isArray(input) ? input : String(input).split(',');
    const clean = [];
    for (let raw of parts) {
      const t = String(raw).trim();
      if(!t) continue;
      let val = t.slice(0,30);
      if(!clean.includes(val)) clean.push(val);
      if(clean.length >= 20) break;
    }
    return clean;
  };

  const handleAssemble = async () => {
    if (quotaExceeded) { setError('Monthly episode quota reached. Upgrade your plan to continue.'); window.dispatchEvent(new Event('ppp:navigate-billing')); return; }
    if (!uploadedFilename || !selectedTemplate || !episodeDetails.title) { setError("A template, title, and audio file are required."); return; }
    // Auto fill season if blank
    if(!episodeDetails.season || !String(episodeDetails.season).trim()) {
      setEpisodeDetails(prev=>({ ...prev, season: '1' }));
    }
    // Validate schedule if schedule mode
    if(publishMode === 'schedule'){
      if(!scheduleDate || !scheduleTime){ setError('Pick date & time for scheduling'); return; }
      const dt = new Date(`${scheduleDate}T${scheduleTime}:00`);
      if(isNaN(dt.getTime()) || dt.getTime() < Date.now()+10*60000){ setError('Scheduled time must be at least 10 minutes in the future.'); return; }
    }
    // If cover selected but not uploaded yet, try to auto-upload instead of blocking
    if(episodeDetails.coverArt && !episodeDetails.cover_image_path){
      try {
        setStatusMessage('Processing cover before assembly...');
        await handleUploadProcessedCover();
      } catch(err){
        setError('Cover processing failed; you can retry or remove the cover.');
        return;
      }
    }
  // Reset previous assembly state to avoid auto-publishing the prior episode again
  setAssemblyComplete(false);
  setAssembledEpisode(null);
  setAutoPublishPending(false);
  setExpectedEpisodeId(null);
  setIsAssembling(true);
    setStatusMessage('Assembling your episode...');
    setError('');
    setCurrentStep(6); // Assemble step
    try {
      const api = makeApi(token);
      // Only send fields backend cares about; drop large preview/data objects
      const sanitizedDetails = {
        title: episodeDetails.title,
        description: episodeDetails.description,
        season: episodeDetails.season,
        episodeNumber: episodeDetails.episodeNumber,
        cover_image_path: episodeDetails.cover_image_path || null,
        explicit: episodeDetails.is_explicit || false,
        tags: normalizeTags(episodeDetails.tags),
      };
      let result;
      try {
        result = await api.post('/api/episodes/assemble', {
          template_id: selectedTemplate.id,
          main_content_filename: uploadedFilename,
          output_filename: episodeDetails.title.toLowerCase().replace(/\s+/g, '-'),
          tts_values: ttsValues,
          episode_details: sanitizedDetails,
          // Pass preselected flubber cuts to be applied first by engine
          flubber_cuts_ms: Array.isArray(flubberCutsMs) && flubberCutsMs.length ? flubberCutsMs : null,
          intents: intents,
        });
      } catch(e) {
        if (e && e.status === 402) {
          const msg = 'Monthly episode quota reached. Upgrade your plan to continue.';
          setError(msg);
          setStatusMessage('');
          toast({ variant: 'destructive', title: 'Quota Reached', description: msg });
          setIsAssembling(false);
          window.dispatchEvent(new Event('ppp:navigate-billing'));
          return;
        }
        throw e;
      }
  if(result.episode_id) setExpectedEpisodeId(result.episode_id);
  setJobId(result.job_id);
  setAutoPublishPending(true); // trigger auto publish on completion if needed
      setStatusMessage(`Episode assembly has been queued. Job ID: ${result.job_id}`);
    } catch (err) {
      setError(err.message);
      setStatusMessage('');
      setIsAssembling(false);
    }
  };

  // Flubber modal handlers
  const handleFlubberConfirm = (cuts) => {
    setFlubberCutsMs(cuts || [])
    setShowFlubberReview(false)
    setCurrentStep(3)
  }
  const handleFlubberCancel = () => {
    setFlubberCutsMs([])
    setShowFlubberReview(false)
    setCurrentStep(3)
  }
  // Intent modal handlers
  const handleIntentSubmit = async (ans) => {
    setIntents(ans);
    setShowIntentQuestions(false);
    // If user says flubber= yes/unknown, attempt context prep before moving on
    try {
      if (uploadedFilename && (ans.flubber==='yes' || ans.flubber==='unknown')){
        setStatusMessage('Scanning for retakes (flubber)...')
        setShowFlubberScan(true)
        // Poll until transcripts are ready (HTTP 425) or we get contexts, up to ~20s
        const api = makeApi(token);
        const payload = { filename: uploadedFilename, intents: { flubber: ans.flubber } };
        let contexts = []
        try {
          for (let attempt = 0; attempt < 20; attempt++) { // 20 x 1s = ~20s max
            try {
              const data = await api.post('/api/flubber/prepare-by-file', payload);
              contexts = Array.isArray(data?.contexts) ? data.contexts : [];
              break;
            } catch (e) {
              if (e && e.status === 425) {
                // Transcript not ready yet; wait and retry
                await new Promise(r => setTimeout(r, 1000))
                continue
              }
              // Any other error: stop polling
              break
            }
            // Should not reach here, but keep retry cadence
              await new Promise(r => setTimeout(r, 1000))
          }
        } catch (_) {
          // fall through to default path
        }
        setShowFlubberScan(false)
        if (contexts.length > 0) {
          setFlubberContexts(contexts)
          setShowFlubberReview(true)
          return // wait for confirm
        }
        // If user said yes but nothing found, show retry modal with fuzzy threshold option
        if (ans.flubber === 'yes') {
          setFlubberNotFound(true)
          return
        }
      }
    } catch(_) { /* non-blocking */ }
    setShowFlubberScan(false)
    setCurrentStep(3)
  }

  const handlePublish = async () => {
    if (!assembledEpisode) {
      setError("Assembled episode required.");
      return;
    }
    // Determine show from template if possible
    let showId = selectedSpreakerShow;
    if (!showId && selectedTemplate && selectedTemplate.podcast_id) {
      // assume backend will map podcast_id -> spreaker_show_id
      showId = selectedTemplate.podcast_id;
    }
    if (!showId) {
      setError("Template is not linked to a show (podcast). Update template to include its show.");
      toast({ variant: 'destructive', title: 'Missing show', description: 'Template needs a show association.' });
      return;
    }
  setIsPublishing(true);
    setStatusMessage('Publishing your episode...');
    setError('');
  const scheduleEnabled = publishMode === 'schedule';
  let publish_at = null;
  let publish_at_local = null; // raw local string (YYYY-MM-DD HH:MM) for display
  if (scheduleEnabled && scheduleDate && scheduleTime) {
      try {
        // Interpret scheduleDate + scheduleTime in local timezone, then convert to UTC ISO
        const local = new Date(`${scheduleDate}T${scheduleTime}:00`);
        if (!isNaN(local.getTime()) && local.getTime() > Date.now() + 60 * 1000) { // at least 1 min in future
          publish_at = new Date(local.getTime()).toISOString(); // includes 'Z' UTC
          publish_at_local = `${scheduleDate} ${scheduleTime}`; // raw, no TZ conversion
        } else {
          toast({ variant: 'destructive', title: 'Invalid schedule time', description: 'Pick a future date/time (>= 1 minute ahead).' });
          setIsPublishing(false);
          return;
        }
      } catch (e) {
        toast({ variant: 'destructive', title: 'Invalid schedule time', description: 'Unable to parse date/time.' });
        setIsPublishing(false);
        return;
      }
    }

    try {
      // If scheduling, we send as 'unpublished' with a future publish_at (Spreaker will publish at time)
      const effectiveState = scheduleEnabled ? 'unpublished' : publishVisibility;
      const payload = {
        spreaker_show_id: showId,
        publish_state: effectiveState,
      };
      if (publish_at) {
        payload.publish_at = publish_at;
        if (publish_at_local) payload.publish_at_local = publish_at_local;
      }
  const api = makeApi(token);
  let result = await api.post(`/api/episodes/${assembledEpisode.id}/publish`, payload);
  if(!result || typeof result !== 'object') result = {};
      if(!result || typeof result !== 'object') result = {};
      const scheduled = !!publish_at;
      const wasPrivate = effectiveState === 'unpublished' && !scheduled;
  const msg = result.message || (scheduled
        ? 'Episode scheduled for future publish.'
        : wasPrivate ? 'Episode uploaded privately to Spreaker.' : 'Episode published publicly.');
      setStatusMessage(msg);
      toast({ title: 'Success!', description: msg });
  try { if(assembledEpisode?.id) setLastAutoPublishedEpisodeId(assembledEpisode.id); } catch {}
  setCurrentStep(6);

    } catch (err) {
      const friendly = err && err.message ? err.message : (typeof err === 'string' ? err : 'Publish failed');
      setError(friendly);
      setStatusMessage('');
      toast({ variant: "destructive", title: "Error", description: friendly });
    } finally {
      setIsPublishing(false);
    }
  };

  const remainingEpisodes = usage?.episodes_remaining_this_month;
  const maxEpisodes = usage?.max_episodes_month;
  const nearQuota = typeof remainingEpisodes === 'number' && typeof maxEpisodes === 'number' && remainingEpisodes > 0 && remainingEpisodes <= Math.ceil(maxEpisodes * 0.1);
  const quotaExceeded = typeof remainingEpisodes === 'number' && remainingEpisodes <= 0;

  // REPLACE episode-based quota with minutes-based (placeholder until backend provides fields)
  const minutesUsed = usage?.processing_minutes_used_this_month; // new expected field
  const minutesCap = usage?.max_processing_minutes_month;       // new expected field
  const minutesRemaining = (typeof minutesCap === 'number' && typeof minutesUsed === 'number') ? (minutesCap - minutesUsed) : null;
  const minutesNearCap = (typeof minutesRemaining === 'number' && typeof minutesCap === 'number') && minutesRemaining > 0 && minutesRemaining <= Math.ceil(minutesCap * 0.1);
  const minutesExceeded = typeof minutesRemaining === 'number' && minutesRemaining <= 0;

  // Relax gating: only require title & episode number; season auto-defaults; show inline reason if disabled
  const missingTitle = !episodeDetails.title || !episodeDetails.title.trim();
  const missingEpisodeNumber = !episodeDetails.episodeNumber || !String(episodeDetails.episodeNumber).trim();
  const blockingQuota = quotaExceeded;
  const canProceedToStep5 = !missingTitle && !missingEpisodeNumber && !blockingQuota;

  // In Test Mode, auto-fill UI fields on Step 5 so the user can proceed (mirrors backend overrides)
  useEffect(() => {
    if (currentStep !== 5 || !testMode) return;
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, '0');
    const mm = String(now.getMinutes()).padStart(2, '0');
    const hhmm = `${hh}${mm}`;
    const day = String(now.getDate());
    const fileStem = (() => {
      try {
        if (uploadedFile?.name) return uploadedFile.name.replace(/\.[^./\\]+$/, '');
        if (uploadedFilename) return String(uploadedFilename).replace(/\.[^./\\]+$/, '');
      } catch {}
      return 'Episode';
    })();
    setEpisodeDetails(prev => ({
      ...prev,
      title: prev.title && prev.title.trim() ? prev.title : `Test - ${fileStem}`,
      season: day,
      episodeNumber: hhmm,
    }));
  }, [currentStep, uploadedFile, uploadedFilename, testMode]);

  // Auto-publish logic after assembly completes
  useEffect(() => {
    if(!assemblyComplete || !autoPublishPending || !assembledEpisode) return;
    // Guard against re-publishing same episode (stale state)
    if(lastAutoPublishedEpisodeId && assembledEpisode.id === lastAutoPublishedEpisodeId){
      setAutoPublishPending(false);
      return;
    }
    if(publishMode === 'draft'){ setAutoPublishPending(false); setStatusMessage('Draft created (processing complete).'); return; }
    // Prepare schedule fields
    let scheduleEnabled = publishMode === 'schedule';
    let publish_at=null, publish_at_local=null;
    if(scheduleEnabled){
      const dt = new Date(`${scheduleDate}T${scheduleTime}:00`);
      if(!isNaN(dt.getTime()) && dt.getTime() > Date.now()+9*60000){
        publish_at = dt.toISOString().replace(/\.\d{3}Z$/, 'Z');
        publish_at_local = `${scheduleDate} ${scheduleTime}`;
      } else {
        toast({ variant: 'destructive', title: 'Schedule invalid', description: 'Falling back to draft.' });
        setAutoPublishPending(false); return;
      }
    }
    (async () => {
      setIsPublishing(true);
      try {
        await handlePublishInternal({ scheduleEnabled, publish_at, publish_at_local });
      } finally { setIsPublishing(false); setAutoPublishPending(false); }
    })();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assemblyComplete, autoPublishPending, assembledEpisode]);

  const handlePublishInternal = async ({ scheduleEnabled, publish_at, publish_at_local }) => {
    // Derived from existing handlePublish logic with injected params
    let showId = selectedSpreakerShow;
    if (!showId && selectedTemplate && selectedTemplate.podcast_id) showId = selectedTemplate.podcast_id;
    if (!showId) { toast({ variant:'destructive', title:'Missing show', description:'Template needs a show association.' }); return; }
    let effectiveState = scheduleEnabled ? 'unpublished' : publishVisibility;
    const payload = { spreaker_show_id: showId, publish_state: effectiveState };
    if(publish_at){ payload.publish_at = publish_at; if(publish_at_local) payload.publish_at_local = publish_at_local; }
    try {
      const api = makeApi(token);
      let result = await api.post(`/api/episodes/${assembledEpisode.id}/publish`, payload);
  const msg = scheduleEnabled? 'Episode scheduled successfully.' : 'Episode published successfully.';
      toast({ title:'Publish', description: msg });
      setStatusMessage(msg);
  try { if(assembledEpisode?.id) setLastAutoPublishedEpisodeId(assembledEpisode.id); } catch {}
      try {
        const pubData = await api.get(`/api/episodes/${assembledEpisode.id}/publish/status`);
          if(pubData.spreaker_episode_id){
            setStatusMessage(prev => prev.includes('Spreaker ID')? prev : prev + ' (Spreaker ID ' + pubData.spreaker_episode_id + ')');
          } else if(pubData.last_error){
            toast({ variant:'destructive', title:'Publish downstream error', description: pubData.last_error });
          }
      } catch {/* ignore */}
    } catch(e){ toast({ variant:'destructive', title:'Publish failed', description: e.message || String(e) }); }
  };

  const handleAISuggest = async () => {
    try {
      const api = makeApi(token);
      const data = await api.post('/api/episodes/ai/metadata', {
        audio_filename: uploadedFilename,
        current_title: episodeDetails.title || null,
        current_description: episodeDetails.description || null,
        prompt: episodeDetails.description || episodeDetails.title || uploadedFilename,
        max_tags: 12,
      });
      if(data){
        setEpisodeDetails(prev => ({
          ...prev,
          title: prev.title || data.title,
            description: prev.description?.length ? prev.description : data.description,
            tags: (prev.tags && prev.tags.length) ? prev.tags : (data.tags || []).join(', '),
        }));
        toast({ title: 'AI Suggestions Applied', description: 'Title, description, and tags populated.' });
      }
    } catch(e){
      toast({ variant:'destructive', title:'AI Suggest Failed', description: e.message || String(e) });
    }
  };

  const renderStepContent = () => {
    switch (currentStep) {
      case 1: // Select Template
        return (
          <div className="space-y-8">
            <CardHeader className="text-center"><CardTitle style={{ color: "#2C3E50" }}>Step 1: Choose a Template</CardTitle></CardHeader>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
              {templates.map(template => (
                <Card key={template.id} className="cursor-pointer hover:shadow-lg transition-shadow" onClick={() => handleTemplateSelect(template)}>
                  <CardContent className="p-6 text-center space-y-4">
                    <BookText className="w-12 h-12 mx-auto text-blue-600" />
                    <h3 className="text-xl font-semibold">{template.name}</h3>
                    <p className="text-gray-500 text-sm">{template.description || "No description available."}</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        )
      case 2: // Upload Content
        return (
          <div className="space-y-8">
            <CardHeader className="text-center"><CardTitle style={{ color: "#2C3E50" }}>Step 2: Upload Main Content</CardTitle></CardHeader>
            <Card className="border-2 border-dashed border-gray-200 bg-white">
              <CardContent className="p-8">
                <div className="border-2 border-dashed rounded-xl p-12 text-center" onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); if (e.dataTransfer.files[0]) handleFileChange(e.dataTransfer.files[0])}}>
                  {uploadedFile ? (
                    <div className="space-y-6">
                      <FileAudio className="w-16 h-16 mx-auto text-green-600" />
                      <p className="text-xl font-semibold text-green-600">File Ready!</p>
                      <p className="text-gray-600">{uploadedFile.name}</p>
                    </div>
                  ) : (
                    <div className="space-y-6">
                      <Mic className="w-16 h-16 mx-auto text-gray-400" />
                      <p className="text-2xl font-semibold text-gray-700">Drag your audio file here</p>
                      <p className="text-gray-500">or</p>
                      <Button onClick={() => fileInputRef.current?.click()} size="lg" className="text-white" style={{ backgroundColor: "#2C3E50" }} disabled={isUploading}>
                        {isUploading ? <><Loader2 className="w-5 h-5 mr-2 animate-spin" /> Uploading...</> : <><Upload className="w-5 h-5 mr-2" /> Choose Audio File</>}
                      </Button>
                    </div>
                  )}
                  <input ref={fileInputRef} type="file" accept="audio/*" onChange={(e) => handleFileChange(e.target.files[0])} className="hidden" />
                </div>
              </CardContent>
            </Card>
             <div className="flex justify-start pt-8">
                <Button onClick={() => setCurrentStep(1)} variant="outline" size="lg"><ArrowLeft className="w-5 h-5 mr-2" />Back to Templates</Button>
            </div>
          </div>
        )
  case 3: { // Customize Episode
        const getSegmentContent = (segment) => {
          if (segment.segment_type === 'content') {
            return (
              <div className="mt-2 bg-blue-50 p-3 rounded-md">
                <p className="font-semibold text-blue-800">Your Uploaded Audio:</p>
                <p className="text-gray-700">{uploadedFile?.name || 'No file uploaded'}</p>
              </div>
            );
          }

          if (segment.source.source_type === 'tts') {
            const voiceId = segment?.source?.voice_id || '';
            const friendly = voiceNameById[voiceId];
            return (
              <div className="mt-4">
                <div className="mt-2 flex items-center justify-between">
                  <span className="text-xs text-gray-500" title={voiceId || undefined}>
                    Voice: {friendly || (voiceId || 'default')}{voicesLoading && !friendly ? '…' : ''}
                  </span>
                  <Button size="sm" variant="outline" onClick={() => { setVoicePickerTargetId(segment.id); setShowVoicePicker(true); }}>
                    Change voice
                  </Button>
                </div>
                <Label htmlFor={segment.id} className="text-sm font-medium text-gray-700 mb-2 block">
                  {segment.source.text_prompt || 'TTS Script'}
                </Label>
                <Textarea
                  id={segment.id}
                  placeholder="Enter text to be converted to speech..."
                  className="min-h-[100px] resize-none text-base bg-white"
                  value={ttsValues[segment.id] || ''}
                  onChange={(e) => handleTtsChange(segment.id, e.target.value)}
                />
              </div>
            );
          }

          if (segment.source.source_type === 'static') {
            const mediaItem = mediaLibrary.find(item => item.filename.endsWith(segment.source.filename));
            const friendlyName = mediaItem ? mediaItem.friendly_name : segment.source.filename;
            return (
              <p className="text-gray-600 mt-2">
                <span className="font-semibold text-gray-700">Audio File:</span> {friendlyName}
              </p>
            );
          }

          return <p className="text-red-500 mt-2">Unknown segment source type</p>;
        };

        return (
          <div className="space-y-8">
            <CardHeader className="text-center">
              <CardTitle style={{ color: "#2C3E50" }}>Step 3: Customize Your Episode</CardTitle>
              <p className="text-md text-gray-500 pt-2">Review the structure and fill in the required text for any AI-generated segments.</p>
            </CardHeader>
            <Card className="border-0 shadow-lg bg-white">
              <CardContent className="p-6 space-y-4">
                {selectedTemplate && selectedTemplate.segments ? (
                  selectedTemplate.segments.map((segment, index) => (
                    <div key={segment.id || index} className="p-4 rounded-md bg-gray-50 border border-gray-200">
                      <h4 className="font-semibold text-lg text-gray-800 capitalize">
                        {segment.segment_type.replace('_', ' ')}
                      </h4>
                      {getSegmentContent(segment)}
                    </div>
                  ))
                ) : (
                  <div className="text-center py-12">
                    <p className="text-lg text-gray-600">This template has no segments to display.</p>
                  </div>
                )}
              </CardContent>
            </Card>
            <div className="flex justify-between pt-8">
              <Button onClick={() => setCurrentStep(2)} variant="outline" size="lg"><ArrowLeft className="w-5 h-5 mr-2" />Back to Upload</Button>
              <Button onClick={() => setCurrentStep(4)} size="lg" className="px-8 py-3 text-lg font-semibold text-white" style={{ backgroundColor: "#2C3E50" }}>Continue to Details<ArrowLeft className="w-5 h-5 ml-2 rotate-180" /></Button>
            </div>
          </div>
        );
  }
  case 4: // Cover Art with cropping
        return (
          <div className="space-y-8">
            <CardHeader className="text-center"><CardTitle style={{ color: "#2C3E50" }}>Step 4: Cover Art</CardTitle></CardHeader>
            <Card className="border-0 shadow-lg bg-white">
              <CardContent className="p-8 space-y-6">
                <div className="space-y-4">
                  {!episodeDetails.coverArt && !episodeDetails.coverArtPreview && (
                    <div className="border-2 border-dashed rounded-xl p-10 text-center" onDragOver={(e)=>e.preventDefault()} onDrop={(e)=>{e.preventDefault(); if(e.dataTransfer.files[0]) handleCoverFileSelected(e.dataTransfer.files[0]);}}>
                      <FileImage className="w-16 h-16 mx-auto text-gray-400" />
                      <p className="mt-4 text-gray-600">Drag & drop a cover image or click below.</p>
                      <Button className="mt-4" variant="outline" onClick={()=>coverArtInputRef.current?.click()}><Upload className="w-4 h-4 mr-2" />Choose Image</Button>
                      <input ref={coverArtInputRef} type="file" accept="image/*" onChange={(e)=>handleCoverFileSelected(e.target.files[0])} className="hidden" />
                      <p className="text-xs text-gray-500 mt-4">Recommended: ≥1400x1400 JPG/PNG.</p>
                    </div>
                  )}
                  {episodeDetails.coverArt && !episodeDetails.coverArtPreview && (
                    <div className="space-y-4">
                      <CoverCropper
                        ref={coverCropperRef}
                        sourceFile={episodeDetails.coverArt}
                        existingUrl={null}
                        value={episodeDetails.cover_crop}
                        onChange={(val)=>setEpisodeDetails(p=>({...p, cover_crop: val }))}
                        onModeChange={(m)=>setCoverMode(m)}
                      />
                      <div className="flex gap-2 flex-wrap">
                        <Button size="sm" variant="outline" onClick={()=>coverArtInputRef.current?.click()}><Upload className="w-4 h-4 mr-1" />Replace</Button>
                        <Button size="sm" variant="ghost" onClick={()=>{setEpisodeDetails(p=>({...p, coverArt:null, coverArtPreview:null, cover_image_path:null, cover_crop:null})); setCoverNeedsUpload(false);}}>Remove</Button>
                        {coverNeedsUpload && <span className="text-xs text-amber-600 font-medium">Will upload on Continue</span>}
                      </div>
                    </div>
                  )}
                  {episodeDetails.coverArtPreview && (
                    <div className="flex flex-col md:flex-row gap-10 items-start">
                      <div className="w-48 h-48 rounded-lg overflow-hidden border bg-gray-50">
                        <img src={episodeDetails.coverArtPreview} alt="Cover preview" className="w-full h-full object-cover" />
                      </div>
                      <div className="space-y-3 text-sm">
                        <p className="text-gray-600">Square cover uploaded{episodeDetails.cover_image_path && <> as <span className="text-green-600">{episodeDetails.cover_image_path}</span></>}.</p>
                        <div className="flex gap-2 flex-wrap">
                          <Button size="sm" variant="outline" onClick={()=>{coverArtInputRef.current?.click();}}><Upload className="w-4 h-4 mr-1" />Replace</Button>
                          <Button size="sm" variant="ghost" onClick={()=>{setEpisodeDetails(p=>({...p, coverArt:null, coverArtPreview:null, cover_image_path:null, cover_crop:null})); setCoverNeedsUpload(false);}}>Remove</Button>
                        </div>
                        <input ref={coverArtInputRef} type="file" accept="image/*" onChange={(e)=>handleCoverFileSelected(e.target.files[0])} className="hidden" />
                      </div>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
            <div className="flex justify-between pt-8">
              <Button onClick={()=>setCurrentStep(3)} variant="outline" size="lg"><ArrowLeft className="w-5 h-5 mr-2" />Back</Button>
              <div className="flex gap-3">
                <Button onClick={()=>setCurrentStep(5)} variant="outline" size="lg">Skip</Button>
                <Button
                  onClick={async ()=>{
                    if(episodeDetails.coverArt && coverNeedsUpload){
                      await handleUploadProcessedCover();
                    }
                    setCurrentStep(5);
                  }}
                  size="lg"
                  disabled={isUploadingCover}
                  className="px-8 py-3 text-lg font-semibold text-white disabled:opacity-70" style={{ backgroundColor:'#2C3E50' }}>
                  {coverNeedsUpload? 'Upload & Continue':'Continue'} <ArrowLeft className="w-5 h-5 ml-2 rotate-180" />
                </Button>
              </div>
            </div>
          </div>
        );
  case 5: // Details & Schedule (cover art removed from this step)
        return (
          <div className="space-y-8">
    <CardHeader className="text-center"><CardTitle style={{ color: "#2C3E50" }}>Step 5: Episode Details & Scheduling</CardTitle></CardHeader>
            <Card className="border-0 shadow-lg bg-white">
              <CardContent className="p-6 space-y-6">
                <div className="grid md:grid-cols-2 gap-6">
                  <div className="col-span-2 md:col-span-1">
                    <Label htmlFor="title">Episode Title *</Label>
                    <Input id="title" placeholder="e.g., The Future of AI" value={episodeDetails.title} onChange={(e) => handleDetailsChange('title', e.target.value)} />
                    <div className="mt-2 flex gap-2">
                      <Button
                        type="button"
                        variant="secondary"
                        onClick={handleAISuggestTitle}
                        disabled={!transcriptReady || isAssembling || isPublishing || isAiTitleBusy}
                      >
                        <Wand2 className="w-4 h-4 mr-1" /> AI Suggest Title
                      </Button>
                      {!transcriptReady && (
                        <span className="text-xs text-gray-500 flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" /> Waiting for transcript…</span>
                      )}
                    </div>
                  </div>
                </div>
                <div className="grid md:grid-cols-3 gap-6">
                  <div>
                    <Label htmlFor="season">Season Number *</Label>
                    <Input id="season" type="number" placeholder="e.g., 1" value={episodeDetails.season} onChange={(e) => handleDetailsChange('season', e.target.value)} />
                  </div>
                  <div>
                    <Label htmlFor="episodeNumber">Episode Number *</Label>
                    <Input id="episodeNumber" type="number" placeholder="e.g., 12" value={episodeDetails.episodeNumber} onChange={(e) => handleDetailsChange('episodeNumber', e.target.value)} />
                  </div>
                  <div className="flex items-center pt-6 gap-2">
                    <input id="explicitFlag" type="checkbox" checked={!!episodeDetails.is_explicit} onChange={e=>handleDetailsChange('is_explicit', e.target.checked)} />
                    <Label htmlFor="explicitFlag" className="cursor-pointer">Explicit</Label>
                  </div>
                </div>
                <div>
                  <Label htmlFor="description">Episode Description</Label>
                  <Textarea id="description" placeholder="Describe what this episode is about..." className="min-h-[120px]" value={episodeDetails.description} onChange={(e) => handleDetailsChange('description', e.target.value)} />
                  <div className="mt-2 flex gap-2">
                    <Button
                      type="button"
                      variant="secondary"
                      onClick={handleAISuggestDescription}
                      disabled={!transcriptReady || isAssembling || isPublishing || isAiDescBusy}
                    >
                      <Wand2 className="w-4 h-4 mr-1" /> AI Suggest Description
                    </Button>
                    {!transcriptReady && (
                      <span className="text-xs text-gray-500 flex items-center gap-1"><Loader2 className="w-3 h-3 animate-spin" /> Waiting for transcript…</span>
                    )}
                  </div>
                </div>
                <div>
                  <Label htmlFor="tags">Tags (comma separated, max 20)</Label>
                  <Textarea id="tags" placeholder="tag1, tag2" className="min-h-[64px]" value={episodeDetails.tags || ''} onChange={(e)=>handleDetailsChange('tags', e.target.value)} />
                  <p className="text-xs text-gray-500 mt-1">Each tag ≤30 chars. Enforced on publish.</p>
                </div>
                <div className="space-y-3 pt-4 border-t">
                  <Label className="font-medium">Publish Options</Label>
                  <div className="flex flex-col gap-2 text-sm">
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input type="radio" name="pubmode" value="now" checked={publishMode==='now'} onChange={()=>setPublishMode('now')} />
                      Publish Immediately (after assembly)
                    </label>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input type="radio" name="pubmode" value="draft" checked={publishMode==='draft'} onChange={()=>setPublishMode('draft')} />
                      Save as Draft (no publish)
                    </label>
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input type="radio" name="pubmode" value="schedule" checked={publishMode==='schedule'} onChange={()=>setPublishMode('schedule')} />
                      Schedule Publish
                    </label>
                  </div>
                  {publishMode==='schedule' && (
                    <div className="grid grid-cols-2 gap-4 text-sm mt-2">
                      <div>
                        <label htmlFor="schedule-date" className="text-xs font-medium mb-1 block">Date</label>
                        <input id="schedule-date" aria-label="Schedule date" type="date" className="border rounded p-2 w-full" value={scheduleDate} onChange={e=>setScheduleDate(e.target.value)} />
                      </div>
                      <div>
                        <label htmlFor="schedule-time" className="text-xs font-medium mb-1 block">Time</label>
                        <input id="schedule-time" aria-label="Schedule time" type="time" step={300} className="border rounded p-2 w-full" value={scheduleTime} onChange={e=>setScheduleTime(e.target.value)} />
                      </div>
                      <div className="col-span-2 text-xs text-gray-500">Must be ≥10 minutes in the future. Converted to UTC automatically.</div>
                    </div>
                  )}
                  {publishMode==='now' && (
                    <div className="mt-2">
                      <span className="text-xs font-medium">Visibility:</span>
                      <div className="flex gap-4 mt-1 text-sm">
                        <label className="flex items-center gap-1"><input type="radio" name="vis" value="public" checked={publishVisibility==='public'} onChange={()=>setPublishVisibility('public')} />Public</label>
                        <label className="flex items-center gap-1"><input type="radio" name="vis" value="unpublished" checked={publishVisibility==='unpublished'} onChange={()=>setPublishVisibility('unpublished')} />Private</label>
                      </div>
                    </div>
                  )}
                </div>
              </CardContent>
            </Card>
            <div className="flex justify-between pt-8">
              <Button onClick={() => setCurrentStep(4)} variant="outline" size="lg"><ArrowLeft className="w-5 h-5 mr-2" />Back</Button>
              <div className="flex flex-col items-end">
                <Button onClick={handleAssemble} disabled={!canProceedToStep5 || isAssembling} size="lg" className="px-8 py-3 text-lg font-semibold text-white disabled:opacity-70" style={{ backgroundColor: '#2C3E50' }}>{isAssembling ? 'Assembling...' : 'Assemble & Review'}<ArrowLeft className="w-5 h-5 ml-2 rotate-180" /></Button>
                {!canProceedToStep5 && (
                  <div className="text-xs text-red-600 mt-2 max-w-sm text-right">
                    {blockingQuota ? 'Quota exceeded – upgrade or wait for reset.' : missingTitle ? 'Enter a title to continue.' : missingEpisodeNumber ? 'Enter an episode number to continue.' : ''}
                  </div>
                )}
              </div>
            </div>
          </div>
        )
      case 6: // Assemble & Review / Complete
        if (!assemblyComplete) {
          return (
            <div className="space-y-8">
              <CardHeader className="text-center"><CardTitle style={{ color: "#2C3E50" }}>Step 6: Assembly In Progress</CardTitle></CardHeader>
              <Card className="border-0 shadow-lg bg-white">
                <CardContent className="p-8 space-y-6 text-center">
                  <Loader2 className="w-16 h-16 mx-auto text-blue-600 animate-spin" />
                  <p className="text-xl font-semibold text-blue-600 mt-4">We're assembling your episode in the background.</p>
                  {processingEstimate ? (
                    <p className="text-gray-700 max-w-xl mx-auto">
                      Processing time for this episode should be approximately {processingEstimate.low}-{processingEstimate.high} min. You can stay here or go back to the dashboard and we'll let you know when it's done.
                    </p>
                  ) : (
                    <p className="text-gray-600 max-w-xl mx-auto">You can safely leave this screen. You'll receive a notification when it's ready. This typically takes a few minutes depending on length and cleanup.</p>
                  )}
                  <div className="text-sm text-gray-500">If you stay, this page will auto-update when complete.</div>
                  <Button onClick={onBack} variant="outline" className="mt-4">Back to Dashboard</Button>
                </CardContent>
              </Card>
            </div>
          );
        } else {
          return (
            <div className="space-y-8">
              <CardHeader className="text-center"><CardTitle style={{ color: "#2C3E50" }}>Step 6: {publishMode==='draft' ? 'Draft Ready' : (publishMode==='schedule' ? 'Scheduled' : 'Completed')}</CardTitle></CardHeader>
              <Card className="border-0 shadow-lg bg-white">
                <CardContent className="p-6 space-y-6">
                  <h3 className="text-2xl font-bold">{assembledEpisode.title}</h3>
                  <p className="text-gray-600">{assembledEpisode.description}</p>
                  {assembledEpisode.final_audio_url && (
                    <div className="mt-4">
                      <Label>Listen to the final episode:</Label>
                      <audio controls src={assembledEpisode.final_audio_url} className="w-full mt-2">
                        Your browser does not support the audio element.
                      </audio>
                    </div>
                  )}
                  <div className="p-4 border rounded bg-gray-50 text-sm">
                    {publishMode==='draft' && 'Episode saved as draft.'}
                    {publishMode==='schedule' && 'Episode assembled and scheduled.'}
                    {publishMode==='now' && 'Episode assembled; publish dispatched.'}
                  </div>
                  {statusMessage && statusMessage.includes('Removed fillers') && (
                    <div className="mt-2 text-xs text-gray-500">{statusMessage.split(' | ').slice(1).join(' | ')}</div>
                  )}
                  {statusMessage && (
                    <div className="text-sm text-gray-600">{statusMessage}</div>
                  )}
                  <div className="flex justify-end pt-4">
                    <Button onClick={onBack}>Back to Dashboard</Button>
                  </div>
                </CardContent>
              </Card>
            </div>
          );
        }
      default:
        return <div>Invalid Step</div>
    }
  }

  return (
    <div className="bg-gray-50 min-h-screen">
      {showFlubberScan && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="bg-white rounded-md p-6 shadow-lg flex flex-col items-center gap-3">
            <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
            <div className="text-sm text-gray-700">Scanning for retakes (this can take a few minutes on long audio)…</div>
            <div className="flex gap-2 mt-2">
              <Button variant="outline" size="sm" onClick={()=>{ setShowFlubberScan(false); setCurrentStep(3); }}>Skip for now</Button>
            </div>
          </div>
        </div>
      )}
      {showFlubberReview && (
        <FlubberQuickReview
          contexts={flubberContexts || []}
          open={showFlubberReview}
          onConfirm={handleFlubberConfirm}
          onCancel={handleFlubberCancel}
        />
      )}
      {showIntentQuestions && (
        <IntentQuestions
          open={showIntentQuestions}
          onSubmit={handleIntentSubmit}
          onCancel={()=> { setShowIntentQuestions(false); setCurrentStep(3); }}
          hide={{
            flubber:false,
            intern: !(capabilities.has_elevenlabs || capabilities.has_google_tts),
            sfx: !capabilities.has_any_sfx_triggers,
          }}
        />
      )}
      {flubberNotFound && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <Card className="w-full max-w-md">
            <CardHeader><CardTitle className="text-base">No retakes detected</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="text-sm text-gray-700">You answered “Yes” to Flubber but nothing was found. Try a fuzzier search?</div>
              <div className="text-xs text-gray-600">Fuzzy threshold (0.5–0.95):</div>
              <input type="range" min={0.5} max={0.95} step={0.05} value={fuzzyThreshold}
                     onChange={e=>setFuzzyThreshold(parseFloat(e.target.value))} className="w-full" />
              <div className="text-xs">Current: {fuzzyThreshold.toFixed(2)}</div>
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="ghost" onClick={()=>{ setFlubberNotFound(false); setCurrentStep(3); }}>Skip</Button>
                <Button onClick={async ()=>{
                  setFlubberNotFound(false);
                  if(!uploadedFilename) { setCurrentStep(3); return; }
                  try {
                    setShowFlubberScan(true);
                    const api = makeApi(token);
                    const payload = { filename: uploadedFilename, intents: { flubber: 'yes' }, fuzzy_threshold: fuzzyThreshold };
                    let contexts = []
                    for (let attempt = 0; attempt < 20; attempt++) {
                      try {
                        const data = await api.post('/api/flubber/prepare-by-file', payload);
                        contexts = Array.isArray(data?.contexts) ? data.contexts : []
                        break
                      } catch (e) {
                        if (e && e.status === 425) {
                          await new Promise(r => setTimeout(r, 1000))
                          continue
                        }
                        break
                      }
                    }
                    setShowFlubberScan(false);
                    if(contexts.length){ setFlubberContexts(contexts); setShowFlubberReview(true); }
                    else { setCurrentStep(3); }
                  } catch(_){ setShowFlubberScan(false); setCurrentStep(3); }
                }}>Retry</Button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
      <header className="border-b border-gray-200 px-4 py-6 bg-white shadow-sm sticky top-0 z-10">
        <div className="container mx-auto max-w-6xl">
          <div className="flex items-center justify-between">
            <Button variant="ghost" className="text-gray-600" onClick={onBack}>
              <ArrowLeft className="w-4 h-4 mr-2" />
              Back to Dashboard
            </Button>
            <h1 className="text-3xl font-bold" style={{ color: "#2C3E50" }}>Episode Creator</h1>
            <div className="w-48 text-right">
                {selectedTemplate && <span className="text-sm text-gray-500">Template: {selectedTemplate.name}</span>}
            </div>
          </div>
        </div>
      </header>
      <div className="px-4 py-6 bg-white border-b border-gray-100">
        <div className="container mx-auto max-w-6xl">
          <RecurringScheduleManager token={token} templates={templates} onApply={(slot) => {
            setSelectedTemplate(templates.find(t=>t.id===slot.template_id));
            setScheduleDate('2025-08-19'); // next occurrence logic can be improved
            setScheduleTime(slot.time_of_day);
            setPublishMode('schedule');
            setCurrentStep(2);
          }} />
          <Progress value={progressPercentage} className="h-2 mb-6" />
          <div className="flex justify-between">
            {steps.map((step) => (
              <div key={step.number} className={`flex flex-col items-center transition-all w-40 text-center ${currentStep >= step.number ? "text-blue-600" : "text-gray-600"}`}>
                <div className={`w-12 h-12 rounded-full flex items-center justify-center mb-3 transition-all ${currentStep >= step.number ? "text-white shadow-lg" : "bg-gray-100 text-gray-600"}`} style={{ backgroundColor: currentStep >= step.number ? "#2C3E50" : undefined }}>
                  {currentStep > step.number ? <CheckCircle className="w-6 h-6" /> : <step.icon className="w-6 h-6" />}
                </div>
                <div className="font-semibold text-sm">{step.title}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="px-4 py-2 bg-yellow-50 border-b border-yellow-100 text-sm">
        {usage && (
          <div className={`text-center ${minutesNearCap ? 'text-amber-600 font-medium' : ''}`}>
            Processing minutes remaining this month: <span className="font-semibold">{(usage?.max_processing_minutes_month == null) ? '∞' : (minutesRemaining ?? '—')}</span>
            {(usage?.max_processing_minutes_month == null) ? ' (unlimited during beta)' : (minutesNearCap ? ' (near limit)' : '')}
          </div>
        )}
      </div>
  <main className="container mx-auto max-w-6xl px-4 py-8" role="main" aria-label="Episode Creator main content" tabIndex={-1}>
        {renderStepContent()}
      </main>
      {showVoicePicker && activeSegment && (
        <VoicePicker
          value={activeSegment?.source?.voice_id || null}
          onChange={(id) => handleVoiceChange(id)}
          onClose={() => { setShowVoicePicker(false); setVoicePickerTargetId(null); }}
        />
      )}
    </div>
  )
}
