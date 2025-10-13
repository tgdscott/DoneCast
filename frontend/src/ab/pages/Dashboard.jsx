
import React, { useEffect, useState, useMemo } from "react";
import { makeApi } from "@/lib/apiClient";

function StatCard({ label, value, sub }) {
  return (
    <div className="rounded-2xl border bg-card p-4">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className="mt-1 text-2xl font-semibold tracking-tight">{value}</div>
      {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
    </div>
  );
}

export default function Dashboard({ token, shows, drafts, onOpenDraft, setActive }) {
  const [selectedShow, setSelectedShow] = useState("All");
  const [stats, setStats] = useState({ episodes: null, minutesLeft: null, scheduled: null, episodesThisWeek: null, playsLast30d: null, recentPlays: [] });
  const [statsError, setStatsError] = useState(null);

  useEffect(() => {
    let aborted = false;
    (async () => {
      if (!token) { setStats({ episodes: null, minutesLeft: null, scheduled: null, episodesThisWeek: null, playsLast30d: null, recentPlays: [] }); setStatsError(null); return; }
      try {
        setStatsError(null);
        const api = makeApi(token);
        let totalEpisodes = null;
        let scheduled = null;
        let episodesById = new Map();
        let episodesMeta = new Map();
        try {
          const page = await api.get('/api/episodes/?limit=200');
          totalEpisodes = (Array.isArray(page?.items) ? page.items.length : Array.isArray(page) ? page.length : null);
          if (typeof page?.total === 'number') totalEpisodes = page.total;
          if (Array.isArray(page?.items)) {
            const nowIso = new Date().toISOString();
            scheduled = page.items.filter(e => e.status === 'scheduled' || (e.publish_at && e.publish_at > nowIso)).length;
            for (const e of page.items) {
              if (!e || !e.id) continue;
              episodesById.set(String(e.id), e.title || 'Untitled');
              episodesMeta.set(String(e.id), { publish_at: e.publish_at || e.processed_at || e.created_at || null });
            }
          }
        } catch (err) { setStatsError('Failed to load episode stats.'); }
        let minutesLeft = null;
        try {
          const usage = await api.get('/api/billing/usage');
          if (usage) {
            if (typeof usage.minutes_left === 'number') {
              minutesLeft = usage.minutes_left;
            } else {
              const used = usage.processing_minutes_used_this_month;
              const cap = usage.max_processing_minutes_month;
              if (typeof cap === 'number' && typeof used === 'number') {
                minutesLeft = Math.max(0, cap - used);
              } else if (cap == null) {
                minutesLeft = '∞';
              }
            }
          }
        } catch (err) { setStatsError('Failed to load usage stats.'); }
        let playsLast30d = null;
        let recentPlays = [];
        try {
          const userStatsPrime = await api.get('/api/users/me/stats');
          if (typeof userStatsPrime?.plays_last_30d === 'number') {
            playsLast30d = userStatsPrime.plays_last_30d;
          }
          // Analytics fallback removed
          const epTotals = null; // Analytics endpoint removed
          if (Array.isArray(epTotals?.items)) {
            const mapped = epTotals.items.map(it => ({
              ...it,
              title: episodesById.get(String(it.episode_id)) || it.title || 'Untitled',
              _pub: episodesMeta.get(String(it.episode_id))?.publish_at || null,
            }));
            mapped.sort((a,b) => {
              const da = a?._pub ? new Date(a._pub).getTime() : 0;
              const db = b?._pub ? new Date(b._pub).getTime() : 0;
              return db - da;
            });
            recentPlays = mapped.slice(0,3);
          }
        } catch (err) { setStatsError('Failed to load play stats.'); }
        try {
          const userStats = await api.get('/api/users/me/stats');
          if (recentPlays.length === 0 && Array.isArray(userStats?.recent_episode_plays)) {
            recentPlays = userStats.recent_episode_plays.slice(0,3).map(it => ({
              episode_id: it.episode_id,
              plays_total: it.plays_total,
              title: it.title || episodesById.get(String(it.episode_id)) || 'Untitled'
            }));
          }
        } catch (err) { setStatsError('Failed to load recent episode stats.'); }
        setStats(prev => aborted ? prev : { ...prev, episodes: totalEpisodes, minutesLeft, scheduled, playsLast30d, recentPlays });
      } catch (err) {
        if (!aborted) { setStats({ episodes: null, minutesLeft: null, scheduled: null, episodesThisWeek: null, playsLast30d: null, recentPlays: [] }); setStatsError('Failed to load dashboard stats.'); }
      }
    })();
    return () => { aborted = true; };
  }, [token]);

  const draftRows = useMemo(() => drafts.map(d => {
    const status = d.transcript === "ready" ? "Transcript ready" : "Transcribing";
    return { id: d.id, title: d.title, status };
  }), [drafts]);

  return (
    <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl md:text-3xl font-semibold tracking-tight">Welcome back</h1>
          <p className="text-sm text-muted-foreground">Ship a new episode in minutes.</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="hidden sm:flex items-center gap-2">
            <label className="text-sm text-muted-foreground">Podcast</label>
            <select className="rounded-lg border px-2 py-1 text-sm" value={selectedShow} onChange={(e)=>setSelectedShow(e.target.value)}>
              <option>All</option>
              {shows.map(s => <option key={s.id}>{s.name}</option>)}
            </select>
          </div>
          <button className="rounded-xl bg-indigo-600 px-4 py-2 text-white shadow hover:bg-indigo-500 focus:outline-none focus-visible:ring"
            onClick={() => setActive("creator-upload")}
          >
            New Episode
          </button>
        </div>
      </div>

      {statsError && (
        <div className="bg-red-100 border border-red-300 text-red-700 rounded p-3 mb-4 text-sm">
          {statsError}
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Episodes" value={(stats.episodes ?? '—').toString()} sub={stats.episodesThisWeek ? `+${stats.episodesThisWeek} this week` : undefined} />
        <StatCard label="Scheduled" value={(stats.scheduled ?? '—').toString()} />
        <StatCard label="Drafts" value={draftRows.length.toString()} />
        <StatCard label="Minutes Left" value={(stats.minutesLeft ?? '—').toString()} />
      </div>

      {/* Plays row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Plays Last 30 Days" value={(stats.playsLast30d ?? '—').toString()} />
        {(stats.recentPlays || []).slice(0,3).map((it, idx) => (
          <StatCard
            key={idx}
            label={it?.title || 'Recent Episode'}
            value={(it?.plays_total ?? '—').toString()}
          />
        ))}
      </div>

      {/* Draft uploads */}
      <section className="rounded-2xl border bg-card">
        <header className="flex items-center justify-between px-4 py-3 border-b">
          <h2 className="text-base font-semibold">Draft uploads</h2>
        </header>
        <ul className="divide-y">
          {draftRows.map((d) => (
            <li key={d.id} className="px-4 py-3 flex items-center justify-between gap-4">
              <div className="min-w-0">
                <div className="font-medium truncate">{d.title}</div>
                <div className="text-xs text-muted-foreground">{d.status}</div>
              </div>
              <button
                className="px-3 py-1.5 text-sm rounded-lg border hover:bg-muted"
                onClick={() => onOpenDraft(d.id)}
              >
                Resume
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
