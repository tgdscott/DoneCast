import React, { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/AuthContext";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Bell } from "lucide-react";
import { makeApi } from "@/lib/apiClient";
import { useBrand } from "@/brand/BrandContext.jsx";
import { useResolvedTimezone } from "@/hooks/useResolvedTimezone";
import { formatInTimezone } from "@/lib/timezone";

function formatShort(iso, timezone) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    return formatInTimezone(
      d,
      sameDay
        ? { hour: '2-digit', minute: '2-digit' }
        : { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' },
      timezone
    );
  } catch {
    return "";
  }
}

export default function TopBar({ onSwitch, active }) {
  const { token, user } = useAuth() || {};
  const { brand } = useBrand();
  const resolvedTimezone = useResolvedTimezone(user?.timezone);
  const tabs = [
    { id: "dashboard", label: "Dashboard" },
    { id: "creator-upload", label: "New Episode" },
    // Removed direct Finalize nav to enforce flow through New Episode
    { id: "settings", label: "Settings" },
  ];

  const [notifications, setNotifications] = useState([]);
  const [open, setOpen] = useState(false);

  // Resolve avatar URL from various common fields across auth providers
  const avatarUrl = useMemo(() => {
    if (!user) return null;
    const candidates = [
      user.picture,
      user.avatar,
      user.photo_url,
      user.image_url,
      user.picture_url,
      user.profile && user.profile.picture,
      Array.isArray(user.photos) && user.photos[0] && user.photos[0].value,
      Array.isArray(user.identities) && user.identities[0] && user.identities[0].picture,
      Array.isArray(user.providerData) && user.providerData[0] && user.providerData[0].photoURL,
      user.user_metadata && user.user_metadata.avatar_url,
      user.oauth_picture,
    ].filter(Boolean);
    const pick = candidates.find((u) => typeof u === "string" && u.trim().length > 0);
    return pick || null;
  }, [user]);

  const initials = useMemo(() => {
    if (!user) return "";
    const name = [user.first_name, user.last_name].filter(Boolean).join(" ") || user.name || "";
    if (name.trim()) {
      const parts = name.trim().split(/\s+/);
      return parts.slice(0, 2).map((p) => p[0]).join("").toUpperCase();
    }
    if (user.email) return user.email.slice(0, 2).toUpperCase();
    return "";
  }, [user]);

  useEffect(() => {
    let cancelled = false;
    if (!token) { setNotifications([]); return; }
    (async () => {
      try {
        const api = makeApi(token);
        const r = await api.get("/api/notifications/");
        if (!cancelled && Array.isArray(r)) {
          setNotifications(r.sort((a, b) => new Date(b.created_at || 0) - new Date(a.created_at || 0)));
        }
      } catch {
        // ignore
      }
    })();
    return () => { cancelled = true; };
  }, [token]);

  const unread = notifications.filter((n) => !n.read_at).length;

  const markAllRead = async () => {
    if (!token) return;
    try {
      const api = makeApi(token);
      await api.post("/api/notifications/read-all");
      setNotifications((curr) => curr.map((n) => (n.read_at ? n : { ...n, read_at: new Date().toISOString() })));
    } catch {
      // ignore
    }
  };

  const markOneRead = async (id) => {
    if (!token) return;
    try {
      const api = makeApi(token);
      await api.post(`/api/notifications/${id}/read`);
      setNotifications((curr) => curr.map((n) => (n.id === id ? { ...n, read_at: new Date().toISOString() } : n)));
    } catch {
      // ignore
    }
  };

  return (
    <header className="sticky top-0 z-40 w-full border-b bg-background/80 backdrop-blur">
      <div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="size-8 rounded-xl bg-primary/15 text-primary font-semibold flex items-center justify-center">
            ++
          </div>
          <span className="font-semibold tracking-tight">{brand.shortName}</span>
        </div>
        <nav className="hidden md:flex items-center gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => onSwitch(tab.id)}
              className={
                "px-3 py-2 rounded-lg text-sm font-medium focus:outline-none focus-visible:ring " +
                (active === tab.id ? "bg-indigo-600 text-white" : "hover:bg-muted")
              }
            >
              {tab.label}
            </button>
          ))}
        </nav>
        <div className="flex items-center gap-3 relative">
          <button
            className="relative rounded-lg hover:bg-muted p-2 focus:outline-none focus-visible:ring"
            aria-label="Notifications"
            onClick={() => setOpen((v) => !v)}
            disabled={!token}
          >
            <Bell className="w-5 h-5" />
            {unread > 0 && (
              <Badge className="absolute -top-1 -right-1 h-5 w-5 rounded-full p-0 flex items-center justify-center bg-red-500 text-white text-xs">
                {unread}
              </Badge>
            )}
          </button>
          {open && (
            <div className="absolute right-12 top-10 w-80 bg-white border border-gray-200 rounded shadow-lg z-50 max-h-96 overflow-auto">
              <div className="p-3 font-semibold border-b flex items-center justify-between">
                <span>Notifications</span>
                {unread > 0 && (
                  <button className="text-xs text-blue-600 hover:underline" onClick={markAllRead}>
                    Mark all read
                  </button>
                )}
              </div>
              {notifications.length === 0 && (
                <div className="p-3 text-sm text-gray-500">No notifications</div>
              )}
              {notifications.map((n) => (
                <div key={n.id} className="p-3 text-sm border-b last:border-b-0 flex flex-col gap-1">
                  <div className="flex items-center justify-between">
                    <div className="font-medium mr-2 truncate">{n.title}</div>
                    <div className="text-[11px] text-gray-500 whitespace-nowrap">{formatShort(n.created_at, resolvedTimezone)}</div>
                  </div>
                  {n.body && <div className="text-gray-600 text-xs">{n.body}</div>}
                  {!n.read_at && (
                    <button className="text-xs text-blue-600 self-start" onClick={() => markOneRead(n.id)}>
                      Mark read
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
          <Avatar className="h-8 w-8">
            {avatarUrl && (
              <AvatarImage
                src={avatarUrl}
                alt="avatar"
                onError={(e) => {
                  // Hide broken image to reveal fallback initials
                  try { e.currentTarget.style.display = "none"; } catch {}
                }}
              />
            )}
            <AvatarFallback>{initials || ""}</AvatarFallback>
          </Avatar>
        </div>
      </div>
    </header>
  );
}
