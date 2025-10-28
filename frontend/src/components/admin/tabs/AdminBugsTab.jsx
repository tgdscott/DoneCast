import React from 'react';
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Bug, Zap, MessageSquare } from "lucide-react";
import { makeApi } from "@/lib/apiClient";
import { useToast } from '@/hooks/use-toast';

export default function AdminBugsTab({ token }) {
  const { toast } = useToast();
  const [feedback, setFeedback] = React.useState([]);
  const [stats, setStats] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [filterType, setFilterType] = React.useState('all');
  const [filterSeverity, setFilterSeverity] = React.useState('all');
  const [filterStatus, setFilterStatus] = React.useState('new');
  const [selectedFeedback, setSelectedFeedback] = React.useState(null);
  const [detailsLoading, setDetailsLoading] = React.useState(false);
  const [adminData, setAdminData] = React.useState({});
  const [savingAdmin, setSavingAdmin] = React.useState(false);

  const loadFeedback = async () => {
    if (!token) return;
    setLoading(true);
    try {
      const api = makeApi(token);
      const params = new URLSearchParams();
      if (filterType !== 'all') params.set('type', filterType);
      if (filterSeverity !== 'all') params.set('severity', filterSeverity);
      if (filterStatus !== 'all') params.set('status', filterStatus);
      
      const [feedbackData, statsData] = await Promise.all([
        api.get(`/api/admin/feedback?${params.toString()}`),
        api.get('/api/admin/feedback/stats'),
      ]);
      
      setFeedback(feedbackData);
      setStats(statsData);
    } catch (err) {
      console.error('Failed to load feedback:', err);
      toast({ variant: 'destructive', title: 'Failed to load bug reports', description: err.message });
    } finally {
      setLoading(false);
    }
  };

  const loadFeedbackDetail = async (feedbackId) => {
    setDetailsLoading(true);
    try {
      const api = makeApi(token);
      const detail = await api.get(`/api/admin/feedback/${feedbackId}/detail`);
      setSelectedFeedback(detail);
      setAdminData({
        admin_notes: detail.admin_notes || '',
        assigned_to: detail.assigned_to || '',
        priority: detail.priority || 'medium',
        related_issues: detail.related_issues || '',
        fix_version: detail.fix_version || '',
        status: detail.status || 'new'
      });
    } catch (err) {
      toast({ variant: 'destructive', title: 'Failed to load details', description: err.message });
    } finally {
      setDetailsLoading(false);
    }
  };

  React.useEffect(() => {
    loadFeedback();
  }, [token, filterType, filterSeverity, filterStatus]);

  const updateStatus = async (feedbackId, newStatus) => {
    try {
      const api = makeApi(token);
      await api.patch(`/api/admin/feedback/${feedbackId}/status?status=${newStatus}`);
      toast({ title: 'Status updated', description: `Marked as ${newStatus}` });
      loadFeedback(); // Reload
    } catch (err) {
      toast({ variant: 'destructive', title: 'Failed to update status', description: err.message });
    }
  };

  const saveAdminData = async (feedbackId) => {
    setSavingAdmin(true);
    try {
      const api = makeApi(token);
      // Filter out empty strings - backend expects null for optional fields
      const payload = Object.fromEntries(
        Object.entries(adminData).filter(([_, v]) => v !== '')
      );
      console.log('[Admin Data Save] Sending:', payload); // DEBUG
      await api.patch(`/api/admin/feedback/${feedbackId}/admin-data`, payload);
      toast({ title: 'Saved', description: 'Admin data updated successfully' });
      loadFeedback(); // Reload list
      if (selectedFeedback?.id === feedbackId) {
        loadFeedbackDetail(feedbackId); // Reload details
      }
    } catch (err) {
      console.error('[Admin Data Save] Error:', err); // DEBUG
      const errorMsg = err.detail || err.message || 'Unknown error';
      toast({ variant: 'destructive', title: 'Failed to save', description: errorMsg });
    } finally {
      setSavingAdmin(false);
    }
  };

  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'critical': return 'bg-red-100 text-red-800';
      case 'high': return 'bg-orange-100 text-orange-800';
      case 'medium': return 'bg-yellow-100 text-yellow-800';
      case 'low': return 'bg-blue-100 text-blue-800';
      default: return 'bg-gray-100 text-gray-800';
    }
  };

  const getTypeIcon = (type) => {
    switch (type) {
      case 'bug': return <Bug className="h-4 w-4 text-red-600" />;
      case 'feature_request': return <Zap className="h-4 w-4 text-blue-600" />;
      default: return <MessageSquare className="h-4 w-4 text-gray-600" />;
    }
  };

  // Generate short bug ID from UUID (e.g., "BUG-ef781d48")
  const getBugId = (uuid) => {
    const shortId = uuid.split('-')[0];
    return `BUG-${shortId}`;
  };

  if (loading) return <div className="text-center p-8">Loading bug reports...</div>;

  return (
    <div className="space-y-6">
      {/* Stats Overview - Bugs vs Feature Requests */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
          <Card>
            <CardContent className="pt-6">
              <div className="text-2xl font-bold text-red-600">{stats.bugs}</div>
              <div className="text-xs text-gray-600">Bugs</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="text-2xl font-bold text-blue-600">{stats.feature_requests}</div>
              <div className="text-xs text-gray-600">Feature Requests</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="text-2xl font-bold text-orange-600">{stats.critical}</div>
              <div className="text-xs text-gray-600">Critical</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="text-2xl font-bold text-yellow-600">{stats.unresolved}</div>
              <div className="text-xs text-gray-600">Unresolved</div>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="text-2xl font-bold text-green-600">{stats.resolved}</div>
              <div className="text-xs text-gray-600">Resolved</div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-4 items-center">
        <Select value={filterType} onValueChange={setFilterType}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Type" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Types</SelectItem>
            <SelectItem value="bug">Bugs</SelectItem>
            <SelectItem value="feature_request">Features</SelectItem>
            <SelectItem value="question">Questions</SelectItem>
            <SelectItem value="complaint">Complaints</SelectItem>
          </SelectContent>
        </Select>

        <Select value={filterSeverity} onValueChange={setFilterSeverity}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Severity" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Severities</SelectItem>
            <SelectItem value="critical">Critical</SelectItem>
            <SelectItem value="high">High</SelectItem>
            <SelectItem value="medium">Medium</SelectItem>
            <SelectItem value="low">Low</SelectItem>
          </SelectContent>
        </Select>

        <Select value={filterStatus} onValueChange={setFilterStatus}>
          <SelectTrigger className="w-40">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All Statuses</SelectItem>
            <SelectItem value="new">New</SelectItem>
            <SelectItem value="acknowledged">Acknowledged</SelectItem>
            <SelectItem value="investigating">Investigating</SelectItem>
            <SelectItem value="resolved">Resolved</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Feedback List */}
      <div className="space-y-4">
        {feedback.length === 0 ? (
          <Card>
            <CardContent className="p-8 text-center text-gray-500">
              No bug reports found with current filters.
            </CardContent>
          </Card>
        ) : (
          feedback.map((item) => (
            <Card key={item.id} className="hover:shadow-md transition-shadow">
              <CardContent className="p-6">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 space-y-2">
                    <div className="flex items-center gap-2">
                      {getTypeIcon(item.type)}
                      <Badge variant="outline" className="font-mono text-xs">{getBugId(item.id)}</Badge>
                      <h3 className="font-semibold text-lg">{item.title}</h3>
                      <Badge className={getSeverityColor(item.severity)}>
                        {item.severity}
                      </Badge>
                      <Badge variant="outline">{item.status}</Badge>
                      {item.priority && item.priority !== 'medium' && (
                        <Badge variant="secondary">P: {item.priority}</Badge>
                      )}
                    </div>
                    
                    <p className="text-gray-700">{item.description}</p>
                    
                    <div className="grid grid-cols-2 gap-2 text-sm text-gray-600">
                      <div><strong>User:</strong> {item.user_email} ({item.user_name})</div>
                      <div><strong>Date:</strong> {new Date(item.created_at).toLocaleDateString()}</div>
                      {item.assigned_to && <div><strong>Assigned:</strong> {item.assigned_to}</div>}
                      {item.fix_version && <div><strong>Fix Version:</strong> {item.fix_version}</div>}
                      {item.page_url && <div><strong>Page:</strong> {item.page_url}</div>}
                      {item.category && <div><strong>Category:</strong> {item.category}</div>}
                      {item.browser_info && <div className="col-span-2"><strong>Browser:</strong> {item.browser_info}</div>}
                      {item.error_logs && <div className="col-span-2"><strong>Error:</strong> <code className="text-xs bg-gray-100 px-1">{item.error_logs}</code></div>}
                    </div>

                    {/* Technical Details - Collapsible */}
                    {(selectedFeedback?.id === item.id) && (
                      <div className="mt-4 space-y-4 border-t pt-4">
                        {detailsLoading ? (
                          <div className="text-center text-gray-500">Loading details...</div>
                        ) : (
                          <>
                            {/* Technical Context Section */}
                            {(selectedFeedback.user_agent || selectedFeedback.console_errors || selectedFeedback.network_errors) && (
                              <details className="border rounded-lg p-3">
                                <summary className="cursor-pointer font-semibold text-sm">
                                  🔍 Technical Context
                                </summary>
                                <div className="mt-3 space-y-2 text-sm">
                                  {selectedFeedback.user_agent && (
                                    <div><strong>User Agent:</strong> <code className="text-xs bg-gray-100 px-1">{selectedFeedback.user_agent}</code></div>
                                  )}
                                  {selectedFeedback.viewport_size && (
                                    <div><strong>Viewport:</strong> {selectedFeedback.viewport_size}</div>
                                  )}
                                  {selectedFeedback.console_errors && Array.isArray(selectedFeedback.console_errors) && selectedFeedback.console_errors.length > 0 && (
                                    <div>
                                      <strong>Console Errors:</strong>
                                      <ul className="list-disc list-inside mt-1 space-y-1">
                                        {selectedFeedback.console_errors.slice(0, 5).map((err, idx) => (
                                          <li key={idx} className="text-xs text-red-600 font-mono bg-red-50 p-1">{err}</li>
                                        ))}
                                      </ul>
                                    </div>
                                  )}
                                  {selectedFeedback.network_errors && Array.isArray(selectedFeedback.network_errors) && selectedFeedback.network_errors.length > 0 && (
                                    <div>
                                      <strong>Network Errors:</strong>
                                      <ul className="list-disc list-inside mt-1 space-y-1">
                                        {selectedFeedback.network_errors.slice(0, 5).map((err, idx) => (
                                          <li key={idx} className="text-xs text-orange-600 font-mono bg-orange-50 p-1">{err.url || err}</li>
                                        ))}
                                      </ul>
                                    </div>
                                  )}
                                  {selectedFeedback.local_storage_data && (
                                    <div>
                                      <strong>Local Storage:</strong>
                                      <pre className="text-xs bg-gray-100 p-2 mt-1 rounded overflow-auto max-h-32">
                                        {selectedFeedback.local_storage_data}
                                      </pre>
                                    </div>
                                  )}
                                </div>
                              </details>
                            )}

                            {/* Reproduction Steps */}
                            {selectedFeedback.reproduction_steps && (
                              <details className="border rounded-lg p-3">
                                <summary className="cursor-pointer font-semibold text-sm">
                                  📝 Reproduction Steps
                                </summary>
                                <div className="mt-3 whitespace-pre-wrap text-sm bg-gray-50 p-2 rounded">
                                  {selectedFeedback.reproduction_steps}
                                </div>
                              </details>
                            )}

                            {/* Status History */}
                            {selectedFeedback.status_history && Array.isArray(selectedFeedback.status_history) && selectedFeedback.status_history.length > 0 && (
                              <details className="border rounded-lg p-3">
                                <summary className="cursor-pointer font-semibold text-sm">
                                  📅 Status History
                                </summary>
                                <div className="mt-3 space-y-2">
                                  {selectedFeedback.status_history.map((entry, idx) => (
                                    <div key={idx} className="text-xs border-l-2 border-blue-400 pl-3 py-1">
                                      <div className="text-gray-500">{new Date(entry.timestamp).toLocaleString()}</div>
                                      <div><strong>{entry.user}</strong></div>
                                      <div className="text-gray-700">
                                        {Object.entries(entry.changes).map(([field, change]) => (
                                          <div key={field}>{field}: {change}</div>
                                        ))}
                                      </div>
                                    </div>
                                  ))}
                                </div>
                              </details>
                            )}

                            {/* Admin Workflow Section */}
                            <div className="border rounded-lg p-4 bg-blue-50">
                              <h4 className="font-semibold mb-3 text-sm">🛠️ Admin Workflow</h4>
                              <div className="space-y-3">
                                <div className="grid grid-cols-2 gap-3">
                                  <div>
                                    <Label className="text-xs">Priority</Label>
                                    <Select
                                      value={adminData.priority}
                                      onValueChange={(val) => setAdminData({...adminData, priority: val})}
                                    >
                                      <SelectTrigger className="h-8">
                                        <SelectValue />
                                      </SelectTrigger>
                                      <SelectContent>
                                        <SelectItem value="low">Low</SelectItem>
                                        <SelectItem value="medium">Medium</SelectItem>
                                        <SelectItem value="high">High</SelectItem>
                                        <SelectItem value="critical">Critical</SelectItem>
                                      </SelectContent>
                                    </Select>
                                  </div>
                                  <div>
                                    <Label className="text-xs">Status</Label>
                                    <Select
                                      value={adminData.status}
                                      onValueChange={(val) => setAdminData({...adminData, status: val})}
                                    >
                                      <SelectTrigger className="h-8">
                                        <SelectValue />
                                      </SelectTrigger>
                                      <SelectContent>
                                        <SelectItem value="new">New</SelectItem>
                                        <SelectItem value="acknowledged">Acknowledged</SelectItem>
                                        <SelectItem value="investigating">Investigating</SelectItem>
                                        <SelectItem value="resolved">Resolved</SelectItem>
                                      </SelectContent>
                                    </Select>
                                  </div>
                                  <div>
                                    <Label className="text-xs">Assigned To</Label>
                                    <Input
                                      className="h-8"
                                      value={adminData.assigned_to}
                                      onChange={(e) => setAdminData({...adminData, assigned_to: e.target.value})}
                                      placeholder="Email or name"
                                    />
                                  </div>
                                  <div>
                                    <Label className="text-xs">Fix Version</Label>
                                    <Input
                                      className="h-8"
                                      value={adminData.fix_version}
                                      onChange={(e) => setAdminData({...adminData, fix_version: e.target.value})}
                                      placeholder="e.g., v1.2.3"
                                    />
                                  </div>
                                </div>
                                <div>
                                  <Label className="text-xs">Related Issues (comma-separated)</Label>
                                  <Input
                                    className="h-8"
                                    value={adminData.related_issues}
                                    onChange={(e) => setAdminData({...adminData, related_issues: e.target.value})}
                                    placeholder="e.g., BUG-ef781d48, BUG-a09f069c"
                                  />
                                  <p className="text-xs text-gray-500 mt-1">Use bug IDs shown at top of each report</p>
                                </div>
                                <div>
                                  <Label className="text-xs">Admin Notes</Label>
                                  <Textarea
                                    className="h-24"
                                    value={adminData.admin_notes}
                                    onChange={(e) => setAdminData({...adminData, admin_notes: e.target.value})}
                                    placeholder="Internal notes about investigation, workarounds, etc..."
                                  />
                                </div>
                                <Button
                                  size="sm"
                                  onClick={() => saveAdminData(selectedFeedback.id)}
                                  disabled={savingAdmin}
                                >
                                  {savingAdmin ? 'Saving...' : 'Save Admin Data'}
                                </Button>
                              </div>
                            </div>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                  
                  <div className="flex flex-col gap-2">
                    <Button
                      size="sm"
                      variant={selectedFeedback?.id === item.id ? "secondary" : "outline"}
                      onClick={() => {
                        if (selectedFeedback?.id === item.id) {
                          setSelectedFeedback(null);
                        } else {
                          loadFeedbackDetail(item.id);
                        }
                      }}
                    >
                      {selectedFeedback?.id === item.id ? 'Hide' : 'Details'}
                    </Button>
                    {item.status !== 'resolved' && (
                      <>
                        <Button size="sm" variant="outline" onClick={() => updateStatus(item.id, 'acknowledged')}>
                          Acknowledge
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => updateStatus(item.id, 'investigating')}>
                          Investigating
                        </Button>
                        <Button size="sm" variant="default" onClick={() => updateStatus(item.id, 'resolved')}>
                          Resolve
                        </Button>
                      </>
                    )}
                    {item.status === 'resolved' && (
                      <Button size="sm" variant="outline" onClick={() => updateStatus(item.id, 'new')}>
                        Reopen
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
