import { useCallback, useEffect, useMemo, useState } from "react";

const getInitialTab = () => {
  try {
    const params = new URLSearchParams(window.location.search);
    return params.get("tab") || "users";
  } catch (error) {
    return "users";
  }
};

const defaultAdminTierDialog = { open: false, userId: null, userName: "", confirmText: "" };

const defaultSettings = {
  aiShowNotes: true,
  guestAccess: false,
  maxFileSize: "500",
  autoBackup: true,
  emailNotifications: true,
};

export function useAdminDashboardState({ users, adminSettings }) {
  const [activeTab, setActiveTab] = useState(getInitialTab);
  const [searchTerm, setSearchTerm] = useState("");
  const [tierFilter, setTierFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [verificationFilter, setVerificationFilter] = useState("all");
  const [currentPage, setCurrentPage] = useState(1);
  const [usersPerPage] = useState(10);
  const [editingDates, setEditingDates] = useState({});
  const [adminTierDialog, setAdminTierDialog] = useState(defaultAdminTierDialog);
  const [settings, setSettings] = useState(defaultSettings);
  const [maintenanceDraft, setMaintenanceDraft] = useState("");

  useEffect(() => {
    setMaintenanceDraft(adminSettings?.maintenance_message ?? "");
  }, [adminSettings?.maintenance_message]);

  useEffect(() => {
    setCurrentPage(1);
  }, [searchTerm, tierFilter, statusFilter, verificationFilter]);

  const filteredUsers = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    return users.filter((user) => {
      const email = (user.email || "").toLowerCase();
      const tier = (user.tier || "").toLowerCase();
      const matchesSearch = !term || email.includes(term) || tier.includes(term);
      const matchesTier = tierFilter === "all" || tier === tierFilter;
      const matchesStatus =
        statusFilter === "all" ||
        (statusFilter === "active" && !!user.is_active) ||
        ((statusFilter === "inactive" || statusFilter === "suspended") && !user.is_active);
      const matchesVerification =
        verificationFilter === "all" ||
        (verificationFilter === "verified" && !!user.email_verified) ||
        (verificationFilter === "unverified" && !user.email_verified);

      return matchesSearch && matchesTier && matchesStatus && matchesVerification;
    });
  }, [users, searchTerm, tierFilter, statusFilter, verificationFilter]);

  const indexOfLastUser = currentPage * usersPerPage;
  const indexOfFirstUser = indexOfLastUser - usersPerPage;

  const currentUsers = useMemo(
    () => filteredUsers.slice(indexOfFirstUser, indexOfLastUser),
    [filteredUsers, indexOfFirstUser, indexOfLastUser]
  );

  const totalPages = useMemo(
    () => Math.max(1, Math.ceil(filteredUsers.length / Math.max(1, usersPerPage))),
    [filteredUsers.length, usersPerPage]
  );

  const maintenanceMessageChanged = maintenanceDraft !== (adminSettings?.maintenance_message ?? "");

  const openAdminTierDialog = useCallback((userId, userName) => {
    setAdminTierDialog({ open: true, userId, userName, confirmText: "" });
  }, []);

  const closeAdminTierDialog = useCallback(() => {
    setAdminTierDialog(defaultAdminTierDialog);
  }, []);

  return {
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
  };
}

export default useAdminDashboardState;
