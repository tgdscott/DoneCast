import React from 'react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { makeApi } from '@/lib/apiClient';
import { useToast } from '@/hooks/use-toast';

export default function AdminSentryPanel({ token }) {
  const { toast } = useToast();
  const [issues, setIssues] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const [selected, setSelected] = React.useState(null);
  const [detailLoading, setDetailLoading] = React.useState(false);

  const loadIssues = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const api = makeApi(token);
      const q = new URLSearchParams({ limit: '10' });
      const data = await api.get(`/api/admin/feedback/sentry/events?${q.toString()}`);
      setIssues(data || []);
    } catch (err) {
      console.error('Failed to load Sentry issues', err);
      toast({ variant: 'destructive', title: 'Failed to load Sentry issues', description: err.message });
    } finally {
      setLoading(false);
    }
  };

  const loadIssueDetail = async (issueId) => {
    setDetailLoading(true);
    try {
      const api = makeApi(token);
      const d = await api.get(`/api/admin/feedback/sentry/events/${issueId}`);
      setSelected(d);
    } catch (err) {
      toast({ variant: 'destructive', title: 'Failed to load issue', description: err.message });
    } finally {
      setDetailLoading(false);
    }
  };

  React.useEffect(() => { loadIssues(); }, [token]);

  return (
    <Card>
      <CardContent>
        <div className="flex items-center justify-between">
          <h3 className="font-semibold">Sentry Issues</h3>
          <div className="space-x-2">
            <Button size="sm" onClick={loadIssues} disabled={loading}>{loading ? 'Refreshing...' : 'Refresh'}</Button>
          </div>
        </div>

        <div className="mt-4 space-y-3">
          {issues.length === 0 && (<div className="text-sm text-gray-500">No recent Sentry issues found.</div>)}
          {issues.map((it) => (
            <div key={it.id} className="flex items-center justify-between p-2 border rounded">
              <div>
                <div className="font-medium">{it.shortId || it.id} — {it.title}</div>
                <div className="text-xs text-gray-500">Level: {it.level} • Events: {it.count || it.timesSeen}</div>
              </div>
              <div className="flex items-center gap-2">
                <Badge>{it.level}</Badge>
                <Button size="sm" variant="outline" onClick={() => loadIssueDetail(it.id)}>Details</Button>
              </div>
            </div>
          ))}
        </div>

        {selected && (
          <div className="mt-4 border-t pt-3">
            <h4 className="font-semibold">Issue Details</h4>
            {detailLoading ? (
              <div className="text-sm text-gray-500">Loading...</div>
            ) : (
              <div className="text-sm mt-2">
                <div><strong>Title:</strong> {selected.title}</div>
                <div><strong>Platform:</strong> {selected.platform}</div>
                <div><strong>First Seen:</strong> {selected.firstSeen}</div>
                <div><strong>Last Seen:</strong> {selected.lastSeen}</div>
                <div className="mt-2"><strong>Short Description:</strong>
                  <pre className="text-xs bg-gray-100 p-2 rounded overflow-auto">{selected.culprit || selected.shortTitle || JSON.stringify(selected.subtitle)}</pre>
                </div>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
