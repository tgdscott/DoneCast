import React, { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";
import { Button } from "../ui/button";
import { Badge } from "../ui/badge";
import { Loader2, RefreshCw, ImageOff, Play, CheckCircle2, Clock, AlertTriangle, CalendarClock, Trash2, ArrowLeft, LayoutGrid, List as ListIcon, Search, Undo2, Scissors, Grid3x3, Pencil, RotateCcw, FileText, Wand2 } from "lucide-react";
import EpisodeHistoryPreview from './EpisodeHistoryPreview';
import FlubberReview from './FlubberReview';
import ManualEditorModal from './ManualEditorModal';
import CoverCropper from './CoverCropper';
import { makeApi, isApiError, assetUrl } from "@/lib/apiClient.js";
import { useResolvedTimezone } from "@/hooks/useResolvedTimezone";
import { formatInTimezone } from "@/lib/timezone";
// ------------------------------
// Utility helpers (pure / outside component to avoid re-creation)
// ------------------------------
const statusLabel = (s) => String(s || '').toLowerCase();
const safeJsonParse = (text) => {
  try { return text ? JSON.parse(text) : {}; } catch { return {}; }
};
const ensureIsoZ = (iso) => {
  if(!iso) return iso;
  // If already has timezone info return as-is
  if(/[zZ]|[+\-]\d{2}:?\d{2}$/.test(iso)) return iso;
  // Accept space separator
  if(/\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(iso)) return iso.replace(' ', 'T')+'Z';
  // Basic naive pattern
  if(/\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}$/.test(iso)) return iso+'Z';
  return iso; // fallback (let Date attempt)
};
const normalizeDate = (iso) => {
  if(!iso) return null;
  const d = new Date(ensureIsoZ(iso));
  return isNaN(d.getTime()) ? null : d;
};
const episodeSortDate = (ep) => normalizeDate(ep.publish_at) || normalizeDate(ep.processed_at) || normalizeDate(ep.created_at) || new Date(0);
const resolveAssetUrl = (path) => {
  if (!path || typeof path !== 'string') return path;
  const trimmed = path.trim();
  if (!trimmed) return trimmed;
  if (/^[a-z][a-z0-9+.-]*:/i.test(trimmed) || trimmed.startsWith('//')) return trimmed;
  return assetUrl(trimmed);
};
const isWithin24h = (iso) => {
  const d = normalizeDate(iso);
  if(!d) return false;
  return (Date.now() - d.getTime()) < 24*3600*1000;
};
const isWithin7Days = (iso) => {
  const d = normalizeDate(iso);
  if(!d) return false;
  const elapsed = Date.now() - d.getTime();
  return elapsed >= 0 && elapsed < 7*24*3600*1000;
};
const formatPublishAt = (iso, { fallback = null, timezone } = {}) => {
  if(!iso) return fallback ?? '';
  try {
    const d = normalizeDate(iso);
    if(!d) return fallback ?? iso;
    const datePart = formatInTimezone(d, { year:'numeric', month:'short', day:'numeric' }, timezone);
    const timePart = formatInTimezone(d, { hour:'numeric', minute:'2-digit', hour12:true, timeZoneName:'short' }, timezone);
    const now = Date.now();
    const diffMin = Math.round((d.getTime()-now)/60000);
    let rel='';
    if (Math.abs(diffMin) < 60*24*7) {
      if (diffMin>0) rel = diffMin<60?`in ${diffMin}m`: (diffMin<1440?`in ${Math.round(diffMin/60)}h`:`in ${Math.round(diffMin/60/24)}d`);
      else if (diffMin<0){ const m=Math.abs(diffMin); rel = m<60?`${m}m ago`:(m<1440?`${Math.round(m/60)}h ago`:`${Math.round(m/60/24)}d ago`); }
    }
    const label = [datePart, timePart].filter(Boolean).join(' ').trim();
    return label ? `${label}${rel ? " - " + rel : ""}` : (fallback ?? iso);
  } catch {
    return fallback ?? iso;
  }
};


const canScheduleEpisode = (episode) => {
  if (!episode) return false;
  if (episode._scheduling) return false;
  if (statusLabel(episode.status) !== 'processed') return false;
  return !!episode.final_audio_exists;
};

const scheduleTooltip = (episode) => {
  if (!episode) return 'Schedule unavailable';
  if (episode._scheduling) return 'Scheduling in progress';
  if (statusLabel(episode.status) !== 'processed') return 'Available after processing completes';
  if (!episode.final_audio_exists) return 'Final audio not ready yet';
  return 'Schedule future publication';
};

const deriveEpisodeHint = (episode) => {
  if (!episode) return null;
  const meta = safeJsonParse(episode.meta_json);
  const candidates = [
    episode.working_audio_name,
    meta?.working_audio_name,
    meta?.cleaned_filename,
    meta?.main_content_filename,
    episode.final_audio_path,
    meta?.uploaded_filename,
  ];
  for (const cand of candidates) {
    if (cand && typeof cand === 'string') return cand;
  }
  return null;
};

