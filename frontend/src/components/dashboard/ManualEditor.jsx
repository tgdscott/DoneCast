import { useEffect, useState, useRef } from 'react';
import { makeApi, isApiError } from '@/lib/apiClient';
import WaveformEditor from './WaveformEditor';

export default function ManualEditor({ episodeId, token, onClose }) {
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [duration, setDuration] = useState(null);
  const [cuts, setCuts] = useState([]); // [{start_ms,end_ms}]
  const [preview, setPreview] = useState(null);
  const [saving, setSaving] = useState(false);
  const [audioUrl, setAudioUrl] = useState('');
  const waveRef = useRef(null);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const api = makeApi(token);
        const j = await api.get(`/api/episodes/${episodeId}/edit-context`);
        if (!live) return;
        console.log('[ManualEditor] Received edit context:', {
          episode_id: j?.episode_id,
          duration_ms: j?.duration_ms,
          audio_url: j?.audio_url,
          playback_type: j?.playback_type,
          final_audio_exists: j?.final_audio_exists,
        });
        setDuration(j?.duration_ms ?? null);
        setCuts(Array.isArray(j?.existing_cuts) ? j.existing_cuts : []);
        setAudioUrl(j?.audio_url || '');
        if (!j?.audio_url) {
          setErr('No audio URL available for this episode. Please ensure the episode has been processed and has audio uploaded.');
        }
      } catch (e) {
        const msg = isApiError(e) ? (e.detail || e.error || e.message) : String(e);
        setErr(msg || 'Failed to load edit context');
      } finally {
        setLoading(false);
      }
    })();
    return () => { live = false; };
  }, [episodeId, token]);

  const toMs = (val) => {
    if (val == null || val === '') return 0;
    const s = String(val).trim();
    if (/^\d+(?:\.\d+)?$/.test(s)) return Math.round(parseFloat(s) * 1000);
    const m = /^(\d+):(\d{1,2})(?:\.(\d{1,3}))?$/.exec(s);
    if (!m) return parseInt(s,10) || 0;
    const min = parseInt(m[1],10);
    const sec = parseInt(m[2],10);
    const ms = m[3] ? parseInt(m[3].padEnd(3,'0'),10) : 0;
    return min*60000 + sec*1000 + ms;
  };
  const toMMSS = (ms) => {
    if (!isFinite(ms) || ms == null) return '';
    const totalSec = Math.max(0, ms/1000);
    const m = Math.floor(totalSec/60);
    const s = Math.floor(totalSec % 60);
    const hundredths = Math.floor((totalSec - Math.floor(totalSec)) * 100);
    return `${m}:${String(s).padStart(2,'0')}.${String(hundredths).padStart(2,'0')}`;
  };
  const addCut = () => setCuts(c => [...c, { start_ms: 0, end_ms: 0 }]);
  const updateCut = (idx, key, val) => setCuts(c => c.map((x,i)=> i===idx ? { ...x, [key]: key==='start_ms'||key==='end_ms' ? toMs(val) : val } : x));
  const removeCut = (idx) => setCuts(c => c.filter((_,i)=> i!==idx));

  // Preview removed per user request

  const commitEdits = async () => {
    setSaving(true); setErr('');
    try {
      const api = makeApi(token);
      const liveCuts = waveRef.current?.getCuts ? waveRef.current.getCuts() : cuts;
      const resp = await api.post(`/api/episodes/${episodeId}/manual-edit/commit`, { cuts: liveCuts });
      if (resp && typeof resp.duration_ms === 'number') { setDuration(resp.duration_ms); }
      onClose?.();
      if (resp && resp.status === 'done') alert('Edits applied. A new final file has been saved.');
      else alert('Edit job queued. The final file will update shortly.');
    } catch (e) {
      const msg = isApiError(e) ? (e.detail || e.error || e.message) : String(e);
      setErr(msg || 'Commit failed');
    } finally { setSaving(false); }
  };

  if (loading) return <div className="p-4 text-sm">Loading editor…</div>;
  return (
    <div className="p-4 space-y-3">
      {/* Header is already shown by ManualEditorModal */}
  {err && <div className="text-xs text-red-600">{typeof err === 'string' ? err : (err.message || 'Error')}</div>}
  <div className="text-xs text-gray-600">Duration: {duration!=null ? (()=>{ const t=Math.floor(duration/1000); const h=Math.floor(t/3600); const m=Math.floor((t%3600)/60); const s=t%60; return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`; })() : '—'}</div>

      {!!audioUrl && (
        <div className="border rounded p-2">
          <WaveformEditor
            ref={waveRef}
            audioUrl={audioUrl}
            initialCuts={cuts}
            onCutsChange={setCuts}
            height={140}
            zoomWindows={[15,30,60,120]}
            onDuration={(ms)=>setDuration(ms)}
          />
        </div>
      )}

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="text-sm font-medium">Cuts</div>
        </div>
        <div className="space-y-2">
          {cuts.map((c, idx) => (
            <div key={idx} className="grid grid-cols-12 gap-2 items-center">
                <label className="col-span-3 text-xs text-gray-500">Start (mm:ss.ss)
                  <input type="text" className="mt-1 w-full border rounded px-2 py-1 text-sm" value={toMMSS(c.start_ms)}
                    onChange={e=>updateCut(idx,'start_ms', e.target.value)} />
              </label>
                <label className="col-span-3 text-xs text-gray-500">End (mm:ss.ss)
                  <input type="text" className="mt-1 w-full border rounded px-2 py-1 text-sm" value={toMMSS(c.end_ms)}
                    onChange={e=>updateCut(idx,'end_ms', e.target.value)} />
              </label>
                <div className="col-span-3 text-xs text-gray-500">Length: {toMMSS(Math.max(0,(c.end_ms - c.start_ms) || 0))}</div>
              <div className="col-span-3 text-right">
                  <button onClick={()=>removeCut(idx)} className="text-xs px-2 py-1 rounded border">Clear this Cut</button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex gap-2">
        <button onClick={async ()=>{
          const liveCuts = waveRef.current?.getCuts ? waveRef.current.getCuts() : cuts;
          const n = Array.isArray(liveCuts) ? liveCuts.length : 0;
          const plural = n === 1 ? 'this section' : 'these sections';
          if(!window.confirm(`Are you sure you want to cut ${plural}? This action cannot be undone.`)) return;
          await commitEdits();
        }} disabled={saving} className="px-3 py-1 rounded bg-blue-600 text-white text-sm disabled:opacity-50">{saving? 'Saving…':'Commit'}</button>
      </div>

      {/* Preview summary removed per user request */}
    </div>
  );
}
