import React from 'react';
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useAuth } from "@/AuthContext";
import { makeApi } from "@/lib/apiClient";
import { useToast } from '@/hooks/use-toast';
import { useResolvedTimezone } from '@/hooks/useResolvedTimezone';
import { formatInTimezone } from '@/lib/timezone';

export default function AdminPodcastsTab() {
  const { token } = useAuth();
  const { toast } = useToast();
  const resolvedTimezone = useResolvedTimezone();
  const [rows, setRows] = React.useState([]);
  const [total, setTotal] = React.useState(0);
  const [limit, setLimit] = React.useState(25);
  const [offset, setOffset] = React.useState(0);
  const [loading, setLoading] = React.useState(false);
  const [qOwner, setQOwner] = React.useState("");

  const load = async (newOffset=0) => {
    if (!token) return;
    setLoading(true);
    try {
      const api = makeApi(token);
      const qs = new URLSearchParams({ limit: String(limit), offset: String(newOffset), ...(qOwner ? { owner_email: qOwner } : {}) });
      console.log('[AdminPodcastsTab] Loading podcasts:', `/api/admin/podcasts?${qs.toString()}`);
      const data = await api.get(`/api/admin/podcasts?${qs.toString()}`);
      console.log('[AdminPodcastsTab] Response:', data);
      setRows(data.items || []);
      setTotal(Number(data.total) || 0);
      setOffset(Number(data.offset) || 0);
    } catch (e) {
      console.error('[AdminPodcastsTab] Load failed:', e);
      try { toast({ title: 'Failed to load podcasts', description: e?.detail || e?.message || 'Error', variant: 'destructive' }); } catch {}
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => { load(0); /* initial */ }, [token]);

  const onSearch = () => load(0);
  const pages = Math.max(1, Math.ceil(total / limit));
  const pageIdx = Math.floor(offset / limit) + 1;

  const openManager = (podcastId) => {
    try {
      const url = `/dashboard?podcast=${encodeURIComponent(podcastId)}`;
      window.location.href = url;
    } catch {}
  };
  const copyId = async (id) => {
    try { await navigator.clipboard.writeText(id); toast({ title: 'Copied podcast id' }); } catch {}
  };

  return (
    <div className="space-y-4">
      <Card className="border-0 shadow-sm bg-white">
        <CardContent className="p-4 flex items-center gap-3">
          <Input placeholder="Filter by owner email" value={qOwner} onChange={e=>setQOwner(e.target.value)} className="max-w-sm" />
          <Button onClick={onSearch} disabled={loading}>Search</Button>
          <div className="ml-auto text-sm text-gray-500">Total: {total}</div>
        </CardContent>
      </Card>
      <Card className="border-0 shadow-sm bg-white">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Podcast</TableHead>
                <TableHead>Owner</TableHead>
                <TableHead>Episodes</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Last Activity</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map(row => (
                <TableRow key={row.id}>
                  <TableCell className="font-medium">{row.name || '—'}</TableCell>
                  <TableCell>{row.owner_email || '—'}</TableCell>
                  <TableCell>{row.episode_count ?? 0}</TableCell>
                  <TableCell>
                    {row.created_at ? (
                      resolvedTimezone ? 
                        formatInTimezone(row.created_at, { dateStyle: 'medium', timeStyle: 'short' }, resolvedTimezone) : 
                        new Date(row.created_at).toLocaleString()
                    ) : '—'}
                  </TableCell>
                  <TableCell>
                    {row.last_episode_at ? (
                      resolvedTimezone ? 
                        formatInTimezone(row.last_episode_at, { dateStyle: 'medium', timeStyle: 'short' }, resolvedTimezone) : 
                        new Date(row.last_episode_at).toLocaleString()
                    ) : '—'}
                  </TableCell>
                  <TableCell className="text-right space-x-2">
                    <Button size="sm" variant="outline" onClick={()=>openManager(row.id)}>Open in Podcast Manager</Button>
                    <Button size="sm" variant="secondary" onClick={()=>copyId(row.id)}>Copy ID</Button>
                  </TableCell>
                </TableRow>
              ))}
              {rows.length === 0 && (
                <TableRow><TableCell colSpan={6} className="text-center text-sm text-gray-500 py-8">{loading ? 'Loading…' : 'No results'}</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-600">Page {pageIdx} of {pages}</div>
        <div className="space-x-2">
          <Button aria-label="Previous page" size="sm" variant="outline" disabled={offset<=0 || loading} onClick={()=>load(Math.max(0, offset - limit))}><ChevronLeft className="w-4 h-4" /></Button>
          <Button aria-label="Next page" size="sm" variant="outline" disabled={offset+limit>=total || loading} onClick={()=>load(offset + limit)}><ChevronRight className="w-4 h-4" /></Button>
        </div>
      </div>
    </div>
  );
}
