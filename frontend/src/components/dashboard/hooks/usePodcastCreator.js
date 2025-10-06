import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from '@/hooks/use-toast';
import { makeApi, coerceArray } from '@/lib/apiClient';
import { uploadMediaDirect } from '@/lib/directUpload';
import { fetchVoices as fetchElevenVoices } from '@/api/elevenlabs';
import { useAuth } from '@/AuthContext.jsx';

export default function usePodcastCreator({
  token,
  templates,
  initialStep,
  testInject,
  preselectedMainFilename,
  preselectedTranscriptReady,
  creatorMode = 'standard',
  preselectedStartStep,
}) {
  const { user: authUser } = useAuth();
  const [currentStep, setCurrentStep] = useState(initialStep || 1);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [uploadedFile, setUploadedFile] = useState(null);
  const [uploadedFilename, setUploadedFilename] = useState(null);
  const [selectedPreupload, setSelectedPreupload] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const uploadXhrRef = useRef(null);
  const [isAssembling, setIsAssembling] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);
  const [assemblyComplete, setAssemblyComplete] = useState(false);
  const [assembledEpisode, setAssembledEpisode] = useState(null);
  const [expectedEpisodeId, setExpectedEpisodeId] = useState(null);
  const [statusMessage, setStatusMessage] = useState('');
  const [error, setError] = useState('');
  const [ttsValues, setTtsValues] = useState({});
  const [mediaLibrary, setMediaLibrary] = useState([]);
  const [showFlubberReview, setShowFlubberReview] = useState(false);
  const [flubberContexts, setFlubberContexts] = useState(null);
  const [flubberCutsMs, setFlubberCutsMs] = useState(null);
  const [internPendingContexts, setInternPendingContexts] = useState(null);
  const [internReviewContexts, setInternReviewContexts] = useState([]);
  const [showInternReview, setShowInternReview] = useState(false);
  const [internResponses, setInternResponses] = useState([]);
  const [internPrefetch, setInternPrefetch] = useState({ status: 'idle', filename: null, contexts: [], log: null, error: null });
  const [showIntentQuestions, setShowIntentQuestions] = useState(false);
  const intentsPromptedRef = useRef(false);
  const [intents, setIntents] = useState({ flubber: null, intern: null, sfx: null, intern_overrides: [] });
  const [intentDetections, setIntentDetections] = useState({ flubber: null, intern: null, sfx: null });
  const [intentDetectionReady, setIntentDetectionReady] = useState(true);
  const [showFlubberScan, setShowFlubberScan] = useState(false);
  const [capabilities, setCapabilities] = useState({ has_elevenlabs:false, has_google_tts:false, has_any_sfx_triggers:false });
  const [flubberNotFound, setFlubberNotFound] = useState(false);
  const [fuzzyThreshold, setFuzzyThreshold] = useState(0.8);
  const [testMode, setTestMode] = useState(false);
  const [usage, setUsage] = useState(null);
  const [minutesDialog, setMinutesDialog] = useState(null);
  const [minutesPrecheck, setMinutesPrecheck] = useState(null);
  const [minutesPrecheckPending, setMinutesPrecheckPending] = useState(false);
  const [minutesPrecheckError, setMinutesPrecheckError] = useState(null);
  const [episodeDetails, setEpisodeDetails] = useState({
    season: '1',
    episodeNumber: '',
    title: '',
    description: '',
    coverArt: null,
    coverArtPreview: null,
    cover_image_path: null,
    cover_crop: null,
  });
  const [isAiTitleBusy, setIsAiTitleBusy] = useState(false);
  const [isAiDescBusy, setIsAiDescBusy] = useState(false);
  const aiCacheRef = useRef({ title: null, notes: null, tags: null });
  const autoFillKeyRef = useRef('');
  const autoRecurringRef = useRef({ templateId: null, date: null, time: null, manual: false });
  const transcriptReadyRef = useRef(false);
  const [jobId, setJobId] = useState(null);
  const [spreakerShows, setSpreakerShows] = useState([]);
  const [selectedSpreakerShow, setSelectedSpreakerShow] = useState(null);
  const [publishMode, setPublishMode] = useState('draft');
  const [publishVisibility, setPublishVisibility] = useState('public');
  const [scheduleDate, setScheduleDate] = useState('');
  const [scheduleTime, setScheduleTime] = useState('');
  const [autoPublishPending, setAutoPublishPending] = useState(false);
  const [lastAutoPublishedEpisodeId, setLastAutoPublishedEpisodeId] = useState(null);
  const publishingTriggeredRef = useRef(false); // Track if publishing already triggered for current episode
  const [transcriptReady, setTranscriptReady] = useState(false);
  const [transcriptPath, setTranscriptPath] = useState(null);
  const resetTranscriptState = useCallback(() => {
    setTranscriptReady(false);
    setTranscriptPath(null);
    transcriptReadyRef.current = false;
  }, []);
  const [showVoicePicker, setShowVoicePicker] = useState(false);
  const [voicePickerTargetId, setVoicePickerTargetId] = useState(null);
  const [voiceNameById, setVoiceNameById] = useState({});
  const [voicesLoading, setVoicesLoading] = useState(false);
  const fileInputRef = useRef(null);
  const coverArtInputRef = useRef(null);
  const coverCropperRef = useRef(null);
  const [coverNeedsUpload, setCoverNeedsUpload] = useState(false);
  const [coverMode, setCoverMode] = useState('crop');
  const [isUploadingCover, setIsUploadingCover] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(null);
  const [uploadStats, setUploadStats] = useState(null); // Track upload speed, ETA, bytes
  const [audioDurationSec, setAudioDurationSec] = useState(null);

  useEffect(() => {
    setInternPrefetch({ status: 'idle', filename: null, contexts: [], log: null, error: null });
  }, [uploadedFilename, selectedPreupload]);

  const internDetectionCount = Number((intentDetections?.intern?.count) ?? 0);

  // Consider a build "active" when something non-trivial is in-flight or staged
  const buildActive = useMemo(() => {
    // After step 6 (assemble/publish phase reached) we no longer consider the pre-build cancel action valid
    if (currentStep >= 6) return false;
    const hasAudio = !!(uploadedFile || uploadedFilename);
    const hasCover = !!(episodeDetails?.coverArt || episodeDetails?.cover_image_path);
    // Active only if user still editing or staging prior to / during assembly start
    return !!(isUploading || isAssembling || isPublishing || autoPublishPending || hasAudio || hasCover);
  }, [
    currentStep,
    isUploading,
    isAssembling,
    isPublishing,
    autoPublishPending,
    uploadedFile,
    uploadedFilename,
    episodeDetails,
  ]);

  useEffect(() => {
    let used = false;
    try {
      if (preselectedMainFilename && !uploadedFilename) {
        setUploadedFilename(preselectedMainFilename);
        setIntentDetections({ flubber: null, intern: null, sfx: null });
        setIntentDetectionReady(false);
        const targetStep = typeof preselectedStartStep === 'number' ? preselectedStartStep : 5;
        setCurrentStep(targetStep);
        if (preselectedTranscriptReady === true) {
          setTranscriptReady(true);
          transcriptReadyRef.current = true;
          setTranscriptPath(null);
        }
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
        if (handedFilename) {
          setUploadedFilename(handedFilename);
          setIntentDetections({ flubber: null, intern: null, sfx: null });
          setIntentDetectionReady(false);
        }
        else if (handedHint) {
          setUploadedFilename(handedHint);
          setIntentDetections({ flubber: null, intern: null, sfx: null });
          setIntentDetectionReady(false);
        }
      }
      if (startStep === '5') setCurrentStep(5);
      if (wasReady === '1') {
        setTranscriptReady(true);
        transcriptReadyRef.current = true;
        setTranscriptPath(null);
      }
    } catch {}
    try {
      localStorage.removeItem('ppp_start_step');
      localStorage.removeItem('ppp_transcript_ready');
    } catch {}
  }, [preselectedMainFilename, preselectedTranscriptReady, uploadedFilename]);

  useEffect(() => {
    if (!testInject) return;
    try {
      if (testInject.selectedTemplate) setSelectedTemplate(testInject.selectedTemplate);
      if (testInject.uploadedFilename) setUploadedFilename(testInject.uploadedFilename);
      if (typeof testInject.transcriptReady === 'boolean') {
        const ready = !!testInject.transcriptReady;
        setTranscriptReady(ready);
        setTranscriptPath(ready ? (testInject.transcriptPath || null) : null);
      }
      if (testInject.episodeDetails) setEpisodeDetails(prev => ({ ...prev, ...testInject.episodeDetails }));
    } catch {}
  }, [testInject]);

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
    const tplId = selectedTemplate?.id || null;
    if (!tplId) {
      autoRecurringRef.current = { templateId: null, date: null, time: null, manual: false };
      return;
    }
    if (autoRecurringRef.current.templateId !== tplId) {
      autoRecurringRef.current = { templateId: tplId, date: null, time: null, manual: false };
    }
  }, [selectedTemplate?.id]);

  const refreshUsage = useCallback(async () => {
    try {
      const api = makeApi(token);
      const u = await api.get('/api/billing/usage');
      if (u) setUsage(u);
      return u;
    } catch (_) {
      return null;
    }
  }, [token]);

  useEffect(() => {
    const api = makeApi(token);
    const fetchMedia = async () => {
      try {
        const data = await api.get('/api/media/');
        setMediaLibrary(coerceArray(data));
      } catch (err) {
        setError(err.message);
      }
    };
    const fetchSpreakerShows = async () => {};
    fetchMedia();
    fetchSpreakerShows();
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
    refreshUsage();
    (async () => {
      try {
        const caps = await api.get('/api/users/me/capabilities');
        if(caps){ setCapabilities({
          has_elevenlabs: !!caps.has_elevenlabs,
          has_google_tts: !!caps.has_google_tts,
          has_any_sfx_triggers: !!caps.has_any_sfx_triggers,
        }); }
      } catch(_) {}
    })();
  }, [token, authUser, refreshUsage]);

  useEffect(() => {
    if (!token || !selectedTemplate?.id || !uploadedFilename) {
      setMinutesPrecheck(null);
      setMinutesPrecheckError(null);
      setMinutesPrecheckPending(false);
      return;
    }

    let cancelled = false;
    setMinutesPrecheckPending(true);
    setMinutesPrecheckError(null);

    const api = makeApi(token);
    (async () => {
      try {
        const payload = {
          template_id: selectedTemplate.id,
          main_content_filename: uploadedFilename,
        };
        const res = await api.post('/api/episodes/precheck/minutes', payload);
        if (cancelled) return;
        setMinutesPrecheck(res || null);
        setMinutesPrecheckError(null);
      } catch (err) {
        if (cancelled) return;
        if (err && err.status === 402 && err.detail) {
          const detail = err.detail;
          const fallback = {
            allowed: false,
            detail,
            minutes_required: Number(detail.minutes_required) || null,
            minutes_remaining: Number(detail.minutes_remaining),
          };
          setMinutesPrecheck(fallback);
          setMinutesPrecheckError(null);
        } else {
          setMinutesPrecheck(null);
          setMinutesPrecheckError(err?.message || 'Unable to check minutes.');
        }
      } finally {
        if (!cancelled) setMinutesPrecheckPending(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [token, selectedTemplate?.id, uploadedFilename]);

  useEffect(() => {
    const tplId = selectedTemplate?.id;
    if (!tplId || !token) {
      return;
    }
    const state = autoRecurringRef.current;
    if (state.manual && state.templateId === tplId) {
      return;
    }
    if (state.templateId === tplId && state.date && state.time && !state.manual) {
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const apiClient = makeApi(token);
        const info = await apiClient.get(`/api/recurring/templates/${tplId}/next`);
        if (cancelled) return;
        const nextDate = info?.next_publish_date;
        const nextTime = info?.next_publish_time;
        if (nextDate && nextTime) {
          setScheduleDate(nextDate);
          setScheduleTime(nextTime);
          setPublishMode((prev) => (prev === 'now' ? prev : 'schedule'));
          autoRecurringRef.current = {
            templateId: tplId,
            date: nextDate,
            time: nextTime,
            manual: false,
          };
        } else {
          autoRecurringRef.current = {
            templateId: tplId,
            date: null,
            time: null,
            manual: false,
          };
        }
      } catch (err) {
        console.warn('Failed to fetch template recurring slot', err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedTemplate?.id, token]);

  useEffect(() => {
    const state = autoRecurringRef.current;
    if (!state.templateId || state.manual) return;
    if (!state.date || !state.time) return;
    if (scheduleDate !== state.date || scheduleTime !== state.time) {
      state.manual = true;
    }
  }, [scheduleDate, scheduleTime]);

  // Intern should always be available (can generate show notes even without TTS)
  // TTS generation will be conditional on has_elevenlabs || has_google_tts
  const requireIntern = true; // Always enable intern detection and show notes
  const canGenerateInternAudio = capabilities.has_elevenlabs || capabilities.has_google_tts;
  const requireSfx = capabilities.has_any_sfx_triggers;

  const intentVisibility = {
    flubber: true,
    intern: requireIntern,
    sfx: requireSfx,
  };

  const resolveInternVoiceId = useCallback(() => {
    if (ttsValues?.intern_voice_id) return ttsValues.intern_voice_id;
    const segments = Array.isArray(selectedTemplate?.segments) ? selectedTemplate.segments : [];
    for (const seg of segments) {
      const segType = String(seg?.segment_type || seg?.slug || seg?.name || '').toLowerCase();
      const action = String(seg?.source?.action || '').toLowerCase();
      if (segType.includes('intern') || action === 'intern' || action === 'ai_command') {
        if (seg?.source?.voice_id) return seg.source.voice_id;
      }
    }
    if (selectedTemplate?.automation_settings?.intern_voice_id) return selectedTemplate.automation_settings.intern_voice_id;
    if (selectedTemplate?.ai_settings?.intern_voice_id) return selectedTemplate.ai_settings.intern_voice_id;
    if (selectedTemplate?.default_intern_voice_id) return selectedTemplate.default_intern_voice_id;
    if (selectedTemplate?.default_elevenlabs_voice_id) return selectedTemplate.default_elevenlabs_voice_id;
    return null;
  }, [
    ttsValues?.intern_voice_id,
    selectedTemplate?.segments,
    selectedTemplate?.automation_settings,
    selectedTemplate?.ai_settings,
    selectedTemplate?.default_intern_voice_id,
    selectedTemplate?.default_elevenlabs_voice_id,
  ]);

  useEffect(() => {
    const voice = resolveInternVoiceId();
    if (!voice) return;
    setTtsValues((prev) => {
      if (prev && prev.intern_voice_id) return prev;
      return { ...prev, intern_voice_id: voice };
    });
  }, [resolveInternVoiceId]);

  const normalizeIntentValue = (value) => {
    if (value === 'yes' || value === 'no' || value === 'unknown') return value;
    return null;
  };

  const handleIntentAnswerChange = (key, value) => {
    if (!['flubber', 'intern', 'sfx'].includes(key)) return;
    setIntents((prev) => {
      const next = normalizeIntentValue(value);
      return { ...prev, [key]: next === null ? prev?.[key] ?? null : next };
    });
  };

  const pendingIntentLabels = [];
  if (intents.flubber === null) pendingIntentLabels.push('Flubber');
  if (requireIntern && intents.intern === null) pendingIntentLabels.push('Intern');
  if (requireSfx && intents.sfx === null) pendingIntentLabels.push('Sound Effects');

  const intentsComplete = pendingIntentLabels.length === 0;

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

  useEffect(() => {
    if (currentStep !== 3) return;
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
    let haveAll = true;
    for (const id of ids) { if (!voiceNameById[id]) { haveAll = false; break; } }
    if (haveAll) return;
    let cancelled = false;
    (async () => {
      try {
        setVoicesLoading(true);
        const res = await fetchElevenVoices('', 1, 200);
        const map = {};
        for (const v of (res?.items || [])) {
          const dn = v.common_name || v.name || '';
          if (dn) map[v.voice_id] = dn;
        }
        if (!cancelled) setVoiceNameById(prev => ({ ...prev, ...map }));
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
            } catch (_) {}
          }
        }
      } catch {
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
      const storedSchedule = localStorage.getItem('ppp_schedule_datetime');
      let base;
      if(storedSchedule){
        const d = new Date(storedSchedule);
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
    } catch {}
  }, []);

  useEffect(() => {
    try {
      if (selectedTemplate?.ai_settings?.auto_generate_tags === false) {
        const storedTags = localStorage.getItem('ppp_last_tags');
        if (storedTags && !episodeDetails.tags) {
          setEpisodeDetails(prev => ({ ...prev, tags: storedTags }));
        }
      }
    } catch {}
  }, [selectedTemplate]);

  useEffect(() => {
    if (!hadStoredPublishRef.current) {
      setPublishMode(testMode ? 'draft' : 'now');
    }
  }, [testMode]);

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
        localStorage.removeItem('ppp_last_tags');
      }
    } catch {}
  }, [episodeDetails.tags, selectedTemplate]);

  useEffect(() => {
    if (currentStep !== 5 || !selectedTemplate || !transcriptReady) return;
    const key = `${uploadedFilename || ''}|${expectedEpisodeId || ''}|${selectedTemplate?.id || ''}`;
    if (autoFillKeyRef.current === key) return;

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
        const seen = new Set(); const merged = [];
        for (const t of [...pinned, ...ai]) {
          const s = String(t).trim(); if (!s) continue;
          const k = s.toLowerCase();
          if (!seen.has(k)) { seen.add(k); merged.push(s); }
          if (merged.length >= 20) break;
        }
        merged.sort((a,b)=>a.localeCompare(b));
        handleDetailsChange('tags', merged.join(', '));
      }

      autoFillKeyRef.current = key;
    })();
  }, [currentStep, selectedTemplate?.id, transcriptReady, uploadedFilename, expectedEpisodeId, transcriptPath]);

  useEffect(() => { transcriptReadyRef.current = transcriptReady; }, [transcriptReady]);

  useEffect(() => {
    aiCacheRef.current = { title: null, notes: null, tags: null };
    autoFillKeyRef.current = '';
    if (currentStep === 5) resetTranscriptState();
  }, [uploadedFilename, expectedEpisodeId, selectedTemplate?.id, currentStep, resetTranscriptState]);

  useEffect(() => {
    if (currentStep !== 5) return;
    if (!uploadedFilename && !expectedEpisodeId) return;
    if (transcriptReady) return;

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
        if (Object.prototype.hasOwnProperty.call(r || {}, 'transcript_path')) {
          setTranscriptPath(r?.transcript_path || null);
        }
        if (r?.ready) {
          setTranscriptReady(true);
          return;
        }
      } catch (_) {}
      if (!stopped) setTimeout(tick, 5000);
    };
    const initial = setTimeout(tick, 250);
    return () => { stopped = true; clearTimeout(initial); };
  }, [currentStep, uploadedFilename, expectedEpisodeId, token, transcriptReady]);

  useEffect(() => {
    if (!transcriptReady) return;
    if (!uploadedFilename && !expectedEpisodeId) return;
    let canceled = false;
    const api = makeApi(token);
    setIntentDetectionReady(false);
    setIntentDetections({ flubber: null, intern: null, sfx: null });
    const params = [];
    if (expectedEpisodeId) params.push(`episode_id=${encodeURIComponent(expectedEpisodeId)}`);
    if (uploadedFilename) params.push(`hint=${encodeURIComponent(uploadedFilename)}`);
    const url = `/api/ai/intent-hints${params.length ? `?${params.join('&')}` : ''}`;

    const fetchHints = async (attempt = 0) => {
      try {
        const res = await api.get(url);
        if (canceled) return;
        const hints = (res && res.intents) ? res.intents : {};
        setIntentDetections(hints);
        const flubberCount = Number((hints?.flubber?.count) ?? 0);
        const internCount = Number((hints?.intern?.count) ?? 0);
        const sfxCount = Number((hints?.sfx?.count) ?? 0);
        setIntents(prev => {
          const next = { ...prev };
          let changed = false;
          if (prev.flubber === null && flubberCount === 0) { next.flubber = 'no'; changed = true; }
          if (prev.intern === null && internCount === 0) { next.intern = 'no'; changed = true; }
          if (prev.sfx === null && sfxCount === 0) { next.sfx = 'no'; changed = true; }
          return changed ? next : prev;
        });
        setIntentDetectionReady(true);
      } catch (err) {
        if (canceled) return;
        const status = err && typeof err === 'object' ? err.status : null;
        if (status && [404, 409, 425].includes(status) && attempt < 5) {
          setTimeout(() => { if (!canceled) fetchHints(attempt + 1); }, 750);
          return;
        }
        setIntentDetections(null);
        setIntentDetectionReady(true);
      }
    };

    fetchHints();

    return () => { canceled = true; };
  }, [transcriptReady, uploadedFilename, expectedEpisodeId, token]);

  useEffect(() => {
    if (!requireIntern) return;
    if (!transcriptReady) return;
    if (!intentDetectionReady) return;
    const sourceFilename = uploadedFilename || selectedPreupload;
    if (!sourceFilename) return;
    if (internDetectionCount <= 0) return;

    let shouldFetch = false;
    setInternPrefetch((prev) => {
      if (prev && prev.filename === sourceFilename) {
        if (prev.status === 'ready' || prev.status === 'loading') {
          return prev;
        }
      }
      shouldFetch = true;
      return { status: 'loading', filename: sourceFilename, contexts: [], log: null, error: null };
    });
    if (!shouldFetch) return;

    let canceled = false;
    const api = makeApi(token);
    const payload = { filename: sourceFilename };
    try {
      const voiceId = resolveInternVoiceId();
      if (voiceId) payload.voice_id = voiceId;
    } catch (_) {}

    (async () => {
      try {
        const data = await api.post('/api/intern/prepare-by-file', payload);
        if (canceled) return;
        const contexts = Array.isArray(data?.contexts) ? data.contexts : [];
        setInternPrefetch({
          status: 'ready',
          filename: sourceFilename,
          contexts,
          log: data?.log || null,
          error: null,
        });
      } catch (error) {
        if (canceled) return;
        setInternPrefetch((prev) => {
          if (prev && prev.filename === sourceFilename) {
            return { status: 'error', filename: sourceFilename, contexts: [], log: null, error };
          }
          return prev;
        });
      }
    })();

    return () => {
      canceled = true;
    };
  }, [
    requireIntern,
    transcriptReady,
    intentDetectionReady,
    internDetectionCount,
    uploadedFilename,
    selectedPreupload,
    token,
    resolveInternVoiceId,
  ]);

  useEffect(() => {
    if (selectedTemplate) return;
    if (!Array.isArray(templates)) return;
    const activeTemplates = templates.filter(t => t?.is_active !== false);
    if (activeTemplates.length === 1) {
      setSelectedTemplate(activeTemplates[0]);
      if (currentStep === 1) setCurrentStep(2);
    }
  }, [templates, selectedTemplate, currentStep]);

  const prefillNumbering = useCallback(async () => {
    try {
      const api = makeApi(token);
      const qs = [];
      if (selectedTemplate && selectedTemplate.podcast_id) {
        qs.push(`podcast_id=${encodeURIComponent(selectedTemplate.podcast_id)}`);
      }
      const url = `/api/episodes/last/numbering${qs.length ? `?${qs.join('&')}` : ''}`;
      const data = await api.get(url);
      if (data) {
        setEpisodeDetails(prev => {
          // Only prefill if user hasn’t changed these yet
          if (prev.episodeNumber && String(prev.episodeNumber).trim()) return prev;
          if (prev.season && String(prev.season).trim() !== '1') return prev;
          const season = (data.season_number != null) ? String(data.season_number) : '1';
          const nextEp = (data.episode_number != null) ? String(Number(data.episode_number) + 1) : '1';
          return { ...prev, season, episodeNumber: nextEp };
        });
      } else {
        setEpisodeDetails(prev => {
          if (prev.episodeNumber && String(prev.episodeNumber).trim()) return prev;
          if (prev.season && String(prev.season).trim() !== '1') return prev;
          return { ...prev, season: '1', episodeNumber: '1' };
        });
      }
    } catch(_) {}
  }, [token, selectedTemplate?.podcast_id]);

  useEffect(() => { prefillNumbering(); }, [prefillNumbering]);
  // Also attempt prefill when entering Step 5 if needed
  useEffect(() => {
    if (currentStep === 5) prefillNumbering();
  }, [currentStep, prefillNumbering]);

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
              setIsAssembling(true);
              setTimeout(()=>{ setJobId(j=>j); }, 750);
              return;
            }
            setAssemblyComplete(true);
            setAssembledEpisode(data.episode);
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
    }, 5000);

    return () => clearInterval(interval);
  }, [jobId, token, expectedEpisodeId]);

  const steps = useMemo(() => {
    const stepTwoTitle = creatorMode === 'preuploaded' ? 'Choose Audio' : 'Upload Audio';
    const stepTwoIcon = creatorMode === 'preuploaded' ? 'Library' : 'FileUp';
    return [
      { number: 1, title: 'Select Template', icon: 'BookText' },
      { number: 2, title: stepTwoTitle, icon: stepTwoIcon },
      { number: 3, title: 'Customize Segments', icon: 'Wand2' },
      { number: 4, title: 'Cover Art', icon: 'FileImage' },
      { number: 5, title: 'Details & Schedule', icon: 'Settings' },
      { number: 6, title: 'Assemble', icon: 'Globe' },
    ];
  }, [creatorMode]);

  const progressPercentage = ((currentStep - 1) / (steps.length - 1)) * 100;

  const handleTemplateSelect = async (template) => {
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
      const segments = Array.isArray(merged.segments) ? [...merged.segments] : [];
      const templateDefaultVoiceId = segments.find(s => s?.source?.source_type === 'tts' && s?.source?.voice_id)?.source?.voice_id || null;
      const seeded = segments.map(s => {
        if (s?.source?.source_type === 'tts') {
          return { ...s, source: { ...s.source, voice_id: s.source.voice_id || templateDefaultVoiceId || s.source.voice_id } };
        }
        return s;
      });
      setSelectedTemplate({ ...merged, segments: seeded });
    } catch {
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
    setCurrentStep(2);
  };

  const handleFileChange = async (file) => {
    if (!file) return;
    const MB = 1024 * 1024;
    if (!(file.type || '').toLowerCase().startsWith('audio/')) {
      setError('Please select an audio file.');
      return;
    }
    // Fetch dynamic limit from public config (cached per session)
    let maxMb = 500;
    try {
      const res = await fetch('/api/public/config');
      const cfg = await res.json().catch(()=>({}));
      const n = parseInt(String(cfg?.max_upload_mb || '500'), 10);
      if (isFinite(n) && !isNaN(n)) maxMb = Math.min(Math.max(n, 10), 2048);
    } catch {}
    if (file.size > maxMb * MB) {
      setError(`Audio exceeds ${maxMb}MB limit.`);
      return;
    }
    setUploadedFile(file);
    setIntents({ flubber: null, intern: null, sfx: null, intern_overrides: [] });
    setInternResponses([]);
    setInternPendingContexts(null);
    setInternReviewContexts([]);
    setShowInternReview(false);
    setIntentDetections({ flubber: null, intern: null, sfx: null });
    setIntentDetectionReady(false);
    setShowIntentQuestions(false);
    intentsPromptedRef.current = false; // new file -> prompt again in Step 2
    setIsUploading(true);
    setUploadProgress(0);
    setUploadStats(null);
    setStatusMessage('Uploading audio file...');
    setError('');

    try {
      const entries = await uploadMediaDirect({
        category: 'main_content',
        file,
        friendlyName: file.name,
        token,
        onProgress: ({ percent, loaded, total, bytesPerSecond, etaSeconds }) => {
          if (typeof percent === 'number') setUploadProgress(percent);
          setUploadStats({ loaded, total, bytesPerSecond, etaSeconds });
        },
        onXhrCreate: (xhr) => {
          uploadXhrRef.current = xhr;
        },
      });
      const fname = entries[0]?.filename;
      setUploadedFilename(fname);
      try {
        if (fname) localStorage.setItem('ppp_uploaded_filename', fname);
      } catch {}
      setStatusMessage('Upload successful!');
      setUploadProgress(100);
    } catch (err) {
      setError(err.message);
      setStatusMessage('');
      setUploadedFile(null);
      try {
        localStorage.removeItem('ppp_uploaded_filename');
      } catch {}
      setUploadProgress(null);
      setUploadStats(null);
    } finally {
      uploadXhrRef.current = null;
      setIsUploading(false);
      setTimeout(() => {
        setUploadProgress(null);
        setUploadStats(null);
      }, 400);
    }
  };

  const handlePreuploadedSelect = useCallback((item) => {
    if (!item) {
      setSelectedPreupload(null);
      setUploadedFilename(null);
      resetTranscriptState();
      setInternResponses([]);
      setInternPendingContexts(null);
      setInternReviewContexts([]);
      setShowInternReview(false);
      setIntentDetections({ flubber: null, intern: null, sfx: null });
      setIntentDetectionReady(false);
      setIntents({ flubber: null, intern: null, sfx: null, intern_overrides: [] });
      return;
    }

    const filename = item.filename || null;
    setSelectedPreupload(filename);
    setUploadedFile(null);
    setInternResponses([]);
    setInternPendingContexts(null);
    setInternReviewContexts([]);
    setShowInternReview(false);
    if (filename) {
      setUploadedFilename(filename);
      try { localStorage.setItem('ppp_uploaded_filename', filename); } catch {}
    }
    const ready = !!item.transcript_ready;
    setTranscriptReady(ready);
    transcriptReadyRef.current = ready;
    setTranscriptPath(ready ? item.transcript_path || null : null);
    const intentsData = item.intents || {};
    setIntentDetections(intentsData);
    setIntentDetectionReady(true);
    setIntents(prev => {
      const next = { ...prev };
      const flubberCount = Number((intentsData?.flubber?.count) ?? 0);
      const internCount = Number((intentsData?.intern?.count) ?? 0);
      const sfxCount = Number((intentsData?.sfx?.count) ?? 0);
      if (flubberCount === 0) next.flubber = 'no';
      else if (next.flubber === null) next.flubber = 'yes';
      if (internCount === 0) next.intern = 'no';
      else if (next.intern === null) next.intern = 'yes';
      if (sfxCount === 0) next.sfx = 'no';
      else if (next.sfx === null) next.sfx = 'yes';
      return next;
    });
  }, [resetTranscriptState]);

  const cancelBuild = () => {
    // Abort in-flight audio upload, if any
    try {
      if (uploadXhrRef.current && typeof uploadXhrRef.current.abort === 'function') {
        uploadXhrRef.current.abort();
      }
    } catch {}
    try {
      localStorage.removeItem('ppp_uploaded_filename');
      localStorage.removeItem('ppp_uploaded_hint');
      localStorage.removeItem('ppp_start_step');
      localStorage.removeItem('ppp_transcript_ready');
    } catch {}
    setUploadedFile(null);
    setUploadedFilename(null);
    setUploadProgress(null);
    resetTranscriptState();
    setIntents({ flubber: null, intern: null, sfx: null, intern_overrides: [] });
    setIntentDetections({ flubber: null, intern: null, sfx: null });
    setIntentDetectionReady(true);
    setInternResponses([]);
    setInternPendingContexts(null);
    setInternReviewContexts([]);
    setShowInternReview(false);
    setShowIntentQuestions(false);
    setStatusMessage('');
    setError('');
    setCurrentStep(1);
    // Navigate back to dashboard/home
    try {
      window.dispatchEvent(new Event('ppp:navigate-dashboard'));
      // If no router listener, hard redirect as a fallback
      if (typeof window !== 'undefined') {
        const base = window.location.origin || '';
        const dash = base ? `${base}/` : '/';
        // Use hash route if app uses hash routing
        if (window.location.hash && !window.location.pathname.includes('/dashboard')) {
          window.location.href = base + '/';
        } else {
          window.location.href = dash;
        }
      }
    } catch {}
  };

  const uploadCover = async (file) => {
    const MB = 1024 * 1024;
    const ct = (file?.type || '').toLowerCase();
    if (!ct.startsWith('image/')) throw new Error('Cover must be an image file.');
    if (file.size > 15 * MB) throw new Error('Cover image exceeds 15MB limit.');
    const fd = new FormData();
    fd.append('files', file);
    fd.append('friendly_names', JSON.stringify([file.name]));
    const api = makeApi(token);
    // Add a timeout so the request doesn't hang forever and block the wizard.
    // Give uploads plenty of time to complete – 8s was too aggressive when
    // users pick multi-megabyte images on slower connections.
    const controller = new AbortController();
    const uploadTimeoutMs = (() => {
      const MB = 1024 * 1024;
      if (!file?.size) return 45000; // sensible default when size unknown
      const approx = 15000 + Math.ceil(file.size / MB) * 4000; // base + 4s/MB
      return Math.min(Math.max(approx, 20000), 90000); // clamp 20s-90s
    })();
    const t = setTimeout(() => controller.abort(), uploadTimeoutMs);
    let data;
    try {
      data = await api.raw('/api/media/upload/episode_cover', { method: 'POST', body: fd, signal: controller.signal });
    } catch (e) {
      // Fallback: try the simpler single-file cover_art endpoint
      try {
        const fd2 = new FormData();
        fd2.append('file', file);
        const controller2 = new AbortController();
        const t2 = setTimeout(() => controller2.abort(), uploadTimeoutMs);
        let alt;
        try {
          alt = await api.raw('/api/media/upload/cover_art', { method: 'POST', body: fd2, signal: controller2.signal });
        } finally {
          clearTimeout(t2);
        }
        // Normalize shape to list
        data = [{ filename: alt?.filename || alt?.path || alt?.stored_as }];
      } catch (e2) {
        if (e && e.name === 'AbortError') {
          throw new Error('Cover upload timed out. Please check your connection and try again.');
        }
        throw e2;
      }
    } finally {
      clearTimeout(t);
    }
    const uploaded = data?.[0]?.filename;
    if (!uploaded) throw new Error('Cover upload: no filename returned.');
    setEpisodeDetails(prev => ({ ...prev, cover_image_path: uploaded }));
    return uploaded;
  };

  const handleCoverFileSelected = (file) => {
    if(!file) return;
    setEpisodeDetails(prev => ({ ...prev, coverArt: file, coverArtPreview: null, cover_image_path: null }));
    setCoverNeedsUpload(true);
  };

  const handleUploadProcessedCover = async () => {
    if(!episodeDetails.coverArt || !coverCropperRef.current) return;
    try {
      setIsUploadingCover(true);
      const blob = await coverCropperRef.current.getProcessedBlob();
      if(!blob){ throw new Error('Could not process image.'); }
  const processedFile = new File([blob], (episodeDetails.coverArt.name.replace(/\.[^.]+$/, '') + '-square.jpg'), { type: 'image/jpeg' });
      await uploadCover(processedFile);
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
    setTtsValues(prev => ({ ...prev, [promptId]: value }));
  };

  const handleDetailsChange = (field, value) => {
    setEpisodeDetails(prev => ({ ...prev, [field]: value }));
  };

  const suggestTitle = async (opts = {}) => {
    const force = !!opts.force;
    if (!force && aiCacheRef.current.title) return aiCacheRef.current.title;
    const api = makeApi(token);
    const payload = {
      episode_id: expectedEpisodeId || crypto.randomUUID(),
      podcast_id: selectedTemplate?.podcast_id,
      transcript_path: transcriptPath || null,
      hint: uploadedFilename || null,
      base_prompt: '',
      extra_instructions: selectedTemplate?.ai_settings?.title_instructions || '',
    };
    let title = '';
    try {
      const res = await api.post('/api/ai/title', payload);
      title = res?.title || '';
    } catch(e) {
      if (e && e.status === 409) {
        resetTranscriptState();
        try { toast({ title: 'Transcript not ready', description: 'Transcript not ready yet — still processing', variant: 'default' }); } catch {}
        return '';
      }
      try {
        if (e && e.status === 429) {
          toast({ variant: 'destructive', title: 'AI Title error', description: 'Too many requests — please slow down and try again.' });
        } else {
          const code = e && e.status ? ` (${e.status})` : '';
          toast({ variant: 'destructive', title: 'AI Title error', description: `Request failed${code}. Please try again.` });
        }
      } catch {}
      return '';
    }
    aiCacheRef.current.title = title;
    return title;
  };

  const suggestNotes = async (opts = {}) => {
    const force = !!opts.force;
    if (!force && aiCacheRef.current.notes) return aiCacheRef.current.notes;
    const api = makeApi(token);
    const payload = {
      episode_id: expectedEpisodeId || crypto.randomUUID(),
      podcast_id: selectedTemplate?.podcast_id,
      transcript_path: transcriptPath || null,
      hint: uploadedFilename || null,
      base_prompt: '',
      extra_instructions: selectedTemplate?.ai_settings?.notes_instructions || '',
    };
    let desc = '';
    try {
      const res = await api.post('/api/ai/notes', payload);
      desc = res?.description || '';
    } catch(e) {
      if (e && e.status === 409) {
        resetTranscriptState();
        try { toast({ title: 'Transcript not ready', description: 'Transcript not ready yet — still processing', variant: 'default' }); } catch {}
        return '';
      }
      try {
        if (e && e.status === 429) {
          toast({ variant: 'destructive', title: 'AI Description error', description: 'Too many requests — please slow down and try again.' });
        } else {
          const code = e && e.status ? ` (${e.status})` : '';
          toast({ variant: 'destructive', title: 'AI Description error', description: `Request failed${code}. Please try again.` });
        }
      } catch {}
      return '';
    }
    aiCacheRef.current.notes = desc;
    return desc;
  };

  const suggestTags = async () => {
    if (aiCacheRef.current.tags) return aiCacheRef.current.tags;
    const api = makeApi(token);
    const payload = {
      episode_id: expectedEpisodeId || crypto.randomUUID(),
      podcast_id: selectedTemplate?.podcast_id,
      transcript_path: transcriptPath || null,
      hint: uploadedFilename || null,
      tags_always_include: selectedTemplate?.ai_settings?.tags_always_include || [],
    };
    try {
      const res = await api.post('/api/ai/tags', payload);
      const tags = Array.isArray(res?.tags) ? res.tags : [];
      aiCacheRef.current.tags = tags;
      return tags;
    } catch (e) {
      if (e && e.status === 409) {
        resetTranscriptState();
        try { toast({ title: 'Transcript not ready', description: 'Transcript not ready yet — still processing', variant: 'default' }); } catch {}
        return [];
      }
      try {
        if (e && e.status === 429) {
          toast({ variant: 'destructive', title: 'AI Tags error', description: 'Too many requests — please slow down and try again.' });
        } else {
          const code = e && e.status ? ` (${e.status})` : '';
          toast({ variant: 'destructive', title: 'AI Tags error', description: `Request failed${code}. Please try again.` });
        }
      } catch {}
      return [];
    }
  };

  const handleAISuggestTitle = async () => {
    if (isAiTitleBusy) return;
    setIsAiTitleBusy(true);
    try {
      const title = await suggestTitle({ force: true });
      if (title && !/[a-f0-9]{16,}/i.test(title)) {
        handleDetailsChange('title', title);
      }
    } finally { setIsAiTitleBusy(false); }
  };

  const handleAISuggestDescription = async () => {
    if (isAiDescBusy) return;
    setIsAiDescBusy(true);
    try {
      const notes = await suggestNotes({ force: true });
      const cleaned = (notes || '')
        .replace(/^(?:\*\*?)?description:?\*?\*?\s*/i, '')
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

  const handleUploadProcessedCoverAndPreview = async () => {
    await handleUploadProcessedCover();
  };

  const handleAssemble = async () => {
    if (minutesPrecheckPending) {
      setError('Checking processing minutes… please wait.');
      return;
    }
    if (minutesPrecheck && minutesPrecheck.allowed === false) {
      const detail = minutesPrecheck.detail || {};
      const required = minutesRequiredPrecheck ?? (Number(detail.minutes_required) || null);
      const remaining = (() => {
        const candidate = detail.minutes_remaining ?? minutesRemainingPrecheck;
        const num = Number(candidate);
        return Number.isFinite(num) ? num : null;
      })();
      const renewal = detail.renewal_date || detail.renewalDate || null;
      const durationSeconds = (() => {
        const total = Number(minutesPrecheck.total_seconds);
        if (Number.isFinite(total) && total > 0) return total;
        const main = Number(minutesPrecheck.main_seconds);
        if (Number.isFinite(main) && main > 0) return main;
        return audioDurationSec && audioDurationSec > 0 ? audioDurationSec : null;
      })();
      setMinutesDialog({
        requiredMinutes: required,
        remainingMinutes: remaining,
        renewalDate: renewal,
        message: detail.message || 'Not enough processing minutes remain to assemble this episode.',
        durationSeconds: durationSeconds || null,
      });
      setStatusMessage('');
      setError('');
      return;
    }
    if (quotaExceeded) { setError('Monthly episode quota reached. Upgrade your plan to continue.'); window.dispatchEvent(new Event('ppp:navigate-billing')); return; }
    if (!uploadedFilename || !selectedTemplate || !episodeDetails.title) { setError('A template, title, and audio file are required.'); return; }
    if(!episodeDetails.season || !String(episodeDetails.season).trim()) {
      setEpisodeDetails(prev=>({ ...prev, season: '1' }));
    }
    if(publishMode === 'schedule'){
      if(!scheduleDate || !scheduleTime){ setError('Pick date & time for scheduling'); return; }
      const dt = new Date(`${scheduleDate}T${scheduleTime}:00`);
      if(isNaN(dt.getTime()) || dt.getTime() < Date.now()+10*60000){ setError('Scheduled time must be at least 10 minutes in the future.'); return; }
    }
    if(episodeDetails.coverArt && !episodeDetails.cover_image_path){
      try {
        setStatusMessage('Processing cover before assembly...');
        await handleUploadProcessedCoverAndPreview();
      } catch(err){
        setError('Cover processing failed; you can retry or remove the cover.');
        return;
      }
    }
    setAssemblyComplete(false);
    setAssembledEpisode(null);
    setAutoPublishPending(false);
    setExpectedEpisodeId(null);
    publishingTriggeredRef.current = false; // Reset for new episode
    setIsAssembling(true);
    setStatusMessage('Assembling your episode...');
    setError('');
    setCurrentStep(6);
    try {
      const api = makeApi(token);
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
          flubber_cuts_ms: Array.isArray(flubberCutsMs) && flubberCutsMs.length ? flubberCutsMs : null,
          intents: intents,
        });
      } catch(e) {
        if (e && e.status === 402) {
          const detail = (e.detail && typeof e.detail === 'object') ? e.detail : {};
          if (detail.code === 'INSUFFICIENT_MINUTES') {
            const required = Number(detail.minutes_required) || 0;
            const remaining = Number(detail.minutes_remaining);
            const renewal = detail.renewal_date || detail.renewalDate || null;
            const secondsEstimate = (audioDurationSec && audioDurationSec > 0)
              ? audioDurationSec
              : (required > 0 ? required * 60 : null);
            setMinutesDialog({
              requiredMinutes: required,
              remainingMinutes: Number.isFinite(remaining) ? Math.max(0, remaining) : null,
              renewalDate: renewal,
              message: detail.message || e.message || 'Not enough processing minutes remain.',
              durationSeconds: secondsEstimate,
            });
            setStatusMessage('');
            setIsAssembling(false);
            setError('');
            try { await refreshUsage(); } catch {}
            return;
          }
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
      setAutoPublishPending(true);
      setStatusMessage(`Episode assembly has been queued. Job ID: ${result.job_id}`);
    } catch (err) {
      setError(err.message || (err?.detail?.message) || 'Assembly failed');
      setStatusMessage('');
      setIsAssembling(false);
    }
  };

  const queueInternReview = (contexts) => {
    if (!Array.isArray(contexts) || contexts.length === 0) return false;
    if (showFlubberReview) {
      setInternPendingContexts(contexts);
    } else {
      setInternPendingContexts(null);
      setInternReviewContexts(contexts);
      setShowInternReview(true);
    }
    return true;
  };

  const proceedAfterFlubber = () => {
    if (internPendingContexts && internPendingContexts.length) {
      setInternReviewContexts(internPendingContexts);
      setInternPendingContexts(null);
      setShowInternReview(true);
    } else {
      setCurrentStep(3);
    }
  };

  const handleFlubberConfirm = (cuts) => {
    setFlubberCutsMs(cuts || []);
    setShowFlubberReview(false);
    proceedAfterFlubber();
  };

  const handleFlubberCancel = () => {
    setFlubberCutsMs([]);
    setShowFlubberReview(false);
    proceedAfterFlubber();
  };

  const handleInternComplete = (results) => {
    const safe = Array.isArray(results) ? results : [];
    setInternResponses(safe);
    setIntents((prev) => ({ ...prev, intern_overrides: safe }));
    setShowInternReview(false);
    setInternReviewContexts([]);
    setInternPendingContexts(null);
    setCurrentStep(3);
  };

  const handleInternCancel = () => {
    setInternResponses([]);
    setIntents((prev) => ({ ...prev, intern_overrides: [] }));
    setShowInternReview(false);
    setInternReviewContexts([]);
    setInternPendingContexts(null);
    setCurrentStep(3);
  };

  const processInternCommand = useCallback(
    async ({ context, startSeconds, endSeconds, regenerate = false, overrideText = null }) => {
      const filename = uploadedFilename || selectedPreupload;
      if (!filename) throw new Error('No audio selected for intern processing.');
      if (typeof endSeconds !== 'number' || !isFinite(endSeconds)) {
        throw new Error('Select an end point for the intern command.');
      }
      const api = makeApi(token);
      const payload = {
        filename,
        end_s: endSeconds,
        voice_id: resolveInternVoiceId() || undefined,
      };
      const commandId = context?.command_id ?? context?.intern_index ?? context?.id ?? context?.index ?? (typeof context?.__index === 'number' ? context.__index : null);
      if (commandId != null) payload.command_id = commandId;
      const start = typeof startSeconds === 'number' && isFinite(startSeconds)
        ? startSeconds
        : (typeof context?.start_s === 'number' ? context.start_s : null);
      if (start != null) payload.start_s = start;
      if (overrideText != null) payload.override_text = overrideText;
      if (regenerate) payload.regenerate = true;
      const res = await api.post('/api/intern/execute', payload);
      return res || {};
    },
    [uploadedFilename, selectedPreupload, token, resolveInternVoiceId],
  );

  const handleIntentSubmit = async (answers = intents) => {
    const normalized = {
      flubber: normalizeIntentValue(answers?.flubber ?? intents.flubber) ?? 'no',
      intern: requireIntern ? (normalizeIntentValue(answers?.intern ?? intents.intern) ?? 'no') : 'no',
      sfx: requireSfx ? (normalizeIntentValue(answers?.sfx ?? intents.sfx) ?? 'no') : 'no',
    };

    setIntents((prev) => {
      const next = { ...prev, ...normalized };
      if (normalized.intern !== 'yes') {
        next.intern_overrides = [];
      }
      return next;
    });
    if (normalized.intern !== 'yes') {
      setInternResponses([]);
      setInternPendingContexts(null);
      setInternReviewContexts([]);
      setShowInternReview(false);
    }
    intentsPromptedRef.current = true;
    setShowIntentQuestions(false);

    let paused = false;

    const shouldScanFlubber = uploadedFilename && (normalized.flubber === 'yes' || normalized.flubber === 'unknown');
    if (shouldScanFlubber) {
      setStatusMessage('Scanning for retakes (flubber)...');
      setShowFlubberScan(true);
      const api = makeApi(token);
      const payload = { filename: uploadedFilename, intents: { flubber: normalized.flubber } };
      let contexts = [];
      try {
        for (let attempt = 0; attempt < 20; attempt++) {
          try {
            const data = await api.post('/api/flubber/prepare-by-file', payload);
            contexts = Array.isArray(data?.contexts) ? data.contexts : [];
            break;
          } catch (e) {
            if (e && e.status === 425) {
              await new Promise((r) => setTimeout(r, 1000));
              continue;
            }
            break;
          }
        }
      } catch (_) {
      } finally {
        setShowFlubberScan(false);
        setStatusMessage('');
      }

      if (contexts.length > 0) {
        setFlubberContexts(contexts);
        setShowFlubberReview(true);
        paused = true;
      } else if (normalized.flubber === 'yes') {
        setFlubberNotFound(true);
        paused = true;
      }
    }

    const shouldProcessIntern = normalized.intern === 'yes' && requireIntern && (uploadedFilename || selectedPreupload);
    if (shouldProcessIntern) {
      const sourceFilename = uploadedFilename || selectedPreupload;
      const prefetched =
        internPrefetch && internPrefetch.status === 'ready' && internPrefetch.filename === sourceFilename
          ? internPrefetch.contexts
          : null;
      const usePrefetched = Array.isArray(prefetched) && prefetched.length > 0;
      if (usePrefetched) {
        if (queueInternReview(prefetched)) {
          paused = true;
        }
      } else {
        try {
          setStatusMessage('Preparing intern commands...');
          const api = makeApi(token);
          const payload = { filename: sourceFilename };
          const voiceId = resolveInternVoiceId();
          if (voiceId) payload.voice_id = voiceId;
          const data = await api.post('/api/intern/prepare-by-file', payload);
          const contexts = Array.isArray(data?.contexts)
            ? data.contexts
            : Array.isArray(data?.commands)
              ? data.commands
              : [];
          if (queueInternReview(contexts)) {
            paused = true;
          }
        } catch (err) {
          const description = err?.detail?.message || err?.message || 'Unable to prepare intern commands right now.';
          toast({ variant: 'destructive', title: 'Intern review unavailable', description });
        } finally {
          setStatusMessage('');
        }
      }
    }

    if (!paused) {
      setCurrentStep(3);
      return true;
    }
    return false;
  };

  const handlePublish = async () => {
    if (!assembledEpisode) {
      setError('Assembled episode required.');
      return;
    }
    let showId = selectedSpreakerShow;
    if (!showId && selectedTemplate && selectedTemplate.podcast_id) {
      showId = selectedTemplate.podcast_id;
    }
    if (!showId) {
      setError('Template is not linked to a show (podcast). Update template to include its show.');
      toast({ variant: 'destructive', title: 'Missing show', description: 'Template needs a show association.' });
      return;
    }
    setIsPublishing(true);
    setStatusMessage('Publishing your episode...');
    setError('');
    const scheduleEnabled = publishMode === 'schedule';
    let publish_at = null;
    let publish_at_local = null;
    if (scheduleEnabled && scheduleDate && scheduleTime) {
      try {
        const local = new Date(`${scheduleDate}T${scheduleTime}:00`);
        if (!isNaN(local.getTime()) && local.getTime() > Date.now() + 60 * 1000) {
          publish_at = new Date(local.getTime()).toISOString();
          publish_at_local = `${scheduleDate} ${scheduleTime}`;
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
      toast({ variant: 'destructive', title: 'Error', description: friendly });
    } finally {
      setIsPublishing(false);
    }
  };

  const remainingEpisodes = usage?.episodes_remaining_this_month;
  const maxEpisodes = usage?.max_episodes_month;
  const nearQuota = typeof remainingEpisodes === 'number' && typeof maxEpisodes === 'number' && remainingEpisodes > 0 && remainingEpisodes <= Math.ceil(maxEpisodes * 0.1);
  const quotaExceeded = typeof remainingEpisodes === 'number' && remainingEpisodes <= 0;

  const minutesUsed = usage?.processing_minutes_used_this_month;
  const minutesCap = usage?.max_processing_minutes_month;
  const minutesRemaining = (typeof minutesCap === 'number' && typeof minutesUsed === 'number') ? (minutesCap - minutesUsed) : null;
  const minutesNearCap = (typeof minutesRemaining === 'number' && typeof minutesCap === 'number') && minutesRemaining > 0 && minutesRemaining <= Math.ceil(minutesCap * 0.1);
  const minutesExceeded = typeof minutesRemaining === 'number' && minutesRemaining <= 0;
  const minutesRemainingPrecheck = (() => {
    const candidate = minutesPrecheck?.minutes_remaining ?? minutesPrecheck?.detail?.minutes_remaining;
    const num = Number(candidate);
    if (Number.isFinite(num)) return num;
    return minutesRemaining;
  })();
  const minutesRequiredPrecheck = (() => {
    const candidate = minutesPrecheck?.minutes_required ?? minutesPrecheck?.detail?.minutes_required;
    const num = Number(candidate);
    return Number.isFinite(num) ? num : null;
  })();
  const minutesBlocking = Boolean(minutesPrecheck && minutesPrecheck.allowed === false);

  const missingTitle = !episodeDetails.title || !episodeDetails.title.trim();
  const missingEpisodeNumber = !episodeDetails.episodeNumber || !String(episodeDetails.episodeNumber).trim();
  const blockingQuota = quotaExceeded || minutesBlocking;
  const canProceedToStep5 = !missingTitle && !missingEpisodeNumber && !blockingQuota && !minutesPrecheckPending;

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

  useEffect(() => {
    if(!assemblyComplete || !autoPublishPending || !assembledEpisode) return;
    
    // Guard 1: Check if publishing already triggered for this episode
    if(publishingTriggeredRef.current && assembledEpisode?.id === lastAutoPublishedEpisodeId){
      setAutoPublishPending(false);
      return;
    }
    
    // Guard 2: Check if episode already published to Spreaker (has spreaker_episode_id)
    if(assembledEpisode?.spreaker_episode_id){
      console.log('[Publishing Guard] Episode already has Spreaker ID:', assembledEpisode.spreaker_episode_id);
      setAutoPublishPending(false);
      publishingTriggeredRef.current = false; // Reset for next episode
      return;
    }
    
    // Guard 3: Legacy check
    if(lastAutoPublishedEpisodeId && assembledEpisode.id === lastAutoPublishedEpisodeId){
      setAutoPublishPending(false);
      return;
    }
    
    if(publishMode === 'draft'){ 
      setAutoPublishPending(false); 
      setStatusMessage('Draft created (processing complete).'); 
      publishingTriggeredRef.current = false; // Reset for next episode
      return; 
    }
    
    // Set flag IMMEDIATELY before async operation to prevent race conditions
    publishingTriggeredRef.current = true;
    
    // Capture schedule values at the moment autopublish triggers (don't re-trigger on date/time changes)
    const capturedPublishMode = publishMode;
    const capturedScheduleDate = scheduleDate;
    const capturedScheduleTime = scheduleTime;
    
    let scheduleEnabled = capturedPublishMode === 'schedule';
    let publish_at=null, publish_at_local=null;
    if(scheduleEnabled){
      const dt = new Date(`${capturedScheduleDate}T${capturedScheduleTime}:00`);
      if(!isNaN(dt.getTime()) && dt.getTime() > Date.now()+9*60000){
        publish_at = dt.toISOString().replace(/\.\d{3}Z$/, 'Z');
        publish_at_local = `${capturedScheduleDate} ${capturedScheduleTime}`;
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
  // CRITICAL: Only trigger when assembly completes and autopublish flag is set
  // Do NOT include scheduleDate/scheduleTime as dependencies or we'll publish multiple times!
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [assemblyComplete, autoPublishPending, assembledEpisode]);

  const handlePublishInternal = async ({ scheduleEnabled, publish_at, publish_at_local }) => {
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
      } catch {}
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

  const quotaInfo = {
    remainingEpisodes,
    maxEpisodes,
    nearQuota,
    quotaExceeded,
    minutesRemaining,
    minutesRemainingPrecheck,
    minutesCap,
    minutesNearCap,
    minutesExceeded,
    minutesRequiredPrecheck,
    minutesBlocking,
    minutesPrecheckPending,
    minutesPrecheckError,
  };

  const clearCover = () => {
    setEpisodeDetails(p=>({ ...p, coverArt:null, coverArtPreview:null, cover_image_path:null, cover_crop:null }));
    setCoverNeedsUpload(false);
  };

  const updateCoverCrop = (val) => {
    setEpisodeDetails(p=>({ ...p, cover_crop: val }));
  };

  const computeNextLocalFromSlot = (slot) => {
    if (!slot) return null;
    let dow = Number(slot.day_of_week);
    if (!Number.isFinite(dow)) return null;
    const timeText = String(slot.time_of_day || '').trim();
    if (!timeText) return null;
    const [hhStr, mmStr] = timeText.split(':');
    const hours = Number(hhStr);
    const minutes = Number(mmStr);
    if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return null;
    const targetDow = (dow + 1) % 7; // Python weekday (Mon=0) -> JS (Sun=0)
    const now = new Date();
    const candidate = new Date(now);
    candidate.setHours(hours, minutes, 0, 0);
    let deltaDays = (targetDow - now.getDay() + 7) % 7;
    if (deltaDays === 0 && candidate <= now) {
      deltaDays = 7;
    }
    candidate.setDate(candidate.getDate() + deltaDays);
    return {
      date: candidate.toISOString().slice(0, 10),
      time: `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`,
    };
  };

  const handleRecurringApply = async (slot) => {
    try {
      const template = templates.find(t=>t.id===slot.template_id);
      if (template) {
        setSelectedTemplate(template);
      }
    } catch {}

    let nextDate = slot?.next_scheduled_date;
    let nextTime = slot?.next_scheduled_time;

    if ((!nextDate || !nextTime) && slot?.id) {
      try {
        const api = makeApi(token);
        const info = await api.get(`/api/recurring/schedules/${slot.id}/next`);
        nextDate = info?.next_publish_date || info?.next_publish_at_local?.slice(0, 10) || nextDate;
        if (info?.next_publish_time) {
          nextTime = info.next_publish_time;
        } else if (info?.next_publish_at_local && info.next_publish_at_local.includes('T')) {
          nextTime = info.next_publish_at_local.split('T')[1]?.slice(0,5) || nextTime;
        }
      } catch (err) {
        console.warn('Failed to fetch next slot info', err);
      }
    }

    if (!nextDate || !nextTime) {
      const fallback = computeNextLocalFromSlot(slot);
      if (fallback) {
        nextDate = fallback.date;
        nextTime = fallback.time;
      }
    }

    if (nextDate && nextTime) {
      setScheduleDate(nextDate);
      setScheduleTime(nextTime);
    }

    setPublishMode('schedule');
    setCurrentStep(2);
  };

  useEffect(() => {
    if (!assemblyComplete) return;
    try {
      localStorage.removeItem('ppp_uploaded_filename');
      localStorage.removeItem('ppp_uploaded_hint');
    } catch {}
    refreshUsage();
  }, [assemblyComplete, refreshUsage]);

  const retryFlubberSearch = async () => {
    setFlubberNotFound(false);
    if(!uploadedFilename) { setCurrentStep(3); return; }
    try {
      setShowFlubberScan(true);
      const api = makeApi(token);
      const payload = { filename: uploadedFilename, intents: { flubber: 'yes' }, fuzzy_threshold: fuzzyThreshold };
      let contexts = [];
      for (let attempt = 0; attempt < 20; attempt++) {
        try {
          const data = await api.post('/api/flubber/prepare-by-file', payload);
          contexts = Array.isArray(data?.contexts) ? data.contexts : [];
          break;
        } catch (e) {
          if (e && e.status === 425) {
            await new Promise(r => setTimeout(r, 1000));
            continue;
          }
          break;
        }
      }
      setShowFlubberScan(false);
      if(contexts.length){ setFlubberContexts(contexts); setShowFlubberReview(true); }
      else { setCurrentStep(3); }
    } catch(_){ setShowFlubberScan(false); setCurrentStep(3); }
  };

  const skipFlubberRetry = () => {
    setFlubberNotFound(false);
    setCurrentStep(3);
  };

  return {
    currentStep,
    setCurrentStep,
    steps,
    progressPercentage,
    selectedTemplate,
    setSelectedTemplate,
    uploadedFile,
    uploadedFilename,
    fileInputRef,
    coverArtInputRef,
    coverCropperRef,
    isUploading,
    isUploadingCover,
    isAssembling,
    isPublishing,
    assemblyComplete,
    assembledEpisode,
    statusMessage,
    error,
    ttsValues,
    mediaLibrary,
    showFlubberReview,
    flubberContexts,
    showInternReview,
    internReviewContexts,
    internResponses,
    showIntentQuestions,
    intents,
    intentDetections,
    intentDetectionReady,
    intentVisibility,
    intentsComplete,
    pendingIntentLabels,
    showFlubberScan,
    capabilities,
    flubberNotFound,
    fuzzyThreshold,
    testMode,
    usage,
    episodeDetails,
    isAiTitleBusy,
    isAiDescBusy,
    jobId,
    spreakerShows,
    selectedSpreakerShow,
    publishMode,
    publishVisibility,
    scheduleDate,
    scheduleTime,
    autoPublishPending,
    transcriptReady,
    transcriptPath,
    showVoicePicker,
    voicePickerTargetId,
    voiceNameById,
    voicesLoading,
    coverNeedsUpload,
    coverMode,
    audioDurationSec,
    processingEstimate,
    quotaInfo,
    missingTitle,
    missingEpisodeNumber,
    blockingQuota,
    canProceedToStep5,
    activeSegment,
    minutesRemaining,
    minutesNearCap,
    minutesCap,
    minutesPrecheck,
    minutesPrecheckPending,
    minutesPrecheckError,
    minutesBlocking,
    minutesRequiredPrecheck,
    minutesRemainingPrecheck,
    minutesDialog,
    setMinutesDialog,
    refreshUsage,
    buildActive,
    cancelBuild,
    handleTemplateSelect,
    handleFileChange,
    handlePreuploadedSelect,
    uploadProgress,
    uploadStats,
    handleCoverFileSelected,
    handleUploadProcessedCover,
    handleTtsChange,
    handleDetailsChange,
    handleAISuggestTitle,
    handleAISuggestDescription,
    handleAssemble,
    handleFlubberConfirm,
    handleFlubberCancel,
    handleInternComplete,
    handleInternCancel,
    handleIntentSubmit,
    handleIntentAnswerChange,
    handlePublish,
    handleVoiceChange,
    handleAISuggest,
    processInternCommand,
    retryFlubberSearch,
    skipFlubberRetry,
    setShowVoicePicker,
    setVoicePickerTargetId,
    setFuzzyThreshold,
    setShowIntentQuestions,
    setShowFlubberScan,
    setFlubberNotFound,
    setStatusMessage,
    setEpisodeDetails,
    setPublishMode,
    setPublishVisibility,
    setScheduleDate,
    setScheduleTime,
    setCoverNeedsUpload,
    setCoverMode,
    selectedPreupload,
    setUsage,
    setError,
    clearCover,
    updateCoverCrop,
    resolveInternVoiceId,
  };
}
