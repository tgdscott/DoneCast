"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Card, CardContent } from "@/components/ui/card";
import { Coins } from "lucide-react";
import React from "react";
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
    prepareUserForDeletion,
    verifyUserEmail,
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
          setAdminSettings={setAdminSettings}
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
                  </div>
                </div>
              )}
              
              {/* Recent Charges */}
              {creditViewerDialog.userData.recent_charges && creditViewerDialog.userData.recent_charges.length > 0 && (
                <div>
                  <div className="text-sm font-semibold text-gray-700 mb-3">Recent Charges (Last 20)</div>
                  <div className="border rounded-lg overflow-hidden">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          <TableHead className="text-xs">Date</TableHead>
                          <TableHead className="text-xs">Type</TableHead>
                          <TableHead className="text-xs">Episode</TableHead>
                          <TableHead className="text-xs text-right">Credits</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {creditViewerDialog.userData.recent_charges.map((charge) => (
                          <TableRow key={charge.id}>
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
    </div>
  );
}
