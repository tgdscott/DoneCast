"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import {
  Headphones,
  Users,
  BarChart3,
  Settings as SettingsIcon,
  CreditCard,
  HelpCircle,
  LogOut,
  Shield,
  TrendingUp,
  Play,
  Zap,
  AlertTriangle,
  MessageSquare,
  Database,
  Bug,
  ArrowLeft,
  Coins,
} from "lucide-react";
import React from "react";
import { useAuth } from "@/AuthContext";
import DbExplorer from "@/components/admin/DbExplorer.jsx";
import { useToast } from "@/hooks/use-toast";
import AdminTierEditor from "@/components/admin/AdminTierEditor.jsx";
import AdminTierEditorV2 from "@/components/admin/AdminTierEditorV2.jsx";
import AdminMusicLibrary from "@/components/admin/AdminMusicLibrary.jsx";
import AdminLandingEditor from "@/components/admin/AdminLandingEditor.jsx";
import AdminBugsTab from "@/components/admin/tabs/AdminBugsTab.jsx";
import AdminPodcastsTab from "@/components/admin/tabs/AdminPodcastsTab.jsx";
import AdminBillingTab from "@/components/admin/tabs/AdminBillingTab.jsx";
import AdminHelpTab from "@/components/admin/tabs/AdminHelpTab.jsx";
import AdminDashboardTab from "@/components/admin/tabs/AdminDashboardTab.jsx";
import { useResolvedTimezone } from "@/hooks/useResolvedTimezone";
import { formatInTimezone } from "@/lib/timezone";
import useAdminDashboardData from "@/components/admin-dashboard/hooks/useAdminDashboardData";
import useAdminDashboardState from "@/components/admin-dashboard/hooks/useAdminDashboardState";
import UsersTab from "@/components/admin-dashboard/tabs/UsersTab.jsx";
import AnalyticsTab from "@/components/admin-dashboard/tabs/AnalyticsTab.jsx";
import DashboardOverviewTab from "@/components/admin-dashboard/tabs/DashboardOverviewTab.jsx";
import SettingsTab from "@/components/admin-dashboard/tabs/SettingsTab.jsx";

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

  const navigationItems = [
    { id: "dashboard", label: "Dashboard Overview", icon: BarChart3 },
    { id: "users", label: "Users", icon: Users },
    { id: "podcasts", label: "Podcasts", icon: Play },
    { id: "analytics", label: "Analytics", icon: TrendingUp },
    { id: "bugs", label: "Bug Reports", icon: Bug },
    { id: "tiers", label: "Tier Editor", icon: SettingsIcon },
    { id: "music", label: "Music Library", icon: Headphones },
    { id: "landing", label: "Front Page Content", icon: MessageSquare },
    { id: "db", label: "DB Explorer", icon: Database },
    { id: "settings", label: "Settings", icon: SettingsIcon },
    { id: "billing", label: "Billing", icon: CreditCard },
    { id: "help", label: "Help & Docs", icon: HelpCircle },
  ]

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
      <div className="w-64 bg-white border-r border-gray-200 flex flex-col">
        {/* Logo */}
        <div className="p-6 border-b border-gray-200">
          <div className="flex items-center space-x-3">
            <Headphones className="w-8 h-8" style={{ color: "#2C3E50" }} />
            <div>
              <h1 className="text-xl font-bold" style={{ color: "#2C3E50" }}>
                Podcast Plus Plus
              </h1>
              <p className="text-sm text-gray-600">Admin Panel</p>
            </div>
          </div>
        </div>

        {/* Navigation Menu */}
  <nav className="flex-1 p-4" role="navigation" aria-label="Admin side navigation">
          <ul className="space-y-2">
            {navigationItems.map((item) => (
              <li key={item.id}>
                <button
                  onClick={() => setActiveTab(item.id)}
                  className={`w-full flex items-center space-x-3 px-4 py-3 rounded-lg text-left transition-all ${
                    activeTab === item.id
                      ? "text-white shadow-md"
                      : "text-gray-600 hover:bg-gray-100 hover:text-gray-800"
                  }`}
                  style={{
                    backgroundColor: activeTab === item.id ? "#2C3E50" : "transparent",
                  }}>
                  <item.icon className="w-5 h-5" />
                  <span className="font-medium">{item.label}</span>
                </button>
              </li>
            ))}
          </ul>
        </nav>

        {/* Admin Info */}
        <div className="p-4 border-t border-gray-200">
          <div className="flex items-center space-x-3 mb-3">
            <Avatar className="h-8 w-8">
              <AvatarFallback>
                <Shield className="w-4 h-4" />
              </AvatarFallback>
            </Avatar>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-800">Admin User</p>
              <p className="text-xs text-gray-500">Platform Administrator</p>
            </div>
          </div>
          <Button 
            onClick={() => window.location.href = '/dashboard?view=user'} 
            variant="ghost" 
            size="sm" 
            className="w-full justify-start text-gray-600 mb-2"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Back to Dashboard
          </Button>
          <Button onClick={logout} variant="ghost" size="sm" className="w-full justify-start text-gray-600">
            <LogOut className="w-4 h-4 mr-2" />
            Logout
          </Button>
        </div>
      </div>
  {/* Main Content */}
  <div className="flex-1 flex flex-col" role="main" aria-label="Admin main content" tabIndex={-1}>
        {/* Top Header */}
        <header className="bg-white border-b border-gray-200 px-6 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold" style={{ color: "#2C3E50" }}>
                {navigationItems.find((item) => item.id === activeTab)?.label}
              </h1>
              <p className="text-gray-600 mt-1">
                {activeTab === "users" && "Manage platform users and their accounts"}
                {activeTab === "analytics" && "Monitor platform performance and user engagement"}
                {activeTab === "bugs" && "View and manage bug reports and user feedback from Mike"}
                {activeTab === "tiers" && "Configure tier features, credits, and processing pipelines (database-driven)"}
                {activeTab === "db" && "Browse & edit core tables (safe fields only)"}
                {activeTab === "music" && "Curate previewable background tracks for onboarding/templates"}
                {activeTab === "settings" && "Configure platform settings and features"}
                {activeTab === "dashboard" && "Overview of platform metrics and activity"}
                {activeTab === "landing" && "Customize landing page reviews, FAQs, and hero messaging"}
                {activeTab === "billing" && "View and manage billing details and subscriptions"}
              </p>
            </div>
            <div className="flex items-center space-x-4">
              <div className="text-xs px-2 py-1 rounded bg-secondary text-secondary-foreground">
                Brand: {document.documentElement.getAttribute("data-brand") || "ppp"}
              </div>
              <div className="text-sm text-gray-600">Last updated: {formatInTimezone(new Date(), { timeStyle: 'medium' }, resolvedTimezone)}</div>
            </div>
          </div>
        </header>

        {/* Content Area */}
        <main className="flex-1 p-6">
          {/* Real-time Alerts */}
          <div className="mb-6">
            {activeTab === 'dashboard' && (
              <DashboardOverviewTab analytics={analytics} runSeed={runSeed} seedResult={seedResult} />
            )}
            {adminSettings?.maintenance_mode && (
              <Card className="border-l-4 border-orange-500 bg-orange-50">
                <CardContent className="p-4">
                  <div className="flex items-center">
                    <AlertTriangle className="w-5 h-5 text-orange-600 mr-3" />
                    <div>
                      <p className="font-medium text-orange-800">Maintenance Mode Active</p>
                      <p className="text-sm text-orange-700">
                        {adminSettings?.maintenance_message || 'Platform is currently in maintenance mode. Users cannot access the service right now.'}
                      </p>
                    </div>
                    <Button
                      variant="outline"
                      size="sm"
                      className="ml-auto bg-transparent"
                      disabled={adminSettingsSaving}
                      onClick={() => saveAdminSettings({ maintenance_mode: false })}>
                      Disable
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {false && (
              <Card className="border-l-4 border-blue-500 bg-blue-50">
                <CardContent className="p-4">
                  <div className="flex items-center">
                    <Zap className="w-5 h-5 text-blue-600 mr-3" />
                    <div>
                      <p className="font-medium text-blue-800">System Update Available</p>
                      <p className="text-sm text-blue-700">
                        Version 2.1.0 is ready to install with new AI features and performance improvements.
                      </p>
                    </div>
                    <Button
                      size="sm"
                      className="ml-auto text-white"
                      style={{ backgroundColor: "#2C3E50" }}>
                      Update Now
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>

          {/* Users Tab */}
          {activeTab === "users" && (
            <UsersTab
              usersLoading={usersLoading}
              currentUsers={currentUsers}
              filteredUsers={filteredUsers}
              searchTerm={searchTerm}
              onSearchChange={setSearchTerm}
              tierFilter={tierFilter}
              onTierFilterChange={setTierFilter}
              statusFilter={statusFilter}
              onStatusFilterChange={setStatusFilter}
              verificationFilter={verificationFilter}
              onVerificationFilterChange={setVerificationFilter}
              usersPerPage={usersPerPage}
              indexOfFirstUser={indexOfFirstUser}
              indexOfLastUser={indexOfLastUser}
              currentPage={currentPage}
              onCurrentPageChange={setCurrentPage}
              totalPages={totalPages}
              savingIds={savingIds}
              saveErrors={saveErrors}
              editingDates={editingDates}
              setEditingDates={setEditingDates}
              onUpdateUser={handleUserUpdate}
              onPrepareUserForDeletion={prepareUserForDeletion}
              onViewUserCredits={viewUserCredits}
              onVerifyUserEmail={verifyUserEmail}
              isSuperAdmin={isSuperAdmin}
              isAdmin={isAdmin}
            />
          )}

          {activeTab === "tiers" && (
            <div className="space-y-4">
              <AdminTierEditorV2 />
              <div className="mt-8 pt-8 border-t">
                <div className="text-sm text-gray-500 mb-4">Legacy Editor (Deprecated)</div>
                <AdminTierEditor />
              </div>
            </div>
          )}

          {activeTab === "music" && (
            <div className="space-y-4">
              <AdminMusicLibrary />
            </div>
          )}

          {activeTab === "landing" && (
            <div className="space-y-4">
              <AdminLandingEditor token={token} />
            </div>
          )}

          {/* DB Explorer Tab */}
          {activeTab === "db" && (
            <div className="space-y-4">
              <DbExplorer readOnly={!isSuperAdmin} />
            </div>
          )}

          {/* Bug Reports Tab (Admin) */}
          {activeTab === "bugs" && (
            <AdminBugsTab token={token} />
          )}

          {/* Podcasts Tab (Admin) */}
          {activeTab === "podcasts" && (
            <AdminPodcastsTab />
          )}

          {/* Billing Tab (Admin) */}
          {activeTab === "billing" && (
            <AdminBillingTab />
          )}

          {/* Help & Docs Tab (Admin) */}
          {activeTab === "help" && (
            <AdminHelpTab />
          )}

          {/* Enhanced Analytics Tab */}
          {activeTab === "analytics" && (
            <AnalyticsTab analytics={analytics} metrics={metrics} analyticsLoading={analyticsLoading} />
          )}
          {/* Enhanced Dashboard Overview Tab */}
          {activeTab === "dashboard" && (
            <AdminDashboardTab
              analytics={analytics}
              handleKillQueue={handleKillQueue}
              killingQueue={killingQueue}
            />
          )}

          {/* Settings Tab */}
          {activeTab === "settings" && (
            <SettingsTab
              token={token}
              adminSettings={adminSettings}
              onAdminSettingsSaved={setAdminSettings}
              settings={settings}
              setSettings={setSettings}
              adminSettingsSaving={adminSettingsSaving}
              adminSettingsErr={adminSettingsErr}
              maintenanceDraft={maintenanceDraft}
              setMaintenanceDraft={setMaintenanceDraft}
              maintenanceMessageChanged={maintenanceMessageChanged}
              handleMaintenanceToggle={handleMaintenanceToggle}
              handleMaintenanceMessageSave={handleMaintenanceMessageSave}
              handleMaintenanceMessageReset={handleMaintenanceMessageReset}
              isSuperAdmin={isSuperAdmin}
            />
          )}
          {/* Other tabs placeholder */}
          {!["users", "analytics", "settings", "dashboard", "music", "tiers", "landing", "db", "podcasts", "bugs", "billing", "help"].includes(activeTab) && (
            <div className="text-center py-12">
              <h3 className="text-xl font-semibold text-gray-600 mb-2">
                {navigationItems.find((item) => item.id === activeTab)?.label} Coming Soon
              </h3>
              <p className="text-gray-500">This section is under development and will be available soon.</p>
            </div>
          )}
        </main>
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
