import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { makeApi } from '@/lib/apiClient';
import { toast } from '@/hooks/use-toast';

const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const sortSlots = (slots) => {
  return [...slots].sort((a, b) => {
    const dayDiff = Number(a.day_of_week ?? 0) - Number(b.day_of_week ?? 0);
    if (dayDiff !== 0) return dayDiff;
    return String(a.time_of_day || '').localeCompare(String(b.time_of_day || ''));
  });
};

const normalizeSlot = (slot) => ({
  id: slot.id || null,
  day_of_week: Number(slot.day_of_week ?? 0),
  time_of_day: String(slot.time_of_day || '').slice(0, 5) || '05:00',
  enabled: slot.enabled !== false,
  advance_minutes: Number(slot.advance_minutes ?? 60) || 60,
  timezone: slot.timezone || null,
  next_scheduled: slot.next_scheduled || null,
  next_scheduled_local: slot.next_scheduled_local || null,
  next_scheduled_date: slot.next_scheduled_date || null,
  next_scheduled_time: slot.next_scheduled_time || null,
});

const formatNext = (slot) => {
  const iso = slot.next_scheduled || (slot.next_scheduled_local ? `${slot.next_scheduled_local}:00` : null);
  if (!iso) return '—';
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) {
    if (slot.next_scheduled_date && slot.next_scheduled_time) {
      return `${slot.next_scheduled_date} ${slot.next_scheduled_time}`;
    }
    return '—';
  }
  return dt.toLocaleString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
};

const detectDeviceTimezone = (fallback = 'UTC') => {
  try {
    const resolved = Intl?.DateTimeFormat?.().resolvedOptions?.().timeZone;
    return resolved || fallback;
  } catch (err) {
    return fallback;
  }
};

