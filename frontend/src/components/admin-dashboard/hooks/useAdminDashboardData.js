import { useState, useEffect, useCallback } from "react";
import { makeApi } from "@/lib/apiClient";

const defaultCreditDialogState = { open: false, userId: null, userData: null, loading: false, refundRequest: null, refundRequestDetail: null };

export function useAdminDashboardData({ token, toast }) {
  const [users, setUsers] = useState([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [summary, setSummary] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [episodesToday, setEpisodesToday] = useState(null);
  const [recentActivity, setRecentActivity] = useState([]);
  const [systemHealth, setSystemHealth] = useState(null);
  const [growthMetrics, setGrowthMetrics] = useState(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [seedResult, setSeedResult] = useState(null);
  const [killingQueue, setKillingQueue] = useState(false);
  const [adminSettings, setAdminSettings] = useState(null);
  const [adminSettingsSaving, setAdminSettingsSaving] = useState(false);
  const [adminSettingsErr, setAdminSettingsErr] = useState(null);
  const [savingIds, setSavingIds] = useState(new Set());
  const [saveErrors, setSaveErrors] = useState({});
  const [creditViewerDialog, setCreditViewerDialog] = useState(defaultCreditDialogState);

  const toastApiError = useCallback((error, fallback = "Request failed") => {
    const message = (error && (error.detail || error.message)) || fallback;
    try {
      toast?.({ title: "Error", description: message, variant: "destructive" });
    } catch (_) {
      // ignore toast errors
    }
  }, [toast]);

  const handleAdminForbidden = useCallback((error, message = "Access denied; returning to dashboard.") => {
    if (error && error.status === 403) {
      try {
        toast?.({ title: "Admin access denied", description: message });
      } catch (_) {
        // ignore toast errors
      }
      try {
        window.location.href = "/dashboard";
      } catch (_) {
        // ignore navigation issues
      }
      return true;
    }
    return false;
  }, [toast]);

  useEffect(() => {
    if (!token) {
      return;
    }

    const api = makeApi(token);
    setUsersLoading(true);
    setAnalyticsLoading(true);

    api.get("/api/admin/users/full")
      .then(setUsers)
      .catch((error) => {
        if (!handleAdminForbidden(error)) {
          toastApiError(error, "Failed to load users");
        }
      })
      .finally(() => setUsersLoading(false));

    api.get("/api/admin/summary")
      .then((data) => setSummary(data))
      .catch((error) => {
        if (!handleAdminForbidden(error)) {
          toastApiError(error, "Failed to load summary");
        }
      });

    api.get("/api/admin/metrics")
      .then((data) => setMetrics(data))
      .catch((error) => {
        setMetrics(null);
        if (!handleAdminForbidden(error)) {
          // metrics optional; do not surface toast
        }
      })
      .finally(() => setAnalyticsLoading(false));

    api.get("/api/admin/metrics/episodes-today")
      .then((data) => setEpisodesToday(data))
      .catch((error) => {
        setEpisodesToday(null);
        if (!handleAdminForbidden(error)) {
          // optional; do not surface toast
        }
      });

    api.get("/api/admin/metrics/recent-activity?limit=10")
      .then((data) => setRecentActivity(data || []))
      .catch((error) => {
        setRecentActivity([]);
        if (!handleAdminForbidden(error)) {
          // optional; do not surface toast
        }
      });

    api.get("/api/admin/metrics/system-health")
      .then((data) => setSystemHealth(data))
      .catch((error) => {
        setSystemHealth(null);
        if (!handleAdminForbidden(error)) {
          // optional; do not surface toast
        }
      });

    api.get("/api/admin/metrics/growth-metrics")
      .then((data) => setGrowthMetrics(data))
      .catch((error) => {
        setGrowthMetrics(null);
        if (!handleAdminForbidden(error)) {
          // optional; do not surface toast
        }
      });

    api.get("/api/admin/settings")
      .then(setAdminSettings)
      .catch((error) => {
        if (!handleAdminForbidden(error)) {
          setAdminSettings(null);
        }
      });
  }, [token, handleAdminForbidden, toastApiError]);

  const runSeed = useCallback(() => {
    if (!token) {
      return;
    }
    const api = makeApi(token);
    api.post("/api/admin/seed")
      .then((data) => {
        setSeedResult(data);
        api.get("/api/admin/summary").then(setSummary).catch(() => { });
      })
      .catch(() => {
        // seed failures are surfaced via console
      });
  }, [token]);

  const handleKillQueue = useCallback(async () => {
    if (!token || killingQueue) {
      return;
    }

    const confirmed = window.confirm("Immediately stop and flush all background tasks? This cannot be undone.");
    if (!confirmed) {
      return;
    }

    setKillingQueue(true);
    try {
      const api = makeApi(token);
      const result = await api.post("/api/admin/tasks/kill");
      const queueLabel = result?.queue ? `Queue ${result.queue}` : "Tasks queue";
      try {
        toast?.({ title: "Queue reset", description: `${queueLabel} purged and restarted.` });
      } catch (_) {
        // ignore toast errors
      }
    } catch (error) {
      toastApiError(error, "Failed to kill queue");
    } finally {
      setKillingQueue(false);
    }
  }, [killingQueue, toast, toastApiError, token]);

  const saveAdminSettings = useCallback(async (patch) => {
    if (!adminSettings) {
      return;
    }

    const next = { ...adminSettings, ...patch };
    setAdminSettings(next);
    setAdminSettingsSaving(true);
    setAdminSettingsErr(null);

    try {
      const api = makeApi(token);
      const data = await api.put("/api/admin/settings", next);
      setAdminSettings(data);
    } catch (error) {
      setAdminSettingsErr("Failed to save settings");
    } finally {
      setAdminSettingsSaving(false);
    }
  }, [adminSettings, token]);

  const updateUser = useCallback(async (id, payload) => {
    setSavingIds((prev) => new Set([...prev, id]));
    setSaveErrors((prev) => ({ ...prev, [id]: null }));

    try {
      const api = makeApi(token);
      const updated = await api.patch(`/api/admin/users/${id}`, payload);
      setUsers((prev) => prev.map((user) => (user.id === id ? updated : user)));

      if (payload.tier && payload.tier !== "admin") {
        try {
          toast?.({ title: "Tier updated", description: `User tier changed to ${payload.tier}` });
        } catch (_) {
          // ignore toast errors
        }
      }
    } catch (error) {
      setSaveErrors((prev) => ({ ...prev, [id]: error.message || "Network error" }));
      toastApiError(error, "Failed to update user");
    } finally {
      setSavingIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  }, [toast, toastApiError, token]);

  const grantAdminTier = useCallback(async (userId) => {
    setSavingIds((prev) => new Set([...prev, userId]));
    setSaveErrors((prev) => ({ ...prev, [userId]: null }));

    try {
      const api = makeApi(token);
      const updated = await api.patch(`/api/admin/users/${userId}`, { tier: "admin" });
      setUsers((prev) => prev.map((user) => (user.id === userId ? updated : user)));
      try {
        toast?.({ title: "Admin access granted", description: "User has been granted admin privileges" });
      } catch (_) {
        // ignore toast errors
      }
    } catch (error) {
      setSaveErrors((prev) => ({ ...prev, [userId]: error.message || "Network error" }));
      toastApiError(error, "Failed to grant admin access");
    } finally {
      setSavingIds((prev) => {
        const next = new Set(prev);
        next.delete(userId);
        return next;
      });
    }
  }, [toast, toastApiError, token]);

  const viewUserCredits = useCallback(async (userId, page = 1, perPage = 20, refundRequest = null) => {
    setCreditViewerDialog({ open: true, userId, userData: null, loading: true, refundRequest, refundRequestDetail: null });

    try {
      const api = makeApi(token);

      // Fetch credit data
      const data = await api.get(`/api/admin/users/${userId}/credits?page=${page}&per_page=${perPage}`);

      // If there's a refund request with notification_id, fetch detailed information
      let refundDetail = null;
      if (refundRequest?.notification_id) {
        try {
          refundDetail = await api.get(`/api/admin/users/refund-requests/${refundRequest.notification_id}/detail`);
        } catch (detailError) {
          // Log but don't fail - detail is nice-to-have
          console.warn('Failed to load refund request detail:', detailError);
        }
      }

      setCreditViewerDialog({
        open: true,
        userId,
        userData: data,
        loading: false,
        refundRequest,
        refundRequestDetail: refundDetail
      });
    } catch (error) {
      toastApiError(error, "Failed to load credit data");
      setCreditViewerDialog(defaultCreditDialogState);
    }
  }, [toastApiError, token]);

  const refundUserCredits = useCallback(async (userId, ledgerEntryIds, notes, manualCredits = undefined) => {
    try {
      const api = makeApi(token);
      const payload = {
        ledger_entry_ids: ledgerEntryIds,
        notes: notes || null
      };
      if (manualCredits !== undefined) {
        payload.manual_credits = manualCredits;
      }
      const result = await api.post(`/api/admin/users/${userId}/credits/refund`, payload);
      toast?.({ title: "Success", description: result.message || "Credits refunded successfully" });
      return result;
    } catch (error) {
      toastApiError(error, "Failed to refund credits");
      throw error;
    }
  }, [toast, toastApiError, token]);

  const awardUserCredits = useCallback(async (userId, credits, reason, notes) => {
    try {
      const api = makeApi(token);
      const result = await api.post(`/api/admin/users/${userId}/credits/award`, {
        credits: credits,
        reason: reason,
        notes: notes || null
      });
      toast?.({ title: "Success", description: result.message || "Credits awarded successfully" });
      return result;
    } catch (error) {
      toastApiError(error, "Failed to award credits");
      throw error;
    }
  }, [toast, toastApiError, token]);

  const denyRefundRequest = useCallback(async (notificationId, denialReason) => {
    try {
      const api = makeApi(token);
      const result = await api.post(`/api/admin/users/refund-requests/${notificationId}/deny`, {
        notification_id: notificationId,
        denial_reason: denialReason
      });
      toast?.({ title: "Success", description: result.message || "Refund request denied" });
      return result;
    } catch (error) {
      toastApiError(error, "Failed to deny refund request");
      throw error;
    }
  }, [toast, toastApiError, token]);

  const closeCreditViewer = useCallback(() => {
    setCreditViewerDialog(defaultCreditDialogState);
  }, []);

  const fetchRefundRequests = useCallback(async () => {
    try {
      const api = makeApi(token);
      const data = await api.get('/api/admin/users/refund-requests');
      return data || [];
    } catch (error) {
      toastApiError(error, "Failed to load refund requests");
      return [];
    }
  }, [toastApiError, token]);

  const deleteUser = useCallback(async (userId, userEmail, showPrep = true) => {
    if (showPrep) {
      // Call prepareUserForDeletion first to show prep dialog
      prepareUserForDeletion(userId, userEmail);
      return;
    }

    // Actual deletion logic (called from prepareUserForDeletion with showPrep=false)
    const confirmation = window.prompt(
      "\u26a0\ufe0f WARNING: This will PERMANENTLY delete this user and ALL their data!\n\n" +
      `User: ${userEmail}\n\n` +
      "This includes:\n" +
      "• User account\n" +
      "• All podcasts\n" +
      "• All episodes\n" +
      "• All media items\n\n" +
      'Type "yes" to confirm deletion:'
    );

    if (!confirmation) {
      return;
    }

    if (confirmation.toLowerCase() !== "yes") {
      try {
        toast?.({
          title: "Confirmation failed",
          description: 'Please type "yes" to confirm deletion.',
          variant: "destructive",
        });
      } catch (_) {
        // ignore toast errors
      }
      return;
    }

    setSavingIds((prev) => new Set([...prev, userId]));
    try {
      const api = makeApi(token);
      const result = await api.del(`/api/admin/users/${userId}`, { confirm_email: userEmail });
      setUsers((prev) => prev.filter((user) => user.id !== userId));

      api.get("/api/admin/summary")
        .then((data) => setSummary(data))
        .catch(() => { });

      const gcsCommand = result?.gcs_cleanup_command;
      try {
        toast?.({
          title: "User deleted",
          description: gcsCommand
            ? "User deleted. GCS files may need manual cleanup. Check console for command."
            : "User and all associated data deleted successfully.",
        });
      } catch (_) {
        // ignore toast errors
      }

      console.log("[ADMIN] User deletion result:", result);
      if (gcsCommand) {
        console.log("[ADMIN] GCS Cleanup Command:", gcsCommand);
      }
    } catch (error) {
      console.error("[DEBUG] Delete failed:", error);
      console.error("[DEBUG] Error status:", error?.status);
      console.error("[DEBUG] Error detail:", error?.detail);
      console.error("[DEBUG] Error message:", error?.message);
      console.error("[DEBUG] Error object full:", JSON.stringify(error, null, 2));

      const errorDetail = error?.detail || error?.message || error?.error?.detail || "";
      const isSafetyError = errorDetail.includes("inactive") || errorDetail.includes("free tier");

      if (isSafetyError && showPrep) {
        try {
          toast?.({
            title: "Safety check failed",
            description: errorDetail + ' Use the "Prepare for Deletion" button first.',
            variant: "destructive",
            duration: 6000,
          });
        } catch (_) {
          // ignore toast errors
        }
      } else {
        toastApiError(error, "Failed to delete user");
      }
    } finally {
      setSavingIds((prev) => {
        const next = new Set(prev);
        next.delete(userId);
        return next;
      });
    }
  }, [toast, toastApiError, token]);

  const prepareUserForDeletion = useCallback(async (userId, userEmail, userIsActive, userTier) => {
    const normalizedTier = (userTier || "").toLowerCase();
    const needsPrep = userIsActive || (userTier && normalizedTier !== "free" && normalizedTier !== "starter" && normalizedTier !== "hobby");

    if (!needsPrep) {
      await deleteUser(userId, userEmail, false);
      return;
    }

    const prepConfirm = window.confirm(
      "\u26a0\ufe0f SAFETY CHECK: This user must be INACTIVE and on HOBBY tier before deletion.\n\n" +
      `User: ${userEmail}\n` +
      `Current Status: ${userIsActive ? "ACTIVE" : "INACTIVE"}\n` +
      `Current Tier: ${userTier || "unknown"}\n\n` +
      "Click OK to automatically set this user to INACTIVE + HOBBY tier, then you can delete them.\n" +
      "Click Cancel to abort."
    );

    if (!prepConfirm) {
      return;
    }

    setSavingIds((prev) => new Set([...prev, userId]));
    try {
      const api = makeApi(token);
      // Use "hobby" as the tier value (backend should handle both "free", "starter", and "hobby")
      const payload = { is_active: false, tier: "hobby" };
      await api.patch(`/api/admin/users/${userId}`, payload);
      setUsers((prev) => prev.map((user) => (user.id === userId ? { ...user, is_active: false, tier: "hobby" } : user)));
      try {
        toast?.({
          title: "User prepared for deletion",
          description: `${userEmail} is now INACTIVE and on HOBBY tier. You can now delete this user.`,
        });
      } catch (_) {
        // ignore toast errors
      }
    } catch (error) {
      toastApiError(error, "Failed to prepare user for deletion");
    } finally {
      setSavingIds((prev) => {
        const next = new Set(prev);
        next.delete(userId);
        return next;
      });
    }
  }, [deleteUser, toast, toastApiError, token]);

  const verifyUserEmail = useCallback(async (userId, userEmail) => {
    const confirmed = window.confirm(
      `Manually verify email for ${userEmail}?\n\n` +
      "This will mark their email as verified, allowing them to access the platform.\n\n" +
      "Use this for users who are having trouble with automated verification."
    );

    if (!confirmed) {
      return;
    }

    setSavingIds((prev) => new Set([...prev, userId]));
    try {
      const api = makeApi(token);
      const result = await api.post(`/api/admin/users/${userId}/verify-email`);
      setUsers((prev) => prev.map((user) => (user.id === userId ? { ...user, email_verified: true } : user)));

      try {
        toast?.({
          title: "Email verified",
          description: result.already_verified
            ? `${userEmail} was already verified.`
            : `${userEmail} has been manually verified.`,
        });
      } catch (_) {
        // ignore toast errors
      }

      console.log("[ADMIN] Email verification result:", result);
    } catch (error) {
      toastApiError(error, "Failed to verify email");
    } finally {
      setSavingIds((prev) => {
        const next = new Set(prev);
        next.delete(userId);
        return next;
      });
    }
  }, [toast, toastApiError, token]);

  const triggerPasswordReset = useCallback(async (userId, userEmail) => {
    const confirmed = window.confirm(
      `Send password reset email to ${userEmail}?\n\n` +
      "This will generate a secure reset token and send the standard 'Reset your password' email to the user.\n\n" +
      "The user will be able to choose a new password via the link in the email."
    );

    if (!confirmed) {
      return;
    }

    setSavingIds((prev) => new Set([...prev, userId]));
    try {
      const api = makeApi(token);
      const result = await api.post(`/api/admin/users/${userId}/password-reset`);

      try {
        toast?.({
          title: "Password reset sent",
          description: result.message || `Password reset email sent to ${userEmail}`,
        });
      } catch (_) {
        // ignore toast errors
      }

      console.log("[ADMIN] Password reset result:", result);
    } catch (error) {
      toastApiError(error, "Failed to send password reset");
    } finally {
      setSavingIds((prev) => {
        const next = new Set(prev);
        next.delete(userId);
        return next;
      });
    }
  }, [toast, toastApiError, token]);

  return {
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
    fetchRefundRequests,
    prepareUserForDeletion,
    deleteUser,
    verifyUserEmail,
    triggerPasswordReset,
  };
}

export default useAdminDashboardData;
