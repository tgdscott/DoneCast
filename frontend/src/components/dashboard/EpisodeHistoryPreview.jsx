import { useState, useRef } from 'react';
import { assetUrl } from '@/lib/apiClient.js';
import { Play, Pause, CalendarClock, Trash2, Pencil, MoreHorizontal } from 'lucide-react';

/**
 * Experimental preview for a refreshed Episode History UI.
 * Purely presentational: no mutations; uses provided callbacks for actions.
 * Shows:
 *  - Dense card (grid) layout with square cover, hover overlay actions
 *  - Inline micro player (prototype) with simple play/pause per episode
 */
export default function EpisodeHistoryPreview({ episodes, onEdit, onDelete, formatPublishAt }) {
  const [playingId, setPlayingId] = useState(null);
  const audioRefs = useRef({});

  const resolveAssetUrl = (path) => {
    if (!path || typeof path !== 'string') return path;
    const trimmed = path.trim();
    if (!trimmed) return trimmed;
    if (/^[a-z][a-z0-9+.-]*:/i.test(trimmed) || trimmed.startsWith('//')) return trimmed;
    return assetUrl(trimmed);
  };

  const togglePlay = (epId) => {
    if (playingId && playingId !== epId) {
      const prev = audioRefs.current[playingId];
      if (prev) { try { prev.pause(); prev.currentTime = 0; } catch {} }
    }
    const el = audioRefs.current[epId];
    if (!el) return;
    if (playingId === epId && !el.paused) {
      el.pause();
      setPlayingId(null);
    } else {
      try { el.play(); setPlayingId(epId); } catch {}
    }
  };

  return (
    <div className="space-y-8">
      <section>
        <h3 className="text-lg font-semibold mb-3">New Grid Concept</h3>
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-4">
          {episodes.slice(0,15).map(ep => {
            const coverUrl = resolveAssetUrl(ep.cover_url) || resolveAssetUrl(`/api/episodes/${ep.id}/cover`);
            return (
              <div key={ep.id} className="group relative rounded-lg overflow-hidden border bg-white shadow-sm hover:shadow-md transition-shadow">
                <div className="aspect-square bg-gray-100 relative">
                  <img src={coverUrl} alt="cover" className="absolute inset-0 w-full h-full object-cover" />
                  <div className="absolute inset-0 bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col justify-between p-2 text-white">
                    <div className="flex justify-end gap-1">
                      <button onClick={()=>onEdit?.(ep)} className="bg-white/20 hover:bg-white/30 rounded p-1" title="Edit"><Pencil className="w-4 h-4"/></button>
                      <button onClick={()=>onDelete?.(ep)} className="bg-white/20 hover:bg-white/30 rounded p-1" title="Delete"><Trash2 className="w-4 h-4"/></button>
                      <button className="bg-white/20 hover:bg-white/30 rounded p-1" title="More"><MoreHorizontal className="w-4 h-4"/></button>
                    </div>
                    <div>
                      <button
                        onClick={()=>togglePlay(ep.id)}
                        className="bg-white/25 hover:bg-white/40 rounded-full w-10 h-10 flex items-center justify-center mx-auto mb-2"
                        title="Play preview"
                      >
                        {playingId === ep.id ? <Pause className="w-5 h-5"/> : <Play className="w-5 h-5 ml-0.5"/>}
                      </button>
                      <div className="text-center text-[10px] font-medium line-clamp-2 leading-tight">{ep.title || 'Untitled'}</div>
                    </div>
                  </div>
                </div>
                <div className="p-2 space-y-1">
                  <div className="text-xs font-semibold leading-snug line-clamp-2" title={ep.title}>{ep.title || 'Untitled Episode'}</div>
                  <div className="text-[10px] text-gray-500 flex items-center gap-1" title={ep.publish_at || ''}>
                    {ep.publish_at && <CalendarClock className="w-3 h-3"/>}
                    {ep.publish_at ? formatPublishAt(ep.publish_at) : '-'}
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={()=>togglePlay(ep.id)}
                      className={`text-[10px] px-2 py-1 rounded border inline-flex items-center gap-1 ${playingId===ep.id ? 'bg-blue-600 text-white border-blue-600' : 'hover:bg-gray-100'}`}
                    >
                      {playingId === ep.id ? <Pause className="w-3 h-3"/> : <Play className="w-3 h-3"/>}
                      {playingId === ep.id ? 'Pause' : 'Play'}
                    </button>
                    {typeof ep.plays_total === 'number' && <span className="text-[10px] text-gray-500">{ep.plays_total} plays</span>}
                  </div>
                  <audio
                    ref={el => { if (el) audioRefs.current[ep.id] = el; }}
                    src={resolveAssetUrl(ep.playback_url || ep.stream_url || ep.final_audio_url || '') || ''}
                    preload="none"
                    onEnded={()=> setPlayingId(id => id===ep.id ? null : id)}
                    className="hidden"
                  />
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section>
        <h3 className="text-lg font-semibold mb-3">New List Concept (Micro Player)</h3>
        <div className="bg-white border rounded-md overflow-hidden divide-y">
          {episodes.slice(0,20).map(ep => {
            const playing = playingId === ep.id;
            return (
              <div key={ep.id} className="flex items-stretch gap-3 px-3 py-2 hover:bg-gray-50 text-sm">
                <button
                  onClick={()=>togglePlay(ep.id)}
                  className={`mt-0.5 rounded-full w-8 h-8 flex items-center justify-center border ${playing ? 'bg-blue-600 text-white border-blue-600' : 'hover:bg-gray-100'}`}
                >
                  {playing ? <Pause className="w-4 h-4"/> : <Play className="w-4 h-4 ml-0.5"/>}
                </button>
                <div className="flex-1 min-w-0">
                  <div className="flex items-start justify-between gap-2">
                    <div className="font-medium truncate" title={ep.title}>{ep.title || 'Untitled Episode'}</div>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button onClick={()=>onEdit?.(ep)} className="text-[11px] text-blue-600 hover:underline">Edit</button>
                      <button onClick={()=>onDelete?.(ep)} className="text-[11px] text-red-600 hover:underline">Delete</button>
                    </div>
                  </div>
                  {ep.description && <div className="text-[11px] text-gray-500 line-clamp-1" title={ep.description}>{ep.description}</div>}
                  <div className="mt-1 flex items-center gap-4 text-[10px] text-gray-500">
                    {ep.publish_at && <span>{formatPublishAt(ep.publish_at)}</span>}
                    {typeof ep.plays_total === 'number' && <span>{ep.plays_total} plays</span>}
                    {ep.status && <span className="uppercase tracking-wide text-[9px] font-semibold px-1.5 py-0.5 rounded bg-gray-100 border">{ep.status}</span>}
                  </div>
                  <audio
                    ref={el => { if (el) audioRefs.current[ep.id] = el; }}
                    src={resolveAssetUrl(ep.playback_url || ep.stream_url || ep.final_audio_url || '') || ''}
                    preload="none"
                    onEnded={()=> setPlayingId(id => id===ep.id ? null : id)}
                    className="hidden"
                  />
                </div>
              </div>
            )
          })}
          {episodes.length === 0 && (
            <div className="px-3 py-6 text-center text-xs text-gray-500">No episodes loaded.</div>
          )}
        </div>
      </section>
    </div>
  );
}
