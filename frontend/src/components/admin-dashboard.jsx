"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
  Headphones,
  Users,
  BarChart3,
  Settings as SettingsIcon,
  CreditCard,
  HelpCircle,
  Search,
  Eye,
  Edit,
  UserX,
  RotateCcw,
  LogOut,
  Shield,
  TrendingUp,
  Play,
  Calendar,
  Zap,
  AlertTriangle,
  CheckCircle,
  XCircle,
  MessageSquare,
  Plus,
  Download,
  ChevronLeft,
  ChevronRight,
  Database,
} from "lucide-react";
import React, { useState, useEffect } from "react";
import { useAuth } from "@/AuthContext";
import { makeApi, buildApiUrl } from "@/lib/apiClient";
import DbExplorer from '@/components/admin/DbExplorer.jsx';
import { useToast } from '@/hooks/use-toast';
import AdminFeatureToggles from '@/components/admin/AdminFeatureToggles.jsx';
import AdminLayoutToggle from '@/components/admin/AdminLayoutToggle.jsx';
import AdminTierEditor from '@/components/admin/AdminTierEditor.jsx';
import AdminMusicLibrary from '@/components/admin/AdminMusicLibrary.jsx';
import AdminLandingEditor from '@/components/admin/AdminLandingEditor.jsx';
import { useResolvedTimezone } from '@/hooks/useResolvedTimezone';
import { formatInTimezone } from '@/lib/timezone';

