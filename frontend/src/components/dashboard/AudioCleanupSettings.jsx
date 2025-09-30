import React, { useState, useEffect, useCallback } from "react";
// 'Waveform' is not exported by lucide-react in the installed version; use a stable icon instead.
import { RefreshCw, Save, Activity as WaveIcon, Sparkles, Scissors, Eraser, Shield, RotateCcw, Bot, Trash2 } from "lucide-react";
import { useAuth } from "@/AuthContext";
import { makeApi, coerceArray } from "@/lib/apiClient";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SectionCard, SectionItem } from "@/components/dashboard/SettingsSections";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const DEFAULT_SETTINGS = {
  removeFillers: true,
  fillerWords: ["um", "uh", "like"],
  fillerLeadTrimMs: 100,
  removePauses: true,
  maxPauseSeconds: 1.8,
  targetPauseSeconds: 0.6,
  censorEnabled: false,
  censorWords: [],
  censorFuzzy: true,
  censorMatchThreshold: 0.8,
  commands: {
    flubber: { action: "rollback_restart", trigger_keyword: "flubber" },
    intern: {
      action: "ai_command",
      trigger_keyword: "intern",
      end_markers: ["stop", "stop intern"],
      remove_end_marker: true,
      keep_command_token_in_transcript: true,
    },
  },
};

const BEEP_MS = 250;
const BEEP_FREQ = 1000;
const BEEP_GAIN_DB = 0;

function tokenizeVariants(value) {
  if (!value) return [];
  return value
    .split(/[|,]/)
    .map((v) => v.trim())
    .filter(Boolean)
    .filter((v, i, arr) => arr.indexOf(v) === i);
}

