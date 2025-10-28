import React from 'react';
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { CreditCard } from "lucide-react";
import { useAuth } from "@/AuthContext";
import { makeApi } from "@/lib/apiClient";
import { useToast } from '@/hooks/use-toast';

export default function AdminBillingTab() {
  const { token } = useAuth();
  const { toast } = useToast();
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (!token) return;
    let canceled = false;
    setLoading(true);
    (async () => {
      try {
        const api = makeApi(token);
        const res = await api.get('/api/admin/billing/overview');
        if (!canceled) setData(res);
      } catch (e) {
        try { toast({ title: 'Failed to load billing overview', description: e?.message || 'Error' }); } catch {}
        if (!canceled) setData(null);
      } finally {
        if (!canceled) setLoading(false);
      }
    })();
    return () => { canceled = true; };
  }, [token]);

  const n = (v) => (typeof v === 'number' && isFinite(v) ? v : 0);
  const money = (cents) => (cents == null ? null : (Math.round(cents) / 100));
  const mrr = money(data?.gross_mrr_cents);

  const openStripe = () => {
    const url = data?.dashboard_url;
    if (!url) return;
    try { window.open(url, '_blank', 'noopener,noreferrer'); } catch {}
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold" style={{ color: '#2C3E50' }}>Billing Overview</h3>
          <p className="text-gray-600">Stripe-derived subscription metrics</p>
        </div>
        <Button onClick={openStripe} disabled={!data?.dashboard_url} className="text-white" style={{ backgroundColor: '#2C3E50' }}>
          <CreditCard className="w-4 h-4 mr-2" />
          Open Stripe Dashboard
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
        <Card className="border-0 shadow-sm bg-white">
          <CardContent className="p-6">
            <div className="text-sm text-gray-500">Active Subscriptions</div>
            <div className="text-3xl font-bold" style={{ color: '#2C3E50' }}>{n(data?.active_subscriptions)}</div>
          </CardContent>
        </Card>
        <Card className="border-0 shadow-sm bg-white">
          <CardContent className="p-6">
            <div className="text-sm text-gray-500">Trialing</div>
            <div className="text-3xl font-bold" style={{ color: '#2C3E50' }}>{n(data?.trialing)}</div>
          </CardContent>
        </Card>
        <Card className="border-0 shadow-sm bg-white">
          <CardContent className="p-6">
            <div className="text-sm text-gray-500">Canceled (30d)</div>
            <div className="text-3xl font-bold" style={{ color: '#2C3E50' }}>{n(data?.canceled_last_30d)}</div>
          </CardContent>
        </Card>
        <Card className="border-0 shadow-sm bg-white">
          <CardContent className="p-6">
            <div className="text-sm text-gray-500">Trials expiring (7d)</div>
            <div className="text-3xl font-bold" style={{ color: '#2C3E50' }}>{n(data?.trial_expiring_7d)}</div>
          </CardContent>
        </Card>
        <Card className="border-0 shadow-sm bg-white">
          <CardContent className="p-6">
            <div className="text-sm text-gray-500">Gross MRR</div>
            <div className="text-3xl font-bold" style={{ color: '#2C3E50' }}>
              {mrr != null ? (
                <>${n(mrr).toLocaleString()}</>
              ) : (
                <Badge variant="secondary">—</Badge>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {loading && <div className="text-sm text-gray-500">Loading…</div>}
    </div>
  );
}
