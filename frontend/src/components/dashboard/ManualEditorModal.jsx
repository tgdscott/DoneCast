import { useEffect, useState, useMemo } from 'react';
import ManualEditor from './ManualEditor';

export default function ManualEditorModal({ episodeId, token, onClose }) {
  // Trap focus and make full-screen modal
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose?.(); };
    document.addEventListener('keydown', onKey);
    document.body.style.overflow = 'hidden';
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = ''; };
  }, [onClose]);
  return (
    <div className="fixed inset-0 z-[1000]">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="absolute inset-4 bg-white rounded shadow-xl flex flex-col">
        <div className="p-3 border-b flex items-center justify-between">
          <div className="font-semibold">Manual Editor</div>
          <button className="text-sm px-2 py-1 border rounded" onClick={onClose}>Close</button>
        </div>
        <div className="flex-1 overflow-auto">
          <ManualEditor episodeId={episodeId} token={token} onClose={onClose} />
        </div>
      </div>
    </div>
  );
}
