import { Button } from "@/components/ui/button";
import { useState, useEffect, useMemo, useRef, useCallback } from "react";
import Joyride, { EVENTS, STATUS } from "react-joyride";
import { makeApi } from "@/lib/apiClient";
import { formatDisplayName, isUuidLike } from "@/lib/displayNames";
import { createTTS } from "@/api/media";
import { toast } from "@/hooks/use-toast";
import VoicePicker from "@/components/VoicePicker";
import RecurringScheduleManager from "../RecurringScheduleManager.jsx";
import { useAuth } from "@/AuthContext.jsx";
import { Loader2, Save } from "lucide-react";
import TemplateHeader from "./TemplateHeader";
import TemplateBasicsCard from "./TemplateBasicsCard";
import AIGuidanceCard from "./AIGuidanceCard";
import EpisodeStructureCard from "./EpisodeStructureCard";
import TemplateSidebar from "./TemplateSidebar";
import MusicTimingSection from "./MusicTimingSection";
import GlobalMusicBrowser from "./GlobalMusicBrowser";
import GenerateVoiceDialog from "./GenerateVoiceDialog";
import {
  AI_DEFAULT,
  DEFAULT_VOLUME_LEVEL,
  segmentIcons,
  sourceIcons,
  sourceIconColors,
  volumeLevelToDb,
} from "./constants";

