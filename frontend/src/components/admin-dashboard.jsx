"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Card, CardContent } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Coins, RefreshCw, Gift, AlertCircle } from "lucide-react";
import React, { useState, useEffect } from "react";
import { useAuth } from "@/AuthContext";
import { useToast } from "@/hooks/use-toast";
import { useResolvedTimezone } from "@/hooks/useResolvedTimezone";
import useAdminDashboardData from "@/components/admin-dashboard/hooks/useAdminDashboardData";
import useAdminDashboardState from "@/components/admin-dashboard/hooks/useAdminDashboardState";
import { navigationItems } from "@/constants/adminNavigation";
import AdminSidebar from "@/components/admin-dashboard/AdminSidebar.jsx";
import AdminHeader from "@/components/admin-dashboard/AdminHeader.jsx";
import AdminMainContent from "@/components/admin-dashboard/AdminMainContent.jsx";

export default function AdminDashboard() {
  const { token, logout, user: authUser } = useAuth();
  const { toast } = useToast();
  const resolvedTimezone = useResolvedTimezone();

  // Determine admin role (superadmin has full access, admin has restrictions)
  const userRole = authUser?.role?.toLowerCase() || (authUser?.is_admin ? 'admin' : 'user');
  const isSuperAdmin = userRole === 'superadmin';
  const isAdmin = userRole === 'admin' || isSuperAdmin;

  const {
    users,
    usersLoading,
    summary,
    metrics,
    episodesToday,
    recentActivity,
    systemHealth,
    growthMetrics,
    analyticsLoading,
    seedResult,
    runSeed,
    adminSettings,
    adminSettingsSaving,
    adminSettingsErr,
    saveAdminSettings,
    setAdminSettings,
    killingQueue,
    handleKillQueue,
    updateUser,
    grantAdminTier,
    savingIds,
    saveErrors,
    creditViewerDialog,
    viewUserCredits,
    closeCreditViewer,
    refundUserCredits,
    awardUserCredits,
    denyRefundRequest,
    prepareUserForDeletion,
    verifyUserEmail,
    triggerPasswordReset,
    handleBulkDeleteTestUsers,
  } = useAdminDashboardData({ token, toast });

  const {
    activeTab,
    setActiveTab,
    searchTerm,
    setSearchTerm,
    tierFilter,
    setTierFilter,
    statusFilter,
    setStatusFilter,
    verificationFilter,
    setVerificationFilter,
    currentPage,
    setCurrentPage,
    usersPerPage,
    editingDates,
    setEditingDates,
    adminTierDialog,
    setAdminTierDialog,
    openAdminTierDialog,
    closeAdminTierDialog,
    settings,
    setSettings,
    maintenanceDraft,
    setMaintenanceDraft,
    maintenanceMessageChanged,
    filteredUsers,
    currentUsers,
    indexOfFirstUser,
    indexOfLastUser,
    totalPages,
  } = useAdminDashboardState({ users, adminSettings });

  // Credit viewer state
  const [selectedCharges, setSelectedCharges] = useState(new Set());
  const [chargesPage, setChargesPage] = useState(1);
  const [chargesPerPage, setChargesPerPage] = useState(20);
  const [refundNotes, setRefundNotes] = useState("");
  const [refundSubmitting, setRefundSubmitting] = useState(false);
  const [useManualAmount, setUseManualAmount] = useState(false);
  const [manualRefundAmount, setManualRefundAmount] = useState("");
  const [awardDialogOpen, setAwardDialogOpen] = useState(false);
  const [awardCredits, setAwardCredits] = useState("");
  const [awardReason, setAwardReason] = useState("");
  const [awardNotes, setAwardNotes] = useState("");
  const [awardSubmitting, setAwardSubmitting] = useState(false);
  const [denyDialogOpen, setDenyDialogOpen] = useState(false);
  const [denyReason, setDenyReason] = useState("");
  const [denySubmitting, setDenySubmitting] = useState(false);

  // Reset state when dialog closes
  useEffect(() => {
    if (!creditViewerDialog.open) {
      setSelectedCharges(new Set());
      setChargesPage(1);
      setChargesPerPage(20);
      setRefundNotes("");
      setAwardDialogOpen(false);
      setAwardCredits("");
      setAwardReason("");
      setAwardNotes("");
    }
  }, [creditViewerDialog.open]);

  // Pre-select charges when opening from refund request
  useEffect(() => {
    if (creditViewerDialog.open && creditViewerDialog.refundRequest && creditViewerDialog.refundRequestDetail) {
      const refundRequest = creditViewerDialog.refundRequest;
      const detail = creditViewerDialog.refundRequestDetail;

      // Pre-select all refundable entries from episodes and non-episode charges
      const allRefundableIds = [];
      if (detail.episodes) {
        detail.episodes.forEach(ep => {
          ep.ledger_entries.forEach(entry => {
            if (entry.can_refund && !entry.already_refunded) {
              allRefundableIds.push(entry.id);
            }
          });
        });
      }
      if (detail.non_episode_charges) {
        detail.non_episode_charges.forEach(entry => {
          if (entry.can_refund && !entry.already_refunded) {
            allRefundableIds.push(entry.id);
          }
        });
      }

      if (allRefundableIds.length > 0) {
        setSelectedCharges(new Set(allRefundableIds));
      } else if (refundRequest.ledger_entry_ids && refundRequest.ledger_entry_ids.length > 0) {
        // Fallback: use the basic refund request data
        const requestedIds = new Set(refundRequest.ledger_entry_ids);
        const availableIds = new Set(
          creditViewerDialog.userData?.recent_charges
            ?.filter(c => c.direction === 'DEBIT')
            .map(c => c.id) || []
        );
        const toSelect = Array.from(requestedIds).filter(id => availableIds.has(id));
        if (toSelect.length > 0) {
          setSelectedCharges(new Set(toSelect));
        }
      }

      // Pre-fill refund notes with the request reason
      if (refundRequest.reason) {
        setRefundNotes(`Refund request: ${refundRequest.reason}${refundRequest.notes ? `\n\nUser notes: ${refundRequest.notes}` : ''}`);
      }
    }
  }, [creditViewerDialog.open, creditViewerDialog.refundRequest, creditViewerDialog.refundRequestDetail, creditViewerDialog.userData]);

  // Reload credits when pagination changes
  useEffect(() => {
    if (creditViewerDialog.open && creditViewerDialog.userId && !creditViewerDialog.loading) {
      viewUserCredits(creditViewerDialog.userId, chargesPage, chargesPerPage, creditViewerDialog.refundRequest);
    }
  }, [chargesPage, chargesPerPage]);

  const handleChargeSelect = (chargeId) => {
    const newSelected = new Set(selectedCharges);
    if (newSelected.has(chargeId)) {
      newSelected.delete(chargeId);
    } else {
      newSelected.add(chargeId);
    }
    setSelectedCharges(newSelected);
  };

  const handleSelectAll = () => {
    if (selectedCharges.size === creditViewerDialog.userData?.recent_charges?.filter(c => c.direction === 'DEBIT').length) {
      setSelectedCharges(new Set());
    } else {
      const debitCharges = creditViewerDialog.userData?.recent_charges?.filter(c => c.direction === 'DEBIT') || [];
      setSelectedCharges(new Set(debitCharges.map(c => c.id)));
    }
  };

  // Calculate total from selected charges (for refund request detail, check episodes and non-episode charges)
  const calculateTotalFromSelectedCharges = () => {
    if (creditViewerDialog.refundRequestDetail) {
      // Use refund request detail data
      const allEntries = [
        ...(creditViewerDialog.refundRequestDetail.episodes?.flatMap(ep => ep.ledger_entries) || []),
        ...(creditViewerDialog.refundRequestDetail.non_episode_charges || [])
      ];
      return allEntries
        .filter(e => selectedCharges.has(e.id) && e.can_refund)
        .reduce((sum, e) => sum + e.credits, 0);
    } else {
      // Use regular charges data
      return Array.from(selectedCharges).reduce((sum, chargeId) => {
        const charge = creditViewerDialog.userData?.recent_charges?.find(c => c.id === chargeId);
        return sum + (charge && charge.direction === 'DEBIT' ? charge.credits : 0);
      }, 0);
    }
  };

  const totalRefundCredits = calculateTotalFromSelectedCharges();
  const effectiveRefundAmount = useManualAmount && manualRefundAmount ? parseFloat(manualRefundAmount) : totalRefundCredits;

  const handleRefund = async () => {
    if (selectedCharges.size === 0) {
      toast({ title: "Error", description: "Please select at least one charge to refund", variant: "destructive" });
      return;
    }

    if (useManualAmount) {
      const manualAmount = parseFloat(manualRefundAmount);
      if (!manualAmount || manualAmount <= 0) {
        toast({ title: "Error", description: "Please enter a valid positive refund amount", variant: "destructive" });
        return;
      }
      if (manualAmount > totalRefundCredits) {
        toast({
          title: "Error",
          description: `Manual amount (${manualAmount.toFixed(1)}) cannot exceed selected charges total (${totalRefundCredits.toFixed(1)})`,
          variant: "destructive"
        });
        return;
      }
    }

    if (!creditViewerDialog.userId) return;

    setRefundSubmitting(true);
    try {
      await refundUserCredits(
        creditViewerDialog.userId,
        Array.from(selectedCharges),
        refundNotes,
        useManualAmount ? parseFloat(manualRefundAmount) : undefined
      );
      setSelectedCharges(new Set());
      setRefundNotes("");
      setUseManualAmount(false);
      setManualRefundAmount("");
      // Reload credits
      viewUserCredits(creditViewerDialog.userId, chargesPage, chargesPerPage);
    } catch (error) {
      // Error already handled in hook
    } finally {
      setRefundSubmitting(false);
    }
  };

  const handleAward = async () => {
    if (!creditViewerDialog.userId) return;
    const credits = parseFloat(awardCredits);
    if (!credits || credits <= 0) {
      toast({ title: "Error", description: "Please enter a valid positive number of credits", variant: "destructive" });
      return;
    }
    if (!awardReason.trim()) {
      toast({ title: "Error", description: "Please provide a reason for awarding credits", variant: "destructive" });
      return;
    }

    setAwardSubmitting(true);
    try {
      await awardUserCredits(creditViewerDialog.userId, credits, awardReason, awardNotes);
      setAwardDialogOpen(false);
      setAwardCredits("");
      setAwardReason("");
      setAwardNotes("");
      // Reload credits
      viewUserCredits(creditViewerDialog.userId, chargesPage, chargesPerPage);
    } catch (error) {
      // Error already handled in hook
    } finally {
      setAwardSubmitting(false);
    }
  };

  const analytics = {
    totalUsers: Number(summary?.users) || 0,
    totalEpisodes: Number(summary?.episodes) || 0,
    publishedEpisodes: Number(summary?.published_episodes) || 0,
    podcasts: Number(summary?.podcasts) || 0,
    templates: Number(summary?.templates) || 0,
    activeUsers: metrics?.daily_active_users_30d?.length
      ? metrics.daily_active_users_30d[metrics.daily_active_users_30d.length - 1]?.count || 0
      : 0,
    newSignups: metrics?.daily_signups_30d?.reduce((acc, entry) => acc + (Number(entry?.count) || 0), 0) || 0,
    revenue: metrics?.mrr_cents != null ? Math.round(metrics.mrr_cents / 100) : null,
    arr: metrics?.arr_cents != null ? Math.round(metrics.arr_cents / 100) : null,
    revenue30d: metrics?.revenue_30d_cents != null ? Math.round(metrics.revenue_30d_cents / 100) : null,
  };

  const handleMaintenanceToggle = (checked) => {
    saveAdminSettings({ maintenance_mode: !!checked });
  };

  const handleMaintenanceMessageSave = () => {
    if (!maintenanceMessageChanged) return;
    const trimmed = maintenanceDraft.trim();
    saveAdminSettings({ maintenance_message: trimmed ? trimmed : null });
  };

  const handleMaintenanceMessageReset = () => {
    setMaintenanceDraft(adminSettings?.maintenance_message ?? "");
  };

  const handleUserUpdate = (id, payload) => {
    if (payload.tier === "admin") {
      const targetUser = users.find((user) => user.id === id);
      if (!targetUser) {
        return;
      }
      openAdminTierDialog(id, targetUser.email || "this user");
      return;
    }

    updateUser(id, payload);
  };

  const confirmAdminTier = () => {
    if (adminTierDialog.confirmText.toLowerCase() !== "yes") {
      try {
        toast({ title: "Confirmation required", description: 'You must type "yes" to confirm', variant: "destructive" });
      } catch (_) {
        // ignore toast errors
      }
      return;
    }

    const { userId } = adminTierDialog;
    closeAdminTierDialog();
    grantAdminTier(userId);
  };

  return (
    <div className="min-h-screen bg-gray-50 flex">
      {/* Sidebar Navigation */}
      <AdminSidebar
        navigationItems={navigationItems}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        logout={logout}
      />

      {/* Main Content */}
      <div className="flex-1 flex flex-col" role="main" aria-label="Admin main content" tabIndex={-1}>
        {/* Top Header */}
        <AdminHeader
          activeTab={activeTab}
          navigationItems={navigationItems}
          resolvedTimezone={resolvedTimezone}
        />

        {/* Content Area */}
        <AdminMainContent
          activeTab={activeTab}
          navigationItems={navigationItems}
          adminSettings={adminSettings}
          adminSettingsSaving={adminSettingsSaving}
          saveAdminSettings={saveAdminSettings}
          analytics={analytics}
          runSeed={runSeed}
          seedResult={seedResult}
          metrics={metrics}
          episodesToday={episodesToday}
          recentActivity={recentActivity}
          systemHealth={systemHealth}
          growthMetrics={growthMetrics}
          analyticsLoading={analyticsLoading}
          handleKillQueue={handleKillQueue}
          killingQueue={killingQueue}
          token={token}
          settings={settings}
          setSettings={setSettings}
          adminSettingsErr={adminSettingsErr}
          maintenanceDraft={maintenanceDraft}
          setMaintenanceDraft={setMaintenanceDraft}
          maintenanceMessageChanged={maintenanceMessageChanged}
          handleMaintenanceToggle={handleMaintenanceToggle}
          handleMaintenanceMessageSave={handleMaintenanceMessageSave}
          handleMaintenanceMessageReset={handleMaintenanceMessageReset}
          isSuperAdmin={isSuperAdmin}
          isAdmin={isAdmin}
          usersLoading={usersLoading}
          currentUsers={currentUsers}
          filteredUsers={filteredUsers}
          searchTerm={searchTerm}
          setSearchTerm={setSearchTerm}
          tierFilter={tierFilter}
          setTierFilter={setTierFilter}
          statusFilter={statusFilter}
          setStatusFilter={setStatusFilter}
          verificationFilter={verificationFilter}
          setVerificationFilter={setVerificationFilter}
          usersPerPage={usersPerPage}
          indexOfFirstUser={indexOfFirstUser}
          indexOfLastUser={indexOfLastUser}
          currentPage={currentPage}
          setCurrentPage={setCurrentPage}
          totalPages={totalPages}
          savingIds={savingIds}
          saveErrors={saveErrors}
          editingDates={editingDates}
          setEditingDates={setEditingDates}
          handleUserUpdate={handleUserUpdate}
          prepareUserForDeletion={prepareUserForDeletion}
          viewUserCredits={viewUserCredits}
          verifyUserEmail={verifyUserEmail}
          triggerPasswordReset={triggerPasswordReset}
          setAdminSettings={setAdminSettings}
          onBulkDeleteTestUsers={handleBulkDeleteTestUsers}
        />
      </div>

      {/* Admin Tier Confirmation Dialog */}
      <Dialog open={adminTierDialog.open} onOpenChange={(open) => !open && closeAdminTierDialog()}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Grant Admin Access</DialogTitle>
            <DialogDescription>
              You are about to grant admin privileges to <strong>{adminTierDialog.userName}</strong>.
              <br /><br />
              Admin users will have access to:
              <ul className="list-disc list-inside mt-2 text-sm space-y-1">
                <li>User management (view, edit, deactivate)</li>
                <li>Analytics dashboard</li>
                <li>DB Explorer (read-only)</li>
                <li>Settings (limited to maintenance mode)</li>
              </ul>
              <br />
              <strong>Admin users CANNOT:</strong>
              <ul className="list-disc list-inside mt-2 text-sm space-y-1">
                <li>Delete users</li>
                <li>Edit settings (except maintenance mode)</li>
                <li>Modify database records</li>
              </ul>
              <br />
              Type <strong>yes</strong> to confirm.
            </DialogDescription>
          </DialogHeader>
          <div className="my-4">
            <Input
              placeholder="Type 'yes' to confirm"
              value={adminTierDialog.confirmText}
              onChange={(e) => setAdminTierDialog(prev => ({ ...prev, confirmText: e.target.value }))}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && adminTierDialog.confirmText.toLowerCase() === 'yes') {
                  confirmAdminTier();
                }
              }}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={closeAdminTierDialog}>
              Cancel
            </Button>
            <Button
              onClick={confirmAdminTier}
              disabled={adminTierDialog.confirmText.toLowerCase() !== 'yes'}
              className="bg-orange-600 hover:bg-orange-700"
            >
              Grant Admin Access
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Credit Viewer Dialog */}
      <Dialog open={creditViewerDialog.open} onOpenChange={(open) => !open && closeCreditViewer()}>
        <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Coins className="h-5 w-5 text-blue-600" />
              Credit Usage Details
            </DialogTitle>
            <DialogDescription>
              {creditViewerDialog.userData?.email && (
                <span className="font-medium">{creditViewerDialog.userData.email}</span>
              )}
            </DialogDescription>
          </DialogHeader>

          {creditViewerDialog.loading ? (
            <div className="py-8 text-center text-gray-500">Loading credit data...</div>
          ) : creditViewerDialog.userData ? (
            <div className="space-y-6">
              {/* Comprehensive Refund Request Detail Panel */}
              {creditViewerDialog.refundRequest && (
                <Card className="border-l-4 border-l-orange-500 bg-orange-50 mb-4">
                  <CardContent className="p-4 space-y-4">
                    {/* Header */}
                    <div className="flex items-start gap-3">
                      <AlertCircle className="h-5 w-5 text-orange-600 mt-0.5" />
                      <div className="flex-1">
                        <div className="font-semibold text-orange-900 mb-2">Refund Request Details</div>

                        {/* User's Request */}
                        <div className="bg-white rounded p-3 mb-3 border border-orange-200">
                          <div className="text-sm font-medium text-gray-700 mb-1">User's Reason</div>
                          <div className="text-sm text-gray-800">{creditViewerDialog.refundRequest.reason}</div>
                          {creditViewerDialog.refundRequest.notes && (
                            <div className="mt-2 pt-2 border-t border-gray-200">
                              <div className="text-xs font-medium text-gray-600 mb-1">User Notes</div>
                              <div className="text-xs text-gray-700 whitespace-pre-wrap">{creditViewerDialog.refundRequest.notes}</div>
                            </div>
                          )}
                          <div className="mt-2 pt-2 border-t border-gray-200 text-xs text-gray-500">
                            Requested: {new Date(creditViewerDialog.refundRequest.created_at).toLocaleString()}
                          </div>
                        </div>

                        {/* Detailed Information (if available) */}
                        {creditViewerDialog.refundRequestDetail && (
                          <div className="space-y-3">
                            {/* User Context */}
                            <div className="bg-white rounded p-3 border border-gray-200">
                              <div className="text-xs font-semibold text-gray-700 mb-2">User Account Context</div>
                              <div className="grid grid-cols-2 gap-2 text-xs">
                                <div>
                                  <span className="text-gray-500">Account Age:</span>{' '}
                                  <span className="font-medium">
                                    {Math.floor((new Date() - new Date(creditViewerDialog.refundRequestDetail.user.account_created_at)) / (1000 * 60 * 60 * 24))} days
                                  </span>
                                </div>
                                <div>
                                  <span className="text-gray-500">Tier:</span>{' '}
                                  <span className="font-medium">{creditViewerDialog.refundRequestDetail.user.tier === 'free' ? 'Starter' : (creditViewerDialog.refundRequestDetail.user.tier || 'Starter')}</span>
                                </div>
                                <div>
                                  <span className="text-gray-500">All-Time Usage:</span>{' '}
                                  <span className="font-medium">{creditViewerDialog.refundRequestDetail.user.total_credits_used_all_time.toFixed(1)} credits</span>
                                </div>
                                <div>
                                  <span className="text-gray-500">This Month:</span>{' '}
                                  <span className="font-medium">{creditViewerDialog.refundRequestDetail.user.total_credits_used_this_month.toFixed(1)} credits</span>
                                </div>
                                <div>
                                  <span className="text-gray-500">Previous Refunds:</span>{' '}
                                  <span className="font-medium">{creditViewerDialog.refundRequestDetail.user.previous_refund_count}</span>
                                  {creditViewerDialog.refundRequestDetail.user.previous_refund_count > 0 && (
                                    <span className="text-gray-500 ml-1">
                                      ({creditViewerDialog.refundRequestDetail.user.previous_refund_total_credits.toFixed(1)} total credits)
                                    </span>
                                  )}
                                </div>
                                <div>
                                  <span className="text-gray-500">Account Status:</span>{' '}
                                  <span className={`font-medium ${creditViewerDialog.refundRequestDetail.user.is_active ? 'text-green-600' : 'text-red-600'}`}>
                                    {creditViewerDialog.refundRequestDetail.user.is_active ? 'Active' : 'Inactive'}
                                  </span>
                                </div>
                              </div>
                            </div>

                            {/* Episodes with Refund Requests - Focused View */}
                            {creditViewerDialog.refundRequestDetail.episodes && creditViewerDialog.refundRequestDetail.episodes.length > 0 && (
                              <div className="space-y-4">
                                <div className="text-sm font-semibold text-gray-700">
                                  Episodes Requested for Refund ({creditViewerDialog.refundRequestDetail.episodes.length})
                                </div>
                                {creditViewerDialog.refundRequestDetail.episodes.map((episode) => {
                                  const episodeSelectedEntries = episode.ledger_entries.filter(e => selectedCharges.has(e.id) && e.can_refund);
                                  const episodeTotalSelected = episodeSelectedEntries.reduce((sum, e) => sum + e.credits, 0);
                                  const allEpisodeEntriesSelected = episode.ledger_entries.filter(e => e.can_refund).every(e => selectedCharges.has(e.id));

                                  return (
                                    <Card key={episode.id} className="border-l-4 border-l-blue-500">
                                      <CardContent className="p-4 space-y-3">
                                        {/* Episode Header */}
                                        <div className="flex items-start justify-between">
                                          <div className="flex-1">
                                            <div className="text-base font-semibold text-gray-900 mb-1">{episode.title}</div>
                                            {episode.podcast_title && (
                                              <div className="text-sm text-gray-600 mb-2">Podcast: {episode.podcast_title}</div>
                                            )}
                                            <div className="flex items-center gap-3 flex-wrap">
                                              {(episode.season_number !== null || episode.episode_number !== null) && (
                                                <div className="text-xs text-gray-500">
                                                  S{episode.season_number || '?'}E{episode.episode_number || '?'}
                                                </div>
                                              )}
                                              <Badge
                                                variant={episode.status === 'published' ? 'default' : episode.status === 'error' ? 'destructive' : 'secondary'}
                                                className="text-xs"
                                              >
                                                {episode.status}
                                              </Badge>
                                              <Badge
                                                variant={episode.service_delivered ? 'default' : 'destructive'}
                                                className="text-xs"
                                              >
                                                {episode.service_delivered ? 'Service Delivered' : 'Service Failed'}
                                              </Badge>
                                              {episode.refund_recommendation && (
                                                <Badge
                                                  variant={
                                                    episode.refund_recommendation === 'full_refund' ? 'default' :
                                                      episode.refund_recommendation === 'no_refund' ? 'secondary' :
                                                        'outline'
                                                  }
                                                  className="text-xs"
                                                >
                                                  {episode.refund_recommendation === 'full_refund' ? '✓ Recommend Full Refund' :
                                                    episode.refund_recommendation === 'no_refund' ? '✗ Do Not Refund' :
                                                      episode.refund_recommendation === 'conditional_refund' ? '? Conditional Refund' :
                                                        '~ Partial Refund'}
                                                </Badge>
                                              )}
                                            </div>
                                          </div>
                                          <div className="text-right">
                                            <div className="text-lg font-bold text-blue-600">
                                              {episode.net_credits_to_refund.toFixed(1)} credits
                                            </div>
                                            <div className="text-xs text-gray-500">
                                              {episode.ledger_entries.filter(e => e.can_refund).length} charges
                                            </div>
                                          </div>
                                        </div>

                                        {/* Episode Details Grid */}
                                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs bg-gray-50 rounded p-3">
                                          <div>
                                            <div className="text-gray-500 mb-0.5">Created</div>
                                            <div className="font-medium">{new Date(episode.created_at).toLocaleDateString()}</div>
                                          </div>
                                          {episode.processed_at && (
                                            <div>
                                              <div className="text-gray-500 mb-0.5">Processed</div>
                                              <div className="font-medium">{new Date(episode.processed_at).toLocaleDateString()}</div>
                                            </div>
                                          )}
                                          {episode.duration_ms && (
                                            <div>
                                              <div className="text-gray-500 mb-0.5">Duration</div>
                                              <div className="font-medium">{Math.floor(episode.duration_ms / 60000)} min</div>
                                            </div>
                                          )}
                                          <div>
                                            <div className="text-gray-500 mb-0.5">Audio File</div>
                                            <div className={`font-medium ${episode.has_final_audio ? 'text-green-600' : 'text-red-600'}`}>
                                              {episode.has_final_audio ? '✓ Yes' : '✗ No'}
                                            </div>
                                          </div>
                                          {episode.audio_file_size && (
                                            <div>
                                              <div className="text-gray-500 mb-0.5">File Size</div>
                                              <div className="font-medium">{(episode.audio_file_size / 1024 / 1024).toFixed(1)} MB</div>
                                            </div>
                                          )}
                                          {episode.is_published && (
                                            <div>
                                              <div className="text-gray-500 mb-0.5">Published</div>
                                              <div className="font-medium text-orange-600">✓ Yes {episode.is_published_to_spreaker && '(Spreaker)'}</div>
                                            </div>
                                          )}
                                          {episode.spreaker_episode_id && (
                                            <div>
                                              <div className="text-gray-500 mb-0.5">Spreaker ID</div>
                                              <div className="font-medium text-xs">{episode.spreaker_episode_id}</div>
                                            </div>
                                          )}
                                          {episode.auphonic_processed && (
                                            <div>
                                              <div className="text-gray-500 mb-0.5">Auphonic</div>
                                              <div className="font-medium text-green-600">✓ Processed</div>
                                            </div>
                                          )}
                                        </div>

                                        {/* Errors */}
                                        {(episode.error_message || episode.spreaker_publish_error || episode.auphonic_error) && (
                                          <div className="bg-red-50 rounded p-2 border border-red-200">
                                            <div className="text-xs font-medium text-red-700 mb-1">Errors</div>
                                            {episode.error_message && (
                                              <div className="text-xs text-red-600">• {episode.error_message}</div>
                                            )}
                                            {episode.spreaker_publish_error && (
                                              <div className="text-xs text-red-600">• Publish Error: {episode.spreaker_publish_error}</div>
                                            )}
                                            {episode.auphonic_error && (
                                              <div className="text-xs text-red-600">• Auphonic Error: {episode.auphonic_error}</div>
                                            )}
                                            {episode.spreaker_publish_error_detail && (
                                              <div className="text-xs text-red-500 mt-1 italic">{episode.spreaker_publish_error_detail}</div>
                                            )}
                                          </div>
                                        )}

                                        {/* Episode Summary/Notes */}
                                        {episode.brief_summary && (
                                          <div className="bg-blue-50 rounded p-2 border border-blue-200">
                                            <div className="text-xs font-medium text-blue-700 mb-1">Summary</div>
                                            <div className="text-xs text-blue-800">{episode.brief_summary}</div>
                                          </div>
                                        )}
                                        {episode.show_notes && (
                                          <div className="bg-gray-50 rounded p-2 border border-gray-200">
                                            <div className="text-xs font-medium text-gray-700 mb-1">Show Notes</div>
                                            <div className="text-xs text-gray-600 line-clamp-3">{episode.show_notes}</div>
                                          </div>
                                        )}

                                        {/* Charges for this Episode */}
                                        <div className="border-t pt-3">
                                          <div className="text-xs font-semibold text-gray-700 mb-2">
                                            Charges for this Episode ({episode.ledger_entries.filter(e => e.can_refund).length} refundable)
                                          </div>
                                          <div className="space-y-2">
                                            {episode.ledger_entries.map((entry) => {
                                              const isSelected = selectedCharges.has(entry.id);
                                              const canSelect = entry.can_refund && !entry.already_refunded;

                                              return (
                                                <div
                                                  key={entry.id}
                                                  className={`flex items-start gap-2 p-2 rounded border ${entry.already_refunded
                                                    ? 'bg-green-50 border-green-200'
                                                    : canSelect && isSelected
                                                      ? 'bg-blue-50 border-blue-300'
                                                      : 'bg-white border-gray-200'
                                                    }`}
                                                >
                                                  {canSelect ? (
                                                    <Checkbox
                                                      checked={isSelected}
                                                      onCheckedChange={(checked) => {
                                                        const newSelected = new Set(selectedCharges);
                                                        if (checked) {
                                                          newSelected.add(entry.id);
                                                        } else {
                                                          newSelected.delete(entry.id);
                                                        }
                                                        setSelectedCharges(newSelected);
                                                      }}
                                                      className="mt-0.5"
                                                    />
                                                  ) : (
                                                    <div className="w-4 h-4 mt-0.5" />
                                                  )}
                                                  <div className="flex-1 min-w-0">
                                                    <div className="flex justify-between items-start">
                                                      <div className="text-xs font-medium text-gray-700">
                                                        {entry.reason} - {entry.credits.toFixed(1)} credits
                                                      </div>
                                                      <div className="text-xs text-gray-500">
                                                        {new Date(entry.timestamp).toLocaleDateString()}
                                                      </div>
                                                    </div>
                                                    {entry.already_refunded && (
                                                      <div className="text-xs text-green-700 mt-1">✓ Already refunded</div>
                                                    )}
                                                    {entry.cost_breakdown && (
                                                      <div className="text-xs text-gray-600 mt-1">
                                                        Base: {entry.cost_breakdown.base_credits?.toFixed(1) || 'N/A'} |
                                                        Total: {entry.cost_breakdown.total?.toFixed(1) || entry.credits.toFixed(1)}
                                                      </div>
                                                    )}
                                                  </div>
                                                </div>
                                              );
                                            })}
                                          </div>
                                          <div className="mt-2 pt-2 border-t text-xs flex justify-between">
                                            <span className="text-gray-600">
                                              Selected: {episodeSelectedEntries.length} of {episode.ledger_entries.filter(e => e.can_refund).length}
                                            </span>
                                            <span className="font-medium text-blue-600">
                                              {episodeTotalSelected.toFixed(1)} credits
                                            </span>
                                          </div>
                                        </div>
                                      </CardContent>
                                    </Card>
                                  );
                                })}
                              </div>
                            )}

                            {/* Non-Episode Charges (TTS Library, Storage, etc.) */}
                            {creditViewerDialog.refundRequestDetail.non_episode_charges && creditViewerDialog.refundRequestDetail.non_episode_charges.length > 0 && (
                              <div className="bg-white rounded p-3 border border-gray-200">
                                <div className="text-xs font-semibold text-gray-700 mb-2">
                                  Other Charges ({creditViewerDialog.refundRequestDetail.non_episode_charges.filter(e => e.can_refund).length} refundable)
                                </div>
                                <div className="space-y-2">
                                  {creditViewerDialog.refundRequestDetail.non_episode_charges.map((entry) => {
                                    const isSelected = selectedCharges.has(entry.id);
                                    const canSelect = entry.can_refund && !entry.already_refunded;

                                    return (
                                      <div
                                        key={entry.id}
                                        className={`flex items-start gap-2 p-2 rounded border ${entry.already_refunded
                                          ? 'bg-green-50 border-green-200'
                                          : canSelect && isSelected
                                            ? 'bg-blue-50 border-blue-300'
                                            : 'bg-white border-gray-200'
                                          }`}
                                      >
                                        {canSelect ? (
                                          <Checkbox
                                            checked={isSelected}
                                            onCheckedChange={(checked) => {
                                              const newSelected = new Set(selectedCharges);
                                              if (checked) {
                                                newSelected.add(entry.id);
                                              } else {
                                                newSelected.delete(entry.id);
                                              }
                                              setSelectedCharges(newSelected);
                                            }}
                                            className="mt-0.5"
                                          />
                                        ) : (
                                          <div className="w-4 h-4 mt-0.5" />
                                        )}
                                        <div className="flex-1">
                                          <div className="text-xs font-medium text-gray-700">
                                            {entry.reason} - {entry.credits.toFixed(1)} credits
                                          </div>
                                          <div className="text-xs text-gray-500">
                                            {new Date(entry.timestamp).toLocaleDateString()}
                                          </div>
                                          {entry.service_details && (
                                            <div className="text-xs text-gray-600 mt-1">
                                              {entry.service_details.service_type || entry.service_details.note}
                                            </div>
                                          )}
                                        </div>
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            )}

                            {/* Refund Summary */}
                            <div className="bg-white rounded p-3 border border-blue-200">
                              <div className="text-xs font-semibold text-gray-700 mb-2">Refund Summary</div>
                              <div className="grid grid-cols-3 gap-2 text-xs">
                                <div>
                                  <span className="text-gray-500">Total Requested:</span>{' '}
                                  <span className="font-semibold text-blue-600">{creditViewerDialog.refundRequestDetail.total_credits_requested.toFixed(1)} credits</span>
                                </div>
                                <div>
                                  <span className="text-gray-500">Already Refunded:</span>{' '}
                                  <span className="font-medium">{creditViewerDialog.refundRequestDetail.total_credits_already_refunded.toFixed(1)} credits</span>
                                </div>
                                <div>
                                  <span className="text-gray-500">Net to Refund:</span>{' '}
                                  <span className="font-semibold text-green-600">{creditViewerDialog.refundRequestDetail.net_credits_to_refund.toFixed(1)} credits</span>
                                </div>
                                <div>
                                  <span className="text-gray-500">Days Since Charges:</span>{' '}
                                  <span className="font-medium">{creditViewerDialog.refundRequestDetail.days_since_charges.toFixed(1)} days</span>
                                </div>
                                <div>
                                  <span className="text-gray-500">Hours Since Request:</span>{' '}
                                  <span className="font-medium">{creditViewerDialog.refundRequestDetail.hours_since_request.toFixed(1)} hours</span>
                                </div>
                                <div>
                                  <span className="text-gray-500">Episodes:</span>{' '}
                                  <span className="font-medium">{creditViewerDialog.refundRequestDetail.episodes?.length || 0}</span>
                                </div>
                              </div>
                            </div>

                            {/* Eligibility Warnings */}
                            {creditViewerDialog.refundRequestDetail.refund_eligibility_notes && creditViewerDialog.refundRequestDetail.refund_eligibility_notes.length > 0 && (
                              <div className="bg-yellow-50 rounded p-3 border border-yellow-300">
                                <div className="text-xs font-semibold text-yellow-800 mb-2 flex items-center gap-1">
                                  <AlertCircle className="h-3 w-3" />
                                  Eligibility Notes
                                </div>
                                <ul className="space-y-1">
                                  {creditViewerDialog.refundRequestDetail.refund_eligibility_notes.map((note, idx) => (
                                    <li key={idx} className="text-xs text-yellow-700 flex items-start gap-1">
                                      <span>•</span>
                                      <span>{note}</span>
                                    </li>
                                  ))}
                                </ul>
                              </div>
                            )}

                          </div>
                        )}

                        {/* Fallback: Basic info if detail not loaded */}
                        {!creditViewerDialog.refundRequestDetail && (
                          <div className="bg-white rounded p-3 border border-orange-200">
                            <div className="text-xs text-gray-600">
                              {creditViewerDialog.refundRequest.ledger_entry_ids && creditViewerDialog.refundRequest.ledger_entry_ids.length > 0 && (
                                <div className="mb-1">
                                  Requested entries: {creditViewerDialog.refundRequest.ledger_entry_ids.join(', ')}
                                </div>
                              )}
                              {creditViewerDialog.refundRequest.episode_id && (
                                <div>
                                  Episode ID: {creditViewerDialog.refundRequest.episode_id}
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Only show regular credit viewer if NOT viewing a refund request with detail */}
              {!creditViewerDialog.refundRequestDetail && (
                <>
                  {/* Summary Stats */}
                  <div className="grid grid-cols-3 gap-4">
                    <Card>
                      <CardContent className="p-4">
                        <div className="text-xs text-gray-500 mb-1">Credit Balance</div>
                        <div className="text-2xl font-bold text-blue-600">
                          {creditViewerDialog.userData.credits_balance.toFixed(1)}
                        </div>
                        <div className="text-xs text-gray-500 mt-1">
                          ≈ {creditViewerDialog.userData.credits_balance.toFixed(0)} minutes
                        </div>
                      </CardContent>
                    </Card>

                    <Card>
                      <CardContent className="p-4">
                        <div className="text-xs text-gray-500 mb-1">Allocated</div>
                        <div className="text-2xl font-bold text-gray-700">
                          {creditViewerDialog.userData.credits_allocated !== null
                            ? creditViewerDialog.userData.credits_allocated.toFixed(0)
                            : '∞'}
                        </div>
                        <div className="text-xs text-gray-500 mt-1">
                          Tier: {creditViewerDialog.userData.tier}
                        </div>
                      </CardContent>
                    </Card>

                    <Card>
                      <CardContent className="p-4">
                        <div className="text-xs text-gray-500 mb-1">Used This Month</div>
                        <div className="text-2xl font-bold text-red-600">
                          {creditViewerDialog.userData.credits_used_this_month.toFixed(1)}
                        </div>
                        <div className="text-xs text-gray-500 mt-1">
                          {creditViewerDialog.userData.credits_allocated !== null
                            ? `${((creditViewerDialog.userData.credits_used_this_month / creditViewerDialog.userData.credits_allocated) * 100).toFixed(0)}% of limit`
                            : 'Unlimited tier'}
                        </div>
                      </CardContent>
                    </Card>
                  </div>

                  {/* Usage Breakdown */}
                  {creditViewerDialog.userData.credits_breakdown && (
                    <div>
                      <div className="text-sm font-semibold text-gray-700 mb-3">Monthly Breakdown</div>
                      <div className="bg-gray-50 rounded-lg p-4 space-y-2">
                        {creditViewerDialog.userData.credits_breakdown.transcription > 0 && (
                          <div className="flex justify-between text-sm">
                            <span className="text-gray-600">Transcription</span>
                            <span className="font-medium">{creditViewerDialog.userData.credits_breakdown.transcription.toFixed(1)} credits</span>
                          </div>
                        )}
                        {creditViewerDialog.userData.credits_breakdown.assembly > 0 && (
                          <div className="flex justify-between text-sm">
                            <span className="text-gray-600">Episode Assembly</span>
                            <span className="font-medium">{creditViewerDialog.userData.credits_breakdown.assembly.toFixed(1)} credits</span>
                          </div>
                        )}
                        {creditViewerDialog.userData.credits_breakdown.tts_generation > 0 && (
                          <div className="flex justify-between text-sm">
                            <span className="text-gray-600">TTS Generation</span>
                            <span className="font-medium">{creditViewerDialog.userData.credits_breakdown.tts_generation.toFixed(1)} credits</span>
                          </div>
                        )}
                        {creditViewerDialog.userData.credits_breakdown.auphonic_processing > 0 && (
                          <div className="flex justify-between text-sm">
                            <span className="text-gray-600">Auphonic Processing</span>
                            <span className="font-medium">{creditViewerDialog.userData.credits_breakdown.auphonic_processing.toFixed(1)} credits</span>
                          </div>
                        )}
                        {creditViewerDialog.userData.credits_breakdown.storage > 0 && (
                          <div className="flex justify-between text-sm">
                            <span className="text-gray-600">Storage</span>
                            <span className="font-medium">{creditViewerDialog.userData.credits_breakdown.storage.toFixed(1)} credits</span>
                          </div>
                        )}
                        {creditViewerDialog.userData.credits_breakdown.ai_metadata > 0 && (
                          <div className="flex justify-between text-sm">
                            <span className="text-gray-600">AI Metadata</span>
                            <span className="font-medium">{creditViewerDialog.userData.credits_breakdown.ai_metadata.toFixed(1)} credits</span>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </>
              )}

              {/* Refund Credits Section */}
              <div className="border rounded-lg p-4 bg-blue-50">
                <div className="flex items-center gap-2 mb-3">
                  <RefreshCw className="h-4 w-4 text-blue-600" />
                  <div className="text-sm font-semibold text-gray-700">Refund Credits</div>
                </div>
                <div className="text-xs text-gray-600 mb-3">
                  {creditViewerDialog.refundRequestDetail ? (
                    <>
                      Select which charges to refund from the episodes above.
                      {(() => {
                        const allEntries = [
                          ...(creditViewerDialog.refundRequestDetail.episodes?.flatMap(ep => ep.ledger_entries) || []),
                          ...(creditViewerDialog.refundRequestDetail.non_episode_charges || [])
                        ];
                        const refundable = allEntries.filter(e => e.can_refund);
                        if (selectedCharges.size < refundable.length) {
                          return <span className="text-orange-600 font-medium"> Partial refund selected.</span>;
                        }
                        return null;
                      })()}
                    </>
                  ) : (
                    "Select charges to refund. Credits will be restored to their original bank (monthly or add-on)."
                  )}
                </div>
                {selectedCharges.size > 0 && (
                  <div className="mb-3 p-2 bg-white rounded border">
                    <div className="text-xs font-medium text-gray-700 mb-1">
                      {useManualAmount ? (
                        <>
                          Manual refund amount: <span className="text-blue-600 font-semibold">{effectiveRefundAmount.toFixed(1)} credits</span>
                          <span className="text-gray-500 ml-2">(Selected total: {totalRefundCredits.toFixed(1)} credits)</span>
                        </>
                      ) : (
                        <>
                          Total to refund: <span className="text-blue-600 font-semibold">{totalRefundCredits.toFixed(1)} credits</span>
                        </>
                      )}
                    </div>
                    {creditViewerDialog.refundRequestDetail && (
                      <div className="text-xs text-gray-600">
                        {(() => {
                          const allEntries = [
                            ...(creditViewerDialog.refundRequestDetail.episodes?.flatMap(ep => ep.ledger_entries) || []),
                            ...(creditViewerDialog.refundRequestDetail.non_episode_charges || [])
                          ];
                          const refundable = allEntries.filter(e => e.can_refund);
                          const selected = refundable.filter(e => selectedCharges.has(e.id));
                          return (
                            <>
                              {selected.length} of {refundable.length} refundable entries selected
                              {selected.length < refundable.length && !useManualAmount && (
                                <span className="text-orange-600 ml-1">(Partial refund)</span>
                              )}
                              {useManualAmount && (
                                <span className="text-orange-600 ml-1">(Manual adjustment)</span>
                              )}
                            </>
                          );
                        })()}
                      </div>
                    )}
                  </div>
                )}
                <div className="space-y-2">
                  {/* Manual Amount Toggle */}
                  {selectedCharges.size > 0 && (
                    <div className="flex items-center gap-2 p-2 bg-gray-50 rounded border">
                      <Checkbox
                        checked={useManualAmount}
                        onCheckedChange={(checked) => {
                          setUseManualAmount(checked);
                          if (checked) {
                            setManualRefundAmount(totalRefundCredits.toFixed(1));
                          } else {
                            setManualRefundAmount("");
                          }
                        }}
                        id="manual-amount-toggle"
                      />
                      <label htmlFor="manual-amount-toggle" className="text-xs font-medium text-gray-700 cursor-pointer">
                        Use manual refund amount
                      </label>
                    </div>
                  )}

                  {/* Manual Amount Input */}
                  {useManualAmount && selectedCharges.size > 0 && (
                    <div className="space-y-1">
                      <label className="text-xs font-medium text-gray-700">Manual Refund Amount (credits)</label>
                      <Input
                        type="number"
                        step="0.1"
                        min="0.1"
                        max={totalRefundCredits}
                        value={manualRefundAmount}
                        onChange={(e) => setManualRefundAmount(e.target.value)}
                        placeholder={totalRefundCredits.toFixed(1)}
                        className="text-xs"
                      />
                      <div className="text-xs text-gray-500">
                        Selected charges total: {totalRefundCredits.toFixed(1)} credits (max: {totalRefundCredits.toFixed(1)})
                      </div>
                    </div>
                  )}

                  <Textarea
                    placeholder="Optional notes for refund..."
                    value={refundNotes}
                    onChange={(e) => setRefundNotes(e.target.value)}
                    className="text-xs"
                    rows={2}
                  />
                  <div className="flex gap-2">
                    <Button
                      onClick={handleRefund}
                      disabled={selectedCharges.size === 0 || refundSubmitting || (useManualAmount && (!manualRefundAmount || parseFloat(manualRefundAmount) <= 0))}
                      className="flex-1 bg-blue-600 hover:bg-blue-700"
                      size="sm"
                    >
                      {refundSubmitting ? "Processing..." : `Confirm Refund ${useManualAmount ? `(${effectiveRefundAmount.toFixed(1)} credits)` : `(${selectedCharges.size} selected)`}`}
                    </Button>
                    {creditViewerDialog.refundRequest && creditViewerDialog.refundRequest.notification_id && (
                      <Button
                        onClick={() => setDenyDialogOpen(true)}
                        disabled={refundSubmitting}
                        variant="destructive"
                        size="sm"
                      >
                        Deny Request
                      </Button>
                    )}
                  </div>
                </div>
              </div>

              {/* Award Credits Section - Only show if NOT viewing refund request detail */}
              {!creditViewerDialog.refundRequestDetail && (
                <div className="border rounded-lg p-4 bg-green-50">
                  <div className="flex items-center gap-2 mb-3">
                    <Gift className="h-4 w-4 text-green-600" />
                    <div className="text-sm font-semibold text-gray-700">Award Credits</div>
                  </div>
                  <div className="text-xs text-gray-600 mb-3">
                    Award credits to this user. Credits will be added as add-on credits.
                  </div>
                  <Button
                    onClick={() => setAwardDialogOpen(true)}
                    className="w-full bg-green-600 hover:bg-green-700"
                    size="sm"
                  >
                    Award Credits
                  </Button>
                </div>
              )}

              {/* Recent Charges - Only show if NOT viewing refund request detail */}
              {!creditViewerDialog.refundRequestDetail && creditViewerDialog.userData.recent_charges && creditViewerDialog.userData.recent_charges.length > 0 && (
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <div className="text-sm font-semibold text-gray-700">Recent Charges</div>
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
                  <div className="border rounded-lg overflow-hidden">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="text-xs w-12">
                            <Checkbox
                              checked={selectedCharges.size > 0 && selectedCharges.size === creditViewerDialog.userData.recent_charges.filter(c => c.direction === 'DEBIT').length}
                              onCheckedChange={handleSelectAll}
                            />
                          </TableHead>
                          <TableHead className="text-xs">Date</TableHead>
                          <TableHead className="text-xs">Type</TableHead>
                          <TableHead className="text-xs">Episode</TableHead>
                          <TableHead className="text-xs text-right">Credits</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {creditViewerDialog.userData.recent_charges.map((charge) => (
                          <TableRow key={charge.id}>
                            <TableCell className="text-xs">
                              {charge.direction === 'DEBIT' && (
                                <Checkbox
                                  checked={selectedCharges.has(charge.id)}
                                  onCheckedChange={() => handleChargeSelect(charge.id)}
                                />
                              )}
                            </TableCell>
                            <TableCell className="text-xs text-gray-600">
                              {new Date(charge.timestamp).toLocaleDateString()}
                            </TableCell>
                            <TableCell className="text-xs">
                              <Badge variant={charge.direction === 'DEBIT' ? 'destructive' : 'default'} className="text-xs">
                                {charge.reason}
                              </Badge>
                            </TableCell>
                            <TableCell className="text-xs text-gray-600 truncate max-w-[200px]">
                              {charge.episode_title || charge.notes || '—'}
                            </TableCell>
                            <TableCell className={`text-xs text-right font-medium ${charge.direction === 'DEBIT' ? 'text-red-600' : 'text-green-600'}`}>
                              {charge.direction === 'DEBIT' ? '-' : '+'}{charge.credits.toFixed(1)}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                  {/* Pagination */}
                  {creditViewerDialog.userData.pagination && creditViewerDialog.userData.pagination.total_pages > 1 && (
                    <div className="flex items-center justify-between mt-3">
                      <div className="text-xs text-gray-500">
                        Page {creditViewerDialog.userData.pagination.page} of {creditViewerDialog.userData.pagination.total_pages}
                        ({creditViewerDialog.userData.pagination.total} total)
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
                          onClick={() => setChargesPage(p => Math.min(creditViewerDialog.userData.pagination.total_pages, p + 1))}
                          disabled={chargesPage >= creditViewerDialog.userData.pagination.total_pages}
                        >
                          Next
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          ) : (
            <div className="py-8 text-center text-gray-500">No data available</div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={closeCreditViewer}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Deny Refund Dialog */}
      <Dialog open={denyDialogOpen} onOpenChange={setDenyDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Deny Refund Request</DialogTitle>
            <DialogDescription>
              Please provide a reason for denying this refund request. The user will be notified.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="deny-reason">Denial Reason *</Label>
              <Textarea
                id="deny-reason"
                placeholder="Explain why this refund request cannot be approved (minimum 10 characters)"
                value={denyReason}
                onChange={(e) => setDenyReason(e.target.value)}
                rows={4}
                className="mt-2"
              />
              <p className="text-xs text-gray-500 mt-1">
                This reason will be sent to the user via email and displayed in their credit history.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setDenyDialogOpen(false);
                setDenyReason("");
              }}
              disabled={denySubmitting}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={async () => {
                if (!denyReason || denyReason.trim().length < 10) {
                  toast({
                    title: "Error",
                    description: "Please provide a detailed reason (at least 10 characters)",
                    variant: "destructive"
                  });
                  return;
                }

                if (!creditViewerDialog.refundRequest?.notification_id) {
                  toast({
                    title: "Error",
                    description: "Refund request notification ID not found",
                    variant: "destructive"
                  });
                  return;
                }

                setDenySubmitting(true);
                try {
                  await denyRefundRequest(
                    creditViewerDialog.refundRequest.notification_id,
                    denyReason.trim()
                  );
                  setDenyDialogOpen(false);
                  setDenyReason("");
                  // Reload credits to show updated status
                  if (creditViewerDialog.userId) {
                    viewUserCredits(creditViewerDialog.userId, chargesPage, chargesPerPage, creditViewerDialog.refundRequest);
                  }
                } catch (error) {
                  // Error already handled in hook
                } finally {
                  setDenySubmitting(false);
                }
              }}
              disabled={denySubmitting || !denyReason || denyReason.trim().length < 10}
            >
              {denySubmitting ? "Denying..." : "Deny Request"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Award Credits Dialog */}
      <Dialog open={awardDialogOpen} onOpenChange={setAwardDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Award Credits</DialogTitle>
            <DialogDescription>
              Award credits to {creditViewerDialog.userData?.email || 'this user'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div>
              <Label htmlFor="award-credits">Credits Amount *</Label>
              <Input
                id="award-credits"
                type="number"
                step="0.1"
                min="0.1"
                value={awardCredits}
                onChange={(e) => setAwardCredits(e.target.value)}
                placeholder="Enter credits amount"
              />
            </div>
            <div>
              <Label htmlFor="award-reason">Reason *</Label>
              <Input
                id="award-reason"
                value={awardReason}
                onChange={(e) => setAwardReason(e.target.value)}
                placeholder="e.g., Customer service compensation"
              />
            </div>
            <div>
              <Label htmlFor="award-notes">Notes (Optional)</Label>
              <Textarea
                id="award-notes"
                value={awardNotes}
                onChange={(e) => setAwardNotes(e.target.value)}
                placeholder="Additional notes..."
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setAwardDialogOpen(false)} disabled={awardSubmitting}>
              Cancel
            </Button>
            <Button onClick={handleAward} disabled={awardSubmitting} className="bg-green-600 hover:bg-green-700">
              {awardSubmitting ? "Awarding..." : "Award Credits"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
