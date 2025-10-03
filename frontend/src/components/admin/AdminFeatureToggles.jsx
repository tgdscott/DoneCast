"use client";

import React from 'react';
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/hooks/use-toast";
import { makeApi } from "@/lib/apiClient";

/**
 * AdminFeatureToggles
 * Renders the shared "Test Mode (Admin)" toggle and saves to /api/admin/settings.
 * Props:
 * - token: string (required)
 * - initial: Partial<typeof DEFAULT_SETTINGS> | null (optional)
 * - onSaved?: (settings) => void (optional)
 */
const DEFAULT_SETTINGS = {
  test_mode: false,
  default_user_active: true,
  max_upload_mb: 500,
  browser_audio_conversion_enabled: false,
};

export default function AdminFeatureToggles({ token, initial = null, onSaved }) {
  const { toast } = useToast();
  const [settings, setSettings] = React.useState(
    initial ? { ...DEFAULT_SETTINGS, ...initial } : null
  );
  const [saving, setSaving] = React.useState(false);
  const [err, setErr] = React.useState(null);

  // Load if no initial provided
  React.useEffect(() => {
    if (initial != null) { setSettings({ ...DEFAULT_SETTINGS, ...initial }); return; }
    if (!token) return;
    let canceled = false;
    (async () => {
      try {
        const api = makeApi(token);
        const data = await api.get('/api/admin/settings');
        if (!canceled) setSettings(data ? { ...DEFAULT_SETTINGS, ...data } : { ...DEFAULT_SETTINGS });
      } catch {
        if (!canceled) setSettings({ ...DEFAULT_SETTINGS });
      }
    })();
    return () => { canceled = true; };
  }, [token, initial]);

  const save = async (next, prev) => {
    if (!token) return;
    setSaving(true);
    setErr(null);
    try {
      const api = makeApi(token);
      const data = await api.put('/api/admin/settings', next);
      const merged = data ? { ...DEFAULT_SETTINGS, ...data } : { ...DEFAULT_SETTINGS, ...next };
      setSettings(merged);
      if (onSaved) onSaved(merged);
    } catch (e) {
      setErr(e?.message || 'Failed');
      try { toast({ title: 'Error', description: 'Failed to update admin settings', variant: 'destructive' }); } catch {}
      // Revert optimistic change on failure
      if (prev) setSettings(prev);
    } finally {
      setSaving(false);
    }
  };

  const onToggle = (checked) => {
    const prev = { ...(settings || {}) };
    const next = { ...prev, test_mode: !!checked };
    setSettings(next); // optimistic update
    save(next, prev);
  };

  const onDefaultActiveToggle = (checked) => {
    const prev = { ...(settings || {}) };
    const next = { ...prev, default_user_active: !!checked };
    setSettings(next);
    save(next, prev);
  };

  const onBrowserConversionToggle = (checked) => {
    const prev = { ...(settings || {}) };
    const next = { ...prev, browser_audio_conversion_enabled: !!checked };
    setSettings(next);
    save(next, prev);
  };

  const onMaxUploadChange = (mbStr) => {
    const prev = { ...(settings || {}) };
    let n = parseInt(mbStr, 10);
    if (!isFinite(n) || isNaN(n)) n = prev.max_upload_mb || 500;
    // clamp sensible bounds
    if (n < 10) n = 10;
    if (n > 2048) n = 2048;
    const next = { ...prev, max_upload_mb: n };
    setSettings(next);
    // debounce-ish: save after small delay to avoid rapid PUT spam
    clearTimeout(onMaxUploadChange._t);
    onMaxUploadChange._t = setTimeout(() => save(next, prev), 400);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <Label htmlFor="admin-test-mode" className="text-base font-medium text-gray-700">Test Mode (Admin)</Label>
          <p className="text-sm text-gray-500 mt-1">
            When enabled, new episodes default to draft and season/episode numbers are overridden to day-of-month and HHMM.
          </p>
        </div>
        <div className="flex items-center space-x-2">
          {saving && <span className="text-xs text-gray-400">Saving…</span>}
          {err && <span className="text-xs text-red-500" title={err}>Err</span>}
          <Switch
            id="admin-test-mode"
            checked={!!(settings && settings.test_mode)}
            disabled={saving}
            onCheckedChange={onToggle}
          />
        </div>
      </div>
      <div className="flex items-center justify-between">
        <div>
          <Label htmlFor="admin-default-user-active" className="text-base font-medium text-gray-700">New Users Are Active By Default</Label>
          <p className="text-sm text-gray-500 mt-1">
            When disabled, newly created accounts start as inactive and will see the Closed-Alpha gate until approved.
          </p>
        </div>
        <div className="flex items-center space-x-2">
          {saving && <span className="text-xs text-gray-400">Saving…</span>}
          {err && <span className="text-xs text-red-500" title={err}>Err</span>}
          <Switch
            id="admin-default-user-active"
            checked={!!(settings && settings.default_user_active)}
            disabled={saving}
            onCheckedChange={onDefaultActiveToggle}
          />
        </div>
      </div>
      <div className="flex items-center justify-between">
        <div>
          <Label htmlFor="admin-browser-audio-conversion" className="text-base font-medium text-gray-700">Browser Audio Conversion</Label>
          <p className="text-sm text-gray-500 mt-1">
            When enabled, uploads converted in the browser are accepted without requiring server-side transcoding.
          </p>
        </div>
        <div className="flex items-center space-x-2">
          {saving && <span className="text-xs text-gray-400">Saving…</span>}
          {err && <span className="text-xs text-red-500" title={err}>Err</span>}
          <Switch
            id="admin-browser-audio-conversion"
            checked={!!(settings && settings.browser_audio_conversion_enabled)}
            disabled={saving}
            onCheckedChange={onBrowserConversionToggle}
          />
        </div>
      </div>
      <div className="flex items-center justify-between">
        <div>
          <Label className="text-base font-medium text-gray-700">Maximum Upload Size (MB)</Label>
          <p className="text-sm text-gray-500 mt-1">
            Applies to main audio uploads. Clients use this for hints; server enforces it.
          </p>
        </div>
        <div className="flex items-center space-x-2">
          {saving && <span className="text-xs text-gray-400">Saving…</span>}
          {err && <span className="text-xs text-red-500" title={err}>Err</span>}
          <input
            type="number"
            min={10}
            max={2048}
            value={(settings && settings.max_upload_mb) ?? 500}
            onChange={(e)=> onMaxUploadChange(e.target.value)}
            className="w-28 border rounded px-2 py-1 text-sm"
          />
        </div>
      </div>
    </div>
  );
}
