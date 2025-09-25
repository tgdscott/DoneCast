"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, LayoutDashboard, User, Palette, Radio } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import ComfortMenu from "@/components/common/ComfortMenu.jsx";
import AudioCleanupSettings from "@/components/dashboard/AudioCleanupSettings";
import AdminSettings from "@/components/dashboard/AdminSettings";
import { useToast } from "@/hooks/use-toast";
import { useAuth } from "@/AuthContext.jsx";
import { makeApi, buildApiUrl } from "@/lib/apiClient";
import { SectionCard, SectionItem } from "@/components/dashboard/SettingsSections";

export default function Settings({ token }) {
  const { toast } = useToast();
  const { user: authUser, refreshUser } = useAuth();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [profileSaving, setProfileSaving] = useState(false);
  const [isSpreakerConnected, setIsSpreakerConnected] = useState(false);
  const pollRef = useRef(null);

  useEffect(() => {
    setFirstName(authUser?.first_name || "");
    setLastName(authUser?.last_name || "");
    setIsSpreakerConnected(!!authUser?.spreaker_access_token);
  }, [authUser]);

  const announceConnected = useCallback(() => {
    setIsSpreakerConnected((prev) => {
      if (!prev) {
        toast({
          title: "Spreaker connected",
          description: "Your account is ready for one-click publishing.",
        });
      }
      return true;
    });
  }, [toast]);

  const verifyConnection = useCallback(async () => {
    if (!token) return false;
    try {
      const user = await makeApi(token).get("/api/auth/users/me");
      if (user?.spreaker_access_token) {
        announceConnected();
        refreshUser?.({ force: true });
        return true;
      }
    } catch {
      // ignore errors, we will retry via polling
    }
    return false;
  }, [announceConnected, refreshUser, token]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("spreaker_connected") === "true") {
      announceConnected();
      verifyConnection().catch(() => {});
      window.history.replaceState({}, document.title, window.location.pathname);
    }
  }, [announceConnected, verifyConnection]);

  useEffect(() => {
    const handleMessage = (event) => {
      const allowed = new Set([window.location.origin]);
      try {
        const apiBase = buildApiUrl("");
        if (apiBase) {
          allowed.add(new URL(apiBase).origin);
        }
      } catch {}
      if (!allowed.has(event.origin)) return;
      const data = event.data;
      if (data === "spreaker_connected" || (data && data.type === "spreaker_connected")) {
        if (pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
        announceConnected();
        verifyConnection().catch(() => {});
      }
    };

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [announceConnected, verifyConnection]);

  useEffect(() => {
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, []);

  const handleSaveProfile = async () => {
    setProfileSaving(true);
    try {
      const api = makeApi(token);
      await api.patch("/api/auth/users/me/prefs", {
        first_name: firstName.trim(),
        last_name: lastName.trim(),
      });
      toast({ title: "Profile saved" });
      refreshUser({ force: true });
    } catch (err) {
      toast({
        title: "Could not save profile",
        description: err?.message || "Please try again.",
        variant: "destructive",
      });
    } finally {
      setProfileSaving(false);
    }
  };

  const handleConnectSpreaker = async () => {
    try {
      let popupUrl = null;
      if (token) {
        const qs = new URLSearchParams({ access_token: token }).toString();
        popupUrl = buildApiUrl(`/api/auth/spreaker/start?${qs}`);
      }
      if (!popupUrl) throw new Error("Could not start the Spreaker sign-in.");
      const popup = window.open(popupUrl, "spreakerAuth", "width=600,height=700");
      if (!popup) throw new Error("Popup blocked. Please allow popups and try again.");
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      pollRef.current = setInterval(async () => {
        if (!popup || popup.closed) {
          if (pollRef.current) {
            clearInterval(pollRef.current);
            pollRef.current = null;
          }
          await verifyConnection();
        }
      }, 1000);
    } catch (err) {
      toast({
        title: "Connection error",
        description: err?.message || "An unexpected error occurred.",
        variant: "destructive",
      });
    }
  };

  const handleDisconnectSpreaker = async () => {
    if (!window.confirm("Disconnect Spreaker? We will stop publishing automatically until you reconnect.")) {
      return;
    }
    try {
      const api = makeApi(token);
      await api.post("/api/spreaker/disconnect", {});
      toast({
        title: "Spreaker disconnected",
        description: "We will keep everything ready if you decide to reconnect later.",
      });
      refreshUser({ force: true });
      setIsSpreakerConnected(false);
    } catch (err) {
      toast({
        title: "Error",
        description: err?.message || "An unexpected error occurred.",
        variant: "destructive",
      });
    }
  };

  const goBack = () => {
    window.location.href = "/";
  };

  const profileDirty =
    firstName.trim() !== (authUser?.first_name || "") ||
    lastName.trim() !== (authUser?.last_name || "");

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
          icon={<Palette className="h-4 w-4 text-white" />}
          title="Display options"
          description="Adjust size and contrast for the dashboard, editor, and transcripts."
        >
          <ComfortMenu inline className="mt-1" />
          <p className="text-xs text-muted-foreground">Changes apply instantly; no save button needed.</p>
        </SectionItem>

        <SectionItem
          icon={<Radio className="h-4 w-4 text-white" />}
          title="Spreaker Connect"
          description="Link your Spreaker account so finished episodes can publish automatically."
        >
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-4">
            <span
              className={
                "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-sm font-medium " +
                (isSpreakerConnected
                  ? "border-emerald-200 bg-emerald-50 text-emerald-600"
                  : "border-slate-200 bg-white text-slate-600")
              }
            >
              <span className="h-2 w-2 rounded-full" style={{ backgroundColor: isSpreakerConnected ? '#047857' : '#94a3b8' }} />
              {isSpreakerConnected ? "Connected" : "Not connected"}
            </span>
            {isSpreakerConnected ? (
              <div className="flex flex-col gap-2 text-sm sm:flex-row sm:items-center sm:gap-3">
                <Button variant="secondary" onClick={handleDisconnectSpreaker}>
                  Disconnect
                </Button>
                <span className="text-xs text-muted-foreground max-w-xs">
                  We will pause auto-publishing until you reconnect.
                </span>
              </div>
            ) : (
              <div className="flex flex-col gap-2 text-sm sm:flex-row sm:items-center sm:gap-3">
                <Button onClick={handleConnectSpreaker}>Connect Spreaker</Button>
                <span className="text-xs text-muted-foreground max-w-xs">
                  A popup will open. If you do not see it, allow popups for this site and try again.
                </span>
              </div>
            )}
          </div>
        </SectionItem>
      </SectionCard>

      <AudioCleanupSettings />

      <AdminSettings />

      <div className="pt-6">
        <button
          type="button"
          onClick={() => {
            try {
              window.location.href = "/ab";
            } catch {}
          }}
          className="text-xs text-muted-foreground transition hover:text-slate-900"
        >
          A/B workspace
        </button>
      </div>
    </div>
  );
}




