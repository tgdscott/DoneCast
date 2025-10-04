
import React, { useMemo, useRef, useState, useEffect } from "react";
import { useAbDrafts } from "../store/useAbDrafts";
import { abApi } from "../lib/abApi";
import { makeApi, buildApiUrl } from "@/lib/apiClient.js";
import { uploadMediaDirect } from "@/lib/directUpload";
import { fetchVoices as fetchElevenVoices } from "@/api/elevenlabs";
import VoicePicker from "@/components/VoicePicker";

export default function CreatorUpload({ token, shows, uploads, setUploads, drafts, setDrafts, markUploadUsed, goFinalize, goCustomizeSegments }) {
  const [selectedShowId, setSelectedShowId] = useState(shows[0]?.id ?? "");
  const [selectedFileId, setSelectedFileId] = useState(uploads[0]?.id ?? null);
  const [tasks, setTasks] = useState([
    { key: 'title', label: 'Title', done: false },
    { key: 'description', label: 'Description', done: false },
    { key: 'tags', label: 'Tags', done: false },
    { key: 'template', label: 'Choose template', done: false },
  { key: 'introoutro', label: 'Finish intro/outro', done: false },
  ]);
  const fileInputRef = useRef(null);

  const { setDraftMeta, getDraftMeta, clearDraft } = useAbDrafts();
  const [templates, setTemplates] = useState([]);
  const [showTemplatePicker, setShowTemplatePicker] = useState(false);
  const [templatePick, setTemplatePick] = useState(null);
  const [showIntroOutro, setShowIntroOutro] = useState(false);
  const [ioLoading, setIoLoading] = useState(false);
  const [ioTemplate, setIoTemplate] = useState(null);
  const [ioEdits, setIoEdits] = useState({}); // { segmentId: { source: { script|prompt } } }
  // Tags are auto-named per segment order: Intro 1/2, Outro 1/2
  const [mediaFiles, setMediaFiles] = useState([]);
  const [showVoicePicker, setShowVoicePicker] = useState(false);
  const [voicePickerTargetId, setVoicePickerTargetId] = useState(null);
  const [ioSuggesting, setIoSuggesting] = useState(false);
  // Friendly voice-name resolution
  const [voiceNameById, setVoiceNameById] = useState({});
  const [voicesLoading, setVoicesLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  // Gate: only show AI Suggest when user has enough episode history for this show
  const [aiEligible, setAiEligible] = useState(false);
  const allTasksDone = useMemo(() => tasks.every(t => t.done), [tasks]);
  // Track transcript readiness for selected file from drafts store
  const selectedDraft = useMemo(() => {
    if (!selectedShowId || !selectedFileId) return null;
    return getDraftMeta(selectedShowId, selectedFileId);
  }, [selectedShowId, selectedFileId, getDraftMeta]);

  // Determine AI eligibility: require >= 5 processed/published episodes for the selected show
  useEffect(() => {
    let aborted = false;
    (async () => {
      try {
        if (!token || !selectedShowId) { setAiEligible(false); return; }
        try {
          const eps = await makeApi(token).get('/api/episodes');
          const list = Array.isArray(eps) ? eps : [];
          const count = list.filter(e => String(e?.podcast_id) === String(selectedShowId) && (e?.status === 'processed' || e?.status === 'published')).length;
          if (!aborted) setAiEligible(count >= 5);
          return;
        } catch {
          if (!aborted) setAiEligible(false);
          return;
        }
        
      } catch {
        if (!aborted) setAiEligible(false);
      }
    })();
    return () => { aborted = true; };
  }, [token, selectedShowId]);

  // Live validation for Intro/Outro modal
  const ioErrors = useMemo(() => {
    const tpl = ioTemplate;
    if (!tpl) return [];
    const segs = (tpl.segments || []).filter(s=>s.segment_type==='intro' || s.segment_type==='outro');
    const errs = [];
    for (const s of segs) {
      const edit = ioEdits?.[s.id]?.source || {};
      const base = s?.source || {};
      const type = base?.source_type || 'static';
      if (type === 'tts') {
        const script = (edit.script ?? base.script ?? '').trim();
        if (!script) errs.push(`${s.segment_type}: AI voice script is required`);
      } else if (type === 'ai_generated') {
        const prompt = (edit.prompt ?? base.prompt ?? '').trim();
        if (!prompt) errs.push(`${s.segment_type}: AI prompt is required`);
      } else {
        const filename = (edit.filename ?? base.filename ?? '').trim();
        if (!filename) {
          errs.push(`${s.segment_type}: choose a static file`);
        } else {
          const ok = mediaFiles.some(m => (s.segment_type==='intro'? m.category==='intro' : m.category==='outro') && m.filename===filename);
          if (!ok) errs.push(`${s.segment_type}: selected file not found in library`);
        }
      }
    }
    return errs;
  }, [ioTemplate, ioEdits, mediaFiles]);

  // Measure duration of a local File using an off-DOM audio element
  const getFileDurationSec = (file) => new Promise((resolve) => {
    try {
      const audio = new Audio();
      let url = null;
      const cleanup = () => { try { if (url) URL.revokeObjectURL(url); } catch {} };
      const onLoaded = () => { const d = audio && isFinite(audio.duration) ? audio.duration : null; cleanup(); resolve(d && d > 0 ? d : null); };
      const onError = () => { cleanup(); resolve(null); };
      audio.addEventListener('loadedmetadata', onLoaded);
      audio.addEventListener('error', onError);
      url = URL.createObjectURL(file);
      audio.src = url;
      audio.load();
    } catch {
      resolve(null);
    }
  });

  const middleEllipsis = (s, max = 60) => {
    if (!s) return "";
    if (s.length <= max) return s;
    const head = Math.ceil((max - 3) * 0.6);
    const tail = (max - 3) - head;
    return s.slice(0, head) + "..." + s.slice(-tail);
  };

  // Prime task "done" states when selected file changes
  useEffect(() => {
    if (!selectedShowId || !selectedFileId) return;
    const meta = getDraftMeta(selectedShowId, selectedFileId);
    setTasks(ts => ts.map(t => (t.key in meta && meta[t.key]) ? { ...t, done: true } : t));
  }, [selectedShowId, selectedFileId, getDraftMeta]);

  // Load templates once (or when token changes)
  useEffect(() => {
    let abort = false;
    (async () => {
      try {
        const list = await abApi(token).listTemplates();
        if (!abort) setTemplates(Array.isArray(list) ? list : []);
      } catch {
        if (!abort) setTemplates([]);
      }
    })();
    return () => { abort = true; };
  }, [token]);

  // If there's exactly one active template, auto-apply it for the current upload
  useEffect(() => {
    if (!selectedShowId || !selectedFileId) return;
    const active = (templates || []).filter(t => t?.is_active !== false);
    if (active.length !== 1) return;
    const meta = getDraftMeta(selectedShowId, selectedFileId);
    if (!meta || !meta.template) {
      applyTemplate(active[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templates, selectedShowId, selectedFileId]);

  // Load media library when Intro/Outro modal opens (for static segment selection)
  useEffect(() => {
    let cancel = false;
    (async () => {
      if (!showIntroOutro) return;
      try {
        const list = await abApi(token).listMedia();
        if (!cancel) setMediaFiles(Array.isArray(list) ? list : []);
      } catch {
        if (!cancel) setMediaFiles([]);
      }
  // No-op: section tags are now auto-named; no need to fetch existing tags
    })();
    return () => { cancel = true; };
  }, [showIntroOutro, token]);

  // Resolve friendly voice names when modal is open and a template is loaded
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!showIntroOutro || !ioTemplate) return;
      try {
        // Gather unique voice ids from template or edits
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
        // If we already know all, skip
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
            for (const v of (items || [])) {
              const dn = v.common_name || v.name || '';
              if (dn) map[v.voice_id] = dn;
            }
          } else {
            const res = await fetchElevenVoices('', 1, 200);
            for (const v of (res?.items || [])) {
              const dn = v.common_name || v.name || '';
              if (dn) map[v.voice_id] = dn;
            }
          }
        } catch {}
        if (!cancelled && Object.keys(map).length) setVoiceNameById(prev => ({ ...prev, ...map }));
        // Resolve unknowns via backend helper
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

  const transcriptEta = useMemo(() => {
    const f = uploads.find(u => u.id === selectedFileId);
    if (!f) return "≈ —";
    if (f && typeof f.durationSec === 'number' && isFinite(f.durationSec) && f.durationSec > 0) {
      const mins = f.durationSec / 60;
      const low = Math.max(1, Math.floor(mins * 0.75));
      const high = Math.max(Math.ceil(mins * 1.25), Math.ceil(mins + 2));
      return `≈ ${low}–${high} min`;
    }
    // Fallback when duration isn't known yet
    const name = (f.fileName || "").toLowerCase();
    if (name.endsWith('.wav') || name.endsWith('.aif') || name.endsWith('.aiff')) return "≈ 8–14 min";
    return "≈ 5–10 min";
  }, [uploads, selectedFileId]);

  const deleteFile = async (id) => {
    setUploads(prev => prev.filter(u => u.id !== id));
    setDrafts(prev => prev.filter(d => d.fileId !== id));
    clearDraft(selectedShowId, id);
    if (selectedFileId === id) setSelectedFileId(null);
    try { await abApi(token).deleteMedia(id); } catch {}
  };

  const refreshUploadsFromServer = async () => {
    if (!token) return;
    setRefreshing(true);
    try {
      const items = await abApi(token).listMedia();
      const filtered = (items || []).filter((it) => {
        const cat = (it?.category || '').toLowerCase();
        return cat === 'main_content' || cat === 'content' || cat === '' || cat === 'audio';
      });
      const mapped = filtered.map((it) => {
        const bytes = (typeof it?.filesize === 'number' ? it.filesize : it?.size);
        const sizeLabel = bytes ? `${Math.max(1, Math.round(bytes/1024/1024))} MB` : "";
        const clientName = it?.friendly_name || it?.client_name || it?.filename || "audio";
        return {
          id: it.id,
          fileName: clientName,
          serverFilename: it.filename,
          size: sizeLabel,
          status: 'done',
          progress: 100,
          nickname: '',
          showId: undefined,
          ttlDays: 14,
        };
      });

      // Merge uploads by id to avoid duplicates
      setUploads((prev) => {
        const byId = new Map(prev.map((u) => [u.id, u]));
        mapped.forEach((m) => {
          const existing = byId.get(m.id);
          if (!existing) byId.set(m.id, m);
          else byId.set(m.id, { ...existing, ...m });
        });
        return Array.from(byId.values());
      });

      // Seed drafts for any new uploads so transcript pills render
      setDrafts((prev) => {
        const have = new Set(prev.map((d) => d.fileId));
        const extras = mapped
          .filter((m) => !have.has(m.id))
          .map((m) => ({
            id: `d_${m.id}`,
            title: (m.fileName || '').replace(/\.[a-z0-9]+$/i, ''),
            fileId: m.id,
            transcript: 'processing',
            hint: (m.serverFilename || m.fileName || '').replace(/\.[a-z0-9]+$/i, ''),
          }));
        return extras.length ? prev.concat(extras) : prev;
      });
    } catch {
      // ignore
    } finally {
      setRefreshing(false);
    }
  };

  // Auto-refresh uploads when the page mounts so newly saved recordings appear without manual refresh
  useEffect(() => {
    if (token) {
      // Fire and forget; internal state manages loading flag
      refreshUploadsFromServer();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  // Poll transcript readiness for the currently selected file if not ready
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!token || !selectedDraft || selectedDraft.transcript === 'ready') return;
      const f = uploads.find(u => u.id === selectedFileId);
      const hint = (selectedDraft.hint || f?.serverFilename || f?.fileName || '').replace(/\.[a-z0-9]+$/i, '');
      if (!hint) return;
      const poll = async () => {
        try {
          const res = await abApi(token).transcriptReady({ hint });
          if (cancelled) return;
          if (res && res.ready) {
            setDraftMeta(selectedShowId, selectedFileId, { transcript: 'ready' });
            return; // stop
          }
        } catch {}
        if (!cancelled) setTimeout(poll, 5000);
      };
      setTimeout(poll, 2000);
    })();
    return () => { cancelled = true; };
  }, [token, selectedDraft?.transcript, selectedDraft?.hint, selectedFileId, selectedShowId, uploads, setDraftMeta]);

  const onBrowse = () => fileInputRef.current?.click();
  const onFilesPicked = async (e) => {
    const files = Array.from(e.target.files || []);
    if (!files.length) return;

    const uploadOne = (file, idx) => new Promise((resolve) => {
      const tempId = `tmp_${Date.now()}_${idx}`;
      const sizeLabel = file.size ? `${Math.max(1, Math.round(file.size/1024/1024))} MB` : "";
      let serverId = null;
      let measuredDuration = null;
      // Show immediately with a blue progress bar
      setUploads(prev => ([
        ...prev,
        {
          id: tempId,
          fileName: file.name,
          serverFilename: undefined,
          size: sizeLabel,
          status: 'uploading',
          progress: 1,
          nickname: '',
          showId: selectedShowId,
          ttlDays: 14,
          durationSec: null,
        }
      ]));

      // In parallel, derive audio duration and attach to the temp (and later server) item
      getFileDurationSec(file).then((sec) => {
        measuredDuration = sec;
        setUploads(prev => prev.map(u => (u.id === tempId || (serverId && u.id === serverId)) ? { ...u, durationSec: sec } : u));
      });

      uploadMediaDirect({
        category: 'main_content',
        file,
        friendlyName: file.name,
        token,
        onProgress: ({ percent }) => {
          if (typeof percent !== 'number') return;
          const pct = Math.max(1, Math.min(99, Math.round(percent)));
          setUploads(prev => prev.map(u => (u.id === tempId ? { ...u, progress: pct } : u)));
        },
      }).then((items) => {
        const si = Array.isArray(items) ? items[0] : items;
        if (si && si.id) {
          serverId = si.id;
          setUploads(prev => prev.map(u => (u.id === tempId ? {
            id: si.id,
            fileName: file.name,
            serverFilename: si.filename,
            size: sizeLabel,
            status: 'done',
            progress: 100,
            nickname: '',
            showId: selectedShowId,
            ttlDays: 14,
            durationSec: measuredDuration ?? u.durationSec ?? null,
          } : u)));

          const newDraft = {
            id: `d_${si.id}`,
            title: (si.friendly_name || si.filename || file.name).replace(/\.[a-z0-9]+$/i, ''),
            fileId: si.id,
            transcript: 'processing',
            hint: (si.filename || file.name).replace(/\.[a-z0-9]+$/i, ''),
          };
          setDrafts(prev => prev.concat([newDraft]));
          resolve(newDraft);
          return;
        }
        setUploads(prev => prev.map(u => (u.id === tempId ? { ...u, status: 'error', progress: 0 } : u)));
        resolve(null);
      }).catch((err) => {
        console.error(err);
        setUploads(prev => prev.map(u => (u.id === tempId ? { ...u, status: 'error', progress: 0, error: err?.message || 'Upload failed' } : u)));
        resolve(null);
      });
    });

    // Sequential uploads to keep UI/order predictable
    const createdDrafts = [];
    for (let i = 0; i < files.length; i++) {
      // eslint-disable-next-line no-await-in-loop
      const d = await uploadOne(files[i], i);
      if (d) createdDrafts.push(d);
    }

    // Select the first completed upload if available
    if (createdDrafts[0]?.fileId) setSelectedFileId(createdDrafts[0].fileId);
    e.target.value = ""; // reset

    // Start a light polling loop for transcript readiness for the first new draft
    const primary = createdDrafts[0];
    if (primary && primary.hint) {
      let cancelled = false;
      const poll = async () => {
        try {
          const res = await abApi(token).transcriptReady({ hint: primary.hint });
          if (cancelled) return;
          if (res && res.ready) {
            setDrafts(prev => prev.map(d => d.id === primary.id ? { ...d, transcript: "ready" } : d));
            return; // stop polling on ready
          }
        } catch {}
        if (!cancelled) setTimeout(poll, 5000);
      };
      setTimeout(poll, 5000);
    }
  };

  // Manual modal
  const [editing, setEditing] = useState(null); // { key, value }
  const openManual = (key) => {
    if (!selectedFileId) return;
    const meta = getDraftMeta(selectedShowId, selectedFileId);
    setEditing({ key, value: meta[key] || "" });
  };
  const saveManual = () => {
    if (!editing) return;
    const val = (editing.value || "").trim();
    setDraftMeta(selectedShowId, selectedFileId, { [editing.key]: val });
    setTasks(ts => ts.map(t => t.key===editing.key ? { ...t, done: !!val } : t));
    setEditing(null);
  };

  const runAiSuggest = async (key) => {
    const f = uploads.find(u => u.id === selectedFileId);
    const res = await abApi(token).aiMetadata({ current_title: "", filename: f?.fileName });
    const patch = key === "title" ? { title: res.title } : key === "description" ? { description: res.description } : { tags: (res.tags||[]).join(", ") };
    setDraftMeta(selectedShowId, selectedFileId, patch);
    setTasks(ts => ts.map(t => t.key===key ? { ...t, done: true } : t));
  };

  // Template choosing flow
  const applyTemplate = (tpl) => {
    if (!selectedShowId || !selectedFileId) return;
    setDraftMeta(selectedShowId, selectedFileId, { template: tpl?.id || tpl, template_name: tpl?.name || undefined });
    setTasks(ts => ts.map(t => t.key==='template' ? { ...t, done: true } : t));
    setShowTemplatePicker(false);
    setTemplatePick(null);
  };

  const openTemplateChooser = () => {
    const active = (templates || []).filter(t => t?.is_active !== false);
    if (!active.length) {
      window.alert('No active templates. Create or enable one in Templates.');
      return;
    }
    if (active.length === 1) {
      applyTemplate(active[0]);
      return;
    }
    setTemplatePick(active[0]?.id || null);
    setShowTemplatePicker(true);
  };

  return (
    <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      <input ref={fileInputRef} type="file" multiple accept="audio/*" className="hidden" onChange={onFilesPicked} />

      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">Upload your audio</h1>
          <p className="text-sm text-muted-foreground">Drop files here. We’ll handle the rest in the background.</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="hidden sm:flex items-center gap-2">
            <label className="text-sm text-muted-foreground">Podcast</label>
            <select className="rounded-lg border px-2 py-1 text-sm" value={selectedShowId} onChange={(e)=>setSelectedShowId(e.target.value)}>
              {shows.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </div>
          {/* Finalize button moved to bottom-right of the next section */}
        </div>
      </div>

      <div className="rounded-2xl border border-dashed bg-card p-6 text-center">
        <div className="text-sm text-muted-foreground">Drag & drop or <button className="underline" onClick={onBrowse}>browse</button></div>
      </div>

      <section className="rounded-2xl border bg-card p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold">Uploads</h2>
          <button
            className="px-2 py-1 rounded border text-xs disabled:opacity-50"
            disabled={refreshing || !token}
            title={!token ? 'Sign in to refresh from server' : 'Refresh uploads from server'}
            onClick={refreshUploadsFromServer}
          >{refreshing ? 'Refreshing…' : 'Refresh'}</button>
        </div>
        <ul className="space-y-2">
          {uploads.map((f)=> (
            <li key={f.id} className="rounded-lg border p-3">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <input type="radio" name="primaryFile" checked={selectedFileId===f.id} onChange={()=>setSelectedFileId(f.id)} title="Use this file for processing & estimates" />
                  <div className="min-w-0">
                    <div className="truncate" title={f.fileName}>
                      {f.nickname ? (
                        <>
                          <span className="font-semibold">{middleEllipsis(f.nickname, 50)}</span>{' '}
                          <span className="italic text-muted-foreground">({middleEllipsis(f.fileName, 50)})</span>
                        </>
                      ) : (
                        <span className="font-medium">{middleEllipsis(f.fileName, 60)}</span>
                      )}
                    </div>
                    <div className="text-xs text-muted-foreground">{f.size}</div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  {/* Transcript status pill */}
                  <span className={`text-xs px-2 py-1 rounded-full border ${(() => {
                    const d = drafts.find(d => d.fileId === f.id);
                    const state = d?.transcript || 'processing';
                    if (state === 'ready') return 'bg-green-50 text-green-700 border-green-200';
                    return 'bg-amber-50 text-amber-700 border-amber-200';
                  })()}`}>
                    {(() => {
                      const d = drafts.find(d => d.fileId === f.id);
                      return (d?.transcript === 'ready') ? 'Transcription Complete' : 'Transcription Pending';
                    })()}
                  </span>
                  <div className="text-sm">
                    {f.status === 'uploading' && <span>{f.progress}%</span>}
                    {f.status === 'queued' && <span>Queued</span>}
                    {f.status === 'done' && <span className="text-green-700">Uploaded</span>}
                  </div>
                </div>
                <button
                  className="px-2 py-1 rounded border text-xs"
                  onClick={()=>{
                    const ok = window.confirm('Delete this upload? This cannot be undone.');
                    if(ok) deleteFile(f.id);
                  }}
                >Delete</button>
              </div>
              {f.status === 'uploading' && (
                <div className="mt-2 h-2 rounded bg-muted">
                  <div className="h-2 rounded bg-indigo-600" style={{ width: f.progress + '%' }} />
                </div>
              )}
              <div className="mt-2 grid sm:grid-cols-2 gap-2">
                <label className="text-xs">
                  Common name (optional)
                  <input className="mt-1 w-full rounded border px-2 py-1 text-sm" value={f.nickname} onChange={(e)=>setUploads(arr => arr.map(x => x.id===f.id ? { ...x, nickname: e.target.value } : x))} />
                </label>
                <div className="text-xs text-muted-foreground flex items-end justify-end">Expires in {f.ttlDays ?? 14} days</div>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <section className="rounded-2xl border bg-card p-4">
          <h2 className="text-base font-semibold">Transcript</h2>
          <div className="mt-2 text-sm">
            {selectedDraft?.transcript === 'ready' ? (
              <div className="rounded-lg border px-3 py-2 bg-green-50 text-green-800 flex items-center justify-between">
                <span>Transcription Complete</span>
                <span className="text-xs">Ready</span>
              </div>
            ) : (
              <div className="rounded-lg border px-3 py-2 bg-amber-50 text-amber-800 flex items-center justify-between">
                <span>Processing</span>
                <span className="text-xs">{transcriptEta}</span>
              </div>
            )}
            <p className="mt-2 text-xs text-muted-foreground">You can keep working while we transcribe.</p>
            {/* Removed extraneous View steps and early Finalize buttons */}
          </div>
        </section>

  <section className="lg:col-span-2 rounded-2xl border bg-card p-4">
          <h2 className="text-base font-semibold">While we work, you can...</h2>
          <ul className="mt-2 grid sm:grid-cols-2 gap-3 text-sm">
            {tasks.map((t)=> (
              <li key={t.key} className={"rounded-lg border px-3 py-2 flex items-center justify-between gap-2 " + (t.done ? 'bg-green-50 border-green-200' : '')}>
                <span className="truncate flex items-center gap-2">{t.done && <span className="inline-block w-4 h-4 rounded-full bg-green-500 shrink-0"/>}{t.label}</span>
                <div className="shrink-0 flex items-center gap-2">
                  {t.key!=='template' && t.key!=='introoutro' && (
                    <>
                      <button className="px-2 py-1 rounded border text-xs" onClick={()=>openManual(t.key)}>Manual</button>
                      <button className="px-2 py-1 rounded border text-xs" onClick={()=>runAiSuggest(t.key)}>AI suggest</button>
                    </>
                  )}
                  {t.key==='template' && (
                    <button className="px-2 py-1 rounded border text-xs" onClick={openTemplateChooser}>Choose</button>
                  )}
                  {t.key==='introoutro' && (
                    <>
                      <button
                        className="px-2 py-1 rounded border text-xs disabled:opacity-50"
                        disabled={ioSuggesting}
                        onClick={async ()=>{
                          // Manual: open in-place builder modal
                          if (!selectedShowId || !selectedFileId) { window.alert('Select an upload first.'); return; }
                          const meta = getDraftMeta(selectedShowId, selectedFileId);
                          const tplId = meta?.template;
                          if (!tplId) { window.alert('Choose a template first.'); return; }
                          setIoLoading(true);
                          setShowIntroOutro(true);
                          try {
                            const res = await fetch(buildApiUrl(`/api/templates/${tplId}`), { headers: token ? { Authorization: `Bearer ${token}` } : {} });
                            if (res.ok) {
                              const tpl = await res.json();
                              setIoTemplate(tpl);
                              // Prefill from existing overrides if any
                              const overrides = meta?.segment_overrides || {};
                              const seed = {};
                              (tpl.segments || []).forEach(s => {
                                if (s.segment_type === 'intro' || s.segment_type === 'outro') {
                                  const existing = overrides[s.id] || {};
                                  if (s?.source?.source_type === 'tts') {
                                    seed[s.id] = { source: {
                                      script: existing?.source?.script ?? s?.source?.script ?? '',
                                      voice_id: existing?.source?.voice_id ?? s?.source?.voice_id ?? null,
                                      voice_name: existing?.source?.voice_name ?? s?.source?.voice_name ?? undefined,
                                    } };
                                  } else if (s?.source?.source_type === 'ai_generated') {
                                    seed[s.id] = { source: { prompt: existing?.source?.prompt ?? s?.source?.prompt ?? '' } };
                                  } else if (s?.source?.source_type === 'static') {
                                    seed[s.id] = { source: { filename: existing?.source?.filename ?? s?.source?.filename ?? '' } };
                                  }
                                }
                              });
                              setIoEdits(seed);
                            } else {
                              setIoTemplate(null);
                            }
                          } catch {
                            setIoTemplate(null);
                          } finally {
                            setIoLoading(false);
                          }
                        }}
                      >Manual</button>
                      {aiEligible && (
                        <button
                          className="px-2 py-1 rounded border text-xs disabled:opacity-50"
                          disabled={ioSuggesting}
                          onClick={async ()=>{
                          // AI suggest: generate scripts for AI voice intro/outro without opening the modal
                          if (!selectedShowId || !selectedFileId) { window.alert('Select an upload first.'); return; }
                          const meta = getDraftMeta(selectedShowId, selectedFileId);
                          const tplId = meta?.template;
                          if (!tplId) { window.alert('Choose a template first.'); return; }
                          setIoSuggesting(true);
                          try {
                            // Fetch template
                            const res = await fetch(buildApiUrl(`/api/templates/${tplId}`), { headers: token ? { Authorization: `Bearer ${token}` } : {} });
                            if (!res.ok) throw new Error('Template not found');
                            const tpl = await res.json();
                            // Hint filename
                            const f = uploads.find(u=>u.id===selectedFileId);
                            const hint = (meta?.hint || f?.serverFilename || f?.fileName || '').replace(/\.[a-z0-9]+$/i, '');
                            // Start from existing overrides
                            const overrides = meta?.segment_overrides || {};
                            const next = { ...overrides };
                            // Prepare ordered lists for auto tags per type
                            const introSegs = (tpl.segments || []).filter(s=>s.segment_type==='intro');
                            const outroSegs = (tpl.segments || []).filter(s=>s.segment_type==='outro');
                            for (const s of (tpl.segments || [])){
                              if ((s.segment_type==='intro' || s.segment_type==='outro') && s?.source?.source_type==='tts'){
                                try {
                                  const idx = (s.segment_type==='intro'
                                    ? introSegs.findIndex(x=>x.id===s.id)
                                    : outroSegs.findIndex(x=>x.id===s.id)) + 1;
                                  const autoTag = s.segment_type==='intro' ? `Intro ${idx}` : `Outro ${idx}`;
                                  const body = {
                                    episode_id: meta?.episode_id || '00000000-0000-0000-0000-000000000000',
                                    podcast_id: selectedShowId,
                                    tag: autoTag,
                                    section_type: s.segment_type,
                                    hint,
                                    history_count: 10,
                                  };
                                  const out = await abApi(token).suggestSection(body);
                                  const script = (out?.script || '').trim();
                                  if (script) {
                                    next[s.id] = { source: { ...(next?.[s.id]?.source || {}), script } };
                                  }
                                } catch (e) {
                                  console.warn('intro/outro suggest failed', e);
                                }
                              }
                            }
                            // Persist overrides and mark task done
                            setDraftMeta(selectedShowId, selectedFileId, { segment_overrides: next, introoutro: true });
                            setTasks(ts => ts.map(x=>x.key==='introoutro'?{...x,done:true}:x));
                          } catch (e) {
                            window.alert(e?.message || String(e));
                          } finally {
                            setIoSuggesting(false);
                          }
                          }}
                        >AI suggest</button>
                      )}
                    </>
                  )}
                </div>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex items-center justify-end">
            <button
              className={`px-4 py-2 rounded-lg ${allTasksDone ? 'bg-indigo-600 text-white hover:bg-indigo-700 border border-indigo-600' : 'bg-gray-200 text-gray-500 border border-gray-300 cursor-not-allowed'}`}
              disabled={!allTasksDone}
              onClick={goFinalize}
              title={allTasksDone ? 'Proceed to Finalize' : 'Complete the items above to enable'}
            >
              Go to Finalize
            </button>
          </div>
        </section>
      </div>

      {showTemplatePicker && (
        <div role="dialog" aria-modal="true" className="fixed inset-0 bg-black/40 grid place-items-center p-4 z-50">
          <div className="w-full max-w-2xl rounded-2xl bg-white p-5 space-y-4">
            <div className="flex items-center justify-between">
              <div className="text-base font-semibold">Choose a template</div>
              <button className="px-2 py-1 text-sm rounded border" onClick={()=>setShowTemplatePicker(false)}>Close</button>
            </div>
            <div className="max-h-[60vh] overflow-auto divide-y border rounded">
              {(templates || []).filter(t=>t?.is_active !== false).map(t => (
                <label key={t.id} className="flex items-center gap-3 p-3 cursor-pointer hover:bg-gray-50">
                  <input
                    type="radio"
                    name="tpl"
                    checked={templatePick===t.id}
                    onChange={()=>setTemplatePick(t.id)}
                  />
                  <div className="min-w-0">
                    <div className="font-medium truncate">{t.name}</div>
                    {t.podcast_id && <div className="text-xs text-muted-foreground">Show-linked</div>}
                  </div>
                  <span className={`ml-auto text-xs px-2 py-0.5 rounded-full border ${t?.is_active !== false ? 'bg-green-50 text-green-700 border-green-200' : 'bg-gray-100 text-gray-700 border-gray-300'}`}>{t?.is_active !== false ? 'Active' : 'Inactive'}</span>
                </label>
              ))}
            </div>
            <div className="flex justify-end gap-2">
              <button className="px-3 py-1.5 rounded border" onClick={()=>setShowTemplatePicker(false)}>Cancel</button>
              <button
                className="px-3 py-1.5 rounded bg-indigo-600 text-white disabled:opacity-50"
                disabled={!templatePick}
                onClick={()=>{
                  const tpl = (templates || []).find(tt=>tt.id===templatePick);
                  if (tpl) applyTemplate(tpl);
                }}
              >Use template</button>
            </div>
          </div>
        </div>
      )}

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
                <div className="text-sm text-muted-foreground">Customize only intro/outro segments for this episode. These edits won't change the saved template. Required: AI voice needs a script; AI text needs a prompt; static needs a selected file.</div>
                <div className="flex items-end justify-end gap-2">
                  <button
                    className="px-2 py-1 text-xs border rounded"
                    onClick={async ()=>{
                      // Suggest scripts for all AI voice intro/outro segments with auto tags
                      const f = uploads.find(u=>u.id===selectedFileId);
                      const meta = getDraftMeta(selectedShowId, selectedFileId);
                      const tpl = ioTemplate;
                      const introSegs = (tpl?.segments||[]).filter(s=>s.segment_type==='intro');
                      const outroSegs = (tpl?.segments||[]).filter(s=>s.segment_type==='outro');
                      for (const s of (tpl?.segments||[])){
                        if (s.segment_type==='intro' || s.segment_type==='outro'){
                          const srcType = s?.source?.source_type || 'static';
                          if (srcType==='tts'){
                            try {
                              const idx = (s.segment_type==='intro'
                                ? introSegs.findIndex(x=>x.id===s.id)
                                : outroSegs.findIndex(x=>x.id===s.id)) + 1;
                              const autoTag = s.segment_type==='intro' ? `Intro ${idx}` : `Outro ${idx}`;
                              const body = {
                                episode_id: meta?.episode_id || '00000000-0000-0000-0000-000000000000',
                                podcast_id: selectedShowId,
                                tag: autoTag,
                                section_type: s.segment_type,
                                hint: (meta?.hint || f?.serverFilename || f?.fileName || '').replace(/\.[a-z0-9]+$/i, ''),
                                history_count: 10,
                              };
                              const out = await abApi(token).suggestSection(body);
                              const script = (out?.script || '').trim();
                              if (script){
                                setIoEdits(prev=> ({...prev, [s.id]: { source: { ...prev?.[s.id]?.source, script } }}));
                              }
                            } catch (e) {
                              console.warn('section suggest failed', e);
                            }
                          }
                        }
                      }
                    }}
                  >AI suggest scripts</button>
                </div>
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
                          <textarea
                            className="mt-1 w-full rounded border p-2 min-h-28"
                            value={ioEdits?.[s.id]?.source?.script || ''}
                            onChange={(e)=>setIoEdits(prev=>({ ...prev, [s.id]: { source: { ...prev?.[s.id]?.source, script: e.target.value } } }))}
                          />
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
                          <button
                            className="text-xs px-2 py-1 border rounded"
                            onClick={() => { setVoicePickerTargetId(s.id); setShowVoicePicker(true); }}
                          >Change voice</button>
                        </div>
                      )}
                      {s?.source?.source_type === 'ai_generated' && (
                        <label className="block text-sm mt-2">
                          AI Prompt
                          <textarea
                            className="mt-1 w-full rounded border p-2 min-h-24"
                            value={ioEdits?.[s.id]?.source?.prompt || ''}
                            onChange={(e)=>setIoEdits(prev=>({ ...prev, [s.id]: { source: { ...prev?.[s.id]?.source, prompt: e.target.value } } }))}
                          />
                        </label>
                      )}
                      {!['tts','ai_generated'].includes(s?.source?.source_type) && (
                        <div className="mt-2 text-sm">
                          <div className="text-muted-foreground">Static segment file:</div>
                          <div className="mt-1 flex items-center gap-2">
                            <select
                              className="border rounded px-2 py-1 text-sm"
                              value={ioEdits?.[s.id]?.source?.filename || s?.source?.filename || ''}
                              onChange={(e)=>setIoEdits(prev=>({ ...prev, [s.id]: { source: { ...prev?.[s.id]?.source, filename: e.target.value } } }))}
                            >
                              <option value="">{s.segment_type === 'intro' ? 'Choose an intro file…' : 'Choose an outro file…'}</option>
                              {mediaFiles
                                .filter(m => (s.segment_type === 'intro' ? (m.category === 'intro') : (m.category === 'outro')))
                                .map(m => (
                                  <option key={m.id} value={m.filename}>
                                    {m.friendly_name || m.filename}
                                  </option>
                                ))}
                            </select>
                            <span className="text-xs text-gray-500">Current: {s?.source?.filename || '—'}</span>
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
          className="px-3 py-1.5 rounded bg-indigo-600 text-white disabled:opacity-50"
          disabled={ioErrors.length > 0}
                    onClick={()=>{
                      // Basic validation before saving
                      const tpl = ioTemplate;
                      const segs = (tpl?.segments || []).filter(s=>s.segment_type==='intro' || s.segment_type==='outro');
                      const errors = [];
                      for (const s of segs) {
                        const edit = ioEdits?.[s.id]?.source || {};
                        const base = s?.source || {};
                        const type = base?.source_type || 'static';
                        if (type === 'tts') {
                          const script = (edit.script ?? base.script ?? '').trim();
                          if (!script) errors.push(`${s.segment_type}: AI voice script is required`);
                        } else if (type === 'ai_generated') {
                          const prompt = (edit.prompt ?? base.prompt ?? '').trim();
                          if (!prompt) errors.push(`${s.segment_type}: AI prompt is required`);
                        } else {
                          const filename = (edit.filename ?? base.filename ?? '').trim();
                          if (!filename) {
                            errors.push(`${s.segment_type}: choose a static file`);
                          } else {
                            const ok = mediaFiles.some(m => (s.segment_type==='intro'? m.category==='intro' : m.category==='outro') && m.filename===filename);
                            if (!ok) errors.push(`${s.segment_type}: selected file not found in library`);
                          }
                        }
                      }
                      if (errors.length) {
            // Keep non-blocking UX; button already disabled when invalid.
            // As a safeguard, still notify if clicked via keyboard when invalid.
            window.alert(`Please fix before saving:\n- ${errors.join('\n- ')}`);
                        return;
                      }
                      // Save overrides and mark task done
                      const meta = getDraftMeta(selectedShowId, selectedFileId);
                      // Ensure friendly voice_name is populated when possible
                      const tempMerged = { ...(meta?.segment_overrides || {}), ...ioEdits };
                      const merged = { ...tempMerged };
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
                      setDraftMeta(selectedShowId, selectedFileId, { segment_overrides: merged, introoutro: true });
                      // Persist sections (one row per intro/outro AI voice) with tag to backend for history
                      (async ()=>{
                        try {
                          if (selectedShowId){
                            const introSegs = (ioTemplate.segments||[]).filter(s=>s.segment_type==='intro');
                            const outroSegs = (ioTemplate.segments||[]).filter(s=>s.segment_type==='outro');
                            for (const s of (ioTemplate.segments||[])){
                              const ed = merged?.[s.id]?.source || {};
                              if (s?.source?.source_type==='tts' && (ed.script || s?.source?.script)){
                                const voice_id = ed.voice_id || s?.source?.voice_id || null;
                                const voice_name = ed.voice_name || s?.source?.voice_name || null;
                                const content = (ed.script || s?.source?.script || '').trim();
                                const idx = (s.segment_type==='intro'
                                  ? introSegs.findIndex(x=>x.id===s.id)
                                  : outroSegs.findIndex(x=>x.id===s.id)) + 1;
                                const autoTag = s.segment_type==='intro' ? `Intro ${idx}` : `Outro ${idx}`;
                                if (content){
                                  await abApi(token).saveSection({
                                    podcast_id: selectedShowId,
                                    episode_id: meta?.episode_id || null,
                                    tag: autoTag,
                                    section_type: s.segment_type,
                                    content,
                                    voice_id,
                                    voice_name,
                                  });
                                }
                              }
                            }
                          }
                        } catch (e) { console.warn('saveSection failed', e); }
                      })();
                      setTasks(ts => ts.map(x=>x.key==='introoutro'?{...x,done:true}:x));
                      setShowIntroOutro(false);
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
            setIoEdits(prev => ({
              ...prev,
              [voicePickerTargetId]: { source: { ...prev?.[voicePickerTargetId]?.source, voice_id } }
            }));
          }}
          onSelect={(item)=>{
            if(!item) return;
            const friendly = item.common_name || item.name || 'Voice';
            setIoEdits(prev => ({
              ...prev,
              [voicePickerTargetId]: { source: { ...prev?.[voicePickerTargetId]?.source, voice_id: item.voice_id, voice_name: friendly } }
            }));
          }}
      token={token}
          onClose={()=>{ setShowVoicePicker(false); setVoicePickerTargetId(null); }}
        />
      )}

      {editing && (
        <div role="dialog" className="fixed inset-0 bg-black/40 grid place-items-center p-4 z-50">
          <div className="w-full max-w-lg rounded-2xl bg-white p-4 space-y-3">
            <div className="text-base font-semibold">Enter {editing.key}</div>
            {editing.key==='description'
              ? <textarea className="w-full rounded border p-2 min-h-40" value={editing.value} onChange={e=>setEditing({...editing, value:e.target.value})}/>
              : <input className="w-full rounded border p-2" value={editing.value} onChange={e=>setEditing({...editing, value:e.target.value})} />}
            {editing.key==='tags' && <div className="text-xs text-muted-foreground">Comma-separated (e.g., tips, interview)</div>}
            <div className="flex justify-end gap-2">
              <button className="px-3 py-1.5 rounded border" onClick={()=>setEditing(null)}>Cancel</button>
              <button className="px-3 py-1.5 rounded bg-indigo-600 text-white" onClick={saveManual}>Save</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}