export default function AdminDashboard() {
  const { token, logout } = useAuth();
  const { toast } = useToast();
  const resolvedTimezone = useResolvedTimezone();
  const [activeTab, setActiveTab] = useState("users")
  const [searchTerm, setSearchTerm] = useState("")
  const [tierFilter, setTierFilter] = useState("all")
  const [statusFilter, setStatusFilter] = useState("all")
  const [currentPage, setCurrentPage] = useState(1)
  const [usersPerPage] = useState(10)

  const [users, setUsers] = useState([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [summary, setSummary] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [seedResult, setSeedResult] = useState(null);
  const [killingQueue, setKillingQueue] = useState(false);
  const authHeader = token ? { Authorization: `Bearer ${token}` } : {};
  // Admin settings (real backend) - currently only test_mode
  const [adminSettings, setAdminSettings] = useState(null);
  const [adminSettingsSaving, setAdminSettingsSaving] = useState(false);
  const [adminSettingsErr, setAdminSettingsErr] = useState(null);
  const [maintenanceDraft, setMaintenanceDraft] = useState('');

  const toastApiError = (e, fallback='Request failed') => {
    const msg = (e && (e.detail || e.message)) || fallback;
    try { toast({ title: 'Error', description: msg, variant: 'destructive' }); } catch {}
  };
  const handleAdminForbidden = (e, message='Access denied; returning to dashboard.') => {
    if (e && e.status === 403) {
      try { toast({ title: 'Admin access denied', description: message }); } catch {}
      try { window.location.href = '/dashboard'; } catch {}
      return true;
    }
    return false;
  };

  useEffect(() => {
    if (!token) return;
    const api = makeApi(token);
    setUsersLoading(true);
    setAnalyticsLoading(true);
    api.get('/api/admin/users/full')
      .then(setUsers)
      .catch((e)=> { if (!handleAdminForbidden(e)) toastApiError(e, 'Failed to load users'); })
      .finally(()=> setUsersLoading(false));
    api.get('/api/admin/summary')
      .then((d)=> setSummary(d))
      .catch((e)=> { if (!handleAdminForbidden(e)) toastApiError(e, 'Failed to load summary'); });
    api.get('/api/admin/metrics')
      .then((d)=> setMetrics(d))
      .catch((e) => { setMetrics(null); if (!handleAdminForbidden(e)) {/* metrics optional */} })
      .finally(()=> setAnalyticsLoading(false));
    // Load real admin settings (may 403 for non-admins)
    api.get('/api/admin/settings')
      .then(setAdminSettings)
      .catch((e) => { if (!handleAdminForbidden(e)) setAdminSettings(null); });
  }, [token]);

  useEffect(() => {
    setMaintenanceDraft(adminSettings?.maintenance_message ?? '');
  }, [adminSettings?.maintenance_message]);

  const saveAdminSettings = async (patch) => {
    if (!adminSettings) return;
    const next = { ...adminSettings, ...patch };
    setAdminSettings(next);
    setAdminSettingsSaving(true);
    setAdminSettingsErr(null);
    try {
      const api = makeApi(token);
      const data = await api.put('/api/admin/settings', next);
      setAdminSettings(data);
    } catch (e) {
      setAdminSettingsErr('Failed to save settings');
    } finally {
      setAdminSettingsSaving(false);
    }
  };

  const maintenanceMessageChanged = maintenanceDraft !== (adminSettings?.maintenance_message ?? '');
  const handleMaintenanceToggle = (checked) => {
    saveAdminSettings({ maintenance_mode: !!checked });
  };
  const handleMaintenanceMessageSave = () => {
    if (!maintenanceMessageChanged) return;
    const trimmed = maintenanceDraft.trim();
    saveAdminSettings({ maintenance_message: trimmed ? trimmed : null });
  };
  const handleMaintenanceMessageReset = () => {
    setMaintenanceDraft(adminSettings?.maintenance_message ?? '');
  };

  const runSeed = () => {
    const api = makeApi(token);
    api.post('/api/admin/seed')
      .then(data=> { setSeedResult(data); api.get('/api/admin/summary').then(setSummary); })
      .catch(()=>{});
  }

  const handleKillQueue = async () => {
    if (!token || killingQueue) return;
    const confirmed = window.confirm('Immediately stop and flush all background tasks? This cannot be undone.');
    if (!confirmed) return;
    setKillingQueue(true);
    try {
      const api = makeApi(token);
      const result = await api.post('/api/admin/tasks/kill');
      const queueLabel = result?.queue ? `Queue ${result.queue}` : 'Tasks queue';
      try {
        toast({ title: 'Queue reset', description: `${queueLabel} purged and restarted.` });
      } catch {}
    } catch (e) {
      toastApiError(e, 'Failed to kill queue');
    } finally {
      setKillingQueue(false);
    }
  };

  // Analytics data (safe defaults so UI doesn't crash while loading)
  // Backend summary currently returns: users, podcasts, templates, episodes, published_episodes
  // We now use /api/admin/metrics for DAU/signups/MRR; fall back gently if null.
  const analytics = {
    totalUsers: Number(summary?.users) || 0,
    totalEpisodes: Number(summary?.episodes) || 0,
    publishedEpisodes: Number(summary?.published_episodes) || 0,
    podcasts: Number(summary?.podcasts) || 0,
    templates: Number(summary?.templates) || 0,
    activeUsers: metrics?.daily_active_users_30d?.length ? (metrics.daily_active_users_30d[metrics.daily_active_users_30d.length - 1]?.count || 0) : 0,
    newSignups: metrics?.daily_signups_30d?.reduce((acc, d) => acc + (Number(d?.count) || 0), 0) || 0,
    revenue: metrics?.mrr_cents != null ? Math.round(metrics.mrr_cents / 100) : null, // MRR in dollars, null if unknown
    arr: metrics?.arr_cents != null ? Math.round(metrics.arr_cents / 100) : null,
    revenue30d: metrics?.revenue_30d_cents != null ? Math.round(metrics.revenue_30d_cents / 100) : null,
  };

  const num = (v) => (typeof v === 'number' && isFinite(v) ? v : 0);

  // Mock settings data
  const [settings, setSettings] = useState({
    aiShowNotes: true,
    guestAccess: false,
    maxFileSize: "500",
    autoBackup: true,
    emailNotifications: true,
  })

  const navigationItems = [
    { id: "dashboard", label: "Dashboard Overview", icon: BarChart3 },
    { id: "users", label: "Users", icon: Users },
  { id: "podcasts", label: "Podcasts", icon: Play },
    { id: "analytics", label: "Analytics", icon: TrendingUp },
  { id: "tiers", label: "Tier Editor", icon: SettingsIcon },
    { id: "music", label: "Music Library", icon: Headphones },
    { id: "landing", label: "Front Page Content", icon: MessageSquare },
    { id: "db", label: "DB Explorer", icon: Database },
    { id: "settings", label: "Settings", icon: SettingsIcon },
    { id: "billing", label: "Billing", icon: CreditCard },
    { id: "help", label: "Help & Docs", icon: HelpCircle },
  ]

  // Filter users based on search + tier + status
  const filteredUsers = users.filter((user) => {
    const q = searchTerm.trim().toLowerCase();
    const email = (user.email || '').toLowerCase();
    const tier = (user.tier || '').toLowerCase();
    const matchesSearch = !q || email.includes(q) || tier.includes(q);
    const matchesTier = (tierFilter === 'all') || (tier === tierFilter);
    const matchesStatus = (statusFilter === 'all')
      || (statusFilter === 'active' && !!user.is_active)
      || ((statusFilter === 'inactive' || statusFilter === 'suspended') && !user.is_active);
    return matchesSearch && matchesTier && matchesStatus;
  })

  const [savingIds, setSavingIds] = useState(new Set());
  const [saveErrors, setSaveErrors] = useState({});
  // Local edit buffer for date inputs so we don't PATCH on every keystroke
  const [editingDates, setEditingDates] = useState({});

  const updateUser = async (id, payload) => {
    setSavingIds(prev => new Set([...prev, id]));
    setSaveErrors(e => ({...e, [id]: null}));
    try {
      const api = makeApi(token);
      const updated = await api.patch(`/api/admin/users/${id}`, payload);
      setUsers(u => u.map(x => x.id === id ? updated : x));
    } catch(e) {
      setSaveErrors(errs => ({...errs, [id]: e.message || 'Network error'}));
    } finally {
      setSavingIds(prev => { const n = new Set(prev); n.delete(id); return n; });
    }
  }
  const formatDateInput = (iso) => iso ? iso.slice(0,10) : '';
  // Validate ISO (YYYY-MM-DD)
  const isValidDateString = (s) => /^(\d{4})-(\d{2})-(\d{2})$/.test(s);
  // Convert ISO -> US (MM/DD/YYYY)
  const isoToUS = (iso) => {
    if (!iso || !isValidDateString(iso.slice(0,10))) return '';
    const y = iso.slice(0,4), m = iso.slice(5,7), d = iso.slice(8,10);
    return `${m}/${d}/${y}`;
  };
  // Convert US -> ISO; returns null if invalid
  const usToISO = (us) => {
    const m = us.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if(!m) return null;
    let [_, mm, dd, yyyy] = m;
    if(mm.length===1) mm = '0'+mm;
    if(dd.length===1) dd = '0'+dd;
    const iso = `${yyyy}-${mm}-${dd}`;
    if(!isValidDateString(iso)) return null;
    return iso;
  };
  const isoToDateObj = (iso) => new Date(iso + 'T00:00:00Z');
  const dateObjToISO = (d) => d.toISOString().slice(0,10);
  const addMonths = (d, months) => { const nd = new Date(d.getTime()); const day = nd.getUTCDate(); nd.setUTCDate(1); nd.setUTCMonth(nd.getUTCMonth()+months); const mlen = new Date(Date.UTC(nd.getUTCFullYear(), nd.getUTCMonth()+1,0)).getUTCDate(); nd.setUTCDate(Math.min(day, mlen)); return nd; };
  const addYears = (d, years) => { const nd = new Date(d.getTime()); nd.setUTCFullYear(nd.getUTCFullYear()+years); return nd; };
  const deriveBaseISO = (user) => {
    const pendingUS = editingDates[user.id];
    if (pendingUS) {
      const iso = usToISO(pendingUS);
      if (iso) return iso;
    }
    return user.subscription_expires_at || new Date().toISOString().slice(0,10);
  };

  const handleDateInputChange = (userId, value) => {
    setEditingDates(prev => ({ ...prev, [userId]: value }));
    // If full YYYY-MM-DD entered, auto-save
    if (value && value.length === 10) {
      updateUser(userId, { subscription_expires_at: value });
      // Clear local buffer after save so value derives from canonical user state
      setEditingDates(prev => { const n = { ...prev }; delete n[userId]; return n; });
    }
  };

  const handleDateBlur = (userId) => {
    const value = editingDates[userId];
    if (value === undefined) return; // nothing to do
    if (value === '') {
      updateUser(userId, { subscription_expires_at: '' });
    } else if (value.length === 10) {
      updateUser(userId, { subscription_expires_at: value });
    }
    setEditingDates(prev => { const n = { ...prev }; delete n[userId]; return n; });
  };

  // Pagination
  const indexOfLastUser = currentPage * usersPerPage
  const indexOfFirstUser = indexOfLastUser - usersPerPage
  const currentUsers = filteredUsers.slice(indexOfFirstUser, indexOfLastUser)
  const totalPages = Math.ceil(filteredUsers.length / usersPerPage)

  const getStatusBadge = (status) => {
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

  const getTierBadge = (tier) => {
  const t = (tier || '').toLowerCase();
  if (t === 'pro') return <Badge className="bg-purple-100 text-purple-800">Pro</Badge>;
  if (t === 'creator') return <Badge className="bg-blue-100 text-blue-800">Creator</Badge>;
  if (t === 'free') return <Badge className="bg-gray-100 text-gray-800">Free</Badge>;
  if (t === 'unlimited') return <Badge className="bg-yellow-100 text-yellow-800">Unlimited</Badge>;
  return <Badge variant="secondary">{tier || '—'}</Badge>;
  }

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
                {activeTab === "tiers" && "Define features per tier (placeholder, not enforced yet)"}
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
            {activeTab === 'dashboard' && analytics && (
              <div className="grid md:grid-cols-3 gap-6 mb-8">
                <Card><CardContent className="p-4"><div className="text-sm text-gray-500">Users</div><div className="text-2xl font-bold">{analytics.totalUsers}</div></CardContent></Card>
                <Card><CardContent className="p-4"><div className="text-sm text-gray-500">Episodes</div><div className="text-2xl font-bold">{analytics.totalEpisodes}</div></CardContent></Card>
                <Card><CardContent className="p-4"><div className="text-sm text-gray-500">Published</div><div className="text-2xl font-bold">{analytics.publishedEpisodes}</div></CardContent></Card>
              </div>
            )}
            {activeTab === 'dashboard' && (
              <Button size="sm" variant="outline" onClick={runSeed}>Seed Demo Data</Button>
            )}
            {seedResult && activeTab === 'dashboard' && (
              <div className="text-xs text-green-700 mt-2">Seeded podcast {seedResult.podcast_id.slice(0,8)} / template {seedResult.template_id.slice(0,8)}</div>
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
            <div className="space-y-6">
              {/* Enhanced Search and Bulk Actions */}
              <Card className="border-0 shadow-sm bg-white">
                <CardContent className="p-6">
                  <div
                    className="flex flex-col lg:flex-row gap-4 items-start lg:items-center justify-between">
                    <div
                      className="flex-1 space-y-4 lg:space-y-0 lg:flex lg:items-center lg:space-x-4">
                      <div className="relative flex-1 max-w-md">
                        <Search
                          className="absolute left-3 top-1/2 transform -translate-y-1/2 text-gray-400 w-4 h-4" />
                        <Input
                          placeholder="Search users by name, email, or tier..."
                          className="pl-10"
                          value={searchTerm}
                          onChange={(e) => setSearchTerm(e.target.value)} />
                      </div>
                      <div className="flex items-center space-x-3">
            <Select value={tierFilter} onValueChange={setTierFilter}>
                          <SelectTrigger className="w-32" aria-label="Filter by tier">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="all">All Tiers</SelectItem>
                            <SelectItem value="pro">Pro</SelectItem>
                            <SelectItem value="creator">Creator</SelectItem>
                            <SelectItem value="free">Free</SelectItem>
              <SelectItem value="unlimited">Unlimited</SelectItem>
                          </SelectContent>
                        </Select>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
                          <SelectTrigger className="w-32" aria-label="Filter by status">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="all">All Status</SelectItem>
                            <SelectItem value="active">Active</SelectItem>
                            <SelectItem value="inactive">Inactive</SelectItem>
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

              {/* Users Table */}
              <Card className="border-0 shadow-sm bg-white">
                <CardContent className="p-0">
                  {!usersLoading ? (
                  <Table>
                    <TableHeader>
                      <TableRow className="border-b border-gray-200">
                        <TableHead className="font-semibold text-gray-700">User</TableHead>
                        <TableHead className="font-semibold text-gray-700">Email</TableHead>
                        <TableHead className="font-semibold text-gray-700">Tier</TableHead>
                        <TableHead className="font-semibold text-gray-700">Status</TableHead>
                        <TableHead className="font-semibold text-gray-700">Episodes</TableHead>
                        <TableHead className="font-semibold text-gray-700">Last Login</TableHead>
                        <TableHead className="font-semibold text-gray-700">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {currentUsers.map(user => {
                        const rawName = user?.email || user?.first_name || user?.last_name || 'User';
                        const safeName = String(rawName || 'User');
                        const emailPart = safeName.includes('@') ? safeName.split('@')[0] : safeName;
                        const initials = (emailPart || 'U').slice(0, 2).toUpperCase();
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
                                  <div className="text-sm text-gray-500">Created {(user.created_at||'').toString().slice(0,10)}</div>
                                </div>
                              </div>
                            </TableCell>
                            <TableCell className="text-gray-600">{user.email}</TableCell>
                            <TableCell>{getTierBadge(user.tier || 'free')}</TableCell>
                            <TableCell>{getStatusBadge(user.is_active ? 'Active' : 'Inactive')}</TableCell>
                            <TableCell className="text-gray-600">{user.episode_count}</TableCell>
                            <TableCell className="text-gray-600">{user.last_activity ? user.last_activity.slice(0,10) : '—'}</TableCell>
                            <TableCell>
                              <div className="flex items-center space-x-2">
                <Select defaultValue={user.tier || 'free'} onValueChange={val => updateUser(user.id,{tier: val})} disabled={savingIds.has(user.id)}>
                                  <SelectTrigger className="w-24 h-8 text-xs" aria-label={`Tier for ${displayName}`}><SelectValue /></SelectTrigger>
                                  <SelectContent>
                                    <SelectItem value="free">Free</SelectItem>
                                    <SelectItem value="creator">Creator</SelectItem>
                                    <SelectItem value="pro">Pro</SelectItem>
                  <SelectItem value="unlimited">Unlimited</SelectItem>
                                  </SelectContent>
                                </Select>
                                <Switch aria-label={`Active status for ${displayName}`} checked={!!user.is_active} disabled={savingIds.has(user.id)} onCheckedChange={v => updateUser(user.id,{is_active: v})} />
                                <input
                                  aria-label="Subscription expiry date"
                                  type="text"
                                  inputMode="numeric"
                                  className={`border rounded px-2 py-1 text-xs w-28 ${editingDates[user.id] && editingDates[user.id].length>0 && usToISO(editingDates[user.id])===null ? 'border-red-400' : ''}`}
                                  value={editingDates[user.id] ?? isoToUS(user.subscription_expires_at)}
                                  onChange={(e)=> {
                                    const raw = e.target.value.replace(/[^0-9/]/g,'');
                                    // Auto-add slashes as typing MMDDYYYY (only digits)
                                    let v = raw;
                                    if (/^\d{3,}$/.test(raw) && raw.indexOf('/')===-1) {
                                      if (raw.length >= 2) v = raw.slice(0,2) + '/' + raw.slice(2);
                                      if (raw.length >= 4) v = v.slice(0,5) + '/' + v.slice(5);
                                    }
                                    // Restrict length to 10 (MM/DD/YYYY)
                                    v = v.slice(0,10);
                                    setEditingDates(prev => ({ ...prev, [user.id]: v }));
                                  }}
                                  onBlur={()=> {
                                    const v = editingDates[user.id];
                                    if (v === undefined) return; // no edit
                                    if (v === '') {
                                      updateUser(user.id,{ subscription_expires_at: '' });
                                    } else {
                                      const iso = usToISO(v);
                                      if (iso) {
                                        updateUser(user.id,{ subscription_expires_at: iso });
                                      }
                                      // If invalid, just revert silently
                                    }
                                    setEditingDates(prev => { const n={...prev}; delete n[user.id]; return n; });
                                  }}
                                  disabled={savingIds.has(user.id)}
                                  placeholder="MM/DD/YYYY"
                                  title="Subscription expiry (MM/DD/YYYY)"
                                />
                                <div className="flex space-x-1">
                                  <button
                                    type="button"
                                    className="text-[10px] px-1 py-0.5 border rounded bg-gray-100 hover:bg-gray-200"
                                    disabled={savingIds.has(user.id)}
                                    onClick={()=>{
                                      const baseIso = deriveBaseISO(user);
                                      const d = addMonths(isoToDateObj(baseIso),1);
                                      const iso = dateObjToISO(d);
                                      // Optimistic local update
                                      setEditingDates(prev => ({...prev, [user.id]: isoToUS(iso)}));
                                      updateUser(user.id,{ subscription_expires_at: iso });
                                    }}>+1M</button>
                                  <button
                                    type="button"
                                    className="text-[10px] px-1 py-0.5 border rounded bg-gray-100 hover:bg-gray-200"
                                    disabled={savingIds.has(user.id)}
                                    onClick={()=>{
                                      const baseIso = deriveBaseISO(user);
                                      const d = addYears(isoToDateObj(baseIso),1);
                                      const iso = dateObjToISO(d);
                                      setEditingDates(prev => ({...prev, [user.id]: isoToUS(iso)}));
                                      updateUser(user.id,{ subscription_expires_at: iso });
                                    }}>+1Y</button>
                                  <button
                                    type="button"
                                    className="text-[10px] px-1 py-0.5 border rounded bg-gray-100 hover:bg-gray-200"
                                    disabled={savingIds.has(user.id)}
                                    onClick={()=>{
                                      const iso = new Date().toISOString().slice(0,10);
                                      setEditingDates(prev => ({...prev, [user.id]: isoToUS(iso)}));
                                      updateUser(user.id,{ subscription_expires_at: iso });
                                    }}>Today</button>
                                  <button
                                    type="button"
                                    className="text-[10px] px-1 py-0.5 border rounded bg-gray-100 hover:bg-gray-200"
                                    disabled={savingIds.has(user.id)}
                                    onClick={()=>{
                                      setEditingDates(prev => ({...prev, [user.id]: ''}));
                                      updateUser(user.id,{ subscription_expires_at: '' });
                                    }}>Clear</button>
                                </div>
                                {savingIds.has(user.id) && <span className="text-[10px] text-gray-400">Saving…</span>}
                                {saveErrors[user.id] && <span className="text-[10px] text-red-500" title={saveErrors[user.id]}>Err</span>}
                              </div>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                  ) : (
                    <div className="p-4 space-y-2">
                      {Array.from({ length: usersPerPage }).map((_, i) => (
                        <div key={i} className="h-10 bg-gray-100 rounded animate-pulse" />
                      ))}
                    </div>
                  )}

                  {/* Pagination */}
                      {activeTab === 'tiers' && (
                        <AdminTierEditor />
                      )}
                  <div
                    className="flex items-center justify-between px-6 py-4 border-t border-gray-200">
                    <div className="text-sm text-gray-600">
                      Showing {indexOfFirstUser + 1} to {Math.min(indexOfLastUser, filteredUsers.length)} of{" "}
                      {filteredUsers.length} users
                    </div>
                    <div className="flex items-center space-x-2">
                      <Button
                        aria-label="Previous page"
                        variant="outline"
                        size="sm"
                        onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                        disabled={currentPage === 1}>
                        <ChevronLeft className="w-4 h-4" />
                      </Button>
                      <span className="text-sm text-gray-600">
                        Page {currentPage} of {totalPages}
                      </span>
                      <Button
                        aria-label="Next page"
                        variant="outline"
                        size="sm"
                        onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
                        disabled={currentPage === totalPages}>
                        <ChevronRight className="w-4 h-4" />
                      </Button>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>
          )}
          {activeTab === 'music' && (
            <div className="space-y-4">
              <AdminMusicLibrary />
            </div>
          )}

          {activeTab === 'landing' && (
            <div className="space-y-4">
              <AdminLandingEditor token={token} />
            </div>
          )}

          {/* DB Explorer Tab */}
          {activeTab === "db" && (
            <div className="space-y-4">
              <DbExplorer />
            </div>
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
            <div className="space-y-6">
              {/* Time Period Selector */}
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-semibold" style={{ color: "#2C3E50" }}>
                    Platform Analytics
                  </h3>
                  <p className="text-gray-600">Comprehensive insights into platform performance</p>
                </div>
                <Select defaultValue="30d">
                  <SelectTrigger className="w-40">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="7d">Last 7 days</SelectItem>
                    <SelectItem value="30d">Last 30 days</SelectItem>
                    <SelectItem value="90d">Last 90 days</SelectItem>
                    <SelectItem value="1y">Last year</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {/* Enhanced Key Metrics */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                {!analyticsLoading ? (
                  <>
                <Card
                  className="border-0 shadow-sm hover:shadow-md transition-all"
                  style={{ backgroundColor: "#ECF0F1" }}>
                  <CardContent className="p-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-gray-600">Total Active Users</p>
                        <p className="text-3xl font-bold" style={{ color: "#2C3E50" }}>
                          {num(analytics.activeUsers).toLocaleString()}
                        </p>
                        <div className="flex items-center mt-2 text-sm">
                          <TrendingUp className="w-4 h-4 text-green-600 mr-1" />
                          <span className="text-green-600">+12% from last month</span>
                        </div>
                      </div>
                      <div className="p-3 rounded-full bg-blue-100">
                        <Users className="w-8 h-8 text-blue-600" />
                      </div>
                    </div>
                    <div className="mt-4 pt-4 border-t border-gray-200">
                      <div className="text-xs text-gray-600">Latest daily active users (DAU) over last 30 days</div>
                    </div>
                  </CardContent>
                </Card>

                <Card
                  className="border-0 shadow-sm hover:shadow-md transition-all"
                  style={{ backgroundColor: "#ECF0F1" }}>
                  <CardContent className="p-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-gray-600">New Sign-ups (30 Days)</p>
                        <p className="text-3xl font-bold" style={{ color: "#2C3E50" }}>
                          {num(analytics.newSignups).toLocaleString()}
                        </p>
                        <div className="flex items-center mt-2 text-sm">
                          <TrendingUp className="w-4 h-4 text-green-600 mr-1" />
                          <span className="text-green-600">+8% from last month</span>
                        </div>
                      </div>
                      <div className="p-3 rounded-full bg-green-100">
                        <Calendar className="w-8 h-8 text-green-600" />
                      </div>
                    </div>
                    <div className="mt-4 pt-4 border-t border-gray-200">
                      <div className="text-xs text-gray-600">
                        Daily average: {Math.round(analytics.newSignups / 30)} users
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card
                  className="border-0 shadow-sm hover:shadow-md transition-all"
                  style={{ backgroundColor: "#ECF0F1" }}>
                  <CardContent className="p-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-gray-600">Total Episodes Published</p>
                        <p className="text-3xl font-bold" style={{ color: "#2C3E50" }}>
                          {analytics.totalEpisodes.toLocaleString()}
                        </p>
                        <div className="flex items-center mt-2 text-sm">
                          <TrendingUp className="w-4 h-4 text-green-600 mr-1" />
                          <span className="text-green-600">+23% from last month</span>
                        </div>
                      </div>
                      <div className="p-3 rounded-full bg-purple-100">
                        <Play className="w-8 h-8 text-purple-600" />
                      </div>
                    </div>
                    <div className="mt-4 pt-4 border-t border-gray-200">
                      <div className="text-xs text-gray-600">This month: 1,247 episodes</div>
                    </div>
                  </CardContent>
                </Card>

                <Card
                  className="border-0 shadow-sm hover:shadow-md transition-all"
                  style={{ backgroundColor: "#ECF0F1" }}>
                  <CardContent className="p-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-gray-600">Revenue (MRR)</p>
                            <p className="text-3xl font-bold" style={{ color: "#2C3E50" }}>
                              {analytics.revenue != null ? (
                                <>${Number(analytics.revenue).toLocaleString()}</>
                              ) : (
                                <Badge variant="secondary">—</Badge>
                              )}
                            </p>
                        <div className="flex items-center mt-2 text-sm">
                          <TrendingUp className="w-4 h-4 text-green-600 mr-1" />
                          <span className="text-green-600">+15% from last month</span>
                        </div>
                      </div>
                      <div className="p-3 rounded-full bg-green-100">
                        <TrendingUp className="w-8 h-8 text-green-600" />
                      </div>
                    </div>
                    <div className="mt-4 pt-4 border-t border-gray-200">
                          <div className="text-xs text-gray-600">
                            ARPU: {analytics.revenue != null && analytics.totalUsers > 0 ? (
                              <>${(Number(analytics.revenue) / Number(analytics.totalUsers)).toFixed(2)}</>
                            ) : (
                              <Badge variant="secondary">—</Badge>
                            )}
                          </div>
                    </div>
                  </CardContent>
                </Card>
                </>
                ) : (
                  <>
                    {Array.from({ length: 4 }).map((_, i) => (
                      <Card key={i} className="border-0 shadow-sm">
                        <CardContent className="p-6">
                          <div className="h-20 bg-gray-100 rounded animate-pulse" />
                        </CardContent>
                      </Card>
                    ))}
                  </>
                )}
              </div>

              {/* Enhanced Charts Section */}
              <div className="grid lg:grid-cols-2 gap-6">
                {!analyticsLoading ? (
                  <>
                <Card className="border-0 shadow-sm bg-white">
                  <CardHeader>
                    <CardTitle
                      className="flex items-center justify-between"
                      style={{ color: "#2C3E50" }}>
                      Daily Signups (30 days)
                      <Button variant="ghost" size="sm" className="text-blue-600">
                        <Download className="w-4 h-4 mr-1" />
                        Export
                      </Button>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="h-64 flex items-end justify-between space-x-1 p-4 bg-gray-50 rounded-lg">
                      {(metrics?.daily_signups_30d || []).map((d, idx, arr) => {
                        const max = Math.max(1, ...arr.map(x => Number(x.count) || 0));
                        const h = Math.round(((Number(d.count) || 0) / max) * 200);
                        return (
                          <div key={idx} className="flex flex-col items-center">
                            <div className="w-3 bg-blue-500 rounded-t" style={{ height: `${h}px` }}></div>
                            <span className="text-[10px] text-gray-500 mt-1">{String(d.date).slice(5)}</span>
                          </div>
                        );
                      })}
                    </div>
                    <div className="mt-4 flex items-center justify-between text-sm text-gray-600">
                      <span>Total signups: {num(analytics.newSignups).toLocaleString()}</span>
                      <span className="text-green-600">30 days</span>
                    </div>
                  </CardContent>
                </Card>

                <Card className="border-0 shadow-sm bg-white">
                  <CardHeader>
                    <CardTitle
                      className="flex items-center justify-between"
                      style={{ color: "#2C3E50" }}>
                      Daily Active Users (30 days)
                      <Button variant="ghost" size="sm" className="text-blue-600">
                        <Download className="w-4 h-4 mr-1" />
                        Export
                      </Button>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="h-64 flex items-end justify-between space-x-1 p-4 bg-gray-50 rounded-lg">
                      {(metrics?.daily_active_users_30d || []).map((d, idx, arr) => {
                        const max = Math.max(1, ...arr.map(x => Number(x.count) || 0));
                        const h = Math.round(((Number(d.count) || 0) / max) * 200);
                        return (
                          <div key={idx} className="flex flex-col items-center">
                            <div className="w-3 bg-purple-500 rounded-t" style={{ height: `${h}px` }}></div>
                            <span className="text-[10px] text-gray-500 mt-1">{String(d.date).slice(5)}</span>
                          </div>
                        );
                      })}
                    </div>
                    <div className="mt-4 flex items-center justify-between text-sm text-gray-600">
                      <span>Latest DAU: {num(analytics.activeUsers).toLocaleString()}</span>
                      <span className="text-green-600">30 days</span>
                    </div>
                  </CardContent>
                </Card>
                </>
                ) : (
                  <>
                    {Array.from({ length: 2 }).map((_, i) => (
                      <Card key={i} className="border-0 shadow-sm bg-white">
                        <CardContent className="p-6">
                          <div className="h-64 bg-gray-100 rounded animate-pulse" />
                        </CardContent>
                      </Card>
                    ))}
                  </>
                )}
              </div>

              {/* Additional Analytics */}
              <div className="grid lg:grid-cols-3 gap-6">
                <Card className="border-0 shadow-sm bg-white">
                  <CardHeader>
                    <CardTitle style={{ color: "#2C3E50" }}>Top Performing Content</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {[
                      { title: "Tech Talk Weekly", downloads: "12.4K", growth: "+23%" },
                      { title: "Mindful Moments", downloads: "8.7K", growth: "+18%" },
                      { title: "Business Insights", downloads: "6.2K", growth: "+15%" },
                    ].map((podcast, index) => (
                      <div key={index} className="flex items-center justify-between">
                        <div>
                          <p className="font-medium text-gray-800">{podcast.title}</p>
                          <p className="text-sm text-gray-600">{podcast.downloads} downloads</p>
                        </div>
                        <Badge className="bg-green-100 text-green-800">{podcast.growth}</Badge>
                      </div>
                    ))}
                  </CardContent>
                </Card>

                <Card className="border-0 shadow-sm bg-white">
                  <CardHeader>
                    <CardTitle style={{ color: "#2C3E50" }}>User Engagement</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="space-y-3">
                      <div>
                        <div className="flex justify-between text-sm mb-1">
                          <span>Daily Active Users</span>
                          <span className="font-medium">78%</span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2">
                          <div className="bg-blue-500 h-2 rounded-full" style={{ width: "78%" }}></div>
                        </div>
                      </div>
                      <div>
                        <div className="flex justify-between text-sm mb-1">
                          <span>Weekly Retention</span>
                          <span className="font-medium">65%</span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2">
                          <div className="bg-green-500 h-2 rounded-full" style={{ width: "65%" }}></div>
                        </div>
                      </div>
                      <div>
                        <div className="flex justify-between text-sm mb-1">
                          <span>Monthly Retention</span>
                          <span className="font-medium">42%</span>
                        </div>
                        <div className="w-full bg-gray-200 rounded-full h-2">
                          <div className="bg-orange-500 h-2 rounded-full" style={{ width: "42%" }}></div>
                        </div>
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card className="border-0 shadow-sm bg-white">
                  <CardHeader>
                    <CardTitle style={{ color: "#2C3E50" }}>Platform Health</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <div className="text-center">
                      <div className="text-3xl font-bold text-green-600 mb-2">98.7%</div>
                      <p className="text-sm text-gray-600">Uptime (30 days)</p>
                    </div>
                    <div className="space-y-2 text-sm">
                      <div className="flex justify-between">
                        <span>Avg Response Time</span>
                        <span className="font-medium">245ms</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Error Rate</span>
                        <span className="font-medium text-green-600">0.03%</span>
                      </div>
                      <div className="flex justify-between">
                        <span>Active Connections</span>
                        <span className="font-medium">1,247</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>
          )}

          {/* Enhanced Dashboard Overview Tab */}
          {activeTab === "dashboard" && (
            <div className="space-y-6">
              {/* Quick Stats */}
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                <Card className="border-0 shadow-sm bg-white hover:shadow-md transition-all">
                  <CardContent className="p-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-gray-600">Active Users</p>
                        <p className="text-2xl font-bold" style={{ color: "#2C3E50" }}>
                          {num(analytics.activeUsers).toLocaleString()}
                        </p>
                        <div className="flex items-center mt-1 text-sm text-green-600">
                          <TrendingUp className="w-3 h-3 mr-1" />
                          +12% vs last month
                        </div>
                      </div>
                      <div className="p-3 rounded-full bg-blue-100">
                        <Users className="w-6 h-6 text-blue-600" />
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card className="border-0 shadow-sm bg-white hover:shadow-md transition-all">
                  <CardContent className="p-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-gray-600">Monthly Revenue</p>
                        <p className="text-2xl font-bold" style={{ color: "#2C3E50" }}>
                          {analytics.revenue != null ? (
                            <>${num(analytics.revenue).toLocaleString()}</>
                          ) : (
                            <Badge variant="secondary">—</Badge>
                          )}
                        </p>
                        <div className="flex items-center mt-1 text-sm text-green-600">
                          <TrendingUp className="w-3 h-3 mr-1" />
                          +18% vs last month
                        </div>
                      </div>
                      <div className="p-3 rounded-full bg-green-100">
                        <TrendingUp className="w-6 h-6 text-green-600" />
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card className="border-0 shadow-sm bg-white hover:shadow-md transition-all">
                  <CardContent className="p-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-gray-600">Episodes Today</p>
                        <p className="text-2xl font-bold" style={{ color: "#2C3E50" }}>
                          47
                        </p>
                        <div className="flex items-center mt-1 text-sm text-blue-600">
                          <Play className="w-3 h-3 mr-1" />
                          23 published, 24 drafts
                        </div>
                      </div>
                      <div className="p-3 rounded-full bg-purple-100">
                        <Play className="w-6 h-6 text-purple-600" />
                      </div>
                    </div>
                  </CardContent>
                </Card>

                <Card className="border-0 shadow-sm bg-white hover:shadow-md transition-all">
                  <CardContent className="p-6">
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm font-medium text-gray-600">System Health</p>
                        <p className="text-2xl font-bold text-green-600">98.7%</p>
                        <div className="flex items-center mt-1 text-sm text-green-600">
                          <CheckCircle className="w-3 h-3 mr-1" />
                          All systems operational
                        </div>
                      </div>
                      <div className="p-3 rounded-full bg-green-100">
                        <CheckCircle className="w-6 h-6 text-green-600" />
                      </div>
                    </div>
                  </CardContent>
                </Card>
              </div>

              {/* Recent Activity and Quick Actions */}
              <div className="grid lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2">
                  <Card className="border-0 shadow-sm bg-white">
                    <CardHeader>
                      <CardTitle
                        className="flex items-center justify-between"
                        style={{ color: "#2C3E50" }}>
                        Recent Platform Activity
                        <Button variant="ghost" size="sm" className="text-blue-600">
                          View All
                        </Button>
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {[
                        {
                          icon: Users,
                          color: "text-blue-600",
                          bg: "bg-blue-100",
                          title: "New user registration spike",
                          description: "23 new users signed up in the last hour",
                          time: "5 minutes ago",
                        },
                        {
                          icon: AlertTriangle,
                          color: "text-orange-600",
                          bg: "bg-orange-100",
                          title: "High server load detected",
                          description: "CPU usage at 78% - monitoring closely",
                          time: "12 minutes ago",
                        },
                        {
                          icon: Play,
                          color: "text-purple-600",
                          bg: "bg-purple-100",
                          title: "Episode milestone reached",
                          description: "Platform just hit 15,000 total episodes published",
                          time: "1 hour ago",
                        },
                        {
                          icon: TrendingUp,
                          color: "text-green-600",
                          bg: "bg-green-100",
                          title: "Revenue target exceeded",
                          description: "Monthly revenue goal reached 5 days early",
                          time: "2 hours ago",
                        },
                      ].map((activity, index) => (
                        <div
                          key={index}
                          className="flex items-start space-x-4 p-4 rounded-lg hover:bg-gray-50 transition-all">
                          <div className={`p-2 rounded-full ${activity.bg}`}>
                            <activity.icon className={`w-4 h-4 ${activity.color}`} />
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="font-medium text-gray-800">{activity.title}</p>
                            <p className="text-sm text-gray-600">{activity.description}</p>
                            <p className="text-xs text-gray-500 mt-1">{activity.time}</p>
                          </div>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                </div>

                <div className="space-y-6">
                  {/* Quick Actions */}
                  <Card className="border-0 shadow-sm bg-white">
                    <CardHeader>
                      <CardTitle style={{ color: "#2C3E50" }}>Quick Actions</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      <Button
                        variant="destructive"
                        className="w-full justify-start"
                        onClick={handleKillQueue}
                        disabled={killingQueue}>
                        <AlertTriangle className="w-4 h-4 mr-3" />
                        {killingQueue ? 'Killing Tasks…' : 'KILL Tasks Queue'}
                      </Button>
                      <Button variant="outline" className="w-full justify-start bg-transparent">
                        <MessageSquare className="w-4 h-4 mr-3" />
                        Send Platform Announcement
                      </Button>
                      <Button variant="outline" className="w-full justify-start bg-transparent">
                        <Download className="w-4 h-4 mr-3" />
                        Generate Monthly Report
                      </Button>
                      <Button variant="outline" className="w-full justify-start bg-transparent">
                        <SettingsIcon className="w-4 h-4 mr-3" />
                        System Maintenance
                      </Button>
                      <Button variant="outline" className="w-full justify-start bg-transparent">
                        <Users className="w-4 h-4 mr-3" />
                        User Support Queue
                      </Button>
                    </CardContent>
                  </Card>

                  {/* System Status */}
                  <Card className="border-0 shadow-sm" style={{ backgroundColor: "#ECF0F1" }}>
                    <CardHeader>
                      <CardTitle style={{ color: "#2C3E50" }}>System Status</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {[
                        { service: "API Gateway", status: "operational", color: "text-green-600", icon: CheckCircle },
                        { service: "Database", status: "operational", color: "text-green-600", icon: CheckCircle },
                        { service: "AI Services", status: "operational", color: "text-green-600", icon: CheckCircle },
                        { service: "File Storage", status: "degraded", color: "text-orange-600", icon: AlertTriangle },
                        { service: "Email Service", status: "down", color: "text-red-600", icon: XCircle },
                      ].map((item, index) => (
                        <div key={index} className="flex items-center justify-between">
                          <div className="flex items-center space-x-3">
                            <item.icon className={`w-4 h-4 ${item.color}`} />
                            <span className="text-sm font-medium text-gray-700">{item.service}</span>
                          </div>
                          <Badge
                            className={`text-xs ${
                              item.status === "operational"
                                ? "bg-green-100 text-green-800"
                                : item.status === "degraded"
                                  ? "bg-orange-100 text-orange-800"
                                  : "bg-red-100 text-red-800"
                            }`}>
                            {item.status}
                          </Badge>
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                </div>
              </div>
            </div>
          )}

          {/* Settings Tab */}
          {activeTab === "settings" && (
            <div className="space-y-6">
              {/* Feature Toggles */}
              <Card className="border-0 shadow-sm bg-white">
                <CardHeader>
                  <CardTitle style={{ color: "#2C3E50" }}>Platform Features</CardTitle>
                  <p className="text-gray-600">Enable or disable platform-wide features</p>
                </CardHeader>
                <CardContent className="space-y-6">
                  {adminSettings ? (
                    <AdminFeatureToggles token={token} initial={adminSettings} onSaved={(s)=>setAdminSettings(s)} />
                  ) : (
                    <p className="text-sm text-gray-500">Loading admin settings…</p>
                  )}

                  <AdminLayoutToggle />

                  <div className="flex items-center justify-between">
                    <div>
                      <Label className="text-base font-medium text-gray-700">Enable AI Show Notes (Beta)</Label>
                      <p className="text-sm text-gray-500 mt-1">
                        Allow users to generate show notes automatically using AI
                      </p>
                    </div>
                    <Switch
                      aria-label="Enable AI Show Notes"
                      checked={settings.aiShowNotes}
                      onCheckedChange={(checked) => setSettings({ ...settings, aiShowNotes: checked })} />
                  </div>

                  <div className="flex items-center justify-between">
                    <div>
                      <Label className="text-base font-medium text-gray-700">Allow Guest Access to Podcasts</Label>
                      <p className="text-sm text-gray-500 mt-1">
                        Enable non-registered users to listen to public podcasts
                      </p>
                    </div>
                    <Switch
                      aria-label="Allow guest access"
                      checked={settings.guestAccess}
                      onCheckedChange={(checked) => setSettings({ ...settings, guestAccess: checked })} />
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
                        onCheckedChange={handleMaintenanceToggle} />
                    </div>
                  </div>

                  <div className="mt-3 space-y-2">
                    <Label className="text-sm font-medium text-gray-700">Maintenance Message</Label>
                    <Textarea
                      value={maintenanceDraft}
                      onChange={(e) => setMaintenanceDraft(e.target.value)}
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
                          disabled={!maintenanceMessageChanged || adminSettingsSaving}>
                          Reset
                        </Button>
                        <Button
                          size="sm"
                          onClick={handleMaintenanceMessageSave}
                          disabled={!maintenanceMessageChanged || adminSettingsSaving}>
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
                      onCheckedChange={(checked) => setSettings({ ...settings, autoBackup: checked })} />
                  </div>
                </CardContent>
              </Card>

              {/* API Configuration - moved Max Upload to AdminFeatureToggles above */}

              {/* System Status */}
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
          )}

          {/* Other tabs placeholder */}
          {!["users", "analytics", "settings", "dashboard", "music"].includes(activeTab) && (
            <div className="text-center py-12">
              <h3 className="text-xl font-semibold text-gray-600 mb-2">
                {navigationItems.find((item) => item.id === activeTab)?.label} Coming Soon
              </h3>
              <p className="text-gray-500">This section is under development and will be available soon.</p>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function AdminPodcastsTab() {
  const { token } = useAuth();
  const { toast } = useToast();
  const [rows, setRows] = React.useState([]);
  const [total, setTotal] = React.useState(0);
  const [limit, setLimit] = React.useState(25);
  const [offset, setOffset] = React.useState(0);
  const [loading, setLoading] = React.useState(false);
  const [qOwner, setQOwner] = React.useState("");

  const load = async (newOffset=0) => {
    if (!token) return;
    setLoading(true);
    try {
      const api = makeApi(token);
      const qs = new URLSearchParams({ limit: String(limit), offset: String(newOffset), ...(qOwner ? { owner_email: qOwner } : {}) });
      const data = await api.get(`/api/admin/podcasts?${qs.toString()}`);
      setRows(data.items || []);
      setTotal(Number(data.total) || 0);
      setOffset(Number(data.offset) || 0);
    } catch (e) {
      try { toast({ title: 'Failed to load podcasts', description: e?.message || 'Error' }); } catch {}
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => { load(0); /* initial */ }, [token]);

  const onSearch = () => load(0);
  const pages = Math.max(1, Math.ceil(total / limit));
  const pageIdx = Math.floor(offset / limit) + 1;

  const openManager = (podcastId) => {
    try {
      const url = `/dashboard?podcast=${encodeURIComponent(podcastId)}`;
      window.location.href = url;
    } catch {}
  };
  const copyId = async (id) => {
    try { await navigator.clipboard.writeText(id); toast({ title: 'Copied podcast id' }); } catch {}
  };

  return (
    <div className="space-y-4">
      <Card className="border-0 shadow-sm bg-white">
        <CardContent className="p-4 flex items-center gap-3">
          <Input placeholder="Filter by owner email" value={qOwner} onChange={e=>setQOwner(e.target.value)} className="max-w-sm" />
          <Button onClick={onSearch} disabled={loading}>Search</Button>
          <div className="ml-auto text-sm text-gray-500">Total: {total}</div>
        </CardContent>
      </Card>
      <Card className="border-0 shadow-sm bg-white">
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Podcast</TableHead>
                <TableHead>Owner</TableHead>
                <TableHead>Episodes</TableHead>
                <TableHead>Created</TableHead>
                <TableHead>Last Activity</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map(row => (
                <TableRow key={row.id}>
                  <TableCell className="font-medium">{row.name || '—'}</TableCell>
                  <TableCell>{row.owner_email || '—'}</TableCell>
                  <TableCell>{row.episode_count ?? 0}</TableCell>
                  <TableCell>{row.created_at ? formatInTimezone(row.created_at, { dateStyle: 'medium', timeStyle: 'short' }, resolvedTimezone) : '—'}</TableCell>
                  <TableCell>{row.last_episode_at ? formatInTimezone(row.last_episode_at, { dateStyle: 'medium', timeStyle: 'short' }, resolvedTimezone) : '—'}</TableCell>
                  <TableCell className="text-right space-x-2">
                    <Button size="sm" variant="outline" onClick={()=>openManager(row.id)}>Open in Podcast Manager</Button>
                    <Button size="sm" variant="secondary" onClick={()=>copyId(row.id)}>Copy ID</Button>
                  </TableCell>
                </TableRow>
              ))}
              {rows.length === 0 && (
                <TableRow><TableCell colSpan={6} className="text-center text-sm text-gray-500 py-8">{loading ? 'Loading…' : 'No results'}</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
      <div className="flex items-center justify-between">
        <div className="text-sm text-gray-600">Page {pageIdx} of {pages}</div>
        <div className="space-x-2">
          <Button aria-label="Previous page" size="sm" variant="outline" disabled={offset<=0 || loading} onClick={()=>load(Math.max(0, offset - limit))}><ChevronLeft className="w-4 h-4" /></Button>
          <Button aria-label="Next page" size="sm" variant="outline" disabled={offset+limit>=total || loading} onClick={()=>load(offset + limit)}><ChevronRight className="w-4 h-4" /></Button>
        </div>
      </div>
    </div>
  );
}

function AdminBillingTab() {
  const { token } = useAuth();
  const { toast } = useToast();
  const [data, setData] = React.useState(null);
  const [loading, setLoading] = React.useState(false);

  React.useEffect(() => {
    if (!token) return;
    let canceled = false;
    setLoading(true);
    (async () => {
      try {
        const api = makeApi(token);
        const res = await api.get('/api/admin/billing/overview');
        if (!canceled) setData(res);
      } catch (e) {
        try { toast({ title: 'Failed to load billing overview', description: e?.message || 'Error' }); } catch {}
        if (!canceled) setData(null);
      } finally {
        if (!canceled) setLoading(false);
      }
    })();
    return () => { canceled = true; };
  }, [token]);

  const n = (v) => (typeof v === 'number' && isFinite(v) ? v : 0);
  const money = (cents) => (cents == null ? null : (Math.round(cents) / 100));
  const mrr = money(data?.gross_mrr_cents);

  const openStripe = () => {
    const url = data?.dashboard_url;
    if (!url) return;
    try { window.open(url, '_blank', 'noopener,noreferrer'); } catch {}
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold" style={{ color: '#2C3E50' }}>Billing Overview</h3>
          <p className="text-gray-600">Stripe-derived subscription metrics</p>
        </div>
        <Button onClick={openStripe} disabled={!data?.dashboard_url} className="text-white" style={{ backgroundColor: '#2C3E50' }}>
          <CreditCard className="w-4 h-4 mr-2" />
          Open Stripe Dashboard
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-6">
        <Card className="border-0 shadow-sm bg-white">
          <CardContent className="p-6">
            <div className="text-sm text-gray-500">Active Subscriptions</div>
            <div className="text-3xl font-bold" style={{ color: '#2C3E50' }}>{n(data?.active_subscriptions)}</div>
          </CardContent>
        </Card>
        <Card className="border-0 shadow-sm bg-white">
          <CardContent className="p-6">
            <div className="text-sm text-gray-500">Trialing</div>
            <div className="text-3xl font-bold" style={{ color: '#2C3E50' }}>{n(data?.trialing)}</div>
          </CardContent>
        </Card>
        <Card className="border-0 shadow-sm bg-white">
          <CardContent className="p-6">
            <div className="text-sm text-gray-500">Canceled (30d)</div>
            <div className="text-3xl font-bold" style={{ color: '#2C3E50' }}>{n(data?.canceled_last_30d)}</div>
          </CardContent>
        </Card>
        <Card className="border-0 shadow-sm bg-white">
          <CardContent className="p-6">
            <div className="text-sm text-gray-500">Trials expiring (7d)</div>
            <div className="text-3xl font-bold" style={{ color: '#2C3E50' }}>{n(data?.trial_expiring_7d)}</div>
          </CardContent>
        </Card>
        <Card className="border-0 shadow-sm bg-white">
          <CardContent className="p-6">
            <div className="text-sm text-gray-500">Gross MRR</div>
            <div className="text-3xl font-bold" style={{ color: '#2C3E50' }}>
              {mrr != null ? (
                <>${n(mrr).toLocaleString()}</>
              ) : (
                <Badge variant="secondary">—</Badge>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {loading && <div className="text-sm text-gray-500">Loading…</div>}
    </div>
  );
}

function AdminHelpTab() {
  const [health, setHealth] = React.useState({ ok: null, detail: null });

  React.useEffect(() => {
    let canceled = false;
    (async () => {
      try {
        const res = await fetch(buildApiUrl('/api/health'));
        const ok = res.ok;
        let detail = null;
        try { detail = await res.json(); } catch {}
        if (!canceled) setHealth({ ok, detail });
      } catch {
        if (!canceled) setHealth({ ok: false, detail: null });
      }
    })();
    return () => { canceled = true; };
  }, []);

  const badge = (ok) => {
    if (ok === true) return <Badge className="bg-green-100 text-green-800">OK</Badge>;
    if (ok === false) return <Badge className="bg-red-100 text-red-800">DOWN</Badge>;
    return <Badge variant="secondary">Unknown</Badge>;
  };

  const links = [
    { label: 'System Health', href: '/api/health', desc: 'Raw health endpoint' },
    { label: 'Job Queue', href: '#/admin/jobs', desc: 'Queue status and workers' },
    { label: 'Database Explorer Guide', href: '#/docs/db-explorer', desc: 'How to safely use DB Explorer' },
    { label: 'Support Inbox', href: '#/support', desc: 'Contact support' },
  ];

  return (
    <div className="space-y-6">
      <Card className="border-0 shadow-sm bg-white">
        <CardContent className="p-6 flex items-center justify-between">
          <div>
            <div className="text-sm text-gray-500">API Health</div>
            <div className="text-xl font-semibold" style={{ color: '#2C3E50' }}>Platform Status</div>
          </div>
          {badge(health.ok)}
        </CardContent>
      </Card>

      <Card className="border-0 shadow-sm bg-white">
        <CardHeader>
          <CardTitle style={{ color: '#2C3E50' }}>Quick Links</CardTitle>
        </CardHeader>
        <CardContent className="divide-y">
          {links.map((l, i) => (
            <div key={i} className="flex items-center justify-between py-3">
              <div>
                <div className="font-medium text-gray-800">{l.label}</div>
                <div className="text-sm text-gray-500">{l.desc}</div>
              </div>
              <a
                href={l.href}
                target={l.href.startsWith('http') || l.href.startsWith('/api/') ? '_blank' : undefined}
                rel="noopener noreferrer"
                className="text-blue-600 hover:underline text-sm"
              >Open</a>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
