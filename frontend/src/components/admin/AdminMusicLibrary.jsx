import React, { useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Play, Pause, Plus, Trash2, Save, Upload as UploadIcon, Link as LinkIcon } from 'lucide-react';
import { useAuth } from '@/AuthContext';
import { useToast } from '@/hooks/use-toast';
import { makeApi, buildApiUrl } from '@/lib/apiClient';

export default function AdminMusicLibrary() {
  const { token } = useAuth();
  const { toast } = useToast();
  const [assets, setAssets] = useState([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [previewingId, setPreviewingId] = useState(null);
  const [uploadProgress, setUploadProgress] = useState({});
  const audioRef = useRef(null);

  const loadAssets = async () => {
    setLoading(true);
    try {
      // Use public listing which provides preview_url and existence checks
      const data = await makeApi(token).get('/api/music/assets');
      setAssets(Array.isArray(data?.assets) ? data.assets : []);
    } catch {
      setAssets([]);
    } finally { setLoading(false); }
  };

  useEffect(() => { loadAssets(); }, []);

  const togglePreview = (asset) => {
    const url = asset.preview_url || asset.url || asset.filename;
    if (!url) return;
    if (previewingId === asset.id) {
      try { audioRef.current?.pause(); } catch {}
      audioRef.current = null;
      setPreviewingId(null);
      return;
    }
    try {
      if (audioRef.current) { try { audioRef.current.pause(); } catch {} }
      const a = new Audio(url);
      audioRef.current = a;
      setPreviewingId(asset.id);
      const stopAt = 20;
      const onTick = () => {
        if (a.currentTime >= stopAt) { a.pause(); setPreviewingId(null); a.removeEventListener('timeupdate', onTick); }
      };
      a.addEventListener('timeupdate', onTick);
      a.onended = () => { setPreviewingId(null); try{ a.removeEventListener('timeupdate', onTick);}catch{} };
      a.play().catch(()=> setPreviewingId(null));
    } catch { setPreviewingId(null); }
  };

  const addBlank = () => {
    setAssets(prev => [{ id: `new-${Date.now()}`, display_name: '', mood_tags: [], url: '', filename: '', isNew: true }, ...prev]);
  };

  const removeAsset = async (asset) => {
    if (String(asset.id).startsWith('new-')) {
      setAssets(prev => prev.filter(a => a.id !== asset.id));
      return;
    }
    if (!confirm('Delete this music asset?')) return;
    try {
      await makeApi(token).del(`/api/admin/music/assets/${asset.id}`);
      await loadAssets();
      try { toast({ title: 'Deleted', description: `${asset.display_name || 'Asset'} removed.` }); } catch {}
    } catch (e) {
      try { toast({ title: 'Delete failed', description: 'Could not remove asset', variant: 'destructive' }); } catch {}
    }
  };

  const updateField = (id, key, value) => {
    setAssets(prev => prev.map(a => a.id === id ? { ...a, [key]: value } : a));
  };

  const setFileFor = (id, file) => {
    setAssets(prev => prev.map(a => a.id === id ? { ...a, _file: file } : a));
  };

  const updateProgress = (id, data) => {
    setUploadProgress(prev => ({ ...prev, [id]: data }));
  };

  const clearProgressLater = (id, delay = 800) => {
    setTimeout(() => {
      setUploadProgress(prev => {
        const next = { ...prev };
        delete next[id];
        return next;
      });
    }, delay);
  };

  const uploadFile = async (asset) => {
    if (!asset._file) {
      try { toast({ title: 'No file selected', variant: 'destructive' }); } catch {}
      return;
    }
    setSaving(true);
    try {
      const fd = new FormData();
      fd.append('file', asset._file);
      if (asset.display_name) fd.append('display_name', asset.display_name);
      if (Array.isArray(asset.mood_tags) && asset.mood_tags.length) fd.append('mood_tags', JSON.stringify(asset.mood_tags));

      updateProgress(asset.id, { state: 'uploading', percent: 0 });

      await new Promise((resolve, reject) => {
        try {
          const xhr = new XMLHttpRequest();
          xhr.open('POST', buildApiUrl('/api/admin/music/assets/upload'));
          if (token) {
            xhr.setRequestHeader('Authorization', `Bearer ${token}`);
          }
          xhr.upload.onprogress = (event) => {
            if (!event.lengthComputable) return;
            const pct = Math.min(100, Math.round((event.loaded / event.total) * 100));
            updateProgress(asset.id, { state: 'uploading', percent: pct });
          };
          xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
              updateProgress(asset.id, { state: 'complete', percent: 100 });
              resolve();
            } else {
              let message = 'Upload failed';
              try {
                const parsed = JSON.parse(xhr.responseText);
                message = parsed?.detail || parsed?.message || message;
              } catch {}
              updateProgress(asset.id, { state: 'error', percent: 0, message });
              reject(new Error(message));
            }
          };
          xhr.onerror = () => {
            const message = 'Network error while uploading';
            updateProgress(asset.id, { state: 'error', percent: 0, message });
            reject(new Error(message));
          };
          xhr.onabort = () => {
            const message = 'Upload cancelled';
            updateProgress(asset.id, { state: 'error', percent: 0, message });
            reject(new Error(message));
          };
          xhr.send(fd);
        } catch (err) {
          reject(err instanceof Error ? err : new Error('Upload failed'));
        }
      });
      try { toast({ title: 'Uploaded', description: `${asset.display_name || asset._file.name} uploaded.` }); } catch {}
      await loadAssets();
      clearProgressLater(asset.id);
    } catch (e) {
      updateProgress(asset.id, { state: 'error', percent: 0, message: e?.message || 'Upload failed' });
      try { toast({ title: 'Upload failed', description: e.message || 'Could not upload file', variant: 'destructive' }); } catch {}
    } finally { setSaving(false); }
  };

  const importFromUrl = async (asset) => {
    if (!asset.url || !/^https?:\/\//i.test(asset.url)) {
      try { toast({ title: 'Enter a valid URL first', variant: 'destructive' }); } catch {}
      return;
    }
    setSaving(true);
    try {
      await makeApi(token).post('/api/admin/music/assets/import-url', {
        display_name: asset.display_name || 'Track',
        source_url: asset.url,
        mood_tags: asset.mood_tags || [],
      });
      try { toast({ title: 'Imported', description: 'Track downloaded and added.' }); } catch {}
      await loadAssets();
    } catch (e) {
      try { toast({ title: 'Import failed', description: e.message || 'Could not import from URL', variant: 'destructive' }); } catch {}
    } finally { setSaving(false); }
  };

  const saveAsset = async (asset) => {
    // For new assets, decide whether to upload or import.
    if (String(asset.id).startsWith('new-')) {
      if (asset._file) {
        await uploadFile(asset);
      } else if (asset.url && /^https?:\/\//i.test(asset.url)) {
        await importFromUrl(asset);
      } else {
        toast({ title: 'Action Required', description: 'Please select a file to upload or provide a full URL to import.', variant: 'destructive' });
      }
      return;
    }

    // For existing assets, update metadata.
    setSaving(true);
    try {
      const body = { display_name: asset.display_name, mood_tags: asset.mood_tags || [] };
      await makeApi(token).put(`/api/admin/music/assets/${asset.id}`, body);
      toast({ title: 'Saved', description: 'Music asset updated.' });
      await loadAssets();
    } catch (e) {
      toast({ title: 'Save failed', description: e.message || 'Could not save asset', variant: 'destructive' });
    } finally { setSaving(false); }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Music Library</h2>
        <div className="flex items-center gap-2">
          <Button onClick={addBlank}><Plus className="h-4 w-4 mr-1" /> Add New</Button>
          <Button variant="outline" onClick={loadAssets} disabled={loading}>Refresh</Button>
        </div>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Assets {loading && <span className="text-xs text-muted-foreground">(Loading…)</span>}</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[48px]"></TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Source URL</TableHead>
                <TableHead>Or Upload File</TableHead>
                <TableHead>Mood Tags (comma-separated)</TableHead>
                <TableHead className="w-[140px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {assets.map(a => {
                const canPreview = !!(a.preview_url || a.url || a.filename);
                const moods = Array.isArray(a.mood_tags) ? a.mood_tags.join(', ') : (a.mood_tags || '');
                const progress = uploadProgress[a.id];
                return (
                  <TableRow key={a.id}>
                    <TableCell>
                      <Button size="icon" variant="outline" disabled={!canPreview} onClick={() => canPreview && togglePreview(a)}>
                        {previewingId === a.id ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                      </Button>
                    </TableCell>
                    <TableCell>
                      <Input value={a.display_name || ''} onChange={(e)=> updateField(a.id, 'display_name', e.target.value)} placeholder="Display name" />
                    </TableCell>
                    {a.isNew ? (
                      <>
                        <TableCell>
                          <Input value={a.url || ''} onChange={(e) => updateField(a.id, 'url', e.target.value)} placeholder="https://.../track.mp3" />
                          {progress && progress.state === 'error' && !a._file && (
                            <div className="text-xs text-red-500 mt-1">{progress.message || 'Upload failed'}</div>
                          )}
                        </TableCell>
                        <TableCell>
                          <input type="file" accept="audio/*" onChange={(e) => setFileFor(a.id, e.target.files?.[0] || null)} />
                          {progress && (
                            <div className="mt-2 space-y-1">
                              <div className="h-2 bg-muted rounded overflow-hidden">
                                <div
                                  className={`h-2 ${progress.state === 'error' ? 'bg-red-500' : 'bg-blue-500'}`}
                                  style={{ width: `${progress.percent}%` }}
                                />
                              </div>
                              <div className="text-xs text-muted-foreground">
                                {progress.state === 'error'
                                  ? (progress.message || 'Upload failed')
                                  : progress.percent === 100
                                    ? 'Processing…'
                                    : `${progress.percent}%`}
                              </div>
                            </div>
                          )}
                        </TableCell>
                      </>
                    ) : (
                      <>
                        <TableCell><span className="text-xs text-muted-foreground truncate" title={a.url}>{a.url || 'N/A'}</span></TableCell>
                        <TableCell><span className="text-xs text-muted-foreground">Existing file</span></TableCell>
                      </>
                    )}
                    <TableCell>
                      <Input value={moods} onChange={(e)=> updateField(a.id, 'mood_tags', e.target.value.split(',').map(s=>s.trim()).filter(Boolean))} placeholder="calm, upbeat, cinematic" />
                    </TableCell>
                    <TableCell className="flex items-center gap-2">
                      {a.isNew ? (
                        <Button size="sm" onClick={() => saveAsset(a)} disabled={saving || !(a._file || a.url)}><Plus className="h-4 w-4 mr-1" /> Create</Button>
                      ) : (
                        <Button size="sm" onClick={() => saveAsset(a)} disabled={saving}><Save className="h-4 w-4 mr-1" /> Save</Button>
                      )}
                      <Button size="sm" variant="destructive" onClick={()=> removeAsset(a)}><Trash2 className="h-4 w-4 mr-1" /> Delete</Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
