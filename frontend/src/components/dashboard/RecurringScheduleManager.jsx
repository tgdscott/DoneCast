import React, { useEffect, useState } from 'react';
import { makeApi } from '@/lib/apiClient';
import { Button } from '../ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Input } from '../ui/input';
import { Label } from '../ui/label';

export default function RecurringScheduleManager({ token, templates, onApply }) {
  const [schedules, setSchedules] = useState([]);
  const [day, setDay] = useState('1');
  const [time, setTime] = useState('09:00');
  const [templateId, setTemplateId] = useState('');
  const [loading, setLoading] = useState(false);
  const [applyingId, setApplyingId] = useState(null);

  useEffect(() => {
    const api = makeApi(token);
    api.get('/api/recurring/schedules').then(setSchedules).catch(() => {});
  }, [token]);

  const handleAdd = async () => {
    setLoading(true);
    try {
      const api = makeApi(token);
      await api.post('/api/recurring/schedules', { day_of_week: parseInt(day), time_of_day: time, template_id: templateId });
      const list = await api.get('/api/recurring/schedules');
      setSchedules(list);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id) => {
    const api = makeApi(token);
    await api.del(`/api/recurring/schedules/${id}`);
    setSchedules(schedules.filter(s => s.id !== id));
  };

  const handleApplyClick = async (schedule) => {
    if (!onApply) return;
    try {
      setApplyingId(schedule.id);
      await onApply(schedule);
    } finally {
      setApplyingId(null);
    }
  };

  const formatNext = (schedule) => {
    const datePart = schedule?.next_scheduled_date;
    const timePart = schedule?.next_scheduled_time;
    if (!datePart || !timePart) return null;
    const localIso = `${datePart}T${timePart}`;
    const localDate = new Date(localIso);
    if (Number.isNaN(localDate.getTime())) {
      return `${datePart} ${timePart}`;
    }
    return localDate.toLocaleString(undefined, {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    });
  };

  return (
    <Card className="mb-6">
      <CardHeader><CardTitle>Recurring Episode Slots</CardTitle></CardHeader>
      <CardContent>
        <div className="flex flex-wrap gap-3 mb-4 items-end">
          <div className="flex flex-col w-28">
            <Label htmlFor="recurring-day" className="text-xs mb-1">Day</Label>
            <select id="recurring-day" aria-label="Day of week" className="border rounded px-2 py-1 text-sm" value={day} onChange={e => setDay(e.target.value)}>
              {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map((d,i)=>(<option key={i} value={i}>{d}</option>))}
            </select>
          </div>
          <div className="flex flex-col w-32">
            <Label className="text-xs mb-1">Time</Label>
            <Input type="time" value={time} onChange={e => setTime(e.target.value)} className="h-9" />
          </div>
          <div className="flex flex-col flex-1 min-w-[160px]">
            <Label htmlFor="recurring-template" className="text-xs mb-1">Template</Label>
            <select id="recurring-template" aria-label="Template" className="border rounded px-2 py-1 text-sm" value={templateId} onChange={e => setTemplateId(e.target.value)}>
              <option value="">Select...</option>
              {templates.map(t=>(<option key={t.id} value={t.id}>{t.name}</option>))}
            </select>
          </div>
          <div className="flex">
            <Button onClick={handleAdd} disabled={loading || !templateId}>{loading ? 'Adding...' : 'Add'}</Button>
          </div>
        </div>
        <ul className="space-y-2">
          {schedules.map(s => (
            <li key={s.id} className="flex items-center gap-4 text-sm">
              <div className="flex flex-col">
                <span>
                  {['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][s.day_of_week]}{' '}
                  {String(s.time_of_day).slice(0,5)} — {templates.find(t=>t.id===s.template_id)?.name || s.template_id}
                </span>
                {(s.next_scheduled_date && s.next_scheduled_time) && (
                  <span className="text-xs text-muted-foreground">
                    Next: {formatNext(s)}{s.timezone ? ` (${s.timezone})` : ''}
                  </span>
                )}
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={() => handleApplyClick(s)}
                disabled={applyingId === s.id}
              >
                {applyingId === s.id ? 'Applying…' : 'Apply'}
              </Button>
              <Button size="sm" variant="destructive" onClick={()=>handleDelete(s.id)}>Delete</Button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
