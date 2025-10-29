import React from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { AlertTriangle, CheckCircle, XCircle } from "lucide-react";
import AdminFeatureToggles from "@/components/admin/AdminFeatureToggles.jsx";
import AdminLayoutToggle from "@/components/admin/AdminLayoutToggle.jsx";

export default function SettingsTab({
  token,
  adminSettings,
  onAdminSettingsSaved,
  settings,
  setSettings,
  adminSettingsSaving,
  adminSettingsErr,
  maintenanceDraft,
  setMaintenanceDraft,
  maintenanceMessageChanged,
  handleMaintenanceToggle,
  handleMaintenanceMessageSave,
  handleMaintenanceMessageReset,
  isSuperAdmin,
}) {
  return (
    <div className="space-y-6">
      <Card className="border-0 shadow-sm bg-white">
        <CardHeader>
          <CardTitle style={{ color: "#2C3E50" }}>Platform Features</CardTitle>
          <p className="text-gray-600">Enable or disable platform-wide features</p>
        </CardHeader>
        <CardContent className="space-y-6">
          {adminSettings ? (
            <AdminFeatureToggles
              token={token}
              initial={adminSettings}
              onSaved={onAdminSettingsSaved}
              readOnly={!isSuperAdmin}
              allowMaintenanceToggle
            />
          ) : (
            <p className="text-sm text-gray-500">Loading admin settings…</p>
          )}

          <AdminLayoutToggle />

          <div className="flex items-center justify-between">
            <div>
              <Label className="text-base font-medium text-gray-700">Enable AI Show Notes (Beta)</Label>
              <p className="text-sm text-gray-500 mt-1">Allow users to generate show notes automatically using AI</p>
            </div>
            <Switch
              aria-label="Enable AI Show Notes"
              checked={settings.aiShowNotes}
              onCheckedChange={(checked) => setSettings({ ...settings, aiShowNotes: checked })}
            />
          </div>

          <div className="flex items-center justify-between">
            <div>
              <Label className="text-base font-medium text-gray-700">Allow Guest Access to Podcasts</Label>
              <p className="text-sm text-gray-500 mt-1">Enable non-registered users to listen to public podcasts</p>
            </div>
            <Switch
              aria-label="Allow guest access"
              checked={settings.guestAccess}
              onCheckedChange={(checked) => setSettings({ ...settings, guestAccess: checked })}
            />
          </div>

          <div className="flex items-center justify-between">
            <div>
              <Label className="text-base font-medium text-gray-700">Maintenance Mode</Label>
              <p className="text-sm text-gray-500 mt-1">Temporarily disable platform access for maintenance</p>
            </div>
            <div className="flex items-center space-x-2">
              {adminSettings?.maintenance_mode && <AlertTriangle className="w-5 h-5 text-orange-500" />}
              <Switch
                aria-label="Maintenance mode"
                checked={!!(adminSettings && adminSettings.maintenance_mode)}
                disabled={adminSettingsSaving || !adminSettings}
                onCheckedChange={handleMaintenanceToggle}
              />
            </div>
          </div>

          <div className="mt-3 space-y-2">
            <Label className="text-sm font-medium text-gray-700">Maintenance Message</Label>
            <Textarea
              value={maintenanceDraft}
              onChange={(event) => setMaintenanceDraft(event.target.value)}
              placeholder="Let your users know what's happening..."
              rows={3}
              disabled={adminSettingsSaving || !adminSettings}
            />
            <div className="flex items-center justify-between text-xs text-gray-500">
              {adminSettingsErr && <span className="text-red-500">{adminSettingsErr}</span>}
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleMaintenanceMessageReset}
                  disabled={!maintenanceMessageChanged || adminSettingsSaving}
                >
                  Reset
                </Button>
                <Button
                  size="sm"
                  onClick={handleMaintenanceMessageSave}
                  disabled={!maintenanceMessageChanged || adminSettingsSaving}
                >
                  Save Message
                </Button>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <Label className="text-base font-medium text-gray-700">Auto Backup</Label>
              <p className="text-sm text-gray-500 mt-1">Automatically backup user data daily</p>
            </div>
            <Switch
              aria-label="Enable auto backup"
              checked={settings.autoBackup}
              onCheckedChange={(checked) => setSettings({ ...settings, autoBackup: checked })}
            />
          </div>
        </CardContent>
      </Card>

      <Card className="border-0 shadow-sm" style={{ backgroundColor: "#ECF0F1" }}>
        <CardHeader>
          <CardTitle style={{ color: "#2C3E50" }}>System Status</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid md:grid-cols-3 gap-4">
            <div className="flex items-center space-x-3">
              <CheckCircle className="w-5 h-5 text-green-600" />
              <div>
                <p className="font-medium text-gray-800">Database</p>
                <p className="text-sm text-green-600">Operational</p>
              </div>
            </div>
            <div className="flex items-center space-x-3">
              <CheckCircle className="w-5 h-5 text-green-600" />
              <div>
                <p className="font-medium text-gray-800">AI Services</p>
                <p className="text-sm text-green-600">Operational</p>
              </div>
            </div>
            <div className="flex items-center space-x-3">
              <XCircle className="w-5 h-5 text-red-600" />
              <div>
                <p className="font-medium text-gray-800">Email Service</p>
                <p className="text-sm text-red-600">Degraded</p>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