export default function AudioCleanupSettings({ className }) {
  const { token } = useAuth();
  const [settings, setSettings] = useState(null);  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [sfxOptions, setSfxOptions] = useState([]);

  const load = useCallback(async () => {    setError(null);
    try {
      const data = await makeApi(token).get("/api/users/me/audio-cleanup-settings");
      const raw = data?.settings || {};
      const base = raw && Object.keys(raw).length ? raw : DEFAULT_SETTINGS;
      const merged = {
        ...base,
        commands: { ...DEFAULT_SETTINGS.commands, ...(base.commands || {}) },
      };
      setSettings(merged);
      setDirty(false);
    } catch (err) {
      setError(err?.message || String(err));
      if (!settings) setSettings(DEFAULT_SETTINGS);
    } finally {    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const run = async () => {
      try {
        const files = coerceArray(await makeApi(token).get("/api/media/"));
        if (!files.length) return;
        const sfx = files.filter((f) => f.category === "sfx");
        const opts = sfx.map((f) => ({
          id: f.id,
          label: f.friendly_name || (f.filename?.split("_").slice(1).join("_") || f.filename),
          value: `media_uploads/${f.filename}`,
        }));
        setSfxOptions(opts);
      } catch {}
    };
    run();
  }, [token]);

  useEffect(() => {
    if (!settings?.censorEnabled) return;
    const needsFix =
      settings.censorBeepMs !== BEEP_MS ||
      settings.censorBeepFreq !== BEEP_FREQ ||
      settings.censorBeepGainDb !== BEEP_GAIN_DB;
    if (needsFix) {
      setSettings((prev) =>
        prev
          ? {
              ...prev,
              censorBeepMs: BEEP_MS,
              censorBeepFreq: BEEP_FREQ,
              censorBeepGainDb: BEEP_GAIN_DB,
            }
          : prev
      );
      setDirty(true);
    }
  }, [settings?.censorEnabled]);

  const update = (patch) => {
    setSettings((prev) => {
      const next = { ...(prev || {}), ...patch };
      return next;
    });
    setDirty(true);
  };

  const updateCommand = (name, patch) => {
    setSettings((prev) => {
      const next = {
        ...(prev || {}),
        commands: {
          ...(prev?.commands || {}),
          [name]: { ...(prev?.commands?.[name] || {}), ...patch },
        },
      };
      return next;
    });
    setDirty(true);
  };

  const save = async () => {
    if (!settings) return;
    setSaving(true);
    setError(null);
    try {
      const payload = { settings };
      const response = await makeApi(token).put("/api/users/me/audio-cleanup-settings", payload);
      if (response && response.status && response.status >= 400) {
        throw new Error("Save failed");
      }
      setDirty(false);
    } catch (err) {
      setError(err?.message || String(err));
    } finally {
      setSaving(false);
    }
  };

  if (!settings) {
    return (
      <div className={cn("space-y-6", className)}>
  <SectionCard icon={<WaveIcon className="h-5 w-5 text-white" />} title="Audio Improvements" subtitle="Loading your presets..." defaultOpen>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <RefreshCw className="h-4 w-4 animate-spin" />
            Loading audio tools...
          </div>
        </SectionCard>
        <SectionCard icon={<Sparkles className="h-5 w-5 text-white" />} title="Magic Words" subtitle="Loading your commands..." defaultOpen>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <RefreshCw className="h-4 w-4 animate-spin" />
            Loading magic words...
          </div>
        </SectionCard>
      </div>
    );
  }

  const commandEntries = Object.entries(settings.commands || {});
  const customCommands = commandEntries.filter(([name]) => !["flubber", "intern"].includes(name));

  return (
    <div className={cn("space-y-6", className)}>
      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <SectionCard
  icon={<WaveIcon className="h-5 w-5 text-white" />}
        title="Audio Improvements"
        subtitle="Keep every episode tight, even if you are recording live."
        defaultOpen
      >
        <SectionItem
          icon={<RotateCcw className="h-4 w-4 text-white" />}
          title="Trim pauses"
          description="Shorten long silences automatically so conversations flow."
        >
          <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white px-4 py-3">
            <div className="text-sm text-slate-700">Shorten long pauses</div>
            <Switch checked={!!settings.removePauses} onCheckedChange={(value) => update({ removePauses: value })} />
          </div>
          {settings.removePauses && (
            <div className="grid gap-4 pt-4 sm:grid-cols-2">
              <div className="space-y-1">
                <Label className="text-xs text-slate-500">Cut anything longer than (seconds)</Label>
                <Input
                  type="number"
                  step="0.1"
                  min="0.4"
                  value={settings.maxPauseSeconds ?? 1.8}
                  onChange={(event) => update({ maxPauseSeconds: parseFloat(event.target.value || "0") })}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-slate-500">Target pause length after cleanup (seconds)</Label>
                <Input
                  type="number"
                  step="0.1"
                  min="0.2"
                  value={settings.targetPauseSeconds ?? 0.6}
                  onChange={(event) => update({ targetPauseSeconds: parseFloat(event.target.value || "0") })}
                />
              </div>
            </div>
          )}
        </SectionItem>

        <SectionItem
          icon={<Eraser className="h-4 w-4 text-white" />}
          title="Eliminate filler words"
          description={'Let Flubber tidy the little "ums" and "uhs" without touching your tone.'}
        >
          <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white px-4 py-3">
            <div className="text-sm text-slate-700">Remove filler words</div>
            <Switch
              checked={!!settings.removeFillers}
              onCheckedChange={(value) => update({ removeFillers: value })}
            />
          </div>
          {settings.removeFillers && (
            <div className="space-y-4 pt-4">
              <div className="space-y-1">
                <Label className="text-xs text-slate-500">Words or phrases to clip</Label>
                <TagInput
                  values={settings.fillerWords || []}
                  onChange={(vals) => update({ fillerWords: vals })}
                  placeholder="Type a word and press Enter"
                />
              </div>
              <div className="max-w-sm space-y-1">
                <Label className="text-xs text-slate-500">Trim a little extra before each cut (ms)</Label>
                <Input
                  type="number"
                  min="0"
                  value={settings.fillerLeadTrimMs ?? 100}
                  onChange={(event) => update({ fillerLeadTrimMs: parseInt(event.target.value || "0", 10) })}
                />
                <p className="text-xs text-muted-foreground">
                  Helpful if you tend to start over mid-syllable.
                </p>
              </div>
            </div>
          )}
        </SectionItem>

        <SectionItem
          icon={<Shield className="h-4 w-4 text-white" />}
          title="Censor unwanted words"
          description="Bleep specific words or phrases before you publish."
        >
          <div className="flex items-center justify-between rounded-2xl border border-slate-200 bg-white px-4 py-3">
            <div className="text-sm text-slate-700">Turn censoring on</div>
            <Switch checked={!!settings.censorEnabled} onCheckedChange={(value) => update({ censorEnabled: value })} />
          </div>
          {settings.censorEnabled && (
            <div className="space-y-4 pt-4">
              <div className="space-y-1">
                <Label className="text-xs text-slate-500">Words or phrases to bleep</Label>
                <TagInput
                  values={settings.censorWords || []}
                  onChange={(vals) => update({ censorWords: vals })}
                  placeholder="Type a word and press Enter"
                />
              </div>
              <div className="flex flex-wrap items-center gap-4">
                <div className="flex items-center gap-2">
                  <Switch checked={!!settings.censorFuzzy} onCheckedChange={(value) => update({ censorFuzzy: value })} />
                  <span className="text-sm text-slate-700">Catch close matches too</span>
                </div>
                <div className="flex items-center gap-2">
                  <Label className="text-xs text-slate-500">Match strictness (0-1)</Label>
                  <Input
                    type="number"
                    min="0"
                    max="1"
                    step="0.05"
                    className="w-24"
                    value={settings.censorMatchThreshold ?? 0.8}
                    onChange={(event) => update({ censorMatchThreshold: parseFloat(event.target.value || "0.8") })}
                  />
                </div>
                <span className="text-xs text-muted-foreground">
                  {(() => {
                    const value = Number(settings.censorMatchThreshold ?? 0.8);
                    if (value <= 0.6) return "Looser: bleeps more, may catch near matches.";
                    if (value >= 0.9) return "Stricter: bleeps less, may miss slang or endings.";
                    return "Balanced for most shows.";
                  })()}
                </span>
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-slate-500">Beep sound</Label>
                <Select
                  value={settings.censorBeepFile && settings.censorBeepFile.trim() ? settings.censorBeepFile : "__builtin__"}
                  onValueChange={(value) => {
                    if (value === "__builtin__") {
                      update({ censorBeepFile: "", censorBeepMs: BEEP_MS, censorBeepFreq: BEEP_FREQ, censorBeepGainDb: BEEP_GAIN_DB });
                    } else {
                      update({ censorBeepFile: value, censorBeepMs: BEEP_MS, censorBeepFreq: BEEP_FREQ, censorBeepGainDb: BEEP_GAIN_DB });
                    }
                  }}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Built-in short beep (250ms)" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__builtin__">Built-in short beep (250ms)</SelectItem>
                    {sfxOptions.map((option) => (
                      <SelectItem key={option.id} value={option.value}>
                        {option.label || option.value}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  Upload a single-hit SFX if you want something custom.
                </p>
              </div>
            </div>
          )}
        </SectionItem>
      </SectionCard>

      <SectionCard
        icon={<Sparkles className="h-5 w-5 text-white" />}
        title="Magic Words"
        subtitle="Steer edits with quick phrases while you record."
        defaultOpen
      >
        <SectionItem
          icon={<RotateCcw className="h-4 w-4 text-white" />}
          title="Flubber"
          description="Redo the last sentence without breaking your flow."
        >
          <p className="text-sm text-slate-600">
            Say your wake word ("flubber" by default) right after a flub. We rewind to the previous natural pause, cut the
            mistake, and let you pick up cleanly.
          </p>
          <div className="grid gap-3 pt-4 sm:grid-cols-2">
            <div className="space-y-1">
              <Label className="text-xs text-slate-500">What you say</Label>
              <Input
                value={settings.commands?.flubber?.trigger_keyword ?? "flubber"}
                onChange={(event) => updateCommand("flubber", { trigger_keyword: event.target.value })}
                placeholder="flubber, do-over, rewind"
              />
              <p className="text-xs text-muted-foreground">Pick anything short you will remember under pressure.</p>
            </div>
          </div>
        </SectionItem>

        <SectionItem
          icon={<Bot className="h-4 w-4 text-white" />}
          title="Intern"
          description="Ask your helper to draft edits, research, or add notes in the moment."
        >
          <div className="space-y-3">
            <p className="text-sm text-slate-600">
              Say the trigger word, give your request, then finish with a stop phrase. We tuck the response into the next
              pause and update your transcript.
            </p>
            <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-600">
              Example: "Oh, Jennifer, would you tell us about this cool thing we do not know, if you do not mind." Rename the
              trigger to "Jennifer" and set the stop phrase to "if you do not mind" for a natural handoff.
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <Label className="text-xs text-slate-500">Trigger word</Label>
                <Input
                  value={settings.commands?.intern?.trigger_keyword ?? "intern"}
                  onChange={(event) => updateCommand("intern", { trigger_keyword: event.target.value })}
                  placeholder="intern, jennifer, helper"
                />
                <p className="text-xs text-muted-foreground">Use a name that feels natural in your show.</p>
              </div>
              <div className="space-y-1">
                <Label className="text-xs text-slate-500">Stop phrase(s)</Label>
                <Input
                  value={(settings.commands?.intern?.end_markers || ["stop", "stop intern"]).join(", ")}
                  onChange={(event) =>
                    updateCommand("intern", { end_markers: tokenizeVariants(event.target.value) })
                  }
                  placeholder="stop, thank you, if you do not mind"
                />
                <p className="text-xs text-muted-foreground">
                  Separate phrases with commas. We stop listening when we hear any of them.
                </p>
              </div>
            </div>
            <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="text-xs text-slate-600 sm:max-w-sm">
                Remove spoken stop phrase from the transcript. It is on by default so the exchange sounds tight, but turn it
                off if you want listeners to hear the phrase.
              </div>
              <Switch
                checked={!!(settings.commands?.intern?.remove_end_marker ?? true)}
                onCheckedChange={(value) => updateCommand("intern", { remove_end_marker: value })}
              />
            </div>
          </div>
        </SectionItem>

        {customCommands.length > 0 && (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-700">
            Custom magic words
            {" "}
            {customCommands.map(([name]) => name).join(", ")}
            {" "}
            will keep working just like before. Reach out if you need us to expose advanced editing again.
          </div>
        )}

        <div className="flex flex-col gap-3 pt-4 sm:flex-row sm:items-center sm:justify-between">
          <span className="text-xs text-muted-foreground">
            {dirty ? "You have unsaved changes." : "All changes saved."}
          </span>
          <Button
            type="button"
            size="sm"
            disabled={!dirty || saving}
            onClick={save}
            className="inline-flex items-center gap-2"
          >
            {saving ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin" /> Saving...
              </>
            ) : (
              <>
                <Save className="h-4 w-4" /> Save changes
              </>
            )}
          </Button>
        </div>
      </SectionCard>
    </div>
  );
}

function TagInput({ values, onChange, placeholder }) {
  const [draft, setDraft] = useState("");

  const add = (value) => {
    const trimmed = value.trim();
    if (!trimmed || values.includes(trimmed)) return;
    onChange([...values, trimmed]);
    setDraft("");
  };

  const remove = (value) => {
    onChange(values.filter((entry) => entry !== value));
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white px-3 py-2">
      <div className="flex flex-wrap gap-2 pb-2">
        {values.map((value) => (
          <Badge
            key={value}
            variant="secondary"
            className="cursor-pointer bg-slate-200 text-slate-700 hover:bg-slate-300"
            onClick={() => remove(value)}
          >
            {value}
          </Badge>
        ))}
      </div>
      <Input
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter") {
            event.preventDefault();
            add(draft);
          }
          if (event.key === "Backspace" && !draft && values.length) {
            remove(values[values.length - 1]);
          }
        }}
        placeholder={placeholder}
      />
    </div>
  );
}

