import React, { useMemo, useState, useEffect } from "react";

/**
 * Lightweight AI Content section for TemplateEditor.
 * No external UI lib required; uses your page's base styles.
 */
export default function TemplateAIContent({ value, onChange, className = "" }) {
  const v = value || { auto_fill_ai: true, title_instructions: "", notes_instructions: "", tags_instructions: "", tags_always_include: [], auto_generate_tags: true };
  const tagsAlwaysStr = useMemo(() => (v.tags_always_include || []).join(", "), [v.tags_always_include]);
  // Local input state so users can type spaces inside a tag without it being trimmed mid-typing
  const [tagsInput, setTagsInput] = useState(tagsAlwaysStr);
  useEffect(() => {
    // Keep local input in sync when external value changes
    setTagsInput(tagsAlwaysStr);
  }, [tagsAlwaysStr]);
  const commitTags = (rawStr) => {
    const list = (rawStr || "")
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    const seen = new Set();
    const dedup = [];
    for (const t of list) {
      const k = t.toLowerCase();
      if (!seen.has(k)) {
        seen.add(k);
        dedup.push(t);
        if (dedup.length >= 20) break; // soft cap
      }
    }
    setTagsInput(dedup.join(", "));
    onChange?.({ ...v, tags_always_include: dedup });
  };
  const set = (patch) => onChange?.({ ...v, ...patch });

  return (
    <div className={`space-y-4 ${className}`}>
      <div className="rounded-lg border border-blue-200 bg-blue-50 p-4">
        <h4 className="text-sm font-semibold text-blue-900 mb-2">📝 Template Variables</h4>
        <p className="text-sm text-blue-800 mb-3">
          <strong>AI already has base prompts</strong> - only add podcast-specific instructions here. 
          Use these variables in your instructions to personalize AI output:
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-blue-800 font-mono">
          <div><code className="bg-blue-100 px-1 py-0.5 rounded">{"{friendly_name}"}</code> - Audio file name</div>
          <div><code className="bg-blue-100 px-1 py-0.5 rounded">{"{season_number}"}</code> - Episode season</div>
          <div><code className="bg-blue-100 px-1 py-0.5 rounded">{"{episode_number}"}</code> - Episode number</div>
          <div><code className="bg-blue-100 px-1 py-0.5 rounded">{"{podcast_name}"}</code> - Show name</div>
          <div><code className="bg-blue-100 px-1 py-0.5 rounded">{"{duration_minutes}"}</code> - Audio length</div>
          <div><code className="bg-blue-100 px-1 py-0.5 rounded">{"{filename}"}</code> - Original filename</div>
          <div><code className="bg-blue-100 px-1 py-0.5 rounded">{"{date}"}</code> - Date (YYYY-MM-DD)</div>
          <div><code className="bg-blue-100 px-1 py-0.5 rounded">{"{year}"}</code> - Year</div>
        </div>
        <p className="text-sm text-blue-800 mt-3">
          <strong>Example:</strong> "The movie title is {"{friendly_name}"}. Format title as: S{"{season_number}"}E{"{episode_number}"} – {"{friendly_name}"}"
        </p>
      </div>
      
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h3 className="text-base font-semibold text-slate-800">AI Content defaults</h3>
        <label className="inline-flex items-center gap-2 text-sm text-slate-700">
          <input type="checkbox" checked={!!v.auto_fill_ai} onChange={(e)=> set({ auto_fill_ai: !!e.target.checked })} />
          <span>Auto fill fields with AI suggestions?</span>
        </label>
      </div>

      <div className="space-y-1">
        <label className="text-sm font-medium text-slate-700">Title instructions</label>
        <textarea className="w-full rounded border border-slate-300 px-3 py-2" rows={3}
          placeholder='e.g., The movie title is {friendly_name}. Format: "S{season_number}E{episode_number} – {friendly_name} – [your hook]". Keep ≤ 80 chars.'
          value={v.title_instructions || ""}
          onChange={(e)=> set({ title_instructions: e.target.value })} />
      </div>

      <div className="space-y-1">
        <label className="text-sm font-medium text-slate-700">Notes/Description instructions</label>
        <textarea className="w-full rounded border border-slate-300 px-3 py-2" rows={4}
          placeholder='e.g., Start with "In this episode of {podcast_name}, we discuss {friendly_name}..." Use snarky tone. Include time-stamped highlights.'
          value={v.notes_instructions || ""}
          onChange={(e)=> set({ notes_instructions: e.target.value })} />
      </div>

      <div className="space-y-1">
        <label className="text-sm font-medium text-slate-700">Tags instructions (optional)</label>
        <textarea className="w-full rounded border border-slate-300 px-3 py-2" rows={3}
          placeholder='e.g., Always include {friendly_name} as a tag. Focus on movie, director, year. No spoilers.'
          value={v.tags_instructions || ""}
          onChange={(e)=> set({ tags_instructions: e.target.value })} />
      </div>

      <div className="space-y-1">
        <label className="inline-flex items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={v.auto_generate_tags === false}
            onChange={(e) => set({ auto_generate_tags: e.target.checked ? false : true })}
          />
          <span>Do not automatically generate tags</span>
        </label>
        <p className="text-xs text-muted-foreground">When checked, the system will not auto-generate tags for episodes using this template.</p>
      </div>

      <div className="space-y-1">
        <label className="text-sm font-medium text-slate-700">Always include these tags (comma-separated)</label>
        <input className="w-full rounded border border-slate-300 px-3 py-2"
          placeholder="e.g., star wars, podcast, film"
          value={tagsInput}
          onChange={(e)=> {
            setTagsInput(e.target.value);
          }}
          onBlur={() => commitTags(tagsInput)}
          onKeyDown={(e) => {
            // Allow commas to be typed; commit on Enter only
            if (e.key === "Enter") {
              e.preventDefault();
              commitTags(tagsInput);
            }
          }}
        />
        <p className="text-xs text-muted-foreground">We’ll add these first, then the AI fills the rest (max 20 total; each ≤ 30 chars).</p>
      </div>
    </div>
  );
}
