import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import VoicePicker from "@/components/VoicePicker";
import { makeApi } from "@/lib/apiClient";
import { toast } from "@/hooks/use-toast";
import { GripVertical, HelpCircle, Loader2, Mic, Trash2, Upload } from "lucide-react";
import { segmentIcons, sourceIcons } from "./constants";

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
    const isLegacy = (legacySourceType === 'ai_generated') ||
        (legacySourceType === 'tts' && (typeof segment?.source?.script === 'string' || typeof segment?.source?.prompt === 'string'));

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
                            <Select value={segment?.source?.source_type || 'static'} onValueChange={(v) => handleSourceChangeLocal('source_type', v)}>
                                <SelectTrigger className="w-full mt-1">
                                    <SelectValue placeholder="Select source type..." />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="static">{sourceIcons.static} Audio file (upload or choose)</SelectItem>
                                    <SelectItem value="tts">{sourceIcons.tts} Per episode AI voice</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <Button type="button" variant="outline" onClick={() => onOpenTTS()} disabled={cooldown > 0}>
                            <Mic className="w-4 h-4 mr-2" />
                            {cooldown > 0 ? `Generate with AI voice (${cooldown}s)` : 'Generate with AI voice (one-time)'}
                        </Button>
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
                    {segment?.source?.source_type === 'static' && (
                        <div>
                            <Label>Audio File</Label>
                            <div className="flex items-center gap-2 mt-1">
                                <Select value={mediaMatch ? segment.source.filename : ''} onValueChange={(v) => handleSourceChangeLocal('filename', v)}>
                                    <SelectTrigger className="w-full"><SelectValue placeholder={`Select a ${segment.segment_type} file...`} /></SelectTrigger>
                                    <SelectContent>
                                        {filesForType.map(mf => (
                                            <SelectItem key={mf.id} value={mf.filename}>
                                                {mf.friendly_name || mf.filename.split('_').slice(1).join('_')}
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

export default SegmentEditor;
