import React, { useEffect, useId, useState } from 'react';
import { Accessibility, Type, Contrast, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useComfort } from '@/ComfortContext.jsx';

export default function ComfortMenu({ inline = false, className = '' }) {
  const { largeText, setLargeText, highContrast, setHighContrast } = useComfort();
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const largeId = useId();
  const contrastId = useId();

  useEffect(() => {
    if (inline || !open) return;
    const onKey = (event) => {
      if (event.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, inline]);

  const settingsContent = (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-4">
        <div className="space-y-1">
          <Label htmlFor={largeId} className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
            <Type className="h-3.5 w-3.5" aria-hidden="true" /> Larger text
          </Label>
          <p id={`${largeId}-hint`} className="text-[11px] text-muted-foreground">Boosts base font size for easier reading.</p>
        </div>
        <Switch id={largeId} checked={largeText} onCheckedChange={setLargeText} aria-describedby={`${largeId}-hint`} />
      </div>
      <div className="flex items-center justify-between gap-4">
        <div className="space-y-1">
          <Label htmlFor={contrastId} className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
            <Contrast className="h-3.5 w-3.5" aria-hidden="true" /> High contrast
          </Label>
          <p id={`${contrastId}-hint`} className="text-[11px] text-muted-foreground">Enhances color contrast and underlines links.</p>
        </div>
        <Switch id={contrastId} checked={highContrast} onCheckedChange={setHighContrast} aria-describedby={`${contrastId}-hint`} />
      </div>
    </div>
  );

  if (inline) {
    const containerClasses = ['rounded-md border bg-white p-4 shadow-sm'];
    if (className) containerClasses.push(className);
    return (
      <div className={containerClasses.join(' ')}>
        <div className="flex items-center justify-between pb-2">
          <div className="flex items-center gap-2">
            <Accessibility className="h-4 w-4 text-primary" aria-hidden="true" />
            <p className="text-sm font-semibold">Display options</p>
          </div>
        </div>
        {settingsContent}
      </div>
    );
  }

  return (
    <div className={`fixed top-4 right-4 z-50 flex flex-col items-end gap-2 text-sm${className ? ` ${className}` : ''}`}>
      <div
        id={panelId}
        className={`w-64 rounded-md border bg-white p-4 shadow-lg transition-all ${open ? 'opacity-100 visible translate-y-0' : 'pointer-events-none invisible -translate-y-2 opacity-0'}`}
        aria-hidden={!open}
      >
        <div className="flex items-center justify-between pb-2">
          <div className="flex items-center gap-2">
            <Accessibility className="h-4 w-4 text-primary" aria-hidden="true" />
            <p className="text-sm font-semibold">Display options</p>
          </div>
          <Button variant="ghost" size="icon" className="h-7 w-7" onClick={() => setOpen(false)} aria-label="Close display options">
            <X className="h-4 w-4" />
          </Button>
        </div>
        {settingsContent}
      </div>
      <Button
        variant={open ? 'secondary' : 'outline'}
        size="sm"
        className="shadow-sm"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        aria-controls={panelId}
      >
        <Accessibility className="mr-2 h-4 w-4" aria-hidden="true" /> Display
      </Button>
    </div>
  );
}
