import React from 'react';
import { Pencil } from 'lucide-react';
import { cn } from '@/lib/utils';

export default function EditRecordingButton({ onClick, className }) {
  return (
    <button
      type="button"
      title="Edit Recording"
      aria-label="Edit Recording"
      onClick={onClick}
      className={cn(
        'absolute bottom-2 right-2 z-20 bg-white/90 hover:bg-white text-gray-700 border border-gray-300 shadow-sm rounded-full w-9 h-9 flex items-center justify-center transition-colors',
        className
      )}
    >
      <Pencil className="w-4 h-4" />
    </button>
  );
}
