import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { DragDropContext, Droppable, Draggable } from "@hello-pangea/dnd";
import TemplateAIContent from "./TemplateAIContent";
import {
    Plus,
  Save,
  ArrowLeft,
  Trash2,
  Loader2,
  GripVertical,
  FileText,
  Mic,
  Music,
  Bot,
  Settings2,
  HelpCircle,
} from "lucide-react";
import { useState, useEffect, useMemo, useRef } from "react";
import { makeApi } from "@/lib/apiClient";
import { createTTS } from "@/api/media";
import { toast } from "@/hooks/use-toast";
import VoicePicker from "@/components/VoicePicker";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";

const AI_DEFAULT = {
  auto_fill_ai: true,
  title_instructions: "",
  notes_instructions: "",
  tags_instructions: "",
    tags_always_include: [],
    auto_generate_tags: true
};


// --- Helper Functions & Constants ---

// --- UI Components ---
const segmentIcons = {
    intro: <Music className="w-5 h-5 text-blue-500" />,
    outro: <Music className="w-5 h-5 text-purple-500" />,
    content: <FileText className="w-5 h-5 text-green-500" />,
    commercial: <Mic className="w-5 h-5 text-orange-500" />,
};

const sourceIcons = {
    static: <FileText className="w-4 h-4 mr-2" />,
    tts: <Mic className="w-4 h-4 mr-2" />,
};

const AddSegmentButton = ({ type, onClick, disabled }) => (
    <Button 
        variant="outline" 
        className="flex flex-col h-24 justify-center items-center gap-2 text-gray-700 hover:bg-gray-100 hover:text-blue-600 transition-colors disabled:opacity-50"
        onClick={() => onClick(type)}
        disabled={disabled}
    >
        {segmentIcons[type]}
        <span className="text-sm font-semibold">{type.charAt(0).toUpperCase() + type.slice(1)}</span>
    </Button>
);

