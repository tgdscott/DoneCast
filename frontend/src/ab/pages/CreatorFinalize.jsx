
import React, { useEffect, useMemo, useState } from "react";
import { useAbDrafts } from "../store/useAbDrafts";
import { abApi } from "../lib/abApi";
import { makeApi, buildApiUrl } from "@/lib/apiClient.js";
import { fetchVoices as fetchElevenVoices } from "@/api/elevenlabs";
import VoicePicker from "@/components/VoicePicker";
import { formatDisplayName } from "@/lib/displayNames";

export default function CreatorFinalize({ token, drafts, uploads, uploadById, goUpload }) {
  const [visibility, setVisibility] = useState("draft");

  // Pick the first draft for demo purposes
  const activeDraft = drafts[0] || null;
  const fileId = activeDraft?.fileId || null;
  const showId = uploads.find(u=>u.id===fileId)?.showId || null;

  // Access drafts store helpers early (setDraftMeta is used in effects below)
  const { getDraftMeta, setDraftMeta } = useAbDrafts();
  const meta = useMemo(()=> (showId && fileId) ? getDraftMeta(showId, fileId) : {}, [showId, fileId, getDraftMeta]);

  const [title, setTitle] = useState(meta.title || "How to pick a podcast niche in 2025");
  const [description, setDescription] = useState(meta.description || "In this episode we cover how to find a topic you can stick with...");
  const [tags, setTags] = useState(meta.tags || "");
  const transcriptReady = !!(meta?.transcript === 'ready');
  const [scheduleAt, setScheduleAt] = useState(meta?.schedule_at || "");
  const [aiError, setAiError] = useState({ title: null, description: null, tags: null });

  // Keep local state in sync if meta changes (e.g., when switching drafts later)
  useEffect(()=>{
    if(meta){
      if(meta.title) setTitle(meta.title);
      if(meta.description) setDescription(meta.description);
      if(typeof meta.tags === 'string') setTags(meta.tags);
      else if(Array.isArray(meta.tags)) setTags(meta.tags.join(", "));
      if(meta.schedule_at) setScheduleAt(meta.schedule_at);
    }
  }, [meta]);

  // Poll transcript readiness lightly if not ready yet
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!token || transcriptReady || !fileId) return;
      const file = uploadById[fileId];
      const hint = (meta?.hint || file?.serverFilename || file?.fileName || '').replace(/\.[a-z0-9]+$/i, '');
      if (!hint) return;
      const poll = async () => {
        try {
          const res = await abApi(token).transcriptReady({ hint });
          if (cancelled) return;
          if (res && res.ready) {
            if (showId && fileId) setDraftMeta(showId, fileId, { transcript: 'ready' });
            return; // stop
          }
        } catch {}
        if (!cancelled) setTimeout(poll, 5000);
      };
      setTimeout(poll, 2000);
    })();
    return () => { cancelled = true; };
  }, [token, transcriptReady, fileId, showId, meta?.hint, uploadById, setDraftMeta]);



  const onSave = () => {
    if (!showId || !fileId) return;
    const tagsValue = (tags || "").trim();
    setDraftMeta(showId, fileId, { title: title?.trim(), description: description?.trim(), tags: tagsValue, schedule_at: scheduleAt || null });
    window.alert('Saved');
  };
  const onPublish = async () => {
    window.alert('Publishing feature removed.');
  };
  const onAISuggestTitle = async () => {
    if (!fileId) return;
    const file = uploadById[fileId];
    setAiError(prev => ({ ...prev, title: null }));
    try {
      const res = await abApi(token).aiMetadata({ current_title: title, current_description: description, filename: file?.serverFilename || file?.fileName });
      if (res?.title) setTitle(res.title);
      // Persist immediately
      if (showId && fileId && res?.title) setDraftMeta(showId, fileId, { title: res.title });
    } catch (err) {
      if (err?.status === 429 || err?.status === 503) {
        const msg = err.status === 429 ? 'Too many requests. Please wait and retry.' : 'Service temporarily unavailable. Please retry.';
        setAiError(prev => ({ ...prev, title: msg }));
      }
    }
  };
  const onAIExpandDesc = async () => {
    if (!fileId) return;
    const file = uploadById[fileId];
    setAiError(prev => ({ ...prev, description: null }));
    try {
      const res = await abApi(token).aiMetadata({ current_title: title, current_description: description, filename: file?.serverFilename || file?.fileName, prompt: 'expand' });
      if (res?.description) setDescription(res.description);
      if (showId && fileId && res?.description) setDraftMeta(showId, fileId, { description: res.description });
    } catch (err) {
      if (err?.status === 429 || err?.status === 503) {
        const msg = err.status === 429 ? 'Too many requests. Please wait and retry.' : 'Service temporarily unavailable. Please retry.';
        setAiError(prev => ({ ...prev, description: msg }));
      }
    }
  };
  const onAIShortenDesc = async () => {
    if (!fileId) return;
    const file = uploadById[fileId];
    setAiError(prev => ({ ...prev, description: null }));
    try {
      const res = await abApi(token).aiMetadata({ current_title: title, current_description: description, filename: file?.serverFilename || file?.fileName, prompt: 'shorten' });
      if (res?.description) setDescription(res.description);
      if (showId && fileId && res?.description) setDraftMeta(showId, fileId, { description: res.description });
    } catch (err) {
      if (err?.status === 429 || err?.status === 503) {
        const msg = err.status === 429 ? 'Too many requests. Please wait and retry.' : 'Service temporarily unavailable. Please retry.';
        setAiError(prev => ({ ...prev, description: msg }));
      }
    }
  };
  const onAISuggestTags = async () => {
    if (!fileId) return;
    const file = uploadById[fileId];
    setAiError(prev => ({ ...prev, tags: null }));
    try {
      const res = await abApi(token).aiMetadata({ current_title: title, current_description: description, filename: file?.serverFilename || file?.fileName, prompt: 'tags' });
      const nextTags = Array.isArray(res?.tags) ? res.tags.join(", ") : (typeof res?.tags === 'string' ? res.tags : null);
      if (nextTags) setTags(nextTags);
      if (showId && fileId && nextTags) setDraftMeta(showId, fileId, { tags: nextTags });
    } catch (err) {
      if (err?.status === 429 || err?.status === 503) {
        const msg = err.status === 429 ? 'Too many requests. Please wait and retry.' : 'Service temporarily unavailable. Please retry.';
        setAiError(prev => ({ ...prev, tags: msg }));
      }
    }
  };

  // Intro/Outro modal state (reuse from Upload page)
  const [showIntroOutro, setShowIntroOutro] = useState(false);
  const [ioLoading, setIoLoading] = useState(false);
  const [ioTemplate, setIoTemplate] = useState(null);
  const [ioEdits, setIoEdits] = useState({});
  // Auto tags: Intro 1/2, Outro 1/2; no manual tag input
  const [mediaFiles, setMediaFiles] = useState([]);
  const [showVoicePicker, setShowVoicePicker] = useState(false);
  const [voicePickerTargetId, setVoicePickerTargetId] = useState(null);
  const [ioSuggesting, setIoSuggesting] = useState(false);
  // Friendly voice names
  const [voiceNameById, setVoiceNameById] = useState({});
  const [voicesLoading, setVoicesLoading] = useState(false);

  // Load media and section tags only when modal opens
  useEffect(() => {
    let cancel = false;
    (async () => {
      if (!showIntroOutro) return;
      try {
        const list = await abApi(token).listMedia();
        if (!cancel) setMediaFiles(Array.isArray(list) ? list : []);
      } catch { if (!cancel) setMediaFiles([]); }
  // No tag fetching needed; tags are auto-named
    })();
    return () => { cancel = true; };
  }, [showIntroOutro, token, showId]);

  // Resolve friendly voice names when modal has a template
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!showIntroOutro || !ioTemplate) return;
      try {
        const ids = new Set();
        (ioTemplate?.segments || []).forEach(s => {
          if (s?.source?.source_type === 'tts') {
            const idA = ioEdits?.[s.id]?.source?.voice_id;
            const idB = s?.source?.voice_id;
            if (idA && String(idA).toLowerCase() !== 'default') ids.add(String(idA));
            if (idB && String(idB).toLowerCase() !== 'default') ids.add(String(idB));
          }
        });
        if (!ids.size) return;
        let haveAll = true;
        for (const id of ids) { if (!voiceNameById[id]) { haveAll = false; break; } }
        if (haveAll) return;
        setVoicesLoading(true);
        let map = {};
        try {
          if (token) {
            const api = makeApi(token);
            const res = await api.get('/api/elevenlabs/voices?size=200');
            const items = Array.isArray(res?.items) ? res.items : (Array.isArray(res) ? res : []);
            for (const v of (items || [])) { const dn = v.common_name || v.name || ''; if (dn) map[v.voice_id] = dn; }
          } else {
            const res = await fetchElevenVoices('', 1, 200);
            for (const v of (res?.items || [])) { const dn = v.common_name || v.name || ''; if (dn) map[v.voice_id] = dn; }
          }
        } catch {}
        if (!cancelled && Object.keys(map).length) setVoiceNameById(prev => ({ ...prev, ...map }));
        const unknown = Array.from(ids).filter(id => id && id.toLowerCase() !== 'default' && !map[id]);
        if (unknown.length && token) {
          const api = makeApi(token);
          for (const id of unknown) {
            try {
              const v = await api.get(`/api/elevenlabs/voice/${encodeURIComponent(id)}/resolve`);
              const dn = v?.common_name || v?.name || '';
              if (dn && !cancelled) setVoiceNameById(prev => ({ ...prev, [id]: dn }));
            } catch {}
          }
        }
      } finally {
        if (!cancelled) setVoicesLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [showIntroOutro, ioTemplate, ioEdits, token]);

  return (
    <>
    <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">Finalize · Titles & Publish</h1>
          <p className="text-sm text-muted-foreground">Review AI suggestions, set visibility, and schedule publishing.</p>
        </div>
        <div className="flex items-center gap-2">
          <button className="rounded-xl border px-4 py-2 hover:bg-muted focus:outline-none" onClick={onSave}>Save</button>
          <button className="rounded-xl bg-indigo-600 px-4 py-2 text-white shadow hover:bg-indigo-500 focus:outline-none focus-visible:ring" onClick={onPublish}>{visibility==='publish' ? 'Publish' : 'Publish'}</button>
        </div>
      </div>

  {/* Simplified header; removed 6-step timeline since navigation isn't back-and-forth here */}

      <div className={`rounded-xl border px-4 py-3 text-sm ${transcriptReady ? 'bg-green-50 text-green-800 border-green-200' : 'bg-amber-50 text-amber-800 border-amber-200'}`}>
        <strong>Transcript status:</strong> {transcriptReady ? 'ready' : 'processing...'} You can keep editing; AI fields {transcriptReady ? 'are available.' : 'will fill in automatically once ready.'}
        <button className="ml-3 px-2 py-1 rounded border text-xs" onClick={goUpload}>View uploads</button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <section className="lg:col-span-2 rounded-2xl border bg-card p-4 space-y-4">
          <h2 className="text-base font-semibold">Title & description</h2>
          <div className="grid gap-3">
            <label className="text-sm font-medium">Title</label>
            <div className="flex gap-2">
              <input className="flex-1 rounded-lg border px-3 py-2 focus:outline-none focus-visible:ring" value={title} onChange={e=>setTitle(e.target.value)} />
              <button className="px-3 py-2 rounded-lg border hover:bg-muted" onClick={onAISuggestTitle} title="AI suggest title (1 credit)">AI suggest</button>
              {aiError.title && (
                <button className="px-3 py-2 rounded-lg bg-red-600 text-white hover:bg-red-700 text-xs" onClick={onAISuggestTitle} title={aiError.title}>Retry</button>
              )}
            </div>
            {aiError.title && <p className="text-xs text-red-600">{aiError.title}</p>}
          </div>
          <div className="grid gap-3">
            <label className="text-sm font-medium">Description</label>
            <textarea className="min-h-32 rounded-lg border px-3 py-2 focus:outline-none focus-visible:ring" value={description} onChange={e=>setDescription(e.target.value)} />
            <div className="flex gap-2">
              <button className="px-3 py-2 rounded-lg border hover:bg-muted" onClick={onAIExpandDesc} title="AI expand description (2 credits)">AI expand</button>
              <button className="px-3 py-2 rounded-lg border hover:bg-muted" onClick={onAIShortenDesc} title="AI shorten description (2 credits)">AI shorten</button>
              {aiError.description && (
                <button className="px-3 py-2 rounded-lg bg-red-600 text-white hover:bg-red-700 text-xs" onClick={onAIExpandDesc} title={aiError.description}>Retry</button>
              )}
            </div>
            {aiError.description && <p className="text-xs text-red-600">{aiError.description}</p>}
          </div>
          <div className="grid gap-3">
            <label className="text-sm font-medium">Tags</label>
            <div className="flex gap-2">
              <input className="flex-1 rounded-lg border px-3 py-2" value={tags} onChange={e=>setTags(e.target.value)} placeholder="comma, separated, tags" />
              <button className="px-3 py-2 rounded-lg border hover:bg-muted" onClick={onAISuggestTags} title="AI suggest tags (1 credit)">AI tags</button>
              {aiError.tags && (
                <button className="px-3 py-2 rounded-lg bg-red-600 text-white hover:bg-red-700 text-xs" onClick={onAISuggestTags} title={aiError.tags}>Retry</button>
              )}
            </div>
            {aiError.tags && <p className="text-xs text-red-600">{aiError.tags}</p>}
          </div>
        </section>

        {/* Intro/Outro editing on Finalize */}
        <section className="lg:col-span-2 rounded-2xl border bg-card p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <h2 className="text-base font-semibold">Intro/Outro</h2>
              {(() => {
                const status = meta?.introoutro_status || (meta?.introoutro ? 'manual' : null);
                if (!status) return null;
                return (
                  <span className="text-xs font-medium text-green-600">{status === 'ai' ? 'AI Text Applied' : 'Completed'}</span>
                );
              })()}
            </div>
            <div className="flex items-center gap-2">
              <button
                className="px-2 py-1 rounded border text-xs disabled:opacity-50"
                disabled={ioSuggesting}
                onClick={async ()=>{
                  if (!showId || !fileId) { window.alert('Select an upload first.'); return; }
                  const currentMeta = meta;
                  const tplId = currentMeta?.template;
                  if (!tplId) { window.alert('Choose a template first (on Upload page).'); return; }
                  setIoLoading(true);
                  setShowIntroOutro(true);
                  try {
                    const res = await fetch(buildApiUrl(`/api/templates/${tplId}`), { headers: token ? { Authorization: `Bearer ${token}` } : {} });
                    if (res.ok) {
                      const tpl = await res.json();
                      setIoTemplate(tpl);
                      const overrides = currentMeta?.segment_overrides || {};
                      const seed = {};
                      (tpl.segments || []).forEach(s => {
                        if (s.segment_type==='intro' || s.segment_type==='outro'){
                          const existing = overrides[s.id] || {};
                          if (s?.source?.source_type === 'tts') {
                            seed[s.id] = { source: {
                              script: existing?.source?.script ?? '',
                              voice_id: existing?.source?.voice_id ?? null,
                              voice_name: existing?.source?.voice_name ?? undefined,
                            } };
                          } else if (s?.source?.source_type === 'ai_generated') {
                            seed[s.id] = { source: { prompt: existing?.source?.prompt ?? '' } };
                          } else if (s?.source?.source_type === 'static') {
                            seed[s.id] = { source: { filename: existing?.source?.filename ?? '' } };
                          }
                        }
                      });
                      setIoEdits(seed);
                    } else {
                      setIoTemplate(null);
                    }
                  } catch { setIoTemplate(null); }
                  finally { setIoLoading(false); }
                }}
              >Manual</button>
              <button
                className="px-2 py-1 rounded border text-xs disabled:opacity-50"
                disabled={ioSuggesting}
                onClick={async ()=>{
                  if (!showId || !fileId) { window.alert('Select an upload first.'); return; }
                  const currentMeta = meta;
                  const tplId = currentMeta?.template;
                  if (!tplId) { window.alert('Choose a template first (on Upload page).'); return; }
                  setIoSuggesting(true);
                  try {
                    const res = await fetch(buildApiUrl(`/api/templates/${tplId}`), { headers: token ? { Authorization: `Bearer ${token}` } : {} });
                    if (!res.ok) throw new Error('Template not found');
                    const tpl = await res.json();
                    const upload = uploadById[fileId];
                    const hint = (currentMeta?.hint || upload?.serverFilename || upload?.fileName || '').replace(/\.[a-z0-9]+$/i, '');
                    const overrides = currentMeta?.segment_overrides || {};
                    const next = { ...overrides };
                    const introSegs = (tpl.segments || []).filter(s=>s.segment_type==='intro');
                    const outroSegs = (tpl.segments || []).filter(s=>s.segment_type==='outro');
                    for (const s of (tpl.segments || [])){
                      if ((s.segment_type==='intro' || s.segment_type==='outro') && s?.source?.source_type==='tts'){
                        try {
                          const idx = (s.segment_type==='intro'
                            ? introSegs.findIndex(x=>x.id===s.id)
                            : outroSegs.findIndex(x=>x.id===s.id)) + 1;
                          const autoTag = s.segment_type==='intro' ? `Intro ${idx}` : `Outro ${idx}`;
                          const body = { episode_id: currentMeta?.episode_id || '00000000-0000-0000-0000-000000000000', podcast_id: showId, tag: autoTag, section_type: s.segment_type, hint, history_count: 10 };
                          const out = await abApi(token).suggestSection(body);
                          const script = (out?.script || '').trim();
                          if (script) next[s.id] = { source: { ...(next?.[s.id]?.source || {}), script } };
                        } catch (e) { console.warn('intro/outro suggest failed', e); }
                      }
                    }
                    setDraftMeta(showId, fileId, { segment_overrides: next, introoutro: true, introoutro_status: 'ai' });
                    window.alert('Intro/Outro suggestions applied');
                  } catch (e) {
                    window.alert(e?.message || String(e));
                  } finally { setIoSuggesting(false); }
                }}
              >AI suggest</button>
            </div>
          </div>
          <p className="text-xs text-muted-foreground">Manage your episode-specific intro/outro here.</p>
        </section>

        <section className="lg:col-span-2 rounded-2xl border bg-card p-4 space-y-3">
          <div className="font-medium">Intern review queue</div>
          <ul className="mt-2 space-y-3 text-sm">
            {[
              { t: 'Insert intro music', detail: 'at 00:00:13', text: 'Insert intro music' },
              { t: 'Add chapter', detail: 'Sponsor segment at 00:14:22', text: 'Add chapter: Sponsor' },
              { t: 'Note', detail: 'Redo question at 00:23:05', text: 'Note: redo that question' },
            ].map((a,i)=> (
              <li key={i} className="rounded-lg border p-3">
                <div className="flex items-center justify-between gap-2">
                  <div>
                    <div className="font-medium">{a.t}</div>
                    <div className="text-xs text-muted-foreground">{a.detail}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button className="px-2 py-1 rounded border text-xs">Undo</button>
                    <button className="px-2 py-1 rounded border text-xs">Approve</button>
                  </div>
                </div>
                <input defaultValue={a.text} className="mt-2 w-full rounded border px-2 py-1 text-sm" />
              </li>
            ))}
          </ul>
        </section>

        <section className="rounded-2xl border bg-card p-4 space-y-4">
          <h2 className="text-base font-semibold">Publish settings</h2>
          <div className="space-y-4 text-sm">
            <div>
              <label className="text-sm font-medium">Visibility</label>
              <div className="mt-2 flex items-center gap-6">
                <label className="flex items-center gap-2">
                  <input type="radio" name="visibility" value="draft" checked={visibility==='draft'} onChange={()=>setVisibility('draft')} /> Draft
                </label>
                <label className="flex items-center gap-2">
                  <input type="radio" name="visibility" value="publish" checked={visibility==='publish'} onChange={()=>setVisibility('publish')} /> Publish
                </label>
              </div>
            </div>
            <div className={visibility === 'draft' ? 'opacity-60 pointer-events-none' : ''}>
              <label className="text-sm font-medium">Schedule</label>
              <input type="datetime-local" className="mt-1 w-full rounded-lg border px-3 py-2" value={scheduleAt} onChange={(e)=>setScheduleAt(e.target.value)} />
            </div>
          </div>
          <button className="w-full rounded-xl bg-indigo-600 px-4 py-2 text-white shadow hover:bg-indigo-500 focus:outline-none focus-visible:ring" onClick={visibility==='publish' ? onPublish : onSave}>{visibility==='publish' ? 'Publish' : 'Save'}</button>
        </section>
      </div>
    </div>

    {showIntroOutro && (
      <div role="dialog" aria-modal="true" className="fixed inset-0 bg-black/40 grid place-items-center p-4 z-50">
        <div className="w-full max-w-3xl rounded-2xl bg-white p-5 space-y-4">
          <div className="flex items-center justify-between">
            <div className="text-base font-semibold">Finish Intro/Outro</div>
            <button className="px-2 py-1 text-sm rounded border" onClick={()=>setShowIntroOutro(false)}>Close</button>
          </div>
          {ioLoading && <div className="text-sm text-muted-foreground">Loading…</div>}
          {!ioLoading && !ioTemplate && (
            <div className="rounded border bg-amber-50 text-amber-800 p-3 text-sm">Template not available. Choose a template first.</div>
          )}
          {!ioLoading && ioTemplate && (
            <div className="space-y-4">
              <div className="text-sm text-muted-foreground">Customize only intro/outro segments for this episode. These edits won’t change the saved template.</div>
              <div className="space-y-3 max-h-[60vh] overflow-auto">
                {(ioTemplate.segments || []).filter(s=>s.segment_type==='intro' || s.segment_type==='outro').map((s, idx) => (
                  <div key={s.id} className="rounded-lg border p-3">
                    <div className="flex items-center justify-between">
                      <div className="font-medium">{s.segment_type === 'intro' ? 'Intro' : 'Outro'} {idx===0? '' : ''}</div>
                      <span className="text-xs px-2 py-0.5 rounded-full border bg-gray-50 text-gray-700 border-gray-200">{s?.source?.source_type || 'static'}</span>
                    </div>
                    {s?.source?.source_type === 'tts' && (
                      <label className="block text-sm mt-2">
                        AI voice script
                        <textarea className="mt-1 w-full rounded border p-2 min-h-28" value={ioEdits?.[s.id]?.source?.script || ''} onChange={(e)=>setIoEdits(prev=>({ ...prev, [s.id]: { source: { ...prev?.[s.id]?.source, script: e.target.value } } }))} />
                      </label>
                    )}
                    {s?.source?.source_type === 'tts' && (
                      <div className="mt-2 flex items-center justify-between">
                        <span className="text-xs text-gray-600">
                          {(() => {
                            const vid = ioEdits?.[s.id]?.source?.voice_id || s?.source?.voice_id || null;
                            const vname = ioEdits?.[s.id]?.source?.voice_name || s?.source?.voice_name || (vid ? voiceNameById[vid] : null);
                            const display = vname || vid || 'Default';
                            return <>
                              Voice: {display}
                              {voicesLoading && vid && !vname && !voiceNameById[vid] ? <span className="ml-2 text-[10px] text-gray-400">(resolving…)</span> : null}
                            </>;
                          })()}
                        </span>
                        <button className="text-xs px-2 py-1 border rounded" onClick={() => { setVoicePickerTargetId(s.id); setShowVoicePicker(true); }}>Change voice</button>
                      </div>
                    )}
                    {s?.source?.source_type === 'ai_generated' && (
                      <label className="block text-sm mt-2">
                        AI Prompt
                        <textarea className="mt-1 w-full rounded border p-2 min-h-24" value={ioEdits?.[s.id]?.source?.prompt || ''} onChange={(e)=>setIoEdits(prev=>({ ...prev, [s.id]: { source: { ...prev?.[s.id]?.source, prompt: e.target.value } } }))} />
                      </label>
                    )}
                    {!['tts','ai_generated'].includes(s?.source?.source_type) && (
                      <div className="mt-2 text-sm">
                        <div className="text-muted-foreground">Static segment file:</div>
                        <div className="mt-1 flex items-center gap-2">
                          <select className="border rounded px-2 py-1 text-sm" value={ioEdits?.[s.id]?.source?.filename || s?.source?.filename || ''} onChange={(e)=>setIoEdits(prev=>({ ...prev, [s.id]: { source: { ...prev?.[s.id]?.source, filename: e.target.value } } }))}>
                            <option value="">{s.segment_type === 'intro' ? 'Choose an intro file…' : 'Choose an outro file…'}</option>
                            {mediaFiles.filter(m => (s.segment_type === 'intro' ? (m.category === 'intro') : (m.category === 'outro'))).map(m => (
                              <option key={m.id} value={m.filename}>{formatDisplayName(m, { fallback: s.segment_type === 'intro' ? 'Intro' : 'Outro' }) || (s.segment_type === 'intro' ? 'Intro' : 'Outro')}</option>
                            ))}
                          </select>
                        </div>
                        {mediaFiles.filter(m => (s.segment_type === 'intro' ? (m.category === 'intro') : (m.category === 'outro'))).length === 0 && (
                          <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1 mt-2">No {s.segment_type} files in your library. Add them in Templates.</div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
              <div className="flex justify-end gap-2">
                <button className="px-3 py-1.5 rounded border" onClick={()=>setShowIntroOutro(false)}>Cancel</button>
                <button
                  className="px-3 py-1.5 rounded bg-indigo-600 text-white"
                  onClick={() => {
                    // Validate minimally like Upload page (lightweight for finalize)
                    const merged = { ...(meta?.segment_overrides || {}), ...ioEdits };
                    // Ensure voice_name present when we know it
                    for (const s of (ioTemplate.segments || [])) {
                      if (s?.source?.source_type === 'tts') {
                        const o = merged?.[s.id]?.source || {};
                        const vid = o.voice_id || s?.source?.voice_id || null;
                        const vname = o.voice_name || s?.source?.voice_name || (vid ? voiceNameById[vid] : undefined);
                        if (vid && vname && (!o.voice_name)) {
                          merged[s.id] = { source: { ...o, voice_name: vname } };
                        }
                      }
                    }
                    setDraftMeta(showId, fileId, { segment_overrides: merged, introoutro: true, introoutro_status: 'manual' });
                    // Persist a history section per AI voice segment when tagged
                    (async ()=>{
                      try {
                        if (showId){
                          const introSegs = (ioTemplate.segments||[]).filter(s=>s.segment_type==='intro');
                          const outroSegs = (ioTemplate.segments||[]).filter(s=>s.segment_type==='outro');
                          for (const s of (ioTemplate.segments||[])){
                            const ed = merged?.[s.id]?.source || {};
                            if (s?.source?.source_type==='tts' && (ed.script || s?.source?.script)){
                              const content = (ed.script || s?.source?.script || '').trim();
                              const idx = (s.segment_type==='intro'
                                ? introSegs.findIndex(x=>x.id===s.id)
                                : outroSegs.findIndex(x=>x.id===s.id)) + 1;
                              const autoTag = s.segment_type==='intro' ? `Intro ${idx}` : `Outro ${idx}`;
                              if (content){
                                await abApi(token).saveSection({ podcast_id: showId, episode_id: meta?.episode_id || null, tag: autoTag, section_type: s.segment_type, content, voice_id: ed.voice_id || s?.source?.voice_id || null, voice_name: ed.voice_name || s?.source?.voice_name || null });
                              }
                            }
                          }
                        }
                      } catch (e) { console.warn('saveSection failed', e); }
                    })();
                    setShowIntroOutro(false); // Stay on Finalize
                    window.alert('Intro/Outro saved to this draft');
                  }}
                >Save</button>
              </div>
            </div>
          )}
        </div>
      </div>
    )}

  {showVoicePicker && voicePickerTargetId && (
      <VoicePicker
        value={ioEdits?.[voicePickerTargetId]?.source?.voice_id || null}
        onChange={(voice_id)=>{
          setIoEdits(prev => ({ ...prev, [voicePickerTargetId]: { source: { ...prev?.[voicePickerTargetId]?.source, voice_id } } }));
        }}
        onSelect={(item)=>{
          if(!item) return;
          const friendly = item.common_name || item.name || 'Voice';
          setIoEdits(prev => ({ ...prev, [voicePickerTargetId]: { source: { ...prev?.[voicePickerTargetId]?.source, voice_id: item.voice_id, voice_name: friendly } } }));
        }}
    token={token}
        onClose={()=>{ setShowVoicePicker(false); setVoicePickerTargetId(null); }}
      />
    )}
    </>
  );
}

