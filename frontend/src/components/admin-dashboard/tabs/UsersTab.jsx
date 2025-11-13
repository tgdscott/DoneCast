import React, { useMemo, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Switch } from "@/components/ui/switch";
import {
  Search,
  Download,
  MessageSquare,
  Plus,
  MailCheck,
  Mail,
  Coins,
  Trash,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";

function getStatusBadge(status) {
  switch (status) {
    case "Active":
      return <Badge className="bg-green-100 text-green-800">Active</Badge>;
    case "Suspended":
      return <Badge className="bg-red-100 text-red-800">Suspended</Badge>;
    case "Inactive":
      return <Badge className="bg-gray-100 text-gray-800">Inactive</Badge>;
    default:
      return <Badge variant="secondary">{status}</Badge>;
  }
}

function getTierBadge(tier) {
  const normalized = (tier || "").toLowerCase();
  if (normalized === "pro") return <Badge className="bg-purple-100 text-purple-800">Pro</Badge>;
  if (normalized === "creator") return <Badge className="bg-blue-100 text-blue-800">Creator</Badge>;
  if (normalized === "free" || normalized === "starter") return <Badge className="bg-gray-100 text-gray-800">Starter</Badge>;
  if (normalized === "unlimited") return <Badge className="bg-yellow-100 text-yellow-800">Unlimited</Badge>;
  if (normalized === "executive") return <Badge className="bg-teal-100 text-teal-800">Executive</Badge>;
  if (normalized === "admin") return <Badge className="bg-orange-100 text-orange-800">Admin</Badge>;
  if (normalized === "superadmin") return <Badge className="bg-red-100 text-red-800">Super Admin</Badge>;
  return <Badge variant="secondary">{tier || "—"}</Badge>;
}

const isValidDateString = (value) => /^(\d{4})-(\d{2})-(\d{2})$/.test(value);
const isoToUS = (iso) => {
  if (!iso || !isValidDateString(iso.slice(0, 10))) return "";
  const year = iso.slice(0, 4);
  const month = iso.slice(5, 7);
  const day = iso.slice(8, 10);
  return `${month}/${day}/${year}`;
};
const usToISO = (input) => {
  const match = input.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (!match) return null;
  let [, mm, dd, yyyy] = match;
  if (mm.length === 1) mm = `0${mm}`;
  if (dd.length === 1) dd = `0${dd}`;
  const iso = `${yyyy}-${mm}-${dd}`;
  if (!isValidDateString(iso)) return null;
  return iso;
};
const isoToDateObj = (iso) => new Date(`${iso}T00:00:00Z`);
const dateObjToISO = (date) => date.toISOString().slice(0, 10);
const addMonths = (date, months) => {
  const nextDate = new Date(date.getTime());
  const day = nextDate.getUTCDate();
  nextDate.setUTCDate(1);
  nextDate.setUTCMonth(nextDate.getUTCMonth() + months);
  const monthLength = new Date(Date.UTC(nextDate.getUTCFullYear(), nextDate.getUTCMonth() + 1, 0)).getUTCDate();
  nextDate.setUTCDate(Math.min(day, monthLength));
  return nextDate;
};
const addYears = (date, years) => {
  const nextDate = new Date(date.getTime());
  nextDate.setUTCFullYear(nextDate.getUTCFullYear() + years);
  return nextDate;
};

// Auto-format date input (MM/DD/YYYY)
const formatDateInput = (value) => {
  const raw = value.replace(/[^0-9/]/g, "");
  let formatted = raw;
  if (/^\d{3,}$/.test(raw) && raw.indexOf("/") === -1) {
    if (raw.length >= 2) formatted = `${raw.slice(0, 2)}/${raw.slice(2)}`;
    if (raw.length >= 4) formatted = `${formatted.slice(0, 5)}/${formatted.slice(5)}`;
  }
  return formatted.slice(0, 10);
};

export default function UsersTab({
  usersLoading,
  currentUsers,
  filteredUsers,
  searchTerm,
  onSearchChange,
  tierFilter,
  onTierFilterChange,
  statusFilter,
  onStatusFilterChange,
  verificationFilter,
  onVerificationFilterChange,
  usersPerPage,
  indexOfFirstUser,
  indexOfLastUser,
  currentPage,
  onCurrentPageChange,
  totalPages,
  savingIds,
  saveErrors,
  editingDates,
  setEditingDates,
  onUpdateUser,
  onPrepareUserForDeletion,
  onViewUserCredits,
  onVerifyUserEmail,
  isSuperAdmin,
  isAdmin,
}) {
  const deriveBaseISO = useCallback((user) => {
    const pending = editingDates[user.id];
    if (pending) {
      const iso = usToISO(pending);
      if (iso) return iso;
    }
    return user.subscription_expires_at || new Date().toISOString().slice(0, 10);
  }, [editingDates]);

  const handleDateBlur = (userId) => {
    const value = editingDates[userId];
    if (value === undefined) return;
    if (value === "") {
      onUpdateUser(userId, { subscription_expires_at: "" });
    } else if (value.length === 10) {
      const iso = usToISO(value);
      if (iso) {
        onUpdateUser(userId, { subscription_expires_at: iso });
      }
    }
    setEditingDates((prev) => {
      const next = { ...prev };
      delete next[userId];
      return next;
    });
  };

  const handlePageChange = (page) => {
    onCurrentPageChange(page);
  };

  return (
    <div className="space-y-6">
      <Card className="border-0 shadow-sm bg-white">
        <CardContent className="p-6">
          <div className="flex flex-col lg:flex-row gap-4 items-start lg:items-center justify-between">
            <div className="flex-1 space-y-4 lg:space-y-0 lg:flex lg:items-center lg:space-x-4">
              <div className="relative flex-1 max-w-md">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
                <Input
                  placeholder="Search users by name, email, or tier..."
                  className="pl-10"
                  value={searchTerm}
                  onChange={(event) => onSearchChange(event.target.value)}
                />
              </div>
              <div className="flex items-center space-x-3">
                <Select value={tierFilter} onValueChange={onTierFilterChange}>
                  <SelectTrigger className="w-32" aria-label="Filter by tier">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Tiers</SelectItem>
                    <SelectItem value="pro">Pro</SelectItem>
                    <SelectItem value="creator">Creator</SelectItem>
                    <SelectItem value="starter">Starter</SelectItem>
                    <SelectItem value="executive">Executive</SelectItem>
                    <SelectItem value="unlimited">Unlimited</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={statusFilter} onValueChange={onStatusFilterChange}>
                  <SelectTrigger className="w-32" aria-label="Filter by status">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Status</SelectItem>
                    <SelectItem value="active">Active</SelectItem>
                    <SelectItem value="inactive">Inactive</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={verificationFilter} onValueChange={onVerificationFilterChange}>
                  <SelectTrigger className="w-32" aria-label="Filter by email verification">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Users</SelectItem>
                    <SelectItem value="verified">Verified</SelectItem>
                    <SelectItem value="unverified">Unverified</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="flex items-center space-x-3">
              <Button aria-label="Export CSV" variant="outline" size="sm">
                <Download className="w-4 h-4 mr-2" />
                Export CSV
              </Button>
              <Button aria-label="Bulk Message" variant="outline" size="sm">
                <MessageSquare className="w-4 h-4 mr-2" />
                Bulk Message
              </Button>
              <Button size="sm" className="text-white" style={{ backgroundColor: "#2C3E50" }}>
                <Plus className="w-4 h-4 mr-2" />
                Add User
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card className="border-0 shadow-sm bg-white">
        <CardContent className="p-0">
          {!usersLoading ? (
            <Table>
              <TableHeader>
                <TableRow className="border-b border-gray-200">
                  <TableHead className="font-semibold text-gray-700">User</TableHead>
                  <TableHead className="font-semibold text-gray-700">Email</TableHead>
                  <TableHead className="font-semibold text-gray-700">Verified</TableHead>
                  <TableHead className="font-semibold text-gray-700">Tier</TableHead>
                  <TableHead className="font-semibold text-gray-700">Status</TableHead>
                  <TableHead className="font-semibold text-gray-700">Episodes</TableHead>
                  <TableHead className="font-semibold text-gray-700">Last Login</TableHead>
                  <TableHead className="font-semibold text-gray-700">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {currentUsers.map((user) => {
                  const rawName = user?.email || user?.first_name || user?.last_name || "User";
                  const safeName = String(rawName || "User");
                  const emailPart = safeName.includes("@") ? safeName.split("@")[0] : safeName;
                  const initials = (emailPart || "U").slice(0, 2).toUpperCase();
                  const displayName = safeName;

                  return (
                    <TableRow key={user.id} className="hover:bg-gray-50">
                      <TableCell>
                        <div className="flex items-center space-x-3">
                          <Avatar className="h-10 w-10">
                            <AvatarImage src={user.avatar || "/placeholder.svg"} />
                            <AvatarFallback>{initials}</AvatarFallback>
                          </Avatar>
                          <div>
                            <div className="font-medium text-gray-800">{displayName}</div>
                            <div className="text-sm text-gray-500">Created {(user.created_at || "").toString().slice(0, 10)}</div>
                          </div>
                        </div>
                      </TableCell>
                      <TableCell className="text-gray-600">{user.email}</TableCell>
                      <TableCell>
                        {user.email_verified ? (
                          <div className="flex items-center text-green-600" title="Email verified">
                            <MailCheck className="w-4 h-4 mr-1" />
                            <span className="text-xs">Yes</span>
                          </div>
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 px-2 text-[10px] text-orange-600 hover:text-orange-700 hover:bg-orange-50"
                            disabled={savingIds.has(user.id)}
                            onClick={() => onVerifyUserEmail(user.id, user.email)}
                            title="Manually verify this user's email"
                          >
                            <Mail className="w-3 h-3 mr-1" />
                            Verify
                          </Button>
                        )}
                      </TableCell>
                      <TableCell>{getTierBadge(user.tier || "starter")}</TableCell>
                      <TableCell>{getStatusBadge(user.is_active ? "Active" : "Inactive")}</TableCell>
                      <TableCell className="text-gray-600">{user.episode_count}</TableCell>
                      <TableCell className="text-gray-600">{user.last_activity ? user.last_activity.slice(0, 10) : "—"}</TableCell>
                      <TableCell>
                        <div className="flex items-center space-x-2">
                          <Select
                            defaultValue={user.tier === "free" ? "starter" : (user.tier || "starter")}
                            onValueChange={(value) => onUpdateUser(user.id, { tier: value })}
                            disabled={savingIds.has(user.id) || user.tier === "superadmin"}
                          >
                            <SelectTrigger className="w-24 h-8 text-xs" aria-label={`Tier for ${displayName}`}>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="starter">Starter</SelectItem>
                              <SelectItem value="creator">Creator</SelectItem>
                              <SelectItem value="pro">Pro</SelectItem>
                              <SelectItem value="executive">Executive</SelectItem>
                              <SelectItem value="unlimited">Unlimited</SelectItem>
                              {isSuperAdmin && <SelectItem value="admin">Admin</SelectItem>}
                              {user.tier === "superadmin" && (
                                <SelectItem value="superadmin" disabled>
                                  Super Admin
                                </SelectItem>
                              )}
                            </SelectContent>
                          </Select>
                          <Switch
                            aria-label={`Active status for ${displayName}`}
                            checked={!!user.is_active}
                            disabled={savingIds.has(user.id)}
                            onCheckedChange={(value) => onUpdateUser(user.id, { is_active: value })}
                          />
                          <input
                            aria-label="Subscription expiry date"
                            type="text"
                            inputMode="numeric"
                            className={`border rounded px-2 py-1 text-xs w-28 ${
                              editingDates[user.id] &&
                              editingDates[user.id].length > 0 &&
                              usToISO(editingDates[user.id]) === null
                                ? "border-red-400"
                                : ""
                            }`}
                            value={editingDates[user.id] ?? isoToUS(user.subscription_expires_at)}
                            onChange={(event) => {
                              const nextValue = formatDateInput(event.target.value);
                              setEditingDates((prev) => ({ ...prev, [user.id]: nextValue }));
                            }}
                            onBlur={() => handleDateBlur(user.id)}
                            disabled={savingIds.has(user.id)}
                            placeholder="MM/DD/YYYY"
                            title="Subscription expiry (MM/DD/YYYY)"
                          />
                          <div className="flex space-x-1">
                            <button
                              type="button"
                              className="text-[10px] px-1 py-0.5 border rounded bg-gray-100 hover:bg-gray-200"
                              disabled={savingIds.has(user.id)}
                              onClick={() => {
                                const baseIso = deriveBaseISO(user);
                                const date = addMonths(isoToDateObj(baseIso), 1);
                                const iso = dateObjToISO(date);
                                setEditingDates((prev) => ({ ...prev, [user.id]: isoToUS(iso) }));
                                onUpdateUser(user.id, { subscription_expires_at: iso });
                              }}
                            >
                              +1M
                            </button>
                            <button
                              type="button"
                              className="text-[10px] px-1 py-0.5 border rounded bg-gray-100 hover:bg-gray-200"
                              disabled={savingIds.has(user.id)}
                              onClick={() => {
                                const baseIso = deriveBaseISO(user);
                                const date = addYears(isoToDateObj(baseIso), 1);
                                const iso = dateObjToISO(date);
                                setEditingDates((prev) => ({ ...prev, [user.id]: isoToUS(iso) }));
                                onUpdateUser(user.id, { subscription_expires_at: iso });
                              }}
                            >
                              +1Y
                            </button>
                            <button
                              type="button"
                              className="text-[10px] px-1 py-0.5 border rounded bg-gray-100 hover:bg-gray-200"
                              disabled={savingIds.has(user.id)}
                              onClick={() => {
                                const iso = new Date().toISOString().slice(0, 10);
                                setEditingDates((prev) => ({ ...prev, [user.id]: isoToUS(iso) }));
                                onUpdateUser(user.id, { subscription_expires_at: iso });
                              }}
                            >
                              Today
                            </button>
                            <button
                              type="button"
                              className="text-[10px] px-1 py-0.5 border rounded bg-gray-100 hover:bg-gray-200"
                              disabled={savingIds.has(user.id)}
                              onClick={() => {
                                setEditingDates((prev) => ({ ...prev, [user.id]: "" }));
                                onUpdateUser(user.id, { subscription_expires_at: "" });
                              }}
                            >
                              Clear
                            </button>
                          </div>
                          {(user.is_active || (user.tier && user.tier.toLowerCase() !== "free" && user.tier.toLowerCase() !== "starter")) && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-8 px-2 text-[10px] text-orange-600 hover:text-orange-700 hover:bg-orange-50"
                              disabled={savingIds.has(user.id)}
                              onClick={() => onPrepareUserForDeletion(user.id, user.email, user.is_active, user.tier)}
                              title="Set user to INACTIVE + FREE tier (required before deletion)"
                            >
                              Prep
                            </Button>
                          )}
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-8 px-2 text-[10px] text-blue-600 hover:text-blue-700 hover:bg-blue-50"
                            onClick={() => onViewUserCredits(user.id)}
                            title="View credit balance and usage"
                          >
                            <Coins className="h-3 w-3 mr-1" />
                            Credits
                          </Button>
                          {isSuperAdmin && (
                            <Button
                              variant="ghost"
                              size="sm"
                              className="h-8 w-8 p-0 text-red-600 hover:text-red-700 hover:bg-red-50"
                              disabled={savingIds.has(user.id)}
                              onClick={() => onPrepareUserForDeletion(user.id, user.email, user.is_active, user.tier)}
                              title={
                                user.is_active || (user.tier && user.tier.toLowerCase() !== "free" && user.tier.toLowerCase() !== "starter")
                                  ? "User must be INACTIVE + STARTER tier to delete. Click to prepare first."
                                  : "Delete user and all their data (permanent)"
                              }
                              aria-label={`Delete user ${displayName}`}
                            >
                              <Trash className="h-4 w-4" />
                            </Button>
                          )}
                          {!isSuperAdmin && isAdmin && (
                            <span className="text-[10px] text-gray-500 italic px-2" title="Only superadmin can delete users">
                              Delete restricted
                            </span>
                          )}
                          {savingIds.has(user.id) && <span className="text-[10px] text-gray-400">Saving…</span>}
                          {saveErrors[user.id] && (
                            <span className="text-[10px] text-red-500" title={saveErrors[user.id]}>
                              Err
                            </span>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          ) : (
            <div className="p-4 space-y-2">
              {Array.from({ length: usersPerPage }).map((_, index) => (
                <div key={index} className="h-10 bg-gray-100 rounded animate-pulse" />
              ))}
            </div>
          )}

          <div className="flex items-center justify-between px-6 py-4 border-t border-gray-200">
            <div className="text-sm text-gray-600">
              Showing {indexOfFirstUser + 1} to {Math.min(indexOfLastUser, filteredUsers.length)} of {filteredUsers.length} users
            </div>
            <div className="flex items-center space-x-2">
              <Button
                aria-label="Previous page"
                variant="outline"
                size="sm"
                onClick={() => handlePageChange(Math.max(1, currentPage - 1))}
                disabled={currentPage === 1}
              >
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <span className="text-sm text-gray-600">
                Page {currentPage} of {totalPages}
              </span>
              <Button
                aria-label="Next page"
                variant="outline"
                size="sm"
                onClick={() => handlePageChange(Math.min(totalPages, currentPage + 1))}
                disabled={currentPage === totalPages}
              >
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