// --- Main Template Editor Component ---
export default function TemplateEditor({ templateId, onBack, token, onTemplateSaved }) {
  const { user: authUser } = useAuth();
  const [template, setTemplate] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(null);
  const [mediaFiles, setMediaFiles] = useState([]);
    const [podcasts, setPodcasts] = useState([]);
    const [baselineTemplate, setBaselineTemplate] = useState(null);
    const skipExitPromptRef = useRef(false);
    // Default AI voice for template prompts
    const [voiceId, setVoiceId] = useState(null);
    const [showVoicePicker, setShowVoicePicker] = useState(false);
    const [voiceName, setVoiceName] = useState(null);
    const [internVoiceId, setInternVoiceId] = useState(null);
    const [showInternVoicePicker, setShowInternVoicePicker] = useState(false);
    const [internVoiceName, setInternVoiceName] = useState(null);
    // One-time AI voice modal state
    const [ttsOpen, setTtsOpen] = useState(false);
    const [ttsTargetSegment, setTtsTargetSegment] = useState(null);
    const [ttsScript, setTtsScript] = useState("");
    const [ttsVoiceId, setTtsVoiceId] = useState(null);
    const [ttsSpeakingRate, setTtsSpeakingRate] = useState(1.0);
    const [ttsFriendlyName, setTtsFriendlyName] = useState("");
    const [ttsVoices, setTtsVoices] = useState([]);
    const [ttsLoading, setTtsLoading] = useState(false);
    const [createdFromTTS, setCreatedFromTTS] = useState({}); // { segmentId: timestampMs }
    const [showMusicOptions, setShowMusicOptions] = useState(false);
    const [showAiSection, setShowAiSection] = useState(true);
    const [showEpisodeStructure, setShowEpisodeStructure] = useState(true);
    const [runTemplateTour, setRunTemplateTour] = useState(false);
    const [scheduleDirty, setScheduleDirty] = useState(false);

        // Load voices when AI voice modal opens
        useEffect(() => {
            const loadVoices = async () => {
                try {
                    const api = makeApi(token);
                    // Prefer paged response shape { items: [...] }
                    const res = await api.get('/api/elevenlabs/voices?size=200');
                    const items = Array.isArray(res?.items) ? res.items : (Array.isArray(res) ? res : []);
                    setTtsVoices(items);
                    // If no explicit voice chosen yet, default to template-level voiceId when available
                    if (!ttsVoiceId && voiceId) setTtsVoiceId(voiceId);
                } catch (e) {
                    // silent fail; dropdown will remain empty
                    setTtsVoices([]);
                }
            };
            if (ttsOpen && ttsVoices.length === 0) {
                loadVoices();
            }
            // eslint-disable-next-line react-hooks/exhaustive-deps
        }, [ttsOpen]);
  const isNewTemplate = templateId === 'new';

  const templateDirty = useMemo(() => {
    if (!template || !baselineTemplate) return false;
    try {
      return JSON.stringify(template) !== JSON.stringify(baselineTemplate);
    } catch {
      return true;
    }
  }, [template, baselineTemplate]);

  const isDirty = templateDirty || scheduleDirty;

  const onMediaUploaded = (newFile) => {
    if (!newFile) return;
    setMediaFiles(prev => {
      const filtered = Array.isArray(prev) ? prev.filter(f => f?.filename !== newFile.filename) : [];
      return [...filtered, newFile];
    });
  };

  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (!isDirty) return;
    const handler = (event) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [isDirty]);

  useEffect(() => {
    if (!template) return;
    setBaselineTemplate((prev) => {
      if (prev) return prev;
      try {
        return JSON.parse(JSON.stringify(template));
      } catch {
        return prev;
      }
    });
  }, [template]);
  // --- Memoized lists for filtered media files ---
    const introFiles = useMemo(() => mediaFiles.filter(mf => mf.category === 'intro'), [mediaFiles]);
  const outroFiles = useMemo(() => mediaFiles.filter(mf => mf.category === 'outro'), [mediaFiles]);
  const musicFiles = useMemo(() => mediaFiles.filter(mf => mf.category === 'music'), [mediaFiles]);
  const commercialFiles = useMemo(() => mediaFiles.filter(mf => mf.category === 'commercial'), [mediaFiles]);

  // --- Data Fetching ---
  useEffect(() => {
    const fetchInitialData = async () => {
      setBaselineTemplate(null);
      setIsLoading(true);
      try {
        const api = makeApi(token);
        const [mediaData, podcastsData, templateData] = await Promise.all([
          api.get('/api/media/'),
          api.get('/api/podcasts/'),
          isNewTemplate ? Promise.resolve(null) : api.get(`/api/templates/${templateId}`),
        ]);

        const mediaArr = Array.isArray(mediaData) ? mediaData : mediaData?.items || [];
        const podcastsArr = Array.isArray(podcastsData) ? podcastsData : podcastsData?.items || [];
        setMediaFiles(mediaArr);
        setPodcasts(podcastsArr);

        if (isNewTemplate) {
          setTemplate({
            name: 'My New Podcast Template',
            is_active: true,
            podcast_id: podcastsArr.length > 0 ? podcastsArr[podcastsArr.length - 1].id : null,
            segments: [
              { id: crypto.randomUUID(), segment_type: 'intro', source: { source_type: 'static', filename: '' } },
              { id: crypto.randomUUID(), segment_type: 'content', source: { source_type: 'static', filename: '' } },
              { id: crypto.randomUUID(), segment_type: 'outro', source: { source_type: 'static', filename: '' } },
            ],
            background_music_rules: [],
            timing: { content_start_offset_s: 0, outro_start_offset_s: 0 },
          });
        } else {
          setTemplate(templateData || null);
        }
        setError(null);
      } catch (err) {
        setError(err?.message || String(err));
      } finally {
        setIsLoading(false);
      }
    };

    fetchInitialData();
  }, [templateId, token, isNewTemplate]);
    useEffect(() => {
      if (!template || showMusicOptions) return;
      const hasAdvanced = Boolean(
        (Array.isArray(template.background_music_rules) && template.background_music_rules.length > 0) ||
        (template.timing && ((template.timing.content_start_offset_s || 0) !== 0 || (template.timing.outro_start_offset_s || 0) !== 0)) ||
        (template.ai_settings && Object.keys(template.ai_settings).length > 0)
      );
      if (hasAdvanced) setShowMusicOptions(true);
    }, [template, showMusicOptions]);

    // Seed local voiceId from template defaults when template changes
    useEffect(() => {
        if (!template) return;
        // Prefer explicit template-level defaults if present
        const tVoice =
            template.default_elevenlabs_voice_id ||
            template.voice_id ||
            (Array.isArray(template.segments)
                ? (template.segments.find(s => s?.source?.source_type === 'tts' && s?.source?.voice_id)?.source?.voice_id || null)
                : null);
        setVoiceId(tVoice || null);
        setVoiceName(null);
        const internDefault =
            template.default_intern_voice_id ||
            template?.automation_settings?.intern_voice_id ||
            template?.ai_settings?.intern_voice_id ||
            null;
        setInternVoiceId(internDefault || null);
        setInternVoiceName(null);
    }, [template]);

    // Resolve friendly name for template-level default voice if we have an id but no name yet
    useEffect(() => {
        if (!voiceId || voiceName) return;
        let cancelled = false;
        (async () => {
            try {
                const api = makeApi(token);
                const v = await api.get(`/api/elevenlabs/voice/${encodeURIComponent(voiceId)}/resolve`);
                const rawName = v?.common_name || v?.name || null;
                const formatted = formatDisplayName(rawName, { fallback: '' });
                if (!cancelled) {
                    const fallbackName = voiceId === 'default'
                        ? 'Default voice'
                        : (formatDisplayName(voiceId, { fallback: '' }) || null);
                    setVoiceName(formatted || fallbackName);
                }
            } catch (_) { /* ignore */ }
        })();
        return () => { cancelled = true; };
    }, [voiceId, voiceName, token]);

    useEffect(() => {
        if (!internVoiceId || internVoiceName) return;
        let cancelled = false;
        (async () => {
            try {
                const api = makeApi(token);
                const v = await api.get(`/api/elevenlabs/voice/${encodeURIComponent(internVoiceId)}/resolve`);
                const rawName = v?.common_name || v?.name || null;
                const formatted = formatDisplayName(rawName, { fallback: '' });
                if (!cancelled) {
                    const fallbackName = internVoiceId === 'default'
                        ? 'Default voice'
                        : (formatDisplayName(internVoiceId, { fallback: '' }) || null);
                    setInternVoiceName(formatted || fallbackName);
                }
            } catch (_) { /* ignore */ }
        })();
        return () => { cancelled = true; };
    }, [internVoiceId, internVoiceName, token]);

  // --- State Handlers ---
  const handleTemplateChange = (field, value) => {
    setTemplate(prev => ({ ...prev, [field]: value }));
  };

  const handleTimingChange = (field, valueInSeconds) => {
    const newTiming = { ...template.timing, [field]: valueInSeconds };
    setTemplate(prev => ({ ...prev, timing: newTiming }));
  };

  const handleBackgroundMusicChange = (index, field, value) => {
    const newRules = [...template.background_music_rules];
    newRules[index][field] = value;
    setTemplate(prev => ({ ...prev, background_music_rules: newRules }));
  };

  const addBackgroundMusicRule = () => {
    const newRule = {
      id: crypto.randomUUID(),
      apply_to_segments: ['content'],
      music_filename: '',
      start_offset_s: 0,
      end_offset_s: 0,
      fade_in_s: 2,
      fade_out_s: 3,
      volume_db: Number(volumeLevelToDb(DEFAULT_VOLUME_LEVEL).toFixed(1)),
    };
    setTemplate(prev => ({ ...prev, background_music_rules: [...(prev.background_music_rules || []), newRule] }));
  };

  const removeBackgroundMusicRule = (index) => {
    const newRules = [...template.background_music_rules];
    newRules.splice(index, 1);
    setTemplate(prev => ({ ...prev, background_music_rules: newRules }));
  };

  const addGlobalMusicToTemplate = (musicAsset) => {
    // Create a new music rule using the global music asset ID
    const newRule = {
      id: crypto.randomUUID(),
      apply_to_segments: ['intro'], // Default to intro, user can change
      music_asset_id: musicAsset.id,
      start_offset_s: 0,
      end_offset_s: 1,
      fade_in_s: 1.5,
      fade_out_s: 2.0,
      volume_db: Number(volumeLevelToDb(DEFAULT_VOLUME_LEVEL).toFixed(1)),
    };
    setTemplate(prev => ({ ...prev, background_music_rules: [...(prev.background_music_rules || []), newRule] }));
    
    // Show success toast
    try {
      toast({
        title: "Music Added",
        description: `"${musicAsset.display_name}" has been added to your template.`,
      });
    } catch (e) {
      // Toast failed, non-fatal
    }
    
    // Expand music section if collapsed
    setShowMusicOptions(true);
  };

  const [musicUploadIndex, setMusicUploadIndex] = useState(null);
  const [isUploadingMusic, setIsUploadingMusic] = useState(false);
  const musicUploadInputRef = useRef(null);
  const musicUploadIndexRef = useRef(null);

  const setMusicVolumeLevel = useCallback((index, level) => {
    const numeric = typeof level === 'number' ? level : parseFloat(level);
    const fallback = DEFAULT_VOLUME_LEVEL;
    const clamped = Math.max(1, Math.min(11, Number.isFinite(numeric) ? numeric : fallback));
    const dbValue = Number(volumeLevelToDb(clamped).toFixed(1));
    handleBackgroundMusicChange(index, 'volume_db', dbValue);
  }, [handleBackgroundMusicChange]);

  const startMusicUpload = useCallback((index) => {
    if (isUploadingMusic) return;
    setMusicUploadIndex(index);
    musicUploadIndexRef.current = index;
    try {
      if (musicUploadInputRef.current) {
        musicUploadInputRef.current.click();
      }
    } catch (_) {
      /* no-op */
    }
  }, [isUploadingMusic]);

  const handleMusicFileSelected = async (event) => {
    const file = event?.target?.files?.[0];
    const targetIndex = musicUploadIndexRef.current;
    if (!file || targetIndex == null) {
      if (event?.target) event.target.value = '';
      setMusicUploadIndex(null);
      musicUploadIndexRef.current = null;
      return;
    }

    setIsUploadingMusic(true);
    try {
      const api = makeApi(token);
      const fd = new FormData();
      fd.append('files', file);
      const data = await api.raw('/api/media/upload/music', { method: 'POST', body: fd });
      const uploadedItem = Array.isArray(data) ? data[0] : data;
      if (!uploadedItem?.filename) {
        throw new Error('Upload succeeded but no file was returned.');
      }
      const uploaded = {
        id: uploadedItem.id || crypto.randomUUID(),
        filename: uploadedItem.filename,
        friendly_name: uploadedItem.friendly_name || undefined,
        category: uploadedItem.category || 'music',
        content_type: uploadedItem.content_type || 'audio/mpeg',
      };
      onMediaUploaded(uploaded);
      handleBackgroundMusicChange(targetIndex, 'music_filename', uploaded.filename);
      try {
        toast({ title: 'Music uploaded', description: 'Your track is now available in the template.' });
      } catch (_) {}
    } catch (e) {
      const message = e?.message || 'Could not upload music.';
      try { toast({ variant: 'destructive', title: 'Upload failed', description: message }); } catch (_) {}
    } finally {
      setIsUploadingMusic(false);
      setMusicUploadIndex(null);
      musicUploadIndexRef.current = null;
      if (event?.target) {
        try { event.target.value = ''; } catch (_) {}
      }
    }
  };

  const handleBackClick = () => {
    if (skipExitPromptRef.current) {
      skipExitPromptRef.current = false;
      if (onBack) onBack();
      return;
    }
    if (isDirty && typeof window !== 'undefined') {
      const confirmLeave = window.confirm('Leave the template editor without saving changes?');
      if (!confirmLeave) {
        return;
      }
    }
    if (onBack) onBack();
  };

    const handleSourceChange = (segmentId, source) => {
     setTemplate(prev => ({
      ...prev,
      segments: prev.segments.map(seg =>
        seg.id === segmentId ? { ...seg, source } : seg
      )
    }));
  };

  const openTtsForSegment = useCallback((segment, prefill) => {
    if (!segment) return;
    setTtsTargetSegment(segment);
    setTtsScript(prefill?.script ?? "");
    setTtsVoiceId(prefill?.voice_id ?? voiceId ?? null);
    setTtsSpeakingRate(
      prefill?.speaking_rate && !Number.isNaN(prefill.speaking_rate)
        ? prefill.speaking_rate
        : 1.0,
    );
    setTtsFriendlyName(prefill?.friendly_name ?? "");
    setTtsOpen(true);
  }, [voiceId]);

  const handleTtsScriptChange = useCallback((value) => {
    setTtsScript(value);
    if (ttsFriendlyName) return;
    const words = (value || "").trim().split(/\s+/).slice(0, 6).join(" ");
    const segLabel = ttsTargetSegment
      ? `${ttsTargetSegment.segment_type.charAt(0).toUpperCase()}${ttsTargetSegment.segment_type.slice(1)}`
      : "Segment";
    const suggestion = `${segLabel} AI voice – ${words}`.trim();
    if (suggestion) setTtsFriendlyName(suggestion);
  }, [ttsFriendlyName, ttsTargetSegment]);

  const handleGenerateClip = useCallback(async () => {
    if (!ttsTargetSegment || !ttsVoiceId || !ttsScript) return;
    setTtsLoading(true);
    try {
      const segType = ttsTargetSegment.segment_type;
      const category = (segType === "intro" || segType === "outro" || segType === "commercial") ? segType : "sfx";
      let confirmCharge = false;
      try {
        const api = makeApi(token);
        const pre = await api.post("/api/media/tts/precheck", {
          text: ttsScript,
          speaking_rate: (ttsSpeakingRate && !Number.isNaN(ttsSpeakingRate)) ? ttsSpeakingRate : 1.0,
          category,
        });
        if (pre?.spam_block) {
          toast({ variant: "destructive", title: "Please wait", description: pre?.message || "You just created a similar clip. Please wait a few seconds or reuse it." });
          setTtsLoading(false);
          return;
        }
        if (pre?.warn_may_cost) {
          const proceed = typeof window !== "undefined" ? window.confirm(pre?.message || "We noticed high usage here. Anything else you create may count against your plan's minutes. Continue?") : true;
          if (!proceed) {
            setTtsLoading(false);
            return;
          }
          confirmCharge = true;
        }
      } catch (_) {
        /* ignore precheck errors */
      }

      const item = await createTTS({
        text: ttsScript,
        voice_id: ttsVoiceId,
        provider: "elevenlabs",
        category,
        friendly_name: ttsFriendlyName && ttsFriendlyName.trim() ? ttsFriendlyName.trim() : undefined,
        speaking_rate: (ttsSpeakingRate && !Number.isNaN(ttsSpeakingRate)) ? ttsSpeakingRate : undefined,
        confirm_charge: confirmCharge,
      });
      const filename = item?.filename;
      if (!filename) throw new Error("AI voice did not return a filename");

      const newMedia = {
        id: item?.id || crypto.randomUUID(),
        filename,
        friendly_name: item?.friendly_name || ttsFriendlyName || filename,
        category,
        content_type: "audio/mpeg",
      };
      onMediaUploaded(newMedia);
      handleSourceChange(ttsTargetSegment.id, { source_type: "static", filename });
      setCreatedFromTTS((prev) => ({ ...prev, [ttsTargetSegment.id]: Date.now() }));
      try {
        toast({ title: "AI voice ready", description: "Audio saved to Media and linked to this segment." });
      } catch (_) {
        /* ignore */
      }
      setTtsOpen(false);
    } catch (e) {
      const apiMessage = e?.detail?.error?.message || e?.detail;
      const detail = (typeof apiMessage === "string" ? apiMessage : e?.message) || "Could not create audio.";
      toast({ variant: "destructive", title: "AI voice failed", description: detail });
    } finally {
      setTtsLoading(false);
    }
  }, [handleSourceChange, onMediaUploaded, ttsFriendlyName, ttsScript, ttsSpeakingRate, ttsTargetSegment, ttsVoiceId, token, toast]);

  const addSegment = (type) => {
    const newSegment = {
      id: crypto.randomUUID(),
      segment_type: type,
      source: { source_type: 'static', filename: '' },
    };
    const segments = [...template.segments];
    const contentIndex = segments.findIndex(s => s.segment_type === 'content');
    
    if (type === 'intro') {
        segments.splice(contentIndex !== -1 ? contentIndex : 0, 0, newSegment);
    } else if (type === 'outro') {
        segments.push(newSegment);
    } else { // commercials
        segments.splice(contentIndex !== -1 ? contentIndex + 1 : segments.length, 0, newSegment);
    }
    setTemplate(prev => ({ ...prev, segments }));
  };

  const deleteSegment = (segmentId) => {
    setTemplate(prev => ({...prev, segments: prev.segments.filter(seg => seg.id !== segmentId)}));
  };

  const onDragEnd = (result) => {
    if (!result.destination) return;

    const items = Array.from(template.segments);
    const [reorderedItem] = items.splice(result.source.index, 1);
    items.splice(result.destination.index, 0, reorderedItem);

    // Enforce structure rules
    const contentIndex = items.findIndex(item => item.segment_type === 'content');
    const firstOutroIndex = items.findIndex(item => item.segment_type === 'outro');

    if (contentIndex !== -1) {
        // Rule: Intros must be before content
        if (reorderedItem.segment_type === 'intro' && result.destination.index > contentIndex) return;
        // Rule: Content cannot be dragged before an intro
        if (reorderedItem.segment_type === 'content' && items.some((item, index) => item.segment_type === 'intro' && index > result.destination.index)) return;
    }
    if (firstOutroIndex !== -1) {
        // Rule: Outros must be after content
        if (reorderedItem.segment_type === 'outro' && contentIndex !== -1 && result.destination.index < contentIndex) return;
        // Rule: Content cannot be dragged after an outro
        if (reorderedItem.segment_type === 'content' && result.destination.index > firstOutroIndex) return;
    }

    setTemplate(prev => ({ ...prev, segments: items }));
  };

  const handleSave = async () => {
    if (!template) return;
    setIsSaving(true);
    setError(null);
    try {
      if (!template.podcast_id) {
        throw new Error('A show is required for this template. Please select one.');
      }
      const api = makeApi(token);
      const payload = { ...template };
      if (voiceId) {
        payload.default_elevenlabs_voice_id = voiceId;
      } else {
        payload.default_elevenlabs_voice_id = null;
      }
      if (internVoiceId) {
        payload.default_intern_voice_id = internVoiceId;
      } else {
        payload.default_intern_voice_id = null;
      }
      if (Array.isArray(payload.segments)) {
        payload.segments = payload.segments.map(seg => {
          if (seg.segment_type !== 'content') {
            const st = seg?.source?.source_type;
            if (st === 'static') {
              const filename = seg?.source?.filename || '';
              return { ...seg, source: { source_type: 'static', filename } };
            }
            if (st === 'tts') {
              const text_prompt = (seg?.source?.text_prompt || '').trim();
              const voice_id = seg?.source?.voice_id || undefined;
              const nextSource = { source_type: 'tts' };
              if (text_prompt) nextSource.text_prompt = text_prompt;
              if (voice_id) nextSource.voice_id = voice_id;
              return { ...seg, source: nextSource };
            }
            return { ...seg, source: { source_type: 'static', filename: seg?.source?.filename || '' } };
          }
          return { ...seg, source: { source_type: 'static', filename: '' } };
        });
      }
      const shouldExit = !scheduleDirty;
      if (isNewTemplate) {
        await api.post('/api/templates/', payload);
      } else {
        await api.put(`/api/templates/${templateId}`, payload);
      }
      try {
        setBaselineTemplate(JSON.parse(JSON.stringify(template)));
      } catch {
        /* ignore snapshot errors */
      }
      if (onTemplateSaved) onTemplateSaved();
      if (shouldExit) {
        skipExitPromptRef.current = true;
        handleBackClick();
      } else {
        try {
          toast({
            title: 'Template saved',
            description: 'Recurring schedule changes are still unsaved.',
          });
        } catch (_) {
          /* ignore */
        }
      }
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setIsSaving(false);
    }
  };

    // --- Render Logic ---
    // IMPORTANT: Hooks (useMemo/useCallback) must run on every render. We compute them
    // before any conditional returns so the hook order is stable across renders.
    const hasContentSegment = template?.segments?.some(s => s.segment_type === 'content') ?? false;
    const resolvedInternVoiceName = internVoiceName && !isUuidLike(internVoiceName)
        ? internVoiceName
        : null;
    const resolvedDefaultVoiceName = voiceName && !isUuidLike(voiceName)
        ? voiceName
        : (voiceId ? (formatDisplayName(voiceId, { fallback: '' }) || null) : null);
    const defaultVoiceDisplay = resolvedDefaultVoiceName
        ? `Using default: ${resolvedDefaultVoiceName}`
        : (voiceId
            ? `Using default: ${formatDisplayName(voiceId, { fallback: 'AI voice' }) || 'AI voice'}`
            : 'Not set (uses default AI voice)');
    const internVoiceDisplay = resolvedInternVoiceName
        || (internVoiceId
            ? (internVoiceId === 'default'
                ? 'Default voice'
                : (formatDisplayName(internVoiceId, { fallback: 'Custom voice' }) || 'Custom voice'))
            : defaultVoiceDisplay);

        // removed duplicate redeclaration of templateTourSteps (defined earlier above)

    const handleStartTour = useCallback(() => {
      setShowMusicOptions(false);
      setRunTemplateTour(true);
    }, []);

    const handleTourCallback = useCallback((data) => {
    const { status, type, step } = data;
    if ([STATUS.FINISHED, STATUS.SKIPPED].includes(status)) {
      setRunTemplateTour(false);
      return;
    }
    if (type === EVENTS.TARGET_NOT_FOUND) {
      setRunTemplateTour(false);
      return;
    }
    if (type === EVENTS.STEP_BEFORE && step?.target === '[data-tour="template-advanced"]') {
      setShowMusicOptions(true);
    }
  }, [setRunTemplateTour, setShowMusicOptions]);

    const templateTourSteps = useMemo(() => [
    {
      target: '[data-tour="template-quickstart"]',
      title: 'Template overview',
      content: 'We will walk through the three key tasks: link a show, build your segment flow, and fine-tune timing before saving.',
      disableBeacon: true,
    },
    {
      target: '[data-tour="template-basics"]',
      title: 'Start with the basics',
      content: podcasts.length === 0
        ? 'Create a show first so you can attach this template. Once a show exists, you will unlock publishing options here.'
        : 'Give the template a clear name and connect it to the show it belongs to. That ensures new episodes pick up the right defaults.',
    },
    {
      target: '[data-tour="template-add"]',
      title: 'Add your building blocks',
      content: 'Use these buttons to add intro, content, outro, or ad segments. You can always drag to reorder later.',
    },
    {
      target: '[data-tour="template-structure"]',
      title: 'Customize each segment',
      content: hasContentSegment
        ? 'Edit scripts, upload clips, and adjust voices right inside this list. Drag handles let you reorder in seconds.'
        : 'Drop in a Content segment so you can drag your uploaded audio into the right spot, then adjust intros, outros, and ads here.',
    },
    {
      target: '[data-tour="template-advanced"]',
      title: 'Fine-tune timing & music',
      content: 'Use Music & Timing Options to set overlaps, fades, and looping beds once you are happy with the structure.',
    },
    {
      target: '[data-tour="template-save"]',
      title: 'Save & reuse',
      content: 'When everything looks right, save the template. New episodes will use these defaults automatically.',
    },
  ], [podcasts.length, hasContentSegment]);

        // After hooks are defined, we can return early for loading/error states
        if (isLoading) return <div className="flex justify-center items-center p-10"><Loader2 className="w-8 h-8 animate-spin" /></div>;
        if (error) return <p className="text-red-500 p-4">Error: {error}</p>;
        if (!template) return null;

  return (
    <div className="p-6 bg-gray-50 min-h-screen">
        <Joyride
            steps={templateTourSteps}
            run={runTemplateTour}
            continuous
            showSkipButton
            scrollToFirstStep
            disableOverlayClose
            callback={handleTourCallback}
            styles={{ options: { zIndex: 10000 } }}
            spotlightClicks
        />
        <TemplateHeader
          isDirty={isDirty}
          isSaving={isSaving}
          onBack={handleBackClick}
          onSave={handleSave}
        />
        <div className="grid gap-6 xl:grid-cols-[2fr_1fr] xl:items-start">
          <div className="space-y-6">
            <TemplateBasicsCard
              template={template}
              podcasts={podcasts}
              onTemplateChange={handleTemplateChange}
            />
            <RecurringScheduleManager
              token={token}
              templateId={template?.id ?? templateId}
              userTimezone={authUser?.timezone || null}
              isNewTemplate={isNewTemplate}
              onDirtyChange={setScheduleDirty}
              collapsible
              defaultOpen
            />
            <AIGuidanceCard
              isOpen={showAiSection}
              onToggle={() => setShowAiSection((prev) => !prev)}
              aiSettings={template?.ai_settings}
              defaultSettings={AI_DEFAULT}
              onChange={(next) => setTemplate((prev) => ({ ...prev, ai_settings: next }))}
            />
            <EpisodeStructureCard
              isOpen={showEpisodeStructure}
              onToggle={() => setShowEpisodeStructure((prev) => !prev)}
              segments={template.segments}
              hasContentSegment={hasContentSegment}
              addSegment={addSegment}
              onSourceChange={handleSourceChange}
              deleteSegment={deleteSegment}
              introFiles={introFiles}
              outroFiles={outroFiles}
              commercialFiles={commercialFiles}
              onDragEnd={onDragEnd}
              onOpenTTS={openTtsForSegment}
              createdFromTTS={createdFromTTS}
              templateVoiceId={voiceId || null}
              token={token}
              onMediaUploaded={onMediaUploaded}
            />
          </div>
          <TemplateSidebar
            template={template}
            onToggleActive={() => handleTemplateChange('is_active', !(template?.is_active !== false))}
            onStartTour={handleStartTour}
          />
        </div>
        <MusicTimingSection
          isOpen={showMusicOptions}
          onToggle={() => setShowMusicOptions((prev) => !prev)}
          template={template}
          onTimingChange={handleTimingChange}
          backgroundMusicRules={template.background_music_rules || []}
          onBackgroundMusicChange={handleBackgroundMusicChange}
          onAddBackgroundMusicRule={addBackgroundMusicRule}
          onRemoveBackgroundMusicRule={removeBackgroundMusicRule}
          musicFiles={musicFiles}
          onStartMusicUpload={startMusicUpload}
          musicUploadIndex={musicUploadIndex}
          isUploadingMusic={isUploadingMusic}
          musicUploadInputRef={musicUploadInputRef}
          onMusicFileSelected={handleMusicFileSelected}
          onSetMusicVolumeLevel={setMusicVolumeLevel}
          voiceName={voiceName}
          onChooseVoice={() => setShowVoicePicker(true)}
          internVoiceDisplay={internVoiceDisplay}
          onChooseInternVoice={() => setShowInternVoicePicker(true)}
        />
        <GlobalMusicBrowser
          token={token}
          onAddMusicToRule={addGlobalMusicToTemplate}
        />
        <div className="flex justify-end items-center mt-6">
            <Button
              data-tour="template-save"
              onClick={handleSave}
              disabled={isSaving || !template.podcast_id || podcasts.length === 0}
              className="bg-blue-600 hover:bg-blue-700 text-white"
            >
                {isSaving ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Saving...</> : <><Save className="w-4 h-4 mr-2" />Save Template</>}
            </Button>
        </div>
        {showVoicePicker && (
          <VoicePicker
            value={voiceId || null}
            onChange={(id) => setVoiceId(id)}
            onSelect={(item) => setVoiceName(item?.common_name || item?.name || null)}
            onClose={() => setShowVoicePicker(false)}
            token={token}
          />
        )}
        {showInternVoicePicker && (
          <VoicePicker
            value={internVoiceId || null}
            onChange={(id) => {
              setInternVoiceId(id);
              if (!id) setInternVoiceName(null);
            }}
            onSelect={(item) => setInternVoiceName(item?.common_name || item?.name || null)}
            onClose={() => setShowInternVoicePicker(false)}
            token={token}
          />
        )}

        <GenerateVoiceDialog
          open={ttsOpen}
          onOpenChange={setTtsOpen}
          script={ttsScript}
          onScriptChange={handleTtsScriptChange}
          voiceId={ttsVoiceId}
          onVoiceChange={setTtsVoiceId}
          voices={ttsVoices}
          friendlyName={ttsFriendlyName}
          onFriendlyNameChange={setTtsFriendlyName}
          onSubmit={handleGenerateClip}
          onCancel={() => setTtsOpen(false)}
          isLoading={ttsLoading}
          canSubmit={Boolean(ttsScript && ttsVoiceId)}
        />
    </div>
  );
}

