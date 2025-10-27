'use client';

import { useId, useState } from 'react';
import { ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';

export function SectionCard({ icon, number, title, subtitle, defaultOpen = true, variant = "default", children }) {
  const [open, setOpen] = useState(defaultOpen);
  const bodyId = useId();
  
  const isDanger = variant === "danger";
  
  const Badge = () => {
    if (icon) {
      return (
        <span className={cn(
          "flex h-10 w-10 items-center justify-center rounded-2xl text-white",
          isDanger ? "bg-red-600/90" : "bg-slate-900/90"
        )}>
          {icon}
        </span>
      );
    }
    if (typeof number !== 'undefined') {
      return (
        <span className={cn(
          "flex h-9 w-9 items-center justify-center rounded-2xl text-sm font-semibold text-white",
          isDanger ? "bg-red-600" : "bg-slate-900"
        )}>
          {number}
        </span>
      );
    }
    return null;
  };

  return (
    <section className={cn(
      "rounded-3xl border shadow-sm",
      isDanger 
        ? "border-red-200 bg-red-50/50" 
        : "border-slate-200 bg-white/80"
    )}>
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left"
        aria-expanded={open}
        aria-controls={bodyId}
      >
        <div className="flex items-center gap-3">
          <Badge />
          <div>
            <h3 className={cn(
              "text-lg font-semibold",
              isDanger ? "text-red-900" : "text-slate-900"
            )}>{title}</h3>
            {subtitle && <p className={cn(
              "text-sm",
              isDanger ? "text-red-700" : "text-muted-foreground"
            )}>{subtitle}</p>}
          </div>
        </div>
        <ChevronDown
          className={cn(
            'h-5 w-5 transition-transform duration-200',
            open ? 'rotate-180' : '',
            isDanger ? "text-red-500" : "text-slate-500"
          )}
          aria-hidden="true"
        />
      </button>
      {open && (
        <div id={bodyId} className={cn(
          "space-y-4 border-t px-5 pb-5 pt-4",
          isDanger ? "border-red-100" : "border-slate-100"
        )}>
          {children}
        </div>
      )}
    </section>
  );
}

export function SectionItem({ icon, title, description, action, children }) {
  return (
    <div className="rounded-2xl border border-slate-200 bg-white/90 p-4 shadow-sm">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-slate-900/90 text-white">
              {icon}
            </span>
            <h4 className="text-base font-semibold text-slate-900">{title}</h4>
          </div>
          {description && <p className="mt-2 text-sm text-muted-foreground">{description}</p>}
        </div>
        {action && <div className="sm:pt-1">{action}</div>}
      </div>
      {children && <div className="mt-4 space-y-3 text-sm text-slate-700">{children}</div>}
    </div>
  );
}
