import React from "react";
import PropTypes from "prop-types";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { AlertTriangle, Zap } from "lucide-react";

// Import tab components
import UsersTab from "@/components/admin-dashboard/tabs/UsersTab.jsx";
import AnalyticsTab from "@/components/admin-dashboard/tabs/AnalyticsTab.jsx";
import DashboardOverviewTab from "@/components/admin-dashboard/tabs/DashboardOverviewTab.jsx";
import SettingsTab from "@/components/admin-dashboard/tabs/SettingsTab.jsx";
import AdminDashboardTab from "@/components/admin/tabs/AdminDashboardTab.jsx";
import AdminPodcastsTab from "@/components/admin/tabs/AdminPodcastsTab.jsx";
import AdminBugsTab from "@/components/admin/tabs/AdminBugsTab.jsx";
import AdminBillingTab from "@/components/admin/tabs/AdminBillingTab.jsx";
import AdminHelpTab from "@/components/admin/tabs/AdminHelpTab.jsx";
import AdminTierEditorV2 from "@/components/admin/AdminTierEditorV2.jsx";
import AdminMusicLibrary from "@/components/admin/AdminMusicLibrary.jsx";
import AdminLandingEditor from "@/components/admin/AdminLandingEditor.jsx";
import DbExplorer from "@/components/admin/DbExplorer.jsx";
import PromoCodesTab from "@/components/admin-dashboard/tabs/PromoCodesTab.jsx";
import AffiliateSettingsTab from "@/components/admin-dashboard/tabs/AffiliateSettingsTab.jsx";

/**
 * AdminMainContent - Main content area that handles tab switching and renders tab components
 * 
 * @param {string} activeTab - Currently active tab ID
 * @param {Array} navigationItems - Array of nav items for fallback labels
 * @param {Object} adminSettings - Admin settings object
 * @param {boolean} adminSettingsSaving - Whether settings are being saved
 * @param {Function} saveAdminSettings - Function to save admin settings
 * @param {Object} analytics - Analytics data
 * @param {Function} runSeed - Function to run database seeding
 * @param {string} seedResult - Result message from seeding
 * @param {Object} metrics - Metrics data
 * @param {boolean} analyticsLoading - Whether analytics are loading
 * @param {Function} handleKillQueue - Function to kill Cloud Tasks queue
 * @param {boolean} killingQueue - Whether queue is being killed
 * @param {string} token - Auth token for API calls
 * @param {Object} settings - Settings object
 * @param {Function} setSettings - Function to update settings
 * @param {string} adminSettingsErr - Error message from saving admin settings
 * @param {string} maintenanceDraft - Draft maintenance message
 * @param {Function} setMaintenanceDraft - Function to update maintenance draft
 * @param {boolean} maintenanceMessageChanged - Whether maintenance message has changed
 * @param {Function} handleMaintenanceToggle - Function to toggle maintenance mode
 * @param {Function} handleMaintenanceMessageSave - Function to save maintenance message
 * @param {Function} handleMaintenanceMessageReset - Function to reset maintenance message
 * @param {boolean} isSuperAdmin - Whether user is superadmin
 * @param {boolean} isAdmin - Whether user is admin
 * @param {boolean} usersLoading - Whether users are loading
 * @param {Array} currentUsers - Current page of users
 * @param {Array} filteredUsers - All filtered users
 * @param {string} searchTerm - User search term
 * @param {Function} setSearchTerm - Function to set search term
 * @param {string} tierFilter - Tier filter
 * @param {Function} setTierFilter - Function to set tier filter
 * @param {string} statusFilter - Status filter
 * @param {Function} setStatusFilter - Function to set status filter
 * @param {string} verificationFilter - Verification filter
 * @param {Function} setVerificationFilter - Function to set verification filter
 * @param {number} usersPerPage - Number of users per page
 * @param {number} indexOfFirstUser - Index of first user on current page
 * @param {number} indexOfLastUser - Index of last user on current page
 * @param {number} currentPage - Current page number
 * @param {Function} setCurrentPage - Function to set current page
 * @param {number} totalPages - Total number of pages
 * @param {Set} savingIds - Set of user IDs being saved
 * @param {Object} saveErrors - Map of user IDs to error messages
 * @param {Object} editingDates - Map of user IDs to editing state
 * @param {Function} setEditingDates - Function to set editing dates
 * @param {Function} handleUserUpdate - Function to update user
 * @param {Function} prepareUserForDeletion - Function to prepare user for deletion
 * @param {Function} viewUserCredits - Function to view user credits
 * @param {Function} verifyUserEmail - Function to verify user email
 * @param {Function} setAdminSettings - Function to set admin settings
 */