// Voice Picker modal
// Keep modal open until user clicks Close; selecting sets the voiceId immediately
// Voice name display is optional; here we show the id compactly
{/* The modal is rendered at the root of this component's return via conditional below */}

const SegmentEditor = ({ segment, onDelete, onSourceChange, mediaFiles, isDragging, onOpenTTS, justCreatedTs, templateVoiceId, token, onMediaUploaded }) => {
    const filesForType = mediaFiles[segment.segment_type] || [];
    const [relinkOpen, setRelinkOpen] = useState(false);
    const filename = (segment?.source?.filename || '').trim();
    const mediaMatch = filesForType.find(mf => mf.filename === filename);
    const hasAudioExt = /\.(mp3|wav|m4a|aac|flac|ogg)$/i.test(filename);
    const likelyStale = !!filename && (filename.toLowerCase().startsWith('file-') || !hasAudioExt);
    const isMissing = !filename || !mediaMatch;
    const [relinkChoice, setRelinkChoice] = useState(filename);
    const [showLocalVoicePicker, setShowLocalVoicePicker] = useState(false);
    const [localVoiceName, setLocalVoiceName] = useState(null);
    const uploadInputRef = useRef(null);
    const [isUploading, setIsUploading] = useState(false);
    const [cooldown, setCooldown] = useState(0); // seconds remaining on 30s cooldown after creation
    const supportsPerEpisodeTts = segment.segment_type !== 'commercial';

    useEffect(() => {
        if (!supportsPerEpisodeTts && segment?.source?.source_type === 'tts') {
            onSourceChange(segment.id, { source_type: 'static', filename: segment?.source?.filename || '' });
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [supportsPerEpisodeTts, segment?.source?.source_type, segment?.source?.filename, segment.id]);

    useEffect(() => {
        if (!justCreatedTs) { setCooldown(0); return; }
        let timer;
        const update = () => {
            const elapsed = Math.floor((Date.now() - justCreatedTs) / 1000);
            const left = Math.max(0, 30 - elapsed);
            setCooldown(left);
        };
        update();
        if (30 - Math.floor((Date.now() - justCreatedTs) / 1000) > 0) {
            timer = setInterval(update, 1000);
        }
        return () => { if (timer) clearInterval(timer); };
    }, [justCreatedTs]);

    // Resolve friendly name for any existing per-segment voice_id when present
    useEffect(() => {
        const id = segment?.source?.voice_id;
        if (!id) { setLocalVoiceName(null); return; }
        let cancelled = false;
        (async () => {
            try {
                const api = makeApi(token);
                const v = await api.get(`/api/elevenlabs/voice/${encodeURIComponent(id)}/resolve`);
                const dn = v?.common_name || v?.name || null;
                if (!cancelled) setLocalVoiceName(dn);
            } catch (_) { /* ignore */ }
        })();
        return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [segment?.source?.voice_id, token]);

    const handleSourceChangeLocal = (field, value) => {
        if (field === 'source_type' && value === 'tts' && !supportsPerEpisodeTts) {
            return;
        }
        const newSource = { ...segment.source, [field]: value };
        // When changing source type, reset relevant fields
        if (field === 'source_type') {
            // Only static is supported now; clear any legacy fields
            newSource.prompt = undefined;
            newSource.script = undefined;
            if (value === 'static') {
                newSource.filename = '';
            }
            if (value === 'tts') {
                // Seed a default voice for per-episode TTS
                newSource.voice_id = segment?.source?.voice_id || templateVoiceId || null;
                newSource.text_prompt = segment?.source?.text_prompt || '';
                delete newSource.filename;
            }
        }
    onSourceChange(segment.id, newSource);
    };

    const handleFileUpload = async (file) => {
        if (!file) return;
        setIsUploading(true);
        try {
            const api = makeApi(token);
            const fd = new FormData();
            fd.append('files', file);
            // Map segment type to media category for upload endpoint
            const segType = segment.segment_type;
            const category = (segType === 'intro' || segType === 'outro' || segType === 'commercial') ? segType : 'sfx';
            const data = await api.raw(`/api/media/upload/${category}`, { method: 'POST', body: fd });
            const uploadedItem = Array.isArray(data) ? data[0] : data;
            const uploaded = uploadedItem && uploadedItem.filename ? {
                id: uploadedItem.id || crypto.randomUUID(),
                filename: uploadedItem.filename,
                friendly_name: uploadedItem.friendly_name || undefined,
                category: category,
                content_type: uploadedItem.content_type || 'audio/mpeg',
            } : null;
            if (!uploaded) throw new Error('Upload succeeded but no file was returned.');
            // Inform parent so the media list updates immediately
            if (typeof onMediaUploaded === 'function') {
                onMediaUploaded(uploaded);
            }
            // Link this segment to the new file
            onSourceChange(segment.id, { source_type: 'static', filename: uploaded.filename });
        } catch (e) {
            try { toast({ variant: 'destructive', title: 'Upload failed', description: e?.message || 'Could not upload audio.' }); } catch {}
        } finally {
            setIsUploading(false);
            try { if (uploadInputRef.current) uploadInputRef.current.value = ''; } catch {}
        }
    };

    if (segment.segment_type === 'content') {
        return (
            <Card className={`transition-shadow ${isDragging ? 'shadow-2xl scale-105' : 'shadow-md'} border-green-500 border-2`}>
                <CardHeader className="flex flex-row items-center justify-between p-3 bg-green-100">
                    <div className="flex items-center gap-3">
                        <GripVertical className="w-5 h-5 text-gray-400" />
                        {segmentIcons.content}
                        <span className="font-semibold text-green-800">Main Content</span>
                    </div>
                    <p className="text-sm text-gray-600">Cannot be deleted</p>
                </CardHeader>
                <CardContent className="p-4">
                    <p className="text-gray-600 italic">The main content for your episode will be added here during episode creation. This block serves as a placeholder for its position in the template.</p>
                </CardContent>
            </Card>
        )
    }

    // Detect legacy source types: old 'tts' with inline script/prompt or 'ai_generated'
    const legacySourceType = segment?.source?.source_type;
    const hasLegacyScript = typeof segment?.source?.script === 'string' && segment?.source?.script.trim().length > 0;
    const hasLegacyPrompt = typeof segment?.source?.prompt === 'string' && segment?.source?.prompt.trim().length > 0;
    const hasModernPrompt = typeof segment?.source?.text_prompt === 'string' && segment?.source?.text_prompt.trim().length > 0;
    const isLegacy = supportsPerEpisodeTts && ((legacySourceType === 'ai_generated') ||
        (legacySourceType === 'tts' && (hasLegacyScript || hasLegacyPrompt) && !hasModernPrompt));
    const currentSourceType = supportsPerEpisodeTts ? (legacySourceType || 'static') : 'static';

    return (
        <Card className={`transition-shadow ${isDragging ? 'shadow-2xl scale-105' : 'shadow-md'}`}>
            <CardHeader className="flex flex-row items-center justify-between p-3 bg-gray-100 border-b">
                <div className="flex items-center gap-3">
                    <GripVertical className="w-5 h-5 text-gray-400" />
                    {segmentIcons[segment.segment_type]}
                    <span className="font-semibold text-gray-800">{segment.segment_type.charAt(0).toUpperCase() + segment.segment_type.slice(1)}</span>
                    {justCreatedTs ? (
                        <span className="ml-2 text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">Created with AI voice</span>
                    ) : null}
                    {segment?.source?.source_type === 'static' && isMissing && (
                        <span
                            className="ml-2 text-xs px-2 py-0.5 rounded-full bg-yellow-50 text-yellow-800 border border-yellow-200"
                            title={likelyStale ? 'This looks like a temporary file id. Choose another audio file.' : 'The referenced audio file could not be found. Select an audio file to reconnect it.'}
                        >
                            Missing audio file
                        </span>
                    )}
                </div>
                <Button variant="ghost" size="icon" onClick={onDelete} className="text-red-500 hover:bg-red-100 hover:text-red-700 w-8 h-8"><Trash2 className="w-4 h-4" /></Button>
            </CardHeader>
            <CardContent className="p-4 space-y-4">
                {isLegacy && (
                    <div className="p-3 rounded-md border border-yellow-200 bg-yellow-50 text-yellow-800 flex items-center justify-between gap-3">
                        <div className="text-sm">Legacy segment type. Convert to file (recommended).</div>
                        <div className="flex items-center gap-2">
                            <Button
                                size="sm"
                                variant="outline"
                                onClick={() => {
                                    // Prefill from legacy source when available
                                    const prefill = {
                                        script: segment?.source?.script || segment?.source?.prompt || '',
                                        voice_id: segment?.source?.voice_id || undefined,
                                        speaking_rate: segment?.source?.speaking_rate || undefined,
                                        friendly_name: `${segment.segment_type.charAt(0).toUpperCase() + segment.segment_type.slice(1)} AI voice – Legacy`,
                                    };
                                    onOpenTTS(prefill);
                                }}
                            >Convert now</Button>
                            <Button size="sm" variant="ghost">Keep legacy</Button>
                        </div>
                    </div>
                )}
                <div>
                    <Label className="text-sm font-medium text-gray-600 flex items-center gap-1">Audio Source<HelpCircle className="h-4 w-4 text-muted-foreground" aria-hidden="true" title="Choose between existing audio files or per-episode AI voice prompts." /></Label>
                    <div className="flex items-center gap-3 mt-1">
                        <div className="flex-1">
                            <Select value={currentSourceType} onValueChange={(v) => handleSourceChangeLocal('source_type', v)}>
                                <SelectTrigger className="w-full mt-1">
                                    <SelectValue placeholder="Select source type..." />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="static">
                                        {(() => {
                                            const Icon = sourceIcons.static;
                                            const colorClass = sourceIconColors.static || "";
                                            return <Icon className={`w-4 h-4 mr-2 ${colorClass}`} />;
                                        })()} Audio file (upload or choose)
                                    </SelectItem>
                                    {supportsPerEpisodeTts && (
                                        <SelectItem value="tts">
                                            {(() => {
                                                const Icon = sourceIcons.tts;
                                                const colorClass = sourceIconColors.tts || "";
                                                return <Icon className={`w-4 h-4 mr-2 ${colorClass}`} />;
                                            })()} Per episode AI voice
                                        </SelectItem>
                                    )}
                                </SelectContent>
                            </Select>
                        </div>
                        {supportsPerEpisodeTts && (
                            <Button type="button" variant="outline" onClick={() => onOpenTTS()} disabled={cooldown > 0}>
                                <Mic className="w-4 h-4 mr-2" />
                                {cooldown > 0 ? `Generate with AI voice (${cooldown}s)` : 'Generate with AI voice (one-time)'}
                            </Button>
                        )}
                        {justCreatedTs && cooldown > 0 && (
                            <span className="text-xs text-muted-foreground" title="We saved the last AI voice clip in your Media. Reuse it or wait a moment before creating another.">
                                Recently created — reuse the saved file or wait a moment.
                            </span>
                        )}
                        {segment?.source?.source_type === 'static' && isMissing && (
                            <Button type="button" variant="secondary" size="sm" title="Select an existing audio file for this segment" onClick={() => { setRelinkChoice(filename || ''); setRelinkOpen(true); }}>Choose audio</Button>
                        )}
                    </div>
                </div>
                <div>
                    {currentSourceType === 'static' && (
                        <div>
                            <Label>Audio File</Label>
                            <div className="flex items-center gap-2 mt-1">
                                <Select value={mediaMatch ? segment.source.filename : ''} onValueChange={(v) => handleSourceChangeLocal('filename', v)}>
                                    <SelectTrigger className="w-full"><SelectValue placeholder={`Select a ${segment.segment_type} file...`} /></SelectTrigger>
                                    <SelectContent>
                                        {filesForType.map(mf => (
                                            <SelectItem key={mf.id} value={mf.filename}>
                                                {formatDisplayName(mf, { fallback: mf.friendly_name || 'Audio clip' }) || 'Audio clip'}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                                <Button variant="outline" size="icon" onClick={() => uploadInputRef.current?.click()} disabled={isUploading}>
                                    {isUploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
                                </Button>
                                <input
                                    type="file"
                                    ref={uploadInputRef}
                                    className="hidden"
                                    accept="audio/*"
                                    onChange={(e) => handleFileUpload(e.target.files?.[0])}
                                />
                            </div>
                        </div>
                    )}
                    {supportsPerEpisodeTts && segment?.source?.source_type === 'tts' && (
                        <div className="space-y-3">
                            <div>
                                <Label>Prompt Label (shown during episode creation)</Label>
                                <Input
                                    value={segment?.source?.text_prompt || ''}
                                    onChange={(e) => handleSourceChangeLocal('text_prompt', e.target.value)}
                                    placeholder="e.g., Intro script"
                                />
                            </div>
                            <div className="flex items-center gap-3">
                                <div className="flex-1">
                                    <Label>Default Voice (optional)</Label>
                                    <div className="text-sm text-gray-800 mt-1">{localVoiceName || (segment?.source?.voice_id || 'Not set')}</div>
                                </div>
                                <Button variant="outline" size="sm" onClick={() => setShowLocalVoicePicker(true)}>Choose voice</Button>
                            </div>
                {showLocalVoicePicker && (
                                <VoicePicker
                                    value={segment?.source?.voice_id || templateVoiceId || null}
                                    onChange={(id) => handleSourceChangeLocal('voice_id', id)}
                                    onSelect={(item) => setLocalVoiceName(item?.common_name || item?.name || null)}
                    onClose={() => setShowLocalVoicePicker(false)}
                    token={token}
                                />
                            )}
                            <p className="text-xs text-gray-500">This will create a text box during episode creation. The audio is generated per episode.</p>
                        </div>
                    )}
                </div>
            </CardContent>

            {/* Reconnect audio dialog */}
            <Dialog open={relinkOpen} onOpenChange={setRelinkOpen}>
                <DialogContent className="sm:max-w-[520px]">
                    <DialogHeader>
                        <DialogTitle>Reconnect audio file</DialogTitle>
                        <DialogDescription>
                            Pick an existing audio item to reconnect this segment.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3 py-2">
                        <div>
                            <Label>Select file</Label>
                            <Select value={relinkChoice || ''} onValueChange={setRelinkChoice}>
                                <SelectTrigger className="mt-1">
                                    <SelectValue placeholder={`Select a ${segment.segment_type} file...`} />
                                </SelectTrigger>
                                <SelectContent>
                                    {filesForType.map(mf => (
                                        <SelectItem key={mf.id} value={mf.filename}>
                                            {formatDisplayName(mf, { fallback: mf.friendly_name || 'Audio clip' }) || 'Audio clip'}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                            {filesForType.length === 0 && (
                                <p className="text-xs text-gray-500 mt-2">No files available for this section yet.</p>
                            )}
                        </div>
                    </div>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setRelinkOpen(false)}>Cancel</Button>
                        <Button
                            disabled={!relinkChoice}
                            onClick={() => {
                                if (!relinkChoice) return;
                                onSourceChange(segment.id, { source_type: 'static', filename: relinkChoice });
                                setRelinkOpen(false);
                            }}
                        >Use audio</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </Card>
    )
}



