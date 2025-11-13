import { useState, useEffect } from 'react';
import { makeApi, isApiError } from '@/lib/apiClient';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { 
  Table, 
  TableBody, 
  TableCell, 
  TableHead, 
  TableHeader, 
  TableRow 
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useToast } from '@/hooks/use-toast';
import { 
  FileText, 
  Download, 
  AlertCircle, 
  ChevronDown, 
  ChevronRight,
  DollarSign,
  Clock,
  RefreshCw,
  List
} from 'lucide-react';

/**
 * Credit Ledger Component - Invoice-style view of credit spending
 * 
 * Shows:
 * - Episode-grouped charges (each episode is like an invoice)
 * - Account-level charges
 * - Detailed line items with timestamps
 * - Refund request functionality
 */
export default function CreditLedger({ token }) {
  const [viewMode, setViewMode] = useState('invoice'); // 'invoice' or 'lineitem'
  const [ledgerData, setLedgerData] = useState(null);
  const [chargesData, setChargesData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expandedEpisodes, setExpandedEpisodes] = useState(new Set());
  const [refundDialogOpen, setRefundDialogOpen] = useState(false);
  const [refundTarget, setRefundTarget] = useState(null);
  const [refundReason, setRefundReason] = useState('');
  const [refundNotes, setRefundNotes] = useState('');
  const [refundSubmitting, setRefundSubmitting] = useState(false);
  const [monthsBack, setMonthsBack] = useState(1);
  const [chargesPage, setChargesPage] = useState(1);
  const [chargesPerPage, setChargesPerPage] = useState(20);
  const { toast } = useToast();

  const fetchLedger = async () => {
    setLoading(true);
    try {
      const api = makeApi(token);
      const data = await api.get(`/api/billing/ledger/summary?months_back=${monthsBack}`);
      setLedgerData(data);
    } catch (err) {
      console.error('Failed to fetch ledger:', err);
      const msg = isApiError(err) ? (err.detail || err.error || 'Failed to load ledger') : String(err);
      toast({
        title: 'Error',
        description: msg,
        variant: 'destructive'
      });
    } finally {
      setLoading(false);
    }
  };

  const fetchCharges = async () => {
    setLoading(true);
    try {
      const api = makeApi(token);
      const data = await api.get(`/api/billing/ledger/charges?page=${chargesPage}&per_page=${chargesPerPage}`);
      setChargesData(data);
    } catch (err) {
      console.error('Failed to fetch charges:', err);
      const msg = isApiError(err) ? (err.detail || err.error || 'Failed to load charges') : String(err);
      toast({
        title: 'Error',
        description: msg,
        variant: 'destructive'
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (viewMode === 'invoice') {
      fetchLedger();
    } else {
      fetchCharges();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, monthsBack, viewMode, chargesPage, chargesPerPage]);

  const toggleEpisode = (episodeId) => {
    const newExpanded = new Set(expandedEpisodes);
    if (newExpanded.has(episodeId)) {
      newExpanded.delete(episodeId);
    } else {
      newExpanded.add(episodeId);
    }
    setExpandedEpisodes(newExpanded);
  };

  const openRefundDialog = (target) => {
    setRefundTarget(target);
    setRefundReason('');
    setRefundNotes('');
    setRefundDialogOpen(true);
  };

  const submitRefundRequest = async () => {
    if (!refundReason || refundReason.trim().length < 10) {
      toast({
        title: 'Error',
        description: 'Please provide a detailed reason (at least 10 characters)',
        variant: 'destructive'
      });
      return;
    }

    setRefundSubmitting(true);
    try {
      const api = makeApi(token);
      
      const payload = {
        reason: refundReason.trim(),
        notes: refundNotes || null
      };

      if (refundTarget.type === 'episode') {
        payload.episode_id = refundTarget.episode_id;
      } else if (refundTarget.type === 'line_item') {
        payload.ledger_entry_ids = [refundTarget.ledger_entry_id];
      }

      const response = await api.post('/api/billing/ledger/refund-request', payload);
      
      toast({
        title: 'Success',
        description: response.message || 'Refund request submitted successfully'
      });

      setRefundDialogOpen(false);
      setRefundReason('');
      setRefundTarget(null);
    } catch (err) {
      console.error('Failed to submit refund:', err);
      let errorMsg = 'Failed to submit refund request';
      
      if (isApiError(err)) {
        // Handle validation errors from FastAPI/Pydantic
        if (err.detail && Array.isArray(err.detail)) {
          // Pydantic validation errors come as an array
          const validationErrors = err.detail.map((e) => {
            const field = e.loc?.join('.') || 'field';
            return `${field}: ${e.msg}`;
          }).join(', ');
          errorMsg = `Validation error: ${validationErrors}`;
        } else if (err.detail) {
          errorMsg = typeof err.detail === 'string' ? err.detail : (err.detail.message || JSON.stringify(err.detail));
        } else if (err.error) {
          errorMsg = typeof err.error === 'string' ? err.error : JSON.stringify(err.error);
        }
      } else if (err instanceof Error) {
        errorMsg = err.message;
      } else if (typeof err === 'string') {
        errorMsg = err;
      }
      
      toast({
        title: 'Error',
        description: errorMsg,
        variant: 'destructive'
      });
    } finally {
      setRefundSubmitting(false);
    }
  };

  const formatDateTime = (timestamp) => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleString('en-US', {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
      });
    } catch {
      return timestamp;
    }
  };

  const formatReason = (reason) => {
    const reasonMap = {
      'TRANSCRIPTION': 'Transcription',
      'TTS_GENERATION': 'TTS Generation',
      'ASSEMBLY': 'Episode Assembly',
      'AUPHONIC_PROCESSING': 'Auphonic Processing',
      'STORAGE': 'Storage',
      'PROCESS_AUDIO': 'Audio Processing',
      'TTS_LIBRARY': 'TTS Library',
      'REFUND_ERROR': 'Refund (Error)',
      'MANUAL_ADJUST': 'Manual Adjustment'
    };
    return reasonMap[reason] || reason;
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <RefreshCw className="h-6 w-6 animate-spin text-gray-400" />
        <span className="ml-2 text-gray-600">Loading credit history...</span>
      </div>
    );
  }

  // Get summary data (from either view)
  const summaryData = viewMode === 'invoice' ? ledgerData : chargesData;
  const displayData = viewMode === 'invoice' ? ledgerData : chargesData;

  if (!displayData) {
    return (
      <div className="flex items-center justify-center p-8">
        <AlertCircle className="h-6 w-6 text-yellow-500 mr-2" />
        <span className="text-gray-600">No data available</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Summary Card */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span className="flex items-center">
              <DollarSign className="h-5 w-5 mr-2" />
              Credit Summary
            </span>
            <div className="flex gap-2">
              {viewMode === 'invoice' && (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setMonthsBack(1)}
                    className={monthsBack === 1 ? 'bg-blue-50' : ''}
                  >
                    1 Month
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setMonthsBack(3)}
                    className={monthsBack === 3 ? 'bg-blue-50' : ''}
                  >
                    3 Months
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setMonthsBack(6)}
                    className={monthsBack === 6 ? 'bg-blue-50' : ''}
                  >
                    6 Months
                  </Button>
                </>
              )}
            </div>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-blue-50 rounded-lg p-4">
              <div className="text-sm text-gray-600 mb-1">Credit Balance</div>
              <div className="text-2xl font-bold text-blue-600">
                {summaryData?.credits_balance !== undefined 
                  ? (summaryData.credits_balance === 999999 
                      ? 'Unlimited' 
                      : `${summaryData.credits_balance.toFixed(1)} credits`)
                  : (ledgerData?.total_credits_available === 999999 
                      ? 'Unlimited' 
                      : `${ledgerData?.total_credits_available?.toFixed(0) || 0} credits`)}
              </div>
              <div className="text-xs text-gray-500 mt-1">Total available</div>
            </div>
            
            <div className="bg-green-50 rounded-lg p-4">
              <div className="text-sm text-gray-600 mb-1">Purchased Credits</div>
              <div className="text-2xl font-bold text-green-700">
                {(() => {
                  const purchased = summaryData?.purchased_credits_available !== undefined
                    ? summaryData.purchased_credits_available
                    : (ledgerData?.purchased_credits_available !== undefined
                        ? ledgerData.purchased_credits_available
                        : 0);
                  return purchased > 0 ? `${purchased.toFixed(1)} credits` : '0.0 credits';
                })()}
              </div>
              <div className="text-xs text-gray-500 mt-1">Never expire</div>
            </div>
            
            <div className="bg-gray-50 rounded-lg p-4">
              <div className="text-sm text-gray-600 mb-1">Monthly Allocation</div>
              <div className="text-2xl font-bold text-gray-700">
                {(() => {
                  const monthlyAlloc = summaryData?.monthly_allocation_available !== undefined
                    ? summaryData.monthly_allocation_available
                    : (ledgerData?.monthly_allocation_available !== undefined
                        ? ledgerData.monthly_allocation_available
                        : (summaryData?.credits_allocated !== undefined
                            ? (summaryData.credits_allocated === null ? 999999 : summaryData.credits_allocated)
                            : 0));
                  if (monthlyAlloc >= 999999) {
                    return 'Unlimited';
                  }
                  return `${monthlyAlloc.toFixed(1)} credits`;
                })()}
              </div>
              <div className="text-xs text-gray-500 mt-1">
                {(() => {
                  const rollover = summaryData?.rollover_credits !== undefined
                    ? summaryData.rollover_credits
                    : (ledgerData?.rollover_credits !== undefined ? ledgerData.rollover_credits : 0);
                  if (rollover > 0) {
                    return `Includes ${rollover.toFixed(1)} rollover`;
                  }
                  return 'Monthly + rollover';
                })()}
              </div>
            </div>
            
            <div className="bg-red-50 rounded-lg p-4">
              <div className="text-sm text-gray-600 mb-1">Used This Month</div>
              <div className="text-2xl font-bold text-red-600">
                {summaryData?.credits_used_this_month !== undefined
                  ? `${summaryData.credits_used_this_month.toFixed(1)} credits`
                  : `${ledgerData?.total_credits_used_this_month?.toFixed(1) || 0} credits`}
              </div>
              <div className="text-xs text-gray-500 mt-1">Current period</div>
            </div>
          </div>
          
          {viewMode === 'invoice' && ledgerData && (
            <div className="mt-4 text-xs text-gray-500">
              Showing data from {formatDateTime(ledgerData.period_start)} to {formatDateTime(ledgerData.period_end)}
            </div>
          )}
        </CardContent>
      </Card>

      {/* View Mode Toggle */}
      <Tabs value={viewMode} onValueChange={setViewMode}>
        <TabsList>
          <TabsTrigger value="invoice">
            <FileText className="h-4 w-4 mr-2" />
            Invoice View
          </TabsTrigger>
          <TabsTrigger value="lineitem">
            <List className="h-4 w-4 mr-2" />
            Line Item View
          </TabsTrigger>
        </TabsList>

        <TabsContent value="invoice" className="space-y-6">
          {ledgerData && (
            <>
              {/* Episode Invoices */}
              {ledgerData.episode_invoices && ledgerData.episode_invoices.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center">
              <FileText className="h-5 w-5 mr-2" />
              Episode Charges (Invoice View)
            </CardTitle>
            <p className="text-sm text-gray-500 mt-1">
              Each episode shows all associated charges like an invoice. Click to expand details.
            </p>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {ledgerData.episode_invoices.map((invoice) => {
                const isExpanded = expandedEpisodes.has(invoice.episode_id);
                
                return (
                  <div key={invoice.episode_id} className="border rounded-lg">
                    {/* Episode Header */}
                    <div 
                      className="flex items-center justify-between p-4 cursor-pointer hover:bg-gray-50"
                      onClick={() => toggleEpisode(invoice.episode_id)}
                    >
                      <div className="flex items-center gap-3">
                        {isExpanded ? (
                          <ChevronDown className="h-5 w-5 text-gray-400" />
                        ) : (
                          <ChevronRight className="h-5 w-5 text-gray-400" />
                        )}
                        <div>
                          <div className="font-semibold">
                            {invoice.episode_number && `Episode ${invoice.episode_number}: `}
                            {invoice.episode_title}
                          </div>
                          <div className="text-xs text-gray-500">
                            {formatDateTime(invoice.created_at)} • {invoice.line_items.length} charges
                          </div>
                        </div>
                      </div>
                      
                      <div className="flex items-center gap-3">
                        <div className="text-right">
                          <div className="font-semibold text-red-600">
                            -{invoice.net_credits.toFixed(2)} credits
                          </div>
                          {invoice.total_credits_refunded > 0 && (
                            <div className="text-xs text-green-600">
                              +{invoice.total_credits_refunded.toFixed(2)} refunded
                            </div>
                          )}
                        </div>
                        
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={(e) => {
                            e.stopPropagation();
                            openRefundDialog({ 
                              type: 'episode', 
                              episode_id: invoice.episode_id,
                              episode_title: invoice.episode_title,
                              credits: invoice.net_credits
                            });
                          }}
                        >
                          Request Refund
                        </Button>
                      </div>
                    </div>

                    {/* Expanded Line Items */}
                    {isExpanded && (
                      <div className="border-t bg-gray-50 p-4">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Timestamp</TableHead>
                              <TableHead>Type</TableHead>
                              <TableHead>Credits</TableHead>
                              <TableHead>Notes</TableHead>
                              <TableHead></TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {invoice.line_items.map((item) => (
                              <TableRow key={item.id}>
                                <TableCell className="text-xs">
                                  <div className="flex items-center gap-1">
                                    <Clock className="h-3 w-3 text-gray-400" />
                                    {formatDateTime(item.timestamp)}
                                  </div>
                                </TableCell>
                                <TableCell>
                                  <Badge variant={item.direction === 'DEBIT' ? 'destructive' : 'secondary'}>
                                    {formatReason(item.reason)}
                                  </Badge>
                                </TableCell>
                                <TableCell className={item.direction === 'DEBIT' ? 'text-red-600' : 'text-green-600'}>
                                  {item.direction === 'DEBIT' ? '-' : '+'}
                                  {item.credits.toFixed(2)}
                                </TableCell>
                                <TableCell className="text-xs text-gray-600">
                                  {item.notes || '-'}
                                  {item.cost_breakdown && (
                                    <div className="text-xs text-gray-400 mt-1">
                                      {item.cost_breakdown.pipeline && `Pipeline: ${item.cost_breakdown.pipeline}`}
                                      {item.cost_breakdown.multiplier && ` (${item.cost_breakdown.multiplier}x)`}
                                    </div>
                                  )}
                                </TableCell>
                                <TableCell>
                                  {item.direction === 'DEBIT' && (
                                    <>
                                      {item.refund_status === 'pending' && (
                                        <Badge variant="secondary" className="text-xs">
                                          Requested
                                        </Badge>
                                      )}
                                      {item.refund_status === 'approved' && (
                                        <Badge variant="default" className="text-xs bg-green-600 text-white">
                                          Refund Approved
                                        </Badge>
                                      )}
                                      {item.refund_status === 'denied' && (
                                        <div className="flex items-center gap-2">
                                          <Badge variant="destructive" className="text-xs">
                                            Refund Denied
                                          </Badge>
                                          {item.refund_denial_reason && (
                                            <Button
                                              variant="ghost"
                                              size="sm"
                                              className="h-6 text-xs text-red-600 hover:text-red-700"
                                              onClick={() => {
                                                toast({
                                                  title: 'Refund Denial Reason',
                                                  description: item.refund_denial_reason,
                                                  variant: 'destructive'
                                                });
                                              }}
                                            >
                                              View Reason
                                            </Button>
                                          )}
                                        </div>
                                      )}
                                      {!item.refund_status && (
                                        <Button
                                          variant="ghost"
                                          size="sm"
                                          onClick={() => openRefundDialog({
                                            type: 'line_item',
                                            ledger_entry_id: item.id,
                                            reason: item.reason,
                                            credits: item.credits,
                                            timestamp: item.timestamp
                                          })}
                                        >
                                          Refund
                                        </Button>
                                      )}
                                    </>
                                  )}
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

              {/* Account-level charges */}
              {ledgerData.account_charges && ledgerData.account_charges.length > 0 && (
                <Card>
                  <CardHeader>
                    <CardTitle>Account-Level Charges</CardTitle>
                    <p className="text-sm text-gray-500 mt-1">
                      Charges not associated with a specific episode
                    </p>
                  </CardHeader>
                  <CardContent>
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead>Timestamp</TableHead>
                          <TableHead>Type</TableHead>
                          <TableHead>Credits</TableHead>
                          <TableHead>Notes</TableHead>
                          <TableHead></TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {ledgerData.account_charges.map((item) => (
                          <TableRow key={item.id}>
                            <TableCell className="text-xs">
                              {formatDateTime(item.timestamp)}
                            </TableCell>
                            <TableCell>
                              <Badge variant={item.direction === 'DEBIT' ? 'destructive' : 'secondary'}>
                                {formatReason(item.reason)}
                              </Badge>
                            </TableCell>
                            <TableCell className={item.direction === 'DEBIT' ? 'text-red-600' : 'text-green-600'}>
                              {item.direction === 'DEBIT' ? '-' : '+'}
                              {item.credits.toFixed(2)}
                            </TableCell>
                            <TableCell className="text-xs text-gray-600">
                              {item.notes || '-'}
                            </TableCell>
                            <TableCell>
                              {item.direction === 'DEBIT' && (
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => openRefundDialog({
                                    type: 'line_item',
                                    ledger_entry_id: item.id,
                                    reason: item.reason,
                                    credits: item.credits,
                                    timestamp: item.timestamp
                                  })}
                                >
                                  Refund
                                </Button>
                              )}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </CardContent>
                </Card>
              )}

              {/* Empty state */}
              {(!ledgerData.episode_invoices || ledgerData.episode_invoices.length === 0) &&
               (!ledgerData.account_charges || ledgerData.account_charges.length === 0) && (
                <Card>
                  <CardContent className="flex flex-col items-center justify-center py-12">
                    <FileText className="h-12 w-12 text-gray-300 mb-4" />
                    <p className="text-gray-600 text-center">
                      No credit charges found in the selected period
                    </p>
                    <p className="text-sm text-gray-400 text-center mt-2">
                      Charges will appear here after you create episodes or use features
                    </p>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </TabsContent>

        <TabsContent value="lineitem" className="space-y-6">
          {chargesData && (
            <>
              {/* Monthly Breakdown */}
              {chargesData.credits_breakdown && (
                <Card>
                  <CardHeader>
                    <CardTitle>Monthly Breakdown</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="bg-gray-50 rounded-lg p-4 space-y-2">
                      {chargesData.credits_breakdown.transcription > 0 && (
                        <div className="flex justify-between text-sm">
                          <span className="text-gray-600">Transcription</span>
                          <span className="font-medium">{chargesData.credits_breakdown.transcription.toFixed(1)} credits</span>
                        </div>
                      )}
                      {chargesData.credits_breakdown.assembly > 0 && (
                        <div className="flex justify-between text-sm">
                          <span className="text-gray-600">Episode Assembly</span>
                          <span className="font-medium">{chargesData.credits_breakdown.assembly.toFixed(1)} credits</span>
                        </div>
                      )}
                      {chargesData.credits_breakdown.tts_generation > 0 && (
                        <div className="flex justify-between text-sm">
                          <span className="text-gray-600">TTS Generation</span>
                          <span className="font-medium">{chargesData.credits_breakdown.tts_generation.toFixed(1)} credits</span>
                        </div>
                      )}
                      {chargesData.credits_breakdown.auphonic_processing > 0 && (
                        <div className="flex justify-between text-sm">
                          <span className="text-gray-600">Auphonic Processing</span>
                          <span className="font-medium">{chargesData.credits_breakdown.auphonic_processing.toFixed(1)} credits</span>
                        </div>
                      )}
                      {chargesData.credits_breakdown.storage > 0 && (
                        <div className="flex justify-between text-sm">
                          <span className="text-gray-600">Storage</span>
                          <span className="font-medium">{chargesData.credits_breakdown.storage.toFixed(1)} credits</span>
                        </div>
                      )}
                      {chargesData.credits_breakdown.ai_metadata > 0 && (
                        <div className="flex justify-between text-sm">
                          <span className="text-gray-600">AI Metadata</span>
                          <span className="font-medium">{chargesData.credits_breakdown.ai_metadata.toFixed(1)} credits</span>
                        </div>
                      )}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Charges Table */}
              {chargesData.charges && chargesData.charges.length > 0 && (
                <Card>
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle>Recent Charges</CardTitle>
                      <div className="flex items-center gap-2">
                        <Select value={String(chargesPerPage)} onValueChange={(v) => { setChargesPerPage(Number(v)); setChargesPage(1); }}>
                          <SelectTrigger className="w-20 h-8 text-xs">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="20">20</SelectItem>
                            <SelectItem value="50">50</SelectItem>
                            <SelectItem value="100">100</SelectItem>
                          </SelectContent>
                        </Select>
                        <span className="text-xs text-gray-500">per page</span>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <div className="border rounded-lg overflow-hidden">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead className="text-xs">Date</TableHead>
                            <TableHead className="text-xs">Type</TableHead>
                            <TableHead className="text-xs">Episode</TableHead>
                            <TableHead className="text-xs text-right">Credits</TableHead>
                            <TableHead className="text-xs"></TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {chargesData.charges.map((charge) => (
                            <TableRow key={charge.id}>
                              <TableCell className="text-xs text-gray-600">
                                {formatDateTime(charge.timestamp)}
                              </TableCell>
                              <TableCell className="text-xs">
                                <Badge variant={charge.direction === 'DEBIT' ? 'destructive' : 'default'} className="text-xs">
                                  {formatReason(charge.reason)}
                                </Badge>
                              </TableCell>
                              <TableCell className="text-xs text-gray-600 truncate max-w-[200px]">
                                {charge.episode_title || charge.notes || '—'}
                              </TableCell>
                              <TableCell className={`text-xs text-right font-medium ${charge.direction === 'DEBIT' ? 'text-red-600' : 'text-green-600'}`}>
                                {charge.direction === 'DEBIT' ? '-' : '+'}{charge.credits.toFixed(1)}
                              </TableCell>
                              <TableCell>
                                {charge.direction === 'DEBIT' && (
                                  <>
                                    {charge.refund_status === 'pending' && (
                                      <Badge variant="secondary" className="text-xs">
                                        Requested
                                      </Badge>
                                    )}
                                    {charge.refund_status === 'approved' && (
                                      <Badge variant="default" className="text-xs bg-green-600 text-white">
                                        Refund Approved
                                      </Badge>
                                    )}
                                    {charge.refund_status === 'denied' && (
                                      <div className="flex items-center gap-2">
                                        <Badge variant="destructive" className="text-xs">
                                          Refund Denied
                                        </Badge>
                                        {charge.refund_denial_reason && (
                                          <Button
                                            variant="ghost"
                                            size="sm"
                                            className="h-6 text-xs text-red-600 hover:text-red-700"
                                            onClick={() => {
                                              toast({
                                                title: 'Refund Denial Reason',
                                                description: charge.refund_denial_reason,
                                                variant: 'destructive'
                                              });
                                            }}
                                          >
                                            View Reason
                                          </Button>
                                        )}
                                      </div>
                                    )}
                                    {!charge.refund_status && (
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => openRefundDialog({
                                          type: 'line_item',
                                          ledger_entry_id: charge.id,
                                          reason: charge.reason,
                                          credits: charge.credits,
                                          timestamp: charge.timestamp
                                        })}
                                      >
                                        Request Refund
                                      </Button>
                                    )}
                                  </>
                                )}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>
                    {/* Pagination */}
                    {chargesData.pagination && chargesData.pagination.total_pages > 1 && (
                      <div className="flex items-center justify-between mt-3">
                        <div className="text-xs text-gray-500">
                          Page {chargesData.pagination.page} of {chargesData.pagination.total_pages} 
                          ({chargesData.pagination.total} total)
                        </div>
                        <div className="flex gap-2">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setChargesPage(p => Math.max(1, p - 1))}
                            disabled={chargesPage === 1}
                          >
                            Previous
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => setChargesPage(p => Math.min(chargesData.pagination.total_pages, p + 1))}
                            disabled={chargesPage >= chargesData.pagination.total_pages}
                          >
                            Next
                          </Button>
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>
              )}

              {/* Empty state */}
              {(!chargesData.charges || chargesData.charges.length === 0) && (
                <Card>
                  <CardContent className="flex flex-col items-center justify-center py-12">
                    <List className="h-12 w-12 text-gray-300 mb-4" />
                    <p className="text-gray-600 text-center">
                      No credit charges found
                    </p>
                    <p className="text-sm text-gray-400 text-center mt-2">
                      Charges will appear here after you create episodes or use features
                    </p>
                  </CardContent>
                </Card>
              )}
            </>
          )}
        </TabsContent>
      </Tabs>

      {/* Refund Dialog */}
      <Dialog open={refundDialogOpen} onOpenChange={setRefundDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Request Refund</DialogTitle>
            <DialogDescription>
              {refundTarget?.type === 'episode' && (
                <>
                  Request a refund for episode "{refundTarget.episode_title}" 
                  ({refundTarget.credits.toFixed(2)} credits)
                </>
              )}
              {refundTarget?.type === 'line_item' && (
                <>
                  Request a refund for {formatReason(refundTarget.reason)} charge 
                  ({refundTarget.credits.toFixed(2)} credits) from {formatDateTime(refundTarget.timestamp)}
                </>
              )}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div>
              <label className="text-sm font-medium mb-2 block">
                Reason for refund request *
              </label>
              <Textarea
                placeholder="Please explain why you're requesting a refund (minimum 10 characters)"
                value={refundReason}
                onChange={(e) => setRefundReason(e.target.value)}
                rows={4}
                className="w-full"
              />
              <p className="text-xs text-gray-500 mt-1">
                Our team will review your request within 24-48 hours
              </p>
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">
                Additional Notes (Optional)
              </label>
              <Textarea
                placeholder="Any additional information that might help us process your request"
                value={refundNotes}
                onChange={(e) => setRefundNotes(e.target.value)}
                rows={3}
                className="w-full"
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => setRefundDialogOpen(false)}
              disabled={refundSubmitting}
            >
              Cancel
            </Button>
            <Button
              onClick={submitRefundRequest}
              disabled={refundSubmitting || !refundReason || refundReason.trim().length < 10}
            >
              {refundSubmitting ? 'Submitting...' : 'Submit Request'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
