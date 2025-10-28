import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { buildApiUrl } from "@/lib/apiClient";

export default function AdminHelpTab() {
  const [health, setHealth] = React.useState({ ok: null, detail: null });

  React.useEffect(() => {
    let canceled = false;
    (async () => {
      try {
        const res = await fetch(buildApiUrl('/api/health'));
        const ok = res.ok;
        let detail = null;
        try { detail = await res.json(); } catch {}
        if (!canceled) setHealth({ ok, detail });
      } catch {
        if (!canceled) setHealth({ ok: false, detail: null });
      }
    })();
    return () => { canceled = true; };
  }, []);

  const badge = (ok) => {
    if (ok === true) return <Badge className="bg-green-100 text-green-800">OK</Badge>;
    if (ok === false) return <Badge className="bg-red-100 text-red-800">DOWN</Badge>;
    return <Badge variant="secondary">Unknown</Badge>;
  };

  const links = [
    { label: 'System Health', href: '/api/health', desc: 'Raw health endpoint' },
    { label: 'Job Queue', href: '#/admin/jobs', desc: 'Queue status and workers' },
    { label: 'Database Explorer Guide', href: '#/docs/db-explorer', desc: 'How to safely use DB Explorer' },
    { label: 'Support Inbox', href: '#/support', desc: 'Contact support' },
  ];

  return (
    <div className="space-y-6">
      <Card className="border-0 shadow-sm bg-white">
        <CardContent className="p-6 flex items-center justify-between">
          <div>
            <div className="text-sm text-gray-500">API Health</div>
            <div className="text-xl font-semibold" style={{ color: '#2C3E50' }}>Platform Status</div>
          </div>
          {badge(health.ok)}
        </CardContent>
      </Card>

      <Card className="border-0 shadow-sm bg-white">
        <CardHeader>
          <CardTitle style={{ color: '#2C3E50' }}>Quick Links</CardTitle>
        </CardHeader>
        <CardContent className="divide-y">
          {links.map((l, i) => (
            <div key={i} className="flex items-center justify-between py-3">
              <div>
                <div className="font-medium text-gray-800">{l.label}</div>
                <div className="text-sm text-gray-500">{l.desc}</div>
              </div>
              <a
                href={l.href}
                target={l.href.startsWith('http') || l.href.startsWith('/api/') ? '_blank' : undefined}
                rel="noopener noreferrer"
                className="text-blue-600 hover:underline text-sm"
              >Open</a>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
