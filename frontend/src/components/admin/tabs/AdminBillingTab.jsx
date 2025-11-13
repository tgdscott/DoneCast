import React from 'react';
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { CreditCard, RefreshCw, AlertCircle, DollarSign, Gift } from "lucide-react";
import { useAuth } from "@/AuthContext";
import { makeApi } from "@/lib/apiClient";
import { useToast } from '@/hooks/use-toast';
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

export default function AdminBillingTab({ onViewUserCredits }) {
  const { token } = useAuth();
  const { toast } = useToast();
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(false);
  const [refundRequests, setRefundRequests] = React.useState([]);
  const [refundRequestsLoading, setRefundRequestsLoading] = React.useState(false);
  const [refundLogs, setRefundLogs] = React.useState([]);
  const [refundLogsLoading, setRefundLogsLoading] = React.useState(false);
  const [creditAwardLogs, setCreditAwardLogs] = React.useState([]);
  const [creditAwardLogsLoading, setCreditAwardLogsLoading] = React.useState(false);

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

  React.useEffect(() => {
    if (!token) return;
    let canceled = false;
    setRefundRequestsLoading(true);
    (async () => {
      try {
        const api = makeApi(token);
        const res = await api.get('/api/admin/users/refund-requests');
        if (!canceled) setRefundRequests(res || []);
      } catch (e) {
        try { toast({ title: 'Failed to load refund requests', description: e?.message || 'Error' }); } catch {}
        if (!canceled) setRefundRequests([]);
      } finally {
        if (!canceled) setRefundRequestsLoading(false);
      }
    })();
    return () => { canceled = true; };
  }, [token]);

  React.useEffect(() => {
    if (!token) return;
    let canceled = false;
    setRefundLogsLoading(true);
    (async () => {
      try {
        const api = makeApi(token);
        const res = await api.get('/api/admin/admin-action-logs/refunds?limit=100');
        if (!canceled) setRefundLogs(res || []);
      } catch (e) {
        try { toast({ title: 'Failed to load refund logs', description: e?.message || 'Error' }); } catch {}
        if (!canceled) setRefundLogs([]);
      } finally {
        if (!canceled) setRefundLogsLoading(false);
      }
    })();
    return () => { canceled = true; };
  }, [token]);

  React.useEffect(() => {
    if (!token) return;
    let canceled = false;
    setCreditAwardLogsLoading(true);
    (async () => {
      try {
        const api = makeApi(token);
        const res = await api.get('/api/admin/admin-action-logs/credits?limit=100');
        if (!canceled) setCreditAwardLogs(res || []);
      } catch (e) {
        try { toast({ title: 'Failed to load credit award logs', description: e?.message || 'Error' }); } catch {}
        if (!canceled) setCreditAwardLogs([]);
      } finally {
        if (!canceled) setCreditAwardLogsLoading(false);
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

  const formatDate = (dateString) => {
    if (!dateString) return '—';
    try {
      return new Date(dateString).toLocaleString();
    } catch {
      return dateString;
    }
  };

  const calculateRefundTotal = () => {
    return refundLogs
      .filter(log => log.action_type === 'REFUND_APPROVED' && log.refund_amount)
      .reduce((sum, log) => sum + (log.refund_amount || 0), 0);
  };

  const calculateCreditAwardTotal = () => {
    return creditAwardLogs
      .filter(log => log.credit_amount)
      .reduce((sum, log) => sum + (log.credit_amount || 0), 0);
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

      {/* Refund Requests Section */}
      <Card className="border-l-4 border-l-orange-500">
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <div>
              <span>Refund Requests</span>
              {refundRequests.length > 0 && (
                <Badge variant="default" className="ml-2">
                  {refundRequests.filter(r => !r.read_at).length} Pending
                </Badge>
              )}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setRefundRequestsLoading(true);
                const api = makeApi(token);
                api.get('/api/admin/users/refund-requests')
                  .then(setRefundRequests)
                  .catch((e) => {
                    toast({ title: 'Failed to load refund requests', description: e?.message || 'Error' });
                    setRefundRequests([]);
                  })
                  .finally(() => setRefundRequestsLoading(false));
              }}
              disabled={refundRequestsLoading}
            >
              <RefreshCw className={`w-4 h-4 mr-2 ${refundRequestsLoading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </CardTitle>
          <p className="text-sm text-gray-600 mt-1">
            Review user refund requests and process them from the credit viewer
          </p>
        </CardHeader>
        <CardContent>
          {refundRequestsLoading ? (
            <div className="text-sm text-gray-500">Loading refund requests…</div>
          ) : refundRequests.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <AlertCircle className="w-12 h-12 mx-auto mb-2 text-gray-300" />
              <p>No refund requests pending</p>
            </div>
          ) : (
            <div className="border rounded-lg overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="text-xs">Date</TableHead>
                    <TableHead className="text-xs">User</TableHead>
                    <TableHead className="text-xs">Reason</TableHead>
                    <TableHead className="text-xs">Entries</TableHead>
                    <TableHead className="text-xs">Status</TableHead>
                    <TableHead className="text-xs"></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {refundRequests.map((request) => (
                    <TableRow key={request.notification_id}>
                      <TableCell className="text-xs text-gray-600">
                        {new Date(request.created_at).toLocaleDateString()}
                      </TableCell>
                      <TableCell className="text-xs">
                        <button
                          onClick={() => onViewUserCredits && onViewUserCredits(request.user_id)}
                          className="text-blue-600 hover:underline"
                        >
                          {request.user_email}
                        </button>
                      </TableCell>
                      <TableCell className="text-xs text-gray-600 max-w-[300px]">
                        <div className="truncate" title={request.reason}>
                          {request.reason}
                        </div>
                        {request.notes && (
                          <div className="text-xs text-gray-400 mt-1 truncate" title={request.notes}>
                            Notes: {request.notes}
                          </div>
                        )}
                      </TableCell>
                      <TableCell className="text-xs text-gray-600">
                        {request.ledger_entry_ids?.length || 0} {request.episode_id ? 'episode' : 'entries'}
                      </TableCell>
                      <TableCell>
                        <Badge variant={request.read_at ? 'secondary' : 'default'}>
                          {request.read_at ? 'Reviewed' : 'Pending'}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="default"
                          size="sm"
                          onClick={() => {
                            if (onViewUserCredits) {
                              // Open credit viewer with refund request details
                              onViewUserCredits(request.user_id, 1, 20, {
                                notification_id: request.notification_id,
                                reason: request.reason,
                                notes: request.notes,
                                ledger_entry_ids: request.ledger_entry_ids || [],
                                episode_id: request.episode_id
                              });
                            }
                          }}
                          className="text-white"
                          style={{ backgroundColor: '#2C3E50' }}
                        >
                          Review & Process
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Refund and Credit Award Logs */}
      <Tabs defaultValue="refunds" className="w-full">
        <TabsList className="grid w-full grid-cols-2">
          <TabsTrigger value="refunds">
            <DollarSign className="w-4 h-4 mr-2" />
            Refund Logs
            {refundLogs.length > 0 && (
              <Badge variant="secondary" className="ml-2">
                {refundLogs.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger value="credits">
            <Gift className="w-4 h-4 mr-2" />
            Credit Awards
            {creditAwardLogs.length > 0 && (
              <Badge variant="secondary" className="ml-2">
                {creditAwardLogs.length}
              </Badge>
            )}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="refunds" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <div>
                  <span>Refund Logs</span>
                  {refundLogs.length > 0 && (
                    <span className="ml-2 text-sm font-normal text-gray-500">
                      Total Refunded: {calculateRefundTotal().toFixed(2)} credits
                    </span>
                  )}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setRefundLogsLoading(true);
                    const api = makeApi(token);
                    api.get('/api/admin/admin-action-logs/refunds?limit=100')
                      .then(setRefundLogs)
                      .catch((e) => {
                        toast({ title: 'Failed to load refund logs', description: e?.message || 'Error' });
                        setRefundLogs([]);
                      })
                      .finally(() => setRefundLogsLoading(false));
                  }}
                  disabled={refundLogsLoading}
                >
                  <RefreshCw className={`w-4 h-4 mr-2 ${refundLogsLoading ? 'animate-spin' : ''}`} />
                  Refresh
                </Button>
              </CardTitle>
              <p className="text-sm text-gray-600 mt-1">
                Log of all approved or denied refund requests
              </p>
            </CardHeader>
            <CardContent>
              {refundLogsLoading ? (
                <div className="text-sm text-gray-500">Loading refund logs…</div>
              ) : refundLogs.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  <AlertCircle className="w-12 h-12 mx-auto mb-2 text-gray-300" />
                  <p>No refund logs found</p>
                </div>
              ) : (
                <div className="border rounded-lg overflow-hidden">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">Date</TableHead>
                        <TableHead className="text-xs">Status</TableHead>
                        <TableHead className="text-xs">User</TableHead>
                        <TableHead className="text-xs">Amount</TableHead>
                        <TableHead className="text-xs">Admin</TableHead>
                        <TableHead className="text-xs">Notes</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {refundLogs.map((log) => (
                        <TableRow key={log.id}>
                          <TableCell className="text-xs text-gray-600">
                            {formatDate(log.created_at)}
                          </TableCell>
                          <TableCell>
                            <Badge 
                              variant={log.action_type === 'REFUND_APPROVED' ? 'default' : 'destructive'}
                            >
                              {log.action_type === 'REFUND_APPROVED' ? 'Approved' : 'Denied'}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-xs">
                            <button
                              onClick={() => onViewUserCredits && onViewUserCredits(log.target_user_id)}
                              className="text-blue-600 hover:underline"
                            >
                              {log.target_user_email}
                            </button>
                          </TableCell>
                          <TableCell className="text-xs font-medium">
                            {log.refund_amount != null ? `${log.refund_amount.toFixed(2)} credits` : '—'}
                          </TableCell>
                          <TableCell className="text-xs text-gray-600">
                            {log.admin_email}
                          </TableCell>
                          <TableCell className="text-xs text-gray-600 max-w-[200px]">
                            <div className="truncate" title={log.denial_reason || log.notes || ''}>
                              {log.denial_reason || log.notes || '—'}
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="credits" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <div>
                  <span>Credit Award Logs</span>
                  {creditAwardLogs.length > 0 && (
                    <span className="ml-2 text-sm font-normal text-gray-500">
                      Total Awarded: {calculateCreditAwardTotal().toFixed(2)} credits
                    </span>
                  )}
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setCreditAwardLogsLoading(true);
                    const api = makeApi(token);
                    api.get('/api/admin/admin-action-logs/credits?limit=100')
                      .then(setCreditAwardLogs)
                      .catch((e) => {
                        toast({ title: 'Failed to load credit award logs', description: e?.message || 'Error' });
                        setCreditAwardLogs([]);
                      })
                      .finally(() => setCreditAwardLogsLoading(false));
                  }}
                  disabled={creditAwardLogsLoading}
                >
                  <RefreshCw className={`w-4 h-4 mr-2 ${creditAwardLogsLoading ? 'animate-spin' : ''}`} />
                  Refresh
                </Button>
              </CardTitle>
              <p className="text-sm text-gray-600 mt-1">
                Log of all credits awarded to users for other purposes
              </p>
            </CardHeader>
            <CardContent>
              {creditAwardLogsLoading ? (
                <div className="text-sm text-gray-500">Loading credit award logs…</div>
              ) : creditAwardLogs.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  <AlertCircle className="w-12 h-12 mx-auto mb-2 text-gray-300" />
                  <p>No credit award logs found</p>
                </div>
              ) : (
                <div className="border rounded-lg overflow-hidden">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="text-xs">Date</TableHead>
                        <TableHead className="text-xs">User</TableHead>
                        <TableHead className="text-xs">Amount</TableHead>
                        <TableHead className="text-xs">Reason</TableHead>
                        <TableHead className="text-xs">Admin</TableHead>
                        <TableHead className="text-xs">Notes</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {creditAwardLogs.map((log) => (
                        <TableRow key={log.id}>
                          <TableCell className="text-xs text-gray-600">
                            {formatDate(log.created_at)}
                          </TableCell>
                          <TableCell className="text-xs">
                            <button
                              onClick={() => onViewUserCredits && onViewUserCredits(log.target_user_id)}
                              className="text-blue-600 hover:underline"
                            >
                              {log.target_user_email}
                            </button>
                          </TableCell>
                          <TableCell className="text-xs font-medium text-green-600">
                            {log.credit_amount != null ? `+${log.credit_amount.toFixed(2)} credits` : '—'}
                          </TableCell>
                          <TableCell className="text-xs text-gray-600 max-w-[200px]">
                            <div className="truncate" title={log.award_reason || ''}>
                              {log.award_reason || '—'}
                            </div>
                          </TableCell>
                          <TableCell className="text-xs text-gray-600">
                            {log.admin_email}
                          </TableCell>
                          <TableCell className="text-xs text-gray-600 max-w-[200px]">
                            <div className="truncate" title={log.notes || ''}>
                              {log.notes || '—'}
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
