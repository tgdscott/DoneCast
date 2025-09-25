import React, { useMemo } from 'react';
import { Clock, CheckCircle2, Radio, Rss, Globe2, CalendarClock } from 'lucide-react';

/**
 * EpisodePublishTimeline
 * Displays a segmented timeline for the publish step with milestone timestamps.
 * - If publishing now: shows immediate + near-future distribution steps.
 * - If scheduled: prepends a scheduled start milestone.
 */
export default function EpisodePublishTimeline({
  publishOption,
  scheduleDate,
  scheduleTime,
  durationText,
  hasArtwork,
  hasSocial,
}) {
  const now = new Date();
  const scheduledAt = useMemo(() => {
    if (publishOption !== 'schedule' || !scheduleDate) return null;
    try {
      const base = scheduleDate + 'T' + (scheduleTime || '09:00');
      return new Date(base);
    } catch { return null; }
  }, [publishOption, scheduleDate, scheduleTime]);

  const fmt = (d) => d ? d.toLocaleString(undefined, { hour: '2-digit', minute: '2-digit', month: 'short', day: 'numeric' }) : '';
  const addMinutes = (d, m) => new Date(d.getTime() + m * 60000);

  const effectiveStart = scheduledAt || now;
  const milestones = [];

  if (publishOption === 'schedule' && scheduledAt) {
    milestones.push({
      key: 'scheduled',
      label: 'Scheduled',
      desc: 'Episode will go live automatically',
      time: fmt(scheduledAt),
      icon: CalendarClock,
      status: scheduledAt > now ? 'pending' : 'done'
    });
  } else {
    milestones.push({
      key: 'publish_now',
      label: 'Publish Initiated',
      desc: 'Processing final metadata',
      time: fmt(now),
      icon: Radio,
      status: 'done'
    });
  }

  // Distribution window (simulated typical ranges)
  milestones.push({
    key: 'distribution',
    label: 'Platform Distribution',
    desc: 'Apple / Spotify ingestion',
    time: fmt(addMinutes(effectiveStart, 5)),
    icon: Globe2,
    status: 'pending'
  });

  milestones.push({
    key: 'search_index',
    label: 'Search Index Visibility',
    desc: 'Appears in directory search (est.)',
    time: fmt(addMinutes(effectiveStart, 60 * 6)),
    icon: Rss,
    status: 'pending'
  });

  if (hasArtwork) {
    milestones.push({
      key: 'artwork',
      label: 'Artwork Generated',
      desc: 'Episode cover variant ready',
      time: fmt(addMinutes(effectiveStart, 2)),
      icon: CheckCircle2,
      status: 'pending'
    });
  }

  if (hasSocial) {
    milestones.push({
      key: 'social',
      label: 'Social Posts Ready',
      desc: 'Share assets prepared',
      time: fmt(addMinutes(effectiveStart, 3)),
      icon: CheckCircle2,
      status: 'pending'
    });
  }

  milestones.push({
    key: 'evergreen',
    label: 'Long-Tail Discovery',
    desc: 'Algorithmic recommendations ramp',
    time: fmt(addMinutes(effectiveStart, 60 * 24)),
    icon: Clock,
    status: 'pending'
  });

  return (
    <div className="rounded-lg border bg-white shadow-sm p-5">
      <h3 className="text-sm font-semibold mb-4 text-slate-700">Release Timeline</h3>
      <ol className="relative ml-3 border-l border-slate-200">
        {milestones.map((m, idx) => {
          const Icon = m.icon;
          const isLast = idx === milestones.length - 1;
          return (
            <li key={m.key} className="mb-6 ml-4">
              <span className={`absolute -left-2 flex h-4 w-4 items-center justify-center rounded-full ring-2 ring-white ${m.status === 'done' ? 'bg-green-500 text-white' : 'bg-slate-300 text-slate-50'}`}>
                <Icon className="h-3 w-3" />
              </span>
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-medium text-slate-600 leading-tight">{m.label}</p>
                  <p className="text-[11px] text-slate-500">{m.desc}</p>
                </div>
                <div className="text-[11px] font-mono text-slate-500 whitespace-nowrap">{m.time}</div>
              </div>
              {!isLast && <div className="mt-4" />}
            </li>
          );
        })}
      </ol>
      {durationText && (
        <div className="mt-2 text-[11px] text-slate-500">Episode length: {durationText}</div>
      )}
      <div className="mt-3 text-[10px] text-slate-400">Times are estimates; distribution speeds vary by platform.</div>
    </div>
  );
}
