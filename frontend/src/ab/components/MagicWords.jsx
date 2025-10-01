
import React, { useState } from "react";

export default function MagicWords() {
  const [flubberWord, setFlubberWord] = useState("Flubber");
  const [useFlubberAuto, setUseFlubberAuto] = useState(true);
  const [internWord, setInternWord] = useState("Intern");
  const [autoAccept, setAutoAccept] = useState(false);
  const [useSfxAuto, setUseSfxAuto] = useState(false);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-semibold">Magic words & Intern</h2>
          <p className="text-sm text-muted-foreground">Choose the phrases you’ll say while recording.</p>
        </div>
      </div>

      <div className="rounded-xl border p-4 space-y-3">
        <div className="font-medium">Flubber wake phrase</div>
        <p className="text-sm text-muted-foreground">Say this when you make a mistake. We’ll mark it for an easy fix later.</p>
        <input value={flubberWord} onChange={e=>setFlubberWord(e.target.value)} className="w-full rounded-lg border px-3 py-2" />
        <label className="inline-flex items-center gap-2 text-sm mt-2">
          <input type="checkbox" checked={useFlubberAuto} onChange={()=>setUseFlubberAuto(v=>!v)} /> Use Flubber if detected?
        </label>
      </div>

      <div className="rounded-xl border p-4 space-y-3">
        <div className="font-medium">Intern wake phrase</div>
        <p className="text-sm text-muted-foreground">Use this to ask for actions.</p>
        <input value={internWord} onChange={e=>setInternWord(e.target.value)} className="w-full rounded-lg border px-3 py-2" />
        <label className="inline-flex items-center gap-2 text-sm mt-2">
          <input type="checkbox" checked={autoAccept} onChange={()=>setAutoAccept(v=>!v)} /> Use Intern actions if detected?
        </label>
      </div>

      <div className="rounded-xl border p-4">
        <div className="flex items-center justify-between">
          <div>
            <div className="font-medium">Sound effects on magic phrase</div>
            <div className="text-sm text-muted-foreground">Play a sound effect when your phrase is heard</div>
          </div>
          <label className="inline-flex items-center gap-2 text-sm">
            <input type="checkbox" checked={useSfxAuto} onChange={()=>setUseSfxAuto(v=>!v)} /> Use sound effects if detected?
          </label>
        </div>
        <div className="mt-3 text-xs text-muted-foreground">Tip: Choose unique phrases to avoid false triggers.</div>
      </div>
    </div>
  );
}
