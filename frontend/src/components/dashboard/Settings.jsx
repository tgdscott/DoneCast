"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, LayoutDashboard, User, Palette, Radio, Clock, AlertTriangle, Trash2, XCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import ComfortMenu from "@/components/common/ComfortMenu.jsx";
import AudioCleanupSettings from "@/components/dashboard/AudioCleanupSettings";
import AdminSettings from "@/components/dashboard/AdminSettings";
import { AccountDeletionDialog, CancelDeletionDialog } from "@/components/dashboard/AccountDeletionDialog";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/AuthContext.jsx";
import { makeApi, buildApiUrl } from "@/lib/apiClient";
import { SectionCard, SectionItem } from "@/components/dashboard/SettingsSections";
import { TIMEZONE_OPTIONS, detectDeviceTimezoneInfo, getTimezoneLabel } from "@/lib/timezones";

export default function Settings({ token }) {
  const { toast } = useToast();
  const { user: authUser, refreshUser } = useAuth();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [timezone, setTimezone] = useState("");
  const [useDeviceTimezone, setUseDeviceTimezone] = useState(false);
  const [profileSaving, setProfileSaving] = useState(false);
  const [deletionDialogOpen, setDeletionDialogOpen] = useState(false);
  const [cancelDeletionDialogOpen, setCancelDeletionDialogOpen] = useState(false);
  const pollRef = useRef(null);
  
  const deviceTimezoneInfo = detectDeviceTimezoneInfo();

  const isScheduledForDeletion = authUser?.scheduled_for_deletion_at != null;
  const gracePeriodEndsAt = authUser?.grace_period_ends_at;

  useEffect(() => {
    setFirstName(authUser?.first_name || "");
    setLastName(authUser?.last_name || "");
    
    // Initialize timezone settings
    const userTz = authUser?.timezone || "";
    if (userTz === 'device' || !userTz) {
      setUseDeviceTimezone(true);
      setTimezone(deviceTimezoneInfo.value);
    } else {
      setUseDeviceTimezone(false);
      setTimezone(userTz);
    }
  }, [authUser, deviceTimezoneInfo.value]);

  const handleSaveProfile = async () => {
    setProfileSaving(true);
    try {
      const api = makeApi(token);
      const payload = {
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        timezone: useDeviceTimezone ? 'device' : timezone,
      };
      await api.patch("/api/auth/users/me/prefs", payload);
      toast({ title: "Settings saved successfully" });
      refreshUser({ force: true });
    } catch (err) {
      toast({
        title: "Could not save settings",
        description: err?.message || "Please try again.",
        variant: "destructive",
      });
    } finally {
      setProfileSaving(false);
    }
  };

  const goBack = () => {
    window.location.href = "/";
  };

  const profileDirty =
    firstName.trim() !== (authUser?.first_name || "") ||
    lastName.trim() !== (authUser?.last_name || "") ||
    (useDeviceTimezone ? 'device' : timezone) !== (authUser?.timezone || "");

  const handleDeletionSuccess = () => {
    // Refresh user data to get updated deletion status
    refreshUser({ force: true });
  };

  const formatGracePeriodDate = (dateString) => {
    if (!dateString) return "";
    try {
      const date = new Date(dateString);
      return date.toLocaleDateString("en-US", {
        year: "numeric",
        month: "long",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
    } catch {
      return dateString;
    }
  };

  return (
    <div className="mx-auto max-w-5xl space-y-8 bg-slate-50/80 p-6">
      <button
        onClick={goBack}
        className="flex items-center text-sm text-slate-600 transition hover:text-slate-900"
        aria-label="Back to dashboard"
        type="button"
      >
        <ArrowLeft className="mr-1 h-4 w-4" />
        Back to dashboard
      </button>

      <div className="space-y-2">
        <h1 className="text-3xl font-semibold text-slate-900">Settings</h1>
        <p className="text-sm text-muted-foreground max-w-2xl">
          Tune the workspace so it feels welcoming and make sure your automations know who they are helping.
        </p>
      </div>

      <SectionCard
        icon={<LayoutDashboard className="h-5 w-5 text-white" />}
        title="Site & Display Preferences"
        subtitle="Personal details stay private to your team."
        defaultOpen
      >
        <SectionItem
          icon={<User className="h-4 w-4 text-white" />}
          title="Name"
          description="We use this to greet you and label any automations we run on your behalf."
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-1">
              <label htmlFor="settings-first-name" className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                First name
              </label>
              <Input
                id="settings-first-name"
                value={firstName}
                onChange={(event) => setFirstName(event.target.value)}
                placeholder="Jane"
                autoComplete="given-name"
              />
            </div>
            <div className="space-y-1">
              <label htmlFor="settings-last-name" className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Last name
              </label>
              <Input
                id="settings-last-name"
                value={lastName}
                onChange={(event) => setLastName(event.target.value)}
                placeholder="Doe"
                autoComplete="family-name"
              />
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-3 pt-2">
            <Button onClick={handleSaveProfile} disabled={!profileDirty || profileSaving}>
              {profileSaving ? "Saving..." : "Save name"}
            </Button>
            <span className="text-xs text-muted-foreground">
              {profileDirty ? "You have unsaved changes" : "Last updated from your profile"}
            </span>
          </div>
        </SectionItem>

        <SectionItem
          icon={<Clock className="h-4 w-4 text-white" />}
          title="Time zone"
          description="All times on the site will display in your selected timezone."
        >
          <div className="space-y-4">
            <div className="flex items-start space-x-3">
              <Checkbox
                id="use-device-timezone"
                checked={useDeviceTimezone}
                onCheckedChange={(checked) => {
                  setUseDeviceTimezone(checked);
                  if (checked) {
                    setTimezone(deviceTimezoneInfo.value);
                  }
                }}
              />
              <div className="space-y-1 flex-1">
                <Label
                  htmlFor="use-device-timezone"
                  className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70 cursor-pointer"
                >
                  Use my device's timezone automatically
                </Label>
                <p className="text-xs text-muted-foreground">
                  Recommended for travelers. Currently detected: <span className="font-medium">{deviceTimezoneInfo.label}</span>
                </p>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="timezone-select" className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Or select a specific timezone
              </Label>
              <Select
                value={timezone}
                onValueChange={setTimezone}
                disabled={useDeviceTimezone}
              >
                <SelectTrigger id="timezone-select" className={useDeviceTimezone ? "opacity-50" : ""}>
                  <SelectValue placeholder="Select timezone">
                    {timezone ? getTimezoneLabel(timezone) || timezone : "Select timezone"}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent className="max-h-[300px]">
                  {TIMEZONE_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                This affects episode schedules, notifications, and all displayed timestamps.
              </p>
            </div>
          </div>
        </SectionItem>

        <SectionItem
          icon={<Palette className="h-4 w-4 text-white" />}
          title="Display options"
          description="Adjust size and contrast for the dashboard, editor, and transcripts."
        >
          <ComfortMenu inline className="mt-1" />
          <p className="text-xs text-muted-foreground">Changes apply instantly; no save button needed.</p>
        </SectionItem>
      </SectionCard>

      <AudioCleanupSettings />

      <AdminSettings />

      {/* Danger Zone - Account Deletion */}
      <SectionCard
        icon={<AlertTriangle className="h-5 w-5 text-white" />}
        title="Danger Zone"
        subtitle="Permanent actions that cannot be easily undone."
        defaultOpen={false}
        variant="danger"
      >
        <SectionItem
          icon={<Trash2 className="h-4 w-4 text-white" />}
          title="Delete Account"
          description="Permanently delete your account and all associated data."
        >
          {isScheduledForDeletion ? (
            <div className="space-y-4">
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-4">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="h-5 w-5 text-amber-600 mt-0.5 flex-shrink-0" />
                  <div className="space-y-2">
                    <p className="text-sm font-semibold text-amber-900">
                      Your account is scheduled for deletion
                    </p>
                    <p className="text-sm text-amber-800">
                      Grace period ends: <span className="font-medium">{formatGracePeriodDate(gracePeriodEndsAt)}</span>
                    </p>
                    <p className="text-xs text-amber-700">
                      You can cancel this deletion at any time before the grace period ends. All your data will be preserved.
                    </p>
                  </div>
                </div>
              </div>
              <Button
                variant="default"
                onClick={() => setCancelDeletionDialogOpen(true)}
                className="gap-2 bg-green-600 hover:bg-green-700"
              >
                <XCircle className="h-4 w-4" />
                Cancel Deletion & Restore Account
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="h-5 w-5 text-red-600 mt-0.5 flex-shrink-0" />
                  <div className="space-y-2">
                    <p className="text-sm font-semibold text-red-900">
                      This action has serious consequences
                    </p>
                    <ul className="text-sm text-red-800 space-y-1">
                      <li>• All your podcasts and episodes will be deleted</li>
                      <li>• Published RSS feeds will stop working</li>
                      <li>• All media files and transcripts will be removed</li>
                      <li>• You'll have a grace period to cancel (2-30 days based on content)</li>
                    </ul>
                  </div>
                </div>
              </div>
              <Button
                variant="destructive"
                onClick={() => setDeletionDialogOpen(true)}
                className="gap-2"
              >
                <Trash2 className="h-4 w-4" />
                Delete My Account
              </Button>
            </div>
          )}
        </SectionItem>
      </SectionCard>

      {/* Deletion Dialogs */}
      <AccountDeletionDialog
        open={deletionDialogOpen}
        onOpenChange={setDeletionDialogOpen}
        token={token}
        userEmail={authUser?.email || ""}
        onSuccess={handleDeletionSuccess}
      />
      <CancelDeletionDialog
        open={cancelDeletionDialogOpen}
        onOpenChange={setCancelDeletionDialogOpen}
        token={token}
        onSuccess={handleDeletionSuccess}
      />

    </div>
  );
}




