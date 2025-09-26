import { useEffect, useState } from 'react';
import { makeApi, isApiError } from '@/lib/apiClient';

export default function ManualEditor({ episodeId, token, onClose }) {
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [duration, setDuration] = useState(null);
  const [cuts, setCuts] = useState([]); // [{start_ms,end_ms}]
  const [preview, setPreview] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let live = true;
    (async () => {
      try {
        const api = makeApi(token);
        const j = await api.get(`/api/episodes/${episodeId}/edit-context`);
        if (!live) return;
        setDuration(j?.duration_ms ?? null);
        setCuts(Array.isArray(j?.existing_cuts) ? j.existing_cuts : []);
      } catch (e) {
        const msg = isApiError(e) ? (e.detail || e.error || e.message) : String(e);
        setErr(msg || 'Failed to load edit context');
      } finally {
        setLoading(false);
      }
    })();
    return () => { live = false; };
  }, [episodeId, token]);

  const addCut = () => setCuts(c => [...c, { start_ms: 0, end_ms: 0 }]);
  const updateCut = (idx, key, val) => setCuts(c => c.map((x,i)=> i===idx ? { ...x, [key]: val } : x));
  const removeCut = (idx) => setCuts(c => c.filter((_,i)=> i!==idx));

  const generatePreview = async () => {
    setErr(''); setPreview(null);
    try {
      const api = makeApi(token);
      const j = await api.post(`/api/episodes/${episodeId}/manual-edit/preview`, { cuts });
      setPreview(j);
    } catch (e) {
      const msg = isApiError(e) ? (e.detail || e.error || e.message) : String(e);
      setErr(msg || 'Preview failed');
    }
  };

  const commitEdits = async () => {
    setSaving(true); setErr('');
    try {
      const api = makeApi(token);
      await api.post(`/api/episodes/${episodeId}/manual-edit/commit`, { cuts });
      onClose?.();
      alert('Edit job queued (MVP).');
    } catch (e) {
      const msg = isApiError(e) ? (e.detail || e.error || e.message) : String(e);
      setErr(msg || 'Commit failed');
    } finally { setSaving(false); }
  };

  if (loading) return <div className="p-4 text-sm">Loading editor…</div>;
  return (
    <div className="p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">Manual Editor</h3>
        <button className="text-xs text-gray-500 hover:text-gray-800" onClick={onClose}>Close</button>
      </div>
  {err && <div className="text-xs text-red-600">{typeof err === 'string' ? err : (err.message || 'Error')}</div>}
      <div className="text-xs text-gray-600">Duration: {duration ?? '—'} ms</div>

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="text-sm font-medium">Cuts</div>
          <button onClick={addCut} className="text-xs px-2 py-1 rounded border">+ Add Cut</button>
        </div>
        <div className="space-y-2">
          {cuts.map((c, idx) => (
            <div key={idx} className="grid grid-cols-12 gap-2 items-center">
              <label className="col-span-3 text-xs text-gray-500">Start (ms)
                <input type="number" className="mt-1 w-full border rounded px-2 py-1 text-sm" value={c.start_ms}
                  onChange={e=>updateCut(idx,'start_ms', parseInt(e.target.value||'0',10))} />
              </label>
              <label className="col-span-3 text-xs text-gray-500">End (ms)
                <input type="number" className="mt-1 w-full border rounded px-2 py-1 text-sm" value={c.end_ms}
                  onChange={e=>updateCut(idx,'end_ms', parseInt(e.target.value||'0',10))} />
              </label>
              <div className="col-span-3 text-xs text-gray-500">Length: {Math.max(0,(c.end_ms - c.start_ms) || 0)} ms</div>
              <div className="col-span-3 text-right">
                <button onClick={()=>removeCut(idx)} className="text-xs px-2 py-1 rounded border">Remove</button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex gap-2">
        <button onClick={generatePreview} className="px-3 py-1 rounded bg-gray-800 text-white text-sm">Preview</button>
        <button onClick={commitEdits} disabled={saving} className="px-3 py-1 rounded bg-blue-600 text-white text-sm disabled:opacity-50">{saving? 'Saving…':'Commit'}</button>
      </div>

      {preview && (
        <div className="text-xs text-gray-700 border rounded p-2">
          <div>New duration: {preview.new_duration_ms ?? '—'} ms</div>
          <div className="text-gray-500">Preview contains {preview.cuts?.length || 0} cuts.</div>
        </div>
      )}
    </div>
  );
}
