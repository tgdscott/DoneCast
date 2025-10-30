import React, { useEffect, useMemo, useState } from 'react';
import { fetchVoices } from '@/api/elevenlabs';
import { makeApi } from '@/lib/apiClient';

/**
 * Props:
 *  - value: currently selected voice_id (string | null)
 *  - onChange: (voice_id: string) => void
 *  - onClose: () => void
 */
export default function VoicePicker({ value, onChange, onClose, onSelect, token }) {
  const [q, setQ] = useState('');
  const [list, setList] = useState([]);
  const [loading, setLoading] = useState(false);
  const [selectedId, setSelectedId] = useState(value || null);
  const [playingId, setPlayingId] = useState(null);
  const [genderFilter, setGenderFilter] = useState('any');
  const audioRef = React.useRef(null);

  useEffect(() => {
    setSelectedId(value || null);
  }, [value]);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      try {
        // Prefer authorized call if token is available (AB flows use bearer tokens)
        if (token) {
          const api = makeApi(token);
          const res = await api.get(`/api/elevenlabs/voices?search=${encodeURIComponent(q)}&page=1&size=100`);
          const items = Array.isArray(res?.items) ? res.items : (Array.isArray(res) ? res : []);
          if (!cancelled) setList(items);
        } else {
          const res = await fetchVoices(q, 1, 100);
          if (!cancelled) setList(res.items || []);
        }
      } catch (e) {
        if (!cancelled) setList([]);
        console.error('Failed to load voices:', e);
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, [q, token]);

  // Filter by gender
  const filteredItems = React.useMemo(() => {
    let items = list || [];
    if (genderFilter !== 'any') {
      items = items.filter(v => {
        const gender = v.labels?.gender?.toLowerCase();
        return gender === genderFilter;
      });
    }
    return items;
  }, [list, genderFilter]);

  const compactLabels = (labels) => {
    if (!labels || typeof labels !== 'object') return '';
    // Prefer common keys if present
    const keys = ['gender', 'accent', 'age', 'style'];
    const picked = keys.map(k => labels[k]).filter(Boolean);
    if (picked.length) return picked.join(' · ');
    // Fallback: first 3 key:value pairs
    const pairs = Object.entries(labels).slice(0, 3).map(([k, v]) => `${k}:${v}`);
    return pairs.join(' · ');
  };

  const handleSelect = (itemOrId) => {
    const id = typeof itemOrId === 'string' ? itemOrId : itemOrId?.voice_id;
    const item = typeof itemOrId === 'string' ? null : itemOrId;
    setSelectedId(id);
    try { onChange && onChange(id); } catch {}
    try { onSelect && item && onSelect(item); } catch {}
  };

  const handlePreview = async (voiceId, previewUrl) => {
    if (!previewUrl) return;
    
    // Stop current if playing
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    
    if (playingId === voiceId) {
      // Already playing this voice, stop it
      setPlayingId(null);
      return;
    }
    
    // Play new voice
    const audio = new Audio(previewUrl);
    audio.addEventListener('ended', () => setPlayingId(null));
    audio.addEventListener('error', () => setPlayingId(null));
    audio.play();
    audioRef.current = audio;
    setPlayingId(voiceId);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-white rounded-lg shadow-lg w-full max-w-5xl max-h-[85vh] flex flex-col">
        <div className="px-4 py-3 border-b flex items-center justify-between">
          <h2 className="text-lg font-semibold">Choose a Voice</h2>
          <button onClick={onClose} className="text-sm text-gray-600 hover:text-gray-900">Close</button>
        </div>

        {/* Search and Gender Filter */}
        <div className="p-4 space-y-3">
          <div className="flex gap-3">
            <input
              type="text"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search voices by name or label..."
              className="flex-1 border rounded-md px-3 py-2 focus:outline-none focus:ring"
            />
            <select
              value={genderFilter}
              onChange={(e) => setGenderFilter(e.target.value)}
              className="border rounded-md px-3 py-2 focus:outline-none focus:ring bg-white"
            >
              <option value="any">Any Gender</option>
              <option value="male">Male</option>
              <option value="female">Female</option>
            </select>
          </div>
        </div>

        {/* List - 2 Column Grid */}
        <div className="px-4 pb-4 overflow-y-auto" style={{ maxHeight: '60vh' }}>
          {loading && (
            <div className="text-sm text-gray-500 p-2">Loading…</div>
          )}
          {!loading && filteredItems.length === 0 && (
            <div className="text-sm text-gray-500 p-2">No voices found.</div>
          )}

          <div className="grid grid-cols-2 gap-3">
            {filteredItems.map((v) => {
              const isSelected = selectedId && v.voice_id === selectedId;
              const labelsText = compactLabels(v.labels);
              const canPreview = !!v.preview_url;
              const isPlaying = playingId === v.voice_id;
              const displayName = v.common_name || v.name || 'Unnamed voice';
              return (
                <div key={v.voice_id} className={`border rounded-md p-3 ${isSelected ? 'border-blue-500 ring-1 ring-blue-300' : 'border-gray-200'}`}>
                  <div className="font-medium text-sm">{displayName}</div>
                  {v.description && (
                    <div className="text-xs text-gray-600 mt-0.5 line-clamp-2">{v.description}</div>
                  )}
                  {labelsText && (
                    <div className="text-xs text-gray-500 mt-1">{labelsText}</div>
                  )}
                  <div className="flex items-center gap-2 mt-3">
                    {canPreview && (
                      <button
                        onClick={() => handlePreview(v.voice_id, v.preview_url)}
                        className={`text-xs px-2 py-1 border rounded ${isPlaying ? 'bg-red-50 border-red-300 text-red-700' : 'hover:bg-gray-50'}`}
                      >
                        {isPlaying ? 'Stop' : 'Preview'}
                      </button>
                    )}
                    <button
                      onClick={() => handleSelect(v)}
                      disabled={!!isSelected}
                      className={`text-xs px-2 py-1 border rounded flex-1 ${isSelected ? 'bg-gray-200 text-gray-700 cursor-default' : 'bg-blue-600 text-white hover:bg-blue-700'}`}
                    >
                      {isSelected ? 'Selected' : 'Select'}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