export default function EpisodeHistory({ token, onBack }) {
  // Core lists & fetch state
  const resolvedTimezone = useResolvedTimezone();
  const formatPublishAtForUser = useCallback(
    (iso, fallback) => formatPublishAt(iso, { fallback, timezone: resolvedTimezone }),
    [resolvedTimezone]
  );
  const [episodes, setEpisodes] = useState([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  // UI list controls
  const [viewMode, setViewMode] = useState('grid'); // 'grid' | 'mosaic' | 'list'
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [sortKey, setSortKey] = useState('newest');
  // Preview toggle removed; mosaic view is now permanent
  // Editing panel
  const [editing, setEditing] = useState(null);
  const [editValues, setEditValues] = useState({ title:'', description:'', publish_state:'', tags:'', is_explicit:false, image_crop:'', cover_file:null, cover_uploading:false, season_number:null, episode_number:null, template_id:null });
  const [saving, setSaving] = useState(false);
  const [templates, setTemplates] = useState([]);
  const [templatesLoading, setTemplatesLoading] = useState(false);
  const [aiBusy, setAiBusy] = useState({ title: false, description: false, tags: false });
  const [templatePrompt, setTemplatePrompt] = useState({ open: false, field: null, saving: false, savingId: null });
  // Add state for numbering duplicates near other edit state declarations
  const [numberingConflict, setNumberingConflict] = useState(false);
  const [hasGlobalNumberingConflict, setHasGlobalNumberingConflict] = useState(false);
  // Deletion & unpublish flows
  const [deletingIds, setDeletingIds] = useState(new Set());
  const [unpublishEp, setUnpublishEp] = useState(null);
  const [unpublishDoing, setUnpublishDoing] = useState(false);
  const [unpublishError, setUnpublishError] = useState("");
  const [unpublishCanForce, setUnpublishCanForce] = useState(false);
  const startEdit = (ep) => {
    setEditing(ep);
    setEditValues({
      title: ep.title || '',
      description: ep.description || '',
      publish_state: '',
      tags: (ep.tags||[]).join(', '),
      is_explicit: !!ep.is_explicit,
      image_crop: ep.image_crop || '',
      cover_file: null,
      cover_uploading:false,
      season_number: ep.season_number ?? null,
      episode_number: ep.episode_number ?? null,
      template_id: ep.template_id ?? null,
    });
    // Add reset conflict
    setNumberingConflict(false);
  };
  const closeEdit = () => { if(saving) return; setEditing(null); };
  const editDirty = () => editing && (
    editValues.title !== (editing.title||'') ||
    editValues.description !== (editing.description||'') ||
    (editValues.publish_state && editValues.publish_state.trim() !== '') ||
    editValues.tags !== (Array.isArray(editing.tags)?editing.tags.join(', '):'') ||
    editValues.is_explicit !== !!editing.is_explicit ||
    editValues.image_crop !== (editing.image_crop||'') ||
    !!editValues.cover_file ||
    (editValues.season_number !== (editing.season_number ?? null)) ||
    (editValues.episode_number !== (editing.episode_number ?? null)) ||
    ((editValues.template_id ?? null) !== (editing.template_id ?? null))
  );
  const cropperRef = useRef(null);
  const pendingAiFieldRef = useRef(null);
  // Scheduling modal state
  const [scheduleEp, setScheduleEp] = useState(null); // episode object
  const [scheduleDate, setScheduleDate] = useState(""); // YYYY-MM-DD
  const [scheduleTime, setScheduleTime] = useState(""); // HH:MM (24h)
  const [scheduleSubmitting, setScheduleSubmitting] = useState(false);
  const [scheduleError, setScheduleError] = useState("");
  // Flubber manual review state
  const [flubberEpId, setFlubberEpId] = useState(null);
  // Manual editor state
  const [manualEpId, setManualEpId] = useState(null);
  // Retry processing state
  const [retryingId, setRetryingId] = useState(null);
  const [retryError, setRetryError] = useState("");
  // Retry publish (republish) state
  const [republishingId, setRepublishingId] = useState(null);
  const [republishError, setRepublishError] = useState("");
  const doRetry = async (ep) => {
    if (!ep) return;
    setRetryError("");
    setRetryingId(ep.id);
    try {
      const api = makeApi(token);
      await api.post(`/api/episodes/${ep.id}/retry`, {});
      // Optimistic: mark as processing; refresh shortly
      setEpisodes(prev => prev.map(e => e.id===ep.id ? { ...e, status:'processing' } : e));
      setTimeout(fetchEpisodes, 1200);
    } catch (e) {
      const msg = isApiError(e) ? (e.detail || e.error || e.message) : String(e);
      setRetryError(msg || 'Retry failed');
    } finally {
      setRetryingId(null);
    }
  };
  // One-click publish (makes episode public immediately)
  const quickPublish = async (episodeId) => {
    if(!episodeId) return;
    setEpisodes(prev => prev.map(e => e.id===episodeId ? { ...e, _publishing:true } : e));
    try {
  const api = makeApi(token);
  await api.post(`/api/episodes/${episodeId}/publish`, { publish_state:'public' });
      // Do not optimistically flip to published; refresh shortly to reflect actual server state
      setEpisodes(prev => prev.map(e => e.id===episodeId ? { ...e, _publishing:false } : e));
      // Poll status briefly to surface errors promptly
      const start = Date.now();
      const poll = async () => {
        try {
          const st = await api.get(`/api/episodes/${episodeId}/publish/status`);
          if (st && (st.status === 'published' || st.spreaker_episode_id || st.last_error)) {
            await fetchEpisodes();
            if (st.last_error) alert(st.last_error);
            return;
          }
        } catch {}
        if (Date.now() - start < 4000) {
          setTimeout(poll, 600);
        } else {
          // final refresh
          try { await fetchEpisodes(); } catch {}
        }
      };
      setTimeout(poll, 600);
    } catch(err){
  const msg = isApiError(err) ? (err.detail || err.error || err.message) : String(err);
  alert(msg || 'Failed to publish');
      setEpisodes(prev => prev.map(e => e.id===episodeId ? { ...e, _publishing:false } : e));
    }
  };
  const openSchedule = (ep) => {
    if (!canScheduleEpisode(ep)) return;
    setScheduleEp(ep);
    setScheduleSubmitting(false);
    setScheduleError("");
    // Default date/time = now + 60 min rounded to next 5 min
    const now = new Date(Date.now() + 60*60000);
    const yyyy = now.getFullYear();
    const mm = String(now.getMonth()+1).padStart(2,'0');
    const dd = String(now.getDate()).padStart(2,'0');
    const mins = now.getMinutes();
    const rounded = Math.ceil(mins/5)*5;
    if(rounded >= 60){ now.setHours(now.getHours()+1); now.setMinutes(0); }
    const hh = String(now.getHours()).padStart(2,'0');
    const mi = String(rounded >= 60? 0 : rounded).padStart(2,'0');
    setScheduleDate(`${yyyy}-${mm}-${dd}`);
    setScheduleTime(`${hh}:${mi}`);
  };
  const doRepublish = async (ep) => {
    if (!ep) return;
    setRepublishError("");
    setRepublishingId(ep.id);
    try {
      const api = makeApi(token);
      await api.post(`/api/episodes/${ep.id}/republish`, {});
      setEpisodes(prev => prev.map(e => e.id===ep.id ? { ...e, _republishing: true } : e));
      setTimeout(fetchEpisodes, 1500);
    } catch (e) {
      const msg = isApiError(e) ? (e.detail || e.error || e.message) : String(e);
      setRepublishError(msg || 'Republish failed');
    } finally {
      setRepublishingId(null);
    }
  };
  // Recompute whether any duplicate (season, episode) exists across list
  const recomputeGlobalNumberingConflicts = useCallback((list) => {
    try {
      const seen = new Set();
      for (const e of list || []) {
        if (e && e.season_number != null && e.episode_number != null) {
          const key = `${e.podcast_id || 'pod'}:${e.season_number}:${e.episode_number}`;
          if (seen.has(key)) { setHasGlobalNumberingConflict(true); return; }
          seen.add(key);
        }
      }
      setHasGlobalNumberingConflict(false);
    } catch {
      setHasGlobalNumberingConflict(false);
    }
  }, []);
  const closeSchedule = () => { if(scheduleSubmitting) return; setScheduleEp(null); };
  const submitSchedule = async () => {
    if(!scheduleEp) return;
    setScheduleSubmitting(true);
    setScheduleError("");
    try {
      if(!scheduleDate || !scheduleTime){ throw new Error('Date & time required'); }
      const local = new Date(`${scheduleDate}T${scheduleTime}:00`);
      if(isNaN(local.getTime())) throw new Error('Invalid date/time');
      if(local.getTime() <= Date.now()+60*1000) throw new Error('Choose a time at least 1 minute in the future');
  // Build ISO (UTC) and trim milliseconds for backend leniency
  let iso = local.toISOString();
  iso = iso.replace(/\.\d{3}Z$/, 'Z');
      setEpisodes(prev => prev.map(e => e.id===scheduleEp.id ? { ...e, _scheduling:true } : e));
  const api = makeApi(token);
  await api.post(`/api/episodes/${scheduleEp.id}/publish`, { publish_state:'public', publish_at: iso, publish_at_local: `${scheduleDate} ${scheduleTime}` });
      setEpisodes(prev => prev.map(e => e.id===scheduleEp.id ? { ...e, status:'scheduled', publish_at: iso, publish_at_local: `${scheduleDate} ${scheduleTime}`, _scheduling:false } : e));
      setScheduleEp(null);
    } catch(e){
  const msg = isApiError(e) ? (e.detail || e.error || e.message) : String(e);
  setScheduleError(msg || 'Failed to schedule');
      setEpisodes(prev => prev.map(p => p.id===scheduleEp.id ? { ...p, _scheduling:false } : p));
    } finally { setScheduleSubmitting(false); }
  };
  const submitEdit = async () => {
    if(!editing) return;
    if(!editDirty()) { closeEdit(); return; }
    setSaving(true);
    const body = {};
    try {
      const origSeason = editing.season_number ?? null;
      const origEpisode = editing.episode_number ?? null;
      const newSeason = editValues.season_number ?? null;
      const newEpisode = editValues.episode_number ?? null;
      const seasonChanged = newSeason !== origSeason;
      const episodeIncreased = (newEpisode != null && origEpisode != null && newEpisode > origEpisode);

      if(editValues.title !== (editing.title||'')) body.title = editValues.title.trim();
      if(editValues.description !== (editing.description||'')) body.description = editValues.description;
      if(editValues.publish_state) body.publish_state = editValues.publish_state;
      const newTags = editValues.tags.split(',').map(t=>t.trim()).filter(Boolean);
      if(newTags.join('\u0001') !== (Array.isArray(editing.tags)?editing.tags.join('\u0001') : '')) body.tags = newTags;
      if(editValues.is_explicit !== !!editing.is_explicit) body.is_explicit = editValues.is_explicit;
      if(editValues.image_crop !== (editing.image_crop||'')) body.image_crop = editValues.image_crop;
      if(editValues.season_number !== (editing.season_number ?? null)) body.season_number = editValues.season_number;
      if(editValues.episode_number !== (editing.episode_number ?? null)) body.episode_number = editValues.episode_number;
      if((editValues.template_id ?? null) !== (editing.template_id ?? null)) body.template_id = editValues.template_id;
      // Cover upload (if new file)
      let coverPath = null;
      if(editValues.cover_file){
        setEditValues(v=>({...v,cover_uploading:true}));
        try {
          const fd = new FormData();
            let fileToSend = editValues.cover_file;
            if(cropperRef.current){
              try {
                const blob = await cropperRef.current.getProcessedBlob();
                if(blob){
                  fileToSend = new File([blob], editValues.cover_file.name.replace(/\.[^.]+$/,'')+"-square.jpg", { type:'image/jpeg' });
                }
                if(cropperRef.current.getMode && cropperRef.current.getMode()==='pad' && body.image_crop){
                  delete body.image_crop; // pad mode keeps full image
                }
              } catch {}
            }
          fd.append('file', fileToSend);
          const api = makeApi(token);
          try {
            const uj = await api.raw('/api/media/upload/cover_art', { method:'POST', body: fd });
            coverPath = uj?.filename || uj?.path || uj?.stored_as || null;
          } catch (e) {
            console.warn('Cover upload failed', e);
          }
        } catch(err){ console.warn('Cover upload error', err); }
        setEditValues(v=>({...v,cover_uploading:false}));
      }
      if(coverPath) body.cover_image_path = coverPath;
      const api = makeApi(token);
      // If the target episode number would collide with another in the same season, offer swap
      if (newSeason != null && newEpisode != null) {
        const conflictEp = episodes.find(e => e.id !== editing.id && (e.season_number ?? null) === newSeason && (e.episode_number ?? null) === newEpisode && (e.podcast_id === editing.podcast_id));
        if (conflictEp && window.confirm(`Episode number E${newEpisode} is already used in season S${newSeason} by "${conflictEp.title || 'Untitled'}". Swap numbers (that one becomes E${origEpisode || '—'})?`)) {
          try { await api.patch(`/api/episodes/${conflictEp.id}`, { episode_number: origEpisode }); } catch {}
        }
      }
      const j = await api.patch(`/api/episodes/${editing.id}`, body);
      setEpisodes(prev => prev.map(p => p.id===editing.id ? { ...p, ...(j?.episode||{}), ...(j?.episode?{}:{
        title: body.title ?? p.title,
        description: body.description ?? p.description,
        tags: body.tags ?? p.tags,
        is_explicit: body.is_explicit ?? p.is_explicit,
        image_crop: body.image_crop ?? p.image_crop,
        cover_path: coverPath || p.cover_path,
        season_number: body.season_number ?? p.season_number,
        episode_number: body.episode_number ?? p.episode_number,
        template_id: body.template_id ?? p.template_id,
      }) } : p));
      // Optional cascades for season change and episode increments
      if ((seasonChanged || episodeIncreased) && episodes && episodes.length) {
        const sorted = [...episodes].sort((a,b)=> episodeSortDate(a) - episodeSortDate(b));
        const idx = sorted.findIndex(e=> e.id===editing.id);
        const subsequent = idx>=0 ? sorted.slice(idx+1) : [];
        // Season cascade
        if (seasonChanged && subsequent.length>0) {
          const apply = window.confirm(`Also change the season to ${newSeason ?? '—'} for ${subsequent.length} episode(s) after this one?`);
          if (apply) {
            for (const e of subsequent) {
              try { await api.patch(`/api/episodes/${e.id}`, { season_number: newSeason }); } catch {}
            }
          }
        }
        // Episode increment cascade
        if (episodeIncreased && subsequent.length>0 && origEpisode != null) {
          const delta = newEpisode - origEpisode;
          const apply = window.confirm(`Increment the episode number by +${delta} for ${subsequent.length} episode(s) after this one?`);
          if (apply) {
            for (const e of subsequent) {
              const en = (e.episode_number ?? 0) + delta;
              try { await api.patch(`/api/episodes/${e.id}`, { episode_number: en }); } catch {}
            }
          }
        }
      }
      closeEdit();
      // Refresh to recompute duplicate warnings
      try { await fetchEpisodes(); } catch {}
    } catch(e){
      const msg = isApiError(e) ? (e.detail || e.error || e.message) : String(e);
      alert(msg || 'Failed to save changes');
    } finally { setSaving(false); }
  };

  const fetchTemplates = useCallback(async () => {
    setTemplatesLoading(true);
    try {
      const api = makeApi(token);
      const data = await api.get('/api/templates/');
      const items = Array.isArray(data) ? data.filter(t => t && t.id) : [];
      setTemplates(items);
    } catch (e) {
      console.warn('Failed to load templates', e);
    } finally {
      setTemplatesLoading(false);
    }
  }, [token]);
  useEffect(() => { fetchTemplates(); }, [fetchTemplates]);

  const editingPodcastId = editing ? editing.podcast_id : null;
  const editingTemplateId = editing ? editing.template_id : null;

  const findTemplateById = useCallback((id) => {
    if (!id) return null;
    const target = String(id);
    return templates.find(t => String(t.id) === target) || null;
  }, [templates]);

  const activeTemplates = useMemo(() => {
    return templates.filter(t => t && t.is_active !== false);
  }, [templates]);

  const relevantTemplates = useMemo(() => {
    if (!activeTemplates.length) return [];
    if (!editingPodcastId) return activeTemplates;
    const scoped = activeTemplates.filter(t => String(t.podcast_id ?? '') === String(editingPodcastId ?? ''));
    return scoped.length ? scoped : activeTemplates;
  }, [activeTemplates, editingPodcastId]);

  const editingTemplate = useMemo(() => {
    const identifier = editValues.template_id ?? editingTemplateId;
    return identifier ? findTemplateById(identifier) : null;
  }, [editValues.template_id, editingTemplateId, findTemplateById]);

  const updateAiBusy = (field, value) => {
    setAiBusy(prev => ({ ...prev, [field]: value }));
  };

  const handleAiError = (err, label) => {
    let message = '';
    if (isApiError(err)) {
      const detail = err.detail;
      if (detail && typeof detail === 'object') {
        const code = String(detail.error || detail.code || '').toUpperCase();
        if (code === 'TRANSCRIPT_NOT_READY') {
          message = 'Transcript not ready yet. Try again soon.';
        } else if (code === 'RATE_LIMIT' || err.status === 429) {
          message = 'Too many AI requests right now. Please wait and retry.';
        } else if (detail.message) {
          message = String(detail.message);
        } else if (detail.detail) {
          message = String(detail.detail);
        }
      } else if (typeof detail === 'string' && detail) {
        if (detail.toUpperCase() === 'TRANSCRIPT_NOT_READY') {
          message = 'Transcript not ready yet. Try again soon.';
        } else {
          message = detail;
        }
      } else if (err.error) {
        message = String(err.error);
      } else if (err.message) {
        message = String(err.message);
      }
    }
    if (!message) {
      message = `AI ${label} request failed.`;
    }
    alert(message);
  };

  const associateTemplate = useCallback(async (templateId, { silent = false } = {}) => {
    if (!templateId) return null;
    if (!editing) {
      return findTemplateById(templateId);
    }
    const normalized = String(templateId);
    const current = editingTemplateId ? String(editingTemplateId) : null;
    if (current === normalized) {
      setEditValues(v => ({ ...v, template_id: templateId }));
      return findTemplateById(templateId);
    }
    try {
      const api = makeApi(token);
      await api.patch(`/api/episodes/${editing.id}`, { template_id: templateId });
      setEpisodes(prev => prev.map(e => e.id === editing.id ? { ...e, template_id: templateId } : e));
      setEditing(prev => prev ? { ...prev, template_id: templateId } : prev);
      setEditValues(v => ({ ...v, template_id: templateId }));
      return findTemplateById(templateId);
    } catch (err) {
      if (!silent) {
        const msg = isApiError(err) ? (err.detail || err.error || err.message) : String(err);
        alert(msg || 'Failed to link template.');
      }
      throw err;
    }
  }, [editing, editingTemplateId, token, findTemplateById, setEpisodes, setEditing, setEditValues]);

  const cancelTemplatePrompt = () => {
    pendingAiFieldRef.current = null;
    setTemplatePrompt({ open: false, field: null, saving: false, savingId: null });
  };

  const runAi = async (field, template) => {
    if (!editing) return;
    updateAiBusy(field, true);
    const api = makeApi(token);
    const hint = deriveEpisodeHint(editing);
    const basePayload = {
      episode_id: editing.id,
      podcast_id: editing.podcast_id,
      transcript_path: null,
      hint: hint || null,
      base_prompt: '',
    };
    const settings = template?.ai_settings || {};
    try {
      if (field === 'title') {
        const payload = {
          ...basePayload,
          extra_instructions: settings?.title_instructions || undefined,
        };
        const res = await api.post('/api/ai/title', payload);
        const suggestion = res?.title || '';
        if (suggestion && !/[a-f0-9]{16,}/i.test(suggestion)) {
          setEditValues(v => ({ ...v, title: suggestion }));
        }
      } else if (field === 'description') {
        const payload = {
          ...basePayload,
          extra_instructions: settings?.notes_instructions || undefined,
        };
        const res = await api.post('/api/ai/notes', payload);
        const raw = (res?.description || '').toString();
        const cleaned = raw
          .replace(/^(?:\*\*?)?description:?\*?\*?\s*/i, '')
          .replace(/^#+\s*description\s*/i, '')
          .trim();
        if (cleaned) {
          setEditValues(v => ({ ...v, description: cleaned }));
        }
      } else if (field === 'tags') {
        const payload = {
          ...basePayload,
          extra_instructions: settings?.tags_instructions || undefined,
          tags_always_include: Array.isArray(settings?.tags_always_include) ? settings.tags_always_include : [],
        };
        const res = await api.post('/api/ai/tags', payload);
        let tags = Array.isArray(res?.tags) ? res.tags : [];
        if ((!tags || !tags.length) && Array.isArray(payload.tags_always_include)) {
          tags = payload.tags_always_include;
        }
        if (tags && tags.length) {
          const normalized = [...new Set(tags.map(t => String(t).trim()).filter(Boolean))];
          setEditValues(v => ({ ...v, tags: normalized.join(', ') }));
        }
      }
    } catch (err) {
      handleAiError(err, field === 'tags' ? 'tags' : field);
    } finally {
      updateAiBusy(field, false);
    }
  };

  const handleTemplateChoice = async (templateId) => {
    if (!templateId) return;
    setTemplatePrompt(prev => ({ ...prev, saving: true, savingId: templateId }));
    try {
      const template = await associateTemplate(templateId);
      setTemplatePrompt({ open: false, field: null, saving: false, savingId: null });
      const field = pendingAiFieldRef.current;
      pendingAiFieldRef.current = null;
      if (field) {
        await runAi(field, template || findTemplateById(templateId));
      }
    } catch (err) {
      setTemplatePrompt(prev => ({ ...prev, saving: false, savingId: null }));
    }
  };

  const handleAiGenerate = async (field) => {
    if (!editing || !field) return;
    if (aiBusy[field]) return;
    let template = editingTemplate;
    if (!template && templatesLoading) {
      pendingAiFieldRef.current = field;
      setTemplatePrompt({ open: true, field, saving: false, savingId: null });
      return;
    }
    if (!template) {
      const associatedId = editValues.template_id ?? editingTemplateId;
      if (associatedId) {
        template = findTemplateById(associatedId);
      }
    }
    if (!template) {
      const options = relevantTemplates;
      if (options.length === 1) {
        try {
          template = await associateTemplate(options[0].id, { silent: true });
        } catch (err) {
          template = options[0];
        }
      } else if (options.length > 1) {
        pendingAiFieldRef.current = field;
        setTemplatePrompt({ open: true, field, saving: false, savingId: null });
        return;
      }
    }
    pendingAiFieldRef.current = null;
    await runAi(field, template);
  };

  const fetchEpisodes = useCallback(async () => {
    setLoading(true); setErr("");
    const controller = new AbortController();
    try {
      let list = [];
      const api = makeApi(token);
      const firstData = await api.get('/api/episodes/?limit=500', { signal: controller.signal });
      list = Array.isArray(firstData?.items) ? firstData.items : [];
      const total = firstData?.total ?? list.length;
      for(let offset=list.length; offset < total; offset += 500){
        let page;
        try { page = await api.get(`/api/episodes/?limit=500&offset=${offset}`, { signal: controller.signal }); }
        catch { break; }
        const items = Array.isArray(page?.items) ? page.items : [];
        if(!items.length) break;
        list = list.concat(items);
        if(items.length < 500) break;
      }
      // Merge analytics plays totals if available
      try {
        const stats = await api.get('/api/spreaker/analytics/plays/episodes?window=last30d', { signal: controller.signal });
        if (Array.isArray(stats?.items) && stats.items.length) {
          const map = new Map(stats.items.map(it => [String(it.episode_id), it.plays_total]));
          list = list.map(e => ({ ...e, plays_total: map.has(String(e.id)) ? map.get(String(e.id)) : e.plays_total }));
        }
      } catch {}
  setEpisodes(list);
  // recompute duplicates
  recomputeGlobalNumberingConflicts(list);
    } catch (e) {
      if(e.name !== 'AbortError') {
        const msg = isApiError(e) ? (e.detail || e.error || e.message) : String(e);
        setErr(msg || 'Failed to load episodes.');
      }
    } finally { setLoading(false); }
    return () => controller.abort();
  }, [token, recomputeGlobalNumberingConflicts]);
  useEffect(() => { fetchEpisodes(); }, [fetchEpisodes]);
  // Per-edit duplicate detection for the current edit form
  useEffect(() => {
    if (!editing) { setNumberingConflict(false); return; }
    const s = editValues.season_number ?? null;
    const n = editValues.episode_number ?? null;
    if (s == null || n == null) { setNumberingConflict(false); return; }
    const dup = episodes.some(e => e.id !== editing.id && (e.season_number ?? null) === s && (e.episode_number ?? null) === n && (e.podcast_id === editing.podcast_id));
    setNumberingConflict(dup);
  }, [editing, editValues.season_number, editValues.episode_number, episodes]);
  // Open unpublish confirmation modal
  const openUnpublish = (ep) => {
    setUnpublishEp(ep);
    setUnpublishDoing(false);
    setUnpublishError("");
    setUnpublishCanForce(false);
  };
  const doUnpublish = async (force=false) => {
    if(!unpublishEp) return;
    setUnpublishDoing(true); setUnpublishError("");
    try {
      const api = makeApi(token);
      await api.post(`/api/episodes/${unpublishEp.id}/unpublish`, { force });
      setEpisodes(prev => prev.map(e => e.id===unpublishEp.id ? { ...e, status:'processed', publish_at:null, spreaker_episode_id:null } : e));
      setUnpublishEp(null);
      setTimeout(fetchEpisodes, 800);
    } catch(e){
      if (e && typeof e === 'object' && e.status === 409) setUnpublishCanForce(true);
      const msg = isApiError(e) ? (e.detail || e.error || e.message) : String(e);
      setUnpublishError(msg || 'Failed to unpublish');
    }
    finally { setUnpublishDoing(false); }
  };
  const handleDeleteEpisode = async (episodeId) => {
    if (!episodeId) return;
  if (!window.confirm('Delete this episode permanently? This cannot be undone.' + '\nDeleting does not return processing minutes.')) return;
    setDeletingIds(prev => new Set(prev).add(episodeId));
    try {
      const api = makeApi(token);
      await api.del(`/api/episodes/${episodeId}`);
      setEpisodes(prev => prev.filter(e => e.id !== episodeId));
    } catch (e) {
      const msg = isApiError(e) ? (e.detail || e.error || e.message) : String(e);
      setErr(msg || 'Delete failed');
    }
    finally { setDeletingIds(prev => { const n = new Set(prev); n.delete(episodeId); return n; }); }
  };
  const statusChip = (s) => {
    switch(statusLabel(s)){
      case 'published': return <Badge className="bg-green-600 hover:bg-green-600"><CheckCircle2 className="w-4 h-4 mr-1"/>Published</Badge>;
      case 'scheduled': return <Badge className="bg-purple-600 hover:bg-purple-600"><CalendarClock className="w-4 h-4 mr-1"/>Scheduled</Badge>;
      case 'processed': return <Badge className="bg-blue-600 hover:bg-blue-600"><Clock className="w-4 h-4 mr-1"/>Processed</Badge>;
      case 'processing': return <Badge className="bg-amber-600 hover:bg-amber-600"><Loader2 className="w-4 h-4 mr-1 animate-spin"/>Processing</Badge>;
      case 'error': return <Badge className="bg-red-600 hover:bg-red-600"><AlertTriangle className="w-4 h-4 mr-1"/>Error</Badge>;
      default: return <Badge variant="outline">{s || 'Unknown'}</Badge>;
    }
  };
  // Derived filtered/sorted episodes
  const displayEpisodes = useMemo(() => {
    let list = [...episodes];
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter(e => (e.title||'').toLowerCase().includes(q) || (e.description||'').toLowerCase().includes(q));
    }
    if (statusFilter !== 'all') {
      list = list.filter(e => String(e.status||'').toLowerCase() === statusFilter);
    }
    switch (sortKey) {
      case 'oldest':
        list.sort((a,b)=> episodeSortDate(a) - episodeSortDate(b));
        break;
      case 'title':
        list.sort((a,b)=> (a.title||'').localeCompare(b.title||''));
        break;
      case 'status':
        list.sort((a,b)=> (a.status||'').localeCompare(b.status||''));
        break;
      case 'plays':
        list.sort((a,b)=> (b.plays_total||0) - (a.plays_total||0));
        break;
      case 'newest':
      default:
        list.sort((a,b)=> episodeSortDate(b) - episodeSortDate(a));
    }
    return list;
  }, [episodes, search, statusFilter, sortKey]);
  const renderGrid = () => (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-6">
      {displayEpisodes.map(ep => {
        const coverUrl = resolveAssetUrl(ep.cover_url) || resolveAssetUrl(`/api/episodes/${ep.id}/cover`);
        // Prioritize a direct public URL if the backend provides it.
        // Otherwise, fall back to existing stream/final URLs.
        let audioUrl = ep.public_url || ep.playback_url || ep.stream_url || ep.final_audio_url || '';
        audioUrl = resolveAssetUrl(audioUrl) || '';
  const missingAudio = audioUrl && ep.final_audio_exists === false && ep.playback_type !== 'stream';
  // Allow unpublish for all scheduled/published episodes (force option available after 24h)
  const showUnpublish = statusLabel(ep.status) === 'scheduled' || statusLabel(ep.status) === 'published';
        // Heuristic: show Retry when status is error, or processing exceeds 1.25x duration (fallback 15min)
        let showRetry = false;
        const st = statusLabel(ep.status);
        if (st === 'error') showRetry = true;
        // Always show retry if processing with no audio (likely stuck/failed)
        if (st === 'processing' && !ep.final_audio_exists && !audioUrl) showRetry = true;
        if (st === 'processing') {
          // Use processed_at if present, otherwise fall back to created_at so we can detect long-running items reliably
          const started = normalizeDate(ep.processed_at) || normalizeDate(ep.created_at) || new Date(0);
          const elapsed = Date.now() - started.getTime();
          // For processing episodes: use actual duration if available, otherwise be aggressive with fallback
          // Show retry after 20 minutes if no duration info, or 1.25x duration if known
          const durMs = (typeof ep.duration_ms === 'number' && ep.duration_ms > 0) ? ep.duration_ms : (20*60*1000);
          const threshold = Math.round(durMs * 1.25);
          if (elapsed > threshold) showRetry = true;
          // ALSO show retry if processing for more than 30 minutes absolute (stuck worker safeguard)
          if (elapsed > 30*60*1000) showRetry = true;
        }
        return (
          <div key={ep.id} className="space-y-2">
          <Card className="group overflow-hidden border border-gray-200 relative">
            <div className="w-full h-36 bg-gray-100 flex items-center justify-center relative">
              <img
                src={coverUrl}
                alt="Cover"
                className="w-full h-full object-cover"
                onError={(e) => { e.currentTarget.style.display = 'none'; const fb = e.currentTarget.nextSibling; if(fb) fb.style.display='flex'; }}
              />
              <div className="hidden w-full h-full items-center justify-center text-gray-400">
                <ImageOff className="w-8 h-8 mr-2"/> No cover
              </div>
              {/* Cover always sourced from Spreaker or local upload; 'No Cover File' badge removed */}
              {showUnpublish && (
                <button
                  className="absolute top-1 left-1 bg-white/85 hover:bg-white text-amber-700 border border-amber-300 rounded p-1 shadow-sm text-[11px] font-medium opacity-0 group-hover:opacity-100 transition-opacity"
                  title="Unpublish episode (revert to processed)"
                  onClick={()=>openUnpublish(ep)}
                >
                  <Undo2 className="w-3 h-3 inline mr-1"/>Unpublish
                </button>
              )}
              {/* Move Cut for edits to bottom-right cluster */}
              <Button
                variant="destructive"
                size="sm"
                className="absolute top-2 right-2 flex items-center gap-1 bg-white/90 text-red-600 hover:bg-white shadow-sm opacity-0 group-hover:opacity-100 transition-opacity"
                title="Delete episode"
                onClick={() => handleDeleteEpisode(ep.id)}
                disabled={deletingIds.has(ep.id)}
              >
                {deletingIds.has(ep.id) ? <Loader2 className="w-4 h-4 animate-spin"/> : <Trash2 className="w-4 h-4"/>}
                Delete
              </Button>
              {showRetry && (
                <button
                  className="absolute bottom-1 left-1 bg-white/90 hover:bg-white text-amber-700 border border-amber-300 rounded px-2 py-1 shadow-sm text-[11px] font-medium flex items-center gap-1"
                  title="Retry processing"
                  onClick={() => doRetry(ep)}
                  disabled={retryingId === ep.id}
                >
                  {retryingId === ep.id ? <Loader2 className="w-3 h-3 animate-spin"/> : <RotateCcw className="w-3 h-3"/>}
                  Retry
                </button>
              )}
              <div className="absolute bottom-1 right-1 flex gap-1 items-center">
                {(ep.status === 'processed' || 
                  (statusLabel(ep.status) === 'published' && isWithin7Days(ep.publish_at)) ||
                  (statusLabel(ep.status) === 'scheduled' && isWithin7Days(ep.publish_at))) && (
                  <>
                    {/* Cut for edits */}
                    <button
                      className="bg-white/85 hover:bg-white text-purple-700 border border-purple-300 rounded p-1 shadow-sm"
                      title="Cut for edits"
                      onClick={() => setFlubberEpId(prev => prev===ep.id? null : ep.id)}
                    >
                      <Scissors className="w-4 h-4" />
                    </button>
                    {/* Manual Editor */}
                    <button
                      className="bg-white/85 hover:bg-white text-blue-700 border border-blue-300 rounded p-1 shadow-sm"
                      title="Open Manual Editor"
                      onClick={() => setManualEpId(prev => prev===ep.id? null : ep.id)}
                    >
                      <Pencil className="w-4 h-4" />
                    </button>
                    {(ep.needs_republish || !!ep.publish_error) ? (
                      <button
                        className="bg-amber-600 hover:bg-amber-700 text-white text-[11px] font-medium px-2 py-1 rounded shadow disabled:opacity-60"
                        onClick={() => doRepublish(ep)}
                        title="Retry publishing to Spreaker"
                        disabled={republishingId === ep.id}
                      >{republishingId === ep.id ? 'Retrying…' : 'Retry Publish'}</button>
                    ) : (
                      <button
                        className="bg-blue-600 hover:bg-blue-700 text-white text-[11px] font-medium px-2 py-1 rounded shadow disabled:opacity-60"
                        onClick={() => quickPublish(ep.id)}
                        title="Publish now"
                      >Publish</button>
                    )}
                  </>
                )}
                <button
                  className={`bg-purple-600 text-white text-[11px] font-medium px-2 py-1 rounded shadow transition disabled:opacity-60 disabled:cursor-not-allowed ${canScheduleEpisode(ep) ? 'hover:bg-purple-700' : 'bg-purple-500/80'}`}
                  onClick={() => openSchedule(ep)}
                  title={scheduleTooltip(ep)}
                  disabled={!canScheduleEpisode(ep)}
                  type="button"
                >Schedule</button>
              </div>
            </div>
            <CardHeader className="pb-2">
              <div className="flex items-start justify-between gap-2">
                <CardTitle className="text-base font-semibold leading-tight line-clamp-2" title={ep.title}>
                  {(ep.season_number!=null && ep.episode_number!=null) ? `S${ep.season_number}E${ep.episode_number} · ${ep.title || 'Untitled Episode'}` : (ep.title || 'Untitled Episode')}
                </CardTitle>
                <Button variant="secondary" size="sm" className="flex items-center gap-1" onClick={()=>startEdit(ep)}><Pencil className="w-4 h-4" />Edit</Button>
                {typeof ep.plays_total === 'number' && (
                  <Badge variant="secondary" className="text-[11px] font-medium">{ep.plays_total} plays</Badge>
                )}
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                {statusChip(ep.status)}
                {ep.cleanup_stats && (
                  <span className="text-[10px] text-gray-500">FW:{ep.cleanup_stats.fillers_removed} PC:{ep.cleanup_stats.pauses_compressed}</span>
                )}
                {ep.publish_at && (
                  <span className="text-[11px] text-gray-500 flex items-center gap-1" title={ep.publish_at}>
                    <CalendarClock className="w-3 h-3"/> {ep.status === 'scheduled' ? 'Publishes' : 'Publish'}: {formatPublishAtForUser(ep.publish_at)}
                  </span>
                )}
                {/* Spreaker & Streaming badges intentionally removed (Option E: reduce redundant UI) */}
                {ep.playback_type === 'local' && (
                  <span className="text-[10px] text-gray-500">Local file</span>
                )}
              </div>
            </CardHeader>
            <CardContent className="space-y-2 pt-0">
              {ep.description && <p className="text-xs text-gray-600 line-clamp-3">{ep.description}</p>}
              {audioUrl ? (
                <audio controls src={audioUrl} className="w-full" preload="none"/>
              ) : (
                <div className="text-gray-500 text-xs flex items-center"><Play className="w-3 h-3 mr-1"/>No audio</div>
              )}
              {missingAudio && <div className="text-[10px] text-red-600">File missing on server</div>}
              {/* Show transcript scroll icon if GCS transcript is available */}
              {(() => {
                let transcriptUrl = null;
                if (ep.meta_json) {
                  try {
                    const meta = typeof ep.meta_json === 'string' ? JSON.parse(ep.meta_json) : ep.meta_json;
                    transcriptUrl = resolveAssetUrl(meta?.transcripts?.gcs_json || null) || null;
                  } catch {}
                }
                if (transcriptUrl) {
                  return (
                    <a
                      href={transcriptUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-xs text-blue-600 hover:text-blue-700 underline"
                      title="View transcript"
                    >
                      {/* Simple scroll icon for now */}
                      <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" viewBox="0 0 16 16"><path d="M4 2a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H4zm0 1h8a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zm2 2v6h4V4H6zm1 1h2v4H7V5z"/></svg>
                      Transcript
                    </a>
                  );
                }
                return null;
              })()}
            </CardContent>
            </Card>
            {manualEpId === ep.id && (
              <ManualEditorModal episodeId={ep.id} token={token} onClose={()=>setManualEpId(null)} />
            )}
            {flubberEpId === ep.id && (
              <FlubberReview episodeId={ep.id} token={token} onClose={()=>setFlubberEpId(null)} />
            )}
          </div>
        );
      })}
    </div>
  );
  const renderList = () => (
    <div className="border border-gray-200 rounded-md overflow-hidden divide-y">
      <div className="grid grid-cols-12 bg-gray-50 text-[11px] uppercase tracking-wide text-gray-500 px-3 py-2 font-medium">
        <div className="col-span-5">Episode</div>
        <div className="col-span-2">Status</div>
        <div className="col-span-2">Publish</div>
        <div className="col-span-2">Plays</div>
        <div className="col-span-1 text-right">Actions</div>
      </div>
      {displayEpisodes.map(ep => {
  let audioUrl = ep.playback_url || ep.stream_url || ep.final_audio_url || '';
        audioUrl = resolveAssetUrl(audioUrl) || '';
  const showUnpublish = statusLabel(ep.status) === 'scheduled' || (statusLabel(ep.status) === 'published' && isWithin24h(ep.publish_at));
        let showRetry = false;
        {
          const st = statusLabel(ep.status);
          if (st === 'error') showRetry = true;
          if (st === 'processing') {
            const started = normalizeDate(ep.processed_at) || normalizeDate(ep.created_at) || new Date(0);
            const elapsed = Date.now() - started.getTime();
            const durMs = (typeof ep.duration_ms === 'number' && ep.duration_ms > 0) ? ep.duration_ms : (15*60*1000);
            const threshold = Math.round(durMs * 1.25);
            if (elapsed > threshold) showRetry = true;
          }
        }
        return (
          <div key={ep.id} className="group grid grid-cols-12 items-start px-3 py-3 gap-2 text-sm hover:bg-gray-50">
            <div className="col-span-5 flex flex-col">
              <span className="font-medium truncate" title={ep.title}>
                {(ep.season_number!=null && ep.episode_number!=null) ? `S${ep.season_number}E${ep.episode_number} · ${ep.title || 'Untitled Episode'}` : (ep.title || 'Untitled Episode')}
              </span>
              {ep.description && <span className="text-[11px] text-gray-500 line-clamp-1" title={ep.description}>{ep.description}</span>}
              {ep.has_transcript && ep.transcript_url && (
                <a
                  href={resolveAssetUrl(ep.transcript_url)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[11px] text-blue-600 hover:text-blue-700 underline mt-1"
                >Transcript</a>
              )}
            </div>
            <div className="col-span-2 flex items-center flex-wrap gap-1">{statusChip(ep.status)}</div>
            <div className="col-span-2 text-[11px] text-gray-600">
              {ep.publish_at ? formatPublishAtForUser(ep.publish_at, ep.publish_at_local) : '-'}
            </div>
            <div className="col-span-2 text-[11px]">{typeof ep.plays_total === 'number' ? ep.plays_total : '-'}</div>
            <div className="col-span-1 flex justify-end">
              {showUnpublish && (
                <button
                  className="mr-2 text-amber-600 hover:text-amber-700 text-xs underline opacity-0 group-hover:opacity-100 transition-opacity"
                  title="Unpublish episode (revert to processed)"
                  onClick={()=>openUnpublish(ep)}
                >Unpublish</button>
              )}
              {showRetry && (
                <button
                  className="mr-2 text-amber-700 hover:text-amber-800 text-xs underline"
                  title="Retry processing"
                  onClick={()=>doRetry(ep)}
                  disabled={retryingId === ep.id}
                >
                  {retryingId === ep.id ? 'Retrying…' : 'Retry'}
                </button>
              )}
              <Button
                variant="destructive"
                size="sm"
                className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity"
                title="Delete episode"
                onClick={() => handleDeleteEpisode(ep.id)}
                disabled={deletingIds.has(ep.id)}
              >
                {deletingIds.has(ep.id) ? <Loader2 className="w-4 h-4 animate-spin"/> : <Trash2 className="w-4 h-4"/>}
                Delete
              </Button>
              <Button variant="outline" size="sm" className="ml-2 flex items-center gap-1" onClick={()=>startEdit(ep)}><Pencil className="w-4 h-4" />Edit</Button>
              <button
                className="ml-2 text-purple-600 hover:text-purple-700 text-xs underline"
                title="Cut for edits"
                onClick={() => setFlubberEpId(prev => prev===ep.id? null : ep.id)}
              >Cut for edits</button>
              {ep.status === 'processed' && (ep.needs_republish || !!ep.publish_error) ? (
                <button
                  className="ml-2 text-amber-700 hover:text-amber-800 text-xs underline"
                  onClick={() => doRepublish(ep)}
                  disabled={republishingId === ep.id}
                >{republishingId === ep.id ? 'Retrying…' : 'Retry Publish'}</button>
              ) : ep.status === 'processed' && (
                <button
                  className="ml-2 text-green-600 hover:text-green-700 text-xs underline"
                  onClick={() => quickPublish(ep.id)}
                >Publish</button>
              )}
              <button
                className={`ml-1 text-xs underline text-purple-600 ${canScheduleEpisode(ep) ? 'hover:text-purple-700' : 'opacity-60 cursor-not-allowed hover:text-purple-600'}`}
                onClick={() => openSchedule(ep)}
                disabled={!canScheduleEpisode(ep)}
                title={scheduleTooltip(ep)}
                type="button"
              >Schedule</button>
            </div>
      {audioUrl && (
              <div className="col-span-12 mt-2">
                <audio controls src={audioUrl} className="w-full" preload="none"/>
  {/* Streaming badge removed (Option E) */}
              </div>
            )}
          </div>
        );
      })}
      {displayEpisodes.length === 0 && (
        <div className="px-3 py-6 text-center text-sm text-gray-500">No matching episodes.</div>
      )}
    </div>
  );
  // Permanent "experimental" mosaic view (uses the preview component as a dense grid)
  const renderMosaic = () => (
    <div className="rounded-lg">
      <EpisodeHistoryPreview
        episodes={displayEpisodes}
        onEdit={(ep)=>startEdit(ep)}
        onDelete={(ep)=>handleDeleteEpisode(ep.id)}
        formatPublishAt={formatPublishAtForUser}
      />
    </div>
  );
  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div className="flex items-center gap-3">
            {onBack && (
              <Button onClick={onBack} variant="ghost" className="text-gray-700 hover:bg-gray-100">
                <ArrowLeft className="w-4 h-4 mr-2" />Back
              </Button>
            )}
            <h2 className="text-2xl font-bold">Episode History</h2>
          </div>
          <div className="flex items-center gap-2 flex-wrap">
            <Button onClick={fetchEpisodes} variant="outline" size="sm" className="h-8">
              <RefreshCw className="w-4 h-4 mr-1"/>Refresh
            </Button>
            <div className="flex items-center border rounded px-2 h-8 bg-white">
              <Search className="w-4 h-4 text-gray-500" />
              <input
                type="text"
                placeholder="Search..."
                className="ml-2 outline-none text-sm placeholder:text-gray-400 bg-transparent"
                value={search}
                onChange={e=>setSearch(e.target.value)}
              />
            </div>
            <select className="h-8 border rounded text-sm px-2 bg-white" value={statusFilter} onChange={e=>setStatusFilter(e.target.value)}>
              <option value="all">All statuses</option>
              <option value="published">Published</option>
              <option value="scheduled">Scheduled</option>
              <option value="processed">Processed</option>
              <option value="processing">Processing</option>
              <option value="error">Error</option>
            </select>
            <select className="h-8 border rounded text-sm px-2 bg-white" value={sortKey} onChange={e=>setSortKey(e.target.value)}>
              <option value="newest">Newest</option>
              <option value="oldest">Oldest</option>
              <option value="title">Title</option>
              <option value="status">Status</option>
              <option value="plays">Plays</option>
            </select>
    <div className="flex border rounded overflow-hidden">
              <button
                className={`px-2 h-8 text-sm flex items-center gap-1 ${viewMode==='grid'?'bg-gray-200 font-medium':'bg-white hover:bg-gray-50'}`}
                onClick={()=>setViewMode('grid')}
                title="Grid view"
              >
                <LayoutGrid className="w-4 h-4"/>
              </button>
              <button
                className={`px-2 h-8 text-sm flex items-center gap-1 border-l ${viewMode==='mosaic'?'bg-gray-200 font-medium':'bg-white hover:bg-gray-50'}`}
                onClick={()=>setViewMode('mosaic')}
                title="Mosaic view"
              >
                <Grid3x3 className="w-4 h-4"/>
              </button>
              <button
                className={`px-2 h-8 text-sm flex items-center gap-1 border-l ${viewMode==='list'?'bg-gray-200 font-medium':'bg-white hover:bg-gray-50'}`}
                onClick={()=>setViewMode('list')}
                title="List view"
              >
                <ListIcon className="w-4 h-4"/>
              </button>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-4 text-xs text-gray-500">
          <span>{episodes.length} total</span>
          {search && <span>• {displayEpisodes.length} match</span>}
          {hasGlobalNumberingConflict && (
            <span className="text-red-600">• Warning: duplicate Season/Episode combinations exist. Edit to resolve.</span>
          )}
        </div>
      </div>
  {loading && <div className="flex items-center text-gray-600"><Loader2 className="w-5 h-5 mr-2 animate-spin"/>Loading...</div>}
  {err && <div className="text-red-600 text-sm">{err}</div>}
  {retryError && <div className="text-amber-700 text-sm">{retryError}</div>}
  {!loading && (viewMode === 'grid' ? renderGrid() : viewMode === 'mosaic' ? renderMosaic() : renderList())}
      {editing && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-end z-50">
          <div className="w-full max-w-md h-full bg-white shadow-xl flex flex-col">
            <div className="px-4 py-3 border-b flex items-center justify-between">
              <h3 className="font-semibold text-lg">Edit Episode</h3>
              <button onClick={closeEdit} className="text-gray-500 hover:text-gray-800 text-sm">Close</button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Season Number</label>
                <input type="number" min="0" className="w-full border rounded px-2 py-1 text-sm" value={editValues.season_number ?? ''} onChange={e=>setEditValues(v=>({...v,season_number:e.target.value===''?null:parseInt(e.target.value)}))} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Episode Number</label>
                <input type="number" min="0" className="w-full border rounded px-2 py-1 text-sm" value={editValues.episode_number ?? ''} onChange={e=>setEditValues(v=>({...v,episode_number:e.target.value===''?null:parseInt(e.target.value)}))} />
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Title</label>
                <div className="flex items-center gap-2">
                  <input className="flex-1 border rounded px-2 py-1 text-sm" value={editValues.title} onChange={e=>setEditValues(v=>({...v,title:e.target.value}))} />
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    onClick={() => handleAiGenerate('title')}
                    disabled={saving || aiBusy.title}
                    title="Regenerate title with AI"
                  >
                    {aiBusy.title ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
                  </Button>
                </div>
                {editingTemplate && (
                  <div className="mt-1 text-[11px] text-gray-500">
                    AI template: {editingTemplate.name}
                  </div>
                )}
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Description / Show Notes</label>
                <div className="flex items-start gap-2">
                  <textarea rows={6} className="flex-1 border rounded px-2 py-1 text-sm resize-vertical" value={editValues.description} onChange={e=>setEditValues(v=>({...v,description:e.target.value}))} />
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    onClick={() => handleAiGenerate('description')}
                    disabled={saving || aiBusy.description}
                    title="Regenerate description with AI"
                  >
                    {aiBusy.description ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
                  </Button>
                </div>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Visibility</label>
                <select className="w-full border rounded px-2 py-1 text-sm" value={editValues.publish_state} onChange={e=>setEditValues(v=>({...v,publish_state:e.target.value}))}>
                  <option value="">(no change)</option>
                  <option value="public">Public</option>
                  <option value="unpublished">Unpublished</option>
                  <option value="limited">Limited</option>
                </select>
              </div>
              <div>
                <label className="block text-xs font-medium text-gray-600 mb-1">Tags (comma separated)</label>
                <div className="flex items-center gap-2">
                  <input className="flex-1 border rounded px-2 py-1 text-sm" value={editValues.tags} onChange={e=>setEditValues(v=>({...v,tags:e.target.value}))} placeholder="tag1, tag2" />
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    onClick={() => handleAiGenerate('tags')}
                    disabled={saving || aiBusy.tags}
                    title="Regenerate tags with AI"
                  >
                    {aiBusy.tags ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
                  </Button>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <input id="explicitFlag" type="checkbox" className="h-4 w-4" checked={editValues.is_explicit} onChange={e=>setEditValues(v=>({...v,is_explicit:e.target.checked}))} />
                <label htmlFor="explicitFlag" className="text-xs font-medium text-gray-600">Explicit content</label>
              </div>
              <div className="space-y-2">
                <label className="block text-xs font-medium text-gray-600">Cover Image & Crop</label>
                <input type="file" accept="image/*" className="w-full text-xs" onChange={e=>setEditValues(v=>({...v,cover_file:e.target.files?.[0]||null}))} />
                {editValues.cover_uploading && <div className="text-[11px] text-blue-600">Uploading cover...</div>}
                <CoverCropper
                  ref={cropperRef}
                  sourceFile={editValues.cover_file}
                  existingUrl={resolveAssetUrl(editing?.cover_url) || (editing ? resolveAssetUrl(`/api/episodes/${editing.id}/cover`) : null)}
                  value={editValues.cover_file ? editValues.image_crop : (editing?.image_crop || '')}
                  onChange={(c)=>setEditValues(v=>{
                    // Only store crop if a new file is selected; otherwise ignore (can't edit existing)
                    if(!v.cover_file) return v;
                    const next = c || '';
                    if(v.image_crop === next) return v;
                    return { ...v, image_crop: next };
                  })}
                  disabled={saving || !editValues.cover_file}
                />
              </div>
              <div className="text-[11px] text-gray-500">Saving updates local DB & pushes supported fields (title, description, visibility, cover when implemented) to Spreaker immediately if already published.</div>
            </div>
            <div className="px-4 py-3 border-t flex items-center justify-end gap-2">
              <Button variant="outline" size="sm" onClick={closeEdit} disabled={saving}>Cancel</Button>
              {/* In submit section (edit drawer footer) show warning */}
              {numberingConflict && <div className="text-[11px] text-red-600 mr-auto">Duplicate season/episode for this podcast</div>}
              <Button size="sm" onClick={submitEdit} disabled={saving || !editDirty() || numberingConflict}>
                {saving ? <><Loader2 className="w-4 h-4 mr-1 animate-spin"/>Saving...</> : 'Save Changes'}
              </Button>
            </div>
          </div>
        </div>
      )}
      {templatePrompt.open && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white w-full max-w-sm rounded shadow-lg p-5 space-y-4">
            <h3 className="text-lg font-semibold flex items-center gap-2 text-slate-800">
              <Wand2 className="w-5 h-5 text-primary" />Choose Template
            </h3>
            <div className="text-sm text-gray-700">
              Select which template rules to use for AI regeneration. We'll remember your choice for this episode.
            </div>
            <div className="space-y-2 max-h-60 overflow-y-auto">
              {templatesLoading ? (
                <div className="flex items-center gap-2 text-sm text-gray-500">
                  <Loader2 className="w-4 h-4 animate-spin" />Loading templates...
                </div>
              ) : relevantTemplates.length ? (
                relevantTemplates.map(template => (
                  <Button
                    key={template.id}
                    variant="outline"
                    className="w-full flex items-center justify-between"
                    disabled={templatePrompt.saving}
                    onClick={() => handleTemplateChoice(template.id)}
                  >
                    <span>{template.name}</span>
                    {templatePrompt.saving && templatePrompt.savingId === template.id ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : null}
                  </Button>
                ))
              ) : (
                <div className="text-sm text-gray-500">No templates available.</div>
              )}
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" disabled={templatePrompt.saving} onClick={cancelTemplatePrompt}>
                Cancel
              </Button>
            </div>
          </div>
        </div>
      )}

      {unpublishEp && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white w-full max-w-sm rounded shadow-lg p-5 space-y-4">
            <h3 className="text-lg font-semibold flex items-center gap-2 text-amber-700"><Undo2 className="w-5 h-5"/>Unpublish Episode</h3>
            <div className="text-sm text-gray-700 space-y-2">
              <p>Revert <strong>{unpublishEp.title || 'Untitled Episode'}</strong> back to processed? It will be removed from the feed and can be republished.</p>
              <p className="text-[11px] text-gray-500">Allowed within 24 hours of original publication. Remote delete attempted.</p>
              {unpublishError && <div className="text-red-600 text-xs">{unpublishError}</div>}
              {unpublishCanForce && !unpublishDoing && (
                <div className="text-amber-700 text-[11px]">Outside standard window. You may force unpublish anyway.</div>
              )}
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" disabled={unpublishDoing} onClick={()=>setUnpublishEp(null)}>Cancel</Button>
              {unpublishCanForce && (
                <Button variant="destructive" size="sm" disabled={unpublishDoing} onClick={()=>doUnpublish(true)}>
                  {unpublishDoing ? <><Loader2 className="w-4 h-4 mr-1 animate-spin"/>Forcing...</> : 'Force Unpublish'}
                </Button>
              )}
              {!unpublishCanForce && (
                <Button size="sm" disabled={unpublishDoing} onClick={()=>doUnpublish(false)}>
                  {unpublishDoing ? <><Loader2 className="w-4 h-4 mr-1 animate-spin"/>Unpublishing...</> : 'Unpublish'}
                </Button>
              )}
            </div>
          </div>
        </div>
      )}
      {scheduleEp && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white w-full max-w-sm rounded shadow-lg p-5 space-y-4">
            <h3 className="text-lg font-semibold text-purple-700">Schedule Publication</h3>
            <div className="text-sm text-gray-700 space-y-3">
              <p>Pick a local date & time to publish <strong>{scheduleEp.title || 'Untitled Episode'}</strong>. We'll convert it to UTC for the server.</p>
              <div className="flex flex-col gap-2">
                <label className="text-xs font-medium text-gray-600">Date</label>
                <input type="date" className="border rounded px-2 py-1 text-sm" value={scheduleDate} onChange={e=>setScheduleDate(e.target.value)} />
                <label className="text-xs font-medium text-gray-600">Time</label>
                <input type="time" step={300} className="border rounded px-2 py-1 text-sm" value={scheduleTime} onChange={e=>setScheduleTime(e.target.value)} />
              </div>
              <p className="text-[11px] text-gray-500">Must be at least 1 minute in the future. Local time is converted to exact UTC ISO for Spreaker.</p>
              {scheduleError && (
                <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2">
                  {scheduleError}
                </div>
              )}
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" size="sm" disabled={scheduleSubmitting} onClick={closeSchedule}>Cancel</Button>
              <Button size="sm" disabled={scheduleSubmitting || !scheduleDate || !scheduleTime} onClick={submitSchedule}>
                {scheduleSubmitting ? <><Loader2 className="w-4 h-4 mr-1 animate-spin"/>Scheduling...</> : 'Schedule'}
              </Button>
            </div>
          </div>
        </div>
      )}
      {(!loading && episodes.length === 0) && (
        <div className="text-gray-500">No episodes yet.</div>
      )}
    </div>
  );
}
