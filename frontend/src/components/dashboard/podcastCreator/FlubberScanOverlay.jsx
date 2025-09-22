import React from 'react';
import { Button } from '../../ui/button';
import { Loader2 } from 'lucide-react';

export default function FlubberScanOverlay({ open, onSkip }) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-md p-6 shadow-lg flex flex-col items-center gap-3">
        <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
        <div className="text-sm text-gray-700">Scanning for retakes (this can take a few minutes on long audio)…</div>
        <div className="flex gap-2 mt-2">
          <Button variant="outline" size="sm" onClick={onSkip}>
            Skip for now
          </Button>
        </div>
      </div>
    </div>
  );
}