export default function RecurringScheduleManager({
  token,
  templateId,
  userTimezone,
  isNewTemplate,
  onDirtyChange,
}) {
  const deviceTimezone = useMemo(() => detectDeviceTimezone(userTimezone || 'UTC'), [userTimezone]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [slots, setSlots] = useState([]);
  const [timezone, setTimezone] = useState(deviceTimezone);
  const [scheduleDirty, setScheduleDirty] = useState(false);
  const [timeInput, setTimeInput] = useState('05:00');
  const [daySelection, setDaySelection] = useState(() => new Set([0]));
  const [baseline, setBaseline] = useState({ timezone: deviceTimezone, slots: [] });

  useEffect(() => {
    if (typeof onDirtyChange === 'function') {
      onDirtyChange(scheduleDirty);
    }
  }, [scheduleDirty, onDirtyChange]);

  useEffect(() => {
    if (!templateId || templateId === 'new' || isNewTemplate) {
      const defaultTz = deviceTimezone;
      setSlots([]);
      setScheduleDirty(false);
      setError(null);
      setLoading(false);
      setTimezone(defaultTz);
      setBaseline({ timezone: defaultTz, slots: [] });
      if (typeof onDirtyChange === 'function') {
        onDirtyChange(false);
      }
      return;
    }

    let cancelled = false;
    setLoading(true);
    (async () => {
      try {
        const api = makeApi(token);
        const data = await api.get(`/api/recurring/templates/${templateId}/schedules`);
        if (cancelled) return;
        const incoming = Array.isArray(data?.schedules) ? data.schedules : [];
        const normalized = sortSlots(incoming.map(normalizeSlot));
        const cloned = normalized.map((slot) => ({ ...slot }));
        const resolvedTz = data?.timezone || normalized[0]?.timezone || deviceTimezone;
        setSlots(cloned);
        setTimezone(resolvedTz);
        setBaseline({
          timezone: resolvedTz,
          slots: cloned.map((slot) => ({ ...slot })),
        });
        setScheduleDirty(false);
        setError(null);
        if (typeof onDirtyChange === 'function') {
          onDirtyChange(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err?.message || 'Failed to load recurring schedule');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [templateId, token, isNewTemplate, userTimezone, deviceTimezone, onDirtyChange]);

  const toggleDay = useCallback((index) => {
    setDaySelection((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  }, []);

  const handleAddSlots = useCallback(() => {
    if (daySelection.size === 0 || !timeInput) {
      return;
    }
    setSlots((prev) => {
      const next = [...prev];
      let added = 0;
      daySelection.forEach((day) => {
        const dayNum = Number(day);
        const exists = next.some(
          (slot) => Number(slot.day_of_week) === dayNum && String(slot.time_of_day) === String(timeInput)
        );
        if (!exists) {
          next.push({
            id: null,
            day_of_week: dayNum,
            time_of_day: timeInput,
            enabled: true,
            advance_minutes: 60,
            timezone,
            next_scheduled: null,
            next_scheduled_local: null,
            next_scheduled_date: null,
            next_scheduled_time: null,
          });
          added += 1;
        }
      });
      if (added > 0) {
        setScheduleDirty(true);
        return sortSlots(next);
      }
      return next;
    });
  }, [daySelection, timeInput, timezone]);

  const updateSlot = useCallback((index, updates, shouldSort = false) => {
    setSlots((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], ...updates };
      return shouldSort ? sortSlots(next) : next;
    });
    setScheduleDirty(true);
  }, []);

  const removeSlot = useCallback((index) => {
    setSlots((prev) => {
      const next = [...prev];
      next.splice(index, 1);
      return next;
    });
    setScheduleDirty(true);
  }, []);

  const handleSave = useCallback(async () => {
    if (!templateId || templateId === 'new') return;
    setSaving(true);
    setError(null);
    try {
      const api = makeApi(token);
      const payload = {
        timezone,
        schedules: slots.map((slot) => ({
          id: slot.id || undefined,
          day_of_week: Number(slot.day_of_week ?? 0),
          time_of_day: String(slot.time_of_day || '').slice(0, 5),
          enabled: slot.enabled !== false,
          advance_minutes: Number(slot.advance_minutes ?? 60) || 60,
          timezone: slot.timezone || timezone,
        })),
      };
      const data = await api.put(`/api/recurring/templates/${templateId}/schedules`, payload);
      const incoming = Array.isArray(data?.schedules) ? data.schedules : [];
      const normalized = sortSlots(incoming.map(normalizeSlot));
      const cloned = normalized.map((slot) => ({ ...slot }));
      const resolvedTz = data?.timezone || timezone;
      setSlots(cloned);
      setTimezone(resolvedTz);
      setBaseline({
        timezone: resolvedTz,
        slots: cloned.map((slot) => ({ ...slot })),
      });
      setScheduleDirty(false);
      if (typeof onDirtyChange === 'function') {
        onDirtyChange(false);
      }
      toast({
        title: 'Recurring schedule updated',
        description: 'Future episodes from this template will use the new time slots.',
      });
    } catch (err) {
      const message = err?.message || 'Failed to save recurring schedule';
      setError(message);
      toast({ variant: 'destructive', title: 'Save failed', description: message });
    } finally {
      setSaving(false);
    }
  }, [templateId, token, slots, timezone, onDirtyChange]);

  const hasSlots = slots.length > 0;
  const selectedDaysSummary = useMemo(() => Array.from(daySelection).sort((a, b) => a - b), [daySelection]);

  if (!templateId || templateId === 'new' || isNewTemplate) {
    return (
      <Card className="shadow-sm">
        <CardHeader>
          <CardTitle>Recurring Publish Schedule</CardTitle>
          <CardDescription>Save your template first to plan automatic publish slots.</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Once this template is saved, you can choose the days and times it should publish automatically. Each new episode will
            pick the next open slot.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="shadow-sm">
      <CardHeader>
        <CardTitle>Recurring Publish Schedule</CardTitle>
        <CardDescription>
          Tell Plus Plus when episodes made from this template should go live. We&rsquo;ll skip conflicts with already scheduled
          episodes.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {error && <div className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}

        <div className="grid gap-4 md:grid-cols-[1fr_auto] md:items-end">
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground">
              Scheduling uses your local timezone (<span className="font-medium text-slate-700">{timezone}</span>).
            </p>
            <div className="grid gap-3 sm:grid-cols-[repeat(2,minmax(0,1fr))] md:grid-cols-[repeat(2,minmax(0,1fr))]">
              <div className="space-y-2">
                <Label className="text-xs uppercase tracking-wide text-muted-foreground">Time</Label>
                <Input type="time" value={timeInput} onChange={(event) => setTimeInput(event.target.value)} className="h-9" />
              </div>
              <div className="space-y-2">
                <Label className="text-xs uppercase tracking-wide text-muted-foreground">Days</Label>
                <div className="flex flex-wrap gap-2">
                  {DAY_LABELS.map((label, index) => {
                    const checked = daySelection.has(index);
                    return (
                      <button
                        type="button"
                        key={label}
                        onClick={() => toggleDay(index)}
                        className={`rounded border px-2 py-1 text-xs font-medium transition-colors ${
                          checked ? 'border-blue-500 bg-blue-50 text-blue-700' : 'border-slate-200 bg-white text-slate-600'
                        }`}
                      >
                        {label}
                      </button>
                    );
                  })}
                </div>
                {selectedDaysSummary.length === 0 && (
                  <p className="text-xs text-muted-foreground">Select at least one day.</p>
                )}
              </div>
            </div>
          </div>
          <Button onClick={handleAddSlots} disabled={daySelection.size === 0 || !timeInput}>
            Add slot{daySelection.size > 1 ? 's' : ''}
          </Button>
        </div>

        {loading ? (
          <div className="text-sm text-muted-foreground">Loading recurring slots…</div>
        ) : hasSlots ? (
          <div className="space-y-3">
            {slots.map((slot, index) => (
              <div
                key={slot.id || `${slot.day_of_week}-${slot.time_of_day}-${index}`}
                className="flex flex-col gap-3 rounded border border-slate-200 bg-white p-3 md:flex-row md:items-center"
              >
                <div className="flex flex-1 flex-col gap-2 sm:flex-row sm:items-center">
                  <div className="space-y-1">
                    <Label className="text-xs uppercase tracking-wide text-muted-foreground">Day</Label>
                    <select
                      value={String(slot.day_of_week)}
                      onChange={(event) => updateSlot(index, { day_of_week: Number(event.target.value) }, true)}
                      className="h-9 rounded border border-slate-300 px-2 text-sm"
                    >
                      {DAY_LABELS.map((label, dayIndex) => (
                        <option key={label} value={dayIndex}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs uppercase tracking-wide text-muted-foreground">Time</Label>
                    <Input
                      type="time"
                      value={slot.time_of_day}
                      onChange={(event) => updateSlot(index, { time_of_day: event.target.value }, true)}
                      className="h-9"
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs uppercase tracking-wide text-muted-foreground">Status</Label>
                    <div className="flex items-center gap-2">
                      <Switch
                        id={`slot-enabled-${index}`}
                        checked={slot.enabled !== false}
                        onCheckedChange={(checked) => updateSlot(index, { enabled: !!checked })}
                      />
                      <Label htmlFor={`slot-enabled-${index}`} className="text-sm text-slate-700">
                        {slot.enabled !== false ? 'Enabled' : 'Paused'}
                      </Label>
                    </div>
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs uppercase tracking-wide text-muted-foreground">Next publish</Label>
                    <div className="text-sm text-slate-700">
                      {formatNext(slot)}
                      <span className="ml-1 text-xs text-muted-foreground">({slot.timezone || timezone})</span>
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Button type="button" variant="destructive" size="sm" onClick={() => removeSlot(index)}>
                    Remove
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="rounded border border-dashed border-slate-300 bg-slate-50 p-4 text-sm text-slate-600">
            No recurring slots yet. Add your publish days and time above, then click Save.
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-4">
          <div className="text-xs text-muted-foreground">
            {scheduleDirty ? 'You have unsaved schedule changes.' : 'Changes saved.'}
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={!scheduleDirty || saving}
              onClick={() => {
                setSlots(baseline.slots.map((slot) => ({ ...slot })));
                setTimezone(baseline.timezone || userTimezone || 'UTC');
                setScheduleDirty(false);
                if (typeof onDirtyChange === 'function') {
                  onDirtyChange(false);
                }
              }}
            >
              Cancel
            </Button>
            <Button type="button" onClick={handleSave} disabled={saving || !scheduleDirty}>
              {saving ? 'Saving…' : 'Save schedule'}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
