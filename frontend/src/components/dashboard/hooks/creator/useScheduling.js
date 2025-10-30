import { useState, useEffect, useCallback } from 'react';
import { makeApi } from '@/lib/apiClient';

export default function useScheduling({ token, selectedTemplate, setPublishMode, setScheduleDate, setScheduleTime }) {
  const [autoRecurringRef, setAutoRecurringRef] = useState({ templateId: null, date: null, time: null, manual: false });

  useEffect(() => {
    const tplId = selectedTemplate?.id;
    if (!tplId) {
      setAutoRecurringRef({ templateId: null, date: null, time: null, manual: false });
      return;
    }
    if (autoRecurringRef.templateId !== tplId) {
      setAutoRecurringRef({ templateId: tplId, date: null, time: null, manual: false });
    }
  }, [selectedTemplate?.id]);

  useEffect(() => {
    const tplId = selectedTemplate?.id;
    if (!tplId || !token) return;

    const state = autoRecurringRef;
    if (state.manual && state.templateId === tplId) return;
    if (state.templateId === tplId && state.date && state.time && !state.manual) return;

    let cancelled = false;
    (async () => {
      try {
        const apiClient = makeApi(token);
        const info = await apiClient.get(`/api/recurring/templates/${tplId}/next`);
        if (cancelled) return;
        const nextDate = info?.next_publish_date;
        const nextTime = info?.next_publish_time;
        if (nextDate && nextTime) {
          setScheduleDate(nextDate);
          setScheduleTime(nextTime);
          setPublishMode((prev) => (prev === 'now' ? prev : 'schedule'));
          setAutoRecurringRef({
            templateId: tplId,
            date: nextDate,
            time: nextTime,
            manual: false,
          });
        } else {
          setAutoRecurringRef({
            templateId: tplId,
            date: null,
            time: null,
            manual: false,
          });
        }
      } catch (err) {
        console.warn('Failed to fetch template recurring slot', err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedTemplate?.id, token, autoRecurringRef]);

  const handleRecurringApply = async (slot) => {
    try {
      const template = templates.find(t => t.id === slot.template_id);
      if (template) {
        setSelectedTemplate(template);
      }
    } catch {}

    let nextDate = slot?.next_scheduled_date;
    let nextTime = slot?.next_scheduled_time;

    if ((!nextDate || !nextTime) && slot?.id) {
      try {
        const api = makeApi(token);
        const info = await api.get(`/api/recurring/schedules/${slot.id}/next`);
        nextDate = info?.next_publish_date || info?.next_publish_at_local?.slice(0, 10) || nextDate;
        if (info?.next_publish_time) {
          nextTime = info.next_publish_time;
        } else if (info?.next_publish_at_local && info.next_publish_at_local.includes('T')) {
          nextTime = info.next_publish_at_local.split('T')[1]?.slice(0, 5) || nextTime;
        }
      } catch (err) {
        console.warn('Failed to fetch next slot info', err);
      }
    }

    if (!nextDate || !nextTime) {
      const fallback = computeNextLocalFromSlot(slot);
      if (fallback) {
        nextDate = fallback.date;
        nextTime = fallback.time;
      }
    }

    if (nextDate && nextTime) {
      setScheduleDate(nextDate);
      setScheduleTime(nextTime);
    }

    setPublishMode('schedule');
    setCurrentStep(2);
  };

  const computeNextLocalFromSlot = (slot) => {
    if (!slot) return null;
    let dow = Number(slot.day_of_week);
    if (!Number.isFinite(dow)) return null;
    const timeText = String(slot.time_of_day || '').trim();
    if (!timeText) return null;
    const [hhStr, mmStr] = timeText.split(':');
    const hours = Number(hhStr);
    const minutes = Number(mmStr);
    if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return null;
    const targetDow = (dow + 1) % 7;
    const now = new Date();
    const candidate = new Date(now);
    candidate.setHours(hours, minutes, 0, 0);
    let deltaDays = (targetDow - now.getDay() + 7) % 7;
    if (deltaDays === 0 && candidate <= now) {
      deltaDays = 7;
    }
    candidate.setDate(candidate.getDate() + deltaDays);
    return {
      date: candidate.toISOString().slice(0, 10),
      time: `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`,
    };
  };

  return {
    handleRecurringApply,
  };
}