// --- Main Template Editor Component ---
export default function TemplateEditor({ templateId, onBack, token, onTemplateSaved }) {
  const [template, setTemplate] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(null);
  const [mediaFiles, setMediaFiles] = useState([]);
    const [podcasts, setPodcasts] = useState([]);
    const [baselineTemplate, setBaselineTemplate] = useState(null);
    const skipExitPromptRef = useRef(false);
    // Default AI voice for TTS (template-level)
    const [voiceId, setVoiceId] = useState(null);
    const [showVoicePicker, setShowVoicePicker] = useState(false);
    const [voiceName, setVoiceName] = useState(null);
    // One-time TTS modal state
    const [ttsOpen, setTtsOpen] = useState(false);
    const [ttsTargetSegment, setTtsTargetSegment] = useState(null);
    const [ttsScript, setTtsScript] = useState("");
    const [ttsVoiceId, setTtsVoiceId] = useState(null);
    const [ttsSpeakingRate, setTtsSpeakingRate] = useState(1.0);
    const [ttsFriendlyName, setTtsFriendlyName] = useState("");
    const [ttsVoices, setTtsVoices] = useState([]);
    const [ttsLoading, setTtsLoading] = useState(false);
    const [createdFromTTS, setCreatedFromTTS] = useState({}); // { segmentId: true }
    const [showAdvanced, setShowAdvanced] = useState(false);

        // Load voices when TTS modal opens
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

  const isDirty = useMemo(() => {
    if (!template || !baselineTemplate) return false;
    try {
      return JSON.stringify(template) !== JSON.stringify(baselineTemplate);
    } catch {
      return true;
    }
  }, [template, baselineTemplate]);

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
                // Fetch media + podcasts in parallel via centralized API client
                const api = makeApi(token);
                const [mediaData, podcastsData] = await Promise.all([
                    api.get('/api/media/'),
                    api.get('/api/podcasts/')
                ]);
                setMediaFiles(mediaData);
                setPodcasts(podcastsData || []);

    if (isNewTemplate) {
          setTemplate({
            name: 'My New Podcast Template',
            is_active: true,
                        podcast_id: (podcastsData && podcastsData.length > 0) ? podcastsData[podcastsData.length - 1].id : null, // assume last = most recent
            segments: [
        { id: crypto.randomUUID(), segment_type: 'intro', source: { source_type: 'static', filename: '' } },
        { id: crypto.randomUUID(), segment_type: 'content', source: { source_type: 'static', filename: '' } },
        { id: crypto.randomUUID(), segment_type: 'outro', source: { source_type: 'static', filename: '' } },
            ],
            background_music_rules: [],
            timing: { content_start_offset_s: 0, outro_start_offset_s: 0 },
          });
                } else {
                    const api = makeApi(token);
                    const templateData = await api.get(`/api/templates/${templateId}`);
                    setTemplate(templateData);
                }
        setError(null);
      } catch (err) {
                setError(err.message || String(err));
      } finally {
        setIsLoading(false);
      }
    };
    fetchInitialData();
  }, [templateId, token, isNewTemplate]);
  useEffect(() => {
    if (!template || showAdvanced) return;
    const hasAdvanced = Boolean(
      (Array.isArray(template.background_music_rules) && template.background_music_rules.length > 0) ||
      (template.timing && ((template.timing.content_start_offset_s || 0) !== 0 || (template.timing.outro_start_offset_s || 0) !== 0)) ||
      (template.ai_settings && Object.keys(template.ai_settings).length > 0)
    );
    if (hasAdvanced) setShowAdvanced(true);
  }, [template, showAdvanced]);

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
    }, [template]);

    // Resolve friendly name for template-level default voice if we have an id but no name yet
    useEffect(() => {
        if (!voiceId || voiceName) return;
        let cancelled = false;
        (async () => {
            try {
                const api = makeApi(token);
                const v = await api.get(`/api/elevenlabs/voice/${encodeURIComponent(voiceId)}/resolve`);
                const dn = v?.common_name || v?.name || null;
                if (!cancelled) setVoiceName(dn);
            } catch (_) { /* ignore */ }
        })();
        return () => { cancelled = true; };
    }, [voiceId, voiceName, token]);

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
    const newRule = { id: crypto.randomUUID(), apply_to_segments: ['content'], music_filename: '', start_offset_s: 0, end_offset_s: 0, fade_in_s: 2, fade_out_s: 3, volume_db: -15 };
    setTemplate(prev => ({ ...prev, background_music_rules: [...(prev.background_music_rules || []), newRule] }));
  };

  const removeBackgroundMusicRule = (index) => {
    const newRules = [...template.background_music_rules];
    newRules.splice(index, 1);
    setTemplate(prev => ({ ...prev, background_music_rules: newRules }));
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
      skipExitPromptRef.current = true;
      if (onTemplateSaved) onTemplateSaved();
      handleBackClick();
    } catch (err) {
      setError(err.message || String(err));
    } finally {
      setIsSaving(false);
    }
  };

  // --- Render Logic ---
  if (isLoading) return <div className="flex justify-center items-center p-10"><Loader2 className="w-8 h-8 animate-spin" /></div>;
  if (error) return <p className="text-red-500 p-4">Error: {error}</p>;
  if (!template) return null;

  const hasContentSegment = template.segments.some(s => s.segment_type === 'content');

  return (
    <div className="p-6 bg-gray-50 min-h-screen space-y-6">
        <div className="flex justify-between items-center">
            <Button onClick={handleBackClick} variant="ghost" className="text-gray-700"><ArrowLeft className="w-4 h-4 mr-2" />Back</Button>
            <h1 className="text-2xl font-bold text-gray-800">Template Editor</h1>
            <div className="flex items-center gap-3">
            {isDirty && !isSaving && <span className="text-xs text-amber-600 font-medium">Unsaved changes</span>}
            <Button onClick={handleSave} disabled={isSaving} className="bg-blue-600 hover:bg-blue-700 text-white">
                {isSaving ? <><Loader2 className="mr-2 h-4 w-4 animate-spin" />Saving...</> : <><Save className="w-4 h-4 mr-2" />Save Template</>}
            </Button>
            </div>
        </div>

                <Card className="shadow-sm">
                    <CardContent className="p-6 flex items-center justify-between">
                        <div>
                            <CardTitle className="text-lg">Template status</CardTitle>
                            <CardDescription>Mark a template inactive to hide it from selection without deleting it.</CardDescription>
                        </div>
                        <div className="flex items-center gap-3">
                            <span className={`text-sm px-2 py-1 rounded-full border ${template?.is_active !== false ? 'bg-green-50 text-green-700 border-green-200' : 'bg-gray-100 text-gray-700 border-gray-300'}`}>
                                {template?.is_active !== false ? 'Active' : 'Inactive'}
                            </span>
                            <Button variant="outline" onClick={() => handleTemplateChange('is_active', !(template?.is_active !== false))}>
                                {template?.is_active !== false ? 'Disable' : 'Enable'}
                            </Button>
                        </div>
                    </CardContent>
                </Card>

                <Card className="shadow-sm"><CardContent className="p-6 space-y-6">
                        <div>
                            <Label htmlFor="template-name" className="text-sm font-medium text-gray-600">Template Name</Label>
                            <Input id="template-name" className="text-2xl font-bold border-0 border-b-2 border-gray-200 focus:border-blue-500 transition-colors p-0" value={template.name || ''} onChange={(e) => handleTemplateChange('name', e.target.value)} />
                        </div>
                        <div>
                            <Label className="text-sm font-medium text-gray-600">Show (Required)</Label>
                            {podcasts.length === 0 ? (
                                <div className="mt-2 p-3 border rounded bg-yellow-50 text-sm text-yellow-700">
                                    You have no shows yet. Create a show first in the Show Manager, then return to create a template.
                                </div>
                            ) : (
                                <Select value={template.podcast_id || ''} onValueChange={(v) => handleTemplateChange('podcast_id', v)}>
                                    <SelectTrigger className="mt-2"><SelectValue placeholder="Select a show" /></SelectTrigger>
                                    <SelectContent>
                                        {podcasts.map(p => <SelectItem key={p.id} value={p.id}>{p.name}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                            )}
                        </div>
                </CardContent></Card>

                {/* Default AI Voice selector */}
                <Card className="shadow-sm">
                    <CardContent className="p-6">
                        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                            <div>
                                <Label className="text-sm font-medium text-gray-600 flex items-center gap-1">Default AI Voice<HelpCircle className="h-4 w-4 text-muted-foreground" aria-hidden="true" title="Set a default voice for template TTS prompts." /></Label>
                                <div className="text-sm text-gray-800 mt-1">{voiceName || 'Not set'}</div>
                            </div>
                            <div className="mt-2 sm:mt-0">
                                <Button variant="outline" onClick={() => setShowVoicePicker(true)}>Choose voice</Button>
                            </div>
                        </div>
                    </CardContent>
                </Card>

        <Card><CardHeader><CardTitle>Add Segments</CardTitle><CardDescription>Add the building blocks for your episode.</CardDescription></CardHeader><CardContent className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <AddSegmentButton type="intro" onClick={addSegment} />
            <AddSegmentButton type="content" onClick={addSegment} disabled={hasContentSegment} />
            <AddSegmentButton type="outro" onClick={addSegment} />
            <AddSegmentButton type="commercial" onClick={addSegment} />
        </CardContent></Card>

        <Card><CardHeader><CardTitle>Episode Structure</CardTitle><CardDescription>Drag and drop segments to reorder them.</CardDescription></CardHeader><CardContent>
            <DragDropContext onDragEnd={onDragEnd}>
                <Droppable droppableId="segments">
                    {(provided) => (
                        <div {...provided.droppableProps} ref={provided.innerRef} className="space-y-4">
                        {template.segments.map((segment, index) => (
                            <Draggable key={segment.id} draggableId={segment.id} index={index} isDragDisabled={segment.segment_type === 'content'}>
                                {(provided, snapshot) => (
                                    <div ref={provided.innerRef} {...provided.draggableProps} {...provided.dragHandleProps}>
                                        <SegmentEditor
                                            segment={segment}
                                            onDelete={() => deleteSegment(segment.id)}
                                            onSourceChange={handleSourceChange}
                                            mediaFiles={{intro: introFiles, outro: outroFiles, commercial: commercialFiles}}
                                            isDragging={snapshot.isDragging}
                                            onOpenTTS={(prefill) => {
                                                setTtsTargetSegment(segment);
                                                // Prefill values when provided (legacy migration), else defaults
                                                setTtsScript(prefill?.script ?? '');
                                                // Prefer legacy voice id, else template-level default
                                                setTtsVoiceId(prefill?.voice_id ?? voiceId ?? null);
                                                setTtsSpeakingRate(
                                                    prefill?.speaking_rate && !Number.isNaN(prefill.speaking_rate)
                                                        ? prefill.speaking_rate
                                                        : 1.0
                                                );
                                                setTtsFriendlyName(prefill?.friendly_name ?? '');
                                                setTtsOpen(true);
                                            }}
                                            justCreated={!!createdFromTTS[segment.id]}
                                            templateVoiceId={voiceId || null}
                                            token={token}
                                        />
                                    </div>
                                )}
                            </Draggable>
                        ))}
                        {provided.placeholder}
                        </div>
                    )}
                </Droppable>
            </DragDropContext>
        </CardContent></Card>

        <div className="flex items-center justify-between pt-2">
            <h2 className="text-lg font-semibold">Advanced options</h2>
            <Button variant="outline" size="sm" onClick={() => setShowAdvanced((prev) => !prev)}>
                {showAdvanced ? 'Hide advanced' : 'Show advanced'}
            </Button>
        </div>
        {showAdvanced && (
            <>
                <Card>
                    <CardHeader>
                        <CardTitle className="flex items-center gap-2"><Settings2 className="w-6 h-6 text-gray-600" /> Advanced Settings</CardTitle>
                        <CardDescription>Fine-tune the timing and background music for your podcast.</CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-6 pt-4">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                            <div>
                                <Label className="flex items-center gap-1">
                                    Content Start Delay (seconds)
                                    <HelpCircle className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" title="Delay before main content begins after intro. Use negatives to overlap." />
                                </Label>
                                <Input type="number" step="0.5" value={template.timing?.content_start_offset_s} onChange={(e) => handleTimingChange('content_start_offset_s', parseFloat(e.target.value || 0))} />
                                <p className="text-xs text-gray-500 mt-1">Delay / overlap (negative overlaps intro). Default 0.</p>
                            </div>
                            <div>
                                <Label className="flex items-center gap-1">
                                    Outro Start Delay (seconds)
                                    <HelpCircle className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" title="Delay before the outro begins. Use negatives to overlap." />
                                </Label>
                                <Input type="number" step="0.5" value={template.timing?.outro_start_offset_s} onChange={(e) => handleTimingChange('outro_start_offset_s', parseFloat(e.target.value || 0))} />
                                <p className="text-xs text-gray-500 mt-1">Delay / overlap (negative overlaps content tail). Default 0.</p>
                            </div>
                        </div>
                        <div>
                            <h4 className="text-lg font-semibold mb-2 flex items-center gap-1">
                                Background Music
                                <HelpCircle className="h-4 w-4 text-muted-foreground" aria-hidden="true" title="Apply looping music or stingers to specific sections." />
                            </h4>
                            <div className="space-y-4">
                                {(template.background_music_rules || []).map((rule, index) => (
                                    <div key={rule.id} className="p-4 border rounded-lg bg-gray-50 space-y-4">
                                        <div className="flex justify-between items-center">
                                            <Label className="font-semibold">Music Rule #{index + 1}</Label>
                                            <Button variant="destructive" size="sm" onClick={() => removeBackgroundMusicRule(index)}>
                                                <Trash2 className="w-4 h-4 mr-2" />Remove
                                            </Button>
                                        </div>
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                            <div>
                                                <Label>Apply to Section</Label>
                                                <Select value={rule.apply_to_segments[0]} onValueChange={(v) => handleBackgroundMusicChange(index, 'apply_to_segments', [v])}>
                                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                                    <SelectContent>
                                                        <SelectItem value="intro">Intro Section</SelectItem>
                                                        <SelectItem value="content">Content Section</SelectItem>
                                                        <SelectItem value="outro">Outro Section</SelectItem>
                                                    </SelectContent>
                                                </Select>
                                            </div>
                                            <div>
                                                <Label>Music File</Label>
                                                <Select value={rule.music_filename} onValueChange={(v) => handleBackgroundMusicChange(index, 'music_filename', v)}>
                                                    <SelectTrigger><SelectValue placeholder="Select music..." /></SelectTrigger>
                                                    <SelectContent>{musicFiles.map(f => <SelectItem key={f.id} value={f.filename}>{f.friendly_name || f.filename.split('_').slice(1).join('_')}</SelectItem>)}</SelectContent>
                                                </Select>
                                            </div>
                                        </div>
                                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                                            <div>
                                                <Label>Start Offset (sec)</Label>
                                                <Input type="number" step="0.5" value={rule.start_offset_s} onChange={(e) => handleBackgroundMusicChange(index, 'start_offset_s', parseFloat(e.target.value || 0))} />
                                            </div>
                                            <div>
                                                <Label>End Offset (sec)</Label>
                                                <Input type="number" step="0.5" value={rule.end_offset_s} onChange={(e) => handleBackgroundMusicChange(index, 'end_offset_s', parseFloat(e.target.value || 0))} />
                                            </div>
                                            <div>
                                                <Label>Fade In (sec)</Label>
                                                <Input type="number" step="0.5" value={rule.fade_in_s} onChange={(e) => handleBackgroundMusicChange(index, 'fade_in_s', parseFloat(e.target.value || 0))} />
                                            </div>
                                            <div>
                                                <Label>Fade Out (sec)</Label>
                                                <Input type="number" step="0.5" value={rule.fade_out_s} onChange={(e) => handleBackgroundMusicChange(index, 'fade_out_s', parseFloat(e.target.value || 0))} />
                                            </div>
                                        </div>
                                        <div className="mt-4">
                                            <Label>Volume (dB)</Label>
                                            <div className="flex items-center gap-2">
                                                <Input
                                                    type="range"
                                                    min="-60"
                                                    max="0"
                                                    step="1"
                                                    value={rule.volume_db}
                                                    onChange={(e) => handleBackgroundMusicChange(index, 'volume_db', parseInt(e.target.value, 10))}
                                                    className="w-full"
                                                />
                                                <span className="text-sm font-mono w-16 text-center">{rule.volume_db} dB</span>
                                            </div>
                                        </div>
                                    </div>
                                ))}
                            </div>
                            <Button onClick={addBackgroundMusicRule} variant="outline" className="mt-4">
                                <Plus className="w-4 h-4 mr-2" />Add Music Rule
                            </Button>
                        </div>
                    </CardContent>
                </Card>

                <TemplateAIContent
                    value={(template?.ai_settings) || AI_DEFAULT}
                    onChange={(next) => setTemplate(prev => ({ ...prev, ai_settings: next }))}
                />
            </>
        )}
                <div className="flex justify-end items-center mt-6">
            <Button onClick={handleSave} disabled={isSaving || !template.podcast_id || podcasts.length === 0} className="bg-blue-600 hover:bg-blue-700 text-white">
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

                {/* One-time TTS Modal */}
                <Dialog open={ttsOpen} onOpenChange={(v) => { setTtsOpen(v); }}>
                    <DialogContent className="sm:max-w-[600px]">
                        <DialogHeader>
                            <DialogTitle>Create with TTS (one-time)</DialogTitle>
                            <DialogDescription>We’ll synthesize this once and save it to your library. You won’t need to re-generate it every episode.</DialogDescription>
                        </DialogHeader>
                        <div className="space-y-4 py-2">
                            <div>
                                <Label>Script</Label>
                                <Textarea value={ttsScript} onChange={(e) => {
                                    setTtsScript(e.target.value);
                                    // Auto-suggest friendly name from first 6 words
                                    const words = (e.target.value || '').trim().split(/\s+/).slice(0, 6).join(' ');
                                    const segLabel = ttsTargetSegment ? (ttsTargetSegment.segment_type.charAt(0).toUpperCase() + ttsTargetSegment.segment_type.slice(1)) : 'Segment';
                                    if (!ttsFriendlyName) setTtsFriendlyName(`${segLabel} TTS – ${words}`.trim());
                                }} placeholder="e.g., Welcome to the show..." className="mt-1" rows={5} />
                            </div>
                            <div>
                                <Label>Voice</Label>
                                <Select value={ttsVoiceId || ''} onValueChange={(v) => setTtsVoiceId(v)}>
                                    <SelectTrigger className="mt-1"><SelectValue placeholder="Select a voice" /></SelectTrigger>
                                    <SelectContent>
                                        {ttsVoices.map(v => (
                                            <SelectItem key={v.voice_id || v.id || v.name} value={(v.voice_id || v.id || '')}>{v.common_name || v.name || v.voice_id || v.id}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div>
                                <Label>Friendly name (optional)</Label>
                                <Input value={ttsFriendlyName} onChange={(e) => setTtsFriendlyName(e.target.value)} placeholder="e.g., Victoria's Intro" />
                            </div>
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setTtsOpen(false)}>Cancel</Button>
                            <Button disabled={ttsLoading || !ttsScript || !ttsVoiceId} onClick={async () => {
                                if (!ttsTargetSegment) return;
                                setTtsLoading(true);
                                try {
                                    const segType = ttsTargetSegment.segment_type;
                                    const category = (segType === 'intro' || segType === 'outro' || segType === 'commercial') ? segType : 'sfx';
                                    const item = await createTTS({
                                        text: ttsScript,
                                        voice_id: ttsVoiceId,
                                        provider: 'elevenlabs',
                                        category,
                                        friendly_name: ttsFriendlyName && ttsFriendlyName.trim() ? ttsFriendlyName.trim() : undefined,
                                        speaking_rate: (ttsSpeakingRate && !Number.isNaN(ttsSpeakingRate)) ? ttsSpeakingRate : undefined,
                                    });
                                    const filename = item?.filename;
                                    if (!filename) throw new Error('TTS did not return a filename');
                                    // Add to media list so it appears immediately
                                    const newMedia = {
                                        id: item?.id || crypto.randomUUID(),
                                        filename,
                                        friendly_name: item?.friendly_name || ttsFriendlyName || filename,
                                        category,
                                        content_type: 'audio/mpeg',
                                    };
                                    setMediaFiles(prev => [...prev, newMedia]);
                                    // Link segment to static file
                                    handleSourceChange(ttsTargetSegment.id, { source_type: 'static', filename });
                                    setCreatedFromTTS(prev => ({ ...prev, [ttsTargetSegment.id]: true }));
                                    try { toast({ title: 'TTS created', description: 'Audio saved to Media and linked to this segment.' }); } catch {}
                                    setTtsOpen(false);
                                } catch (e) {
                                    // Try to extract a meaningful error message from the API response.
                                    const apiMessage = e?.detail?.error?.message || e?.detail;
                                    const detail = (typeof apiMessage === 'string' ? apiMessage : e?.message) || 'Could not create audio.';
                                    toast({ variant: 'destructive', title: 'TTS Failed', description: detail });
                                } finally {
                                    setTtsLoading(false);
                                }
                            }}>{ttsLoading ? 'Creating…' : 'Create'}</Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
    </div>
  );
}

// Voice Picker modal
// Keep modal open until user clicks Close; selecting sets the voiceId immediately
// Voice name display is optional; here we show the id compactly
{/* The modal is rendered at the root of this component's return via conditional below */}

const SegmentEditor = ({ segment, onDelete, onSourceChange, mediaFiles, isDragging, onOpenTTS, justCreated, templateVoiceId, token }) => {
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

    if (segment.segment_type === 'content') {
        return (
            <Card className={`transition-shadow ${isDragging ? 'shadow-2xl scale-105' : 'shadow-md'} border-green-500 border-2`}>
                <CardHeader className="flex flex-row items-center justify-between p-4 bg-green-100">
                    <div className="flex items-center gap-3">
                        <GripVertical className="w-5 h-5 text-gray-400" />
                        {segmentIcons.content}
                        <span className="font-semibold text-green-800">Main Content</span>
                    </div>
                    <p className="text-sm text-gray-600">Cannot be deleted</p>
                </CardHeader>
                <CardContent className="p-6">
                    <p className="text-gray-600 italic">The main content for your episode will be added here during episode creation. This block serves as a placeholder for its position in the template.</p>
                </CardContent>
            </Card>
        )
    }

    // Detect legacy source types: old 'tts' with inline script/prompt or 'ai_generated'
    const legacySourceType = segment?.source?.source_type;
    const isLegacy = (legacySourceType === 'ai_generated') ||
        (legacySourceType === 'tts' && (typeof segment?.source?.script === 'string' || typeof segment?.source?.prompt === 'string'));

    return (
        <Card className={`transition-shadow ${isDragging ? 'shadow-2xl scale-105' : 'shadow-md'}`}>
            <CardHeader className="flex flex-row items-center justify-between p-4 bg-gray-100 border-b">
                <div className="flex items-center gap-3">
                    <GripVertical className="w-5 h-5 text-gray-400" />
                    {segmentIcons[segment.segment_type]}
                    <span className="font-semibold text-gray-800">{segment.segment_type.charAt(0).toUpperCase() + segment.segment_type.slice(1)}</span>
                    {justCreated ? (
                        <span className="ml-2 text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200">Created from TTS</span>
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
            <CardContent className="p-6 space-y-4">
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
                                        friendly_name: `${segment.segment_type.charAt(0).toUpperCase() + segment.segment_type.slice(1)} TTS – Legacy`,
                                    };
                                    onOpenTTS(prefill);
                                }}
                            >Convert now</Button>
                            <Button size="sm" variant="ghost">Keep legacy</Button>
                        </div>
                    </div>
                )}
                <div>
                    <Label className="text-sm font-medium text-gray-600 flex items-center gap-1">Audio Source<HelpCircle className="h-4 w-4 text-muted-foreground" aria-hidden="true" title="Choose between existing audio files or per-episode TTS prompts." /></Label>
                    <div className="flex items-center gap-3 mt-1">
                        <div className="flex-1">
                            <Select value={segment?.source?.source_type || 'static'} onValueChange={(v) => handleSourceChangeLocal('source_type', v)}>
                                <SelectTrigger className="w-full mt-1">
                                    <SelectValue placeholder="Select source type..." />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="static">{sourceIcons.static} Audio file (upload or choose)</SelectItem>
                                    <SelectItem value="tts">{sourceIcons.tts} Per Episode TTS</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <Button type="button" variant="outline" onClick={() => onOpenTTS()}><Mic className="w-4 h-4 mr-2" />Create with TTS (one-time)</Button>
                        {segment?.source?.source_type === 'static' && isMissing && (
                            <Button type="button" variant="secondary" size="sm" title="Select an existing audio file for this segment" onClick={() => { setRelinkChoice(filename || ''); setRelinkOpen(true); }}>Choose audio</Button>
                        )}
                    </div>
                </div>
                <div>
                    {segment?.source?.source_type === 'static' && (
                        <div>
                            <Label>Audio File</Label>
                            <Select value={mediaMatch ? segment.source.filename : ''} onValueChange={(v) => handleSourceChangeLocal('filename', v)}>
                                <SelectTrigger className="w-full mt-1"><SelectValue placeholder={`Select a ${segment.segment_type} file...`} /></SelectTrigger>
                                <SelectContent>
                                    {filesForType.map(mf => (
                                        <SelectItem key={mf.id} value={mf.filename}>
                                            {mf.friendly_name || mf.filename.split('_').slice(1).join('_')}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                    )}
                    {segment?.source?.source_type === 'tts' && (
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
                                            {mf.friendly_name || mf.filename.split('_').slice(1).join('_')}
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