export default function AdminMainContent({
  activeTab,
  navigationItems,
  adminSettings,
  adminSettingsSaving,
  saveAdminSettings,
  analytics,
  runSeed,
  seedResult,
  metrics,
  episodesToday,
  recentActivity,
  systemHealth,
  growthMetrics,
  analyticsLoading,
  handleKillQueue,
  killingQueue,
  token,
  settings,
  setSettings,
  adminSettingsErr,
  maintenanceDraft,
  setMaintenanceDraft,
  maintenanceMessageChanged,
  handleMaintenanceToggle,
  handleMaintenanceMessageSave,
  handleMaintenanceMessageReset,
  isSuperAdmin,
  isAdmin,
  usersLoading,
  currentUsers,
  filteredUsers,
  searchTerm,
  setSearchTerm,
  tierFilter,
  setTierFilter,
  statusFilter,
  setStatusFilter,
  verificationFilter,
  setVerificationFilter,
  usersPerPage,
  indexOfFirstUser,
  indexOfLastUser,
  currentPage,
  setCurrentPage,
  totalPages,
  savingIds,
  saveErrors,
  editingDates,
  setEditingDates,
  handleUserUpdate,
  prepareUserForDeletion,
  viewUserCredits,
  verifyUserEmail,
  triggerPasswordReset,
  setAdminSettings,
  onBulkDeleteTestUsers,
}) {
  return (
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
          onTriggerPasswordReset={triggerPasswordReset}
          isSuperAdmin={isSuperAdmin}
          isAdmin={isAdmin}
          onBulkDeleteTestUsers={onBulkDeleteTestUsers}
        />
      )}

      {activeTab === "tiers" && (
        <div className="space-y-4">
          <AdminTierEditorV2 />
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
        <AdminBillingTab onViewUserCredits={viewUserCredits} />
      )}

      {/* Help & Docs Tab (Admin) */}
      {activeTab === "help" && (
        <AdminHelpTab />
      )}

      {/* Promo Codes Tab (Admin) */}
      {activeTab === "promo-codes" && (
        <PromoCodesTab token={token} />
      )}

      {/* Referrals Tab (Admin) */}
      {activeTab === "referrals" && (
        <AffiliateSettingsTab token={token} />
      )}

      {/* Enhanced Analytics Tab */}
      {activeTab === "analytics" && (
        <AnalyticsTab
          analytics={analytics}
          metrics={metrics}
          growthMetrics={growthMetrics}
          systemHealth={systemHealth}
          analyticsLoading={analyticsLoading}
        />
      )}

      {/* Enhanced Dashboard Overview Tab */}
      {activeTab === "dashboard" && (
        <AdminDashboardTab
          analytics={analytics}
          episodesToday={episodesToday}
          recentActivity={recentActivity}
          systemHealth={systemHealth}
          growthMetrics={growthMetrics}
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
      {!["users", "analytics", "settings", "dashboard", "music", "tiers", "landing", "db", "podcasts", "bugs", "billing", "help", "promo-codes", "referrals"].includes(activeTab) && (
        <div className="text-center py-12">
          <h3 className="text-xl font-semibold text-gray-600 mb-2">
            {navigationItems.find((item) => item.id === activeTab)?.label} Coming Soon
          </h3>
          <p className="text-gray-500">This section is under development and will be available soon.</p>
        </div>
      )}
    </main>
  );
}

AdminMainContent.propTypes = {
  activeTab: PropTypes.string.isRequired,
  navigationItems: PropTypes.array.isRequired,
  adminSettings: PropTypes.object,
  adminSettingsSaving: PropTypes.bool.isRequired,
  saveAdminSettings: PropTypes.func.isRequired,
  analytics: PropTypes.object.isRequired,
  runSeed: PropTypes.func.isRequired,
  seedResult: PropTypes.string,
  metrics: PropTypes.object,
  analyticsLoading: PropTypes.bool.isRequired,
  handleKillQueue: PropTypes.func.isRequired,
  killingQueue: PropTypes.bool.isRequired,
  token: PropTypes.string,
  settings: PropTypes.object.isRequired,
  setSettings: PropTypes.func.isRequired,
  adminSettingsErr: PropTypes.string,
  maintenanceDraft: PropTypes.string.isRequired,
  setMaintenanceDraft: PropTypes.func.isRequired,
  maintenanceMessageChanged: PropTypes.bool.isRequired,
  handleMaintenanceToggle: PropTypes.func.isRequired,
  handleMaintenanceMessageSave: PropTypes.func.isRequired,
  handleMaintenanceMessageReset: PropTypes.func.isRequired,
  isSuperAdmin: PropTypes.bool.isRequired,
  isAdmin: PropTypes.bool.isRequired,
  usersLoading: PropTypes.bool.isRequired,
  currentUsers: PropTypes.array.isRequired,
  filteredUsers: PropTypes.array.isRequired,
  searchTerm: PropTypes.string.isRequired,
  setSearchTerm: PropTypes.func.isRequired,
  tierFilter: PropTypes.string.isRequired,
  setTierFilter: PropTypes.func.isRequired,
  statusFilter: PropTypes.string.isRequired,
  setStatusFilter: PropTypes.func.isRequired,
  verificationFilter: PropTypes.string.isRequired,
  setVerificationFilter: PropTypes.func.isRequired,
  usersPerPage: PropTypes.number.isRequired,
  indexOfFirstUser: PropTypes.number.isRequired,
  indexOfLastUser: PropTypes.number.isRequired,
  currentPage: PropTypes.number.isRequired,
  setCurrentPage: PropTypes.func.isRequired,
  totalPages: PropTypes.number.isRequired,
  savingIds: PropTypes.instanceOf(Set).isRequired,
  saveErrors: PropTypes.object.isRequired,
  editingDates: PropTypes.object.isRequired,
  setEditingDates: PropTypes.func.isRequired,
  handleUserUpdate: PropTypes.func.isRequired,
  prepareUserForDeletion: PropTypes.func.isRequired,
  viewUserCredits: PropTypes.func.isRequired,
  verifyUserEmail: PropTypes.func.isRequired,
  triggerPasswordReset: PropTypes.func.isRequired,
  setAdminSettings: PropTypes.func.isRequired,
  onBulkDeleteTestUsers: PropTypes.func,
};
